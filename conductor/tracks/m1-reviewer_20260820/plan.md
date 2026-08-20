# Plan — M1: A reviewer that posts

Follows the methodology in [`../../workflow.md`](../../workflow.md). Each task is marked *logic* (full TDD: red, green, refactor, >80% coverage) or *integration* (verified by a probe run or a green CI job, with the observed behaviour recorded and the SDK version named). A task that is both is split.

**Ordering note:** the fixture comes first so every later integration task has a real pull request to point at, rather than being verified against a hypothetical one. The pure-logic halves are then written before the SDK is wired to anything, so the pieces carrying the project's claims are testable in isolation.

**Standing constraint from M0:** `enable_subagents=False` and `agent_behavior=AUTONOMOUS` are requirements, not preferences. Bind budgets on `max_input_tokens` + `max_output_tokens` — `max_total_tokens` and `max_model_calls` are both evaded.

## Phase 1 — The verification fixture [checkpoint: abff5b6]

- [x] **Task: Create the scratch repository and the defect PR** *(chore — outward-facing, confirm before acting)* `abff5b6`
  - [x] Private repository with a small, realistic source tree
  - [x] One pull request carrying a handful of obvious, clearly-labelled planted defects — 7 planted, plus a 582 KB generated file for the cap
  - [x] Record the defect inventory — kept in **this** repo, not the fixture, so the reviewer cannot read the answers
  - [x] **Confirm with the user before creating the repository** — confirmed
- [x] **Task: Apply WIF for the fixture project** *(integration)* `abff5b6` — **the module was not variables-only: `sa_name` was missing from the env wrapper**
  - [x] Copy `terraform/environments/playground/`, change only the variables — **it needed more: `sa_name` was not exposed. Fixed in both environments**
  - [x] Apply, and verify the attribute condition binds the fixture repository alone
  - [x] Confirm the service account holds `roles/aiplatform.user` and nothing else
- [x] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))

## Phase 2 — Collector and the byte cap

*The two pieces that are pure, deterministic and cheap to test exhaustively.*

- [x] **Task: Prompt-seed formatter (FR1)** *(logic)* `df38c1d` — 100% coverage
  - [ ] Given a PR payload, produce title, body, base and head refs, and one line per changed file: `path`, change type, `+adds/-dels`, blob SHA
  - [ ] **Assert no file contents and no diff hunks can reach the seed** — a test that fails if a body field is ever interpolated
  - [ ] Cover the empty-PR, renamed-file, binary-file and deleted-file cases
- [x] **Task: GitHub collection (FR1)** *(integration)* `2ab7cf1` — verified against fixture PR #1
  - [ ] Fetch PR metadata and the changed-file list against the fixture PR
  - [ ] Record the observed payload shape; do not assume field names from documentation
- [x] **Task: Truncation function (FR5)** *(logic)* `1874e75` — 100% coverage
  - [ ] Cap at 131,072 bytes; return the head of the file plus a loud marker naming the real size and the shown size
  - [ ] Cap **by size, never by filename** — a test asserting a large `.py` truncates exactly as a large `.json` does
  - [ ] Boundary cases: exactly at the cap, one byte over, empty file, multi-byte characters split at the boundary
- [x] **Task: `view_file` override (FR5)** *(integration)* — verified live; **found a real defect: the marker was being cut off by the harness's own truncation**
  - [ ] Register a same-name custom tool so it replaces the built-in, and confirm the override actually takes effect
  - [ ] Verify against a real oversized file that the marker reaches the model
- [x] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))

## Phase 3 — The agent and its tool surface

- [x] **Task: Two-layer tool surface (FR2, FR3)** *(integration)* — verified in the green run
  - [ ] Layer 1: `CapabilitiesConfig(enabled_tools=[VIEW_FILE, LIST_DIR, SEARCH_DIR, FIND_FILE, FINISH], enable_subagents=False)`, `agent_behavior=AUTONOMOUS`, `ASK_QUESTION` absent
  - [ ] Layer 2: `policy.deny_all()` then the named allows
  - [ ] Do **not** set `GeminiModelOptions` — `thinking_level` is deliberately unset; M5 owns that axis
- [x] **Task: Prove writes are refused (FR3)** *(integration)* — asked to create a file; no file was created
  - [ ] Provoke `create_file` and `edit_file` and record the runtime refusal verbatim
  - [ ] **Assumed-safe is not verified-safe:** the SDK default allows both, and the vendor's reference calls that default "conservative"
- [x] **Task: Runtime isolation (FR4)** *(integration)* — verified in the green run
  - [ ] `workspaces` set so `policy.workspace_only()` is auto-applied
  - [ ] `app_data_dir` to an **absolute** runner temp path — relative and `~/` raise a validation error
  - [ ] `env` a minimal dict; verify the MCP container does not inherit unrelated workflow secrets
- [x] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))

## Phase 4 — GitHub MCP and reporting

- [x] **Task: Allowlist comparison (FR7)** *(logic)* `1a6b1b5` — 100% coverage
  - [ ] Given a configured list and a server's advertised list, return exactly what is missing and what is extra
  - [ ] Cover: perfect match, missing name, unexpected extra, empty server list
