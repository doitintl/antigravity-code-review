# Spec — M0: Prove the foundation

**Type:** Chore (infrastructure & verification)
**Milestone:** M0 — [`../../../docs/roadmap.md`](../../../docs/roadmap.md)
**Closes:** Q1, Q4, Q5

## Overview

Everything in this project assumes Workload Identity Federation → Application Default Credentials → Vertex works inside a GitHub Actions runner with no interactive step. Neither published Antigravity reviewer has demonstrated it — both authenticate with an API key secret.

The SDK half is already proven: ADC authenticated headlessly from a non-interactive process on the first probe attempt. The CI half is not, and everything else is built on top of it.

This track proves it, and closes the four remaining M0 verification items so the milestone leaves nothing behind.

## Rollout model

`sascha-playground-doit` while implementing. At rollout, **each GitHub repository authenticates into its own corresponding GCP project.**

This is not incidental. Q11 established that the SDK exposes no surface for per-request billing labels, so per-PR attribution in Cloud Billing is not reachable. One project per repository is what remains: it makes project-level attribution *equal* to per-repository attribution by construction. The Terraform must therefore be a parameterised module instantiated per repository, never a one-off with a project baked in.

## Functional requirements

**FR1 — Terraform WIF module.** A parameterised module at `terraform/wif/` provisioning: a workload identity pool, an OIDC provider for GitHub Actions, a service account, a pool→service-account binding scoped to a single repository, and `roles/aiplatform.user` on the target project. Inputs at minimum `project_id`, `github_owner`, `github_repo`. No project or repository hardcoded.

**FR2 — Attribute restriction.** The provider restricts token exchange to the named repository. A pool any repository can exchange against is a credential leak wearing a keyless costume.

**FR3 — CI workflow.** `.github/workflows/m0-foundation.yml`, triggered on `workflow_dispatch` and on push to this track's branch. Authenticates via `google-github-actions/auth` using WIF (no `credentials_json`), installs the pinned SDK, runs the probe, and fails loudly if any credential-shaped input is present.

**FR4 — Probe entrypoint.** One trivial agent call against Vertex with `vertex=True`, explicit `project`, `location="global"`, printing prompt / cached / candidates / thoughts / total tokens and `service_tier`.

**FR5 — Harness tool inventory.** Obtain the *registered* tool list from the harness rather than from the model, and determine what `manage_task` and `schedule` do — specifically whether either writes anything. Recorded in [`../../../docs/probe-results.md`](../../../docs/probe-results.md).

**FR6 — SDK example parity.** Run the SDK's own `budget_limits.py` and `observability.py` against Vertex; both are load-bearing for M2 and M3.

⚠️ **These do not ship in the wheel.** The installed package contains no `examples/` directory — verified against `0.1.12`. They live in the source repository at `google-antigravity/antigravity-sdk-python/examples/getting_started/`, which also holds 24 other examples, with 10 more under `deep_dives/` including `observability_otel.py`. Fetch them from a **tag matching the pinned version**, not from `main`: an example from a newer revision would silently test a different SDK than the one this project pins, which is the same class of error as an uncited rate.

This also corrects [`../../../docs/prior-art.md`](../../../docs/prior-art.md), which says "the SDK ships 25 runnable examples" — it does not ship them at all in the distributed artefact. 34 exist in source.

**FR7 — Q4, subagent roll-up.** A controlled run: identical task with and without delegation, comparing root `total_usage`, and whether subagent tokens count against `BudgetConfig`.

**FR8 — Q5, retry accounting.** Force a `response_schema` violation; determine whether model-output retries consume `max_model_calls` and appear in usage.

## Non-functional requirements

- **No long-lived credentials** anywhere — not in repository secrets, not in the workflow, not in Terraform state.
- **Least privilege:** the service account holds `roles/aiplatform.user` and nothing more.
- **Cost bounded:** every probe call carries a `BudgetConfig`; a full run stays under $0.50.
- **Reproducible:** `terraform apply` from clean state produces a working pool, and the workflow then runs green with no manual step.

## Acceptance criteria

1. A green workflow run, authenticated by WIF, printing a non-zero token count from Vertex. **This is the exit criterion.**
2. `terraform plan` is clean against the applied state, and the module instantiates for a second repository by changing variables only.
3. Token exchange from a repository other than the bound one is rejected.
4. Q4 and Q5 answered with evidence in `docs/probe-results.md`, each naming the SDK version observed.
5. `manage_task` and `schedule` documented — what they are, whether they write, and what covers them.
6. `docs/roadmap.md` M0 fully checked; the register shows Q1, Q4 and Q5 closed.
7. No credential-shaped value appears in any committed file or in a workflow log.

## Out of scope

The reviewer itself (M1) · cost arithmetic and the rate table (M2) · the dollar ceiling (M3) · rolling the module out to other repositories · the composite Action (M6).

## Risks

**ADC may not work headlessly in the runner.** The risk this track exists to retire. The documented fallback is Vertex Express Mode (`vertex=True, api_key=...`), which keeps spend attributable at the cost of reintroducing a key. If that fallback proves necessary, **M0 exits red** and the "no API keys" claim in `README.md` is corrected rather than quietly dropped.

**Terraform state has to live somewhere.** A GCS backend needs a bucket, which is chicken-and-egg on a fresh project. Local state is acceptable for this track provided it is gitignored and the limitation is stated in the module README.
