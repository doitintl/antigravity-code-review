# Probe results

Measured against `google-antigravity==0.1.12`, Vertex, model `gemini-3.7-flash`, on 2026-08-19. Reproduce with [`probe/probe_offline.py`](../probe/probe_offline.py) and [`probe/probe_live.py`](../probe/probe_live.py).

Total cost of establishing everything below: **under 90k tokens**, roughly **$0.08** at the introductory rate. Every question the plan had been hedging for four revisions, for the price of a cup of nothing.

## The headline: `location` must be `global`

```
404: Publisher model `projects/…/locations/us-central1/publishers/google/models/
gemini-3.7-flash` was not found or your project does not have access to it.
```

`us-central1` does not serve this model; `global` does. The plan's config sketches all passed a regional location, and the roadmap's M0 checklist would have chased a credentials bug for an hour before finding it. **ADC itself worked on the first attempt** — that 404 is an availability error from a successfully authenticated call, which is most of Q1 answered: the SDK does acquire ADC headlessly from a non-interactive process. Only the WIF token exchange inside a runner remains unproven.

## The tool surface has a floor, and it is not small

| configuration | prompt tokens, first turn |
|---|---|
| default (all built-in tools) | **10,889** |
| `enabled_tools=[VIEW_FILE, FINISH]` | **4,470** |

The prompt in both cases was three words. **Trimming the tool list removed 6,419 tokens from every single turn — a 59% cut to the per-turn floor.**

Put that against a fourteen-turn review: roughly 90k tokens of pure tool-schema scaffolding, on a review whose own content might be 130k. The capability layer was argued for on principle in [`design.md`](design.md); it is now the largest single cost lever the project has actually measured, ahead of anything in the pricing table.

The corollary is less comfortable: **a bare "Say OK." costs ~11k input tokens.** Any per-review cost model that reasons from content size alone will understate by that floor times the turn count.

## ✅ FR5 — the tools you "cannot see" are not there at all

**This reverses the finding that previously stood here.** With `enabled_tools=[VIEW_FILE, FINISH]`, the model was asked to name every tool it could call and answered `manage_task, schedule, view_file`. That was read as the harness injecting tools underneath the allowlist. It is not what happens.

Taken from the wire contract rather than the model — `probe/probe_tool_inventory.py`, `0.1.12`, no billed call:

| source of truth | count | contains `manage_task` / `schedule`? |
|---|---|---|
| `HarnessSideTools` proto slots | 14 | no |
| `BuiltinTools` enum | 13 | no |
| `InitializeConversationResponse` | 4 fields — `cascade_id`, `history`, `cumulative_usage`, `trajectory_usage` | **no tool catalogue at all** |

The direction of the handshake is the whole answer. `HarnessConfig` is what the SDK **sends**; the harness sends back no tool list. **The registered set is exactly what the client declares, so there is nothing underneath the allowlist to hide.**

### Where the model got the names

`manage_task` is a real tool — in the Antigravity **IDE**, not in this SDK. The 101 MB `bin/localharness` is shared with that product and still carries its system-prompt templates. Recovered verbatim from the binary:

```
/third_party/jetski/prompt/template_provider/templates/system_prompts/plugins.tmpl
"Use the manage_task tool to interact with them (e.g. to kill them or check their status)"
"context canceled by manage_task"
```

So the model did not invent the name: **it read it.** That is prompt contamination from a shared binary — a more tractable problem than an unauditable tool, and a different one. `schedule` appears only as a bare string with no tool context.

### Neither is reachable, and neither writes

An unregistered name is answered by the tool runner with `Unknown tool: '<name>'` (`tools/tool_runner.py:368`). There is no dispatch path to a tool the client never declared. The cost of the model trying is one wasted model call.

`tool_search_config.enabled` is `False` and is never set by `_to_harness_side_tools_proto`, so deferred tool loading — the one route by which an unlisted tool could legitimately appear — is off.

### What this changes

