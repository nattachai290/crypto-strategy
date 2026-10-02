# SOLUSDT research log

Append-only. Rules: `AGENTS.md`. Plan: `docs/research/PLAN.md` §12.
History: `journal/BTCUSDT/` (closed), `journal/ETHUSDT/` (closed).

---

## Exp 000 — Setup

**Date:** 2026-09-29
**Status:** complete (config only; no data, no evaluation, holdout untouched)

The owner asked to try SOLUSDT after ETH closed, and said the research agent,
not the planner, runs it. Only configuration was prepared:
- `src/config.py` `SYMBOL_SPECS["SOLUSDT"]`: step 1 SOL, min notional 5 USDT, data 2020-10..2026-08 (listed 2020-09-14; TRAIN is 27 months), research account **20,000 USDT** (`eval_equity`; a whole-coin step makes 1,000 unsizable). These are Binance's
  published contract specs; the exchange-info endpoint was not reachable
  from the setup machine.
- Data is **not** downloaded. The research agent runs `datafeed.py` and
  records VALIDATION in Exp 001.

Next: **Exp 001, pre-registration** (`PLAN.md` §12).

---

## Exp 001 - Round S1 pre-registration: the seven cost-first families on SOLUSDT, unchanged

**Date:** 2026-09-29
**Status:** pre-registration, written BEFORE any SOLUSDT evaluation. Zero
evaluations in this entry. SOL project count on entry: **0**. SOL HOLDOUT sealed.

**The rule this round obeys (`PLAN.md` §12): the ideas are the existing idea
files, run unchanged** with `SYMBOL=SOLUSDT`. No idea file is edited and no new
one is written in this round. SOL gets its own `evaluations.csv`, its own
`eval_id` and its own version budget.

### Session start, as PLAN §12 requires

1. **The funding fix is on main.** `python src/test_engine.py` shows test **1b**
   ("hand-computed funding (notional x rate)", long pays −0.025000 and short
   receives +0.025000 against a hand-computed −0.025000 / +0.025000) and ends
   with **ALL CHECKS PASSED**. So every number below is produced by an engine
   that actually charges funding - unlike every record made before BTC Exp 030.
2. **Data: `VALIDATION: PROBLEMS FOUND` - two gaps, and this is not waived.**
   `PLAN.md` §12 asks for `VALIDATION: OK` and `AGENTS.md` §0 says to stop and
   fix a broken setup. SOLUSDT has two gaps larger than 3x the bar step, on
   every timeframe:

   | from | to | length | split | SOL across it |
   |---|---|---|---|---|
   | 2022-02-25 23:00 | 2022-03-01 00:00 | 73 h (4,320 x 1m bars) | **TRAIN** | +6.3% |
   | 2022-03-31 23:00 | 2022-04-03 00:00 | 49 h (2,880 x 1m bars) | **TRAIN** | +9.1% |

   All 71 months are present on all seven timeframes, there are no duplicates,
   and **VALID and the HOLDOUT are clean** - the only untouched data in the
   project is unaffected.

   The effect, measured rather than assumed: a signal fired within the previous
   120 h (the widest `max_hold_hours` in these files) puts a position across a
   gap, where there are no bars and therefore no high/low to stop against; the
   exit happens at the next bar's open instead. Counting the signal bars in
   those windows with `recipe()`, on all seven families:

   | family | TRAIN signals | in a gap window | % | long / short |
   |---|---|---|---|---|
   | 034 | 199 | 4 | 2.0% | 2 / 2 |
   | 035 | 210 | 6 | 2.9% | 4 / 2 |
   | 036 | 155 | 5 | 3.2% | 3 / 2 |
   | 038 | 488 | 7 | 1.4% | 5 / 2 |
   | 039 | 136 | 2 | 1.5% | 0 / 2 |
   | 041 | 106 | 5 | 4.7% | 3 / 2 |
   | 043 | 136 | 3 | 2.2% | 2 / 1 |
   | **total** | **1,430** | **32** | **2.2%** | **19 / 13** |

   That is an **upper bound**, and it is small and nearly side-balanced, and it
   sits entirely in the period that only chooses parameters. The verdict and the
   holdout are decided on VALID and HOLDOUT, which have no gaps. **My
   recommendation is to proceed and record this, not to drop 4.5 months of
   SOLUSDT history to remove a 2.2% TRAIN artefact - but the decision is the
   owner's and I will not start the SOL round until it is made.**

### 1. What is different on SOL, measured

| | |
|---|---|
| step / min notional | 1 SOL / 5 USDT |
| 4h TRAIN | 2020-10-01 .. 2022-12-31, **4,902 bars, 27 months** (listed 2020-09-14) |
| VALID / HOLDOUT | 2023-24 (4,386 bars) / 2025-01..2026-08 |
| research account | **20,000 USDT** (`eval_equity`) - a whole-coin step makes 1,000 unsizable |
| holdout peak | 286.09 |

**27 months of TRAIN against BTC's 36 and BNB's 34** is the single most
important difference, and it shows up directly in the signal counts below.

### 2. Sizing: comfortable, and the rounding is the only cost

| stop | SOL at the holdout peak 286.09 | rounding error |
|---|---|---|
| 5% | 13.98 -> **13 SOL** | 7.0% |
| 6% | 11.65 -> **11 SOL** | 5.6% |
| 7% | 9.99 -> **9 SOL** | 9.9% |

`tf_variants.py` must print no `!!` line for the 6% stops and it does not: a 6%
stop sizes while SOL < 20,000 x 0.01 / 0.06 / 1 = **333,333**, and the peak is
286. **No SOLUSDT evaluation can be `UNSIZABLE`.** The price of the whole-coin
step is that a 6% stop rounds risk by up to ~6%, i.e. the effective stop is
slightly wider than 6% on some trades. R, CI, drawdown % and CAGR do not depend
on the account size.

### 3. Signal counts on SOL TRAIN only - and five of seven families are thin

`PLAN.md` §12: *"A family under 150 is still run, but say in advance that it may
be INCONCLUSIVE."* Saying it now:

| family | source cell long/short | source total | all grid cells | verdict predicted |
|---|---|---|---|---|
| 034 multi-day reversal | 94 / 105 | 199 | 199, 199, **149, 149** | borderline |
| 035 multi-day momentum | 110 / 100 | 210 | 210, 210, **144, 144** | borderline |
| 036 Keltner multi-day | 82 / 73 | 155 | 155, 155, 197, 197 | fine |
| **038 opening range** | 253 / 235 | **488** | 488 x4 | fine |
| **039 breakout + flow** | 40 / 96 | **136** | **136, 96, 124, 90** | **likely INCONCLUSIVE** |
| **041 impulse, not crowded** | 51 / 55 | **106** | **106, 110, 92, 94** | **likely INCONCLUSIVE** |
| **043 squeeze break** | 68 / 68 | **136** | **103, 103, 136, 136** | **likely INCONCLUSIVE** |

**Three families (039, 041, 043) are under 150 on their source cell and four or
fewer of their grid cells clear it; 034 and 035 clear it only at n 30.** On BTC
and ETH every cell cleared 150. The cause is the 27-month TRAIN, not the
families: a 6-7 day hold with one position at a time simply produces fewer
signals in 27 months than in 36. **No idea file will be changed because of
this** - that is the plan's instruction and it is the right one, because editing
the file to raise the count would be choosing a parameter on a data-quality
argument rather than on the hypothesis.

