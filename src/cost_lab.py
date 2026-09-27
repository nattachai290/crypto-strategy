"""Cost lab: the arithmetic that decides whether intraday trading is viable.

The backtester reports, per trade:

    gross_r   the R the price move actually produced
    cost_r    the R that fees + slippage + funding consumed
    exp_r     gross_r - cost_r

A strategy is profitable only if gross_r > cost_r. From the sweep, the whole
field had gross_r around 0.17 and cost_r around 0.16 - i.e. a real but small
edge that realistic execution costs eat entirely.

cost_r is almost entirely determined by two things:

    cost_r  =  round_trip_cost_fraction / stop_distance_fraction

So there are only two ways out, and this script measures both:

  A. WIDEN THE STOP. cost_r falls linearly with stop width. Does the gross edge
     survive, or does a wider stop just cap the winners?
  B. TRADE CHEAPER. Taker round trip is 0.14% of notional. A post-only maker
     round trip is 0.04%. That is a 3.5x cut in cost_r - but only if your
     limit orders actually fill, which is a real risk this script does not
     pretend away: it reports maker numbers as an upper bound, not a promise.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
import experiment as E
from backtest import run_backtest

# Execution scenarios: (label, fee_taker, slippage, note)
SCENARIOS = [
    ("taker (real)", C.FEE_TAKER, C.SLIPPAGE, "VIP0, the realistic baseline"),
    ("vip_taker", 0.0004, 0.0001, "VIP1-ish, still crossing the book"),
    ("maker*", C.FEE_MAKER, 0.0, "UPPER BOUND: post-only both sides, assumes every fill"),
    ("half_fill*", C.FEE_MAKER, 0.0, "UPPER BOUND: half of these fills are realistic"),
]

CANDIDATES = [
    ("combo_funding_reversion", 15,
     dict(rate_thresh=0.0002, z_thresh=1.5, stop_mult=1.8, tp_mult=2.2, max_hold=30)),
    ("combo_funding_reversion", 30,
     dict(rate_thresh=0.0002, z_thresh=1.5, stop_mult=1.8, tp_mult=2.2, max_hold=30)),
    ("combo_breakout_confirmed", 30,
     dict(n=48, adx_min=18, vol_expand=1.0, stop_mult=1.8, tp_mult=3.5, max_hold=48)),
    ("combo_breakout_confirmed", 15,
     dict(n=48, adx_min=18, vol_expand=1.0, stop_mult=1.8, tp_mult=3.5, max_hold=48)),
    ("supertrend_flip", 30,
     dict(n=10, mult=3.0, stop_mult=2.0, tp_mult=4.0, max_hold=48)),
    ("combo_trend_pullback", 30,
     dict(fast=21, slow=55, adx_min=20, stop_mult=1.8, tp_mult=3.0, max_hold=36)),
    ("combo_trend_pullback", 15,
     dict(fast=21, slow=55, adx_min=20, stop_mult=1.8, tp_mult=3.0, max_hold=36)),
    ("donchian_breakout", 30,
     dict(n=60, stop_mult=2.0, tp_mult=3.0, max_hold=48)),
    ("combo_vol_flow", 15,
     dict(squeeze_q=0.2, ratio_n=20, flow_thresh=0.53, stop_mult=1.8,
          tp_mult=3.0, max_hold=30)),
]

# (stop_mult, tp_mult) pairs - the target scales with the stop so the R profile
# stays comparable instead of quietly changing shape.
WIDTHS = [(1.0, 1.0), (1.5, 1.5), (1.8, 2.2), (2.5, 3.0), (3.5, 4.0),
          (5.0, 6.0), (7.0, 8.0)]


def main() -> pd.DataFrame:
    rows = []
    for name, tf, base in CANDIDATES:
        bars = E.get_bars(tf)
        funding = E.load_funding()
        for sm, tm in WIDTHS:
            p = dict(base)
            p["stop_mult"] = sm
            p["tp_mult"] = tm
            sig = E.build_signals(name, bars, p, funding)
            for label, fee, slip, note in SCENARIOS:
                r = run_backtest(bars, sig, funding=funding,
                                 fee_taker=fee, slippage=slip)
                m = r.metrics
                tdf = r.to_trades_df()
                stop_pct = float(
                    ((tdf["stop_px"] - tdf["entry_px"]).abs() / tdf["entry_px"]).median()
                ) if len(tdf) else np.nan
                rows.append({
                    "strategy": name, "tf": tf, "stop_mult": sm, "tp_mult": tm,
                    "exec": label, "trades": m["trades"],
                    "stop_pct": stop_pct,
                    "gross_r": m["avg_gross_r"], "cost_r": m["avg_cost_r"],
                    "exp_r": m["expectancy_r"], "edge_r": m["edge_r"],
                    "sharpe": m["sharpe"], "max_dd": m["max_dd"],
                    "win_rate": m["win_rate"], "pf": min(m["profit_factor"], 99),
                    "net_return": m["net_return"], "exposure": m["exposure"],
                })
        print(f"  done {name} {tf}m", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(C.RESULTS / "cost_lab.csv", index=False)
    return df


def show(df: pd.DataFrame) -> None:
    pd.set_option("display.width", 200)
    print("\n" + "=" * 110)
    print("A. COST PER TRADE vs STOP WIDTH  (taker execution, the realistic case)")
    print("=" * 110)
    t = df[df["exec"] == "taker (real)"]
    piv = t.pivot_table(index=["strategy", "tf"], columns="stop_mult",
                        values="cost_r")
    print("\ncost_r (R consumed per trade) - should fall as 1/stop:")
    print(piv.round(3).to_string())
    piv2 = t.pivot_table(index=["strategy", "tf"], columns="stop_mult",
                         values="exp_r")
    print("\nnet expectancy_r (gross - cost) at taker costs:")
    print(piv2.round(4).to_string())
    piv3 = t.pivot_table(index=["strategy", "tf"], columns="stop_mult",
                         values="gross_r")
    print("\ngross_r (does the edge survive a wider stop?):")
    print(piv3.round(3).to_string())

    print("\n" + "=" * 110)
    print("B. EXECUTION COST SCENARIOS  (stop_mult = 1.8, the sweep's setting)")
    print("=" * 110)
    b = df[df["stop_mult"] == 1.8]
    for label, *_ in SCENARIOS:
        s = b[b["exec"] == label]
        print(f"\n--- {label} ---")
        print(s[["strategy", "tf", "trades", "gross_r", "cost_r", "exp_r",
                 "sharpe", "max_dd", "net_return"]].round(4).to_string(index=False))

    print("\n" + "=" * 110)
    print("C. ANYTHING PROFITABLE AT REALISTIC (TAKER) COSTS?")
    print("=" * 110)
    t = df[df["exec"] == "taker (real)"]
    good = t[t["exp_r"] > 0.02].sort_values("exp_r", ascending=False)
    if len(good):
        print(good[["strategy", "tf", "stop_mult", "trades", "stop_pct", "gross_r",
                    "cost_r", "exp_r", "sharpe", "max_dd", "win_rate",
                    "net_return"]].round(4).to_string(index=False))
    else:
        print("  NONE. No configuration produced a positive net expectancy")
        print("  after taker fees and slippage. The edge is real but smaller")
        print("  than the cost of executing it.")


if __name__ == "__main__":
    d = main()
    show(d)
