"""Check that reachability evidence is evidence, not a filled-in field.

`load_fixture` requires the evidence field to be present and non-empty. That
stops it being forgotten and does nothing at all about it being filled in with
`TODO`, and a fixture that passes validation while carrying no evidence is worse
than one that fails, because it goes on to produce a number.

**These rules are deliberately mechanical: a fixed placeholder list and a length
floor.** They cannot tell a careful trigger path from a confident-sounding
guess, and they do not try to. This project has already published one wrong
headline number because an instrument judged text by keyword — a scorer greping
for "page type" scored a reviewer that wrote "pages" as a miss. A credibility
heuristic over prose would be the same mistake in a new place. What survives
these checks is still a human judgement; what they catch is the placeholder
nobody came back to.
"""

from __future__ import annotations

from collections.abc import Iterable

from antigravity_code_review.evalharness.fixtures import Defect, Fixture

# Anything whose entire content is one of these. Matched after case-folding and
# stripping trailing punctuation, so "Yes." and "yes" are the same non-answer.
PLACEHOLDERS = frozenset(
    {
        "",
        "-",
        "?",
        "..",
        "...",
        "todo",
        "tbd",
        "fixme",
        "yes",
        "no",
        "true",
        "false",
        "n/a",
        "na",
        "none",
        "unknown",
        "unclear",
        "reachable",
        "unreachable",
        "verified",
        "checked",
        "obvious",
    }
)

# A trigger path does not fit in ten words. The floor is low on purpose: it is
# here to catch "it is reachable", not to legislate how evidence is written.
MIN_EVIDENCE_CHARS = 40

_LEADING_PLACEHOLDERS = ("todo", "tbd", "fixme")


class UnreachableFixtureError(ValueError):
    """A fixture set carries defects whose reachability was never established."""


def _normalise(text: str) -> str:
    return text.strip().casefold().rstrip(".:;!,")


def evidence_complaint(defect: Defect, fixture_name: str | None = None) -> str | None:
    """Return why this defect's reachability evidence is not evidence, or None.

    Args:
        defect: the defect to check.
        fixture_name: included in the complaint when the defect came from a set.

    Returns:
        A complaint naming the defect, its file, and what was wrong — or None
        when the evidence clears both checks.
    """
    where = f"{fixture_name}/{defect.id}" if fixture_name else defect.id
    where = f"{where} ({defect.file})"
    text = defect.reachable.strip()
    normalised = _normalise(text)

    if normalised in PLACEHOLDERS:
        return (
            f"{where}: reachability evidence is the placeholder {text!r}. "
            "A defect that cannot be shown to manifest scores a correct triage "
            "decision as a miss."
        )

    if normalised.startswith(_LEADING_PLACEHOLDERS):
        return (
            f"{where}: reachability evidence is still a placeholder — it begins {text[:20]!r}."
        )

    if len(normalised) < MIN_EVIDENCE_CHARS:
        return (
            f"{where}: reachability evidence is {len(normalised)} characters, "
            f"below the {MIN_EVIDENCE_CHARS}-character floor. A trigger path does "
            "not fit in ten words."
        )

    return None


def audit(fixtures: Iterable[Fixture]) -> list[str]:
    """Return every complaint across a fixture set.

    Every one, not the first. Fixing them a run at a time is how a set stays
    weak for a month.
    """
    complaints = []
    for fixture in fixtures:
        for defect in fixture.defects:
            complaint = evidence_complaint(defect, fixture.name)
            if complaint:
                complaints.append(complaint)
    return complaints


def require_reachable(fixtures: Iterable[Fixture]) -> None:
    """Raise unless every defect in the set carries real reachability evidence.

    Called before a run rather than after it, so a weak fixture cannot quietly
    contribute to a recall figure.

    Raises:
        UnreachableFixtureError: listing every complaint at once.
    """
    complaints = audit(fixtures)
    if complaints:
        listed = "\n  - ".join(complaints)
        raise UnreachableFixtureError(
            f"{len(complaints)} defect(s) carry no reachability evidence:\n  - {listed}"
        )
