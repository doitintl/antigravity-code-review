"""Score a run against a fixture: location first, text only to disambiguate.

**This module decides what "recall" means in this project**, which is why it
gets the treatment the rate table got. The rate table carries the claims about
money; this carries the claims about quality, and a wrong number here is just as
invisible and gets quoted just as readily.

Its most important property is a negative one: **text never rejects a location
match.** The instrument this replaces did exactly that. It greped a judge's
output for `"page type"`; the judge had written `"pages"`; the run was scored
0/4 when the truth was one known defect correctly reported plus one novel defect
nobody else had found. That was the third time in this investigation an
instrument rather than the reviewer produced the headline number, and all three
made the reviewer look worse than it was.

So text gets exactly one job — choosing between two findings at the *same* place
— and it is a tie-breaker, never a veto. If a finding is where the defect is, it
is a hit, whatever words it used.

Three further decisions worth stating:

**One finding satisfies at most one defect.** Two defects on the same line and
one comment is one of them found, not both. The assignment is greedy on text
similarity, which is what similarity is for.

**Findings matching nothing are kept as `novel`, not discarded.** A run in M2.5
reported a real defect that neither the fixture nor the reference reviewer had.
Throwing those away would make the harness an instrument for confirming the
fixture rather than for judging a review.

**An incomplete run has no recall.** Not zero — `None`. Q8 established that a
budget stop returns empty text, which reads exactly like a clean review, and two
runs were interpreted backwards before anyone checked the stop reason.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from antigravity_code_review.evalharness.findings import (
    DEFAULT_TOLERANCE,
    Finding,
    normalise_path,
)
from antigravity_code_review.evalharness.fixtures import Defect, Fixture
from antigravity_code_review.evalharness.runs import RunOutcome

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")

# Words that appear in every review comment ever written and carry no signal
# about *which* defect is being described. Only ever used for tie-breaking, so
# an imperfect list costs a tie-break, never a match.
_NOISE_WORDS = """the a an and or but is are was were be been being this that these those it its
    to of in on at for with from by as not no if then than so such can could should
    would may might will shall do does did done have has had here there when where
    which who whom what why how all any both each few more most other some only own
    same too very just also into over under again further once because while about
    against between during before after above below up down out off over under"""
_NOISE = frozenset(_NOISE_WORDS.split())


class ScorerValidationError(RuntimeError):
    """The scorer could not find a fixture's defects in a reference review.

    Raised loudly and before use, because the alternative is a silent zero on
    every run that follows — and a zero from a broken instrument looks exactly
    like a zero from a reviewer that found nothing.
    """


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "")} - _NOISE


def _similarity(defect: Defect, finding: Finding) -> float:
    """Jaccard overlap of content words. Only ever used to break a tie."""
    left, right = _tokens(defect.description), _tokens(finding.claim)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _overlaps(defect: Defect, finding: Finding, tolerance: int) -> bool:
    """Whether the finding's span reaches the defect's, within `tolerance`.

    Spans, not points. A defect in a block is in the whole block, and a
    reviewer may reasonably anchor its comment anywhere in it — the reference
    reviewer on one fixture anchored at the end of a seventeen-line block while
    ours anchored at the start. Comparing anchor points called that a miss.

    An absent line on either side means the location carries no information to
    contradict, so it matches.
    """
    span = defect.span
    if span is None or finding.line is None or finding.end_line is None:
        return True
    return (
        finding.line - tolerance <= span[1]
        and finding.end_line + tolerance >= span[0]
    )


def _candidates(
    defect: Defect, findings: Sequence[Finding], tolerance: int
) -> list[tuple[float, int, Finding]]:
    """Findings whose location could be this defect's, best text overlap first."""
    target = normalise_path(defect.file)
    out = []
    for index, finding in enumerate(findings):
        # Both sides normalised. A Finding built by hand rather than parsed must
        # not score as a miss on a prefix — a scorer whose answer depends on how
        # its input was constructed is the fragility this module exists to avoid.
        if normalise_path(finding.file) != target:
            continue
        if not _overlaps(defect, finding, tolerance):
            continue
        out.append((_similarity(defect, finding), index, finding))
    out.sort(key=lambda t: (-t[0], t[1]))
    return out


