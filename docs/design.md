# Design

## Goal

A pull request reviewer that finds defects a single-shot reviewer structurally cannot, reports what each review cost, and refuses to exceed a cost ceiling.

## The two context strategies

**Push.** Assemble one prompt containing the diff, the full content of changed files, and some slice of the repository; make one model call. Cheap, fast, deterministic in shape.

**Pull.** Put PR metadata and a list of changed files in the prompt; give the agent file-reading tools; let it fetch what it needs across several turns.

Push fails in two ways that matter.

**It cannot follow a thread.** Consider a change that adds a field to a form and a schema, where the bug is that a *different* file's allowlist governs whether that field is routed through an approval workflow. Nothing in the diff points at the allowlist. A pull-based agent greps for the field name, finds the routing code, and sees the omission. A push-based agent finds it only if its up-front file selection happened to include that file.

**It has a cliff, not a slope.** Because everything is in one request, one oversized file ends the review. A real example: a PR touching a **2.9 MB generated OpenAPI specification** — whose *diff* was about 4 KB — produced

```
400 INVALID_ARGUMENT. The input token count exceeds the maximum
number of tokens allowed 1048576.
```

and posted nothing at all. The full current content of every changed file was being attached, uncapped, so roughly 980k tokens of a file nobody was reviewing crowded out the review.

Pull avoids this by construction: the agent sees `openapi.json  (modified) +12/-4`, decides it is uninteresting, and never opens it.

**The honest cost of pull:** several model calls instead of one, so higher cost and higher latency per review. This project does not argue that pull is free. It argues that pull is worth it *and* that you should be able to prove the bill.

## Architecture

```
GitHub PR event
      │
      ▼
GitHub Actions workflow
      │  Workload Identity Federation → ADC (no API key)
      ▼
runner: python -m antigravity_code_review
      │
      ├── collect PR metadata + changed-file list  (GitHub REST)
      ├── build the prompt: metadata + file list ONLY, no file bodies
      │
      ▼
Antigravity Agent (Vertex, read-only policy)
      │
      ├── view_file / find_file / search_directory   ← the agent decides
      ├── github MCP server (allowlisted tools)      ← posts the review
      └── BudgetConfig (SDK-native)                  ← caps calls and tokens
      │
      ▼
   PR review posted   +   review-cost.json artifact
```

### Components

**Collector.** Reads the PR from the GitHub API and produces the prompt seed: title, body, base and head refs, and one line per changed file (`path`, change type, `+adds/-dels`, blob SHA). **No file contents and no diff hunks.** Keeping the diff out is what stops a large file from mattering; the agent fetches hunks through a tool when it wants them.

**Agent.** An `Agent` from the SDK, configured with `vertex=True` and ADC. The tool surface is constrained in **two layers**, and the order of them is the point:

```python
config = LocalAgentConfig(
    vertex=True, project=PROJECT, location=LOCATION,
    # Layer 1 — capability: these are the only tools that EXIST for this agent
    capabilities=types.CapabilitiesConfig(
        enabled_tools=[
            types.BuiltinTools.VIEW_FILE,
            types.BuiltinTools.LIST_DIR,
            types.BuiltinTools.SEARCH_DIR,
            types.BuiltinTools.FIND_FILE,
            types.BuiltinTools.FINISH,
        ],
        enable_subagents=False,
    ),
    # Layer 2 — policy: deny-by-default over whatever survived layer 1
    policies=[
        policy.deny_all(),
        policy.allow(types.BuiltinTools.VIEW_FILE),
        policy.allow(types.BuiltinTools.LIST_DIR),
        policy.allow(types.BuiltinTools.SEARCH_DIR),
        policy.allow(types.BuiltinTools.FIND_FILE),
        policy.allow(types.BuiltinTools.FINISH),
        policy.allow(github_mcp, GITHUB_TOOLS),
    ],
    workspaces=[os.getcwd()],
)
```

🔴 **Do not rely on the default being read-only. It is not.** `LocalAgentConfig` defaults to `policy.confirm_run_command()`, which denies `run_command` and **allows every other tool, including `create_file` and `edit_file`**. An earlier draft of this document claimed the SDK is read-only by default and was wrong. For a tool that reads pull requests from untrusted contributors, write access acquired by inheriting a default is exactly the kind of thing nobody notices until it matters.

