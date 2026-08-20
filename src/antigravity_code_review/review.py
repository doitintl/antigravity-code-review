"""Entrypoint: review one pull request.

The shape of this file is the design in miniature — collect metadata only, let
the agent pull what it wants through capped tools, and have the *runner* publish
the result rather than the agent.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile

from google.antigravity import Agent, types

from antigravity_code_review.collector import format_seed
from antigravity_code_review.config import GITHUB_MCP_IMAGE, GITHUB_MCP_TOOLS, build_config
from antigravity_code_review.github import (
    get_pull_request,
    list_changed_files,
    publish_pending_review,
)
from antigravity_code_review.guards import compare_allowlist, is_fork
from antigravity_code_review.mcp_preflight import McpUnavailable, alist_server_tools
from antigravity_code_review.usage import format_usage, read_usage


async def review(repo: str, number: int, project: str) -> int:
    pr = get_pull_request(repo, number)

    # Belt and braces with the workflow's own gate: a fork PR cannot reach
    # Vertex, and saying so beats an authentication error nobody can read.
    if is_fork(pr):
        print(f"SKIPPED: #{number} comes from a fork; no identity federation is available.")
        return 0

    files = list_changed_files(repo, number)
    seed = format_seed(pr, files)
    print(f"collected {len(files)} changed files, seed is {len(seed)} chars")

    workspace = os.getcwd()
    app_data_dir = tempfile.mkdtemp(prefix="agy-review-", dir=tempfile.gettempdir())
    owner, _, repo_name = repo.partition("/")
    config = build_config(project, workspace, app_data_dir, owner, repo_name, number)

    # FR7 preflight. Done before the agent is constructed, so a wrong tool name
    # costs a subprocess rather than a model call and a full-context retry. The
    # SDK exposes no way to ask, so this speaks MCP to the container directly.
    try:
        advertised = await alist_server_tools(
            GITHUB_MCP_IMAGE, os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
        )
        drift = compare_allowlist(GITHUB_MCP_TOOLS, advertised)
        print(f"MCP preflight: server offers {len(advertised)} tools; {drift.message}")
        if not drift.ok:
            print("FAIL: configured MCP tools are not offered by the server.", file=sys.stderr)
            return 2
    except McpUnavailable as exc:
        # A missing runtime is not a mismatched allowlist. Say which.
        print(f"MCP preflight skipped: {exc}")

    async with Agent(config) as agent:
        response = await agent.chat(seed)
        text = (await response.text()).strip()
        stop = response.stop_reason
        usage = read_usage(agent.conversation.total_usage)

    print(f"stop: {stop}")
    print(format_usage(usage))
    print(f"agent said: {text[:300]}")

    # Q8: a pending review is invisible to everyone but the account that opened
    # it, which in CI is github-actions[bot]. So the runner publishes it on
    # EVERY path, not only when the agent stopped early — a clean run that
    # nobody submits is a review nobody can read.
    normal = stop is None or stop == types.StopReason.UNSPECIFIED
    published = publish_pending_review(repo, number, str(stop), normal=normal)
    print(f"pending review published: {published} (normal stop: {normal})")
    if not published:
        print("WARNING: the agent left no pending review, so nothing was posted.")

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
