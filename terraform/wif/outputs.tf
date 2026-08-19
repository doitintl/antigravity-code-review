output "workload_identity_provider" {
  description = "Full resource name of the OIDC provider. Pass to google-github-actions/auth as `workload_identity_provider`."
  value       = google_iam_workload_identity_pool_provider.main.name
}

output "service_account_email" {
  description = "Service account the workflow impersonates. Pass to google-github-actions/auth as `service_account`."
  value       = google_service_account.main.email
}

output "project_id" {
  description = "Project billed for inference and queried during reconciliation."
  value       = var.project_id
}

output "project_number" {
  description = "Project number, useful when constructing principal sets by hand."
  value       = data.google_project.main.number
}

output "bound_repository" {
  description = "The only repository permitted to exchange a token against this provider."
  value       = local.repo_full
}

output "github_actions_auth_snippet" {
  description = "Drop-in step for the workflow, so the values never have to be transcribed by hand."
  value       = <<-EOT
    - uses: google-github-actions/auth@v2
      with:
        workload_identity_provider: ${google_iam_workload_identity_pool_provider.main.name}
        service_account: ${google_service_account.main.email}
  EOT
}
