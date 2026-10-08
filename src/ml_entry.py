"""ML entry model: can a trained model time entries better than chance? (PLAN.md section 19)

    SYMBOL=BTCUSDT python src/ml_entry.py          # 1h, primary
    SYMBOL=ETHUSDT python src/ml_entry.py          # replication
    SYMBOL=BTCUSDT python src/ml_entry.py --final  # HOLDOUT once, only after PASS

Stage 2 of the owner's "train the timing" request. A LightGBM model per side
predicts the NET R (after fees, slippage, funding) of entering at the next
open with ONE fixed, symmetric exit (EXIT: 3-ATR stop, out after 24 bars).
The exit is symmetric on purpose: BTC Exp 045 showed a path-dependent exit
(a trailing stop) turns market drift into profit, so the drift-matched
random control below would not be fair to it.

Protocol, all pre-registered:
  * Features at bar i use bars <= i only (FEATURES; test 15 checks it).
  * TRAIN 2020-2022 only. Rows whose label window reaches past TRAIN are
    dropped (purge = EXIT max_hold + 2 bars).
  * The trade threshold is chosen on TRAIN out-of-fold predictions from 3
    expanding, purged walk-forward folds; the final model is refit on all of
    TRAIN with fixed hyper-parameters (LGB_PARAMS). Nothing is tuned on VALID.
  * VALID: at each bar take the side whose prediction is higher, if it is
    above the threshold. Each signal is one trade, simulated on its own.
  * Controls: 200 random circular time-shifts of the model's own signals
    (the SAME long and short counts and the same clustering, so drift helps
    them exactly as much as the model); the model's mean must beat their 95th
    percentile (SKILL). Plus the usual gates.
Writes results/<SYMBOL>/s19_ml_entry_1h/ and the generated journal/<SYMBOL>/s19_ml_entry_1h.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
import exit_lab as XL  # noqa: E402
import indicators as ta  # noqa: E402

TF = 60
EXIT = XL.EXITS["time_only"]          # symmetric: 3 ATR stop, 24 bars
PURGE = EXIT["max_hold"] + 2
THRESHOLDS = (0.0, 0.05, 0.10, 0.20)  # predicted net R needed to trade
MIN_OOF_TRADES = 300
MIN_VALID_TRADES = 300
N_RANDOM = 200
N_ROUNDS = 300
LGB_PARAMS = dict(objective="regression", learning_rate=0.03, num_leaves=15, min_data_in_leaf=200,
                  bagging_fraction=0.8, bagging_freq=1, feature_fraction=0.8, lambda_l2=1.0,
                  seed=7, deterministic=True, num_threads=4, verbose=-1)
SPLITS = XL.SPLITS
FOLDS = [("2020-01-01", "2021-07-01", "2022-01-01"),   # fit [a, b), predict [b, c)
         ("2020-01-01", "2022-01-01", "2022-07-01"),
         ("2020-01-01", "2022-07-01", "2023-01-01")]


# --------------------------------------------------------------------------
# features (causal: bar i uses bars <= i)
# --------------------------------------------------------------------------
def features(b: pd.DataFrame, funding: pd.DataFrame | None = None) -> pd.DataFrame:
    o, h, l, c = b["open"], b["high"], b["low"], b["close"]
    v = b["volume"].replace(0, np.nan)
    lr = np.log(c).diff()
    atr = ta.atr_(h, l, c, 14)
    rng_ = (h - l).replace(0, np.nan)
    f = pd.DataFrame(index=b.index)
    for k in (1, 3, 6, 12, 24, 48, 96, 168):
        f[f"ret_{k}"] = np.log(c / c.shift(k))
    f["vol_24"] = lr.rolling(24).std()
    f["vol_168"] = lr.rolling(168).std()
    f["vol_ratio"] = f["vol_24"] / f["vol_168"]
    f["atr_pct"] = atr / c
    for k in (24, 168):
        hi, lo = h.rolling(k).max(), l.rolling(k).min()
        f[f"range_pos_{k}"] = (c - lo) / (hi - lo).replace(0, np.nan)
    f["body"] = (c - o) / rng_
    f["upper_wick"] = (h - np.maximum(o, c)) / rng_
    f["lower_wick"] = (np.minimum(o, c) - l) / rng_
    f["body_3"] = f["body"].rolling(3).mean()
    lv = np.log(v)
    f["volume_z"] = (lv - lv.rolling(168).mean()) / lv.rolling(168).std()
    if "taker_buy_base" in b:
        tb = b["taker_buy_base"] / v
        f["taker_ratio"] = tb
        f["taker_ratio_24"] = tb.rolling(24).mean()
    for k in (20, 50, 200):
        f[f"ema_dist_{k}"] = (c - ta.ema(c, k)) / atr
    f["hour"] = b.index.hour
    f["weekday"] = b.index.dayofweek
    if funding is not None and len(funding):
        fr = funding[["calc_time", "last_funding_rate"]].copy()
        fr["calc_time"] = pd.to_datetime(fr["calc_time"], utc=True)
        close_t = pd.DataFrame({"t": b.index + pd.Timedelta(minutes=TF)})
        got = pd.merge_asof(close_t.astype({"t": "datetime64[ns, UTC]"}),
                            fr.sort_values("calc_time").astype({"calc_time": "datetime64[ns, UTC]"}),
                            left_on="t", right_on="calc_time", direction="backward")
        f["funding_last"] = got["last_funding_rate"].to_numpy()
    return f.replace([np.inf, -np.inf], np.nan)


# --------------------------------------------------------------------------
# labels and the model
# --------------------------------------------------------------------------
def labels(b: pd.DataFrame, funding, fee=C.FEE_TAKER, slip=C.SLIPPAGE) -> pd.DataFrame:
    """Net R of a long and of a short entered on every bar (signal bar index)."""
    out = pd.DataFrame(index=b.index, columns=["long", "short"], dtype=float)
    for col, s in (("long", 1.0), ("short", -1.0)):
        side = np.full(len(b), s)
        side[-1] = 0
        t = XL.simulate(b, side, EXIT, funding, fee=fee, slip=slip)
        # simulate indexes by the FILL bar; the signal bar is one before it
        pos = b.index.get_indexer(t["entry_time"]) - 1
        out.iloc[pos, out.columns.get_loc(col)] = t["net_r"].to_numpy()
    return out


def _span(index, a, b, purge: int = 0) -> np.ndarray:
    """Rows in [a, b), minus the last `purge` bars (their labels reach past b)."""
    a, b = pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")
    m = (index >= a) & (index < b)
    if purge:
        idx = np.flatnonzero(m)
        m[idx[-purge:]] = False
    return m


def fit(X: pd.DataFrame, y: pd.Series):
    """LightGBM's native API (no scikit-learn needed); fixed params, fixed rounds."""
    import lightgbm as lgb
    ok = y.notna()
    return lgb.train(LGB_PARAMS, lgb.Dataset(X[ok], y[ok]), num_boost_round=N_ROUNDS)


