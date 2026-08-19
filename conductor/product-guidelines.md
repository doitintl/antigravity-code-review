# Product Guidelines

## Voice

The house style is **evidence before assertion**. It is already demonstrated across [`../docs/`](../docs/); this document codifies it so it survives contact with new contributors.

**Every claim carries its evidence or its uncertainty.** "Verified against `0.1.12`" and "unproven, and everything else depends on it" are both acceptable. A confident sentence carrying neither is not.

**Numbers carry a source and a date.** A rate without a citation is a defect however right it happens to be — an uncited figure is indistinguishable from a plausible guess, and a reader has no way to tell the two apart.

**Corrections are stated plainly and kept.** "An earlier draft of this document claimed the SDK is read-only by default and was wrong." No hedging, no quiet edit. The correction is more useful to the next reader than the appearance of having been right the first time.

**The tool argues against itself where honest.** "If per-PR cost visibility does not matter to you, use one of those instead. They work today and are simpler." A README that cannot name its own weaker case will not be trusted on its stronger one.

**Trade-offs are named, not buried.** "The honest cost of pull: several model calls instead of one, so higher cost and higher latency per review."

### Mechanics

- Short declarative lead-ins in **bold** before the paragraph that explains them.
- British spelling: `sanitised`, `behaviour`, `licence`.
- 🔴 for a defect that changes a decision; ⚠️ for a caveat that changes an estimate. Used sparingly enough that they still mean something.
- Code, figures and quoted output inline where the argument is, not collected in an appendix.
- Prefer the specific over the general: "a 2.9 MB generated OpenAPI specification" beats "a large file".

## UX principles

The user-facing surfaces are the PR comment, the truncation marker, the cost line, the stop message, and `review-cost.json`.

**Truncation must be loud.** A silently shortened file is worse than an absent one, because the model reasons confidently about content it cannot see and the reader of the review cannot tell that it did.

**A partial result must never present as complete.** The same failure class as silent truncation. A stopped review says that it stopped, in plain words, and names why.

**Say the reason, not the enum.** `MAX_TOTAL_TOKENS_EXCEEDED` belongs in the artifact; "stopped at the $0.50 ceiling" belongs on the pull request.

**A budget stop is a result, not an error.** It does not fail the workflow.

**The cost line is always present**, including on reviews with no findings. A cost figure that appears only sometimes is a cost figure nobody trusts.

**Machine-readable beside human-readable.** Every figure shown on the PR also lands in `review-cost.json`, so it aggregates without anyone scraping comments.

**Never report $0.00 for a run that spent tokens.** A failed or zero-token run records `null` with a reason. Under-reporting is the failure mode that hurts precisely when someone is investigating a spike.

## Review comment style

Findings are **specific, located and actionable**: the file and line, what breaks, and what to do about it.

Not included: praise padding, a summary of what the PR does (the author knows), or any finding the reviewer cannot evidence from what it actually read. A reviewer that pads is a reviewer people stop reading.
