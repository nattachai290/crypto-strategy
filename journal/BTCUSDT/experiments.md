# Research Log — BTCUSDT Intraday Futures

Every experiment gets an entry. Entries are **appended, never edited**, so we
can see which ideas survived and which did not.

Verdict vocabulary:
- `KEEP` — survived out-of-sample with acceptable drawdown
- `WATCH` — promising on paper, not yet verified out-of-sample
- `REJECT` — failed the test; hypothesis considered dead
- `INCONCLUSIVE` — test was not decisive (too few trades, bug, etc.)

---

## Exp 000 — Infrastructure & data

**Date:** 2026-09-26
**Status:** complete

### Hypothesis
Before any strategy work, build a trustworthy harness. If the data or the
fill model is wrong, every later result is fiction.

### What was built
- `src/config.py` — costs, risk, leverage, session rules, walk-forward sizes
- `src/datafeed.py` — S3 download + cache + **validation** of the public data
- `src/indicators.py` — causal indicators, no TA dependency
- `src/backtest.py` — event-driven backtester + metrics
- `src/strategies.py` — 10 rule-based strategies (the "rules" arm)
- `src/ml_filter.py` — causal features + trade-outcome labelling
- `src/run_ml.py` — walk-forward rules-vs-ML comparison
- `src/experiment.py` — loading, resampling, walk-forward splits, sweeps

### Data acquired
| Dataset | Rows | Coverage |
|---|---|---|
| BTCUSDT 1m klines | 3,506,400 | 2020-01-01 .. 2026-08-31, **80/80 months, 0 gaps** |
| BTCUSDT 1m mark klines | 3,506,400 | same |
| BTCUSDT funding rate | 7,305 | same |

Validation confirmed month completeness and gap-free 1m series.

### Bugs found and fixed (important context)
1. **Silent data truncation.** Binance added a header row inside the monthly
   zips (klines from 2022-01, fundingRate from 2024-01). A `dtype=float64` read
   raised per-file, and the run continued — so 58 of 80 months were dropped
   while the script *looked* like it succeeded. Fixed by reading as text,
   dropping the header, then coercing. Added `validate()` so this can never
   pass silently again.
   *Lesson applied: a data pipeline that logs errors and exits 0 is a lie.
   Validation is now mandatory.*
2. **Backtest loop too slow.** numpy scalar indexing inside the per-bar loop
   made a single 210k-bar backtest take minutes. Converted hot arrays to
   Python lists and precomputed the funding-event index per bar, removing the
   inner `while` loop. **Not yet re-verified for speed or correctness after
   the change** — see open items.
3. `rolling(500).quantile()` / `.rank(pct=True)` were O(n·w) and dominated
   signal generation. Replaced with coarse-grid + forward-fill versions
   (`indicators.rolling_quantile`, `indicators.rolling_pct_rank`).

### Anti-self-deception rules baked into the engine
- Signal on bar `i` close → fill at bar `i+1` **open** (never the bar you used)
- Market orders → taker fee 0.05%, plus 0.02% slippage per fill against us
- Bar touching both stop and target → **stop fills first**
- Funding charged at real timestamps while a position is open
- Position size derived from the stop distance, so "1% risk" is 1% in any regime
- Equity marked to market every bar, so max-DD and Sharpe see the intrabar path
- Walk-forward: model never sees a bar it is scored on

### Open items / next session
1. **Re-verify the optimised backtester**: confirm speed AND that metrics are
   unchanged vs. the pre-optimisation version. The optimisation touched the
   hot loop, so this must be checked before trusting any number.
2. Sanity-check the engine against a hand-computed trade (one entry, one stop)
   to confirm the R accounting and fee/slippage maths.
3. Run `python src\experiment.py baseline` — the full-sample sweep of all 10
   rule strategies. Log results here.
4. Then walk-forward rules vs ML (`python src\run_ml.py 5`).

### No result yet
Nothing has been traded or backtested to a conclusion. This entry is
infrastructure only.

---

## Exp 001 — Engine verification

**Date:** 2026-09-26
**Status:** complete

### Hypothesis
The optimised backtester still computes the same thing as the naive version
it replaced. If it does not, every later number is noise.

### Method
`src/test_engine.py`, four independent checks:

1. **Hand-computed trade** — fixed prices, fixed stop, expected PnL and R
   derived analytically. The R for a stopped long is
   `-(stop + exit_slip*stop)/stop - (fee*entry + fee*exit)/risk`.
2. **Differential test** — a deliberately naive reference implementation
   written from the spec, run on 8 random seeds. Trade lists must match
   entry, exit, side, reason, holding bars and R.
3. **Cost monotonicity** — zero cost must beat real cost must beat double cost;
   the trade sequence must be invariant to fees.
4. **No look-ahead** — a truncated run must be an exact prefix of the full run.

### Result
**ALL CHECKS PASSED.** 2,297 trades matched the reference bar-for-bar.

### Bugs the tests caught (all real, all in code I had written)
| # | Bug | Effect |
|---|---|---|
| 1 | `net_pnl` omitted the **entry** fee | expectancy and R understated losses by ~0.3R per trade; `sum(net_pnl) != equity change`, so all downstream stats were wrong |
| 2 | Exit fee charged on the pre-slippage price | small, but inconsistent with the entry side |
| 3 | `bars` held counted as `i - entry_i` | off by one |
| 4 | The last bar of a data window was treated as a **session close** | every time-windowed backtest silently refused to open trades near its own end. Biased every walk-forward fold. |
| 5 | `Trade` timestamps were tz-naive | broke comparison against the tz-aware index |

Two of my own *test* expectations were also wrong, and it is worth recording
why, because both would have led to "fixing" correct code:
- I asserted trade count is invariant to costs. It is not, and should not be:
  slippage shifts the entry price, hence the stop and target levels, so a
  different set of fills is the *correct* outcome.
- I asserted a stopped trade realises about -1.0R. With entry slippage, exit
  slippage and two taker fees it realises -1.30R on a 200-point stop at 50,000.
  Round-trip cost is 0.14% of price; a 0.4% stop means 0.35R of friction.

### Verdict
`KEEP` — the harness is trustworthy. Numbers from here on mean something.

---

## Exp 002 — Performance: why the sweep hung

**Date:** 2026-09-26
**Status:** complete

### Symptom
A single 700k-bar backtest took >10 minutes. An 82-config sweep never printed
its first progress line.

### Causes found
| Cause | Cost | Fix |
|---|---|---|
| `list(df.index)` materialising 3.5M Timestamps | 4.0s of an 8.2s 1m backtest | pull Timestamps lazily from the index object |
| `supertrend` recursion over **numpy scalars** with `np.isnan` | **>15 minutes** on 700k bars | rewrote over plain Python floats: 0.55s (**~1800x**) |
| `supertrend` band recurrence used the *current* bar's close instead of the **previous** close | 7 direction changes in 6.5 years instead of 17,575 | fixed; indicator was quietly broken |
| Pure-Python loop over all bars for max-drawdown duration | ~4s on 1m | vectorised run-length encoding |
| 12 worker processes x 16 BLAS threads | thread thrashing | `OMP/MKL_NUM_THREADS=1` before numpy import |
| `rolling(500).quantile()` / `.rank()` | O(n*w) | coarse grid + forward fill |

1m backtest: **8.7s -> 3.7s**. 5m: **~2s**. The sweep went from "unfinishable"
to 82 configs in under 4 minutes on 12 cores.

### Verdict
`KEEP`. Lesson: measure before optimising, and profile the *whole* pipeline —
the assumption that the backtest loop was the bottleneck was wrong, and it was
the indicator that was pathological.

---

## Exp 003 — Baseline + combined-indicator sweep (the main event)

**Date:** 2026-09-26
**Status:** complete — **REJECT for almost everything, WATCH for one**

### Hypothesis
Some combination of indicator, timeframe and exit style has positive
out-of-sample expectancy after realistic costs.

### Method (leak-free)
- 82 configurations: 10 single-indicator baselines + 7 combined-indicator
  strategies, across 3m/5m/15m/30m, with and without exit management
  (break-even move, ATR trailing stop).
- All evaluated on **TRAIN only** (2020-01 .. 2023-12).
- Top 20 by train Sharpe, minimum 150 trades, shortlist only.
- Shortlist then run on **TEST** (2024-01 .. 2026-08), which no selection
  decision had seen.

### Result
**18 of 20 shortlisted configurations were negative out-of-sample.**

