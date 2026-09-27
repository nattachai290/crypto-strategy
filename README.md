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

> **AI agents / new contributors:** read `AGENTS.md` (rules) and
> `journal/<SYMBOL>/STATUS.md` (current state + next steps) before changing
> anything. Code in `src/` is shared; everything coin-specific lives in a
> `<SYMBOL>/` folder, selected per run with `SYMBOL=...` (default `BTCUSDT`).

```
AGENTS.md            rules for AI agents (CLAUDE.md imports it)
src/config.py        all tunable constants + costs + risk rules
src/datafeed.py      download & cache Binance public data, with validation
src/indicators.py    causal indicators (EMA/ATR/RSI/ADX/BB/VWAP/supertrend...)
src/backtest.py      event-driven backtester + metrics
src/strategies.py    rule-based strategy zoo (the "rules" arm)
src/ml_filter.py     causal features + trade-outcome labelling
src/run_ml.py        walk-forward "rules vs ML" comparison
src/experiment.py    data loading (native bars only), walk-forward splits
src/test_engine.py   engine correctness tests
src/evaluate.py      the research gate: idea file -> verdict
src/recipes.py       combinable triggers / filters / exits
ideas/               idea files (JSON), shared by all coins
docs/research/       TECHNIQUES.md - what to try
journal/<SYMBOL>/    STATUS.md + research log (one entry per experiment)
results/<SYMBOL>/    evaluations.csv + holdout_log.csv (current workflow)
results/<SYMBOL>/legacy/  Exp 003–010 outputs, report.html, logs (history)
data/raw|cache/<SYMBOL>/  downloaded zips / parquet (git-ignored)
```

## Research workflow (from Exp 011)

New ideas are JSON files in `ideas/`, combining triggers, filters and exits
(`src/recipes.py`), and are judged by one command with fixed gates:

```bash
python src/evaluate.py --list                          # building blocks
python src/evaluate.py ideas/example_trend_breakout.json   # TRAIN select -> VALID verdict
python src/evaluate.py ideas/<idea>.json --final       # one-time HOLDOUT, only after PASS
```

Rules: `AGENTS.md`. Technique catalogue + backlog: `docs/research/TECHNIQUES.md`.

## Usage (older experiment scripts, Exp 000–010)

```bash
pip install -r requirements.txt

# 0. verify the engine (must pass before any number is trusted)
python src/test_engine.py

# 1. download + validate data (only needed once)
python src/datafeed.py

# 2. leak-free sweep: train -> shortlist -> test
python src/sweep.py 20

# 3. the cost arithmetic: stop width x execution scenario
python src/cost_lab.py

# 4. stop width chosen on train, frozen, then tested
python src/round2_stopwidth.py

# 5. rules vs ML filter, walk-forward
python src/run_ml.py 15 2.0

# 6. the definitive number: pooled executed trades + bootstrap + chained equity
python src/definitive.py 15 "1.0,2.0,3.5,5.0"
```

## Data cache

`.parquet` files in `data/cache/<SYMBOL>/` are **generated** by `src/datafeed.py` and are
**not committed** — rebuild them after cloning with `python src/datafeed.py`.

The raw Binance monthly zips in `data/raw/<SYMBOL>/` (1m/3m/5m/15m/30m klines + funding,
2020-01 .. 2026-08, ~240 MB) are **not committed** either. `datafeed.py`
downloads any month that is missing from
https://data.binance.vision/?prefix=data/futures/um/monthly/klines/BTCUSDT/ ,
verifies its SHA-256 checksum, skips files already on disk, and only takes
months inside `DATA_START..DATA_END` from `src/config.py`.

Every timeframe is Binance's own native file — **nothing is resampled**
(see `journal/BTCUSDT/experiments.md` Exp 010).

## Headline result

**No statistically demonstrated edge** in intraday BTCUSDT futures at retail
(VIP0) costs, across 106+ configurations, 4 timeframes, 6.5 years, and two
strategy families. After fixing a one-bar data offset (Exp 010) the best
walk-forward configuration is **+0.051 R/trade on 72 trades**, 95% CI
`[-0.065, +0.168]`, **+0.9%/year** — indistinguishable from zero.
(Earlier numbers such as "+2.2%/year" came from shifted data and are void;
see `journal/BTCUSDT/STATUS.md` for which result files are stale.)

The single most important finding is *why*:

```
cost_r = round_trip_cost / stop_distance
       =    0.14%      /   0.5%      =  0.28 R per trade
```

Every "1.8x ATR stop" rule is a cost-efficiency mistake. Widening the stop
from 1x to 5x, **without changing a single signal**, moved the account from
roughly -17..-25%/year to roughly break-even. See `journal/BTCUSDT/experiments.md`
Exp 004, 007 and 010.

## The log

`journal/<SYMBOL>/experiments.md` is the source of truth. Every run gets an entry with
the hypothesis, the result, and — most importantly — the verdict. Entries are
appended, never edited, so we can see which ideas actually survived contact
with out-of-sample data.

## Honest expectations

Most published intraday BTC futures strategies do not survive realistic
costs. That turned out to be true here as well, and finding that out cheaply
was the point of building the harness. Cheaper execution was tested too
(Exp 008/010): a post-only entry with a taker exit cuts the round trip from
0.14% to 0.09% (1.55x, not 3.5x — a stop-loss never gets a maker fill), and
adverse selection eats part of that. It helps, but no configuration's
confidence interval excludes zero. Next steps are listed in `journal/BTCUSDT/STATUS.md`.
