# BCHUSDT - experiments (append-only)

---

## Exp 000 - Coin added for the Coinbase premium confirmation (PLAN.md section 26)

**Date:** 2026-10-02
**Status:** set up, not run.

Added by a fixed rule written before any confirmation result:
- Coinbase USD history starts by 2021-07 with no gap of more than 30 days;
- a Binance USDT-M perp listed by 2020-09.

Specs are in `src/config.py`. Only idea 057 runs here, unchanged.


---

## Exp 001 - Coinbase premium (PLAN.md section 26) on BCHUSDT: the frozen 057 idea, four timeframes

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
| 15m | REJECT | 1289 | +0.0235 | 0.0995 | **-0.0760** | [-0.1438, -0.0088] | 632/657 | -0.4174 | 0.7192 | -0.1274 | 0/0 | - | z 1.5 / n 72 / 4R |
| 30m | REJECT | 228 | -0.0272 | 0.0557 | **-0.0829** | [-0.2321, +0.0729] | 118/110 | -0.0969 | 0.2661 | -0.1114 | 0/0 | DRIFT | z 2.5 / n 336 / 4R |
| 60m | WATCH | 352 | +0.1002 | 0.0466 | **+0.0536** | [-0.0872, +0.1989] | 167/185 | +0.0810 | 0.2615 | +0.0268 | 0/0 | - | z 1.5 / n 336 / 4R |
| 240m | WATCH | 91 | +0.3302 | 0.0200 | **+0.3101** | [+0.0595, +0.5644] | 46/45 | +0.1473 | 0.0562 | +0.2826 | 0/0 | SKILL | z 1.5 / n 336 / 2R |

**Gates failed:** 15m: `train_mean_r>0;valid_mean_r>0;valid_ci_lo>0;stress_mean_r>0;valid_max_dd<=20%`; 30m: `valid_mean_r>0;valid_ci_lo>0;stress_mean_r>0;valid_max_dd<=20%`; 60m: `valid_ci_lo>0;valid_max_dd<=20%`; 240m: `valid_trades>=100`

**TRAIN breadth** (`train_positive_share`, the share of eligible grid cells that
were positive on TRAIN): 15m 0% of 8 cells · 30m 50% of 8 cells · 60m 88% of 8 cells · 240m 100% of 4 cells.

BCH is the cleanest confirmation shape in the round: **4h is WATCH with
+0.3101 mean R, CI [+0.0595, +0.5644] clearing 0, gross +0.3302 against cost
0.0200, and the random-entry control says SKILL** - the only SKILL of the whole
confirmation apart from ATOMUSDT at 30m. Its 15m row is the worst in the round
(-0.0760 with a CI that excludes 0) and its 30m row is -0.0829 with DRIFT. **91
VALID trades is under the 100 floor.** BCH also shows that the TRAIN breadth
that made §25 exciting does not travel: **0% of 8 cells positive on TRAIN at
15m, 50% at 30m** (BTC and ETH were 100% at 30m).

**Verdict for this coin.** The frozen idea is a lead worth a proper pre-registered follow-up only if the pooled breadth bar is met.
**Nothing here goes to `--final`.** The round's summary is
`journal/_multi/experiments.md` Exp 011 and `journal/_multi/premium_confirm.md`.
