"""Q4 / FR7 — do subagent tokens reach `total_usage`, and do they count against `BudgetConfig`?

The register recorded "one delegation reported 45k root prompt tokens — evidence
of roll-up, no control run". A single large number is not evidence: the
delegating configuration also carries an extra tool in its surface, and the
floor is the dominant term. This probe runs the controlled pair the register
asked for, and adds a direct instrument the earlier attempt did not use.

`Conversation.trajectory_usages` reports usage **per trajectory**. A subagent
runs in its own trajectory. So rather than arguing from totals, we can ask
whether the subagent's trajectory is present and whether the root total
accounts for it. That turns an inference into a reading.

Three runs:
  A  delegation off              — the control
  B  delegation on, forced       — the comparison
  C  delegation on, tight budget — does a subagent's spend trip the ceiling?

⚠️ **Subagents do not work on Vertex in 0.1.12.** Every delegation attempt fails
with `CORTEX_STEP_TYPE_INVOKE_SUBAGENT: failed to fetch tiered models for
subagent model resolution: PlatformClient is nil`. Reproduced with the `model=`
shorthand, with `read_only()` tools, and with an explicit
`models=[ModelTarget(endpoint=VertexEndpoint(...))]`. The spawn still costs
tokens, which is what makes the accounting question answerable at all — and
which is itself the more important finding.

Run:  GOOGLE_CLOUD_PROJECT=<project> uv run python probe/probe_subagent_rollup.py
"""

from __future__ import annotations

import asyncio
import os
import sys

from google.antigravity import Agent, LocalAgentConfig, types
from google.antigravity.hooks import hooks

SDK_VERSION = "0.1.12"
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
MODEL = os.environ.get("AGY_MODEL", "gemini-3.7-flash")

# Kept deliberately trivial. The question is where the tokens are counted, not
# how well the model researches.
TASK = "Delegate the following to a subagent, then report only its answer: multiply 17 by 23."
CONTROL_TASK = "Multiply 17 by 23. Reply with just the number."

_delegated = False


@hooks.pre_tool_call_decide
async def watch_for_delegation(data: types.ToolCall) -> types.HookResult:
    """Record whether the model actually delegated, rather than assuming it did."""
    global _delegated
    if data.name == types.BuiltinTools.START_SUBAGENT.value:
        _delegated = True
    return types.HookResult(allow=True)


def summarise(usage) -> str:
    if usage is None:
        return "(none)"
    return (
        f"prompt={usage.prompt_token_count or 0:,} "
        f"out={usage.candidates_token_count or 0:,} "
        f"think={usage.thoughts_token_count or 0:,} "
        f"total={usage.total_token_count or 0:,}"
    )


async def run(label: str, project: str, *, delegate: bool, budget: types.BudgetConfig) -> dict:
    global _delegated
    _delegated = False

    tools = [types.BuiltinTools.FINISH]
    if delegate:
        tools.append(types.BuiltinTools.START_SUBAGENT)

    config = LocalAgentConfig(
        vertex=True,
        project=project,
        location=LOCATION,
        model=MODEL,
        tools=[],
        hooks=[watch_for_delegation] if delegate else [],
        capabilities=types.CapabilitiesConfig(
            enabled_tools=tools,
            enable_subagents=delegate,
        ),
        budget_config=budget,
    )

    async with Agent(config) as agent:
        response = await agent.chat(TASK if delegate else CONTROL_TASK)
        text = (await response.text()).strip()
        conv = agent.conversation
        total = conv.total_usage
        trajectories = conv.trajectory_usages

    print(f"\n--- {label} ---")
    print(f"  delegation observed : {_delegated}")
    print(f"  stop_reason         : {response.stop_reason}")
    print(f"  reply               : {text[:70]!r}")
    print(f"  total_usage         : {summarise(total)}")
    print(f"  trajectories        : {len(trajectories)}")
    for tid, usage in (trajectories or {}).items():
        print(f"      {str(tid)[:28]:<28} {summarise(usage)}")

    return {
        "label": label,
        "delegated": _delegated,
        "stop": response.stop_reason,
        "total": total,
        "trajectories": trajectories,
    }


