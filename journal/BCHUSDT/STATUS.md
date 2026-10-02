# BCHUSDT - status

> **Coinbase premium on BCHUSDT (PLAN.md §26, Exp 001): the idea `057`,
> unchanged, at four timeframes. No PASS; nothing goes to `--final`; this coin
> exists only for this test.** `datafeed.py --tfs 15,30,60,240` -> VALIDATION: OK,
> `datafeed.py --premium` -> PREMIUM VALIDATION: OK. `size_skips` 0 on every row.
>
> | tf | verdict | VALID trades | gross_r | cost_r | mean R | 95% CI | long/short | baseline | TRAIN chose |
> |---|---|---|---|---|---|---|---|---|---|
> | 15m | REJECT | 1289 | +0.0235 | 0.0995 | **-0.0760** | [-0.1438, -0.0088] | 632/657 | - | z 1.5 / n 72 / 4R |
> | 30m | REJECT | 228 | -0.0272 | 0.0557 | **-0.0829** | [-0.2321, +0.0729] | 118/110 | DRIFT | z 2.5 / n 336 / 4R |
> | 60m | WATCH | 352 | +0.1002 | 0.0466 | **+0.0536** | [-0.0872, +0.1989] | 167/185 | - | z 1.5 / n 336 / 4R |
> | 240m | WATCH | 91 | +0.3302 | 0.0200 | **+0.3101** | [+0.0595, +0.5644] | 46/45 | SKILL | z 1.5 / n 336 / 2R |
>
> **This coin:** the cleanest shape in the confirmation: 4h CI above 0 **and** a SKILL control, on 91 VALID trades. Worth knowing: **this is the one clean lead in the whole round** and it is still 9 trades short of the floor.
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

- Data: `SYMBOL=BCHUSDT python src/datafeed.py --tfs 15,30,60,240`, then
  `SYMBOL=BCHUSDT python src/datafeed.py --premium`.
- Runs: the four 057 files, then `baseline.py` on the 30m and 4h rows.
- Pooled verdict: `python src/premium_confirm.py` (journal/_multi/premium_confirm.md).
