# BTCUSDT USDT-M Futures — Intraday Strategy Research

A research harness for BTCUSDT **day trading** on Binance USDT-M futures
(perpetual). Everything is backtested against real exchange data with costs
included, because a strategy that only works with zero fees and zero
slippage is not a strategy.

## Setup / agreed parameters

| Item | Value |
|---|---|
| Instrument | BTCUSDT perpetual (USDT-M) |
| Style | Intraday only, flat by session end, long **and** short |
| Capital | 100 USDT |
| Risk / trade | 1% of current equity (compounding) |
| Max leverage | 10x notional cap |
| Max concurrent positions | 1 (no pyramiding) |
| Fee | VIP0 taker 0.05% / maker 0.02% (market orders => taker) |
| Slippage | 0.02% per fill, always against us |
| Funding | charged at real timestamps while a position is open |
| Intrabar rule | if a bar touches stop **and** target, the **stop** fills first |
| Holding period target | 1–4 hours |
| Data | 1m klines + funding rate, 2020-01 .. 2026-08 (~80 months) |

## Why these settings are conservative

* **Signals execute at the NEXT bar's open.** A signal computed from bar `i`'s
  close is filled at bar `i+1`'s open, never at bar `i`'s close. Most
  intraday backtest bugs come from filling at the bar you used to decide.
* **Stop-first on ambiguous bars.** With 5m bars, a bar's high/low does not
  tell us the order of moves. Assuming the favourable order roughly doubles
  reported returns. We assume the worst.
* **Round-trip cost ≈ 0.14%** (0.05% + 0.05% fee, 0.02% + 0.02% slippage).
  At a 2-ATR stop on 5m bars a typical R is ~0.1–0.3% of price, so costs eat
  a large slice of every trade. This is the whole game.
* **Position sizing from the stop**, not a fixed notional, so "1% risk" means
  the same thing for a quiet month and a violent one.

## Layout

```
src/config.py        all tunable constants + costs + risk rules
src/datafeed.py      download & cache Binance public data, with validation
src/indicators.py    causal indicators (EMA/ATR/RSI/ADX/BB/VWAP/supertrend...)
src/backtest.py      event-driven backtester + metrics
src/strategies.py    rule-based strategy zoo (the "rules" arm)
src/ml_filter.py     causal features + trade-outcome labelling
src/run_ml.py        walk-forward "rules vs ML" comparison
src/experiment.py    data loading, resampling, walk-forward splits, sweeps
journal/             the research log - one entry per experiment
results/             CSV output of every run
```

## Usage

```powershell
# 0. verify the engine (must pass before any number is trusted)
python src\test_engine.py

# 1. download + validate data (only needed once)
python src\datafeed.py

# 2. leak-free sweep: train -> shortlist -> test
python src\sweep.py 20

# 3. the cost arithmetic: stop width x execution scenario
python src\cost_lab.py

# 4. stop width chosen on train, frozen, then tested
python src\round2_stopwidth.py

# 5. rules vs ML filter, walk-forward
python src\run_ml.py 15 2.0

# 6. the definitive number: pooled executed trades + bootstrap + chained equity
python src\definitive.py 15 "1.0,2.0,3.5,5.0"
```

## Headline result

**No statistically demonstrated edge** in intraday BTCUSDT futures at retail
(VIP0) costs, across 106+ configurations, 4 timeframes, 6.5 years, and two
strategy families. The best configuration returns **+2.2%/year** with a 95%
confidence interval on expectancy of `[-0.039, +0.115] R/trade` — i.e.
indistinguishable from zero.

The single most important finding is *why*:

```
cost_r = round_trip_cost / stop_distance
       =    0.14%      /   0.5%      =  0.28 R per trade
```

Every "1.8x ATR stop" rule is a cost-efficiency mistake. Widening the stop
from 1x to 5x, **without changing a single signal**, moved the account from
-25%/year to roughly break-even. See `journal/experiments.md` Exp 004 and 007.

## The log

`journal/experiments.md` is the source of truth. Every run gets an entry with
the hypothesis, the result, and — most importantly — the verdict. Entries are
appended, never edited, so we can see which ideas actually survived contact
with out-of-sample data.

## Honest expectations

Most published intraday BTC futures strategies do not survive realistic
costs. That turned out to be true here as well, and finding that out cheaply
was the point of building the harness. The one lever not yet exhausted is
execution cost: a post-only maker round trip is 0.04% instead of 0.14%, which
is a 3.5x reduction in the dominant term — but it requires a real fill model
to test honestly, because an unfilled limit order is a skipped trade, not a
cheap one.