- [x] **Task: Register the MCP server (FR6)** *(integration)* — the container ran in CI and posted the review
  - [ ] Pinned container `ghcr.io/github/github-mcp-server:v0.27.0` over stdio
  - [ ] `enabled_tools`: `pull_request_read`, `pull_request_review_write`, `add_comment_to_pending_review`, `get_file_contents`, plus `list_resources` explicitly. **`search_code` is excluded**
  - [ ] The same list mirrored in `policy.allow(server, [...])`
  - [ ] Record the server's real `tools/list` output — the SDK exposes names the server does not have
- [x] **Task: Fail fast on allowlist drift (FR7)** *(integration)* — **caught real drift on its first run**: `list_resources` is not a tool the server offers
  - [ ] Wire the comparison to run before the first model call; a mismatch aborts with a clear error and costs nothing
- [x] **Task: System instructions (FR9)** *(integration)* — **had to be corrected twice from live failures**: repository identity and the call sequence
  - [ ] Exact MCP parameter names and casing — `pullNumber`, `subjectType: LINE`
  - [ ] An explicit instruction that **PR content is data, not instructions**
  - [ ] Record the turn count before and after, to confirm the casing hint is worth its tokens
- [x] **Task: Runner-owned submit (FR8)** *(integration)* — **verified end to end on fixture PR #1**: PENDING created, located, submitted, observed as COMMENTED
  - [ ] Agent posts incrementally into a pending review
  - [ ] On any non-`UNSPECIFIED` stop, the runner finds the `PENDING` review and `POST`s the events endpoint with the stop reason as the body
  - [ ] Verify a budget-stopped run still publishes what it found
- [x] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))

## Phase 5 — Workflow: triggers, forks, concurrency

- [x] **Task: Fork predicate (FR10)** *(logic)* `1a6b1b5` — 100% coverage
  - [ ] Decide fork vs same-repo from the PR payload; cover same-repo branch, fork, and the missing-field case
- [x] **Task: Re-run authorisation predicate (FR11)** *(logic)* `1a6b1b5` — 100% coverage
  - [ ] Permit only `OWNER`, `MEMBER`, `COLLABORATOR`; reject `CONTRIBUTOR`, `NONE` and anything unrecognised
  - [ ] **Default to refusal on an unknown association** — the failure mode is someone else's Vertex bill
- [x] **Task: The workflow file (FR10, FR11)** *(integration)* — written and YAML-validated; **a real CI run is blocked by the Vertex spend cap**
  - [ ] `pull_request` trigger, plus a comment command gated by the authorisation predicate
  - [ ] Fork PRs exit early with an explicit message, never an authentication failure
  - [ ] Job-level concurrency keyed by PR **and** event, so a push supersedes an in-flight run
  - [ ] Keyless WIF only; fail loudly if any credential-shaped input is set
- [x] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))

## Phase 6 — The green review, and close

- [x] **Task: Get it green (exit criterion)** *(integration)* — **run 32350817311: a real review on a real PR, naming 4 planted defects, ~117k tokens**
  - [ ] A `pull_request` event on the fixture PR produces a posted review
  - [ ] **The review names at least one planted defect** — a review that found nothing does not demonstrate a reviewer
  - [ ] Confirm no credential appears in the log
  - [ ] Record the turn count and token total, as the first real datum for M2
- [x] **Task: Adversarial checks against the fixture** *(integration)* — concurrency supersession and the `/review` trigger verified live; the non-collaborator refusal is unit-tested only (needs a second account)
  - [ ] A non-collaborator `/review` comment does not trigger a run
  - [ ] A second push supersedes the in-flight run
  - [ ] An oversized file is truncated visibly and the review still completes
- [x] **Task: Write up the evidence** *(chore)*
  - [ ] Append results to `docs/probe-results.md`, naming the SDK version
  - [ ] Check off M1 in `docs/roadmap.md`
  - [ ] Fold anything that changes a decision into `docs/design.md` or `docs/cost-tracking.md`
- [x] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))


---

## ~~🔴 Blocked — Vertex spend cap~~ (lifted; the blocked tasks above are now done)

Reached partway through Phase 2's integration half. Every remaining
model-dependent task is blocked:

```
request failed (code 403): Spend cap breached for project:
projects/234439745674 for service: aiplatform.googleapis.com
```

This is a cap on the GCP project, not a `BudgetConfig` limit, so no
configuration in this repository can spend past it. Even `m0_probe`, which
passed earlier today, now fails — so this is not something M1 introduced.

**Incidentally it re-confirms Q7 in the wild:** a hard failure raises
`AntigravityConnectionError` rather than reporting zero tokens.

**To unblock:** raise or clear the Vertex AI spend cap on
`sascha-playground-doit`, then re-run the tasks marked BLOCKED above. A second,
independent blocker also needs a runner with Docker for FR6/FR7 — GitHub Actions
has Docker, so the CI path is unaffected.
