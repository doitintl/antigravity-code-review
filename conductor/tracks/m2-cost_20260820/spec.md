# Spec — M2: Cost tracking

**Type:** Feature
**Milestone:** M2 — [`../../../docs/roadmap.md`](../../../docs/roadmap.md)
**Closes:** Q10 (as far as it can be closed)

## Overview

M1 produces reviews. It does not say what they cost. Eight runs measured 117–127k tokens each, and the only dollar figure attached to that so far was priced against an *assumed* model — which is precisely the uncited-rate defect [`cost-tracking.md`](../../../docs/cost-tracking.md) forbids.

This track makes every review report its cost, and makes that figure checkable against the billing export rather than merely plausible.

Most of the design is already fixed in [`cost-tracking.md`](../../../docs/cost-tracking.md): the rate table structure, the PR comment format, the `review-cost.json` shape, and what is deliberately not claimed. This spec consolidates it and pins what was open.

## Decisions taken for this track

| Question | Decision | Why |
|---|---|---|
| Pin the model? | **Yes — pin `model`, keep `thinking_level` unset** | The rate table keys on the model. The pinned value is the SDK's own documented default, so this changes no behaviour, only whether the rate is knowable. `thinking_level` is a separate axis and stays M5's to measure |
| Rate source | **Try Vertex; ship with a stated caveat either way** | A rate without a source and a date is a defect. A cited rate with a stated limitation satisfies that rule; a silent assumption does not |
| Reconciliation | **One manual check; defer the scheduled job** | The exit criterion asks that the figure *be findable* in billing, not that a cron job find it. The job also needs a billing export that may not exist |

## Functional requirements

**FR1 — Rate table.** Rates as data, not comments, each carrying its source URL and verification date. Promotional rates carry an end date so the figure is right on both sides of it. Cached input priced at its multiplier, never as free. Reasoning tokens priced at the **output** rate. Rates overridable for negotiated pricing.

**FR2 — Unknown means unknown.** An unrecognised model *or* an unrecognised `service_tier` reports tokens and **no cost**. It never borrows a neighbouring rate. `ServiceTier` has three members and only standard rates are published.

**FR3 — Per-turn accumulation.** Usage is accumulated per turn, not read once at the end: it survives a failed run, and `service_tier` is per request. Each turn is priced at the tier it *reports* — priority traffic downgraded to standard bills at standard.

**FR4 — Compaction counting.** Register `@hooks.on_compaction` and count compactions. A compaction rewrites the prefix and is the likeliest explanation for a low cache rate.

**FR5 — Retry counting.** Record retry counts. M0 measured a retried turn at 7.4× a clean one, and `max_model_calls` does not bound them.

**FR6 — Cost line on the PR.** One line, always present, including the cache rate — the single most actionable number.

**FR7 — `review-cost.json` artifact.** The shape fixed in `cost-tracking.md`: repo, pr, model, turns, tool calls, token breakdown, service tiers, compactions, retries, `cost_usd`, `rate_applied`, `stop_reason`, and `caveats`.

**FR8 — Model pinned and recorded.** `model` pinned in the config and recorded in the artifact alongside the figure, so the rate applied is attributable. `GeminiModelOptions` is still never constructed.

**FR9 — One manual reconciliation.** One real review's `cost_usd` compared against the billing export for the same window, and the comparison recorded with its date and the figures on both sides.

## Non-functional requirements

- **Every rate cited.** Source URL and verification date in the data, not in a comment above it.
- **The figure is an estimate** until it appears in billing, and says so.
- **Pure-logic modules under full TDD**, >80% coverage. The arithmetic carries the project's claims about money.
- **No new credentials.** Reconciliation reads billing with existing access or is recorded as not-yet-possible.

## Acceptance criteria

1. **Every review posts a cost line and uploads `review-cost.json`.** This is the exit criterion's first half.
2. **One real review's figure is reconciled against the billing export**, with both numbers and the date recorded. Exit criterion's second half.
3. An unknown model reports tokens and no cost, demonstrated by a test.
4. An unknown `service_tier` reports tokens and no cost, demonstrated by a test.
5. Cached input is priced at its multiplier; a test fails if it is ever treated as free.
6. Reasoning tokens are priced at the output rate; a test fails if they are dropped.
7. A promotional rate applies before its end date and the standard rate after, demonstrated by tests on both sides of the boundary.
8. The model that produced a figure is recorded in the artifact.
9. Compaction and retry counts appear in the artifact.

## Out of scope

The dollar ceiling and `budget_for()` translation (M3) · repository rules (M4) · the eval harness (M5) · the composite Action (M6) · the **scheduled** reconciliation job · cache-storage billing, which is per token-hour and explicitly not claimed · cost per acted-on finding, which is the metric that matters and needs resolved-comment tracking.

## Risks

**Vertex rates may stay unverified.** The page resisted three fetch attempts in M0. Mitigated by citing what was actually read and stating the limitation in `caveats`, rather than by quietly using AI Studio rates.

**The billing export may not exist or may lag.** Billing data is typically delayed by hours. If reconciliation cannot be completed, that is recorded as an unmet criterion rather than waved through.

**A wrong rate is invisible.** This is why unknown-means-unknown is a functional requirement and not a nicety: a missing number is obvious, a wrong one gets quoted in meetings.
