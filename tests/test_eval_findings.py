"""Findings as records, because scoring free text has already produced a false zero.

The reviewer emits one JSON object per line — file, line, claim. Scoring then
matches on **location first** and consults the text only to disambiguate. The
alternative was tried: a scorer greping for `"page type"` against a judge that
wrote `"pages"` reported 0/4 where the truth was 1/4 plus a novel defect. That
was the third time an instrument rather than the reviewer produced the headline
number in this project.

Two tolerances are the point of this module rather than an indulgence:

- **a line range**, because a finding about a function is about a span;
- **a near-miss line**, because a reviewer that says line 214 about a defect
  recorded at 216 has found it. A scorer that says otherwise is measuring
  transcription, not review.
"""

import pytest

from antigravity_code_review.evalharness.findings import Finding, parse_findings


class TestParsingWhatTheModelActuallyEmits:
    def test_one_object_per_line(self):
        out = parse_findings('{"file":"a.ts","line":3,"claim":"boom"}')
        assert len(out) == 1
        assert out[0].file == "a.ts" and out[0].line == 3 and out[0].claim == "boom"

    def test_a_markdown_fence_does_not_lose_the_findings(self):
        """Asked for bare JSON, a model wraps it in a fence anyway."""
        text = '```json\n{"file":"a.ts","line":1,"claim":"x"}\n```'
        assert len(parse_findings(text)) == 1

    def test_prose_around_the_json_is_ignored(self):
        text = 'Here is what I found:\n{"file":"a.ts","line":1,"claim":"x"}\nThat is all.'
        assert len(parse_findings(text)) == 1

    def test_one_malformed_line_does_not_lose_the_others(self):
        text = '{"file":"a.ts","line":1,"claim":"x"}\n{not json\n{"file":"b.ts","line":2,"claim":"y"}'
        assert len(parse_findings(text)) == 2

    def test_a_finding_with_no_claim_is_dropped(self):
        assert parse_findings('{"file":"a.ts","line":1}') == []

    def test_a_finding_with_no_file_is_dropped(self):
        assert parse_findings('{"line":1,"claim":"x"}') == []

    def test_empty_output_is_no_findings(self):
        assert parse_findings("") == []

    def test_a_json_array_is_accepted_too(self):
        """Instructed to emit one per line, a model sometimes emits a list."""
        out = parse_findings('[{"file":"a.ts","line":1,"claim":"x"},'
                             '{"file":"b.ts","line":2,"claim":"y"}]')
        assert len(out) == 2


class TestLineRanges:
    def test_a_dash_range_is_kept_as_a_span(self):
        f = parse_findings('{"file":"a.ts","line":"120-135","claim":"x"}')[0]
        assert f.line == 120 and f.end_line == 135

    def test_explicit_start_and_end_fields_are_read(self):
        f = parse_findings('{"file":"a.ts","start_line":10,"end_line":20,"claim":"x"}')[0]
        assert f.line == 10 and f.end_line == 20

    def test_a_single_line_spans_only_itself(self):
        f = parse_findings('{"file":"a.ts","line":7,"claim":"x"}')[0]
        assert f.line == 7 and f.end_line == 7

    def test_a_missing_line_is_allowed_and_spans_nothing(self):
        f = parse_findings('{"file":"a.ts","claim":"x"}')[0]
        assert f.line is None and f.end_line is None

    def test_a_reversed_range_is_normalised_rather_than_dropped(self):
        f = parse_findings('{"file":"a.ts","line":"135-120","claim":"x"}')[0]
        assert f.line == 120 and f.end_line == 135

    def test_a_line_written_as_a_string_is_read(self):
        assert parse_findings('{"file":"a.ts","line":"42","claim":"x"}')[0].line == 42

    def test_a_line_that_is_not_a_number_is_dropped_not_guessed(self):
        f = parse_findings('{"file":"a.ts","line":"somewhere near the top","claim":"x"}')[0]
        assert f.line is None


class TestPathsAreCompared_NotTranscribed:
    @pytest.mark.parametrize("written", ["src/a.ts", "./src/a.ts", "/src/a.ts", "a/src/a.ts"])
    def test_diff_and_shell_prefixes_are_normalised_away(self, written):
        """`a/` and `b/` come off a unified diff; `./` off a shell."""
        assert parse_findings(f'{{"file":"{written}","line":1,"claim":"x"}}')[0].file == "src/a.ts"

    def test_backslashes_become_forward_slashes(self):
        assert parse_findings('{"file":"src\\\\a.ts","line":1,"claim":"x"}')[0].file == "src/a.ts"

    def test_the_path_as_written_is_kept_for_reporting(self):
        f = parse_findings('{"file":"./src/a.ts","line":1,"claim":"x"}')[0]
        assert f.file_as_written == "./src/a.ts"


class TestCovers:
    def test_a_span_covers_its_own_lines(self):
        f = Finding(file="a.ts", line=10, end_line=20, claim="x")
        assert f.covers(10) and f.covers(15) and f.covers(20)

    def test_a_span_does_not_cover_a_distant_line(self):
        assert not Finding(file="a.ts", line=10, end_line=20, claim="x").covers(400)

    def test_a_near_miss_is_covered_within_the_tolerance(self):
        """A reviewer that says 214 about a defect recorded at 216 has found it."""
        f = Finding(file="a.ts", line=214, end_line=214, claim="x")
        assert f.covers(216, tolerance=3)

    def test_outside_the_tolerance_is_not_covered(self):
        f = Finding(file="a.ts", line=214, end_line=214, claim="x")
        assert not f.covers(230, tolerance=3)

    def test_the_tolerance_extends_a_range_at_both_ends(self):
        f = Finding(file="a.ts", line=100, end_line=110, claim="x")
        assert f.covers(97, tolerance=3) and f.covers(113, tolerance=3)
        assert not f.covers(96, tolerance=3)

    def test_a_finding_with_no_line_covers_anything_in_its_file(self):
        """A file-level finding is not wrong for declining to guess a line."""
        assert Finding(file="a.ts", line=None, end_line=None, claim="x").covers(9999)

    def test_covering_a_missing_target_line_is_true_for_any_finding_in_the_file(self):
        assert Finding(file="a.ts", line=10, end_line=10, claim="x").covers(None)


class TestTheRecordIsUsable:
    def test_a_finding_is_frozen(self):
        import dataclasses

        f = Finding(file="a.ts", line=1, end_line=1, claim="x")
        with pytest.raises(dataclasses.FrozenInstanceError):
            f.file = "b.ts"  # type: ignore[misc]

    def test_it_round_trips_to_the_dict_the_runner_posts(self):
        f = parse_findings('{"file":"a.ts","line":3,"claim":"boom"}')[0]
        assert f.as_comment() == {"file": "a.ts", "line": 3, "claim": "boom"}

    def test_a_range_posts_at_its_first_line(self):
        f = parse_findings('{"file":"a.ts","line":"10-20","claim":"x"}')[0]
        assert f.as_comment()["line"] == 10
