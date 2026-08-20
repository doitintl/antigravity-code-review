"""Build a fixture skeleton from a pull request that another reviewer has reviewed.

Curation is the expensive part of an eval set, and the mitigation the spec names
is to start from pull requests where findings are already recorded and were
produced independently. This script does the mechanical half of that:

- resolves the **commit the reference reviewer actually saw**, which is almost
  never the pull request head. The first real comparison this project ran used
  the head, two fix commits later than the reviewed code, and read as a recall
  failure while measuring different source;
- resolves the **merge base** at that commit, so `base...head` is the change as
  reviewed rather than the change as it stands today;
- emits one defect stub per reference comment, pre-filled with file and line.

The two fields it deliberately leaves blank are `class` and `reachable`. Both
are judgements. A script that guessed at them would produce a fixture whose
provenance nobody can reconstruct, which is the failure the format exists to
prevent — so `load_fixture` rejects the stub until a human fills them in.

    uv run python evals/curate_fixture.py <owner>/<repo> <pr> > evals/fixtures/<name>.json

Output names a repository and its files, so it belongs in `evals/fixtures/`,
which is gitignored. This repository is public; the code it measures is not.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

REFERENCE_LOGIN = "claude"


def _api(path: str):
    out = subprocess.run(
        ["gh", "api", path, "--paginate"], capture_output=True, text=True, check=True
    ).stdout
    return json.loads(out) if out.strip() else None


def _summarise(body: str) -> str:
    """First sentence of a review comment, with the reasoning fold removed."""
    head = body.split("<details>")[0].strip()
    head = re.sub(r"^[^\w`]*", "", head)          # strip a leading severity emoji
    head = re.sub(r"\s+", " ", head)
    return head[:400]


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit("usage: curate_fixture.py <owner/repo> <pr> [name]")
    repo, number = sys.argv[1], int(sys.argv[2])
    name = sys.argv[3] if len(sys.argv) > 3 else f"{repo.split('/')[-1]}-{number}"

    comments = [
        c
        for c in _api(f"repos/{repo}/pulls/{number}/comments?per_page=100")
        if REFERENCE_LOGIN in (c.get("user") or {}).get("login", "")
    ]
    if not comments:
        raise SystemExit(f"FAIL: no {REFERENCE_LOGIN} review comments on {repo}#{number}")

    # The commit the reference reviewer saw, not the pull request head.
    head_sha = comments[0]["original_commit_id"]
    base_branch = _api(f"repos/{repo}/pulls/{number}")["base"]["sha"]
    base_sha = _api(f"repos/{repo}/compare/{base_branch}...{head_sha}")["merge_base_commit"]["sha"]

    at_review = [c for c in comments if c["original_commit_id"] == head_sha]
    print(
        f"# {len(at_review)} of {len(comments)} comment(s) are at {head_sha[:8]}",
        file=sys.stderr,
    )

    fixture = {
        "name": name,
        "repo": repo,
        "pr": number,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "reference_review": f"{name}.json",
        "notes": "TODO: how this fixture was curated, and anything excluded from it.",
        "defects": [
            {
                "id": f"{name}-{i + 1}",
                "file": c["path"],
                "line": c.get("line") or c.get("original_line"),
                "class": "",       # TODO: local | cross-file | convention | security
                "description": _summarise(c["body"]),
                "reachable": "",   # TODO: evidence that this can actually manifest
            }
            for i, c in enumerate(at_review)
        ],
    }
    print(json.dumps(fixture, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
