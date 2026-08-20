"""Triviality gating and finding parsing — the two pure pieces of the review path."""

from antigravity_code_review.review import is_trivial, parse_findings


def f(name="a.ts", adds=10, dels=0, patch="@@ -1 +1 @@"):
    return {"filename": name, "additions": adds, "deletions": dels, "patch": patch}


class TestTriviality:
    """A one-line typo fix should not cost thirty cents."""

    def test_a_one_line_change_is_trivial(self):
        assert is_trivial([f(adds=1, dels=0)]) is not None

    def test_a_substantial_single_file_change_is_not(self):
        assert is_trivial([f(adds=40)]) is None

    def test_two_files_are_not_trivial_even_if_small(self):
        assert is_trivial([f("a.ts", 1), f("b.ts", 1)]) is None

    def test_no_files_is_skipped(self):
        assert "no files" in is_trivial([])

    def test_all_generated_files_is_skipped(self):
        """A PR of nothing but undiffable artefacts has nothing to review."""
        reason = is_trivial([{"filename": "big.json", "additions": 9000, "deletions": 0}])
        assert reason and "no reviewable diffs" in reason

    def test_the_reason_is_stated_not_just_a_boolean(self):
        """A skipped review must say why, or it looks like a failure."""
        assert isinstance(is_trivial([f(adds=1)]), str)


class TestParseFindings:
    def test_parses_one_json_object_per_line(self):
        out = parse_findings('{"file":"a.ts","line":3,"claim":"boom"}')
        assert out == [{"file": "a.ts", "line": 3, "claim": "boom"}]

    def test_tolerates_a_markdown_fence(self):
        """Asked for bare JSON, a model will sometimes fence it anyway.

        Losing every finding to a stray ``` is an expensive way to be strict.
        """
        text = '```json\n{"file":"a.ts","line":3,"claim":"boom"}\n```'
        assert len(parse_findings(text)) == 1

    def test_skips_prose_around_the_json(self):
        text = 'Here are the defects:\n{"file":"a.ts","line":1,"claim":"x"}\nThat is all.'
        assert len(parse_findings(text)) == 1

    def test_a_missing_line_is_allowed(self):
        out = parse_findings('{"file":"a.ts","claim":"x"}')
        assert out[0]["line"] is None

    def test_a_finding_without_a_claim_is_dropped(self):
        assert parse_findings('{"file":"a.ts","line":1}') == []

    def test_malformed_json_does_not_lose_the_valid_lines(self):
        text = '{"file":"a.ts","line":1,"claim":"x"}\n{not json}\n{"file":"b.ts","line":2,"claim":"y"}'
        assert len(parse_findings(text)) == 2

    def test_empty_output_means_no_defects(self):
        assert parse_findings("") == []
