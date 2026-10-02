# ATOMUSDT - experiments (append-only)

---

## Exp 000 - Coin added for the Coinbase premium confirmation (PLAN.md section 26)

**Date:** 2026-10-02
**Status:** set up, not run.

Added by a fixed rule written before any confirmation result:
- Coinbase USD history starts by 2021-07 with no gap of more than 30 days;
- a Binance USDT-M perp listed by 2020-09.

Specs are in `src/config.py`. Only idea 057 runs here, unchanged.


---

## Exp 001 - Coinbase premium (PLAN.md section 26) on ATOMUSDT: the frozen 057 idea, four timeframes

**Date:** 2026-10-02
**Status:** complete. Four idea files, one evaluation each, **unchanged from BTC
and ETH** (`057_coinbase_premium_follow` at 1h plus `_tf15`, `_tf30`, `_tf240`), plus
`baseline.py` on the 30m and 4h rows as the plan requires. No code and no idea
file was changed, `--final` was not run (nothing passed), HOLDOUT was never read.

**Data.** `datafeed.py --tfs 15,30,60,240` -> **VALIDATION: OK**;
`datafeed.py --premium` -> **PREMIUM VALIDATION: OK**. This coin is one of the ten
fixed before any run by `PLAN.md` §26: Coinbase history with no gap longer than
30 days and a Binance perp listed by 2020-09.

**Verdicts:** **REJECT x2**, **WATCH x2**. No PASS. `size_skips` is 0 on every row.

| tf | verdict | VALID trades | gross_r | cost_r | mean R | 95% CI | long/short | CAGR | maxDD | stress x1.5 | skips train/valid | baseline (30m/4h) | TRAIN chose |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 15m | REJECT | 387 | +0.1733 | 0.0883 | **+0.0850** | [-0.0482, +0.2208] | 192/195 | +0.1580 | 0.1943 | +0.0435 | 0/0 | - | z 2.5 / n 336 / 4R |
| 30m | WATCH | 362 | +0.1628 | 0.0654 | **+0.0973** | [-0.0241, +0.2191] | 186/176 | +0.1773 | 0.1260 | +0.0676 | 0/0 | SKILL | z 2.5 / n 72 / 2R |
| 60m | REJECT | 243 | +0.1385 | 0.0443 | **+0.0943** | [-0.0564, +0.2479] | 119/124 | +0.1114 | 0.1600 | +0.0739 | 0/0 | - | z 2.5 / n 72 / 2R |
| 240m | WATCH | 90 | +0.3002 | 0.0249 | **+0.2754** | [+0.0187, +0.5427] | 45/45 | +0.1276 | 0.1108 | +0.2657 | 0/0 | DRIFT | z 1.5 / n 336 / 2R |

**Gates failed:** 15m: `train_mean_r>0;valid_ci_lo>0`; 30m: `valid_ci_lo>0`; 60m: `train_mean_r>0;valid_ci_lo>0`; 240m: `valid_trades>=100`

**TRAIN breadth** (`train_positive_share`, the share of eligible grid cells that
were positive on TRAIN): 15m 0% of 8 cells · 30m 25% of 8 cells · 60m 0% of 8 cells · 240m 33% of 3 cells.

ATOM is the only coin in the confirmation with a SKILL at 30m
(+0.0973, CI [-0.0241, +0.2191], control SKILL on both TRAIN and VALID) and a
WATCH at 4h (+0.2754, CI [+0.0187, +0.5427], gross +0.3002 against cost 0.0249).
It is also the only coin positive at **every** clock (+0.0850 at 15m, +0.0973,
+0.0943, +0.2754). **90 VALID trades at 4h, under the floor, and the 4h control
is DRIFT.** Its TRAIN breadth is poor where it is not 4h: 0% of 8 cells positive
at 15m and 1h.

**Verdict for this coin.** The frozen idea is a lead worth a proper pre-registered follow-up only if the pooled breadth bar is met.
**Nothing here goes to `--final`.** The round's summary is
`journal/_multi/experiments.md` Exp 011 and `journal/_multi/premium_confirm.md`.
