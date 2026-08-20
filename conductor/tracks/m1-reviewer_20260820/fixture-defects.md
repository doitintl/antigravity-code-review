# Planted defects — fixture PR

**Repository:** `SaschaHeyer/agy-review-fixture` (private)
**Pull request:** [#1 — Add transfers between accounts](https://github.com/SaschaHeyer/agy-review-fixture/pull/1)

⚠️ **This inventory lives here, not in the fixture repository.** A first version
committed it to the PR branch, where it appeared in the changed-file list — the
reviewer could simply have read the answers and parroted them back. The exit
criterion would then have measured nothing. It was removed from the branch; the
net diff is `src/payments/transfers.py` and `src/payments/rates.generated.json`
only.

Inventory for the reviewer fixture. A review is judged on how many of these it
names, not on general impressions.

| # | File | Line area | Defect | Severity |
|---|---|---|---|---|
| 1 | `src/payments/transfers.py` | `PAYMENTS_API_KEY` | Hardcoded live-looking API key committed to source | critical |
| 2 | `src/payments/transfers.py` | `record_transfer` | SQL injection — query built with `%` string formatting on caller input | critical |
| 3 | `src/payments/transfers.py` | `transfer` | Money handled as `float`; the rest of the codebase uses `Decimal` | high |
| 4 | `src/payments/transfers.py` | `transfer` | No balance check — debits past zero, bypassing `Ledger.debit`'s overdraft guard | high |
| 5 | `src/payments/transfers.py` | `transfer` | Reaches into `ledger._balances` private state instead of the public API | medium |
| 6 | `src/payments/transfers.py` | `except Exception: pass` | Audit failure silently swallowed; the transfer still reports success | high |
| 7 | ~~`src/payments/transfers.py`~~ | ~~`transfer`~~ | ~~Always returns `True`~~ — **NOT A VALID DEFECT. Unreachable:** `Decimal - float` raises `TypeError` first, so `return True` never executes. Shadowed by defect 3. Found 0/8 times, correctly | ~~medium~~ |
| 8 | — | `src/payments/rates.generated.json` | Large generated file (>128 KB) — exercises the `view_file` byte cap, not a defect to report | n/a |

**8 is not a defect.** It is there so the truncation path is exercised by a real
pull request. A reviewer that spends the review complaining about a generated
data file is itself a finding.


## Reachability

Defect 7 was planted and is not reachable. `transfer()` raises `TypeError` on
every call before it can return, so a reviewer that does not report the return
value is triaging correctly rather than missing something.

**Check reachability before counting a defect as planted.** A fixture that
scores a correct decision as a failure produces numbers that look like evidence.
Verified by running the fixture:

```
transfer RAISED TypeError: unsupported operand type(s) for -: 'decimal.Decimal' and 'float'
```

Six defects are reachable. Score against six.
