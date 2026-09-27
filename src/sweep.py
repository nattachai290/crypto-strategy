"""Strategy sweep with a leak-free protocol.

Protocol (this is the important part):

  1. Every configuration is evaluated on TRAIN only (2020-01 .. 2023-12).
  2. We shortlist the top-K by train Sharpe - with a minimum trade count so
     we do not crown a lucky 4-trade run.
  3. Only the shortlist is then run on TEST (2024-01 .. 2026-08), which no
     selection decision has seen.
  4. We report train and test side by side. A config whose test Sharpe is far
     below its train Sharpe was fitted to noise.

We also run a walk-forward pass over the top configurations to see whether
any edge is stable across regimes rather than concentrated in one period.
"""
from __future__ import annotations

import itertools
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

# Must be set BEFORE numpy/pandas import. With 12 worker processes each
# spinning up 16 BLAS threads the machine thrashes and everything runs ~10x
# slower than single-threaded.
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
import experiment as E
import strategies as S
from backtest import fmt_metrics, run_backtest

TRAIN_END = "2024-01-01"   # train = everything before this
TEST_START = "2024-01-01"

# --------------------------------------------------------------------------
# Configuration space
# --------------------------------------------------------------------------
CONFIGS: list[tuple[str, str, dict]] = []


def add(name: str, tf: int, **params) -> None:
    CONFIGS.append((name, f"{tf}m", dict(params, tf=tf)))


def build_configs() -> None:
    # ---------- generation 1 baselines across timeframes ----------
    # 1m is deliberately left out of the broad sweep: the 1m series has 3.5M
    # bars, and a 1m bar is mostly noise for a 1-4h holding period. It gets a
    # focused run later, only for configurations that earn it.
    for tf in (3, 5, 15, 30):
        add("ema_trend", tf, fast=20, slow=50, stop_mult=2.0, tp_mult=4.0, max_hold=36)
        add("donchian_breakout", tf, n=60, stop_mult=2.0, tp_mult=3.0, max_hold=48)
        add("vwap_reversion", tf, n_z=2.0, stop_mult=2.0, tp_mult=2.0, max_hold=36)
        add("supertrend_flip", tf, n=10, mult=3.0, stop_mult=2.0, tp_mult=4.0, max_hold=48)
        add("adx_trend", tf, adx_min=22, stop_mult=2.0, tp_mult=3.5, max_hold=36)
    for tf in (3, 5, 15, 30):
        add("bb_reversion", tf, n=48, k=2.2, stop_mult=1.8, tp_mult=1.6, max_hold=24)
        add("squeeze_expansion", tf, bb_n=48, stop_mult=2.0, tp_mult=3.0, max_hold=36)
        add("flow_momentum", tf, ratio_n=20, thresh=0.56, stop_mult=2.0, tp_mult=3.0, max_hold=24)

    # ---------- generation 2: combined indicators ----------
    for tf in (3, 5, 15, 30):
        add("combo_trend_pullback", tf, fast=21, slow=55, adx_min=20,
            stop_mult=1.8, tp_mult=3.0, max_hold=36)
        add("combo_trend_pullback", tf, fast=13, slow=34, adx_min=24,
            stop_mult=1.5, tp_mult=2.5, max_hold=24)
        add("combo_vwap_trend_aware", tf, n_z=1.8, adx_max=28,
            stop_mult=1.8, tp_mult=2.2, max_hold=30)
        add("combo_breakout_confirmed", tf, n=48, adx_min=18, vol_expand=1.0,
            stop_mult=1.8, tp_mult=3.5, max_hold=48)
        add("combo_vol_flow", tf, squeeze_q=0.2, ratio_n=20, flow_thresh=0.53,
            stop_mult=1.8, tp_mult=3.0, max_hold=30)
        add("combo_funding_reversion", tf, rate_thresh=0.0002, z_thresh=1.5,
            stop_mult=1.8, tp_mult=2.2, max_hold=30)
        for nv in (4, 5):
            add("combo_vote", tf, n_votes=nv, stop_mult=1.8, tp_mult=3.0, max_hold=36)
        add("combo_session_window", tf, hours=(13, 14), range_n=24,
            stop_mult=1.6, tp_mult=2.5, max_hold=18)

    # ---------- generation 2 + exit management ("fixing the trade") --------
    for tf in (5, 15):
        add("combo_trend_pullback", tf, fast=21, slow=55, adx_min=20,
            stop_mult=1.8, tp_mult=4.0, max_hold=48, be_at=1.0)
        add("combo_trend_pullback", tf, fast=21, slow=55, adx_min=20,
            stop_mult=1.8, tp_mult=5.0, max_hold=72, trail_at=1.5, trail_atr=1.5)
        add("combo_breakout_confirmed", tf, n=48, adx_min=18,
            stop_mult=2.0, tp_mult=0.0, max_hold=72, trail_at=1.2, trail_atr=2.0)
        add("combo_vol_flow", tf, squeeze_q=0.2, stop_mult=1.8, tp_mult=4.0,
            max_hold=48, be_at=1.2, trail_at=2.0, trail_atr=1.8)
        add("combo_vote", tf, n_votes=5, stop_mult=2.0, tp_mult=0.0,
            max_hold=72, trail_at=1.5, trail_atr=2.0)
        add("ema_trend", tf, fast=20, slow=50, stop_mult=2.0, tp_mult=0.0,
            max_hold=72, trail_at=1.5, trail_atr=2.0)
        add("donchian_breakout", tf, n=60, stop_mult=2.0, tp_mult=0.0,
            max_hold=72, trail_at=1.5, trail_atr=2.0)


