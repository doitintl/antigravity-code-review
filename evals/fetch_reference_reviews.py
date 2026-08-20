"""Fetch `claude[bot]`'s review comments for a fixture pull request, verbatim.

The reference review is what the scorer is validated against (AC3). A scorer
that cannot find a fixture's known defects in an independent reviewer's own text
reports a false zero for everything — which has already happened once here, when
keyword matching on `"page type"` scored a judge that wrote `"pages"` as a miss.

Verbatim and refetched rather than transcribed, so the validation set cannot
drift into paraphrases of what we hoped was written.

    uv run python evals/fetch_reference_reviews.py <owner>/<repo> <pr> <sha> <name>

Output lands in `evals/reference/`, which is gitignored. This repository is
public and the pull requests it measures are not; the fetcher is committed, the
fetched text never is.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REFERENCE_DIR = Path(__file__).parent / "reference"


def fetch(repo: str, number: int, at_sha: str | None = None) -> list[dict]:
    """Return the review comments left by `claude[bot]`, optionally pinned."""
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}/pulls/{number}/comments?per_page=100", "--paginate"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    comments = []
    for c in json.loads(out):
        if "claude" not in (c.get("user") or {}).get("login", ""):
            continue
        commit = c.get("original_commit_id") or ""
        if at_sha and not commit.startswith(at_sha):
            continue
        comments.append(
            {
                "id": c["id"],
                "path": c["path"],
                "line": c.get("line") or c.get("original_line"),
                "commit": commit,
                "body": c["body"],
            }
        )
    return comments


def main() -> int:
    if len(sys.argv) < 4:
        raise SystemExit("usage: fetch_reference_reviews.py <owner/repo> <pr> <sha> [name]")
    repo, number, sha = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    name = sys.argv[4] if len(sys.argv) > 4 else f"{repo.split('/')[-1]}-{number}"

    comments = fetch(repo, number, sha)
    if not comments:
        raise SystemExit(f"FAIL: no claude[bot] comments on {repo}#{number} at {sha}")

    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    target = REFERENCE_DIR / f"{name}.json"
    target.write_text(
        json.dumps(
            {"repo": repo, "pr": number, "sha": sha, "reviewer": "claude[bot]", "comments": comments},
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote {target} — {len(comments)} comment(s) at {sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
