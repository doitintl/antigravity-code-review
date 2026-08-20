"""The scorer. This module decides what "recall" means, so it gets the rate table's treatment.

Its single most important property is negative: **text must never reject a
location match.** The bug this replaces did exactly that — a scorer greping for
`"page type"` scored a judge that wrote `"pages"` as a miss, and reported 0/4
where the truth was 1/4 plus one defect nobody else had found. Every "paraphrase"
test below is that bug, written down so it cannot come back.

Text earns one job and no others: choosing between two findings at the *same*
place. It is a tie-breaker, never a veto.
"""

from typing import ClassVar

import pytest

from antigravity_code_review.evalharness.findings import Finding
from antigravity_code_review.evalharness.fixtures import load_fixture
from antigravity_code_review.evalharness.scoring import (
    ScorerValidationError,
    ambiguous_pairs,
    findings_from_reference,
    location_coverage,
    score_run,
    scored_recall,
    validate_against_reference,
)


def _fixture(*defects):
    return load_fixture(
        {
            "name": "f",
            "repo": "acme/widgets",
            "base_sha": "1111111",
            "head_sha": "2222222",
            "defects": list(defects),
        }
    )


def _defect(did, file="src/a.ts", line=100, cls="local", desc="a defect", **kw):
    return {
        "id": did,
        "file": file,
        "line": line,
        "class": cls,
        "description": desc,
        "reachable": "evidence that is long enough to clear the reachability floor here",
        **kw,
    }


def _finding(file="src/a.ts", line=100, claim="something is wrong", end=None):
    return Finding(file=file, line=line, end_line=end if end is not None else line, claim=claim)


class TestLocationIsWhatMatches:
    def test_a_finding_at_the_recorded_line_is_a_hit(self):
        s = score_run(_fixture(_defect("d1")), [_finding()])
        assert s.found("d1")

    def test_a_finding_in_another_file_is_not(self):
        s = score_run(_fixture(_defect("d1")), [_finding(file="src/b.ts")])
        assert not s.found("d1")

    def test_a_finding_far_away_in_the_same_file_is_not(self):
        s = score_run(_fixture(_defect("d1", line=100)), [_finding(line=800)])
        assert not s.found("d1")

    def test_a_near_miss_within_tolerance_is_a_hit(self):
        s = score_run(_fixture(_defect("d1", line=214)), [_finding(line=216)])
        assert s.found("d1")

    def test_a_span_covering_the_defect_is_a_hit(self):
        s = score_run(_fixture(_defect("d1", line=130)), [_finding(line=120, end=140)])
        assert s.found("d1")

    def test_a_diff_prefixed_path_still_matches(self):
        s = score_run(_fixture(_defect("d1")), [_finding(file="b/src/a.ts")])
        assert s.found("d1")

    def test_a_defect_with_no_line_matches_any_finding_in_its_file(self):
        s = score_run(_fixture(_defect("d1", line=None)), [_finding(line=4321)])
        assert s.found("d1")


class TestTextNeverVetoesALocation:
    """The regression that produced a published false zero."""

    def test_a_total_paraphrase_at_the_right_place_is_a_hit(self):
        fixture = _fixture(
            _defect("d1", line=1005, desc="the tag is settable on all page types but read for two")
        )
        s = score_run(fixture, [_finding(line=1005, claim="editors can set this on pages that "
                                                          "never render it")])
        assert s.found("d1")

    def test_zero_shared_vocabulary_is_still_a_hit(self):
        fixture = _fixture(_defect("d1", desc="alpha beta gamma delta"))
        s = score_run(fixture, [_finding(claim="epsilon zeta eta theta")])
        assert s.found("d1")

    def test_an_empty_claim_at_the_right_place_is_still_a_hit(self):
        s = score_run(_fixture(_defect("d1")), [_finding(claim="x")])
        assert s.found("d1")


class TestTextOnlyDisambiguates:
    def test_two_findings_at_one_place_go_to_the_defects_they_describe(self):
        fixture = _fixture(
            _defect("overdraft", line=33, desc="the balance guard is bypassed by a direct write"),
            _defect("types", line=33, desc="decimal and float are mixed in the arithmetic"),
        )
        s = score_run(
            fixture,
            [
                _finding(line=33, claim="mixing Decimal and float raises here"),
                _finding(line=33, claim="this write bypasses the guard on the balance"),
            ],
        )
        assert s.matched_claim("types").startswith("mixing Decimal")
        assert s.matched_claim("overdraft").startswith("this write bypasses")

    def test_one_finding_cannot_satisfy_two_defects(self):
        fixture = _fixture(_defect("d1", line=33), _defect("d2", line=33))
        s = score_run(fixture, [_finding(line=33)])
        assert sum(1 for d in ("d1", "d2") if s.found(d)) == 1

    def test_two_findings_cover_two_defects_at_the_same_place(self):
        fixture = _fixture(_defect("d1", line=33), _defect("d2", line=33))
        s = score_run(fixture, [_finding(line=33, claim="one"), _finding(line=33, claim="two")])
        assert s.found("d1") and s.found("d2")