| Config | train Sharpe | test Sharpe | test return | test maxDD |
|---|---|---|---|---|
| combo_funding_reversion 15m | -0.023 | **+0.089** | +18.7% | 10.3% |
| combo_funding_reversion 30m | -0.047 | **+0.069** | +9.9% | 6.3% |
| combo_vote 15m | -0.005 | -0.059 | -75.9% | 86.8% |
| combo_breakout_confirmed 30m | +0.025 | -0.067 | -27.5% | 43.7% |
| supertrend_flip 30m | -0.012 | -0.089 | -38.0% | 44.7% |
| donchian_breakout 15m | -0.086 | -0.106 | -57.6% | 64.8% |
| ... 13 more | | all negative | | |

Note the shape of the best rows: `combo_funding_reversion` was **worse in
train than in test**. That is the opposite of an overfit, which normally
shines in-sample and dies out-of-sample. Either it has a small real edge, or
it is one of ~2 lucky configs out of 20. Both are consistent with the data.

### Diagnostics on the survivor (`src/diagnose.py`, full 80 months)
```
trades                 680
median stop            0.94% of price
round-trip cost        0.14% of notional  ->  0.163 R per trade
gross expectancy       0.172 R   (the price moves really do contain an edge)
fee + slippage drag    0.163 R
net expectancy         0.009 R
bootstrap 95% CI       [-0.070, +0.088]   p(mean>0) = 0.59
```

**The bootstrap interval straddles zero.** With 680 trades we cannot
distinguish this from zero expectancy. Honest verdict: *inconclusive*, not
"profitable".

### The structural finding
The decomposition `gross_r - cost_r = exp_r` is exact, and it reframes the
whole problem:

```
cost_r  =  round_trip_cost  /  stop_distance
         =  0.14%           /  0.94%   =  0.163 R
```

A strategy only needs to be *right by 0.163R per trade* before it earns
anything. The best edge found was 0.172R. The margin is 0.009R — and no amount
of indicator cleverness changes that arithmetic. It can only be improved by
either a genuinely larger edge, or cheaper execution.

### Verdict
- 18 configs: `REJECT` — negative out-of-sample expectancy.
- `combo_funding_reversion`: `WATCH` — positive OOS, low drawdown, but the
  confidence interval includes zero. Not tradable on this evidence.
- The cost arithmetic, not the signals, is the binding constraint.
  Next: `src/cost_lab.py` measures both escape routes — widen the stop so
  `cost_r` falls, and trade as a maker.

---

## Exp 004 — The cost lab: stop width is the whole game

**Date:** 2026-09-27
**Status:** complete — this changed the direction of the project

### Hypothesis
`cost_r = round_trip_cost / stop_distance`. If that is right, widening the
stop should cut cost roughly linearly while leaving the gross edge intact.

### Method
`src/cost_lab.py` — 9 configurations x 7 stop widths x 4 execution scenarios
on the full 80 months. But because looking at stop width on the full sample
makes `stop_mult` a fitted parameter, `src/round2_stopwidth.py` then redoes
the selection honestly: sweep stop width on **TRAIN only**, freeze the winner,
and run that single choice on **TEST**.

### Result — the hypothesis held
Train-only, `combo_breakout_confirmed` 30m:

| stop_mult | trades | gross_r | cost_r | exp_r | Sharpe | maxDD |
|---|---|---|---|---|---|---|
| 1.5 | 1039 | 0.091 | 0.153 | -0.062 | -0.090 | 47.3% |
| 2.5 | 776 | 0.082 | 0.097 | -0.015 | -0.010 | 23.1% |
| 3.5 | 591 | 0.087 | 0.074 | **+0.013** | +0.025 | 16.3% |
| 5.0 | 409 | 0.096 | 0.055 | **+0.040** | +0.040 | 14.1% |
| 7.0 | 303 | 0.091 | 0.042 | **+0.049** | +0.070 | 9.8% |

**`gross_r` barely moves (0.08-0.10) while `cost_r` falls 0.153 -> 0.042.**
That is the whole finding. A tighter stop does not make the strategy better;
it makes the *cost* bigger relative to the same edge. Every "1.8x ATR stop"
rule in the first sweep was a cost-efficiency mistake wearing a risk-management
costume.

Note that risk per trade is unchanged — position size scales down as the stop
widens, because sizing is derived from the stop. The 1% risk rule still holds.

### Frozen stop width, then out-of-sample (TEST = 2024-01 .. 2026-08)

| config | stop_mult | train exp_r | test trades | test exp_r | test Sharpe | test return | test maxDD |
|---|---|---|---|---|---|---|---|
| combo_funding_reversion 15m | 2.5 | -0.036 | 87 | **+0.163** | +0.091 | **+13.2%** | 5.5% |
| combo_funding_reversion 30m | 1.5 | -0.051 | 114 | +0.095 | +0.075 | +11.5% | 7.8% |
| combo_breakout_confirmed 15m | 9.0 | -0.014 | 36 | +0.136 | +0.055 | +3.8% | 3.1% |
| combo_breakout_confirmed 30m | 7.0 | +0.049 | 3 | +0.249 | +0.032 | +0.8% | 1.3% |
| supertrend_flip 30m | 7.0 | +0.020 | 28 | -0.055 | -0.004 | -0.5% | 4.7% |
| donchian_breakout 30m | 7.0 | +0.028 | 3 | -0.257 | -0.052 | -0.7% | 1.2% |
| combo_trend_pullback 30m | 9.0 | +0.013 | 0 | — | — | — | — |
| combo_vol_flow 15m | 7.0 | -0.029 | 147 | -0.038 | -0.026 | -3.4% | 9.8% |

The best two rows are `combo_funding_reversion`: 87 trades, +13.2% on 100 USDT
over 2.67 years, max drawdown 5.5%, PF 1.51, win rate 60.9%.

### The honest reading of that +13.2%
- **+4.8% per year.** That is not "high profit". It is a marginal edge.
- 87 trades is a small sample. The bootstrap CI on expectancy over the full
  history was **[-0.070, +0.088]**, straddling zero.
- Two of the four positive rows are `combo_funding_reversion`, and in both
  cases the *train* result was worse than the test result. Selecting the best
  of 8 candidates on test is still selection, just a second one.

### Verdict
- The stop-width effect: `KEEP`. Mechanistically explained, large, and it
  replicates on train-only data.
- `combo_funding_reversion`: `WATCH` — survives out-of-sample with low
  drawdown, but the confidence interval includes zero and the trade count is
  small. Not enough to trade.
- Everything else: `REJECT`.

---

## Exp 005 — These strategies only exist in some market regimes

**Date:** 2026-09-27
**Status:** complete — reframes the problem

### Observation
While checking the walk-forward output (which looked wrong — 1 trade in a
6-month fold) the cause turned out to be real, not a bug: `combo_funding_reversion`
generated **5 signals in 2022 H1** and 3,403 in 2020-2023 overall.

| window | signals |
|---|---|
| 2022-01 .. 2022-07 | 5 |
| 2022-07 .. 2023-01 | 34 |
| 2023-01 .. 2023-07 | 7 |
| 2023-07 .. 2024-01 | 145 |
| 2024-01 .. onwards | the bulk |

Funding only reaches extremes when the crowd is one-sided, which happens in
sustained trends and not in ranges. **The strategy has no opinion most of the
time.** Averaging a Sharpe over folds that contain 1 trade is meaningless; the
only folds with statistical content are the ones where the regime matched.

### Consequence for the research
A backtest that averages over 6.5 years of mostly-inactive periods will
understate a regime-conditional strategy and overstate a regime-independent
one. Any claim about these systems has to be stated as: *conditional on the
regime, here is the record*. Which means the honest headline is not an
annualised return, it is a regime table plus a bootstrap interval.

### Verdict
`KEEP` as a finding. It explains why fold-level Sharpe bounces around so much
and it is the reason not to trust any single-number summary from here on.

---

## Exp 006 — Rules vs ML filter, walk-forward

**Date:** 2026-09-27
**Status:** complete — ML wins, but not enough on its own

### Hypothesis
The rules arm fires on a fixed condition. A model trained on causal features
can pick the subset of signals that actually work, raising `gross_r`.

### Method
`src/run_ml.py` on 15m bars.
- Candidate pool: 12 strategies, one signal per bar max (priority order).
- 110,203 labelled candidates, 35 causal features (trend, vol regime, VWAP
  distance, taker flow, funding, calendar, realised-vol ratios).
- Label: realised net R from the same intrabar logic as the backtester
  (stop-first, taker fees, slippage, funding).
- 9 walk-forward folds: fit on 24 months, predict the next 6, never overlapping.
- Two model families (LightGBM regression on R, classification on win), four
  prediction thresholds each.
- Scored through the *same* backtester, so it is apples-to-apples.

### Result — 9-fold walk-forward summary (15m, stop_mult 3.5)

