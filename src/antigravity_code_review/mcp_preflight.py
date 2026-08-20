"""Ask the GitHub MCP server what it actually offers, before the agent starts.

FR7 wanted this validated through the SDK. The SDK has no surface for it —
`Agent` exposes `chat` and `conversation` and nothing else, and no MCP tool list
is reachable from either. Rather than leave the check "degraded to unvalidated",
this speaks MCP to the container directly.

That turns out to be the better place for it. The handshake happens before the
agent is constructed, so a wrong tool name costs a subprocess and a second,
rather than a model call and a retry at full context.
"""

from __future__ import annotations

import json
import shutil
import subprocess

PROTOCOL_VERSION = "2025-06-18"


class McpUnavailable(RuntimeError):
    """The server could not be reached. Distinct from 'the server disagreed'."""


def _frame(obj: dict) -> str:
    return json.dumps(obj) + "\n"


def list_server_tools(image: str, token: str, timeout: int = 60) -> list[str]:
    """Return the tool names the MCP server advertises.

    Speaks the three-message stdio handshake: initialize, the initialized
    notification, then tools/list. Raises `McpUnavailable` when docker is
    missing or the server never answers — a missing runtime is a different
    problem from a mismatched allowlist, and conflating them would turn a
    laptop without docker into a false failure.
    """
    if shutil.which("docker") is None:
        raise McpUnavailable("docker is not on PATH")

    payload = (
        _frame(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "antigravity-code-review", "version": "0"},
                },
            }
        )
        + _frame({"jsonrpc": "2.0", "method": "notifications/initialized"})
        + _frame({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    )

    try:
        result = subprocess.run(
            [
                "docker",
                "run",
                "-i",
                "--rm",
                "-e",
                f"GITHUB_PERSONAL_ACCESS_TOKEN={token}",
                image,
            ],
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise McpUnavailable(f"{image} did not answer within {timeout}s") from exc

    names: list[str] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue
        tools = (message.get("result") or {}).get("tools")
        if tools:
            names.extend(t.get("name", "") for t in tools if t.get("name"))

    if not names:
        raise McpUnavailable(
            f"{image} advertised no tools (exit {result.returncode}): {result.stderr.strip()[:200]}"
        )
    return sorted(set(names))
