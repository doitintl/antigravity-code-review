"""Run every M1 verification that the Vertex spend cap blocked, in one pass.

M1 stopped partway through Phase 2 when `sascha-playground-doit` hit a
project-level Vertex spend cap. Rather than leave the remaining checks scattered
across a plan for someone to rediscover, they are collected here.

Each check reports PASS / FAIL / SKIP independently, so one blocked dependency
(Docker, for the MCP checks) does not hide the others. Nothing here is
destructive: no review is submitted on the fixture PR.

Run once the cap is lifted:

    GOOGLE_CLOUD_PROJECT=sascha-playground-doit \\
    uv run --extra dev python probe/m1_resume.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import tempfile

RESULTS: list[tuple[str, str, str]] = []


def record(name: str, status: str, detail: str = "") -> None:
    RESULTS.append((name, status, detail))
    print(f"[{status:4}] {name}" + (f" — {detail}" if detail else ""))


async def check_vertex_reachable(project: str) -> bool:
    """Cheapest possible call. If this fails, everything after it would too."""
    from google.antigravity import Agent, LocalAgentConfig, types

    cfg = LocalAgentConfig(
        vertex=True,
        project=project,
        location="global",
        capabilities=types.CapabilitiesConfig(
            enabled_tools=[types.BuiltinTools.FINISH], enable_subagents=False
        ),
        budget_config=types.BudgetConfig(max_input_tokens=20_000, max_output_tokens=50),
    )
    try:
        async with Agent(cfg) as agent:
            response = await agent.chat("Say OK.")
            await response.text()
            usage = agent.conversation.total_usage
        record("vertex reachable", "PASS", f"{usage.total_token_count:,} tokens billed")
        return True
    except Exception as exc:  # noqa: BLE001 - the failure mode is the result
        msg = str(exc)
        hint = "spend cap still in place" if "Spend cap" in msg else msg[:120]
        record("vertex reachable", "FAIL", hint)
        return False


async def check_view_file_override(project: str) -> None:
    """FR5: assert the custom tool really replaces the built-in.

    The SDK documents an info log confirming it, which is stronger evidence than
    inferring it from behaviour.
    """
    from google.antigravity import Agent, LocalAgentConfig, types

    from antigravity_code_review.tools import view_file

    stream = _CaptureLogs()
    logging.getLogger().addHandler(stream)
    logging.getLogger("google.antigravity").setLevel(logging.INFO)
    try:
        cfg = LocalAgentConfig(
            vertex=True,
            project=project,
            location="global",
            tools=[view_file],
            capabilities=types.CapabilitiesConfig(
                enabled_tools=[types.BuiltinTools.VIEW_FILE, types.BuiltinTools.FINISH],
                enable_subagents=False,
            ),
            budget_config=types.BudgetConfig(max_input_tokens=60_000, max_output_tokens=400),
            workspaces=[os.getcwd()],
        )
        async with Agent(cfg) as agent:
            response = await agent.chat(
                f"Use view_file to read {os.getcwd()}/README.md and name its first heading."
            )
            await response.text()
        overrode = any("override" in line.lower() for line in stream.lines)
        record(
            "view_file override (FR5)",
            "PASS" if overrode else "FAIL",
            "harness confirmed the override" if overrode else "no override log line seen",
        )
    finally:
        logging.getLogger().removeHandler(stream)


async def check_writes_refused(project: str) -> None:
    """FR3: the assertion design.md insists must be made rather than assumed."""
    from google.antigravity import Agent

    from antigravity_code_review.config import build_config

    workspace = os.getcwd()
    app_data = tempfile.mkdtemp(prefix="agy-resume-")
    cfg = build_config(project, workspace, app_data)
    # Strip the MCP server so this check does not need Docker.
    cfg = cfg.model_copy(update={"mcp_servers": []})
    try:
        async with Agent(cfg) as agent:
            response = await agent.chat(
                "Create a file at "
                f"{workspace}/SHOULD_NOT_EXIST.txt containing the word 'written'. "
                "If you cannot, say exactly why."
            )
            await response.text()
        leaked = os.path.exists(os.path.join(workspace, "SHOULD_NOT_EXIST.txt"))
        record(
            "writes refused (FR3)",
            "FAIL" if leaked else "PASS",
            "A FILE WAS WRITTEN" if leaked else "no file created",
        )
        if leaked:
            os.remove(os.path.join(workspace, "SHOULD_NOT_EXIST.txt"))
    finally:
        shutil.rmtree(app_data, ignore_errors=True)


def check_mcp_allowlist() -> None:
    """FR6/FR7: needs Docker. Skips rather than failing when unavailable."""
    if shutil.which("docker") is None:
        record("MCP allowlist (FR6/FR7)", "SKIP", "docker not on PATH; CI runners have it")
        return
    record("MCP allowlist (FR6/FR7)", "SKIP", "run in CI, where the container can start")


async def main() -> int:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise SystemExit("FAIL: GOOGLE_CLOUD_PROJECT is not set.")

    print(f"M1 resume checks — project={project}\n")

    if not await check_vertex_reachable(project):
        print("\nVertex is still refusing calls; the model-dependent checks cannot run.")
        _summary()
        return 1

    await check_view_file_override(project)
    await check_writes_refused(project)
    check_mcp_allowlist()

    print(
        "\nStill to do by hand: trigger the workflow on fixture PR #1 and confirm "
        "the posted review names a planted defect (see fixture-defects.md)."
    )
    return _summary()


class _CaptureLogs(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record_: logging.LogRecord) -> None:
        self.lines.append(record_.getMessage())


def _summary() -> int:
    print("\n" + "=" * 60)
    failed = [n for n, s, _ in RESULTS if s == "FAIL"]
    for name, status, detail in RESULTS:
        print(f"  {status:4}  {name}" + (f" — {detail}" if detail else ""))
    print("=" * 60)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
