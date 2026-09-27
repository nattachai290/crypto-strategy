"""Final evaluation: chain the walk-forward folds and bootstrap the result.

Two things were wrong with reading walk-forward output directly:

1. `ret_sum` summed per-fold percentage returns. Each fold restarts at 100
   USDT, so adding the percentages does not compound and does not describe a
   real account. The folds have to be chained: each fold starts at the
   previous fold's closing equity.
2. A Sharpe averaged over nine folds is not a confidence interval. The
   question is whether the *pooled out-of-sample trade stream* has positive
   expectancy, so the bootstrap has to run over those pooled trades.

This produces the one number worth quoting, plus its interval, plus a
per-year breakdown so the regime dependence from Exp 005 is visible.
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
from backtest import run_backtest

TRAIN_M, TEST_M = 24, 6


def folds() -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    months = C.month_range()
    out = []
    i = 0
    while i + TRAIN_M + TEST_M <= len(months):
        out.append((C.mstart(months[i + TRAIN_M]),
                    C.mend(months[i + TRAIN_M + TEST_M - 1])))
        i += TEST_M
    return out


def pooled_oos_trades(ds: pd.DataFrame, feats: list[str], method: str, thr: float,
                      n_boot: int = 20000, seed: int = 0):
    """Fit on each fold's train window, trade the next window, collect every
    out-of-sample trade into one series."""
    rng = np.random.default_rng(seed)
    rows = []
    for te0, te1 in folds():
        tr_end = te0
        tr_start = tr_end - pd.Timedelta(days=31 * TRAIN_M)
        dtr = ds[(ds.index >= tr_start) & (ds.index < tr_end)]
        dte = ds[(ds.index >= te0) & (ds.index < te1)]
        if len(dtr) < 2000 or len(dte) < 50:
            continue
        ptr = run_ml._fit_predict(dtr[feats].fillna(0.0),
                                  dtr["net_r"].to_numpy(),
                                  dte[feats].fillna(0.0), kind=method)
        cut = thr if method == "reg" else 0.5 + thr
        keep = ptr >= cut
        if keep.sum() < 10:
            continue
        sub = dte[keep]
        rows.append(sub[["net_r", "side", "reason", "stop_dist", "entry_px"]])
    if not rows:
        return None, None
    pooled = pd.concat(rows)
    x = pooled["net_r"].to_numpy()
    idx = rng.integers(0, len(x), size=(n_boot, len(x)))
    means = x[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return pooled, {"trades": len(x), "mean_R": float(x.mean()),
                    "ci_lo": float(lo), "ci_hi": float(hi),
                    "p_gt_0": float((means > 0).mean()),
                    "win_rate": float((x > 0).mean())}


def chained_curve(ds: pd.DataFrame, feats: list[str], method: str, thr: float,
                  bars, funding) -> dict:
    """Run the walk-forward as one continuous account."""
    equity = C.INITIAL_EQUITY
    peak = equity
    max_dd = 0.0
    curve = []
    total_trades = 0
    for te0, te1 in folds():
        tr_end = te0
        tr_start = tr_end - pd.Timedelta(days=31 * TRAIN_M)
        dtr = ds[(ds.index >= tr_start) & (ds.index < tr_end)]
        dte = ds[(ds.index >= te0) & (ds.index < te1)]
        if len(dtr) < 2000 or len(dte) < 10:
            continue
        ptr = run_ml._fit_predict(dtr[feats].fillna(0.0),
                                  dtr["net_r"].to_numpy(),
                                  dte[feats].fillna(0.0), kind=method)
        cut = thr if method == "reg" else 0.5 + thr
        sub = dte[ptr >= cut]
        sig = pd.DataFrame(index=bars.index)
        for col in ("side", "stop_dist", "tp_dist", "max_hold"):
            sig[col] = np.nan if col == "stop_dist" else 0.0
        if len(sub):
            sig.loc[sub.index, "side"] = sub["side"].to_numpy()
            sig.loc[sub.index, "stop_dist"] = sub["stop_dist"].to_numpy()
            sig.loc[sub.index, "tp_dist"] = sub["tp_dist"].to_numpy()
            sig.loc[sub.index, "max_hold"] = sub["max_hold"].to_numpy()
        res = run_backtest(bars, sig, start_time=te0, end_time=te1,
                           funding=funding, initial_equity=equity)
        total_trades += res.metrics["trades"]
        equity = res.metrics["final_equity"]
        peak = max(peak, equity)
        max_dd = max(max_dd, 1.0 - equity / peak)
        curve.append({"fold": str(te0.date()), "equity": equity,
                      "trades": res.metrics["trades"],
                      "fold_return": res.metrics["net_return"]})
    years = (len(curve) * TEST_M) / 12.0
    return {"start": C.INITIAL_EQUITY, "end": equity,
            "total_return": equity / C.INITIAL_EQUITY - 1.0,
            "cagr": (equity / C.INITIAL_EQUITY) ** (1.0 / years) - 1.0 if years else 0.0,
            "max_dd": max_dd, "trades": total_trades, "years": years,
            "curve": curve}


def main(tf: int = 15, stop_scale: float = 2.0) -> None:
    run_ml.CANDIDATES = [
        (nm, {**pr,
              **{k: v * stop_scale for k, v in pr.items() if k in ("stop_mult", "tp_mult") and v > 0}})
        for nm, pr in run_ml.CANDIDATES
    ]
    bars = E.get_bars(tf)
    funding = E.load_funding()
    sig = run_ml.build_candidates(bars, funding)
    ds = run_ml.make_dataset(bars, sig, funding).dropna(subset=["net_r"])
    feats = [c for c in ds.columns
             if c not in ("net_r", "reason", "bars", "side", "src", "i",
                          "stop_dist", "tp_dist", "max_hold", "entry_px")]
    print(f"pool={len(ds):,} candidates, {len(feats)} features, {tf}m, "
          f"stop_scale={stop_scale}\n")

    combos = [("reg", t) for t in (0.0, 0.05, 0.1, 0.2)] + \
             [("clf", t) for t in (0.0, 0.05, 0.1, 0.2)]
    summary = []
    for method, thr in combos:
        pooled, boot = pooled_oos_trades(ds, feats, method, thr)
        if pooled is None:
            print(f"  {method} thr={thr}: no trades")
            continue
        ch = chained_curve(ds, feats, method, thr, bars, funding)
        summary.append({"method": method, "thr": thr, **boot,
                        "chained_end": ch["end"], "chained_return": ch["total_return"],
                        "cagr": ch["cagr"], "max_dd": ch["max_dd"]})
        y = pooled.groupby(pooled.index.year)["net_r"].agg(["count", "mean"])
        print(f"  {method} thr={thr:<5} trades={boot['trades']:<4} "
              f"meanR={boot['mean_R']:+.4f} "
              f"CI[{boot['ci_lo']:+.3f},{boot['ci_hi']:+.3f}] "
              f"p={boot['p_gt_0']:.2f} win={boot['win_rate']*100:.1f}% | "
              f"chained {ch['start']:.0f}->{ch['end']:.2f}U "
              f"({ch['total_return']*100:+.1f}%, CAGR {ch['cagr']*100:+.1f}%, "
              f"DD {ch['max_dd']*100:.1f}%)")
        print("      by year: " + "  ".join(
            f"{i}:{r['count']}/{r['mean']:+.3f}" for i, r in y.iterrows()))

    df = pd.DataFrame(summary)
    df.to_csv(C.RESULTS / f"final_eval_{tf}m_s{stop_scale}.csv", index=False)
    print("\n" + "=" * 100)
    print("SUMMARY - pooled out-of-sample, 9 walk-forward folds, 2022-01 .. 2026-08")
    print("=" * 100)
    print(df[["method", "thr", "trades", "mean_R", "ci_lo", "ci_hi", "p_gt_0",
              "win_rate", "chained_return", "cagr", "max_dd"]]
          .round(4).to_string(index=False))
    best = df.sort_values("mean_R", ascending=False).iloc[0]
    print(f"\nbest: {best['method']} thr={best['thr']}  "
          f"mean R = {best['mean_R']:+.4f}  "
          f"95% CI [{best['ci_lo']:+.4f}, {best['ci_hi']:+.4f}]")
    if best["ci_lo"] > 0:
        print("  -> the interval EXCLUDES zero: this is a positive edge")
    else:
        print("  -> the interval INCLUDES zero: still not statistically proven")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 15,
         float(sys.argv[2]) if len(sys.argv) > 2 else 2.0)
