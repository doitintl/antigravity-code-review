"""Run a named configuration against a fixture, N times, and price each run.

Three properties this module is built around.

**It drives the reviewer, not a copy of it.** `run_passes` is imported from
`review.py`. A harness that reimplements the pipeline measures the
reimplementation, which is the exact failure mode M5 exists to end.

**It reviews the pinned commit.** The changed-file list comes from
`compare(base_sha...head_sha)`, never from the pull request's current files. The
first real comparison this project ran used the live PR and was two fix commits
past the reviewed code; it looked like a recall failure and was a methodology
error.

**It repeats.** N runs per configuration per fixture, N ≥ 3, because one sample
cannot see the ±1 finding swing that has already exceeded every intervention
tested against it.

Checkouts are cached by `(repo, sha)`. A pinned commit does not change, so
fetching it three times is three times the wait for the same bytes — and a
harness that is slow to run will not be run.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from antigravity_code_review.collect_usage import UsageCollector
from antigravity_code_review.collector import format_file_line
from antigravity_code_review.config import (
    CONTRACT_PASSES,
    JUDGE_INSTRUCTIONS,
    PASS_INSTRUCTIONS,
)
from antigravity_code_review.cost import price_session
from antigravity_code_review.evalharness.findings import parse_findings
from antigravity_code_review.evalharness.fixtures import Fixture
from antigravity_code_review.evalharness.report import MIN_RUNS, RunRecord
from antigravity_code_review.evalharness.runs import classify, combine
from antigravity_code_review.evalharness.scoring import score_run
from antigravity_code_review.rates import FLASH

CACHE = Path(os.environ.get("AGY_EVAL_CACHE", ".eval-cache")).resolve()


class RunnerError(RuntimeError):
    """The fixture could not be prepared. Raised rather than reviewed anyway.

    A review of the wrong tree produces a number, and the number looks fine.
    """


@dataclass(frozen=True)
class Configuration:
    """A named, comparable reviewer configuration (FR8).

    `judge_instructions=None` runs the passes with no judging step, which is
    one of the comparisons M5 was built to settle: the judge reported 1 of 4
    known defects from passes that had surfaced all four, and whether it helps
    at all has never been measured over repeated runs.
    """

    name: str
    passes: tuple[tuple[str, str], ...] = tuple(CONTRACT_PASSES)
    pass_instructions: str = PASS_INSTRUCTIONS
    judge_instructions: str | None = JUDGE_INSTRUCTIONS


CONTRACT_PASSES_WITH_JUDGE = Configuration(name="contract-passes+judge")
CONTRACT_PASSES_NO_JUDGE = Configuration(name="contract-passes-only", judge_instructions=None)

CONFIGURATIONS = {c.name: c for c in (CONTRACT_PASSES_WITH_JUDGE, CONTRACT_PASSES_NO_JUDGE)}


def _gh(path: str) -> Any:
    result = subprocess.run(
        ["gh", "api", path, "--paginate"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RunnerError(f"gh api {path} failed: {result.stderr.strip()}")
    return json.loads(result.stdout) if result.stdout.strip() else None


def changed_files(fixture: Fixture) -> list[dict[str, Any]]:
    """The files changed between the fixture's two pinned SHAs.

    `base...head` three-dot compare, so the answer is the change as reviewed
    rather than everything that has landed on the base branch since.
    """
    compare = _gh(f"repos/{fixture.repo}/compare/{fixture.base_sha}...{fixture.head_sha}")
    files = compare.get("files") if isinstance(compare, dict) else None
    if not files:
        raise RunnerError(
            f"{fixture.name}: no changed files between {fixture.base_sha[:8]} and "
            f"{fixture.head_sha[:8]}. A fixture with nothing to review measures nothing."
        )
    return files


def checkout(fixture: Fixture, cache: Path = CACHE) -> Path:
    """Materialise the fixture's head commit, reusing a cached checkout.

    Blobless clone: the reviewer opens a handful of files out of a tree that can
    hold thousands, and fetching every blob to review 21 of them is most of the
    wall clock for none of the benefit.
    """
    target = cache / fixture.repo.replace("/", "__") / fixture.head_sha
    marker = target / ".agy-checkout-ok"
    if marker.exists():
        return target

    target.mkdir(parents=True, exist_ok=True)
    steps = [
        ["git", "init", "-q"],
        ["git", "remote", "add", "origin", f"https://github.com/{fixture.repo}.git"],
        # gh already holds the token; this keeps it out of the remote URL and
        # out of any process listing.
        ["git", "config", "credential.helper", "!gh auth git-credential"],
        ["git", "fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", fixture.head_sha],
        ["git", "checkout", "-q", "FETCH_HEAD"],
    ]
    for step in steps:
        result = subprocess.run(step, cwd=target, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RunnerError(
                f"{fixture.name}: {' '.join(step[:3])} failed in {target}: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
    marker.write_text(fixture.head_sha, encoding="utf-8")
    return target


async def run_once(
    fixture: Fixture,
    configuration: Configuration,
    *,
    project: str,
    files: list[dict[str, Any]] | None = None,
    workspace: Path | None = None,
) -> RunRecord:
    """One run of one configuration against one fixture, scored and priced."""
    from antigravity_code_review.review import run_passes

    entries = files if files is not None else changed_files(fixture)
    tree = workspace if workspace is not None else checkout(fixture)
    patches = {f["filename"]: f["patch"] for f in entries if f.get("patch")}
    listing = "\n".join(format_file_line(f) for f in entries)

    collector = UsageCollector()
    os.environ["AGY_WORKSPACE"] = str(tree)

    raw, outcomes = await run_passes(
        project=project,
        workspace=str(tree),
        patches=patches,
        listing=listing,
        subject=(
            f"A change at commit {fixture.head_sha[:8]} touches {len(entries)} files"
        ),
        collector=collector,
        passes=configuration.passes,
        pass_instructions=configuration.pass_instructions,
        judge_instructions=configuration.judge_instructions,
    )

    outcome = combine(outcomes)
    findings = parse_findings("\n".join(json.dumps(f) for f in raw))
    priced = price_session(collector.turns, FLASH, datetime.now(tz=timezone.utc).date())

    return RunRecord(
        score=score_run(
            fixture, findings, configuration=configuration.name, outcome=outcome
        ),
        cost_usd=priced.cost_usd,
        cost_reason=None if priced.cost_usd is not None else "no rate resolved for every turn",
        tokens=priced.tokens_total,
        tool_calls=collector.tool_calls,
    )


async def run_configuration(
    fixtures: Sequence[Fixture],
    configuration: Configuration,
    *,
    project: str,
    runs: int = MIN_RUNS,
) -> list[RunRecord]:
    """Run one configuration `runs` times against every fixture.

    `runs` defaults to the report's own floor rather than to 1. A default of one
    would make the cheap thing the misleading thing, and the misleading thing
    has already been done here three times.

    A run that raises is recorded as an incomplete run rather than dropped. A
    harness that loses its failures reports the recall of the runs that
    happened to work.
    """
    if runs < MIN_RUNS:
        print(
            f"WARNING: runs={runs}, below the floor of {MIN_RUNS}. One sample cannot "
            "see a plus-or-minus-one finding swing."
        )

    records: list[RunRecord] = []
    for fixture in fixtures:
        entries = changed_files(fixture)
        tree = checkout(fixture)
        for index in range(runs):
            print(f"\n=== {configuration.name} | {fixture.name} | run {index + 1}/{runs} ===")
            try:
                record = await run_once(
                    fixture,
                    configuration,
                    project=project,
                    files=entries,
                    workspace=tree,
                )
            except Exception as exc:  # noqa: BLE001 - a lost run must not be a silent one
                print(f"   RUN FAILED: {type(exc).__name__}: {exc}")
                record = RunRecord(
                    score=score_run(
                        fixture,
                        [],
                        configuration=configuration.name,
                        outcome=classify(None, error=f"{type(exc).__name__}: {exc}"),
                    ),
                    cost_usd=None,
                    cost_reason="the run raised before it could be priced",
                )
            records.append(record)
            hits = f"{record.score.hits}/{len(record.score.matches)}"
            money = "cost unknown" if record.cost_usd is None else f"${record.cost_usd:.4f}"
            state = "INCOMPLETE" if record.score.incomplete else "complete"
            print(f"   {state}: {hits} found, {money}")
    return records
