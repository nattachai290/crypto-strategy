"""Section 43's two-model book as 1h and 1d sub-models (PLAN.md section 45)

    python src/ml_tf.py              # both sub-models, TRAIN/VALID once each (resumable)
    python src/ml_tf.py --tf 60      # one sub-model (60 = 1h, 1440 = 1d)
    python src/ml_tf.py --final      # HOLDOUT once: ONE sub-model, only after PASS (shared with sections 31-44)

Why (_multi Exp 084):
- Section 43 (4h) is the best ten-coin book: CI lo -0.00039, t +1.40, DD 4.3%, 9/10 coins.
- Single changes to it are used up (sections 42/44, Exp 072/080/081), and the gap to the CI gate is sample size,
  not direction.
- The owner asked (2026-10-06) that every round run as 1h / 4h / 1d sub-models; sections 40-44 ran on 4h only.
- A 1h book decides 4x as often. If the per-trade edge holds, the t roughly doubles. Costs per R are higher at
  1h, so that is not given.

Hypothesis: section 43's mechanism transfers to other decision timeframes. That mechanism is:
- the range model times the breakout;
- the per-side arm removes the tilt;
- the direction model must agree on the side.
On 1h it gives a larger sample at a similar per-trade edge; on 1d a smaller one at a larger edge.

Each sub-model is built from the same parts as section 43, at its own timeframe:
  range model   next DAY's range / ATR (h = 1 day in bars: 24 on 1h, 1 on 1d), section 30's setting for that tf,
                wide rows, expanding monthly walk-forward
  arm           side (section 41): q-quantile of the forecasts at the coin's last 60 same-side breakouts
  direction     section 38's sub-model for that tf as its TRAIN chose it (1h `expanding`, 1d `roll24`), 1-3 day
                horizons; checked against section 38's recorded TRAIN forecasts (`reproduces_s38_dir`)
  exit          the N/2 opposite channel or the 8-ATR stop of that tf, no clock; section 31's account
Cells per sub-model: q {0.70, 0.85} x N {1 day, 3 days} (the day lengths of section 40's 6/18 bars on 4h), each
in form `none` (no direction filter) and `sign` (section 43's agreement).
TRAIN picks among the `sign` cells by section 38's rule. A sub-model is REJECT if:
- no sign cell is selectable;
- the chosen sign cell beats its own `none` cell by a TRAIN t of less than +0.5 (`train_margin>=0.5`).
VALID gates: section 43's, per sub-model.
Holdout: ONE sub-model may take it - the PASS one with the highest TRAIN t (as section 38). Sections 31-45 share
ONE holdout.
Writes results/_multi/s45_ml_tf/{1h,1d}/ and journal/_multi/s45_ml_tf.md.
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
import ml_agree as MA  # noqa: E402
import ml_entry as ME  # noqa: E402
import ml_exit as MX  # noqa: E402
import ml_hold as MH  # noqa: E402
import ml_large as ML  # noqa: E402
import ml_meta as MM  # noqa: E402
import ml_port as MP  # noqa: E402
import ml_recent as MR  # noqa: E402
import ml_side as MS  # noqa: E402
import ml_vol as MV  # noqa: E402
import ml_wf as WF  # noqa: E402
import ml_wf2 as W2  # noqa: E402
import ml_wide as MW  # noqa: E402
import run_record as RR  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "s45_ml_tf"
REPORT = C.ROOT / "journal" / "_multi" / "s45_ml_tf.md"

# ---- pre-registered (PLAN.md section 45, _multi Exp 085)
TFS = (60, 1440)
TF_NAME = {60: "1h", 240: "4h", 1440: "1d"}
DIR_SCHEME = {60: "expanding", 240: "hl12", 1440: "roll24"}   # section 38's TRAIN choice per tf
QS = ("q70", "q85")
N_DAYS = (1, 3)
FORMS = ("none", "sign")
MIN_MARGIN = MA.MIN_MARGIN
MIN_TRADES = ML.MIN_TRADES
LOCKS = MM.LOCKS + (MM.OUT,)                      # sections 31-44: one shared holdout


# --------------------------------------------------------------------------
# pure pieces (test 43)
# --------------------------------------------------------------------------
def day_bars(tf: int, days: int = 1) -> int:
    return max(1, days * 1440 // tf)


def cells(tf: int) -> list[tuple[str, str, int]]:
    """(form, q, N bars) for one sub-model."""
    return [(f, q, day_bars(tf, d)) for f in FORMS for q in QS for d in N_DAYS]


def cell_name(cell) -> str:
    return f"{cell[0]}_{cell[1]}_n{cell[2]}"


# --------------------------------------------------------------------------
def run_cell(P, pred, dirp, cell, tf, a, b, traded, stress=1.0, keep_skipped=False):
    form, q, n = cell
    fr, paths, skipped = [], {}, []
    for c in P:
        idx_all = P[c]["X"].index
        p = pred[c].reindex(idx_all).to_numpy()
        d = dirp[c].reindex(idx_all).to_numpy()
        tb = P[c].get("tbars", P[c]["bars"])
        hh, ll, xh, xl = MV.channels(tb, n)
        kall = P[c]["pos"]
        close_all = tb["close"].to_numpy(float)[kall]
        au, ad, ru, rd = MS.arms(p, close_all, hh[kall], ll[kall], "side", q)
        bu, bd = MA.agree_arms(au, ad, d, form)
        lo, hi, rows = MH._window(P, c, a, b)
        if not len(rows):
            continue
        k = kall[rows]
        idx = idx_all[rows]
        allowed = MW.month_mask(idx, c, traded)
        close = close_all[rows]
        desired = MS.side_path(close, hh[k], ll[k], xh[k], xl[k], bu[rows], bd[rows], allowed)
        if keep_skipped:
            ref = MS.side_path(close, hh[k], ll[k], xh[k], xl[k], au[rows], ad[rows], allowed)
            lab = MW.label_h(P[c]["bars"], day_bars(tf))[rows]
            skipped.append(RR.skipped(idx, c, ref, desired, "direction forecast disagrees", lab))
        if not np.any(desired != 0):
            continue
        tgt = np.full(hi - lo, np.nan)
        tgt[k - lo] = desired
        t = MH.simulate(tb.iloc[lo:hi], tgt, P[c]["atr"][lo:hi], P[c]["fund"],
                        fee=C.FEE_TAKER * stress, slip=P[c]["slip"] * stress, stop_atr=WF.STOP_ATR)
        if len(t):
            kk = idx_all.get_indexer(t["entry_time"] - pd.Timedelta(minutes=tf))
            kk0 = np.maximum(kk, 0)
            t["conf"] = np.where(kk >= 0, np.where(t["side"].to_numpy() > 0, ru[kk0], rd[kk0]), np.nan)
            t["dir_fc"] = np.where(kk >= 0, d[kk0], np.nan)
        fr.append(t.assign(coin=c))
        paths[c] = (desired, rows, lo, hi)
    t = pd.concat(fr, ignore_index=True) if fr else pd.DataFrame(
        columns=["entry_time", "exit_time", "side", "net_r", "conf", "coin"])
    out = MP.size_trades(t, ML.SIZING, ML.CAP), paths
    return (*out, pd.concat(skipped, ignore_index=True) if skipped else None) if keep_skipped else out


def judge(P, pred, dirp, cell, tf, a, b, traded, min_coins=ML.MIN_COINS):
    t, paths = run_cell(P, pred, dirp, cell, tf, a, b, traded)
    acc = MP.account(t, a, b)
    acc["stress_weekly_mean"] = MP.account(run_cell(P, pred, dirp, cell, tf, a, b, traded, 1.5)[0],
                                           a, b)["weekly_mean"]
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
               neg_weeks=int((w < 0).sum()), short_share=MR.short_share(t), hold=MX.hold_stats(t),
               side_mean_r={("long" if s > 0 else "short"): float(g["net_r"].mean()) for s, g in t.groupby("side")},
               gross_r=float(t["gross_r"].mean()) if "gross_r" in t and len(t) else None)
    return acc, t


def evaluate(P, pred, dirp, tf, traded, min_coins=ML.MIN_COINS, keep=False) -> dict:
    a_tr, b_tr = WF.WINDOWS["train"]
    a_va, b_va = WF.WINDOWS["valid"]
    table, train_trades = [], {}
    for cell in cells(tf):
        t, _ = run_cell(P, pred, dirp, cell, tf, a_tr, b_tr, traded)
        train_trades[cell_name(cell)] = t
        acc = MP.account(t, a_tr, b_tr)
        row = {"form": cell_name(cell), "filter": cell[0], "q": cell[1], "channel": cell[2],
               **{k: acc[k] for k in ("trades", "weekly_mean", "tstat", "per_year", "max_dd", "mean_r",
                                      "long_ret", "short_ret")},
               "per_year_r": {str(y): float(g["ret"].sum()) for y, g in t.groupby(pd.to_datetime(t["exit_time"]).dt.year)},
               "short_share": MR.short_share(t), "hold": MX.hold_stats(t)}
        row["selectable"] = MR.selectable(row, MIN_TRADES)
        table.append(row)
        print(f"TRAIN-WF {TF_NAME[tf]} {row['form']}: {acc['trades']} trades, weekly {acc['weekly_mean']:+.5f}, "
              f"t {acc['tstat']:+.2f}, years {row['per_year_r']}, selectable {row['selectable']}", flush=True)
    signs = [x for x in table if x["filter"] == "sign"]
    ok = [x for x in signs if x["selectable"]]
    best = max(ok, key=lambda x: x["tstat"]) if ok else max(signs, key=lambda x: x["tstat"])
    cell = ("sign", best["q"], best["channel"])
    twin = next(x for x in table if x["filter"] == "none" and x["q"] == best["q"] and x["channel"] == best["channel"])
    margin = best["tstat"] - twin["tstat"]
    tj, _ = judge(P, pred, dirp, cell, tf, a_tr, b_tr, traded, min_coins)
    train_checks = {k: tj[k] for k in ("trades", "weekly_mean", "ci_lo", "ci_hi", "tstat", "stress_weekly_mean",
                                       "timing", "shift_median", "shift_p95", "long_ret", "short_ret", "max_dd",
                                       "mean_r", "per_year_r", "top5_weeks_share", "hold", "side_mean_r", "gross_r")}
    train_checks["breadth"] = {k: tj["breadth"][k] for k in ("eligible", "share")}
    v, t = judge(P, pred, dirp, cell, tf, a_va, b_va, traded, min_coins)
    nv, _ = judge(P, pred, dirp, ("none", cell[1], cell[2]), tf, a_va, b_va, traded, min_coins)
    v["none_same_cell"] = {k: nv[k] for k in ("trades", "weekly_mean", "ci_lo", "ci_hi", "tstat", "mean_r",
                                              "long_ret", "short_ret", "max_dd", "short_share", "side_mean_r")}
    v["dir_by_year"] = MA.dir_by_year(P, dirp, a_va, b_va)
    gates = {"train_cell_selectable": bool(ok),
             f"train_margin>={MIN_MARGIN}": margin >= MIN_MARGIN,
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
    res = {"chosen": {"form": best["form"], "q": cell[1], "channel": cell[2], "tf": tf, "dir": DIR_SCHEME[tf],
                      "sizing": ML.SIZING, "cap": ML.CAP},
           "train_table": table, "train_margin": margin, "train_checks": train_checks, "valid": v,
           "verdict": "REJECT" if failed else "PASS", "gates_failed": failed,
           "model": {"tf": tf, "range_label": f"next {day_bars(tf)} bars' range / ATR (one day)",
                     "direction": f"section 38 {TF_NAME[tf]} {DIR_SCHEME[tf]}, horizons {MR.horizons(tf)}",
                     "coins": list(ML.COINS), "qs": list(QS), "n_days": list(N_DAYS), "min_margin": MIN_MARGIN}}
    if keep:
        res["_trades"] = t
        res["_train_trades"] = train_trades
    return res


# --------------------------------------------------------------------------
def range_forecasts(P, tf, cfg, masks, spans, keep=None, step: int = 1) -> dict:
    """Section 40's range model at tf: label = next day's range / ATR, lag one day + 1 bar."""
    h = day_bars(tf)
    Ph = {c: {**P[c], "y": pd.Series(np.where(masks[c], MV.vol_label(P[c]["bars"], h), np.nan),
                                     index=P[c]["X"].index)} for c in P}
    saved = WF.H_BARS
    WF.H_BARS = h
    try:
        pred = {c: np.full(len(P[c]["X"]), np.nan) for c in P}
        for a, b in spans:
            log, models = ([], {}) if keep is not None else (None, None)
            p = WF.walk_forward(Ph, tf, cfg, a, b, step=step, log=log, models=models)
            if keep is not None:
                keep.setdefault("log", []).extend(log)
                keep.setdefault("models", {}).update(models)
            for c in P:
                pred[c] = np.where(np.isfinite(p[c]), p[c], pred[c])
    finally:
        WF.H_BARS = saved
    return {c: pd.Series(pred[c], index=P[c]["X"].index) for c in P}


def _check_dir(PT, dirp, tf) -> bool | None:
    f = MR.OUT / TF_NAME[tf] / "record" / "train" / "predictions.parquet"
    if not f.exists():
        return None
    ref = pd.read_parquet(f)
    got = pd.concat([pd.DataFrame({"time": dirp[c].index, "coin": c, "mine": dirp[c].to_numpy()}) for c in PT])
    m = ref.merge(got, on=["time", "coin"], how="inner")
    ok = np.isfinite(m["forecast"]) & np.isfinite(m["mine"])
    return bool(len(m) and ok.any() and np.allclose(m.loc[ok, "forecast"], m.loc[ok, "mine"], atol=1e-5))


def _record(res, P, pred, keep, traded, started, inputs, tf, out) -> None:
    feats = MH._cols(P)
    h = day_bars(tf)
    lab = {c: MV.vol_label(P[c]["bars"], h) for c in P}
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
        logs = [r for r in keep["log"] if lo <= pd.Timestamp(r["month"], tz="UTC") < hi]
        ylab = pd.concat([pd.Series(lab[c][(P[c]["X"].index >= lo) & (P[c]["X"].index < hi)]) for c in P],
                         ignore_index=True)
        meta = RR.metadata(feats, list(P), logs, dict(ME.LGB_PARAMS, **MP._cfg(tf)["setting"]),
                           f"(max high - min low) of the next {h} {TF_NAME[tf]} bars / ATR", (h,),
                           {"split": [a, b], "cell": res["chosen"]["form"]}, ylab)
        wk = MP.weekly(res["_trades"], a, b) if split == "valid" else None
        RR.write(out / "record" / split, feature_importance=imp, training_metadata=meta, predictions=preds,
                 run_info=RR.run_info(started, inputs), holdout_power=RR.holdout_power(wk) if wk is not None else None)


def run_tf(tf, months, traded, by_tf, core, members, final_res: dict | None = None) -> None:
    started = time.time()
    out = OUT / TF_NAME[tf]
    out.mkdir(parents=True, exist_ok=True)
    inputs = [WF.cache_dir(tf) / f"{c}.parquet" for c in sorted(by_tf[tf])]
    spans = [WF.WINDOWS["train"], WF.WINDOWS["valid"]] + ([WF.WINDOWS["holdout"]] if final_res else [])
    print(f"[ml_tf {TF_NAME[tf]}] training coins {len(by_tf[tf])}; traded {len(ML.COINS)}", flush=True)
    P = W2.prepare(by_tf, tf)
    masks = {c: MW.training_mask(P[c]["X"].index, c, core, members, True) for c in P}
    setting = MP._cfg(tf)["setting"]
    keep = {}
    pred_all = range_forecasts(P, tf, setting, masks, spans, keep=keep)
    print(f"[ml_tf {TF_NAME[tf]}] range forecasts done; direction ({DIR_SCHEME[tf]}) next", flush=True)
    per_h = MR.forecasts_w(P, tf, setting, masks, spans, DIR_SCHEME[tf])
    PT = {c: P[c] for c in ML.COINS if c in P}
    dirp = ML.combine_set(PT, per_h, MR.horizons(tf))
    del per_h
    gc.collect()
    pred = {c: pred_all[c] for c in PT}
    if final_res:
        a, b = WF.WINDOWS["holdout"]
        ch = final_res["chosen"]
        h, t = judge(PT, pred, dirp, ("sign", ch["q"], ch["channel"]), tf, a, b, traded)
        h["tf"] = tf
        h["verdict"] = ("CONFIRMED" if h["weekly_mean"] > 0 and h["ci_lo"] > 0 and h["shift_median"] is not None
                        and h["timing"] is not None and h["timing"] > h["shift_median"]
                        and h["breadth"]["share"] >= MP.BREADTH_SHARE else "FAILED")
        (OUT / "holdout.json").write_text(json.dumps(h, indent=1, default=str))
        t.to_csv(out / "trades_holdout.csv.gz", index=False)
        print(json.dumps({k: h.get(k) for k in ("tf", "trades", "weekly_mean", "ci_lo", "verdict")}, indent=1))
        return
    res = evaluate(PT, pred, dirp, tf, traded, keep=True)
    res["traded_from"] = {c: next((m for m in months if c in traded[m]), None) for c in ML.COINS}
    res["reproduces_s38_dir"] = _check_dir(PT, dirp, tf)
    print(f"[ml_tf {TF_NAME[tf]}] reproduces section 38 direction: {res['reproduces_s38_dir']}", flush=True)
    _record(res, PT, pred, keep, traded, started, inputs, tf, out)
    res.pop("_trades").to_csv(out / "trades_valid.csv.gz", index=False)
    for form, tt in res.pop("_train_trades").items():
        tt.to_csv(out / f"trades_train_{form}.csv.gz", index=False)
    (out / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    print(f"\nML_TF {TF_NAME[tf]}: chose {res['chosen']['form']} -> {res['verdict']} failed {res['gates_failed']}")


def run(tf: int | None = None, final: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if final:
        res = {t: json.loads((OUT / TF_NAME[t] / "summary.json").read_text()) for t in TFS
               if (OUT / TF_NAME[t] / "summary.json").exists()}
        pick = MR.holdout_pick(res)
        if pick is None:
            raise SystemExit("--final refused: no sub-model is PASS")
        for o in (OUT,) + LOCKS:
            if (o / "holdout.json").exists():
                raise SystemExit(f"--final refused: sections 31-45 share one holdout and {o.name} used it")
        months, traded, by_tf, core, members = MR._load()
        run_tf(pick, months, traded, by_tf, core, members, final_res=res[pick])
        write_report()
        return
    todo = [tf] if tf else list(TFS)
    todo = [t for t in todo if not (OUT / TF_NAME[t] / "summary.json").exists()]
    if not todo:
        raise SystemExit(f"{OUT} has every requested sub-model: pre-registered, run once "
                         "(delete only after a journaled code fix)")
    if not (MW.OUT / "members.json").exists():
        raise SystemExit("no section 36 member sets: run  python src/ml_wide.py --build  first")
    months, traded, by_tf, core, members = MR._load()
    for t in todo:
        run_tf(t, months, traded, by_tf, core, members)
        gc.collect()
    write_report()


def write_report() -> None:
    f = (lambda x, k=5: "-" if x is None else f"{x:+.{k}f}")
    L = ["# Section 43's two-model book as 1h and 1d sub-models (PLAN.md section 45)", "",
         "GENERATED by `src/ml_tf.py`. Do not edit by hand.", ""]
    for tf in TFS:
        sp = OUT / TF_NAME[tf] / "summary.json"
        if not sp.exists():
            L += [f"## {TF_NAME[tf]}: not run yet", ""]
            continue
        r = json.loads(sp.read_text())
        v, o = r["valid"], r["valid"].get("none_same_cell", {})
        L += [f"## {TF_NAME[tf]}: **{r['verdict']}** (TRAIN chose {r['chosen']['form']}; failed: "
              f"{r['gates_failed'] or 'none'})", "",
              f"- reproduces section 38 direction ({DIR_SCHEME[tf]}): {r.get('reproduces_s38_dir')}; "
              f"TRAIN t margin sign - none: {f(r.get('train_margin'), 2)}",
              f"- VALID {v['trades']} trades: weekly {f(v['weekly_mean'])}, 95% CI [{f(v['ci_lo'])}, {f(v['ci_hi'])}], "
              f"t {v['tstat']:+.2f}; mean R {f(v['mean_r'], 4)} (gross {f(v.get('gross_r'), 4)}); long "
              f"{f(v['long_ret'], 4)} / short {f(v['short_ret'], 4)}; per-trade by side {v.get('side_mean_r')}; "
              f"max DD {v['max_dd']:.4f}; hold {v.get('hold')}",
              f"- cost x1.5 {f(v['stress_weekly_mean'])}; timing {f(v['timing'], 4)} vs shifted p95 "
              f"{f(v['shift_p95'], 4)}; breadth {len(v['breadth']['beat'])} of {v['breadth']['eligible']}; "
              f"short share {v['short_share']}",
              f"- the same cell without the direction filter (VALID): {o.get('trades')} trades, weekly "
              f"{f(o.get('weekly_mean'))}, CI [{f(o.get('ci_lo'))}, {f(o.get('ci_hi'))}], mean R {f(o.get('mean_r'), 4)}",
              f"- direction forecast on VALID by year: {v.get('dir_by_year')}",
              f"- best 5 weeks = {f(v['top5_weeks_share'], 3)} of the total; weekly mean without them "
              f"{f(v['weekly_mean_without_top5'])}", "",
              "| cell | TRAIN trades | weekly mean | t | mean R | long | short | by year | selectable |",
              "|---|---|---|---|---|---|---|---|---|"]
        for x in r["train_table"]:
            L.append(f"| {x['form']} | {x['trades']} | {f(x['weekly_mean'])} | {x['tstat']:+.2f} | "
                     f"{f(x['mean_r'], 4)} | {f(x['long_ret'], 4)} | {f(x['short_ret'], 4)} | {x['per_year_r']} | "
                     f"{x['selectable']} |")
        L.append("")
    hp = OUT / "holdout.json"
    if hp.exists():
        h = json.loads(hp.read_text())
        L += [f"## HOLDOUT ({TF_NAME.get(h.get('tf'), h.get('tf'))}): **{h['verdict']}** - {h['trades']} trades, "
              f"weekly {f(h['weekly_mean'])}, CI lo {f(h['ci_lo'])}"]
    REPORT.write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tf", type=int, choices=TFS, help="run one sub-model")
    ap.add_argument("--final", action="store_true", help="run the holdout once (needs a PASS sub-model)")
    a = ap.parse_args()
    run(a.tf, a.final)


if __name__ == "__main__":
    main()
