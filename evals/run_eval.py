"""Run a configuration against the fixture set, N times, and print the report.

    uv run python evals/run_eval.py --config contract-passes+judge --runs 3
    uv run python evals/run_eval.py --config contract-passes-only --fixture agy-fixture-1

Three gates run before any model call, in this order, because each of them has
already been the reason a published number was wrong:

1. **Reachability.** Every defect carries evidence it can manifest. A defect
   that cannot fire scores a correct triage decision as a miss.
2. **The scorer, validated against a reference review** — including the control
   where every claim is replaced by unrelated words. An unvalidated scorer
   reports a false zero that looks exactly like a real one.
3. **Run count.** Below three, the report says every figure in it is an anecdote.

Failing any of the first two stops the run rather than annotating it. Spending
money to produce a number the harness already knows it cannot trust is worse
than spending nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from antigravity_code_review.evalharness.fixtures import load_fixtures
from antigravity_code_review.evalharness.reachability import require_reachable
from antigravity_code_review.evalharness.report import aggregate, render
from antigravity_code_review.evalharness.runner import CONFIGURATIONS, run_configuration
from antigravity_code_review.evalharness.scoring import (
    ScorerValidationError,
    ambiguous_pairs,
    findings_from_reference,
    score_run,
    validate_against_reference,
)

FIXTURES = Path(os.environ.get("AGY_EVAL_FIXTURES", "evals/fixtures"))
REFERENCE = Path(os.environ.get("AGY_EVAL_REFERENCE", "evals/reference"))
NONSENSE = "quixotic zephyr brindle fathom glimmer thicket"


def _validate_scorer(fixtures) -> int:
    """Return how many fixtures the scorer could not be validated against."""
    unvalidated = 0
    for fixture in fixtures:
        path = REFERENCE / (fixture.reference_review or "")
        if not fixture.reference_review or not path.exists():
            unvalidated += 1
            print(f"  UNVALIDATED  {fixture.name}: no reference review")
            continue
        reference = json.loads(path.read_text(encoding="utf-8"))
        score = validate_against_reference(fixture, reference)
        scrubbed = [
            dataclasses.replace(f, claim=NONSENSE) for f in findings_from_reference(reference)
        ]
        control = score_run(fixture, scrubbed, configuration="paraphrase-control")
        if control.hits != score.hits:
            raise ScorerValidationError(
                f"{fixture.name}: {score.hits} hits on the reference text and "
                f"{control.hits} with the words replaced. Text is vetoing location — "
                "this is the false-zero bug."
            )
        print(f"  VALIDATED    {fixture.name}: {score.hits}/{len(score.matches)}, paraphrase-safe")
    return unvalidated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="contract-passes+judge", choices=sorted(CONFIGURATIONS))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--fixture", action="append", help="limit to named fixtures")
    parser.add_argument("--out", help="write the run records here as JSON")
    args = parser.parse_args()

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise SystemExit("FAIL: GOOGLE_CLOUD_PROJECT is not set")

    fixtures = load_fixtures(FIXTURES)
    if args.fixture:
        wanted = set(args.fixture)
        fixtures = [f for f in fixtures if f.name in wanted]
        missing = wanted - {f.name for f in fixtures}
        if missing:
            raise SystemExit(f"FAIL: no such fixture(s): {', '.join(sorted(missing))}")
    if not fixtures:
        raise SystemExit(f"FAIL: no fixtures in {FIXTURES}. See evals/README.md.")

    print("GATE 1 — reachability")
    require_reachable(fixtures)
    print(f"  PASS  {sum(len(f.defects) for f in fixtures)} defect(s) carry evidence\n")

    print("GATE 2 — the scorer, validated before it is trusted")
    unvalidated = _validate_scorer(fixtures)
    print()

    print("GATE 3 — defect pairs location alone cannot separate")
    ambiguous = 0
    for fixture in fixtures:
        for left, right, gap in ambiguous_pairs(fixture):
            ambiguous += 1
            print(
                f"  AMBIGUOUS    {fixture.name}: {left} and {right} are {gap} lines apart. "
                "Location cannot tell them apart; the text tie-break decides."
            )
    if not ambiguous:
        print("  PASS  every recorded defect is separable by location alone")
    print()

    configuration = CONFIGURATIONS[args.config]
    records = asyncio.run(
        run_configuration(fixtures, configuration, project=project, runs=args.runs)
    )

    report = aggregate(records)
    print("\n" + "=" * 80)
    print(render(report))
    if unvalidated:
        print()
        print(
            f"  CAVEAT: {unvalidated} fixture(s) have no reference review, so the scorer "
            "is unvalidated\n  against them. Their numbers rest on the scorer being right."
        )
    if ambiguous:
        print()
        print(
            f"  CAVEAT: {ambiguous} defect pair(s) sit closer than the line tolerance can "
            "separate.\n  For those, 'location first, text only to disambiguate' is really "
            "'text decides'."
        )

    if args.out:
        Path(args.out).write_text(
            json.dumps(
                [
                    {
                        "fixture": r.score.fixture,
                        "configuration": r.score.configuration,
                        "incomplete": r.score.incomplete,
                        "stop_reason": r.score.stop_reason,
                        "hits": r.score.hits,
                        "of": len(r.score.matches),
                        "missed": r.score.missed(),
                        "novel": [f.as_comment() for f in r.score.novel],
                        "matched": {
                            d: (f.as_comment() if f else None) for d, f in r.score.matches.items()
                        },
                        "cost_usd": r.cost_usd,
                        "tokens": r.tokens,
                        "tool_calls": r.tool_calls,
                    }
                    for r in records
                ],
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
