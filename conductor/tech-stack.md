# Technology Stack

Every version and behaviour below marked *verified* was measured against the installed package on 2026-08-19. See [`../docs/probe-results.md`](../docs/probe-results.md).

## Runtime

| | | |
|---|---|---|
| Language | **Python ≥ 3.10** | required by `google-antigravity`; *verified* from wheel metadata |
| Agent SDK | **`google-antigravity==0.1.12`** | pinned exactly. A 0.1.x SDK shipping a compiled runtime binary — expect churn, keep the used surface small |
| Dependencies | **uv + `pyproject.toml`** | lockfile by default; install speed is a visible per-run cost given a 32–38 MB wheel |
| CI runtime | **GitHub Actions, `ubuntu-latest`** | `manylinux_2_17_x86_64` wheel published; *verified* |

## Model and inference

| | | |
|---|---|---|
| Platform | **Vertex AI** (Gemini Enterprise Agent Platform) | billed to the project WIF authenticates into |
| Location | **`global`** | 🔴 *verified*: `us-central1` returns 404 for this model |
| Model | **`gemini-3.7-flash`**, pinned | the SDK's own default. Pinned because pricing requires knowing the rate and `UsageMetadata` does not report which model served a request |
| Service tier | **standard** | *verified*: every probe call reported `STANDARD`. `PRIORITY` and `FLEX` are opt-in and unpriced here |
| Auth | **Workload Identity Federation → ADC** | no long-lived credential anywhere. *Verified*: the SDK acquires ADC headlessly. The WIF exchange inside a runner is still unproven |

## Agent configuration

Two layers, in this order — the SDK's own guidance, not a preference:

- **`CapabilitiesConfig(enabled_tools=[...], enable_subagents=False)`** — an exclusive allowlist; tools not listed are stripped from the model's context entirely. *Verified*: cuts the per-turn prompt floor from 10,889 to 4,470 tokens.
- **`policy.deny_all()` plus named allows** — priority-based resolution, specific allow (3) outranks global wildcard deny (7). Kept on a **narrowed** argument: it is no longer needed to cover invisible built-in tools, because M0 showed there are none. It is still needed for **MCP tools**, which the server declares dynamically and which `enabled_tools` cannot constrain in advance.
- **`BudgetConfig`** — all five dials cumulative across the **root trajectory**, not the session; *verified* from source and by probe. There is no per-request guard, and **two dials are evaded**: `max_total_tokens` by subagent spend, `max_model_calls` by model-output retries. Bind a cost ceiling on `max_input_tokens` + `max_output_tokens`.
- **`RetryConfig(model_output_retry=...)`** — the default of 4 re-prompts at full context is a real cost, *measured* at 7.4x a clean turn. Since `max_model_calls` does not cover retries, `max_retries` is the only control over that spend.

## GitHub integration

**GitHub MCP server** — hosted at `api.githubcopilot.com/mcp/` (44 tools) or a pinned container. Tools used, *verified* by name: `pull_request_read`, `pull_request_review_write`, `add_comment_to_pending_review`, `get_file_contents`.

⚠️ `enabled_tools` on an MCP server is an **exposure filter, not a validator** — a wrong name is exposed to the model and fails at call time, costing a model call. Validate against `tools/list` at startup.

**Publication is runner-owned.** On any non-`UNSPECIFIED` stop reason the runner submits the orphaned `PENDING` review via `POST /pulls/{n}/reviews/{id}/events`. *Verified* working.

## Packaging

**Composite action** — sets up Python, installs the package, runs the reviewer. Matches `rsamborski/run-agy-sdk`; transparent, and pays install cost per run. Revisit a container action if install time becomes the latency problem.

## Quality tooling

| | |
|---|---|
| **pytest** | unit tests for the collector, rate table, budget translation and cost arithmetic — the pure-logic parts carrying the project's actual claims |
| **ruff** | lint and format in one fast tool |
| **mypy** | static typing; the SDK ships Pydantic models, so annotations carry real information |
| **Fixture eval harness** | Built at M5, in `src/antigravity_code_review/evalharness/`. Fixtures pinned by base and head SHA, defects classed and shown reachable, findings matched on **location** rather than wording, repeated runs, per-defect hit rates, cost beside recall, incomplete runs excluded from recall and still charged. Not a unit test — the thing that makes quality claims checkable at all |
| **Eval gates** | Four, run before any model call: reachability evidence, scorer validated against a reference review *including a paraphrase control*, how easily a finding could score by accident, and defect pairs location cannot separate. Spending money to produce a number the harness already knows it cannot trust is worse than spending nothing |

## Deliberately not used

- **Per-request billing labels.** No SDK surface exists; *verified*. Reconciliation is project-level only.
- **Subagents.** On by default; disabled explicitly. Whether their tokens roll into `total_usage` is unconfirmed, and an uncounted spender is exactly what this project claims to have eliminated.
- **`RetryConfig.benchmark()`.** Unbounded API retries — the opposite of what a cost-capped job wants.
- **Non-Gemini models, non-GitHub forges.** Focus, not principle.
