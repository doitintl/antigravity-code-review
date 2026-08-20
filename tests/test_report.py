"""The cost line and the artifact. What people actually read.

The line has to survive being quoted out of context, so it says what it is: an
estimate, with the rate that produced it.
"""

import json
from datetime import date

from antigravity_code_review.cost import TurnUsage, price_session
from antigravity_code_review.rates import FLASH, ServiceTier
from antigravity_code_review.report import cost_artifact, cost_line, review_body

INTRO = date(2026, 8, 20)


def session(**kw):
    turns = kw.pop("turns", [TurnUsage(prompt_tokens=100_000, cached_tokens=50_000,
                                       candidate_tokens=1_500, thought_tokens=3_000)])
    return price_session(turns, kw.pop("model", FLASH), kw.pop("on", INTRO))


class TestCostLine:
    def test_reports_turns_tokens_cache_rate_and_cost(self):
        line = cost_line(session(), tool_calls=31)
        assert "1 turn" in line
        assert "100,000 in" in line
        assert "50% cached" in line
        assert "$" in line

    def test_marks_the_figure_as_an_estimate(self):
        """It is an estimate until it shows up in the billing export."""
        assert "~" in cost_line(session(), tool_calls=0)

    def test_unknown_cost_says_so_rather_than_showing_zero(self):
        line = cost_line(session(model="nope"), tool_calls=0)
        assert "$0" not in line
        assert "unknown" in line.lower()

    def test_pluralises_turns(self):
        s = price_session([TurnUsage(prompt_tokens=10)] * 3, FLASH, INTRO)
        assert "3 turns" in cost_line(s, tool_calls=0)

    def test_does_not_claim_model_calls(self):
        """An SDK turn is one chat(); many model calls happen inside it."""
        assert "model call" not in cost_line(session(), tool_calls=11)

    def test_output_tokens_are_shown(self):
        assert "4,500 out" in cost_line(session(), tool_calls=0)


class TestArtifact:
    def test_is_valid_json(self):
        a = cost_artifact(session(), repo="o/r", pr=7, model=FLASH, tool_calls=31)
        json.dumps(a)

    def test_records_the_model_that_produced_the_figure(self):
        """Without it the rate applied is unattributable."""
        a = cost_artifact(session(), repo="o/r", pr=7, model=FLASH, tool_calls=31)
        assert a["model"] == FLASH

    def test_carries_the_token_breakdown(self):
        a = cost_artifact(session(), repo="o/r", pr=7, model=FLASH, tool_calls=0)
        assert a["tokens"]["prompt"] == 100_000
        assert a["tokens"]["cached"] == 50_000
        assert a["tokens"]["thoughts"] == 3_000

    def test_carries_compaction_and_retry_counts(self):
        a = cost_artifact(session(), repo="o/r", pr=7, model=FLASH, tool_calls=0,
                          compactions=2, retries={"api": 1, "model_output": 3})
        assert a["compactions"] == 2
        assert a["retries"]["model_output"] == 3

    def test_states_the_cache_storage_caveat(self):
        """Billed per token-hour and deliberately not counted here."""
        a = cost_artifact(session(), repo="o/r", pr=7, model=FLASH, tool_calls=0)
        assert any("cache storage" in c.lower() for c in a["caveats"])

    def test_states_the_estimate_caveat(self):
        a = cost_artifact(session(), repo="o/r", pr=7, model=FLASH, tool_calls=0)
        assert any("estimate" in c.lower() for c in a["caveats"])

    def test_unknown_cost_is_null_not_zero(self):
        a = cost_artifact(session(model="nope"), repo="o/r", pr=7, model="nope", tool_calls=0)
        assert a["cost_usd"] is None

    def test_records_service_tier_counts(self):
        s = price_session([TurnUsage(prompt_tokens=1, service_tier=ServiceTier.STANDARD)],
                          FLASH, INTRO)
        a = cost_artifact(s, repo="o/r", pr=7, model=FLASH, tool_calls=0)
        assert a["service_tiers"] == {"STANDARD": 1}

    def test_records_the_stop_reason(self):
        a = cost_artifact(session(), repo="o/r", pr=7, model=FLASH, tool_calls=0,
                          stop_reason="MAX_OUTPUT_TOKENS_EXCEEDED")
        assert a["stop_reason"] == "MAX_OUTPUT_TOKENS_EXCEEDED"

    def test_records_the_rate_source_so_the_figure_is_checkable(self):
        a = cost_artifact(session(), repo="o/r", pr=7, model=FLASH, tool_calls=0)
        assert a["rate_source"].startswith("https://")
        assert a["rate_verified_on"]


class TestReviewBody:
    """Written for the PR author, not for us."""

    def test_no_internal_implementation_detail(self):
        """'Posted by the runner, not by the agent' meant nothing to a reader."""
        b = review_body(session(), tool_calls=15, model=FLASH, findings=4)
        for leak in ("runner", "agent", "harness", "hook"):
            assert leak not in b.lower()

    def test_headline_states_the_finding_count(self):
        assert "4 findings" in review_body(session(), tool_calls=1, model=FLASH, findings=4)

    def test_singular_finding(self):
        assert "1 finding" in review_body(session(), tool_calls=1, model=FLASH, findings=1)

    def test_zero_findings_says_so_plainly(self):
        b = review_body(session(), tool_calls=1, model=FLASH, findings=0)
        assert "no issues found" in b.lower()

    def test_costs_are_a_table_not_a_log_line(self):
        b = review_body(session(), tool_calls=1, model=FLASH, findings=1)
        assert "|---|---|" in b
        assert "·" not in b

    def test_names_the_model_that_produced_it(self):
        assert FLASH in review_body(session(), tool_calls=1, model=FLASH, findings=1)

    def test_an_early_stop_is_called_out_prominently(self):
        b = review_body(session(), tool_calls=1, model=FLASH, findings=2,
                        stop_reason="MAX_OUTPUT_TOKENS_EXCEEDED")
        assert "incomplete" in b.lower()
        assert b.count(">") >= 1

    def test_a_normal_run_carries_no_warning(self):
        b = review_body(session(), tool_calls=1, model=FLASH, findings=2)
        assert "incomplete" not in b.lower()

    def test_the_estimate_caveat_is_present_but_subordinate(self):
        b = review_body(session(), tool_calls=1, model=FLASH, findings=1)
        assert "estimate" in b.lower()
        assert "<sub>" in b

    def test_unknown_cost_does_not_render_a_dollar_sign(self):
        b = review_body(session(model="nope"), tool_calls=1, model="nope", findings=1)
        assert "not available" in b
        assert "$" not in b
