"""A finding as a record: file, line, claim — not prose.

**This is FR3, and it exists because scoring free text produced a false zero.**
A keyword scorer looking for `"page type"` was run against a judge that had
written `"pages"`, and reported 0 findings where the truth was one known defect
correctly identified plus one nobody else had found. That was the third time in
this investigation that an instrument, rather than the reviewer, produced the
headline number — and all three made the reviewer look worse than it was.

Records fix the class of error rather than the instance. Matching on **location**
is robust to wording by construction; the claim text is then only ever used to
disambiguate two findings at the same place.

Two tolerances are deliberate:

**A range.** A finding about a function is about a span. Recording only its first
line and then demanding an exact match measures transcription.

**A near miss.** A reviewer that says line 214 about a defect recorded at 216 has
found it. Line numbers shift with the diff a reader is looking at, and a scorer
that treats two lines of drift as a miss is measuring the wrong thing.

The parser is tolerant on purpose. Asked for bare JSON a model will sometimes
wrap it in a fence, sometimes emit an array, sometimes write the line number as
a string. Losing a whole run's findings to a stray ``` would be an expensive way
to be strict — and, given what an eval harness is for, a silent one.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

# `a/` and `b/` are unified-diff prefixes; `./` comes off a shell. None of them
# is part of the path, and a scorer that thinks otherwise reports a false miss
# on a correctly located finding.
_PREFIXES = ("./", "a/", "b/")

_RANGE = re.compile(r"^\s*(\d+)\s*[-–—:]\s*(\d+)\s*$")

# How far a reported line may sit from the recorded one and still count. Three
# lines is roughly a signature plus a brace: close enough to be the same defect,
# far enough that two genuinely different defects in one file stay apart.
DEFAULT_TOLERANCE = 3


def normalise_path(path: str) -> str:
    """Strip diff and shell prefixes and normalise separators."""
    cleaned = str(path).strip().replace("\\", "/")
    changed = True
    while changed:
        changed = False
        for prefix in _PREFIXES:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix) :]
                changed = True
    return cleaned.lstrip("/")


@dataclass(frozen=True)
class Finding:
    """One reported defect, located.

    `line` and `end_line` are inclusive and equal for a single line. Both are
    `None` for a finding that names a file and declines to guess a line, which
    is a legitimate thing for a reviewer to do and is not scored as wrong.
    """

    file: str
    line: int | None
    end_line: int | None
    claim: str
    file_as_written: str = ""

    def covers(self, target: int | None, tolerance: int = DEFAULT_TOLERANCE) -> bool:
        """Whether this finding's location includes `target`, within `tolerance`.

        A finding with no line covers its whole file; so does a target with no
        line. In both cases the location carries no information to contradict,
        and inventing a mismatch out of an absent number is exactly the kind of
        false negative this module exists to prevent.
        """
        if target is None or self.line is None or self.end_line is None:
            return True
        return self.line - tolerance <= target <= self.end_line + tolerance

    def as_comment(self) -> dict[str, Any]:
        """The shape the runner posts as a review comment.

        A range posts at its first line: GitHub wants somewhere to hang the
        comment, and the start of the span is where a reader looks.
        """
        return {"file": self.file, "line": self.line, "claim": self.claim}


def _lines(obj: dict[str, Any]) -> tuple[int | None, int | None]:
    """Read a location out of whatever the model wrote."""
    start = obj.get("start_line")
    end = obj.get("end_line")
    if start is not None or end is not None:
        first = _int(start) if start is not None else _int(end)
        last = _int(end) if end is not None else _int(start)
        return _ordered(first, last)

    raw = obj.get("line")
    if raw is None:
        return None, None
    if isinstance(raw, bool):
        return None, None
    if isinstance(raw, int):
        return raw, raw

    match = _RANGE.match(str(raw))
    if match:
        return _ordered(int(match.group(1)), int(match.group(2)))

    value = _int(raw)
    return (value, value) if value is not None else (None, None)


def _ordered(first: int | None, last: int | None) -> tuple[int | None, int | None]:
    """A reversed range is a typo, not a reason to lose the finding."""
    if first is None or last is None:
        return first or last, last or first
    return (first, last) if first <= last else (last, first)


def _int(value: Any) -> int | None:
    text = str(value).strip()
    return int(text) if text.isdigit() else None


def _build(obj: dict[str, Any]) -> Finding | None:
    file = obj.get("file") or obj.get("path")
    claim = obj.get("claim") or obj.get("description") or obj.get("message")
    if not file or not claim:
        return None
    start, end = _lines(obj)
    return Finding(
        file=normalise_path(str(file)),
        line=start,
        end_line=end,
        claim=str(claim).strip(),
        file_as_written=str(file),
    )


def parse_findings(text: str) -> list[Finding]:
    """Parse a reviewer's output into records, tolerantly.

    Accepts one JSON object per line, a fenced block, a JSON array, and prose
    around any of them. Anything unparseable is skipped rather than raised on:
    one malformed line must not cost a run its other findings.
    """
    if not text or not text.strip():
        return []

    stripped = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    # An array, when the model ignored "one per line" and emitted a list.
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
        except ValueError:
            parsed = None
        if isinstance(parsed, list):
            built = [_build(o) for o in parsed if isinstance(o, dict)]
            return [f for f in built if f is not None]

    findings = []
    for raw in text.splitlines():
        line = raw.strip().removeprefix("```json").removeprefix("```").strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        finding = _build(obj)
        if finding is not None:
            findings.append(finding)
    return findings
