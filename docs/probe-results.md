# Probe results

Measured against `google-antigravity==0.1.12`, Vertex, project `sascha-playground-doit`, model `gemini-3.7-flash`, on 2026-08-19. Reproduce with [`probe/probe_offline.py`](../probe/probe_offline.py) and [`probe/probe_live.py`](../probe/probe_live.py).

Total cost of establishing everything below: **under 90k tokens**, roughly **$0.08** at the introductory rate. Every question the plan had been hedging for four revisions, for the price of a cup of nothing.

## The headline: `location` must be `global`

```
404: Publisher model `projects/…/locations/us-central1/publishers/google/models/
gemini-3.7-flash` was not found or your project does not have access to it.
```

`us-central1` does not serve this model; `global` does. The plan's config sketches all passed a regional location, and the roadmap's M0 checklist would have chased a credentials bug for an hour before finding it. **ADC itself worked on the first attempt** — that 404 is an availability error from a successfully authenticated call, which is most of Q1 answered: the SDK does acquire ADC headlessly from a non-interactive process. Only the WIF token exchange inside a runner remains unproven.

## The tool surface has a floor, and it is not small

| configuration | prompt tokens, first turn |
|---|---|
| default (all built-in tools) | **10,889** |
| `enabled_tools=[VIEW_FILE, FINISH]` | **4,470** |

The prompt in both cases was three words. **Trimming the tool list removed 6,419 tokens from every single turn — a 59% cut to the per-turn floor.**

Put that against a fourteen-turn review: roughly 90k tokens of pure tool-schema scaffolding, on a review whose own content might be 130k. The capability layer was argued for on principle in [`design.md`](design.md); it is now the largest single cost lever the project has actually measured, ahead of anything in the pricing table.

The corollary is less comfortable: **a bare "Say OK." costs ~11k input tokens.** Any per-review cost model that reasons from content size alone will understate by that floor times the turn count.

## 🔴 There are tools you cannot see and cannot switch off

With `enabled_tools=[VIEW_FILE, FINISH]`, the model was asked to name every tool it could call. It answered:

```
manage_task, schedule, view_file
```

`manage_task` and `schedule` are **not members of `BuiltinTools`**, are not named anywhere in the SDK's documentation, and were not requested. `enabled_tools` is an allowlist over the documented enum only; the harness injects its own tools underneath it.

This matters twice over:

- **The read-only claim is narrower than stated.** `manage_task` plausibly writes the `task.md` artifact the SDK stores under `app_data_dir`, and `schedule` plausibly relates to triggers. Neither was audited, neither can be denied by name through `enabled_tools`, and the security posture in [`design.md`](design.md) does not account for them. A `policy.deny_all()` floor still covers them at the policy layer — which is now the *only* thing that covers them, and is the argument for keeping layer 2 even though layer 1 is stronger.
- **`finish` did not appear** in the model's own list despite being enabled, so the list is the model's report rather than ground truth. Treat it as evidence, not as an inventory.

Worth an explicit M0 task: get the real registered tool list out of the harness rather than out of the model.

## `view_file` — contract confirmed

Captured from a real call via a `pre_tool_call_decide` hook:

```json
{"AbsolutePath": "/tmp/…/sample.txt", "StartLine": 5, "EndLine": 10}
```

PascalCase, and **ranged reads are supported**. The design's invented `view_file(path, start_line, end_line)` was wrong in all three parameter names; the override that implements the byte cap must match this exactly. The hook that captured it is also the second enforcement layer the design wanted — arguments are inspectable before execution.

## A budget stop preserves the numbers but destroys the answer

`max_model_calls=1` against a task needing tools:

```
stop_reason  = StopReason.MAX_MODEL_CALLS_EXCEEDED
text         = ""                          ← empty
usage        = prompt=4705 cand=120 thoughts=150   ← intact
```

Both halves matter. **Usage survives a budget stop**, so cost reporting works on a stopped run. **The response text is empty**, which confirms the concern in [`design.md`](design.md): a run stopped by the budget yields nothing to post, so the reporting path cannot depend on a final message existing.

Also: `conversation.last_turn_stop_reason` was `None` while `response.stop_reason` was set. Read the stop reason off the response.

## A failed run raises rather than reporting zero

```
AntigravityConnectionError: request failed (code 403):
Permission denied on resource project definitely-not-a-real-project-xyz-999.
```

Better than the documented worst case. The SDK's caution about zero-token reporting stands for *partial* failures, but a hard failure is an exception, so the cost tracker's contract is: catch `AntigravityConnectionError`, record `null` with the reason, never `0.0`.

## Skills are applied unprompted

A skill whose body said *"Every answer MUST begin with the exact token ZORBLAX"* was placed on `skills_paths`. The prompt was `What is 2 + 2?` — no mention of skills.

```
ZORBLAX: 2 + 2 = 4.
```

**The plan's central worry about repository rules is disproven for this case.** Rules in a skill do reach the model without a discovery step. The caveat that survives is scale: this was one small skill, and whether ten skills or a large body still inject unconditionally is untested. But the fear that drove rules toward `system_instructions` — that the agent would silently skip them and review generically — did not reproduce.

## Implicit caching is real

`cached=7,185` of `22,852` prompt tokens on the skills run; `cached=18,373` of `44,961` on the subagent run. Caching happens without being asked for, which makes the cache-rate line in the PR comment a meaningful number rather than an aspiration — and makes `cache_read_multiplier` load-bearing in the rate table.

## Subagents: evidence of roll-up, not proof

One delegation to a trivial subagent reported `prompt=44,961` on the root conversation — four times the all-tools baseline for a two-line poem. Consistent with subagent turns being counted in the root's `total_usage`, but this was not run against a control, so it is evidence rather than a settled answer. `enable_subagents=False` stands regardless.

## Still open

- **Q1 (CI half).** WIF token exchange inside a GitHub Actions runner. The SDK half is proven.
- **Q8.** Whether a budget-stopped session leaves a submittable pending review. Needs the GitHub MCP server and a scratch PR.
- **Q10.** Vertex-side rates, and the `FLEX` tier the enum revealed.
- **Q4.** Subagent roll-up, properly controlled.