@dataclass(frozen=True)
class RunScore:
    """What one run of one configuration against one fixture found.

    `recall` is `None` for an incomplete run rather than 0.0. The distinction is
    the whole of FR5: a stopped run that produced nothing is not a run that
    found nothing.
    """

    fixture: str
    configuration: str
    matches: dict[str, Finding | None]
    novel: list[Finding]
    incomplete: bool
    stop_reason: str | None = None
    classes: dict[str, str] = field(default_factory=dict)

    def found(self, defect_id: str) -> bool:
        return self.matches.get(defect_id) is not None

    def matched_claim(self, defect_id: str) -> str:
        finding = self.matches.get(defect_id)
        return finding.claim if finding else ""

    def missed(self) -> list[str]:
        """Defect ids this run did not report, in fixture order."""
        return [d for d, f in self.matches.items() if f is None]

    @property
    def hits(self) -> int:
        return sum(1 for f in self.matches.values() if f is not None)

    @property
    def recall(self) -> float | None:
        if self.incomplete or not self.matches:
            return None
        return self.hits / len(self.matches)

    def recall_by_class(self) -> dict[str, tuple[int, int]]:
        """FR6: hits and total per defect class.

        Reported as a pair rather than a ratio so a 1-of-1 band is visibly not
        the same claim as a 40-of-40 one.
        """
        out: dict[str, list[int]] = {}
        for defect_id, finding in self.matches.items():
            cls = self.classes.get(defect_id, "unknown")
            bucket = out.setdefault(cls, [0, 0])
            bucket[1] += 1
            if finding is not None:
                bucket[0] += 1
        return {cls: (hit, total) for cls, (hit, total) in out.items()}


def score_run(
    fixture: Fixture,
    findings: Sequence[Finding],
    *,
    configuration: str = "default",
    incomplete: bool = False,
    stop_reason: str | None = None,
    outcome: RunOutcome | None = None,
    tolerance: int = DEFAULT_TOLERANCE,
) -> RunScore:
    """Match a run's findings against a fixture's known defects.

    Args:
        fixture: the fixture that was reviewed.
        findings: the run's structured findings.
        configuration: names the configuration under test (FR8).
        incomplete: the run did not finish normally. Excluded from recall.
        stop_reason: recorded verbatim for the report (FR5).
        outcome: a `RunOutcome` from `runs.classify` or `runs.combine`. When
            given it supplies both of the above, so the reviewer and the
            harness cannot drift apart on what "incomplete" means.
        tolerance: how far a reported line may sit from the recorded one.

    Returns:
        A `RunScore`. Every defect appears in `matches`, hit or not; every
        finding that matched nothing appears in `novel`.
    """
    if outcome is not None:
        incomplete = outcome.incomplete
        stop_reason = outcome.reason if outcome.incomplete else outcome.stop_reason

    matches: dict[str, Finding | None] = {d.id: None for d in fixture.defects}
    classes = {d.id: d.defect_class.value for d in fixture.defects}
    taken: set[int] = set()

    # Assign the strongest text agreements first, so that when two defects share
    # a location the finding that actually describes each one lands on it.
    ranked = []
    for defect in fixture.defects:
        for score, index, finding in _candidates(defect, findings, tolerance):
            ranked.append((score, defect.id, index, finding))
    ranked.sort(key=lambda t: (-t[0], t[2]))

    for _, defect_id, index, finding in ranked:
        if matches[defect_id] is not None or index in taken:
            continue
        matches[defect_id] = finding
        taken.add(index)

    novel = [f for i, f in enumerate(findings) if i not in taken]
    return RunScore(
        fixture=fixture.name,
        configuration=configuration,
        matches=matches,
        novel=novel,
        incomplete=incomplete,
        stop_reason=stop_reason,
        classes=classes,
    )


def ambiguous_pairs(
    fixture: Fixture, tolerance: int = DEFAULT_TOLERANCE
) -> list[tuple[str, str, int]]:
    """Defect pairs too close together for location alone to tell apart.

    Two findings' spans overlap when the defects are within `2 * tolerance` of
    each other in the same file. For those, "location first, text only to
    disambiguate" degrades to "text decides", and the scorer's central guarantee
    is weaker than it looks.

    Reported rather than fixed. Narrowing the tolerance to separate them would
    reintroduce the near-miss failure this project measured, and moving the
    recorded lines would be editing the evidence. What the harness owes its
    reader is the disclosure.

    Returns:
        `(first_id, second_id, gap)` triples, in fixture order.
    """
    pairs = []
    defects = [d for d in fixture.defects if d.line is not None]
    for i, left in enumerate(defects):
        for right in defects[i + 1 :]:
            if normalise_path(left.file) != normalise_path(right.file):
                continue
            gap = abs((left.line or 0) - (right.line or 0))
            if gap <= 2 * tolerance:
                pairs.append((left.id, right.id, gap))
    return pairs


