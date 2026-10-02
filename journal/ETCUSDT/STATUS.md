# ETCUSDT - status

> **Coinbase premium on ETCUSDT (PLAN.md §26, Exp 001): the idea `057`,
> unchanged, at four timeframes. No PASS; nothing goes to `--final`; this coin
> exists only for this test.** `datafeed.py --tfs 15,30,60,240` -> VALIDATION: OK,
> `datafeed.py --premium` -> PREMIUM VALIDATION: OK. `size_skips` 0 on every row.
>
> | tf | verdict | VALID trades | gross_r | cost_r | mean R | 95% CI | long/short | baseline | TRAIN chose |
> |---|---|---|---|---|---|---|---|---|---|
> | 15m | REJECT | 1337 | +0.0932 | 0.1043 | **-0.0111** | [-0.0733, +0.0522] | 675/662 | - | z 1.5 / n 72 / 2R |
> | 30m | REJECT | 727 | -0.0134 | 0.0718 | **-0.0852** | [-0.1795, +0.0109] | 371/356 | DRIFT | z 1.5 / n 72 / 4R |
> | 60m | REJECT | 365 | +0.0412 | 0.0494 | **-0.0082** | [-0.1424, +0.1295] | 186/179 | - | z 1.5 / n 336 / 4R |
> | 240m | WATCH | 97 | +0.1800 | 0.0314 | **+0.1486** | [-0.1227, +0.4361] | 55/42 | DRIFT | z 1.5 / n 72 / 4R |
>
> **This coin:** a 4h WATCH with a CI wide enough to straddle 0, and a negative book at every faster clock. Worth knowing: gross +0.1800 at 4h against cost 0.0314 - structure without an edge.
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

- Data: `SYMBOL=ETCUSDT python src/datafeed.py --tfs 15,30,60,240`, then
  `SYMBOL=ETCUSDT python src/datafeed.py --premium`.
- Runs: the four 057 files, then `baseline.py` on the 30m and 4h rows.
- Pooled verdict: `python src/premium_confirm.py` (journal/_multi/premium_confirm.md).
