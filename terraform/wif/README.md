# `wif` — keyless GitHub Actions auth to Vertex

Provisions Workload Identity Federation so a GitHub Actions workflow can call Vertex AI **without any long-lived credential**: no service account key, nothing in repository secrets, nothing to rotate or leak.

## Why one project per repository

The module takes `project_id` as an input and hardcodes nothing, because the rollout model is **one GCP project per reviewed repository**.

That is not tidiness. [Q11](../../docs/roadmap.md) established that the SDK exposes no surface for attaching billing labels to a generation request, so per-PR attribution in Cloud Billing is unreachable and Source 2 of the cost model was struck. What remains is project-level attribution — and if each repository bills to its own project, project-level attribution *is* per-repository attribution by construction. The parameterisation is the mechanism, not the packaging.

## Usage

```hcl
module "wif" {
  source = "../../wif"

  project_id   = "my-project"
  github_owner = "doitintl"
  github_repo  = "antigravity-code-review"
}
```

Then in the workflow:

```yaml
permissions:
  id-token: write      # required to mint the OIDC token
  contents: read

steps:
  - uses: google-github-actions/auth@v2
    with:
      workload_identity_provider: ${{ vars.WIF_PROVIDER }}
      service_account: ${{ vars.WIF_SERVICE_ACCOUNT }}
```

`terraform output github_actions_auth_snippet` prints this with the values filled in, so they never have to be transcribed by hand.

## What it creates

| Resource | Purpose |
|---|---|
| Workload identity pool | Trust anchor for external identities |
| OIDC provider | Trusts `token.actions.githubusercontent.com`, **restricted by attribute condition to one repository** |
| Service account | The reviewer's identity on Vertex |
| `roles/aiplatform.user` | The only project role granted. Additive `_member`, so it cannot clobber existing IAM |
| `roles/iam.workloadIdentityUser` | Lets the bound repository impersonate the service account |

APIs enabled: `iam`, `iamcredentials`, `sts`, `aiplatform`. Set `enable_services = false` if services are managed elsewhere. **They are never disabled on destroy** — other workloads in the project may depend on them.

## The attribute condition is the security boundary

```
assertion.repository == 'owner/repo'
```

Without it, **any repository on GitHub** could exchange a token against this pool. A pool scoped only by issuer trusts all of GitHub. Verify it after applying:

```bash
gcloud iam workload-identity-pools providers describe github-oidc \
  --project=PROJECT --location=global --workload-identity-pool=github-actions \
  --format='value(attributeCondition)'
```

`allowed_ref` adds a branch restriction. **Leave it null for the reviewer** — it runs on pull request events from arbitrary branches, so pinning a ref would break it. It exists for deploy pipelines reusing this module, which usually should be pinned.

## State

This module declares no backend; the root configuration chooses. Use a **GCS backend with object versioning** for anything shared.

⚠️ **Local state is acceptable only while bootstrapping** a project that has no state bucket yet — the case this repository is currently in. `terraform.tfstate` and `.terraform/` are gitignored. Local state is not shared, not locked, and not recoverable if the file is lost; the resources would then have to be imported. Move to GCS before a second person touches this.

State contains no secret material here: no keys are created. It does record project numbers and resource names.

## Verifying least privilege

```bash
gcloud projects get-iam-policy PROJECT \
  --flatten="bindings[].members" \
  --filter="bindings.members:agy-code-review@PROJECT.iam.gserviceaccount.com" \
  --format="value(bindings.role)"
```

Expected: exactly `roles/aiplatform.user`.
