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
