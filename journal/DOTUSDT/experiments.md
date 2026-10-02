# DOTUSDT - experiments (append-only)

---

## Exp 000 - Coin added for the Coinbase premium confirmation (PLAN.md section 26)

**Date:** 2026-10-02
**Status:** set up, not run.

Added by a fixed rule written before any confirmation result:
- Coinbase USD history starts by 2021-07 with no gap of more than 30 days;
- a Binance USDT-M perp listed by 2020-09.

Specs are in `src/config.py`. Only idea 057 runs here, unchanged.


---

## Exp 001 - Coinbase premium (PLAN.md section 26) on DOTUSDT: the frozen 057 idea, four timeframes

**Date:** 2026-10-02
**Status:** complete. Four idea files, one evaluation each, **unchanged from BTC
and ETH** (`057_coinbase_premium_follow` at 1h plus `_tf15`, `_tf30`, `_tf240`), plus
`baseline.py` on the 30m and 4h rows as the plan requires. No code and no idea
file was changed, `--final` was not run (nothing passed), HOLDOUT was never read.

**Data.** `datafeed.py --tfs 15,30,60,240` -> **VALIDATION: OK**;
`datafeed.py --premium` -> **PREMIUM VALIDATION: OK**. This coin is one of the ten
fixed before any run by `PLAN.md` §26: Coinbase history with no gap longer than
30 days and a Binance perp listed by 2020-09.

**Verdicts:** **REJECT x2**, WATCH, INCONCLUSIVE. No PASS. `size_skips` is 0 on every row.

| tf | verdict | VALID trades | gross_r | cost_r | mean R | 95% CI | long/short | CAGR | maxDD | stress x1.5 | skips train/valid | baseline (30m/4h) | TRAIN chose |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 15m | REJECT | 1095 | +0.1069 | 0.1006 | **+0.0063** | [-0.0706, +0.0874] | 527/568 | -0.0121 | 0.4445 | -0.0406 | 0/0 | - | z 1.5 / n 336 / 4R |
| 30m | REJECT | 342 | +0.0632 | 0.0651 | **-0.0019** | [-0.1370, +0.1365] | 170/172 | -0.0173 | 0.2209 | -0.0319 | 0/0 | DRIFT | z 2.5 / n 72 / 4R |
| 60m | WATCH | 403 | +0.0881 | 0.0486 | **+0.0396** | [-0.0873, +0.1695] | 188/215 | +0.0642 | 0.2639 | +0.0098 | 0/0 | - | z 1.5 / n 72 / 4R |
| 240m | INCONCLUSIVE | 115 | +0.0647 | 0.0247 | **+0.0400** | [-0.1676, +0.2560] | 57/58 | +0.0192 | 0.1475 | +0.0298 | 0/0 | DRIFT | z 1.5 / n 72 / 2R |

**Gates failed:** 15m: `valid_ci_lo>0;stress_mean_r>0;valid_max_dd<=20%`; 30m: `valid_mean_r>0;valid_ci_lo>0;stress_mean_r>0;valid_max_dd<=20%`; 60m: `valid_ci_lo>0;valid_max_dd<=20%`; 240m: `valid_ci_lo>0`

**TRAIN breadth** (`train_positive_share`, the share of eligible grid cells that
were positive on TRAIN): 15m 62% of 8 cells · 30m 88% of 8 cells · 60m 50% of 8 cells · 240m nan% of 0 cells.

DOT's 4h row is **INCONCLUSIVE** (0 eligible TRAIN cells, TRAIN 77
trades) and is excluded from the pool; its mean would have been +0.0400 on 115
VALID trades. 30m -0.0019 with a CI of [-0.1370, +0.1365] and DRIFT, 15m
+0.0063, 1h WATCH +0.0396. **DOT is the coin where the premium simply does
nothing: gross +0.0647 at 4h against cost 0.0247, and every mean inside its CI.**

**Verdict for this coin.** The frozen idea is not a candidate.
**Nothing here goes to `--final`.** The round's summary is
`journal/_multi/experiments.md` Exp 011 and `journal/_multi/premium_confirm.md`.
