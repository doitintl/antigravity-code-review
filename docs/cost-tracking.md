# Cost tracking

The requirement: **know what every pull request review cost, and be able to stop one that is running away.**

This is not a reporting nicety. A pull-context reviewer makes many model calls, so it is inherently more expensive per review than a single-shot one. A tool that cannot answer "what did this cost" is hard to defend when someone reviews the spend, and "it's cheap" is not an answer anybody has to accept.

## Two sources, deliberately

**Source 1 — the SDK, per run.** Immediate, free, and attributable to a specific PR.

**Source 2 — Cloud Billing, per request.** Authoritative, delayed by hours, and attributable only if the requests were labelled.

They are both implemented because each covers the other's weakness. If they disagree by more than a small margin, the rate table is wrong or requests are going unlabelled — and either is worth knowing.

## Source 1: `Conversation.total_usage`

The SDK accumulates usage across a whole conversation and exposes it as a `UsageMetadata`:

| field | meaning |
|---|---|
| `prompt_token_count` | input tokens |
| `cached_content_token_count` | the cached **subset of** prompt tokens |
| `candidates_token_count` | output tokens, excluding reasoning |
| `thoughts_token_count` | reasoning tokens |
| `total_token_count` | prompt + candidates + thoughts |
| `service_tier` | e.g. standard, priority |

Two of these are where cost estimates usually go wrong, and both errors flatter the tool:

**Cached input is not free.** It bills at a fraction of the input rate — currently a tenth. A review that is 99% cache hits is *cheaper*, not free. Treating cached tokens as zero can understate a review by an order of magnitude, and it makes total context size look irrelevant when it is in fact the main driver.

**Reasoning tokens bill at the output rate.** They are reported separately from `candidates_token_count`, so a naive sum of "input + output" misses them entirely on any model that thinks.

Note also that `cached_content_token_count` is a **subset of** `prompt_token_count`, not an addition to it. The uncached portion is the difference.

```python
usage = conversation.total_usage

cached   = usage.cached_content_token_count or 0
uncached = (usage.prompt_token_count or 0) - cached
output   = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)

cost = (
    uncached / 1e6 * rate.input
    + cached / 1e6 * rate.input * rate.cache_read_multiplier
    + output  / 1e6 * rate.output
)
```

### Two traps the SDK documents and it would be easy to miss

🔴 **A failed run reports zero tokens.** The SDK's observability guide states plainly that if agent execution fails — a bad key, a backend error — usage counts *"may be reported as 0"*. So the failure mode of this cost tracker is **silently reporting $0.00 for a run that consumed real tokens before dying**, which understates spend in exactly the situation where someone is investigating a spike. Treat a zero-token completed run as **suspect, not free**: record it as `null` with a reason rather than `0.0`, and let reconciliation against billing be the arbiter.

⚠️ **Thinking tokens move the total unpredictably.** Also from the SDK's own guide: they *"can significantly increase the total count unexpectedly"*. They bill at the output rate and are reported separately, so any estimate that sums only prompt and candidates will be wrong, and wrong in the direction that flatters the tool.

### Accumulate per turn, do not read the total at the end

`Conversation.total_usage` is the obvious call and it is the wrong one to rely on alone. Read `response.usage_metadata` after every turn and keep the running total yourself. Three reasons, each independent:

**It survives a failure.** A run that dies reports zero, per the caution above. A per-turn tally still holds everything spent up to the last completed turn, which is a far better answer than `null` and a much better one than `0.00`.

**`service_tier` is per request, not per session.** Priority-tier requests bill at a higher rate, and the SDK's own guidance is that overflow traffic is *gracefully downgraded* to standard and billed at standard rates. So a session can straddle two price points, and a single session-level tier cannot express that. **Price each turn at the tier it reports**, not the tier that was configured — the configured one is a request, not a receipt.

**Compaction is visible only turn by turn.** See below.

### Compaction is the cache-rate story

The `Conversation` manages **context compaction**, and the SDK exposes `@hooks.on_compaction` for it. Compaction matters more to this project than to most:

- it is an extra model call over the accumulated history, billed and easy to mistake for a review turn;
- it **rewrites the prompt prefix**, so the cached prefix stops matching and the following turns pay full input rate again.

A pull-context reviewer is exactly the shape that triggers it — many turns, each appending file contents. So a compaction is very likely *the* explanation when the cache rate in the PR comment comes back low, and without the hook the number is a mystery that invites a wrong fix. Register it, count compactions, and put the count in `review-cost.json` next to the cache rate it explains.

### The model has to be pinned, and that is a deliberate exception

The SDK's configuration guidance is explicit: *"Avoid setting the model explicitly unless requested. It is generally better to leave the model unset to use the default behavior."*

**This project sets it anyway, and the reason is this document.** Pricing requires knowing the rate, the rate depends on the model, and **the SDK does not report which model actually served a request** — `UsageMetadata` carries token counts and a service tier, not a model identifier. Leave the model unset and you get tokens you cannot price.

