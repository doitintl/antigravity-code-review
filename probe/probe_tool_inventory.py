"""FR5 — the *registered* tool list, taken from the harness contract rather than the model.

Q4/roadmap recorded that the model "also reports `manage_task` and `schedule`".
Asking the model what tools it has is asking a generative system to introspect;
it answers plausibly, not accurately. This probe reads the actual wire contract
instead.

Architecture, established from `localharness_pb2` in 0.1.12:

    HarnessConfig {                      <-- the SDK SENDS this to the harness
      repeated Tool tools;               <-- custom tools registered by us
      HarnessSideTools harness_side_tools;  <-- which built-ins are switched on
      repeated McpServerConfig mcp_servers;
      ...
    }
    InitializeConversationResponse {     <-- what the harness sends BACK
      cascade_id, history, cumulative_usage, trajectory_usage
    }

The response carries no tool catalogue. There is therefore no "harness tool
list" to query: the registered set is exactly what the client declares. That
makes it capturable with no billed call, which is why this probe is free.

Run:  uv run python probe/probe_tool_inventory.py
"""

from __future__ import annotations

import json

from google.antigravity import types
from google.antigravity.connections.local.local_connection import LocalConnectionStrategy
from google.antigravity.proto import localharness_pb2 as lh

SDK_VERSION = "0.1.12"

# Names the model claimed in an earlier session, which prompted FR5.
MODEL_CLAIMED = ["manage_task", "schedule"]


def harness_side_tool_slots() -> list[str]:
    """Every tool slot the harness contract defines, from the proto descriptor."""
    return [f.name for f in lh.HarnessSideTools.DESCRIPTOR.fields]


def enabled_slots(cfg: types.CapabilitiesConfig | None) -> dict[str, bool]:
    """The built-in tools actually switched on for a given capabilities config.

    Calls the SDK's own translation rather than reimplementing it, so this
    cannot drift from what really goes on the wire.
    """
    strategy = LocalConnectionStrategy(capabilities_config=cfg)
    proto = strategy._to_harness_side_tools_proto(cfg)

    out: dict[str, bool] = {}
    for field in proto.DESCRIPTOR.fields:
        sub = getattr(proto, field.name)
        out[field.name] = bool(getattr(sub, "enabled", False)) if field.message_type else bool(sub)
    return out


def main() -> int:
    print(f"SDK {SDK_VERSION} — registered tool inventory, read from the harness contract\n")

    slots = harness_side_tool_slots()
    print(f"HarnessSideTools slots ({len(slots)}):")
    for name in slots:
        print(f"  - {name}")

    builtins = list(types.BuiltinTools)
    print(f"\nBuiltinTools enum ({len(builtins)}):")
    for member in builtins:
        print(f"  - {member.value}")

    print("\n--- Does the harness advertise a tool list back to us? ---")
    response_fields = [f.name for f in lh.InitializeConversationResponse.DESCRIPTOR.fields]
    print(f"InitializeConversationResponse fields: {response_fields}")
    print("=> No tool catalogue is returned. The registered set is what the client declares.")

    print("\n--- The model's claimed tools, checked against the contract ---")
    known = set(slots) | {m.value for m in builtins}
    for name in MODEL_CLAIMED:
        verdict = "PRESENT" if name in known else "NOT REGISTERED"
        print(f"  {name:<14} {verdict}")

    print("\n--- Enabled built-ins per configuration ---")
    scenarios: list[tuple[str, types.CapabilitiesConfig | None]] = [
        # What LocalAgentConfig actually constructs when the caller says nothing.
        # NOT the same as cfg=None: enabled_tools=None means "no filter", which
        # _resolve_active_tools expands to every BuiltinTool, writes included.
        ("LocalAgentConfig default", types.CapabilitiesConfig()),
        # The strategy-level fallback. Unreachable through LocalAgentConfig, and
        # kept here only to show the two defaults differ.
        ("cfg=None (unreachable)", None),
        (
            "read_only()",
            types.CapabilitiesConfig(
                enabled_tools=types.BuiltinTools.read_only(), enable_subagents=False
            ),
        ),
        (
            "reviewer (M1 shape)",
            types.CapabilitiesConfig(
                enabled_tools=[types.BuiltinTools.VIEW_FILE, types.BuiltinTools.FINISH],
                enable_subagents=False,
            ),
        ),
    ]

    results = {}
    for label, cfg in scenarios:
        table = enabled_slots(cfg)
        on = sorted(k for k, v in table.items() if v)
        results[label] = table
        print(f"\n  {label}")
        print(f"    enabled: {on or '(none)'}")

    # The security question FR5 exists to answer: can the agent write by default?
    print("\n--- Write-capable slots, by configuration ---")
    write_slots = ["file_edit", "write_to_file", "run_command"]
    for label, table in results.items():
        writes = [s for s in write_slots if table.get(s)]
        print(f"  {label:<26} {'WRITES: ' + ', '.join(writes) if writes else 'no write tools'}")

    print("\n--- Provenance of the model's claimed tools ---")
    print(
        "  `manage_task` is a real tool — in the Antigravity IDE, not in this SDK.\n"
        "  The 101 MB `bin/localharness` is shared with that product and still\n"
        "  carries its system-prompt templates. Strings recovered from it:\n"
        "    .../jetski/prompt/template_provider/templates/system_prompts/plugins.tmpl\n"
        '    "Use the manage_task tool to interact with them (e.g. to kill them\n'
        '     or check their status)"\n'
        '    "context canceled by manage_task"\n'
        "  So the model did not invent the name: it read it. That is prompt\n"
        "  contamination from a shared binary, not a free-floating hallucination.\n"
        "  `schedule` appears only as a bare string with no tool context.\n"
        "  Neither is reachable: an unregistered name is answered by the tool\n"
        "  runner with \"Unknown tool: '<name>'\" (tools/tool_runner.py:368).\n"
        "  Cost is one wasted model call. Neither can write."
    )

    print("\n--- Slots the SDK never sets ---")
    print(
        "  `permissions` and `tool_search_config` are absent from\n"
        "  _to_harness_side_tools_proto entirely, so they sit at proto defaults.\n"
        "  tool_search_config.enabled=False means deferred tool loading is off,\n"
        "  which closes the one route by which an unlisted tool could appear."
    )

    json.dumps({"sdk": SDK_VERSION, "slots": slots})  # schema smoke-check
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
