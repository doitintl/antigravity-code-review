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

## What this project adds

Neither example measures what a review costs. One advertises the capability and ships a placeholder; the other does not raise the subject. So the contribution here is narrow and specific:

1. **Per-PR cost reporting**, from `Conversation.total_usage`, pricing cached input and reasoning tokens correctly rather than ignoring them.
2. **An enforceable per-PR ceiling**, via a pre-turn hook that stops the run rather than merely reporting afterwards.
3. **Workload Identity Federation in CI**, so there is no API key anywhere and spend attributes to a project by construction.
4. **Reconciliation** against the Cloud Billing export, so the reported figure is checked rather than trusted.

Everything else — the policy model, the MCP posting path, skills for repository rules, hooks as a second layer — is borrowed, with thanks.

## A note on the honest conclusion

If per-PR cost visibility does not matter to you, **use one of the two above and skip this project.** They are working, published, and simpler. This exists because "what did that cost" and "stop at this ceiling" are hard questions to answer once an agentic reviewer is running across many repositories, and because a tool whose spend nobody can explain tends not to survive its first review of spend.
