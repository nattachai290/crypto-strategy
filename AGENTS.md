# AGENTS.md — rules for any AI agent working in this repo

Read this file first, then `docs/STATUS.md` (where the project stands and
what to do next), then the latest entries of `journal/experiments.md`.

This is a **research harness**, not a trading bot. Its job is to find out
honestly whether an intraday edge exists in BTCUSDT USDT-M perpetual futures
after realistic costs. So far the answer is **no** (see `docs/STATUS.md`).
A result that looks too good is a bug until proven otherwise.

---

## 1. Hard rules (never break these)

### Honesty of results
1. **Never loosen the cost model to make a result look better.** Fees
   (taker 0.05% / maker 0.02%), slippage 0.02% per fill, funding at real
   timestamps and stop-first intrabar fills are fixed in `src/config.py`.
   Changing any of them requires a journal entry explaining why (see §4).
2. **Signal on bar `i` close → fill at bar `i+1` open.** Never fill at the bar
   used to make the decision. All indicators must be causal (value at `i` uses
   only bars `<= i`).
3. **Stop fills first** when a bar touches both stop and target
   (`PESSIMISTIC_INTRABAR = True`). Do not flip it.
4. **Train/test separation is sacred.** Parameters, thresholds, stop widths
   and model choices are selected on train (or inside the walk-forward train
   window) only. Choosing the best of N on test is a second selection and must
   be reported as such.
5. **Only executed trades describe the account.** Bootstrap and CAGR come from
   the pooled trades the backtester actually executed across walk-forward
   folds, with equity chained fold-to-fold. Never bootstrap the ML label set,
   never sum per-fold percentage returns (Exp 007).
6. **A result is not "profitable" unless its 95% bootstrap CI on expectancy
   (R/trade) excludes zero.** Report `gross_r`, `cost_r`, `exp_r`, trade count
   and the CI together — never a return or Sharpe alone.
7. **Never report a number you did not produce in this session or cannot
   point to in `results/`.** If you did not run it, say so.

### Data
8. **No resampling.** Every timeframe is loaded from Binance's own native
   kline file via `experiment.get_bars(tf)`. A home-made resampler once shifted
   every bar by one window and invalidated nine experiments (Exp 010). Do not
   add a resample path back.
9. **Data loading must fail loudly.** A pipeline that logs an error and exits 0
   is a lie (Exp 000: 58 of 80 months silently dropped). Run
   `datafeed.validate()` after any data change; it must print `OK`.
10. Timestamps are **UTC, tz-aware**, and a bar's timestamp is its **open
    time** (Binance convention).

### Engine
11. **`python src/test_engine.py` must print `ALL CHECKS PASSED`** before and
    after any change to `src/backtest.py`, `src/indicators.py`,
    `src/strategies.py`, `src/ml_filter.py` or `src/config.py`. If you change
    behaviour on purpose, extend the tests (the differential reference in
    `test_engine.py` must be updated in the same commit) — never weaken or
    delete a check to make it pass.
12. The engine is **single-position** (`MAX_CONCURRENT = 1`, no pyramiding).
    Do not add concurrency without a new test suite for it.
13. Position size is derived from stop distance so "1% risk" means the same in
    every regime. Keep it that way.

### Journal and records
14. `journal/experiments.md` is **append-only**. Never edit or delete a past
    entry, even when it is wrong — append a new entry (or a clearly labelled
    "Correction" section) that supersedes it, as Exp 008 → Exp 010 did.
15. `journal/ledger.md` and `results/ledger.csv` are **generated** by
    `src/ledger.py` / `src/ledger_report.py`. Do not edit by hand.
16. Every new experiment gets: a new script (or a flagged mode of an existing
    one), its own CSV in `results/`, its log in `data/<name>.log`, and a
    journal entry using the template in §4.

### Git
17. Do not commit `data/cache/*.parquet`, `__pycache__/`, or secrets/API keys.
    The raw zips in `data/raw/` are already tracked (see `docs/STATUS.md`); do
    not add large new binaries without asking the owner.
18. No live trading code, exchange API keys, or order placement in this repo
    unless the owner explicitly asks for it.

---

## 2. Repository map

```
AGENTS.md / CLAUDE.md   these rules (CLAUDE.md just imports this file)
docs/STATUS.md          current state, validity of each result file, next steps
README.md               human-facing overview
requirements.txt        Python dependencies
report.html             generated HTML report (Thai) — src/make_report.py
journal/experiments.md  research log, SOURCE OF TRUTH, append-only
journal/ledger.md       generated summary of results/ledger.csv
results/*.csv|json      raw output of each experiment script
data/raw/               Binance monthly zips (1m/3m/5m/15m/30m klines + funding)
data/cache/             generated parquet (git-ignored) — built by datafeed.py
data/*.log              console logs of past runs
src/                    all code (flat; scripts import each other via sys.path)
```