| method | trades | total return | mean Sharpe | worst DD | expectancy_R |
|---|---|---|---|---|---|
| rules (no filter) | ~2,700 | -1.9 | **-0.30** | 45% | -0.13 |
| reg thr 0.00 | 1923 | -1.86 | -0.249 | 43% | -0.135 |
| reg thr 0.05 | 1583 | -1.57 | -0.229 | 38% | -0.137 |
| reg thr 0.10 | 1206 | -1.08 | **-0.175** | 37% | -0.124 |
| clf thr 0.10 | 1211 | -1.26 | -0.202 | 37% | -0.125 |
| clf thr 0.20 | 272 | -0.31 | **-0.114** | 17% | -0.209 |

### Reading
1. **The ML filter genuinely works.** It lifts `gross_r` sharply — in fold 6
   the unfiltered rules had `gross_r = 0.047`; `reg thr 0.20` had
   `gross_r = 0.487`, ten times better, with a 72% win rate. That is real
   signal selection, not noise.
2. **It is still not profitable**, because the candidate pool's stop was too
   tight: `cost_r` was 0.15-0.25 R per trade. A 0.487 gross edge minus 0.17
   cost is still a loss.
3. Monotonic in the threshold: raising it always reduces both the number of
   trades and the damage. That is what a real (if weak) ranking looks like —
   but it also means "trade less" is doing most of the work.

### Verdict
- ML filter: `KEEP` as a component. It measurably improves trade selection.
- Not `KEEP` as a strategy on its own: it needs the wide stops from Exp 004
  underneath it. Next experiment combines the two — ML filter on top of a
  2x-scaled stop width. If `gross_r ~ 0.3` and `cost_r ~ 0.08`, the
  arithmetic finally works in our favour.

---

## Exp 007 — Definitive out-of-sample measurement

**Date:** 2026-09-27
**Status:** complete — **the headline result**

### Two measurement errors that had to be fixed first
Both of these produced numbers that looked encouraging and were wrong:

1. **`ret_sum` added per-fold percentage returns.** Each fold restarts at
   100 USDT, so summing the percentages neither compounds nor describes any
   real account. Folds have to be chained: each starts at the previous
   fold's closing balance.
2. **The ML label set measures a population the account never traded.** There
   are ~110,000 labelled candidate signals, but with one position open at a
   time the backtest executes only a few hundred per configuration. Bootstrapping
   the 13,000 labels said `mean R = -0.046`; the 686 trades the backtest
   actually executed said `+0.056`. Same model, same folds — different
   populations. Only the executed trades describe the account.

Corrected: pool **every trade the backtester actually executed** across all 9
folds into one series, bootstrap that, and chain the equity.

### Result — 24 configurations, 15m bars, 2022-01 .. 2026-08

`cost_r` and `gross_r` are per-trade, in R. `cagr` and `max_dd` are on a
chained 100 USDT account.

| stop scale | best config | mean R | 95% CI | p(R>0) | cost_r | gross_r | CAGR | maxDD |
|---|---|---|---|---|---|---|---|---|
| 1.0 | clf 0.00 | -0.135 | [-0.187, -0.084] | 0.000 | 0.155 | +0.020 | **-28.1%** | 77% |
| 2.0 | clf 0.10 | +0.021 | [-0.050, +0.092] | 0.727 | 0.091 | +0.113 | **+1.8%** | 6.5% |
| 3.5 | clf 0.00 | +0.007 | [-0.050, +0.064] | 0.594 | 0.059 | +0.066 | +0.1% | 6.8% |
| 5.0 | reg 0.10 | **+0.038** | **[-0.039, +0.115]** | 0.833 | 0.055 | +0.093 | **+2.2%** | 1.8% |

### The one thing that clearly worked
The stop-width effect is real, large, monotone, and mechanistically explained:

| stop scale | cost_r | CAGR range across all 6 configs |
|---|---|---|
| 1.0 | 0.138 - 0.171 | -28% .. -18% |
| 2.0 | 0.086 - 0.092 | -4.3% .. +1.8% |
| 3.5 | 0.059 - 0.069 | -2.9% .. +0.1% |
| 5.0 | 0.043 - 0.055 | -0.0% .. +2.2% |

Going from a 1x to a 5x stop width took the account from losing 25%/year to
roughly break-even, **without changing the signals at all**. Cost is 0.14% of
notional; a 0.5% stop means 0.28R of friction, a 2.5% stop means 0.056R.

### The thing that did not work
**No configuration produced a confidence interval that excluded zero.** The
best is `+0.038 R/trade` with a CI of `[-0.039, +0.115]` on 154 trades. That
is indistinguishable from zero, and it corresponds to **+2.2% per year** on a
chained account with a 1.8% maximum drawdown.

### Verdict
- **REJECT** as a profitable system. Across 106+ configurations, 4
  timeframes, 6.5 years, two strategy families (hand-written rules and an ML
  filter), and a cost model that is deliberately harsh, **there is no
  statistically demonstrated edge** in intraday BTCUSDT futures at retail
  (VIP0) execution costs.
- **KEEP** the finding that stop width dominates everything else. That is a
  real, transferable insight and it cost most of the losses in the first sweep.
- **KEEP** the ML filter as a component: it raised `gross_r` from ~0.02 to
  0.11-0.17 consistently. It is a better trade *picker*; it just cannot
  out-pick a 0.09R cost bill.
- Practical note: at 100 USDT with 1% risk, even a genuine 2%/yr edge is about
  2 USDT a year. The size of the edge is not the problem — whether it exists
  is.

### The one lever left, and it is large
Execution cost is still 60% of the friction budget at wide stops:

| execution | round trip | cost_r at a 2.5% stop |
|---|---|---|
| taker (VIP0, used throughout) | 0.14% | 0.056 |
| post-only maker | 0.04% | **0.016** |

A maker round trip is 3.5x cheaper. Against the `gross_r` of 0.09 measured
here, that turns a +0.038R into roughly +0.07R — the difference between
"cannot be distinguished from zero" and "comfortably positive".

This is **not yet proven** and is the obvious next experiment, but it cannot
be faked: a post-only order that sits unfilled is not a cheaper trade, it is a
skipped trade, and if it only fills when the market is about to move against
you the edge inverts. Testing it honestly requires a fill model against the
1-minute book — likely adverse selection, so realistically somewhere between
the 0.14% taker line and the 0.04% maker line. That work has not been done.

### Correction to the above, after building the fill model (Exp 008)
I overstated the benefit. The 3.5x figure assumed maker fees on the *exit*
too, and a stop-loss does not get a maker fill. The honest round trip is:

| execution | fee | slippage | round trip |
|---|---|---|---|
| taker | 0.05% + 0.05% | 0.02% + 0.02% | **0.14%** |
| post-only entry, taker exit | 0.02% + 0.05% | 0.00% + 0.02% | **0.09%** |

**1.55x, not 3.5x.** And that is only the price. The real cost of a resting
limit is that it fills selectively — it fills when the market comes to you,
which is when the market is moving against the entry.

---

## Exp 008 — Post-only execution, measured instead of assumed

**Date:** 2026-09-27
**Status:** superseded by Exp 010 (data was time-shifted). Mechanism stands;
**numbers are wrong and were re-run.** See Exp 010 for the corrected figures.

### Hypothesis
Cutting the round trip from 0.14% to 0.09% is enough to turn the marginal
edge positive, *provided* the adverse selection from resting orders is not
worse than the saving.

### Method
Added an `entry_mode="post_only"` execution model to the backtester:

- The limit rests at the **signal bar's close**, pushed `entry_offset_atr`
  into the market.
- It fills only if the **next bar's range trades through it**. For a long that
  means `low[i] <= limit`, i.e. the order fills when price came *down* to us.
  Adverse selection is therefore a structural consequence of the model, not an
  assumption bolted on afterwards.
- `entry_fill_ratio` models queue position: a touch does not guarantee full size.
- Exits stay taker, because a stop really is a market order.

Validated in `test_engine.py` section 5: fill rate is 0.99 at offset 0, 0.68 at
0.25, 0.43 at 0.50, 0.11 at 1.0, 0.00 at 2.0 — monotonically falling, and it
never fills above the signal close.

Two engine bugs found while building this, both caught by the new tests:
1. A `continue` in the entry path skipped the mark-to-market write, leaving
   `np.empty` memory in the equity curve. Silent, and it corrupted max-DD.
2. The limit offset depended on the caller supplying an `atr` column. Without
   it the offset collapsed to zero and every limit rested exactly at the close,
   which quietly turned the whole experiment back into the taker case. Now
   falls back to an internally computed ATR.

