# Plan — M2: Cost tracking

Follows the methodology in [`../../workflow.md`](../../workflow.md). Each task is marked *logic* (full TDD: red, green, refactor, >80% coverage) or *integration* (verified by a probe run or a green CI job, with the observed behaviour recorded and the SDK version named).

**Ordering note:** the arithmetic comes first and is tested exhaustively, because it carries the project's actual claims about money. Nothing is wired into the reviewer until the numbers are right in isolation.

## Phase 1 — Rates, cited

- [x] **Task: Verify the rates against a primary source** *(chore)*
  - [x] Attempt the Vertex / Agent Platform pricing page; record what was actually readable
  - [x] Record the source URL and the verification date **in the data**, not in a comment above it
  - [x] If Vertex resists again, state the limitation in the caveats rather than quietly using AI Studio rates
- [x] **Task: Rate table** *(logic)*
  - [x] `Rate`, `Promo`, and the lookup, keyed by model **and** service tier
  - [x] Promotional rate applies before its end date, standard rate after — tested on both sides of the boundary
  - [x] Unknown model → tokens, no cost. Unknown tier → tokens, no cost. Never borrow a neighbouring rate
  - [x] Rates overridable for negotiated pricing
- [x] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))

## Phase 2 — The arithmetic

- [x] **Task: Cost calculation** *(logic)*
  - [x] Cached input at its multiplier — a test fails if it is ever treated as free
  - [x] Reasoning tokens at the **output** rate — a test fails if they are dropped
  - [x] Net uncached input computed the way the SDK computes it, not re-derived
  - [x] Returns tokens and `None` for cost when the rate is unknown, rather than zero
- [x] **Task: Per-turn collector** *(logic)*
  - [x] Accumulate per turn, so a failed run still reports what it spent
  - [x] Price each turn at the `service_tier` it reports, not at the session's
  - [x] Mixed-tier sessions sum correctly
- [x] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))

## Phase 3 — Wiring it to the reviewer

- [x] **Task: Pin the model and record it (FR8)** *(integration)*
  - [x] Pin `model` in the config; **do not** construct `GeminiModelOptions` — `thinking_level` stays M5's
  - [x] Verify against a run that the pinned value is what the harness actually used
- [x] **Task: Compaction and retry hooks (FR4, FR5)** *(integration)*
  - [x] `@hooks.on_compaction`, counted
  - [x] Retry counts recorded; note that `max_model_calls` does not bound them
- [x] **Task: Outputs (FR6, FR7)** *(logic + integration — split)*
  - [x] *Logic:* format the cost line and the artifact from a usage record, tested against fixtures
  - [x] *Integration:* post the line on the PR and upload `review-cost.json`
- [x] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))

## Phase 4 — Reconcile and close

- [ ] **Task: Reconcile one real review against billing** *(integration)* — 🔴 **BLOCKED: no BigQuery billing export exists on `sascha-playground-doit`**
  - [x] Run a review, note `cost_usd` — `$0.044709`, run 32354944747
  - [ ] Compare and record both figures with the date — **cannot: nothing to compare against**
  - [x] **If billing data is unavailable, record the criterion as unmet rather than waving it through** — done; recorded unmet in `probe-results.md` and the roadmap
- [x] **Task: Write up the evidence** *(chore)*
  - [x] Append results to `docs/probe-results.md`, naming the SDK version
  - [x] Check off M2 in `docs/roadmap.md`; update Q10
  - [x] Fold anything that changes a decision into `docs/cost-tracking.md`
- [x] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))


---

## 🔴 Exit criterion half met

*"Every review reports its cost"* — **met**. `~$0.0447` on the fixture PR, cost
line in the review body, `review-cost.json` uploaded on every run.

*"…and the same figure can be found in the billing export"* — **not met**.
`sascha-playground-doit` has no BigQuery billing export; `bq ls` across 200
datasets finds nothing billing-related.

**To unblock:** enable a BigQuery billing export on billing account
`01209B-4D4586-59A1B1`, wait for a review to land in it (typically hours), then
run the comparison. Everything else in this track is done.

This is left open rather than closed with a note, because the entire argument
for two sources is that self-reported cost is unverified cost — and this track
produced two plausible-looking wrong numbers before the real runs caught them.
