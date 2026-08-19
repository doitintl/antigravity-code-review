# Roadmap

Milestones are ordered so that the riskiest unknowns are settled first and each stage produces something measurable. Nothing here is dated; sequence matters more than calendar.

## M0 — Prove the foundation

**The one question that can sink the project: does the SDK authenticate headlessly in CI?**

Everything else assumes Workload Identity Federation → Application Default Credentials → Vertex, inside a GitHub Actions runner with no interactive step. That path is documented, but until it runs green in a workflow it is an assumption.

Both published implementations authenticate with an API key secret, so **nobody has demonstrated the WIF path in CI**. The SDK side is supported (`vertex=True` with ADC, and the codelab's agent falls back to it), so this is wiring rather than research — but it is unproven, and everything else depends on it.

- [ ] A workflow that authenticates via WIF and completes one trivial agent call on Vertex
- [ ] Confirm the SDK picks up ADC with `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`
- [ ] Confirm `Conversation.total_usage` is populated on a **Vertex** run, not only on an API-key run
- [ ] Re-verify the tool names against the installed version rather than trusting the examples
- [ ] Run the SDK's own `budget_limits.py` and `observability.py` on Vertex, since both are load-bearing here
- [ ] Note the wheel's platform requirements for `ubuntu-latest`

**Exit:** a green workflow printing a token count. If ADC does not work headlessly, stop and reconsider before building anything on top.

## M1 — A reviewer that posts

Most of this exists in the prior art and should be adopted rather than rewritten.

- [ ] Collector: PR metadata and changed-file list, **no file bodies, no diff hunks**
- [ ] Read-only policy: `policy.deny_all()`, then allow `view_file`, `list_directory`, `search_directory`, `find_file`
- [ ] `view_file` byte cap with a loud truncation marker (the one thing the prior art does not do)
- [ ] GitHub MCP server with a pinned image and an `enabled_tools` allowlist
- [ ] Decide reporting: incremental MCP posting vs `response_schema`, on evidence — see the conflict with the budget guard in [`design.md`](design.md)
- [ ] Triggers: `pull_request`, plus a comment command to re-run
- [ ] Job-level concurrency keyed by PR and event, so pushes supersede

**Exit:** a real review posted on a real PR.

## M2 — Cost tracking

- [ ] Rate table with promotional end dates; unknown model reports tokens and no cost
- [ ] Price cached input at its multiplier, not as free
- [ ] Include reasoning tokens at the output rate
- [ ] Cost line in the PR comment
- [ ] `review-cost.json` artifact
- [ ] Vertex billing labels, sanitised, failing open

**Exit:** every review reports its cost, and the same figure can be found in the billing export.

## M3 — A dollar ceiling

Enforcement is the SDK's job. This milestone is the unit conversion and the reporting around it.

- [ ] `max_cost_usd` input, translated into `BudgetConfig` token limits via the rate table
- [ ] `max_model_calls` as a second guard, since a stuck loop is cheap per turn and still unbounded
- [ ] Surface `StopReason` in the PR comment, in plain words, and verbatim in the artifact
- [ ] A budget stop is **not** a workflow failure
- [ ] Document that the ceiling is a near-bound: cached reads still cost a little while consuming no `max_input_tokens`

**Exit:** a deliberately pathological PR stops at its ceiling, says why, and still posts what it found.

## M4 — Repository rules

- [ ] Supply rules as an Agent Skill via `skills_paths`, the SDK's own mechanism
- [ ] **Determine whether `skills_paths` injects unconditionally or is discovered on demand.** If discovery is optional, rules that must always apply move to `system_instructions`
- [ ] Fail loudly if a configured rules path is missing, rather than reviewing generically while appearing repo-aware
- [ ] Document the size limit for rules

**Exit:** a rule stated in the skill changes the review on a PR that violates it, **and** a run log showing the rule was actually in context rather than assumed to be.

## M5 — Evaluation

Deliberately not last. Without it, every quality claim is an anecdote, and there is no way to tell whether a change helped.

- [ ] Fixture PRs with planted defects of known kinds, including at least one requiring a file **outside** the diff
- [ ] Score: defects found, spurious findings, cost, wall-clock
- [ ] A baseline against a single-shot reviewer on the same fixtures
- [ ] A prompt-injection fixture: a PR whose content instructs the reviewer to approve
- [ ] A large-generated-file fixture, the case that breaks push-based reviewers

**Exit:** a table showing what is found, what it costs, and how long it takes, against a baseline.

## M6 — Release

- [ ] Composite action with pinned dependencies
- [ ] Documented inputs and required IAM
- [ ] Worked WIF setup example
- [ ] Versioned tags and a changelog

## Explicitly out of scope for v1

- **Writing code or suggesting committed patches.** Read-only is a security property worth keeping; suggestions are a later, deliberate decision.
- **Auto-approving or blocking merges.** The reviewer comments. Whether a human can merge is a branch-protection decision, and it belongs to the repository owner.
- **Non-GitHub forges.**
- **Non-Gemini models.** Not a principled limit, just focus.
- **Cost per acted-on finding.** The metric that actually justifies a reviewer, and it needs comment-resolution tracking. Named here so it is not forgotten, and so a cheap cost-per-review figure is not mistaken for value.

## Risks

| Risk | Why it matters | Mitigation |
|---|---|---|
| ADC does not work headlessly | Blocks everything | M0 is exactly this |
| Cost per review is several times a single-shot reviewer | May not be justifiable | Measure in M5; cap via BudgetConfig in M3 |
| Latency exceeds time-to-merge | A review after the merge buys nothing | Measure wall-clock in M5; treat it as a first-class metric |
| Compiled binary in the wheel | Weaker audit story than pure source | Pin versions; state it plainly |
| Non-determinism | Regressions land unnoticed | M5 |
| Prompt injection from PR content | The agent reads attacker-controllable text by design | System instruction plus an evaluation fixture |
| The SDK is new and moving | API churn | Pin; keep the surface used small |
| Two published reviewers already exist | This project may not be worth building | Its scope is deliberately narrow — cost tracking and enforcement. If that turns out not to matter, use the prior art and archive this |