### Why capabilities come before policies

An earlier draft used policies alone. Policies decide what a tool call *does when it arrives*; capabilities decide **whether the model is ever told the tool exists**. Under `deny_all()` on its own, `create_file`, `edit_file`, `run_command`, `start_subagent` and `generate_image` are all still advertised in every request — confirmed against the wire contract in M0: the shipped default enables 12 of the 14 `HarnessSideTools` slots, `file_edit`, `write_to_file` and `run_command` among them. That is worse in three separate ways, and one of them is this project's own subject:

**It costs money on every turn.** Tool schemas sit in the prompt prefix of a multi-turn pull-context review. Advertising eight tools the agent may never use is a tax on all fourteen turns of a review, and it is the cheapest saving available anywhere in this design.

**It invites denied calls, and a denied call is not free.** A model that can see `edit_file` will eventually try to fix what it found. Each attempt is a model call — billed, and counted against `max_model_calls`. Deny-by-default converts that into a refusal rather than a write, which is correct, but it does not convert it into silence.

**It removes one place to be wrong.** Getting the priority table below right is a prerequisite for the policy layer holding. Nothing has to be right for a tool that was never registered.

This is not a reading of the documentation — it is the SDK's own guidance, and it makes the same argument in the same terms. From the `CapabilitiesConfig` docstring in `0.1.12`:

> `enabled_tools` / `disabled_tools` control which tools the harness *exposes* to the model. A disabled tool is stripped from the model's context entirely — the model never sees it, never wastes tokens considering it, and never attempts to call it. […] By contrast, the policy system leaves a tool visible in the model's context but rejects the call at runtime. […] This costs tokens and may cause retries.
>
> **Guideline**: Prefer `disabled_tools` / `enabled_tools` for tools the agent should never use. Use `policy.deny()` for conditional or context-dependent restrictions.

`enabled_tools` is an **explicit allowlist, mutually exclusive with `disabled_tools`**; when both are `None` the harness default is all tools enabled. A reviewer's tool set is fixed and unconditional, which is exactly the case the guideline assigns to layer 1. Note the docstring names retries as a cost of the policy-only approach — a denied call can be re-attempted, so the waste is not bounded at one turn.

And `enable_subagents` **defaults to true**. M0 settled what that costs, and the answer is worse than the open question it replaces:

- Subagent tokens **do** roll into `Conversation.total_usage` — visible in `trajectory_usages` as a trajectory of their own.
- They do **not** count against `BudgetConfig`. The dial binds on the root trajectory, so a ceiling above the root and below root+subagent does not stop the run. **The ceiling leaks.**
- On Vertex, delegation **fails outright** in `0.1.12` — `CORTEX_STEP_TYPE_INVOKE_SUBAGENT: failed to fetch tiered models for subagent model resolution: PlatformClient is nil` — and the failed spawn still bills roughly **ten times** a direct answer.

So `enable_subagents=False` is not a cost preference here, it is a requirement: it is the only thing that makes the M3 ceiling truthful, and on Vertex delegation buys a guaranteed failure at 10x the price. See [`probe-results.md`](probe-results.md).

### Two levers the plan had not found

**`compaction_threshold`** on `CapabilitiesConfig` bounds how large the context grows before the harness compacts it. Compaction is both a billed call and a cache-prefix invalidation, so this is the one dial that trades those two costs against each other directly, and it is the only thing resembling a per-turn size guard in the SDK.

**`thinking_level`** on `GeminiModelOptions` — `MINIMAL`, `LOW`, `MEDIUM`, `HIGH`, `EXTRA_HIGH`. Thinking tokens bill at the **output** rate, and [`cost-tracking.md`](cost-tracking.md) already flags them as the term that moves a total unpredictably. That makes this the single largest cost lever in the configuration, and the plan had treated reasoning spend as weather rather than as a setting. It is also the obvious first axis for M5 to measure: the cheapest defensible reviewer is whichever thinking level stops finding defects.

### The policy layer, precisely

Three details decide whether the policy block does what it looks like it does:

**Policy resolution is priority-based, not order-based.** Nine levels: a *specific* deny (1) beats a *specific* allow (3), which beats a *prefix wildcard* allow (6), which beats a *global wildcard* deny (7). So `deny_all()` sets the floor and the named allows sit above it. First match wins only *within* a priority level.

