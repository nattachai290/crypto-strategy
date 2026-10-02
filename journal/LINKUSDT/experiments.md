# LINKUSDT - experiments (append-only)

---

## Exp 000 - Coin added for the Coinbase premium confirmation (PLAN.md section 26)

**Date:** 2026-10-02
**Status:** set up, not run.

Added by a fixed rule written before any confirmation result:
- Coinbase USD history starts by 2021-07 with no gap of more than 30 days;
- a Binance USDT-M perp listed by 2020-09.

Specs are in `src/config.py`. Only idea 057 runs here, unchanged.


---

## Exp 001 - Coinbase premium (PLAN.md section 26) on LINKUSDT: the frozen 057 idea, four timeframes

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
| 15m | REJECT | 308 | +0.0602 | 0.0778 | **-0.0176** | [-0.1497, +0.1191] | 152/156 | -0.0372 | 0.3693 | -0.0588 | 0/0 | - | z 2.5 / n 336 / 4R |
| 30m | REJECT | 295 | +0.0281 | 0.0598 | **-0.0317** | [-0.1704, +0.1134] | 162/133 | -0.0562 | 0.3216 | -0.0693 | 0/0 | DRIFT | z 2.5 / n 72 / 4R |
| 60m | REJECT | 192 | -0.0370 | 0.0429 | **-0.0799** | [-0.2376, +0.0895] | 103/89 | -0.0798 | 0.3203 | -0.0983 | 0/0 | - | z 2.5 / n 72 / 4R |
| 240m | WATCH | 95 | +0.4664 | 0.0266 | **+0.4398** | [+0.1338, +0.7595] | 51/44 | +0.2247 | 0.0526 | +0.4306 | 0/0 | DRIFT | z 1.5 / n 72 / 4R |

**Gates failed:** 15m: `valid_mean_r>0;valid_ci_lo>0;stress_mean_r>0;valid_max_dd<=20%`; 30m: `valid_mean_r>0;valid_ci_lo>0;stress_mean_r>0;valid_max_dd<=20%`; 60m: `valid_mean_r>0;valid_ci_lo>0;stress_mean_r>0;valid_max_dd<=20%`; 240m: `valid_trades>=100`

**TRAIN breadth** (`train_positive_share`, the share of eligible grid cells that
were positive on TRAIN): 15m 88% of 8 cells · 30m 100% of 8 cells · 60m 75% of 8 cells · 240m 25% of 4 cells.

LINK is the strongest single 4h book in the confirmation
(+0.4398 mean R, CI [+0.1338, +0.7595], gross +0.4664 against cost 0.0266) and the
only coin besides BCHUSDT and ATOMUSDT whose 4h CI clears 0. **But it is 95 VALID
trades, under the 100 floor, and its random-entry control says DRIFT on both
clocks** - the 4h TRAIN mean is below the p95 of 200 random-entry sets - so by
`AGENTS.md` §1 step 6 the number is a lead, not a candidate. LINK also fails at
every faster clock: 15m -0.0176, 30m -0.0317 (DRIFT), 1h -0.0799. **One coin
out of eight is not confirmation.**

**Verdict for this coin.** The frozen idea is not a candidate.
**Nothing here goes to `--final`.** The round's summary is
`journal/_multi/experiments.md` Exp 011 and `journal/_multi/premium_confirm.md`.
