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

## The budget guard

Measuring is not enough. A `pre_turn` hook checks accumulated cost before each turn:

```python
async def budget_guard(ctx):
    cost = price(ctx.conversation.total_usage, model)
    if cost.total >= MAX_COST_USD:
        await post_summary(
            f"⚠️ Review stopped at the cost ceiling "
            f"(${cost.total:.4f} of ${MAX_COST_USD:.2f}). "
            f"Findings so far are below. Re-run with a higher ceiling for a full pass."
        )
        return ctx.stop()
```

Design points:

- **Stop, do not silently truncate.** The PR comment says the review was cut short. A partial review presented as complete is the same failure class as a silently truncated file.
- **Findings already posted survive**, because they were emitted through tools as the agent worked rather than held to the end.
- **A ceiling is per PR, not per turn.** Runaway loops are the thing being defended against, and they look normal one turn at a time.
- **Default it generously and log the distribution.** Set too tight, it becomes a source of mysteriously incomplete reviews.

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
  "cost_usd": 0.0412,
  "rate_applied": "introductory",
  "budget_usd": 0.50,
  "stopped_on_budget": false,
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
