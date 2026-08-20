"""Read a pull request from the GitHub API.

Deliberately thin. The reviewer posts through the GitHub MCP server, so the only
GitHub code here is what the collector needs before the agent starts, plus the
runner-owned submit that MCP cannot do for us.

Field names are taken from an observed payload rather than from documentation —
`docs/probe-results.md` records the shape actually returned for the fixture PR.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any


class GitHubError(RuntimeError):
    """A GitHub API call failed. Raised rather than returning an empty result.

    An empty changed-file list and a failed request look identical downstream,
    and one of them would produce a confident review of nothing.
    """


def _api(path: str, method: str = "GET", body: dict[str, Any] | None = None) -> Any:
    """Call the GitHub API via `gh`, which already holds the runner's token."""
    cmd = ["gh", "api", "-X", method, path]
    if body is not None:
        cmd += ["--input", "-"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            input=json.dumps(body) if body is not None else None,
            env={**os.environ},
        )
    except subprocess.CalledProcessError as exc:
        raise GitHubError(f"{method} {path} failed: {exc.stderr.strip()}") from exc
    return json.loads(result.stdout) if result.stdout.strip() else None


def get_pull_request(repo: str, number: int) -> dict[str, Any]:
    """Fetch pull request metadata."""
    return _api(f"repos/{repo}/pulls/{number}")


def list_changed_files(repo: str, number: int) -> list[dict[str, Any]]:
    """Fetch the changed-file list, following pagination.

    Paginated deliberately: a PR touching more than 30 files would otherwise be
    reviewed against a silently partial list, which is the same class of failure
    as a silently truncated file.
    """
    files: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = _api(f"repos/{repo}/pulls/{number}/files?per_page=100&page={page}")
        if not batch:
            break
        files.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return files


def find_pending_review(repo: str, number: int) -> dict[str, Any] | None:
    """Return this actor's PENDING review on the PR, if one exists.

    Q8 established the reason this matters: a budget-stopped session leaves a
    PENDING review carrying real comments but zero visible ones — invisible to
    everybody until something submits it. The runner is that something.
    """
    for review in _api(f"repos/{repo}/pulls/{number}/reviews") or []:
        if review.get("state") == "PENDING":
            return review
    return None


def submit_review(repo: str, number: int, review_id: int, body: str, event: str = "COMMENT") -> Any:
    """Submit a pending review.

    `event` stays COMMENT rather than REQUEST_CHANGES or APPROVE. An automated
    reviewer that can block a merge is a different product with a different
    failure mode, and approving on the strength of an agent's read is worse.
    """
    return _api(
        f"repos/{repo}/pulls/{number}/reviews/{review_id}/events",
        method="POST",
        body={"body": body, "event": event},
    )


def rescue_pending_review(repo: str, number: int, stop_reason: str) -> bool:
    """Publish whatever the agent had written when it stopped.

    Called on any non-UNSPECIFIED stop. Returns True when a review was
    published. The stop reason goes in the body verbatim, because a review that
    ends early and does not say so reads as a complete review that found little.
    """
    review = find_pending_review(repo, number)
    if review is None:
        return False
    body = (
        f"_This review was submitted by the runner after the agent stopped: "
        f"`{stop_reason}`. Findings above are what it had recorded by that point "
        f"and may be incomplete._"
    )
    submit_review(repo, number, review["id"], body)
    return True
