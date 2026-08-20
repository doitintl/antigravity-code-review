"""Re-score saved runs against the current fixtures, without spending anything.

A fixture correction should never require re-running the reviewer. The findings
a run produced are facts about that run; what they are compared against is a
separate thing that can be wrong on its own — and on this project it was.

The first sweep reported `draft-538` at 0/4. Two of its three runs had in fact
identified a known defect and anchored the comment at line 989; the fixture had
recorded the reference reviewer's own anchor, 1005, and a three-line tolerance
called it a miss. The reference text itself named the block as `989-1005`; the
curation had discarded the span and kept the point.

So: keep the findings, fix the fixture, re-score. Re-running would have cost
another three and a half dollars and would have measured the reviewer again to
fix a defect in the harness.

    uv run python evals/rescore.py evals/results/<file>.json
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from antigravity_code_review.evalharness.findings import Finding, normalise_path
from antigravity_code_review.evalharness.fixtures import load_fixtures
from antigravity_code_review.evalharness.report import RunRecord, aggregate, render
from antigravity_code_review.evalharness.runs import Outcome, RunOutcome
from antigravity_code_review.evalharness.scoring import score_run

FIXTURES = Path(os.environ.get("AGY_EVAL_FIXTURES", "evals/fixtures"))


def _findings(record: dict) -> list[Finding]:
    """Every finding the run produced: the matched ones plus the unmatched ones.

    Reconstructed from the record rather than re-derived, so re-scoring cannot
    quietly change what the run actually said.
    """
    raw = [f for f in (record.get("matched") or {}).values() if f]
    raw += record.get("novel") or []
    out = []
    for f in raw:
        line = f.get("line")
        value = int(line) if isinstance(line, int) else None
        out.append(
            Finding(
                file=normalise_path(str(f.get("file", ""))),
                line=value,
                end_line=value,
                claim=str(f.get("claim", "")),
                file_as_written=str(f.get("file", "")),
            )
        )
    return out


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("usage: rescore.py <results.json>")
    path = Path(sys.argv[1])
    records = json.loads(path.read_text(encoding="utf-8"))
    fixtures = {f.name: f for f in load_fixtures(FIXTURES)}

    rescored, moved = [], []
    for record in records:
        fixture = fixtures.get(record["fixture"])
        if fixture is None:
            print(f"  SKIP  {record['fixture']}: no such fixture any more")
            continue
        outcome = RunOutcome(
            Outcome.INCOMPLETE if record["incomplete"] else Outcome.COMPLETE,
            record.get("stop_reason"),
            record.get("stop_reason"),
        )
        score = score_run(
            fixture,
            _findings(record),
            configuration=record["configuration"],
            outcome=outcome,
        )
        if score.hits != record["hits"]:
            moved.append(
                f"{record['fixture']}: {record['hits']}/{record['of']} -> "
                f"{score.hits}/{len(score.matches)}"
            )
        rescored.append(RunRecord(score=score, cost_usd=record.get("cost_usd")))

    if moved:
        print("RUNS WHOSE SCORE CHANGED (the runs did not change; the fixtures did)")
        for line in moved:
            print(f"  {line}")
    else:
        print("No run's score changed.")
    print()
    print("=" * 80)
    print(render(aggregate(rescored)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
