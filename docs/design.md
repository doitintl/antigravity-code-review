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
      ├── view_file / grep_search / list_directory   ← the agent decides
      ├── post_inline_comment / post_summary          ← custom tools
      └── budget_guard hook                           ← pre-turn cost check
      │
      ▼
   PR review posted   +   review-cost.json artifact
```

### Components

**Collector.** Reads the PR from the GitHub API and produces the prompt seed: title, body, base and head refs, and one line per changed file (`path`, change type, `+adds/-dels`, blob SHA). **No file contents and no diff hunks.** Keeping the diff out is what stops a large file from mattering; the agent fetches hunks through a tool when it wants them.

**Agent.** An `Agent` from the SDK, configured with `vertex=True` and ADC. Read-only by policy:

```python
policies = [
    deny("*"),
    allow("view_file"),
    allow("grep_search"),
    allow("list_directory"),
]
```

The SDK's `Agent` is read-only by default; the explicit denylist-then-allowlist is belt and braces, and it is auditable in a way a default is not.

**Reporting tools.** Two custom Python callables registered as tools: `post_inline_comment(path, line, severity, body)` and `post_summary(body)`. Registering them as tools rather than parsing a structured blob at the end means findings can be emitted as the agent works, and a run that hits its budget ceiling still leaves what it found.

**Budget guard.** A pre-turn hook, described in [`cost-tracking.md`](cost-tracking.md).

### Why not simply parse a final JSON blob

A single structured response is easier to validate but discards everything when the run is cut short — by a budget stop, a timeout, or a transient failure. Emitting findings through tools makes partial results the normal case rather than a loss.

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

Reviewers are far more useful when they know a repository's own invariants. The plan is to load rules from a conventional path (for example `.github/review-rules.md`) and place them in the system instructions.

One caveat, learned from watching a similar mechanism in production: if rules are exposed as something the agent *may* look up, it will often decline to, and the review then silently reflects generic knowledge while appearing to be repo-aware. **Rules that must apply belong in the system instructions, not behind a tool call.**

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

1. **Headless authentication in CI.** ADC via WIF is documented for the SDK and is the intended path, but has not yet been exercised in a GitHub Actions runner here. This is M0's first task because everything else depends on it.
2. **Actual tool names and signatures** exposed by the SDK's capability set. The names used in this document are illustrative.
3. **Cost versus a single-shot reviewer**, measured rather than assumed. Plausibly several times higher per review. Whether the extra findings justify it is an empirical question, and the answer may be "only on larger PRs".
4. **Latency.** Multi-turn agents are slower. If a review lands after a human has already merged, it buys nothing — which is the single most common way an AI reviewer becomes shelfware.
5. **Context caching.** Whether the SDK exposes explicit caching, and whether a stable system-instruction prefix makes it worthwhile.
