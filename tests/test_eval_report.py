"""The report. Its job is to stop a single number acquiring authority it has not earned.

Every rule here is a specific thing that went wrong:

- **Per-defect hit rate, not one number.** M1 measured five defects at 8/8, one
  at 4/8 and one at 0/8 that was a broken fixture. A single "recall" figure would
  have averaged those into something that moves for unattributable reasons.
- **Ranges, not points.** Three fixtures can detect a ±1 finding swing and cannot
  support a percentage. Run-to-run variance already exceeded the interventions
  being tested, twice.
- **Incomplete runs listed separately.** A budget stop returns empty text, and
  two runs were once interpreted backwards because of it.
- **Cost beside recall.** A configuration that finds one more defect for four
  times the money is a different trade from one that finds it for free.
"""

import pytest

from antigravity_code_review.evalharness.findings import Finding
from antigravity_code_review.evalharness.fixtures import load_fixture
from antigravity_code_review.evalharness.report import RunRecord, aggregate, render
from antigravity_code_review.evalharness.runs import classify
from antigravity_code_review.evalharness.scoring import score_run


def _fixture(name="f", *defects):
    return load_fixture(
        {
            "name": name,
            "repo": "acme/widgets",
            "base_sha": "1111111",
            "head_sha": "2222222",
            "defects": list(defects)
            or [
                {
                    "id": "d1",
                    "file": "src/a.ts",
                    "line": 10,
                    "class": "local",
                    "description": "one",
                    "reachable": "long enough evidence to clear the reachability floor here",
                },
                {
                    "id": "d2",
                    "file": "src/a.ts",
                    "line": 200,
                    "class": "security",
                    "description": "two",
                    "reachable": "long enough evidence to clear the reachability floor here",
                },
            ],
        }
    )


def _record(fixture, lines, *, cost=0.30, incomplete=False, config="contract-passes"):
    findings = [Finding(file="src/a.ts", line=n, end_line=n, claim="c") for n in lines]
    outcome = classify("MAX_TOOL_CALLS_EXCEEDED", text="") if incomplete else classify(None)
    return RunRecord(
        score=score_run(fixture, findings, configuration=config, outcome=outcome),
        cost_usd=cost,
    )


class TestPerDefectHitRate:
    def test_a_defect_found_in_two_of_three_runs_reports_two_of_three(self):
        f = _fixture()
        report = aggregate([_record(f, [10]), _record(f, [10]), _record(f, [])])
        assert report.hit_rate("f", "d1") == (2, 3)

    def test_a_defect_found_in_every_run_is_distinguished_from_one_found_once(self):
        """'2 of 3' and '3 of 3' are different facts."""
        f = _fixture()
        report = aggregate([_record(f, [10, 200]), _record(f, [10]), _record(f, [10])])
        assert report.hit_rate("f", "d1") == (3, 3)
        assert report.hit_rate("f", "d2") == (1, 3)

    def test_a_defect_never_found_still_appears(self):
        f = _fixture()
        report = aggregate([_record(f, [10]), _record(f, [10])])
        assert report.hit_rate("f", "d2") == (0, 2)

    def test_incomplete_runs_are_not_in_the_denominator(self):
        f = _fixture()
        report = aggregate([_record(f, [10]), _record(f, [10]), _record(f, [], incomplete=True)])
        assert report.hit_rate("f", "d1") == (2, 2)


class TestRangesNotPoints:
    def test_recall_is_reported_as_a_range_across_runs(self):
        f = _fixture()
        report = aggregate([_record(f, [10, 200]), _record(f, [10]), _record(f, [10])])
        assert report.recall_range("f") == (1, 2, 2)  # low, high, of

    def test_a_stable_result_reports_an_equal_low_and_high(self):
        f = _fixture()
        report = aggregate([_record(f, [10]), _record(f, [10])])
        assert report.recall_range("f") == (1, 1, 2)

    def test_a_fixture_with_only_incomplete_runs_has_no_range_at_all(self):
        f = _fixture()
        report = aggregate([_record(f, [10], incomplete=True)])
        assert report.recall_range("f") is None


class TestByDefectClass:
    def test_classes_are_kept_apart(self):
        f = _fixture()
        report = aggregate([_record(f, [10]), _record(f, [10]), _record(f, [10, 200])])
        by = report.by_class()
        assert by["local"] == (3, 3)
        assert by["security"] == (1, 3)

    def test_a_class_present_in_no_fixture_is_absent_not_zero(self):
        f = _fixture()
        report = aggregate([_record(f, [10])])
        assert "convention" not in report.by_class()


