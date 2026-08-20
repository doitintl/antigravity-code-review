# Vendored SDK examples

Not our code. Copied verbatim from
[`google-antigravity/antigravity-sdk-python`](https://github.com/google-antigravity/antigravity-sdk-python)
at tag **`v0.1.12`** — the tag matching the SDK version this project pins — and
kept here because **the examples do not ship in the wheel**: the installed
package has no `examples/` directory.

| file | upstream path | git blob SHA |
|---|---|---|
| `budget_limits.py` | `examples/getting_started/budget_limits.py` | `f1a72f7c7ed01ab19ec8c32e81cd1fa14f292ed0` |
| `observability.py` | `examples/getting_started/observability.py` | `f693785172654a6ff48f47f89f78dc40c8ad2238` |

Apache-2.0, © Google LLC. Original headers retained.

**Do not edit or reformat these files.** `probe/probe_example_parity.py` checks
each against the SHA above before running, and a mismatch fails the probe — the
point of vendoring them is to prove which revision was tested. They are excluded
from `ruff` in `pyproject.toml` for the same reason.

They are written for the API-key path, so the parity runner injects `vertex=True`,
`project` and `location` by patching `LocalAgentConfig` rather than by editing
the files. See `docs/probe-results.md` for what the run found.
