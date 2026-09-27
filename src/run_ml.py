"""Rules vs ML comparison, evaluated walk-forward.

Pipeline
--------
1. Candidate generator = union of several rule strategies (they supply the
   entry, the ATR stop, the target and the time stop).
2. Label = realised net R of that candidate trade (costs included).
3. Model = LightGBM regressor on causal features, refit every fold on the
   training window only.
4. Take the trade only if the model's predicted R clears a threshold that is
   also chosen on the training window only.
5. Score the filtered stream through the *same* backtester used for the
   rules, so the comparison is apples-to-apples.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
import experiment as E
import ml_filter as M
from backtest import fmt_metrics, run_backtest

# Candidate generator: a deliberately diverse pool, using the stop widths that
# Exp 004 showed survive costs. Wide stops matter more than clever indicators.
CANDIDATES: list[tuple[str, dict]] = [
    ("ema_trend", dict(fast=20, slow=50, stop_mult=3.5, tp_mult=3.5, max_hold=72)),
    ("donchian_breakout", dict(n=60, stop_mult=3.5, tp_mult=3.5, max_hold=72)),
    ("vwap_reversion", dict(n_z=2.0, stop_mult=3.5, tp_mult=3.5, max_hold=48)),
    ("bb_reversion", dict(n=48, k=2.2, stop_mult=3.5, tp_mult=3.5, max_hold=36)),
    ("supertrend_flip", dict(n=10, mult=3.0, stop_mult=3.5, tp_mult=3.5, max_hold=72)),
    ("adx_trend", dict(adx_min=22, stop_mult=3.5, tp_mult=3.5, max_hold=72)),
    ("flow_momentum", dict(ratio_n=20, thresh=0.56, stop_mult=3.5, tp_mult=3.5, max_hold=36)),
    ("combo_breakout_confirmed", dict(n=48, adx_min=18, vol_expand=1.0,
                                      stop_mult=3.5, tp_mult=3.5, max_hold=72)),
    ("combo_trend_pullback", dict(fast=21, slow=55, adx_min=20, stop_mult=3.5,
                                  tp_mult=3.5, max_hold=72)),
    ("combo_vol_flow", dict(squeeze_q=0.2, ratio_n=20, flow_thresh=0.53,
                            stop_mult=3.5, tp_mult=3.5, max_hold=48)),
    ("combo_funding_reversion", dict(rate_thresh=0.0002, z_thresh=1.5,
                                     stop_mult=2.5, tp_mult=2.5, max_hold=30)),
    ("combo_vote", dict(n_votes=5, stop_mult=3.5, tp_mult=3.5, max_hold=72)),
]

MIN_TRAIN_ROWS = 2000
LABEL_EPS = 0.0  # train on R directly


def build_candidates(bars: pd.DataFrame, funding) -> pd.DataFrame:
    """Union of candidate signals; at most one candidate per bar (priority order)."""
    parts = []
    for name, params in CANDIDATES:
        sig = E.build_signals(name, bars, params, funding)
        m = (sig["side"] != 0).to_numpy()
        s = sig[m].copy()
        s["src"] = name
        parts.append(s)
    allsig = pd.concat(parts).sort_index()
    return allsig[~allsig.index.duplicated(keep="first")]


def make_dataset(bars: pd.DataFrame, sig: pd.DataFrame, funding) -> pd.DataFrame:
    feats = M.build_features(bars, funding)
    # simulate_outcomes walks the full bar index, so the sparse candidate set
    # has to be re-expanded onto it first.
    full = sig.reindex(bars.index)
    lab = M.simulate_outcomes(bars, full, funding=funding)
    X = feats.join(lab, how="inner")
    return X.replace([np.inf, -np.inf], np.nan)


def _fit_predict(Xtr, ytr, Xte, kind="reg", seed=7):
    import lightgbm as lgb

    if kind == "reg":
        m = lgb.LGBMRegressor(
            n_estimators=400, learning_rate=0.03, num_leaves=31,
            min_child_samples=100, subsample=0.8, subsample_freq=1,
            colsample_bytree=0.7, reg_lambda=5.0, random_state=seed, verbose=-1,
        )
        m.fit(Xtr, ytr)
        return m.predict(Xte)
    y = (ytr > LABEL_EPS).astype(int)
    if y.sum() < 20 or (1 - y).sum() < 20:
        return np.full(len(Xte), float(y.mean()))
    m = lgb.LGBMClassifier(
        n_estimators=400, learning_rate=0.03, num_leaves=31,
        min_child_samples=100, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.7, reg_lambda=5.0, random_state=seed, verbose=-1,
    )
    m.fit(Xtr, y)
    return m.predict_proba(Xte)[:, 1]


def pick_threshold(ytr, ptr, grid) -> float:
    """Best mean net-R of kept trades on TRAIN only."""
    best, bt = -1e9, 0.0
    for t in grid:
        k = ptr >= t
        if k.sum() < 50:
            continue
        v = float(ytr[k].mean()) * float(k.mean())  # reward x coverage
        if v > best:
            best, bt = v, t
    return bt


def main(tf: int = 5, stop_scale: float = 1.0) -> None:
    """stop_scale multiplies every candidate's stop and target width.

    Exp 004 showed the round-trip cost of 0.14% of notional equals
    0.14/stop_pct R, so a 0.56% stop costs 0.25R per trade while a 1.1% stop
    costs 0.13R. On 15m that is the difference between "no edge" and "edge".
    """
    bars = E.get_bars(tf)
    funding = E.load_funding()
    print(f"bars={len(bars):,} {bars.index[0]} .. {bars.index[-1]}  "
          f"stop_scale={stop_scale}")
    if stop_scale != 1.0:
        global CANDIDATES
        scaled = []
        for nm, pr in CANDIDATES:
            q = dict(pr)
            for k in ("stop_mult", "tp_mult"):
                if k in q and q[k] > 0:
                    q[k] = q[k] * stop_scale
            scaled.append((nm, q))
        CANDIDATES = scaled

    allsig = build_candidates(bars, funding)
    print(f"candidate signals: {len(allsig):,}")

    ds = make_dataset(bars, allsig, funding)
    ds = ds.dropna(subset=["net_r"])
    print(f"labelled candidates: {len(ds):,}  mean R={ds['net_r'].mean():.4f}  "
          f"win={100*(ds['net_r']>0).mean():.1f}%")
    ds.to_parquet(C.CACHE / f"ml_dataset_{tf}m_s{stop_scale}.parquet")

    feats = [c for c in ds.columns if c not in ("net_r", "reason", "bars", "side", "src")]
    grid = [-1.0, -0.6, -0.4, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.5, 0.8]

    splits = E.walk_forward_splits()
    rows = []
    for sp in splits:
        tr0, tr1 = sp["train"]
        te0, te1 = sp["test"]
        dtr = ds[(ds.index >= tr0) & (ds.index < tr1)]
        dte = ds[(ds.index >= te0) & (ds.index < te1)]
        if len(dtr) < MIN_TRAIN_ROWS or len(dte) < 50:
            continue
        Xtr = dtr[feats].fillna(0.0)
        ytr = dtr["net_r"].to_numpy()
        Xte = dte[feats].fillna(0.0)

        sig_all = None
        for kind in ("reg", "clf"):
            ptr = _fit_predict(Xtr, ytr, Xte, kind=kind)
            for t in (0.0, 0.05, 0.10, 0.20):
                keep = ptr >= (t if kind == "reg" else 0.5 + t)
                if keep.sum() < 20:
                    continue
                rows.append(_score(bars, funding, sp, kind, t, dte[keep], "ml"))
        rows.append(_score(bars, funding, sp, "rules", None, dte, "all"))
        print(f"  fold {sp['fold']} {sp['test_label']}: done "
              f"({len(dtr)} train / {len(dte)} test candidates)")

    df = pd.DataFrame(rows)
    if len(df):
        agg = df.groupby(["method", "thr"]).apply(
            lambda g: pd.Series({
                "folds": len(g),
                "trades": g["trades"].sum(),
                "ret_sum": g["net_return"].sum(),
                "sharpe_avg": g["sharpe"].mean(),
                "sharpe_med": g["sharpe"].median(),
                "maxdd_worst": g["max_dd"].max(),
                "win": g["win_rate"].mean(),
                "pf": g["profit_factor"].replace(np.inf, np.nan).mean(),
                "expR": g["expectancy_r"].mean(),
                "expo": g["exposure"].mean(),
            }), include_groups=False
        ).reset_index()
        print("\n=== walk-forward summary ===")
        print(agg.to_string(index=False))
        df.to_csv(C.LEGACY / f"ml_walkforward_{tf}m_s{stop_scale}.csv", index=False)


def _score(bars, funding, sp, method, thr, subset, tag) -> dict:
    """Turn a filtered candidate set back into a signal frame and backtest it."""
    sig = pd.DataFrame(index=bars.index)
    sig["side"] = 0.0
    sig["stop_dist"] = np.nan
    sig["tp_dist"] = 0.0
    sig["max_hold"] = 0.0
    if len(subset):
        idx = subset.index
        sig.loc[idx, "side"] = subset["side"].to_numpy()
        sig.loc[idx, "stop_dist"] = subset["stop_dist"].to_numpy()
        sig.loc[idx, "tp_dist"] = subset["tp_dist"].to_numpy()
        sig.loc[idx, "max_hold"] = subset["max_hold"].to_numpy()
    res = run_backtest(
        bars, sig, start_time=sp["test"][0], end_time=sp["test"][1],
        funding=funding, name=f"{method}_{tag}", params={"method": method, "thr": thr},
    )
    row = {"fold": sp["fold"], "test_label": sp["test_label"], "method": method,
           "thr": thr, "tag": tag, "candidates": len(subset)}
    row.update(res.metrics)
    print(f"    {method:<6} thr={thr}  {fmt_metrics(res.metrics)}")
    return row


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5,
         float(sys.argv[2]) if len(sys.argv) > 2 else 1.0)
