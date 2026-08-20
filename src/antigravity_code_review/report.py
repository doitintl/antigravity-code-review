"""What the reader sees: one line on the pull request, one JSON artifact.

The line is written to survive being quoted out of context, because it will be.
It carries a tilde and the word estimate, so a figure copied into a spreadsheet
still says what it is. `cost-tracking.md` is blunt about the failure mode:
reporting your own cost without an independent check is how a number everyone
quotes turns out to have been wrong for a month.
"""

from __future__ import annotations

from typing import Any

from antigravity_code_review.cost import PricedSession
from antigravity_code_review.rates import SOURCE, VERIFIED_ON

CAVEATS = [
    "The figure is an estimate until it appears in the billing export.",
    "Cache storage is billed per token-hour and is not included.",
    "Cost per review is not cost per acted-on finding.",
]


def cost_line(session: PricedSession, tool_calls: int) -> str:
    """One line, always present, cache rate included.

    The cache rate earns its place: it is the single most actionable number
    here. A low hit rate on a repeated review usually means volatile content
    early in the prompt, which is fixable.
    """
    # "turn", not "model call". An SDK turn is one chat() call, and a review
    # spends many model calls inside a single turn working its tool loop. The
    # token totals are cumulative over the turn and are correct either way, but
    # calling one turn "1 model call" was simply false — a review that made
    # eleven tool calls plainly did not make one model call.
    calls = f"{session.turns} turn" + ("" if session.turns == 1 else "s")
    output = session.tokens_candidates + session.tokens_thoughts

    if session.cost_usd is None:
        money = "cost unknown (unrecognised model or service tier)"
    else:
        money = f"~${session.cost_usd:.4f}"

    return (
        f"Reviewed in {calls} · {session.tokens_prompt:,} in "
        f"({session.cache_rate:.0%} cached) · {output:,} out · "
        f"{tool_calls} tool calls · {money}"
    )


def review_body(
    session: PricedSession,
    *,
    tool_calls: int,
    model: str,
    findings: int | None = None,
    stop_reason: str | None = None,
) -> str:
    """The review body a human actually reads.

    Written for the author of the pull request, not for us. An earlier version
    opened with "Posted by the runner, not by the agent" — an internal
    architectural distinction that mattered a great deal while building this and
    means nothing to somebody reading their own PR. Implementation detail is not
    context.

    The cost sits in a table because a middle-dot-separated line of six numbers
    is a log line, and a log line pasted into a review reads like one.
    """
    if findings is None:
        headline = "### Code review"
    elif findings == 0:
        headline = "### Code review — no issues found"
    else:
        noun = "finding" if findings == 1 else "findings"
        headline = f"### Code review — {findings} {noun}"

    output = session.tokens_candidates + session.tokens_thoughts
    cost = "not available" if session.cost_usd is None else f"**${session.cost_usd:.4f}**"

    rows = [
        ("Model", f"`{model}`"),
        ("Input tokens", f"{session.tokens_prompt:,} ({session.cache_rate:.0%} cached)"),
        ("Output tokens", f"{output:,}"),
        ("Tool calls", f"{tool_calls:,}"),
        ("Estimated cost", cost),
    ]
    table = "\n".join(
        ["| | |", "|---|---|", *[f"| {label} | {value} |" for label, value in rows]]
    )

    parts = [headline, "", table, ""]

    if stop_reason:
        parts += [
            (
                f"> **This review is incomplete.** The run stopped early "
                f"(`{stop_reason}`), so the findings above are only what had "
                f"been recorded by that point."
            ),
            "",
        ]

    note = (
        f"<sub>Cost is an estimate at published {session.rate_applied or 'list'} rates "
        f"(source verified {VERIFIED_ON}); cache storage is billed separately and is not "
        f"included. Verify against your billing export before quoting it.</sub>"
    )
    parts.append(note)
    return "\n".join(parts)


def cost_artifact(
    session: PricedSession,
    *,
    repo: str,
    pr: int,
    model: str,
    tool_calls: int,
    compactions: int = 0,
    retries: dict[str, int] | None = None,
    budget_usd: float | None = None,
    stop_reason: str | None = None,
) -> dict[str, Any]:
    """Machine-readable, so it can be aggregated without scraping comments.

    `model`, `rate_source` and `rate_verified_on` travel with the figure. Without
    them the number cannot be checked by anyone who did not run it, and an
    uncheckable cost figure is the thing this project exists not to produce.
    """
    return {
        "repo": repo,
        "pr": pr,
        "model": model,
        "turns": session.turns,
        "tool_calls": tool_calls,
        "tokens": {
            "prompt": session.tokens_prompt,
            "cached": session.tokens_cached,
            "candidates": session.tokens_candidates,
            "thoughts": session.tokens_thoughts,
            "total": session.tokens_total,
        },
        "cache_rate": round(session.cache_rate, 4),
        "service_tiers": session.service_tiers,
        "compactions": compactions,
        "retries": retries or {"api": 0, "model_output": 0},
        "cost_usd": None if session.cost_usd is None else round(session.cost_usd, 6),
        "rate_applied": session.rate_applied,
        "rate_source": SOURCE,
        "rate_verified_on": VERIFIED_ON,
        "budget_usd": budget_usd,
        "stop_reason": stop_reason,
        "caveats": list(CAVEATS),
    }
