# Plan — M5: An evaluation harness

Follows [`../../workflow.md`](../../workflow.md). Tasks are *logic* (full TDD, >80% coverage) or *integration* (verified by a real run, recorded with the SDK version).

**The scorer is a logic module and carries this project's claims about quality.** It gets the same treatment the rate table got, for the same reason.

## Phase 1 — Fixtures

- [ ] **Task: Fixture format** *(logic)*
  - [ ] A fixture names repo, base SHA, head SHA, and a list of defects
  - [ ] Each defect: file, line, class (local / cross-file / convention / security), description
  - [ ] Reject a fixture that names a PR without SHAs — a head that moves is a different review
- [ ] **Task: Curate three fixtures** *(chore)*
  - [ ] Start from pull requests `claude[bot]` reviewed, where findings are recorded and independent
  - [ ] `doitbse/draft#538` at `5349acd3` is the first, with its four findings
  - [ ] At least two repositories
- [ ] **Task: Reachability check** *(logic + integration)*
  - [ ] *Logic:* a defect must carry evidence of reachability
  - [ ] *Integration:* verify each recorded defect can actually manifest, as M1's `return True` could not
- [ ] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))

## Phase 2 — Scoring that survives paraphrase

- [ ] **Task: Structured finding records** *(logic)*
  - [ ] Reviewer emits file, line, claim rather than prose
  - [ ] Tolerate a line range and a near-miss line number; a finding is not wrong for being two lines off
- [ ] **Task: The scorer** *(logic)*
  - [ ] Match on **location first**, text only to disambiguate
  - [ ] A paraphrase of the same defect at the same location scores as found
  - [ ] **Validate against a reference review before use** — a scorer that cannot find the defects in `claude[bot]`'s own text reports a false zero for everything
- [ ] **Task: Incomplete runs are not clean runs** *(logic)*
  - [ ] A run with a non-normal `stop_reason` is `incomplete`, excluded from recall, never counted as zero findings
- [ ] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))

## Phase 3 — The harness

- [ ] **Task: Runner** *(integration)*
  - [ ] Check out a fixture at its head SHA, run a named configuration, collect findings and cost
  - [ ] Repeat N times (N ≥ 3) per configuration
- [ ] **Task: Report** *(logic)*
  - [ ] Per-defect hit rate across runs, not one number
  - [ ] Broken down by defect class
  - [ ] Cost per run beside recall
  - [ ] Incomplete runs listed separately
- [ ] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))

## Phase 4 — Replace the single-sample numbers

- [ ] **Task: Measure the contract-pass configuration properly** *(integration)*
  - [ ] Run it ≥3 times over all fixtures
  - [ ] Compare against the single-sample figures in `probe-results.md` and correct them
- [ ] **Task: Re-test what was rejected on one sample** *(integration)*
  - [ ] Batching, `thinking_level`, judge tooling were each rejected on n=1
  - [ ] Some may have been rejected on noise. Say which
- [ ] **Task: Write up the evidence** *(chore)*
  - [ ] Record results with the SDK version; check off M5 in `docs/roadmap.md`
- [ ] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))