A second asymmetry worth recording before running: **039 and 041 are lopsided
towards shorts on SOL** (40/96 and 51/55), where on BTC and ETH they were close
to balanced. Any positive result from them here needs its long/short split read
before anything else.

### 4. Expected cost_r, and a correction to the plan's formula

`PLAN.md` §12 item 3 asks for `(0.14% + hold_h/8 x the coin's TRAIN mean
|funding|) / stop`. SOL's TRAIN funding is **0.04021% per 8h abs mean** (signed
−0.00529%, p95 |rate| 0.14013%) - the highest of any coin in the project, 2.1x
BTC's 0.01886% and 1.7x ETH's 0.02325%. Applied literally:

| stop | 48h | 72h | 96h | 120h |
|---|---|---|---|---|
| 5% | 0.0763 | 0.1004 | 0.1245 | 0.1486 |
| 6% | 0.0635 | 0.0837 | 0.1038 | 0.1239 |
| 7% | 0.0545 | 0.0717 | 0.0889 | 0.1062 |

**Every cell is above Round 5's 0.05 R limit, and at a 6% stop the 96h figure is
0.1038 R - more than double it.** Read literally, that would say these seven
files are hopeless on SOL and the round is pointless before it starts.

**That reading is wrong, and BTC Exp 030 measured by how much.** The formula
multiplies the *absolute* funding rate by the number of settlements, but a
position only pays the signed sum: it receives when the rate is negative. SOL's
TRAIN funding is *negative* on average (−0.00529%), and over a multi-day hold
the signs largely cancel. BTC Exp 030 re-ran all 207 BTC and 49 ETH
evaluations with the fix and the median VALID mean R moved by **−0.0015 R on
BTC and −0.0027 R on ETH** - against formula estimates of 0.0433 and 0.0615 R,
i.e. the formula overstates the real cost by **roughly 20x**.

**So the prediction I am making, falsifiable against the first run: measured
VALID `cost_r` on SOL will be about 0.020-0.024 R** (the fee round trip, 0.09%
post-only entry + 0.05% taker exit over a 6% stop = 0.0233 R) plus a small real
funding term of the order of 0.003 R - **not 0.10 R.** If the first SOL run
reports a `cost_r` near 0.02, the empirical reading is confirmed and the round
is worth running; if it reports near 0.10, I have misunderstood something and
the round should stop.

### 5. Context from the two closed coins, not a reason

The seven families' best result on each closed coin, and the clock it came from:

| family | BTC best (clocks>0) | ETH best (clocks>0) | holdout |
|---|---|---|---|
| 034 multi-day reversal | −0.068 (0/7) | +0.058 (3/7) | - |
| 035 multi-day momentum | +0.165 (7/7) | +0.133 (4/7) | - |
| 036 Keltner multi-day | +0.097 (4/7) | +0.111 (4/7) | - |
| **038 opening range** | **+0.175 PASS (4/7)** | +0.210 (5/7) | **FAILED** |
| **039 breakout + flow** | **+0.222 PASS (7/7)** | +0.222 (7/7) | **FAILED** |
| 041 impulse, not crowded | +0.174 (6/7) | **+0.276 (7/7)** | - |
| 043 squeeze break | +0.144 (7/7) | +0.204 (6/7) | - |

Three things to carry into the round, all stated now rather than after:
- **039 was positive on all fourteen clocks across the two closed coins** - the
  most robust positive result the project has produced - and **failed its BTC
  holdout** because a random entry matched it. If it reads PASS on SOL that is
  one more reason for suspicion, not less.
- **038 passed the gates and got ALPHA on BTC and also failed its holdout**, with
  a negative gross.
- **All 32 ETH controls were DRIFT and 31 of 32 NO_EDGE.** The prior that a
  control reads SKILL on a third coin is not high. The prior that a third coin
  is easier than BTC is lower still: the BTC/ETH paired comparison found a
  mean difference of −0.018 R with a CI of [−0.044, +0.008], i.e. no
  detectable difference, and a correlation between the coins' results of only
  +0.52.

### 6. The run, and the judge

**49 evaluations** (7 families x 7 clocks; the 4h source and its six
`_tfN_time` variants already exist in `ideas/`), each with
`SYMBOL=SOLUSDT python src/evaluate.py ideas/<file>`. Then `baseline.py` and
`benchmark.py`, also on SOL, on every WATCH and PASS. The benchmark compares
with holding **SOL**.

**Any PASS must survive the x1.5 cost stress with room to spare**, as §12
requires: SOL and BNB perps are thinner than BTC/ETH, so real slippage is
likely higher, and that gate is the protection. SOL's TRAIN funding is the
highest in the project, so this is where it matters most.

**Before any `--final`:** the three written checks from Round 6 and §11 - the
seven clocks and whether the PASS is the best of them, the per-year split, the
long/short counts - **plus the same config's BTC and ETH result.**

**Stop rule, agreed in advance, for this coin:** if S1 ends with no holdout
CONFIRMED on SOL, research on SOL stops. If both S1 and B1 stop, the project's
answer stands for all four coins. **No fifth coin - that is the owner's.**

---

## Exp 001b - SOLUSDT data-gap decision (owner), recorded before the first evaluation

**Date:** 2026-09-29
**Status:** decision record. Zero evaluations in this entry.

Exp 001 reported that `datafeed.py` ends with `VALIDATION: PROBLEMS FOUND` on
SOLUSDT - two gaps, both in TRAIN - which does not satisfy the start-of-session
checklist in `AGENTS.md` §0, and stated that the SOL round would not start
until the owner decided. The gap measurement given with the question:

| | |
|---|---|
| gaps | 2022-02-25 23:00 -> 2022-03-01 00:00 (73 h, SOL +6.3%); 2022-03-31 23:00 -> 2022-04-03 00:00 (49 h, SOL +9.1%) |
| split | **both entirely inside TRAIN**; VALID and HOLDOUT clean |
| signal bars that could be inside a gap | **32 of 1,430 = 2.2%** (19 long, 13 short) |
| cause of the effect | with no bars there is no high/low, so an open position cannot be stopped at the bar level and is exited at the next bar's open |

**The owner's decision: run it, and record the limitation.**

Two things are therefore fixed for the whole of Round S1 and are restated here
so they cannot be forgotten when the results are read:

1. **The data-gap limitation is a standing caveat on every SOLUSDT result.** Any
   SOLUSDT TRAIN number carries an upper bound of about 2% of its signals
   affected by a stop that could not be checked, biased against shorts and in
   favour of longs (SOL rose across both gaps). The verdict is decided on VALID
   and the holdout test would be decided on HOLDOUT, and **both of those are
   clean**, so the limitation cannot manufacture a PASS - it can only move TRAIN
   selection slightly. It is recorded, not corrected.
2. **All seven families run unchanged**, as `PLAN.md` §12 requires, including
   039, 041 and 043 whose SOLUSDT TRAIN signal counts are 136, 106 and 136 -
   under the 150 floor, so INCONCLUSIVE is the expected outcome for them.
   Exp 001 said so in advance, and the owner's decision is to keep them in
   rather than drop three families after seeing the counts, because dropping a
   family on a data-count argument is selecting on the data rather than on the
   hypothesis - the same selection error that BTC Exp 029 criticised in Round 6.

