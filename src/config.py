"""
Global config for USDT-M futures day-trading research (one symbol per run).

All costs are deliberately set to realistic/conservative values so that
backtest results are not inflated. Change nothing here without writing a
note in journal/<SYMBOL>/experiments.md.
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

# --------------------------------------------------------------------------
# Instrument. One symbol per run, chosen with the SYMBOL environment variable:
#     SYMBOL=ETHUSDT python src/sweep.py
# Every data/result/journal path below is split per symbol so coins never mix.
# To add a coin, add its exchange specs here first (see AGENTS.md).
# --------------------------------------------------------------------------
SYMBOL_SPECS: dict[str, dict] = {
    "BTCUSDT": dict(
        qty_step=0.001,       # contract quantity step
        min_notional=5.0,     # Binance min notional (rounded up)
        data_start="2020-01", # first monthly file used
        data_end="2026-08",   # last monthly file used
        # evaluate.py splits:  TRAIN [data_start, valid_start)
        #                      VALID [valid_start, holdout_start)
        #                      HOLDOUT [holdout_start, data_end]  (locked)
        valid_start="2023-01",
        holdout_start="2025-01",
    ),
}
SYMBOL = os.environ.get("SYMBOL", "BTCUSDT").upper()
if SYMBOL not in SYMBOL_SPECS:
    raise SystemExit(f"unknown SYMBOL {SYMBOL!r}; add it to SYMBOL_SPECS in "
                     f"src/config.py (known: {', '.join(SYMBOL_SPECS)})")
SPEC = SYMBOL_SPECS[SYMBOL]
MARKET = "um"  # USDT-margined

# --------------------------------------------------------------------------
# Paths - shared code in src/, everything symbol-specific under <dir>/<SYMBOL>/
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / SYMBOL          # Binance zips (git-ignored)
CACHE = ROOT / "data" / "cache" / SYMBOL      # parquet (git-ignored)
RESULTS = ROOT / "results" / SYMBOL           # evaluate.py records (current workflow)
LEGACY = RESULTS / "legacy"                   # Exp 003-010 scripts' CSVs, report, logs/
JOURNAL = ROOT / "journal" / SYMBOL           # STATUS, experiments, evaluations, ledger

for _d in (RAW, CACHE, RESULTS, LEGACY, JOURNAL):
    _d.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Data source (Binance public data / S3)
# --------------------------------------------------------------------------
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
WEB = "https://data.binance.vision/data"

# Data window (monthly files), per symbol
DATA_START = SPEC["data_start"]
DATA_END = SPEC["data_end"]

# Raw kline columns for Binance futures (no header in file)
KLINE_COLS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades", "taker_buy_base",
    "taker_buy_quote", "ignore",
]
FUNDING_COLS = [
    "calc_time", "funding_interval_hours", "last_funding_rate",
]

# --------------------------------------------------------------------------
# Account / risk
# --------------------------------------------------------------------------
INITIAL_EQUITY = 100.0        # USDT
RISK_PER_TRADE = 0.01         # 1% of current equity risked per trade
MAX_LEVERAGE = 10.0           # hard cap on notional / equity
# The engine is deliberately single-position: one open trade at a time, no
# pyramiding. Multiple concurrent positions would need the position state
# refactored into a list, and that is not worth the risk to a verified engine.
# Trade frequency is instead increased via max_hold (see Exp 009).
MAX_CONCURRENT = 1
MIN_NOTIONAL = SPEC["min_notional"]
QTY_STEP = SPEC["qty_step"]

# --------------------------------------------------------------------------
# Costs (VIP0 USDT-M futures)
# --------------------------------------------------------------------------
FEE_MAKER = 0.0002            # 0.02%
FEE_TAKER = 0.0005            # 0.05%
# Slippage applied against us on every fill. Market orders on BTCUSDT
# futures during liquid hours are ~0.01-0.02%; use 0.02% baseline.
SLIPPAGE = 0.0002             # 0.02% per fill, charged on notional

# Conservative intrabar assumption: if a candle's range touches both the
# stop and the target, we fill the STOP first (pessimistic).
# Set True = pessimistic (default), False = optimistic.
PESSIMISTIC_INTRABAR = True

# --------------------------------------------------------------------------
# Day-trade session filter (UTC). BTC is 24/7 but "day trade" means we
# choose not to hold across these boundaries.
# --------------------------------------------------------------------------
# Hours [start, end) during which trading is allowed, UTC.
SESSION_START_HOUR = 0
SESSION_END_HOUR = 24
# Flat all positions at session end (True = pure intraday, no overnight)
FLAT_AT_SESSION_END = True
# Optional cooldown after a stop (minutes). 0 = off
COOLDOWN_AFTER_STOP_BAR = 0

# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------
# Walk-forward splits: (train_end, test_end) as YYYY-MM
# Train = 24 months, test = 6 months, step = 6 months
WF_TRAIN_MONTHS = 24
WF_TEST_MONTHS = 6
# evaluate.py - the standard research gate (see AGENTS.md). Changing any of
# these makes old and new verdicts incomparable: journal it first.
VALID_START = SPEC["valid_start"]
HOLDOUT_START = SPEC["holdout_start"]
EVAL_MAX_GRID = 64            # max parameter combinations per idea
EVAL_MIN_TRAIN_TRADES = 100   # a combo needs this many train trades to be eligible
EVAL_MIN_VALID_TRADES = 100   # PASS needs this many validation trades
EVAL_MIN_ANY_TRADES = 30      # below this the verdict is INCONCLUSIVE
EVAL_STRESS_COST = 1.5        # fees and slippage x this for the stress test
EVAL_MAX_DD = 0.20            # PASS needs validation max drawdown <= this
EVAL_BOOTSTRAP = 10000        # bootstrap resamples for the CI
EVAL_MAX_VERSIONS = 3         # evaluations allowed per idea STRUCTURE (evaluate.signature)

# Annualisation factor for minute bars
MINUTES_PER_YEAR = 365 * 24 * 60


def month_range(start: str = DATA_START, end: str = DATA_END) -> list[str]:
    y, m = int(start[:4]), int(start[5:7])
    ey, em = int(end[:4]), int(end[5:7])
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def mstart(month: str) -> dt.datetime:
    return dt.datetime.strptime(month + "-01", "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)


def mend(month: str) -> dt.datetime:
    y, m = int(month[:4]), int(month[5:7])
    return dt.datetime(y + (m == 12), (m % 12) + 1, 1, tzinfo=dt.timezone.utc)
