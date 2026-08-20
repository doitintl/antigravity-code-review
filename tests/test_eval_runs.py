"""An empty review and a clean review look identical. That is the whole of FR5.

Q8 measured it: a budget stop preserves usage and returns **empty text**. So a
run that was cut off mid-review produces exactly what a run that found nothing
produces, and the only thing that tells them apart is the stop reason.

This project has already got it wrong twice. Two diagnostic runs returned empty
text against a 3,000-token output cap, were read as "no findings", and the
opposite conclusion was drawn and written down. Later, a contract-pass run with
one of three passes crashed reported 2/4 as though three had run.

So: **a run that did not finish normally is `incomplete`, is excluded from
recall, and is never counted as having found nothing.** Its findings are kept
and reported — they are real — but they are not permitted to produce a
percentage, because the run never got to look for the rest.
"""

import pytest

from antigravity_code_review.evalharness.runs import (
    Outcome,
    RunOutcome,
    classify,
    combine,
    is_normal_stop,
)


class TestWhatCountsAsANormalStop:
    @pytest.mark.parametrize("stop", [None, "UNSPECIFIED", "StopReason.UNSPECIFIED"])
    def test_unspecified_and_absent_are_normal(self, stop):
        assert is_normal_stop(stop)

    @pytest.mark.parametrize(
        "stop",
        [
            "MAX_MODEL_CALLS_EXCEEDED",
            "StopReason.MAX_OUTPUT_TOKENS_EXCEEDED",
            "MAX_TOTAL_TOKENS_EXCEEDED",
            "MAX_INPUT_TOKENS_EXCEEDED",
        ],
    )
    def test_every_budget_stop_is_not(self, stop):
        assert not is_normal_stop(stop)

    def test_an_enum_is_read_the_same_as_its_string(self):
        class FakeStopReason:
            def __str__(self):
                return "StopReason.MAX_MODEL_CALLS_EXCEEDED"

        assert not is_normal_stop(FakeStopReason())

    def test_case_does_not_decide_it(self):
        assert is_normal_stop("unspecified")


class TestClassifying:
    def test_a_normal_stop_with_findings_is_complete(self):
        assert classify(None, text="{...}", findings=3).outcome is Outcome.COMPLETE

    def test_a_normal_stop_with_no_findings_is_still_complete(self):
        """A reviewer that looked and found nothing has finished. That is a
        real zero, and it is the only kind that may be counted as one."""
        result = classify(None, text="", findings=0)
        assert result.outcome is Outcome.COMPLETE

    def test_a_budget_stop_with_empty_text_is_incomplete(self):
        result = classify("MAX_OUTPUT_TOKENS_EXCEEDED", text="", findings=0)
        assert result.outcome is Outcome.INCOMPLETE

    def test_a_budget_stop_that_did_produce_findings_is_still_incomplete(self):
        """It never got to look for the rest, so its recall would be a floor
        reported as a measurement."""
        result = classify("MAX_TOOL_CALLS_EXCEEDED", text="{...}", findings=2)
        assert result.outcome is Outcome.INCOMPLETE

    def test_an_exception_is_incomplete_whatever_the_stop_reason_says(self):
        result = classify(None, error="AntigravityConnectionError: 403 spend cap")
        assert result.outcome is Outcome.INCOMPLETE
        assert "spend cap" in result.reason

    def test_the_stop_reason_is_recorded_verbatim(self):
        assert classify("MAX_MODEL_CALLS_EXCEEDED").stop_reason == "MAX_MODEL_CALLS_EXCEEDED"

    def test_the_reason_names_the_stop_so_a_reader_need_not_guess(self):
        assert "MAX_OUTPUT_TOKENS_EXCEEDED" in classify("MAX_OUTPUT_TOKENS_EXCEEDED").reason

    def test_the_reason_says_when_the_output_was_empty(self):
        """The specific trap: empty text after a stop reads as a clean review."""
        assert "empty" in classify("MAX_OUTPUT_TOKENS_EXCEEDED", text="").reason.lower()

    def test_a_complete_run_carries_no_reason(self):
        assert classify(None, text="x").reason is None


class TestCombiningTheStagesOfOneRun:
    """A review is several passes and a judge. One crashed pass makes the whole
    number a floor, and a run already reported 2/4 with a pass missing."""

    def test_all_complete_is_complete(self):
        combined = combine([classify(None), classify(None)])
        assert combined.outcome is Outcome.COMPLETE

    def test_one_incomplete_stage_makes_the_run_incomplete(self):
        combined = combine([classify(None), classify("MAX_TOOL_CALLS_EXCEEDED")])
        assert combined.outcome is Outcome.INCOMPLETE

    def test_the_combined_reason_names_every_stage_that_failed(self):
        combined = combine(
            [
                classify(None, stage="pass-1"),
                classify("MAX_TOOL_CALLS_EXCEEDED", stage="pass-2"),
                classify(None, error="boom", stage="judge"),
            ]
        )
        assert "pass-2" in combined.reason and "judge" in combined.reason
        assert "pass-1" not in combined.reason

    def test_combining_nothing_is_incomplete_not_complete(self):
        """No stages ran. That is not a clean review of anything."""
        assert combine([]).outcome is Outcome.INCOMPLETE

    def test_the_combined_stop_reason_keeps_the_first_abnormal_one(self):
        combined = combine([classify(None), classify("MAX_INPUT_TOKENS_EXCEEDED")])
        assert combined.stop_reason == "MAX_INPUT_TOKENS_EXCEEDED"


class TestTheOutcomeIsUsable:
    def test_incomplete_is_truthy_to_read(self):
        assert classify("MAX_MODEL_CALLS_EXCEEDED").incomplete
        assert not classify(None).incomplete

    def test_it_is_frozen(self):
        import dataclasses

        with pytest.raises(dataclasses.FrozenInstanceError):
            classify(None).outcome = Outcome.INCOMPLETE  # type: ignore[misc]

    def test_it_renders_for_a_report(self):
        line = str(classify("MAX_OUTPUT_TOKENS_EXCEEDED", text=""))
        assert "incomplete" in line.lower() and "MAX_OUTPUT_TOKENS_EXCEEDED" in line

    def test_a_complete_run_renders_plainly(self):
        assert str(classify(None)) == "complete"

    def test_it_is_a_run_outcome(self):
        assert isinstance(classify(None), RunOutcome)
