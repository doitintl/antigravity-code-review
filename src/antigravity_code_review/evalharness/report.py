"""Report the measurement without letting one number acquire unearned authority.

The whole of M5 exists because single numbers kept turning out to be about the
instrument. So this module is written to make the honest shape of the result the
easy one to read, and the misleading shape awkward to produce.

**Per-defect hit rate, never one figure.** M1 measured five defects at 8/8, one
at 4/8, and one at 0/8 that turned out to be a broken fixture. Averaged, that is
a number that moves for reasons nobody can attribute; kept apart, it is three
different facts, one of which was a bug in the harness.

**Ranges, not points.** Three fixtures can detect a ±1 finding swing and cannot
support a percentage. Run-to-run variance has already exceeded the interventions
being tested. `render` prints no percentage at all — a deliberate constraint, and
the test suite enforces it.

**Incomplete runs listed separately, and still charged for.** Excluding a stopped
run from recall does not make it free; one cost $1.46 and produced nothing.

**Unknown cost is never zero.** A run whose rate could not be resolved reports as
unknown and is counted, because under-reporting spend hurts exactly when someone
is investigating a spike.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from antigravity_code_review.evalharness.scoring import RunScore

# FR4. One sample cannot see a ±1 swing, and this project spent a milestone
# discovering that the hard way.
MIN_RUNS = 3


@dataclass(frozen=True)
class RunRecord:
    """One run of one configuration against one fixture, priced.

    `cost_usd` is `None` when the rate could not be resolved — never 0.0. The
    rate table refuses to guess for exactly this reason, and the report must not
    undo that by averaging a missing number in as nothing.
    """

    score: RunScore
    cost_usd: float | None = None
    cost_reason: str | None = None
    tokens: int | None = None
    tool_calls: int | None = None


@dataclass(frozen=True)
class Report:
    """Aggregated across every run of one configuration."""

    configuration: str
    records: list[RunRecord]
    complete_records: list[RunRecord] = field(default_factory=list)
    incomplete: list[RunRecord] = field(default_factory=list)

    @property
    def complete(self) -> int:
        return len(self.complete_records)

    @property
    def fixtures(self) -> list[str]:
        seen = {}
        for record in self.records:
            seen[record.score.fixture] = None
        return list(seen)

    @property
    def novel_count(self) -> int:
        return sum(len(r.score.novel) for r in self.complete_records)

    @property
    def unknown_cost_runs(self) -> int:
        return sum(1 for r in self.records if r.cost_usd is None)

    @property
    def total_cost(self) -> float:
        return sum(r.cost_usd for r in self.records if r.cost_usd is not None)

    def _for(self, fixture: str) -> list[RunRecord]:
        return [r for r in self.complete_records if r.score.fixture == fixture]

    def hit_rate(self, fixture: str, defect_id: str) -> tuple[int, int]:
        """How many complete runs found this defect, out of how many ran.

        `(2, 3)` and `(3, 3)` are different facts and the report says so rather
        than rounding both to a percentage.
        """
        runs = self._for(fixture)
        return sum(1 for r in runs if r.score.found(defect_id)), len(runs)

    def recall_range(self, fixture: str) -> tuple[int, int, int] | None:
        """`(lowest, highest, of)` defects found across complete runs.

        `None` when no run of this fixture completed — which is not the same
        claim as zero, and is the distinction FR5 exists to preserve.
        """
        runs = self._for(fixture)
        if not runs:
            return None
        hits = [r.score.hits for r in runs]
        return min(hits), max(hits), len(runs[0].score.matches)

    def cost_range(self, fixture: str) -> tuple[float, float, float] | None:
        """`(lowest, highest, mean)` over runs whose cost is known.

        Includes incomplete runs: a stopped run spent real money.
        """
        costs = [
            r.cost_usd
            for r in self.records
            if r.score.fixture == fixture and r.cost_usd is not None
        ]
        if not costs:
            return None
        return min(costs), max(costs), sum(costs) / len(costs)

    def by_class(self) -> dict[str, tuple[int, int]]:
        """FR6: hits and opportunities per defect class, across complete runs."""
        totals: dict[str, list[int]] = {}
        for record in self.complete_records:
            for cls, (hit, total) in record.score.recall_by_class().items():
                bucket = totals.setdefault(cls, [0, 0])
                bucket[0] += hit
                bucket[1] += total
        return {cls: (hit, total) for cls, (hit, total) in sorted(totals.items())}


def aggregate(records: Sequence[RunRecord]) -> Report:
    """Split runs into complete and incomplete, and index them for reporting."""
    complete = [r for r in records if not r.score.incomplete]
    incomplete = [r for r in records if r.score.incomplete]
    configuration = records[0].score.configuration if records else "unknown"
    return Report(
        configuration=configuration,
        records=list(records),
        complete_records=complete,
        incomplete=incomplete,
    )


def _bar(hits: int, total: int) -> str:
    return "*" * hits + "." * (total - hits) if total else ""


def render(report: Report) -> str:
    """Render the report as text, with no percentage anywhere in it.

    That omission is the design. A percentage over three fixtures and three runs
    invites a comparison the sample cannot support, and this project has watched
    a single number acquire that kind of authority three separate times.
    """
    out: list[str] = []
    out.append(f"CONFIGURATION: {report.configuration}")
    out.append(
        f"{len(report.records)} run(s) — {report.complete} complete, "
        f"{len(report.incomplete)} incomplete"
    )
    if report.complete and report.complete < MIN_RUNS:
        out.append(
            f"  WARNING: n={report.complete}, fewer than {MIN_RUNS} complete runs. "
            "One sample cannot see a plus-or-minus-one finding swing; treat every "
            "figure below as an anecdote."
        )
    out.append("")

    out.append(f"{'fixture':18} {'recall':14} {'cost/run':32} runs")
    out.append("-" * 80)
    for fixture in report.fixtures:
        rng = report.recall_range(fixture)
        recall = "no complete run" if rng is None else (
            f"{rng[0]}-{rng[1]} of {rng[2]}" if rng[0] != rng[1] else f"{rng[0]} of {rng[2]}"
        )
        cost = report.cost_range(fixture)
        money = "cost unknown" if cost is None else (
            f"${cost[0]:.4f}-${cost[1]:.4f} (mean ${cost[2]:.4f})"
            if cost[0] != cost[1]
            else f"${cost[0]:.4f}"
        )
        out.append(f"{fixture:18} {recall:14} {money:32} {len(report._for(fixture))} complete")
    out.append("")

    out.append("PER-DEFECT HIT RATE ACROSS RUNS")
    for fixture in report.fixtures:
        runs = report._for(fixture)
        if not runs:
            out.append(f"  {fixture}: no complete run")
            continue
        out.append(f"  {fixture}")
        first = runs[0].score
        for defect_id in first.matches:
            hits, total = report.hit_rate(fixture, defect_id)
            cls = first.classes.get(defect_id, "unknown")
            out.append(f"    {defect_id:34} {cls:12} {hits}/{total}  {_bar(hits, total)}")
    out.append("")

    out.append("BY DEFECT CLASS (hits / opportunities across complete runs)")
    for cls, (hits, total) in report.by_class().items():
        out.append(f"  {cls:14} {hits}/{total}  {_bar(hits, total)}")
    out.append("")

    if report.novel_count:
        out.append(
            f"NOVEL FINDINGS: {report.novel_count} finding(s) matched no known defect. "
            "Not scored, and not discarded — one such finding was real."
        )
        out.append("")

    out.append("INCOMPLETE RUNS (excluded from recall, still charged for)")
    if not report.incomplete:
        out.append("  none")
    for record in report.incomplete:
        money = "cost unknown" if record.cost_usd is None else f"${record.cost_usd:.4f}"
        out.append(f"  {record.score.fixture:18} {money:14} {record.score.stop_reason}")
    out.append("")

    out.append(f"TOTAL COST: ${report.total_cost:.4f}")
    if report.unknown_cost_runs:
        out.append(
            f"  {report.unknown_cost_runs} run(s) report no cost. That is unknown, "
            "not zero — the total above is a floor."
        )
    return "\n".join(out)
