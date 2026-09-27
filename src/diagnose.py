"""Diagnostics: is a strategy actually good, or just not yet caught out?

A positive out-of-sample Sharpe on 130 trades is not evidence. These four
checks are what separate "maybe real" from "noise":

  1. WALK-FORWARD over the whole 6.5 years, not a single split. An edge that
     only exists in one regime is not an edge.
  2. COST SENSITIVITY. Run the same signals with zero cost and with double
     cost. If the strategy is already dead at zero cost there is no edge to
     rescue; if it is alive at zero cost but dead at realistic cost, the
     problem is turnover, and the fix is fewer/bigger trades.
  3. COST IN R. Convert the round-trip cost into R units. This is the single
     most useful number in intraday futures: if the round trip costs 0.35R,
     the strategy needs to be right by 0.35R before it makes anything, and no
     amount of signal cleverness changes that arithmetic.
  4. BOOTSTRAP CI on expectancy. Resample the trade R-series with replacement
     to get a confidence interval. If the interval straddles zero, the honest
     answer is "unknown", not "profitable".
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
import experiment as E
from backtest import fmt_metrics, run_backtest


# --------------------------------------------------------------------------
def walk_forward(name: str, params: dict, tf: int, train_m: int = 24,
                 test_m: int = 6, verbose: bool = True) -> pd.DataFrame:
    """Roll through history: fit-free, so 'train' only defines the window."""
    bars = E.get_bars(tf)
    funding = E.load_funding()
    sig = E.build_signals(name, bars, {k: v for k, v in params.items() if k != "tf"},
                          funding)
    months = C.month_range()
    rows = []
    i = 0
    while i + train_m + test_m <= len(months):
        te0 = C.mstart(months[i + train_m])
        te1 = C.mend(months[i + train_m + test_m - 1])
        res = run_backtest(bars, sig, start_time=te0, end_time=te1, funding=funding)
        rows.append({"fold": len(rows) + 1,
                     "test": f"{months[i+train_m]}..{months[i+train_m+test_m-1]}",
                     **res.metrics})
        i += test_m
    df = pd.DataFrame(rows)
    if verbose and len(df):
        print(f"\n  walk-forward folds for {name} {tf}m ({len(df)} folds)")
        print("   " + "  ".join(
            f"{r['test'][:7]}:{r['sharpe']:+.2f}/{r['trades']}t" for _, r in df.iterrows()))
        pos = (df["sharpe"] > 0).sum()
        print(f"   positive folds: {pos}/{len(df)}   "
              f"median Sharpe {df['sharpe'].median():+.3f}   "
              f"total return {df['net_return'].sum()*100:+.1f}%   "
              f"worst DD {df['max_dd'].max()*100:.1f}%")
    return df


# --------------------------------------------------------------------------
def cost_sensitivity(name: str, params: dict, tf: int,
                     start: str = "2020-01-01") -> pd.DataFrame:
    bars = E.get_bars(tf)
    funding = E.load_funding()
    sig = E.build_signals(name, bars, {k: v for k, v in params.items() if k != "tf"},
                          funding)
    st = pd.Timestamp(start, tz="UTC")
    cases = [
        ("free", dict(fee_taker=0.0, slippage=0.0)),
        ("half", dict(fee_taker=C.FEE_TAKER / 2, slippage=C.SLIPPAGE / 2)),
        ("real", dict(fee_taker=C.FEE_TAKER, slippage=C.SLIPPAGE)),
        ("double", dict(fee_taker=C.FEE_TAKER * 2, slippage=C.SLIPPAGE * 2)),
    ]
    rows = []
    for label, kw in cases:
        r = run_backtest(bars, sig, start_time=st, funding=funding, **kw)
        rows.append({"cost": label, "fee": kw["fee_taker"], "slip": kw["slippage"],
                     **r.metrics})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
def cost_in_r(name: str, params: dict, tf: int, start: str = "2020-01-01") -> dict:
    """How many R units does the round trip cost, and what does the edge need?"""
    bars = E.get_bars(tf)
    funding = E.load_funding()
    sig = E.build_signals(name, bars, {k: v for k, v in params.items() if k != "tf"},
                          funding)
    r = run_backtest(bars, sig, start_time=pd.Timestamp(start, tz="UTC"), funding=funding)
    if not r.trades:
        return {}
    tdf = r.to_trades_df()
    notional_entry = (tdf["qty"] * tdf["entry_px"])
    atr_pct = (tdf["stop_px"] - tdf["entry_px"]).abs() / tdf["entry_px"]
    cost_px = 2 * (C.FEE_TAKER + C.SLIPPAGE)  # round trip, fraction of notional
    cost_r = cost_px / atr_pct                 # cost expressed in R
    gross_r = tdf["gross_pnl"].sum() / tdf["qty"].mul(0).add(1).sum() if False else None
    gross_sum_r = (tdf["gross_pnl"] / (tdf["qty"] * (tdf["stop_px"] - tdf["entry_px"]).abs())).sum()
    net_sum_r = tdf["r_multiple"].sum()
    fees_sum_r = (tdf["fees"] / (tdf["qty"] * (tdf["stop_px"] - tdf["entry_px"]).abs())).sum()
    wins = tdf[tdf["r_multiple"] > 0]["r_multiple"]
    losses = tdf[tdf["r_multiple"] <= 0]["r_multiple"]
    win_rate = len(wins) / len(tdf)
    avg_w = wins.mean() if len(wins) else 0.0
    avg_l = losses.mean() if len(losses) else 1.0
    breakeven_wr = avg_l / (avg_w + avg_l) if (avg_w + avg_l) > 0 else np.nan
    return {
        "strategy": name, "tf": tf, "trades": len(tdf),
        "stop_pct_median": float(atr_pct.median()),
        "roundtrip_cost_pct": cost_px,
        "cost_per_trade_R": float(cost_r.mean()),
        "gross_expectancy_R": float(gross_sum_r / len(tdf)),
        "fee_drag_R": float(fees_sum_r / len(tdf)),
        "net_expectancy_R": float(net_sum_r / len(tdf)),
        "win_rate": float(win_rate),
        "breakeven_win_rate": float(breakeven_wr),
        "edge_per_trade_R": float(gross_sum_r / len(tdf) - cost_r.mean()),
    }


# --------------------------------------------------------------------------
def bootstrap_ci(name: str, params: dict, tf: int, n: int = 20000,
                 start: str = "2020-01-01", seed: int = 0) -> dict:
    """CI on mean R per trade, resampling trades with replacement."""
    bars = E.get_bars(tf)
    funding = E.load_funding()
    sig = E.build_signals(name, bars, {k: v for k, v in params.items() if k != "tf"},
                          funding)
    r = run_backtest(bars, sig, start_time=pd.Timestamp(start, tz="UTC"), funding=funding)
    if len(r.trades) < 30:
        return {"strategy": name, "tf": tf, "trades": len(r.trades),
                "note": "too few trades for a bootstrap"}
    tdf = r.to_trades_df()
    x = tdf["r_multiple"].to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n, len(x)))
    means = x[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    p_pos = float((means > 0).mean())
    return {"strategy": name, "tf": tf, "trades": len(x),
            "mean_R": float(x.mean()), "ci_lo": float(lo), "ci_hi": float(hi),
            "p_mean_gt_0": p_pos,
            "verdict": "CI excludes 0" if lo > 0 or hi < 0 else "CI straddles 0"}


# --------------------------------------------------------------------------
def perturb(name: str, params: dict, tf: int, grid: dict,
            start: str = "2020-01-01") -> pd.DataFrame:
    """Neighbouring parameter values - a real edge survives small changes."""
    bars = E.get_bars(tf)
    funding = E.load_funding()
    rows = []
    base = {k: v for k, v in params.items() if k != "tf"}
    keys = list(grid)
    for combo in _product(grid):
        p = dict(base)
        p.update(dict(zip(keys, combo)))
        try:
            sig = E.build_signals(name, bars, p, funding)
            res = run_backtest(bars, sig, start_time=pd.Timestamp(start, tz="UTC"),
                               funding=funding)
            rows.append({**dict(zip(keys, combo)), **res.metrics})
        except Exception as e:  # noqa: BLE001
            rows.append({**dict(zip(keys, combo)), "error": str(e)})
    return pd.DataFrame(rows)


def _product(grid: dict):
    keys = list(grid)
    for vals in __import__("itertools").product(*(grid[k] for k in keys)):
        yield vals


# --------------------------------------------------------------------------
def report(name: str, params: dict, tf: int) -> None:
    print("=" * 100)
    print(f"DIAGNOSTIC  {name}  {tf}m  {params}")
    print("=" * 100)

    print("\n[1] cost in R  (full history)")
    cir = cost_in_r(name, params, tf)
    for k, v in cir.items():
        print(f"    {k:<22} {v if not isinstance(v, float) else round(v, 4)}")

    print("\n[2] cost sensitivity")
    cs = cost_sensitivity(name, params, tf)
    print("    " + cs[["cost", "trades", "net_return", "sharpe", "max_dd",
                       "expectancy_r", "win_rate"]].to_string(index=False))

    print("\n[3] bootstrap CI on expectancy")
    b = bootstrap_ci(name, params, tf)
    for k, v in b.items():
        print(f"    {k:<22} {v if not isinstance(v, float) else round(v, 4)}")

    print("\n[4] walk-forward")
    walk_forward(name, params, tf)


if __name__ == "__main__":
    import json
    spec = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {
        "name": "combo_funding_reversion", "tf": 15,
        "params": {"rate_thresh": 0.0002, "z_thresh": 1.5, "stop_mult": 1.8,
                   "tp_mult": 2.2, "max_hold": 30}}
    report(spec["name"], spec["params"], spec["tf"])
