# BNBUSDT research log

Append-only. Rules: `AGENTS.md`. Plan: `docs/research/PLAN.md` §12.
History: `journal/BTCUSDT/` (closed), `journal/ETHUSDT/` (closed).

---

## Exp 000 — Setup

**Date:** 2026-09-29
**Status:** complete (config only; no data, no evaluation, holdout untouched)

The owner asked to try BNBUSDT after ETH closed, and said the research agent,
not the planner, runs it. Only configuration was prepared:
- `src/config.py` `SYMBOL_SPECS["BNBUSDT"]`: step 0.01 BNB, min notional 5 USDT, data 2020-03..2026-08 (listed 2020-02-10), research account 1,000 USDT. These are Binance's
  published contract specs; the exchange-info endpoint was not reachable
  from the setup machine.
- Data is **not** downloaded. The research agent runs `datafeed.py` and
  records VALIDATION in Exp 001.

Next: **Exp 001, pre-registration** (`PLAN.md` §12).

---

## Exp 001 - Round B1 pre-registration: the seven cost-first families on BNBUSDT, unchanged

**Date:** 2026-09-29
**Status:** pre-registration, written BEFORE any BNBUSDT evaluation. Zero
evaluations in this entry. BNB project count on entry: **0**. BNB HOLDOUT sealed.

**The rule this round obeys (`PLAN.md` §12): the ideas are the existing idea
files, run unchanged** with `SYMBOL=BNBUSDT`. No idea file is edited and no new
one is written in this round.

### Session start, as PLAN §12 requires

1. **The funding fix is on main.** `python src/test_engine.py` shows test **1b**
   ("hand-computed funding (notional x rate)") passing on both the long and the
   short case and ends with **ALL CHECKS PASSED**. Every number below comes from
   an engine that actually charges funding.
2. **Data: `VALIDATION: OK`.** All 71 months present on all seven timeframes,
   no duplicates, **no gaps over 3x the bar step on any timeframe** - the clean
   dataset of the two new coins. (SOLUSDT has two gaps; see SOL Exp 001.)

### 1. What is different on BNB, measured

| | |
|---|---|
| step / min notional | 0.01 BNB / 5 USDT |
| 4h TRAIN | 2020-03-01 .. 2022-12-31, **6,216 bars, 34 months** (listed 2020-02-10) |
| VALID / HOLDOUT | 2023-24 / 2025-01..2026-08 |
| research account | 1,000 USDT (the default; no `eval_equity` override) |
| holdout peak | **1,342.39** |
| funding rows | 7,125 |

**BNB is the least volatile of the coins here and the least extreme in every
dimension**: 34 months of TRAIN against SOL's 27, a 0.01 step against a whole
coin, and a holdout peak an order of magnitude above ETH's. That matters for the
cost line, which is the round's whole design constraint.

### 2. Sizing: comfortable, and the rounding is small

| stop | BNB at the holdout peak 1,342.39 | rounding error |
|---|---|---|
| 5% | 0.149 -> **0.14 BNB** | 6.0% |
| 6% | 0.124 -> **0.12 BNB** | 3.3% |
| 7% | 0.106 -> **0.10 BNB** | 6.0% |

`tf_variants.py` prints no `!!` line for the 6% stops: a 6% stop sizes while
BNB < 1,000 x 0.01 / 0.06 / 0.01 = **16,667**, and the peak is 1,342. **No
BNBUSDT evaluation can be `UNSIZABLE`.**

### 3. Signal counts on BNB TRAIN only

