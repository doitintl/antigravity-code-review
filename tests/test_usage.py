"""Tests for usage accounting.

Each case here corresponds to a way a cost figure has actually been got wrong,
either in this project's own drafts or in the SDK's documented traps.
"""

from __future__ import annotations

import types as pytypes

import pytest

from antigravity_code_review.usage import format_usage, read_usage


def meta(**kw):
    """A stand-in for the SDK's UsageMetadata. Fields default to None, as the
    real object does, so tests exercise the None handling rather than dodge it."""
    defaults = {
        "prompt_token_count": None,
        "cached_content_token_count": None,
        "candidates_token_count": None,
        "thoughts_token_count": None,
        "total_token_count": None,
        "service_tier": None,
    }
    return pytypes.SimpleNamespace(**{**defaults, **kw})


class TestReadUsage:
    def test_absent_metadata_is_not_populated(self):
        u = read_usage(None)
        assert u.populated is False
        assert u.total == 0

    def test_all_none_is_not_populated(self):
        # The SDK reports every field as int | None. A run that failed before
        # spending anything looks exactly like this, and must not read as $0.00.
        u = read_usage(meta())
        assert u.populated is False

    def test_zero_tokens_is_not_populated(self):
        # Documented trap: a failed run "may be reported as 0". Zero is treated
        # as suspect, not as free.
        u = read_usage(meta(prompt_token_count=0, total_token_count=0))
        assert u.populated is False

    def test_reads_all_fields(self):
        u = read_usage(
            meta(
                prompt_token_count=10_889,
                cached_content_token_count=7_185,
                candidates_token_count=2,
                thoughts_token_count=24,
                total_token_count=10_915,
            )
        )
        assert u.populated is True
        assert (u.prompt, u.cached, u.candidates, u.thoughts, u.total) == (
            10_889,
            7_185,
            2,
            24,
            10_915,
        )

    def test_service_tier_enum_is_unwrapped(self):
        tier = pytypes.SimpleNamespace(value="standard")
        assert read_usage(meta(prompt_token_count=5, service_tier=tier)).service_tier == "standard"

    def test_service_tier_plain_string_survives(self):
        assert read_usage(meta(prompt_token_count=5, service_tier="priority")).service_tier == "priority"


class TestDerivedQuantities:
    def test_uncached_is_prompt_minus_cached(self):
        # cached_content_token_count is a SUBSET of prompt_token_count, not an
        # addition. Treating it as additive double-counts the input.
        u = read_usage(meta(prompt_token_count=1_000, cached_content_token_count=900))
        assert u.uncached == 100

    def test_uncached_never_negative(self):
        u = read_usage(meta(prompt_token_count=100, cached_content_token_count=500))
        assert u.uncached == 0

    def test_output_includes_thinking(self):
        # Thinking tokens bill at the output rate. Summing prompt + candidates
        # misses them entirely on any model that thinks.
        u = read_usage(meta(candidates_token_count=100, thoughts_token_count=250))
        assert u.output == 350

    def test_cache_rate(self):
        u = read_usage(meta(prompt_token_count=1_000, cached_content_token_count=250))
        assert u.cache_rate == pytest.approx(0.25)

    def test_cache_rate_is_none_without_input(self):
        assert read_usage(meta(candidates_token_count=5)).cache_rate is None


class TestFormatUsage:
    def test_unpopulated_says_so_rather_than_showing_zeros(self):
        out = format_usage(read_usage(None))
        assert "NOT REPORTED" in out
        assert "unknown, not zero" in out

    def test_populated_line_carries_every_component(self):
        out = format_usage(
            read_usage(
                meta(
                    prompt_token_count=22_852,
                    cached_content_token_count=7_185,
                    candidates_token_count=105,
                    thoughts_token_count=188,
                    total_token_count=23_145,
                    service_tier="standard",
                )
            )
        )
        assert "22,852 in" in out
        assert "31% cached" in out
        assert "105 out" in out
        assert "188 thinking" in out
        assert "tier=standard" in out

    def test_missing_tier_reads_unknown(self):
        assert "tier=unknown" in format_usage(read_usage(meta(prompt_token_count=1)))

    def test_no_cache_fragment_when_no_input(self):
        assert "cached" not in format_usage(read_usage(meta(candidates_token_count=3)))
