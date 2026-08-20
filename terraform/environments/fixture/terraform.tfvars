# The M1 verification fixture. Deliberately reuses the playground project rather
# than standing up a new one: the security boundary is the per-provider attribute
# condition, not the project, and the fixture is throwaway. The one-project-per-
# repository rollout model still applies to real reviewed repositories.
project_id   = "sascha-playground-doit"
github_owner = "SaschaHeyer"
github_repo  = "agy-review-fixture"

create_pool = false
pool_id     = "github-pool"
provider_id = "agy-review-fixture"

# Distinct service account: several repositories share this project, and the
# module creates one SA per repository.
sa_name = "agy-review-fixture"