| family | source cell long/short | source total | all grid cells | predicted |
|---|---|---|---|---|
| 034 multi-day reversal | 110 / 135 | 245 | 245, 245, 178, 178 | fine |
| 035 multi-day momentum | 148 / 91 | 239 | 239, 239, 157, 157 | fine |
| 036 Keltner multi-day | 107 / 88 | 195 | 195, 195, 251, 251 | fine |
| **038 opening range** | 302 / 297 | **599** | 599 x4 | fine |
| **039 breakout + flow** | 55 / 114 | 169 | **169, 119, 141, 100** | borderline |
| **041 impulse, not crowded** | 73 / 88 | 161 | **161, 168, 140, 142** | borderline |
| **043 squeeze break** | 93 / 75 | 168 | **133, 133, 168, 168** | borderline |

**BNB clears 150 on every cell of the four broad families and on the looser half
of the three narrow ones** - better than SOL's 27 months, worse than BTC's and
ETH's 36. `PLAN.md` §12 says a family under 150 is still run with the risk of
INCONCLUSIVE said in advance: **039, 041 and 043 will trade roughly half what
they trade on BTC**, so expect INCONCLUSIVE or thin WATCHes from them and read
the long/short split before anything else.

**039 is lopsided towards shorts on BNB too** (55 long / 114 short), as it is on
SOL (40/96), where on BTC and ETH it was close to balanced. That is two coins
agreeing on the same asymmetry, which is a property of BNB's and SOL's data
rather than of a filter, and it has to be checked against any positive result.

### 4. Expected cost_r, and the same correction to the plan's formula

`PLAN.md` §12 item 3 asks for `(0.14% + hold_h/8 x the coin's TRAIN mean
|funding|) / stop`. BNB's TRAIN funding is **0.02707% per 8h abs mean** (signed
+0.00243%, p95 |rate| 0.12309%) - higher than BTC's 0.01886% and ETH's 0.02325%:

| stop | 48h | 72h | 96h | 120h |
|---|---|---|---|---|
| 5% | 0.0605 | 0.0767 | 0.0930 | 0.1092 |
| 6% | 0.0504 | 0.0639 | 0.0775 | 0.0910 |
| 7% | 0.0432 | 0.0548 | 0.0664 | 0.0780 |

Again every cell but one is above Round 5's 0.05 R limit. **The same correction
applies as on SOL** (SOL Exp 001 §4): the formula multiplies the *absolute* rate
by the number of settlements, but a position pays the signed sum, and BTC Exp
030 measured the real effect by re-running all 207 BTC and 49 ETH evaluations
with the fix - the median VALID mean R moved **−0.0015 R on BTC and −0.0027 R on
ETH**, against formula estimates of 0.0433 and 0.0615 R, so **the formula
overstates the real cost by roughly 20x**.

**Prediction, falsifiable against the first run: measured VALID `cost_r` on BNB
will be about 0.020-0.024 R**, not 0.078. If the first BNB run reports a
`cost_r` near 0.02 the round is worth running; if it reports near 0.08 I have
misunderstood something and should stop.

### 5. Context from the two closed coins, not a reason

| family | BTC best (clocks>0) | ETH best (clocks>0) | holdout |
|---|---|---|---|
| 034 multi-day reversal | −0.068 (0/7) | +0.058 (3/7) | - |
| 035 multi-day momentum | +0.165 (7/7) | +0.133 (4/7) | - |
| 036 Keltner multi-day | +0.097 (4/7) | +0.111 (4/7) | - |
| **038 opening range** | **+0.175 PASS (4/7)** | +0.210 (5/7) | **FAILED** |
| **039 breakout + flow** | **+0.222 PASS (7/7)** | +0.222 (7/7) | **FAILED** |
| 041 impulse, not crowded | +0.174 (6/7) | **+0.276 (7/7)** | - |
| 043 squeeze break | +0.144 (7/7) | +0.204 (6/7) | - |

- **039 was positive on all fourteen clocks across the two closed coins and
  failed its BTC holdout** because a random entry matched it. A PASS on BNB is a
  reason for more suspicion, not less.
- **038 also passed the gates, got ALPHA on BTC, and failed its holdout** with a
  negative gross.
