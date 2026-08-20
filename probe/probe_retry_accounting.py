"""Q5 / FR8 — do model-output retries consume `max_model_calls`, and do they appear in usage?

The default is 4 model-output re-prompts, each at full context. If they are
invisible to usage, every cost figure this project reports is understated by up
to four extra prompts per turn. If they do not consume `max_model_calls`, then
that dial does not bound what it appears to bound — the same class of leak Q4
found in `max_total_tokens`.

Forcing the violation: a schema no output can satisfy — an integer required to
be both >= 10 and <= 5. The model cannot comply, so every attempt fails
validation and the retry path is exercised deterministically rather than hoped
for.

The discriminator: `max_retries=4` against `max_model_calls=3`.

  stops with MAX_MODEL_CALLS_EXCEEDED  -> retries DO consume model calls
  runs the retries out and stops otherwise -> they do NOT

Run:  GOOGLE_CLOUD_PROJECT=<project> uv run python probe/probe_retry_accounting.py
"""

from __future__ import annotations

import asyncio
import os
import sys

from google.antigravity import Agent, LocalAgentConfig, types

SDK_VERSION = "0.1.12"
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
MODEL = os.environ.get("AGY_MODEL", "gemini-3.7-flash")

PROMPT = "Give me a number."

SATISFIABLE = {
    "type": "object",
    "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 10}},
    "required": ["n"],
}

# No integer is both >= 10 and <= 5.
IMPOSSIBLE = {
    "type": "object",
    "properties": {"n": {"type": "integer", "minimum": 10, "maximum": 5}},
    "required": ["n"],
}


def summarise(usage) -> str:
    if usage is None:
        return "(none)"
    return (
        f"prompt={usage.prompt_token_count or 0:,} "
        f"out={usage.candidates_token_count or 0:,} "
        f"total={usage.total_token_count or 0:,}"
    )


async def run(
    label: str,
    project: str,
    schema: dict,
    *,
    max_retries: int,
    max_calls: int,
    max_out: int = 6_000,
) -> dict:
    config = LocalAgentConfig(
        vertex=True,
        project=project,
        location=LOCATION,
        model=MODEL,
        system_instructions="Answer only with the structured output.",
        response_schema=schema,
        capabilities=types.CapabilitiesConfig(
            enabled_tools=[types.BuiltinTools.FINISH], enable_subagents=False
        ),
        retry_config=types.RetryConfig(
            model_output_retry=types.ModelOutputRetryConfig(max_retries=max_retries)
        ),
        # Generous on purpose. A tight output dial fires before the call dial and
        # masks the very thing this probe is trying to isolate — the first
        # version of this probe made exactly that mistake.
        budget_config=types.BudgetConfig(max_model_calls=max_calls, max_output_tokens=max_out),
    )

    error = ""
    try:
        async with Agent(config) as agent:
            response = await agent.chat(PROMPT)
            text = (await response.text()).strip()
            conv = agent.conversation
            result = {
                "stop": response.stop_reason,
                "text": text,
                "usage": conv.total_usage,
                "turns": conv.turn_count,
                "structured": conv.get_last_structured_output(),
            }
    except Exception as exc:  # noqa: BLE001 - the failure mode is the result
        result = {"stop": None, "text": "", "usage": None, "turns": 0, "structured": None}
        error = f"{type(exc).__name__}: {exc}"

    print(f"\n--- {label} ---")
    print(f"  max_retries={max_retries}  max_model_calls={max_calls}")
    print(f"  stop_reason : {result['stop']}")
    print(f"  turns       : {result['turns']}")
    print(f"  structured  : {result['structured']}")
    print(f"  usage       : {summarise(result['usage'])}")
    if error:
        print(f"  raised      : {error[:160]}")
    result["error"] = error
    return result


async def main(project: str) -> int:
    print(f"SDK {SDK_VERSION} — Q5 retry accounting")
    print(f"project={project} location={LOCATION} model={MODEL}")

    # Baseline: one clean structured call, so the cost of a single successful
    # attempt is known and the retry runs have something to be measured against.
    base = await run(
        "BASELINE — satisfiable schema", project, SATISFIABLE, max_retries=0, max_calls=6
    )

    # The discriminator.
    forced = await run(
        "FORCED VIOLATION — max_retries=4, max_model_calls=3",
        project,
        IMPOSSIBLE,
        max_retries=4,
        max_calls=3,
    )

    # Same violation, generous call budget: isolates how many attempts the retry
    # path really makes, and what they cost, without the budget interfering.
    free = await run(
        "FORCED VIOLATION — max_retries=4, max_model_calls=20",
        project,
        IMPOSSIBLE,
        max_retries=4,
        max_calls=20,
    )

    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)

    base_total = (base["usage"].total_token_count or 0) if base["usage"] else 0
    free_total = (free["usage"].total_token_count or 0) if free["usage"] else 0

    consumed = forced["stop"] == types.StopReason.MAX_MODEL_CALLS_EXCEEDED
    print(
        f"  retries consume max_model_calls : "
        f"{'YES — stopped on the call budget' if consumed else 'NO — budget was not the stop reason'}"
        f"   (stop={forced['stop']})"
    )

    if base_total and free_total:
        ratio = free_total / base_total
        print(f"  one clean attempt  : {base_total:,} tokens")
        print(f"  retried attempt    : {free_total:,} tokens  ({ratio:.1f}x)")
        print(
            "  retries appear in usage         : "
            f"{'YES' if ratio > 1.5 else 'NOT VISIBLY — usage looks like a single attempt'}"
        )
    else:
        print("  usage comparison unavailable (a run raised before reporting)")

    return 0


if __name__ == "__main__":
    proj = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not proj:
        raise SystemExit("FAIL: GOOGLE_CLOUD_PROJECT is not set.")
    sys.exit(asyncio.run(main(proj)))
