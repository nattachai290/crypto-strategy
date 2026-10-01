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

---

## Exp 005 — ETH closed; research moves to SOLUSDT and BNBUSDT

**Date:** 2026-09-29
**Status:** complete (decision record; no evaluation)

Round E1's stop rule (Exp 001) fired, so ETH research stops. 041@1m stays a
WATCH and gets no holdout. The owner approved trying SOLUSDT and BNBUSDT with
the same seven families, run by the research agent (`PLAN.md` §12,
`journal/SOLUSDT/`, `journal/BNBUSDT/`).

---

## Exp 006 - TradingView ports T1-T6, pre-registration (ETHUSDT)

**Date:** 2026-09-30
**Status:** pre-registration, written BEFORE the first ETH port evaluation. Zero
evaluations in this entry.

**This is the ETH half of the round pre-registered on BTC as Exp 032.** The
ports are the same files, run unchanged with `SYMBOL=ETHUSDT`; ETH's records,
`eval_id`s and version budget are its own (PLAN §13 rule 3). The rule that the
ports were written from the owner's pasted Pine source and not from memory, the
deviation lists, the judgement and the stop rule are in BTC Exp 032 and are not
repeated here. What follows is what is **specific to ETH**.

**Session checklist passed first:** `test_engine.py` ends with **ALL CHECKS
PASSED** with test **1b** present; `datafeed.py` gives **VALIDATION: OK** on
ETHUSDT.

### 1. TRAIN signal counts on ETH, per port, per timeframe

`recipe()` on ETH TRAIN 2020-2022. **Bold = under the 150 floor** - run anyway,
do not change the file (PLAN §13).

| port | 15m | 30m | 1h | 4h (source) |
|---|---|---|---|---|
| T1 044 RSI+BB both sides | 714 | 342 | 178 | **44** |
| T2 045 LuxAlgo SMC | 391 | 194 | **103** | **17** |
| T3 046 MACD+SMA200 | 1,053 | 575 | 274 | **68** |
| T4 047 Super Scalper (src 15m) | **7,702** | 3,915 | 1,915 | 518 |
| T5 048 RSI+BB long only | 338 | **136** | **61** | **14** |
| T6 049 Liquidity Sweep (src 15m) | 460 | 271 | 152 | **15** |

**ETH's counts track BTC's closely**, within about 10% on every cell, so the
shortage of 4h signals is a property of the ports rather than of the coin. T5's
4h file has **14 signals in three years**; T2's has 17; T6's 4h has 15. Those
five files cannot reach 100 VALID trades and are expected to be INCONCLUSIVE for
want of trades. On the 15m chart the same ports produce 338 to 7,702.

### 2. Expected `cost_r` on ETH

Entry cost is the same 0.070% taker / 0.040% post-only of price. **ETH's TRAIN
funding is 0.02325% per 8h abs mean against BTC's 0.01886% - 1.23x - so every
ceiling below is about 23% higher than BTC's, and the fee-only floors are set by
the stop width instead.** ETH's ATR is wider, so the ATR-stop ports are
*cheaper* per R on ETH than on BTC at every timeframe:

| port | tf | stop | fee-only cost_r (ETH) | + full hold funding, ceiling (ETH) |
|---|---|---|---|---|
| T1 / T3 / T5 | 15m | 1.0-1.5% | **0.027-0.040** | 0.059-0.349 |
| T1 / T3 / T5 | 30m | 1.41-2.12% | **0.019-0.028** | 0.083-0.495 |
| T1 / T3 / T5 | 1h | 2.0-3.0% | **0.013-0.020** | 0.116-0.698 |
| T1 / T3 / T5 | 4h | 4.0-6.0% | **0.007-0.010** | 0.233-1.395 |
| T2 | 15m | 1.0-1.5% | **0.027-0.040** | 0.015-0.088 |
| T2 | 30m | 1.41-2.12% | **0.019-0.028** | 0.021-0.124 |
| T2 | 1h | 2.0-3.0% | **0.013-0.020** | 0.029-0.175 |
| T2 | 4h | 4.0-6.0% | **0.007-0.010** | 0.058-0.349 |
| T4 (ATR 2x swing) | 15m | median 2.18% of price | **0.018** | |
| T4 | 30m | 3.22% | **0.012** | |
| T4 | 1h | 4.61% | **0.009** | |
| T4 | 4h | 9.21% | **0.004** | |
| T6 (swing + 1.2 ATR) | 15m | median 1.49% of price | **0.027** | |
| T6 | 30m | 2.06% | **0.019** | |
| T6 | 1h | 2.86% | **0.014** | |
| T6 | 4h | 6.93% | **0.006** | |

