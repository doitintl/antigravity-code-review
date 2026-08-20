# Plan — M0: Prove the foundation

Follows the methodology in [`../../workflow.md`](../../workflow.md). Each task is marked *logic* (full TDD: red, green, refactor, >80% coverage) or *integration* (verified by a probe run or a green CI job, with the observed behaviour recorded and the SDK version named).

**Scheduling note:** Phase 3 runs against local ADC and is independent of Phases 1–2. If WIF fights back in Phase 2, four of the five open M0 items can still close.

## Phase 1 — WIF infrastructure as Terraform

- [x] **Task: Write the parameterised WIF module** *(integration)* `2962837`
  - [x] Create `terraform/wif/` with `variables.tf` (`project_id`, `github_owner`, `github_repo`, `pool_id`, `sa_name`), `main.tf`, `outputs.tf`
  - [x] Workload identity pool and OIDC provider for `token.actions.githubusercontent.com`
  - [x] Service account with `roles/aiplatform.user` on `project_id`, and nothing else
  - [x] `roles/iam.workloadIdentityUser` binding scoped by attribute condition to `assertion.repository == "<owner>/<repo>"`
  - [x] Outputs: provider resource name and service account email, for the workflow to consume
  - [x] Gitignore local state; document the local-state limitation in the module README
- [x] **Task: Apply and verify the boundary** *(integration)* `2962837`
  - [x] `terraform apply` against `sascha-playground-doit`
  - [x] Verify the attribute condition rejects an exchange from an unbound repository
  - [x] Confirm the service account holds no role beyond `aiplatform.user`
  - [x] Record the applied resource names for the workflow to reference
- [ ] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))

## Phase 2 — The green run (exit criterion)

- [x] **Task: Probe entrypoint** *(logic + integration — split into both)*
  - [x] `m0_probe.py`: one trivial agent call, `vertex=True`, explicit `project`, `location="global"`, tight `BudgetConfig`
  - [x] *Logic:* usage-formatting function — prompt / cached / candidates / thoughts / total / `service_tier` — unit tested against a synthetic `UsageMetadata`, including the all-`None` case
  - [x] Non-zero exit if usage is absent or zero, so a silent no-op cannot pass as green
- [x] **Task: CI workflow** *(integration)*
  - [x] `.github/workflows/m0-foundation.yml` on `workflow_dispatch` and push to this branch
  - [x] `permissions: id-token: write, contents: read`
  - [x] `google-github-actions/auth` with WIF, pinned by commit SHA, **no `credentials_json`**
  - [x] Install `google-antigravity==0.1.12` via uv; assert the `manylinux` wheel resolves on `ubuntu-latest`
  - [x] Fail the job if any credential-shaped input is set
- [x] **Task: Get it green** *(integration)*
  - [x] Run, capture the token count, confirm no credential appears in the log
  - [x] **If ADC fails headlessly:** record the failure verbatim, try Express Mode, and if that proves necessary, exit M0 *red* and correct the "no API keys" claim in `README.md` rather than dropping it quietly
- [x] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))

## Phase 3 — Close the remaining verification items

*Runs against local ADC; independent of Phases 1–2.*

- [x] **Task: Harness tool inventory (FR5)** *(integration)* `20814bf`
  - [x] Extract the registered tool list from the harness, not from the model
  - [x] Determine what `manage_task` and `schedule` do, and whether either writes
  - [x] If either writes, raise it as a security finding against the posture in `docs/design.md` — neither writes; neither is registered. No finding raised
- [x] **Task: SDK example parity (FR6)** *(integration)* `308a349`
  - [x] Fetch `budget_limits.py` and `observability.py` from `google-antigravity/antigravity-sdk-python`, **from the tag matching the pinned `0.1.12`**, not from `main` — they do not ship in the wheel
  - [x] Run both against Vertex (`location="global"`); note any divergence from the API-key path they were written for — both PASS; neither sets `vertex=True`, and `observability.py` carries no `BudgetConfig`
  - [x] Correct `docs/prior-art.md`: the examples are not shipped in the distributed artefact — and the count is **32**, not 34 or 25; the 34 counted two READMEs
- [x] **Task: Q4 — subagent roll-up (FR7)** *(integration)* `b9db348`
  - [x] Controlled pair: identical task with and without delegation; compare root `total_usage` — roll-up confirmed via `trajectory_usages`
  - [x] Determine whether subagent tokens count against `BudgetConfig` — **no.** The dial binds on the root trajectory; the ceiling leaks
  - [x] *Unplanned:* subagents fail outright on Vertex in `0.1.12` (`PlatformClient is nil`), and the failed spawn still bills ~10x the control
- [x] **Task: Q5 — retry accounting (FR8)** *(integration)* `e06f13c`
  - [x] Force a `response_schema` violation; measure whether retries consume `max_model_calls` and appear in usage — retries **are** billed and visible (7.4x baseline), but do **not** consume `max_model_calls`
- [ ] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))

## Phase 4 — Record and close

- [x] **Task: Write up the evidence** *(chore)* `86fb5c8`
  - [x] Append Phase 2 and Phase 3 results to `docs/probe-results.md`, each naming the SDK version
  - [x] Check off all M0 items in `docs/roadmap.md`; mark Q1, Q4 and Q5 closed in the register — 0 M0 items remain open
  - [x] Fold any new finding into `docs/design.md` or `docs/cost-tracking.md` where it changes a decision — both updated; `conductor/product.md` and `conductor/tech-stack.md` raised for the doc-sync step rather than edited unilaterally
- [ ] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))