- **All 32 ETH controls were DRIFT, 31 of 32 NO_EDGE.** The BTC/ETH paired
  comparison found no detectable difference between the coins (mean −0.018 R,
  CI [−0.044, +0.008]) and only +0.52 correlation between their results, so
  BNB is neither more nor less likely than a coin flip, and its VALID is not
  independent of the BTC/ETH work that shaped these ideas.

### 6. The run, and the judge

**49 evaluations** with `SYMBOL=BNBUSDT`, then `baseline.py` and
`benchmark.py` on every WATCH and PASS, comparing with holding **BNB**.

**Any PASS must survive the x1.5 cost stress with room to spare** (§12): BNB
perps are thinner than BTC/ETH, so real slippage is likely higher, and that gate
is the protection.

**Before any `--final`:** the three written checks from Round 6 and §11 - the
seven clocks and whether the PASS is the best of them, the per-year split, the
long/short counts - **plus the same config's BTC and ETH result.**

**Stop rule, agreed in advance, for this coin:** if B1 ends with no holdout
CONFIRMED on BNB, research on BNB stops. If both B1 and S1 stop, the project's
answer stands for all four coins. **No fifth coin - that is the owner's.**

---

## Exp 002 — Review note (planner)

**Date:** 2026-09-29
**Status:** review (no evaluation; holdout untouched)

Round B1's 49 evaluations are recorded in `results/BNBUSDT/evaluations.csv`
(0 PASS, 10 WATCH, 33 REJECT, 6 INCONCLUSIVE, `size_skips` 0), but this
journal has no results entry.

For the research agent:
- run `baseline.py` and `benchmark.py` on the two WATCHes without them
  (041 @3m, 043 @1m);
- write the round summary as **Exp 003**, per AGENTS.md §8;
- update STATUS.md.

With no PASS, the stop rule (PLAN.md §12) has fired: BNB research stops.
Details and the cross-coin table: `journal/SOLUSDT/experiments.md` Exp 004.

---

## Exp 003 - Round B1 results: 0 PASS, 9 of 10 controls DRIFT, and the stop rule fires

**Date:** 2026-09-29
**Status:** complete. **49 evaluations: 0 PASS, 10 WATCH, 33 REJECT, 6
INCONCLUSIVE.** `baseline.py` and `benchmark.py` on **all 10** WATCH rows, as
AGENTS.md step 6b/6c requires (two of them were the ones Exp 002 listed as
missing; the third turned out to have been written by the interrupted run and
was correctly skipped rather than recomputed). `size_skips` 0 on every row.
**BNBUSDT HOLDOUT UNTOUCHED - no PASS, so `--final` was never a candidate and
was never run.**

### All 49 evaluations

`tr` = TRAIN trades, `v` = VALID trades, `gross`/`cost`/`mean` in R, `CI` the 95%
bootstrap bounds on the VALID mean, `dd` the VALID max drawdown, `L/S` the VALID
long/short trade counts. Controls are shown only for WATCH rows.

**034 multi-day reversal** — 0 PASS, 4 REJECT, 1 WATCH, 2 INCONCLUSIVE

| name | tf | tr | v | gross | cost | mean | CI low | CI high | dd | L/S | verdict | baseline | benchmark |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 034_multiday_reversal | 4h | 170 | 120 | +0.0150 | 0.0231 | −0.0081 | −0.1617 | +0.1514 | 6.6% | 55/65 | REJECT | | |
| 034_multiday_reversal_tf60_time | 1h | 177 | 121 | −0.0868 | 0.0217 | −0.1084 | −0.2546 | +0.0386 | 18.7% | 52/69 | REJECT | | |
| 034_multiday_reversal_tf30_time | 30m | 174 | 114 | −0.1369 | 0.0147 | −0.1516 | −0.3035 | −0.0006 | 19.3% | 52/62 | REJECT | | |
| 034_multiday_reversal_tf15_time | 15m | 153 | 100 | −0.0569 | 0.0171 | −0.0740 | −0.2005 | +0.0642 | 9.7% | 43/57 | REJECT | | |
| 034_multiday_reversal_tf5_time | 5m | 141 | 86 | +0.0011 | 0.0143 | −0.0132 | −0.1998 | +0.1899 | 10.5% | 40/46 | REJECT | | |
| **034_multiday_reversal_tf3_time** | **3m** | 125 | 79 | +0.2097 | 0.0233 | **+0.1864** | −0.0212 | +0.4051 | 5.0% | 33/46 | **WATCH** | **DRIFT** | **ALPHA** |
| 034_multiday_reversal_tf1_time | 1m | 96 | 69 | −0.0721 | 0.0156 | −0.0877 | −0.2565 | +0.0805 | 9.0% | 25/44 | INCONCLUSIVE | | |