So the model is pinned, recorded in `review-cost.json` alongside the figure, and treated as part of the cost contract rather than a tuning knob. Where the identifier itself comes from matters too: the same guidance says never to guess model names or assume they follow a pattern, so the rate table's keys are copied from published pricing rather than inferred.

Worth noting how small the exception actually is: the pinned default, `gemini-3.7-flash`, **is the SDK's own documented default model**. Pinning it changes no behaviour at all. It changes only whether the rate is knowable, which is the entire point.

### The rate table

Rates are data, not comments, and carry an expiry:

```python
RATES = {
    "gemini-3.7-flash": Rate(
        input=1.50, output=7.50,          # per million tokens, standard tier
        promo=Promo(input=0.75, output=3.75, ends_after="2026-12-31"),
        cache_read_multiplier=0.1,
    ),
}
```

Three rules the table enforces:

1. **An unknown model reports tokens and no cost.** It never borrows a neighbouring model's rate. A missing number is obvious; a wrong one is invisible and gets quoted in meetings.
2. **A time-boxed introductory rate has an end date in the data.** Hardcoding the promotional rate overstates savings the day it lapses; hardcoding the standard rate overstates cost while it runs. With the date present, the figure is right on both sides of it and the report says which rate was applied and when it changes.
3. **The output includes caveats**, such as cache *storage* being billed per token-hour and not counted here.

Rates are overridable for negotiated or non-standard pricing, because a published list price is not what every organisation pays.

## Source 2: billing labels

Vertex AI accepts labels on generation requests. Labelling every request with the PR that caused it makes Cloud Billing itself the ledger:

```python
labels = {
    "app": "antigravity-code-review",
    "repo": "owner_name",     # sanitised: lowercase, [a-z0-9_-], truncated
    "pr": "1234",
}
```

Labels have a restricted syntax (lowercase letters, digits, underscores and hyphens, bounded length), so values must be sanitised rather than passed through. An invalid label rejects the request — a cost feature must never be the reason a review fails, so sanitisation failures drop the label and continue.

Then, from the billing export:

```sql
SELECT
  (SELECT value FROM UNNEST(labels) WHERE key = 'repo') AS repo,
  (SELECT value FROM UNNEST(labels) WHERE key = 'pr')   AS pr,
  ROUND(SUM(cost), 4) AS usd
FROM `PROJECT.DATASET.gcp_billing_export_v1_XXXXXX`
WHERE service.description = 'Vertex AI'
  AND DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY repo, pr
ORDER BY usd DESC
```

**This is also why the authentication choice matters.** Because the action authenticates via WIF into a project rather than using a shared API key, each repository's reviews are billed to that repository's own project *by construction*. There is no key to mint, scope or rotate, and no shared bill to apportion afterwards.

Caveat worth stating plainly: labels are only as good as their coverage. If any code path issues an unlabelled request, that spend silently leaves the report. The reconciliation check below is what catches it.

## The budget: dollars on top of the SDK's tokens

**The SDK already enforces budgets.** `BudgetConfig` caps a session declaratively:

| field | caps | scope |
|---|---|---|
| `max_model_calls` | model invocations | session |
| `max_tool_calls` | tool invocations | session |
| `max_input_tokens` | **net uncached** input (prompt minus cached) | **evaluated proactively before each dispatch** |
| `max_output_tokens` | generated tokens, candidate **and** thinking | cumulative |
| `max_total_tokens` | net uncached input + output | cumulative |

When one trips, the session stops and the response carries a typed `StopReason` — `MAX_TOTAL_TOKENS_EXCEEDED`, `MAX_MODEL_CALLS_EXCEEDED`, and so on.

🔴 **The scope column is where an earlier draft of this document was wrong, and the error was load-bearing.** It treated `max_input_tokens` as a session total and built the dollar ceiling on it. The SDK describes it as *"evaluated proactively before dispatch"*, computing net uncached prompt tokens for **that request**, while only `max_output_tokens` and `max_total_tokens` are described as tracking cumulative consumption. A per-request cap does not bound a session: twenty turns at 90k net input each never trip a 100k limit, and the ceiling silently fails to hold for the exact workload this project exists to bound. Confirm the scope of all three in M0 before trusting any of them.

That correction turns out to be a gift. `max_input_tokens` is *better* as a per-dispatch cap than it was as a session one, because a single oversized prompt is precisely the failure this project set out to avoid — the 2.9 MB OpenAPI file in [`design.md`](design.md) is one dispatch, not twenty. So it becomes the cliff guard, and the cumulative dials carry the budget.

**Do not write a hook for this.** An earlier draft of this document proposed a `pre_turn` hook computing cost and calling `stop()`. That was reinventing `BudgetConfig`, worse: it checks only between turns, it has no typed stop reason, and it would have to reimplement the net-uncached arithmetic the SDK already does correctly.

**What is missing is the unit.** `BudgetConfig` counts tokens. People budget in money, and a token ceiling is not portable across models: 200k tokens is a different amount of money on Flash than on Pro, and it changes again when a promotional rate lapses. So this project's contribution is a translation layer:

```python
def budget_for(max_cost_usd: float, model: str, output_ratio: float = 0.05) -> BudgetConfig:
    """Turn a dollar ceiling into the SDK's token limits.

    output_ratio is the share of the ceiling reserved for output. It decides how
    the budget is *split*, not whether it holds — see the arithmetic below.
    """
    rate = effective_rate_for(model)

    out_tokens = max_cost_usd * output_ratio       / rate.output * 1e6
    in_tokens  = max_cost_usd * (1 - output_ratio) / rate.input  * 1e6

    return types.BudgetConfig(
        # cumulative, and the ceiling that actually binds
        max_total_tokens=int(out_tokens + in_tokens),
        # cumulative, and includes thinking tokens
        max_output_tokens=int(out_tokens),
        # per-dispatch: refuse one oversized prompt, unrelated to the budget
        max_input_tokens=SINGLE_PROMPT_CAP,
        # a stuck loop is cheap per turn and still unbounded
        max_model_calls=MAX_CALLS,
        max_tool_calls=MAX_TOOL_CALLS,
    )
```

**The pair is a real bound, and the split does not have to be right for it to hold.** Output is capped at `out_tokens`, and the total at `out_tokens + in_tokens`, so the most expensive session the SDK will permit spends `out_tokens` at the output rate and the remaining `in_tokens` at the input rate — exactly `max_cost_usd`. A wrong `output_ratio` wastes headroom on one dial while the other stops the run early; it does not let the run exceed the ceiling. That property is worth more than a well-tuned guess.

Two details keep it honest rather than approximate:

**The token dials count net uncached input**, which is the cost-relevant quantity. A cheaper cached read does not consume the budget at the same rate as a fresh one, which is exactly right and is not something a naive token counter would get correct.

**Cached reads still cost something** while consuming no net input, so a session running almost entirely on cache hits spends a little more than the arithmetic above allows. The dollar ceiling is therefore a **near-bound, not a hard bound**, and is documented as such. The reported figure from Source 1 remains the accurate one.

### The retry budget nobody counts

Two SDK defaults spend money without appearing anywhere in the design above:

- **API retries** — 2 by default, on 429s, 5xx and dropped connections, with exponential backoff.
- **Model output retries** — **4 by default**, when the model emits a malformed tool call or output that fails `response_schema` validation.

The second is the one that matters here. A schema violation on the final turn re-prompts the model at full context up to four more times, so **the most expensive turn of a review is also the one most likely to be billed five times**. That is invisible in a design that reasons about turns, and it interacts badly with a dollar ceiling.

```python
retry_config=types.RetryConfig(
    model_output_retry=types.ModelOutputRetryConfig(max_retries=1),
)
```

Whether those retries count against `BudgetConfig`'s dials is unverified and belongs in M0. **Never use `RetryConfig.benchmark()` here** — it is an unbounded-API-retry preset intended for load tests, and unbounded is the opposite of what a cost-capped CI job wants. Retry counts belong in `review-cost.json` for the same reason token counts do.

### Reporting the stop

Whatever stops the run must be visible:

- the PR comment names the reason in plain words, not the enum
- `review-cost.json` records `stop_reason` verbatim
- a stop is **not** a workflow failure. A partial review is a result, not an error

A partial review presented as complete is the same failure class as a silently truncated file.

## Outputs

**On the PR**, one line, always present:

```
Reviewed in 14 model calls · 128,400 in (92% cached) · 8,100 out · ~$0.0412
```

Cache rate is included because it is the single most actionable number: a low hit rate on a repeated review usually means volatile content early in the prompt.

**As an artifact**, `review-cost.json`:

```json
{
  "repo": "owner/name",
  "pr": 1234,
  "model": "gemini-3.7-flash",
  "turns": 14,
  "tool_calls": 31,
  "tokens": {
    "prompt": 128400, "cached": 118100,
    "candidates": 6200, "thoughts": 1900, "total": 136500
  },
  "service_tiers": {"standard": 14},
  "compactions": 1,
  "retries": {"api": 0, "model_output": 2},
  "cost_usd": 0.0412,
  "rate_applied": "introductory",
  "budget_usd": 0.50,
  "stop_reason": null,
  "caveats": ["cache storage is billed per token-hour and is not included"]
}
```

Machine-readable so it can be aggregated without scraping comments.

## Reconciliation

A scheduled job compares the sum of `cost_usd` from artifacts against the billing export for the same window and flags drift beyond a threshold. This is the check that catches an unlabelled code path, a stale rate, or a promotional rate that expired while nobody was looking.

Reporting on your own cost without an independent check is how a number that everyone quotes turns out to have been wrong for a month.

## What is deliberately not claimed

- **Cache storage** is billed per token-hour and is not included in the per-run figure. Runs on infrequently reviewed repositories therefore read slightly low.
- **The figure is an estimate** until it appears in the billing export. Presented as such.
- **Cost per review is not cost per outcome.** The number that justifies a reviewer is cost per *acted-on finding*, and that requires tracking which comments were resolved rather than dismissed. Out of scope for the first release, but it is the metric that matters, and it is worth saying so rather than letting a cheap-per-review figure stand in for value.