**Name the MCP tools, do not pass the bare server.** `policy.allow(github_mcp)` is a *prefix wildcard* allow at priority 6; `policy.allow(github_mcp, [...])` with an explicit list is a *specific* allow at priority 3. Both outrank `deny_all()`, so both "work" — but the list form raises the priority, states the intent in the policy rather than only in the server config, and gives the same allowlist two places to be enforced. Pass the list, and keep `enabled_tools` on the server as well.

**The `BuiltinTools` enum is safe to pass to `policy.allow()`.** Its signature annotates `tool: str | BaseMcpServerConfig`, but `BuiltinTools` subclasses `str`, so `policy.allow(BuiltinTools.VIEW_FILE)` constructs the same policy a string would and is checked at import time instead of at runtime. Prefer it: `LIST_DIR` is `list_directory` and `SEARCH_DIR` is `search_directory`, so the hand-written strings are the error-prone half. That the SDK's own safety documentation contains an example allowing `code_search` — which is not a built-in tool at all — is the argument for letting the enum do the checking.

**`workspaces` earns its keep.** Setting it auto-applies `policy.workspace_only()`, restricting `view_file`, `create_file` and `edit_file` to those directories. Set it even though writes are already denied twice: defence in depth costs one line.

**Constrain the subprocess environment.** `LocalAgentConfig(env=...)` overrides what the harness subprocess inherits, and the GitHub MCP server is a `docker` child of that subprocess. Left unset, a container pulled from a registry inherits the runner's entire environment — every secret the workflow exposes, not just the token it needs. Pass a minimal dict.

**Predicates fail closed.** If a `when=` predicate raises, the SDK treats it as a *match* and applies that policy's decision. Fine for a deny, dangerous for an allow, so keep predicates on denies.

**A second enforcement layer.** Policies gate *which* tools may run, not *what arguments* they may run with. If `run_command` is ever allowed, a hook must constrain it — the pattern in both reference implementations is to reject anything that is not a `git` invocation. For a reviewer, prefer not allowing it at all.

**Reporting.** Two established options, and this is a genuine trade-off rather than a settled question.

*Structured output.* Pass `response_schema=ReviewResult` so the SDK enforces a typed result, then post it in one go. Reliable and easy to validate. This is what the Google codelab does.

*GitHub MCP server.* Register `ghcr.io/github/github-mcp-server` with an explicit `enabled_tools` allowlist and let the agent post through it:

```python
github_mcp = types.McpStdioServer(
    name="github",
    command="docker",
    args=["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
          "ghcr.io/github/github-mcp-server:v0.27.0"],
    enabled_tools=[
        "pull_request_read", "pull_request_review_write",
        "add_comment_to_pending_review", "get_file_contents", "search_code",
    ],
)
```

This is what `run-agy-sdk` does. It removes any need to write GitHub API code, and `enabled_tools` is itself a security boundary.

**Budget limits.** The SDK provides these natively via `BudgetConfig`; this project translates a *dollar* ceiling into those token limits. See [`cost-tracking.md`](cost-tracking.md).

### Where reporting and the budget limit conflict

A single structured response only exists at the end, so a run stopped by a budget limit produces **nothing at all**. Incremental posting through MCP is the obvious escape.

This is not hypothetical: `BudgetConfig` stops the session and reports a `StopReason`, so the run genuinely ends mid-review.

🔴 **But incremental MCP posting does not survive a stop either, with the tool list above.** `add_comment_to_pending_review` builds a **pending** review — a draft, visible to nobody — and it becomes a review only when `pull_request_review_write` submits it. An agent stopped after twelve comments and before the submit call has posted exactly as much as the structured-output path: nothing. The draft is arguably worse than nothing, because it is *somewhere*, so the failure does not look like a failure.

That collapses the trade-off into a single requirement, whichever reporting path wins: **the runner, not the agent, must own publication.** The agent gathers; the runner submits what exists when the session ends, however it ended. Concretely, on a non-`UNSPECIFIED` `StopReason` the runner submits the pending review itself and appends the stop reason in plain words.

