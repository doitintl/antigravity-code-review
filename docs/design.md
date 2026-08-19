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
      └── budget_guard hook                          ← pre-turn cost check
      │
      ▼
   PR review posted   +   review-cost.json artifact
```

### Components

**Collector.** Reads the PR from the GitHub API and produces the prompt seed: title, body, base and head refs, and one line per changed file (`path`, change type, `+adds/-dels`, blob SHA). **No file contents and no diff hunks.** Keeping the diff out is what stops a large file from mattering; the agent fetches hunks through a tool when it wants them.

**Agent.** An `Agent` from the SDK, configured with `vertex=True` and ADC. Read-only by policy, using the tool names the SDK actually exposes:

```python
review_policies = [
    policy.deny_all(),
    policy.allow("view_file"),
    policy.allow("list_directory"),
    policy.allow("search_directory"),
    policy.allow("find_file"),
    policy.allow("finish"),
]
```

The SDK's `Agent` is read-only by default; the explicit deny-all-then-allow is belt and braces, and it is auditable in a way a default is not.

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

**Budget guard.** A pre-turn hook, described in [`cost-tracking.md`](cost-tracking.md).

### Where reporting and the budget guard conflict

A single structured response only exists at the end, so a run stopped at its cost ceiling produces **nothing at all**. Incremental posting through MCP survives a stop, but is harder to validate and can leave a half-finished review on the PR.

**Leaning:** MCP with incremental posting, plus a stop message that makes the partial state explicit. To be settled with evidence in M1 rather than by preference. If structured output wins instead, the budget guard must post an explicit "stopped, no findings" comment rather than failing silently.

## Guardrails carried over from the push-based design

Some hard-won limits still apply, because the failure mode moves rather than disappearing. In a pull design the model chooses what to read, so a single tool call can still pull a 3 MB file into context.

**Cap file reads inside the tool.** `view_file` truncates beyond a configurable byte limit (default 128 KB, roughly 32k tokens) and says so in the returned text:

```
[TRUNCATED: 'docs/openapi.json' is 2,947,014 bytes, showing the first 131,072.
The rest was NOT provided. Do not draw conclusions about the omitted portion.]
```

Truncation must be loud. A silently shortened file is worse than an absent one, because the model reasons confidently about content it cannot see and the reader of the review cannot tell.

**Cap by size, not by filename.** The obvious alternative is a denylist (`package-lock.json`, `*.lock`, and so on). Denylists only cover the generated files someone already imagined, and every repository has a different one: a snapshot, a bundled schema, a fixture, a vendored client. A byte cap covers the ones not invented yet.

**Prefer ranged reads.** `view_file(path, start_line, end_line)` lets the agent page through a large file deliberately instead of pulling it whole.

## Repository rules

Reviewers are far more useful when they know a repository's own invariants.

The SDK supports this directly through **Agent Skills**, via `skills_paths` on the config — the mechanism the Google codelab uses to supply its `code-review-and-quality` skill. Use that rather than inventing a parallel convention.

One caveat, learned from watching a similar mechanism in production: **if repository rules are reachable only through a discovery tool the agent may choose to call, it will often not call it.** The review then reflects generic knowledge while appearing to be repo-aware, which is worse than having no rules at all, because nobody can tell from the output. Whether `skills_paths` injects unconditionally or is discovered on demand decides this, and it is an explicit M4 check. Anything that must always apply belongs in `system_instructions`.

## Non-determinism and evaluation

An agentic reviewer will not produce identical output twice. Comparing it against anything, including its own previous version, needs a fixture-based evaluation: a set of PRs with known planted defects, scored on how many were found and how many findings were spurious.

This is scheduled early ([`roadmap.md`](roadmap.md), M5) rather than late, because without it every claim about quality is an anecdote. A related lesson worth stating: a plausible-sounding change (a reasoning budget, a stricter prompt) can measurably make results *worse*, and you will not know without a harness.

## Security posture

- **No long-lived credentials.** WIF exchanges the workflow's OIDC token for short-lived Google Cloud credentials. Nothing to rotate, nothing to leak.
- **Least privilege.** The service account needs only the Vertex AI user role.
- **No writes.** No shell, no file writes, no network beyond the model endpoint and the GitHub API used by the reporting tools.
- **Untrusted input.** PR content is data, not instructions. A PR that contains text addressed to the reviewer must not change its behaviour; this needs an explicit system instruction and an evaluation fixture, because the agent reads attacker-controllable content by design.
- **Fork PRs.** `pull_request` from a fork gets a read-only token and no access to identity federation. Handle deliberately: either skip, or use `pull_request_target` with a strict checkout of the base and no execution of PR code. **Do not** check out and run fork code with write permissions.
- **Supply chain.** The SDK ships a compiled runtime binary in its PyPI wheels, so the source repository alone is not sufficient to run it. Pin the version, and record that this is a weaker audit story than a pure-source dependency.

## Open questions

These are unresolved and are called out rather than assumed.

1. **Headless authentication in CI via WIF.** The SDK supports `vertex=True` with ADC, and the codelab's agent falls back to it when no API key is set. But **both published examples authenticate their workflow with an API key secret**, so the WIF path inside a GitHub Actions runner is demonstrated nowhere. Still M0's first task, though a smaller risk than it looked: the SDK side is supported, only the CI wiring is unproven.
2. **Whether `skills_paths` injects unconditionally or is discovered on demand.** Decides whether repository rules reliably reach the model. See "Repository rules" above.
3. **Cost versus a single-shot reviewer**, measured rather than assumed. Plausibly several times higher per review. Whether the extra findings justify it is an empirical question, and the answer may be "only on larger PRs".
4. **Latency.** Multi-turn agents are slower. If a review lands after a human has already merged, it buys nothing — which is the single most common way an AI reviewer becomes shelfware.
5. **Context caching.** Whether the SDK exposes explicit caching, and whether a stable system-instruction prefix makes it worthwhile.