**The fee-only cost is 0.004-0.040 R on every ETH cell**, inside `LESSONS.md` §1's
0.1 R rule, so the round's prior is not a cost death. It is `LESSONS.md` §2 -
these will be long positions in a bull market - and §3, a VALID mean R of +0.2
meaning "maybe +0.0 to +0.05".

### 3. What is different about running these on ETH

- **`LESSONS.md` §5: never carry a config to another coin without re-running it.
  The same idea file has the same VALID sign on BTC/ETH 71-73% of the time,
  Spearman +0.30 to +0.43.** So ETH is neither a free confirmation nor a wasted
  duplicate; it is a 70%-correlated second look, and a disagreement is
  informative rather than redundant.
- **ETH's VALID 2023-24 is a bull year like BTC's but a different one**, and per
  `LESSONS.md` §2 the ETH long side was positive in 78% of its evaluations
  against BTC's 56% - so **T5, which is long-only by construction, has a better
  prior on ETH than on BTC.** That is a drift prior, not an edge prior, and it is
  exactly what `baseline.py` is there to separate.
- **Sizing is a non-issue on ETH** (Exp 003: a 6% stop sizes while ETH < 166,667
  against a holdout peak of 4,832, 34x headroom), so T4's and T6's wide ATR
  stops at 1h and 4h - which `PLAN.md` §13 flags as possibly `UNSIZABLE` on BTC -
  are comfortably sizable here. **That difference is recorded in advance**: a
  `UNSIZABLE` on BTC and a clean REJECT on ETH for the same file would be a
  sizing artefact on one side only.
- **T2's licence (CC BY-NC-SA 4.0, LuxAlgo) travels with the port**, on either
  coin: non-commercial use only.

### 4. Judgement and stop rule

Unchanged from BTC Exp 032: both controls on every WATCH and PASS; **`--final`
is not run by this agent** - a qualifying config stops the round and goes to the
owner, because a holdout is one-shot per config; report each port's TradingView
claim next to what is left after costs and controls; **a round with no holdout
CONFIRMED ends the TradingView question unless the owner brings new scripts.**

---

## Exp 007 - TradingView ports T1-T6 on ETHUSDT: 0 PASS, 3 WATCH, all DRIFT and all NO_EDGE

**Date:** 2026-09-30
**Status:** complete. 24 evaluations. ETH HOLDOUT UNTOUCHED - no PASS, so
`--final` was not a candidate and was not run. No idea file edited.

**24 evaluations: 0 PASS, 3 WATCH, 16 REJECT, 5 INCONCLUSIVE.** Both controls on
all 3 WATCH rows. ETH now has 73 evaluations.

### Per port, VALID mean R by clock

| port | 15m | 30m | 1h | 4h | verdicts |
|---|---|---|---|---|---|
| **T1** 044 ChartArt RSI+BB v1.1 | −0.202 | −0.038 | −0.337 | −0.448 | 3 REJ, 1 INC |
| **T2** 045 LuxAlgo SMC | −0.199 | **+0.250** | −0.136 | **+0.200** | 2 WATCH, 2 REJ |
| **T3** 046 ChartArt MACD+SMA200 | +0.013 | −0.162 | −0.065 | −0.050 | 3 REJ, 1 INC |
| **T4** 047 Super Scalper | −0.142 | −0.094 | −0.035 | **+0.270** | 3 REJ, 1 WATCH |
| **T5** 048 ChartArt RSI+BB long-only | −0.062 | −0.064 | −0.422 | −0.658 | 2 REJ, 2 INC |
| **T6** 049 Liquidity Sweep | −0.251 | −0.126 | −0.099 | **+0.403** | 3 REJ, 1 INC |

**ETH is markedly harsher than BTC for these ports: 16 REJECT against 13, and
three of the six ports are negative at every clock (T1, T5) or nearly so (T3).**
`LESSONS.md` §5 predicted a same-idea-file result keeps its sign on BTC/ETH
71-73% of the time, Spearman +0.30 to +0.43, so this is agreement with the
project's own measurement, not a surprise - but the direction is worth stating:
**of the 24 ports x clock cells, the two coins disagree in sign on 9 of the 18
BTC-positive-or-negative cells that have a counterpart here.**

### The three WATCH rows, with controls

| config | v trades | gross_r | cost_r | mean R | 95% CI | CAGR | maxDD | L/S | baseline | benchmark |
|---|---|---|---|---|---|---|---|---|---|---|
| **047 T4 @4h** | 114 | +0.3073 | 0.0369 | **+0.2704** | [−0.0224, +0.6171] | +15.6% | 6.9% | **57/57** | DRIFT | NO_EDGE |
| 045 T2 @4h | 87 | +0.2393 | 0.0388 | +0.2004 | [−0.0934, +0.5155] | +8.6% | 6.8% | 43/44 | DRIFT | NO_EDGE |
| 045 T2 @30m | 92 | +0.3654 | 0.1154 | +0.2500 | [−0.2425, +0.8142] | +10.5% | 13.6% | 53/39 | DRIFT | NO_EDGE |