### Result (ORIGINAL RUN — INVALID, see Exp 010)
9 walk-forward folds, 15m bars, ML reg threshold 0.10, pooled executed trades.

| stop scale | mode | fill% | trades | gross_r | cost_r | net R | CAGR |
|---|---|---|---|---|---|---|---|
| 2.0 | taker | 100% | 587 | +0.077 | 0.090 | -0.0126 | -1.7% |
| 2.0 | **post-only 0.30** | 56% | 585 | +0.113 | 0.072 | **+0.0414** | **+3.5%** |
| 3.5 | taker | 100% | 288 | +0.061 | 0.069 | -0.0081 | -0.7% |
| 3.5 | **post-only 0.30** | 58% | 254 | +0.098 | 0.053 | **+0.0452** | +2.1% |
| 5.0 | taker | 100% | 154 | +0.093 | 0.055 | +0.0380 | +1.3% |
| 5.0 | **post-only 0.15** | 75% | 143 | +0.113 | 0.042 | **+0.0706** | +2.0% |

### What survives
The *direction* of every finding held after the fix: post-only beats taker at
all three stop widths, `cost_r` falls by roughly the predicted amount, and the
edge breaks down past offset 0.30 where fill rate drops too low. The mechanism
is sound. Only the magnitudes were wrong, and they were all **better than
reality** — the corrected post-only gain is roughly +0.01 to +0.05 R rather
than +0.03 to +0.05 R, and the headline "best" result is gone.

---

## Exp 009 — Holding period: fixing a flaw and the sample size at once

**Date:** 2026-09-27
**Status:** running

### The flaw
The best configuration holds for `max_hold = 72` bars on 15m = **18 hours**.
The brief was intraday, 1–4 hours. The thing I had been calling a day-trading
strategy was a swing strategy with an intraday label, and I did not notice for
seven experiments. It also happens to be the reason the sample is tiny.

Both problems have the same fix: shorten `max_hold`. It makes the strategy
what it was supposed to be, and it trades more often. Risk: cutting winners
early destroys the edge, so the parameter is swept, not assumed.

### Method
`src/round4_holdperiod.py` — 5m and 15m, three stop scales, holding periods of
2/3/4/6/8 hours, post-only execution at offset 0.20, ML reg threshold 0.10.
Walk-forward as before, with bootstrap on the pooled executed trades.

### Result (5m bars, the grid that carried signal)

| hold | trades | gross_r | cost_r | net R | 95% CI | CAGR |
|---|---|---|---|---|---|---|
| 2h | 19 | -0.033 | 0.063 | -0.0961 | [-0.295, +0.115] | -0.4% |
| 3h | 95 | +0.005 | 0.091 | -0.0863 | [-0.208, +0.036] | -1.9% |
| 4h | 139 | +0.010 | 0.105 | -0.0957 | [-0.216, +0.024] | -2.7% |
| 6h | 230 | +0.041 | 0.115 | -0.0738 | [-0.175, +0.027] | -4.0% |
| 8h | 274 | -0.065 | 0.116 | -0.1810 | [-0.279, -0.084] | -9.4% |

(5m, stop scale 2.0. At scales 3.5 and 5.0 the 6h row is the only positive one:
+0.0076 and +0.0140 respectively, both with intervals straddling zero.)

### The finding that matters
**The edge only exists when positions are held for many hours.** Cutting the
hold to the 1–4 hours the brief actually asked for turns every configuration
negative. On 15m the effect is so strong that at 8 hours the ML filter at
threshold 0.10 passes *one* signal in nine folds — the model has correctly
learned that short-horizon trades in this pool are not worth taking, and it
refuses to trade.

That is the honest conclusion: **there is no intraday edge here to find.** The
marginal positive result from Exp 008 (+0.07 R, CI [-0.007, +0.150]) depends on
6–18 hour holds. Complying with the brief removes it.

### Verdict
`REJECT` for intraday. The project answered the question it was asked and the
answer is that the question has a negative answer. What remains worth doing is
not more indicator search — it is either (a) accepting a multi-hour swing
horizon and being explicit that it is not day trading, or (b) testing a
genuinely different hypothesis, such as market-making or funding carry, which
earn from the spread rather than from a directional edge.

---

## Exp 010 — Every resampled bar was one window in the past

**Date:** 2026-09-27
**Status:** complete — **invalidates the numbers in Exp 003-009**

### How it was found
Someone asked why the project only had 1-minute files. I had been describing
resampling as if 1m were the only granularity Binance publishes. It is not —
a directory listing shows **15 timeframes**: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h,
6h, 8h, 12h, 1d, 3d, 1w, 1mo. So "we derive it ourselves" was a choice, and
choices like that need checking rather than assuming.

### The defect
`resample()` used `label="right", closed="left"`. Pandas then stamps each bar
with the **end** of its window. Binance stamps a kline with the **start** —
that is what `open_time` means.

Result: every 5m bar in the project contained the price action from
`[T-5m, T)` instead of `[T, T+5m)`. The timestamps looked perfect, the bar
count was exactly right (8,928 for March 2024), and the index compared equal.

Diffing against Binance's native 5m file for 2024-03:

```
native 5m : 8928 bars
mine      : 8928 bars
index identical : True

mine_close == native close of PREVIOUS 5m bar?  mismatches = 0 / 8927
mine_close == native close of the SAME bar?     mismatches = 8925 / 8928
```

A clean one-bar shift, zero exceptions. `open/high/low/volume/taker_buy_base`
all shifted identically.

### Why nine experiments did not catch it
The backtest is **internally consistent**: signals, stop levels, targets and
fills were all computed from the same shifted series, so the simulation is a
faithful study of a market that happens to run five minutes behind. Nothing
in the engine could detect it, and the metrics were self-consistent.

What it *did* corrupt:
- funding charged at real timestamps against positions that in reality were
  different trades
- calendar features (hour-of-day) read off the mislabelled bar
- any comparison against data outside the pipeline

### Fix and verification
`label="left", closed="left"`. New `src/verify_resample.py` downloads the
natively published file for each timeframe and diffs every column:

```
  1m  OK   bars 44640   index_match=True   all columns match
  3m  OK   bars 14880   index_match=True   all columns match
  5m  OK   bars  8928   index_match=True   all columns match
 15m  OK   bars  2976   index_match=True   all columns match
 30m  OK   bars  1488   index_match=True   all columns match
  1h  OK   bars   744   index_match=True   all columns match
```

This check should have existed from the start. Downloading one timeframe and
deriving the rest is a reasonable optimisation; deriving them *without ever
comparing against the source* is how you end up nine experiments deep on
shifted data.

### Corrected headline results

Definitive walk-forward, 15m, 9 folds, re-run on fixed data:

| stop scale | method | thr | trades | gross_r | cost_r | net R | 95% CI | CAGR |
|---|---|---|---|---|---|---|---|---|
| 1.0 | reg | 0.10 | 767 | +0.020 | 0.149 | -0.129 | [-0.196, -0.063] | -17.0% |
| 2.0 | reg | 0.00 | 883 | +0.067 | 0.085 | -0.018 | [-0.066, +0.030] | -3.2% |
| 3.5 | reg | 0.05 | 366 | +0.046 | 0.064 | -0.018 | [-0.077, +0.044] | -1.0% |
| 5.0 | reg | 0.00 | 289 | +0.060 | 0.050 | +0.009 | [-0.046, +0.063] | +0.7% |
| 5.0 | clf | 0.05 | 130 | +0.062 | 0.048 | +0.014 | [-0.065, +0.094] | +0.4% |
| 5.0 | clf | 0.10 | 72 | +0.101 | 0.050 | +0.051 | [-0.065, +0.168] | +0.9% |

Post-only re-run (Exp 008 corrected), ML reg thr 0.10:

| stop scale | taker net R | best post-only | gain | CI excludes 0 |
|---|---|---|---|---|
| 2.0 | -0.031 | +0.021 (`po 0.50`) | +0.052 | no |
| 3.5 | -0.015 | -0.001 (`po 0.30 q50%`) | +0.014 | no |
| 5.0 | -0.009 | +0.094 (`po 0.30 q50%`, 41 trades) | +0.103 | no |

### What changed
- **The previous best result (+0.0706 R, CI [-0.007, +0.150]) does not
  reproduce.** The best now is +0.051 R on 72 trades, CI [-0.065, +0.168] —
  worse and less reliable than it looked.
- **CAGR drops from +1.3% to +0.9%** at the best setting. Still nothing.
- The best post-only configs are now the 40-trade `q50%` variants, which have
  intervals half as wide as they are long. That is noise, not an improvement.
- **The stop-width finding survives** — it is the same mechanism on shifted
  data, and shifting time does not change relative cost ratios.
