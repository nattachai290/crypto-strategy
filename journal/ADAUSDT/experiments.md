# ADAUSDT - experiments (append-only)

---

## Exp 000 - Coin added for the Coinbase premium confirmation (PLAN.md section 26)

**Date:** 2026-10-02
**Status:** set up, not run.

Added by a fixed rule written before any confirmation result:
- Coinbase USD history starts by 2021-07 with no gap of more than 30 days;
- a Binance USDT-M perp listed by 2020-09.

Specs are in `src/config.py`. Only idea 057 runs here, unchanged.


---

## Exp 001 - Coinbase premium (PLAN.md section 26) on ADAUSDT: the frozen 057 idea, four timeframes

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
| 15m | REJECT | 1053 | +0.0696 | 0.0961 | **-0.0265** | [-0.1036, +0.0526] | 498/555 | -0.1679 | 0.5186 | -0.0711 | 0/0 | - | z 1.5 / n 336 / 4R |
| 30m | REJECT | 237 | -0.0042 | 0.0587 | **-0.0630** | [-0.2186, +0.0998] | 113/124 | -0.0803 | 0.2601 | -0.0908 | 0/0 | DRIFT | z 2.5 / n 336 / 4R |
| 60m | WATCH | 401 | +0.1638 | 0.0450 | **+0.1188** | [-0.0117, +0.2530] | 191/210 | +0.2454 | 0.2236 | +0.0978 | 0/0 | - | z 1.5 / n 72 / 4R |
| 240m | INCONCLUSIVE | 114 | -0.0208 | 0.0231 | **-0.0439** | [-0.2577, +0.1765] | 57/57 | -0.0287 | 0.1523 | -0.0535 | 0/0 | DRIFT | z 1.5 / n 72 / 2R |

**Gates failed:** 15m: `valid_mean_r>0;valid_ci_lo>0;stress_mean_r>0;valid_max_dd<=20%`; 30m: `valid_mean_r>0;valid_ci_lo>0;stress_mean_r>0;valid_max_dd<=20%`; 60m: `valid_ci_lo>0;valid_max_dd<=20%`; 240m: `valid_mean_r>0;valid_ci_lo>0;stress_mean_r>0`

**TRAIN breadth** (`train_positive_share`, the share of eligible grid cells that
were positive on TRAIN): 15m 25% of 8 cells · 30m 100% of 8 cells · 60m 88% of 8 cells · 240m nan% of 0 cells.

ADA's 4h row is **INCONCLUSIVE** for the same reason (0 eligible
TRAIN cells, TRAIN 94 trades) and is excluded from the pool. **It is also the one
4h row in the whole round with a negative mean (-0.0439 on 114 VALID trades), so
if it had been admissible it would have been the seventh positive coin out of
eight - still short of the seven required with SOL and LTC out.** Its 1h row is
WATCH at +0.1188. 30m -0.0630 (DRIFT).

**Verdict for this coin.** The frozen idea is not a candidate.
**Nothing here goes to `--final`.** The round's summary is
`journal/_multi/experiments.md` Exp 011 and `journal/_multi/premium_confirm.md`.
