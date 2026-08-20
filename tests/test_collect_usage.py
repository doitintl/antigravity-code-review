"""Per-turn accumulation from cumulative snapshots."""

import types

from antigravity_code_review.collect_usage import UsageCollector


def snap(prompt=0, cached=0, candidates=0, thoughts=0, tier="STANDARD"):
    return types.SimpleNamespace(
        prompt_token_count=prompt, cached_content_token_count=cached,
        candidates_token_count=candidates, thoughts_token_count=thoughts,
        service_tier=tier,
    )


class TestDeltas:
    def test_first_turn_is_the_whole_snapshot(self):
        c = UsageCollector()
        c.record_cumulative(snap(prompt=100, candidates=10))
        assert c.turns[0].prompt_tokens == 100

    def test_second_turn_is_the_difference_not_the_total(self):
        """total_usage is cumulative; recording it directly double-counts."""
        c = UsageCollector()
        c.record_cumulative(snap(prompt=100))
        c.record_cumulative(snap(prompt=250))
        assert c.turns[1].prompt_tokens == 150
        assert sum(t.prompt_tokens for t in c.turns) == 250

    def test_a_turn_that_consumed_nothing_is_not_recorded(self):
        c = UsageCollector()
        c.record_cumulative(snap(prompt=100))
        c.record_cumulative(snap(prompt=100))
        assert len(c.turns) == 1

    def test_none_usage_is_ignored(self):
        c = UsageCollector()
        c.record_cumulative(None)
        assert c.turns == []

    def test_all_none_fields_do_not_crash(self):
        c = UsageCollector()
        c.record_cumulative(types.SimpleNamespace(
            prompt_token_count=None, cached_content_token_count=None,
            candidates_token_count=None, thoughts_token_count=None, service_tier=None))
        assert c.turns == []

    def test_a_decreasing_counter_never_goes_negative(self):
        c = UsageCollector()
        c.record_cumulative(snap(prompt=200))
        c.record_cumulative(snap(prompt=100))
        assert all(t.prompt_tokens >= 0 for t in c.turns)

    def test_tier_is_carried_per_turn(self):
        c = UsageCollector()
        c.record_cumulative(snap(prompt=10, tier="FLEX"))
        assert c.turns[0].service_tier == "FLEX"

    def test_partial_run_still_reports_what_it_spent(self):
        """The reason for accumulating rather than reading the total at the end."""
        c = UsageCollector()
        c.record_cumulative(snap(prompt=100, candidates=5))
        assert sum(t.total_tokens for t in c.turns) == 105


class TestHooks:
    def test_returns_registerable_hooks(self):
        assert len(UsageCollector().hooks()) == 3

    def test_counters_start_at_zero(self):
        c = UsageCollector()
        assert c.compactions == 0 and c.tool_calls == 0


class TestBinding:
    def test_unbound_collector_ignores_the_turn_hook(self):
        """PostTurnArgs carries only response_text, so usage comes from the
        conversation. Without one bound there is nothing to read, and that must
        not raise mid-review."""
        c = UsageCollector()
        assert c._conversation is None
        assert c.turns == []

    def test_bind_attaches_the_conversation(self):
        c = UsageCollector()
        c.bind(object())
        assert c._conversation is not None
