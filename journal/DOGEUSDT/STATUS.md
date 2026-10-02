# DOGEUSDT - status

> **Coinbase premium on DOGEUSDT (PLAN.md §26, Exp 001): the idea `057`,
> unchanged, at four timeframes. No PASS; nothing goes to `--final`; this coin
> exists only for this test.** `datafeed.py --tfs 15,30,60,240` -> VALIDATION: OK,
> `datafeed.py --premium` -> PREMIUM VALIDATION: OK. `size_skips` 0 on every row.
>
> | tf | verdict | VALID trades | gross_r | cost_r | mean R | 95% CI | long/short | baseline | TRAIN chose |
> |---|---|---|---|---|---|---|---|---|---|
> | 15m | REJECT | 352 | +0.0356 | 0.0873 | **-0.0518** | [-0.1909, +0.0919] | 164/188 | - | z 2.5 / n 336 / 4R |
> | 30m | REJECT | 361 | +0.0457 | 0.0618 | **-0.0161** | [-0.1518, +0.1226] | 165/196 | DRIFT | z 2.5 / n 72 / 4R |
> | 60m | WATCH | 316 | +0.0961 | 0.0439 | **+0.0522** | [-0.0954, +0.2095] | 154/162 | - | z 1.5 / n 336 / 4R |
> | 240m | INCONCLUSIVE | 101 | +0.1150 | 0.0172 | **+0.0977** | [-0.1206, +0.3221] | 48/53 | DRIFT | z 1.5 / n 72 / 2R |
>
> **This coin:** 4h INCONCLUSIVE (0 eligible TRAIN cells), so no evidence either way. Worth knowing: its mean would have been +0.0977 on 101 VALID trades had a cell been eligible.
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

- Data: `SYMBOL=DOGEUSDT python src/datafeed.py --tfs 15,30,60,240`, then
  `SYMBOL=DOGEUSDT python src/datafeed.py --premium`.
- Runs: the four 057 files, then `baseline.py` on the 30m and 4h rows.
- Pooled verdict: `python src/premium_confirm.py` (journal/_multi/premium_confirm.md).
