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

## Phase 2 — Scoring that survives paraphrase [checkpoint: 722ddec]

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
- [x] **Task: Incomplete runs are not clean runs** *(logic)* — `722ddec`
  - [x] A run with a non-normal `stop_reason` is `incomplete`, excluded from recall, never counted
        as zero findings — implemented stronger than FR5's wording: **any** non-normal stop is
        incomplete, even one that produced findings, because its recall is a floor
  - [x] `combine()` rolls the passes and the judge into one outcome — the missing check that let a
        run with a crashed pass report 2/4 as though three had run
  - [x] `review.py` classifies through the same function, so the reviewer and the harness cannot
        disagree about what "finished" means
- [x] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md)) — `722ddec`
  - 375 tests pass; all six harness modules at 100%; ruff and mypy clean
  - **The check has teeth:** a reconstructed keyword scorer scores 4/4 on the reference text and
    **0/4 with the words replaced** — the published false zero, reproduced on demand — while the
    location scorer holds 4/4

## Phase 3 — The harness [checkpoint: abcc54e]

**Order swapped, deliberately.** The report is pure logic and it defines the run record the
runner has to emit; building the runner first would mean inventing that record twice. The
runner is also the expensive half, and it should not be written against a guess.

- [x] **Task: Report** *(logic)* — `1c935e6`
  - [x] Per-defect hit rate across runs, not one number
  - [x] Broken down by defect class
  - [x] Cost per run beside recall — unknown cost stays unknown; the total is labelled a floor
  - [x] Incomplete runs listed separately — and still charged for
  - [x] **`render()` contains no percent sign**, and a test enforces it
- [~] **Task: Runner** *(integration)*
  - [x] Check out a fixture at its head SHA, run a named configuration, collect findings and cost —
        validated end to end: **4/5 found, complete, `$0.0780`, 123,095 tokens, 53 tool calls**
  - [x] Checkout is blobless and cached by `(repo, sha)` — ~5s cold for a 2,400-file tree, free after
  - [x] Drives `review.run_passes` rather than a copy — a harness that reimplements the pipeline
        measures the reimplementation
  - [x] `evals/run_eval.py` gates on reachability **and** scorer validation before any model call
  - [x] Repeat N times (N ≥ 3) per configuration — **12 runs, 4 fixtures, 2 repositories,
        `$3.4765`**; 11 complete, 1 incomplete (a 429 on the judge, correctly excluded from
        recall and still charged)
  - [x] `evals/rescore.py` — re-score saved runs against corrected fixtures without re-spending.
        Earned its place immediately: a fixture defect cost `$0` to correct rather than `$3.48`
- [x] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md)) — `abcc54e`
  - 438 tests pass; all seven logic modules at 100%; ruff and mypy clean
  - **The phase found a defect in itself:** the harness reported a false 0/4 because a defect was
    recorded as a point where the reference text had named a span. Caught only because unmatched
    findings are kept as `novel` rather than discarded. Corrected cross-file 0/25 → 2/25, for `$0`

## Phase 4 — Replace the single-sample numbers

- [x] **Task: Measure the contract-pass configuration properly** *(integration)* — `72e18f9`
  - [x] Run it ≥3 times over all fixtures — 12 runs, 4 fixtures, 2 repositories, `$3.4765`
  - [x] Compare against the single-sample figures in `probe-results.md` and correct them
  - **By class:** security 4/6, local 5/11, **cross-file 2/25**, **convention 0/11**
  - **The single-sample figures held, and the reason they held is now known:** the 0/4 recorded
    for `draft#538` reproduced at 0–1 of 4 over three runs. What changed is that it is no longer
    an anecdote — cross-file blindness is stable across two repositories, not a bad draw
  - **The harness produced a false 0/4 and corrected it for `$0`** — a defect recorded as a point
    where the reference text had named a span. Cross-file 0/25 → 2/25
- [ ] **Task: Re-test what was rejected on one sample** *(integration)*
  - [ ] Batching, `thinking_level`, judge tooling were each rejected on n=1
  - [ ] Some may have been rejected on noise. Say which
  - **Arms built and ready:** `contract-passes+judge` (the baseline, AC8),
    `contract-passes-only` (does the judge help at all), and
    `contract-passes+judge+high-thinking` (`thinking_level=HIGH`, rejected on n=1)
  - **Batching is deliberately not re-tested.** It failed its pre-registered bar on *both* axes —
    0/4 recall at $0.70 against 0/4 at $0.39 — so noise is not what rejected it. Re-running it
    would cost a full sweep to re-establish the half of the result that was never in doubt.
    Recorded as a decision, not an omission
  - **Judge tooling is not re-tested either.** Giving the judge tools was one prompt change
    measured once; the arm that matters more is whether the judge helps *at all*, which
    `contract-passes-only` answers. Said plainly rather than quietly dropped
- [ ] **Task: Write up the evidence** *(chore)*
  - [ ] Record results with the SDK version; check off M5 in `docs/roadmap.md`
- [ ] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))
