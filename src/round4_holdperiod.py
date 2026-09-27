"""Exp 009 - fix the holding period, which also fixes the sample size.

Two problems with the current best configuration, and they have the same fix:

1. It holds for `max_hold = 72` bars on 15m = **18 hours**. The brief was
   intraday, 1-4 hours. That is not an intraday strategy, it is a swing
   strategy wearing an intraday label.
2. It trades only 154 times in 4.5 years, so the bootstrap interval is far too
   wide to say anything. Confidence intervals scale as 1/sqrt(n), and no
   amount of signal cleverness fixes a sample of 154.

A shorter `max_hold` addresses both: the strategy becomes what it was supposed
to be, and it trades more often. The risk is that cutting winners early
destroys the edge, so this sweeps the parameter rather than assuming.

Measured with the post-only execution model from Exp 008, which was the only
change that helped consistently.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
import definitive as D
import experiment as E
import run_ml
from backtest import run_backtest

TRAIN_M, TEST_M = 24, 6

# (tf, stop_scale, max_hold) - max_hold chosen so the hold is 1-8 hours
GRID = []
for tf, bars_per_hour in ((5, 12), (15, 4)):
    for sc in (2.0, 3.5, 5.0):
        for hours in (2, 3, 4, 6, 8):
            GRID.append((tf, sc, hours, hours * bars_per_hour))

EXEC = ("taker", ("post_only", 0.20, 1.0))


def run_one(tf: int, sc: float, mh: int, method: str, thr: float, ds, feats,
            bars, funding, entry_mode: str, offset: float, ratio: float,
            n_boot: int = 20000, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    all_trades = []
    equity = C.INITIAL_EQUITY
    peak, max_dd = equity, 0.0
    seen = filled = 0
    for te0, te1 in D.get_folds():
        tr0 = te0 - pd.DateOffset(months=TRAIN_M)
        dtr = ds[(ds.index >= tr0) & (ds.index < te0)]
        dte = ds[(ds.index >= te0) & (ds.index < te1)]
        if len(dtr) < 2000 or len(dte) < 10:
            continue
        ptr = run_ml._fit_predict(dtr[feats].fillna(0.0), dtr["net_r"].to_numpy(),
                                  dte[feats].fillna(0.0), kind=method)
        sub = dte[ptr >= thr]
        res = run_backtest(bars, D.signal_frame(bars, sub), start_time=te0,
                           end_time=te1, funding=funding, initial_equity=equity,
                           entry_mode=entry_mode, entry_offset_atr=offset,
                           entry_fill_ratio=ratio)
        all_trades.extend(res.trades)
        seen += res.metrics.get("entry_signals", 0)
        filled += res.metrics.get("entry_fills", 0)
        equity = res.metrics["final_equity"]
        peak = max(peak, equity)
        max_dd = max(max_dd, 1.0 - equity / peak)
    if not all_trades:
        return {}
    tdf = pd.DataFrame([t.__dict__ for t in all_trades])
    x = tdf["r_multiple"].to_numpy()
    means = x[rng.integers(0, len(x), size=(n_boot, len(x)))].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    yrs = len(D.get_folds()) * TEST_M / 12.0
    return {
        "tf": tf, "stop_scale": sc, "max_hold_bars": mh,
        "hold_hours": mh / (tf and 60.0 / tf),
        "trades": len(tdf), "mean_R": float(x.mean()),
        "ci_lo": float(lo), "ci_hi": float(hi),
        "p_gt_0": float((means > 0).mean()),
        "gross_r": float(tdf["gross_r"].mean()),
        "cost_r": float(tdf["cost_r"].mean()),
        "win_rate": float((x > 0).mean()),
        "avg_bars": float(tdf["bars"].mean()),
        "cagr": (equity / C.INITIAL_EQUITY) ** (1 / yrs) - 1,
        "max_dd": max_dd, "end": equity,
        "fill_rate": filled / seen if seen else 1.0,
    }


def main() -> None:
    cache: dict = {}
    rows = []
    for tf in (5, 15):
        bars = E.get_bars(tf)
        funding = E.load_funding()
        base = run_ml.CANDIDATES
        for sc in (2.0, 3.5, 5.0):
            key = (tf, sc)
            if key not in cache:
                run_ml.CANDIDATES = [
                    (nm, {**pr, **{k: v * sc for k, v in pr.items()
                                   if k in ("stop_mult", "tp_mult") and v > 0}})
                    for nm, pr in base]
                sig = run_ml.build_candidates(bars, funding)
                ds = run_ml.make_dataset(bars, sig, funding).dropna(
                    subset=["net_r"])
                feats = [c for c in ds.columns
                         if c not in ("net_r", "reason", "bars", "side", "src",
                                      "i", "stop_dist", "tp_dist", "max_hold",
                                      "entry_px")]
                cache[key] = (bars, ds, feats)
            bars, ds, feats = cache[key]

            print(f"\n{'='*112}\ntf={tf}m  stop_scale={sc}  "
                  f"post-only offset 0.20  ML reg thr=0.10\n{'='*112}")
            print(f"{'hold':>7}{'bars':>7}{'trades':>8}{'fill%':>7}{'avg_bars':>10}"
                  f"{'gross_r':>10}{'cost_r':>9}{'net R':>9}{'95% CI':>22}"
                  f"{'CAGR':>8}{'maxDD':>8}")
            for hours in (2, 3, 4, 6, 8):
                bph = 60.0 / tf
                mh = int(round(hours * bph))
                # max_hold is part of the candidate params, so the labelled
                # dataset must be rebuilt for each holding period
                run_ml.CANDIDATES = [
                    (nm, {**pr, "max_hold": mh, **{
                        k: v * sc for k, v in pr.items()
                        if k in ("stop_mult", "tp_mult") and v > 0}})
                    for nm, pr in base]
                sig = run_ml.build_candidates(bars, funding)
                ds = run_ml.make_dataset(bars, sig, funding).dropna(
                    subset=["net_r"])
                r = run_one(tf, sc, mh, "reg", 0.10, ds, feats, bars, funding,
                            "post_only", 0.20, 1.0)
                if not r:
                    continue
                r["note"] = "po0.20"
                rows.append(r)
                print(f"{hours:>5.0f}h{mh:>7}{r['trades']:>8}"
                      f"{r['fill_rate']*100:>6.0f}%{r['avg_bars']:>10.1f}"
                      f"{r['gross_r']:>+10.3f}{r['cost_r']:>9.3f}"
                      f"{r['mean_R']:>+9.4f}"
                      f"{'['+format(r['ci_lo'],'+.3f')+','+format(r['ci_hi'],'+.3f')+']':>22}"
                      f"{r['cagr']*100:>+7.1f}%{r['max_dd']*100:>7.1f}%", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(C.LEGACY / "round4_holdperiod.csv", index=False)
    print(f"\n{'='*112}\nVERDICT\n{'='*112}")
    excl = df[df["ci_lo"] > 0]
    print(f"configurations tested: {len(df)}   "
          f"CI excluding zero: {len(excl)}")
    if len(excl):
        print(excl.sort_values("mean_R", ascending=False)[
            ["tf", "stop_scale", "hold_hours", "trades", "mean_R", "ci_lo",
             "ci_hi", "cagr", "max_dd"]].to_string(index=False))
    else:
        best = df.sort_values("mean_R", ascending=False).head(5)
        print("\nnone exclude zero. best by mean_R:")
        print(best[["tf", "stop_scale", "hold_hours", "trades", "mean_R", "ci_lo",
                    "ci_hi", "cagr", "max_dd"]].to_string(index=False))
        # the binding constraint is sample size, so rank by t-like separation
        df["sep"] = df["mean_R"] / (df["ci_hi"] - df["ci_lo"]).replace(0, np.nan)
        print("\nranked by separation from zero (mean_R / CI width):")
        print(df.sort_values("sep", ascending=False).head(5)[
            ["tf", "stop_scale", "hold_hours", "trades", "mean_R", "sep",
             "ci_lo", "ci_hi"]].to_string(index=False))


if __name__ == "__main__":
    main()
