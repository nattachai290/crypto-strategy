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
