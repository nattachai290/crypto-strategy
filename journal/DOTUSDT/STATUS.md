# DOTUSDT - status

> **Coinbase premium on DOTUSDT (PLAN.md §26, Exp 001): the idea `057`,
> unchanged, at four timeframes. No PASS; nothing goes to `--final`; this coin
> exists only for this test.** `datafeed.py --tfs 15,30,60,240` -> VALIDATION: OK,
> `datafeed.py --premium` -> PREMIUM VALIDATION: OK. `size_skips` 0 on every row.
>
> | tf | verdict | VALID trades | gross_r | cost_r | mean R | 95% CI | long/short | baseline | TRAIN chose |
> |---|---|---|---|---|---|---|---|---|---|
> | 15m | REJECT | 1095 | +0.1069 | 0.1006 | **+0.0063** | [-0.0706, +0.0874] | 527/568 | - | z 1.5 / n 336 / 4R |
> | 30m | REJECT | 342 | +0.0632 | 0.0651 | **-0.0019** | [-0.1370, +0.1365] | 170/172 | DRIFT | z 2.5 / n 72 / 4R |
> | 60m | WATCH | 403 | +0.0881 | 0.0486 | **+0.0396** | [-0.0873, +0.1695] | 188/215 | - | z 1.5 / n 72 / 4R |
> | 240m | INCONCLUSIVE | 115 | +0.0647 | 0.0247 | **+0.0400** | [-0.1676, +0.2560] | 57/58 | DRIFT | z 1.5 / n 72 / 2R |
>
> **This coin:** 4h INCONCLUSIVE (0 eligible TRAIN cells); the premium does nothing here. Worth knowing: every 4h number sits inside its own CI.
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

- Data: `SYMBOL=DOTUSDT python src/datafeed.py --tfs 15,30,60,240`, then
  `SYMBOL=DOTUSDT python src/datafeed.py --premium`.
- Runs: the four 057 files, then `baseline.py` on the 30m and 4h rows.
- Pooled verdict: `python src/premium_confirm.py` (journal/_multi/premium_confirm.md).
