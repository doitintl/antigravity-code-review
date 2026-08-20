# The evaluation set

The harness code lives in `src/antigravity_code_review/evalharness/`. **The
fixtures do not live here.** This repository is public and the pull requests
worth measuring are not, so `evals/fixtures/*.json` and `evals/reference/` are
gitignored: what is committed is the code that builds a fixture and the code
that consumes one, never the code under measurement.

That is a real limitation and it is stated rather than worked around. Anyone
outside can read the format and the scorer; nobody outside can reproduce the
numbers without access to the same pull requests.

## What a fixture is

A repository, a **base SHA**, a **head SHA**, and the defects known to be present
in the change between them.

Never a pull request number alone. The first comparison this project ran against
a real pull request used the PR *head*, which by then was two fix commits later
than the code the reference reviewer had seen. "We found nothing they found" was
measuring different source, and it read as a recall failure. A PR number is a
moving target; a pair of SHAs is the review.

Each defect carries:

| field | why |
|---|---|
| `file`, `line` | scoring matches on **location first**, text only to disambiguate. Keyword matching over free text has already produced one false zero here |
| `class` | `local`, `cross-file`, `convention`, `security`. Recall is not uniform across these, and one aggregate number would average a 100% band and a 0% band into a figure that moves for unattributable reasons |
| `description` | one sentence, for the report |
| `reachable` | evidence the defect can actually manifest |

## Reachability is the rule that costs something

`load_fixture` rejects a defect with no `reachable` evidence, and the evidence is
prose rather than a boolean on purpose: a boolean records that somebody was
asked, a sentence records what they found.

The rule exists because M1's fixture planted an unconditional `return True` that
was shadowed by an earlier `TypeError` on every call. The reviewer declined to
report unreachable dead code — correctly — and the harness scored it 0/8 and it
looked like a blind spot.

What counts as evidence depends on the class:

- **`local`, `security`, `cross-file`** — a trigger path. Best case, a recorded
  execution: *"transfer of 500 from a balance of 100 returned True and left the
  account at −407.50, while the guarded API raises `insufficient funds` on the
  same move."*
- **`convention`** — the convention exists, and the change departs from it. The
  manifestation is on the reader, not at runtime, and recording it in its own
  class is what stops it being averaged into a runtime-defect number.

Evidence conditional on another defect in the same change being fixed is
acceptable **and must say so**. A reviewer reads the code as written and reports
the shadowing defect too. Evidence that no input can produce is not acceptable,
and such a defect does not belong in a fixture.

## Building one

```bash
# 1. Skeleton, from a pull request another reviewer has already reviewed.
#    Resolves the commit that reviewer actually saw, and the merge base at it.
uv run python evals/curate_fixture.py <owner>/<repo> <pr> <name> > evals/fixtures/<name>.json

# 2. The reference review, verbatim, for validating the scorer against.
uv run python evals/fetch_reference_reviews.py <owner>/<repo> <pr> <sha> <name>

# 3. Fill in `class` and `reachable` by hand. The curation script leaves both
#    blank deliberately — they are judgements, and load_fixture refuses the
#    fixture until a human has made them.
```

Starting from pull requests another reviewer has reviewed is the mitigation for
the expensive part: findings that are already recorded, and were produced
independently of anything here.

## What the set should contain

- **At least three pull requests, from at least two repositories.**
- **All four defect classes**, because a set drawn from one repository tends to
  be drawn from one class. Tuning against a set that was entirely cross-file
  already regressed local recall — a SQL injection and a type mismatch were lost
  to a configuration that scored better on the cross-file fixture.
- **A cheap one.** A harness that is expensive to run will not be run.

Three fixtures is enough to detect a ±1 finding swing and not enough to claim a
percentage. The report says intervals, not points.

## Running it

```bash
uv run python evals/run_eval.py --config contract-passes+judge --runs 3
uv run python evals/run_eval.py --config contract-passes-only --fixture <name> --out results.json
```

Three gates run **before any model call**, because each has already been the
reason a published number here was wrong:

1. **Reachability** — every defect carries evidence it can manifest. A defect
   that cannot fire scores a correct triage decision as a miss.
2. **The scorer, validated against a reference review**, including the control
   where every claim is replaced by unrelated words. An unvalidated scorer
   reports a false zero that looks exactly like a real one.
3. **Run count** — below three, the report says in its own output that every
   figure in it is an anecdote.

Failing either of the first two stops the run. Spending money to produce a
number the harness already knows it cannot trust is worse than spending nothing.

Checkouts are blobless and cached by `(repo, sha)` under `.eval-cache/`: about
five seconds cold for a 2,400-file tree, free afterwards. A pinned commit does
not change, so fetching it three times is three waits for the same bytes.

## The runner drives the reviewer, not a copy of it

`run_once` calls `review.run_passes`. A harness that reimplements the pipeline
measures the reimplementation — which is the failure mode the whole milestone
exists to end.

It also reviews **the pinned commit**: the changed-file list comes from
`compare(base…head)`, never from the pull request's current files.

## Configurations

`Configuration` names a comparable arm (FR8): the passes, the pass instructions,
and whether there is a judge.

| name | passes | judge |
|---|---|---|
| `contract-passes+judge` | four, prose output | yes |
| `contract-passes-only` | four, **structured output** | no |

**These two differ in two things, not one, and that is stated rather than
hidden.** The shipped passes deliberately emit prose; only the judge emits JSON.
A no-judge arm built on the prose instructions parses zero findings from every
run and reports a clean-looking `0/N` — which reads as strong evidence that the
judge is essential and is really an artefact of the parser. So the no-judge arm
asks its passes for structured output, and any conclusion drawn from the
comparison has to carry that caveat.

## What the report will not do

`render()` contains no percent sign, and a test enforces it. A percentage over
three fixtures and three runs invites a comparison the sample cannot support,
and a single number has acquired that kind of authority here three times
already. What it prints instead:

- **per-defect hit rate** — `2/3` and `3/3` are different facts;
- **recall as a range** across runs, per fixture;
- **recall by defect class**, because the bands are not uniform;
- **cost beside recall**, with unknown cost reported as unknown and the total
  labelled a floor;
- **incomplete runs listed separately** — excluded from recall, still charged for.
