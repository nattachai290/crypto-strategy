# ETHUSDT research log

Append-only. Rules: `AGENTS.md`. Plan: `docs/research/PLAN.md` §11. The BTCUSDT
history (Exp 000–029, closed) is in `journal/BTCUSDT/`.

---

## Exp 000 — Setup

**Date:** 2026-09-29
**Status:** complete (no evaluation; holdout untouched)

After BTCUSDT closed (BTC Exp 029), the owner approved moving the research to
ETHUSDT.

- `src/config.py` `SYMBOL_SPECS["ETHUSDT"]` (Binance USDT-M ETHUSDT):
  - quantity step 0.001 ETH, minimum order notional 20 USDT;
  - data 2020-01..2026-08;
  - TRAIN 2020–2022, VALID 2023–2024, HOLDOUT 2025-01..2026-08, the same
    calendar split as BTC.
- The exchange-info endpoint could not be reached from the setup machine, so
  the step and notional are Binance's published values for ETHUSDT. They only
  affect sizing. At 1,000 USDT, 1% risk and a 6% stop, one trade is about
  170 USDT, far above both limits.
- `SYMBOL=ETHUSDT python src/datafeed.py`: **VALIDATION: OK**. All seven
  timeframes have 80/80 months, 0 duplicates and 0 gaps > 3 bars (1m: 3,506,400
  rows; 4h: 14,610). Funding: 7,305 rows, 2020-01..2026-08.
- **Round E1 signal counts, 4h, ETH TRAIN 2020–2022 only** (long/short, every
  trigger/filter grid value of each source file):

  | family | grid value → signals |
  |---|---|
  | 034 | n30 110/135 · n60 71/94 |
  | 035 | n30 161/99 · n60 120/64 |
  | 036 | n20 m2.0 120/82 · n50 m2.0 155/109 |
  | 038 | 339/310 |
  | 039 | n20 k1.2 111/138 · n20 k1.5 75/114 · n30 k1.2 89/106 · n30 k1.5 65/88 |
  | 041 | atr_k1.5 74–76/128 · atr_k2.0 59–63/101 |
  | 043 | q0.2 87/66 · q0.3 107/84 |

  Every value is at least 150, so nothing is dropped.
- **Disclosure: one smoke run.** To check the pipeline on ETH, the setup ran
  `039_breakout_flow_confirm.json` (4h) once into a scratch directory. It is
  **not recorded**: `results/ETHUSDT/` stays empty.
  - Result: TRAIN +0.263 (114 trades); VALID +0.102, CI [−0.099, +0.317],
    89 trades; size_skips 0 on both periods.
  - The plan was written **before** this run and was not changed after it.
  - Round E1 runs the same file for the record.
- `src/benchmark.py` now names the symbol's asset ("ETH", "BTC") in its
  report text instead of a fixed "BTC". The numbers were already per symbol.
- `test_engine.py`: ALL CHECKS PASSED.

Next: **Exp 001, Round E1 pre-registration** (`PLAN.md` §11).

---

## Exp 001 - Round E1 pre-registration: the seven cost-first families, re-measured on ETH

**Date:** 2026-09-29
**Status:** pre-registration, written BEFORE any ETH evaluation. Zero
evaluations in this entry. ETH project count on entry: **0**. ETH HOLDOUT sealed.

**The rule this round obeys (`PLAN.md` §11): the ideas are the existing idea
files, run unchanged** with `SYMBOL=ETHUSDT`. No idea file is edited and no new
one is written in this round. ETH gets its own `evaluations.csv`, its own
`eval_id` and its own version budget, so nothing about BTC's records moves.

### 1. Sizing: a real difference from BTC, and it is in our favour

1,000 USDT account, 1% risk = 10 USDT per trade. With a 0.001 ETH step a stop
of `s` sizes only while ETH < 10 / (0.001 x s):

| stop | sizes while ETH < | ETH holdout peak | headroom |
|---|---|---|---|
| 5% | 200,000 | 4,832 | **41x** |
| 6% | 166,667 | 4,832 | **34x** |
| 7% | 142,857 | 4,832 | **30x** |