class TestCost:
    def test_cost_is_reported_as_a_range_and_a_mean(self):
        f = _fixture()
        report = aggregate([_record(f, [10], cost=0.20), _record(f, [10], cost=0.40)])
        low, high, mean = report.cost_range("f")
        assert (low, high) == (0.20, 0.40)
        assert mean == pytest.approx(0.30)

    def test_a_run_with_unknown_cost_does_not_become_zero(self):
        """Never emit 0.0 for a run that spent tokens. Under-reporting hurts
        exactly when someone is investigating a spike."""
        f = _fixture()
        report = aggregate([_record(f, [10], cost=None), _record(f, [10], cost=0.40)])
        low, high, _ = report.cost_range("f")
        assert low == 0.40 and high == 0.40
        assert report.unknown_cost_runs == 1

    def test_all_costs_unknown_reports_no_cost_rather_than_zero(self):
        f = _fixture()
        report = aggregate([_record(f, [10], cost=None)])
        assert report.cost_range("f") is None

    def test_incomplete_runs_still_report_their_cost(self):
        """A stopped run spent real money. Excluding it from recall does not
        make it free."""
        f = _fixture()
        report = aggregate([_record(f, [], cost=1.46, incomplete=True)])
        assert report.total_cost == pytest.approx(1.46)


class TestIncompleteRunsAreListedSeparately:
    def test_they_are_counted(self):
        f = _fixture()
        report = aggregate([_record(f, [10]), _record(f, [], incomplete=True)])
        assert report.complete == 1 and len(report.incomplete) == 1

    def test_each_carries_its_reason(self):
        f = _fixture()
        report = aggregate([_record(f, [], incomplete=True)])
        assert "MAX_TOOL_CALLS_EXCEEDED" in report.incomplete[0].score.stop_reason


class TestNovelFindings:
    def test_findings_matching_no_known_defect_are_surfaced(self):
        f = _fixture()
        report = aggregate([_record(f, [10, 9999])])
        assert report.novel_count == 1


class TestRendering:
    def _report(self):
        f = _fixture()
        return aggregate(
            [
                _record(f, [10, 200], cost=0.29),
                _record(f, [10], cost=0.34),
                _record(f, [10], cost=0.31),
                _record(f, [], cost=0.05, incomplete=True),
            ]
        )

    def test_it_names_the_configuration(self):
        assert "contract-passes" in render(self._report())

    def test_it_shows_a_per_defect_hit_rate(self):
        out = render(self._report())
        assert "3/3" in out and "1/3" in out

    def test_it_shows_a_range_rather_than_a_single_percentage(self):
        out = render(self._report())
        assert "1-2 of 2" in out

    def test_it_never_prints_a_bare_aggregate_recall_percentage(self):
        """The spec is explicit: a single number acquires authority it has not
        earned, and this project has already watched that happen three times."""
        assert "%" not in render(self._report())

    def test_it_lists_incomplete_runs_under_their_own_heading(self):
        out = render(self._report())
        assert "INCOMPLETE" in out.upper()
        assert "MAX_TOOL_CALLS_EXCEEDED" in out

    def test_it_puts_cost_beside_recall(self):
        out = render(self._report())
        assert "$" in out

    def test_it_breaks_recall_down_by_class(self):
        out = render(self._report())
        assert "security" in out and "local" in out

    def test_it_says_how_many_runs_the_numbers_rest_on(self):
        out = render(self._report())
        assert "3 complete" in out

    def test_it_warns_when_a_configuration_has_fewer_than_three_complete_runs(self):
        """FR4. One sample cannot see a plus-or-minus-one swing, and this
        project spent a milestone learning that."""
        f = _fixture()
        out = render(aggregate([_record(f, [10])]))
        assert "n=1" in out or "fewer than 3" in out

    def test_no_warning_when_there_are_enough_runs(self):
        assert "fewer than 3" not in render(self._report())

    def test_a_fixture_whose_every_run_stopped_says_so_rather_than_showing_zero(self):
        f = _fixture()
        out = render(aggregate([_record(f, [10], incomplete=True)]))
        assert "no complete run" in out

    def test_an_unknown_cost_is_called_a_floor_not_a_total(self):
        f = _fixture()
        out = render(aggregate([_record(f, [10], cost=None), _record(f, [10], cost=0.40)]))
        assert "unknown, not zero" in out and "floor" in out

    def test_a_novel_finding_is_surfaced_in_the_text(self):
        f = _fixture()
        out = render(aggregate([_record(f, [10, 9999])]))
        assert "NOVEL" in out

    def test_a_report_over_no_runs_at_all_does_not_crash(self):
        out = render(aggregate([]))
        assert "unknown" in out and "0 run(s)" in out
