"""The byte cap is the only thing standing between a generated file and a dead review.

design.md is blunt about this: every BudgetConfig dial is a session total, so
none of them refuses a single oversized prompt. The cap is not defence in depth,
it is the defence. These tests treat it that way.
"""

from antigravity_code_review.truncation import DEFAULT_CAP_BYTES, truncate


class TestUnderTheCap:
    def test_short_text_is_returned_unchanged(self):
        assert truncate("hello", "a.py") == "hello"

    def test_exactly_at_the_cap_is_not_truncated(self):
        text = "x" * DEFAULT_CAP_BYTES
        assert truncate(text, "a.py") == text

    def test_empty_file(self):
        assert truncate("", "a.py") == ""


class TestOverTheCap:
    def test_one_byte_over_truncates(self):
        text = "x" * (DEFAULT_CAP_BYTES + 1)
        assert truncate(text, "a.py") != text

    def test_marker_names_the_file_and_both_sizes(self):
        text = "x" * (DEFAULT_CAP_BYTES + 500)
        out = truncate(text, "docs/openapi.json")
        assert "TRUNCATED" in out
        assert "docs/openapi.json" in out
        assert f"{DEFAULT_CAP_BYTES + 500:,}" in out
        assert f"{DEFAULT_CAP_BYTES:,}" in out

    def test_truncation_is_loud_not_silent(self):
        """A silently shortened file is worse than an absent one."""
        out = truncate("x" * (DEFAULT_CAP_BYTES * 2), "big.json")
        assert "TRUNCATED" in out.upper()

    def test_head_of_the_file_is_preserved(self):
        text = "IMPORTANT_FIRST_LINE\n" + "x" * (DEFAULT_CAP_BYTES * 2)
        assert "IMPORTANT_FIRST_LINE" in truncate(text, "big.txt")

    def test_marker_comes_first_so_it_survives_downstream_truncation(self):
        """The harness truncates tool output again, and we cannot configure it.

        A trailing marker gets cut off, and a live run proved it: the model saw
        only the harness's generic notice and never learned which file was cut.
        """
        out = truncate("x" * (DEFAULT_CAP_BYTES * 2), "big.json")
        assert out.startswith("[TRUNCATED:")

    def test_marker_survives_an_aggressive_downstream_cut(self):
        out = truncate("x" * (DEFAULT_CAP_BYTES * 2), "docs/openapi.json")
        assert "docs/openapi.json" in out[:300]


class TestCapsBySizeNotByName:
    """A denylist only covers the generated files someone already imagined."""

    def test_source_file_truncates_exactly_like_generated_json(self):
        big = "x" * (DEFAULT_CAP_BYTES + 100)
        py = truncate(big, "src/app.py")
        js = truncate(big, "package-lock.json")
        assert ("TRUNCATED" in py) == ("TRUNCATED" in js)

    def test_small_lockfile_is_not_truncated(self):
        assert truncate("{}", "package-lock.json") == "{}"


class TestMultibyte:
    def test_does_not_split_a_multibyte_character(self):
        """Cutting mid-character would produce text the model cannot read."""
        text = "é" * DEFAULT_CAP_BYTES  # 2 bytes each, so well over the cap
        out = truncate(text, "accents.txt")
        out.encode("utf-8")  # must not raise
        assert "TRUNCATED" in out

    def test_byte_cap_is_measured_in_bytes_not_characters(self):
        text = "é" * (DEFAULT_CAP_BYTES // 2 + 10)
        assert "TRUNCATED" in truncate(text, "accents.txt")


class TestCustomCap:
    def test_cap_is_configurable(self):
        assert "TRUNCATED" in truncate("x" * 101, "a.py", cap_bytes=100)
