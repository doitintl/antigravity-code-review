"""Fixtures: the code under measurement, pinned so it cannot move.

A fixture names a repository, **two commit SHAs**, and the defects known to be
present in the change between them. It never identifies the code by pull request
number alone.

That rule is not fastidiousness. The first comparison this project ran against a
real pull request used the *head*, which by then was two fix commits later than
the code the reference reviewer had seen. "We found nothing they found" was
measuring different source, and it read as a recall failure. A pull request
number is a moving target; a SHA is the review.

The second rule is that a defect carries **evidence that it can manifest**. M1's
fixture planted an unconditional `return True` that was unreachable, because an
earlier `Decimal`/`float` mismatch raised `TypeError` on every call. The reviewer
was right not to report dead code; the harness scored it 0/8 and it looked like a
blind spot. A planted defect is a hypothesis until someone shows it can fire.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

# Seven hex characters is git's own floor for an abbreviated object name, and it
# is the shortest thing that can honestly be called a commit. Shorter is a
# prefix, and a prefix can resolve to two objects in a large repository.
_SHA = re.compile(r"^[0-9a-f]{7,40}$")
_REPO = re.compile(r"^[^/\s]+/[^/\s]+$")


class FixtureError(ValueError):
    """A fixture is malformed and must not be measured against.

    Raised rather than repaired. A harness that quietly fills in a missing SHA
    or downgrades an unknown defect class produces numbers whose provenance
    nobody can reconstruct, which is the failure this module exists to prevent.
    """


class DefectClass(str, Enum):
    """What kind of thinking a defect requires to find.

    Recall is not uniform across these and a single aggregate number would
    average them into a figure that moves for unattributable reasons. M1
    measured every security defect at 8/8 and one marginal local defect at 4/8;
    M2.5 measured cross-file contract mismatches at 0/4 until the comparison was
    posed as a question. Those are different facts and the report keeps them
    apart (FR6).
    """

    LOCAL = "local"
    CROSS_FILE = "cross-file"
    CONVENTION = "convention"
    SECURITY = "security"


@dataclass(frozen=True)
class Defect:
    """One known defect in a fixture's change.

    `reachable` is prose evidence that the defect can actually manifest — a
    sentence a human wrote after checking, not a boolean a human ticked. A
    boolean records that somebody was asked; a sentence records what they found.
    """

    id: str
    file: str
    line: int | None
    defect_class: DefectClass
    description: str
    reachable: str


@dataclass(frozen=True)
class Fixture:
    """A pull request pinned by commit, with its known defects."""

    name: str
    repo: str
    base_sha: str
    head_sha: str
    defects: tuple[Defect, ...]
    pr: int | None = None
    reference_review: str | None = None
    reachability_probe: str | None = None
    notes: str | None = None

    def defects_by_class(self) -> dict[DefectClass, list[Defect]]:
        """Group for per-class reporting (FR6)."""
        grouped: dict[DefectClass, list[Defect]] = {}
        for defect in self.defects:
            grouped.setdefault(defect.defect_class, []).append(defect)
        return grouped


def _require(obj: dict[str, Any], key: str, where: str) -> Any:
    value = obj.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise FixtureError(f"{where}: {key} is required")
    return value


def _sha(obj: dict[str, Any], key: str, where: str) -> str:
    raw = obj.get(key)
    if raw is None or not str(raw).strip():
        raise FixtureError(
            f"{where}: {key} is required — a fixture is pinned by commit SHA, "
            "never by pull request number. A head that moves is a different review."
        )
    value = str(raw).strip().lower()
    if not _SHA.match(value):
        raise FixtureError(
            f"{where}: {key}={raw!r} is not a commit SHA (7-40 hex characters). "
            "A branch name follows the branch."
        )
    return value


def _defect(obj: dict[str, Any], where: str) -> Defect:
    file = _require(obj, "file", where)
    description = _require(obj, "description", where)
    identifier = str(obj.get("id") or f"{file}:{obj.get('line', '?')}")

    raw_class = obj.get("class")
    try:
        defect_class = DefectClass(str(raw_class))
    except ValueError as exc:
        known = ", ".join(c.value for c in DefectClass)
        raise FixtureError(f"{where}: unknown defect class {raw_class!r} (known: {known})") from exc

    line = obj.get("line")
    if line is not None and not isinstance(line, bool) and not isinstance(line, int):
        if not str(line).strip().isdigit():
            raise FixtureError(f"{where}: line={line!r} is not a line number")
        line = int(str(line).strip())

    reachable = obj.get("reachable")
    if not reachable or not str(reachable).strip():
        raise FixtureError(
            f"{where}: defect {identifier!r} carries no reachability evidence. "
            "A defect shadowed by an earlier failure cannot be found, and scoring "
            "it as a miss measures the harness rather than the reviewer."
        )

    return Defect(
        id=identifier,
        file=str(file),
        line=int(line) if line is not None else None,
        defect_class=defect_class,
        description=str(description),
        reachable=str(reachable).strip(),
    )


def load_fixture(obj: dict[str, Any], source: str | None = None) -> Fixture:
    """Validate and build one fixture, or raise `FixtureError` saying why.

    Args:
        obj: the parsed fixture document.
        source: where it came from, used in error messages so a bad fixture in a
            directory of them names its own file.

    Returns:
        A frozen `Fixture`.

    Raises:
        FixtureError: on any missing SHA, unknown defect class, defect without
            reachability evidence, or duplicate defect id.
    """
    where = source or str(obj.get("name") or "<fixture>")

    name = str(_require(obj, "name", where)).strip()
    repo = str(_require(obj, "repo", where)).strip()
    if not _REPO.match(repo):
        raise FixtureError(f"{where}: repo={repo!r} must be owner/name")

    base_sha = _sha(obj, "base_sha", where)
    head_sha = _sha(obj, "head_sha", where)

    raw_defects = obj.get("defects") or []
    if not raw_defects:
        raise FixtureError(
            f"{where}: no defects. A fixture with nothing known to find measures nothing."
        )

    defects = tuple(_defect(d, where) for d in raw_defects)
    ids = [d.id for d in defects]
    if len(set(ids)) != len(ids):
        raise FixtureError(f"{where}: defect ids must be unique within a fixture")

    pr = obj.get("pr")
    return Fixture(
        name=name,
        repo=repo,
        base_sha=base_sha,
        head_sha=head_sha,
        defects=defects,
        pr=int(pr) if pr is not None else None,
        reference_review=obj.get("reference_review"),
        reachability_probe=obj.get("reachability_probe"),
        notes=obj.get("notes"),
    )


def load_fixtures(directory: str | Path) -> list[Fixture]:
    """Load every `*.json` fixture in a directory, sorted by name.

    Raises:
        FixtureError: if any fixture is malformed, or two share a name.
    """
    path = Path(directory)
    fixtures = []
    for file in sorted(path.glob("*.json")):
        try:
            obj = json.loads(file.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise FixtureError(f"{file.name}: not valid JSON: {exc}") from exc
        fixtures.append(load_fixture(obj, source=file.name))

    names = [f.name for f in fixtures]
    if len(set(names)) != len(names):
        raise FixtureError(f"{path}: fixture names must be unique across the set")
    return sorted(fixtures, key=lambda f: f.name)