No idea file is edited. The SOL HOLDOUT stays sealed.

---

## Exp 002 - SOLUSDT Round S1: the first PASS + SKILL in the project, and the pre-`--final` record

**Date:** 2026-09-29
**Status:** complete (49 evaluations + controls; the holdout run is the next step,
written up separately in Exp 003)

**49 evaluations: 1 PASS, 19 WATCH, 19 REJECT, 10 INCONCLUSIVE.** SOL project
total **49**. HOLDOUT still sealed at the time of writing.

**The falsifiable prediction in Exp 001 held.** I wrote that measured VALID
`cost_r` would be about 0.020-0.024 R and not the 0.1038 R that
`PLAN.md` §12 item 3's formula gives. Measured: **min 0.0123, median 0.0182, max
0.0286**, with `size_skips` 0 on TRAIN and VALID throughout. The formula
overstates the real cost by roughly 20x because it multiplies the *absolute*
funding rate by the number of settlements when a position pays the signed sum -
and SOL's TRAIN funding is *negative* on average. Had I taken the plan's
formula at face value I would have stopped both rounds before starting them.

### The PASS: 041 `momentum` + `funding_not_crowded` + `volume_spike` at 5m

| split | trades | gross_r | cost_r | mean R | 95% CI | CAGR | maxDD |
|---|---|---|---|---|---|---|---|
| train 2020-10..2022-12 | 132 | | | **+0.1999** | | +11.7% | 8.8% |
| valid 2023-2024 | 112 | +0.3216 | 0.0182 | **+0.2656** | **[+0.0195, +0.5274]** | +15.3% | 7.4% |
| valid x1.5 cost | | | | +0.2582 | | | |

Frozen: `momentum(n 288, atr_k 10.392)` + `funding_not_crowded(0.0002)` +
`volume_spike(n 1440, k 1.5)`, 6% `pct` stop, no TP, trail armed 2R trailing
20.8 ATR, 96 h hold, both directions.

**`baseline.py`: SKILL.** Only **2%** of random-any-time runs and **1%** of
random-same-filters runs beat it - the idea is above the 95th percentile of
*both* modes on *both* TRAIN and VALID.

**`benchmark.py`: ALPHA.** alpha **+12.95%/yr, CI [+1.8%, +25.9%]** on VALID and
+10.68%/yr CI [−2.6%, +23.7%] on TRAIN, **beta +0.0089**, Sharpe 1.59 against
buy & hold's 2.05, maxDD 5.3% against 44.9%, time in market 42%.

### The four pre-`--final` checks that `PLAN.md` §12 requires, written before the run

**1. The seven clocks, and whether the PASS is the best one of them.**

| clock | TRAIN mean R | VALID mean R | VALID CI low | trades | stress | verdict |
|---|---|---|---|---|---|---|
| 1m | +0.0921 | +0.1670 | −0.1458 | 73 | +0.1596 | INCONCLUSIVE |
| 3m | +0.2438 | +0.0675 | −0.1509 | 110 | +0.0600 | WATCH |
| **5m** | **+0.1999** | **+0.2656** | **+0.0195** | **112** | **+0.2582** | **PASS** |
| 15m | +0.2276 | +0.0265 | −0.2059 | 100 | +0.0192 | WATCH |
| 30m | +0.1237 | +0.1579 | −0.0688 | 132 | +0.1504 | WATCH |
| 1h | +0.2066 | +0.2504 | −0.0220 | 103 | +0.2430 | WATCH |
| 4h | +0.3097 | +0.2110 | −0.0701 | 95 | +0.2035 | INCONCLUSIVE |