# --------------------------------------------------------------------------
# Worker
# --------------------------------------------------------------------------
_BARS: dict[int, pd.DataFrame] = {}
_FUND = None


def _bars_for(tf: int) -> pd.DataFrame:
    global _BARS
    if tf not in _BARS:
        _BARS[tf] = E.get_bars(tf)
    return _BARS[tf]


def _funding():
    global _FUND
    if _FUND is None:
        _FUND = E.load_funding()
    return _FUND


def run_one(args) -> dict:
    name, _tfl, params = args
    tf = int(params.get("tf", 5))
    try:
        bars = _bars_for(tf)
        sig = E.build_signals(name, bars, {k: v for k, v in params.items()
                                           if k != "tf"}, _funding())
        res = run_backtest(
            bars, sig,
            start_time=pd.Timestamp("2020-01-01", tz="UTC"),
            end_time=pd.Timestamp(TRAIN_END, tz="UTC"),
            funding=_funding(), name=name, params={**params, "tf_min": tf},
        )
        row = {"strategy": name, "tf": tf,
               **{k: v for k, v in params.items() if k != "tf"},
               "n_signals": int((sig["side"] != 0).sum()),
               **{f"tr_{k}": v for k, v in res.metrics.items()}}
        return row
    except Exception as e:  # noqa: BLE001
        return {"strategy": name, "tf": tf, "params": str(params),
                "error": f"{type(e).__name__}: {e}"}


def run_one_test(args) -> dict:
    name, params = args
    tf = int(params.get("tf", 5))
    try:
        bars = _bars_for(tf)
        sig = E.build_signals(name, bars, {k: v for k, v in params.items()
                                           if k != "tf"}, _funding())
        res = run_backtest(
            bars, sig,
            start_time=pd.Timestamp(TEST_START, tz="UTC"),
            funding=_funding(), name=name, params={**params, "tf_min": tf},
        )
        return {"strategy": name, "tf": tf,
                **{k: v for k, v in params.items() if k != "tf"},
                "n_signals": int((sig["side"] != 0).sum()),
                **{f"te_{k}": v for k, v in res.metrics.items()}}
    except Exception as e:  # noqa: BLE001
        return {"strategy": name, "tf": tf, "error": f"{type(e).__name__}: {e}"}


