data "google_project" "main" {
  project_id = var.project_id
}

locals {
  repo_full = "${var.github_owner}/${var.github_repo}"

  # Token exchange is restricted to one repository. Without this condition any
  # repository on GitHub could mint credentials against this pool, which is a
  # credential leak wearing a keyless costume.
  attribute_condition = var.allowed_ref == null ? (
    "assertion.repository == '${local.repo_full}'"
    ) : (
    "assertion.repository == '${local.repo_full}' && assertion.ref == '${var.allowed_ref}'"
  )

  # Principals are matched on the mapped repository attribute rather than on
  # google.subject, so the binding survives GitHub changing the shape of `sub`.
  principal_set = "principalSet://iam.googleapis.com/projects/${data.google_project.main.number}/locations/global/workloadIdentityPools/${var.pool_id}/attribute.repository/${local.repo_full}"

  services = [
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "aiplatform.googleapis.com",
  ]
}

resource "google_project_service" "main" {
  for_each = var.enable_services ? toset(local.services) : toset([])

  project = var.project_id
  service = each.value

  # Never disable an API on destroy: other workloads in the project may depend
  # on it, and tearing down a reviewer should not break them.
  disable_on_destroy = false
}

resource "google_iam_workload_identity_pool" "main" {
  count = var.create_pool ? 1 : 0

  project                   = var.project_id
  workload_identity_pool_id = var.pool_id
  display_name              = "GitHub Actions"
  description               = "Keyless auth for GitHub Actions workflows in ${local.repo_full}."

  depends_on = [google_project_service.main]
}

resource "google_iam_workload_identity_pool_provider" "main" {
  project = var.project_id

  # Either the pool this module just created, or the pre-existing one named by
  # var.pool_id. Referencing the resource when it exists keeps the dependency
  # ordering explicit rather than relying on eventual consistency.
  workload_identity_pool_id          = var.create_pool ? google_iam_workload_identity_pool.main[0].workload_identity_pool_id : var.pool_id
  workload_identity_pool_provider_id = var.provider_id
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.repository"       = "assertion.repository"
    "attribute.repository_owner" = "assertion.repository_owner"
    "attribute.ref"              = "assertion.ref"
  }

  attribute_condition = local.attribute_condition

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "main" {
  project      = var.project_id
  account_id   = var.sa_name
  display_name = "Antigravity code review (${local.repo_full})"
  description  = "Runs the PR reviewer on Vertex. Holds aiplatform.user and nothing else."

  depends_on = [google_project_service.main]
}

# The only role the reviewer needs. Additive (`_member`, not `_binding` or
# `_policy`) so it cannot clobber anything else in the project's IAM.
resource "google_project_iam_member" "aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.main.email}"
}

# Lets the bound repository impersonate the service account. This is the whole
# point of the module: no key is ever created, so there is nothing to leak or
# rotate.
resource "google_service_account_iam_member" "workload_identity_user" {
  service_account_id = google_service_account.main.name
  role               = "roles/iam.workloadIdentityUser"
  member             = local.principal_set

  depends_on = [google_iam_workload_identity_pool_provider.main]
}
