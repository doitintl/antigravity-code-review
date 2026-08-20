"""Usage accounting.

Pure logic, deliberately separated from the agent call so it can be tested
without an SDK or a network. Everything here is a claim about money, which is
this project's central claim, so it is the part that earns full TDD.
"""

from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass(frozen=True)
class Usage:
    """A turn's token counts, normalised.

    The SDK reports every field as `int | None`. `None` and `0` mean different
    things — absent versus measured-as-zero — and conflating them is how a cost
    tracker reports $0.00 for a run that spent real money.
    """

    prompt: int
    cached: int
    candidates: int
    thoughts: int
    total: int
    service_tier: str | None
    populated: bool

    @property
    def uncached(self) -> int:
        """Net uncached input — the cost-relevant quantity.

        `cached_content_token_count` is a *subset of* `prompt_token_count`, not
        an addition to it, so the uncached portion is the difference.
        """
        return max(0, self.prompt - self.cached)

    @property
    def output(self) -> int:
        """Billable output. Thinking tokens bill at the output rate and are
        reported separately, so a sum of prompt + candidates misses them."""
        return self.candidates + self.thoughts

    @property
    def cache_rate(self) -> float | None:
        """Fraction of input served from cache, or None when there was no input."""
        if self.prompt <= 0:
            return None
        return self.cached / self.prompt


def _int(value: Any) -> int:
    return int(value) if isinstance(value, int) else 0


def read_usage(metadata: Any) -> Usage:
    """Normalise an SDK `UsageMetadata` into a `Usage`.

    `populated` is False when the object is absent or reports no tokens at all.
    The SDK's own guidance warns that a failed run may report zero, so a
    zero-token result is treated as suspect rather than free — the caller
    records it as unknown, never as 0.0.
    """
    if metadata is None:
        return Usage(0, 0, 0, 0, 0, None, populated=False)

    prompt = _int(getattr(metadata, "prompt_token_count", None))
    cached = _int(getattr(metadata, "cached_content_token_count", None))
    candidates = _int(getattr(metadata, "candidates_token_count", None))
    thoughts = _int(getattr(metadata, "thoughts_token_count", None))
    total = _int(getattr(metadata, "total_token_count", None))

    tier = getattr(metadata, "service_tier", None)
    tier_name = getattr(tier, "value", None) or (str(tier) if tier is not None else None)

    return Usage(
        prompt=prompt,
        cached=cached,
        candidates=candidates,
        thoughts=thoughts,
        total=total,
        service_tier=tier_name,
        populated=(prompt + candidates + thoughts + total) > 0,
    )


def format_usage(usage: Usage) -> str:
    """One line, always present, whether or not anything was measured."""
    if not usage.populated:
        return "usage: NOT REPORTED (treat as unknown, not zero)"

    rate = usage.cache_rate
    cache_part = f" ({rate:.0%} cached)" if rate is not None else ""
    tier = usage.service_tier or "unknown"
    return (
        f"{usage.prompt:,} in{cache_part} · "
        f"{usage.candidates:,} out · {usage.thoughts:,} thinking · "
        f"{usage.total:,} total · tier={tier}"
    )