- **The conclusion is unchanged: no proven edge.** The bug made the results
  look *better* than they are, never worse.

### Verdict
`REJECT` the Exp 003-009 numbers. The framework is sound; the data pipeline
had a one-bar labelling error. Everything must be re-run — which is cheap now
that `make_dataset` is 110x faster and `verify_resample.py` guards the
pipeline.

### The lesson
I verified the backtester to the point of a differential test against a second
implementation, wrote a bootstrap, checked for look-ahead, and audited fills —
and the defect lived in the **data preparation step**, which nothing was
checking because "we resampled it ourselves" felt like a safe assumption.
Verification effort follows attention, and my attention was on the engine.

---

## Exp 011 — Two exit-management engine bugs, and a standard research gate

**Date:** 2026-09-27
**Status:** complete

Also records that Exp 009 (listed as "running" above) completed with the
verdict written in its entry.

### Bug 1 — break-even / trailing stop used the current bar's close
`run_backtest` moved the stop at the start of bar `i` using `c[i]`, the close
of that same bar, and then checked bar `i`'s high/low against the moved stop.
That is look-ahead, and it cut both ways:
- a bar that fell through the original stop and then closed above the
  break-even trigger was booked as a break-even exit instead of -1R
  (optimistic);
- far more often, a bar that rallied lifted the stop above its own open, and
  the trade was "stopped" at that open. Winners were cut at the first strong
  bar (pessimistic).

Fix: the stop moves using `c[i-1]` / `atr[i-1]`, from the bar after the
trigger close onward, and never on the entry bar. New tests in
`test_engine.py` §6 fail on the old code and pass on the new.

### Bug 2 — the trailing stop had no ATR while in a position
`strategies._pack` wrote the `atr` column only on signal bars (0
elsewhere). The engine reads ATR on every bar of an open position to move
the trail, so the trail only moved on bars that happened to follow another
raw signal. Fix: ATR on every bar. Test §6 D checks it.

### Effect (15m, full history, taker; same signals)
| config | engine | trades | mean R | gross_r | CAGR |
|---|---|---|---|---|---|
| combo_breakout_confirmed stop 2 tp 4 BE 1 | old | 1584 | -0.105 | +0.084 | -19.9% |
| | fixed | 1732 | -0.084 | +0.113 | -16.7% |
| ema_trend stop 2 tp 4 BE 0.5 trail 1/1.5 | old | 1124 | -0.374 | -0.083 | -41.9% |
| | fixed | 1527 | -0.263 | +0.040 | -40.3% |
| donchian_breakout stop 3.5 BE 1 trail 1.5/2.5 | old | 1757 | -0.030 | +0.076 | -8.0% |
| | fixed | 2167 | -0.018 | +0.089 | -5.7% |

(Bug 1 fix only. In a separate check, donchian_breakout stop 3.5, trail
1.0/1.5, no TP, max_hold 96: the bug 2 fix moved mean R from -0.010 to -0.019.)
Net, the old engine **understated** break-even/trailing exits. Every exit-
management result before this entry (the `be_at`/`trail_*` variants in
Exp 003) is biased low. They are still negative after the fix, but exit
techniques deserve a proper retest.

### New standard protocol: `src/evaluate.py`
From here on every idea is an `ideas/*.json` file evaluated the same way:
- TRAIN 2020-01..2022-12: a grid of ≤ 64 combos; pick the best mean R among
  combos with ≥ 100 trades.
- VALID 2023-01..2024-12: the frozen choice only. Gates: ≥ 100 trades, train
  and valid mean R > 0, bootstrap CI lower bound > 0, mean R > 0 at 1.5x
  costs, maxDD ≤ 20% → PASS / WATCH / REJECT / INCONCLUSIVE.
- HOLDOUT 2025-01..2026-08: one run per config, only after PASS, locked in
  `results/BTCUSDT/holdout_log.csv`.
- New `src/recipes.py`: triggers + filters + exits combined from JSON; test
  §7 checks every block for causality.

Smoke tests (examples, both REJECT): `example_trend_breakout` valid mean R
+0.016, CI [-0.082, +0.117], fails at 1.5x cost; `example_range_reversion`
negative on train. The trend-breakout example's holdout was consumed while
testing the `--final` lock (it FAILED, -0.23 R); that is recorded in
`holdout_log.csv`.

### Verdict
`KEEP` the engine fixes and the protocol. All results in
`results/BTCUSDT/evaluations.csv` use the fixed engine and native data.

---

## Exp 012 — Thirteen ideas: the stop is not an ATR multiple, it is a price distance

**Date:** 2026-09-28
**Status:** complete — 13 ideas, 0 PASS, 8 WATCH, 3 REJECT, 2 INCONCLUSIVE, **holdout not used**
(only a PASS may spend the holdout, and nothing passed, so HOLDOUT 2025-01..2026-08 is
still completely untouched).

Infrastructure first: `test_engine.py` → ALL CHECKS PASSED; `datafeed.py` → VALIDATION: OK
with all five native timeframes at 80/80 months, 0 duplicates, 0 gaps. Two changes were
needed to get here and neither touches costs, risk, splits or gates:

- `datafeed.py` now fetches the 480 monthly zips through a 8-thread pool instead of
  one at a time (network I/O only; the parse stays single-threaded and in key order, so
  the cache is identical). 2.5 h → ~4 min.
- `evaluate.py` must be run with `--workers 1` on Windows. Its worker pool assumes
  `fork`, and Windows `ProcessPoolExecutor` spawns instead, so the child processes start
  with an empty `_G` and every combo dies with `KeyError: 'bars'`. This is a platform
  bug in the harness, not in an idea; it is reported rather than patched because
  `evaluate.py` is not ours to edit.

### Ideas tested

| idea file | eval_id | verdict | valid mean R | 95% CI | note |
|---|---|---|---|---|---|
| 001_trend_breakout_trail | 252109899e | REJECT | −0.0242 | [−0.143, +0.099] | gross +0.155, cost 0.179 |
| 002_pct_stop_trend_breakout | 5066a68b70 | WATCH | +0.0389 | [−0.048, +0.127] | cost 0.179 → 0.087 |
| 003_funding_fade | 55b321947e | INCONCLUSIVE | −0.943 (7 trades) | — | 23 train trades, unusable |
| 004_squeeze_expansion | d3042109b4 | REJECT | +0.0641 | [−0.153, +0.296] | gross **+0.269**, cost **0.205** |
| 005_session_open_break | cdde91ae48 | REJECT | −0.0750 | [−0.234, +0.082] | cost 0.167, 2024 −0.141 |
| 006_long_only_trend | c208dafd61 | INCONCLUSIVE | +0.2437 (42 trades) | [−0.110, +0.645] | train +0.0015 — regime only |
| 007_direction_ablation | 93ef5c196c | WATCH | +0.0698 | [−0.041, +0.165] | train picked **short**, not long |
| 008_exit_by_price | 0269bf5d77 | WATCH | +0.0698 | [−0.041, +0.165] | identical: train prefers the SHORTEST hold |
| 009_short_5m_pct_stop | 32e903fb0d | WATCH | +0.0374 | [−0.108, +0.168] | 5m gave *fewer* trades, not more |
| **010_short_breakout_post_only** | **70fb497bcf** | **WATCH** | **+0.0850** | **[−0.030, +0.186]** | **best; cost 0.068, DD 8.5%** |
| 011_wider_stop | 29b6b39400 | WATCH | +0.0637 | [−0.052, +0.158] | 0.02–0.025 is a plateau |
| 012_taker_flow | 72454823e9 | WATCH | +0.0850 | [−0.030, +0.186] | filter inert, identical to 010 |
| 013_squeeze_pct_stop | 7bcd1ac0d7 | WATCH | +0.0502 | [−0.102, +0.203] | gross collapsed to +0.129 |

### What we learned

1. **A stop measured in ATR multiples is not a constant price distance, and that was
   the single largest source of loss in this project.** Idea 001 measured a genuine
   gross edge (+0.155 R on valid) and still lost, because the same 3.0x ATR stop was
   1.28% of price in 2020-2022 and 0.78% in 2023-2024, so `cost_r` drifted from 0.109 to
   0.179 and crossed the gross edge. Adding a `pct` stop to `recipes.py`
   (`stop.type: "pct"`, a fraction of price with an ATR sanity clamp) took the identical
   entry from −0.024 to +0.039, cost_r 0.179 → 0.087, maxDD 37.8% → 16.3%. A stop width
   that scales with volatility scales the *cost* of trading with it.