- **The read-only claim is *not* narrower than stated.** The previous entry speculated that `manage_task` "plausibly writes the `task.md` artifact"; it does not write anything here, because it does not exist here.
- **`policy.deny_all()` keeps its place, on a different argument.** It is no longer the only thing covering invisible built-ins — there are none. It still matters for MCP tools, which *are* declared dynamically by the server.
- **The one part of the original finding that survives:** `finish` did not appear in the model's own list despite being enabled. **A model's account of its own tools is evidence, not an inventory.** That is what motivated reading the proto, and it was the right instinct.

### Confirmed in passing: the default really is write-capable

The same probe re-confirms commit `887880e`. `LocalAgentConfig` does not leave `capabilities` unset — it constructs `CapabilitiesConfig()` with `enabled_tools=None`, which `_resolve_active_tools` expands to *every* built-in:

| configuration | write-capable slots enabled |
|---|---|
| `LocalAgentConfig` default | **`file_edit`, `write_to_file`, `run_command`** (12 of 14 slots on, subagents included) |
| `BuiltinTools.read_only()` | none |
| reviewer shape `[VIEW_FILE, FINISH]` | none |

Note the trap: the strategy-level fallback for `cfg=None` *is* read-only, and a first pass at this probe measured that path and concluded the default was safe. `LocalAgentConfig` never reaches it. **Measure the default that ships, not the one the code would use if the caller passed nothing.**

## `view_file` — contract confirmed

Captured from a real call via a `pre_tool_call_decide` hook:

```json
{"AbsolutePath": "/tmp/…/sample.txt", "StartLine": 5, "EndLine": 10}
```

PascalCase, and **ranged reads are supported**. The design's invented `view_file(path, start_line, end_line)` was wrong in all three parameter names; the override that implements the byte cap must match this exactly. The hook that captured it is also the second enforcement layer the design wanted — arguments are inspectable before execution.

## A budget stop preserves the numbers but destroys the answer

`max_model_calls=1` against a task needing tools:

```
stop_reason  = StopReason.MAX_MODEL_CALLS_EXCEEDED
text         = ""                          ← empty
usage        = prompt=4705 cand=120 thoughts=150   ← intact
```

Both halves matter. **Usage survives a budget stop**, so cost reporting works on a stopped run. **The response text is empty**, which confirms the concern in [`design.md`](design.md): a run stopped by the budget yields nothing to post, so the reporting path cannot depend on a final message existing.

Also: `conversation.last_turn_stop_reason` was `None` while `response.stop_reason` was set. Read the stop reason off the response.

## A failed run raises rather than reporting zero

```
AntigravityConnectionError: request failed (code 403):
Permission denied on resource project definitely-not-a-real-project-xyz-999.
```

Better than the documented worst case. The SDK's caution about zero-token reporting stands for *partial* failures, but a hard failure is an exception, so the cost tracker's contract is: catch `AntigravityConnectionError`, record `null` with the reason, never `0.0`.

## Skills are applied unprompted

A skill whose body said *"Every answer MUST begin with the exact token ZORBLAX"* was placed on `skills_paths`. The prompt was `What is 2 + 2?` — no mention of skills.

```
ZORBLAX: 2 + 2 = 4.
```

**The plan's central worry about repository rules is disproven for this case.** Rules in a skill do reach the model without a discovery step. The caveat that survives is scale: this was one small skill, and whether ten skills or a large body still inject unconditionally is untested. But the fear that drove rules toward `system_instructions` — that the agent would silently skip them and review generically — did not reproduce.

## Implicit caching is real

`cached=7,185` of `22,852` prompt tokens on the skills run; `cached=18,373` of `44,961` on the subagent run. Caching happens without being asked for, which makes the cache-rate line in the PR comment a meaningful number rather than an aspiration — and makes `cache_read_multiplier` load-bearing in the rate table.

## Subagents: evidence of roll-up, not proof