**All three are DRIFT and all three are NO_EDGE - the same verdict pair as the
project's 102 of 108.** No SKILL reading anywhere on ETH, against two on BTC.

### What is different about ETH, and it is the reverse of the BTC long prior

- **T1 and T5 are negative at all four clocks on ETH, and both were positive at
  4h on BTC.** T5 is the long-only script, and `LESSONS.md` §2 had given it a
  *better* drift prior on ETH than on BTC (78% of ETH evaluations had a positive
  long leg against BTC's 56%). **That prior was wrong in the only direction that
  could have flattered it**: T5's 4h row is −0.658 on ETH against +1.616 on BTC.
  The lesson generalises - a drift prior computed from a coin's aggregate
  statistics is not a prior about a specific rule.
- **T4 is the port that agrees across coins.** BTC 4h +0.1001 on 141 trades,
  70 long / 71 short; ETH 4h +0.2704 on 114 trades, **57 / 57**. Both DRIFT and
  both NO_EDGE. **The only port that is positive on the same clock on both coins
  with balanced sides on both, and it is still not an edge** - which is the same
  lesson as 039's 21-of-21 clocks on three coins and then 2-of-7 on BNB.
- **T4's cost_r is 0.0369 at 4h on ETH against 0.0324 on BTC**, both far inside
  `LESSONS.md` §1's 0.1 R band, because the ATR stop is 9.21% of ETH's price at
  4h against 7.11% of BTC's. **T3 is the expensive one on both coins** (0.115 to
  0.151 R on BTC, 0.116-0.176 R here) because of the invented time cap, and on
  ETH it is negative anyway.
- **T6's 4h row is +0.403 on 7 trades** (3 long, 4 short) and INCONCLUSIVE. The
  pre-registration measured 15 ETH signals for that cell and predicted INCONCLUSIVE
  from the session geometry - only the 12:00 bar is inside UTC 12-15 on a 4h
  chart. It is negative at 15m, 30m and 1h, which is where the script was designed
  to run.

### Verdict

`REJECT`, and the round's stop rule: **no PASS on ETH, so no holdout was used.**
24 evaluations, 0 PASS, 3 WATCH (all DRIFT, all NO_EDGE), 16 REJECT, 5
INCONCLUSIVE.

Across both coins the round is **48 evaluations, 0 PASS, 8 WATCH (2 SKILL), 29
REJECT, 11 INCONCLUSIVE**, and **not one published strategy cleared the gates on
the timeframe its author published it for.**

---

## Exp 008 - Review of ETH Exp 006/007

**Date:** 2026-09-30
**Status:** complete. A review, no evaluations.

The review of both coins is BTC journal **Exp 034**. Parts that apply here:
- Records are intact: 49 → 73 rows, every old row unchanged. The ETH holdout
  is still untouched.
- Exp 006's cost floor was wrong by about 3.5×. A round trip is ≈ 0.14% of
  price, i.e. ≈ 0.14 R at a 1% stop.
- T3's cost is fees and slippage, not the time cap. Funding was a net credit.
- The claim that T5 disproved the `LESSONS.md` §2 prior rests on 7 trades at
  4h and cannot show that. T5 is negative at every clock, and that is the
  evidence.

The verdict stands: 0 PASS, 3 WATCH (all DRIFT, all NO_EDGE). The TradingView
question is closed on ETH.

---

## Exp 009 - New data: open interest and long/short ratios M1-M4, pre-registration (ETHUSDT)

**Date:** 2026-10-01
**Status:** pre-registration, written BEFORE the first ETH M1-M4 evaluation.
Zero evaluations in this entry.

**This is the ETH half of the round pre-registered on BTC as Exp 036.** The
files are the same, run unchanged with `SYMBOL=ETHUSDT`; ETH's records, `eval_id`s
and version budget are its own. The checklist, the judgement, the stop rule and
the bear-market predictions are in BTC Exp 036 and are not repeated. What follows
is what is **specific to ETH**, and it is worse than BTC's on the data side.

**Checklist:** `test_engine.py` ends with **ALL CHECKS PASSED** (tests 1b and 11
present); `datafeed.py` gives **VALIDATION: OK** on ETHUSDT.

### 1. The metrics data check

```
[metrics] rows=499,540  2021-12-01 .. 2026-08-31  days=1735/1735
           missing 5m slots=140 (0.03%)  dup=0  oi<=0=208
METRICS VALIDATION: PROBLEMS FOUND (see above)
```