class TestNovelFindingsAreNotThrownAway:
    def test_a_finding_matching_nothing_is_reported_as_novel(self):
        """A run once found a real defect nobody else had. Discarding those makes
        the harness a tool for confirming the fixture rather than judging a review."""
        s = score_run(_fixture(_defect("d1")), [_finding(), _finding(file="src/z.ts", line=9)])
        assert len(s.novel) == 1
        assert s.novel[0].file == "src/z.ts"

    def test_novel_findings_are_not_counted_as_recall(self):
        s = score_run(_fixture(_defect("d1")), [_finding(file="src/z.ts", line=9)])
        assert s.recall == 0.0 and len(s.novel) == 1


class TestAggregatingAcrossRuns:
    def test_incomplete_runs_are_absent_from_the_recall_list_not_zero_in_it(self):
        """Averaging a stopped run in as 0.0 is how a budget stop becomes a
        recall failure in a table nobody re-reads."""
        fixture = _fixture(_defect("d1"))
        runs = [
            score_run(fixture, [_finding()]),
            score_run(fixture, [], incomplete=True),
            score_run(fixture, []),
        ]
        assert scored_recall(runs) == [1.0, 0.0]


class TestReportingShape:
    def test_recall_is_hits_over_defects(self):
        s = score_run(_fixture(_defect("d1"), _defect("d2", line=500)), [_finding()])
        assert s.recall == 0.5

    def test_recall_by_class_keeps_the_bands_apart(self):
        fixture = _fixture(
            _defect("sec", cls="security", line=10),
            _defect("x1", cls="cross-file", line=200),
            _defect("x2", cls="cross-file", line=300),
        )
        s = score_run(fixture, [_finding(line=10), _finding(line=200)])
        by = s.recall_by_class()
        assert by["security"] == (1, 1)
        assert by["cross-file"] == (1, 2)

    def test_missed_defects_are_named_not_just_counted(self):
        s = score_run(_fixture(_defect("d1"), _defect("gone", line=900)), [_finding()])
        assert s.missed() == ["gone"]

    def test_an_incomplete_run_has_no_recall_at_all(self):
        """Excluded from recall, never counted as zero findings."""
        s = score_run(_fixture(_defect("d1")), [], incomplete=True)
        assert s.incomplete
        assert s.recall is None

    def test_a_complete_run_with_no_findings_does_have_a_recall_of_zero(self):
        s = score_run(_fixture(_defect("d1")), [])
        assert s.recall == 0.0

    def test_a_run_outcome_supplies_incompleteness_and_its_reason(self):
        """One definition of 'incomplete', shared with the reviewer."""
        from antigravity_code_review.evalharness.runs import classify

        s = score_run(
            _fixture(_defect("d1")),
            [_finding()],
            outcome=classify("MAX_OUTPUT_TOKENS_EXCEEDED", text=""),
        )
        assert s.incomplete and s.recall is None
        assert "MAX_OUTPUT_TOKENS_EXCEEDED" in s.stop_reason

    def test_a_complete_outcome_leaves_recall_intact(self):
        from antigravity_code_review.evalharness.runs import classify

        s = score_run(_fixture(_defect("d1")), [_finding()], outcome=classify(None))
        assert not s.incomplete and s.recall == 1.0

    def test_the_configuration_is_recorded_on_the_score(self):
        """FR8: a run names the configuration that produced it."""
        s = score_run(_fixture(_defect("d1")), [_finding()], configuration="contract-passes")
        assert s.configuration == "contract-passes"


class TestAmbiguousDefectPairs:
    """Where two defects sit closer than twice the line tolerance, location
    alone cannot separate them and the tie-break decides. That weakens the
    guarantee this scorer is built on, so the fixture is made to admit it
    rather than letting the degradation stay invisible."""

    def test_two_defects_within_the_tolerance_window_are_reported(self):
        f = _fixture(_defect("d1", line=30), _defect("d2", line=33))
        pairs = ambiguous_pairs(f)
        assert pairs == [("d1", "d2", 3)]

    def test_defects_far_apart_are_not(self):
        f = _fixture(_defect("d1", line=30), _defect("d2", line=300))
        assert ambiguous_pairs(f) == []

    def test_defects_in_different_files_are_never_ambiguous(self):
        f = _fixture(_defect("d1", line=30), _defect("d2", file="src/b.ts", line=31))
        assert ambiguous_pairs(f) == []

    def test_a_defect_with_no_line_is_not_paired(self):
        """It matches everything in its file by design; that is not ambiguity
        between two recorded locations."""
        f = _fixture(_defect("d1", line=None), _defect("d2", line=33))
        assert ambiguous_pairs(f) == []

    def test_the_window_follows_the_tolerance(self):
        f = _fixture(_defect("d1", line=30), _defect("d2", line=40))
        assert ambiguous_pairs(f) == []
        assert ambiguous_pairs(f, tolerance=6) == [("d1", "d2", 10)]


