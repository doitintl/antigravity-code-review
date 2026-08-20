"""Validate the scorer before trusting a number it produced. AC3.

Two checks, and the second is the one that matters.

**1. Can the scorer find each fixture's defects in the reference review those
defects were recorded from?** If it cannot, every run scored afterwards reports
a false zero, and nothing about that zero looks wrong. This check is partly
circular by construction — the locations came from the same review — and it is
still worth running, because it is what catches a regression in path
normalisation or line tolerance against real data rather than against a
hand-built example.

**2. Does the scorer still find them when the words are replaced entirely?**
This is the failure that actually happened. A scorer greped for `"page type"`;
the judge had written `"pages"`; the run was scored 0/4 where the truth was 1/4
plus a novel defect. Check 2 reruns check 1 with every claim replaced by
unrelated text, and demands the same result. A scorer that passes 1 and fails 2
is the old scorer.

    uv run python evals/validate_scorer.py
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from antigravity_code_review.evalharness.fixtures import load_fixtures
from antigravity_code_review.evalharness.scoring import (
    ScorerValidationError,
    findings_from_reference,
    score_run,
    validate_against_reference,
)

FIXTURES = Path(os.environ.get("AGY_EVAL_FIXTURES", "evals/fixtures"))
REFERENCE = Path(os.environ.get("AGY_EVAL_REFERENCE", "evals/reference"))

# Deliberately shares no vocabulary with any review comment ever written.
NONSENSE = "quixotic zephyr brindle fathom glimmer thicket"


def main() -> int:
    fixtures = load_fixtures(FIXTURES)
    failures = []
    validated = unvalidatable = 0

    for fixture in fixtures:
        if not fixture.reference_review:
            unvalidatable += 1
            print(
                f"  NO REFERENCE  {fixture.name:16} {len(fixture.defects)} defect(s) — the scorer "
                "is unvalidated against this fixture; only its unit tests cover it"
            )
            continue

        path = REFERENCE / fixture.reference_review
        if not path.exists():
            unvalidatable += 1
            print(f"  MISSING       {fixture.name:16} {path} not fetched")
            continue

        reference = json.loads(path.read_text(encoding="utf-8"))

        try:
            score = validate_against_reference(fixture, reference)
        except ScorerValidationError as exc:
            failures.append(str(exc))
            print(f"  FAIL          {fixture.name:16} check 1: {exc}")
            continue

        # Check 2: the same locations, none of the same words.
        scrubbed = [
            dataclasses.replace(f, claim=NONSENSE) for f in findings_from_reference(reference)
        ]
        paraphrased = score_run(fixture, scrubbed, configuration="paraphrase-control")

        if paraphrased.hits != score.hits:
            failures.append(
                f"{fixture.name}: {score.hits} hits on the reference text, "
                f"{paraphrased.hits} with the words replaced — text is vetoing location"
            )
            print(
                f"  FAIL          {fixture.name:16} check 2: {score.hits} -> "
                f"{paraphrased.hits} when the words change. This is the false-zero bug."
            )
            continue

        validated += 1
        print(
            f"  VALIDATED     {fixture.name:16} {score.hits}/{len(score.matches)} on the "
            f"reference text, {paraphrased.hits}/{len(paraphrased.matches)} with the words "
            "replaced entirely"
        )

    print()
    print(f"validated: {validated}   unvalidatable: {unvalidatable}   failed: {len(failures)}")
    if unvalidatable:
        print(
            "  A fixture with no reference review cannot validate the scorer. Its recall\n"
            "  numbers rest on the scorer being right, which is the assumption this\n"
            "  check exists to stop making."
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