**035 multi-day momentum** — 0 PASS, 1 REJECT, 5 WATCH, 1 INCONCLUSIVE

| name | tf | tr | v | gross | cost | mean | CI low | CI high | dd | L/S | verdict | baseline | benchmark |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 035_multiday_momentum | 4h | 106 | 66 | +0.0618 | 0.0157 | +0.0462 | −0.1370 | +0.2365 | 4.3% | 41/25 | WATCH | DRIFT | NO_EDGE |
| **035_multiday_momentum_tf60_time** | **1h** | 113 | 70 | +0.2132 | 0.0171 | **+0.1961** | −0.0103 | +0.4172 | 4.7% | 42/28 | **WATCH** | **SKILL** | NO_EDGE |
| 035_multiday_momentum_tf30_time | 30m | 110 | 65 | +0.0846 | 0.0214 | +0.0633 | −0.1869 | +0.3298 | 6.5% | 34/31 | WATCH | DRIFT | NO_EDGE |
| 035_multiday_momentum_tf5_time | 5m | 129 | 92 | +0.0386 | 0.0208 | +0.0178 | −0.1834 | +0.2316 | 7.4% | 50/42 | WATCH | DRIFT | NO_EDGE |
| 035_multiday_momentum_tf3_time | 3m | 118 | 81 | +0.1558 | 0.0249 | +0.1308 | −0.0938 | +0.3688 | 7.4% | 39/42 | WATCH | DRIFT | NO_EDGE |
| 035_multiday_momentum_tf15_time | 15m | 144 | 98 | +0.0017 | 0.0141 | −0.0123 | −0.2031 | +0.1979 | 8.2% | 54/44 | REJECT | | |
| 035_multiday_momentum_tf1_time | 1m | 92 | 70 | −0.0381 | 0.0174 | −0.0556 | −0.2648 | +0.1740 | 8.6% | 35/35 | INCONCLUSIVE | | |

**036 Keltner multi-day** — 0 PASS, **6 REJECT**, 1 INCONCLUSIVE. **0 of 7 clocks
positive.**

| name | tf | tr | v | gross | cost | mean | CI low | CI high | dd | L/S | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 036_keltner_multiday | 4h | 151 | 103 | −0.1051 | 0.0138 | −0.1190 | −0.2895 | +0.0711 | 12.3% | 58/45 | REJECT |
| 036_keltner_multiday_tf60_time | 1h | 216 | 143 | −0.0097 | 0.0170 | −0.0268 | −0.1661 | +0.1240 | 13.2% | 84/59 | REJECT |
| 036_keltner_multiday_tf30_time | 30m | 215 | 132 | −0.0193 | 0.0174 | −0.0367 | −0.1620 | +0.0943 | 8.3% | 72/60 | REJECT |
| 036_keltner_multiday_tf15_time | 15m | 140 | 91 | −0.0621 | 0.0147 | −0.0768 | −0.2226 | +0.0796 | 9.1% | 47/44 | REJECT |
| 036_keltner_multiday_tf5_time | 5m | 116 | 79 | −0.0747 | 0.0149 | −0.0896 | −0.2485 | +0.0722 | 10.5% | 48/31 | REJECT |
| 036_keltner_multiday_tf3_time | 3m | 115 | 93 | −0.0251 | 0.0181 | −0.0432 | −0.1629 | +0.0841 | 8.7% | 49/44 | REJECT |
| 036_keltner_multiday_tf1_time | 1m | 79 | 57 | −0.0852 | 0.0166 | −0.1018 | −0.2360 | +0.0295 | 6.5% | 29/28 | INCONCLUSIVE |

