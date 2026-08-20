project_id   = "sascha-playground-doit"
github_owner = "doitintl"
github_repo  = "antigravity-code-review"

# This project already federates GitHub through an existing pool holding three
# per-repository providers. Attach a fourth rather than standing up a second
# pool; the security boundary is the attribute condition, not the container.
create_pool = false
pool_id     = "github-pool"
provider_id = "agy-code-review"