2. **`gross_r` is not comparable across different stop widths, and reading it as
   "edge" is a trap.** Idea 004's squeeze entry showed gross_r +0.269, the highest
   number ever recorded here and roughly double anything else — but it also stopped out
   71% of its trades, because the squeeze filter selects the calmest periods in the
   sample and a 3x ATR stop there is ~0.7% of price. Re-running the identical entry with
   a 2% stop (idea 013) collapsed gross_r to +0.129. The "huge gross edge" was mostly a
   tight stop inflating R, not information. Compare `net R`, never `gross_r`, across
   ideas.

3. **The profitable side is the short side, and TRAIN chose it, not us.** Idea 007 held
   trigger, filters, stop and exits fixed and varied only `direction`. Train picked
   `short`, and short-only more than doubled valid mean R over both-sides (+0.070 vs
   +0.039) while halving the trade count and cutting maxDD to 9.7%. This contradicts the
   prior in Exp 003-011 that short intraday BTC is merely expensive: on this entry the
   short side carries the edge and the long side dilutes it.

4. **Execution is half the edge, and it is measurable.** A post-only entry at 0.1 ATR
   took cost_r 0.086 → 0.068 with a 92% fill rate, adding +0.015 R and taking maxDD from
   9.7% to 8.5%. Note the honest caveat: the post-only limit is filled preferentially
   when price comes back to the level, so 8% of signals are dropped and the survivors
   are mildly adverse-selected. The 1.55x from Exp 008/010 is confirmed on native data.

5. **Two plausible improvements were falsified, which is worth as much as the wins.**
   (a) *Longer holds* (idea 008): train chose the shortest hold offered (8h) over 16h
   and 24h, and 67% of combos were positive against 50% — the clock is not what
   truncates winners. (b) *Order-flow confirmation* (idea 012): the `taker_flow` filter
   at the thresholds the grid chose (`ratio < 0.55`) is satisfied almost always, so it
   is a no-op — results are identical to idea 010 to the last decimal. The taker ratio
   simply does not deviate far enough from 0.5 at any threshold that still leaves 100
   trades.

6. **Lowering the timeframe no longer costs anything — and still did not help.** With a
   `pct` stop, cost_r is 0.14%/pct regardless of timeframe, which removes the reason
   every 1m/3m/5m configuration in Exp 003-006 lost. So idea 009 tried 5m with every
   lookback scaled 3x to hold each indicator's *time* span constant, expecting 3x the
   signals. It got 205 valid trades versus 233 on 15m and a worse mean R (+0.037 vs
   +0.070). The statistical-power argument was sound and the market refused it.

7. **The remaining gap is precision, not sign.** The best configuration fails exactly one
   gate. From its CI, sd ≈ 0.80 R, so PASS needs mean R > 1.568/sqrt(n): 0.103 R at the
   current 219 trades, 0.128 at 150, 0.157 at 100. It sits at 0.085. Every idea that
   raised mean R did so by cutting trades, which raises the bar faster than it lowers it.
   That is the real obstacle, and more parameter search will not clear it.

### Best candidate (idea 010, eval 70fb497bcf)

15m, `donchian_break(48)` + `htf_trend(50,4)` + `adx_min(20)`, **short only**,
`pct` stop 2.0% (ATR clamp 1.5–8.0), no TP, ATR trail armed at 1.5R trailing 2.5 ATR,
8h time stop, post-only entry at 0.1 ATR.

| split | trades | gross_r | cost_r | mean R | 95% CI | CAGR | maxDD |
|---|---|---|---|---|---|---|---|
| train 2020-2022 | 631 | +0.140 | 0.056 | +0.0839 | | | 12.1% |
| valid 2023-2024 | 219 | +0.153 | 0.068 | +0.0850 | [−0.030, +0.186] | +6.2% | 8.5% |
| valid ×1.5 cost | | | | +0.0736 | | | |

Both validation years positive (2023 +0.069, 2024 +0.145), 100% of train combos
positive, win rate 64%, PF 1.31. It is a **WATCH**: `valid_ci_lo > 0` fails and nothing
else. **This is not a profitable strategy and it has never been tested on the holdout.**

### Verdict

`WATCH` — hold, do not spend. The batch produced a real, mechanistically explained
improvement in the honest direction (mean R −0.024 → +0.085, maxDD 37.8% → 8.5%,
CAGR −11.8% → +6.2%) and one methodological finding worth more than the strategy:
**on this market the stop, not the signal, decides the result.** But eight WATCHes is not
evidence, and the one gate that fails is the one that matters — the confidence interval
still contains zero, so this could easily be a lucky corner of 2023-2024. The holdout
stays sealed. Do not run `--final`.

---

## Exp 013 — Asking why the short edge exists, and not finding out

**Date:** 2026-09-28
**Status:** complete — 3 ideas, 1 WATCH (identical to 010), 2 REJECT. **Holdout still
never touched.** 16 evaluations run in total; 0 PASS.

Exp 012 ended with a WATCH and one uncomfortable possibility: idea 010's edge had never
been explained, and an unexplained edge that was found by trying thirteen things is
exactly the kind of edge that is a coincidence. These three ideas attack that
possibility directly instead of trying to improve the number.

### Ideas tested

| idea file | eval_id | verdict | valid mean R | 95% CI | train combos positive | note |
|---|---|---|---|---|---|---|
| 014_short_breakout_funding_crowding | 942d22a978 | WATCH | +0.0850 | [−0.030, +0.186] | 100% | **identical to 010** — filter inert |
| 015_short_supertrend_robustness | 785b9ba3b1 | REJECT | +0.0384 | [−0.077, +0.149] | **0%** | edge does **not** reproduce |
| 016_long_mean_reversion_pct_stop | dc08ab8828 | REJECT | −0.0614 | [−0.279, +0.164] | 0% | long side has no gross edge |

### What we learned

1. **The short edge is not a crowding edge.** Idea 014 blocked shorts when funding was
   extreme *on the short side* — the one condition under which the liquidation-crowding
   story predicts the trade should be skipped. Train selected the loosest threshold in
   the grid (0.0001), which blocks essentially nothing, and valid came back identical to
   idea 010 to the last decimal: 219 trades, +0.0850. The leveraged-long-crowd
   explanation for short breakouts is not supported. Funding is not where this lives.

2. **The short edge is not "short BTC in a downtrend" either. It is a narrow pattern.**
   This is the important result. Idea 015 swapped the Donchian channel for a Supertrend
   flip — a completely unrelated mechanism, an ATR trailing stop instead of a price
   channel — keeping only direction, the trend filter and the stop. Train mean R was
   **−0.0212 with 0% of combos positive**, against **+0.0839 with 100% positive** for the
   Donchian version on the same period. Same market, same direction, same costs, same
   stop width, opposite result. So the +0.085 R belongs to the 12-hour Donchian break
   specifically, not to shorting, not to the trend, not to the execution.

3. **The long side has no gross edge of any kind.** Idea 016 tested the one long
   mechanism never tried — reversion after a 2-2.5 sigma stretch, with a stop placed
   below the stretch where it belongs rather than at a volatility multiple. gross_r was
   +0.020 on train and +0.033 on valid: indistinguishable from zero, in both periods,
   in both years, and 0% of train combos positive. Combined with Exp 012's idea 006
   (long-only trend, +0.0015 on train), the long side of intraday BTCUSDT at retail costs
   produced nothing worth trading in sixteen evaluations. Every candidate with a gross
   edge in this project has been short.

4. **Two consecutive ideas returned results bit-identical to idea 010.** Ideas 012, 014
   and 015 together establish something the numbers alone hide: idea 010 sits in a wide
   basin, not on a spike. Nothing in its neighbourhood — order flow, funding crowding, a
   different entry mechanism — moves it. A wide basin is genuinely reassuring about
   *robustness of the estimate within this sample*, and it is exactly what a
   parameter-sweep artefact does not look like. It is not reassuring about the sample.

### Where this leaves the best candidate

Idea 010 is unchanged and still the best thing here: valid 219 trades, gross +0.153,
cost 0.068, mean R +0.0850, CI [−0.030, +0.186], CAGR +6.2%, maxDD 8.5%, both years
positive, 100% of train combos positive, and now three neighbouring hypotheses that all
fail to move it. What Exp 013 removed is the *explanation*. There is no mechanism left
that predicts it, and idea 015 is direct evidence that a plausible alternative mechanism
operating on the same trades produces a loss instead of a gain. An unexplained effect
found by searching thirteen configurations, whose closest relative loses money, with a
confidence interval that still spans zero, should be treated as a candidate and not as a
strategy.

### Verdict

