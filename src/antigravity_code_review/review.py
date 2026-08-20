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
from antigravity_code_review.config import GITHUB_MCP_TOOLS, build_config
from antigravity_code_review.github import (
    get_pull_request,
    list_changed_files,
    rescue_pending_review,
)
from antigravity_code_review.guards import compare_allowlist, is_fork
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
    config = build_config(project, workspace, app_data_dir)

    async with Agent(config) as agent:
        # Validate the MCP allowlist before the first model call. M0 recorded
        # that the SDK exposes names the server does not have, and that finding
        # out through a failed call costs a model call. This costs nothing.
        advertised = await _advertised_tools(agent)
        if advertised is not None:
            drift = compare_allowlist(GITHUB_MCP_TOOLS, advertised)
            print(f"MCP allowlist: {drift.message}")
            if not drift.ok:
                print("FAIL: MCP allowlist does not match the server.", file=sys.stderr)
                return 2

        response = await agent.chat(seed)
        text = (await response.text()).strip()
        stop = response.stop_reason
        usage = read_usage(agent.conversation.total_usage)

    print(f"stop: {stop}")
    print(format_usage(usage))
    print(f"agent said: {text[:300]}")

    # Q8: a stopped session leaves a PENDING review holding real comments and
    # zero visible ones. Publishing it is the runner's job either way, but on a
    # non-normal stop the body has to say why it ended.
    if stop is not None and stop != types.StopReason.UNSPECIFIED:
        published = rescue_pending_review(repo, number, str(stop))
        print(f"stopped early ({stop}); pending review published: {published}")

    return 0


async def _advertised_tools(agent: Agent) -> list[str] | None:
    """Best-effort read of what the MCP server actually offers.

    Returns None when the SDK gives us no way to ask, so a missing introspection
    surface degrades to "unvalidated" rather than to a false failure.
    """
    for attr in ("mcp_tools", "list_mcp_tools", "tools"):
        source = getattr(agent, attr, None)
        if source is None:
            continue
        value = source() if callable(source) else source
        if asyncio.iscoroutine(value):
            value = await value
        if value:
            return [getattr(t, "name", str(t)) for t in value]
    return None


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