BTC's holdout peak is 125,357, so BTC had **1x** headroom at a 6% stop and
Round 5 had to keep stops narrow to avoid `UNSIZABLE`. **ETH has 34x headroom:
no `UNSIZABLE` verdict is possible in this round, and stop width is not
constrained by sizing on ETH at all.** One confound BTC carried is simply gone.
The minimum notional is 20 USDT, which at ETH's all-time low is 0.2 ETH - small
enough that it never binds either.

### 2. The cost line: the plan's assumption is half right, and the half that is wrong is bigger

`PLAN.md` §11 says: *"ETH is more volatile than BTC. At the same hold, a bigger
gross move meets the same ~0.11% cost, so the cost line sits a little lower."*
Both halves of that sentence were measured on TRAIN 2020-2022 only, before
running anything, and **the two halves point in opposite directions.**

**The gross side - the plan is right, and the effect is bigger than "a little":**

| hold | median \|move\| BTC | ETH | ratio | mean BTC | ETH | p90 BTC | ETH |
|---|---|---|---|---|---|---|---|
| 48h | 2.632% | **3.645%** | 1.38x | 3.744% | 5.042% | 8.500% | 11.433% |
| 72h | 3.420% | **4.666%** | 1.37x | 4.682% | 6.359% | 10.748% | 14.133% |
| 96h | 4.014% | **5.524%** | 1.38x | 5.452% | 7.447% | 12.364% | 16.414% |
| 120h | 4.403% | **6.313%** | 1.43x | 6.117% | 8.391% | 13.921% | 18.274% |

ETH's 96h move is **38% bigger** than BTC's, consistently across the median, the
mean and the p90. So the denominator of the comparison really is lower on ETH.

**The cost side - the plan is wrong, because it forgot funding.** Cost is not
only the 0.14% taker round trip: a position open 96h crosses twelve funding
settlements, and the funding rate is per-coin:

| | TRAIN funding abs mean, per 8h | signed mean | p95 \|rate\| |
|---|---|---|---|
| BTCUSDT | 0.01886% | +0.01582% | 0.07704% |
| **ETHUSDT** | **0.02325%** | +0.02002% | **0.09420%** |

**ETH's funding is 1.23x BTC's, and it is on the wrong side of the comparison.**
`cost_r = (entry + hold_h/8 x funding) / stop`, at 6% and 96h:

| | taker 0.14% | post-only 0.09% |
|---|---|---|
| BTCUSDT | 0.0611 | 0.0527 |
| **ETHUSDT** | **0.0698** | **0.0615** |

**So on ETH the cost line is 17% *higher* than on BTC, not lower.** The net
effect of the two errors partly cancels: the ratio of a typical gross move to
the cost is 1.38 / 1.17 = **1.18x better on ETH**, but only because the gross
rose more, not because the cost fell. `PLAN.md` §11's sentence should be read
with that correction.

### 3. A correction to Round 5's own arithmetic, found while doing the above

Rounds 5 and 6 computed the expected cost with a **nominal 0.01% per 8h**
funding assumption. Measured on BTCUSDT TRAIN, the real absolute mean is
**0.01886% - 1.9x the assumption.** So a 96h / 6% post-only trade really cost
**0.0527 R, not the 0.0433 R** those pre-registrations claimed; Round 6's limit
of 0.05 R was breached by the very configurations it approved, and the 5%
stop / 120h cell was 0.0622 R rather than 0.0580 R.

**This changes no BTC verdict** - the engine has always charged the real funding,
and every `cost_r` in `evaluations.csv` is measured, not assumed. It changes
what the pre-registration arithmetic *said*. Recorded because Exp 025 corrected
three other things of this kind, and because a reader of the Exp 028 entry would
otherwise take 0.0433 R at face value. The cost-side lesson survives intact and
is if anything stronger: the line is ~0.06 R, not ~0.04 R.

### 4. What that predicts, written down before running

The honest prior for Round E1, and it is not a cheerful one:

1. **The same structure should score *lower* mean R on ETH than on BTC even if
   it captures the same fraction of the available move.** Cost at 96h/6% is
   0.0615 R on ETH against 0.0527 R on BTC, and the 6% stop is 6% of *ETH's* price
   where ETH moves 38% more - so the same R-multiple of a move is 38% more R but
   17% more cost. The sign of the difference is not obvious in advance, which is
   the point of running it.
2. **The two families that reached the BTC holdout (038 opening range, 039
   breakout + flow) are the two to watch**, and the plan already says a PASS on
   ETH that failed on BTC is one more reason for suspicion, not a reason to
   hurry.
3. **ETH's VALID is not independent of BTC's.** Daily correlation is ~0.8, so a
   family that scored well on BTC 2023-24 has no new evidence in ETH 2023-24;
   the ETH holdout is the only fresh data in this round.

### 5. Signal counts on ETH TRAIN only (the plan's step 1)

Counted with `recipe()` on ETH 4h bars, TRAIN 2020-01-01..2022-12-31 (6,576
bars), `direction: both`, each file exactly as written. **Every grid cell of
every family clears 150**, so no family is expected to be INCONCLUSIVE for want
of signals - a real difference from BTC, where Round 6 had to drop grid values.

| family | source cell | ETH long / short | total | every cell in the grid |
|---|---|---|---|---|
| 034 multi-day reversal | n30, 48h | 110 / 135 | 245 | 245, 245, 165, 165 |
| 035 multi-day momentum | n30, 72h | 161 / 99 | 260 | 260, 260, 184, 184 |
| 036 Keltner multi-day | n20 m2.0, 48h | 120 / 82 | 202 | 202, 202, 264, 264 |
| 038 opening range both sides | 5%, 48h | 339 / 310 | 649 | 649 x4 |
| 039 breakout + flow | n20 k1.2 | 111 / 138 | 249 | 249, 189, 195, 153 |
| 041 impulse, not crowded | atr_k1.5 th.0002 | 74 / 128 | 202 | 202, 204, 160, 164 |
| 043 squeeze break | q0.2, 48h | 107 / 84 | 191 | 153, 153, 191, 191 |

The thinnest cell is 039 at n30/k1.5 with 153 and 043 at q0.2 with 153 - both
above the floor, both still above it once the 48-120h hold has eaten most of the
window, so `INCONCLUSIVE` is still possible on VALID for the thinnest families.
Said in advance, per the plan, and **no file will be changed because of it**.

### 6. The run, and the judge

**49 evaluations** (7 families x 7 clocks, the 4h source and its six `_tfN_time`
variants, which already exist in `ideas/`), each with
`SYMBOL=ETHUSDT python src/evaluate.py ideas/<file>`. Then `baseline.py` and
`benchmark.py`, also on ETH, on every WATCH and PASS. The benchmark compares
with holding **ETH**, not BTC.

**Before any `--final`, the same three written checks as Round 6** - the seven
clocks and whether the PASS is the best of them, the per-year split, the
long/short counts - **plus the same config's BTC result.** 038 and 039 both
failed their BTC holdout, so an ETH PASS of either is a reason for more
suspicion, not less.

**Stop rule, agreed in advance:** if Round E1 ends with no holdout `CONFIRMED`
on ETH, ETH research stops too and the project's answer stands for both coins.

---

## Exp 002 - A defect in the engine's funding charge, found while reading the ETH cost line

**Date:** 2026-09-29
**Status:** finding recorded, **not fixed**. `src/backtest.py` is not mine to
change (AGENTS.md §5, Level 3: ask the owner first). No evaluation in this entry.
The ETH holdout is untouched.

### How it was found

Not by a test. Exp 001's step 3 asked for the expected `cost_r` per family on
ETH, computed from ETH's own funding rate, and the answer was **0.0615 R**. The
`cost_r` the engine actually produced was **0.0185 R**, a factor of 3.3 lower,
which cannot be explained by a hold that is on average shorter than the maximum.
So either the formula or the engine was wrong. Decomposing the trade file
settled which.

### The defect

`src/backtest.py:441`, inside the "manage open position" block:

```python
amt = pos_qty * sum(fr_l[fi:fe]) * sgn
cash -= amt
pos_funding -= amt
```

