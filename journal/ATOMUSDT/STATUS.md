# ATOMUSDT - status

> **Coinbase premium on ATOMUSDT (PLAN.md §26, Exp 001): the idea `057`,
> unchanged, at four timeframes. No PASS; nothing goes to `--final`; this coin
> exists only for this test.** `datafeed.py --tfs 15,30,60,240` -> VALIDATION: OK,
> `datafeed.py --premium` -> PREMIUM VALIDATION: OK. `size_skips` 0 on every row.
>
> | tf | verdict | VALID trades | gross_r | cost_r | mean R | 95% CI | long/short | baseline | TRAIN chose |
> |---|---|---|---|---|---|---|---|---|---|
> | 15m | REJECT | 387 | +0.1733 | 0.0883 | **+0.0850** | [-0.0482, +0.2208] | 192/195 | - | z 2.5 / n 336 / 4R |
> | 30m | WATCH | 362 | +0.1628 | 0.0654 | **+0.0973** | [-0.0241, +0.2191] | 186/176 | SKILL | z 2.5 / n 72 / 2R |
> | 60m | REJECT | 243 | +0.1385 | 0.0443 | **+0.0943** | [-0.0564, +0.2479] | 119/124 | - | z 2.5 / n 72 / 2R |
> | 240m | WATCH | 90 | +0.3002 | 0.0249 | **+0.2754** | [+0.0187, +0.5427] | 45/45 | DRIFT | z 1.5 / n 336 / 2R |
>
> **This coin:** the only coin positive at every clock and the only 30m SKILL outside BTC/ETH. Worth knowing: the 4h control is DRIFT and 90 VALID trades is under the 100 floor.
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

- Data: `SYMBOL=ATOMUSDT python src/datafeed.py --tfs 15,30,60,240`, then
  `SYMBOL=ATOMUSDT python src/datafeed.py --premium`.
- Runs: the four 057 files, then `baseline.py` on the 30m and 4h rows.
- Pooled verdict: `python src/premium_confirm.py` (journal/_multi/premium_confirm.md).
