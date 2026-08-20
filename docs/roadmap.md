# Roadmap

Milestones are ordered so that the riskiest unknowns are settled first and each stage produces something measurable. Nothing here is dated; sequence matters more than calendar.

## M0 — Prove the foundation

**The one question that can sink the project: does the SDK authenticate headlessly in CI?**

Everything else assumes Workload Identity Federation → Application Default Credentials → Vertex, inside a GitHub Actions runner with no interactive step. That path is documented, but until it runs green in a workflow it is an assumption.

Both published implementations authenticate with an API key secret, so **nobody has demonstrated the WIF path in CI**. The SDK side is supported (`vertex=True` with ADC, and the codelab's agent falls back to it), so this is wiring rather than research — but it is unproven, and everything else depends on it.

- [x] A workflow that authenticates via WIF and completes one trivial agent call on Vertex — **green, run 32270032966**
- [x] Configure with explicit `vertex=True, project=, location=`. **`location` must be `global`** — `us-central1` returns a 404 for `gemini-3.7-flash`
- [x] `Conversation.total_usage` is populated on Vertex, and reports `service_tier=STANDARD`
- [x] Tool names verified against `0.1.12`. **The model's report of `manage_task` and `schedule` was wrong** — neither is registered; the model read the names out of IDE system-prompt templates carried in the shared harness binary
- [x] Registered tool list taken from the harness contract: **14 `HarnessSideTools` slots, 13 `BuiltinTools`, and no tool catalogue returned by the harness at all.** Nothing is injected under the allowlist; an unregistered name is answered with `Unknown tool`
- [x] `budget_limits.py` and `observability.py` run green on Vertex from tag `v0.1.12`. **All five budget dials fire with their documented `StopReason`**; only `max_input_tokens` halts *before* spending
- [x] `BudgetConfig` dial scopes — all five are cumulative, but across the **root trajectory**, not the session. Q4 and Q5 show two of the five are evaded: `max_total_tokens` by subagent spend, `max_model_calls` by model-output retries
- [x] `enabled_tools` is an exclusive allowlist. **Measured: it cuts the per-turn prompt floor from 10,889 to 4,470 tokens**
- [x] **Subagent tokens roll into `total_usage` but do *not* count against `BudgetConfig`** — the dial binds on the root trajectory, so the ceiling leaks. Separately, **subagents fail outright on Vertex** (`PlatformClient is nil`), and the failed spawn still bills ~10x a direct answer
- [x] **Retries are billed and visible in usage (7.4x a clean turn), but do *not* consume `max_model_calls`.** `ModelOutputRetryConfig(max_retries=...)` is the only control over retry spend
- [x] `view_file` takes `AbsolutePath`, `StartLine`, `EndLine`; ranged reads supported
- [x] A hard failure raises `AntigravityConnectionError` rather than reporting zero
- [x] No billing-label surface exists. Source 2 is struck; see [`probe-results.md`](probe-results.md)
- [x] Wheel platform requirements — `0.1.12` publishes `manylinux_2_17_x86_64`, so `ubuntu-latest` is fine; `macosx_11_0_arm64` means the probe runs locally; Python ≥3.10. At 32–38 MB per wheel, the compiled-runtime supply-chain note is confirmed rather than suspected

If ADC does not work headlessly, the documented fallback is Vertex Express Mode (`vertex=True, api_key=...`) — spend stays attributable to a project, at the cost of a key.

**Exit:** a green workflow printing a token count. If ADC does not work headlessly, stop and reconsider before building anything on top.

## M1 — A reviewer that posts

Most of this exists in the prior art and should be adopted rather than rewritten.

- [ ] Collector: PR metadata and changed-file list, **no file bodies, no diff hunks**
- [ ] Tool surface, layer 1: `CapabilitiesConfig(enabled_tools=[...], enable_subagents=False)` so unused tools are never advertised — cheaper on every turn, and nothing to deny. **`enable_subagents=False` is now a hard requirement**, not a preference: it is the only thing making the M3 ceiling truthful, and delegation is broken on Vertex regardless
- [ ] Tool surface, layer 2: `policy.deny_all()` then the named allows. **Verify `create_file` / `edit_file` are actually refused at runtime** rather than assumed — the SDK default allows them, and the vendor's own reference calls that default "conservative"
- [ ] **Keep `agent_behavior` at `AUTONOMOUS` and leave `ASK_QUESTION` out of `enabled_tools`.** It is on in the default surface, and the SDK documents interactive tools as needing `AgentBehavior.INTERACTIVE` to work — a reviewer running unattended in CI can otherwise stall waiting for a human who is not there
- [ ] Set `workspaces` so `policy.workspace_only()` is auto-applied; set `app_data_dir` to an absolute runner temp path so agent scratch stays out of the checkout; set `env` to a minimal dict so the MCP container does not inherit every workflow secret
- [ ] `view_file` byte cap with a loud truncation marker (the one thing the prior art does not do) — implemented as a same-name custom tool overriding the built-in, since the built-in has no configurable limit
- [ ] GitHub MCP server — hosted (`api.githubcopilot.com/mcp/`, 44 tools) or pinned container — with an `enabled_tools` allowlist **and** the matching list in `policy.allow(server, [...])`. Real tool names: `pull_request_read`, `pull_request_review_write`, `add_comment_to_pending_review`, `get_file_contents`
- [x] Reporting decided: incremental MCP posting, runner-owned submit — see [`probe-results.md`](probe-results.md)
- [ ] **The runner submits, not the agent.** On any non-`UNSPECIFIED` stop, find the `PENDING` review and `POST /pulls/{n}/reviews/{id}/events` with the stop reason as the body — verified working
- [x] **MCP allowlist validated against the server's `tools/list` before the first model call.** The SDK exposes no way to ask, so the preflight speaks MCP to the container directly. It caught real drift on its first run
- [x] ~~Allow `list_resources` explicitly~~ — **the server does not offer it.** It is an MCP protocol method, not a GitHub tool; the advice was reasoned from a tool that does not exist
- [ ] Put exact MCP parameter names and casing in `system_instructions` (`pullNumber`, `subjectType: LINE`) — worth three to four turns per review
- [ ] Triggers: `pull_request`, plus a comment command to re-run
- [ ] Job-level concurrency keyed by PR and event, so pushes supersede

**Exit:** a real review posted on a real PR. ✅ **Met** — run [32350817311](https://github.com/SaschaHeyer/agy-review-fixture/actions/runs/32350817311), ~117k tokens per review.

## M2 — Cost tracking

- [x] Rate table with promotional end dates, cited to the Vertex page with a verification date; unknown model **or tier** reports tokens and no cost
- [x] Cached input priced at its multiplier (0.1x), never as free
- [x] Reasoning tokens at the output rate — confirmed by primary source, which prices "response and reasoning" as one line
- [x] Usage accumulated per turn from cumulative snapshots. **Note: an SDK turn is one `chat()`, not one model call**, and `PostTurnArgs` carries no usage — it must be read from the conversation
- [x] Each turn priced at the tier it reports. **The SDK's tier values are lowercase**; an uppercase table made every review report `cost unknown`
- [x] `@hooks.on_compaction` registered and counted
- [ ] Tighten `ModelOutputRetryConfig(max_retries=...)` and record retry counts — the default is 4 re-prompts at full context
- [x] Cost line in the review body — inside it, not as a separate comment, so the figure travels with what it priced
- [x] `review-cost.json` uploaded on every run, `if: always()` so a stopped run still reports what it spent
- [ ] Vertex billing labels, sanitised, failing open — **contingent on Q11**; if the SDK exposes no label surface, drop Source 2 to project-level attribution and say so plainly rather than shipping a breakdown that is always empty

**Exit:** every review reports its cost ✅ **met** (~$0.0447 measured), and the same figure can be found in the billing export 🔴 **not met — no billing export exists on this project**.

## M2.5 — Read diffs, not files ✅

`doitbse/draft#538` — 30 files, the pull request the previous reviewer failed on
with `400: input token count exceeds 1048576`. Ours did not hit that wall; it hit
a different one, at $1.46 a run with zero findings. See
[`probe-results.md`](probe-results.md).

- [x] **`view_diff(path)` tool** returning the changed hunks for one file, byte-capped. For that PR: 2,799 bytes against a *wrong* 131,072 — the cap reads to line 3,113 and the change is at line 13,329
- [x] **Diff size in the prompt seed**, so a generated artefact is recognisable without opening it. "Do not review generated files" is unactionable when reading the file is the only way to tell
- [x] **`compaction_threshold` set**, which M1 left unset. With diff-first reading, a run that died at $1.46 now completes at ~$0.30. The value is a first guess; M5 measures it
- [x] **`SearchPath` documented.** `search_directory` requires it, it appears nowhere in the SDK surface, and omitting it *terminates the session* rather than returning a correctable error. Hit 4 of 7 runs before the fix
- [x] **Named contract passes — the finding of this milestone.** Asked to "review this pull request" the reviewer surfaced **0 of 4** known defects, under a strict precision bar, under a loose one, and at four times the reasoning budget. Asked three named structural questions it surfaced **3–4 of 4**
- [x] **A judging step.** The passes describe rather than decide, and annotate real defects "by design" when left to rule on their own
- [x] **The runner posts, the agent does not.** Reverses M1's incremental MCP posting: the agent invented a `create_pending` method, tripped "only one pending review per pull request" on partial failures, and duplicated comments. One API call from structured findings cannot do any of those — and gives M5 records matched on location rather than wording
- [x] **Gate on triviality.** A single file with ≤3 changed lines, or a PR with no reviewable diffs, is skipped with a stated reason before any model call
- [x] **Incomplete passes excluded, never counted as clean** — Q8: a budget stop returns empty text that reads exactly like "no findings"
- [x] **Precision instructions from Anthropic's `code-review` plugin** ([`prior-art.md`](prior-art.md)). Measured to have **no effect on recall by themselves**; what mattered was naming the contract question
- [x] ~~**Batch the review by file group.**~~ **Measured and rejected:** 0/4 at $0.70 against 0/4 at $0.39. The batch holding both relevant files returned `NO FINDINGS`, refuting the scope hypothesis that motivated it

**Exit:** a real 30-file pull request reviewed to completion, with findings, inside a sane budget. ✅ **Met** — completes at ~$0.30, surfaces 3–4 of 4 known defects, reports one plus a defect the reference reviewer missed.

⚠️ **Quality beyond that is unmeasurable until M5.** Run-to-run variance now exceeds the interventions being tested: identical prompts produced 20,012 then 9,912 characters, and 4/4 then 3/4 surfaced, with no code change. Every number here is a single sample on one pull request.

## M3 — A dollar ceiling

Enforcement is the SDK's job. This milestone is the unit conversion and the reporting around it.

- [ ] `max_cost_usd` input, translated into `BudgetConfig` token limits via the rate table
- [ ] Bind the ceiling on `max_input_tokens` + `max_output_tokens` — the two dials nothing has been observed to evade. **`max_total_tokens` is not a usable backstop:** it binds on the root trajectory and subagent spend escapes it
- [ ] **Note there is no per-request guard in the SDK.** The `view_file` byte cap is the only thing stopping one oversized prompt
- [ ] `max_tool_calls` as a further guard, since a stuck loop is cheap per turn and still unbounded. **`max_model_calls` does not cover model-output retries** — tighten `ModelOutputRetryConfig(max_retries=...)` instead, the default of 4 re-prompts at full context is wrong for a cost-bounded reviewer
- [ ] Surface `StopReason` in the PR comment, in plain words, and verbatim in the artifact
- [ ] A budget stop is **not** a workflow failure
- [ ] Document that the ceiling is a near-bound: cached reads still cost a little while consuming no `max_input_tokens`
- [ ] Budget stops preserve usage but return **empty text** — the cost line survives, the review body does not

**Exit:** a deliberately pathological PR stops at its ceiling, says why, and still posts what it found.

## M4 — Repository rules

- [ ] Supply rules as an Agent Skill via `skills_paths`, the SDK's own mechanism
- [x] `skills_paths` applies a skill's body unprompted — verified with a sentinel rule
- [ ] Re-test at scale: one small skill injected; ten skills or a large body may not
- [ ] Fail loudly if a configured rules path is missing, rather than reviewing generically while appearing repo-aware
- [ ] Document the size limit for rules

**Exit:** a rule stated in the skill changes the review on a PR that violates it, **and** a run log showing the rule was actually in context rather than assumed to be.

## M5 — Evaluation

Deliberately not last. Without it, every quality claim is an anecdote, and there is no way to tell whether a change helped.

- [x] Fixture PRs with defects of known kinds, including many requiring files **outside** the diff — 4 fixtures, 2 repositories, 20 defects, all four classes. Three are real pull requests with independently-produced findings; 9 of 20 defects are cross-file
- [x] Score: defects found, spurious findings, cost — per defect, per class, as ranges across repeated runs. Spurious findings are kept as `novel` rather than discarded, which is what caught the harness's own false 0/4
- [x] A large-generated-file fixture, the case that breaks push-based reviewers — the 21-file fixture changes a **2,947,014-byte** `openapi.json`, the exact file that broke the previous reviewer. Every run completed
- [x] ~30 minute wall-clock per full sweep of 12 runs (**~6.6 min per run**), measured across two sweeps
- [ ] **A baseline against a single-shot reviewer on the same fixtures** — not done. Q12 called this "a decision, not a discovery"; it needs a second reviewer stood up, not more harness
- [ ] **A prompt-injection fixture** — not done. It measures a different property (safety, not recall) and needs a fixture authored for it

**Exit — met, with two items above left open and named.** The table exists: [`probe-results.md`](probe-results.md) reports what is found per defect and per class, what it costs per run, and how long a sweep takes, over **24 runs across two configurations** costing **$5.85**.

**What it established:** security 4–6/6 and local 2–5/11 against **cross-file 0–2/25** and **convention 0/11** — the reviewer's blindness to cross-file and convention defects is stable across two repositories and two configurations, not a bad draw. **What it refuted:** that the judge was discarding those findings. Removing it made cross-file recall worse, not better.

**What it corrected in its own instrument, twice:** a defect recorded as a point where the reference reviewer had named a span, which produced a false 0/4; and one fixture flagged `SOFT` because 71% of its lines sit within a defect's tolerance window, so its numbers cannot be read beside the others'.

## M6 — Release

- [ ] Composite action with pinned dependencies
- [ ] Documented inputs and required IAM
- [ ] Worked WIF setup example
- [ ] Versioned tags and a changelog

## Open questions register

Every unresolved question in this plan, in one place, because a question buried in a paragraph is a question nobody closes. **A milestone is not startable while a question marked as blocking it is open.**

Status as of the `0.1.12` introspection pass on 2026-08-19. **Closed** means answered from the installed package or published source, not inferred.

Evidence for every closed row is in [`probe-results.md`](probe-results.md), reproducible from [`probe/`](../probe).

| # | Question | Blocks | Status |
|---|---|---|---|
| Q1 | Does WIF → ADC → Vertex work headlessly in a GitHub Actions runner? | M0 exit | ✅ **Closed — yes.** Green run 32270032966: keyless, `external_account` credential, 3,797 tokens billed on Vertex |
| Q2 | Are the `BudgetConfig` dials per-dispatch or cumulative? | M3 | ✅ **Closed — cumulative, but across the *root trajectory*.** Quoted from the source docstring in [`cost-tracking.md`](cost-tracking.md). A draft claimed per-dispatch and was wrong; Q4 later narrowed "session" to "root trajectory" |
| Q3 | Is `CapabilitiesConfig(enabled_tools=...)` exclusive or additive? | M1 | ✅ **Closed — explicit allowlist, mutually exclusive with `disabled_tools`.** The SDK's own docstring also endorses preferring it over `policy.deny()` |
| Q4 | Do subagent tokens reach `total_usage` and `BudgetConfig`? | M2 accuracy | ✅ **Closed — `total_usage` yes, `BudgetConfig` no.** `trajectory_usages` shows the subagent's own trajectory summing into the root total, but a ceiling above the root trajectory and below root+subagent did not stop the session. **The ceiling leaks.** Also: subagents fail outright on Vertex (`PlatformClient is nil`), billing ~10x for nothing |
| Q5 | Do retries count against `max_model_calls` and appear in usage? | M3 accuracy | ✅ **Closed — usage yes, `max_model_calls` no.** Forced with an unsatisfiable schema: 4 retries ran inside a 3-call budget without stopping, at 7.4x the tokens of a clean turn |
| Q6 | What is the built-in `view_file` parameter contract? | M1 | ✅ **Closed.** `AbsolutePath`, `StartLine`, `EndLine` — captured from a real call. Ranged reads supported |
| Q7 | Does a failed run really report zero tokens? | M2 | ✅ **Closed.** A hard failure raises `AntigravityConnectionError`; it does not silently report 0. Catch it and record `null` |
| Q8 | Does a budget-stopped session leave a *submittable* pending review? | M1, M3 | ✅ **Closed — yes to both.** A stop leaves a `PENDING` review with 0 visible comments; the runner submits it with one `POST /reviews/{id}/events`. Runner-owned publication is proven necessary and cheap |
| Q9 | Does `skills_paths` inject frontmatter unconditionally? | M4 | ✅ **Closed.** A skill's *body* rule was applied to an unrelated prompt with no discovery step. Untested at scale |
| Q10 | Do Vertex rates match the AI Studio rates the table cites? Priority and flex tiers? | ~~M2 exit~~ | ✅ **Closed 2026-08-20 from the primary source.** The Agent Platform page finally resolved: rates match ($0.75/$3.75 intro to 2026-12-31, $1.50/$7.50 after, cached at 0.1x). **Priority and flex ARE published**, correcting the note below. Non-global endpoints cost ~10% more. Superseded detail: Headline rates corroborate across sources ($0.75/$3.75 promo, $1.50/$7.50 standard); the Vertex page itself resisted three fetch attempts. Every probe call reported `STANDARD`, and `PRIORITY`/`FLEX` are opt-in, so the existing *unknown → tokens, no cost* rule covers them. Verify the Vertex SKU list before quoting a figure externally |
| Q11 | **Any SDK surface for per-request billing labels?** | M2 Source 2 | ✅ **Closed — no.** No `labels` field on `LocalAgentConfig` (25 fields), none on `GeminiModelOptions` (`thinking_level`, `service_tier` only), and no label/tag field anywhere in `types`. **Source 2 is not implementable as designed** |
| Q12 | Which single-shot reviewer is the baseline, on which fixtures? | M5 | A decision, not a discovery. Make it when M5 starts |
| Q13 | Incremental MCP posting, `response_schema`, or `finish_tool_schema_json`? | M1 exit | ✅ **Decided — incremental MCP + runner-owned submit.** Q8 shows the partial work survives and is recoverable; a budget stop returns empty text, so no single-response path can match that |

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
