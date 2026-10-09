"""ML forecasts WHEN a large coin will move; a breakout decides the side (PLAN.md section 40)

    python src/ml_vol.py            # TRAIN/VALID, once (uses section 36's caches; no new download)
    python src/ml_vol.py --final    # HOLDOUT once, only after PASS (shared with sections 31-39)

Why (_multi Exp 062/065): the direction forecasts of sections 37-39 are a
lagging regime signal - right while a regime lasts, wrong at the turn - and
their strongest input everywhere is BTC's 7-day volatility. Volatility
clusters and is far easier to forecast than direction.

Hypothesis: a LightGBM model can forecast which 4h bars start a large move
(the next day's range in ATRs). A price breakout taken ONLY when such a move
is forecast follows through more often than the same breakout taken at any
time, because the expected move is large against the fixed costs. The side
comes from the price itself (which way the range breaks), not from a forecast
whose level drifts with the regime.

Model: the ten large coins (from 365 days after listing), 4h decisions with
1h/1d closed-bar features (section 30's features), wide training rows
(section 36's members), section 30's 4h LightGBM setting, refit monthly
(walk-forward, expanding). Label: (highest high - lowest low) of the next
H_VOL = 6 bars (one day) divided by the ATR at the decision bar - always > 0,
no side.

Trading rule per coin (decided at the close of bar k, filled at the open of
k+1, section 31's account: confidence sizing up to 1% per trade, 5% cap per
direction, costs and funding, 8-ATR protective stop, NO clock):
  armed    the forecast is above its own rolling q-quantile (causal) -
           or always, in the rule-only baseline
  entry    armed and close[k] > highest high of the previous N bars -> long;
           armed and close[k] < lowest low of the previous N bars -> short;
           a new position only in a month the coin is traded
  exit     long: close[k] < lowest low of the previous N/2 bars; short: close
           > highest high of the previous N/2 bars; or an armed opposite
           breakout (reverse)
  conf     forecast / its rolling threshold (1 in the baseline) -> risk 0.5-1%
TRAIN (walk-forward 2021-22) picks 1 of 6 cells: arm in {none, q70, q85} x
N in {6 bars (1 day), 18 bars (3 days)}. Selection: section 38's rule (>= 100
trades, both TRAIN years and both legs positive, then the weekly t). No
selectable cell, or an arm=none choice (the rule without ML), is REJECT
(train_cell_selectable, train_chose_ml). VALID gates: section 37's.
Reported: the same breakout without ML on VALID (the chosen N, arm=none) as
the comparison the hypothesis is about, and the short share by year.
The run-time record (src/run_record.py) is written; skipped signals are the
breakouts the ML arm filtered out, with their realised next-day move x side.
Holdout: sections 31-40 share ONE holdout.
Writes results/_multi/s40_ml_vol_4h/ and journal/_multi/s40_ml_vol_4h.md.
"""
from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
import indicators as ta  # noqa: E402
import ml_entry as ME  # noqa: E402
import ml_hold as MH  # noqa: E402
import ml_large as ML  # noqa: E402
import ml_port as MP  # noqa: E402
import ml_rank as MRK  # noqa: E402
import ml_recent as MR  # noqa: E402
import ml_wf as WF  # noqa: E402
import ml_wf2 as W2  # noqa: E402
import ml_wide as MW  # noqa: E402
import run_record as RR  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "s40_ml_vol_4h"
REPORT = C.ROOT / "journal" / "_multi" / "s40_ml_vol_4h.md"

# ---- pre-registered (PLAN.md section 40, _multi Exp 066)
TF = 240
H_VOL = 6                                         # label: next day's range in ATRs
ARMS = {"none": None, "q70": 0.70, "q85": 0.85}
CHANNELS = (6, 18)                                # breakout lookback N (bars); exit channel N // 2
MIN_TRADES = ML.MIN_TRADES
LOCKS = MRK.LOCKS + (MRK.OUT,)                    # sections 31-39: one shared holdout