### `src/` by role

| Role | Files |
|---|---|
| Config | `config.py` — paths, costs, risk, session, walk-forward sizes |
| Data | `datafeed.py` (download + cache + `validate()`), `verify_resample.py`, `show_bars.py` |
| Core library | `indicators.py` (causal indicators), `strategies.py` (rule zoo, `REGISTRY`), `backtest.py` (`run_backtest`, `compute_metrics`), `ml_filter.py` (features + outcome labels), `experiment.py` (`get_bars`, `load_funding`, splits, `evaluate`) |
| Tests | `test_engine.py` — hand-computed trade, differential test, cost monotonicity, no-look-ahead, post-only fills |
| Experiments (one per journal entry) | `sweep.py` (Exp 003), `diagnose.py` (003), `cost_lab.py` (004), `round2_stopwidth.py` (004b), `run_ml.py` (006), `final_eval.py` / `definitive.py` (007/010), `round3_maker.py` (008/010), `round4_holdperiod.py` (009) |
| Reporting | `ledger.py`, `ledger_report.py`, `report_data.py`, `make_report.py` |

Strategy contract (`strategies.py`): `fn(bars, **params) -> DataFrame[side,
stop_dist, tp_dist, max_hold]` where row `i` is the order to fill at bar
`i+1` open. `side` ∈ {-1, 0, +1}. Register new strategies in `REGISTRY`.

Key metric identity: `exp_r = gross_r - cost_r` (per trade, in R). Any row
where this does not hold is a bug — `ledger.verify_arithmetic()` checks it.

---

## 3. Commands

Python 3.11+ (developed on 3.13). Scripts are run from the repo root.

```bash
pip install -r requirements.txt

python src/test_engine.py            # must pass before trusting any number
python src/datafeed.py               # build data/cache/*.parquet from data/raw (+ download missing)
python src/verify_resample.py        # diff vs native Binance files (needs network)

python src/sweep.py 20               # Exp 003 leak-free sweep
python src/cost_lab.py               # Exp 004
python src/round2_stopwidth.py       # Exp 004b
python src/run_ml.py 15 2.0          # Exp 006  (tf minutes, stop scale)
python src/definitive.py 15 "1.0,2.0,3.5,5.0"   # Exp 007/010 headline
python src/round3_maker.py 15        # Exp 008/010 post-only
python src/round4_holdperiod.py      # Exp 009

python src/ledger.py                 # rebuild results/ledger.csv
python src/ledger_report.py          # rebuild journal/ledger.md
python src/report_data.py && python src/make_report.py   # rebuild report.html
```

Heavy scripts use multiprocessing and set `OMP_NUM_THREADS=1` etc. before
importing numpy — keep that at the top of any new parallel script.

---

## 4. Journal entry template

Append to `journal/experiments.md`, numbering sequentially (next is **Exp 011**):

```markdown
---

## Exp NNN — <one-line title>

**Date:** YYYY-MM-DD
**Status:** running | complete | superseded by Exp MMM

### Hypothesis
What you expect and why. State it before looking at results.

### Method
Script + exact command, data window, split (train/test/walk-forward),
timeframe, stop scale, execution mode, number of configs tried.

### Result
Table with trades, gross_r, cost_r, exp_r, 95% CI, CAGR, maxDD.
Results file: `results/<file>.csv`, log: `data/<file>.log`.

### Verdict
KEEP | WATCH | REJECT | INCONCLUSIVE — with one paragraph of reasoning.
```

Verdict vocabulary: `KEEP` survived OOS with acceptable drawdown; `WATCH`
promising, not verified OOS; `REJECT` failed; `INCONCLUSIVE` not decisive.

---

## 5. Working style

- Measure before optimising; profile the whole pipeline (Exp 002: the slow
  part was an indicator, not the backtest loop).
- When a number surprises you, look for a bug first (Exp 001, 008, 010).
- Prefer small, verified changes. Rerun `test_engine.py` after each.
- Keep code style consistent with the existing files: plain numpy/pandas,
  no TA libraries, docstrings that explain *why*, `from __future__ import
  annotations`, type hints on public functions.
- Write the journal in English. `report.html` is in Thai for the owner.
