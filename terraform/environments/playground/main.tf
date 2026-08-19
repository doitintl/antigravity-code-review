# Root configuration for the development target.
#
# One directory per reviewed repository. To onboard another repo, copy this
# directory, change the three values in terraform.tfvars, and apply. Nothing
# else should need editing — if it does, the module is under-parameterised.

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 7.20.0"
    }
  }

  # Local state, deliberately, while bootstrapping — see ../../wif/README.md.
  # Move to a GCS backend with object versioning before a second person applies.
}

provider "google" {
  project = var.project_id
}

variable "project_id" {
  type        = string
  description = "GCP project billed for inference."
}

variable "github_owner" {
  type        = string
  description = "GitHub owner or organisation."
}

variable "github_repo" {
  type        = string
  description = "Repository permitted to exchange tokens."
}

variable "create_pool" {
  type        = bool
  description = "False here: this project already federates GitHub via an existing pool."
  default     = false
}

variable "pool_id" {
  type        = string
  description = "Existing pool to attach the provider to."
}

variable "provider_id" {
  type        = string
  description = "Provider ID within the pool."
}

module "wif" {
  source = "../../wif"

  project_id   = var.project_id
  github_owner = var.github_owner
  github_repo  = var.github_repo

  create_pool = var.create_pool
  pool_id     = var.pool_id
  provider_id = var.provider_id
}

output "workload_identity_provider" {
  value = module.wif.workload_identity_provider
}

output "service_account_email" {
  value = module.wif.service_account_email
}

output "bound_repository" {
  value = module.wif.bound_repository
}

output "github_actions_auth_snippet" {
  value = module.wif.github_actions_auth_snippet
}
