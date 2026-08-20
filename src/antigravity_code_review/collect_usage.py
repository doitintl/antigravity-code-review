"""Accumulate usage as the review runs, not once at the end.

Two reasons, both from `cost-tracking.md`:

**It survives a failed run.** A session stopped by a budget still spent money,
and reading `total_usage` after an exception gets nothing. Per-turn accumulation
means the cost line is reportable whatever happened.

**`service_tier` is per request.** Priority traffic downgraded to standard bills
at standard, and a session-level tier would quietly miss that.

Compactions are counted here too. A compaction rewrites the prompt prefix, which
invalidates the cache, and is therefore the likeliest explanation for a cache
rate that suddenly drops on a repeated review.
"""

from __future__ import annotations

from typing import Any

from google.antigravity.hooks import hooks

from antigravity_code_review.cost import TurnUsage


class UsageCollector:
    """Gathers per-turn usage, compactions and retries over one review."""

    def __init__(self) -> None:
        self.turns: list[TurnUsage] = []
        self.compactions: int = 0
        self.tool_calls: int = 0
        self._last_totals: tuple[int, int, int, int] = (0, 0, 0, 0)
        self._conversation: Any = None

    def bind(self, conversation: Any) -> None:
        """Attach the conversation so the post-turn hook can read usage from it.

        `PostTurnArgs` carries only `response_text` — verified against the proto
        descriptor for 0.1.12 — so the hook payload cannot supply usage. The
        conversation can, but only exists after the Agent is constructed, which
        is after the hooks are registered. Hence binding rather than injection.
        """
        self._conversation = conversation

    def record_cumulative(self, usage: Any, service_tier: Any = None) -> None:
        """Record a turn from a cumulative usage snapshot.

        `Conversation.total_usage` is cumulative, so each turn's own consumption
        is the difference from the previous reading. Recording the snapshot
        directly would count every earlier turn again on every turn.
        """
        if usage is None:
            return
        prompt = int(getattr(usage, "prompt_token_count", 0) or 0)
        cached = int(getattr(usage, "cached_content_token_count", 0) or 0)
        candidates = int(getattr(usage, "candidates_token_count", 0) or 0)
        thoughts = int(getattr(usage, "thoughts_token_count", 0) or 0)

        prev = self._last_totals
        delta = TurnUsage(
            prompt_tokens=max(prompt - prev[0], 0),
            cached_tokens=max(cached - prev[1], 0),
            candidate_tokens=max(candidates - prev[2], 0),
            thought_tokens=max(thoughts - prev[3], 0),
            service_tier=service_tier or getattr(usage, "service_tier", None),
        )
        self._last_totals = (prompt, cached, candidates, thoughts)

        # A turn that consumed nothing is not a turn worth pricing, and would
        # skew the model-call count the cost line reports.
        if delta.total_tokens:
            self.turns.append(delta)

    def hooks(self) -> list[Any]:
        """Hooks to register on the agent config."""

        @hooks.on_compaction
        async def count_compaction(_data: Any) -> None:
            self.compactions += 1

        @hooks.post_tool_call
        async def count_tool_call(_data: Any) -> None:
            self.tool_calls += 1

        @hooks.post_turn
        async def snapshot_turn(_data: Any) -> None:
            """Snapshot after every turn, not once at the end.

            A first version recorded only the final cumulative reading, so a
            multi-turn review reported "1 model call" and priced the whole
            session at whichever tier the last request happened to use.

            The usage comes from the bound conversation rather than the hook
            payload, because PostTurnArgs has exactly one field and it is the
            response text.
            """
            if self._conversation is None:
                return
            usage = getattr(self._conversation, "total_usage", None)
            tier = None
            last = getattr(self._conversation, "last_turn_usage", None)
            if last is not None:
                tier = getattr(last, "service_tier", None)
            if usage is not None:
                self.record_cumulative(usage, service_tier=tier)

        return [count_compaction, count_tool_call, snapshot_turn]
