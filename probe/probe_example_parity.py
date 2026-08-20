"""FR6 — run the SDK's own examples against Vertex, unmodified.

`budget_limits.py` and `observability.py` are load-bearing for M2 and M3, so
they are checked rather than assumed. Two things make that awkward:

1. **They do not ship in the wheel.** The installed package has no `examples/`
   directory at all. They live only in the source repository, so they are
   vendored under `probe/sdk_examples/` and pinned by blob SHA to tag
   `v0.1.12` — the tag matching the version this project pins. An example from
   a newer revision would silently test a different SDK.

2. **They are written for the API-key path.** Every one constructs a bare
   `LocalAgentConfig(...)` with no `vertex`, `project` or `location`, so run
   verbatim they would authenticate against the Gemini API rather than Vertex.

Rather than editing them — which would destroy the provenance that makes the
run meaningful — this runner patches `LocalAgentConfig` at the module the
examples import it from, injects the Vertex fields, and executes the file
untouched. The vendored bytes still hash to the upstream blob.

Run:  GOOGLE_CLOUD_PROJECT=<project> uv run python probe/probe_example_parity.py
"""

from __future__ import annotations

import hashlib
import os
import runpy
import sys
import traceback
from pathlib import Path

import google.antigravity as agy
from google.antigravity import types

SDK_VERSION = "0.1.12"
TAG = "v0.1.12"
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
MODEL = os.environ.get("AGY_MODEL", "gemini-3.7-flash")

EXAMPLES = Path(__file__).parent / "sdk_examples"

# git blob SHAs at tag v0.1.12. If these stop matching, the vendored copy has
# drifted from the pinned SDK and the run proves nothing.
UPSTREAM_SHA = {
    "budget_limits.py": "f1a72f7c7ed01ab19ec8c32e81cd1fa14f292ed0",
    "observability.py": "f693785172654a6ff48f47f89f78dc40c8ad2238",
}

# A ceiling for examples that ship no budget of their own. observability.py is
# one: run as written it is unbounded, which this project does not permit.
FALLBACK_BUDGET = types.BudgetConfig(max_model_calls=6, max_output_tokens=1500)


def git_blob_sha(path: Path) -> str:
    """Reproduce git's blob hash so the vendored copy can be checked against the tag."""
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def verify_provenance() -> bool:
    ok = True
    print(f"Provenance — vendored copies vs {TAG}:")
    for name, want in UPSTREAM_SHA.items():
        got = git_blob_sha(EXAMPLES / name)
        match = got == want
        ok &= match
        print(f"  {name:<22} {'MATCH' if match else 'DRIFT'}  {got}")
    return ok


def install_vertex_shim(project: str) -> list[str]:
    """Patch LocalAgentConfig so unmodified examples land on Vertex.

    Returns a list of the divergences this had to paper over — which is the
    actual finding, not a side effect.
    """
    divergences: list[str] = []
    original = agy.LocalAgentConfig

    def patched(*args, **kwargs):
        if not kwargs.get("vertex"):
            divergences.append("no vertex=True — would have used the Gemini API key path")
        kwargs.setdefault("vertex", True)
        kwargs.setdefault("project", project)
        kwargs.setdefault("location", LOCATION)
        kwargs.setdefault("model", MODEL)
        if not kwargs.get("budget_config"):
            divergences.append("no BudgetConfig — unbounded as written")
            kwargs["budget_config"] = FALLBACK_BUDGET
        return original(*args, **kwargs)

    agy.LocalAgentConfig = patched  # type: ignore[assignment]
    return divergences


def run_example(name: str, project: str) -> tuple[bool, list[str], str]:
    print("\n" + "=" * 70)
    print(f"RUN  {name}   (vertex=True, location={LOCATION}, model={MODEL})")
    print("=" * 70)

    divergences = install_vertex_shim(project)
    try:
        runpy.run_path(str(EXAMPLES / name), run_name="__main__")
        return True, divergences, ""
    except SystemExit as exc:
        return (exc.code in (0, None)), divergences, f"SystemExit({exc.code})"
    except Exception:  # noqa: BLE001 - the failure mode is the result
        return False, divergences, traceback.format_exc(limit=6)


def main() -> int:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise SystemExit("FAIL: GOOGLE_CLOUD_PROJECT is not set.")

    print(f"SDK {SDK_VERSION} — example parity against Vertex\n")
    if not verify_provenance():
        raise SystemExit("FAIL: vendored examples do not match the pinned tag.")

    results = {}
    for name in UPSTREAM_SHA:
        ok, divergences, err = run_example(name, project)
        results[name] = (ok, divergences, err)

    print("\n" + "=" * 70)
    print("PARITY SUMMARY")
    print("=" * 70)
    for name, (ok, divergences, err) in results.items():
        print(f"\n{name}: {'PASS' if ok else 'FAIL'}")
        for d in dict.fromkeys(divergences):
            print(f"    divergence: {d}")
        if err:
            print(f"    error: {err.strip().splitlines()[-1]}")

    return 0 if all(ok for ok, _, _ in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
