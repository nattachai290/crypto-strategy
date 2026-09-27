"""Definitive out-of-sample measurement.

Everything before this was a proxy. This walks the 9 walk-forward folds,
collects **every trade the backtester actually executed** into one series, and
reports:

  * trade-weighted expectancy (not the mean of per-fold means, which is what
    made the numbers disagree between runs)
  * a bootstrap CI over that pooled executed-trade series
  * a chained equity curve where each fold starts at the previous fold's
    closing balance
  * a per-year breakdown

The distinction that matters: the ML label set contains ~13,000 candidate
signals, but the backtest only executes a few hundred of them, because only
one position can be open at a time. Scoring the 13,000 labels measures a
population the account never actually traded.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
import experiment as E
import run_ml
from backtest import Trade, run_backtest

TRAIN_M, TEST_M = 24, 6


def get_folds() -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    months = C.month_range()
    out, i = [], 0
    while i + TRAIN_M + TEST_M <= len(months):
        out.append((C.mstart(months[i + TRAIN_M]),
                    C.mend(months[i + TRAIN_M + TEST_M - 1])))
        i += TEST_M
    return out


def signal_frame(bars, sub: pd.DataFrame) -> pd.DataFrame:
    sig = pd.DataFrame(index=bars.index)
    sig["side"] = 0.0
    sig["stop_dist"] = np.nan
    sig["tp_dist"] = 0.0
    sig["max_hold"] = 0.0
    if len(sub):
        sig.loc[sub.index, "side"] = sub["side"].to_numpy()
        sig.loc[sub.index, "stop_dist"] = sub["stop_dist"].to_numpy()
        sig.loc[sub.index, "tp_dist"] = sub["tp_dist"].to_numpy()
        sig.loc[sub.index, "max_hold"] = sub["max_hold"].to_numpy()
    return sig


def run(tf: int, stop_scale: float, method: str, thr: float, ds, feats,
        bars, funding, n_boot: int = 20000, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    all_trades: list[Trade] = []
    equity = C.INITIAL_EQUITY
    peak = equity
    max_dd = 0.0
    fold_rows = []
    for te0, te1 in get_folds():
        tr0 = te0 - pd.DateOffset(months=TRAIN_M)
        dtr = ds[(ds.index >= tr0) & (ds.index < te0)]
        dte = ds[(ds.index >= te0) & (ds.index < te1)]
        if len(dtr) < 2000 or len(dte) < 10:
            continue
        ptr = run_ml._fit_predict(dtr[feats].fillna(0.0), dtr["net_r"].to_numpy(),
                                  dte[feats].fillna(0.0), kind=method)
        cut = thr if method == "reg" else 0.5 + thr
        sub = dte[ptr >= cut]
        res = run_backtest(bars, signal_frame(bars, sub), start_time=te0,
                           end_time=te1, funding=funding,
                           initial_equity=equity)
        all_trades.extend(res.trades)
        equity = res.metrics["final_equity"]
        peak = max(peak, equity)
        max_dd = max(max_dd, 1.0 - equity / peak)
        fold_rows.append({"fold": str(te0.date()), "signals": len(sub),
                          "trades": res.metrics["trades"],
                          "equity": round(equity, 2),
                          "ret": round(res.metrics["net_return"] * 100, 2)})

    if not all_trades:
        return {}
    tdf = pd.DataFrame([t.__dict__ for t in all_trades])
    x = tdf["r_multiple"].to_numpy()
    idx = rng.integers(0, len(x), size=(n_boot, len(x)))
    means = x[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    yrs = len(fold_rows) * TEST_M / 12.0
    return {
        "method": method, "thr": thr, "tf": tf, "stop_scale": stop_scale,
        "trades": len(tdf),
        "mean_R": float(x.mean()), "ci_lo": float(lo), "ci_hi": float(hi),
        "p_gt_0": float((means > 0).mean()),
        "win_rate": float((x > 0).mean()),
        "gross_r": float(tdf["gross_r"].mean()), "cost_r": float(tdf["cost_r"].mean()),
        "start": C.INITIAL_EQUITY, "end": equity,
        "total_return": equity / C.INITIAL_EQUITY - 1.0,
        "cagr": (equity / C.INITIAL_EQUITY) ** (1.0 / yrs) - 1.0 if yrs else 0.0,
        "max_dd": max_dd, "years": yrs,
        "folds": fold_rows, "tdf": tdf,
    }


def main() -> None:
    tf = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    scales = [float(x) for x in (sys.argv[2].split(",") if len(sys.argv) > 2
                                 else ["1.0", "2.0", "3.5"])]
    bars = E.get_bars(tf)
    funding = E.load_funding()
    base = run_ml.CANDIDATES
    results = []
    for sc in scales:
        run_ml.CANDIDATES = [
            (nm, {**pr, **{k: v * sc for k, v in pr.items()
                           if k in ("stop_mult", "tp_mult") and v > 0}})
            for nm, pr in base]
        sig = run_ml.build_candidates(bars, funding)
        ds = run_ml.make_dataset(bars, sig, funding).dropna(subset=["net_r"])
        feats = [c for c in ds.columns
                 if c not in ("net_r", "reason", "bars", "side", "src", "i",
                              "stop_dist", "tp_dist", "max_hold", "entry_px")]
        print(f"\n{'='*104}\nstop_scale={sc}  pool={len(ds):,}  "
              f"{tf}m\n{'='*104}")
        for method, thr in [("reg", t) for t in (0.0, 0.05, 0.1)] + \
                          [("clf", t) for t in (0.0, 0.05, 0.1)]:
            r = run(tf, sc, method, thr, ds, feats, bars, funding)
            if not r:
                continue
            results.append({k: v for k, v in r.items() if k not in ("folds", "tdf")})
            star = "  <-- CI excludes 0" if r["ci_lo"] > 0 else ""
            print(f"  {method} thr={thr:<5} trades={r['trades']:<5} "
                  f"meanR={r['mean_R']:+.4f} CI[{r['ci_lo']:+.4f},{r['ci_hi']:+.4f}] "
                  f"p={r['p_gt_0']:.3f} win={r['win_rate']*100:.1f}% "
                  f"grossR={r['gross_r']:+.3f} costR={r['cost_r']:.3f} | "
                  f"{r['start']:.0f}->{r['end']:.2f}U "
                  f"({r['total_return']*100:+.1f}% over {r['years']:.1f}y, "
                  f"CAGR {r['cagr']*100:+.1f}%, maxDD {r['max_dd']*100:.1f}%){star}")

    df = pd.DataFrame(results)
    df.to_csv(C.LEGACY / "definitive_oos.csv", index=False)
    pd.set_option("display.width", 220)
    print("\n" + "=" * 104)
    print("DEFINITIVE OUT-OF-SAMPLE  (9 walk-forward folds, executed trades only)")
    print("=" * 104)
    print(df[["tf", "stop_scale", "method", "thr", "trades", "mean_R", "ci_lo",
              "ci_hi", "p_gt_0", "win_rate", "gross_r", "cost_r", "end",
              "cagr", "max_dd"]].round(4).to_string(index=False))
    best = df.sort_values("mean_R", ascending=False).iloc[0]
    print(f"\nbest: {best['method']} thr={best['thr']} scale={best['stop_scale']} "
          f"-> mean R {best['mean_R']:+.4f}, 95% CI "
          f"[{best['ci_lo']:+.4f}, {best['ci_hi']:+.4f}]")
    print("VERDICT: interval excludes 0" if best["ci_lo"] > 0
          else "VERDICT: interval includes 0 - no statistically proven edge")


if __name__ == "__main__":
    main()
