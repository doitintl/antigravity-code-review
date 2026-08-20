"""The rate table carries this project's claims about money.

Every test here corresponds to a rule cost-tracking.md states in prose. The
sharpest one is that an unknown rate must produce *no* cost rather than a
plausible one: a missing number is obvious, a wrong one is invisible and gets
quoted in meetings.
"""

from datetime import date

import pytest

from antigravity_code_review.rates import (
    FLASH,
    Rate,
    ServiceTier,
    lookup,
)

BEFORE = date(2026, 8, 20)   # inside the introductory window
AFTER = date(2027, 6, 1)     # after it lapses
BOUNDARY_LAST = date(2026, 12, 31)
BOUNDARY_FIRST = date(2027, 1, 1)


class TestStandardTier:
    def test_introductory_rate_applies_before_the_end_date(self):
        r = lookup(FLASH, ServiceTier.STANDARD, BEFORE)
        assert r.input_per_m == 0.75
        assert r.output_per_m == 3.75

    def test_standard_rate_applies_after(self):
        r = lookup(FLASH, ServiceTier.STANDARD, AFTER)
        assert r.input_per_m == 1.50
        assert r.output_per_m == 7.50

    def test_the_boundary_is_inclusive_of_the_last_day(self):
        assert lookup(FLASH, ServiceTier.STANDARD, BOUNDARY_LAST).input_per_m == 0.75
        assert lookup(FLASH, ServiceTier.STANDARD, BOUNDARY_FIRST).input_per_m == 1.50


class TestCachedInput:
    def test_cached_input_is_priced_not_free(self):
        """Pricing cached reads at zero overstates the saving on every review."""
        r = lookup(FLASH, ServiceTier.STANDARD, BEFORE)
        assert r.cached_input_per_m > 0

    def test_cached_input_is_one_tenth_of_input(self):
        r = lookup(FLASH, ServiceTier.STANDARD, BEFORE)
        assert r.cached_input_per_m == pytest.approx(r.input_per_m * 0.1)


class TestOtherTiers:
    def test_priority_is_published_and_dearer(self):
        std = lookup(FLASH, ServiceTier.STANDARD, BEFORE)
        pri = lookup(FLASH, ServiceTier.PRIORITY, BEFORE)
        assert pri.input_per_m > std.input_per_m

    def test_flex_is_published_and_cheaper(self):
        std = lookup(FLASH, ServiceTier.STANDARD, BEFORE)
        flex = lookup(FLASH, ServiceTier.FLEX, BEFORE)
        assert flex.input_per_m < std.input_per_m

    def test_every_tier_has_both_periods(self):
        for tier in ServiceTier:
            assert lookup(FLASH, tier, BEFORE) is not None
            assert lookup(FLASH, tier, AFTER) is not None


class TestUnknownMeansUnknown:
    def test_unknown_model_has_no_rate(self):
        assert lookup("gemini-99-imaginary", ServiceTier.STANDARD, BEFORE) is None

    def test_unknown_model_does_not_borrow_a_neighbour(self):
        assert lookup("gemini-3.6-flash", ServiceTier.STANDARD, BEFORE) is None

    def test_unknown_tier_has_no_rate(self):
        assert lookup(FLASH, "SUPER_PRIORITY", BEFORE) is None

    def test_none_tier_has_no_rate(self):
        assert lookup(FLASH, None, BEFORE) is None


class TestProvenance:
    def test_every_rate_carries_a_source_and_a_date(self):
        """A rate without a source and a date is a defect, however right it is."""
        for tier in ServiceTier:
            for when in (BEFORE, AFTER):
                r = lookup(FLASH, tier, when)
                assert r.source.startswith("https://")
                assert date.fromisoformat(r.verified_on)


class TestOverrides:
    def test_a_negotiated_rate_can_replace_the_published_one(self):
        custom = Rate(
            input_per_m=0.10, cached_input_per_m=0.01, output_per_m=0.50,
            effective_until=None, source="https://example.invalid/contract",
            verified_on="2026-08-20",
        )
        r = lookup(FLASH, ServiceTier.STANDARD, BEFORE, overrides={FLASH: {ServiceTier.STANDARD: [custom]}})
        assert r.input_per_m == 0.10

    def test_overrides_do_not_leak_into_the_published_table(self):
        lookup(FLASH, ServiceTier.STANDARD, BEFORE,
               overrides={FLASH: {ServiceTier.STANDARD: []}})
        assert lookup(FLASH, ServiceTier.STANDARD, BEFORE).input_per_m == 0.75


class TestTierCasing:
    """The SDK emits lowercase; published tables write uppercase. Accept both."""

    def test_sdk_lowercase_value_resolves(self):
        assert lookup(FLASH, "standard", BEFORE) is not None

    def test_uppercase_string_resolves(self):
        assert lookup(FLASH, "STANDARD", BEFORE) is not None

    def test_sdk_enum_instance_resolves(self):
        from google.antigravity.models import ServiceTier as SdkTier
        assert lookup(FLASH, SdkTier.STANDARD, BEFORE) is not None

    def test_our_values_match_the_sdk_values(self):
        """If these drift apart, every real run prices as unknown."""
        from google.antigravity.models import ServiceTier as SdkTier
        assert {t.value for t in ServiceTier} == {t.value for t in SdkTier}
