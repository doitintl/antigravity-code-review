variable "project_id" {
  type        = string
  description = "GCP project that hosts the pool and is billed for inference. One project per reviewed repository — see README.md."
}

variable "github_owner" {
  type        = string
  description = "GitHub owner or organisation, e.g. \"doitintl\"."
}

variable "github_repo" {
  type        = string
  description = "Repository name, e.g. \"antigravity-code-review\". Token exchange is restricted to this repository alone."
}

variable "create_pool" {
  type        = bool
  description = <<-EOT
    Whether to create the workload identity pool, or attach a provider to one
    that already exists.

    Default true: under the one-project-per-repository rollout model each
    project owns exactly one pool, so the module should be self-contained.

    Set false when onboarding into a project that already federates GitHub —
    pools are containers, and the security boundary is the per-provider
    attribute condition either way. `pool_id` must then name the existing pool.
  EOT
  default     = true
}

variable "pool_id" {
  type        = string
  description = "Workload identity pool ID — created when create_pool is true, otherwise the existing pool to attach to. 4-32 chars, lowercase letters, digits and hyphens."
  default     = "github-actions"

  validation {
    condition     = can(regex("^[a-z0-9-]{4,32}$", var.pool_id))
    error_message = "pool_id must be 4-32 characters of lowercase letters, digits and hyphens."
  }
}

variable "provider_id" {
  type        = string
  description = "OIDC provider ID within the pool."
  default     = "github-oidc"

  validation {
    condition     = can(regex("^[a-z0-9-]{4,32}$", var.provider_id))
    error_message = "provider_id must be 4-32 characters of lowercase letters, digits and hyphens."
  }
}

variable "sa_name" {
  type        = string
  description = "Service account ID (the part before the @). The reviewer's identity on Vertex."
  default     = "agy-code-review"

  validation {
    condition     = can(regex("^[a-z]([a-z0-9-]{4,28})[a-z0-9]$", var.sa_name))
    error_message = "sa_name must be 6-30 characters, start with a letter, and contain only lowercase letters, digits and hyphens."
  }
}

variable "enable_services" {
  type        = bool
  description = "Enable the APIs this module depends on. Set false if the project's services are managed elsewhere."
  default     = true
}

variable "allowed_ref" {
  type        = string
  description = <<-EOT
    Optional git ref restriction, e.g. "refs/heads/main". When set, the token
    exchange additionally requires the workflow to be running on this ref.

    Leave null for the reviewer: it must run on pull request events from any
    branch, so a ref restriction would break it. Provided because a deploy
    pipeline reusing this module usually should be pinned to one branch.
  EOT
  default     = null
}
