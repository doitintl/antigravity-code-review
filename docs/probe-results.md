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

## ✅ Q5 / FR8 — retries are billed, and they escape `max_model_calls`

The default is **4 model-output re-prompts**, each at full context. Two things needed measuring: whether they show up in usage, and whether they consume the dial that is supposed to bound them.

Forcing the violation deterministically: a schema no output can satisfy — an integer required to be both `minimum: 10` and `maximum: 5`. Every attempt fails validation, so the retry path is exercised rather than hoped for. `probe/probe_retry_accounting.py`.

| run | `max_retries` | `max_model_calls` | total tokens | `stop_reason` |
|---|---|---|---|---|
| baseline, satisfiable schema | 0 | 6 | **2,371** | `UNSPECIFIED` |
| impossible schema | 4 | 3 | **9,856** | `UNSPECIFIED` |
| impossible schema | 4 | 20 | **17,631** | `UNSPECIFIED` |

### Retries are billed, and they are visible

**Yes to usage.** A retried turn cost 7.4× the clean one. Retries are not free and they are not hidden — `total_usage` accounts for them. Any cost figure derived from `total_usage` is therefore correct on this axis.

**The exposure is per turn, not per session.** One turn that trips the retry path costs up to five prompts at full context instead of one. A cost model reasoning from "turns × floor" understates a retrying turn by up to 4×.

### 🔴 Retries do *not* consume `max_model_calls`

The discriminator was `max_retries=4` against `max_model_calls=3`. If retries consumed model calls, five attempts could not fit in a budget of three, and the session would stop with `MAX_MODEL_CALLS_EXCEEDED`. **It did not** — it stopped `UNSPECIFIED`, having spent 9,856 tokens, roughly four times the single-attempt baseline. At least four attempts ran inside a three-call budget.

This is the same shape of leak Q4 found in `max_total_tokens`: **a dial that looks like a bound and is not one.** Two of the five `BudgetConfig` dials are now known to be evaded by work the SDK performs on the caller's behalf.

| dial | evaded by |
|---|---|
| `max_total_tokens` | subagent trajectories (Q4) |
| `max_model_calls` | model-output retries (Q5) |

### What this means for M3

- **Tighten `ModelOutputRetryConfig(max_retries=...)` deliberately.** It is the only control over retry spend, because the call budget does not cover it. The default of 4 is the wrong default for a cost-bounded reviewer.
- The M3 ceiling should be expressed on `max_input_tokens` and `max_output_tokens` — the dials nothing was observed to evade, and `max_input_tokens` is additionally the only one that halts *before* spending (FR6).

### Two smaller observations

- **The attempt count is not deterministic.** The same impossible schema cost 9,856 tokens under one budget and 17,631 under another. Retry counts vary run to run, so retry cost is a distribution, not a constant. Do not model it as a fixed multiplier.
- **`get_last_structured_output()` returned `None` even on the satisfiable schema.** Not chased further, because Q13 already decided against `response_schema` in favour of incremental MCP posting — but it is one more reason that decision was right.

## Cross-check against the SDK's own documentation

M0's findings were all measured. This section checks them against the published SDK reference (the `google-antigravity-sdk` skill bundle) — because agreement and disagreement are both informative, and this project has already been burned twice by reasoning from documentation.

### Corroborated

- **FR5 — the tool list.** The reference table lists exactly **13 built-in tools**, matching the `BuiltinTools` enum read off the wire. **`manage_task` and `schedule` appear nowhere in it.** An independent source agrees they are not SDK tools.
- **The write-capable default.** *"All built-in tools are **enabled** by default… `run_command` is **denied** by the default `confirm_run_command()` policy — all other tools are allowed."* That is the measurement, in the vendor's words.
- **Usage arithmetic.** `total_token_count` is documented as prompt + candidates + thinking, matching `usage.py`. The reference also warns to *"always monitor `thoughts_token_count`"*, which is why reasoning tokens are priced at the output rate in [`cost-tracking.md`](cost-tracking.md).

### 🔴 Contradicted — the documentation is wrong, or silent, in three places

| claim | documentation says | measurement says |
|---|---|---|
| `max_total_tokens` scope | dials *"govern entire agent sessions"*, counted *"across the session"* | binds on the **root trajectory**; subagent spend escapes (Q4) |
| `max_model_calls` scope | *"caps generator invocations across the session"* | **does not cover model-output retries** (Q5) |
| subagents on Vertex | no compatibility caveat anywhere | **fail outright** in `0.1.12` |

Neither budget page mentions either evasion. A reader configuring a cost ceiling from the documentation alone would build one that leaks, and would have no reason to suspect it.

### The trap in the safety documentation, stated plainly

The safety reference says the default policy means *"new agents are **conservative by default** — they cannot execute shell commands"*. Its own reference entry for the same policy says `confirm_run_command()` *"Denies `run_command`, **allows everything else**"*.

Both sentences are true. The first one is the one people remember, and it is how this project came to claim the SDK was read-only by default — corrected in `887880e`. **"Conservative" is doing a lot of work for a default that permits `create_file` and `edit_file` on input written by untrusted pull-request contributors.** The warning in [`design.md`](design.md) is aimed exactly here.

### A fifth reproduction of the subagent defect — the one that matters most

The agent-configuration reference advises: *"Avoid setting the model explicitly unless requested. It is generally better to leave the model unset to use the default behavior."* Every earlier reproduction set `model="gemini-3.7-flash"` explicitly, and the failure is specifically about *model resolution* — so the obvious question is whether the configuration caused it.

It does not. Run with `model` **unset**, exactly as the documentation recommends:

