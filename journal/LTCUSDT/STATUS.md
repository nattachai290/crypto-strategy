# LTCUSDT - status

> **PLAN.md §26 (Exp 001): this coin was SKIPPED, no evaluation was run.**
> `SYMBOL=LTCUSDT python src/datafeed.py --tfs 15,30,60,240` printed
> **`VALIDATION: PROBLEMS FOUND`** - all four timeframes carry **2 gaps longer than
> 3x the bar interval**, all months present, 0 duplicates. Per the owner's rule
> the coin is recorded, skipped, and **counts as a failure** in the pre-registered
> bars; no threshold was changed and no data was repaired. **`premium_confirm.py`
> -> `NOT_CONFIRMED`.** Details: `journal/_multi/experiments.md` Exp 011.

**Added 2026-10-02 (PLAN.md section 26, owner-approved) only to confirm the
Coinbase premium idea `057_coinbase_premium_follow` on a coin it has never
seen.** No other idea is to be run on this coin without a new plan.

- Data: `SYMBOL=LTCUSDT python src/datafeed.py --tfs 15,30,60,240`, then
  `SYMBOL=LTCUSDT python src/datafeed.py --premium`.
- Runs: the four 057 files, then `baseline.py` on the 30m and 4h rows.
- Pooled verdict: `python src/premium_confirm.py` (journal/_multi/premium_confirm.md).
