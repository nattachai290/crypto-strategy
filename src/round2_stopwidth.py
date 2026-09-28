"""Round 2: pick the stop width on TRAIN only, then test it out-of-sample.

Exp 003 found that the binding constraint was cost, and cost scales as
1/stop_width. Round 1 looked at stop width on the *full* 80 months, which
means stop_mult is now a fitted parameter and its full-sample numbers are
optimistic. This script redoes the selection honestly:

  1. For each candidate, sweep stop_mult on TRAIN (2020-01..2023-12) only.
  2. Pick the stop_mult with the best train expectancy.
  3. Run that single frozen choice on TEST (2024-01..2026-08).
  4. Report walk-forward folds and a bootstrap CI on the test result.

If the wide-stop advantage survives step 3, it is real. If it collapses, the
edge was the selection, not the market.
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
from diagnose import bootstrap_ci, walk_forward

TRAIN_END = pd.Timestamp("2024-01-01", tz="UTC")

CANDIDATES = [
    ("combo_breakout_confirmed", 30, dict(n=48, adx_min=18, vol_expand=1.0,
                                          stop_mult=1.8, tp_mult=3.5, max_hold=48)),
    ("combo_breakout_confirmed", 15, dict(n=48, adx_min=18, vol_expand=1.0,
                                          stop_mult=1.8, tp_mult=3.5, max_hold=48)),
    ("combo_funding_reversion", 30, dict(rate_thresh=0.0002, z_thresh=1.5,
                                         stop_mult=1.8, tp_mult=2.2, max_hold=30)),
    ("combo_funding_reversion", 15, dict(rate_thresh=0.0002, z_thresh=1.5,
                                         stop_mult=1.8, tp_mult=2.2, max_hold=30)),
    ("supertrend_flip", 30, dict(n=10, mult=3.0, stop_mult=2.0, tp_mult=4.0,
                                 max_hold=48)),
    ("donchian_breakout", 30, dict(n=60, stop_mult=2.0, tp_mult=3.0, max_hold=48)),
    ("combo_trend_pullback", 30, dict(fast=21, slow=55, adx_min=20, stop_mult=1.8,
                                      tp_mult=3.0, max_hold=36)),
    ("combo_vol_flow", 15, dict(squeeze_q=0.2, ratio_n=20, flow_thresh=0.53,
                                stop_mult=1.8, tp_mult=3.0, max_hold=30)),
]

WIDTHS = [1.5, 2.5, 3.5, 5.0, 7.0, 9.0]
MIN_TRADES = 250


def main() -> None:
    train_rows, test_rows = [], []
    for name, tf, base in CANDIDATES:
        bars = E.get_bars(tf)
        funding = E.load_funding()
        best = None
        for sm in WIDTHS:
            p = dict(base)
            p["stop_mult"] = sm
            p["tp_mult"] = round(sm * 1.0, 2)
            sig = E.build_signals(name, bars, p, funding)
            r = run_backtest(bars, sig, end_time=TRAIN_END, funding=funding)
            m = r.metrics
            train_rows.append({"strategy": name, "tf": tf, "stop_mult": sm,
                               "trades": m["trades"], "gross_r": m["avg_gross_r"],
                               "cost_r": m["avg_cost_r"], "exp_r": m["expectancy_r"],
                               "sharpe": m["sharpe"], "max_dd": m["max_dd"]})
            if m["trades"] >= MIN_TRADES and (best is None or
                                              m["expectancy_r"] > best[1]):
                best = (sm, m["expectancy_r"], m)
        print(f"  swept {name} {tf}m -> best stop_mult={best[0] if best else None}",
              flush=True)
        if best is None:
            continue
        sm = best[0]
        p = dict(base)
        p["stop_mult"] = sm
        p["tp_mult"] = round(sm * 1.0, 2)
        sig = E.build_signals(name, bars, p, funding)
        rt = run_backtest(bars, sig, start_time=TRAIN_END, funding=funding)
        mt = rt.metrics
        test_rows.append({"strategy": name, "tf": tf, "stop_mult": sm,
                          "chosen_on": "train expectancy",
                          **{f"tr_{k}": v for k, v in best[2].items()},
                          **{f"te_{k}": v for k, v in mt.items()}})

    tr = pd.DataFrame(train_rows)
    te = pd.DataFrame(test_rows)
    tr.to_csv(C.LEGACY / "round2_stopwidth_train.csv", index=False)
    te.to_csv(C.LEGACY / "round2_stopwidth_test.csv", index=False)

    pd.set_option("display.width", 220)
    print("\n" + "=" * 110)
    print("TRAIN: expectancy vs stop width (TRAIN 2020-01..2023-12 only)")
    print("=" * 110)
    for (n, tf), g in tr.groupby(["strategy", "tf"]):
        print(f"\n{n} {tf}m")
        print(g[["stop_mult", "trades", "gross_r", "cost_r", "exp_r", "sharpe",
                 "max_dd"]].round(4).to_string(index=False))

    print("\n" + "=" * 110)
    print("TEST: the stop width chosen on train, then frozen")
    print("=" * 110)
    if len(te):
        print(te[["strategy", "tf", "stop_mult", "tr_trades", "tr_expectancy_r",
                  "tr_sharpe", "te_trades", "te_expectancy_r", "te_sharpe",
                  "te_max_dd", "te_win_rate", "te_profit_factor", "te_net_return",
                  "te_avg_gross_r", "te_avg_cost_r"]]
              .round(4).to_string(index=False))
        print("\n  te_net_return is on 100 USDT starting equity, "
              "2024-01 .. 2026-08 (2.67 years)")

    # walk-forward + bootstrap on whichever configs survived the test
    print("\n" + "=" * 110)
    print("SURVIVORS: walk-forward over the full history + bootstrap CI")
    print("=" * 110)
    if len(te):
        surv = te.sort_values("te_expectancy_r", ascending=False)
        for _, r in surv.iterrows():
            base = next(b for (n, tf, b) in CANDIDATES
                        if n == r["strategy"] and tf == r["tf"])
            p = dict(base)
            p["stop_mult"] = r["stop_mult"]
            p["tp_mult"] = round(r["stop_mult"] * 1.0, 2)
            print(f"\n--- {r['strategy']} {r['tf']}m stop_mult={r['stop_mult']} ---")
            bs = bootstrap_ci(r["strategy"], p, int(r["tf"]))
            for k, v in bs.items():
                print(f"    {k:<18} "
                      f"{v if not isinstance(v, float) else round(v, 4)}")
            wf = walk_forward(r["strategy"], p, int(r["tf"]))
            if len(wf) and wf["trades"].sum() > 0:
                live = wf[wf["trades"] >= 20]
                print(f"    folds with >=20 trades: {len(live)}/{len(wf)}, "
                      f"positive {int((live['sharpe'] > 0).sum())}/{len(live)}")


if __name__ == "__main__":
    main()