```
trajectories=2  total=43,446  stop=UNSPECIFIED
error executing cascade step: CORTEX_STEP_TYPE_INVOKE_SUBAGENT:
failed to fetch tiered models for subagent model resolution: PlatformClient is nil
```

Identical failure, identical cost, against the vendor's own recommended configuration. **The defect is in the SDK, not in how this project calls it.**

### One thing the documentation does not mention at all

`Conversation.trajectory_usages` — the per-trajectory usage map that made Q4 answerable by reading rather than by inference — appears nowhere in the observability reference. It is the single most useful instrument found in this milestone, and it is undocumented.

### Carried to M1

`ask_question` is enabled in the default tool surface, and the reference notes that interactive tools need `agent_behavior=AgentBehavior.INTERACTIVE` to work properly. The reviewer runs unattended in CI: it must stay `AUTONOMOUS` (the default) **and** leave `ASK_QUESTION` out of `enabled_tools`, or it can stall waiting for a human who is not there.

## M1 — what was verified before the spend cap

### 🔴 The blocker

Partway through M1, `sascha-playground-doit` stopped accepting Vertex calls:

```
request failed (code 403): Spend cap breached for project:
projects/234439745674 for service: aiplatform.googleapis.com
```

A **project-level spend cap**, not a `BudgetConfig` dial — no configuration in
this repository can spend past it. `m0_probe`, green earlier the same day, now
fails identically, so M1 did not introduce it.

**It re-confirms Q7 in the wild:** the SDK raised `AntigravityConnectionError`
rather than reporting zero tokens. The one failure mode this project most needed
to be loud was loud.

### ✅ Verified without a model

**Runner-owned submit (FR8), end to end on a real pull request.** This is the Q8
mechanism in production form, and it needs no agent at all:

| step | result |
|---|---|
| create a `PENDING` review with one comment | id `4980504813`, state `PENDING` |
| `find_pending_review` locates it | yes |
| `rescue_pending_review` submits it | yes |
| state afterwards | **`COMMENTED`**, no pending review remaining |

The event is `COMMENT`, deliberately — not `REQUEST_CHANGES` or `APPROVE`. An
automated reviewer that can block a merge is a different product with a
different failure mode, and approving on the strength of an agent's read is
worse than either.

**Collection against fixture PR #1.** 2 changed files, seed produced, and the
invariant held: no patch content reached the prompt. Observed file-entry keys
were `additions, blob_url, changes, contents_url, deletions, filename, raw_url,
sha, status` — note that GitHub omits `patch` entirely on large entries, so code
that assumed its presence would have failed on exactly the generated file the
byte cap exists for.

**The parameterisation claim from M0, tested and found wanting.** M0's
acceptance criterion 2 said the WIF module "instantiates for a second repository
by changing variables only". It did not: the environment wrapper never exposed
`sa_name`, so a second repository in the same project collides on the service
account. The *module* parameterised it correctly; the wrapper did not pass it
through. Fixed in both environments. **The claim was true of the module and
false of the thing anyone would actually copy.**

### The fixture

`SaschaHeyer/agy-review-fixture` PR #1 — seven planted defects (hardcoded
credential, SQL injection, float money in a `Decimal` codebase, a missing balance
check bypassing the overdraft guard, private-state access, a swallowed audit
exception, an unconditional `True` return) plus a 582 KB generated JSON file to
exercise the byte cap on a real diff.

The inventory lives in this repository, **not** in the fixture. A first version
committed it to the PR branch, where it appeared in the changed-file list — the
reviewer could have read the answers and parroted them back, and the exit
criterion would have measured nothing.

## ✅ M1 exit criterion met — a real review on a real pull request

