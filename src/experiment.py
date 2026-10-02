"""Experiment runner: load data, resample, walk-forward evaluate, log results."""
from __future__ import annotations

import json
import sys
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
import strategies as S
from backtest import fmt_metrics, run_backtest

_CACHE: dict = {}


# --------------------------------------------------------------------------
# Data loading / resampling
# --------------------------------------------------------------------------
def load_raw() -> pd.DataFrame:
    """1m klines, exactly as Binance published them."""
    if "raw" in _CACHE:
        return _CACHE["raw"]
    p = C.CACHE / f"{C.SYMBOL}_klines_1m.parquet"
    df = pd.read_parquet(p)
    df = df.set_index("open_time").sort_index()
    df.index.name = "time"
    keep = ["open", "high", "low", "close", "volume", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote"]
    df = df[keep].astype("float64")
    _CACHE["raw"] = df
    return df


def load_native(tf: int) -> pd.DataFrame:
    """Load Binance's own klines for `tf`. Never derived, never resampled."""
    key = f"native{tf}"
    if key in _CACHE:
        return _CACHE[key]
    name = {1: "1m", 3: "3m", 5: "5m", 15: "15m", 30: "30m",
            60: "1h", 120: "2h", 240: "4h"}.get(tf, f"{tf}m")
    p = C.CACHE / f"{C.SYMBOL}_klines_{name}.parquet"
    if not p.exists():
        raise FileNotFoundError(
            f"Binance's native {name} klines are not downloaded.\n"
            f"  expected: {p}\n"
            f"  fetch them with:  python src\\datafeed.py\n"
            f"This project does not resample: derived bars once produced a "
            f"silent one-bar offset that invalidated every result "
            f"(journal Exp 010).")
    df = pd.read_parquet(p)
    df = df.set_index("open_time").sort_index()
    df.index.name = "time"
    keep = ["open", "high", "low", "close", "volume", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote"]
    df = df[keep].astype("float64")
    _CACHE[key] = df
    return df


def load_funding() -> pd.DataFrame | None:
    if "funding" in _CACHE:
        return _CACHE["funding"]
    p = C.CACHE / f"{C.SYMBOL}_funding.parquet"
    if not p.exists():
        _CACHE["funding"] = None
        return None
    f = pd.read_parquet(p)
    f["calc_time"] = pd.to_datetime(f["calc_time"], unit="ms", utc=True)
    f = f.sort_values("calc_time").reset_index(drop=True)
    _CACHE["funding"] = f
    return f


# Metrics columns attached to the bars (PLAN.md section 14), renamed from
# Binance's file. Ratios are long/short: > 1 means more longs.
METRIC_NAMES = {
    "sum_open_interest": "oi",                        # open interest, in coins
    "sum_open_interest_value": "oi_usd",              # open interest, in USDT
    "count_toptrader_long_short_ratio": "top_acct_ls",  # top traders, by accounts
    "sum_toptrader_long_short_ratio": "top_pos_ls",     # top traders, by position size
    "count_long_short_ratio": "acct_ls",              # all accounts
    "sum_taker_long_short_vol_ratio": "taker_ls",     # taker buy / sell volume
}
METRIC_LAG = pd.Timedelta(minutes=5)       # a row is used only 5 min after its create_time
METRIC_TOLERANCE = pd.Timedelta(minutes=30)  # older than this at bar close -> NaN


def load_metrics() -> pd.DataFrame | None:
    """The metrics cache (python src/datafeed.py --metrics), or None."""
    if "metrics" in _CACHE:
        return _CACHE["metrics"]
    p = C.CACHE / f"{C.SYMBOL}_metrics.parquet"
    m = None
    if p.exists():
        m = pd.read_parquet(p)
        m["create_time"] = pd.to_datetime(m["create_time"], utc=True)
        m = m.sort_values("create_time").rename(columns=METRIC_NAMES)
    _CACHE["metrics"] = m
    return m


def attach_metrics(bars: pd.DataFrame, metrics: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Add the metrics columns to `bars`, causally.

    The bar opening at t closes at t + minutes; its signal is filled at the
    next open. It may only see a metrics row whose create_time + METRIC_LAG <=
    t + minutes: the 5-minute lag is deliberate caution, because Binance does
    not document whether create_time is the start or the end of the sample.
    A row older than METRIC_TOLERANCE at the bar close (a gap in Binance's
    file) gives NaN, never a stale value, and bars before metrics_start are
    NaN. Blocks read NaN as 'no signal'."""
    cols = list(METRIC_NAMES.values())
    right = metrics[["create_time"] + cols].copy()
    ns = "datetime64[ns, UTC]"  # both sides at one resolution, or merge_asof refuses
    right["avail"] = (right["create_time"] + METRIC_LAG).astype(ns)
    right = right.sort_values("avail")
    left = pd.DataFrame({"close_time": (bars.index + pd.Timedelta(minutes=minutes)).astype(ns)})
    left["_i"] = np.arange(len(left))
    got = pd.merge_asof(left.sort_values("close_time"), right.drop(columns="create_time"),
                        left_on="close_time", right_on="avail", direction="backward",
                        tolerance=METRIC_TOLERANCE).sort_values("_i")
    out = bars.copy()
    for c in cols:
        out[c] = got[c].to_numpy(float)
    return out


PREMIUM_LAG = pd.Timedelta(minutes=2)       # an hourly candle is used 2 min after it closes
PREMIUM_TOLERANCE = pd.Timedelta(hours=3)   # older than this at the bar close -> NaN


def load_premium(symbol: str | None = None) -> pd.DataFrame | None:
    """A symbol's Coinbase premium cache (python src/datafeed.py --premium), or None."""
    symbol = symbol or C.SYMBOL
    key = f"premium_{symbol}"
    if key in _CACHE:
        return _CACHE[key]
    p = C.ROOT / "data" / "cache" / symbol / f"{symbol}_premium.parquet"
    m = pd.read_parquet(p) if p.exists() else None
    if m is not None:
        m["time"] = pd.to_datetime(m["time"], utc=True)
        m = m.sort_values("time")
    _CACHE[key] = m
    return m


def attach_premium(bars: pd.DataFrame, prem: pd.DataFrame, minutes: int, col: str) -> pd.DataFrame:
    """Add `col` = the Coinbase premium, causally: the hourly candle opening at
    H is complete at H + 1h and is used from H + 1h + PREMIUM_LAG; a bar may
    only see candles available at its own close. Stale (> PREMIUM_TOLERANCE)
    or missing hours give NaN."""
    ns = "datetime64[ns, UTC]"
    right = pd.DataFrame({"avail": (prem["time"] + pd.Timedelta(hours=1) + PREMIUM_LAG).astype(ns),
                          col: prem["premium"].to_numpy(float)}).sort_values("avail")
    left = pd.DataFrame({"close_time": (bars.index + pd.Timedelta(minutes=minutes)).astype(ns)})
    left["_i"] = np.arange(len(left))
    got = pd.merge_asof(left.sort_values("close_time"), right, left_on="close_time", right_on="avail",
                        direction="backward", tolerance=PREMIUM_TOLERANCE).sort_values("_i")
    out = bars.copy()
    out[col] = got[col].to_numpy(float)
    return out


def get_bars(minutes: int) -> pd.DataFrame:
    """Binance's published klines for this timeframe.

    Deliberately has NO resampling path. The previous version derived every
    timeframe from the 1m file, and although a fixed version of that resampler
    matched Binance byte-for-byte, the original one silently shifted every bar
    by one window - and nine experiments were run on it before anyone
    compared the output to the source. Loading the native file removes the
    whole class of error.
    """
    key = f"bars{minutes}"
    if key in _CACHE:
        return _CACHE[key]
    bars = load_native(minutes)
    # PLAN.md section 14: when the metrics cache exists, its columns ride on
    # the bars (oi, oi_usd, top_acct_ls, top_pos_ls, acct_ls, taker_ls). The
    # engine never reads them; only the metrics blocks in recipes.py do.
    m = load_metrics()
    if m is not None:
        bars = attach_metrics(bars, m, minutes)
    # PLAN.md section 25: Coinbase premium, own coin (cb_prem) and BTC's
    # (cb_prem_btc), when their caches exist. Only the premium blocks read them.
    p = load_premium()
    if p is not None:
        bars = attach_premium(bars, p, minutes, "cb_prem")
    pb = load_premium("BTCUSDT")
    if pb is not None:
        bars = attach_premium(bars, pb, minutes, "cb_prem_btc")
    _CACHE[key] = bars
    return bars


# --------------------------------------------------------------------------
# Walk-forward splits
# --------------------------------------------------------------------------
def walk_forward_splits() -> list[dict]:
    months = C.month_range()
    splits = []
    i = 0
    while i + C.WF_TRAIN_MONTHS + C.WF_TEST_MONTHS <= len(months):
        tr = months[i: i + C.WF_TRAIN_MONTHS]
        te = months[i + C.WF_TRAIN_MONTHS: i + C.WF_TRAIN_MONTHS + C.WF_TEST_MONTHS]
        splits.append({
            "fold": len(splits) + 1,
            "train": (C.mstart(tr[0]), C.mend(tr[-1])),
            "test": (C.mstart(te[0]), C.mend(te[-1])),
            "train_label": f"{tr[0]}..{tr[-1]}",
            "test_label": f"{te[0]}..{te[-1]}",
        })
        i += C.WF_TEST_MONTHS
    return splits


def long_split() -> dict:
    """Single 50/50 chronological split: research on the first half, verify on the second."""
    months = C.month_range()
    half = len(months) // 2
    tr, te = months[:half], months[half:]
    return {
        "train": (C.mstart(tr[0]), C.mend(tr[-1])),
        "test": (C.mstart(te[0]), C.mend(te[-1])),
        "train_label": f"{tr[0]}..{tr[-1]}",
        "test_label": f"{te[0]}..{te[-1]}",
    }


# --------------------------------------------------------------------------
# Evaluation helpers
# --------------------------------------------------------------------------
def build_signals(name: str, bars: pd.DataFrame, params: dict,
                  funding: pd.DataFrame | None) -> pd.DataFrame:
    fn = S.REGISTRY[name]
    if name in S.NEEDS_FUNDING:
        return fn(bars, funding=funding, **params)
    return fn(bars, **params)


def evaluate(name: str, params: dict, minutes: int, *, split: dict | None = None,
             tag: str = "", verbose: bool = True) -> dict:
    bars = get_bars(minutes)
    funding = load_funding()
    sig = build_signals(name, bars, params, funding)
    res = run_backtest(
        bars, sig,
        start_time=split["train"][0] if split else None,
        end_time=split["train"][1] if split else None,
        name=name, params={**params, "tf_min": minutes},
    )
    row = {
        "strategy": name, "tf": minutes, "tag": tag,
        **{k: v for k, v in params.items()},
        **res.metrics,
    }
    if verbose:
        lbl = split["train_label"] if split else "FULL"
        print(f"{name:<20} {str(params):<52} [{lbl}]")
        print(f"    {fmt_metrics(res.metrics)}")
    return row


def append_result(row: dict, path: Path | None = None) -> None:
    path = path or (C.LEGACY / "results.csv")
    df = pd.DataFrame([row])
    if path.exists():
        old = pd.read_csv(path)
        df = pd.concat([old, df], ignore_index=True)
    df.to_csv(path, index=False)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    if cmd == "baseline":
        run_baseline()


# --------------------------------------------------------------------------
# Baseline sweep: every rule strategy on a few timeframes, full sample
# --------------------------------------------------------------------------
BASELINES: list[tuple[str, dict, list[int]]] = [
    ("ema_trend", dict(fast=20, slow=50, stop_mult=2.0, tp_mult=4.0, max_hold=36), [5, 15]),
    ("ema_trend", dict(fast=9, slow=21, stop_mult=1.5, tp_mult=2.5, max_hold=24), [5, 15]),
    ("donchian_breakout", dict(n=60, stop_mult=2.0, tp_mult=3.0, max_hold=48), [5, 15]),
    ("donchian_breakout", dict(n=24, stop_mult=1.5, tp_mult=2.0, max_hold=24), [5, 15]),
    ("vwap_reversion", dict(n_z=2.0, stop_mult=2.0, tp_mult=2.0, max_hold=36), [5, 15]),
    ("bb_reversion", dict(n=48, k=2.2, stop_mult=1.8, tp_mult=1.6, max_hold=24), [5, 15]),
    ("supertrend_flip", dict(n=10, mult=3.0, stop_mult=2.0, tp_mult=4.0, max_hold=48), [5, 15]),
    ("squeeze_expansion", dict(bb_n=48, stop_mult=2.0, tp_mult=3.0, max_hold=36), [5, 15]),
    ("session_breakout", dict(session_hours=(8,), stop_mult=1.8, tp_mult=2.5, max_hold=24), [5]),
    ("flow_momentum", dict(ratio_n=20, thresh=0.56, stop_mult=2.0, tp_mult=3.0, max_hold=24), [5, 15]),
    ("adx_trend", dict(adx_min=22, stop_mult=2.0, tp_mult=3.5, max_hold=36), [5, 15]),
]


def run_baseline() -> pd.DataFrame:
    rows = []
    for name, params, tfs in BASELINES:
        for tf in tfs:
            try:
                row = evaluate(name, params, tf, tag="baseline_full")
                rows.append(row)
                append_result(row)
            except Exception as e:  # noqa: BLE001
                print(f"{name} tf={tf} FAILED: {e}")
    df = pd.DataFrame(rows)
    if len(df):
        cols = ["strategy", "tf", "trades", "net_return", "cagr", "sharpe",
                "max_dd", "win_rate", "profit_factor", "expectancy_r",
                "fees_pct_equity", "exposure"]
        cols = [c for c in cols if c in df.columns]
        print("\n=== SUMMARY (full sample) ===")
        print(df[cols].sort_values("sharpe", ascending=False).to_string(index=False))
        df.to_csv(C.LEGACY / "baseline_summary.csv", index=False)
    return df


if __name__ == "__main__":
    main()