One delegation to a trivial subagent reported `prompt=44,961` on the root conversation — four times the all-tools baseline for a two-line poem. Consistent with subagent turns being counted in the root's `total_usage`, but this was not run against a control, so it is evidence rather than a settled answer. `enable_subagents=False` stands regardless.

## Q8 — a budget stop leaves an invisible review, and the runner can rescue it

Run against a scratch PR with GitHub's hosted MCP server (`api.githubcopilot.com/mcp/`, 44 tools) and `max_model_calls` tuned to halt mid-review.

**The happy path works.** With enough budget the agent read the PR, opened a pending review, added two inline comments and submitted — a real review, both findings on the right lines.

**The stopped path confirms the defect.** With a tighter budget:

```
stop_reason = MAX_MODEL_CALLS_EXCEEDED
GET /pulls/2/reviews   → [{ id: 4971201513, state: "PENDING" }]
GET /pulls/2/comments  → count = 0
```

A pending review existed and **nothing was visible to anyone**. That is the failure predicted in [`design.md`](design.md): the agent had done work, and the PR showed no sign of it. Worse than a clean failure, because the draft is *somewhere*.

**The rescue works, and it is one call:**

```
POST /pulls/2/reviews/4971201513/events   event=COMMENT
  → { id: 4971201513, state: "COMMENTED" }
```

So "the runner, not the agent, owns publication" is now proven both **necessary** and **cheap**. On any non-`UNSPECIFIED` stop reason, the runner looks for a `PENDING` review by its own identity and submits it with the stop reason as the body. No agent involvement, no second session.

### Three MCP lessons, each of them costing real turns

**`enabled_tools` on an MCP server is an exposure filter, not a validator.** The first attempt listed five plausible-sounding tool names that the server does not have. The SDK exposed them to the model anyway; the failure arrived at call time as `unknown tool "create_pending_pull_request_review": Bad Request`, after a model call had already been spent on it. [`design.md`](design.md) calls `enabled_tools` "itself a security boundary" — true for *restricting*, but it does not tell you a name is wrong. **Validate the list against `tools/list` at startup.** The real names are `pull_request_read`, `pull_request_review_write`, `add_comment_to_pending_review`, `get_file_contents` — which is what the plan originally had.

**`policy.allow(github_mcp)` does not cover `list_resources`.** The agent's first move was `list_resources`, an SDK-level MCP tool sitting outside the server's own namespace. `deny_all()` blocked it and a model call was wasted on the refusal — a live demonstration of the cost argued for in "Why capabilities come before policies". Allow it explicitly or budget for the wasted turn.

**Parameter guessing is a measurable line item.** The model burned three model calls discovering that `pull_request_read` wants `pullNumber` and not `pull_number`, then hit `subjectType` expecting `LINE` rather than `line`. GitHub's consolidated multi-method tools (`pull_request_read` with `method="get_files"`) are compact in the schema and expensive at the point of use. **Put the exact parameter names and casing in `system_instructions`** — that is not prompt fussiness, it is three or four turns per review, measured.

## Q1 — WIF works headlessly in CI ✅

Run 32270032966 on `ubuntu-latest`, `google-antigravity==0.1.12`, no API key present:

```
keyless: credential type is 'external_account' (urn:ietf:params:oauth:token-type:jwt)  OK
project: sascha-playground-doit · location: global · model: gemini-3.7-flash
reply: 'OK' · stop: StopReason.UNSPECIFIED
3,768 in (0% cached) · 1 out · 28 thinking · 3,797 total · tier=standard
PASS
```

**The risk the roadmap called "the one question that can sink the project" is retired.** Neither published reviewer had demonstrated this path; both use an API key secret.

### A WIF credential file is not a key

The first attempt failed on this project's own guard, and the reason is worth keeping.

`google-github-actions/auth` sets `GOOGLE_APPLICATION_CREDENTIALS` **under WIF as well**, so a guard that treats the variable's presence as proof of a key rejects the very mechanism it exists to prove. The file is an *external account credential configuration* — instructions for exchanging the runner's OIDC token — and contains no private key.