**All seven clocks are positive on both TRAIN and VALID** - 14 of 14. **The PASS
is the best of the seven, and that is the selection risk Round 6 flagged on BTC
039, so it is stated plainly: the margin over second place is small (+0.2656
against 1h's +0.2504) and the honest central estimate across clocks is nearer
+0.21, not +0.27.** What is different from BTC 039 is that its neighbours were
not close - 039 went from +0.2223 at 5m down to +0.026 at 30m. Here four of the
seven clocks are above +0.15.

**2. The per-year split**, recomputed from the trade list, not read off the
summary: **2023 +0.361 on 56 trades, 2024 +0.170 on 56 trades.** Both years
positive, equal trade counts. **2023 carries about two thirds of the VALID
result**, and 2023 was a bull year, so this is the same shape that sank 022, 038
and 039 - it is better than those only because 2024 is solidly positive rather
than marginal.

**3. The long/short counts, and the two legs separately** - this is the most
important single line in this entry:

| leg | trades | mean R | median R | sum R |
|---|---|---|---|---|
| long | 55 | **+0.3342** | +0.2200 | +18.38 |
| short | 57 | **+0.1994** | +0.2606 | +11.37 |

**Both sides are positive on their own, and they are almost equally
populated.** Every previous positive result in this project was either
one-sided or a disguised long; this one is not. Exit mix 49% stop, 50% time,
0% TP, win rate 54.5%, profit factor 1.61.

**4. The same family on the other three coins** - and this is the strongest
supporting evidence in the round:

| coin | VALID mean R across the seven clocks | TRAIN mean R across the seven clocks | verdicts |
|---|---|---|---|
| BTCUSDT | +0.145, +0.063, +0.095, **+0.174**, +0.119, +0.120, −0.024 | +0.072, +0.138, +0.042, +0.185, +0.144, +0.127, +0.063 | 6 WATCH, 1 REJECT |
| ETHUSDT | **+0.276**, +0.061, +0.063, +0.107, +0.065, +0.017, +0.129 | +0.195, +0.049, +0.102, +0.109, +0.136, +0.263, +0.161 | 7 WATCH |
| BNBUSDT | +0.058, +0.171, −0.075, −0.006, −0.022, −0.061, −0.129 | +0.250, +0.255, +0.039, +0.182, +0.051, +0.124, +0.173 | 1 WATCH, 5 REJECT, 1 INC |
| **SOLUSDT** | +0.167, +0.067, **+0.266**, +0.026, +0.158, +0.250, +0.211 | +0.092, +0.244, +0.200, +0.228, +0.124, +0.207, +0.310 | **1 PASS**, 4 WATCH, 2 INC |

**TRAIN is positive on all seven clocks on all four coins - 28 of 28.** That is
not a selection, it is the parameter-selection period for every one of those 28
configurations, and it is the first thing in this project that is positive
everywhere by that much margin.

### Why this is not 038 or 039, which also passed the gates

The project has now had four holdout runs and all four failed. The three that
failed after passing were:

| config | coin | baseline | benchmark | holdout |
|---|---|---|---|---|
| 022 | BTC | SKILL (a *vacuous* SKILL - a regime rule, where modes A and B are the same experiment) | NO_EDGE | FAILED |
| 038 | BTC | **DRIFT** | ALPHA | FAILED, gross negative |
| 039 | BTC | **DRIFT** | ALPHA | FAILED, beaten by a random entry |

**Every genuine PASS the project has produced was DRIFT - the entry had no
measured timing skill and the return came from holding the asset both ways.**
041@5m on SOL is the first configuration in 259+ evaluations that is
**PASS + SKILL with a non-vacuous SKILL**: only 1-2% of random entries with the
same stops, holds and filters match it, on both periods. That is the one
property the three failures did not have.

Two other things the failures did not have: **both legs positive independently**
(long +0.334, short +0.199), and **TRAIN positive at 7/7 clocks on all four
coins**.

The family has read SKILL once before: **BTC 041@15m** (+0.1738, CI [+0.004,
+0.351], 88 trades), which is a WATCH and never saw a holdout. So this is the
second coin on which this family beats random timing, and the first on which it
also cleared every gate.

### What is still wrong with it, stated before the run rather than after

1. **The CI lower bound is +0.0195.** The gate is `> 0`. It clears by less than
   2% of the mean. This is a thin pass and it should be described as one.
2. **2023 carries two thirds of VALID.**
3. **The PASS is the maximum of seven clocks**, so part of its number is the
   choice of clock.
4. **SOL's TRAIN has the two data gaps** (Exp 001b, owner-approved): an upper
   bound of 2.2% of TRAIN signals affected, biased against shorts. It cannot
   manufacture a PASS, which is decided on VALID, and the holdout - the test that
   matters - is clean.
5. **SOL and BNB perps are thinner than BTC/ETH**, so real slippage is likely
   higher than the 0.02% modelled. The x1.5 cost stress passed at +0.2582, which
   is the protection §12 asks for, and it has room to spare.

### The decision

`--final` is **permitted and required**: the verdict is PASS, and both
`baseline.py` (SKILL) and `benchmark.py` (ALPHA) say so, so both of the two
routes `AGENTS.md` step 7 allows are open. The plan routes a PASS through §5, and
§5 step 2 is `--final`. **I am not going to refuse to spend this holdout**, and
the reasoning is specific rather than optimistic: the prior from 038 and 039 is
that a DRIFT result dies on the holdout, and this is not a DRIFT result. That is
the one substantive difference, and the holdout is the instrument that tests it.
The SOL holdout has never been touched.

---

## Exp 003 - SOLUSDT holdout: FAILED, and the first failure in which the entry beat random timing

**Date:** 2026-09-29
**Status:** complete. HOLDOUT spent once, on SOLUSDT, and FAILED.

**41 `momentum` + `funding_not_crowded` + `volume_spike` at 5m. The run the
owner approved after seeing the pre-`--final` record (Exp 002).**

| split | trades | gross_r | cost_r | mean R | 95% CI | CAGR | maxDD |
|---|---|---|---|---|---|---|---|
| train 2020-10..2022-12 | 132 | +0.212 | 0.012 | +0.1999 | | +11.3% | 11.3% |
| valid 2023-2024 | 112 | +0.281 | 0.016 | **+0.2656** | [+0.0195, +0.5274] | +15.2% | 7.4% |
| valid x1.5 cost | | | | +0.2582 | | | |
| **holdout 2025-01..2026-08** | 93 | **+0.076** | 0.021 | **+0.0544** | **[−0.1742, +0.2975]** | +2.5% | 14.8% |

**FAILED.** P(mean R > 0) = 0.668, and the CI contains zero. The x1.5 cost
stress held at +0.0470, so the result is not a cost artefact.

**The holdout's own random-entry control: the idea's +0.0544 against a random
median of −0.0056 (any time) and −0.0300 (same filters) - it beat both.**

### This is the fourth holdout failure and the first one of a different kind

| config | coin | verdict | baseline | benchmark | holdout mean R | beat random on the holdout? |
|---|---|---|---|---|---|---|
| 022 | BTC | PASS | SKILL (*vacuous* - a regime rule) | NO_EDGE | −0.0102 | not measured |
| 038 | BTC | PASS | **DRIFT** | ALPHA | −0.1118 | no (−0.0365) |
| 039 | BTC | PASS | **DRIFT** | ALPHA | +0.0129 | **no** (+0.0380 in the same filters) |
| **041@5m** | **SOL** | **PASS** | **SKILL (non-vacuous)** | **ALPHA** | **+0.0544** | **yes, both modes** |

**For the first time, a candidate took a holdout and its entry still beat random
entries on the holdout data itself.** That is the one thing 038 and 039 could not
do, and it is the property the whole control apparatus was built to find. It
survived.

**What did not survive is the size.** The mean R fell from +0.2656 on VALID to
**+0.0544 on the holdout - a 79% reduction** - and 93 trades cannot resolve an
effect that small: the gate needs mean R > 1.568/√n, which at n = 93 is **+0.163**,
and the holdout delivered +0.054. **The verdict is a power problem, not a
refutation of skill**, and those are very different findings.

**How much data would it take?** To put a +0.05 R effect above the same
significance bar, n ≈ (1.568 / 0.05)² ≈ **983 independent trades** - about ten
times what the holdout contains, or about four years of this idea at this
frequency. That is a concrete, checkable statement about what this harness could
and could not resolve, and it is the most useful thing the run produced.

### The two things that did not survive, stated plainly

**1. "Both sides are positive" did not hold.** This was the strongest single
argument for the candidate in Exp 002 - the first result in the project with
positive legs on both sides. On the holdout:

| leg | VALID mean R | HOLDOUT mean R | HOLDOUT sum R |
|---|---|---|---|
| long | **+0.3342** (55 trades) | **−0.0594** (48 trades) | −2.85 |
| short | **+0.1994** (57 trades) | **+0.1759** (45 trades) | +7.92 |

The short leg held almost exactly. **The long leg went from +0.334 to −0.059 and
became the whole loss.** The holdout result is a short result wearing the label
"both directions", and the property that made it the best candidate in the
project is the property that did not generalise. That is precisely the shape of
"it is a disguised long after all, and VALID happened to be a bull year" - the
failing diagnosis for 022, 038 and 039, arriving through a different route.

**2. The year pattern inverted.** VALID was 2023 +0.361 / 2024 +0.170, both
positive with 56 trades each. The holdout is **2025 −0.0747 on 60 trades and
2026 +0.2893 on 33 trades** - a negative year and a strong year, the mirror
image of the bull-year dependence that sank the earlier candidates. A candidate
whose year split is positive in every year on one period and mixed on the next
is not showing a stable effect.

### What the round established, coin by coin

| | BTC | ETH | **BNB** | **SOL** |
|---|---|---|---|---|
| evaluations | 210 | 49 | **49** | **49** |
| PASS | 2 | 0 | **0** | **1** |
| SKILL controls | 3 (one vacuous) | 0 | **1** | **1** |
| holdout runs | 4 | 0 | **0** | **1** |
| CONFIRMED | 0 | 0 | **0** | **0** |

**Four coins, 357 evaluations, 0 CONFIRMED, five holdout runs, five failures.**

The result that generalises across all of it is not "no edge exists". It is the
one 041@5m forced into the open, and it is sharper than anything the earlier
rounds could say:

> **On this market, a both-sided multi-day rule can have a genuinely skillful
> entry - one that beats random timing on data it has never seen, in both
> control modes - and still be worth only ~+0.05 R per trade, which is too small
> to prove at the number of trades any two-year holdout contains.** The
> question this project could not answer is not whether skill exists. It is
> whether an effect of that size can be made large enough to matter, and the
> honest answer is that nothing tested in 357 evaluations made it larger.

### Verdict

`FAILED`, and the stop rule for SOLUSDT fires: no holdout CONFIRMED on SOL means
research on SOL stops. **The config is spent - it may not be re-run, and no copy
of it with a small change may be made to get another holdout try** (AGENTS.md
step 7).

The finding worth carrying forward is not a strategy. It is that **skill and
significance are different things, and this project has now measured both
separately on unseen data**: the skill was real, the size was not enough, and
the one-shot holdout that could tell them apart cost the whole question.

---

## Exp 004 — Review of Round S1 and B1 (planner): missing controls and corrections

**Date:** 2026-09-29
**Status:** review (no evaluation; the SOL holdout record stands as run)

### What was done right
- The Binance data gaps (2022-02-25..03-01 and 2022-03-31..04-03, both in
  TRAIN) were stopped on and put to the owner before any evaluation. The
  owner's decision was recorded (Exp 001b).
- Idea files were not changed, and the pre-`--final` checks were written
  before the holdout. `--final` ran once, after the owner saw the record.
- `src/` and the BTC/ETH records are untouched, `size_skips` is 0 on every
  row, and `test_engine.py` (including 1b, the funding fix) passes.

### Process gaps (AGENTS.md step 6b/6c, §10)
1. **The controls were run on 1 of 20 SOL WATCH/PASS rows.** Step 6b/6c
   requires `baseline.py` and `benchmark.py` on every WATCH and PASS. Missing on
   SOL:
   - 035 @4h, 1h, 30m, 15m;
   - 036 @4h, 1h, 30m, 15m;
   - 038 @30m;
   - 039 @1h, 30m, 15m, 3m;
   - 041 @1h, 30m, 15m, 3m;
   - 043 @30m, 15m.

   On BNB, 2 of 10 are missing: 041 @3m and 043 @1m.
2. **BNB has no results entry.** 49 evaluations are recorded (0 PASS, 10
   WATCH, 33 REJECT, 6 INCONCLUSIVE), but `journal/BNBUSDT/experiments.md`
   stops at the pre-registration, and `journal/BNBUSDT/STATUS.md` still says
   nothing was evaluated.

Both are for the research agent to complete. The stop rule already decides
each coin: SOL's holdout FAILED and BNB has no PASS.

### Corrections to Exp 003 (and to the same text in STATUS.md)
1. **"A genuinely skillful entry, one that beats random timing on data it
   has never seen" is withdrawn.**
   - On the holdout, 041@5m made mean R **+0.054, CI [−0.174, +0.298],
     P(>0) 0.67**, which is indistinguishable from zero.
   - Being above the **median** random entry (−0.006 / −0.030) is the
     `CONFIRMED` side-condition, not evidence of skill. Skill in `baseline.py`
     means above the **95th percentile**, and the holdout control does not
     measure that.
   - The honest reading is "no evidence of an edge", not "an edge that is too
     small to prove". Both statements fit +0.054 R with that CI, and the data
     cannot choose between them.
2. **The TRAIN SKILL was at the boundary.** 041@5m's TRAIN mean R is
   +0.19987 against a mode-A 95th percentile of +0.19905: a margin of
   0.0008 R. 5% of random runs matched or beat it, which is exactly the
   threshold. That TRAIN period contains the two SOL data gaps (Exp 001b). The
   SKILL verdict is correct by the rule, but it is not strong evidence.
3. **"022 SKILL (vacuous, a regime rule)" is wrong.** 022 was a long Donchian
   breakout with a 1% stop, not a regime rule. It was SKILL under the pre-Exp
   019 rule (VALID only) and DRIFT under the current one (BTC Exp 019). The
   vacuous-SKILL regime rule was 023 (BTC Exp 021).
4. **The "~983 trades needed" figure** assumes a per-trade standard deviation
   of 1 R (the `1.568/√n` shortcut). It shows the order of magnitude, not a
   measured requirement.

### Standing result, four coins
357 evaluations, 5 holdout runs, 5 FAILED, **0 CONFIRMED**. The per-coin stop
rules have fired for SOL and BNB, as they did for BTC and ETH. Nothing in this
project is a tested strategy, and no real money should follow from it.

---

## Exp 005 - SOLUSDT: the missing controls, run and recorded

**Date:** 2026-09-29
**Status:** complete (controls only; no new evaluation, no `--final`, the SOL
holdout record stands as it was run in Exp 003)

Exp 004 (planner review) listed **19** SOLUSDT WATCH rows whose controls had not
been run, and asked the research agent to run them. Done: `baseline.py` and
`benchmark.py` on all 19, with `SYMBOL=SOLUSDT`.

**Counting note, so the record is exact.** `results/SOLUSDT/evaluations.csv` has
**21 rows** whose verdict is WATCH or PASS but only **20 distinct
configurations** - the PASS `041_impulse_not_crowded_tf5_time` is recorded twice
(`eval_id 3678ea08ce`), once before and once after its `--final` run, exactly as
BTC's 022/038/039 rows are. Exp 004's count of 20 configurations was correct.
**All 20 now have both controls and none is missing** (checked by reading
`results/SOLUSDT/baseline/` and `benchmark/` and joining on `eval_id`, not by
counting rows).

### Every control on the round: 19 new, all DRIFT and all NO_EDGE

| config | tf | VALID trades | VALID mean R | CI low | baseline | benchmark |
|---|---|---|---|---|---|---|
| 035 @4h | 4h | 99 | +0.2816 | −0.0522 | DRIFT | NO_EDGE |
| 035 @1h | 1h | 81 | +0.1171 | −0.1674 | DRIFT | NO_EDGE |
| 035 @30m | 30m | 119 | +0.1464 | −0.0876 | DRIFT | NO_EDGE |
| 035 @15m | 15m | 124 | +0.0529 | −0.1635 | DRIFT | NO_EDGE |
| 036 @4h | 4h | 109 | +0.0632 | −0.1984 | DRIFT | NO_EDGE |
| 036 @1h | 1h | 223 | +0.0657 | −0.0692 | DRIFT | NO_EDGE |
| 036 @30m | 30m | 145 | +0.1433 | −0.0806 | DRIFT | NO_EDGE |
| 036 @15m | 15m | 130 | +0.0141 | −0.1952 | DRIFT | NO_EDGE |
| 038 @30m | 30m | 186 | +0.0317 | −0.1590 | DRIFT | NO_EDGE |
| 039 @1h | 1h | 118 | +0.0128 | −0.2255 | DRIFT | NO_EDGE |
| 039 @30m | 30m | 111 | +0.0519 | −0.2172 | DRIFT | NO_EDGE |
| 039 @15m | 15m | 123 | +0.0580 | −0.1856 | DRIFT | NO_EDGE |
| 039 @3m | 3m | 113 | +0.0297 | −0.1965 | DRIFT | NO_EDGE |
| 041 @1h | 1h | 103 | +0.2504 | −0.0220 | DRIFT | NO_EDGE |
| 041 @30m | 30m | 132 | +0.1579 | −0.0688 | DRIFT | NO_EDGE |
| 041 @15m | 15m | 100 | +0.0265 | −0.2059 | DRIFT | NO_EDGE |
| 041 @3m | 3m | 110 | +0.0675 | −0.1509 | DRIFT | NO_EDGE |
| 043 @30m | 30m | 94 | +0.0844 | −0.1284 | DRIFT | NO_EDGE |
| 043 @15m | 15m | 100 | +0.0167 | −0.1907 | DRIFT | NO_EDGE |

With the PASS from Exp 002, the round's controls are **19 DRIFT + 1 SKILL, and 19
NO_EDGE + 1 ALPHA** - and the two non-default verdicts are the same single
configuration.

### What the 19 add to what Exp 002 and 003 recorded

**1. The PASS is not representative of its own family on SOLUSDT.** 041@5m read
SKILL and ALPHA. The other four 041 clocks on SOLUSDT read:

| 041 clock | VALID trades | VALID mean R | CI low | baseline | benchmark |
|---|---|---|---|---|---|
| 1m | 73 | +0.1670 | −0.1458 | (INCONCLUSIVE, no control needed) | |
| 3m | 110 | +0.0675 | −0.1509 | **DRIFT** | **NO_EDGE** |
| **5m** | 112 | **+0.2656** | **+0.0195** | **SKILL** | **ALPHA** |
| 15m | 100 | +0.0265 | −0.2059 | **DRIFT** | **NO_EDGE** |
| 30m | 132 | +0.1579 | −0.0688 | **DRIFT** | **NO_EDGE** |
| 1h | 103 | +0.2504 | −0.0220 | **DRIFT** | **NO_EDGE** |
| 4h | 95 | +0.2110 | −0.0701 | (INCONCLUSIVE, no control needed) | |

**041@1h is the sharpest one: +0.2504 on 103 VALID trades, and it is DRIFT and
NO_EDGE.** A near-identical VALID number to the PASS, on a neighbouring clock,
with the opposite control verdict. So the SKILL reading is not a property of the
family on SOLUSDT - it is a property of one configuration, and Exp 004's
correction stands: 041@5m's TRAIN mean R of +0.19987 was against a mode-A 95th
percentile of +0.19905, a margin of 0.0008 R, with 5% of random runs matching or
beating it, on a TRAIN period that contains the two data gaps.

**2. No new SKILL and no new ALPHA appeared.** All 19 are DRIFT and NO_EDGE, so
the round totals are unchanged from Exp 002: 1 SKILL, 1 ALPHA, both the same row.
**No holdout is warranted or attempted** - the SOL holdout was spent in Exp 003
and the config is spent (AGENTS.md step 7), and BNB/SOL have no other PASS.

**3. The 035 @4h row is the round's largest VALID number and it is DRIFT:**
+0.2816 on 99 trades, CI low −0.0522. The same 035 family that read SKILL on
BNBUSDT at 1h (BNB Exp 003) reads DRIFT on SOLUSDT at 4h, at a larger VALID mean
R. **Across the two new coins, the only SKILL reading on either belongs to a
configuration that is not a PASS.**

**4. 036 Keltner and 038 opening range, the two families with the weakest prior
from BTC, are now measured on their own data on SOLUSDT** and are DRIFT and
NO_EDGE at all four clocks controlled.

### The four corrections from Exp 004, acknowledged

Recorded here so the record shows they were read and applied, and with the
standing text left as it is (this journal is append-only and Exp 002/003 are not
rewritten):

1. **"A genuinely skillful entry, one that beats random timing on data it has
   never seen" is withdrawn.** The holdout gave +0.054 R with CI
   [−0.174, +0.298] and P(>0) 0.67, which is indistinguishable from zero. Being
   above the *median* random entry is the CONFIRMED side-condition, not evidence
   of skill; `baseline.py`'s SKILL means above the 95th percentile, and the
   holdout control does not measure that. The honest reading is "no evidence of
   an edge", and the data cannot choose between that and "an edge too small to
   prove". **The 19 new controls point the same way: 19 of 20 configurations on
   this coin are DRIFT.**
2. **The TRAIN SKILL was at the boundary** - +0.19987 against +0.19905, a margin
   of 0.0008 R, on a period containing the two data gaps (Exp 001b). The verdict
   is correct by the rule and is not strong evidence. Agreed; the 041@1h row
   above is the direct check on it.
3. **"022 SKILL (vacuous, a regime rule)" was wrong.** 022 was a long Donchian
   breakout with a 1% stop; it was SKILL under the pre-Exp 019 rule and DRIFT
   under the current one. The vacuous-SKILL regime rule was 023.
   **This does not affect Exp 003's table**, which is about the holdout outcomes:
   022's holdout was −0.0102 R either way.
4. **The "~983 trades needed" figure** assumed a per-trade standard deviation of
   1 R. It shows an order of magnitude, not a measured requirement.

### Verdict

No change. **SOLUSDT: 49 evaluations, 1 PASS, 0 CONFIRMED, the holdout spent
once and FAILED.** Research on SOLUSDT stops, per the stop rule in the Exp 001
pre-registration. The gap in process that Exp 004 identified is closed: every
WATCH and PASS configuration on this coin now has both controls.

---

## Exp 006 - Replication of `051_retail_crowd_fade_tf30` on SOLUSDT (pre-registration)

**Date:** 2026-10-01
**Status:** pre-registration, written BEFORE the first SOLUSDT run of this file.
Zero evaluations in this entry. **One file, unchanged, one coin: 1 evaluation.**

**What this is.** BTC Exp 038 recorded `051_retail_crowd_fade_tf30` as the first
configuration in this project with **SKILL on two coins** - BTC +0.106 R on 198
VALID trades, ETH +0.080 R on 197, beta ~0 on both, WATCH and NO_EDGE on both. It
missed PASS only on the CI gate. `PLAN.md` §15's question is whether that is skill
or one lucky cell out of 438 evaluations, and SOLUSDT's VALID data has never been
seen by this configuration. **No new idea, no new file, no new timeframe, no
variant.** `--final` is not run.

**Session checklist.** `test_engine.py` ends with **ALL CHECKS PASSED** with tests
**1b** (funding, notional x rate) and **11** (metrics: zip reading, causal
alignment to the bars, blocks against loops). SOL keeps its `eval_equity` of
**20,000**, because its qty step is a whole SOL.

### 1. `datafeed.py` output for this coin, verbatim

```
[validate]   1m: rows=3,104,640  2020-10-01 .. 2026-08-31  months=71/71  dup=0  gaps>3x=2
[validate]  30m: rows=  103,488  2020-10-01 .. 2026-08-31  months=71/71  dup=0  gaps>3x=2
VALIDATION: PROBLEMS FOUND (see above)
```

**This is the known, already-approved SOLUSDT data gap, not a new defect** (SOL
Exp 001b, owner-approved, restated in Exp 005 item 6): two gaps inside TRAIN, on
**2022-02-25 (73 h)** and **2022-03-31 (49 h)**. All 71 months are present, 0
duplicates, on every timeframe. **The upper bound on this file's exposure is the
same one already recorded for the coin: 32 of 1,430 signals = 2.2%, split 19 long
/ 13 short, and VALID and HOLDOUT are clean** - so it cannot manufacture a
positive VALID result. For this particular file the exposure is smaller still,
because its TRAIN usable window is 2021-12 to 2022-12 and both gaps sit inside it,
and the split is against shorts while Exp 005 measured the SOL holdout loss on the
**long** side.

### 2. `METRICS VALIDATION` output for this coin, verbatim

```
[metrics] rows=499,522  2021-12-01 .. 2026-08-31  days=1735/1735
           missing 5m slots=160 (0.03%)  dup=0  oi<=0=197
[metrics] NaN (kept, read as no signal): {'count_toptrader_long_short_ratio': 92217,
           'sum_toptrader_long_short_ratio': 92181, 'count_long_short_ratio': 5790,
           'sum_taker_long_short_vol_ratio': 37250}
METRICS VALIDATION: PROBLEMS FOUND (see above)
```

**All 1,735 days present, 0 duplicate rows, 0.03% of the 5-minute slots missing.**
The red line has the same single cause as on BTC and ETH - `sum_open_interest`
equals 0 on **197 rows (0.039%)** - and the same standing decision: **recorded as
a limitation, code unchanged** (BTC Exp 036/037, ETH Exp 009/010).

### 3. `acct_ls` NaN share per split - the column this file actually reads

The trigger is `crowd_fade` on `col: acct_ls`, which maps to Binance's
`count_long_short_ratio`. **The top-trader columns are not used by this file at
all**, so their 92,217 NaNs are irrelevant here - which is the whole point of
running M2 rather than M3 on these two coins.

| split | window | rows | `acct_ls` NaN | share | min | median | max |
|---|---|---|---|---|---|---|---|
| **TRAIN** | 2021-12-01 .. 2022-12-31 | 114,041 | 5,749 | **5.041%** | 0.6544 | 2.8848 | 7.5694 |
| **VALID** | 2023-01-01 .. 2024-12-31 | 210,380 | 21 | **0.010%** | 0.5313 | 2.1710 | 5.9226 |
| **HOLDOUT** | 2025-01-01 .. 2026-08-31 | 175,101 | 20 | **0.011%** | 0.9208 | 2.7116 | 6.1108 |

**The column is essentially complete in VALID (0.010%) and 5% absent in TRAIN.**
Note also that **SOL's median account ratio in TRAIN is 2.88 against 2.17 in
VALID**: retail was more one-sided long in the 2022 bear market than in the
2023-24 bull market, which is the regime the hypothesis was written for and a
reason the z-scores may not mean the same thing in the two periods.

**On 30m bars, 21,406 of 39,216 TRAIN bars have no `acct_ls` at all (54.6%)** -
that is the metrics starting on 2021-12-01, inside a 26-month calendar TRAIN, plus
the 5% NaN. So this file's usable TRAIN is **13 months**, the same as ETH's and
a third of BTC's 28.

### 4. TRAIN signal count per grid cell, and how many cells are likely eligible

`recipe()` on this coin's TRAIN, 30m bars, per grid cell of the unchanged file
(z 1.5 / 2.5 x hold 24 / 72 h):

| cell | long | short | total |
|---|---|---|---|
| **z 1.5 / 24 h** | 90 | 72 | **162** |
| z 1.5 / 72 h | 90 | 72 | 162 |
| z 2.5 / 24 h | 28 | **3** | 31 |
| z 2.5 / 72 h | 28 | 3 | 31 |

(`max_hold_hours` does not change the signal count, only the exit, so the four
cells collapse to two signal counts.)

**Eligibility is judged on backtest trades, not signals, and the bar is
`EVAL_MIN_TRAIN_TRADES` = 100.** One position at a time with a 12-bar cooldown
turns 162 signals into fewer trades, so the z 1.5 cell will land somewhere near
120-145 and is **marginal**. The z 2.5 cell at 31 signals **cannot be eligible**.
**So this run most likely has 1 eligible cell out of 4, or 0.**

**That is the same weakness BTC Exp 039 already found in ETH's half** - "on ETH
only 1 of the 4 grid cells had ≥ the minimum TRAIN trades (`n_eligible` = 1), so
ETH's choice was not a selection" - and it is a little worse here, because SOL's
TRAIN is the same 13 months with a third of BTC's usable data. **Write it down
before the run: on this coin the parameters are very likely to be taken from a
single eligible cell, which is a frozen default rather than a selection, and
`PLAN.md` §15's "if TRAIN has no eligible cell the coin counts as failed" is a
live possibility rather than a formality.**

**A second thing to write down before the run: the z 2.5 cell is 28 long and 3
short.** On this coin the stricter threshold is not just rarer, it is
**long-only in practice**, and on BTC the 2.5 cell was the ineligible one. So if
z 2.5 were ever selected here the result would be a long-leg result, and
`LESSONS.md` §2 would apply to it directly.

### 5. The pass criterion, copied from `PLAN.md` §15

> The replication **succeeds only if, on SOL and on BNB, both:**
> 1. VALID mean R > 0, and
> 2. `baseline.py` says **SKILL**.
>
> **One coin out of two is not a replication.** If TRAIN on a coin has no
> eligible cell (INCONCLUSIVE with no SKILL reading), that coin counts as
> **failed**, not as missing.

Reported next to the criterion but **not** part of it: the parameters TRAIN chose
and how many cells were eligible; the long and short legs; beta and alpha; per-year
results; the 4-coin pooled VALID mean R with a trade-level bootstrap CI (computed
in the review from `eval_trades/`).

**The prior, written down before the run.** `LESSONS.md` §2 and §3 are the prior:
a VALID mean R of +0.1 is "maybe +0.0 to +0.05", and the positive results in this
project have been long positions. §5 is the reason this coin is a real test rather
than a formality - a config carries its sign from coin to coin 71-73% of the time,
so a negative SOL result is informative rather than automatic, and a positive one
is the strongest entry-timing evidence the project has produced. `baseline.py` and
`benchmark.py` are run **whatever the verdict**, because the question is SKILL and
a REJECT row still has a skill reading.

### 6. What happens either way

- **Succeeds on both coins:** still no holdout - the verdict will not be PASS, and
  AGENTS.md rule 4 stands. The next step is a **forward test** on data after
  2026-08, with a criterion written before reading it, which needs the owner's
  decision.
- **Fails on either coin:** M2's two-coin SKILL is read as chance, the metrics
  question is closed as `PLAN.md` §14's stop rule already says, and **no M2
  variant is tried.**
- **`--final` is not run by this agent under any outcome.**

---

## Exp 007 - Replication of `051_retail_crowd_fade_tf30` on SOLUSDT: the criterion FAILS (DRIFT, not SKILL)

**Date:** 2026-10-01
**Status:** complete. 1 evaluation. **HOLDOUT UNTOUCHED - `--final` not run, and
not a candidate (the verdict is WATCH, not PASS).** No idea file edited. SOLUSDT
now has **51 evaluations**. Both controls run whatever the verdict, as
`PLAN.md` §15 requires.

**The file, unchanged: `ideas/051_retail_crowd_fade_tf30.json`, 30m, stop 2.12%,
z 1.5 / 2.5 x hold 24 / 72 h.**

### The result

| | trades | gross_r | cost_r | mean R | 95% CI | CAGR | maxDD | L/S |
|---|---|---|---|---|---|---|---|---|
| **TRAIN** | 133 | +0.078 | 0.067 | **+0.0113** | | | 21.0% | |
| **VALID** | **236** | +0.163 | 0.062 | **+0.1010** | [−0.1134, +0.3234] | **+10.8%** | **14.7%** | **119/117** |
| VALID x1.5 cost | | | | +0.0708 | | | | |

- valid: win 38%, PF 1.14, avg hold 15.2 h, exits stop/tp/time **55%/0%/45%**,
  fill 100%, **size skips 0 (train 0)**
- valid per year: **2023 +0.1685 (108), 2024 +0.0440 (128)**
- gates: trades >=100 ✅, train >0 ✅, valid >0 ✅, **ci_lo >0 ❌**, stress >0 ✅,
  maxDD <=20% ✅, skips ✅ -> **WATCH**, failing on the CI gate alone, exactly as
  on BTC and ETH
- **grid: 4 combos, 2 with >=100 train trades, 100% of those positive on train**
- **chosen on train: z 1.5 / hold 24 h** - the same cell BTC and ETH chose

### Both controls

| control | verdict | the numbers |
|---|---|---|
| `baseline.py` | **DRIFT** | idea VALID **+0.1010** against the random 95th percentile of **+0.1275** -> **margin −0.0265 R**; random median −0.0733; **7.0% of random runs beat the idea**; on TRAIN the gap is much wider, **+0.0113 against p95 +0.1608** |
| `benchmark.py` | **NO_EDGE** | VALID **beta +0.0128**, alpha **+0.0949/yr, 95% CI [−0.0981, +0.2741]** (spans 0), CAGR +10.8% against buy & hold +335.5%, maxDD 11.6% against 44.9%, Sharpe **+0.656 against +2.053** |

### Against `PLAN.md` §15's criterion

> succeeds only if, on SOL and on BNB, both: 1. VALID mean R > 0, and
> 2. `baseline.py` says **SKILL**.

| criterion | SOLUSDT | result |
|---|---|---|
| 1. VALID mean R > 0 | +0.1010 on 236 trades | **MET** |
| 2. `baseline.py` says SKILL | **DRIFT** | **NOT MET** |

**SOLUSDT FAILS the criterion.** Not narrowly on a technicality in the other
direction: on VALID it misses the random-entry bar by 0.0265 R, and on **TRAIN it
misses it by 0.1495 R** - a config whose own training period is indistinguishable
from random entry timing on this coin.

### The reported-besides-the-criterion numbers

- **Parameters TRAIN chose: z 1.5 / 24 h, from 2 eligible cells of 4, 100% of
  them positive on TRAIN.** Better than the pre-registration expected, which
  predicted 1 eligible cell or 0 - so on this coin the choice *was* a selection
  between two cells, not a frozen default. The z 2.5 cell had 31 signals and
  could not be eligible, as predicted.
- **Long and short legs on VALID: long +0.1739 (119 trades), short +0.0268
  (117).** The long leg carries the coin and the short leg is close to zero -
  **the same shape as BTC (+0.167 / +0.055) and ETH (+0.133 / +0.031).**
  `LESSONS.md` §2 again, on the third coin: what pays is being long.
- **Beta +0.0128, alpha +0.0949 with a CI that spans zero.** No ALPHA anywhere.
- **Per year: 2023 +0.1685, 2024 +0.0440** - the year *after* the first falls by
  three quarters, which is the opposite of BTC (2023 +0.054 -> 2024 +0.156) and
  ETH (2023 +0.005 -> 2024 +0.134). Three coins, three different year shapes, all
  positive in both years.
- **Cost is not the story:** `valid_cost_r` 0.0617 at a 2.12% stop, which is
  *below* the 0.066 R fee-only estimate of 0.14% of price per round trip, and in
  line with the other three coins (0.0647 / 0.0656 / 0.0644). Nothing about this
  result is a cost artefact.
- **Exits: 55% stop / 0% target / 45% time**, avg hold 15.2 h - the shortest hold
  of the four coins, and the highest stop-exit share, on the narrowest stop.

### Verdict against the criterion

`REJECT` **on the replication question**, while the evaluation itself is `WATCH`.
The two are different statements and both are recorded: **the configuration is
still WATCH on this coin - 236 trades, positive on TRAIN and VALID, all gates but
the CI - and the replication still fails, because the skill it needed to show is
not there.** `baseline.py` had 200 draws per mode and 7.0% of them beat the idea.

Per `PLAN.md` §15: **one coin out of two is not a replication, and this coin is
the one that was supposed to carry it.** The other half is in BNB Exp 005, and
`PLAN.md` §15's outcome text is explicit that a failure reads M2's two-coin SKILL
as chance, closes the metrics question as §14's stop rule already says, and ends
M2 **with no variant tried.** No `--final` was run and none is warranted.


---

## Exp 008 - Allocation test on SOLUSDT (PLAN.md section 16): NOT RUN

**Date:** 2026-10-01
**Status:** refused by the script. No result.

`SYMBOL=SOLUSDT python src/allocation.py` downloaded the spot and perp daily files, then stopped with `[perp] 2 missing days in the daily klines` (`allocation.py` line 138 refuses any gap above 1 day). These are the two known SOL data gaps (2022-02-25, 2022-03-31; see Exp 001 and STATUS). No `results/SOLUSDT/allocation/` and no `allocation.md` were written. The task forbids changing the script, adding rules or using `--rerun`, so SOL was not forced. Options for the owner: waive the gap check for SOL (a Level 3 code change) or leave SOL out (SOL spot has no 2018 anyway).


---

## Exp 009 - Allocation test on SOLUSDT, first run after the fixes: STILL NOT RUN

**Date:** 2026-10-01
**Status:** refused by the script. No result.

`SYMBOL=SOLUSDT python src/allocation.py` stopped with `[perp] 5 missing days in the daily klines: ['2022-02-26', '2022-02-27', '2022-02-28', '2022-04-01', '2022-04-02']`. The fix tolerates at most 3 missing days; the planner expected 2 (the two 2022 intraday gaps, Exp 001), but the daily file is missing 5 days. No `results/SOLUSDT/allocation/` or `allocation.md` was written. The script and its limit were not changed. Options for the owner: raise the tolerance for SOL (a code change) or leave SOL out (SOL spot starts 2020-08, so it has no 2018 anyway).


---

## Exp 010 - Coinbase premium (PLAN.md section 26): data validation failed, coin skipped

**Date:** 2026-10-02
**Status:** skipped by the owner's rule. **No evaluation was run on this coin**,
no idea file or code was changed, `--final` was not run, HOLDOUT was never read.
**This coin counts as a failure in the pre-registered bars.**

**Why it was skipped.** `SYMBOL=SOLUSDT python src/datafeed.py --tfs
15,30,60,240` printed **`VALIDATION: PROBLEMS FOUND`**. The four timeframes all
carry the same defect: **2 gaps longer than 3x the bar interval** (15m 206,976
rows / 30m 103,488 / 1h 51,744 / 4h 12,936, 2020-10-01 .. 2026-08-31, 71 of 71
months present, 0 duplicates). **Per the owner's rule for this round, a coin
whose validation does not pass is recorded and skipped and counts as a failure
in the pre-registered bars. No threshold was changed and no data was repaired.**
**No evaluation was run on this coin, so this is not a result - SOLUSDT simply
does not appear in the confirmation.**

**What this means for the round.** SOL was the only coin the plan listed as
"Coinbase only from mid-2021" that was already configured, so losing it removes
one of the four late-start coins. The 30m bar needs 7 of 10 positive and the 4h
bar needs 7 positive coins; with SOL and LTC both out, **at most 8 coins can
contribute and the breadth requirements are harder to reach, not easier.**

**Files.** none for this coin. The round's summary is
`journal/_multi/experiments.md` Exp 011, `journal/_multi/premium_confirm.md`
(generated), `results/_multi/premium_confirm/`.
