# Spec — M5: An evaluation harness

**Type:** Feature
**Milestone:** M5 — [`../../../docs/roadmap.md`](../../../docs/roadmap.md)

## Overview

M2.5 established that naming the contract question takes surfaced findings from 0/4 to 3–4/4 on a real pull request. It also established that **nothing further can be measured**: run-to-run variance now exceeds the interventions being tested, and three separate times an instrument rather than the reviewer produced the headline number.

This track builds the thing that makes review quality measurable. It is not a later refinement; it is the precondition for any further claim about how good the reviewer is.

## What went wrong without it

Recorded because the harness exists to prevent each of these:

| # | error | effect |
|---|---|---|
| 1 | compared against the PR **head**, two fix commits after the reviewed code | measured different source and called it a miss |
| 2 | a budget stop returns **empty text** (Q8), read as "no findings" | two runs interpreted backwards |
| 3 | keyword scoring keyed on `"page type"`; the judge wrote `"pages"` | a correctly reported finding scored 0 |
| 4 | single sample per configuration | ±1 finding swing with no code change |

**All four understated the reviewer.** A harness that repeats them is worse than none, because its numbers carry authority.

## Functional requirements

**FR1 — Fixtures pinned by commit.** Each fixture names a repository, a **base SHA** and a **head SHA**, never a PR number alone. A pull request's head moves; a review of a moved head is a review of different code.

**FR2 — Reachability checked.** A planted or recorded defect must be shown to be reachable before it counts. M1's fixture contained a defect shadowed by an earlier `TypeError`, and would have scored a correct triage decision as a miss.

**FR3 — Structured findings.** The reviewer emits findings as records — file, line, claim — not prose. Scoring matches on **location first**, and text only to disambiguate. Keyword matching over free text has already produced one false zero.

**FR4 — Repeated runs.** Every configuration runs **N times** (N ≥ 3). The report gives per-defect hit rate across runs, not a single number. A defect found in 2 of 3 runs is a different fact from one found in 3 of 3.

**FR5 — Stop reasons are first-class.** Every run records its `stop_reason`. An empty result after a non-normal stop is reported as **incomplete**, never as clean.

**FR6 — Defect classes.** Each known defect is tagged — local, cross-file contract, convention, security. M1 measured recall varying sharply by class, and a single aggregate number would average those into something that moves for unattributable reasons.

**FR7 — Cost per run**, from M2's collector, reported alongside recall. A configuration that finds one more defect for four times the money is a different trade from one that finds it for free.

**FR8 — Configurations are comparable.** A run names the configuration that produced it, so contract-pass variants can be compared without rebuilding the harness.

## Non-functional requirements

- **Fixtures are real pull requests**, not constructed ones. M1's four-file fixture made the failure mode it needed to expose structurally impossible.
- **Reproducible from a clean checkout**, given the SHAs.
- **The harness is cheap to run** or it will not be run.
- **Pure-logic modules under full TDD.** The scorer carries the project's claims about quality, exactly as the rate table carries its claims about money.

## Acceptance criteria

1. **At least three fixture pull requests** from at least two repositories, each pinned by base and head SHA.
2. Every recorded defect is **verified reachable**.
3. Findings are matched on **file and line**; a paraphrase of the same defect scores as found, and the scorer is validated against a **reference review** before use.
4. Each configuration runs **≥3 times**, reporting per-defect hit rate.
5. Runs stopped early are reported as **incomplete**, and excluded from recall.
6. Recall is broken down **by defect class**.
7. Cost per run is reported beside recall.
8. **The `draft#538` result is reproduced** — the contract-pass configuration measured over repeated runs, replacing the single-sample numbers in `probe-results.md`.

## Out of scope

Improving the reviewer. This track measures; changes are made against it afterwards, which is the whole point of building it first. Also out: the composite Action (M6), and cost-per-acted-on-finding, which needs resolved-comment tracking.

## Risks

**Fixture curation is the expensive part.** Real PRs with known findings mostly come from a reviewer having already run. Mitigated by starting from PRs `claude[bot]` reviewed, where findings are recorded and independently produced.

**Three fixtures is still small.** It is enough to detect a ±1 swing and not enough to claim a percentage. The harness should report intervals rather than points, and the spec says so rather than letting a single number acquire authority it has not earned.

**Cost.** ~$0.30 per run × 3 runs × 3 fixtures × each configuration ≈ $3 per configuration. Cheap against the cost of tuning on noise, which is what this replaces.