No missing days and no duplicate rows on this coin - the 0.03% of missing
5-minute slots is well inside the 1% tolerance. **The only cause of the red
line is the same one as on BTC: `sum_open_interest` equals 0 on 208 of 499,540
rows (0.042%)**, on 21 dates. **Owner decision 2026-10-01: recorded as a
limitation, code unchanged** (BTC Exp 036 §1 has the full list and the measured
impact: **zero spurious signals** on BTC at both grid values, because the 720-bar
z-score is unmoved by 11 zeros in 26,304 bars; ETH's 208 rows are the same
magnitude, and ETH's usable TRAIN is a quarter the size, so the same null result
is expected here - and is not assumed, it will be visible in the trade counts).

**Column coverage, and this is the serious limitation of the ETH half:**

| split | window | rows | top-trader ratios NaN | all-account L/S NaN | taker ratio NaN | open interest NaN |
|---|---|---|---|---|---|---|
| TRAIN | 2021-12-01 .. 2022-12-31 | 114,041 | **80.79%** | 5.04% | 32.66% | 0% |
| VALID | 2023-01-01 .. 2024-12-31 | 210,398 | **0.014%** | 0.009% | 0.000% | 0% |
| HOLDOUT | 2025-01-01 .. 2026-08-31 | 175,101 | **0.032%** | 0.012% | 0.000% | 0% |

**Counted in 5-minute rows, only 21,908 of ETH's 114,041 TRAIN rows (19.2%)
carry a valid top-trader ratio, against 210,368 of 210,398 in VALID.** The
metrics themselves start 2021-12-01, so the top-trader column is effectively
usable for roughly the last three months of TRAIN and for all of VALID.

**Consequences, stated before any run:**

- **M3 `052_smart_money_divergence` is not testable on ETH at 1h or 4h.** A
  720-bar z-score over a column that is missing 81% of the time cannot warm up.
  The measured TRAIN counts below are **2-3 signals at 1h and 0 at 4h**. Those
  files will be INCONCLUSIVE for want of trades, and the honest reading is that
  **ETH says nothing at all about M3.** A negative ETH row for M3 is a data
  limitation, not evidence against top-trader divergence.
- **The whole ETH TRAIN is 13 months and is almost entirely the 2022 bear
  market** (`PLAN.md` §14's own table). `LESSONS.md` §5 is the reason this half
  is replication and not a finding: a config carries its sign from BTC to ETH
  71-73% of the time, Spearman +0.30 to +0.43, so ETH is a 70%-correlated second
  look - useful when it disagrees, not an independent confirmation.

### 2. TRAIN signal counts on ETH

**Bold = under the 150 floor.**

| idea | 15m (stop 1.5%) | 30m (2.12%) | 1h (3%) | 4h (6%) |
|---|---|---|---|---|
| **M1** 050 `oi_flush_reversal` | 118-231 | **52-99** | **24-55** | **2-12** |
| **M2** 051 `retail_crowd_fade` | **72-300** | **31-167** | **12-91** | **6-35** |
| **M3** 052 `smart_money_divergence` | **50-54** | **15-26** | **2-3** | **0** |
| **M4** 053 `oi_confirmed_breakout` | 42-454 | **49-250** | **46-151** | **26-40** |

**ETH is thinner than BTC on every cell of every idea**, for the one reason
stated above: 13 months of TRAIN against 28, and 63.9% of ETH's 1h TRAIN bars
with no open interest at all (16,800 of 26,304). **Nine of the sixteen ETH cells
are under 50 TRAIN signals.** M3 at 4h has **zero**. The prior written down
before the run is therefore that **most ETH rows will be INCONCLUSIVE**, and that
a REJECT on ETH is much more likely to be about the data than about the idea.

**Long/short balance again:** M1 1h 33 long / 22 short, M2 1h 41/50, M4 1h
77/74, M3 1h 2/1 - balanced or long-leaning, never the one-sided shape of the
project's earlier positive results.

### 3. Expected `cost_r` on ETH

Identical to BTC because it is set by the stop, not the coin: **0.093 R at 1.5%,
0.066 at 2.12%, 0.047 at 3%, 0.023 at 6%** - all inside `LESSONS.md` §1's 0.1 R
line on fees alone. The funding ceiling is higher here: ETH's TRAIN funding is
0.02325% per 8h abs mean against BTC's 0.01886%, **1.23x**, so 144 h of full
hold at 1h is 0.42% of price, or 0.14 R on a 3% stop - above the 0.1 R line
where BTC's 0.11 R only just reaches it. Sizing is a non-issue on ETH (a 6% stop
sizes while ETH < 166,667 against a holdout peak of 4,832), so a 4h `UNSIZABLE`
here would be a defect, not an artefact.

