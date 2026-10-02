# ALGOUSDT - status

> **Coinbase premium on ALGOUSDT (PLAN.md §26, Exp 001): the idea `057`,
> unchanged, at four timeframes. No PASS; nothing goes to `--final`; this coin
> exists only for this test.** `datafeed.py --tfs 15,30,60,240` -> VALIDATION: OK,
> `datafeed.py --premium` -> PREMIUM VALIDATION: OK. `size_skips` 0 on every row.
>
> | tf | verdict | VALID trades | gross_r | cost_r | mean R | 95% CI | long/short | baseline | TRAIN chose |
> |---|---|---|---|---|---|---|---|---|---|
> | 15m | REJECT | 439 | -0.0098 | 0.0769 | **-0.0867** | [-0.1873, +0.0177] | 221/218 | - | z 2.5 / n 72 / 2R |
> | 30m | WATCH | 264 | +0.1535 | 0.0541 | **+0.0994** | [-0.0666, +0.2712] | 126/138 | DRIFT | z 2.5 / n 72 / 4R |
> | 60m | WATCH | 449 | +0.1312 | 0.0390 | **+0.0922** | [-0.0177, +0.2012] | 217/232 | - | z 1.5 / n 72 / 2R |
> | 240m | REJECT | 102 | +0.0562 | 0.0244 | **+0.0319** | [-0.2257, +0.3055] | 57/45 | DRIFT | z 1.5 / n 72 / 4R |
>
> **This coin:** the weakest admissible 4h coin: +0.0319 with 0% of 2 eligible TRAIN cells positive. Worth knowing: positive at 4h and nothing else survives; the 4h control is DRIFT.
>
> **The round's verdict is `NOT_CONFIRMED`** (`premium_confirm.py`, run once):
> 30m is positive on only 2 of 10 coins with SKILL on 1, against a pre-registered
> bar of 7 and 5; 4h pooled over the 5 admissible coins gives 475 trades, mean
> **+0.2368 R**, weekly-block CI **[+0.1023, +0.3830]**, long **+0.2269** / short
> **+0.2481**, but breadth is 5 against 7 required. 14 of 16 random-entry
> controls are DRIFT. Details: `journal/_multi/experiments.md` Exp 011,
> `journal/_multi/premium_confirm.md`. **Per `PLAN.md` §26 the premium lead is
> closed like `051`: no pooled holdout, and no 057 variant on these coins.**

**Added 2026-10-02 (PLAN.md section 26, owner-approved) only to confirm the
Coinbase premium idea `057_coinbase_premium_follow` on a coin it has never
seen.** No other idea is to be run on this coin without a new plan.

- Data: `SYMBOL=ALGOUSDT python src/datafeed.py --tfs 15,30,60,240`, then
  `SYMBOL=ALGOUSDT python src/datafeed.py --premium`.
- Runs: the four 057 files, then `baseline.py` on the 30m and 4h rows.
- Pooled verdict: `python src/premium_confirm.py` (journal/_multi/premium_confirm.md).