`WATCH`, and the case is now weaker than after Exp 012 rather than stronger. The
reusable, well-supported result from these two batches is not the strategy — it is the
cost mechanism: **a stop must be a price distance, not a volatility multiple**
(`cost_r = round_trip_cost / stop_pct`, Exp 012), and post-only execution is worth about
+0.015 R at a 92% fill rate. Both are now in TECHNIQUES.md and will apply to any future
work on any symbol. The strategy result is that sixteen ideas across both sides, four
timeframes, two execution models and a fixed cost structure produced no configuration
whose confidence interval excludes zero — which is the same answer this project gave
after 106 configurations before Exp 012, now reached again by a different route and with
a materially better understanding of why.

Do not run `--final`. Do not report any of this as profitable. If work continues, the
honest next question is not another parameter but the one Exp 013 could not answer: why
does a 12-hour Donchian break, taken short in a downtrend, revert often enough to win 64%
of the time — and if the answer is "because BTC drifts down", that is a statement about
the asset, not an edge, and should be written down as such.

---

## Exp 014 — STOPPED: the engine had the wrong sign on every short trade

**Date:** 2026-09-29
**Status:** interrupted. Round 1 was NOT started. No idea was evaluated in this entry.

Found while executing R1.0 of `docs/research/PLAN.md` (the analysis of idea 010, which
reads its trade list directly). R1.0 is analysis only, so it is unaffected; everything
that depends on the engine's PnL is.

### The bug

`src/backtest.py`, inside `close_position()`:

```python
net   = pos_qty * (px_adj - pos_entry) - fee - pos_fees + pos_funding   # line 308
gross = pos_qty * (px_adj - pos_entry)                                   # line 326
```

`pos_side` is missing. For a long that expression is right; for a short the PnL is
`pos_qty * (pos_entry - px_adj)` and the sign is inverted. Everything else in the
function's neighbourhood carries the sign correctly, which is what makes this an
oversight rather than a convention:

| place | expression | correct? |
|---|---|---|
| entry slippage (l.363) | `o[i] * (1.0 + slip * want)` | yes |
| stop / target placement (l.403-404) | `entry -/+ want * sd` | yes |
| funding (l.429-430) | `... * (1.0 if pos_side > 0 else -1.0)` | yes |
| mark-to-market equity (l.491) | `pos_qty * pos_side * (c[i] - pos_entry)` | yes |
| **realised PnL / R (l.308, 314, 326)** | **`pos_qty * (px_adj - pos_entry)`** | **NO** |

### Proof: a long and a short on identical signals are mirror images

One synthetic series, price falling cleanly 100.00 -> 99.00, zero costs, stop 2.0 wide,
no target, time exit after 5 bars. The only difference between the two runs is `side`.

| run | entry | exit | gross_pnl | r_multiple |
|---|---|---|---|---|
| `side = -1` (should **profit**: price fell) | 99.9831 | 99.9153 | **−0.033898** | **−0.0339** |
| `side = +1` (should **lose**) | 99.9831 | 99.9153 | **−0.033898** | **−0.0339** |

Identical to six decimals. A long and a short on the same trade cannot have the same
P&L, so the engine is wrong for one of them, and the short's sign is the one that is.

### Why the test suite passed

Two independent reasons, and both are worth recording:

1. **The hand-computed test is a long.** `test_engine.py` §1 is titled "flat market
   that drifts down into the stop of a long". There is no hand-computed short anywhere
   in the file.
2. **The differential reference shares the bug.** `reference_backtest()` was written
   "independently" but from the same reading, and at `test_engine.py:100` it has the
   identical line `pnl = pos["qty"] * (px_adj - pos["entry"])`. §2 compares the engine
   against that reference over random signals that *do* include shorts
   (`p=[0.7, 0.15, 0.15]` for 0/+1/-1), so it exercises the broken path on every seed
   - and the two implementations agree perfectly, because they are wrong in the same
   way. A differential test can only catch a discrepancy, never a shared assumption.

The test that would have caught it is one line: the same synthetic bar series run once
with `side = +1` and once with `side = -1`, asserting the two P&Ls are exact negatives
of each other. That is a symmetry property, not a hand-computed constant, so it does
not depend on anyone remembering the sign convention.

### Impact on every result recorded so far

The R of a short trade can be recovered exactly from the committed trade lists, because
the only error is the sign of the price-difference term:

```
D      = (fees - funding) / (qty * stop_dist)      # cost in R
r_true = -r_reported - 2*D                          # side = -1
r_true =  r_reported                                # side = +1
```

| eval_id | idea | n | n short | reported mean R | **true mean R** | true 95% CI |
|---|---|---|---|---|---|---|
| 70fb497bcf | 010 short breakout post-only | 219 | 219 | +0.0850 | **−0.1721** | [−0.274, −0.057] |
| 72454823e9 | 012 same + taker_flow | 219 | 219 | +0.0850 | **−0.1721** | [−0.274, −0.057] |
| 942d22a978 | 014 same + funding filter | 219 | 219 | +0.0850 | **−0.1721** | [−0.274, −0.057] |
| 93ef5c196c | 007 direction ablation, short leg | 233 | 233 | +0.0698 | **−0.1944** | [−0.291, −0.084] |
| 0269bf5d77 | 008 exit study, short leg | 233 | 233 | +0.0698 | **−0.1944** | [−0.291, −0.084] |
| 32e903fb0d | 009 5m short | 205 | 205 | +0.0374 | **−0.1734** | [−0.305, −0.026] |
| 785b9ba3b1 | 015 supertrend short | 147 | 147 | +0.0384 | **−0.1396** | [−0.250, −0.023] |
| 29b6b39400 | 011 wider stop, short | 202 | 202 | +0.0637 | **−0.1438** | [−0.239, −0.027] |
| 5066a68b70 | 002 pct stop, both sides | 455 | 209 | +0.0389 | **−0.0356** | [−0.122, +0.054] |
| 7bcd1ac0d7 | 013 squeeze pct stop, both | 166 | 63 | +0.0502 | **−0.0911** | [−0.237, +0.062] |
| bd648a5e36 | example trend breakout | 497 | 222 | +0.0160 | **−0.0087** | [−0.105, +0.090] |
| 252109899e | 001 both sides | 699 | 316 | −0.0242 | **−0.0683** | [−0.186, +0.058] |
| c89e3474cc | example range reversion | 112 | 68 | +0.0596 | **−0.2183** | [−0.373, −0.059] |
| d3042109b4 | 004 squeeze, both | 195 | 70 | +0.0641 | **−0.2092** | [−0.435, +0.040] |
| 55b321947e | 003 funding fade | 7 | 7 | −0.9430 | +0.7514 | [−0.110, +1.586] |
| cdde91ae48 | 005 session open, both | 318 | 142 | −0.0750 | +0.0258 | [−0.131, +0.187] |
| c208dafd61 | 006 long-only trend, 30m | 42 | **0** | +0.2437 | +0.2437 | [−0.110, +0.645] |
| dc08ab8828 | 016 long reversion | 74 | **0** | −0.0614 | −0.0614 | [−0.279, +0.164] |

- **16 of 18 evaluations traded the short side. 13 of 18 have the sign of their edge
  flipped.**
- The two long-only evaluations are untouched, and they are the only numbers in the
  project that survive as they stand.
- The best candidate of Exp 012-013 (idea 010, the WATCH) is in truth a **significantly
  losing** strategy: −0.1721 R with a CI that excludes zero on the wrong side.
- The grid selections on TRAIN were made on inverted expectancy, so every short-side
  parameter choice in Exp 012-013 is void, not just the reported verdicts.
- Mixed long/short runs are also wrong in a second-order way: after a short closes,
  `cash` is wrong, so later position sizes are wrong. Only pure long-only runs are
  exactly correct.

### What this does to the conclusions of Exp 012 and Exp 013

They are backwards, and specifically:

- "The short side is the only place with any positive signal, and TRAIN chose it" - the
  short side is the only place that loses *significantly*, and TRAIN chose it because
  the inverted number looked best.
- "The effect is specific to the 12h Donchian break, because Supertrend shorts gave
  0% of train combos positive" - both lose. The comparison was between two inverted
  results, so it carried no information.
- "The edge survives lower timeframes / post-only / wider stops" - all of those were
  measured on inverted PnL.
- What *does* survive: the cost-mechanism findings, which are about `cost_r`, not about
  the sign of the edge. A stop must be a price distance rather than an ATR multiple
  (Exp 012), and post-only is worth ~+0.015 R. Those statements are unaffected, because
  the sign error applies equally to the gross and the cost side of any single trade.
  Exp 012's "compare net R, never gross R" advice also survives.
