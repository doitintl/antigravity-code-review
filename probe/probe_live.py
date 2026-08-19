"""Live Vertex probe. Answers Q4-Q9 with the smallest calls that can settle them.

Each test is isolated: a failure prints and moves on. Every agent gets a tight
BudgetConfig so a misbehaving test cannot run away with the bill.
"""
import asyncio, json, os, sys, tempfile, traceback, pathlib

from google.antigravity import Agent, LocalAgentConfig, types

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "sascha-playground-doit")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
MODEL = "gemini-3.7-flash"

RESULTS = {}
TOTALS = {"prompt": 0, "cached": 0, "cand": 0, "thoughts": 0}


def base(**kw):
    kw.setdefault("budget_config", types.BudgetConfig(
        max_model_calls=6, max_tool_calls=8,
        max_input_tokens=200_000, max_output_tokens=4_000))
    return LocalAgentConfig(
        vertex=True, project=PROJECT, location=LOCATION, model=MODEL, **kw)


def usage_of(agent):
    try:
        return agent.conversation.total_usage
    except Exception:
        return None


def note(u, tag):
    if not u:
        return f"[{tag}] usage=None"
    TOTALS["prompt"] += u.prompt_token_count or 0
    TOTALS["cached"] += u.cached_content_token_count or 0
    TOTALS["cand"] += u.candidates_token_count or 0
    TOTALS["thoughts"] += u.thoughts_token_count or 0
    return (f"[{tag}] prompt={u.prompt_token_count} cached={u.cached_content_token_count} "
            f"cand={u.candidates_token_count} thoughts={u.thoughts_token_count} "
            f"total={u.total_token_count} tier={u.service_tier}")


async def t1_baseline():
    """M0: is total_usage populated on Vertex at all? What tier is reported?"""
    async with Agent(base(system_instructions="Answer in one word.")) as a:
        r = await a.chat("Say OK.")
        txt = await r.text()
        u = usage_of(a)
        RESULTS["T1_baseline"] = {
            "text": txt.strip()[:60],
            "usage": note(u, "T1"),
            "stop_reason": str(getattr(r, "stop_reason", None)),
            "response_usage_metadata_present": getattr(r, "usage_metadata", None) is not None,
            "service_tier": str(getattr(u, "service_tier", None)),
        }


async def t2_tool_registry():
    """Q3 + Q6: what tools are actually registered, and what is view_file's schema?"""
    cfg = base(
        system_instructions="You inspect files.",
        capabilities=types.CapabilitiesConfig(
            enabled_tools=[types.BuiltinTools.VIEW_FILE, types.BuiltinTools.FINISH],
            enable_subagents=False,
        ),
        workspaces=[os.getcwd()],
    )
    async with Agent(cfg) as a:
        found = {}
        for attr in ("tools", "_tools", "tool_registry", "_tool_registry"):
            obj = getattr(a, attr, None)
            if obj is not None:
                found[attr] = str(type(obj))
        # try the conversation too
        conv = getattr(a, "conversation", None)
        for attr in ("tools", "_tools", "tool_schemas", "_tool_schemas"):
            obj = getattr(conv, attr, None)
            if obj is not None:
                found["conversation." + attr] = str(type(obj))
        RESULTS["T2_registry_attrs"] = found

        # Ask the model itself what it can call - definitive for exclusivity
        r = await a.chat("List the exact names of every tool you can call. Names only, comma separated.")
        RESULTS["T2_model_reports_tools"] = (await r.text()).strip()[:400]
        RESULTS["T2_usage"] = note(usage_of(a), "T2")


async def t3_view_file_contract():
    """Q6: call view_file for real and see what parameter names it accepts."""
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "sample.txt"
        p.write_text("\n".join(f"line {i}" for i in range(1, 201)))
        cfg = base(
            system_instructions=(
                "You read files with view_file. When you call it, you MUST report "
                "back the exact JSON arguments you sent."),
            capabilities=types.CapabilitiesConfig(
                enabled_tools=[types.BuiltinTools.VIEW_FILE, types.BuiltinTools.FINISH],
                enable_subagents=False),
            workspaces=[d],
        )
        seen = []

        from google.antigravity.hooks import hooks

        @hooks.pre_tool_call_decide
        async def capture(data):
            seen.append({"name": getattr(data, "name", "?"),
                         "args": str(getattr(data, "args", getattr(data, "arguments", None)))[:400]})
            return types.HookResult(allow=True)

        cfg2 = base(
            system_instructions="You read files with view_file.",
            capabilities=cfg.capabilities, workspaces=[d], hooks=[capture])
        async with Agent(cfg2) as a:
            r = await a.chat(f"Read lines 5 to 10 of {p}. Report what you saw.")
            RESULTS["T3_answer"] = (await r.text()).strip()[:300]
            RESULTS["T3_tool_calls_observed"] = seen
            RESULTS["T3_usage"] = note(usage_of(a), "T3")


