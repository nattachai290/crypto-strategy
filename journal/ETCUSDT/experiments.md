# ETCUSDT - experiments (append-only)

---

## Exp 000 - Coin added for the Coinbase premium confirmation (PLAN.md section 26)

**Date:** 2026-10-02
**Status:** set up, not run.

Added by a fixed rule written before any confirmation result:
- Coinbase USD history starts by 2021-07 with no gap of more than 30 days;
- a Binance USDT-M perp listed by 2020-09.

Specs are in `src/config.py`. Only idea 057 runs here, unchanged.


---

## Exp 001 - Coinbase premium (PLAN.md section 26) on ETCUSDT: the frozen 057 idea, four timeframes

**Date:** 2026-10-02
**Status:** complete. Four idea files, one evaluation each, **unchanged from BTC
and ETH** (`057_coinbase_premium_follow` at 1h plus `_tf15`, `_tf30`, `_tf240`), plus
`baseline.py` on the 30m and 4h rows as the plan requires. No code and no idea
file was changed, `--final` was not run (nothing passed), HOLDOUT was never read.

**Data.** `datafeed.py --tfs 15,30,60,240` -> **VALIDATION: OK**;
`datafeed.py --premium` -> **PREMIUM VALIDATION: OK**. This coin is one of the ten
fixed before any run by `PLAN.md` §26: Coinbase history with no gap longer than
30 days and a Binance perp listed by 2020-09.

**Verdicts:** **REJECT x3**, WATCH. No PASS. `size_skips` is 0 on every row.

| tf | verdict | VALID trades | gross_r | cost_r | mean R | 95% CI | long/short | CAGR | maxDD | stress x1.5 | skips train/valid | baseline (30m/4h) | TRAIN chose |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 15m | REJECT | 1337 | +0.0932 | 0.1043 | **-0.0111** | [-0.0733, +0.0522] | 675/662 | -0.1129 | 0.4664 | -0.0623 | 0/0 | - | z 1.5 / n 72 / 2R |
| 30m | REJECT | 727 | -0.0134 | 0.0718 | **-0.0852** | [-0.1795, +0.0109] | 371/356 | -0.2872 | 0.5961 | -0.1181 | 0/0 | DRIFT | z 1.5 / n 72 / 4R |
| 60m | REJECT | 365 | +0.0412 | 0.0494 | **-0.0082** | [-0.1424, +0.1295] | 186/179 | -0.0300 | 0.3683 | -0.0307 | 0/0 | - | z 1.5 / n 336 / 4R |
| 240m | WATCH | 97 | +0.1800 | 0.0314 | **+0.1486** | [-0.1227, +0.4361] | 55/42 | +0.0695 | 0.0839 | +0.1382 | 0/0 | DRIFT | z 1.5 / n 72 / 4R |

**Gates failed:** 15m: `valid_mean_r>0;valid_ci_lo>0;stress_mean_r>0;valid_max_dd<=20%`; 30m: `valid_mean_r>0;valid_ci_lo>0;stress_mean_r>0;valid_max_dd<=20%`; 60m: `valid_mean_r>0;valid_ci_lo>0;stress_mean_r>0;valid_max_dd<=20%`; 240m: `valid_trades>=100;valid_ci_lo>0`

**TRAIN breadth** (`train_positive_share`, the share of eligible grid cells that
were positive on TRAIN): 15m 12% of 8 cells · 30m 25% of 8 cells · 60m 38% of 8 cells · 240m 100% of 2 cells.

ETC's 4h row is WATCH at +0.1486 with CI [-0.1227, +0.4361] - wide
enough to straddle 0 - on 97 VALID trades. Every faster clock is negative (15m
-0.0111, 30m -0.0852 with DRIFT, 1h -0.0082) and the 4h control is DRIFT. **ETC
is the coin that most resembles the general pattern: the signal has some gross
structure (+0.1800 at 4h) and nothing else survives.**

**Verdict for this coin.** The frozen idea is not a candidate.
**Nothing here goes to `--final`.** The round's summary is
`journal/_multi/experiments.md` Exp 011 and `journal/_multi/premium_confirm.md`.
