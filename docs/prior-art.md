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

Read this before writing anything. A search of public GitHub finds essentially no third-party SDK usage beyond the two reviewers above, but the source repository carries **32 runnable examples** — 23 under `examples/getting_started/` and 9 under `examples/deep_dives/` — covering more than either reviewer uses.

Counted from the git tree at tag `v0.1.12`, `.py` files only:

| path | runnable examples |
|---|---|
| `examples/getting_started/` | 23 |
| `examples/deep_dives/` | 9 |
| `examples/resources/mcp_server.py` | 1 helper, not an example |
| **total `.py`** | **33** |
| all files including 3 READMEs and 3 media assets | 39 |

This figure has now been wrong twice. The original **25** was low; the **34** that replaced it counted each directory's `README.md` as an example (24 + 10). Reproduce the count rather than quoting it:

```bash
gh api "repos/google-antigravity/antigravity-sdk-python/git/trees/v0.1.12?recursive=1" \
  --jq '.tree[] | select(.path|startswith("examples/")) | select(.path|endswith(".py")) | .path'
```

⚠️ **They are not shipped in the wheel.** Verified against `0.1.12`: the installed package has no `examples/` directory. Fetch them from `google-antigravity/antigravity-sdk-python` at the tag matching the pinned version — an example from `main` would silently exercise a different SDK than the one pinned here.

Directly relevant:

- **`budget_limits.py`** — `BudgetConfig` caps model calls, tool calls, and net uncached input / output / total tokens, stopping the session with a typed `StopReason`. **This removes the need for a custom budget hook**, which an earlier draft of this project proposed.
- **`observability.py`** — reads `conversation.total_usage` and prints prompt, output and thinking tokens. The usage primitive is demonstrated, just never priced.
- **`observability_otel.py`** — OpenTelemetry tracing via `google.antigravity.utils.otel`, including subagents. A better substrate for run analysis than bespoke logging.
- **`agent_skills.py`** — `skills_paths` in practice. Notably it prompts the agent with *"What available skills do you have?"*, which reads as **discovery rather than unconditional injection**.
- **`policies.py`**, **`hooks.py`**, **`human_in_the_loop.py`** — the safety model.
- **`structured_output.py`**, **`custom_tools.py`**, **`mcp_tools.py`**, **`subagents.py`**, **`slash_commands.py`**, **`persona_config.py`**, **`triggers.py`**.

There is also an official `skills/google-antigravity-sdk/` skill in the repository, with `references/safety_policies.md` among others — worth loading into any agent working on this project.

## The official `google-antigravity-sdk` agent skill

Ships with the SDK (`skills/google-antigravity-sdk/`) and is also distributable as an agent skill. Load it before writing code. Its `references/` are more precise than the README, and in one case they **contradict** it: the README says the `Agent` runs *"in read-only mode by default"*, while `references/built_in_tools.md` says all built-in tools are enabled by default and only `run_command` is denied. The reference is the one to trust for a security decision, and the disagreement is itself the argument for never inheriting a default for a safety property.

Most useful pages: `safety_policies.md` (the nine-level priority model), `built_in_tools.md` (canonical tool names and default state), `observability.md` (usage tracking, and the warning that failed runs may report zero tokens), `agent_configuration.md` (the rule against assuming model identifiers).


## Anthropic's `code-review` plugin

[`plugins/code-review/commands/code-review.md`](https://github.com/anthropics/claude-code/blob/main/plugins/code-review/commands/code-review.md). Read after our reviewer failed on `doitbse/draft#538`. It is a prompt, not a codebase, which makes it unusually legible — and it independently confirms two things this project worked out the hard way, then supplies several it had not.

### It reads the diff

Its `allowed-tools` line grants `Bash(gh pr diff:*)`. **The review is anchored on the diff, not on file contents.** Our reviewer opens whole files from a changed-file list, which is how it came to read the wrong 128 KB of a 2.9 MB generated file. Independent confirmation of the M2.5 finding.

### It forbids exploration

> All tools are functional and will work without error. Do not test tools or make exploratory calls. **Every tool call should have a clear purpose.**

Ours made **87 tool calls and found nothing**. This instruction is aimed exactly at that failure, and costs nothing to adopt.

### It sets a precision bar, and an explicit list of things not to flag

The bar is narrow and testable — code that will not compile, code that is wrong regardless of input, or a convention violation you can quote. And then, unusually, six categories to *suppress*: pre-existing issues, anything a linter catches, pedantic nitpicks, general code-quality concerns, things that look like bugs but are correct, and issues explicitly silenced in code.

> **If you are not certain an issue is real, do not flag it. False positives erode trust and waste reviewer time.**

Our system instruction says "report real defects… do not report formatting preferences", which is the same intent at a fraction of the specificity. M1's non-determinism measurement found the marginal finding dropping off a short list; a precision bar this explicit is a better instrument than a curation instruction.

### It validates every finding before posting

Step 5 launches a subagent **per issue** whose only job is to confirm the issue is real, and step 6 discards everything unvalidated. Generation and verification are separated, and only verified findings reach the pull request.

### It gates before spending

A cheap first agent skips closed, draft, trivial, and already-reviewed pull requests. Our workflow gates on fork and authorisation but happily spends on a one-line typo fix.

### What we cannot copy, and why

The design leans on **parallel subagents** — four reviewers with different mandates, then one validator per finding, with models tiered haiku/sonnet/opus by task.

**That is the capability M0 found broken.** Subagents fail outright on Vertex (`PlatformClient is nil`), and their tokens escape `BudgetConfig` entirely, so even working they would break the cost ceiling M2 and M3 are built on. Model tiering is also unavailable to us for a smaller reason: M2 pins one model so the rate table has a key.

So the *shape* does not transfer. The **separation of generate from verify** does — as a second pass in one session rather than a fan-out.

### What to adopt

1. **Anchor on the diff.** Already possible: `pull_request_read(method="get_diff")` is in our allowlist and unused.
2. **"Every tool call should have a clear purpose. Do not make exploratory calls."** Verbatim.
3. **An explicit do-not-flag list**, and a precision bar stated as "if you are not certain, do not flag it".
4. **A verification pass** over the findings before publishing, in-session.
5. **Gate on triviality**, not only on forks and permissions.
6. **One comment per issue.** Ours posted duplicates when a run failed mid-way.
7. **Permalinks with the full SHA** and a line of context either side, which is how their inline comments stay readable.

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