# --------------------------------------------------------------------------
# pure pieces (test 38)
# --------------------------------------------------------------------------
def vol_label(bars: pd.DataFrame, h: int = H_VOL) -> np.ndarray:
    """(max high - min low) over bars i+1..i+h divided by the ATR at i; NaN unless
    every bar in the window traded and bar i has a usable ATR. Aligned like
    ml_wide.label_h (all rows but the last)."""
    live = bars["volume"].to_numpy(float) > 0
    atr = ta.atr_(bars["high"], bars["low"], bars["close"], MH.ATR_N).to_numpy(float)
    hi = bars["high"].to_numpy(float)
    lo = bars["low"].to_numpy(float)
    n = len(bars)
    fut_hi = pd.Series(hi[::-1]).rolling(h, min_periods=h).max().to_numpy()[::-1]   # max of i..i+h-1
    fut_lo = pd.Series(lo[::-1]).rolling(h, min_periods=h).min().to_numpy()[::-1]
    rng = np.r_[fut_hi[1:], np.nan] - np.r_[fut_lo[1:], np.nan]                    # window i+1..i+h
    dead = np.r_[0, np.cumsum(~live)]
    i = np.arange(n)
    clean = (i + h < n) & (dead[np.minimum(i + 1 + h, n)] - dead[np.minimum(i + 1, n)] == 0) & live
    ok = clean & np.isfinite(atr) & (atr > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        y = np.where(ok, rng / atr, np.nan)
    return y[:-1]


def channels(b: pd.DataFrame, n: int) -> tuple[np.ndarray, ...]:
    """Highest high / lowest low of the previous n bars and of the previous n//2
    bars, at each bar (the bar itself excluded: causal at its close)."""
    h, lo = b["high"], b["low"]
    m = max(1, n // 2)
    return (h.shift(1).rolling(n, min_periods=n).max().to_numpy(), lo.shift(1).rolling(n, min_periods=n).min().to_numpy(),
            h.shift(1).rolling(m, min_periods=m).max().to_numpy(), lo.shift(1).rolling(m, min_periods=m).min().to_numpy())


def breakout_path(close: np.ndarray, hh: np.ndarray, ll: np.ndarray, xh: np.ndarray, xl: np.ndarray,
                  armed: np.ndarray, allowed: np.ndarray) -> np.ndarray:
    """Desired position (-1/0/+1) after each decision bar."""
    out, pos = np.zeros(len(close)), 0.0
    for t in range(len(close)):
        c = close[t]
        up = armed[t] and allowed[t] and np.isfinite(hh[t]) and c > hh[t]
        dn = armed[t] and allowed[t] and np.isfinite(ll[t]) and c < ll[t]
        if pos > 0 and ((np.isfinite(xl[t]) and c < xl[t]) or dn):
            pos = -1.0 if dn else 0.0
        elif pos < 0 and ((np.isfinite(xh[t]) and c > xh[t]) or up):
            pos = 1.0 if up else 0.0
        elif pos == 0:
            pos = 1.0 if up else (-1.0 if dn else 0.0)
        out[t] = pos
    return out


def arm(p: np.ndarray, q: float | None) -> tuple[np.ndarray, np.ndarray]:
    """(armed, confidence ratio): forecast above its causal rolling q-quantile."""
    if q is None:
        return np.ones(len(p), bool), np.ones(len(p))
    thr = np.full(len(p), np.nan)
    ok = np.isfinite(p)
    if ok.any():
        thr[ok] = pd.Series(p[ok]).rolling(MH.ROLL, min_periods=MH.MIN_ROLL).quantile(q).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(np.isfinite(thr) & (thr > 0), p / thr, np.nan)
    return np.isfinite(ratio) & (ratio > 1.0), ratio


def cells() -> list[tuple[str, int]]:
    return [(a, n) for a in ARMS for n in CHANNELS]


def cell_name(cell) -> str:
    return f"{cell[0]}_n{cell[1]}"


# --------------------------------------------------------------------------
def run_cell(P, pred, cell, a, b, traded, stress=1.0, keep_skipped=False):
    arm_name, n = cell
    fr, paths, skipped = [], {}, []
    for c in P:
        p = pred[c].reindex(P[c]["X"].index).to_numpy() if pred is not None else np.full(len(P[c]["X"]), 1.0)
        armed_all, ratio_all = arm(p, ARMS[arm_name])
        lo, hi, rows = MH._window(P, c, a, b)
        if not len(rows):
            continue
        tb = P[c].get("tbars", P[c]["bars"])
        hh, ll, xh, xl = channels(tb, n)
        k = P[c]["pos"][rows]
        idx = P[c]["X"].index[rows]
        allowed = MW.month_mask(idx, c, traded)
        close = tb["close"].to_numpy(float)[k]
        desired = breakout_path(close, hh[k], ll[k], xh[k], xl[k], armed_all[rows], allowed)
        if keep_skipped:
            ref = breakout_path(close, hh[k], ll[k], xh[k], xl[k], np.ones(len(rows), bool), allowed)
            lab = MW.label_h(P[c]["bars"], H_VOL)[rows]
            skipped.append(RR.skipped(idx, c, ref, desired, "breakout not armed", lab))
        if not np.any(desired != 0):
            continue
        tgt = np.full(hi - lo, np.nan)
        tgt[k - lo] = desired
        t = MH.simulate(tb.iloc[lo:hi], tgt, P[c]["atr"][lo:hi], P[c]["fund"],
                        fee=C.FEE_TAKER * stress, slip=P[c]["slip"] * stress, stop_atr=WF.STOP_ATR)
        if len(t):
            kk = P[c]["X"].index.get_indexer(t["entry_time"] - pd.Timedelta(minutes=TF))
            t["conf"] = np.where(kk >= 0, ratio_all[np.maximum(kk, 0)], np.nan)
        fr.append(t.assign(coin=c))
        paths[c] = (desired, rows, lo, hi)
    t = pd.concat(fr, ignore_index=True) if fr else pd.DataFrame(
        columns=["entry_time", "exit_time", "side", "net_r", "conf", "coin"])
    out = MP.size_trades(t, ML.SIZING, ML.CAP), paths
    return (*out, pd.concat(skipped, ignore_index=True) if skipped else None) if keep_skipped else out


def judge(P, pred, cell, a, b, traded, min_coins=ML.MIN_COINS):
    t, paths = run_cell(P, pred, cell, a, b, traded)
    acc = MP.account(t, a, b)
    acc["stress_weekly_mean"] = MP.account(run_cell(P, pred, cell, a, b, traded, 1.5)[0], a, b)["weekly_mean"]
    timing, per, pooled = MH.control({c: P[c] for c in paths}, paths)
    coins = {}
    for c in paths:
        tc = t[t["coin"] == c]
        coins[c] = {"trades": int(len(tc)), "mean_r": float(tc["net_r"].mean()) if len(tc) else None,
                    "timing": per[c]["timing"], "shift_median": MH._q(per[c]["shifts"], 50)}
    elig = {c: x for c, x in coins.items() if x["trades"] >= ML.MIN_COIN_TRADES}
    beat = [c for c, x in elig.items() if x["mean_r"] > 0 and x["timing"] is not None
            and x["shift_median"] is not None and x["timing"] > x["shift_median"]]
    w = MP.weekly(t, a, b)
    tot = float(w.sum())
    top = w.sort_values(ascending=False).iloc[:5]
    acc.update(timing=timing, shift_median=MH._q(pooled, 50), shift_p95=MH._q(pooled, 95), per_coin=coins,
               breadth={"eligible": len(elig), "beat": beat, "share": len(beat) / len(elig) if elig else 0.0},
               per_year_r={str(y): float(g["ret"].sum()) for y, g in t.groupby(pd.to_datetime(t["exit_time"]).dt.year)},
               top5_weeks_share=float(top.sum()) / tot if tot > 0 else None,
               weekly_mean_without_top5=float(w.drop(top.index).mean()) if len(w) > 5 else None,
               neg_weeks=int((w < 0).sum()), short_share=MR.short_share(t))
    return acc, t


def evaluate(P, pred, traded, min_coins=ML.MIN_COINS, keep=False) -> dict:
    a_tr, b_tr = WF.WINDOWS["train"]
    a_va, b_va = WF.WINDOWS["valid"]
    table, train_trades = [], {}
    for cell in cells():
        t, _ = run_cell(P, pred, cell, a_tr, b_tr, traded)
        train_trades[cell_name(cell)] = t
        acc = MP.account(t, a_tr, b_tr)
        row = {"form": cell_name(cell), "arm": cell[0], "channel": cell[1],
               **{k: acc[k] for k in ("trades", "weekly_mean", "tstat", "per_year", "max_dd", "mean_r",
                                      "long_ret", "short_ret")},
               "per_year_r": {str(y): float(g["ret"].sum()) for y, g in t.groupby(pd.to_datetime(t["exit_time"]).dt.year)},
               "short_share": MR.short_share(t)}
        row["selectable"] = MR.selectable(row, MIN_TRADES)
        table.append(row)
        print(f"TRAIN-WF {row['form']}: {acc['trades']} trades, weekly {acc['weekly_mean']:+.5f}, t {acc['tstat']:+.2f}, "
              f"years {row['per_year_r']}, selectable {row['selectable']}", flush=True)
    ok = [x for x in table if x["selectable"]]
    best = max(ok, key=lambda x: x["tstat"]) if ok else max(table, key=lambda x: x["tstat"])
    cell = (best["arm"], best["channel"])
    tj, _ = judge(P, pred, cell, a_tr, b_tr, traded, min_coins)
    train_checks = {k: tj[k] for k in ("trades", "weekly_mean", "ci_lo", "ci_hi", "tstat", "stress_weekly_mean",
                                       "timing", "shift_median", "shift_p95", "long_ret", "short_ret", "max_dd",
                                       "mean_r", "per_year_r", "top5_weeks_share")}
    train_checks["breadth"] = {k: tj["breadth"][k] for k in ("eligible", "share")}
    v, t = judge(P, pred, cell, a_va, b_va, traded, min_coins)
    base, _ = judge(P, pred, ("none", cell[1]), a_va, b_va, traded, min_coins)
    v["rule_only_same_channel"] = {k: base[k] for k in ("trades", "weekly_mean", "ci_lo", "ci_hi", "tstat", "mean_r",
                                                         "long_ret", "short_ret", "max_dd", "short_share")}
    gates = {"train_cell_selectable": bool(ok),
             "train_chose_ml": cell[0] != "none",
             "train_weekly_mean>0": best["weekly_mean"] > 0,
             f"valid_trades>={MIN_TRADES}": v["trades"] >= MIN_TRADES,
             "valid_weekly_mean>0": v["weekly_mean"] > 0,
             "valid_ci_lo>0": v["ci_lo"] > 0,
             "stress_weekly_mean>0": v["stress_weekly_mean"] > 0,
             "timing_beats_shift_p95": v["shift_p95"] is not None and v["timing"] is not None
             and v["timing"] > v["shift_p95"],
             f"coins>={min_coins}": v["breadth"]["eligible"] >= min_coins,
             f"breadth>={MP.BREADTH_SHARE}": v["breadth"]["share"] >= MP.BREADTH_SHARE,
             "both_legs>0": v["long_ret"] > 0 and v["short_ret"] > 0,
             f"max_dd<={MP.MAX_DD}": v["max_dd"] <= MP.MAX_DD}
    failed = [k for k, g in gates.items() if not g]
    res = {"chosen": {"form": best["form"], "arm": cell[0], "channel": cell[1], "tf": TF, "sizing": ML.SIZING,
                      "cap": ML.CAP},
           "train_table": table, "train_checks": train_checks, "valid": v,
           "verdict": "REJECT" if failed else "PASS", "gates_failed": failed,
           "model": {"tf": TF, "label": f"next {H_VOL} bars' range / ATR", "coins": list(ML.COINS), "arms": ARMS,
                     "channels": list(CHANNELS)}}
    if keep:
        res["_trades"] = t
        res["_train_trades"] = train_trades
    return res


# --------------------------------------------------------------------------
def _record(res, P, pred, keep, traded, started, inputs) -> None:
    feats = MH._cols(P)
    cell = (res["chosen"]["arm"], res["chosen"]["channel"])
    lab = {c: vol_label(P[c]["bars"]) for c in P}
    for split in ("train", "valid"):
        a, b = WF.WINDOWS[split]
        lo, hi = pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")
        ms = {m: mdl for m, mdl in keep["models"].items() if lo <= m < hi}
        Xm = {m: pd.concat([P[c]["X"].reindex(columns=feats)[(P[c]["X"].index >= m)
                                                             & (P[c]["X"].index < m + pd.offsets.MonthBegin(1))]
                            for c in P], ignore_index=True) for m in ms}
        imp = RR.importance(ms)
        imp["shap"] = RR.shap_summary(ms, Xm)
        preds = RR.predictions({c: P[c]["X"].index for c in P},
                               {c: pred[c].reindex(P[c]["X"].index).to_numpy() for c in P}, lab, a, b)
        _, _, sk = run_cell(P, pred, cell, a, b, traded, keep_skipped=True)
        logs = [r for r in keep["log"] if lo <= pd.Timestamp(r["month"], tz="UTC") < hi]
        ylab = pd.concat([pd.Series(lab[c][(P[c]["X"].index >= lo) & (P[c]["X"].index < hi)]) for c in P],
                         ignore_index=True)
        meta = RR.metadata(feats, list(P), logs, dict(ME.LGB_PARAMS, **MP._cfg(TF)["setting"]),
                           f"(max high - min low) of the next {H_VOL} 4h bars / ATR at the decision bar", (H_VOL,),
                           {"split": [a, b], "cell": res["chosen"]["form"]}, ylab)
        wk = MP.weekly(res["_trades"], a, b) if split == "valid" else None
        RR.write(OUT / "record" / split, feature_importance=imp, training_metadata=meta, predictions=preds,
                 skipped_signals=sk, run_info=RR.run_info(started, inputs),
                 holdout_power=RR.holdout_power(wk) if wk is not None else None)


def forecasts(P, cfg, masks, spans, keep=None, step: int = 1) -> dict:
    """Walk-forward forecasts of the next day's range (expanding window)."""
    Ph = {c: {**P[c], "y": pd.Series(np.where(masks[c], vol_label(P[c]["bars"]), np.nan), index=P[c]["X"].index)}
          for c in P}
    saved = WF.H_BARS
    WF.H_BARS = H_VOL                                     # the walk-forward lag is H_VOL + 1 bars
    try:
        pred = {c: np.full(len(P[c]["X"]), np.nan) for c in P}
        for a, b in spans:
            log, models = ([], {}) if keep is not None else (None, None)
            p = WF.walk_forward(Ph, TF, cfg, a, b, step=step, log=log, models=models)
            if keep is not None:
                keep.setdefault("log", []).extend(log)
                keep.setdefault("models", {}).update(models)
            for c in P:
                pred[c] = np.where(np.isfinite(p[c]), p[c], pred[c])
    finally:
        WF.H_BARS = saved
    return {c: pd.Series(pred[c], index=P[c]["X"].index) for c in P}


def run(final: bool = False) -> None:
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    res_path, lock = OUT / "summary.json", OUT / "holdout.json"
    if final:
        res = json.loads(res_path.read_text()) if res_path.exists() else None
        if not res or res["verdict"] != "PASS":
            raise SystemExit("--final refused: needs a PASS from the TRAIN/VALID run")
        for o in (OUT,) + LOCKS:
            if (o / "holdout.json").exists():
                raise SystemExit(f"--final refused: sections 31-40 share one holdout and {o.name} used it")
    elif res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    if not (MW.OUT / "members.json").exists():
        raise SystemExit("no section 36 member sets: run  python src/ml_wide.py --build  first")
    months, traded, by_tf, core, members = MR._load()
    inputs = [WF.cache_dir(TF) / f"{c}.parquet" for c in sorted(by_tf[TF])]
    spans = [WF.WINDOWS["train"], WF.WINDOWS["valid"]] + ([WF.WINDOWS["holdout"]] if final else [])
    print(f"[ml_vol] training coins {len(by_tf[TF])}; traded {len(ML.COINS)}", flush=True)
    P = W2.prepare(by_tf, TF)
    del by_tf
    gc.collect()
    masks = {c: MW.training_mask(P[c]["X"].index, c, core, members, True) for c in P}
    keep = {}
    pred_all = forecasts(P, MP._cfg(TF)["setting"], masks, spans, keep=keep)
    PT = {c: P[c] for c in ML.COINS if c in P}
    pred = {c: pred_all[c] for c in PT}
    if final:
        a, b = WF.WINDOWS["holdout"]
        h, t = judge(PT, pred, (res["chosen"]["arm"], res["chosen"]["channel"]), a, b, traded)
        h["verdict"] = ("CONFIRMED" if h["weekly_mean"] > 0 and h["ci_lo"] > 0 and h["shift_median"] is not None
                        and h["timing"] is not None and h["timing"] > h["shift_median"]
                        and h["breadth"]["share"] >= MP.BREADTH_SHARE else "FAILED")
        lock.write_text(json.dumps(h, indent=1, default=str))
        t.to_csv(OUT / "trades_holdout.csv.gz", index=False)
        write_report(res)
        print(json.dumps({k: h.get(k) for k in ("trades", "weekly_mean", "ci_lo", "verdict")}, indent=1))
        return
    res = evaluate(PT, pred, traded, keep=True)
    res["traded_from"] = {c: next((m for m in months if c in traded[m]), None) for c in ML.COINS}
    a_va, b_va = WF.WINDOWS["valid"]
    res["valid"]["forecast_vs_label_spearman"] = {}
    for s, (a, b) in (("train", WF.WINDOWS["train"]), ("valid", (a_va, b_va))):
        x, y = [], []
        for c in PT:
            idx = PT[c]["X"].index
            w = (idx >= pd.Timestamp(a, tz="UTC")) & (idx < pd.Timestamp(b, tz="UTC"))
            x.append(pred[c].reindex(idx).to_numpy()[w])
            y.append(vol_label(PT[c]["bars"])[w])
        x, y = np.concatenate(x), np.concatenate(y)
        ok = np.isfinite(x) & np.isfinite(y)
        res["valid"]["forecast_vs_label_spearman"][s] = float(pd.Series(x[ok]).rank().corr(pd.Series(y[ok]).rank()))
    _record(res, PT, pred, keep, traded, started, inputs)
    res.pop("_trades").to_csv(OUT / "trades_valid.csv.gz", index=False)
    for form, tt in res.pop("_train_trades").items():
        tt.to_csv(OUT / f"trades_train_{form}.csv.gz", index=False)
    res_path.write_text(json.dumps(res, indent=1, default=str))
    write_report(res)
    print(f"\nML_VOL: chose {res['chosen']['form']} -> {res['verdict']} failed {res['gates_failed']}")


def write_report(r: dict) -> None:
    v = r["valid"]
    f = (lambda x, k=5: "-" if x is None else f"{x:+.{k}f}")
    b = v.get("rule_only_same_channel", {})
    L = ["# ML forecasts when a large coin will move; a breakout decides the side (PLAN.md section 40)", "",
         "GENERATED by `src/ml_vol.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}** (TRAIN chose {r['chosen']['form']}; failed: {r['gates_failed'] or 'none'})", "",
         f"- volatility forecast vs realised range, Spearman: {v.get('forecast_vs_label_spearman')}",
         f"- VALID {v['trades']} trades: weekly {f(v['weekly_mean'])}, 95% CI [{f(v['ci_lo'])}, {f(v['ci_hi'])}], "
         f"t {v['tstat']:+.2f}; mean R {f(v['mean_r'], 4)}; long {f(v['long_ret'], 4)} / short {f(v['short_ret'], 4)}; "
         f"max DD {v['max_dd']:.4f}",
         f"- cost x1.5 {f(v['stress_weekly_mean'])}; timing {f(v['timing'], 4)} vs shifted p95 {f(v['shift_p95'], 4)}; "
         f"breadth {len(v['breadth']['beat'])} of {v['breadth']['eligible']}; short share {v['short_share']}",
         f"- the same breakout without ML (VALID): {b.get('trades')} trades, weekly {f(b.get('weekly_mean'))}, "
         f"CI [{f(b.get('ci_lo'))}, {f(b.get('ci_hi'))}], mean R {f(b.get('mean_r'), 4)}",
         f"- best 5 weeks = {f(v['top5_weeks_share'], 3)} of the total; weekly mean without them "
         f"{f(v['weekly_mean_without_top5'])}", "",
         "| cell | TRAIN trades | weekly mean | t | mean R | long | short | by year | short share | selectable |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for x in r["train_table"]:
        L.append(f"| {x['form']} | {x['trades']} | {f(x['weekly_mean'])} | {x['tstat']:+.2f} | {f(x['mean_r'], 4)} | "
                 f"{f(x['long_ret'], 4)} | {f(x['short_ret'], 4)} | {x['per_year_r']} | {x['short_share']} | "
                 f"{x['selectable']} |")
    hp = OUT / "holdout.json"
    if hp.exists():
        h = json.loads(hp.read_text())
        L += ["", f"## HOLDOUT: **{h['verdict']}** - {h['trades']} trades, weekly {f(h['weekly_mean'])}, "
                  f"CI lo {f(h['ci_lo'])}"]
    REPORT.write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--final", action="store_true", help="run the holdout once (needs PASS)")
    run(ap.parse_args().final)


if __name__ == "__main__":
    main()