Run [32350817311](https://github.com/SaschaHeyer/agy-review-fixture/actions/runs/32350817311), triggered by a `pull_request` event on `SaschaHeyer/agy-review-fixture` PR #1, keyless via WIF:

```
collected 2 changed files, seed is 612 chars
stop: StopReason.UNSPECIFIED
113,116 in (43% cached) · 1,628 out · 2,802 thinking · 117,546 total · tier=standard
pending review published: True (normal stop: True)
```

It named the planted defects — hardcoded live API key, SQL injection via `%`
formatting, `Decimal`/`float` mismatch, and private-state mutation bypassing
`Ledger`'s overdraft guard — and correctly ignored the 582 KB generated file it
was not asked to review.

### Two bugs the exit criterion caught that nothing else would have

**1. The review was invisible.** The first run that reached the MCP server
reported posting its comments, and the pull request showed none. `FR8` says *the
runner submits*; the implementation had quietly narrowed that to *the runner
submits when the agent stopped early*. On a clean finish nobody submitted.

This is **Q8 in production**: a pending review is invisible to every account
except the one that opened it, and in CI that account is `github-actions[bot]`,
not a human. The finding that was a curiosity in M0 was a silent total failure
in M1.

**2. The loud truncation marker was being cut off.** The harness applies its own
`tool_output_truncation` to whatever a tool returns, and `LocalAgentConfig`
exposes no field to configure or disable it. Our marker was appended, so the
model saw only the harness's generic *"the output was truncated because it was
too long"* — never which file, how big, or how much was missing. **The reviewer
would have reasoned about a file it could not see while believing it had read
it**, which is precisely the failure FR5 exists to prevent.

Fixed by leading with the marker. Verified live: asked what it had been told,
the model reported 200,034 bytes total and 68,962 not shown — exactly
`200,034 − 131,072`.

### Three cheaper lessons

- **The agent must be told which repository it is reviewing.** Without `owner`
  and `repo` in the system instructions every GitHub call resolved to `'/'` and
  failed. M0 measured the casing hint as worth three to four turns; naming the
  repository is worth more, because without it nothing works at all.
- **Left to guess a tool name, the agent invents one.** It tried
  `create_pending`, which does not exist. The instructions now spell out the
  sequence and name that invention as a thing not to make.
- **`gh` needs `GH_TOKEN` in Actions**, which is not the same variable the MCP
  container needs. The collector failed before the agent started — the right
  order to fail in, and only legible because the collector raises rather than
  returning an empty file list.

### Cost, as the first real M2 datum

**~117k tokens per review** of a two-file pull request, 43–56% cached across
runs. At standard Vertex rates that is roughly $0.18 per review. The prompt is
dominated by the tool surface and the file the agent chose to read, not by the
seed, which was 612 characters.

### Non-determinism, already visible

Two clean runs of the *same* pull request found overlapping but different
defect sets — one caught the swallowed audit exception, the other did not.
Neither found the unconditional `return True`. **One run is an anecdote**, which
is the argument for M5 stated as a measurement rather than a principle.

## Non-determinism, measured across eight runs of one pull request

"An agentic reviewer will not produce identical output twice" is in
[`design.md`](design.md) as a principle. Eight runs of the *same* pull request
make it a measurement, and the measurement is more useful than the principle —
because the variance turns out not to be spread evenly at all.

| planted defect | found in |
|---|---|
| hardcoded live API key | **8/8** |
| SQL injection via `%` formatting | **8/8** |
| `Decimal`/`float` mismatch | **8/8** |
| no balance check (overdraft) | **8/8** |
| private `_balances` mutation | **8/8** |
| swallowed audit exception | **4/8** |
| unconditional `return True` | **0/8** |

**Five of seven were perfectly stable.** Every security-critical finding was
reported in every run. The variance is confined to one defect, and the apparent
total miss is not a miss at all.

### The 0/8 is a broken fixture, not a broken reviewer

`transfer()` computes `ledger.balance(sender) - total` where the balance is a
`Decimal` and `total` is a `float`. That raises `TypeError` on every call, which
was verified by running it:

```
transfer RAISED TypeError: unsupported operand type(s) for -: 'decimal.Decimal' and 'float'
```

**`return True` is unreachable.** Defect 7 is shadowed by defect 3, and the
reviewer was right not to report dead code. A fixture that scores it down for
this would be measuring the wrong thing and would look like evidence.

This is the trap M5 exists to walk into, arriving early and cheaply: **an eval
fixture can contain a defect that cannot manifest, and the harness will read a
correct triage decision as a failure.** Planted defects need to be checked for
reachability, not just planted.

### The 4/8 is a reporting effect, not a detection failure

The one genuine variance separates perfectly on how many findings the run
reported at all:

| | comment counts |
|---|---|
| runs that reported it | 5, 5, 6, 12 |
| runs that did not | 3, 3, 4, 4 |

Zero overlap. **The swallowed exception is the marginal finding that falls off
the end of a short list**, not something the model sometimes fails to see.

Given the same file with no tool orchestration and no curation instruction, the
same model reported it **6/6 times**, producing 8–16 findings rather than 3–6:

| condition | findings per run | swallowed exception |
|---|---|---|
| reviewer, in CI | 3–6 | 4/8 |
| same model, code inline, "report every defect" | 16, 16, 16 | 3/3 |
| same model, code inline, "be concise" | 8, 9, 10 | 3/3 |

Two plausible causes, and this project owns both of them rather than the model:

1. **The system instruction tells it to curate** — *"report real defects… do not
   report formatting preferences"*. Curation is exactly where a marginal finding
   gets dropped.
2. **Each finding costs an MCP round trip.** Posting inline as it goes makes the
   sixth finding materially more expensive than the first, which is
   back-pressure against reporting it at all.

Distinguishing the two is a one-variable experiment, and it belongs in M5.

### What this changes for M5

**A single "defect recall" number would have been actively misleading here.** It
would average a 100% band, a 50% band, and a 0% band that is really a fixture
bug, into one meaningless figure that moves for reasons nobody can attribute.

M5 should instead measure:

- **recall per defect class**, since stability is not uniform across them;
- **noticed versus reported** as separate quantities, because the only real
  variance found so far lives entirely in the gap between them;
- **findings-per-run as a first-class metric**, since it predicted the miss
  perfectly and is far cheaper to collect than defect recall.

And fixtures need a reachability check before a defect counts as planted.

## ✅ Q10 closed — Vertex rates, from the primary source

The Agent Platform pricing page resisted three fetch attempts during M0, which
is why Q10 stood open with the rates corroborated only from AI Studio. It
resolved on 2026-08-20.

**The figures were right.** $0.75/$3.75 introductory through 2026-12-31,
$1.50/$7.50 from 2027-01-01, cached input at one tenth. The table did not need
correcting; it needed the citation it was missing.

The primary source corrected two things around it:

- **Priority and flex rates *are* published.** M0 recorded that "only standard
  rates are published" and concluded unknown tiers fall under the unknown-rate
  rule. All three tiers are listed, so all three are priced.
- **Region changes the rate.** Non-global endpoints cost ~10% more. This project
  pins `location="global"`, so the assumption is now explicit rather than lucky.

It also confirms from primary source that output covers **"response and
reasoning"** — thinking tokens billing at the output rate is now a citation
rather than an inference from a docstring.

## M2 — what a review actually costs

Measured on the fixture PR, `0.1.12`, `gemini-3.7-flash`, global endpoint:

```
Reviewed in 1 turn · 79,074 in (57% cached) · 4,163 out · 11 tool calls · ~$0.0447
```

**About 4–7 cents per review**, not the ~$0.18 estimated in M1. That earlier
figure was wrong twice over: it priced at the standard rate rather than the
introductory one, and it ignored caching entirely. Both errors pushed the same
way, which is what an uncited estimate tends to do.

### Three bugs the real runs found

**The service-tier values are lowercase.** The SDK emits `ServiceTier.STANDARD`
with value `"standard"`; the rate table used `"STANDARD"`, so the lookup never
matched and **every review reported `cost unknown`**.

That it surfaced at all is the unknown-means-unknown rule earning its place. Had
the table fallen back to a neighbouring rate, every review would have been
silently mispriced and the figure would have looked entirely plausible. The rule
was written as a principle in `cost-tracking.md`; this is it working as an
incident.

**`PostTurnArgs` carries no usage.** It has exactly one field, `response_text`,
verified against the proto descriptor. A hook-based design looking for per-turn
usage in the payload finds nothing and silently records nothing. Usage has to be
read from the conversation, which only exists after the `Agent` is constructed —
after the hooks are registered.

**A "turn" is not a "model call".** The cost line reported *"1 model call"* for a
review that made eleven tool calls. `post_turn` fires once per `chat()`, and a
review spends many model calls inside a single turn working its tool loop. The
token totals are cumulative and were always right; the label was false, and
false in the direction that makes a reviewer look cheaper than it is. **The SDK
exposes no per-model-call count** — `trajectory_usages` is per trajectory.

### 🔴 The exit criterion is half met

*"Every review reports its cost"* — **met**. Cost line on the review, and
`review-cost.json` uploaded on every run including stopped ones.

*"…and the same figure can be found in the billing export"* — **not met**.
`sascha-playground-doit` has **no billing-export dataset**; `bq ls` across 200
datasets finds nothing billing-related. Without an export there is no
independent figure to reconcile against.

This is recorded as unmet rather than waved through, because the whole argument
for two sources is that self-reported cost is unverified cost. `cost-tracking.md`
is blunt about it: reporting your own cost without an independent check is how a
number everyone quotes turns out to have been wrong for a month — and this track
has already produced two wrong numbers that looked fine.

**To close it:** enable a BigQuery billing export on the billing account, wait
for a review to appear in it, and compare. Until then the figure is arithmetic
from a cited rate, which is better than a guess and is not the same as verified.

## 🔴 The reviewer does not survive a real pull request

First test outside the fixture: `doitbse/draft#538`, 30 changed files,
+715/-30, in a 2,446-file Next.js repository. **The same pull request the
previous reviewer failed on**, which makes it a clean comparison.

### What the old reviewer did

```
400 INVALID_ARGUMENT: The input token count exceeds the maximum
number of tokens allowed 1048576
```

It attached codebase context — 2,314 files, 21.7 MB against a 1.5 MB limit —
fell back to "Sparse Context Mode", and still blew the window. This is the
failure quoted in [`design.md`](design.md) as the reason this project exists.

### What ours did

Not that. Something else, twice, at $1.51 and $1.46 a run:

```
stop: MAX_INPUT_TOKENS_EXCEEDED
7,575,648 in (85% cached) · 32,714 out · 87 tool calls · zero findings
```

### The byte cap works. That part is proven

`docs/openapi.json` in this PR is **2,947,014 bytes** — byte for byte the file
`design.md` uses as its motivating example. This is the real case, not a
reconstruction of it.

| | tokens if read |
|---|---|
| `openapi.json`, uncapped | **~736,000** |
| `openapi.json`, capped at 131,072 bytes | ~33,000 |
| the other 29 changed files | ~147,000 |
| **all 30 files, uncapped** | **~884,000** — inside a 1M window, with nothing to spare |
| **all 30 files, capped** | **~180,000** |

**The cliff is gone.** One generated file no longer ends the review. That was the
project's founding claim and it holds.

### What kills it instead: accumulation across turns

The agent behaves correctly. It calls `find_file` to orient, then `view_file`
once per changed file. The trace shows nothing wasteful.

But **every file it reads stays in context for every later turn.** Thirty files
of ~180k tokens, resent across ~30 turns, is ~5M cumulative — and the observed
figure was 7.5M. The cost is quadratic in files read, and nothing in the
configuration bounds it.

`CapabilitiesConfig(compaction_threshold=...)` is the lever, and **M1 never set
it**. `design.md` names it as the only thing that bounds context growth, and the
implementation left it at whatever the SDK defaults to.

### Why the fixture never caught this

Four files. A two-file diff gives the agent nothing to accumulate and no reason
to explore. **The M1 exit criterion was met by a pull request small enough that
the failure mode could not occur** — which is the argument for M5 restated as an
incident, and an argument for fixtures that resemble real work.

### What this changes

- **M3 must bound context growth, not just spend.** A dollar ceiling that stops
  a runaway after $1.50 is not the same as a reviewer that does not run away.
- **`compaction_threshold` belongs in the configuration**, with a measured value.
- **Per-review cost is not flat.** The 4-7 cents measured on the fixture is a
  two-file number; this PR cost twenty times that and produced nothing.
- **A large PR may need splitting** — reviewing in batches, or per directory —
  rather than one session holding thirty files at once.

Recorded as a failure rather than filed as a bug, because the reviewer is
working as designed and the design is what needs to change.

## 🔴 The reviewer reads files. It should be reading diffs

Following the `doitbse/draft#538` failure, one question turned out to matter
more than the accumulation problem: **why did the agent open a 2.9 MB generated
file at all?**

| | |
|---|---|
| `docs/openapi.json` | 2,947,014 bytes, 74,560 lines |
| the actual change | **+30 lines, patch 2,799 bytes** — 0.09% of the file |
| where the change is | **line 13,329** |
| what the 131,072-byte cap reads | lines 1 – **3,113** |

**The agent read the wrong 128 KB.** It spent roughly 33,000 tokens, never saw
the changed lines, and the truncation marker correctly told it not to reason
about the part it could not see. On that file it could not have produced a
review no matter what it did.

The byte cap is doing its job — it prevents the crash. It cannot make a
head-of-file read relevant to a change two thirds of the way down.

### Three gaps that compound

1. **The seed carries no size signal.** `docs/openapi.json (added, +30/-0, sha)`
   is indistinguishable from a forty-line source file. The agent has nothing to
   triage on, so it opens everything.
2. **`view_file` reads from the top.** For a change at line 13,329 the head is
   exactly the wrong slice, and the agent has no way to know where to look.
3. **The patch exists and is never offered.** GitHub returns it per file, it is
   2,799 bytes, and it contains precisely the thing under review — **1,053×
   smaller than the file**.

### The correction

[`design.md`](design.md) is right that diff hunks must not go **in the seed** —
attaching them for every file is what produced the original 1M-token failure.
But the conclusion drawn from that was too broad. The fix is not "no hunks
anywhere"; it is **hunks on demand, through a tool**.

That is the pull-context principle exactly. The current design applies it to file
bodies and forgets the diff, which leaves the agent reading whole files to find
changes it was never shown.

**Proposed:** a `view_diff(path)` tool returning the changed hunks for one file,
byte-capped like `view_file`. For this pull request that is 2,799 bytes instead
of 131,072 — and unlike the 131,072, it contains the change.

**Also proposed:** carry file size in the seed, so a generated artefact can be
recognised without opening it. The instruction "do not review generated files"
is unactionable when the only way to tell is to read the file.

### Why none of this surfaced earlier

The fixture's oversized file was a flat 582 KB JSON array with the "change"
being the whole file, so a head read was representative and the cap looked
sufficient. A real generated file gets a small edit in the middle, which is the
case that breaks it. **The fixture tested the cap, not the thing the cap was for.**

## M2.5 — the cost problem is fixed; recall is not demonstrated

Three changes after the `draft#538` failure: a `view_diff` tool serving the
patches the collector already fetched, diff size carried in the seed,
`compaction_threshold` set, and system instructions rebuilt around the precision
structure in Anthropic's `code-review` plugin.

### The cost and completion problem is solved

Same pull request, same repository, before and after:

| | before | after |
|---|---|---|
| input tokens | 7,575,648 | **2,111,714** |
| tool calls | 87 | 88 |
| stop reason | `MAX_INPUT_TOKENS_EXCEEDED` | **completed normally** |
| cost | $1.46 | **$0.39** |

It no longer runs out of context on a 30-file pull request. The first diff-only
run was cheaper still — 269,566 tokens at $0.11 — before cross-file reading was
encouraged, which is the honest cost of following references.

### Recall is not

At the commit `claude[bot]` reviewed, on the same 21 changed files, ours reported
**no findings**. `claude[bot]` reported four, all of them real enough that the
next commit on the branch is titled *"fix(website): address PR #538 review
findings"*.

**A methodology error nearly buried this.** The first comparison ran against the
pull request *head*, which is two fix commits later than the code
`claude[bot]` saw — so "we found nothing they found" was measuring different
source. Re-running at `5349acd3` gave the same result, so the gap is real, but
the first version of this comparison was not evidence of it.

### What does not explain it

- **Not the context ceiling.** The run completes with room to spare.
- **Not missing repository conventions.** The repo has a 9.5 KB `CLAUDE.md`, and
  `claude[bot]`'s prompt does launch dedicated compliance agents against it — but
  the convention behind its sharpest finding, that a new field must be routed
  through `stagedFields` rather than `directFields`, **is not in `CLAUDE.md`**. It
  derived that from reading the PUT handler.
- **Not a refusal to look.** 88 tool calls, and the model reports having followed
  references across HubSpot APIs, schema validation and the blog renderer.

### What might

- **Over-suppression.** The instructions now carry an explicit do-not-flag list
  and "if you are not certain an issue is real, do not flag it". M1 already
  measured this reviewer dropping a marginal finding whenever its list ran short.
  A precision bar tuned for a different model may simply be silencing it.
- **No verification pass.** Anthropic's design *generates* findings with one set
  of agents and *confirms* them with another. Ours does both in one pass, where a
  strict bar cannot distinguish "checked and dismissed" from "never formed".
- **Depth.** `claude[bot]`'s findings require holding a component, a query
  function and a schema comment together, then reasoning about intent. That is a
  harder task than pattern-matching a diff, and the models are not the same.

### The next diagnostic, and why

Point the reviewer at one known finding and ask directly. That distinguishes
**cannot see it** from **saw it and suppressed it**, which have opposite fixes:
the first needs better reasoning or context, the second needs a looser bar. Until
that is run, the cause is a hypothesis and is recorded as one.

**What can be claimed today:** the reviewer completes on a real pull request
inside a sane budget, which it could not do before. **What cannot:** that it
finds anything worth reading there.

## ✅ Why the reviewer found nothing: scope, not capability

The diagnostic that settles it. Three conditions on the same code, at the commit
`claude[bot]` reviewed.

| condition | scope | result |
|---|---|---|
| full review, strict bar | 21 changed files | **no findings** |
| pointed question, strict bar | 2 files | **found it exactly**, with line references |
| open question, strict bar | 2 files | **found it** — plus a bug `claude[bot]` did not report |
| open question, **loose** bar | 2 files | **found it** |

**The model can do the reasoning.** Asked "for which page types is
`gatedContentTag` read, and for which can an editor set it — are those the same
set?", it answered precisely: read for `landing` and `hubspot-landing` only, and
settable on all seven. That is `claude[bot]`'s finding, independently reproduced.

**The precision bar is not the cause.** The strict instructions — do-not-flag
list, "if you are not certain, do not flag it" — found it at two files. Loosening
to "err on the side of reporting" changed nothing about whether it was found.

**The variable is scope.** Two files: found. Twenty-one files: silent.

### A trap this diagnostic fell into first

The first two conditions returned **empty text**, which reads exactly like "no
findings". They were budget stops — `MAX_OUTPUT_TOKENS_EXCEEDED` against a 3,000
cap set for economy. Q8 predicted this precisely: *a budget stop preserves usage
and returns empty text.*

**An empty review is indistinguishable from a clean review** unless the stop
reason is checked. The runner does check it, and the review body says so — but a
diagnostic written in haste did not, and drew the opposite conclusion for two
runs. Anything reading these results must check `stop_reason` first.

### What this implies for the design

Anthropic's `code-review` plugin fans out to four agents with narrow mandates and
then validates each finding. Read against this measurement, **narrow scope is not
a parallelism optimisation — it is the mechanism that makes findings appear at
all.**

We cannot copy the fan-out: subagents fail on Vertex and escape `BudgetConfig`
(Q4). But the property that matters is scope per pass, not parallelism, and that
is reachable sequentially — **several small sessions instead of one large one.**

That also fixes the accumulation problem by construction. A session over three
files cannot grow the context that a session over thirty does, so batching
addresses recall and cost with the same change.

**Next:** batch by file group and measure recall against `draft#538` at
`5349acd3`, where four findings are known and one is now independently
reproduced.

## The batching experiment — baseline, and the bar it must clear

Recorded before the result, so the bar cannot move afterwards.

**All measurements on `doitbse/draft#538` at `5349acd3`** — the commit
`claude[bot]` reviewed, 21 changed files, four known findings:

| # | file | defect |
|---|---|---|
| 1 | `site-page-editor-shell.tsx` | `gatedContentTag` editable on all seven page types, read for only two |
| 2 | `schemas/site-page.ts` | the field lands in `directFields`, bypassing the staging approval gate |
| 3 | `lib/landing-page-utm.ts` | `utm_campaign` uses the bare leaf slug, which is not unique across parent paths |
| 4 | `lib/landing-page-sales-notification.ts` | fires on every publish, not the first, so republishing re-announces a page live for weeks |

None of the four is pattern-matchable. Every one needs either a second file or
domain knowledge of the flow.

### Baseline — single session, everything tried

| variant | scope | recall | cost |
|---|---|---|---|
| strict bar | 21 files | **0/4** | $0.39 |
| loose bar | 21 files | **0/4** | — |
| `thinking_level=HIGH` (4x reasoning) | 21 files | **0/4** | ~$0.60 |
| strict bar | **2 files** | **found #1** | ~$0.05 |
| loose bar | **2 files** | **found #1** + a defect `claude[bot]` missed | ~$0.05 |

Instructions, precision bar, and reasoning budget were each varied and none
moved it. Scope moved it every time.

### The bar

Batching is adopted **only if it beats 0/4 at $0.39**. Nothing else about the
reviewer changes — same model, same instructions, same tools — so any difference
is attributable to scope per pass.

A result of 1/4 would be real but thin: finding #1 is already known reachable at
two-file scope, so recovering only that shows batching works and little else.
**2/4 or better means it generalises**, because #2, #3 and #4 have never been
found by this reviewer under any condition.

If it does not clear the bar, it does not ship, and the entry below says so.

## 🔴 Batching failed the bar. It does not ship

| | recall | cost |
|---|---|---|
| baseline, single session, 21 files | 0/4 | **$0.39** |
| **batched, 6 sessions of 4 files** | **0/4** | **$0.70** |

No better on recall, 79% worse on cost. Per the bar recorded before the run, it
is not adopted. It stays in `probe/` as a measurement.

### It also refutes the conclusion it was built on

**Batch 3 contained `site-page-editor-shell.tsx` and `gated-content-cta.ts`** —
the exact pair where the diagnostic found the defect three times out of three. It
returned `NO FINDINGS`.

So *"recall is a function of scope per pass"* was **wrong**, and the earlier
entry saying otherwise was wrong. The diagnostic that produced it was confounded:
every condition that found the defect also **named the feature** and used **only
the two files that mattered**. Scope was varied, but never alone.

### Two things the follow-up separated

**The escape hatch was mine, and it mattered.** The batch instructions said *"if
you find nothing, say exactly NO FINDINGS"* — and all six batches did, to the
character. Removing that line, same four files, produced real findings instead
of silence. **Offering a clean way to say nothing makes saying nothing the path
of least resistance.** That is a defect in how the probe was written, not in the
reviewer.

**Naming the feature did not help.** With the escape hatch gone and the
`gatedContentTag` feature described in the prompt, it still did not find the
page-type mismatch.

### What actually distinguishes found from missed

Across every run so far, one pattern holds:

- **Local defects it finds reliably.** The `sortOrder` `NaN` — `a.sortOrder -
  b.sortOrder` on an optional field — was reported in four separate runs, at
  two-file and four-file scope, under strict and loose bars. **`claude[bot]` did
  not report it.**
- **Cross-file contract mismatches it does not find spontaneously.** All four
  known findings are of this kind: a field settable in one place and read in
  another, a field missing from an allowlist, an identifier assumed unique that
  is not, a notification assumed once-only that is not. It found one of them —
  **only** when asked *"for which page types is this read, and for which can it
  be set — are those the same set?"*

The distinction is not scope, and not the precision bar. It is whether the
comparison has been **posed**. Given a hypothesis to test, the model tests it
correctly. Left to generate its own hypotheses across a diff, it inspects each
change locally and reports what is wrong *within* it.

### Where that leaves the design

Anthropic's plugin does not solve this by scope either — it solves it by giving
each agent a **mandate**: this one checks CLAUDE.md compliance, that one hunts
bugs in the introduced code. A mandate is a hypothesis generator.

So the next thing worth testing is not smaller batches but **named review passes**
— "for every field this PR adds, find where it is read and where it is written,
and report any asymmetry" — which is the shape of three of the four known
findings. That is a checklist of contract questions, not a smaller window.

Untested. Recorded as the next hypothesis rather than a conclusion, since the
last one did not survive contact.

## ✅ Contract passes beat the baseline on both axes

Instead of "review this pull request", ask three named structural questions over
the whole diff. Not batched — batching measured worse.

| approach | recall | cost |
|---|---|---|
| single session, 21 files | 0/4 | $0.39 |
| batched, 6 x 4 files | 0/4 | $0.70 |
| **contract passes** | **2/4** | **$0.26** |

**Better recall at two thirds the cost**, and achieved with **one of the three
passes crashed** — the one targeting finding #3.

The passes:

1. *For every field this PR adds: where can it be written, where is it read, are
   those the same conditions?* → findings #1, #2
2. *For every value used as an identifier: what uniqueness is assumed versus
   guaranteed?* → finding #3
3. *For every side effect added: can it fire more than once for the same
   subject?* → finding #4

### The instrument was validated first

Fed `claude[bot]`'s own review text, the scorer returns **4/4**. A scorer that
could not find these in the reference would have reported a false 0/4 for
everything — which is the class of error this investigation has already made
twice.

### 🔴 "Found" means surfaced, not flagged

This qualification matters more than the number. On finding #1 the report says:

> **Condition difference (by design)**: the field can be set on any `SitePage`,
> but `findGatedContentCta` only reads it where `status == 'published'` and
> `pageType in ['landing', 'hubspot-landing']`.

That is exactly `claude[bot]`'s finding — **and it is labelled "by design" and
dropped.** The asymmetry was identified correctly and then judged not to be a
defect.

So the contract passes fix the half that was actually broken: the model now
*performs the comparison* instead of inspecting each change locally. What it does
not yet do is *judge* the result. A surfaced asymmetry marked "by design" never
becomes a review comment.

That is a tractable gap, and it is the mirror of Anthropic's step 5. They
generate findings and validate them to remove false positives; we surface facts
and need a pass to decide which are defects. **Same separation, opposite
direction.**

### 🔴 An invalid tool call kills the session

Pass 2 died on:

```
AntigravityExecutionError: model output error:
invalid tool call error (invalid_signature) SearchPath is required
```

`search_directory` requires a `SearchPath` argument that appears nowhere in the
SDK surface — `GrepSearchToolConfig` exposes only `enabled`. Omitting it
**terminates the whole session** rather than returning a tool error the model
could correct. It has now hit 4 of 7 runs, and it explains the "internal error in
running grep command" seen in the first `draft#538` attempts.

`ModelOutputRetryConfig(max_retries=1)` did not save it, because this is not a
schema-validation retry — it is fatal.

Fix by naming the required parameter in `system_instructions`, the way the MCP
casing was fixed. Dropping the tool is the wrong answer: following references is
the capability the contract passes depend on.

### What ships

The contract-pass structure earns adoption on the measurement. Two things must
land with it: the `SearchPath` parameter documented, and a judging step so a
surfaced asymmetry is decided rather than annotated.

**And the standing caveat: this is one pull request with four findings.** 2/4 on
n=1 is a reason to build M5's fixture set, not a claim that the reviewer works.

## Contract passes + judging: surfacing solved, reporting is the bottleneck

Second measured run, after documenting `SearchPath` and adding a judging step.

| | run 1 | run 2 |
|---|---|---|
| passes completed | 2 of 3 (one crashed) | **3 of 3** |
| findings **surfaced** | 2/4 | **4/4** |
| findings **reported as defects** | n/a | **1/4**, plus one novel |
| cost | $0.26 | $0.34 |

**Documenting `SearchPath` fixed the crash**, pass 2 ran, and with it every one of
the four known findings was surfaced. The passes now describe all of them.

**The judge then reported two defects**, one of which is finding #1, stated
correctly and in its own words:

> An editor can set a gated content tag on standard or documentation pages, but
> it will never match or render an in-article CTA because CTA resolution only
> queries landing pages.

Its second defect is **novel** — a missing `BU_SALES_SLACK_CHANNEL_ENV` mapping
for the Attribute business unit, which neither `claude[bot]` nor any earlier run
reported.

Findings #2, #3 and #4 were surfaced by the passes and dropped by the judge.

### 🔴 The scorer produced a false negative. Third measurement error

The run reported **0/4 reported**. The correct figure is **1/4 plus one novel**.

The scorer greps for `"page type"`; the judge wrote `"pages"`. It was validated
against `claude[bot]`'s phrasing and then applied to a different writer, so
paraphrase defeated it.

That is the third time an instrument, not the reviewer, produced the headline
number in this investigation:

1. comparing against the wrong commit, two fix commits after the reviewed code;
2. a budget stop returning empty text, read as "no findings";
3. keyword scoring failing on paraphrase.

**Every one made the reviewer look worse than it was.** A keyword scorer cannot
measure recall over free text, and the fixture work in M5 needs a scorer that
compares meaning — or findings emitted in a structured form that can be matched
on file and line rather than wording.

### Where the bottleneck moved

It has moved twice, and both moves were real progress:

1. **Not performing the comparison** — fixed by naming the contract question.
   Surfacing went 0/4 → 2/4 → 4/4.
2. **Performing it and not reporting it** — the current bottleneck. The judge
   sees four described asymmetries and calls one a defect.

The judge is one prompt with no tools; it cannot check the codebase to decide
whether an asymmetry is guarded. Giving it the same tools the passes have is the
obvious next thing to try, and is untested.

### What can be claimed

The reviewer now **finds** all four known findings, in the sense of describing
each correctly. It **reports** one of them plus one nobody else found. The
remaining gap is a judgement problem, not a perception problem, which is a
better problem to have and a narrower one to fix.

**Still one pull request with four findings.** Every number above is n=1.

## 🛑 Stop tuning: the measurement is now noisier than the interventions

Three runs of the contract-pass reviewer on the same pull request, at the same
commit, with the same four known findings.

| | run 1 | run 2 | run 3 |
|---|---|---|---|
| change | — | `SearchPath` documented, judge added | judge given tools |
| passes completed | 2 of 3 | 3 of 3 | 3 of 3 |
| **surfaced** | 2/4 | **4/4** | **3/4** |
| **reported** | — | 1/4 + 1 novel | **1/4** |
| cost | $0.26 | $0.34 | $0.31 |

**Giving the judge tools changed nothing measurable.** Reported held at 1/4, cost
moved by three cents, and the novel defect from run 2 disappeared.

### The variance is larger than the effects

Between run 2 and run 3, with **no change to the passes at all**:

- pass 1 output: 20,012 chars → 9,912 chars
- findings surfaced: 4/4 → 3/4

A finding that was surfaced in one run was not surfaced in the next, from an
identical prompt against identical code. M1 already measured this reviewer's
non-determinism and found the marginal finding dropping off a short list; this is
the same effect at the scale that matters.

**So the last two interventions cannot be evaluated.** A change worth less than
one finding is invisible against a ±1 finding swing, and every number in the
table is a single sample.

### What is established, and what is not

**Established**, because the effects are large enough to clear the noise:

- Naming the contract question works. 0/4 surfaced across every variant of "find
  bugs" — including four times the reasoning — against 3/4 or 4/4 once the
  comparison is posed. That is the finding of this whole investigation.
- Documenting `SearchPath` fixed a fatal crash, reproducibly, across three runs.
- Diff-first plus `compaction_threshold` took a run that died at $1.46 to one
  that completes at ~$0.30.

**Not established**: whether the judge helps, whether tools help the judge,
whether 1/4 or 2/4 is the real reporting rate, and whether any of it generalises
past this one pull request.

### The rule this run bought

**No further tuning against n=1.** Three separate times an instrument produced
the headline number here rather than the reviewer, and now run-to-run variance
exceeds the interventions being tested. Continuing would be fitting to noise, and
doing it carefully would not make it less so.

M5 is no longer a later milestone. It is the precondition for any further claim
about review quality, and it needs three things:

1. **Several pull requests** with known findings, not one.
2. **Repeated runs per configuration**, since one sample cannot see a ±1 swing.
3. **Structured findings** — file, line, claim — matched on location rather than
   wording. Keyword scoring over free text has already produced one false zero.

## M2.5 shipped: the port works, and the judge is now the ceiling

The contract-pass structure moved from `probe/` into `review.py`, and running it
end to end immediately found something no unit test would have.

### Contract questions alone lost local recall

On the fixture — seven planted defects, mostly local — the ported reviewer found
**2**, against the general reviewer's **4**. It lost a SQL injection and a
`Decimal`/`float` mismatch, and reframed a committed API key as *"has no effect
because the configuration key is never read"*.

That last one is the lens showing through. A write/read asymmetry pass pointed at
a credential sees dead configuration, because asymmetry is the only question it
was asked. **Contract questions add cross-file recall; they do not replace asking
whether the changed code is simply wrong**, and shipping them as a replacement
traded one blindness for another.

Fixed by adding a fourth pass that runs first and asks the plain question — will
this compile, will it produce a wrong result, is it a security defect, does it
contradict a convention here — with an explicit instruction not to describe a
credential in source as unused configuration.

**Caught only because the port was run rather than assumed correct from its
parts, and only because the fixture exercises different defect classes than
`draft#538`.** Optimising against one pull request regressed the other, which is
the n=1 trap arriving on schedule.

### The judge is now the limiter

| run | passes | reported |
|---|---|---|
| contract only | 3 | hardcoded key · overdraft bypass |
| + local-defect pass | 4 | **SQL injection** · **`Decimal`/`float` TypeError** |

More passes surfaced more, and **the count reported stayed at 2 while the
identity of the 2 changed completely.** None of the four runs reported the same
pair.

This is M1's measurement reappearing one stage later. There, the reviewer dropped
the marginal finding whenever its list ran short; here, the judge selects roughly
two defects from whatever the passes surface. The bottleneck has moved from
perceiving to describing to judging, and each move was progress.

Cost improved while this happened: **$0.0751 with four passes**, against $0.1240
with three — a shorter, less exploratory run.

### Not tuning this

The rule from the previous entry applies. Four runs, four different pairs, one
fixture: the variance is larger than any change worth making, and picking a judge
prompt that reports four instead of two would be fitting to noise.

**This is an M5 question**, and it is now the sharpest one the harness has to
answer: given a set of surfaced properties, how many become reported defects, how
stable is that selection, and does it depend on the prompt or on the model.

## Still open

- **Q10.** Vertex-side rates, and the `FLEX` tier the enum revealed.
- **Q4.** Subagent roll-up, properly controlled.
- **Q5.** Whether retries count against `max_model_calls`.

These runs used a private scratch repository with two throwaway pull requests. Recreate one with any repo containing a PR with a couple of obvious defects.
