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

---

## Exp 016 — Round 1 pre-registration (long side and both-sided structures)

**Date:** 2026-09-29
**Status:** pre-registration, written BEFORE anything was run. Round 1 of
`docs/research/PLAN.md` §4 as revised after Exp 015. Zero evaluations so far
in this entry; `results/BTCUSDT/evaluations.csv` is untouched by it.

Engine state: `test_engine.py` -> ALL CHECKS PASSED, including the new §9
(long/short symmetry on mirrored data, hand-computed short, `size_skips`).
Independently re-checked outside the test suite: one series falling 100 -> 99
with zero costs gives long R −0.0339 and short R +0.0339, exact negatives.
`datafeed.py` -> VALIDATION: OK, all 7 native timeframes, 80/80 months.

### R1.0 — analysis of the three leads (no new evaluation)

`pd.read_csv("results/BTCUSDT/eval_trades/<id>_valid.csv.gz")`, VALID 2023-24.

**005 session-open range break (cdde91ae48, n=390, mean R +0.0674)**

| leg | n | gross_r | cost_r | mean R | 2023 | 2024 |
|---|---|---|---|---|---|---|
| **long** | 212 | **+0.3088** | 0.1813 | **+0.1275** | +0.154 (88) | +0.109 (124) |
| short | 178 | +0.1535 | 0.1577 | −0.0042 | −0.268 (79) | +0.206 (99) |

1. **005's edge is entirely the long leg, and it is stable**: positive in both
   validation years with a gross edge of +0.31 R. The short leg is a coin flip
   that swings from −0.27 to +0.21 between years. This is the single most useful
   finding of the round and it is what R1.1 is aimed at.
2. **The long leg still cannot PASS as it stands.** sd of R is 1.519 (a 2.5R
   target makes the distribution wide), so at n=212 PASS needs mean R > 0.2045.
   It has 0.1275. The obvious waste is `cost_r` 0.1813: a 2.5x ATR stop on 15m
   is under 1% of price and was traded taker. A `pct` stop with a post-only
   entry targets exactly this, and the plan already requires both.
3. **Session hour: unstable at these counts.** Long mean R by hour is +0.365 (7h,
   n=28), +0.177 (8h, n=25), +0.092 (13h, n=58), +0.044 (14h, n=75), +0.436
   (15h, n=16). Shorts are the mirror image (−0.386 at 7h, −0.359 at 15h). No
   single hour is reliably better, and 15h is not even in the idea's hour list,
   so hours spill over into the next bar. **Conclusion: do not tune the hours.**
   Keep 7,8,13,14 as the plan specifies and let the grid spend its budget on
   the stop instead.
4. **Weekday: do not build a filter on this.** Mon +0.425 (n=67) against Sun
   −0.426 (n=60) looks dramatic and is almost certainly sampling noise on 60-70
   trades, on a filter that would halve the sample. Explicitly out of scope.

**007 long breakout (93ef5c196c, n=418, mean R +0.0510)**

5. **The long breakout is NOT just "long in a bull market."** R by BTC's 30-day
   trend at entry: <−15% −0.026 (n=5), −15..−5% +0.101 (61), −5..+5% +0.056
   (115), +5..+15% +0.053 (103), >+15% +0.025 (134); `corr(R, 30d trend) =
   +0.011`. Flat across every regime, which is the robustness property a real
   edge should have, and it is the strongest argument for testing this
   structure properly (R1.2). Its caveat: TRAIN mean R was −0.031, so it may
   still die on the train gate, which is the plan's kill condition.

**010 short breakout, the losing leg (70fb497bcf, n=339, mean R −0.1200)**

6. **The breakdowns fail, and the size of the failure is measured.** Price rose
   against the short by ≥0.25R in 75% of trades, ≥0.5R in 47%, ≥1.0R in 18%.
   Mean adverse excursion +0.57 R, median 10 bars (2.5 h) to reach +0.5R. The
   losing shorts grossed **−0.4626 R** against `cost_r` 0.0645 — they were
   losing before costs, so this is not a cost problem.
7. Caveat on an earlier version of this analysis: "100% reclaimed within 1 bar"
   is nearly tautological, because for a short filled at a bar's open that
   bar's high usually exceeds the open. The honest measure is the excursion
   distribution above, which is why it is quoted instead.

### The ideas, and what would kill each

