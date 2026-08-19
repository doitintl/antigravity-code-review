# Product Definition — antigravity-code-review

## Summary

A GitHub Action that reviews pull requests with a pull-context agent built on the Google Antigravity SDK, reporting what each review costs in dollars and refusing to exceed a per-PR ceiling. Instead of packing the diff and file contents into one prompt, it seeds the agent with PR metadata and a changed-file list and lets it read, grep and list its way to what it needs — reaching defects that live outside the diff, and degrading gracefully where a single-shot reviewer exhausts the context window and posts nothing.

Two published Antigravity SDK reviewers already exist. This project's contribution is deliberately narrow: pricing, a dollar-denominated ceiling, and Workload Identity Federation so spend attributes to a project by construction. See [`../docs/prior-art.md`](../docs/prior-art.md).

## Problem

Push-context reviewers fail in two ways that matter.

**They cannot follow a thread.** A defect whose evidence sits in a file outside the diff is only reachable if the up-front file selection happened to include it.

**They have a cliff, not a slope.** One oversized generated file exhausts the input window and the review fails outright — observed as a 2.9 MB OpenAPI specification whose diff was about 4 KB, producing `400 INVALID_ARGUMENT` and no review at all.

Pull-context fixes both, at a real cost: many model calls instead of one. That trade-off is why cost is a first-class feature here rather than a footnote.

## Users

**DoiT engineering teams** — adding it to their own repositories. Cares about per-repository cost attribution, IAM that fits DoiT's GCP setup, and a review that lands before a human merges.

**Public open-source users** — anyone with a GCP project and a GitHub repository. Cares about a worked WIF setup example, defaults that are safe for strangers, and honest documentation of what it costs.

Where the two conflict, internal needs win — but nothing ships that a stranger could not stand up.

## Success criteria

All four matter. They are proven at different stages rather than simultaneously.

1. **Finds defects a single-shot reviewer cannot.** At least one fixture defect reachable only via a file outside the diff. *Proven at M5.*
2. **Anyone can answer "what did that review cost".** A per-PR figure that reconciles, and a dollar ceiling that holds. *Proven at M2–M3.*
3. **Teams keep it switched on.** Reviews land before merge, cost stays defensible, nobody disables it. Makes latency a first-class metric beside cost.
4. **A clear verdict on the SDK for agentic CI.** The reviewer is partly a vehicle for testing whether Google Antigravity is viable in this role. A well-evidenced "no" is a real result.

## v1 scope

**One repository, proven end to end**: a real review posted, its cost reported, its ceiling enforced. Multi-repository roll-up and a published reusable Action follow once that holds.

## Distribution

Public repository under `doitintl`, Apache 2.0, consumed as `doitintl/antigravity-code-review@v1`.

## Out of scope for v1

- Writing code or suggesting committed patches. Read-only is a security property worth keeping.
- Auto-approving or blocking merges. The reviewer comments; merge permission is a branch-protection decision owned by the repository.
- Non-GitHub forges.
- Non-Gemini models. Not a principled limit, just focus.
- Cost per acted-on finding — the metric that actually justifies a reviewer. Named here so it is not forgotten, and so a cheap cost-per-review figure is not mistaken for value.

## Constraints established by measurement

Verified against `google-antigravity==0.1.12` on 2026-08-19. Evidence and reproduction in [`../docs/probe-results.md`](../docs/probe-results.md).

- **`location` must be `global`.** `us-central1` returns a 404 for `gemini-3.7-flash`.
- **Per-PR billing reconciliation is not buildable.** The SDK exposes no surface for labelling a generation request, so per-PR figures are self-reported and reconciliation is project-level only. One of four original contributions, struck on evidence.
- **Read-only is narrower than it looks.** `manage_task` and `schedule` reach the model regardless of `enabled_tools`; only `policy.deny_all()` covers them.
- **The runner must own publication.** A budget stop leaves an invisible `PENDING` review with no visible comments; one API call recovers it.
- **Tool surface is the largest measured cost lever.** Trimming to the tools actually needed cut the per-turn prompt floor from 10,889 to 4,470 tokens — a 59% reduction applied to every turn of every review.

## Open questions

- WIF token exchange inside a GitHub Actions runner is unproven. The SDK half of the path is proven: ADC authenticated headlessly on the first attempt.
- Vertex-side rates unconfirmed against the primary source; the published Gemini API rates corroborate across secondary sources.
- What `manage_task` and `schedule` can actually do.