def decide(pl: np.ndarray, ps: np.ndarray, thr: float) -> np.ndarray:
    """+1 / -1 / 0: the side with the higher prediction, if it clears thr."""
    side = np.where(pl >= ps, 1.0, -1.0)
    best = np.maximum(pl, ps)
    return np.where(best > thr, side, 0.0)


def trades_of(b, side, funding, fee=C.FEE_TAKER, slip=C.SLIPPAGE) -> pd.DataFrame:
    return XL.simulate(b, side, EXIT, funding, fee=fee, slip=slip)


def account(b, side, funding, start, end) -> dict:
    """Reported, not a gate: the same signals through the real engine, one
    position at a time, on the research account (what a person could trade)."""
    from backtest import run_backtest
    atr = ta.atr_(b["high"], b["low"], b["close"], XL.ATR_N)
    act = side != 0
    sig = pd.DataFrame({"side": side, "stop_dist": np.where(act, EXIT["stop_atr"] * atr, np.nan),
                        "tp_dist": 0.0, "max_hold": np.where(act, EXIT["max_hold"], 0.0),
                        "atr": atr.to_numpy()}, index=b.index)
    m = run_backtest(b, sig, funding=funding, start_time=start, end_time=end,
                     initial_equity=C.EVAL_EQUITY).metrics
    keys = ("trades", "avg_r", "cagr", "max_dd", "win_rate", "size_skips")
    return {k: (float(m[k]) if isinstance(m.get(k), (int, float, np.floating, np.integer)) else m.get(k))
            for k in keys}


MIN_SHIFT = 168  # bars: a shifted copy must be at least a week away from the real timing


def shifted_means(side_w: np.ndarray, long_w: np.ndarray, short_w: np.ndarray,
                  n: int = N_RANDOM, seed: int = 19) -> np.ndarray:
    """Mean net R of n random circular time-shifts of the model's own signal
    sequence inside a window. A shift keeps everything about the signals
    (long and short counts, how they cluster in runs) except their alignment
    with the market. Picking scattered random bars instead (the first design)
    gives a control with far less spread than clustered, overlapping model
    trades, so noise beat its 95th percentile too often (found by test 16)."""
    m = len(side_w)
    if not (side_w != 0).any() or m <= 2 * MIN_SHIFT:
        return np.full(n, np.nan)
    rng = np.random.default_rng(seed)
    out = np.empty(n)
    for j in range(n):
        s = np.roll(side_w, int(rng.integers(MIN_SHIFT, m - MIN_SHIFT)))
        r = np.where(s > 0, long_w, np.where(s < 0, short_w, np.nan))
        out[j] = np.nanmean(r[s != 0]) if np.isfinite(r[s != 0]).any() else np.nan
    return out


