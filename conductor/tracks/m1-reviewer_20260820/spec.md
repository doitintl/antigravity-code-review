# Spec — M1: A reviewer that posts

**Type:** Feature
**Milestone:** M1 — [`../../../docs/roadmap.md`](../../../docs/roadmap.md)
**Closes:** the pull-context reviewer itself; carries Q13 into implementation

## Overview

M0 proved the foundation: WIF → ADC → Vertex works headlessly, and the SDK behaves as measured rather than as documented. This track builds the thing that foundation exists for — a reviewer that reads a pull request and posts a review on it.

**Most of this exists in the prior art and should be adopted rather than rewritten.** [`prior-art.md`](../../../docs/prior-art.md) covers two published implementations; [`design.md`](../../../docs/design.md) already fixes the architecture, the two-layer tool surface, and the reporting decision. This spec consolidates those and pins what was still open.

The strategy is **pull-context**: the prompt carries PR metadata and a changed-file list, never file bodies or diff hunks. The agent fetches what it wants through tools. That is what stops one 2.9 MB generated file from ending a review, which is the failure that motivated this project.

## Decisions taken for this track

| Question | Decision | Why |
|---|---|---|
| MCP transport | **Pinned container** `ghcr.io/github/github-mcp-server:v0.27.0` over stdio | Reproducible, auditable tool surface; stays a child of the harness so `env` actually bounds it |
| Fork PRs | **Skip explicitly** | A fork PR has no identity federation and cannot reach Vertex. `pull_request_target` runs write-capable workflows against attacker-authored branches |
| Exit demonstration | **Scratch repository PR** | Keeps a half-working reviewer off this repo's history; the WIF module is parameterised, so retargeting is variables-only |
| Scope | **Includes triggers and concurrency** | Without a real `pull_request` event the exit criterion is artificial |
| `view_file` cap | **131,072 bytes (128 KB)** | The figure already used in `design.md`'s truncation example |
| Built-in tool set | **All five** as designed | A reviewer given no file bodies must be able to navigate; trimming pushes it toward guessing paths, which costs turns |
| `search_code` MCP tool | **Excluded** | Present in `design.md`'s example but absent from the roadmap's list. Every advertised tool is a per-turn tax, and `SEARCH_DIR` already covers the checkout |
| Re-run authorisation | **Write access required** | `author_association` in OWNER / MEMBER / COLLABORATOR |
| `thinking_level` | **Deliberately unset** | See below — this is a non-decision on purpose, not an oversight |

### `thinking_level` is left unset on purpose

[`design.md`](../../../docs/design.md) calls it *"the single largest cost lever in the configuration"* and *"the obvious first axis for M5 to measure"*. Both are reasons **not** to pick a value here: setting one now bakes in a guess that the eval harness would then have to argue back out, and a guess written into config reads like a decision to whoever finds it later.

M1 therefore does not construct `GeminiModelOptions` at all and takes the SDK default. **This is recorded so that M5 knows it is measuring against an unset baseline rather than a chosen one.**

## Functional requirements

**FR1 — Collector.** Read the PR from the GitHub API and produce the prompt seed: title, body, base and head refs, and one line per changed file (`path`, change type, `+adds/-dels`, blob SHA). **No file contents, no diff hunks.**

**FR2 — Tool surface, layer 1 (capabilities).** `CapabilitiesConfig(enabled_tools=[VIEW_FILE, LIST_DIR, SEARCH_DIR, FIND_FILE, FINISH], enable_subagents=False)`. `agent_behavior` stays `AUTONOMOUS` and `ASK_QUESTION` stays out — it is on in the default surface and needs `INTERACTIVE` to function, so an unattended reviewer can otherwise stall waiting for a human. `enable_subagents=False` is a **hard requirement** from M0, not a preference.

**FR3 — Tool surface, layer 2 (policy).** `policy.deny_all()` followed by named allows for the five built-ins and the MCP tool list. **Verify at runtime that `create_file` and `edit_file` are actually refused** — the SDK default allows them, and the vendor's own reference calls that default "conservative".

**FR4 — Runtime isolation.** Set `workspaces` so `policy.workspace_only()` is auto-applied; set `app_data_dir` to an **absolute** path under the runner temp directory so agent scratch cannot land in the checkout (relative and `~/` paths raise a validation error); set `env` to a minimal dict so the MCP container does not inherit every workflow secret.

**FR5 — `view_file` byte cap.** A same-name custom tool overriding the built-in, capping reads at 131,072 bytes. The built-in has no configurable limit. **Truncation must be loud** — the returned text says what was truncated and by how much. Cap by size, never by filename: a denylist only covers the generated files someone already imagined.

