"""Turn tokens into dollars, per turn, and refuse to guess.

Three decisions here are load-bearing, and each exists because the alternative
produces a number that looks right:

**Cached input is cheap, never free.** Pricing it at zero overstates the saving
on every cached review, and cached reads are the majority of a repeated one.

**Reasoning tokens bill at the output rate.** The pricing page prices "response
and reasoning" together. Dropping thoughts understates a thinking model badly.

**Unknown is None, not zero.** Zero reads as free and sums silently into a
total. None propagates, so a session containing one unpriceable turn reports no
cost at all rather than a partial figure that looks complete.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from antigravity_code_review.rates import Rate, ServiceTier, lookup

PER_MILLION = 1_000_000


@dataclass(frozen=True)
class TurnUsage:
    """One request's usage, as the SDK reports it.

    `service_tier` is per request rather than per session, which is why turns
    are priced individually: priority traffic downgraded to standard bills at
    standard, and a session-level tier would miss that.
    """

    prompt_tokens: int = 0
    cached_tokens: int = 0
    candidate_tokens: int = 0
    thought_tokens: int = 0
    service_tier: ServiceTier | str | None = ServiceTier.STANDARD

    @property
    def uncached_prompt_tokens(self) -> int:
        """Never negative: a cached count above the prompt count would invert the sum."""
        return max(self.prompt_tokens - self.cached_tokens, 0)

    @property
    def billable_cached_tokens(self) -> int:
        return min(self.cached_tokens, self.prompt_tokens)

    @property
    def output_tokens(self) -> int:
        """Candidates and thoughts together — the page prices them as one."""
        return self.candidate_tokens + self.thought_tokens

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.output_tokens


@dataclass(frozen=True)
class PricedTurn:
    tokens_total: int
    cost_usd: float | None
    rate_applied: str | None


@dataclass(frozen=True)
class PricedSession:
    turns: int
    tokens_prompt: int
    tokens_cached: int
    tokens_candidates: int
    tokens_thoughts: int
    tokens_total: int
    cost_usd: float | None
    rate_applied: str | None
    service_tiers: dict[str, int] = field(default_factory=dict)

    @property
    def cache_rate(self) -> float:
        """Share of prompt tokens served from cache. The most actionable number."""
        if not self.tokens_prompt:
            return 0.0
        return self.tokens_cached / self.tokens_prompt


def _cost_of(usage: TurnUsage, rate: Rate) -> float:
    return (
        usage.uncached_prompt_tokens * rate.input_per_m
        + usage.billable_cached_tokens * rate.cached_input_per_m
        + usage.output_tokens * rate.output_per_m
    ) / PER_MILLION


def _label(rate: Rate) -> str:
    return "introductory" if rate.is_introductory else "standard"


def price_turn(usage: TurnUsage, model: str, on: date, **kw) -> PricedTurn:
    """Price one turn at the tier it reports."""
    rate = lookup(model, usage.service_tier, on, **kw)
    if rate is None:
        return PricedTurn(tokens_total=usage.total_tokens, cost_usd=None, rate_applied=None)
    return PricedTurn(
        tokens_total=usage.total_tokens,
        cost_usd=_cost_of(usage, rate),
        rate_applied=_label(rate),
    )


def price_session(turns: list[TurnUsage], model: str, on: date, **kw) -> PricedSession:
    """Price a whole session, accumulating per turn.

    Accumulating per turn rather than reading the total at the end is what makes
    the figure survive a failed run: a session stopped by a budget still reports
    what it already spent.
    """
    total = 0.0
    unknown = False
    labels: set[str] = set()
    tiers: Counter[str] = Counter()

    for t in turns:
        priced = price_turn(t, model, on, **kw)
        if priced.cost_usd is None:
            unknown = True
        else:
            total += priced.cost_usd
        if priced.rate_applied:
            labels.add(priced.rate_applied)
        raw = getattr(t.service_tier, "value", t.service_tier)
        tiers[str(raw).upper() if raw is not None else "UNKNOWN"] += 1

    return PricedSession(
        turns=len(turns),
        tokens_prompt=sum(t.prompt_tokens for t in turns),
        tokens_cached=sum(t.billable_cached_tokens for t in turns),
        tokens_candidates=sum(t.candidate_tokens for t in turns),
        tokens_thoughts=sum(t.thought_tokens for t in turns),
        tokens_total=sum(t.total_tokens for t in turns),
        # One unpriceable turn makes the whole figure unknown. A partial total
        # is worse than none: it looks complete and is quietly short.
        cost_usd=None if unknown else total,
        rate_applied=", ".join(sorted(labels)) or None,
        service_tiers=dict(tiers),
    )