**Leaning:** MCP for gathering, runner-owned submit, `StopReason` named in the posted body. To be settled with evidence in M1 rather than by preference — and the evidence to gather first is whether a stopped session leaves a pending review the runner can still submit, or leaves nothing at all.

There is a second reason to prefer MCP gathering over a single structured response, and it is a cost one. A `response_schema` violation triggers **four model output retries by default**, each re-prompting at the full accumulated context of a finished review. The most expensive turn is the one most exposed to the retry multiplier. See [`cost-tracking.md`](cost-tracking.md).

## Guardrails carried over from the push-based design

Some hard-won limits still apply, because the failure mode moves rather than disappearing. In a pull design the model chooses what to read, so a single tool call can still pull a 3 MB file into context.

**Cap file reads inside the tool — which means replacing the tool.** The built-in `view_file` has no documented byte limit and no documented way to add one. The SDK's supported mechanism is to **register a custom tool with the same name**, which takes priority over the built-in automatically (no `disabled_tools` entry needed) and logs `Custom tool "view_file" successfully overrides built-in tool.` on startup.

That is more work than a config flag, and the plan should carry the real cost: the override reimplements the whole tool, not just the cap, so it must match the built-in's parameter contract exactly — note the SDK's own override example takes `AbsolutePath`, not `path` — and it must reimplement ranged reads rather than inheriting them. Confirm the real signature against the pinned version in M0; the alternative is an agent whose file reads silently stop working.

**There is no second guard.** Every `BudgetConfig` dial is a session total, so none of them refuses a single oversized prompt — a 900k-token turn is permitted right up until the cumulative ceiling trips, and by then it has been paid for. The only other lever is `CapabilitiesConfig(compaction_threshold=...)`, which bounds how large the context grows before the harness compacts it. So the byte cap is not defence in depth here; it is the defence.

Whatever does the truncating must say so in the returned text:

```
[TRUNCATED: 'docs/openapi.json' is 2,947,014 bytes, showing the first 131,072.
The rest was NOT provided. Do not draw conclusions about the omitted portion.]
```

Truncation must be loud. A silently shortened file is worse than an absent one, because the model reasons confidently about content it cannot see and the reader of the review cannot tell.

**Cap by size, not by filename.** The obvious alternative is a denylist (`package-lock.json`, `*.lock`, and so on). Denylists only cover the generated files someone already imagined, and every repository has a different one: a snapshot, a bundled schema, a fixture, a vendored client. A byte cap covers the ones not invented yet.

**Prefer ranged reads.** Paging through a large file deliberately beats pulling it whole. The exact range parameters are part of the tool contract to be confirmed in M0 alongside the override.

## Repository rules

Reviewers are far more useful when they know a repository's own invariants.

The SDK supports this directly through **Agent Skills**, via `skills_paths` on the config — the mechanism the Google codelab uses to supply its `code-review-and-quality` skill. Use that rather than inventing a parallel convention.

One caveat, learned from watching a similar mechanism in production: **if repository rules are reachable only through a discovery step the agent may skip, it will often skip them.** The review then reflects generic knowledge while appearing to be repo-aware, which is worse than having no rules at all, because nobody can tell from the output.

The SDK's own skills example prompts the agent with *"What available skills do you have?"* — which reads as **discovery rather than unconditional injection**.

