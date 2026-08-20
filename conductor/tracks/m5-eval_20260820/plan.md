# Plan — M5: An evaluation harness

Follows [`../../workflow.md`](../../workflow.md). Tasks are *logic* (full TDD, >80% coverage) or *integration* (verified by a real run, recorded with the SDK version).

**The scorer is a logic module and carries this project's claims about quality.** It gets the same treatment the rate table got, for the same reason.

## Phase 1 — Fixtures [checkpoint: 26f9c4b]

- [x] **Task: Fixture format** *(logic)* — `0c056bf`
  - [x] A fixture names repo, base SHA, head SHA, and a list of defects
  - [x] Each defect: file, line, class (local / cross-file / convention / security), description
  - [x] Reject a fixture that names a PR without SHAs — a head that moves is a different review
- [x] **Task: Curate three fixtures** *(chore)* — `1e976d4`
  - [x] Start from pull requests `claude[bot]` reviewed, where findings are recorded and independent
  - [x] `doitbse/draft#538` at `5349acd3` is the first, with its four findings
  - [x] At least two repositories — four fixtures, two repositories, twenty defects, all four classes
  - **Fixture data is gitignored.** This repository is public and the reviewed pull requests are
    private; only the curation tooling and the format are committed. Stated in `evals/README.md`.
  - Only one repository has independently-reviewed pull requests (30+ scanned), so the second
    repository is the planted M1 fixture — and it is the set's only local/security coverage.
- [x] **Task: Reachability evidence is checked, not merely present** *(logic)* — `7684c96` — split
      from the combined task per [`../../workflow.md`](../../workflow.md): "a task that looks like
      both is two tasks"
  - [x] A defect must carry evidence of reachability
  - [x] A placeholder is not evidence — reject `TODO`, `yes`, `n/a` and their kin
  - [x] Gate a whole set before a run, so a weak fixture cannot quietly produce a number
- [x] **Task: Verify each recorded defect can actually manifest** *(integration)* — `791d2b1`
  - [x] Execute the planted fixture's defects, as M1's `return True` could not be — all five
        reproduced; recorded in [`probe-results.md`](../../../docs/probe-results.md)
  - [x] Say plainly which fixtures rest on executed evidence and which on a recorded trigger path
        — **5 executed, 15 recorded**, printed as separate lines and stated as a limitation, as M1's `return True` could not
- [x] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md)) — `26f9c4b`
  - 278 tests pass; the phase's three logic modules are at 100% coverage; ruff and mypy clean
  - Verification was **run by the agent**, not handed to the user, at the user's direction
  - Step 4 found real private-repository detail in two files and forced a scrub — recorded in
    the git note rather than quietly fixed

## Phase 2 — Scoring that survives paraphrase

- [x] **Task: Structured finding records** *(logic)* — `00b2b46`
  - [x] Reviewer emits file, line, claim rather than prose — `review.py` now parses through the
        same module, so the reviewer's output and the scorer's input are one definition
  - [x] Tolerate a line range and a near-miss line number; a finding is not wrong for being two
        lines off — ranges, reversed ranges, and a 3-line tolerance
- [x] **Task: The scorer** *(logic)* — `0949667`
  - [x] Match on **location first**, text only to disambiguate — text is a tie-breaker, never a veto
  - [x] A paraphrase of the same defect at the same location scores as found — proven on real data:
        **15/15 with every claim replaced by unrelated words**
  - [x] **Validate against a reference review before use** — `evals/validate_scorer.py`, two checks;
        the second reruns the first with the words scrubbed, which is the failure that happened
- [~] **Task: Incomplete runs are not clean runs** *(logic)*
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