`pos_qty` is a quantity **in ETH**. `fr` is a funding rate, a fraction. Their
product is therefore an amount **in ETH**. It is then subtracted from `cash`,
which is the account equity **in USDT**. A perpetual's funding payment is
`notional x rate`, and notional is `qty x price`, so the charge is **short by
the mark price** - the units do not match.

Confirmed with a hand-computed test on real ETH 4h bars (a flat fortnight, fees
and slippage zeroed, one LONG held 328h across 40 known settlements at
+0.01000% each, so funding is the only cost in the trade):

| | USDT | note |
|---|---|---|
| the trade | 0.013223 ETH at 3,781.01 = **50.00 USDT** notional | 20% stop, so notional = 10 USDT risk / 20% |
| **engine books** | **-0.000064** | |
| `qty x rate` (what line 441 computes) | +0.000066 | matches the engine, sign aside |
| `qty x price x rate` (what funding is) | **+0.249** | |
| shortfall | **3,890x** | = the mark price |

The same test on BTCUSDT prices would show a shortfall of roughly 40,000x.

**The strongest evidence that this is an isolated slip and not a convention:
every other money line in the same function multiplies by the price, and only
this one does not.**

| line | code | has the price? |
|---|---|---|
| 304 | `fee = pos_qty * px_adj * fee_taker` | yes |
| 308 | `move = pos_qty * pos_side * (px_adj - pos_entry)` | yes |
| 317 | `slip_drag = pos_qty * slippage * (pos_entry + px_adj)` | yes |
| 319 | `cost_total = (pos_fees + fee) + slip_drag - pos_funding` | (sum of the above) |
| **441** | **`amt = pos_qty * sum(fr_l[fi:fe]) * sgn`** | **no** |

`cash` is `initial_equity` (line 273) and is in USDT throughout, so the funding
line is the single place where an ETH-denominated quantity is subtracted from a
USDT balance.

### How much it matters: much less than the arithmetic suggests

Recomputed for every published multi-day result from its own trade list - the
trade's quantity, entry price, hold and the real funding rates of the period,
with funding charged at `notional x rate`:

| | BTCUSDT | ETHUSDT |
|---|---|---|
| multi-day results examined (mean hold >= 48h) | 54 | 35 |
| the missing funding, average | **0.0067 R** | **0.0047 R** |
| the missing funding, median | **0.0037 R** | **0.0045 R** |
| the missing funding, worst | **0.0383 R** (027 multi-day pullback, 1h, 3% stop) | **0.0099 R** (035 momentum, 1h) |
| results positive as published and at or below zero once corrected | **0** | 2, both of them tiny positives (+0.0036 → -0.0039, +0.0084 → -0.0015) that were already REJECT/WATCH on other gates |

**So the defect is real and it changes no verdict on either coin.** The reason
the impact is small despite a 3,900x factor is that funding is close to zero in
expectation and its sign alternates: a long pays when the rate is positive and
receives when it is negative, and over a multi-day hold the two largely cancel.
The engine was charging ~1/3,900 of a number that is itself ~1/30 of the naive
`abs(rate) x settlements` estimate. Two errors nearly cancelling is not a
reason to leave the bug in place, but it is a reason not to re-open 210 BTC
evaluations or 49 ETH ones.

**And the direction of the error is the safe one:** understating a cost can only
make a result look better than it is. Every negative conclusion in this project
is therefore safe *a fortiori* - a correctly-charged funding would make the
WATCHes worse and would not make any REJECT into anything else. Nothing that
failed, failed because of this. In particular the two ETH near-misses are
untouched by the correction: 041@1m +0.2760 becomes +0.271 and 039@1m +0.2219
becomes +0.217, and both still fail the same gate they already failed.

### What this does to my own Exp 001, which I have to correct

Exp 001 measured two things correctly and then drew a wrong conclusion from
them:

- **Correct:** BTC's TRAIN funding abs mean is 0.01886% per 8h and ETH's is
  0.02325%, so ETH's funding is 1.23x BTC's. Those are measurements of the rate
  series and they stand.