The test that actually distinguishes them is the `type` field:

| `type` | meaning |
|---|---|
| `external_account` | federation. Keyless. What we want |
| `service_account` | a downloaded key. Fails |

Both the workflow and the probe now inspect the file rather than the variable name, and additionally reject any file containing `private_key`.

### The per-turn floor is smaller than measured locally

3,768 input tokens for `"Say OK."` with `enabled_tools=[FINISH]`, against 4,470 measured locally with `[VIEW_FILE, FINISH]` and 10,889 with the default set. Consistent with the tool surface being the dominant term in the floor.

## ✅ FR6 — the SDK's own examples, run against Vertex

`budget_limits.py` and `observability.py` are load-bearing for M3 and M2, so they were run rather than read. They do not ship in the wheel; both were fetched from tag `v0.1.12` and vendored under `probe/sdk_examples/`, pinned by git blob SHA:

| example | blob SHA at `v0.1.12` |
|---|---|
| `budget_limits.py` | `f1a72f7c7ed01ab19ec8c32e81cd1fa14f292ed0` |
| `observability.py` | `f693785172654a6ff48f47f89f78dc40c8ad2238` |

`probe/probe_example_parity.py` verifies those hashes before running, so a drifted copy fails loudly instead of quietly testing a different SDK.

### Both pass on Vertex — after two divergences are papered over

Every example in the tree constructs a bare `LocalAgentConfig(...)`: **no `vertex`, no `project`, no `location`.** Run verbatim they authenticate against the Gemini API with a key. The runner patches `LocalAgentConfig` to inject the Vertex fields rather than editing the files, so the vendored bytes still hash to upstream.

| example | result on Vertex | divergence from the path it was written for |
|---|---|---|
| `budget_limits.py` | **PASS** | no `vertex=True` |
| `observability.py` | **PASS** | no `vertex=True`; **no `BudgetConfig` — unbounded as written** |

That second one matters: this project requires every probe call to carry a budget, and the SDK's own observability example carries none. Anything adopted from it needs a ceiling added.

### All five budget dials fire correctly on Vertex

This is the result M3 rests on. Each dial produced its documented `StopReason`, and the stop persisted into the following turn:

| dial | setting | `StopReason` observed |
|---|---|---|
| `max_model_calls` | 1 | `MAX_MODEL_CALLS_EXCEEDED` |
| `max_tool_calls` | 1 | halted after the first tool execution |
| `max_input_tokens` | 50 | halted **before inference** |
| `max_output_tokens` | 30 | `MAX_OUTPUT_TOKENS_EXCEEDED` |
| `max_total_tokens` | 100 | `MAX_TOTAL_TOKENS_EXCEEDED` |

**`max_input_tokens` halts proactively, before the call is made.** The other dials stop the session once the budget is already spent. That asymmetry is worth stating plainly in M3's ceiling documentation: only one of the five prevents spend rather than reacting to it.

### A cost datum, incidentally

`observability.py` asks one question — "What is the weather in Seattle?" — with the **default** tool surface and one custom tool. It billed:

```
Prompt tokens: 21,853 · Output: 43 · Thinking: 55 · Total: 21,951
```

A tool-using turn is two model calls, so that is ~10.9k input tokens *per call* — matching the 10,889 default-surface floor measured earlier, and confirming it is charged per model call rather than per turn. The same question with `enabled_tools=[FINISH]` and one custom tool cost 7,918 total across its two calls.

**A single tool call doubles the floor.** Any per-review estimate must multiply the floor by model calls, not by turns.

### One thing that is *not* a divergence

The example's streamed output first appeared empty, because its `@post_tool_call` audit hook prints a leading newline mid-stream and pushes the agent's text below the audit line. Streaming on Vertex is fine — a control run yielded the full text in one chunk, `stop_reason=UNSPECIFIED`. All four of the example's own stated success criteria are met.