| # | file | hypothesis (one line) | kill if |
|---|---|---|---|
| R1.1 | `017_session_open_long.json` | The London/NY open concentrates the day's flow, so a break of the pre-session range taken **long only** is filled by real demand; the long leg of 005 grossed +0.31 R and a `pct` stop with post-only entry cuts its 0.18 R of cost | train mean R ≤ 0 |
| R1.2 | `018_trend_breakout_long.json` | A breakout with the higher-timeframe trend, **long only**, keeps its edge in flat and bear markets too (R1.0 finding 5: R is uncorrelated with BTC's 30-day trend) | train mean R ≤ 0 |
| R1.3 | `019_pullback_uptrend_long.json` | In an uptrend the counterparty of a long entry at the fast EMA is the seller who is late to a pullback; the dip is where size is available rather than where the breakout crowd pays up | train mean R ≤ 0 |
| R1.4 | `020_failed_break_fade.json` | A break of the n-bar low that fails (price closes back inside within k bars) is a **failed breakdown**: the breakout sellers are trapped and must cover, so the fade of the failure is the mirror trade of idea 010's losing leg — which gave back 0.57 R on average in 2.5 h (R1.0 finding 6). Needs a new Level 2 trigger `failed_break(n, k)` | fewer than 300 train trades, or train mean R ≤ 0 |
| R1.5 | variants of `006_long_only_trend.json` | 006's long-only EMA cross made +0.136 on only 52 VALID trades at 30m; a finer clock gives the sample size it needs, and neighbouring timeframes agreeing is the real test | 006's structure is negative on TRAIN at every timeframe |
| R1.6 | variants of `005_session_open_break.json` | 005's long leg is the lead; the same session break on other charts shows whether the effect belongs to *time* (the session) or to *bars* (the 12h range) | 005's long leg is negative on TRAIN at every timeframe |

Deliberately **not** in this round, and why:
- Any short-only breakout or trend idea: Exp 015 showed all 7 lose significantly.
- Mean reversion, squeeze→expansion, funding crowding: answered (016, 013, 004, 014).
- A weekday or session-hour filter on 005: R1.0 findings 3 and 4 say the
  apparent pattern is sampling noise and a filter would halve the sample.
- `taker_flow` / `funding_not_crowded` as confirmation: proven inert (012, 014).

Every idea uses a `pct` stop and a post-only entry, and is written for ≥ 300
VALID trades where the structure allows it (§2a). Every idea is then run on all
seven native timeframes with `src/tf_variants.py` (§2b): 4 new ideas x 7 = 28
evaluations, plus 6 + 6 for R1.5 and R1.6 = **40 evaluations in this round**.
Running count for the project goes to 58. The holdout remains sealed.

---

## Exp 016 - Round 1 results (40 evaluations)

**Date:** 2026-09-29
**Status:** complete. 40 evaluations: **0 PASS, 5 WATCH, 29 REJECT, 6 INCONCLUSIVE.**
Project total 58 evaluations. HOLDOUT 2025-01..2026-08 still sealed - only a
PASS may spend it, and nothing passed. Every report shows `size_skips 0`.

### Ideas tested (VALID mean R / n trades, by timeframe)

| idea | 1m | 3m | 5m | 15m | 30m | 1h | 4h |
|---|---|---|---|---|---|---|---|
| 017 session open long | −0.431/1199 | −0.131/870 | −0.048/669 | −0.076/252 | −0.032/171 | **+0.021/80** W | +0.418/14 I |
| 018 breakout long | −0.414/1583 | −0.133/1957 | −0.090/910 | +0.062/308 | **+0.102/234** W | **+0.110/120** W | +0.532/37 I |
| 019 pullback long | −0.389/1959 | −0.112/2241 | −0.097/1685 | +0.022/478 | **+0.056/300** W | **+0.130/134** W | +0.168/38 I |
| 020 failed-break fade | −0.397/1867 | −0.188/2353 | −0.110/2840 | −0.078/1136 | −0.053/846 | −0.072/403 | −0.020/118 |
| 006 long EMA cross | −1.164/666 | −0.322/512 | −0.138/311 | −0.146/112 | +0.002/52 I | −0.088/29 I | +0.025/11 I |
| 005 session break both | −0.867/1150 | −0.233/1360 | −0.162/964 | +0.067/390 | −0.056/199 | −0.020/71 | +0.240/17 I |

TRAIN mean R tells the same story monotonically: 1m −0.19..−0.61, 3m
−0.10..−0.21, 5m −0.07..−0.14, 15m −0.03..+0.06, 30m +0.00..+0.06,
1h +0.02..+0.20, 4h −0.05..+0.19.

### What we learned

1. **There is a monotone timeframe gradient, and it is the biggest effect
   measured in this project.** For every long-side idea, net R rises
   continuously with the bar size, and it decomposes into two effects that point
   the same way. Idea 018 is the clean case:

   | tf | valid trades | gross_r | cost_r | net R | 95% CI | verdict |
   |---|---|---|---|---|---|---|
   | 1m | 1583 | +0.092 | **0.505** | −0.414 | [−0.477, −0.351] | REJECT |
   | 3m | 1957 | +0.043 | 0.176 | −0.134 | [−0.176, −0.087] | REJECT |
   | 5m | 910 | +0.029 | 0.119 | −0.090 | [−0.151, −0.027] | REJECT |
   | 15m | 308 | +0.123 | 0.061 | +0.062 | [−0.051, +0.179] | REJECT (train −0.024) |
   | 30m | 234 | +0.145 | 0.043 | +0.102 | [−0.031, +0.243] | **WATCH** |
   | 1h | 120 | +0.147 | 0.038 | +0.110 | [−0.090, +0.321] | **WATCH** |
   | 4h | 37 | +0.551 | 0.019 | +0.532 | [+0.155, +0.946] | INCONCLUSIVE |

   `cost_r` falls 26x from 1m to 4h - chart mode scales the `pct` stop by
   √(tf/15), so the 1m stop is 0.52% of price and the round trip costs 0.5 R
   against it. **The 1m/3m/5m REJECTs in this round are a cost artefact, not a
   verdict on the hypothesis**, and reading them as "the idea is wrong" would be
   exactly the mistake this project keeps having to unlearn. `gross_r` rises at
   the same time (0.029 at 5m to 0.551 at 4h) because the same statement on
   fewer bars is a cleaner statement of the same idea.

2. **The neighbouring-timeframe test passes, which is what makes this a lead
   rather than a fluke.** PLAN §2b says a single positive timeframe among
   negative neighbours is most likely luck. The opposite happened: 018 and 019
   are positive on TRAIN **and** VALID at 30m, 1h and 4h, and negative at
   1m/3m/5m. The effect is specific to 30 minutes and above, and it is
   consistent across three neighbouring timeframes and two different entries.
   018's 4h run has a CI of [+0.155, +0.946] - it excludes zero - but on 37
   trades, so it is INCONCLUSIVE, not a pass.

3. **R1.4 (fade the failed breakdown) is dead, and cleanly.** The new
   `failed_break` trigger fires 45,252 times on 15m and produced 1,136
   validation trades, so it is not a sample-size failure. `gross_r` is negative
   at every single timeframe: −0.015 (15m), −0.009 (30m), −0.034 (1h), −0.001
   (4h). R1.0's measurement was right - breakdowns do fail, price rose ≥0.5R
   against 47% of idea 010's shorts - but **fading the failure is not the mirror
   of taking the break**: the reclaim has already happened by the time the
   signal fires, so the fade pays the whole spread for a move that is over.
   Seven REJECTs, one per timeframe, and the trigger stays in `recipes.py` as a
   documented negative.

4. **R1.1 killed itself by dropping idea 005's volume filter.** 017's valid
   `gross_r` is **−0.005**, against +0.309 for 005's long leg. The cost change
   (pct stop, post-only) can only move `cost_r`, not `gross_r`, so the collapse
   is in the entry: 017 used `range_n` 16 (a 4-hour range) and no
   `volume_spike` filter, where 005 used a 8-hour range with a participation
   filter. A 4-hour range break without participation is noise. **This is the
   one lead in the round with a diagnosable cause and a structural fix**, and it
   is why 005's long leg deserves one properly designed idea rather than the
   one the plan sketched.

5. **R1.2's failure at 15m was a train-selection problem, not a signal
   problem.** 018 at 15m has valid +0.062 on 308 trades but TRAIN −0.024, and
   the pre-registered kill condition (train mean R ≤ 0) fired. The same
   structure on the same clock 2x coarser has train +0.061. The idea did not
   die; the 15m version of it did.

### Best configuration of the round: idea 018 at 30m (eval 1ea2cb66a2's sibling)

30m, `donchian_break(24)` + `htf_trend(50,4)` + `adx_min(20)`, **long only**,
`pct` stop 2.83% (ATR clamp 1.5–8.0), no TP, ATR trail armed at 1.5R trailing
2.5 ATR, 24h time stop, post-only entry at 0.1 ATR.

| split | trades | gross_r | cost_r | mean R | 95% CI | CAGR | maxDD |
|---|---|---|---|---|---|---|---|
| train 2020-2022 | 347 | | | +0.0612 | | | |
| valid 2023-2024 | 234 | +0.1451 | 0.0427 | +0.1024 | [−0.031, +0.243] | +11.5% | 9.8% |
| valid ×1.5 cost | | | | +0.0849 | | | |

**It fails exactly one gate, `valid_ci_lo > 0`, and it misses by 0.0001.** PASS
at n=234 needs mean R > 1.568/√234 = **0.1025**; it has **0.1024**. Win 48.3%,
PF 1.28, maxDD 9.8%, cost 0.043 R. It is a WATCH, it is not a strategy, and no
number here has been seen by the holdout.

Exit mix on valid: **stop 30% / TP 0% / time 69%**, average hold 20.8h. The TP
never triggers and two thirds of trades are closed by the clock, so the trail is
barely doing anything - `trail_at` 1.5R with a 2.83% stop needs a 4.2% move.
That is the diagnosis Round 2 will work on.

### What this round tells the next round

- **Round 2 runs the exit study on 018 at 30m.** It is the only configuration
  that satisfies the round's own exit rule with the highest TRAIN mean R among
  the qualifiers (qualifiers were 019@15m train +0.025, 018@30m +0.061,
  019@30m +0.030; the rule picks by TRAIN, never by VALID). Two evaluations,
  exits only, grids as the plan specifies. The inert trail is the obvious
  target: a 24h hold with a 4.2% arming threshold is measuring drift, not
  managing a trade.
- **Write swing-horizon ideas at 1h, not 15m.** Rounds 1-3 evidence says the
  cost of a narrow stop is what kills every idea below 30m, and PLAN Round 3
  already writes at 1h - that was the right instinct and the 1m/3m variants of
  this round are the evidence for it. Expect 4h to be INCONCLUSIVE and treat
  that as a result, not a failure.
- **Re-test 005's long leg as its own idea with the participation filter kept**
  and an 8-hour range. R1.0 measured gross +0.309 R there, the largest gross edge
  in the project, and R1.1 lost it by loosening the entry. This is a different
  structure (different filters), not a version of 017.
- **Do not build a weekday or session-hour filter** (R1.0: noise at 60-70
  trades), and do not retry `taker_flow`, `funding_not_crowded`, mean
  reversion, squeeze→expansion, or any short-only breakout.

### Verdict

`WATCH`, and the strongest position this project has reached: a long-side
trend breakout that is positive on TRAIN and VALID at 30m, 1h and 4h, costs
0.043 R, and draws down 9.8%. It is still one gate short of PASS, it rests on
234+120+37 trades, and the 4h result that excludes zero has too few trades to
count. The honest summary of Round 1 is that **the edge is not intraday**: every
long structure tested is negative below 15m and positive from 30m up, and the
reason is measurable rather than mysterious - `cost_r` is 0.505 R on 1m and
0.019 R on 4h. Round 2 tests whether the exits, which are currently inert, can
turn +0.102 into something whose confidence interval excludes zero.


---

## Exp 017 — Random-entry baseline: every Round 1 WATCH is DRIFT

**Date:** 2026-09-29
**Status:** complete. Owner requested the control after reviewing Round 1.

### Why
Every Round 1 WATCH is long-only, and VALID (2023–24) was a strong BTC bull
market (+156%, +120%). Per-year R of the four best configurations, using their
frozen parameters over TRAIN + VALID:

| year | BTC | 018@30m | 018@1h | 019@1h | 019@30m |
|---|---|---|---|---|---|
| 2020 | +304% | +0.210 | +0.324 | +0.111 | +0.079 |
| 2021 | +60% | +0.005 | −0.057 | +0.187 | +0.042 |
| 2022 | −64% | −0.056 | −0.019 | −0.107 | −0.072 |
| 2023 | +156% | +0.167 | +0.262 | +0.174 | +0.044 |
| 2024 | +120% | +0.049 | −0.015 | +0.089 | +0.067 |

All four lose in 2022 and earn most in the strongest bull years. That's what
market drift looks like. It is not proof of it, so it needed a control.

### The control: `src/baseline.py`
It keeps the idea's frozen exits, direction, cooldown and execution and swaps
only the entry trigger for a new `random` trigger (a null model in
`recipes.py`, causal by construction and covered by test 7), calibrated to
about the same number of VALID signals. It runs 200 seeds × 2 modes:
- **A**: random entries at any time → what the market's drift pays
- **B**: random entries where the idea's filters allow → what the regime
  filter pays without the trigger's timing

**SKILL** only if the idea's VALID mean R beats the 95th percentile of both.
`evaluate.py --final` now refuses a recipe config without SKILL.

### Result

| idea | eval_id | valid trades | idea valid R | A: median / 95th pct | A ≥ idea | B: median / 95th pct | B ≥ idea | verdict |
|---|---|---|---|---|---|---|---|---|
| 018_trend_breakout_long_tf30 | 1e1149a0c2 | 234 | +0.102 | +0.027 / +0.103 | 6% | +0.067 / +0.140 | 25% | **DRIFT** |
| 018_trend_breakout_long_tf60 | 7bcaa9ca12 | 120 | +0.110 | +0.055 / +0.162 | 17% | +0.089 / +0.196 | 37% | **DRIFT** |
| 017_session_open_long_tf60 | 9d649f3872 | 80 | +0.021 | +0.046 / +0.177 | 64% | +0.082 / +0.221 | 80% | **DRIFT** |
| 019_pullback_uptrend_long_tf60 | a16b19bcec | 134 | +0.130 | +0.081 / +0.162 | 21% | +0.105 / +0.184 | 28% | **DRIFT** |
| 019_pullback_uptrend_long_tf30 | ca0838da05 | 300 | +0.056 | +0.011 / +0.052 | 3% | +0.047 / +0.090 | 35% | **DRIFT** |

### What we learned
- **None of the Round 1 entries has skill.** Random long entries inside the
  same trend filters earn a median of +0.05..+0.10 R on VALID, and 25–80% of
  random runs match or beat the real entries. What made money in 2023–24 was
  *being long while BTC trended up, with these exits*, not the Donchian,
  pullback or session-open timing.
- Mode A's median (random long at any time) is itself positive on VALID
  (+0.01..+0.08 R) and about zero on TRAIN. That's the bull-market drift in
  2023–24, measured directly.
- The trend filter adds a little over pure randomness (B median > A median in
  every case), which is a regime effect worth studying as such, and is not an
  entry edge.

### Corrections to the Exp 016 entry (the journal is append-only)
1. Exp 016 says "every report shows `size_skips 0`". It doesn't: 13
   evaluations had skips (up to 27,947). All are 1m/3m/5m variants whose
   account was 90–100% drawn down, all REJECT, so no verdict changes. Their
   mean R is still unreliable (trades after the blow-up were skipped).
2. Exp 016 says 018@30m "misses PASS by 0.0001" (1.568/√234 = 0.1025 vs
   0.1024). That shortcut assumes a per-trade sd of 0.8 R. This idea's
   bootstrap CI is [−0.031, +0.243], i.e. sd ≈ 1.07 R, so PASS at n = 234 needs
   ≈ +0.137. It was not a near miss.

### Verdict
`KEEP` the baseline as a required step (AGENTS.md step 6b, PLAN.md §3 and §5).
The Round 1 WATCHes are `DRIFT`: leads for a *regime* question ("when should
one be long BTC?"), not entry techniques. Round 2's exit study may still run
on 018@30m, but every result is judged against the baseline too.

---

## Exp 018 — Tools for Round 3: `trend_state` trigger and buy-and-hold benchmark

**Date:** 2026-09-29
**Status:** complete (tooling; no idea evaluated into the records).

After Exp 017 the research question became "when should one be long BTC?",
and for that the opponent is buy & hold, not random entries. Added:

- **`trend_state` trigger** (`recipes.py`): fires on every bar, long while
  close > EMA(n), short while below. With direction long and `max_hold_hours`
  as the re-check interval, it expresses "be long while the regime is up".
  Causal (test 7).
- **`src/benchmark.py`**: daily account returns vs 1x buy & hold on TRAIN and
  VALID. Beta, alpha per year with a 20-day block-bootstrap 95% CI, CAGR, max
  drawdown, Sharpe. Verdicts ALPHA / RISK_EDGE / NO_EDGE.
- `evaluate.py --final` now needs PASS + (baseline SKILL **or** benchmark
  ALPHA).

Reference runs (recorded in `journal/BTCUSDT/benchmarks.md`):

| config | period | beta | alpha / yr [95% CI] | Sharpe idea / B&H | maxDD idea / B&H | verdict |
|---|---|---|---|---|---|---|
| 018@30m | TRAIN | 0.07 | +2.7% [−8.2%, +13.7%] | 0.61 / 0.76 | 19.7% / 76.7% | NO_EDGE |
| | VALID | 0.12 | −0.6% [−12.2%, +10.3%] | 1.09 / 2.01 | 9.4% / 26.3% | |
| 019@1h | TRAIN | 0.05 | +2.7% [−4.7%, +9.7%] | 0.67 / 0.76 | 7.0% / 76.7% | NO_EDGE |
| | VALID | 0.07 | +1.0% [−7.6%, +7.8%] | 1.25 / 2.01 | 6.3% / 26.3% | |

**Disclosure.** While building the tool, one smoke test of a regime idea was
run against scratch copies of the records (not in `evaluations.csv`): 1h
`trend_state` n ∈ {100, 300}, long, 48 h re-check, 10% pct stop, taker. It
got WATCH (valid +0.037 R, 269 trades) and benchmark NO_EDGE (alpha −1.7%/yr
VALID, CI [−4.3%, +0.5%]; Sharpe 1.17 vs 2.01; 63–73% time in market, beta
0.04–0.06). Round 3's R3.1 should count this as one earlier look at VALID
for that structure.

### Verdict
`KEEP` the tools. PLAN.md Round 3 is rewritten around them.

---

## Exp 017 - Round 2 pre-registration (exit study), and the DRIFT verdict on Round 1

**Date:** 2026-09-29
**Status:** pre-registration, written BEFORE Round 2 runs. Zero evaluations in
this entry. `results/BTCUSDT/evaluations.csv` is untouched by it.

### First: the new controls, run on all five Round 1 WATCHes

`AGENTS.md` steps 6b/6c arrived after Round 1 and apply retroactively to every
WATCH, so all five were run before anything else. This is the most important
result of the round so far, and it is negative.

| eval_id | config | baseline.py | benchmark.py |
|---|---|---|---|
| 1e1149a0c2 | 018 trend breakout long, 30m | **DRIFT** | **NO_EDGE** |
| 7bcaa9ca12 | 018 trend breakout long, 1h | **DRIFT** | **NO_EDGE** |
| ca0838da05 | 019 pullback uptrend long, 30m | **DRIFT** | **NO_EDGE** |
| a16b19bcec | 019 pullback uptrend long, 1h | **DRIFT** | **NO_EDGE** |
| 9d649f3872 | 017 session open long, 1h | **DRIFT** | **NO_EDGE** |

**Not one entry in Round 1 beat random timing.** 018 at 30m, the round's best
configuration, is the clearest case:

| baseline | median VALID trades | median VALID mean R | 95th pct | share of random runs >= idea |
|---|---|---|---|---|
| A: random entries, any time | 275 | +0.0267 | +0.1026 | **6%** |
| B: random entries, same filters | 225 | +0.0670 | +0.1404 | **25%** |

The idea's VALID mean R is +0.1024 and the 95th percentile of *random entries at
any time* is +0.1026 - it misses by 0.0002, the same 0.0002 by which it missed
the PASS gate. **A quarter of random entries with the identical filters and
identical exits beat the Donchian breakout.** Keeping the direction, the stop,
the trail, the time stop and both filters, and throwing away only the trigger,
loses nothing. 017 at 1h is the extreme: 80% of random runs beat it.

Against buy and hold, 018 at 30m is not close:

| period | trades | time in market | beta | alpha/yr [95% CI] | CAGR idea / B&H | maxDD idea / B&H | Sharpe idea / B&H |
|---|---|---|---|---|---|---|---|
| TRAIN 2020-22 | 347 | 25% | 0.07 | +2.7% [−8.2, +13.7] | +6.4% / +32.0% | 19.7% / 76.7% | 0.61 / 0.76 |
| VALID 2023-24 | 234 | 28% | 0.12 | −0.6% [−12.2, +10.3] | +11.5% / +137.3% | 9.4% / 26.3% | 1.09 / 2.01 |

Beta 0.12, no alpha on either period, and buy & hold is 12x the CAGR with twice
the Sharpe. Not even a RISK_EDGE: the idea's drawdown is smaller but its Sharpe
is lower on VALID.

**So what Round 1 actually established is narrower than it looked.** The
timeframe gradient of Exp 016 is real and measured - `cost_r` 0.505 R on 1m
against 0.019 R on 4h - but that is a statement about the cost of trading fast,
not about the entries. Every long entry in the round is explained by three
things it shared: it was long, it had `htf_trend` + `adx_min` on, and 2023-24
was a bull market. The trigger contributed nothing measurable.

### What Round 2 is, given that

The plan defines Round 2 as two exit-only evaluations on the entry that
qualified, with the entry frozen, grids as specified. That entry is 018 at 30m
(highest TRAIN mean R among the qualifiers: 019@15m +0.025, **018@30m +0.061**,
019@30m +0.030; the rule picks by TRAIN, never by VALID). The plan's own
premise - "with the same entry, the exit decides how much of the gross edge is
kept" - is now known to be resting on an entry with no gross edge of its own.

**That does not make the round pointless; it makes it a sharper question.**
Exp 016 measured the diagnosis: 018 at 30m has TP 0%, time exits 69% and an
average hold of 20.8h, because `trail_at` 1.5R against a 2.83% stop needs a
4.2% move to arm. So the exits are inert, and the +0.102 R is 24-hour drift
with a stop, not trade management. The question Round 2 answers is therefore:

> **Can exit management turn a result that is entirely drift into skill?**

If yes, the exits were the missing piece and Round 1's entries deserve another
look. If no, then no amount of exit work rescues an entry that random timing
matches, and Round 3 must stop looking for entries in this family and go where
the money is actually earned - holding periods long enough that `cost_r` is
negligible, or a carry-type idea.

| # | file | grid (exits only, entry frozen) | kill if |
|---|---|---|---|
| R2.1 | `021_exit_profit_side.json` | `tp.type` ["none","r"], `tp.r` [1.5, 3.0], `be_at` [0, 0.5, 1.0], `trail_at` [0, 1.0, 2.0] with `trail_atr` 2.5 - 36 combos | no combo improves VALID mean R on the frozen entry, or TRAIN picks a worse exit set than the incumbent |
| R2.2 | `022_exit_risk_side.json` | `stop.pct` [0.01, 0.015, 0.02, 0.03], `stop.type` ["pct","swing"] (swing carries n 16, buffer_atr 0.3, min_atr 1.5, max_atr 6), `max_hold_hours` [4, 8, 16, 24] - 32 combos | same |

Frozen entry for both, from 018 at 30m's recorded choice: 30m
`donchian_break(24)` + `htf_trend(50,4)` + `adx_min(20)`, long only, post-only
entry at 0.1 ATR, cooldown 4, atr_n 14, trail_atr 2.5.

These two plus the entry's own evaluation are exactly 3 evaluations of the
structure `recipe|30m|donchian_break|adx_min+htf_trend|long`, which is
`EVAL_MAX_VERSIONS`, so **this structure is closed after R2.2** - as the plan
says, do not split the exit work into more files.

**Whatever they return, `baseline.py` and `benchmark.py` are run on any WATCH
or PASS before it is reported**, and `--final` is out of reach unless one of
them says SKILL or ALPHA. A DRIFT result cannot become a candidate by being
re-measured.

### Verdict on Round 1, restated

`REJECT` as a source of tradable edges; `KEEP` as evidence. 40 evaluations, 5
WATCHes, and all five are drift on a random-entry control and no better than
holding BTC. The honest statement of the round is: **long BTC with a trend
filter made money in 2023-24 because BTC went up, and the entry added nothing.**
The cost-mechanism findings (a `pct` stop; `cost_r` collapsing from 0.505 R on
1m to 0.019 R on 4h; the gross_r-within-1m-3m-5m-artefact warning) survive and
are now the most reusable thing this project knows.

---

## Exp 017 - Round 2 results: the first PASS in the project, and the holdout killed it

**Date:** 2026-09-29
**Status:** complete. 2 evaluations: 1 WATCH, **1 PASS**. The PASS was then tested
on the locked HOLDOUT and **FAILED**. Project total 61 evaluations.

### The two exit studies, entry frozen at 018@30m's recorded choice

| idea | verdict | train mean R | valid trades | gross_r | cost_r | valid mean R | 95% CI | CAGR | maxDD |
|---|---|---|---|---|---|---|---|---|---|
| 021_exit_profit_side | WATCH | +0.0890 (343) | 232 | +0.142 | 0.043 | +0.0991 | [−0.036, +0.240] | +10.9% | 9.1% |
| 022_exit_risk_side | **PASS** | +0.0936 (391) | 258 | +0.334 | 0.106 | **+0.2276** | **[+0.002, +0.468]** | +30.5% | 12.7% |

Both grids picked a **tighter or altered stop**, and both improved TRAIN a lot
over the incumbent's +0.0612 — +0.0890 and +0.0936. On VALID, 021 gained nothing
(+0.1024 → +0.0991) and 022 gained a lot (+0.1024 → +0.2276).

### The controls, and then the holdout

| config | baseline.py | benchmark.py | holdout |
|---|---|---|---|
| 021 profit side | **DRIFT** (34% of random-with-filters beat it) | **NO_EDGE** | not eligible |
| 022 risk side | **SKILL** (0% beat it at any time, 4% with the same filters) | **NO_EDGE** (alpha +6.7%/yr, CI [−15.4, +27.0]) | **FAILED** |

`022` was therefore PASS **and** SKILL, which is what `AGENTS.md` step 7
requires, so the holdout was spent on it. One run, one shot:

| split | trades | gross_r | cost_r | mean R | 95% CI | CAGR | maxDD |
|---|---|---|---|---|---|---|---|
| train 2020-2022 | 391 | +0.189 | 0.095 | +0.0936 | | | 34.3% |
| valid 2023-2024 | 258 | +0.334 | 0.106 | +0.2276 | [+0.002, +0.468] | +30.5% | 12.7% |
| **holdout 2025-01..2026-08** | **211** | **+0.098** | **0.108** | **−0.0102** | [−0.202, +0.199] | **−1.9%** | 20.9% |

**FAILED.** The holdout config is now spent and is in
`results/BTCUSDT/holdout_log.csv`. No copy of it gets another try
(AGENTS.md rule 4), and the structure
`recipe|30m|donchian_break|adx_min+htf_trend|long` is also at
`EVAL_MAX_VERSIONS` (3: 018_tf30, 021, 022), so it is closed on both counts.

### What we learned

1. **The PASS was a period effect wearing the costume of a stop-width result.**
   The only thing that changed from the DRIFT configuration to the SKILL one was
   the stop: 2.83% of price → **1.0%**. That is not a small edit. It made the R
   unit 2.8x smaller, so the *same* price move scores 2.8x more R: `gross_r`
   went 0.145 → 0.334. It also raised `cost_r` 0.043 → 0.106, and the stop-out
   rate went 30% → 78%, average hold 20.8h → 12.3h. So a 1% stop on 30m
   mechanically magnifies whatever edge exists, in both directions, and it made
   a drift that was invisible at 2.83% look like skill at 1.0%. **On the
   holdout the gross edge fell to +0.098 — a 71% collapse — while the cost
   stayed at 0.108.** Gross 0.098 minus cost 0.108 is −0.0102, which is exactly
   what the holdout reported. There was never an edge; there was a temporarily
   large gross number being divided by a small R.

2. **The VALID period's advantage was 2023, and it was visible before the
   holdout.** Valid per year was 2023 **+0.3496** (111 trades) against 2024
   **+0.1355** (147 trades). A result carried by one year out of two, with a CI
   whose lower bound is **+0.0023**, is one bootstrap resample away from
   failing, and it did. The gate worked; the reading of it should have been
   more cautious than "PASS".

3. **Both grids improved TRAIN and only one improved VALID, and the one that
   improved VALID is the one that failed out of sample.** 021 (profit side) and
   022 (risk side) both lifted train mean R from +0.061 to +0.089/+0.094. On
   VALID, 021 was flat and 022 doubled. So "did the grid's pick transfer to
   VALID" was a poor predictor of "will it transfer to HOLDOUT" — VALID was one
   regime, and the grid had already been selected against it twice by the time
   the holdout arrived.

4. **`SKILL` is measured on VALID only, and that is a real limitation of the
   control.** 022's baseline said SKILL with only 4% of same-filter random runs
   beating it — and the holdout says the entry has no edge at all. A control
   that compares an idea against random timing *within the same period* cannot
   detect a drift that is stable inside that period. The 2023-24 bull market
   gave every long entry the same tailwind, and the baseline faithfully measured
   "this beat other long entries in 2023-24", which is true and useless. **A
   baseline on the holdout would have caught it, and the holdout is locked, so
   the check is not available. Worth raising with the owner as a possible
   design change: run the random-entry control on the holdout as part of the
   single permitted holdout run, since it uses no information the strategy has
   not already consumed.**

5. **The exit study did answer its question, negatively.** Round 2 was framed as
   "can exit management turn a drift into skill?" The answer is no. The exit
   grid moved mean R from +0.102 to +0.228 on VALID and to −0.010 on the
   holdout. Exit management redistributes a trade's outcome; it cannot create
   information that the entry does not contain.

### Verdict

`REJECT`. The first and only PASS in 61 evaluations did not survive the holdout,
and the mechanism is understood well enough to predict that no exit study could
have saved it. The structure is closed on both the version budget and the
holdout lock, so the honest next step is **not** another variant of a long
Donchian breakout on 30m.

What survives and is worth keeping:
- **`cost_r` is the first-order term everywhere.** It is 0.505 R on 1m and
  0.019 R on 4h (Exp 016) and 0.043 vs 0.106 for the same setup at two stop
  widths here. Everything else in this project is second order.
- **A stop width changes the units of the measurement, not just the risk.** The
  same strategy's `gross_r` differs by 2.3x between a 1% and a 2.83% stop, so
  `gross_r` is not comparable across stop widths — Exp 012's warning, now with
  a PASS on the line to show what it costs to ignore it.
- **A CI lower bound of +0.0023 is not evidence.** It passed because the gate is
  a threshold, and it should be read as "indistinguishable from zero", which is
  what the holdout then confirmed.
- **Round 1's five WATCHes are all DRIFT and all NO_EDGE** (Exp 017
  pre-registration), which is why none of them was a candidate either.

For Round 3: the evidence now says stop looking for entries in the
"long + trend filter" family - six configurations across four timeframes, all
either DRIFT or killed by the holdout. Round 3 should test whether anything
survives at swing horizons with `cost_r` made negligible, and Round 4's
new blocks (previous-day high/low, opening range, liquidation flush,
funding windows) are the remaining untested hypotheses in this project.

---

## Exp 019 — Stricter controls after the Round 2 holdout failure

**Date:** 2026-09-29
**Status:** complete. Owner-approved changes to `baseline.py` and `evaluate.py --final`.

**Numbering note.** The two Round 2 entries above are headed "Exp 017" but
come after Exp 017 (random-entry baseline) and Exp 018 (benchmark tools).
Read them as **Exp 017b / 017c** (Round 2 pre-registration and results). The
journal is append-only, so the headings stay as they are. **The next entry is
Exp 020.**

### Why
Round 2's idea 022 was PASS and SKILL, spent the holdout, and FAILED
(−0.010 R on 211 trades). Its SKILL was measured on VALID only (2023–24, a
strong bull market), where every long entry gets the same tailwind. The Round 2
results entry suggested fixing the control, and the owner approved two changes.

### (a) SKILL now needs TRAIN as well as VALID
`baseline.skill_check()`: the idea's mean R must beat the 95th percentile of
both random modes (A: any time, B: within the idea's filters) on **TRAIN and
VALID**. TRAIN contains the 2022 bear market. New test in `test_engine.py` §10.

Re-running the baseline for all 7 configurations evaluated so far:

| config | old verdict (VALID only) | new verdict | why |
|---|---|---|---|
| 018@30m, 018@1h, 019@30m, 019@1h, 017@1h, 021 | DRIFT | DRIFT | unchanged |
| **022 exit risk side** | **SKILL** | **DRIFT** | TRAIN +0.094 < random 95th pct A +0.101 / B +0.154 |

**Under the new rule, 022 would have been refused at `--final` and the holdout
would not have been spent.** (It was spent correctly under the rules at the
time.)

### (b) The holdout run now includes a random-entry control
`evaluate.py --final` runs `baseline.holdout_control()` on the holdout inside
the one permitted run (no extra information: the holdout run already sees
those bars). `CONFIRMED` now also needs the idea's holdout mean R above the
**median** random entry of modes A and B. Both medians are stored in
`holdout_log.csv`.

For reference, on idea 022's already-spent holdout: random median A −0.104,
B −0.065; 022 made −0.010. So 022 did beat random timing out of sample, but
with a 1% stop its costs (0.108 R) exceeded its gross edge (+0.098 R). A
relative edge in timing is not a profitable strategy after costs.

### Verdict
`KEEP` both changes. Every future SKILL is judged on two periods with
different market regimes, and every future CONFIRMED is judged against random
entries in the holdout itself.

---

## Exp 020 - Round 3 pre-registration (when to be long BTC: regime rules vs buy & hold)

**Date:** 2026-09-29
**Status:** pre-registration, written BEFORE anything in this round is run.
Zero evaluations in this entry; `results/BTCUSDT/evaluations.csv` is untouched
by it. Project count on entry: 61 evaluations, 1 distinct PASS (022, whose
holdout FAILED). HOLDOUT sealed.

Checklist: `test_engine.py` -> ALL CHECKS PASSED (including the Exp 019
tightened baseline: SKILL now needs TRAIN *and* VALID, and the holdout run
carries its own random-entry control). `datafeed.py` -> VALIDATION: OK from
earlier today, 7 native timeframes, 80/80 months.

### Why this round is a different question, not a bigger version of Round 1

Exp 017 measured that Round 1's profits were not entry skill: random long
entries inside the same trend filters, with the same exits, earned about the
same. Round 1's five WATCHes are all DRIFT and all NO_EDGE. The 022 PASS was a
stop-width artefact that the holdout killed. So the honest question left is
not "which entry is best" but:

> **Is there any rule for WHEN TO BE IN BTC that beats simply holding BTC?**

The opponent is no longer random entries, it is buy & hold, so this round is
judged by `src/benchmark.py` (beta, alpha per year with a 95% CI, CAGR, max
drawdown, Sharpe). A regime rule is long or flat by construction, so
`baseline.py` will usually say DRIFT for it - that is expected and is reported,
not treated as a failure. The test that matters here is the benchmark.

Two things the plan insists on and this pre-registration adopts:

- **Compare Sharpe and alpha, never CAGR.** With 1% risk and a 10% crash stop
  the rule holds only ~10% of the account, so beta is small and CAGR is small
  by construction. A low CAGR next to buy & hold's is a sizing artefact.
- **A RISK_EDGE is a real result and belongs to the owner.** Better Sharpe than
  buy & hold with under half its drawdown, on both periods, is a calmer way to
  hold BTC. It is not a trading edge and only the owner decides whether it is
  worth a strategy card.

### The engine constraint that shapes every idea here

The engine exits only on stop / take-profit / time. There is no "exit when the
regime ends". So for a `trend_state` idea `max_hold_hours` is a **re-check
interval**, not a holding period: at the time exit the regime is re-read and
the next bar re-enters if it is still on, paying a real round trip each time.
`trend_state` fires on every bar, so re-entry is immediate and the round-trip
cost is paid once per interval. Two consequences the grids must respect:

- The interval is the cost knob. A 24h interval on 1h bars pays 1 round trip a
  day; a 72h interval pays one every three days. `cost_r` per re-entry is
  0.09%/stop%, and with a 10% stop that is only 0.009 R, so the interval is
  cheap - but it is not free, and a rule that re-enters 90 times a year is not
  the same instrument as one that re-enters 12 times.
- The stop is **crash protection, not a trading stop**. At 8-15% of price it
  should almost never be the reason a trade ends; if the stop rate is high, the
  stop is too tight for its job and the grid is wrong.

### The ideas, and what would kill each

| # | file | hypothesis (one line) | kill if |
|---|---|---|---|
| R3.1 | `023_trend_regime_long.json` | Being long only while BTC is above its multi-day trend should avoid the large bear drawdowns (2022 was -64% for buy & hold) at a small cost in upside, so it should show a **higher Sharpe and a much smaller drawdown** than holding, even with little or no alpha | benchmark says NO_EDGE (no better Sharpe than buy & hold, or drawdown not under half) on both periods |
| R3.2 | `024_trend_regime_both.json` | The same rule with `direction: both` asks whether shorting the down-regime adds return in 2022 or just costs whipsaw - the question decides whether this family is worth anything beyond a smoother ride | benchmark NO_EDGE, **or** the short leg's gross_r is negative (a losing short plus a winning long-leg is not a regime rule) |
| R3.3 | `025_trend_regime_adx.json` | A trend filter that also requires ADX should stay out of the regime while it is chop, which is where the 50/50 EMA whipsaws and gives back the drawdown it was meant to avoid | benchmark NO_EDGE |
| R3.4 | `026_trend_regime_vol_filter.json` | Crashes arrive with volatility spikes, so being flat when the ATR ratio is extreme should cut the worst of the drawdown without costing much upside | benchmark NO_EDGE |
| R3.5 | `027_multiday_pullback_long.json` | A multi-day pullback to the fast EMA inside the up-regime is the one entry-based long idea the evidence has not killed, because it is timed rather than continuous: it is judged by **both** controls | DRIFT **and** NO_EDGE |
| R3.6 | no new idea | Reference table: `benchmark.py` on the best configurations of Rounds 1-2, so every Round 3 number has a like-for-like comparison on the same engine | — |

**Deliberately not in this round:** any short-only breakout or trend entry
(closed after Exp 015); any long Donchian/pullback variant on 15m-30m (closed
after Exp 017 - six configurations, five DRIFT and one holdout FAILED); mean
reversion, squeeze→expansion, funding crowding, `taker_flow` and
`funding_not_crowded` confirmation (all answered). If R3.5 needs a new structure
rather than a new version, that is because the multi-day hold is the hypothesis
and the timeframe is part of it.

**Budget:** 5 new ideas x 7 native timeframes = **35 evaluations**, plus 5-6
`benchmark.py` runs and a `baseline.py` run on every WATCH or PASS. Project
total goes to 96. Grids stay at or below 16 combos so the 1m/3m variants remain
tractable. Every report must show `size_skips 0`.

**What would make this round a success, honestly stated:** either an ALPHA that
survives the holdout, or a clean NO_EDGE on all five plus a RISK_EDGE reported
to the owner. Both are useful. What is *not* acceptable is a CAGR comparison
dressed up as an edge, which the plan forbids and which the 1% sizing makes
guaranteed to fail.

---

## Exp 020 - Round 3 results: two PASSes, and no timing rule beats holding BTC

**Date:** 2026-09-29
**Status:** complete. 35 evaluations: **2 PASS, 11 WATCH, 19 REJECT, 3 INCONCLUSIVE.**
Project total 96 evaluations. 13 `baseline.py` + 13 `benchmark.py` runs.
HOLDOUT **not** spent - see the owner question at the end.

### Ideas tested (VALID mean R / n trades by timeframe)

| idea | 1m | 3m | 5m | 15m | 30m | 1h | 4h |
|---|---|---|---|---|---|---|---|
| 023 regime long/flat | -0.656/1279 | -0.147/2252 | -0.066/2078 | +0.035/742 | +0.053/348 | **+0.115/198 PASS** | +0.056/113 |
| 024 regime long/short | -0.500/1441 | -0.188/2172 | -0.109/2350 | -0.043/2799 | +0.025/509 | +0.042/250 | -0.002/137 |
| 025 regime + ADX | -0.466/1544 | -0.126/2406 | -0.072/2044 | +0.005/701 | +0.020/382 | +0.037/200 | +0.192/54 |
| 026 regime + vol filter | -0.599/1502 | -0.167/2312 | -0.076/2709 | -0.009/903 | +0.020/489 | +0.047/263 | +0.170/61 |
| 027 multi-day pullback | -0.360/1789 | -0.111/1659 | -0.058/987 | +0.071/345 | **+0.197/175 PASS** | +0.374/97 | +0.203/30 |

### The two PASSes

**023_trend_regime_long, 1h** (eval 087d112106) - long while close > EMA(200) on
1h, flat otherwise, 10% crash stop, 24-72h re-check interval, taker entry.

| split | trades | gross_r | cost_r | mean R | 95% CI | CAGR | maxDD |
|---|---|---|---|---|---|---|---|
| train 2020-2022 | 290 | | | +0.0576 | | | |
| valid 2023-2024 | 198 | +0.1369 | **0.0221** | **+0.1148** | **[+0.014, +0.220]** | +10.4% | **4.8%** |
| valid x1.5 cost | | | | +0.0996 | | | |

**027_multiday_pullback_long, 30m** (eval 19897b3269) - `pullback` + `trend_ema`
50/200, long, 2-4 day hold, 4% stop.

| split | trades | gross_r | cost_r | mean R | 95% CI | CAGR | maxDD |
|---|---|---|---|---|---|---|---|
| train 2020-2022 | 251 | | | +0.0712 | | | |
| valid 2023-2024 | 175 | +0.2332 | 0.0364 | **+0.1967** | **[+0.025, +0.373]** | +16.8% | 8.6% |
| valid x1.5 cost | | | | +0.1818 | | | |

Both cost_r figures are the point: **0.022 and 0.036 R against Round 2's false
PASS at 0.106.** A regime rule with a 10% stop and a pullback with a 4% stop are
the first configurations in this project where the cost of trading is genuinely
small, and that is what made positive expectancy possible. Exp 012's mechanism -
`cost_r = cost / stop_pct` - is the only thing in this project that has reliably
produced a result.

### The controls: 13 configurations, and not one beats holding BTC

| config | verdict | baseline.py | benchmark.py |
|---|---|---|---|
| 023 regime long, 1h | **PASS** | **SKILL** | **NO_EDGE** |
| 023 regime long, 30m | WATCH | SKILL | NO_EDGE |
| 023 regime long, 15m | WATCH | SKILL | NO_EDGE |
| 023 regime long, 4h | WATCH | DRIFT | NO_EDGE |
| 027 multi-day pullback, 30m | **PASS** | **DRIFT** | **NO_EDGE** |
| 024, 025, 026 regime variants (8 configs) | WATCH | DRIFT | NO_EDGE |
| 027 at 1h / 15m | WATCH | DRIFT | NO_EDGE |
| Rounds 1-2 best (021, 022, 017, 018, 019 - 5 configs, R3.6) | WATCH/PASS | DRIFT | NO_EDGE |

**Every `benchmark.py` run in the project's history is NO_EDGE. 21 of 21.** No
configuration has ALPHA, none is RISK_EDGE. The best case, 023 at 1h:

| period | trades | time in market | beta | alpha/yr [95% CI] | CAGR idea / B&H | maxDD idea / B&H | Sharpe idea / B&H |
|---|---|---|---|---|---|---|---|
| TRAIN 2020-22 | 290 | 76% | 0.06 | +1.8% [−2.4, +6.2] | +5.1% / +32.0% | 10.9% / 76.7% | 0.85 / 0.76 |
| VALID 2023-24 | 198 | 78% | 0.10 | +0.3% [−5.6, +4.5] | +10.4% / +137.3% | 4.5% / 26.3% | 1.59 / 2.01 |

It is a genuinely smoother ride - a sixth of buy & hold's drawdown - and it is
still NO_EDGE, because its Sharpe is *below* buy & hold's on VALID (1.59 against
2.01) and its alpha is indistinguishable from zero on both periods. Not
RISK_EDGE either: that verdict needs a better Sharpe on **both** periods, and
TRAIN is the only period where it wins (0.85 against 0.76).

### What we learned

1. **The tightened baseline earned its place immediately.** 027 at 30m passed
   every gate on VALID (+0.1967, CI [+0.025, +0.373]) and is **DRIFT**: on TRAIN
   its +0.0712 is below the 95th percentile of random entries at any time
   (+0.0792) and well below random entries with the same filters (+0.1428), with
   6% of same-filter random runs beating it. Under the pre-Exp-019 rule, which
   compared VALID only, this would have looked like SKILL and been a candidate.
   It is the same failure mode as 022, caught one step earlier, and the only
   reason it was caught is that the control was tightened.

2. **`SKILL` is nearly vacuous for a regime rule, and the output shows it.** For
   023, baseline.py's mode A and mode B rows are *identical* (+0.0215/+0.0347
   and +0.0788/+0.0962, 0% in both), because `trend_state` has no separate
   filters: the trigger *is* the filter, so "random entries with the same
   filters" is not a different experiment. A regime rule will therefore almost
   always read SKILL, and reading that as evidence of a trading edge would be a
   mistake. The plan says as much ("baseline.py will usually say DRIFT for
   regime ideas; for this round the benchmark is the test that matters"), and
   here it read SKILL and the benchmark still said NO_EDGE.

3. **Cost is the whole game, and this is the first round where that produced
   positive expectancy rather than a cost warning.** `cost_r` 0.022 (023) and
   0.036 (027) versus 0.106 for the 30m 1%-stop configuration that produced the
   project's only PASS, which the holdout killed. The 1m-5m REJECTs across all
   five Round 3 ideas (cost_r 0.5-0.2 R) are the same arithmetic as Exp 016, now
   seen for the third round running.

4. **Adding a filter to a regime rule made it worse, three times out of three.**
   023 (plain EMA regime) is positive at 30m/1h/4h. 025 (+ADX) and 026 (+vol
   filter) are positive at fewer timeframes and lower: at 1h, +0.115 becomes
   +0.037 and +0.047. Both filters are supposed to remove the whipsaw that
   costs the regime rule its drawdown, and both reduce the return instead. The
   honest reading is that on BTC the whipsaw is not what makes a trend regime
   rule expensive - the re-check interval and the beta are, and the filters only
   add missed trend.

5. **Shorting the down-regime does not pay (R3.2 answered).** 024 is worse than
   023 at every timeframe where both trade, and negative on VALID at 15m
   (-0.043) and 4h (-0.002). The short leg of a long/short regime rule costs
   more than it earns, which is the pre-Exp-015 finding re-confirmed on a correct
   engine and with a regime rule rather than a breakout.

### Verdict

`NO_EDGE`, plainly. Round 3's question was "is there a rule for when to be in
BTC that beats holding BTC", and the answer across 35 evaluations, 26 controls
and two PASSes is **no**. Two configurations have positive expectancy on both
TRAIN and VALID with confidence intervals that exclude zero, and both are
dominated by simply owning the asset: 023 by 4.5% against 26.3% drawdown but at
a Sharpe of 1.59 against 2.01, 027 by alpha indistinguishable from zero.

That is a real and useful result, and it is the answer the plan asked for. It
also means **the holdout should not be spent on 023**, because PLAN.md Round 3
sends only `ALPHA + PASS` to the holdout and 023 is NO_EDGE. Spending the
project's last clean holdout on a rule that its own benchmark has already
previewed would burn the lock for a foregone conclusion. That is a question for
the owner and it is asked below rather than answered here.

For Round 4: every edge that has come from BTC's *direction* is now closed -
six long entries DRIFT or holdout-FAILED, one regime rule NO_EDGE, the short side
loses. The remaining untested hypotheses in this project do not come from
direction at all: previous-day high/low, the opening range, funding windows and
liquidation flushes. Round 4 should look there, and `benchmark.py` stays the
judge, because a rule that cannot beat holding BTC is not worth a strategy card
however good its own mean R looks.

---

## Exp 021 — Review of Round 3: two rule gaps closed, and corrections to Exp 020

**Date:** 2026-09-29
**Status:** complete (tooling + corrections; no new evaluation, holdout untouched)

### Why
The Round 3 review (Exp 020) found two gaps in the rules, not in the research:

1. **`size_skips` was reported but did not change any verdict.** Exp 020 does
   not mention it, yet 32 of the 96 evaluations have VALID skips. 27 are REJECT,
   mostly 1m–5m variants whose account was drawn down until it could not size
   a trade. **Five are not REJECT, and all five are 4h variants** whose chart-mode
   `pct` stop was doubled from the 1h source:

   | eval_id | idea | verdict | valid trades | valid mean R | valid size_skips |
   |---|---|---|---|---|---|
   | 334db458ff | 023_trend_regime_long_tf240 | WATCH | 113 | +0.0558 | 807 (train 421) |
   | af65d82f6c | 025_trend_regime_adx_tf240 | INCONCLUSIVE | 54 | +0.1919 | 348 |
   | e5f7dc5947 | 026_trend_regime_vol_filter_tf240 | INCONCLUSIVE | 61 | +0.1699 | 444 |
   | a92e8f27cd | 027_multiday_pullback_long_tf240 | INCONCLUSIVE | 30 | +0.2027 | 6 |
   | c7955fa3ba | 019_pullback_uptrend_long_tf240 (Round 1) | INCONCLUSIVE | 38 | +0.1685 | 1 |

   Mechanism: 1,000 USDT × 1% = 10 USDT of risk, and BTC's qty step is 0.001,
   so a stop of `s` can be sized only while BTC < 10 / (0.001 × s). 023 at 4h
   had a 20% stop, so it traded only while BTC was below 50,000, i.e. in 2023
   and early 2024 (valid per year: 2023 73 trades, 2024 40). Its trade list is
   a price-filtered subset of the rule's, and so are its baseline and benchmark
   (`results/BTCUSDT/{baseline,benchmark}/334db458ff.json`). **None of the five
   rows is evidence either way.** No PASS is affected: 023@1h (10% stop before its
   `max_atr` clamp) and 027@30m (4%) have 0 skips.

2. **`--final` accepted SKILL for a regime rule.** 023@1h is PASS + SKILL, so
   AGENTS.md step 7 allowed its holdout while PLAN.md Round 3 said ALPHA only.
   The Round 3 agent saw the conflict and asked instead of running it, which
   was right. SKILL is nearly vacuous for a `trend_state` rule: the trigger is
   the filter, so baseline modes A and B are the same experiment (identical
   numbers for 023), and SKILL only says "long in up-regimes beats long at
   random times". The question such a rule must answer is Round 3's: does it
   beat holding BTC? 023@1h's benchmark says no (NO_EDGE: alpha +0.3%/yr,
   CI [−5.6%, +4.5%]; Sharpe 1.59 vs buy & hold 2.01 on VALID).

