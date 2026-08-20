"""Ask the GitHub MCP server what it actually offers, before the agent starts.

FR7 wanted the configured tool names validated against the server's `tools/list`.
The SDK exposes no surface for that — `Agent` offers `chat` and `conversation`
and nothing else — so this speaks MCP to the container directly, using the `mcp`
client library the SDK already depends on.

Doing it here rather than inside the agent is the better trade: the handshake
happens before the `Agent` is constructed, so a wrong tool name costs a
subprocess and a few seconds instead of a model call and a retry at full context.

A hand-rolled JSON-RPC version of this failed in a way worth recording. Writing
all three frames and closing stdin makes the server exit before it answers, and
the resulting empty output looks exactly like "the server has no tools" — which
sent one investigation off to check whether the pinned image tag existed at all.
It does. Use a real client and hold the stream open.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess


class McpUnavailable(RuntimeError):
    """The server could not be reached. Distinct from 'the server disagreed'.

    A laptop without docker is a different problem from an allowlist that
    disagrees with the server, and conflating them makes a missing runtime look
    like a configuration error.
    """


async def _list_tools(image: str, token: str) -> list[str]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command="docker",
        args=["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN", image],
        env={"GITHUB_PERSONAL_ACCESS_TOKEN": token},
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.list_tools()
        return sorted(t.name for t in result.tools)


def list_server_tools(image: str, token: str, timeout: int = 120) -> list[str]:
    """Return the tool names the MCP server advertises."""
    if shutil.which("docker") is None:
        raise McpUnavailable("docker is not on PATH")

    # Pull explicitly. An implicit pull writes its failure to the same stream as
    # the handshake, so a registry problem arrives disguised as a protocol one.
    pull = subprocess.run(
        ["docker", "pull", "--quiet", image],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if pull.returncode != 0:
        raise McpUnavailable(f"could not pull {image}: {pull.stderr.strip()[:300]}")

    try:
        names = asyncio.run(asyncio.wait_for(_list_tools(image, token), timeout=timeout))
    except TimeoutError as exc:
        raise McpUnavailable(f"{image} did not answer within {timeout}s") from exc
    except Exception as exc:
        raise McpUnavailable(f"{image} handshake failed: {type(exc).__name__}: {exc}") from exc

    if not names:
        raise McpUnavailable(f"{image} advertised no tools")
    return names
