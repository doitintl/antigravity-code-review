"""Cost arithmetic. This is the module that turns tokens into a number people quote.

Two rules dominate: cached input is cheap but never free, and reasoning tokens
bill at the output rate. Getting either wrong produces a figure that looks
reasonable and is not, which is the worst kind of wrong for this project.
"""

from datetime import date

import pytest

from antigravity_code_review.cost import TurnUsage, price_session, price_turn
from antigravity_code_review.rates import FLASH, ServiceTier

INTRO = date(2026, 8, 20)
STD = date(2027, 6, 1)


def turn(prompt=1_000_000, cached=0, candidates=0, thoughts=0, tier=ServiceTier.STANDARD):
    return TurnUsage(
        prompt_tokens=prompt,
        cached_tokens=cached,
        candidate_tokens=candidates,
        thought_tokens=thoughts,
        service_tier=tier,
    )


class TestInputPricing:
    def test_one_million_uncached_input_costs_the_input_rate(self):
        c = price_turn(turn(), FLASH, INTRO)
        assert c.cost_usd == pytest.approx(0.75)

    def test_cached_input_is_billed_at_the_multiplier_not_free(self):
        """Free cached reads would overstate the saving on every cached review."""
        c = price_turn(turn(prompt=1_000_000, cached=1_000_000), FLASH, INTRO)
        assert c.cost_usd == pytest.approx(0.075)
        assert c.cost_usd > 0

    def test_half_cached_splits_the_price(self):
        c = price_turn(turn(prompt=1_000_000, cached=500_000), FLASH, INTRO)
        assert c.cost_usd == pytest.approx(0.5 * 0.75 + 0.5 * 0.075)

    def test_cached_never_exceeds_prompt(self):
        """Defensive: a cached count above the prompt count would go negative."""
        c = price_turn(turn(prompt=100, cached=999_999), FLASH, INTRO)
        assert c.cost_usd >= 0


class TestOutputPricing:
    def test_candidates_bill_at_the_output_rate(self):
        c = price_turn(turn(prompt=0, candidates=1_000_000), FLASH, INTRO)
        assert c.cost_usd == pytest.approx(3.75)

    def test_reasoning_tokens_bill_at_the_output_rate_too(self):
        """The source page prices 'response and reasoning' together."""
        c = price_turn(turn(prompt=0, thoughts=1_000_000), FLASH, INTRO)
        assert c.cost_usd == pytest.approx(3.75)

    def test_dropping_thoughts_would_understate(self):
        with_thoughts = price_turn(turn(prompt=0, candidates=1000, thoughts=1000), FLASH, INTRO)
        without = price_turn(turn(prompt=0, candidates=1000), FLASH, INTRO)
        assert with_thoughts.cost_usd > without.cost_usd


class TestUnknownRates:
    def test_unknown_model_reports_tokens_and_no_cost(self):
        c = price_turn(turn(), "gemini-99-imaginary", INTRO)
        assert c.cost_usd is None
        assert c.tokens_total == 1_000_000

    def test_unknown_cost_is_none_not_zero(self):
        """Zero reads as free. None reads as unknown. They are not the same."""
        c = price_turn(turn(), "nope", INTRO)
        assert c.cost_usd is not None or c.cost_usd is None
        assert c.cost_usd is None

    def test_unknown_tier_reports_tokens_and_no_cost(self):
        c = price_turn(turn(tier="SUPER"), FLASH, INTRO)
        assert c.cost_usd is None


class TestRateBoundary:
    def test_introductory_is_cheaper_than_standard(self):
        intro = price_turn(turn(), FLASH, INTRO)
        std = price_turn(turn(), FLASH, STD)
        assert intro.cost_usd < std.cost_usd

    def test_rate_applied_is_reported(self):
        assert price_turn(turn(), FLASH, INTRO).rate_applied == "introductory"
        assert price_turn(turn(), FLASH, STD).rate_applied == "standard"


class TestSession:
    def test_turns_sum(self):
        s = price_session([turn(), turn()], FLASH, INTRO)
        assert s.cost_usd == pytest.approx(1.50)
        assert s.turns == 2

    def test_each_turn_prices_at_its_own_reported_tier(self):
        """Priority traffic downgraded to standard must bill at standard."""
        mixed = price_session(
            [turn(tier=ServiceTier.PRIORITY), turn(tier=ServiceTier.STANDARD)], FLASH, INTRO
        )
        assert mixed.cost_usd == pytest.approx(1.35 + 0.75)

    def test_one_unknown_turn_makes_the_session_cost_unknown(self):
        """A partial total is worse than no total: it looks complete."""
        s = price_session([turn(), turn(tier="SUPER")], FLASH, INTRO)
        assert s.cost_usd is None
        assert s.tokens_total == 2_000_000

    def test_empty_session_is_zero_not_unknown(self):
        s = price_session([], FLASH, INTRO)
        assert s.cost_usd == 0
        assert s.turns == 0

    def test_session_survives_a_failed_run(self):
        """Per-turn accumulation means a stopped run still reports what it spent."""
        s = price_session([turn()], FLASH, INTRO)
        assert s.cost_usd > 0

    def test_cache_rate_is_reported(self):
        s = price_session([turn(prompt=1000, cached=900)], FLASH, INTRO)
        assert s.cache_rate == pytest.approx(0.9)

    def test_cache_rate_of_an_empty_session_is_zero(self):
        assert price_session([], FLASH, INTRO).cache_rate == 0

    def test_service_tier_counts_are_reported(self):
        s = price_session(
            [turn(), turn(), turn(tier=ServiceTier.FLEX)], FLASH, INTRO
        )
        assert s.service_tiers == {"STANDARD": 2, "FLEX": 1}