async def t4_budget_stop():
    """Q5 + budget behaviour: does a tight max_model_calls stop, and is usage kept?"""
    cfg = LocalAgentConfig(
        vertex=True, project=PROJECT, location=LOCATION, model=MODEL,
        system_instructions="You are verbose and always use tools before answering.",
        capabilities=types.CapabilitiesConfig(
            enabled_tools=[types.BuiltinTools.LIST_DIR, types.BuiltinTools.VIEW_FILE,
                           types.BuiltinTools.FINISH],
            enable_subagents=False),
        workspaces=[os.getcwd()],
        budget_config=types.BudgetConfig(max_model_calls=1, max_output_tokens=2000),
    )
    async with Agent(cfg) as a:
        r = await a.chat("List every directory here, then read three files, then summarise.")
        try:
            txt = (await r.text()).strip()[:200]
        except Exception as e:
            txt = f"<text() raised {type(e).__name__}: {e}>"
        RESULTS["T4_budget_stop"] = {
            "stop_reason": str(getattr(r, "stop_reason", None)),
            "text": txt,
            "usage": note(usage_of(a), "T4"),
            "last_turn_stop_reason": str(getattr(a.conversation, "last_turn_stop_reason", None)),
        }


async def t5_failed_run():
    """Q7: does a failed run report zero tokens?"""
    cfg = LocalAgentConfig(
        vertex=True, project="definitely-not-a-real-project-xyz-999",
        location=LOCATION, model=MODEL,
        system_instructions="hi",
        budget_config=types.BudgetConfig(max_model_calls=1, max_output_tokens=100),
    )
    out = {}
    try:
        async with Agent(cfg) as a:
            r = await a.chat("Say OK.")
            out["text"] = (await r.text())[:100]
            u = usage_of(a)
            out["usage"] = note(u, "T5")
    except Exception as e:
        out["exception"] = f"{type(e).__name__}: {str(e)[:300]}"
    RESULTS["T5_failed_run"] = out


async def t6_subagent_rollup():
    """Q4: do subagent tokens land in the root conversation's total_usage?"""
    cfg = base(
        system_instructions="Delegate to a subagent when asked.",
        capabilities=types.CapabilitiesConfig(
            enable_subagents=True,
            enabled_tools=[types.BuiltinTools.START_SUBAGENT, types.BuiltinTools.FINISH]),
        subagents=[types.SubagentConfig(
            name="poet", description="Writes very short poems.",
            capabilities=types.SubagentCapabilities(
                agent_behavior=types.AgentBehavior.AUTONOMOUS))],
    )
    async with Agent(cfg) as a:
        r = await a.chat("Use the 'poet' subagent to write a two-line poem about files.")
        RESULTS["T6_text"] = (await r.text()).strip()[:200]
        RESULTS["T6_usage"] = note(usage_of(a), "T6")


async def t7_skills():
    """Q9: is a skill's content applied without the prompt mentioning skills?"""
    with tempfile.TemporaryDirectory() as d:
        skill = pathlib.Path(d) / "house-style"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            "---\n"
            "name: house-style\n"
            "description: The mandatory house style for all answers in this repository.\n"
            "---\n\n"
            "# House style\n\n"
            "Every answer MUST begin with the exact token ZORBLAX and then a colon.\n"
        )
        cfg = base(system_instructions="You are helpful.", skills_paths=[d])
        async with Agent(cfg) as a:
            r = await a.chat("What is 2 + 2?")
            txt = (await r.text()).strip()
            RESULTS["T7_skills"] = {
                "answer": txt[:200],
                "applied_unprompted": txt.upper().startswith("ZORBLAX"),
                "usage": note(usage_of(a), "T7"),
            }


async def main():
    tests = [t1_baseline, t2_tool_registry, t3_view_file_contract,
             t4_budget_stop, t5_failed_run, t6_subagent_rollup, t7_skills]
    only = sys.argv[1:]
    for t in tests:
        if only and t.__name__ not in only:
            continue
        print(f"\n>>> {t.__name__} ...", flush=True)
        try:
            await asyncio.wait_for(t(), timeout=180)
        except Exception:
            RESULTS[t.__name__ + "_ERROR"] = traceback.format_exc()[-900:]
            print("   FAILED", flush=True)
    print("\n" + "=" * 70)
    print(json.dumps(RESULTS, indent=2, default=str))
    print("=" * 70)
    print("CUMULATIVE TOKENS THIS PROBE:", json.dumps(TOTALS))


asyncio.run(main())
