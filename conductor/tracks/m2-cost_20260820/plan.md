# Plan — M2: Cost tracking

Follows the methodology in [`../../workflow.md`](../../workflow.md). Each task is marked *logic* (full TDD: red, green, refactor, >80% coverage) or *integration* (verified by a probe run or a green CI job, with the observed behaviour recorded and the SDK version named).

**Ordering note:** the arithmetic comes first and is tested exhaustively, because it carries the project's actual claims about money. Nothing is wired into the reviewer until the numbers are right in isolation.

## Phase 1 — Rates, cited

- [ ] **Task: Verify the rates against a primary source** *(chore)*
  - [ ] Attempt the Vertex / Agent Platform pricing page; record what was actually readable
  - [ ] Record the source URL and the verification date **in the data**, not in a comment above it
  - [ ] If Vertex resists again, state the limitation in the caveats rather than quietly using AI Studio rates
- [ ] **Task: Rate table** *(logic)*
  - [ ] `Rate`, `Promo`, and the lookup, keyed by model **and** service tier
  - [ ] Promotional rate applies before its end date, standard rate after — tested on both sides of the boundary
  - [ ] Unknown model → tokens, no cost. Unknown tier → tokens, no cost. Never borrow a neighbouring rate
  - [ ] Rates overridable for negotiated pricing
- [ ] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))

## Phase 2 — The arithmetic

- [ ] **Task: Cost calculation** *(logic)*
  - [ ] Cached input at its multiplier — a test fails if it is ever treated as free
  - [ ] Reasoning tokens at the **output** rate — a test fails if they are dropped
  - [ ] Net uncached input computed the way the SDK computes it, not re-derived
  - [ ] Returns tokens and `None` for cost when the rate is unknown, rather than zero
- [ ] **Task: Per-turn collector** *(logic)*
  - [ ] Accumulate per turn, so a failed run still reports what it spent
  - [ ] Price each turn at the `service_tier` it reports, not at the session's
  - [ ] Mixed-tier sessions sum correctly
- [ ] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))

## Phase 3 — Wiring it to the reviewer

- [ ] **Task: Pin the model and record it (FR8)** *(integration)*
  - [ ] Pin `model` in the config; **do not** construct `GeminiModelOptions` — `thinking_level` stays M5's
  - [ ] Verify against a run that the pinned value is what the harness actually used
- [ ] **Task: Compaction and retry hooks (FR4, FR5)** *(integration)*
  - [ ] `@hooks.on_compaction`, counted
  - [ ] Retry counts recorded; note that `max_model_calls` does not bound them
- [ ] **Task: Outputs (FR6, FR7)** *(logic + integration — split)*
  - [ ] *Logic:* format the cost line and the artifact from a usage record, tested against fixtures
  - [ ] *Integration:* post the line on the PR and upload `review-cost.json`
- [ ] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))

## Phase 4 — Reconcile and close

- [ ] **Task: Reconcile one real review against billing** *(integration)*
  - [ ] Run a review, note `cost_usd`, wait for the billing export window
  - [ ] Compare and record both figures with the date
  - [ ] **If billing data is unavailable, record the criterion as unmet rather than waving it through**
- [ ] **Task: Write up the evidence** *(chore)*
  - [ ] Append results to `docs/probe-results.md`, naming the SDK version
  - [ ] Check off M2 in `docs/roadmap.md`; update Q10
  - [ ] Fold anything that changes a decision into `docs/cost-tracking.md`
- [ ] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))