The SDK states that it follows the [official Agent Skills specification](https://agentskills.io/home), and under that specification the split is well defined: a skill's **frontmatter name and description are advertised** to the model, while the **body is loaded when the model decides it is relevant**. That is a likely answer rather than a confirmed one, but it is a sharper starting hypothesis than "unknown", and it predicts the observed example exactly.

If it holds, the rule follows: anything that must *always* apply belongs in `system_instructions`, the frontmatter description must be written as a trigger rather than a title, and `skills_paths` carries the deep reference material the agent consults when it decides it needs it. M4 verifies this against a run log rather than assuming it.

## Telemetry

The SDK ships OpenTelemetry support (`google.antigravity.utils.otel`), so spans can be exported to Cloud Trace rather than invented here. That is the right substrate for "why was this review slow" and "which tool dominated", and it means per-run analysis is a query rather than a bespoke logging layer.

Cost still has to be layered on top, because a span carries tokens and not money.

## Non-determinism and evaluation

An agentic reviewer will not produce identical output twice. Comparing it against anything, including its own previous version, needs a fixture-based evaluation: a set of PRs with known planted defects, scored on how many were found and how many findings were spurious.

This is scheduled early ([`roadmap.md`](roadmap.md), M5) rather than late, because without it every claim about quality is an anecdote. A related lesson worth stating: a plausible-sounding change (a reasoning budget, a stricter prompt) can measurably make results *worse*, and you will not know without a harness.

## Security posture

- **No long-lived credentials.** WIF exchanges the workflow's OIDC token for short-lived Google Cloud credentials. Nothing to rotate, nothing to leak.
- **Least privilege.** The service account needs only the Vertex AI user role.
- **No writes to the repository.** No shell, no file writes into the checkout, no network beyond the model endpoint and the GitHub API used by the reporting tools. Stated that way deliberately: the harness itself writes artifacts (`task.md`), scratch files and media under `~/.gemini/antigravity/brain/` regardless of policy, because that is the agent's own storage rather than a tool call. Point `app_data_dir` at an absolute path under the runner's temp directory, so agent scratch cannot land in the checkout and is discarded with the job. Relative paths and `~/` raise a validation error.
- **A minimal subprocess environment.** `env` on the config bounds what the harness — and the MCP container it launches — inherits from the workflow.
- **Untrusted input.** PR content is data, not instructions. A PR that contains text addressed to the reviewer must not change its behaviour; this needs an explicit system instruction and an evaluation fixture, because the agent reads attacker-controllable content by design.
- **Fork PRs.** `pull_request` from a fork gets a read-only token and no access to identity federation. Handle deliberately: either skip, or use `pull_request_target` with a strict checkout of the base and no execution of PR code. **Do not** check out and run fork code with write permissions.
- **Supply chain.** The SDK ships a compiled runtime binary in its PyPI wheels, so the source repository alone is not sufficient to run it. Pin the version, and record that this is a weaker audit story than a pure-source dependency.

## Open questions

These are unresolved and are called out rather than assumed.

1. **Headless authentication in CI via WIF.** The SDK supports `vertex=True` with ADC, and the codelab's agent falls back to it when no API key is set. But **both published examples authenticate their workflow with an API key secret**, so the WIF path inside a GitHub Actions runner is demonstrated nowhere. Still M0's first task, though a smaller risk than it looked: the SDK side is supported, only the CI wiring is unproven. Pass `project` and `location` explicitly, as the SDK documents them — the environment-variable names are inherited convention, not documented SDK surface, and an assumption in the one place the project cannot afford one. If ADC turns out not to work headlessly, the documented fallback is Vertex **Express Mode** (`vertex=True, api_key=...`): it keeps spend on Vertex and attributable, at the cost of reintroducing the key this design exists partly to remove.
2. **Whether `CapabilitiesConfig(enabled_tools=...)` is exclusive or additive.** The SDK's documentation says both, in different files. The whole first layer of the tool boundary depends on the answer. See "Why capabilities come before policies".
3. ~~**Whether subagent tokens roll into `Conversation.total_usage` and count against `BudgetConfig`.**~~ **Answered (Q4).** They reach `total_usage` but escape `BudgetConfig`, and on Vertex delegation fails outright while still billing ~10x. They are an uncounted spender. `enable_subagents=False` is mandatory.
4. **How much of a skill reaches the model unprompted.** The SDK's own example asks the agent *"What available skills do you have?"*, which reads as discovery rather than unconditional injection. The Agent Skills specification predicts frontmatter-always, body-on-demand. Needs confirming against a run log, not inferred. See "Repository rules" above.
5. **Cost versus a single-shot reviewer**, measured rather than assumed. Plausibly several times higher per review. Whether the extra findings justify it is an empirical question, and the answer may be "only on larger PRs".
6. **Latency.** Multi-turn agents are slower. If a review lands after a human has already merged, it buys nothing — which is the single most common way an AI reviewer becomes shelfware.
7. **Context caching, and how often compaction destroys it.** Whether the SDK exposes explicit caching, and whether a stable prefix makes it worthwhile. Compaction is the known adversary here: it rewrites the prefix mid-review, and `@hooks.on_compaction` is how to find out how often. See [`cost-tracking.md`](cost-tracking.md).