# Above this share of a fixture's lines sitting inside some defect's tolerance
# window, a finding placed at random is likely to score, and the fixture's
# numbers mean materially less than the same numbers from a large file.
COVERAGE_WARN = 0.25


def location_coverage(
    fixture: Fixture,
    file_lengths: dict[str, int],
    tolerance: int = DEFAULT_TOLERANCE,
) -> tuple[int, int]:
    """How much of a fixture's changed files lies within reach of some defect.

    Location-first scoring rests on a defect's tolerance window being a small
    part of the file it sits in. That assumption holds for a 1,900-line source
    file and collapses for a 41-line one: with five defects and a plus-or-minus
    three window, 71% of such a file is inside *some* window, and five findings
    scattered anywhere plausible score 4 of 5 with their text replaced by
    nonsense.

    The scorer is not wrong there — the fixture is small. But two identical
    numbers from fixtures of different sizes are not the same claim, and a
    harness that prints both without comment is inviting the reader to treat
    them alike. So this is measured and reported.

    Args:
        fixture: the fixture to measure.
        file_lengths: line count per changed file. Files absent from this map
            are skipped rather than guessed at.
        tolerance: the same window the scorer matches with.

    Returns:
        `(lines_within_reach, lines_total)` over the files that carry defects.
    """
    by_file: dict[str, list[Defect]] = {}
    for defect in fixture.defects:
        by_file.setdefault(normalise_path(defect.file), []).append(defect)

    reachable = total = 0
    lengths = {normalise_path(k): v for k, v in file_lengths.items()}
    for path, defects in by_file.items():
        length = lengths.get(path)
        if not length:
            continue
        total += length
        covered: set[int] = set()
        for defect in defects:
            if defect.line is None:
                # It matches anything in the file, so the honest answer is all of it.
                covered = set(range(1, length + 1))
                break
            low = max(1, defect.line - tolerance)
            high = min(length, defect.line + tolerance)
            covered |= set(range(low, high + 1))
        reachable += len(covered)
    return reachable, total


def findings_from_reference(reference: dict[str, Any]) -> list[Finding]:
    """Turn a fetched reference review into findings the scorer can consume.

    The reasoning fold is dropped: it is an essay, and carrying it into a claim
    would let one verbose comment dominate every tie-break in the fixture.
    """
    out = []
    for comment in reference.get("comments") or []:
        path = comment.get("path")
        if not path:
            continue
        body = str(comment.get("body") or "").split("<details>")[0].strip()
        line = comment.get("line")
        if line is None:
            line = comment.get("original_line")
        value = int(line) if isinstance(line, int) else None
        out.append(
            Finding(
                file=normalise_path(path),
                line=value,
                end_line=value,
                claim=re.sub(r"\s+", " ", body)[:600],
                file_as_written=str(path),
            )
        )
    return out


def validate_against_reference(
    fixture: Fixture,
    reference: dict[str, Any],
    *,
    tolerance: int = DEFAULT_TOLERANCE,
    required: float = 1.0,
) -> RunScore:
    """Prove the scorer can find this fixture's defects in a reference review.

    Run **before** the scorer is used, because a scorer that cannot locate the
    known defects in the text they were derived from will report a false zero
    for every run afterwards — and nothing about that zero will look wrong.

    Args:
        fixture: the fixture to validate against.
        reference: a fetched reference review.
        tolerance: line tolerance, matching the scoring run.
        required: the recall the reference review must achieve, 1.0 by default.

    Returns:
        The `RunScore` of the reference review, for reporting.

    Raises:
        ScorerValidationError: if the reference review is empty, or the scorer
            cannot reach `required` recall against it.
    """
    findings = findings_from_reference(reference)
    if not findings:
        raise ScorerValidationError(
            f"{fixture.name}: the reference review has no comments, so the scorer "
            "cannot be validated against it. An unvalidated scorer reports a false "
            "zero indistinguishable from a real one."
        )

    score = score_run(
        fixture, findings, configuration="reference-review", tolerance=tolerance
    )
    achieved = score.recall or 0.0
    if achieved < required:
        raise ScorerValidationError(
            f"{fixture.name}: the scorer found {score.hits}/{len(score.matches)} of this "
            f"fixture's defects in the reference review those defects came from. "
            f"Missed: {', '.join(score.missed())}. "
            "This is a defect in the scorer or in the fixture's recorded locations, "
            "not in any reviewer — and left unfixed it reports a false zero for "
            "every run scored afterwards."
        )
    return score


def scored_recall(scores: Iterable[RunScore]) -> list[float]:
    """Recall of the complete runs only. Incomplete runs are absent, not zero."""
    return [s.recall for s in scores if s.recall is not None]