def random_control(b, side, funding, window, n=N_RANDOM, seed=19) -> np.ndarray:
    """Mean net R of n time-shifted copies of the model's signals inside `window`."""
    idx = np.flatnonzero(window[:-1])
    lab = labels_cache["lab"]
    return shifted_means(np.asarray(side)[idx], lab["long"].to_numpy()[idx],
                         lab["short"].to_numpy()[idx], n=n, seed=seed)


labels_cache: dict = {}


def run(final: bool = False) -> None:
    import experiment as E
    bars = E.get_bars(TF)
    fund = E.load_funding()
    out = C.RESULTS / "s19_ml_entry_1h"
    out.mkdir(parents=True, exist_ok=True)
    res_path = out / "summary.json"
    X = features(bars, fund)
    lab = labels(bars, fund)
    labels_cache["lab"] = lab
    idx = bars.index
    if final:
        res = json.loads(res_path.read_text()) if res_path.exists() else None
        if not res or res["verdict"] != "PASS":
            raise SystemExit("--final refused: needs a PASS from the TRAIN/VALID run")
        lock = out / "holdout.json"
        if lock.exists():
            raise SystemExit(f"--final refused: holdout already used ({lock})")
        tr = _span(idx, *SPLITS["train"], purge=PURGE)
        ml, ms = fit(X[tr], lab["long"][tr]), fit(X[tr], lab["short"][tr])
        w = _span(idx, *SPLITS["holdout"], purge=PURGE)
        side = np.where(w, decide(ml.predict(X), ms.predict(X), res["threshold"]), 0.0)
        t = trades_of(bars, side, fund)
        h = XL.summarize(t)
        rnd = random_control(bars, side, fund, w)
        h["random_median"] = float(np.nanmedian(rnd)) if np.isfinite(rnd).any() else float("inf")
        h["verdict"] = ("CONFIRMED" if h.get("mean_r", -1) > 0 and (h.get("ci_lo") or -1) > 0
                        and h["mean_r"] > h["random_median"] else "FAILED")
        lock.write_text(json.dumps(h, indent=1))
        print(json.dumps(h, indent=1))
        return
    if res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    res = evaluate(bars, fund, X, lab)
    res_path.write_text(json.dumps(res, indent=1))
    write_report(res)
    print(f"\n{C.SYMBOL}: threshold {res['threshold']} -> {res['verdict']}  failed {res['gates_failed']}"
          f"\nVALID {res['valid']}")


