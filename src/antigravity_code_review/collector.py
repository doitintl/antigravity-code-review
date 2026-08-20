"""Build the prompt seed: what the reviewer is told before it reads anything.

The pull-context strategy lives or dies here. The seed carries pull request
metadata and one line per changed file — **never file contents and never diff
hunks**. GitHub's files API returns a `patch` field on most entries, and
interpolating it would silently reintroduce the failure this project exists to
avoid: a 2.9 MB generated file crowding out the review of everything else.

The agent fetches the content it actually wants through `view_file`, which is
byte-capped. That is the difference between a reviewer with a cliff and one with
a slope.
"""

from __future__ import annotations

from typing import Any

# Fields on a GitHub file entry that carry content rather than metadata. Named
# explicitly so that adding a field to the seed is a deliberate act.
CONTENT_FIELDS = ("patch", "content", "blob", "raw_url_content")


def format_file_line(entry: dict[str, Any]) -> str:
    """Render one changed file as a single metadata line.

    Reads only the metadata keys by name. `patch` is never touched, which is why
    this takes the fields it wants rather than iterating over what it was given.
    """
    path = entry.get("filename", "<unknown>")
    status = entry.get("status", "modified")
    additions = entry.get("additions") or 0
    deletions = entry.get("deletions") or 0
    sha = entry.get("sha") or "-"

    # Patch size is carried so the agent can triage before opening anything.
    # Without it a 2.9 MB generated artefact is indistinguishable from a
    # forty-line source file, and the agent opens both.
    patch = entry.get("patch")
    if patch is None:
        diff_note = "no diff available — too large to review"
    else:
        diff_note = f"diff {len(patch):,}B"

    line = f"- {path} ({status}, +{additions}/-{deletions}, {diff_note}, {sha})"

    previous = entry.get("previous_filename")
    if previous:
        line += f" [renamed from {previous}]"
    return line


def format_seed(pr: dict[str, Any], files: list[dict[str, Any]]) -> str:
    """Render the full prompt seed for a pull request."""
    title = pr.get("title") or "(no title)"
    body = (pr.get("body") or "").strip() or "(no description)"
    base = (pr.get("base") or {}).get("ref", "?")
    head = (pr.get("head") or {}).get("ref", "?")
    number = pr.get("number", "?")

    lines = [
        f"Pull request #{number}: {title}",
        f"Merging {head} into {base}",
        "",
        "Description:",
        body,
        "",
    ]

    if not files:
        lines.append("Changed files: none reported (0 files).")
    else:
        lines.append(f"Changed files ({len(files)}):")
        lines.extend(format_file_line(f) for f in files)

    lines += [
        "",
        (
            "File contents are deliberately not included. Use view_diff to see "
            "what changed in a file — that is what you are reviewing. Use "
            "view_file only when you need surrounding context the diff does not "
            "show; it is byte-capped and reads from the top of the file, which "
            "for a large file is unlikely to be where the change is."
        ),
    ]
    return "\n".join(lines)