**038 opening range both sides** — 0 PASS, **5 REJECT**, 1 INCONCLUSIVE. **1 of 7
clocks positive.** This is the family that PASSed and got ALPHA on BTCUSDT and
then failed its holdout.

| name | tf | tr | v | gross | cost | mean | CI low | CI high | dd | L/S | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 038_opening_range_both_sides | 4h | 254 | 162 | +0.0061 | 0.0166 | −0.0105 | −0.1420 | +0.1305 | 13.1% | 90/72 | REJECT |
| 038_opening_range_both_sides_tf60_time | 1h | 368 | 235 | −0.0149 | 0.0196 | −0.0345 | −0.1103 | +0.0397 | 12.3% | 113/122 | REJECT |
| 038_opening_range_both_sides_tf30_time | 30m | 355 | 232 | −0.0746 | 0.0176 | −0.0922 | −0.1675 | −0.0175 | 19.6% | 117/115 | REJECT |
| 038_opening_range_both_sides_tf15_time | 15m | 306 | 206 | −0.0413 | 0.0190 | −0.0603 | −0.1470 | +0.0310 | 15.7% | 102/104 | REJECT |
| 038_opening_range_both_sides_tf5_time | 5m | 208 | 139 | +0.0485 | 0.0235 | +0.0250 | −0.0813 | +0.1399 | 7.6% | 60/79 | REJECT |
| 038_opening_range_both_sides_tf3_time | 3m | 125 | 83 | −0.0118 | 0.0239 | −0.0358 | −0.1889 | +0.1199 | 6.8% | 37/46 | REJECT |
| 038_opening_range_both_sides_tf1_time | 1m | 72 | 61 | −0.0736 | 0.0261 | −0.0997 | −0.2705 | +0.0734 | 7.7% | 28/33 | INCONCLUSIVE |

**039 breakout + flow** — 0 PASS, 5 REJECT, 1 WATCH, 1 INCONCLUSIVE. **2 of 7.**

| name | tf | tr | v | gross | cost | mean | CI low | CI high | dd | L/S | verdict | baseline | benchmark |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 039_breakout_flow_confirm | 4h | 97 | 81 | −0.1526 | 0.0148 | −0.1673 | −0.3314 | +0.0077 | 15.8% | 34/47 | INCONCLUSIVE | | |
| 039_breakout_flow_confirm_tf60_time | 1h | 134 | 93 | −0.0328 | 0.0172 | −0.0500 | −0.2310 | +0.1404 | 8.6% | 33/60 | REJECT | | |
| 039_breakout_flow_confirm_tf30_time | 30m | 141 | 103 | +0.0103 | 0.0158 | −0.0055 | −0.1851 | +0.1914 | 10.3% | 42/61 | REJECT | | |
| 039_breakout_flow_confirm_tf15_time | 15m | 137 | 104 | +0.0208 | 0.0163 | +0.0045 | −0.1611 | +0.1852 | 7.9% | 40/64 | REJECT | | |
| 039_breakout_flow_confirm_tf5_time | 5m | 126 | 88 | +0.0294 | 0.0192 | +0.0102 | −0.1940 | +0.2284 | 7.7% | 34/54 | WATCH | DRIFT | NO_EDGE |
| 039_breakout_flow_confirm_tf3_time | 3m | 121 | 86 | −0.0665 | 0.0207 | −0.0871 | −0.2712 | +0.1050 | 10.1% | 34/52 | REJECT | | |
| 039_breakout_flow_confirm_tf1_time | 1m | 101 | 86 | −0.1143 | 0.0173 | −0.1315 | −0.3197 | +0.0757 | 14.1% | 35/51 | REJECT | | |