class TestHowEasilyAFindingCanScoreByAccident:
    """The check that a user's question forced, and it found a real problem.

    Location-first scoring assumes a defect's tolerance window is a small part
    of the file. On a 41-line file with five defects and a plus-or-minus-three
    window, 71% of the lines are inside *some* window — and five findings
    scattered anywhere plausible scored 4/5 with their text replaced by
    nonsense. The scorer is not wrong; the fixture is small, and a number from
    it means less than the same number from a 1,900-line file.

    So the harness measures its own gullibility and reports it, rather than
    letting two identical-looking numbers carry different weight in silence.
    """

    def test_a_defect_in_a_large_file_covers_almost_none_of_it(self):
        f = _fixture(_defect("d1", file="src/a.ts", line=900))
        covered, total = location_coverage(f, {"src/a.ts": 1800})
        assert covered == 7 and total == 1800

    def test_a_defect_in_a_tiny_file_covers_most_of_it(self):
        f = _fixture(_defect("d1", file="src/a.ts", line=5))
        covered, total = location_coverage(f, {"src/a.ts": 10})
        assert covered / total > 0.5

    def test_overlapping_windows_are_not_double_counted(self):
        f = _fixture(_defect("d1", file="src/a.ts", line=10), _defect("d2", file="src/a.ts", line=12))
        covered, _ = location_coverage(f, {"src/a.ts": 100})
        assert covered == 9  # 7..15, not 7 + 7

    def test_a_window_is_clipped_to_the_file(self):
        f = _fixture(_defect("d1", file="src/a.ts", line=2))
        covered, _ = location_coverage(f, {"src/a.ts": 4})
        assert covered == 4  # lines 1..4, never 0 or 5

    def test_a_defect_with_no_line_covers_its_whole_file(self):
        """It matches anything in the file, so the honest coverage is all of it."""
        f = _fixture(_defect("d1", file="src/a.ts", line=None))
        covered, total = location_coverage(f, {"src/a.ts": 200})
        assert covered == total == 200

    def test_a_file_whose_length_is_unknown_is_skipped_not_guessed(self):
        f = _fixture(_defect("d1", file="src/a.ts", line=10))
        assert location_coverage(f, {}) == (0, 0)

    def test_multiple_files_are_summed(self):
        f = _fixture(
            _defect("d1", file="src/a.ts", line=50),
            _defect("d2", file="src/b.ts", line=50),
        )
        covered, total = location_coverage(f, {"src/a.ts": 100, "src/b.ts": 100})
        assert covered == 14 and total == 200


class TestValidatingTheScorerBeforeUse:
    """AC3. A scorer that cannot find the known defects in an independent
    reviewer's own text reports a false zero for everything downstream."""

    REFERENCE: ClassVar[dict] = {
        "comments": [
            {"path": "src/a.ts", "line": 100, "body": "The tag is read for only two page types."},
            {"path": "src/b.ts", "line": 42, "body": "This fires on every publish, not the first."},
        ]
    }

    def _fixture(self):
        return _fixture(
            _defect("d1", file="src/a.ts", line=100, cls="cross-file"),
            _defect("d2", file="src/b.ts", line=42, cls="cross-file"),
        )

    def test_a_reference_review_becomes_findings(self):
        found = findings_from_reference(self.REFERENCE)
        assert [f.file for f in found] == ["src/a.ts", "src/b.ts"]
        assert found[0].line == 100

    def test_the_reference_review_scores_full_recall(self):
        result = validate_against_reference(self._fixture(), self.REFERENCE)
        assert result.recall == 1.0

    def test_validation_raises_when_the_scorer_cannot_find_them(self):
        broken = {"comments": [{"path": "src/elsewhere.ts", "line": 1, "body": "x"}]}
        with pytest.raises(ScorerValidationError) as exc:
            validate_against_reference(self._fixture(), broken)
        assert "d1" in str(exc.value)

    def test_the_error_says_the_instrument_is_at_fault_not_the_reviewer(self):
        broken = {"comments": [{"path": "src/elsewhere.ts", "line": 1, "body": "x"}]}
        with pytest.raises(ScorerValidationError) as exc:
            validate_against_reference(self._fixture(), broken)
        assert "scorer" in str(exc.value).lower()

    def test_a_reference_review_with_no_comments_is_a_validation_failure(self):
        with pytest.raises(ScorerValidationError):
            validate_against_reference(self._fixture(), {"comments": []})

    def test_the_reference_body_is_trimmed_of_its_reasoning_fold(self):
        ref = {"comments": [{"path": "src/a.ts", "line": 100,
                             "body": "The claim.\n<details>\nlong reasoning\n</details>"}]}
        assert "long reasoning" not in findings_from_reference(ref)[0].claim

    def test_a_comment_with_no_path_is_skipped_rather_than_crashing(self):
        ref = {"comments": [{"body": "no path"}, {"path": "src/a.ts", "line": 1, "body": "x"}]}
        assert len(findings_from_reference(ref)) == 1

    def test_original_line_is_used_when_line_is_absent(self):
        ref = {"comments": [{"path": "src/a.ts", "original_line": 100, "body": "x"}]}
        assert findings_from_reference(ref)[0].line == 100
