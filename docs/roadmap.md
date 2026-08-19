# Roadmap

Milestones are ordered so that the riskiest unknowns are settled first and each stage produces something measurable. Nothing here is dated; sequence matters more than calendar.

## M0 — Prove the foundation

**The one question that can sink the project: does the SDK authenticate headlessly in CI?**

Everything else assumes Workload Identity Federation → Application Default Credentials → Vertex, inside a GitHub Actions runner with no interactive step. That path is documented, but until it runs green in a workflow it is an assumption.

Both published implementations authenticate with an API key secret, so **nobody has demonstrated the WIF path in CI**. The SDK side is supported (`vertex=True` with ADC, and the codelab's agent falls back to it), so this is wiring rather than research — but it is unproven, and everything else depends on it.

- [ ] A workflow that authenticates via WIF and completes one trivial agent call on Vertex
- [ ] Configure with explicit `vertex=True, project=, location=` — the documented surface — rather than relying on environment-variable pickup, which is inherited convention
- [ ] Confirm `Conversation.total_usage` is populated on a **Vertex** run, not only on an API-key run
- [ ] Re-verify the tool names against the installed version rather than trusting the examples
- [ ] Run the SDK's own `budget_limits.py` and `observability.py` on Vertex, since both are load-bearing here
- [ ] **Settle the scope of each `BudgetConfig` dial**: is `max_input_tokens` per-dispatch or cumulative? The dollar ceiling in M3 is built on the answer
- [ ] **Settle whether `CapabilitiesConfig(enabled_tools=...)` is exclusive or additive.** The docs say both. The first layer of the tool boundary depends on it
- [ ] **Confirm whether subagent tokens roll into `total_usage` and count against `BudgetConfig`.** Subagents default to on
- [ ] Confirm whether retries — 2 API, 4 model-output by default — count against `max_model_calls` and appear in usage
- [ ] Confirm the built-in `view_file` parameter contract (the override example takes `AbsolutePath`) and whether it supports ranged reads
- [ ] Confirm whether a failed run really reports zero tokens, and how a partial failure presents
- [ ] **Find the SDK surface for attaching billing labels to generation requests** — see Q11, the one open question that can invalidate a design rather than adjust it
- [x] Wheel platform requirements — `0.1.12` publishes `manylinux_2_17_x86_64`, so `ubuntu-latest` is fine; `macosx_11_0_arm64` means the probe runs locally; Python ≥3.10. At 32–38 MB per wheel, the compiled-runtime supply-chain note is confirmed rather than suspected

If ADC does not work headlessly, the documented fallback is Vertex Express Mode (`vertex=True, api_key=...`) — spend stays attributable to a project, at the cost of a key.

**Exit:** a green workflow printing a token count. If ADC does not work headlessly, stop and reconsider before building anything on top.

## M1 — A reviewer that posts

Most of this exists in the prior art and should be adopted rather than rewritten.

- [ ] Collector: PR metadata and changed-file list, **no file bodies, no diff hunks**
- [ ] Tool surface, layer 1: `CapabilitiesConfig(enabled_tools=[...], enable_subagents=False)` so unused tools are never advertised — cheaper on every turn, and nothing to deny
- [ ] Tool surface, layer 2: `policy.deny_all()` then the named allows. **Verify `create_file` / `edit_file` are actually refused at runtime** rather than assumed — the SDK default allows them
- [ ] Set `workspaces` so `policy.workspace_only()` is auto-applied; set `app_data_dir` to an absolute runner temp path so agent scratch stays out of the checkout; set `env` to a minimal dict so the MCP container does not inherit every workflow secret
- [ ] `view_file` byte cap with a loud truncation marker (the one thing the prior art does not do) — implemented as a same-name custom tool overriding the built-in, since the built-in has no configurable limit
- [ ] GitHub MCP server with a pinned image, an `enabled_tools` allowlist, **and** the matching explicit tool list in `policy.allow(server, [...])` — the list form is a specific allow rather than a prefix wildcard
- [ ] Decide reporting: incremental MCP posting vs `response_schema`, on evidence — see the conflict with the budget guard in [`design.md`](design.md)
- [ ] **The runner submits, not the agent.** Establish whether a budget-stopped session leaves a submittable pending review; a pending review nobody submits is invisible, which is the same outcome as no review at all
- [ ] Triggers: `pull_request`, plus a comment command to re-run
- [ ] Job-level concurrency keyed by PR and event, so pushes supersede

**Exit:** a real review posted on a real PR.

## M2 — Cost tracking

- [ ] Rate table with promotional end dates; unknown model reports tokens and no cost
- [ ] Price cached input at its multiplier, not as free
- [ ] Include reasoning tokens at the output rate
- [ ] Accumulate usage **per turn**, not once at the end: it survives a failed run, and `service_tier` is per request
- [ ] Price each turn at the `service_tier` it *reports* — priority traffic downgraded to standard bills at standard
- [ ] Register `@hooks.on_compaction` and count compactions; a compaction rewrites the prefix and is the likeliest explanation for a low cache rate
- [ ] Tighten `ModelOutputRetryConfig(max_retries=...)` and record retry counts — the default is 4 re-prompts at full context
- [ ] Cost line in the PR comment
- [ ] `review-cost.json` artifact
- [ ] Vertex billing labels, sanitised, failing open — **contingent on Q11**; if the SDK exposes no label surface, drop Source 2 to project-level attribution and say so plainly rather than shipping a breakdown that is always empty

**Exit:** every review reports its cost, and the same figure can be found in the billing export.

## M3 — A dollar ceiling

Enforcement is the SDK's job. This milestone is the unit conversion and the reporting around it.

- [ ] `max_cost_usd` input, translated into `BudgetConfig` token limits via the rate table
- [ ] Bind the ceiling on the **cumulative** dials — `max_total_tokens` and `max_output_tokens` — so a wrong output-share assumption wastes headroom rather than breaking the bound
- [ ] Use `max_input_tokens` for its actual job: refusing one oversized prompt before dispatch
- [ ] `max_model_calls` and `max_tool_calls` as further guards, since a stuck loop is cheap per turn and still unbounded
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

## Open questions register

Every unresolved question in this plan, in one place, because a question buried in a paragraph is a question nobody closes. **A milestone is not startable while a question marked as blocking it is open.**

Status as of the `0.1.12` introspection pass on 2026-08-19. **Closed** means answered from the installed package or published source, not inferred.

| # | Question | Blocks | Status |
|---|---|---|---|
| Q1 | Does WIF → ADC → Vertex work headlessly in a GitHub Actions runner? | M0 exit, everything | **Open.** The only question that needs CI rather than a laptop |
| Q2 | Are the `BudgetConfig` dials per-dispatch or cumulative? | M3 | ✅ **Closed — all five are cumulative across the session.** Quoted from the source docstring in [`cost-tracking.md`](cost-tracking.md). A draft claimed otherwise and was wrong |
| Q3 | Is `CapabilitiesConfig(enabled_tools=...)` exclusive or additive? | M1 | ✅ **Closed — explicit allowlist, mutually exclusive with `disabled_tools`.** The SDK's own docstring also endorses preferring it over `policy.deny()` |
| Q4 | Do subagent tokens reach `total_usage` and `BudgetConfig`? | M2 accuracy | **Open.** Needs a live run. Mooted in practice by `enable_subagents=False` |
| Q5 | Do retries count against `max_model_calls` and appear in usage? | M3 accuracy | **Open.** Needs a live run |
| Q6 | What is the built-in `view_file` parameter contract? | M1 | **Open.** Needs a live session to introspect the registered tool schema |
| Q7 | Does a failed run really report zero tokens? | M2 | **Open.** Needs a live run with bad credentials |
| Q8 | Does a budget-stopped session leave a *submittable* pending review? | M1, M3 | **Open.** Needs a live run against a scratch PR |
| Q9 | Does `skills_paths` inject frontmatter unconditionally? | M4 | **Open.** Needs a live run plus a log |
| Q10 | Do Vertex rates match the AI Studio rates the table cites? Priority and flex tiers? | M2 exit | **Open.** Fetch attempted 2026-08-19, page truncated. Note `ServiceTier` has three members — `STANDARD`, `PRIORITY`, `FLEX` — so there are three rate columns to source, not two |
| Q11 | **Any SDK surface for per-request billing labels?** | M2 Source 2 | ✅ **Closed — no.** No `labels` field on `LocalAgentConfig` (25 fields), none on `GeminiModelOptions` (`thinking_level`, `service_tier` only), and no label/tag field anywhere in `types`. **Source 2 is not implementable as designed** |
| Q12 | Which single-shot reviewer is the baseline, on which fixtures? | M5 | A decision, not a discovery. Make it when M5 starts |
| Q13 | Incremental MCP posting, `response_schema`, or `finish_tool_schema_json`? | M1 exit | Downstream of Q8. Note introspection found a **third** option the plan had not considered: `CapabilitiesConfig.finish_tool_schema_json` constrains the `finish` tool's own schema |

**Q11 invalidates a design rather than adjusting one.** Per-PR attribution in Cloud Billing is not reachable, so reconciliation drops to project-level. That removes one of the four contributions [`prior-art.md`](prior-art.md) claims, and the README has been corrected rather than left to imply otherwise. One escape remains worth a probe: `VertexEndpoint` is exported and takes an `options` object, so labels may be reachable a layer below the config.

Q1 needs CI. **Q4–Q9 are one script against the laptop's existing ADC.** Q2, Q3 and Q11 are already answered and needed no billed call at all — which is the argument for introspecting an installed package before designing against its documentation.

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
| A failed run reports 0 tokens | Cost tracking silently under-reports exactly when someone is investigating | Accumulate per turn; record zero-token runs as `null` with a reason; reconcile against billing |
| Write tools are allowed by the SDK default | A reviewer could modify the repository it is reviewing | `enabled_tools` plus `deny_all()` plus `workspaces`; assert it in M1 rather than trusting it |
| `max_input_tokens` may be per-dispatch, not cumulative | The dollar ceiling would not bind at all, on exactly the long sessions it exists for | Settle in M0; bind the ceiling on `max_total_tokens` / `max_output_tokens`, which the SDK documents as cumulative |
| Retries and compaction spend outside the model-call count | Cost and the ceiling both drift, invisibly | Tighten `ModelOutputRetryConfig`; hook compaction; record both in the artifact |
| Subagents are enabled by default and may not be counted | An uncounted spender inside a cost-tracking tool | `enable_subagents=False`; confirm roll-up in M0 before ever enabling |
| A stopped run leaves an unsubmitted pending review | Looks like a clean failure, is actually a hidden draft | The runner owns submission on any non-`UNSPECIFIED` stop reason |
| Two published reviewers already exist | This project may not be worth building | Its scope is deliberately narrow — cost tracking and enforcement. If that turns out not to matter, use the prior art and archive this |
