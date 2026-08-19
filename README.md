# antigravity-code-review

An AI pull request reviewer built on the [Google Antigravity SDK](https://github.com/google-antigravity/antigravity-sdk-python), with **per-PR cost tracking and per-PR cost limits** as first-class features.

> **Status: design stage.** This repository currently contains the plan, not an implementation.
> [`docs/design.md`](docs/design.md) — architecture ·
> [`docs/cost-tracking.md`](docs/cost-tracking.md) — the cost model ·
> [`docs/roadmap.md`](docs/roadmap.md) — milestones and risks ·
> [`docs/prior-art.md`](docs/prior-art.md) — what already exists and what is borrowed from it.

## Why another PR reviewer

Most AI reviewers **push** context: they decide up front what the model should see, pack the diff plus a slice of the repository into one prompt, and make a single call. That is cheap and simple, and it has two structural problems.

**It has to guess right.** A finding that requires reading a file *outside* the diff is only reachable if the up-front guess happened to include that file.

**It has a hard ceiling.** Everything goes into one request, so a single large generated file — an OpenAPI spec, a bundled schema, a snapshot — can exhaust the model's input window and the review fails outright rather than degrading.

This project **pulls** context instead. The prompt carries the PR metadata and a *list* of changed files. The agent then reads, greps and lists its way to what it actually needs, one call at a time.

The trade-off is real and is not hidden here: pulling means many model calls, so it costs more per review than a single-shot reviewer. That is precisely why cost tracking is a headline feature rather than an afterthought.

## What makes this different

**You will know what every review cost.** Each run reports input, cached, output and reasoning tokens separately, prices them, and writes a machine-readable artifact. Costs roll up per PR, per repository, and per month.

**You can cap it in dollars.** The SDK enforces budgets in *tokens*; this translates a `max_cost_usd` ceiling into those limits, so the number you set is the number you care about. A budget you can only observe is not a budget.

**No API keys.** Authentication uses Workload Identity Federation to Vertex AI, so there is no long-lived credential in any repository secret, and inference is billed to the Google Cloud project you point it at.

**Read-only by construction, not by default.** The SDK's default policy denies `run_command` and **allows everything else, including `create_file` and `edit_file`**. A reviewer must therefore deny explicitly rather than inherit safety. This one names the handful of tools it needs twice: once as the only capabilities that exist, and once as the only policies above a `deny_all()` floor.

## How it will work

```yaml
- uses: doitintl/antigravity-code-review@v1
  with:
    gcp_project: your-project
    model: gemini-3.7-flash
    max_cost_usd: "0.50"   # abort and post partial results beyond this
```

Roughly, in the agent process:

```python
from google.antigravity import Agent, LocalAgentConfig, types
from google.antigravity.hooks import policy

config = LocalAgentConfig(
    vertex=True,
    project=PROJECT,
    location=LOCATION,
    system_instructions=REVIEWER_INSTRUCTIONS,
    workspaces=[os.getcwd()],            # auto-applies policy.workspace_only()

    # Layer 1: the only tools that exist for this agent
    capabilities=types.CapabilitiesConfig(
        enabled_tools=[
            types.BuiltinTools.VIEW_FILE,
            types.BuiltinTools.LIST_DIR,
            types.BuiltinTools.SEARCH_DIR,
            types.BuiltinTools.FIND_FILE,
            types.BuiltinTools.FINISH,
        ],
        enable_subagents=False,          # on by default; an uncounted spender
    ),
    # Layer 2: deny-by-default over whatever survived layer 1
    policies=[
        policy.deny_all(),
        policy.allow(types.BuiltinTools.VIEW_FILE),
        policy.allow(types.BuiltinTools.LIST_DIR),
        policy.allow(types.BuiltinTools.SEARCH_DIR),
        policy.allow(types.BuiltinTools.FIND_FILE),
        policy.allow(types.BuiltinTools.FINISH),
        policy.allow(github_mcp, GITHUB_TOOLS),     # posts the review
    ],
    skills_paths=["./.github/review-skills"],
    budget_config=budget_for(max_cost_usd=0.50, model=MODEL),
)
```

Two things in there are worth knowing before anyone "fixes" them.

`deny_all()` first looks like it should block everything. It does not: policy resolution is **priority-based, not order-based**, and a *specific* allow (priority 3) outranks a *global wildcard* deny (priority 7). The allowlist wins, which is the intended reading.

And the capability layer is not redundant with the policy layer. A denied tool is still *advertised* to the model — its schema is in the prompt on every one of a review's fourteen turns, and the model will spend real calls trying to use it and being refused. `enabled_tools` means it was never there. On a multi-turn reviewer that is a cost decision as much as a security one, which is the sort of overlap this project is looking for.

## Cost model in one paragraph

Token counts come from the SDK's own `Conversation.total_usage`, which reports `prompt_token_count`, `cached_content_token_count`, `candidates_token_count` and `thoughts_token_count` separately. That distinction matters: **cached input still bills, at a fraction of the input rate rather than free**, and **reasoning tokens bill at the output rate**. A cost figure that ignores either is wrong in a direction that flatters the tool. Full detail, including the second independent source used to check the arithmetic, is in [`docs/cost-tracking.md`](docs/cost-tracking.md).

## Prior art

**Two Antigravity SDK reviewers already exist, and this project starts from them.** Full notes in [`docs/prior-art.md`](docs/prior-art.md).

- [`rsamborski/run-agy-sdk`](https://github.com/rsamborski/run-agy-sdk) — a composite Action running the SDK for reviews. Source of the GitHub-MCP posting path and the deny-by-default policy model used here.
- [Google codelab: *Supercharge Code Quality*](https://codelabs.developers.google.com/agy-cli-sdk-code-review) — interactive CLI review plus an automated SDK reviewer. Source of `response_schema`, `skills_paths` for repository rules, and hooks as a second enforcement layer.

Also relevant:

- [`anthropics/claude-code-action`](https://github.com/anthropics/claude-code-action) — the pull-context design this follows. Its prompt carries a file list and the model gets `Glob`, `Grep`, `LS` and `Read`.
- [`derailed-dash/gemini-review-action`](https://github.com/derailed-dash/gemini-review-action) — a push-context reviewer on Gemini. Cheap and effective on ordinary PRs.
- [`google-github-actions/run-gemini-cli`](https://github.com/google-github-actions/run-gemini-cli) — official Google action wrapping the Gemini CLI, with a PR-review workflow.

**What is actually new here is narrow: the money.** The SDK already gives you token usage (`Conversation.total_usage`), budget limits (`BudgetConfig`), tracing, skills and policies. Neither published reviewer converts any of it into currency. `run-agy-sdk` declares a `stats` output for "token expenditures" and ships `f.write("stats={}\n")  # placeholder`; the codelab does not raise the subject. Both authenticate with an API key secret rather than Workload Identity Federation.

So this contributes three things: **pricing** (a rate table that gets cached input and reasoning tokens right), a **dollar-denominated ceiling** on top of the SDK's token limits, and **WIF** so spend attributes to a project by construction. The reviewing, the enforcement and the accounting are all borrowed, with thanks.

It was four. **Per-PR reconciliation against the billing export is struck**, because the SDK exposes no way to attach a billing label to a generation request — verified against `0.1.12`, not assumed. Spend attributes to a *project*, so reconciliation survives at project level and per-PR figures remain self-reported by Source 1. That is a weaker claim than this README made a day ago, and it is the accurate one.

**If per-PR cost visibility does not matter to you, use one of those instead.** They work today and are simpler.

## Contributing

Design feedback is welcome while this is at the planning stage — open an issue. See [`docs/roadmap.md`](docs/roadmap.md) for what is and is not in scope.

## Licence

Apache 2.0. See [`LICENSE`](LICENSE).
