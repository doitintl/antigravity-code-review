"""M0 exit criterion: prove WIF → ADC → Vertex works headlessly in CI.

One trivial agent call. If this prints a non-zero token count from a GitHub
Actions runner with no API key anywhere, the foundation this project is built
on is real rather than assumed.

Exits non-zero when usage is absent or zero, so a silent no-op cannot pass as a
green run — a probe that cannot fail proves nothing.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from google.antigravity import Agent, LocalAgentConfig, types

from antigravity_code_review.usage import format_usage, read_usage

# `global` is not a default anyone would guess: us-central1 returns 404 for this
# model. Verified 0.1.12 — see docs/probe-results.md.
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
MODEL = os.environ.get("AGY_MODEL", "gemini-3.7-flash")

# API keys must not be present at all. Their absence is the claim this probe
# exists to support, so it is asserted rather than trusted.
FORBIDDEN_ENV = ("GEMINI_API_KEY", "GOOGLE_API_KEY")


def assert_keyless() -> None:
    """Assert no key material is in play.

    `GOOGLE_APPLICATION_CREDENTIALS` is deliberately NOT treated as evidence of
    a key. Under Workload Identity Federation, google-github-actions/auth sets
    it to an *external account credential configuration* — instructions for
    exchanging the runner's OIDC token, carrying no private key. A first
    revision of this probe failed the run on the variable's mere presence,
    which would have rejected the very mechanism it exists to prove.

    What matters is the file's `type`:
      external_account  -> WIF. Keyless. This is what we want.
      service_account   -> a downloaded key. Fails.
    """
    present = [name for name in FORBIDDEN_ENV if os.environ.get(name)]
    if present:
        raise SystemExit(
            f"FAIL: {', '.join(present)} is set. This probe must prove keyless "
            "auth; with a key present a green run would prove nothing."
        )

    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path:
        print("keyless: no API key, no credentials file (bare ADC)  OK")
        return

    try:
        with open(creds_path, encoding="utf-8") as handle:
            cred = json.load(handle)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"FAIL: GOOGLE_APPLICATION_CREDENTIALS is set but unreadable: {exc}")

    cred_type = cred.get("type")
    if cred_type != "external_account":
        raise SystemExit(
            f"FAIL: credential type is {cred_type!r}, not 'external_account'. "
            "That is a downloaded key, not federation."
        )
    if "private_key" in cred:
        raise SystemExit("FAIL: the credential file contains a private key.")

    print(
        f"keyless: credential type is 'external_account' ({cred.get('subject_token_type', '?')})  OK"
    )


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