### 4. The bear-market question, which ETH is unusually well placed to answer

The ETH TRAIN is 13 months of a falling market and the VALID is 2023-24. **So on
this coin the bear-market predictions in BTC Exp 036 §4 are directly testable on
TRAIN and are the most informative thing in the ETH half** - with the standing
caveat that a 13-month single-regime TRAIN is thin, so this is replication of the
BTC question and never a finding on its own:

- **M1's long leg** in a falling market - capitulation or cascade?
- **M2's long leg** - the one idea with a reason to be long when retail is short.
- **M2 and M3 must agree in sign.** On ETH **M3 cannot answer this** (19% of
  TRAIN), so the "smart money versus retail" comparison is carried by BTC only.
  That is worth saying plainly: the round's cleanest paired test is available on
  the primary coin and unavailable on the replication coin.
- **M4's short leg** - a downward Donchian break with open interest rising.

### 5. Judgement and stop rule

Both controls on every WATCH and PASS; **`--final` is not run by this agent**; and
the same `PLAN.md` §14 stop rule - no holdout CONFIRMED closes the new-data
question for these four signals, and any other use of the metrics needs a new
owner decision.

---

## Exp 010 - New data M1-M4 on ETHUSDT: 0 PASS, 1 WATCH (SKILL but NO_EDGE), and 10 of 16 rows too thin to read

**Date:** 2026-10-01
**Status:** complete. 16 evaluations. **ETH HOLDOUT UNTOUCHED - no PASS, so
`--final` was not a candidate and was not run.** No idea file edited. ETH now
has **89 evaluations**.

**16 evaluations: 0 PASS, 1 WATCH, 5 REJECT, 10 INCONCLUSIVE.** Both controls on
the 1 WATCH row. **The pre-registration's thinness prior was right and it is the
headline on this coin: 9 of the 16 cells were measured at under 50 TRAIN signals
before the first run, and 10 rows came back INCONCLUSIVE.**

### The four ideas, VALID mean R by clock

| idea | 15m | 30m | 1h | 4h | verdicts |
|---|---|---|---|---|---|
| **M1** 050 `oi_flush_reversal` | −0.159 | +0.028 | +0.018 | +0.303 (21 trades) | 3 INC, 1 REJ |
| **M2** 051 `retail_crowd_fade` | +0.026 | **+0.080** | +0.151 | +0.099 (52) | 2 INC, 1 WATCH, 1 REJ |
| **M3** 052 `smart_money_divergence` | −0.062 | −0.103 | −0.111 | +0.043 (18) | **4 INC** |
| **M4** 053 `oi_confirmed_breakout` | −0.145 | −0.068 | −0.075 | +0.022 | 3 REJ, 1 INC |

### The one WATCH row, with controls

| config | v trades | gross_r | cost_r | mean R | 95% CI | CAGR | maxDD | L/S | baseline | benchmark |
|---|---|---|---|---|---|---|---|---|---|---|
| **051 M2 @30m** | 197 | +0.1453 | 0.0656 | **+0.0797** | [−0.1088, +0.2842] | +7.1% | 14.4% | 94/103 | **SKILL** | **NO_EDGE** |

**One SKILL, one NO_EDGE, on the same row** - the same `SKILL + NO_EDGE` shape as
BTC 022, which spent a holdout and returned −0.0102 R, and as the port round's
ChartArt MACD+SMA200 rows. Per `PLAN.md` §5 step 1 that is not a strategy.

### What the trade lists say

Per-leg mean R on VALID, from `results/ETHUSDT/eval_trades/`:

| idea | clock | long leg | short leg | 2023 | 2024 |
|---|---|---|---|---|---|
| M1 | 15m | −0.107 (157) | **−0.278** (69) | −0.298 | −0.013 |
| M1 | 30m | +0.083 (134) | **−0.107** (55) | −0.038 | +0.096 |
| M1 | 1h | +0.031 (60) | −0.010 (29) | −0.198 | +0.282 |
| M2 | 30m | +0.133 (94) | +0.031 (103) | +0.005 | +0.134 |
| M2 | 1h | **+0.294** (61) | +0.032 (74) | +0.050 | +0.233 |
| M2 | 4h | **+0.684** (17) | **−0.185** (35) | +0.045 | +0.152 |
| M3 | 1h | −0.139 (92) | −0.075 (73) | −0.039 | −0.167 |
| M4 | 15m | −0.173 (282) | −0.099 (173) | −0.220 | −0.085 |
| M4 | 30m | −0.054 (202) | −0.090 (134) | −0.110 | −0.035 |

