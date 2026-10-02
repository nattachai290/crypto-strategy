# ALGOUSDT - experiments (append-only)

---

## Exp 000 - Coin added for the Coinbase premium confirmation (PLAN.md section 26)

**Date:** 2026-10-02
**Status:** set up, not run.

Added by a fixed rule written before any confirmation result:
- Coinbase USD history starts by 2021-07 with no gap of more than 30 days;
- a Binance USDT-M perp listed by 2020-09.

Specs are in `src/config.py`. Only idea 057 runs here, unchanged.


---

## Exp 001 - Coinbase premium (PLAN.md section 26) on ALGOUSDT: the frozen 057 idea, four timeframes

**Date:** 2026-10-02
**Status:** complete. Four idea files, one evaluation each, **unchanged from BTC
and ETH** (`057_coinbase_premium_follow` at 1h plus `_tf15`, `_tf30`, `_tf240`), plus
`baseline.py` on the 30m and 4h rows as the plan requires. No code and no idea
file was changed, `--final` was not run (nothing passed), HOLDOUT was never read.

**Data.** `datafeed.py --tfs 15,30,60,240` -> **VALIDATION: OK**;
`datafeed.py --premium` -> **PREMIUM VALIDATION: OK**. This coin is one of the ten
fixed before any run by `PLAN.md` §26: Coinbase history with no gap longer than
30 days and a Binance perp listed by 2020-09.

**Verdicts:** **WATCH x2**, **REJECT x2**. No PASS. `size_skips` is 0 on every row.

| tf | verdict | VALID trades | gross_r | cost_r | mean R | 95% CI | long/short | CAGR | maxDD | stress x1.5 | skips train/valid | baseline (30m/4h) | TRAIN chose |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 15m | REJECT | 439 | -0.0098 | 0.0769 | **-0.0867** | [-0.1873, +0.0177] | 221/218 | -0.1842 | 0.3824 | -0.1321 | 0/0 | - | z 2.5 / n 72 / 2R |
| 30m | WATCH | 264 | +0.1535 | 0.0541 | **+0.0994** | [-0.0666, +0.2712] | 126/138 | +0.1260 | 0.1800 | +0.0725 | 0/0 | DRIFT | z 2.5 / n 72 / 4R |
| 60m | WATCH | 449 | +0.1312 | 0.0390 | **+0.0922** | [-0.0177, +0.2012] | 217/232 | +0.2100 | 0.1486 | +0.0505 | 0/0 | - | z 1.5 / n 72 / 2R |
| 240m | REJECT | 102 | +0.0562 | 0.0244 | **+0.0319** | [-0.2257, +0.3055] | 57/45 | +0.0115 | 0.1225 | +0.0229 | 0/0 | DRIFT | z 1.5 / n 72 / 4R |

**Gates failed:** 15m: `train_mean_r>0;valid_mean_r>0;valid_ci_lo>0;stress_mean_r>0;valid_max_dd<=20%`; 30m: `valid_ci_lo>0`; 60m: `valid_ci_lo>0`; 240m: `train_mean_r>0;valid_ci_lo>0`

**TRAIN breadth** (`train_positive_share`, the share of eligible grid cells that
were positive on TRAIN): 15m 0% of 8 cells · 30m 38% of 8 cells · 60m 38% of 8 cells · 240m 0% of 2 cells.

ALGO is the weakest of the five admissible 4h coins: REJECT at
+0.0319 with CI [-0.2257, +0.3055] on 102 VALID trades, and **0% of 2 eligible
TRAIN cells positive**. Its two WATCH rows are at 30m (+0.0994, DRIFT) and 1h
(+0.0922). **The 4h mean is positive and the 4h control is DRIFT, so this row
contributes to the pool while contributing no evidence of timing.**

**Verdict for this coin.** The frozen idea is not a candidate.
**Nothing here goes to `--final`.** The round's summary is
`journal/_multi/experiments.md` Exp 011 and `journal/_multi/premium_confirm.md`.