def evaluate(bars: pd.DataFrame, fund, X: pd.DataFrame | None = None, lab: pd.DataFrame | None = None) -> dict:
    """TRAIN out-of-fold threshold -> final model -> VALID verdict (no files written)."""
    X = features(bars, fund) if X is None else X
    lab = labels(bars, fund) if lab is None else lab
    labels_cache["lab"] = lab
    idx = bars.index

    # 1. threshold from purged, expanding walk-forward folds inside TRAIN
    oof_l = pd.Series(np.nan, index=idx)
    oof_s = pd.Series(np.nan, index=idx)
    for a, b_, c_ in FOLDS:
        fm = _span(idx, a, b_, purge=PURGE)
        pm = _span(idx, b_, c_, purge=PURGE)  # scored labels stay inside TRAIN
        ml, ms = fit(X[fm], lab["long"][fm]), fit(X[fm], lab["short"][fm])
        oof_l[pm], oof_s[pm] = ml.predict(X[pm]), ms.predict(X[pm])
    oof_mask = oof_l.notna().to_numpy()
    thr_table = {}
    for thr in THRESHOLDS:
        side = np.where(oof_mask, decide(oof_l.fillna(-9).to_numpy(), oof_s.fillna(-9).to_numpy(), thr), 0.0)
        r = np.where(side > 0, lab["long"], np.where(side < 0, lab["short"], np.nan))
        r = r[(side != 0) & ~np.isnan(r)]
        thr_table[str(thr)] = {"trades": int(len(r)), "mean_r": float(np.nanmean(r)) if len(r) else None}
        print(f"OOF thr {thr:.2f}: {thr_table[str(thr)]}", flush=True)
    ok = {k: v for k, v in thr_table.items() if v["trades"] >= MIN_OOF_TRADES}
    thr = float(max(ok, key=lambda k: ok[k]["mean_r"])) if ok else THRESHOLDS[0]

    # 2. final model on all of TRAIN, frozen, applied to VALID
    tr = _span(idx, *SPLITS["train"], purge=PURGE)
    ml, ms = fit(X[tr], lab["long"][tr]), fit(X[tr], lab["short"][tr])
    # purged: a VALID trade must not run into HOLDOUT prices
    vw = _span(idx, *SPLITS["valid"], purge=PURGE)
    side = np.where(vw, decide(ml.predict(X), ms.predict(X), thr), 0.0)
    t = trades_of(bars, side, fund)
    v = XL.summarize(t)
    stress = XL.summarize(trades_of(bars, side, fund, fee=C.FEE_TAKER * 1.5, slip=C.SLIPPAGE * 1.5))
    rnd = random_control(bars, side, fund, vw)
    p95 = float(np.nanpercentile(rnd, 95)) if np.isfinite(rnd).any() else np.inf
    oof_mean = ok.get(str(thr), {}).get("mean_r") if ok else None
    gates = {"oof_mean>0": (oof_mean or -1) > 0,
             f"valid_trades>={MIN_VALID_TRADES}": v.get("trades", 0) >= MIN_VALID_TRADES,
             "valid_mean>0": v.get("mean_r", -1) > 0,
             "valid_ci_lo>0": (v.get("ci_lo") or -1) > 0,
             "stress_mean>0": stress.get("mean_r", -1) > 0,
             "beats_random_p95": v.get("mean_r", -9) > p95}
    failed = [k for k, g in gates.items() if not g]
    imp = sorted(zip(X.columns, ml.feature_importance() + ms.feature_importance()),
                 key=lambda x: -x[1])[:10]
    res = {"symbol": C.SYMBOL, "tf": TF, "exit": "time_only", "threshold": thr,
           "oof": thr_table, "valid": v, "valid_stress": stress,
           "valid_account": account(bars, side, fund, *SPLITS["valid"]),
           "valid_last_exit": str(t["entry_time"].max() + pd.Timedelta(minutes=TF) * int(
               t.loc[t["entry_time"].idxmax(), "bars"])) if len(t) else None,
           "random_mean": float(np.nanmean(rnd)) if np.isfinite(rnd).any() else None, "random_p95": p95,
           "verdict": "REJECT" if failed else "PASS", "gates_failed": failed,
           "top_features": [[k, int(s)] for k, s in imp]}
    return res


def write_report(r: dict) -> None:
    v = r["valid"]
    L = [f"# {C.SYMBOL} - ML entry model (PLAN.md section 19)", "",
         "GENERATED by `src/ml_entry.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}** (threshold {r['threshold']} R chosen on TRAIN out-of-fold; failed: "
         f"{r['gates_failed'] or 'none'})", "",
         f"- VALID {v.get('trades', 0)} trades: mean net R {v.get('mean_r', float('nan')):+.4f}, "
         f"95% weekly-block CI [{v.get('ci_lo', float('nan')):+.4f}, {v.get('ci_hi', float('nan')):+.4f}], "
         f"gross {v.get('gross_r', float('nan')):+.4f}, long {v.get('long_r', float('nan')):+.3f} / "
         f"short {v.get('short_r', float('nan')):+.3f}",
         f"- the model's signals shifted in time (same long/short counts and clustering): mean "
         f"{r['random_mean'] if r['random_mean'] is None else round(r['random_mean'], 4)}, 95th pct "
         f"{r['random_p95']:+.4f}",
         f"- cost x1.5: mean {r['valid_stress'].get('mean_r', float('nan')):+.4f}",
         f"- one position at a time through the engine (reported, not a gate): {r.get('valid_account')}", "",
         "| threshold | OOF trades | OOF mean net R |", "|---|---|---|"]
    for k, t in r["oof"].items():
        L.append(f"| {k} | {t['trades']} | {t['mean_r'] if t['mean_r'] is None else round(t['mean_r'], 4)} |")
    L += ["", "Top features: " + ", ".join(f"{k} ({s})" for k, s in r["top_features"]), ""]
    h = C.RESULTS / "s19_ml_entry_1h" / "holdout.json"
    if h.exists():
        hj = json.loads(h.read_text())
        L += [f"**HOLDOUT: {hj['verdict']}** - {hj['trades']} trades, mean {hj['mean_r']:+.4f}, "
              f"CI [{hj['ci_lo']:+.4f}, {hj['ci_hi']:+.4f}], random median {hj['random_median']:+.4f}", ""]
    (C.JOURNAL / "s19_ml_entry_1h.md").write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--final", action="store_true")
    run(ap.parse_args().final)


if __name__ == "__main__":
    main()