**041 impulse, not crowded** — 0 PASS, 5 REJECT, 1 WATCH, 1 INCONCLUSIVE. **2 of
7.** The same family that produced the SOLUSDT PASS.

| name | tf | tr | v | gross | cost | mean | CI low | CI high | dd | L/S | verdict | baseline | benchmark |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 041_impulse_not_crowded | 4h | 107 | 91 | −0.1183 | 0.0106 | −0.1289 | −0.2862 | +0.0369 | 13.5% | 48/43 | REJECT | | |
| 041_impulse_not_crowded_tf60_time | 1h | 149 | 111 | −0.0474 | 0.0137 | −0.0612 | −0.2226 | +0.1113 | 12.8% | 56/55 | REJECT | | |
| 041_impulse_not_crowded_tf30_time | 30m | 134 | 83 | −0.0120 | 0.0097 | −0.0217 | −0.1986 | +0.1674 | 6.3% | 46/37 | REJECT | | |
| 041_impulse_not_crowded_tf15_time | 15m | 155 | 112 | +0.0071 | 0.0127 | −0.0056 | −0.1708 | +0.1718 | 9.2% | 52/60 | REJECT | | |
| 041_impulse_not_crowded_tf5_time | 5m | 136 | 107 | −0.0617 | 0.0128 | −0.0745 | −0.2428 | +0.0978 | 10.8% | 49/58 | REJECT | | |
| 041_impulse_not_crowded_tf3_time | 3m | 114 | 97 | +0.1855 | 0.0147 | +0.1708 | −0.0139 | +0.3609 | 5.5% | 52/45 | WATCH | DRIFT | NO_EDGE |
| 041_impulse_not_crowded_tf1_time | 1m | 83 | 72 | +0.0737 | 0.0159 | +0.0579 | −0.1800 | +0.3166 | 8.8% | 43/29 | INCONCLUSIVE | | |

**043 squeeze break** — 0 PASS, 4 REJECT, 2 WATCH, 1 INCONCLUSIVE. **2 of 7.**

| name | tf | tr | v | gross | cost | mean | CI low | CI high | dd | L/S | verdict | baseline | benchmark |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 043_squeeze_multiday_break | 4h | 108 | 62 | −0.0680 | 0.0173 | −0.0853 | −0.1950 | +0.0286 | 6.1% | 35/27 | REJECT | | |
| 043_squeeze_multiday_break_tf60_time | 1h | 118 | 65 | −0.0849 | 0.0188 | −0.1038 | −0.2340 | +0.0258 | 6.8% | 35/30 | REJECT | | |
| 043_squeeze_multiday_break_tf30_time | 30m | 123 | 71 | −0.0125 | 0.0214 | −0.0339 | −0.1484 | +0.0830 | 4.0% | 34/37 | REJECT | | |
| 043_squeeze_multiday_break_tf15_time | 15m | 145 | 91 | −0.0862 | 0.0204 | −0.1066 | −0.2104 | −0.0039 | 10.9% | 46/45 | REJECT | | |
| 043_squeeze_multiday_break_tf5_time | 5m | 133 | 70 | +0.0636 | 0.0226 | +0.0410 | −0.1587 | +0.2432 | 4.5% | 34/36 | WATCH | DRIFT | NO_EDGE |
| 043_squeeze_multiday_break_tf3_time | 3m | 157 | 89 | −0.0063 | 0.0210 | −0.0273 | −0.1606 | +0.1180 | 4.8% | 48/41 | REJECT | | |
| 043_squeeze_multiday_break_tf1_time | 1m | 118 | 70 | +0.0443 | 0.0244 | +0.0199 | −0.1942 | +0.2482 | 7.0% | 33/37 | WATCH | DRIFT | NO_EDGE |

