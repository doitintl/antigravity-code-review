# Plan — M0: Prove the foundation

Follows the methodology in [`../../workflow.md`](../../workflow.md). Each task is marked *logic* (full TDD: red, green, refactor, >80% coverage) or *integration* (verified by a probe run or a green CI job, with the observed behaviour recorded and the SDK version named).

**Scheduling note:** Phase 3 runs against local ADC and is independent of Phases 1–2. If WIF fights back in Phase 2, four of the five open M0 items can still close.

## Phase 1 — WIF infrastructure as Terraform

- [ ] **Task: Write the parameterised WIF module** *(integration)*
  - [ ] Create `terraform/wif/` with `variables.tf` (`project_id`, `github_owner`, `github_repo`, `pool_id`, `sa_name`), `main.tf`, `outputs.tf`
  - [ ] Workload identity pool and OIDC provider for `token.actions.githubusercontent.com`
  - [ ] Service account with `roles/aiplatform.user` on `project_id`, and nothing else
  - [ ] `roles/iam.workloadIdentityUser` binding scoped by attribute condition to `assertion.repository == "<owner>/<repo>"`
  - [ ] Outputs: provider resource name and service account email, for the workflow to consume
  - [ ] Gitignore local state; document the local-state limitation in the module README
- [ ] **Task: Apply and verify the boundary** *(integration)*
  - [ ] `terraform apply` against `sascha-playground-doit`
  - [ ] Verify the attribute condition rejects an exchange from an unbound repository
  - [ ] Confirm the service account holds no role beyond `aiplatform.user`
  - [ ] Record the applied resource names for the workflow to reference
- [ ] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))

## Phase 2 — The green run (exit criterion)

- [ ] **Task: Probe entrypoint** *(logic + integration — split into both)*
  - [ ] `m0_probe.py`: one trivial agent call, `vertex=True`, explicit `project`, `location="global"`, tight `BudgetConfig`
  - [ ] *Logic:* usage-formatting function — prompt / cached / candidates / thoughts / total / `service_tier` — unit tested against a synthetic `UsageMetadata`, including the all-`None` case
  - [ ] Non-zero exit if usage is absent or zero, so a silent no-op cannot pass as green
- [ ] **Task: CI workflow** *(integration)*
  - [ ] `.github/workflows/m0-foundation.yml` on `workflow_dispatch` and push to this branch
  - [ ] `permissions: id-token: write, contents: read`
  - [ ] `google-github-actions/auth` with WIF, pinned by commit SHA, **no `credentials_json`**
  - [ ] Install `google-antigravity==0.1.12` via uv; assert the `manylinux` wheel resolves on `ubuntu-latest`
  - [ ] Fail the job if any credential-shaped input is set
- [ ] **Task: Get it green** *(integration)*
  - [ ] Run, capture the token count, confirm no credential appears in the log
  - [ ] **If ADC fails headlessly:** record the failure verbatim, try Express Mode, and if that proves necessary, exit M0 *red* and correct the "no API keys" claim in `README.md` rather than dropping it quietly
- [ ] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))

## Phase 3 — Close the remaining verification items

*Runs against local ADC; independent of Phases 1–2.*

- [ ] **Task: Harness tool inventory (FR5)** *(integration)*
  - [ ] Extract the registered tool list from the harness, not from the model
  - [ ] Determine what `manage_task` and `schedule` do, and whether either writes
  - [ ] If either writes, raise it as a security finding against the posture in `docs/design.md`
- [ ] **Task: SDK example parity (FR6)** *(integration)*
  - [ ] Run `budget_limits.py` and `observability.py` against Vertex; note any divergence from the API-key path
- [ ] **Task: Q4 — subagent roll-up (FR7)** *(integration)*
  - [ ] Controlled pair: identical task with and without delegation; compare root `total_usage`
  - [ ] Determine whether subagent tokens count against `BudgetConfig`
- [ ] **Task: Q5 — retry accounting (FR8)** *(integration)*
  - [ ] Force a `response_schema` violation; measure whether retries consume `max_model_calls` and appear in usage
- [ ] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))

## Phase 4 — Record and close

- [ ] **Task: Write up the evidence** *(chore)*
  - [ ] Append Phase 2 and Phase 3 results to `docs/probe-results.md`, each naming the SDK version
  - [ ] Check off all M0 items in `docs/roadmap.md`; mark Q1, Q4 and Q5 closed in the register
  - [ ] Fold any new finding into `docs/design.md` or `docs/cost-tracking.md` where it changes a decision
- [ ] **Task: Phase Verification & Checkpoint** (refer to [`../../workflow.md`](../../workflow.md))
