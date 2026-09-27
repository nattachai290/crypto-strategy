"""Exp 008 - does cheaper execution actually help, once you count the fills?

Earlier I claimed post-only execution would cut cost by 3.5x. That was wrong:
it assumed maker fees on the exit too, and a stop-loss does not get a maker
fill. The honest round trip is:

    taker      0.05% + 0.05% fee, 0.02% + 0.02% slippage      = 0.14%
    post-only  0.02% + 0.05% fee, 0.00% + 0.02% slippage      = 0.09%

so 1.55x, not 3.5x. And that is only the *price* of the improvement. The
real cost of a resting limit is that it fills selectively: it fills when the
market comes to you, which is exactly when the market is moving against the
entry. This experiment measures that instead of assuming it away.

`entry_offset_atr` controls how far into the market the limit rests:
larger offset = higher fill rate = more adverse selection.
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
SCALES = [2.0, 3.5, 5.0]
# (label, entry_mode, offset_atr, fill_ratio)
MODES = [
    ("taker", "taker", 0.0, 1.0),
    ("po 0.00", "post_only", 0.00, 1.0),
    ("po 0.15", "post_only", 0.15, 1.0),
    ("po 0.30", "post_only", 0.30, 1.0),
    ("po 0.50", "post_only", 0.50, 1.0),
    ("po 0.30 q50%", "post_only", 0.30, 0.5),
    ("po 0.50 q50%", "post_only", 0.50, 0.5),
]


def run_mode(sc: float, method: str, thr: float, ds, feats, bars, funding,
             entry_mode: str, offset: float, ratio: float,
             n_boot: int = 20000, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    all_trades = []
    equity = C.INITIAL_EQUITY
    peak, max_dd = equity, 0.0
    sig_seen = sig_filled = 0
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
                           end_time=te1, funding=funding,
                           initial_equity=equity, entry_mode=entry_mode,
                           entry_offset_atr=offset, entry_fill_ratio=ratio)
        all_trades.extend(res.trades)
        sig_seen += res.metrics.get("entry_signals", 0)
        sig_filled += res.metrics.get("entry_fills", 0)
        equity = res.metrics["final_equity"]
        peak = max(peak, equity)
        max_dd = max(max_dd, 1.0 - equity / peak)
    if not all_trades:
        return {}
    tdf = pd.DataFrame([t.__dict__ for t in all_trades])
    x = tdf["r_multiple"].to_numpy()
    idx = rng.integers(0, len(x), size=(n_boot, len(x)))
    means = x[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    yrs = len(D.get_folds()) * TEST_M / 12.0
    return {
        "trades": len(tdf), "mean_R": float(x.mean()),
        "ci_lo": float(lo), "ci_hi": float(hi),
        "p_gt_0": float((means > 0).mean()),
        "win_rate": float((x > 0).mean()),
        "gross_r": float(tdf["gross_r"].mean()),
        "cost_r": float(tdf["cost_r"].mean()),
        "end": equity, "cagr": (equity / C.INITIAL_EQUITY) ** (1 / yrs) - 1,
        "max_dd": max_dd, "years": yrs,
        "fill_rate": sig_filled / sig_seen if sig_seen else 1.0,
        "signals": sig_seen,
    }


def main() -> None:
    tf = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    bars = E.get_bars(tf)
    funding = E.load_funding()
    base = run_ml.CANDIDATES
    rows = []
    for sc in SCALES:
        run_ml.CANDIDATES = [
            (nm, {**pr, **{k: v * sc for k, v in pr.items()
                           if k in ("stop_mult", "tp_mult") and v > 0}})
            for nm, pr in base]
        sig = run_ml.build_candidates(bars, funding)
        ds = run_ml.make_dataset(bars, sig, funding).dropna(subset=["net_r"])
        feats = [c for c in ds.columns
                 if c not in ("net_r", "reason", "bars", "side", "src", "i",
                              "stop_dist", "tp_dist", "max_hold", "entry_px")]
        print(f"\n{'='*112}\nstop_scale={sc}   tf={tf}m   "
              f"ML reg thr=0.10   9 walk-forward folds, pooled executed trades\n"
              f"{'='*112}")
        print(f"{'mode':<15}{'fill%':>7}{'trades':>8}{'gross_r':>10}"
              f"{'cost_r':>9}{'net R':>9}{'95% CI':>22}{'CAGR':>9}{'maxDD':>8}")
        for label, mode, off, ratio in MODES:
            r = run_mode(sc, "reg", 0.10, ds, feats, bars, funding,
                         mode, off, ratio)
            if not r:
                continue
            r.update({"stop_scale": sc, "mode": label, "entry_mode": mode,
                      "offset": off, "fill_ratio": ratio, "tf": tf})
            rows.append(r)
            print(f"{label:<15}{r['fill_rate']*100:>6.1f}%{r['trades']:>8}"
                  f"{r['gross_r']:>+10.3f}{r['cost_r']:>9.3f}{r['mean_R']:>+9.4f}"
                  f"{'['+format(r['ci_lo'],'+.3f')+','+format(r['ci_hi'],'+.3f')+']':>22}"
                  f"{r['cagr']*100:>+8.1f}%{r['max_dd']*100:>7.1f}%", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(C.LEGACY / "round3_maker.csv", index=False)

    print(f"\n{'='*112}\nVERDICT\n{'='*112}")
    for sc in SCALES:
        s = df[df["stop_scale"] == sc]
        if not len(s):
            continue
        t = s[s["mode"] == "taker"]
        best = s.loc[s["mean_R"].idxmax()]
        print(f"\nstop_scale {sc}:")
        print(f"  taker baseline      net_R {t['mean_R'].iloc[0]:+.4f}  "
              f"cost_r {t['cost_r'].iloc[0]:.4f}  CAGR {t['cagr'].iloc[0]*100:+.1f}%")
        print(f"  best post-only      {best['mode']:<14} net_R {best['mean_R']:+.4f}  "
              f"cost_r {best['cost_r']:.4f}  fill {best['fill_rate']*100:.0f}%  "
              f"CAGR {best['cagr']*100:+.1f}%")
        gain = best["mean_R"] - t["mean_R"].iloc[0]
        print(f"  improvement         {gain:+.4f} R/trade  "
              f"({'HELPS' if gain > 0 else 'HURTS'})")
        any_excl = s[s["ci_lo"] > 0]
        print(f"  CI excludes zero    "
              f"{'yes: ' + ', '.join(r['mode'] for _, r in any_excl.iterrows()) if len(any_excl) else 'no'}")


if __name__ == "__main__":
    main()
