# Prior art

Two working Antigravity SDK code reviewers already exist. This project starts from them rather than beside them, and the honest summary is that **they solve the reviewing and this project's contribution is the money**.

## `rsamborski/run-agy-sdk`

[github.com/rsamborski/run-agy-sdk](https://github.com/rsamborski/run-agy-sdk) — a composite GitHub Action running the SDK for reviews and general goal-driven tasks. Apache 2.0.

Worth adopting:

- **GitHub MCP server for all GitHub interaction** — `ghcr.io/github/github-mcp-server`, pinned, with an explicit `enabled_tools` allowlist. No GitHub API code to write or maintain, and the allowlist is a security boundary in its own right.
- **Deny-by-default policies** — `policy.deny_all()`, then `policy.allow(github_mcp)`, `policy.allow("view_file")`, `policy.allow("find_file")`.
- **Mode-dependent policy.** Automated review paths deny shell execution outright; only interactive goal mode relaxes it, and then behind a `trust-workspace` flag that defaults to false.
- **TOML command definitions** under `.github/commands/`, with environment interpolation, so the reviewer prompt is configuration rather than code.
- **Directory-traversal check on command names** before opening a file built from user input.
- `workspaces=[os.getcwd()]` to scope what the agent can reach.

Where this project differs:

- It authenticates with `GEMINI_API_KEY` as a repository secret. This project uses Workload Identity Federation, so there is no long-lived credential and inference bills to a chosen project.
- **Its `action.yml` advertises a `stats` output described as "token expenditures", and the implementation is a placeholder** — `f.write("stats={}\n")`. That gap is this project's entire premise, and finding it stated so plainly is the strongest evidence that per-PR cost is a real hole rather than an imagined one.

## Google codelab: *Supercharge Code Quality*

[codelabs.developers.google.com/agy-cli-sdk-code-review](https://codelabs.developers.google.com/agy-cli-sdk-code-review) — eight steps, covering interactive review with the CLI and an automated reviewer with the SDK, against a deliberately vulnerable sample application.

Worth adopting:

- **`response_schema=ReviewResult`** for typed, structured findings.
- **`skills_paths`** to supply a `code-review-and-quality` Agent Skill. This is the supported mechanism for repository-specific rules, and it is better than inventing a convention.
- **Verified read-only policy set**: `view_file`, `list_directory`, `search_directory`, `find_file`, `run_command`, `finish`.
- **Hooks as a second enforcement layer** — `log_tool_results` for auditing and `enforce_safe_tools` to reject any `run_command` that is not a `git` invocation. Policies gate which tools run; hooks gate what arguments they run with. Both are needed.
- **Dual authentication** in the agent itself: `GEMINI_API_KEY` when present, otherwise `vertex=True` with ADC. This is the single most useful confirmation for this project, because it means the Vertex path is supported by design rather than something to be forced.

Where this project differs:

- Its **workflow** still uses an API key secret, and posts results by writing `code_review.md` and having `actions/github-script` create a comment. So the ADC path exists in the agent but is exercised nowhere in CI.
- **No token or cost tracking of any kind.**

## The SDK's own `examples/` tree

Read this before writing anything. A search of public GitHub finds essentially no third-party SDK usage beyond the two reviewers above, but the SDK ships 25 runnable examples that cover more than either of them uses.

Directly relevant:

- **`budget_limits.py`** — `BudgetConfig` caps model calls, tool calls, and net uncached input / output / total tokens, stopping the session with a typed `StopReason`. **This removes the need for a custom budget hook**, which an earlier draft of this project proposed.
- **`observability.py`** — reads `conversation.total_usage` and prints prompt, output and thinking tokens. The usage primitive is demonstrated, just never priced.
- **`observability_otel.py`** — OpenTelemetry tracing via `google.antigravity.utils.otel`, including subagents. A better substrate for run analysis than bespoke logging.
- **`agent_skills.py`** — `skills_paths` in practice. Notably it prompts the agent with *"What available skills do you have?"*, which reads as **discovery rather than unconditional injection**.
- **`policies.py`**, **`hooks.py`**, **`human_in_the_loop.py`** — the safety model.
- **`structured_output.py`**, **`custom_tools.py`**, **`mcp_tools.py`**, **`subagents.py`**, **`slash_commands.py`**, **`persona_config.py`**, **`triggers.py`**.

There is also an official `skills/google-antigravity-sdk/` skill in the repository, with `references/safety_policies.md` among others — worth loading into any agent working on this project.

## What this project adds

Neither example measures what a review costs. One advertises the capability and ships a placeholder; the other does not raise the subject. So the contribution here is narrow and specific:

1. **Money.** Nothing in the SDK or either reviewer converts tokens into currency. There is no rate table, no dollar figure, and no dollar-denominated ceiling. Pricing it correctly is not trivial: cached input bills at a fraction rather than free, reasoning tokens bill at the output rate, and introductory rates expire.
2. **A dollar ceiling**, by translating `max_cost_usd` into `BudgetConfig`'s token limits. The enforcement is the SDK's; the unit conversion is ours. A token budget is not portable across models, and money is what people actually budget in.
3. **Workload Identity Federation in CI**, so there is no API key anywhere and spend attributes to a project by construction. Both reviewers use an API key secret.
4. **Reconciliation** against the Cloud Billing export, so the reported figure is checked rather than trusted.

Everything else — the policy model, the MCP posting path, skills, hooks, budget enforcement, usage accounting, tracing — is borrowed, with thanks.

**This list has shrunk twice**, both times from reading source rather than documentation. That is the right direction for it to move.

## A note on the honest conclusion

If per-PR cost visibility does not matter to you, **use one of the two above and skip this project.** They are working, published, and simpler. This exists because "what did that cost" and "stop at this ceiling" are hard questions to answer once an agentic reviewer is running across many repositories, and because a tool whose spend nobody can explain tends not to survive its first review of spend.
