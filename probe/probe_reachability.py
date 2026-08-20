"""Verify that every recorded defect can actually manifest, and say which ones were run.

FR2 exists because M1's fixture planted an unconditional `return True` that was
shadowed by an earlier `TypeError` on every call. The reviewer correctly
declined to report unreachable dead code and the harness scored it 0/8, which
looked like a blind spot in the reviewer and was a defect in the fixture.

This probe does two things and reports them separately, because they are not the
same strength of claim:

1. **The gate.** Every defect in the set carries reachability evidence that is
   not a placeholder. Mechanical, free, always runs.

2. **Execution.** A fixture may name a `reachability_probe` — a script that
   actually runs the defective code and prints what happened. Where one exists,
   its evidence is observed. Where none exists, the evidence is a recorded
   trigger path, and this probe **says so** rather than letting the two look
   alike in the output. A set where nothing was executed is a set whose
   reachability rests entirely on reading, and that is exactly the position M1
   was in.

Fixtures and their probe scripts name repositories and files, so both live in
`evals/fixtures/`, which is gitignored. This file names neither.

    uv run python probe/probe_reachability.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from antigravity_code_review.evalharness.fixtures import load_fixtures
from antigravity_code_review.evalharness.reachability import audit

FIXTURES = Path(os.environ.get("AGY_EVAL_FIXTURES", "evals/fixtures"))


def main() -> int:
    fixtures = load_fixtures(FIXTURES)
    if not fixtures:
        print(f"FAIL: no fixtures in {FIXTURES}. See evals/README.md.")
        return 1

    defects = sum(len(f.defects) for f in fixtures)
    repos = len({f.repo for f in fixtures})
    print(f"{len(fixtures)} fixture(s), {repos} repositor(y/ies), {defects} defect(s)\n")

    print("=" * 70)
    print("1. THE GATE — is the evidence evidence, or a filled-in field?")
    print("=" * 70)
    complaints = audit(fixtures)
    for complaint in complaints:
        print(f"  FAIL {complaint}")
    if not complaints:
        print(f"  PASS  all {defects} defect(s) carry non-placeholder evidence")

    print()
    print("=" * 70)
    print("2. EXECUTION — which evidence was observed, and which only recorded?")
    print("=" * 70)

    executed = recorded = failed = 0
    for fixture in fixtures:
        script = fixture.reachability_probe
        path = (FIXTURES / script) if script else None
        if path is None or not path.exists():
            recorded += len(fixture.defects)
            print(
                f"  RECORDED  {fixture.name:16} {len(fixture.defects)} defect(s) — evidence is a "
                "trigger path recorded by a reviewer, not executed here"
            )
            continue
        print(f"  RUNNING   {fixture.name:16} {path.name}")
        result = subprocess.run(
            [sys.executable, str(path.resolve())],
            capture_output=True,
            text=True,
            cwd=path.parent,
            check=False,
        )
        for line in (result.stdout or "").splitlines():
            print(f"      {line}")
        if result.returncode == 0:
            executed += len(fixture.defects)
            print(f"  EXECUTED  {fixture.name:16} {len(fixture.defects)} defect(s) observed")
        else:
            failed += len(fixture.defects)
            print(f"  FAILED    {fixture.name:16} exit {result.returncode}")
            for line in (result.stderr or "").splitlines()[-8:]:
                print(f"      {line}")

    print()
    print("=" * 70)
    print(f"observed by execution : {executed}")
    print(f"recorded trigger path : {recorded}")
    print(f"failed to reproduce   : {failed}")
    if recorded and not executed:
        print()
        print("  Nothing in this set was executed. Every reachability claim rests on")
        print("  reading, which is the position M1 was in when it planted a defect")
        print("  that could not fire.")
    print("=" * 70)

    return 1 if (complaints or failed) else 0


if __name__ == "__main__":
    sys.exit(main())
