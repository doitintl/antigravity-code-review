"""M0 exit criterion: prove WIF → ADC → Vertex works headlessly in CI.

One trivial agent call. If this prints a non-zero token count from a GitHub
Actions runner with no API key anywhere, the foundation this project is built
on is real rather than assumed.

Exits non-zero when usage is absent or zero, so a silent no-op cannot pass as a
green run — a probe that cannot fail proves nothing.
"""

from __future__ import annotations

import asyncio
import os
import sys

from google.antigravity import Agent, LocalAgentConfig, types

from antigravity_code_review.usage import format_usage, read_usage

# `global` is not a default anyone would guess: us-central1 returns 404 for this
# model. Verified 0.1.12 — see docs/probe-results.md.
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
MODEL = os.environ.get("AGY_MODEL", "gemini-3.7-flash")

# Credential-shaped inputs that must not be present. Their absence is the claim
# this probe exists to support, so it is asserted rather than trusted.
FORBIDDEN_ENV = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS")


def assert_keyless() -> None:
    present = [name for name in FORBIDDEN_ENV if os.environ.get(name)]
    if present:
        raise SystemExit(
            f"FAIL: {', '.join(present)} is set. This probe must prove keyless "
            "auth; with a key present a green run would prove nothing."
        )
    print("keyless: no API key or credentials file in the environment  OK")


async def probe(project: str) -> int:
    config = LocalAgentConfig(
        vertex=True,
        project=project,
        location=LOCATION,
        model=MODEL,
        system_instructions="Answer in one word.",
        capabilities=types.CapabilitiesConfig(
            # Only what the probe needs. Verified 0.1.12: trimming the tool list
            # cuts the per-turn prompt floor from 10,889 to 4,470 tokens.
            enabled_tools=[types.BuiltinTools.FINISH],
            enable_subagents=False,
        ),
        budget_config=types.BudgetConfig(
            max_model_calls=3,
            max_output_tokens=200,
        ),
    )

    async with Agent(config) as agent:
        response = await agent.chat("Say OK.")
        text = (await response.text()).strip()
        usage = read_usage(agent.conversation.total_usage)

        print(f"project:  {project}")
        print(f"location: {LOCATION}")
        print(f"model:    {MODEL}")
        print(f"reply:    {text[:60]!r}")
        print(f"stop:     {getattr(response, 'stop_reason', None)}")
        print(f"{format_usage(usage)}")

        if not usage.populated:
            print(
                "\nFAIL: the call returned no usage. Either it never reached "
                "Vertex, or it failed in a way that reports zero — which the "
                "SDK documents as possible. Not treating this as green.",
                file=sys.stderr,
            )
            return 1

    print("\nPASS: authenticated headlessly and billed real tokens on Vertex.")
    return 0


def main() -> int:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise SystemExit("FAIL: GOOGLE_CLOUD_PROJECT is not set.")

    assert_keyless()
    return asyncio.run(probe(project))


if __name__ == "__main__":
    sys.exit(main())