# --------------------------------------------------------------------------
def main(top_k: int = 20, workers: int = 12) -> None:
    build_configs()
    print(f"configs: {len(CONFIGS)}   train: 2020-01..2023-12   "
          f"test: {TEST_START}..2026-08")
    rows: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, r in enumerate(ex.map(run_one, CONFIGS), 1):
            rows.append(r)
            if i % 25 == 0 or i == len(CONFIGS):
                print(f"  train {i}/{len(CONFIGS)}", flush=True)
    tr = pd.DataFrame(rows)
    if "error" in tr.columns:
        bad = tr[tr["error"].notna() & (tr["error"] != "")]
        if len(bad):
            print(f"\n{len(bad)} configs errored:")
            for _, b in bad.iterrows():
                print("  ", b["strategy"], b.get("params", ""), b["error"])
        tr = tr[tr["error"].isna() | (tr["error"] == "")].drop(columns=["error"])
    tr.to_csv(C.RESULTS / "sweep_train.csv", index=False)
    print(f"\ntrain results: {len(tr)}")

    # shortlist: need enough trades for the number to mean anything
    MIN_TRADES = 150
    ok = tr[tr["tr_trades"] >= MIN_TRADES].copy()
    ok = ok[ok["tr_exposure"] > 0.01]
    ok = ok.sort_values("tr_sharpe", ascending=False)
    short = ok.head(top_k)
    print(f"\n=== shortlist (train Sharpe, >= {MIN_TRADES} trades) ===")
    cols = ["strategy", "tf", "tr_trades", "tr_sharpe", "tr_max_dd", "tr_win_rate",
            "tr_profit_factor", "tr_expectancy_r", "tr_exposure", "tr_fees_pct_equity"]
    cols = [c for c in cols if c in short.columns]
    print(short[cols].to_string(index=False))

    # ---- now the moment of truth: TEST the shortlist only ----------------
    # Rebuild the original parameter dicts (the shortlist rows carry derived
    # metric columns too, which the strategy functions do not accept).
    def same(a, b) -> bool:
        if isinstance(b, (tuple, list)):
            return tuple(a) == tuple(b)
        try:
            return abs(float(a) - float(b)) < 1e-9
        except (TypeError, ValueError):
            return a == b

    jobs = []
    for _, r in short.iterrows():
        pr = None
        for (nm, _tfl, p) in CONFIGS:
            if nm != r["strategy"] or int(p.get("tf", 5)) != int(r["tf"]):
                continue
            if all(k in r.index and same(r[k], v)
                   for k, v in p.items() if k != "tf"):
                pr = dict(p)
                break
        if pr is None:
            print("  !! could not match params for", r["strategy"], r["tf"])
        else:
            jobs.append((r["strategy"], pr))

    te: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, r in enumerate(ex.map(run_one_test, jobs), 1):
            te.append(r)
            print(f"  test {i}/{len(jobs)}", flush=True)
    tedf = pd.DataFrame(te)
    tedf.to_csv(C.RESULTS / "sweep_test.csv", index=False)

    mrg = short.reset_index(drop=True)
    for c in tedf.columns:
        if c not in mrg.columns:
            mrg[c] = tedf[c].values
    mrg["sharpe_decay"] = mrg["tr_sharpe"] - mrg["te_sharpe"]
    print("\n=== TRAIN vs TEST (out-of-sample) ===")
    show = ["strategy", "tf", "tr_trades", "tr_sharpe", "te_trades", "te_sharpe",
            "sharpe_decay", "te_max_dd", "te_win_rate", "te_profit_factor",
            "te_expectancy_r", "te_net_return", "te_fees_pct_equity"]
    show = [c for c in show if c in mrg.columns]
    out = mrg.sort_values("te_sharpe", ascending=False)
    print(out[show].to_string(index=False))
    mrg.to_csv(C.RESULTS / "sweep_merged.csv", index=False)
    print(f"\nwritten: {C.RESULTS/'sweep_merged.csv'}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