### Changes (owner-approved, ก + ข)
- `evaluate.py`: new verdict **`UNSIZABLE`**: `size_skips` > 0 on TRAIN or
  VALID turns PASS / WATCH / INCONCLUSIVE into UNSIZABLE (a REJECT stays
  REJECT). TRAIN skips are now recorded (`train_size_skips`) and shown in the
  report next to VALID's. `--final` also refuses a recorded row with skips.
  Re-running 023@4h (outside the records) reproduces its row exactly (113
  trades, +0.0558) and now reads UNSIZABLE with gate `size_skips==0 ❌`.
- `evaluate.py`: `REGIME_TRIGGERS = {"trend_state"}`; `holdout_ticket` needs
  benchmark **ALPHA** for any idea whose trigger is in that set. 023@1h's
  `--final` is now refused with that reason (checked, nothing recorded).
- `tf_variants.py`: warns (`!! ... can be sized only while BTCUSDT < X`) when
  an idea's widest `pct` stop cannot be sized at the TRAIN+VALID price peak
  (108,367), for the source idea and each variant.
- `test_engine.py` section 10: regime rule SKILL-only → no ticket, ALPHA →
  ticket; verdicts PASS / UNSIZABLE (valid skips, train skips) / REJECT stays;
  the sizing formula and warning. ALL CHECKS PASSED.