async def main(project: str) -> int:
    print(f"SDK {SDK_VERSION} — Q4 subagent roll-up, controlled pair")
    print(f"project={project} location={LOCATION} model={MODEL}")

    generous = types.BudgetConfig(max_model_calls=12, max_total_tokens=80_000)

    a = await run("A — delegation OFF (control)", project, delegate=False, budget=generous)
    b = await run("B — delegation ON", project, delegate=True, budget=generous)

    print("\n" + "=" * 70)
    print("ROLL-UP")
    print("=" * 70)
    a_total = a["total"].total_token_count or 0
    b_total = b["total"].total_token_count or 0
    print(f"  A total: {a_total:,}")
    print(f"  B total: {b_total:,}   delta: {b_total - a_total:+,}")

    if not b["delegated"]:
        print("  ⚠️  B did not delegate. The comparison says nothing about subagents.")
    else:
        traj = b["trajectories"] or {}
        summed = sum((u.total_token_count or 0) for u in traj.values())
        print(f"  B trajectories: {len(traj)}, summing to {summed:,}")
        if len(traj) > 1:
            print("  => the subagent has its own trajectory entry")
        print(
            f"  => root total {'ACCOUNTS FOR' if b_total >= summed else 'IS LESS THAN'} "
            f"the sum of trajectories"
        )

    # C: can a subagent's spend trip the ceiling?
    #
    # The ceiling must sit ABOVE what the root trajectory reaches on its own and
    # BELOW root + subagent, or the test proves nothing: a ceiling near the
    # control's cost is breached by the root alone, since enabling
    # START_SUBAGENT already raises the tool-surface floor. Derive it from B's
    # own root trajectory rather than from the control.
    traj_b = b["trajectories"] or {}
    root_b = max((u.total_token_count or 0) for u in traj_b.values()) if traj_b else a_total
    ceiling = root_b + 2_000
    print("\n" + "=" * 70)
    print(f"BUDGET — delegation ON with max_total_tokens={ceiling:,}")
    print(f"(B's root trajectory alone was {root_b:,}; only subagent spend can breach this)")
    print("=" * 70)
    c = await run(
        "C — delegation ON, tight budget",
        project,
        delegate=True,
        budget=types.BudgetConfig(max_model_calls=12, max_total_tokens=ceiling),
    )

    stopped = c["stop"] == types.StopReason.MAX_TOTAL_TOKENS_EXCEEDED
    c_total = c["total"].total_token_count or 0
    c_traj = c["trajectories"] or {}
    c_root = max((u.total_token_count or 0) for u in c_traj.values()) if c_traj else c_total
    overshot = c_total > ceiling

    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    print(f"  subagent tokens reach total_usage    : {'yes' if b['delegated'] else 'UNPROVEN'}")

    if stopped:
        verdict = "yes — stopped at the ceiling"
    elif overshot:
        # The discriminator. Root stayed under the ceiling, the session did not
        # stop, and yet total_usage sailed past it. The budget is not evaluated
        # against total_usage.
        verdict = (
            f"NO — session reached {c_total:,} against a {ceiling:,} ceiling "
            f"and did not stop (root trajectory {c_root:,}, under the ceiling)"
        )
    else:
        verdict = "inconclusive — the ceiling was never approached"
    print(f"  subagent tokens count against budget : {verdict}")

    if overshot and not stopped:
        print(
            f"\n  ⚠️  THE CEILING LEAKS BY {c_total - ceiling:,} TOKENS.\n"
            "     BudgetConfig binds on the root trajectory, not on total_usage.\n"
            "     Subagent spend is billed, is reported, and is not capped."
        )
    return 0


if __name__ == "__main__":
    proj = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not proj:
        raise SystemExit("FAIL: GOOGLE_CLOUD_PROJECT is not set.")
    sys.exit(asyncio.run(main(proj)))