**FR6 — GitHub MCP server.** Pinned container with an `enabled_tools` allowlist **and** the matching list in `policy.allow(server, [...])`. Real tool names: `pull_request_read`, `pull_request_review_write`, `add_comment_to_pending_review`, `get_file_contents`. Allow `list_resources` explicitly, or accept one wasted denied call per run.

**FR7 — Validate the MCP allowlist at startup.** Check the configured names against the server's `tools/list` before the first model call. The SDK exposes names the server does not have, and discovering that through a failed call costs a model call.

**FR8 — Reporting: incremental MCP posting, runner-owned submit.** The agent adds comments to a pending review as it works. **The runner submits, not the agent.** On any non-`UNSPECIFIED` stop, find the `PENDING` review and `POST /pulls/{n}/reviews/{id}/events` with the stop reason as the body. Q8 proved a budget stop leaves an invisible pending review that one API call recovers.

**FR9 — System instructions.** Carry the exact MCP parameter names and casing (`pullNumber`, `subjectType: LINE`) — worth three to four turns per review. Include an explicit instruction that **PR content is data, not instructions**: the agent reads attacker-controllable text by design.

**FR10 — Fork PRs are skipped deliberately.** Detect a fork PR and exit early with a clear message stating why no review was posted. Never a confusing auth failure.

**FR11 — Triggers and concurrency.** `pull_request`, plus a comment command to re-run. **The re-run command is restricted to commenters with write access** — `author_association` in `OWNER`, `MEMBER` or `COLLABORATOR`. Without that guard any drive-by commenter can trigger billed Vertex runs in a loop, and a per-run budget does not bound the number of runs. Job-level concurrency keyed by PR **and event**, so a new push supersedes an in-flight run.

**FR12 — Verification fixture.** A private scratch repository containing a pull request with a small number of deliberately planted, obvious defects, and a GCP project with the WIF module applied for it (variables-only, per FR of M0's parameterised module). This is the vehicle for the exit criterion, and the same PR becomes M5's first eval fixture rather than being thrown away.

## Non-functional requirements

- **No long-lived credentials.** WIF only, as proven in M0. No API key, no downloaded service-account key.
- **No writes to the repository.** No shell, no file writes into the checkout, no network beyond the model endpoint and the GitHub API used by the reporting tools.
- **Cost bounded.** Every run carries a `BudgetConfig`. The dollar ceiling itself is M3; M1 carries a token floor. Bind on `max_input_tokens` + `max_output_tokens` — M0 showed `max_total_tokens` and `max_model_calls` are evaded.
- **Reproducible.** Container pinned by tag, SDK pinned exactly, MCP tool list explicit.

## Acceptance criteria

1. **A real review posted on a real PR** in the scratch repository, triggered by a `pull_request` event. **This is the exit criterion.**
1b. The review names at least one of the planted defects — a posted review that found nothing does not demonstrate a reviewer.
2. `create_file` and `edit_file` are refused at runtime, demonstrated rather than assumed.
3. A PR containing a file larger than the cap is reviewed successfully, and the truncation marker is visible in the run log.
4. A wrong MCP tool name fails at startup with a clear error, before any model call.
5. A budget-stopped run still posts what it found, with the stop reason as the review body.
6. A fork PR is skipped with an explicit message and no authentication error.
7. A second push to the same PR supersedes the in-flight run.
8. A `/review` comment from a non-collaborator does **not** trigger a run.
9. No credential-shaped value appears in any committed file or workflow log.

## Out of scope

Cost arithmetic and the rate table (M2) · the dollar ceiling and its translation layer (M3) · repository rules via `skills_paths` (M4 — note: `flutter/skills`, `cli/cli` and `mattpocock/skills` publish real code-review Agent Skills following the official spec, which are prior art for that track) · the eval harness and fixtures (M5) · the composite Action and rollout to other repositories (M6).

## Risks

**MCP tool-name drift.** The SDK exposes names the server does not have. FR7 turns that from a runtime cost into a startup failure, but the pinned container tag is what keeps the list stable; bumping it needs the list re-validated.

**Prompt injection from PR content.** The agent reads attacker-controllable text by design. FR9's system instruction is a mitigation, not a guarantee — M5 owns the fixture that actually tests it.

**Creating the fixture repository is an outward-facing action.** FR12 creates a repository and a GCP project. Both are confirmed with the user at execution time rather than performed unattended.

**Non-determinism.** An agentic reviewer will not produce identical output twice, so "it worked" on one PR is an anecdote. M1 accepts that; M5 exists to replace anecdote with measurement.