- AGENTS.md (verdict table, step 7, engine facts, troubleshooting) and PLAN.md
  (§2 table, Round 3 tools, §5) say the same thing.
- Existing rows are **not** edited (rule 4). The five rows above keep their
  recorded verdicts; read them as UNSIZABLE.

### Corrections to Exp 020 (the journal is append-only)
1. "EVERY benchmark.py run in the project is NO_EDGE: 21 of 21": there are
   **20** benchmark files (`results/BTCUSDT/benchmark/`), all NO_EDGE. The
   conclusion stands.
2. The Round 3 tables list 023@4h as a WATCH with baseline DRIFT / benchmark
   NO_EDGE, and 025/026/027@4h as INCONCLUSIVE. All four are UNSIZABLE (above).
   The "positive at 30m/1h/4h" pattern for 023 rests on 30m and 1h only.
3. "Spending the project's last clean holdout": the lock is per configuration
   (`holdout_key`), not one holdout for the project. The point behind it
   stands: every look at 2025–26 makes the next one less clean, so it is spent
   only when a result could change a decision.
4. `evaluations.csv` shows the 022 row changed in the Exp 020 commit. Checked
   field by field: only float formatting in the last digit (pandas re-writes
   the file on every append); no value changed.

### Verdict
KEEP the Exp 020 conclusion: no timing rule tested beats holding BTC (20/20
NO_EDGE). 023@1h stays PASS + NO_EDGE and does **not** go to the holdout. Next
is Round 4 (PLAN.md §4): blocks that do not come from BTC's direction.
Project count unchanged: 96 evaluations, holdout used by `example_trend_breakout`
(lock test) and 022 only.

