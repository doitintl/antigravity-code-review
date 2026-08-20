"""Published rates, as data, each carrying where it came from and when.

**A rate without a source and a date is a defect**, however right it happens to
be. An uncited figure is indistinguishable from a plausible guess, and nobody
reviewing this file can tell the two apart. So provenance lives in the data
rather than in a comment above it, where it cannot drift away from the number.

Every figure below was read from the Agent Platform pricing page on the date
recorded. That page resisted three fetch attempts during M0, which is why Q10
stood open with the rates corroborated only from AI Studio; it resolved on
2026-08-20 and these are the primary-source figures.

Two things the primary source settled that the earlier design had wrong:

- **Priority and flex rates *are* published.** M0 recorded that "only standard
  rates are published" and reasoned that unknown tiers fall under the
  unknown-rate rule. They are all listed, so all three are priced here.
- **Region changes the rate.** Non-global endpoints cost ~10% more. This project
  pins `location="global"`, so the global column applies — but the assumption is
  now explicit rather than accidental.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

SOURCE = "https://cloud.google.com/vertex-ai/generative-ai/pricing"
VERIFIED_ON = "2026-08-20"

# The model this project pins. Named rather than inlined so the rate table and
# the agent configuration cannot disagree about which model is being priced.
FLASH = "gemini-3.7-flash"


class ServiceTier(str, Enum):
    """Mirrors the SDK's ServiceTier, values included.

    The values are **lowercase** because that is what the SDK emits. A first
    version used uppercase and every real run priced as "unknown tier" — caught
    only because unknown-means-unknown refuses to guess. Had it fallen back to a
    neighbouring rate, every review would have been silently mispriced instead.
    """

    STANDARD = "standard"
    PRIORITY = "priority"
    FLEX = "flex"


@dataclass(frozen=True)
class Rate:
    """Dollars per million tokens, for one model, tier and period.

    `effective_until` is the last date this rate applies, inclusive. `None`
    means open-ended. Time-boxing the introductory rate in the data is what
    makes the figure right on both sides of the boundary: hardcoding the promo
    overstates savings the day it lapses, and hardcoding the standard rate
    overstates cost while it runs.
    """

    input_per_m: float
    cached_input_per_m: float
    output_per_m: float
    effective_until: date | None
    source: str
    verified_on: str

    @property
    def is_introductory(self) -> bool:
        return self.effective_until is not None


def _period(inp: float, cached: float, out: float, until: date | None) -> Rate:
    return Rate(
        input_per_m=inp,
        cached_input_per_m=cached,
        output_per_m=out,
        effective_until=until,
        source=SOURCE,
        verified_on=VERIFIED_ON,
    )


_INTRO_ENDS = date(2026, 12, 31)

# Global-endpoint rates. Output covers "response and reasoning" on the source
# page, which is the primary-source confirmation that thinking tokens bill at
# the output rate rather than an inference from a docstring.
RATES: dict[str, dict[ServiceTier, list[Rate]]] = {
    FLASH: {
        ServiceTier.STANDARD: [
            _period(0.75, 0.075, 3.75, _INTRO_ENDS),
            _period(1.50, 0.15, 7.50, None),
        ],
        ServiceTier.PRIORITY: [
            _period(1.35, 0.135, 6.75, _INTRO_ENDS),
            _period(2.70, 0.27, 13.50, None),
        ],
        ServiceTier.FLEX: [
            _period(0.375, 0.0375, 1.875, _INTRO_ENDS),
            _period(0.75, 0.075, 3.75, None),
        ],
    },
}


def lookup(
    model: str,
    tier: ServiceTier | str | None,
    on: date,
    overrides: dict[str, dict[ServiceTier, list[Rate]]] | None = None,
) -> Rate | None:
    """Return the rate in force on `on`, or None when it is not known.

    Returning None rather than a neighbouring rate is the whole point. A missing
    number is obvious to whoever reads the report; a wrong one is invisible and
    gets quoted.

    `overrides` allows negotiated pricing without editing the published table,
    and never mutates it.
    """
    table = overrides if overrides is not None else RATES
    by_tier = table.get(model)
    if by_tier is None:
        return None

    # Case-insensitive on purpose. The SDK emits lowercase, published tables
    # write it uppercase, and a case mismatch should not read as an unknown tier.
    try:
        raw = getattr(tier, "value", tier)
        key = ServiceTier(str(raw).lower()) if raw is not None else None
    except (ValueError, AttributeError):
        return None
    if key is None:
        return None

    for rate in by_tier.get(key, []):
        if rate.effective_until is None or on <= rate.effective_until:
            return rate
    return None