## ✅ Q4 / FR7 — subagent tokens roll up, and the budget ceiling leaks

The register recorded "one delegation reported 45k root prompt tokens — evidence of roll-up, no control run". A single large number was never evidence: enabling `START_SUBAGENT` also raises the tool-surface floor, and the floor dominates. `probe/probe_subagent_rollup.py` runs the controlled pair, and uses an instrument the earlier attempt did not: **`Conversation.trajectory_usages`** reports usage per trajectory, and a subagent gets its own. That turns an inference into a reading.

### 🔴 First, the blocker: subagents do not work on Vertex

Every delegation attempt fails:

```
error executing cascade step: CORTEX_STEP_TYPE_INVOKE_SUBAGENT:
failed to fetch tiered models for subagent model resolution: PlatformClient is nil
```

Reproduced four ways on `0.1.12`: with the `model=` shorthand and `[FINISH, START_SUBAGENT]`; with `read_only()` plus `START_SUBAGENT`; with an explicit `models=[ModelTarget(...)]`; and with `models=[ModelTarget(endpoint=VertexEndpoint(project=..., location="global"))]`. It is not a tool-configuration problem — subagent *model resolution* wants a platform client that is nil on the Vertex path.

**A failed delegation is not free.** It costs roughly ten times a direct answer:

| run | delegation | trajectories | total tokens |
|---|---|---|---|
| A — control | off | 1 | **3,881** |
| B — delegation on | attempted, failed | 2 | **36,269** |

### Roll-up: yes, and it can be read directly rather than inferred

In run B the two trajectories were `25,580` (root) and `10,689` (subagent), summing to `36,269` — **exactly `total_usage`**. The subagent's trajectory is present in `trajectory_usages` and is accounted for in the root total.

### 🔴 Budget: no — `BudgetConfig` binds on the root trajectory, not on `total_usage`

This is the finding that changes M3. Run C set `max_total_tokens=27,580`, chosen to sit *above* B's root trajectory and *below* root + subagent, so that only subagent spend could breach it:

| | tokens | vs ceiling 27,580 |
|---|---|---|
| root trajectory | 25,455 | under |
| **session total** | **38,395** | **over by 10,815** |
| `stop_reason` | `UNSPECIFIED` | **did not stop** |

An earlier run with `max_total_tokens=6,000` — below the root trajectory — *did* stop with `MAX_TOTAL_TOKENS_EXCEEDED`. The two runs bracket the behaviour: **the dial works, and it is evaluated against the root trajectory only.** Subagent tokens are billed, are reported in `total_usage`, and are not capped.

**`max_total_tokens` does not bound a session that delegates.** A ceiling expressed in dollars would be understated by the entire subagent workload, silently.

### What this means for M3 and M1

- **`enable_subagents=False` is now a hard requirement, not a preference.** M1 already planned it for prompt-floor reasons. It is now also the only thing making the M3 ceiling truthful, and the only thing preventing a guaranteed-to-fail 36k-token detour on Vertex.
- **M3 must state the bound honestly.** With subagents off, `max_total_tokens` is a real ceiling. With them on, it is not a ceiling at all. That is a stronger caveat than the "near-bound" wording currently planned for cached reads.
- Q2 said the dials are "cumulative across the session". Refine that: **cumulative across the *root trajectory*.**

### The caveat this rests on

The subagent failed during model resolution, so these numbers are the spawn-and-fail path. Whether a *successful* subagent's tokens would also escape the ceiling cannot be determined on Vertex while the defect stands. The safe reading is the conservative one: do not rely on `max_total_tokens` to bound a delegating session.

## Still open

- **Q10.** Vertex-side rates, and the `FLEX` tier the enum revealed.
- **Q4.** Subagent roll-up, properly controlled.
- **Q5.** Whether retries count against `max_model_calls`.

These runs used a private scratch repository with two throwaway pull requests. Recreate one with any repo containing a PR with a couple of obvious defects.