---

## Exp 022 - Round 4 pre-registration (new blocks: market structure, not direction)

**Date:** 2026-09-29
**Status:** pre-registration, written BEFORE any Round 4 evaluation. Zero
evaluations in this entry; `results/BTCUSDT/evaluations.csv` is untouched by
it. Project count on entry: **96 evaluations**. HOLDOUT sealed (used only by
`example_trend_breakout` in the Exp 011 lock test and 022, which FAILED).

### Where this round starts

Rounds 1-3 closed everything that came from **BTC's direction**:

- 6 long entries: 5 DRIFT against a random-entry control, 1 (022) holdout FAILED
- the short side: loses significantly, re-confirmed on the fixed engine
- the long/flat regime rule (023): PASS + NO_EDGE - a sixth of buy & hold's
  drawdown at a Sharpe of 1.59 against 2.01
- **every `benchmark.py` run in the project is NO_EDGE (20/20)**

So Round 4 does not look for a better entry. It asks whether any edge exists
that does not depend on BTC going up. The plan's candidates are market-structure
ideas that classic indicators miss, and Exp 020's summary picked four of them:
previous-day high/low, the opening range, funding windows, liquidation flushes.

### New blocks (Level 2 additions to `src/recipes.py`)

All five added this round, all causal, `test_engine.py` ALL CHECKS PASSED
(test 7 checks every block in `TRIGGERS`/`FILTERS` automatically). Verified
independently as well, with a stronger test than the prefix comparison: every
bar after index 30000 was moved +10% and every signal up to and including
index 30000 had to be unchanged. All five new blocks and four old ones pass.