### Every gate the round's ten WATCHes failed

| config | trades | mean R | needed at that n | CI low | stress | failed gates |
|---|---|---|---|---|---|---|
| 034 @3m | 79 | +0.1864 | 0.1756 | −0.0212 | +0.1786 | ci_lo |
| 035 @1h | 70 | +0.1961 | 0.1875 | −0.0103 | +0.1885 | **ci_lo** |
| 035 @3m | 81 | +0.1308 | 0.1741 | −0.0938 | +0.1230 | trades<100, ci_lo |
| 035 @4h | 66 | +0.0462 | 0.1931 | −0.1370 | +0.0386 | trades<100, ci_lo |
| 035 @30m | 65 | +0.0633 | 0.1945 | −0.1869 | +0.0556 | trades<100, ci_lo |
| 035 @5m | 92 | +0.0178 | 0.1635 | −0.1834 | +0.0101 | trades<100, ci_lo |
| 039 @5m | 88 | +0.0102 | 0.1671 | −0.1940 | +0.0024 | trades<100, ci_lo |
| 041 @3m | 97 | +0.1708 | 0.1592 | −0.0139 | +0.1630 | ci_lo |
| 043 @1m | 70 | +0.0199 | 0.1875 | −0.1942 | +0.0116 | trades<100, ci_lo |
| 043 @5m | 70 | +0.0410 | 0.1875 | −0.1587 | +0.0331 | trades<100, ci_lo |

**Every one of them fails on the 95% CI lower bound, and eight of ten also fail
on the 100-trade floor. Not one fails on drawdown and not one fails on the x1.5
cost stress.** BNBUSDT produced effects of the right size on 54-97 trades and
could not put a single CI above zero.

### The controls: 9 DRIFT, 1 SKILL, 9 NO_EDGE, 1 ALPHA

| config | baseline | benchmark | note |
|---|---|---|---|
| 034 @3m (+0.1864) | **DRIFT** | **ALPHA** | the round's largest VALID number and it is DRIFT |
| **035 @1h (+0.1961)** | **SKILL** | NO_EDGE | the only SKILL on BNB |
| 041 @3m (+0.1708) | DRIFT | NO_EDGE | the SOLUSDT PASS family |
| 035 @3m (+0.1308) | DRIFT | NO_EDGE | |
| 035 @30m (+0.0633) | DRIFT | NO_EDGE | |
| 035 @4h (+0.0462) | DRIFT | NO_EDGE | |
| 043 @5m (+0.0410) | DRIFT | NO_EDGE | |
| 043 @1m (+0.0199) | DRIFT | NO_EDGE | the control Exp 002 listed as missing |
| 039 @5m (+0.0102) | DRIFT | NO_EDGE | |
| 035 @5m (+0.0178) | DRIFT | NO_EDGE | |

**The round's two most eye-catching rows are both disqualified by the controls,
in opposite directions, and that is the whole finding.** 034@3m has the largest
VALID mean R and the only ALPHA, and it is DRIFT. 035@1h is the only SKILL and it
is NO_EDGE. Neither is a strategy: `PLAN.md` §5 step 1 stops a configuration that
has neither SKILL nor ALPHA, and stops one that has one without the other.

**035@1h is recorded and not pursued.** TRAIN 113 trades +0.2931, VALID 70
trades gross +0.2132, cost 0.0171, mean R **+0.1961**, CI [−0.0103, +0.4172],
CAGR +6.8%, maxDD 4.7%, stress +0.1885, 42 long / 28 short, per-year 2023
+0.1007 and 2024 +0.2916 on 35 trades each - the year split is unusually even,
and 2024 is the stronger half. `baseline.py` says SKILL. `benchmark.py` says
NO_EDGE: alpha +0.0467/yr on VALID with CI [−0.0185, +0.1201] and +0.0510 on
TRAIN with CI [−0.0715, +0.2047], so both alpha intervals contain zero, and
Sharpe 1.27 equals buy & hold's 1.27.

