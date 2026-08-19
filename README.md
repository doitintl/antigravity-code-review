# antigravity-code-review

An AI pull request reviewer built on the [Google Antigravity SDK](https://github.com/google-antigravity/antigravity-sdk-python), with **per-PR cost tracking and per-PR cost limits** as first-class features.

> **Status: design stage.** This repository currently contains the plan, not an implementation. See [`docs/design.md`](docs/design.md) for the architecture and [`docs/cost-tracking.md`](docs/cost-tracking.md) for the cost model. Milestones are in [`docs/roadmap.md`](docs/roadmap.md).

## Why another PR reviewer

Most AI reviewers **push** context: they decide up front what the model should see, pack the diff plus a slice of the repository into one prompt, and make a single call. That is cheap and simple, and it has two structural problems.

**It has to guess right.** A finding that requires reading a file *outside* the diff is only reachable if the up-front guess happened to include that file.

**It has a hard ceiling.** Everything goes into one request, so a single large generated file — an OpenAPI spec, a bundled schema, a snapshot — can exhaust the model's input window and the review fails outright rather than degrading.

This project **pulls** context instead. The prompt carries the PR metadata and a *list* of changed files. The agent then reads, greps and lists its way to what it actually needs, one call at a time.

The trade-off is real and is not hidden here: pulling means many model calls, so it costs more per review than a single-shot reviewer. That is precisely why cost tracking is a headline feature rather than an afterthought.

## What makes this different

**You will know what every review cost.** Each run reports input, cached, output and reasoning tokens separately, prices them, and writes a machine-readable artifact. Costs roll up per PR, per repository, and per month.

**You can cap it.** A pre-turn hook checks cumulative spend before each step and stops the run when it exceeds the configured ceiling, posting what it has so far. A budget you can only observe is not a budget.

**No API keys.** Authentication uses Workload Identity Federation to Vertex AI, so there is no long-lived credential in any repository secret, and inference is billed to the Google Cloud project you point it at.

**Read-only by default.** The agent is configured with an explicit tool allowlist. It can read the repository and post review comments. It cannot write files or run shell commands.

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
from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig
from google.antigravity.hooks.policy import deny, allow

config = LocalAgentConfig(
    vertex=True,
    project=os.environ["GOOGLE_CLOUD_PROJECT"],
    location=os.environ["GOOGLE_CLOUD_LOCATION"],
    system_instructions=REVIEWER_INSTRUCTIONS,
    capabilities=CapabilitiesConfig(),
    policies=[
        deny("*"),            # nothing unless named below
        allow("view_file"),
        allow("grep_search"),
        allow("list_directory"),
    ],
    tools=[post_inline_comment, post_summary],
    hooks=[budget_guard],     # stops the run at the cost ceiling
)
```

Tool names above are illustrative and are pinned against the SDK during the first milestone.

## Cost model in one paragraph

Token counts come from the SDK's own `Conversation.total_usage`, which reports `prompt_token_count`, `cached_content_token_count`, `candidates_token_count` and `thoughts_token_count` separately. That distinction matters: **cached input still bills, at a fraction of the input rate rather than free**, and **reasoning tokens bill at the output rate**. A cost figure that ignores either is wrong in a direction that flatters the tool. Full detail, including the second independent source used to check the arithmetic, is in [`docs/cost-tracking.md`](docs/cost-tracking.md).

## Prior art

- [`anthropics/claude-code-action`](https://github.com/anthropics/claude-code-action) — the pull-context design this follows. Its prompt carries a file list and the model is given `Glob`, `Grep`, `LS` and `Read`.
- [`derailed-dash/gemini-review-action`](https://github.com/derailed-dash/gemini-review-action) — a push-context reviewer on Gemini. Cheap and effective on ordinary PRs.
- [`google-github-actions/run-gemini-cli`](https://github.com/google-github-actions/run-gemini-cli) — official Google action wrapping the Gemini CLI, including a PR-review workflow.

If an off-the-shelf action meets your needs, use it. The case for this project is the combination of pull-context reviewing, an enforceable per-PR budget, and cost attribution good enough to defend in a spending review.

## Contributing

Design feedback is welcome while this is at the planning stage — open an issue. See [`docs/roadmap.md`](docs/roadmap.md) for what is and is not in scope.

## Licence

Apache 2.0. See [`LICENSE`](LICENSE).
