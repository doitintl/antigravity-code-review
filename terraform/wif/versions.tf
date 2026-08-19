terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 7.20.0"
    }
  }

  # No backend block. This module is consumed by a root configuration that
  # chooses its own state location — see examples/ and README.md. A GCS backend
  # is the right answer for anything shared; local state is acceptable only
  # while bootstrapping a project that has no state bucket yet.
}
