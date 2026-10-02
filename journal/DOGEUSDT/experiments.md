# DOGEUSDT - experiments (append-only)

---

## Exp 000 - Coin added for the Coinbase premium confirmation (PLAN.md section 26)

**Date:** 2026-10-02
**Status:** set up, not run.

Added by a fixed rule written before any confirmation result:
- Coinbase USD history starts by 2021-07 with no gap of more than 30 days;
- a Binance USDT-M perp listed by 2020-09.

Specs are in `src/config.py`. Only idea 057 runs here, unchanged.


---

## Exp 001 - Coinbase premium (PLAN.md section 26) on DOGEUSDT: the frozen 057 idea, four timeframes

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
| 15m | REJECT | 352 | +0.0356 | 0.0873 | **-0.0518** | [-0.1909, +0.0919] | 164/188 | -0.1014 | 0.3851 | -0.0968 | 0/0 | - | z 2.5 / n 336 / 4R |
| 30m | REJECT | 361 | +0.0457 | 0.0618 | **-0.0161** | [-0.1518, +0.1226] | 165/196 | -0.0440 | 0.3021 | -0.0520 | 0/0 | DRIFT | z 2.5 / n 72 / 4R |
| 60m | WATCH | 316 | +0.0961 | 0.0439 | **+0.0522** | [-0.0954, +0.2095] | 154/162 | +0.0696 | 0.3587 | +0.0318 | 0/0 | - | z 1.5 / n 336 / 4R |
| 240m | INCONCLUSIVE | 101 | +0.1150 | 0.0172 | **+0.0977** | [-0.1206, +0.3221] | 48/53 | +0.0471 | 0.0946 | +0.0890 | 0/0 | DRIFT | z 1.5 / n 72 / 2R |

**Gates failed:** 15m: `valid_mean_r>0;valid_ci_lo>0;stress_mean_r>0;valid_max_dd<=20%`; 30m: `valid_mean_r>0;valid_ci_lo>0;stress_mean_r>0;valid_max_dd<=20%`; 60m: `valid_ci_lo>0;valid_max_dd<=20%`; 240m: `train_mean_r>0;valid_ci_lo>0`

**TRAIN breadth** (`train_positive_share`, the share of eligible grid cells that
were positive on TRAIN): 15m 75% of 8 cells · 30m 100% of 8 cells · 60m 75% of 8 cells · 240m nan% of 0 cells.

DOGE's 4h row is **INCONCLUSIVE, not a result**: `evaluate.py`
found **0 eligible TRAIN cells** (TRAIN 86 trades, under the 100-cell floor), so
no cell could be chosen. **Per `AGENTS.md` §1 step 6 an INCONCLUSIVE row is not
evidence in either direction and `premium_confirm.py` correctly left it out of the
4h pool.** Its mean would have been +0.0977 on 101 VALID trades. 15m -0.0518 and
30m -0.0161 (DRIFT).

**Verdict for this coin.** The frozen idea is not a candidate.
**Nothing here goes to `--final`.** The round's summary is
`journal/_multi/experiments.md` Exp 011 and `journal/_multi/premium_confirm.md`.
