"""Whether a run finished, which is not the same question as what it found.

**An empty review and a clean review are byte-identical.** Q8 measured it: a
budget stop preserves usage intact and returns empty text. The only thing that
tells the two apart is the stop reason, and this project has read it wrong
twice.

The first time, two diagnostic runs hit a 3,000-token output cap, returned
empty text, were read as "no findings", and the opposite conclusion was drawn
and written down. The second time, a contract-pass run with one of its three
passes crashed reported 2/4 as though all three had run — a floor presented as
a measurement.

So the rule here is deliberately blunter than "empty output after a stop":

**A run that did not finish normally is incomplete, is excluded from recall, and
is never counted as having found nothing.** Its findings are kept and reported,
because they are real. They are simply not allowed to produce a percentage, on
the grounds that the run never got to look for the rest.

One SDK detail this depends on, from `probe-results.md`:
`conversation.last_turn_stop_reason` was `None` while `response.stop_reason` was
set. **Read the stop reason off the response.** A caller that reads the wrong
one classifies every stopped run as clean.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

# The SDK reports a clean finish as StopReason.UNSPECIFIED, and some paths
# report nothing at all. Everything else is a stop, and every stop the probes
# exercised — model calls, tool calls, input, output, total tokens — halts a
# review part-way through.
_NORMAL = frozenset({"", "none", "unspecified", "stopreason.unspecified"})


class Outcome(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


def is_normal_stop(stop_reason: object | None) -> bool:
    """Whether this stop reason means the run finished of its own accord.

    Accepts the SDK enum, its string form, a bare name, or None — a caller
    should not have to know which of those it is holding to get the right
    answer, and one that guesses wrong marks every stopped run clean.
    """
    if stop_reason is None:
        return True
    return str(stop_reason).strip().casefold() in _NORMAL


@dataclass(frozen=True)
class RunOutcome:
    """Whether one run, or one stage of one, finished normally."""

    outcome: Outcome
    reason: str | None = None
    stop_reason: str | None = None
    stage: str | None = None

    @property
    def incomplete(self) -> bool:
        return self.outcome is Outcome.INCOMPLETE

    def __str__(self) -> str:
        if not self.incomplete:
            return "complete"
        return f"incomplete: {self.reason}"


def classify(
    stop_reason: object | None,
    *,
    text: str | None = None,
    error: str | None = None,
    findings: int = 0,
    stage: str | None = None,
) -> RunOutcome:
    """Decide whether a run finished, and say why when it did not.

    Args:
        stop_reason: read off the **response**, not off the conversation.
        text: the run's output, used only to make the reason more useful.
        error: an exception raised during the run, if any.
        findings: how many findings were parsed. Recorded, never exculpatory —
            a stopped run that found two defects is still a stopped run.
        stage: names this stage of a multi-pass run, for the combined reason.

    Returns:
        A frozen `RunOutcome`.
    """
    name = None if stop_reason is None else str(stop_reason).strip()

    if error:
        return RunOutcome(Outcome.INCOMPLETE, f"failed: {error}", name, stage)

    if is_normal_stop(stop_reason):
        return RunOutcome(Outcome.COMPLETE, None, name, stage)

    detail = "empty output" if not (text or "").strip() else f"{findings} finding(s) before the stop"
    return RunOutcome(
        Outcome.INCOMPLETE,
        f"stopped early ({name}), {detail}",
        name,
        stage,
    )


def combine(outcomes: Sequence[RunOutcome]) -> RunOutcome:
    """Roll several stages of one review into a single outcome.

    Any incomplete stage makes the whole run incomplete. A review is several
    passes and a judge, and a run with one pass missing has looked at less than
    it claims to have — which is exactly how 2/4 got reported for a run whose
    third pass had crashed.

    An empty sequence is incomplete, not complete: no stage ran, and that is not
    a clean review of anything.
    """
    if not outcomes:
        return RunOutcome(Outcome.INCOMPLETE, "no stages ran", None, None)

    broken = [o for o in outcomes if o.incomplete]
    if not broken:
        return RunOutcome(Outcome.COMPLETE, None, None, None)

    named = ", ".join(f"{o.stage or 'stage'}: {o.reason}" for o in broken)
    first_stop = next((o.stop_reason for o in broken if o.stop_reason), None)
    return RunOutcome(
        Outcome.INCOMPLETE,
        f"{len(broken)} of {len(outcomes)} stage(s) incomplete — {named}",
        first_stop,
        None,
    )