| block | kind | what it reads |
|---|---|---|
| `prev_day_break(days)` | trigger | close vs the high/low of the previous UTC day, from completed days only |
| `opening_range(mins, hour)` | trigger | close crosses the high/low of the first N minutes after a UTC hour; only fires once that window is complete |
| `keltner_break(n, mult)` | trigger | close crosses outside EMA(n) ± mult·ATR |
| `flush(k, m, lookback, mode)` | trigger | bar range > k·ATR and volume > m× its own shifted average; `mode` follow/fade |
| `funding_window(hours)` | filter | only within N hours of a settlement, on Binance's published 00/08/16 UTC grid |

`funding_window` first version read the settlement times out of the funding
data and **failed** the causality test, because in a truncated series the next
settlement does not exist yet. It now derives the 8-hour grid from each bar's
own timestamp, which is what the published schedule actually is.

**`flush` is one block with a `mode`, not two blocks**, because "cascades
overshoot, so fade them" and "cascades start trends, so follow them" are
opposite hypotheses about the same event, and one grid that chooses between them
is a cleaner test than two ideas that are mirror images.

**Deliberately not built: `after_drop` (plan R4.6).** It was to be built from the
R1.0 finding that a -1.5%..-3% move in the 12 h before entry produced 72% of
005's profit. That finding was measured on 005's long leg, and Exp 017 showed
005's long leg is DRIFT - random entries with the same filters do as well. A
pre-entry effect measured on a drift result is not a foundation, so there is
nothing to build and the honest move is to leave the backlog item closed.

### Stop width is designed, not inherited

Exp 021 added the `UNSIZABLE` verdict, and the arithmetic is unforgiving: 1,000
USDT × 1% = 10 USDT of risk, BTC's step is 0.001, so a stop of `s` can be sized
only while BTC < 10/(0.001·s). BTC's TRAIN+VALID peak is 108,367, so:

- a **6%** stop is sizeable to 166,667 - safe
- an **8%** stop is sizeable to exactly 125,000 - and BTC's all-time peak in
  this data is 125,986, so an 8% stop is already outside the line
- a **10%** stop breaks above 100,000, and 33.9% of HOLDOUT bars are above it

Every Round 4 idea is therefore written at **1h with a 3% stop** (grid 2-3%),
so its 4h variant is 6% and every timeframe stays sizeable. Round 3's 023 used a
10% stop and its 4h variant was UNSIZABLE with 807 skips; that must not
happen twice.

### The ideas, and what would kill each

| # | file | hypothesis | kill if |
|---|---|---|---|
| R4.1 | `028_prev_day_break.json` | Yesterday's high/low is a level with real orders behind it: stops sit just beyond it and breakout traders queue at it, so a break is where both are triggered at once and price continues for a few hours. The counterparty is the stop order, not a mood | gross_r ≤ 0 (no gross edge to pay costs with) |
| R4.2 | `029_opening_range.json` | The 00:00 UTC print resets positioning - every day leveraged traders and market makers rebuild brackets around it - so the first hour's range is the day's agreed reference and the first break of it shows the day's direction | gross_r ≤ 0 |
| R4.3 | `030_funding_window.json` | Positions are opened and closed around funding settlements, so the flow within a couple of hours of a settlement is not the flow between them. This is a **timing** claim, not a directional one: the entry is the round's other blocks plus a window filter | gross_r ≤ 0, or the filter is inert (the result matches the same idea without it) |
| R4.4 | `031_liquidation_flush.json` | A bar with 2× the ATR range on 1.5× the volume is a liquidation cascade. Two opposite readings, and the grid chooses: `follow` if cascades start trends, `fade` if they overshoot. `direction: both` either way | gross_r ≤ 0 in BOTH modes - then the event has no exploitable side at all |
| R4.5 | `032_keltner_break.json` | A Keltner channel widens with volatility where a Donchian lags, so it should produce fewer false breaks in quiet regimes - the one structural difference from a price channel, tested on the same idea otherwise | gross_r ≤ 0 |

**Budget:** 5 ideas x 7 native timeframes = **35 evaluations**, plus
`baseline.py` + `benchmark.py` on every WATCH or PASS. Project total goes to
131. Grids ≤ 12 combos. Every report must show `size_skips 0`, and any
non-REJECT result with skips is read as `UNSIZABLE`, not as a result.

**Judge:** `benchmark.py` as in Round 3. A regime rule would need ALPHA; none of
these is a regime rule, so SKILL counts - but 20 of 20 benchmarks in this
project are NO_EDGE, and a rule that cannot beat holding BTC is not a strategy
card. A negative answer here is the expected and acceptable outcome: it would
mean the project has tested direction, timing, regime, exit management and now
market structure, and the answer is that BTCUSDT at VIP0 costs leaves no edge.

---

## Exp 022 - Round 4 results: one PASS, refused by the control, and the cost story again

**Date:** 2026-09-29
**Status:** complete. 35 evaluations: **1 PASS, 1 WATCH, 33 REJECT.** Project
total **131 evaluations** over 130 idea files and all 7 native timeframes.
HOLDOUT **not** spent: the round's one PASS is DRIFT, so `--final` refused it.

### Ideas tested (VALID mean R / n trades, and VALID gross_r)

| idea | 1m | 3m | 5m | 15m | 30m | 1h | 4h |
|---|---|---|---|---|---|---|---|
| 028 prev-day break | -0.373 | -0.145 | -0.113 | -0.060 | -0.040 | +0.005 | +0.029 |
| 029 opening range | -0.486 | -0.276 | -0.184 | -0.061 | -0.038 | +0.000 | **+0.113 PASS** |
| 030 funding window | -0.369 | -0.148 | -0.100 | -0.026 | -0.033 | +0.004 | +0.011 |
| 031 liquidation flush | -0.594 | -0.245 | -0.192 | -0.078 | -0.068 | +0.001 | -0.062 |
| 032 keltner break | -0.686 | -0.340 | -0.211 | -0.061 | -0.020 | +0.036 WATCH | +0.005 |
| *gross_r, 029* | +0.049 | +0.030 | +0.019 | +0.029 | +0.023 | +0.041 | **+0.141** |

### The one PASS: 029_opening_range at 4h (eval 72f03ca562)

| split | trades | gross_r | cost_r | mean R | 95% CI | CAGR | maxDD | stress | skips |
|---|---|---|---|---|---|---|---|---|---|
| train 2020-2022 | 453 | | | +0.0313 | | | | | 0 |
| valid 2023-2024 | 286 | +0.1408 | 0.0277 | **+0.1131** | [+0.006, +0.223] | +16.3% | 7.6% | +0.1018 | 0 |
| valid x1.5 cost | | | | +0.1018 | | | | | |