- **Correct:** ETH's 96h move is 38% larger than BTC's. That stands.
- **Wrong, and now retracted:** "on ETH the cost line is 17% higher than on BTC"
  and "Rounds 5 and 6 computed the cost with a 1.9x-too-small funding
  assumption, so a 96h/6% trade really cost 0.0527 R not 0.0433 R". Both assume
  funding was being charged. **It was not being charged at all in any amount
  that matters**, so neither correction is a correction. The measured ETH
  `cost_r` is **0.0185 R median**, essentially identical to BTC's 0.0186 R, and
  the fee round trip (0.09% post-only entry + 0.05% taker exit over a 6% stop =
  0.0233 R, less at wider stops and for partial fills) accounts for essentially
  all of it.

The methodological conclusion of Rounds 5-6 survives and is in fact cleaner than
it looked: **cost really is ≈ 0.02 R for a multi-day trade, and it is fees
almost entirely, not funding.** The "multi-day holds leave room for an edge"
argument therefore rests on the fee structure and the stop width, which is a
weaker but still valid basis, and it no longer needs funding at all.

### Owner decision needed 🛑

1. **Fix it or leave it?** A one-line change (`qty * price * rate`, using the
   bar's mark, exactly as the fee and slippage lines already do) plus a
   hand-computed test in `test_engine.py` that fails before and passes after.
   Level 3, so I will not do it unasked, and I will not add a failing test
   either. My recommendation: **fix it**, because it is a real defect in a
   research tool whose entire value is that its costs are honest, and because a
   future agent will otherwise re-derive it from a `cost_r` that is 3.3x lower
   than the arithmetic says.
2. **If it is fixed, re-run anything?** **No, on the evidence above**: 0 BTC
   verdicts change, 0 ETH verdicts change, and the two ETH near-misses are moved
   by 0.005 R when they fail a gate by 0.0033 to 0.01. Re-running 259
   evaluations to move nothing is not worth it. I would fix the engine, leave the
   records, and note the defect against every multi-day result in the report.

---

## Exp 003 - Round E1 results: 0 PASS, 32 WATCH, and the same DRIFT+ALPHA state for a third time

**Date:** 2026-09-29
**Status:** complete. **49 evaluations: 0 PASS, 32 WATCH, 14 REJECT, 3
INCONCLUSIVE.** ETH project total **49**. ETH HOLDOUT untouched - nothing
qualified for it. `baseline.py` and `benchmark.py` ran on all 32 WATCHes.

### The controls were uniform, which is itself the result

| control | verdict |
|---|---|
| `baseline.py`, 32 of 32 | **DRIFT, every one** |
| `benchmark.py`, 32 of 32 | 31 NO_EDGE, **1 ALPHA** |

Exp 001 predicted this: *"R5.1's nine WATCHes were all DRIFT, so DRIFT is the
expected outcome and must be reported as such."* On BTC, every single
cost-first multi-day idea that reached a control was DRIFT, and on ETH not one
of 32 is anything else. **Thirty-two independent configurations across two
coins, and the entry beats random timing in none of them.**

### The binding gate is the same one on every near-miss

The top ten VALID results, and which gate each fails:

| config | trades | mean R | needed for n | CI low | stress | maxDD | failed |
|---|---|---|---|---|---|---|---|
| 041 @1m | 77 | +0.2760 | 0.1787 | **-0.0033** | +0.2681 | 7.3% | trades<100, **ci_lo** |
| 039 @1m | 103 | +0.2219 | 0.1545 | **-0.0095** | +0.2139 | 5.3% | **ci_lo** |
| 038 @1m | 63 | +0.2103 | 0.1975 | -0.0743 | +0.2010 | 4.7% | trades, ci_lo |
| 043 @5m | 54 | +0.2037 | 0.2134 | -0.1129 | +0.1959 | 5.8% | trades, ci_lo |
| 039 @5m | 95 | +0.1581 | 0.1609 | -0.0677 | +0.1504 | 5.9% | trades, ci_lo |

**Every one of them fails on `ci_lo` and nothing fails on drawdown or on the
x1.5 cost stress.** The effects are the right size - the mean R clears the
`1.568/sqrt(n)` bar comfortably in most rows - and the samples are 54 to 103
trades, which is simply not enough to put a bootstrap CI above zero. That is a
power problem, not a finding, and it is the honest description: the round
produced several effects that are too large to be nothing and too small to be
separated from noise at this sample size.

### The one ALPHA, and it is the third time this state has appeared

**041 `momentum` + `funding_not_crowded` + `volume_spike` at 1m: WATCH, DRIFT,
ALPHA.**

| split | trades | gross_r | cost_r | mean R | 95% CI | CAGR | maxDD |
|---|---|---|---|---|---|---|---|
| train 2020-2022 | 101 | | | +0.1951 | | +6.4% | 10.6% |
| valid 2023-2024 | 77 | +0.2954 | 0.0194 | +0.2760 | [-0.0033, +0.6057] | +10.8% | 6.9% |
| valid x1.5 cost | | | | +0.2681 | | | |

41 long / 36 short, **beta -0.004**, alpha **+10.8%/yr with CI [+0.004, +0.218]**
on VALID and +9.5%/yr CI [-0.001, +0.187] on TRAIN, Sharpe **1.37 against
buy & hold's 1.18**, maxDD **6.9% against 45.4%**.

**Two things about it are the healthiest in the project, and one is fatal.**

Healthy, and worth recording:
- **beta is -0.004.** It is not a disguised long. That was the test Round 5 set
  for itself and this passes it cleanly.
- **The per-year split is 2023 +0.2773 on 38 trades against 2024 +0.2749 on 39.**
  That is 50.5% / 49.5%. Every previous positive result in this project was
  lopsided: 022 was 2023 +0.3496 over 2024 +0.1355, 038 was +0.0916 over
  +0.2579, 039 was +0.3192 over +0.1358, and the Round 6/ETH near-misses all
  leaned on 2023. **A result that is identical in a bull year and a flat year
  is the only shape of evidence that is not a regime effect**, and this is the
  first one the project has produced.
- It is positive on **all seven clocks** (+0.017 to +0.276), and 039 is too
  (+0.026 to +0.222), so it is not a single-clock artefact.

Fatal: **`baseline.py` says DRIFT.** On TRAIN the idea sits below the 95th
percentile of random entries with the same stop, hold and filters. So the entry
has no measured timing skill, and the return comes from being in ETH both ways
rather than from when it entered.

**This is the third configuration in the project to land on DRIFT + ALPHA, and
the first two both failed their holdouts:**

| config | coin | verdict | baseline | benchmark | holdout |
|---|---|---|---|---|---|
| 038 opening range @4h | BTC | PASS | DRIFT | ALPHA | **FAILED** -0.1118 R |
| 039 breakout+flow @5m | BTC | PASS | DRIFT | ALPHA | **FAILED** +0.0129 R, beaten by a random entry |
| **041 impulse @1m** | **ETH** | **WATCH** | **DRIFT** | **ALPHA** | **not run - a WATCH cannot be** |

**`--final` is refused and I did not run it.** AGENTS.md rule 4 is absolute
("Never run `--final` on anything that is not `PASS`"), and 041@1m fails two
gates: 77 trades against a floor of 100, and a CI lower bound of -0.0033. It is
the closest the project has come since 038, and it is still a WATCH. Spending
the ETH holdout on it is the owner's decision (`PLAN.md` §5), and on the
evidence of the other two DRIFT+ALPHA results my recommendation is **not to** -
but it is the owner's call and I have left the holdout sealed.

### What ETH adds that BTC did not: a cross-coin answer

Every one of the 49 ETH rows was matched to its BTC twin (same idea file, same
frozen config, different coin) and compared as a pair.

| | |
|---|---|
| ETH higher on **17** of 49 configs, lower on **32** | |
| mean difference **-0.0179 R**, median -0.0317 R | 95% CI **[-0.0441, +0.0082]** |
| BTC's 2 PASSes on ETH | **both become WATCH** |
| BTC REJECT -> ETH WATCH | 14 |
| BTC WATCH -> ETH REJECT | 5 |

**My own first impression was wrong and the paired test corrected it.** Reading
only the top rows, ETH looked markedly better than BTC (041@4h +0.129 against
BTC's -0.024; 043@5m +0.204 against +0.084). Paired over all 49 configs there is
**no detectable difference, and if anything ETH is slightly worse.** ETH's 38%
larger moves buy nothing once the structure is the same.

**The correlation between the two coins' VALID results is only +0.52 Pearson /
+0.43 Spearman.** That is the most useful methodological fact this round
produced: a structure's result on one coin predicts its result on the other only
weakly, so the 210 BTC evaluations could not have been "reused" for ETH, and the
ETH results are substantially independent evidence rather than a rerun.

### Per family, on both coins, how many of the seven clocks are positive

| family | BTC | ETH | BTC median | ETH median | BTC best | ETH best |
|---|---|---|---|---|---|---|
| **039 breakout + flow** | **7/7** | **7/7** | +0.145 | +0.102 | +0.2223 (PASS) | +0.2219 |
| **041 impulse, not crowded** | 6/7 | **7/7** | +0.119 | +0.065 | +0.174 | +0.2760 |
| 043 squeeze break | 7/7 | 6/7 | +0.099 | +0.027 | +0.144 | +0.204 |
| 035 multi-day momentum | 7/7 | 4/7 | +0.123 | +0.008 | +0.165 | +0.133 |
| 038 opening range | 4/7 | 5/7 | +0.016 | +0.040 | +0.1753 (PASS) | +0.210 |
| 036 Keltner multi-day | 4/7 | 4/7 | +0.001 | +0.018 | +0.097 | +0.111 |
| 034 multi-day reversal | 0/7 | 3/7 | -0.098 | -0.064 | -0.068 | +0.058 |

**039 is positive on all fourteen clocks across both coins** - the most robust
positive result this project has produced - and its BTC version is the one that
PASSed, got ALPHA, and then failed the holdout because a random entry matched
it. Robustness across coins and across clocks is not what distinguishes an edge
from a period effect; only the holdout did that, twice.

**034 multi-day reversal is now dead on both coins** (BTC 0/7 positive, ETH
3/7, and the ETH positives are the smallest numbers in the round at +0.004 to
+0.058). This is the fourth coin-clock to close that family, after 016 at 15m
and 034's BTC rejection at all seven clocks.

### Verdict

`REJECT`, and the round is complete. **0 PASS, 0 CONFIRMED, the ETH holdout
untouched.** Nothing here is a strategy: 32 of 32 controls say DRIFT, and the one
ALPHA has no timing skill and two failed gates.

The stop rule agreed in the pre-registration is therefore live: **if Round E1
ends with no holdout CONFIRMED on ETH, ETH research stops too, and the project's
answer stands for both coins.** Round E1 has ended with no PASS, so no holdout
could be run, so it has ended with no CONFIRMED.

The project's answer, now on two coins and 259 evaluations:

> **At Binance USDT-M VIP0 costs, no entry this harness has been able to
> construct has an edge that survives a random-entry control.** Multi-day
> both-sided rules on a 6% stop do produce real positive gross moves that
> reproduce on unseen data in every year - and the entry is not what produces
> them. The value, if there is any, is in the cost structure, which is an
> execution and position-sizing decision rather than a trading technique, and
> this harness has no instrument for it.

---

## Exp 004 — The funding defect of Exp 002 is fixed (BTC Exp 030)

**Date:** 2026-09-29
**Status:** complete (no evaluation recorded; ETH holdout untouched)

The owner approved the fix. `backtest.py` now charges funding as notional ×
rate, and test 1b fails before the fix and passes after it. All 49 ETH
configs were re-run in scratch. VALID mean R changes by a median of
−0.0027 R (5th–95th percentile −0.0086 to +0.0061). Two verdicts change:
- 035@1h: WATCH → REJECT;
- 034@4h: REJECT → WATCH (+0.0115, CI far below 0).

041@1m, the closest config, goes from +0.2760 to +0.2714, and its CI low
goes from −0.0033 to −0.0075 (it stays a WATCH). No PASS. The Exp 003 stop rule stands: ETH research stops. Details
and the BTC side are in `journal/BTCUSDT/experiments.md` Exp 030.