**1. M1's short leg loses here too, and by more.** −0.278 at 15m, −0.107 at 30m,
−0.010 at 1h, −0.101 at 4h, against a long leg of −0.107 to +0.429. **The
mirror-image finding from BTC Exp 037 replicates on the second coin: fading a
rally that comes with rising open interest is the losing side, and it is worse
on ETH than on BTC in 2023** (−0.298 against −0.220 at 15m). Two coins, one
mechanism, and the mechanism is the reason the idea is wrong rather than the
reason it is untested.

**2. M2's long leg is positive on this coin too, and the 4h cell's long leg
(+0.684 on 17 trades) has no short-side support at all** (−0.185 on 35). The
pre-registered prediction - M2 is the idea with a structural reason to be long
when retail is short - is confirmed here as well, which makes it the round's
most replicated result and still only a DRIFT/SKILL/NO_EDGE reading. **The year
split runs the other way from BTC's**: M2@1h is +0.050 in 2023 and +0.233 in
2024 here, against +0.400 and +0.082 on BTC. Both coins positive in both years,
in opposite order.

**3. M3 is untestable on ETH, exactly as pre-registered, and this is a data
limitation rather than evidence.** All four rows INCONCLUSIVE, VALID mean R
negative at 15m/30m/1h, and the trade lists confirm the row is being fed by very
few periods: 504 trades at 15m but a 1h TRAIN mean R of **+1.6635 against a VALID
−0.1109**. The cause is measured, not guessed: **only 19.2% of this coin's TRAIN
has a valid top-trader ratio against 80.79% NaN, while VALID is 0.014% NaN.**
So the paired test the pre-registration wanted - do "fade the crowd" and "follow
the smart money" agree? - **is available on the primary coin only, and BTC's
answer was that they agree by both being long.** A negative ETH row for M3 is
not evidence against top-trader divergence and must not be read as one.

**4. M4 is negative at all three clocks where it trades, against BTC's +0.800
and +0.489 at 15m and 30m.** BTC's two biggest numbers of the round do not
replicate on the second coin, which is the cleanest possible statement that they
were the bull market and not an edge. `AGENTS.md` §9's rule applied literally
again: **+0.8000 on 29 trades, 27 of them long, in 2023-24 BTC.**

### Cost, against the pre-registration

Measured VALID `cost_r` here is **0.0218 to 0.1011, median 0.0672**, against a
pre-registered fee-only floor of 0.023-0.093. At 15m the floor is 0.093 and the
measurement is 0.0991, so **funding again added only about 0.006 R** - the
pre-registration's funding ceiling of 0.14 R at 144 h was never approached,
because realised holds are 33-85 bars, not the cap. The one cell above
`LESSONS.md` §1's 0.1 R line is 15m at 0.1011, and 15m is again the worst clock.

### Verdict

`REJECT`, and the round's stop rule: **no PASS on this coin, so no holdout was
used.** 16 evaluations, 0 PASS, 1 WATCH (SKILL / NO_EDGE), 5 REJECT, 10
INCONCLUSIVE.

Across both coins the round is **32 evaluations, 0 PASS, 8 WATCH (4 SKILL, 4
DRIFT, 8 of 8 NO_EDGE), 9 REJECT, 15 INCONCLUSIVE**, and the project total is now
**438 evaluation rows, 5 holdout runs, 5 FAILED, 0 CONFIRMED.** The one data
source this project had never read - Binance's open interest and long/short
ratios - did not produce an edge on either coin, and the two hypotheses written
against it turned out to be the same long trade.

---

## Exp 011 - Review of ETH Exp 009/010

**Date:** 2026-10-01
**Status:** complete. A review, no evaluations. The full review of both coins
is BTC journal **Exp 038**.

Records are intact: 73 → 89 rows, old rows unchanged, holdout untouched.

ETH's single SKILL row, `051_retail_crowd_fade @30m`, is the second half of the
project's first two-coin SKILL. TRAIN independently chose the same parameters
on BTC (z 1.5, 24 h). Beta is +0.009, and both legs are positive (long +0.133,
short +0.031). It is NO_EDGE (VALID alpha +0.072, CI [−0.112, +0.233]) and
WATCH, so it is not an edge and not eligible for the holdout. M1's short-leg
"rising OI" wording is corrected in BTC Exp 038: `oi_flush` shorts when OI
**falls**, i.e. it fades a short squeeze.


---

## Exp 012 - Allocation test run on ETHUSDT (PLAN.md section 16)

**Date:** 2026-10-01
**Status:** complete. One run, no `--rerun`, no rule changed.