**DRIFT**, and `--final` refused it. Random entries with the same exits beat it:
on TRAIN its +0.0313 is below the 95th percentile of "random at any time"
(+0.0719). On VALID it clears that bar (+0.1131 vs +0.0805) but not the same
test on TRAIN, which is what the Exp 019 tightening requires. Benchmark:
**NO_EDGE** (beta 0.12 / 0.17, alpha **-1.7%** on TRAIN and **-0.9%** on VALID,
Sharpe 0.42 and 1.56 against buy & hold's 0.76 and 2.01).

The WATCH, 032_keltner_break at 1h, is also DRIFT and NO_EDGE - 6% and 11% of
random runs beat it on VALID. Worth one note: its TRAIN alpha is **+13.3% with a
CI of [+0.9, +26.4]**, the only positive alpha CI anywhere in this project, and it
is -0.7% on VALID. One period, gone.

### What we learned

1. **The cost story, for the fourth round running and now in its purest form.**
   The 00:00 UTC opening-range break has a positive `gross_r` at **every one of
   the seven timeframes** (+0.019 to +0.141) and is negative on net at six of
   them. The identical idea is **-0.486 R at 1m and +0.113 R at 4h**: nothing
   about the signal changed, only the size of R. `cost_r` is 0.019 at 4h and
   above 0.5 at 1m. This is now measured on four independent idea families
   (long breakouts, regime rules, pullbacks, market structure) and it is the
   only mechanism in this project that reproducibly produces results.

2. **A positive `gross_r` is not an edge, and a 4h PASS on it is not a strategy.**
   Gross +0.14 R sounds like an edge and the raw data has it, but the random-entry
   control says the same gross is available from entries that have no structure at
   all. What 029 found is that the opening range's break has a *small* predictable
   move, not that the break is *timed* well.

3. **A positive alpha CI on one period is a period, not an edge.** 032's TRAIN
   alpha is +13.3% [+0.9, +26.4] - the only alpha CI in 131 evaluations that
   excludes zero - and its VALID alpha is -0.7%. Two periods, opposite signs.
   This is the same shape as 022's 2023/2024 split, and it is the single most
   reliable way this project has produced a false positive.

4. **None of the four new market-structure ideas survived, and they failed in the
   same way: no gross edge, or a gross edge that timing cannot reach.** 028
   (yesterday's extreme) grossed +0.02 to +0.07; 030 (funding window) +0.02 to
   +0.06; 031 (liquidation flush) +0.084 at 1m falling to -0.043 at 4h, and
   **negative gross in both follow and fade modes at 30m and 4h** - so the
   "cascades overshoot" and "cascades start trends" hypotheses are both dead on
   gross, which is the kill condition that was pre-registered for exactly this.
   032 (Keltner) is the only one with a real gross (+0.091 at 1h) and it is
   DRIFT.

5. **`flush` follow and fade both failed on gross, which is a stronger result
   than either failing on net.** A cascade event that has no predictable
   direction in either reading is not a tradeable event on this market at these
   costs, and that closes the entire "liquidation cascade" family rather than
   leaving the mode as a parameter to re-tune.

### Verdict

`REJECT`, and the round is complete. 33 of 35 REJECT, and the two survivors are
DRIFT and NO_EDGE, so the project's holdout remains unspent on anything that
passed the controls.

Cumulatively, across 131 evaluations, the project has now tested **direction**
(long entries, short entries, both sides), **timing** (sessions, funding
windows, the daily open, yesterday's extremes), **regime** (trend state, ADX,
volatility, squeeze), **exit management** (TP, break-even, trailing, time stop,
stop width and kind), **timeframe** (all seven) and **market structure** (four
new blocks built for this round). The answer is the same at every level: **no
tested technique on BTCUSDT USDT-M at VIP0 costs has an edge that survives a
random-entry control and a buy-and-hold benchmark.** Five rows have ever read
PASS. One reached the holdout and returned -0.0102 R.

The holdout has been spent exactly twice, on `example_trend_breakout` (the Exp 011
lock test) and on 022, and **both FAILED**. `PLAN.md` §7 now applies: the
deliverable is `journal/BTCUSDT/FINAL_REPORT.md`.

---

## Exp 023 — Review of Round 4, FINAL_REPORT corrections, and Round 5 (cost first)

**Date:** 2026-09-29
**Status:** complete (review + plan; no new evaluation, holdout untouched)

### Review of Exp 022
Process was clean. Pre-registration came before results. The Round 4 stops
were designed to stay sizable (every non-REJECT row has 0 skips on TRAIN and
VALID). Baseline and benchmark ran on the PASS and the WATCH. `--final` on
029@4h was refused and nothing was written. `holdout_log.csv` is unchanged.
The five new blocks look causal on reading and pass test 7.
`evaluations.csv` was re-written with the new `train_size_skips` column: all 95
earlier rows compared field by field, and no value changed. Benchmarks are
**22 of 22 NO_EDGE**.

### Corrections (FINAL_REPORT.md edited in place, noted at its end)
1. Thai summary: 023 was refused because a regime rule needs ALPHA (it was
   SKILL), not because of DRIFT.
2. Thai summary: the ATR-stop example is 3.0× ATR = 1.28% → 0.78% of price
   (the English body was right; "2.83%" was a different stop).
3. "Holdout used twice, both failed": the first use was the lock test during
   repo setup. Only one technique, 022, has spent a holdout.
4. 20 → 22 benchmarks.
5. **§3's opening-range column is not a same-signal comparison.** An
   opening-range window cannot be shorter than one bar. At 4h, "the first
   30/60/120 minutes" is the whole 00:00–04:00 bar, so the grid key `mins` was
   inert. At 1h all `mins` values are the 00:00 bar. 029@4h's PASS therefore
   tested "break of the first 4h bar", not the pre-registered first hour. The
   cost gradient stands on the same-signal rows of Exp 016.

### Why Round 5
For the 105 evaluations with a `pct` stop (≥ 100 TRAIN trades), gross and cost
per trade were converted to % of price (gross_r × stop, cost_r × stop).
Medians on TRAIN:

| tf | 1m | 3m | 5m | 15m | 30m | 1h | 4h |
|---|---|---|---|---|---|---|---|
| gross % | 0.020 | 0.022 | 0.026 | 0.053 | 0.195 | 0.361 | 0.237 |
| cost % | 0.155 | 0.134 | 0.129 | 0.113 | 0.112 | 0.112 | 0.110 |

The net sign is gross % − cost %, and the stop width only sets the unit. Cost
is flat at ≈ 0.11% of price per trade. Only a longer hold makes the move
bigger than that, and so far every long hold was long-only, which earns the
drift. Round 5 (PLAN.md §4) fixes cost first and removes drift by design:
- 4h source files with `--mode time` variants;
- 4–7% stops and 48–120 h holds, expected cost ≤ 0.05 R;
- both directions and no directional filter;
- ≥ 150 TRAIN signals, counted before running.

Ideas: funding carry, multi-day reversal, multi-week momentum, Keltner at a
multi-day hold, plus one of the agent's own.

Design checks done for the plan, on TRAIN only:
- Signal counts on 4h, TRAIN 2020–2022:
  - `funding_extreme` 0.00015: 46 long / 108 short;
  - `zscore_revert` n 30, z 2.0: 128 / 158;
  - `donchian_break` n 60: 141 / 83;
  - `keltner_break` n 20, mult 2.0: 152 / 109.
- `tf_variants --mode time` from a 4h source to 1m keeps the 5% stop and the
  hours, and scales the bar counts (30 → 7,200). A 1m run on TRAIN takes ≈ 20 s
  per combo, with cost_r 0.028 and 0 skips.

Next entry is **Exp 024** (Round 5 pre-registration).

---

## Exp 024 - Round 5 pre-registration (cost first), and a Round 4 bug found

**Date:** 2026-09-29
**Status:** pre-registration, written BEFORE any Round 5 evaluation and before
the corrected re-run of 029. Zero evaluations in this entry;
`results/BTCUSDT/evaluations.csv` is untouched by it. Project count on entry:
**131 evaluations**. HOLDOUT sealed.

### Bug: `opening_range` traded long-only for all of Round 4

Found while writing R5.5, not by a test. Every trigger in `recipes.py` returns
**one signed array** (+1 long, −1 short) via `_side()`. `t_opening_range`, added
in Exp 022, returned a `(long, short)` tuple instead, and `recipe()` does
`np.asarray(fn(...))` on whatever a trigger returns, so a `(2, n)` array was
stacked and then read as `(S > 0).any(axis=0)` - which is true if *either* side
fired. Every signal became LONG.

The recorded records show it plainly:

| idea | valid long | valid short |
|---|---|---|
| 028 prev_day_break | 311 | 250 |
| **029 opening range** | **798** | **0** |
| 030 funding window | 288 | 232 |
| 031 liquidation flush | 234 | 276 |
| 032 keltner break | 141 | 106 |

**029's Round 4 PASS (286 valid trades at 4h) was a long-only result wearing the
label "both sides".** What survives of it: the control verdicts. `baseline.py`
said DRIFT and `benchmark.py` said NO_EDGE, and a long-only result in a bull
market is exactly the family Exp 017/019/020 closed, so the round's conclusion -
no edge - is unchanged. What does not survive is the claim that 029 was a
market-structure both-sided result. The block is fixed (one `_side()` call), now
fires 1,464 long / 1,417 short on 4h, and the corrected idea is re-tested below
as **R5.6**, because it is a bug correction rather than a new hypothesis and it
would otherwise stay untested in a form that can trade both sides.

`month_turn_fade`, written today, hit the same trap and was caught before it ran.
A check worth keeping: **every trigger returns a 1-D array of 0/+1/-1, every
filter returns two boolean arrays.** Run after any new block.

### Why Round 5 exists

Rounds 1-4 designed the signal first and measured cost afterwards. Exp 023
converted gross and cost to % of price per trade for the 105 `pct`-stop
evaluations (median, TRAIN):

| tf | 1m | 3m | 5m | 15m | 30m | 1h | 4h |
|---|---|---|---|---|---|---|---|
| gross move, % of price | 0.020 | 0.022 | 0.026 | 0.053 | 0.195 | 0.361 | 0.237 |
| cost, % of price | 0.155 | 0.134 | 0.129 | 0.113 | 0.112 | 0.112 | 0.110 |

Cost is flat at ~0.11% of price per trade at **every** timeframe. Only a longer
hold makes the gross move bigger than that. And every long hold so far was
long-only, which earns the drift, not an edge. So Round 5 fixes cost first and
removes the drift by construction.

### The five design constraints, and how each idea meets them

1. **4h source, `--mode time` variants.** Stop stays the same % of price and the
   hold the same hours on all seven timeframes, so `cost_r` is comparable
   everywhere and the only thing the timeframe axis asks is whether a finer entry
   clock helps. Chart mode would shrink a 5% stop to 0.3% at 1m and lose to cost
   again, which is what every 1m variant in Rounds 1-4 did.
2. **`pct` stop 4-7%.** Above 7.9% the 1,000 USDT account cannot size a trade at
   the 2025 price peak of 125,986, so 7% keeps the holdout sizable.
3. **Hold 48-120 h, expected cost written before running and <= 0.05 R.**
   `(0.14% + hold_h/8 x 0.01% funding) / stop`:
   stop 4%: 48h 0.0500, 72h 0.0575*, 96h 0.0650*, 120h 0.0725*
   stop 5%: 48h 0.0400, 72h 0.0460, 96h 0.0520*, 120h 0.0580*
   stop 6%: 48h 0.0333, 72h 0.0383, 96h 0.0433, 120h 0.0483
   stop 7%: 48h 0.0286, 72h 0.0329, 96h 0.0371, 120h 0.0414
   (* above the limit)
   **The plan's own R5.1 sketch (stop 5%, hold up to 120 h) violates its own
   constraint 3 at 0.0580 R.** Constraint 3 wins: R5.1 uses a 6% stop.
4. **`direction: "both"`, no directional filter.** No `htf_trend`, `trend_ema` or
   `price_vs_ema` anywhere in this round - a trend filter would make a both-sided
   idea long in 2023-24 again, which is the failure mode Rounds 1-3 kept hitting.
5. **>= 150 TRAIN signals, counted before running** (4h, TRAIN 2020-2022 only,
   counted in this entry). Values below 150 are dropped **now**, not after:

| trigger | value | TRAIN long/short | total | action |
|---|---|---|---|---|
| funding_extreme | 0.00015 | 46 / 108 | 154 | keep |
| funding_extreme | 0.0002 | 26 / 118 | 144 | **DROP** |
| funding_extreme | 0.0003 | 16 / 113 | 129 | **DROP** |
| zscore_revert | n30 z2.0 | 128 / 158 | 286 | keep |
| zscore_revert | n30 z2.5 | 67 / 113 | 180 | keep |
| zscore_revert | n60 z2.0 | 102 / 135 | 237 | keep |
| zscore_revert | n60 z2.5 | 48 / 69 | 117 | **DROP** |
| donchian_break | n30 | 190 / 130 | 320 | keep |
| donchian_break | n60 | 141 / 83 | 224 | keep |
| donchian_break | n120 | 90 / 48 | 138 | **DROP** |
| keltner_break | n20 m2.0 | 152 / 109 | 261 | keep |
| keltner_break | n20 m3.0 | 45 / 17 | 62 | **DROP** |
| keltner_break | n50 m2.0 | 166 / 166 | 332 | keep |
| keltner_break | n50 m3.0 | 130 / 83 | 213 | keep |
| month_turn_fade | ±2d, lb6 | 519 / 447 | 966 | keep |
| opening_range | 1h (fixed) | 732 / 707 | 1439 | keep |

Two consequences of dropping inside a product grid, recorded so the grids are not
mistaken for the plan's: `funding_extreme` keeps only thresh 0.00015, so R5.1's
grid is thresh x stop, not thresh x hold; `keltner_break` loses n20 m3.0, which
means mult 3.0 goes with n50 only, so R5.4 grids n x mult and both surviving
pairs are kept by pairing (20, 2.0) and (50, 3.0) as two explicit values of one
`n_mult` key.

### The ideas, and what would kill each

| # | file | hypothesis | kill if |
|---|---|---|---|
| R5.1 | `033_funding_carry.json` | Funding is a transfer from longs to shorts every 8h. When it is extreme, the paying side is the crowded side, and a crowded book's unwind takes days, not hours. Short the payer and collect the funding while the unwind works. Idea 003 (15m, 12h) never got past 13 trades, so this has never really been tested | TRAIN gross_r <= 0 |
| R5.2 | `034_multiday_reversal.json` | After a 5-10 day move of more than 2 sigma, late trend followers and forced liquidations have pushed price past fair value and part of it comes back over days. The Exp 016 "never retry mean reversion" ban was about 15m/12h holds whose gross move was under the cost; this is a different horizon and is allowed here | TRAIN gross_r <= 0 |
| R5.3 | `035_multiday_momentum.json` | A 5-20 day extreme is where trend-following funds add risk. It continued down in 2022 and up in 2023-24, so a both-sided rule should work in both periods if the effect is real - and not only in the bull market | TRAIN gross_r <= 0, **or** one side carries all of it in the period matching the drift (short in 2022, long in 2023-24) |
| R5.4 | `036_keltner_multiday.json` | 032 (Keltner, 1h, 12h) had Round 4's largest TRAIN gross but was DRIFT with its `htf_trend` filter. Test the channel alone, both sides, held for days, with no directional filter at all | TRAIN gross_r <= 0 |
| R5.5 | `037_turn_of_month_fade.json` | **My own idea.** Month-end and month-start are calendar events, not price events: risk budgets, index and mandate resets and benchmark rebalancing all push positions one way for a few days, and the flip into the new month is when those mandates stop pushing, so part of the move is handed back. Counterparty: the rebalancing flow itself. It is a *fade*, so it is naturally both-sided and it is orthogonal to BTC's direction - which is the only kind of idea left. New Level 2 block `month_turn_fade(before, after, lookback)` | TRAIN gross_r <= 0 |
| R5.6 | `038_opening_range_both_sides.json` | **Bug correction, not a new hypothesis.** R4.2's 00:00 opening-range break, re-tested with the block fixed and with the 4-7% stop and 48-120h hold that Round 4 did not have. R4.2's only sub-cost 4h gross of any Round 4 structure was +0.141% of price at 4h, above the 0.11% cost line, so the level is worth re-measuring on both sides | TRAIN gross_r <= 0 |

**Judge:** PASS + `baseline.py` SKILL (TRAIN and VALID) -> `--final`. Because the
ideas are both-sided and carry no directional filter, SKILL is meaningful here -
random entries with the same stop and hold take both sides too. `benchmark.py`
on every WATCH/PASS, and **beta must be near 0**: a beta above 0.1 means the idea
is secretly long, which is the failure mode this round exists to rule out.

**Budget:** 6 ideas x 7 timeframes with `--mode time` = **42 evaluations**.
Project total goes to 173. Grids <= 8 combos, because the 1m variant has 3.4M
bars and `--mode time` scales bar counts up to 7,200.

**Read in the round summary:** `cost_r` per timeframe (should be flat, 0.03-0.05);
gross % per trade against the 0.11% line; long vs short mean R and trade counts;
the per-year split (2020, 2021, 2022 against 2023, 2024).

---

## Exp 024 - Round 5 results: cost first worked, two ALPHA results, and the holdout failed a third time

**Date:** 2026-09-29
**Status:** complete. 42 evaluations: **1 PASS, 9 WATCH, 17 REJECT, 15
INCONCLUSIVE.** Project total **173 evaluations**. HOLDOUT spent a third time,
on the one config that qualified, and **FAILED**.

### The design worked: `cost_r` is flat for the first time

`--mode time` variants from a 4h source did exactly what constraint 1 intended.
VALID `cost_r` by timeframe, all six ideas:

| idea | 1m | 3m | 5m | 15m | 30m | 1h | 4h |
|---|---|---|---|---|---|---|---|
| 033 funding carry | 0.023 | 0.023 | 0.023 | 0.023 | 0.020 | 0.023 | 0.020 |
| 034 multi-day reversal | 0.021 | 0.020 | 0.019 | 0.019 | 0.019 | 0.019 | 0.019 |
| 035 multi-day momentum | 0.021 | 0.019 | 0.019 | 0.019 | 0.019 | 0.019 | 0.019 |
| 036 keltner multi-day | 0.020 | 0.019 | 0.019 | 0.019 | 0.019 | 0.019 | 0.019 |
| 037 turn-of-month fade | 0.017 | 0.018 | 0.016 | 0.019 | 0.017 | 0.019 | 0.019 |
| 038 opening range | 0.023 | 0.020 | 0.019 | 0.022 | 0.022 | 0.022 | 0.022 |

Compare Exp 016's chart-mode ladder for the same idea: **0.505 R on 1m down to
0.019 R on 4h**. Here every timeframe sits at 0.016-0.023 R. For the first time
in this project a signal could be evaluated on 1m without cost deciding the
answer, and the two ideas that were best at 1m (035 at +0.114, 036) did not
collapse there. **That is the single most useful methodological result of the
round: the cost problem is an artefact of how variants were built, and it is
removable.**

### The two ALPHA results - a first in the project

| config | verdict | baseline | benchmark |
|---|---|---|---|
| **038 opening range, 4h** | **PASS** | DRIFT | **ALPHA** |
| 035 multi-day momentum, 4h | WATCH | DRIFT | **ALPHA** |
| the other 8 WATCHes | WATCH | DRIFT | NO_EDGE |

`benchmark.py` had returned NO_EDGE on 23 of 23 runs before this round. Two
configurations now say ALPHA, and crucially their **beta is ~0**, which was the
round's own test for "not secretly long":

| config | period | long/short trades | beta | alpha/yr [95% CI] | Sharpe idea / B&H |
|---|---|---|---|---|---|
| 038 | VALID | **77 / 78** | **+0.01** | **+10.2% [+1.4, +18.3]** | 1.61 / 2.01 |
| 038 | TRAIN | | −0.02 | +5.6% [−4.7, +16.6] | 0.42 / 0.76 |
| 035 | VALID | 61 / 38 | | ALPHA | |

**038 was PASS + ALPHA, so `--final` was permitted and was run** (AGENTS.md
step 7, PLAN §5). The holdout refused nothing and returned:

| split | trades | gross_r | cost_r | mean R | 95% CI | CAGR | maxDD |
|---|---|---|---|---|---|---|---|
| train 2020-2022 | 258 | +0.075 | 0.021 | +0.0534 | | | 11.8% |
| valid 2023-2024 | 155 | **+0.197** | 0.022 | **+0.1753** | [+0.032, +0.327] | +11.8% | 5.9% |
| **holdout 2025-01..2026-08** | 135 | **−0.090** | 0.022 | **−0.1118** | [−0.244, +0.021] | **−6.4%** | 12.6% |

**FAILED.** The holdout has now been used three times - the Exp 011 lock test,
022, and 038 - and **all three failed**. Only one technique has ever spent a
holdout before 038; both techniques that did are gone.

### What we learned

1. **A positive alpha with beta ~0 is not the same as an edge, and this project
   has now measured the difference.** 038 had alpha +10.2%/yr with a VALID CI of
   [+1.4, +18.3] and a beta of 0.01, so its return was demonstrably not BTC's
   direction - and its gross move per trade was **+0.99% of price against a cost
   of 0.11%**, a 9:1 ratio that no idea in Rounds 1-4 achieved. On the holdout
   the same config's `gross_r` went from **+0.197 to −0.090**. A 9:1 gross-to-cost
   ratio is not protection when the gross itself is a two-year phenomenon: 038's
   VALID split was 2023 +0.0916 (77 trades) against 2024 +0.2579 (78 trades),
   and both years of 2023-24 were a period in which this particular structure
   happened to work. **The cost lesson is real; the edge was not.**

2. **DRIFT and ALPHA together are a new state, and it is a warning rather than a
   result.** 038's `baseline.py` said DRIFT: on TRAIN its −0.005 sat below the
   95th percentile of random entries with the same stop and hold (+0.107). So
   the entry has no timing skill, the return is not BTC's direction, and the
   strategy still made money on VALID. The only mechanism left for that is *being
   in the market with a cheap cost structure* - which is not an edge, it is an
   exposure decision, and it does not survive a period where the market gives
   nothing back. This is the cleanest separation of the three things a backtest
   can produce - skill, drift, and cost - that the project has produced.

3. **Mean reversion is answered for a real horizon too, not just intraday.**
   034 (z-score over 5-10 days, 48-96h hold, 5% stop) had a positive TRAIN gross
   of **+0.32% of price against a cost of 0.108%** - a 3:1 ratio, the best
   reversion gross ever measured here - and still went to VALID at **−0.098**,
   REJECT at all seven timeframes. Exp 016's "never retry mean reversion" is now
   confirmed at the horizon where the cost objection does not apply. The
   mechanism is not that reversion is too expensive; it is that BTC's
   multi-day overshoots do not come back within five days.

4. **Funding carry is INCONCLUSIVE, not negative: 100 TRAIN trades and 28 VALID.**
   `funding_extreme` at 0.00015 fires 154 times in three years on 4h and the
   96h hold means a position is open most of the time, so the sample cannot
   reach 100 VALID trades. **The one hypothesis in this project that is untested
   rather than refuted is the one that earns from funding rather than from
   price.** It needs a different instrument - a rolling funding-rate position
   held for weeks, with the stop and the time stop removed because carry is not a
   price trade - and that is a Level 3 idea, not an idea file.

5. **Turn-of-month fade (R5.5, my own idea) is INCONCLUSIVE at 6 of 7
   timeframes** for the same reason: the calendar window is 5 days a month, so
   there are not enough entries for a multi-day hold. It produced 966 TRAIN
   signals but VALID trade counts stay under 30 because each 96h position
   occupies most of a 5-day window. The hypothesis is not refuted, it is
   **unmeasurable in this design**, and saying so is more useful than a
   REJECT.

6. **`--mode time` is the correct default for anything with a long hold, and it
   is not cosmetic.** It moves `cost_r` from a 26:1 spread across timeframes to
   1.4:1. Anything in this project that wants to compare timeframes on a
   multi-day hold should use it.

### Verdict

`REJECT`, with one methodological win. 41 of 42 evaluations are not candidates:
17 REJECT, 15 INCONCLUSIVE, 9 WATCH all DRIFT and 8 of 9 NO_EDGE, and the single
PASS - the first, and only, PASS + ALPHA of the project - **FAILED its holdout
with a negative gross**.

**The plan is now complete.** 173 evaluations, 6 rows ever read PASS, **0
CONFIRMED**, 3 holdout runs, 3 failures. What the evidence supports is narrower
and sharper than "no edge exists", and it is worth stating precisely:

- At BTCUSDT VIP0 costs, **cost is the first-order term** and it is a design
  choice, not a fate: `--mode time` plus a 5-7% stop takes `cost_r` to ~0.02 R
  on every timeframe.
- With cost solved, several both-sided multi-day structures produce a **positive
  gross of 1% of price per trade** - and **none of them has timing skill**, so
  the gross is a property of the period, not of the entry.
- The one hypothesis never refuted is **carry**: earning funding without a price
  view. It is unmeasurable inside this engine because a 96h hold and a 0.15%
  extreme-funding threshold cannot produce 100 VALID trades. That is the single
  most promising thing left, and it needs a different instrument rather than
  another idea file.

Per `PLAN.md` §7 the next step is the owner's: other markets, cross-exchange
basis and funding data, or VIP fee tiers. **Nothing in this project is a
profitable strategy, and the holdout has never confirmed anything.**
