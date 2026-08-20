"""The curation script's one piece of pure logic.

`_summarise` turns a reference reviewer's comment body into the one-sentence
description that every curated defect carries. It is small, and it is on the
path of every fixture this project will ever build: a bug here degrades the
whole set quietly, in a field a reader would assume was transcribed.

Everything else in `curate_fixture.py` shells out to `gh`. Per `workflow.md`
those are integration concerns, and a unit test over them would assert the mock.
"""

from curate_fixture import _summarise

BODY = (
    "\U0001f7e1 The new field renders for every page type, but the query only ever reads "
    "two of them.\n\n"
    "<details>\n<summary>Extended reasoning...</summary>\n\n"
    "**What happens:** a very long explanation that must not reach the fixture.\n"
    "</details>\n\n<!-- marker -->"
)


class TestTheReasoningFoldIsDropped:
    def test_the_extended_reasoning_is_not_carried_into_the_fixture(self):
        assert "must not reach the fixture" not in _summarise(BODY)

    def test_the_claim_itself_survives(self):
        assert "renders for every page type" in _summarise(BODY)

    def test_a_body_with_no_fold_is_kept_whole(self):
        assert _summarise("A plain finding with no fold.") == "A plain finding with no fold."


class TestTheLeadingSeverityMarkerIsStripped:
    def test_an_emoji_prefix_does_not_lead_the_description(self):
        assert _summarise(BODY).startswith("The new field")

    def test_a_backtick_opening_is_not_mistaken_for_decoration(self):
        """A finding may legitimately open with a code span."""
        assert _summarise("`buildLinks()` drops the parent path.").startswith("`buildLinks()`")

    def test_a_word_opening_is_left_alone(self):
        assert _summarise("Wrapped in a guard.").startswith("Wrapped")


class TestItIsOneReadableLine:
    def test_newlines_are_collapsed(self):
        assert "\n" not in _summarise("first line\nsecond line\n\nthird")

    def test_runs_of_whitespace_become_single_spaces(self):
        assert _summarise("a     b\t\tc") == "a b c"

    def test_it_is_capped_so_one_essay_cannot_dominate_a_fixture(self):
        assert len(_summarise("x " * 5000)) <= 400