### Verdict
**Every rule, spot and perp: NO_IMPROVEMENT.** No rule IMPROVES (Sharpe >= buy-and-hold on the full run and both halves, with maxDD <= 0.6x buy-and-hold's).

**Caveat (perp buy_hold):** same effect as BTC. The perp buy_hold equity touches zero (maxDD 103%, 2025-26 maxDD 104%), so its CAGR/Sharpe/DD are not a clean benchmark. The spot table is unaffected. Not fixed or rerun.

### Full results (generated by `src/allocation.py`; same content as `journal/ETHUSDT/allocation.md`)

#### ETHUSDT - allocation test (PLAN.md section 16)

GENERATED by `src/allocation.py`. Do not edit by hand.

Daily bars, 1x exposure, position decided at the close and traded at the next
open. Every rule starts on the same day as buy-and-hold (day 200 of the data).
**IMPROVES** = Sharpe >= buy-and-hold's and max drawdown <= 0.6 x buy-and-
hold's, on the full run and on each half separately.

## spot (2018-03-05 .. 2026-08-31, cost 0.12% per side)

| rule | verdict | CAGR | max DD | Sharpe | longest underwater (days) | exposure | switches |
|---|---|---|---|---|---|---|---|
| buy_hold | - | +12.8% | 90.3% | 0.57 | 1382 | 100% | 0 |
| sma200 | NO_IMPROVEMENT | +31.0% | 73.8% | 0.76 | 973 | 50% | 54 |
| golden_cross | NO_IMPROVEMENT | +15.7% | 79.4% | 0.55 | 1028 | 50% | 17 |
| breakout_20w | NO_IMPROVEMENT | +14.7% | 73.6% | 0.54 | 1937 | 35% | 18 |

By segment (total return / max drawdown):

| rule | 2018 bear | 2019 | 2020-21 bull | 2022 bear | 2023-24 | 2025-26 | first half | second half |
|---|---|---|---|---|---|---|---|---|
| buy_hold | -84% / 90% | +0% / 64% | +2772% / 62% | -67% / 74% | +181% / 45% | -28% / 68% | +328% / 90% | -34% / 74% |
| sma200 | -44% / 44% | +7% / 48% | +755% / 67% | -16% / 19% | +124% / 29% | +4% / 38% | +413% / 74% | +94% / 38% |
| golden_cross | -50% / 57% | +0% / 50% | +860% / 62% | -31% / 37% | +29% / 43% | -18% / 43% | +377% / 79% | -27% / 62% |
| breakout_20w | -22% / 22% | +4% / 45% | +198% / 62% | +0% / -0% | +32% / 36% | +0% / 29% | +144% / 74% | +32% / 44% |

## perp (2020-07-19 .. 2026-08-31, cost 0.07% per side, plus funding)

| rule | verdict | CAGR | max DD | Sharpe | longest underwater (days) | exposure | switches |
|---|---|---|---|---|---|---|---|
| buy_hold | - | +19.9% | 103.0% | 0.38 | 1756 | 100% | 0 |
| sma200 | NO_IMPROVEMENT | +51.3% | 68.3% | 0.96 | 1029 | 56% | 34 |
| golden_cross | NO_IMPROVEMENT | +31.2% | 71.5% | 0.74 | 1937 | 56% | 11 |
| breakout_20w | NO_IMPROVEMENT | +27.9% | 74.7% | 0.71 | 1937 | 41% | 13 |
| sma200_long_short | NO_IMPROVEMENT | +61.3% | 75.4% | 1.02 | 1022 | 100% | 34 |

By segment (total return / max drawdown):

| rule | 2018 bear | 2019 | 2020-21 bull | 2022 bear | 2023-24 | 2025-26 | first half | second half |
|---|---|---|---|---|---|---|---|---|
| buy_hold | - | - | +1090% / 67% | -91% / 99% | +619% / 71% | -61% / 104% | +1090% / 67% | -74% / 104% |
| sma200 | - | - | +678% / 68% | -11% / 15% | +85% / 33% | +1% / 39% | +678% / 68% | +64% / 39% |
| golden_cross | - | - | +859% / 67% | -34% / 40% | +8% / 49% | -21% / 44% | +859% / 67% | -44% / 66% |
| breakout_20w | - | - | +306% / 70% | +0% / -0% | +15% / 40% | -3% / 29% | +306% / 70% | +11% / 49% |
| sma200_long_short | - | - | +505% / 75% | +42% / 27% | +70% / 35% | +30% / 47% | +505% / 75% | +212% / 47% |




---

## Exp 013 - Allocation test rerun on ETHUSDT after the allocation.py fixes (PLAN.md section 16)

**Date:** 2026-10-01
**Status:** complete. `--rerun`, allowed because the code was fixed (BTC Exp 041: liquidation at equity <= 0). No rule changed or added.

### Verdict
Every rule, spot and perp: **NO_IMPROVEMENT**, same as the first run.

**Spot: identical to the first run.** Compared programmatically, the old and new `summary.json` spot sections differ only by the new `missing_days` field; every metric, segment and verdict is the same.

**Perp changed, only `buy_hold`.** Old: CAGR +19.9%, maxDD 103.0%, Sharpe 0.38. New: liquidated at equity <= 0 (about 2025-04, derived from 77% exposure of the days; the 2025-26 and second-half segments show -100% / 100%): total -100%, CAGR -100%, maxDD 100%. The other four perp rows are identical to the first run, and so is every verdict.

### Full results (generated; same content as `journal/ETHUSDT/allocation.md`)

#### ETHUSDT - allocation test (PLAN.md section 16)

GENERATED by `src/allocation.py`. Do not edit by hand.

Daily bars, 1x exposure, position decided at the close and traded at the next
open. Every rule starts on the same day as buy-and-hold (day 200 of the data).
**IMPROVES** = Sharpe >= buy-and-hold's and max drawdown <= 0.6 x buy-and-
hold's, on the full run and on each half separately.

## spot (2018-03-05 .. 2026-08-31, cost 0.12% per side)

| rule | verdict | CAGR | max DD | Sharpe | longest underwater (days) | exposure | switches |
|---|---|---|---|---|---|---|---|
| buy_hold | - | +12.8% | 90.3% | 0.57 | 1382 | 100% | 0 |
| sma200 | NO_IMPROVEMENT | +31.0% | 73.8% | 0.76 | 973 | 50% | 54 |
| golden_cross | NO_IMPROVEMENT | +15.7% | 79.4% | 0.55 | 1028 | 50% | 17 |
| breakout_20w | NO_IMPROVEMENT | +14.7% | 73.6% | 0.54 | 1937 | 35% | 18 |

By segment (total return / max drawdown):

| rule | 2018 bear | 2019 | 2020-21 bull | 2022 bear | 2023-24 | 2025-26 | first half | second half |
|---|---|---|---|---|---|---|---|---|
| buy_hold | -84% / 90% | +0% / 64% | +2772% / 62% | -67% / 74% | +181% / 45% | -28% / 68% | +328% / 90% | -34% / 74% |
| sma200 | -44% / 44% | +7% / 48% | +755% / 67% | -16% / 19% | +124% / 29% | +4% / 38% | +413% / 74% | +94% / 38% |
| golden_cross | -50% / 57% | +0% / 50% | +860% / 62% | -31% / 37% | +29% / 43% | -18% / 43% | +377% / 79% | -27% / 62% |
| breakout_20w | -22% / 22% | +4% / 45% | +198% / 62% | +0% / -0% | +32% / 36% | +0% / 29% | +144% / 74% | +32% / 44% |

## perp (2020-07-19 .. 2026-08-31, cost 0.07% per side, plus funding)

| rule | verdict | CAGR | max DD | Sharpe | longest underwater (days) | exposure | switches |
|---|---|---|---|---|---|---|---|
| buy_hold | - | -100.0% | 100.0% | 0.68 | 1756 | 77% | 1 |
| sma200 | NO_IMPROVEMENT | +51.3% | 68.3% | 0.96 | 1029 | 56% | 34 |
| golden_cross | NO_IMPROVEMENT | +31.2% | 71.5% | 0.74 | 1937 | 56% | 11 |
| breakout_20w | NO_IMPROVEMENT | +27.9% | 74.7% | 0.71 | 1937 | 41% | 13 |
| sma200_long_short | NO_IMPROVEMENT | +61.3% | 75.4% | 1.02 | 1022 | 100% | 34 |

By segment (total return / max drawdown):

| rule | 2018 bear | 2019 | 2020-21 bull | 2022 bear | 2023-24 | 2025-26 | first half | second half |
|---|---|---|---|---|---|---|---|---|
| buy_hold | - | - | +1090% / 67% | -91% / 99% | +619% / 71% | -100% / 100% | +1090% / 67% | -100% / 100% |
| sma200 | - | - | +678% / 68% | -11% / 15% | +85% / 33% | +1% / 39% | +678% / 68% | +64% / 39% |
| golden_cross | - | - | +859% / 67% | -34% / 40% | +8% / 49% | -21% / 44% | +859% / 67% | -44% / 66% |
| breakout_20w | - | - | +306% / 70% | +0% / -0% | +15% / 40% | -3% / 29% | +306% / 70% | +11% / 49% |
| sma200_long_short | - | - | +505% / 75% | +42% / 27% | +70% / 35% | +30% / 47% | +505% / 75% | +212% / 47% |