- The only surviving result of any size is **idea 006: long-only, 30m EMA cross,
  +0.2437 R on 42 validation trades** - too few trades to be anything, but it is now the
  most interesting number in `results/BTCUSDT/`.

### Verdict

`REJECT` the whole of Exp 012-013's conclusions; keep the cost mechanism. Do **not**
start Round 1: `PLAN.md` §2 is built on "the short side is the only positive signal" and
on "no new long-only ideas in Rounds 1-2", and both of those are now false, so the plan
needs revising before it is executed. This is a Level 3 change (`src/backtest.py`) and
AGENTS.md §5 / PLAN.md §9 require the owner's yes before the fix is made.


---

## Exp 015 — Engine fixed (short sign, account sizing); all 18 ideas re-evaluated

**Date:** 2026-09-29
**Status:** complete. Owner approved the engine fix and the 1,000 USDT research account.

### Fix 1 — the short-side P&L sign (found in Exp 014)
`backtest.close_position()` now signs the price move by `pos_side`
(`move = qty * side * (exit - entry)`), used by cash, net P&L, `gross_pnl` and
`gross_r`. The reference implementation in `test_engine.py` had the same line
and was fixed too. New `test_engine.py` section 9, which **failed on the old
code** (a stopped-out short read +0.80 R instead of −1.30 R) and passes now:
- A: the same trade long vs short, zero costs, gives exactly opposite P&L and R
- B: mirror the whole price series, flip every random signal, and every trade's
  R must be identical (5 seeds). No remembered sign convention is involved,
  and a shared-assumption reference can't fool it
- C: a hand-computed short stopped out by a rally, with real fees and slippage
- D: an unsizable trade is counted in `size_skips`, never silently dropped

### Fix 2 — the 100 USDT account could not size most trades
Found while checking the fix: after correcting the sign, idea 010's recorded
parameters produced 170 validation trades instead of 219. Cause: BTC's qty
step is 0.001 BTC. At 2024 prices (60–100k) with a 2% stop, one step already
risks 1.2–2 USD, which is more than 1% of 100 USDT, so the engine floored qty to
0 and skipped the trade. It was worse than a sample-size problem:

| idea 010, VALID, recorded params | trades | 2023 / 2024 | mean R |
|---|---|---|---|
| 100 USDT account (as run so far) | 170 | 160 / **10** | −0.163 |
| unconstrained sizing | 376 | 172 / 204 | −0.144 |

**The skipping depended on P&L:** a losing strategy's equity falls, more of its
trades become unsizable, and its later losses are never booked. Under the sign
bug the (wrongly) winning shorts grew the account and could keep trading,
which is part of why 219 trades had been reported.

Owner decision: research runs use `C.EVAL_EQUITY = 1000` USDT (1% risk still;
R, CI, drawdown % and CAGR measure the same thing). Whether the owner's real
100 USDT account can size a candidate is checked in its strategy card
(PLAN.md §6). The engine now reports `size_skips`, and `evaluate.py` prints
it in every report. Every re-run below has `size_skips = 0`.

### Records
The Exp 011–014 records (`evaluations.csv`, `evaluations.md`, trade lists)
were moved unchanged to `results/BTCUSDT/legacy/pre_signfix/`. The 16 plain
`.csv` trade files committed alongside the `.csv.gz` ones were duplicates and
were removed. `holdout_log.csv` is unchanged (one row, the example's lock test).
All 18 idea files were then re-evaluated from scratch with `--rerun`: a replay
of past decisions on a correct engine, not new tuning, so the version budget
was not applied.

### Result: 0 PASS, 0 WATCH, 16 REJECT, 2 INCONCLUSIVE

| idea | eval_id | tf | direction chosen | old valid (n / mean R) | train mean R | valid n | valid mean R | 95% CI | ×1.5 cost | maxDD | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 001_trend_breakout_trail | 252109899e | 15m | both | 699 / -0.024 | -0.029 | 818 | -0.057 | [-0.168, +0.065] | -0.138 | 49% | REJECT |
| 002_pct_stop_trend_breakout | 5066a68b70 | 15m | both | 455 / +0.039 | -0.043 | 786 | -0.031 | [-0.126, +0.066] | -0.092 | 37% | REJECT |
| 003_funding_fade | 55b321947e | 15m | both | 7 / -0.943 | +0.058 | 13 | +0.218 | [-0.280, +0.732] | +0.179 | 5% | INCONCLUSIVE |
| 004_squeeze_expansion | d3042109b4 | 15m | both | 195 / +0.064 | -0.049 | 198 | -0.190 | [-0.408, +0.051] | -0.319 | 34% | REJECT |
| 005_session_open_break | cdde91ae48 | 15m | both | 318 / -0.075 | +0.079 | 390 | +0.067 | [-0.079, +0.214] | -0.002 | 17% | REJECT |
| 006_long_only_trend | c208dafd61 | 30m | long | 42 / +0.244 | +0.002 | 52 | +0.136 | [-0.048, +0.334] | +0.103 | 2% | INCONCLUSIVE |
| 007_direction_ablation_pct_stop | 93ef5c196c | 15m | long | 233 / +0.070 | -0.031 | 418 | +0.051 | [-0.041, +0.147] | +0.010 | 14% | REJECT |
| 008_short_breakout_exit_by_price | 0269bf5d77 | 15m | short | 233 / +0.070 | -0.075 | 296 | -0.133 | [-0.249, -0.015] | -0.171 | 37% | REJECT |
| 009_short_breakout_5m_pct_stop | 32e903fb0d | 5m | short | 205 / +0.037 | -0.052 | 197 | -0.110 | [-0.229, +0.017] | -0.156 | 20% | REJECT |
| 010_short_breakout_post_only | 70fb497bcf | 15m | short | 219 / +0.085 | -0.123 | 339 | -0.120 | [-0.206, -0.027] | -0.146 | 32% | REJECT |
| 011_short_breakout_wider_stop | 29b6b39400 | 15m | short | 202 / +0.064 | -0.075 | 395 | -0.086 | [-0.134, -0.038] | -0.105 | 27% | REJECT |
| 012_short_breakout_taker_flow | 72454823e9 | 15m | short | 219 / +0.085 | -0.049 | 166 | -0.126 | [-0.244, -0.001] | -0.152 | 19% | REJECT |
| 013_squeeze_expansion_pct_stop | 7bcd1ac0d7 | 15m | both | 166 / +0.050 | -0.002 | 187 | -0.091 | [-0.234, +0.061] | -0.123 | 17% | REJECT |
| 014_short_breakout_funding_crowding | 942d22a978 | 15m | short | 219 / +0.085 | -0.153 | 380 | -0.160 | [-0.255, -0.062] | -0.192 | 46% | REJECT |
| 015_short_supertrend_robustness | 785b9ba3b1 | 15m | short | 147 / +0.038 | +0.041 | 227 | -0.120 | [-0.221, -0.013] | -0.147 | 24% | REJECT |
| 016_long_mean_reversion_pct_stop | dc08ab8828 | 15m | long | 74 / -0.061 | -0.066 | 85 | -0.146 | [-0.341, +0.062] | -0.185 | 14% | REJECT |
| example_range_reversion | c89e3474cc | 15m | both | 112 / +0.060 | +0.092 | 131 | -0.150 | [-0.324, +0.025] | -0.228 | 20% | REJECT |
| example_trend_breakout | bd648a5e36 | 15m | both | 497 / +0.016 | -0.049 | 678 | -0.042 | [-0.117, +0.032] | -0.099 | 31% | REJECT |

### What we learned
- **Shorting breakouts on BTC loses, and significantly.** All 7 short-only
  ideas are negative on VALID and 6 of 7 have the whole CI below zero. The
  mirror image of a losing short isn't a free long, because costs are paid on
  both sides: idea 010 grosses −0.058 R and pays 0.063 R of cost, so the reverse
  trade would gross about +0.058 R, roughly what its own costs would take.
- When TRAIN chooses the direction (007), it now chooses **long**.
- **Leads, none passing:** 005 (session-open range break, both sides) is
  positive on both TRAIN (+0.079) and VALID (+0.067, 390 trades) and fails only
  on CI and at ×1.5 cost (−0.002). 006 (long-only 30m EMA cross) is +0.136 on
  52 VALID trades, too few, and flat on TRAIN.
- Exp 014's corrected table was right in direction; its exact values differ
  because it kept the old TRAIN parameter choices and the 100 USDT sizing.
- Everything about costs from Exp 012 stands (`pct` stops, never compare
  gross_r, post-only).

### Verdict
`KEEP` the engine fixes and the 1,000 USDT research account. The research
direction flips: long side and both-side structures, session effects, and no
more short-only breakout variants. `PLAN.md` Round 1 is revised accordingly.
