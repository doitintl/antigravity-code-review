"""Entrypoint: review one pull request.

Three stages, and the split is the point.

**Passes describe.** Three named contract questions over the diff — where is each
added field written versus read, what uniqueness is assumed versus guaranteed,
can each side effect fire twice. Asked to "review this pull request" the reviewer
surfaced 0 of 4 known defects on a real 21-file change, under every precision bar
tried and at four times the reasoning budget. Asked these, it surfaced 3 to 4.

**The judge decides.** The passes annotate real defects as "by design" when left
to rule on their own, so a separate step opens the files and decides, and must
quote the guard to call something intended.

**The runner posts.** The agent never posts. It emits structured findings — file,
line, claim — and the runner turns those into review comments and submits.

That last part reverses M1's decision to post through the GitHub MCP server, and
the reversal is deliberate. Incremental MCP posting cost turns the reviewer did
not have: it invented a `create_pending` method, tripped "only one pending review
per pull request" whenever a run failed part-way, and duplicated comments across
retries. Q8's finding survives intact — a stopped run must still publish what it
found — but the runner can do that from structured findings more reliably than
the agent can do it from a tool it keeps mis-calling. It also gives M5 the
structured records it needs to score recall by location rather than by wording.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.antigravity import Agent, LocalAgentConfig, types

from antigravity_code_review.collect_usage import UsageCollector
from antigravity_code_review.collector import format_file_line
from antigravity_code_review.config import (
    CONTRACT_PASSES,
    JUDGE_INSTRUCTIONS,
    LOCATION,
    PASS_INSTRUCTIONS,
    REVIEW_TOOLS,
)
from antigravity_code_review.cost import price_session
from antigravity_code_review.github import (
    get_pull_request,
    list_changed_files,
    post_review,
)
from antigravity_code_review.guards import is_fork
from antigravity_code_review.rates import FLASH
from antigravity_code_review.report import cost_artifact, cost_line, review_body
from antigravity_code_review.tools import make_view_diff, view_file

# A pull request too small to be worth a review. A one-line typo fix should not
# cost thirty cents; the check costs nothing because the file list is already in
# hand before any model call.
TRIVIAL_MAX_CHANGES = 3
TRIVIAL_MAX_FILES = 1


def is_trivial(files: list[dict[str, Any]]) -> str | None:
    """Return a reason to skip, or None to proceed."""
    if not files:
        return "no files changed"
    reviewable = [f for f in files if f.get("patch")]
    if not reviewable:
        return "no reviewable diffs (all changed files are generated or too large)"
    if len(reviewable) <= TRIVIAL_MAX_FILES:
        changes = sum((f.get("additions") or 0) + (f.get("deletions") or 0) for f in reviewable)
        if changes <= TRIVIAL_MAX_CHANGES:
            return f"trivial change ({changes} lines in {len(reviewable)} file)"
    return None


def _agent_config(project: str, workspace: str, instructions: str, patches: dict, hooks: list):
    return LocalAgentConfig(
        vertex=True,
        project=project,
        location=LOCATION,
        model=FLASH,
        system_instructions=instructions,
        tools=[view_file, make_view_diff(patches)],
        hooks=hooks,
        capabilities=types.CapabilitiesConfig(
            enabled_tools=list(REVIEW_TOOLS),
            enable_subagents=False,
            agent_behavior=types.AgentBehavior.AUTONOMOUS,
            compaction_threshold=300_000,
        ),
        workspaces=[workspace],
        app_data_dir=tempfile.mkdtemp(prefix="agy-review-", dir=tempfile.gettempdir()),
        budget_config=types.BudgetConfig(
            max_input_tokens=900_000,
            max_output_tokens=30_000,
            max_tool_calls=80,
        ),
        retry_config=types.RetryConfig(
            model_output_retry=types.ModelOutputRetryConfig(max_retries=1)
        ),
    )


async def _run(cfg, prompt: str, collector: UsageCollector) -> tuple[str, Any]:
    async with Agent(cfg) as agent:
        collector.bind(agent.conversation)
        response = await agent.chat(prompt)
        text = (await response.text()).strip()
        collector.record_cumulative(agent.conversation.total_usage)
    return text, response.stop_reason


def parse_findings(text: str) -> list[dict[str, Any]]:
    """Parse the judge's JSON-per-line output, tolerantly.

    Tolerantly because a model asked for bare JSON will sometimes wrap it in a
    markdown fence anyway, and losing every finding to a stray ``` would be an
    expensive way to be strict.
    """
    findings = []
    for raw in text.splitlines():
        line = raw.strip().removeprefix("```json").removeprefix("```").strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if obj.get("file") and obj.get("claim"):
            findings.append(
                {
                    "file": str(obj["file"]),
                    "line": int(obj["line"]) if str(obj.get("line", "")).isdigit() else None,
                    "claim": str(obj["claim"]),
                }
            )
    return findings


async def review(repo: str, number: int, project: str) -> int:
    pr = get_pull_request(repo, number)

    if is_fork(pr):
        print(f"SKIPPED: #{number} comes from a fork; no identity federation is available.")
        return 0

    files = list_changed_files(repo, number)
    skip = is_trivial(files)
    if skip:
        print(f"SKIPPED: {skip}. No review posted.")
        return 0

    patches = {f["filename"]: f["patch"] for f in files if f.get("patch")}
    listing = "\n".join(format_file_line(f) for f in files)
    print(f"collected {len(files)} changed files, diffs for {len(patches)}")

    workspace = os.getcwd()
    os.environ.setdefault("AGY_WORKSPACE", workspace)
    collector = UsageCollector()
    reports, incomplete = [], []

    for name, question in CONTRACT_PASSES:
        print(f"[pass] {name}")
        cfg = _agent_config(project, workspace, PASS_INSTRUCTIONS, patches, collector.hooks())
        prompt = (
            f"Pull request #{number} changes {len(files)} files:\n{listing}\n\n"
            f"YOUR AUDIT QUESTION:\n{question}\n"
        )
        try:
            text, stop = await _run(cfg, prompt, collector)
        except Exception as exc:  # noqa: BLE001 - a dead pass must not lose the others
            print(f"   FAILED: {type(exc).__name__}: {exc}")
            incomplete.append(name)
            continue
        normal = stop is None or stop == types.StopReason.UNSPECIFIED
        if not normal and not text:
            # Q8: a budget stop returns empty text, which reads exactly like a
            # clean pass. Never let that count as "nothing found".
            print(f"   INCOMPLETE ({stop}) — empty output, not a clean result")
            incomplete.append(name)
            continue
        print(f"   {len(text)} chars")
        reports.append(f"### {name}\n{text}")

    findings: list[dict[str, Any]] = []
    if reports:
        print("[judge] deciding which described properties are defects")
        cfg = _agent_config(project, workspace, JUDGE_INSTRUCTIONS, patches, collector.hooks())
        try:
            text, stop = await _run(cfg, "AUDIT REPORT:\n\n" + "\n\n".join(reports)[:200_000], collector)
            findings = parse_findings(text)
            print(f"   {len(findings)} defect(s)")
        except Exception as exc:  # noqa: BLE001 - losing the judge must not lose the cost record
            print(f"   FAILED: {type(exc).__name__}: {exc}")
            incomplete.append("judge")

    priced = price_session(collector.turns, FLASH, datetime.now(tz=timezone.utc).date())
    print(cost_line(priced, tool_calls=collector.tool_calls))

    body = review_body(
        priced,
        tool_calls=collector.tool_calls,
        model=FLASH,
        findings=len(findings),
        stop_reason=f"{len(incomplete)} incomplete pass(es): {', '.join(incomplete)}"
        if incomplete
        else None,
    )
    posted = post_review(repo, number, findings, body)
    print(f"posted review with {posted} inline comment(s)")

    artifact = cost_artifact(
        priced,
        repo=repo,
        pr=number,
        model=FLASH,
        tool_calls=collector.tool_calls,
        compactions=collector.compactions,
        retries={"api": 0, "model_output": 0},
    )
    artifact["findings"] = findings
    artifact["incomplete_passes"] = incomplete
    Path("review-cost.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print("wrote review-cost.json")
    return 0


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY")
    number = os.environ.get("PR_NUMBER")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    missing = [
        n
        for n, v in (
            ("GITHUB_REPOSITORY", repo),
            ("PR_NUMBER", number),
            ("GOOGLE_CLOUD_PROJECT", project),
        )
        if not v
    ]
    if missing:
        raise SystemExit(f"FAIL: missing environment: {', '.join(missing)}")
    assert repo and number and project  # narrowed by the check above
    return asyncio.run(review(repo, int(number), project))


if __name__ == "__main__":
    sys.exit(main())