**It is a WATCH, so `--final` is refused by AGENTS.md rule 4, and no holdout was
run or is warranted.** BNBUSDT has no PASS, so the BNB holdout has never been
touched and stays sealed.

### What B1 establishes that Rounds E1, 5 and 6 did not

**1. The most robust result the project ever produced did not survive a third
coin.** 039 was positive on **7/7 BTC clocks and 7/7 ETH clocks - fourteen of
fourteen** - and on SOLUSDT it was **7/7 again, twenty-one of twenty-one**. On
BNBUSDT it is **2/7**. The same frozen idea file, unchanged, on a fourth coin.
Whatever produced 039's gross move is a property of BTC, ETH and SOL, and not of
BNB, and nothing in the project predicted which would be which. **Robustness
across clocks and across three coins is not evidence of an edge** - that is now
measured, not argued: the most robust family in the project was also a family
whose BTC version failed its holdout.

**2. 038 and 036 are dead here.** 036 Keltner is **0 of 7** on BNB - not one
clock positive - having been 4/7 on BTC and 4/7 on ETH. 038 opening range, the
BTC PASS that got ALPHA and then failed its holdout, is **1 of 7**.

**3. BNBUSDT's own cost prediction was confirmed too.** The Exp 001 formula gave
0.0775 R at a 6% stop and 96 h; measured VALID `cost_r` is **min 0.0097, median
0.0173, max 0.0261**, with `size_skips` 0 throughout. The formula is an upper
bound because it multiplies the absolute funding rate by the number of
settlements, where a position pays the signed sum.

**4. The signal-count prediction held.** Exp 001 said 039, 041 and 043 would
trade about half of what they trade on BTC and might be INCONCLUSIVE: on BNB
they produced 6 INCONCLUSIVE rows against 3 on BTC and 0 on ETH, and their best
VALID samples are 88, 97 and 70 trades against 103-132 on the 36-month coins.

**5. Cross-coin reading, all four coins, VALID mean R positive on how many of the
seven clocks:**

| family | BTC | ETH | BNB | SOL |
|---|---|---|---|---|
| 034 multi-day reversal | 0/7 | 3/7 | 1/7 | 1/7 |
| 035 multi-day momentum | 7/7 | 4/7 | **5/7** | 6/7 |
| 036 Keltner multi-day | 4/7 | 4/7 | **0/7** | 5/7 |
| 038 opening range | 4/7 | 5/7 | **1/7** | 3/7 |
| 039 breakout + flow | **7/7** | **7/7** | **2/7** | **7/7** |
| 041 impulse, not crowded | 6/7 | 7/7 | 2/7 | **7/7** |
| 043 squeeze break | 7/7 | 6/7 | 2/7 | 3/7 |

**035 is the only family that is broadly positive on all four coins** (7/7, 4/7,
5/7, 6/7), and its BNB 1h configuration is the only SKILL reading on a third or
fourth coin. That is worth recording as the most consistent *family* in the
project. It is not worth trading: no BNB configuration is a PASS, the SKILL one
is NO_EDGE, and BTC's 035 was never better than a WATCH.

### Verdict

`REJECT`, and the round closes BNBUSDT. **0 PASS, 0 CONFIRMED, the BNB holdout
never touched.** 49 evaluations, 33 REJECT, 10 WATCH, 6 INCONCLUSIVE, and a
control on every single WATCH: 9 DRIFT, 1 SKILL, 9 NO_EDGE, 1 ALPHA, with the
SKILL row NO_EDGE and the ALPHA row DRIFT.

**The stop rule agreed in the Exp 001 pre-registration has now fired on all four
coins.** Nothing in this project is a tested strategy, and no real money should
follow from it.
