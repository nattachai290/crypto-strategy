# LINKUSDT - status

> **Coinbase premium on LINKUSDT (PLAN.md §26, Exp 001): the idea `057`,
> unchanged, at four timeframes. No PASS; nothing goes to `--final`; this coin
> exists only for this test.** `datafeed.py --tfs 15,30,60,240` -> VALIDATION: OK,
> `datafeed.py --premium` -> PREMIUM VALIDATION: OK. `size_skips` 0 on every row.
>
> | tf | verdict | VALID trades | gross_r | cost_r | mean R | 95% CI | long/short | baseline | TRAIN chose |
> |---|---|---|---|---|---|---|---|---|---|
> | 15m | REJECT | 308 | +0.0602 | 0.0778 | **-0.0176** | [-0.1497, +0.1191] | 152/156 | - | z 2.5 / n 336 / 4R |
> | 30m | REJECT | 295 | +0.0281 | 0.0598 | **-0.0317** | [-0.1704, +0.1134] | 162/133 | DRIFT | z 2.5 / n 72 / 4R |
> | 60m | REJECT | 192 | -0.0370 | 0.0429 | **-0.0799** | [-0.2376, +0.0895] | 103/89 | - | z 2.5 / n 72 / 4R |
> | 240m | WATCH | 95 | +0.4664 | 0.0266 | **+0.4398** | [+0.1338, +0.7595] | 51/44 | DRIFT | z 1.5 / n 72 / 4R |
>
> **This coin:** the strongest single 4h book of the confirmation, on 95 VALID trades and a DRIFT control. Worth knowing: its 4h control is DRIFT, so the +0.4398 is drift, not timing.
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

- Data: `SYMBOL=LINKUSDT python src/datafeed.py --tfs 15,30,60,240`, then
  `SYMBOL=LINKUSDT python src/datafeed.py --premium`.
- Runs: the four 057 files, then `baseline.py` on the 30m and 4h rows.
- Pooled verdict: `python src/premium_confirm.py` (journal/_multi/premium_confirm.md).
