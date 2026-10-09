"""Two ML models together: the range model says WHEN, the direction model must agree on WHICH WAY (PLAN.md section 43)

    python src/ml_agree.py            # TRAIN/VALID, once (uses section 36's caches; no new download)
    python src/ml_agree.py --final    # HOLDOUT once, only after PASS (shared with sections 31-42)

Why (_multi Exp 076, a read-only diagnostic of recorded TRAIN files): section 41's TRAIN trades
(side_q70_n6, 992 trades), each joined to section 38 4h's recorded walk-forward direction forecast
(hl12, 1-3 day horizons) at the decision bar:

| breakout side vs direction forecast sign | trades | mean R |
|---|---|---|
| agree | 563 | +0.039 (long +0.032, short +0.045) |
| disagree | 429 | -0.017 (long -0.022, short -0.013) |

- The difference is +0.056 R, with t +2.57.
- It holds in 2021 (+0.043 vs -0.029) and in 2022 (+0.037 vs -0.007).
- Agreement beats disagreement on 7 of 10 coins.
- It holds in every other section 41 cell tried: `side_q85_n6`, `pooled_q70_n6`, `side_q70_n18`.

Each model is weak alone:
- the range forecast knows when a move starts, not its side (section 40-42);
- the direction forecast ranks bars but its level lags the regime (sections 37-39).

A breakout that both agree on is the first trade in this line where two independent ML signals point the
same way.

Hypothesis: a breakout taken when the range model expects a large move AND the direction model leans the
same way follows through more often than one the direction model disagrees with.

Known weakness, stated before the run:
- the filter was found by looking at TRAIN trades, so the TRAIN comparison below is not independent
  evidence; VALID decides;
- section 38's direction forecasts leaned short in 2023-24 (short share 0.55/0.64), so in the bull VALID the
  filter may cut more good longs than bad shorts.

Unchanged from section 41:
- the range forecasts;
- the arm, frozen at section 41's TRAIN choice (side / q70 / N = 6);
- the N/2 channel exit and the 8-ATR stop, no clock;
- section 31's account.
The direction forecasts are section 38 4h's (hl12, horizons 6/12/18 bars, section 36's ensemble) recomputed;
they must match section 38's recorded TRAIN forecasts (`reproduces_s38_dir`).

Forms:
  none   section 41 (must reproduce section 41's TRAIN row side_q70_n6, `reproduces_s41`)
  sign   a side is armed only where section 41 arms it AND sign(direction forecast) equals that side; an
         opposite breakout without agreement does not reverse the position

TRAIN picks by section 38's rule. These are REJECT:
- `sign` not selectable;
- `none` chosen;
- a TRAIN t gain of `sign` over `none` smaller than +0.5 (`train_margin>=0.5`, pre-registered after
  _multi Exp 075: a near-tie is not a choice).

VALID gates: section 41's. Reported:
- the `none` book on VALID (= section 41);
- the agreement share and each side's kept share;
- the direction forecast's mean and short share by year.

Holdout: sections 31-43 share ONE holdout.
Writes results/_multi/s43_ml_agree_4h/ and journal/_multi/s43_ml_agree_4h.md.
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
import ml_entry as ME  # noqa: E402
import ml_exit as MX  # noqa: E402
import ml_hold as MH  # noqa: E402
import ml_large as ML  # noqa: E402
import ml_port as MP  # noqa: E402
import ml_recent as MR  # noqa: E402
import ml_side as MS  # noqa: E402
import ml_vol as MV  # noqa: E402
import ml_wf as WF  # noqa: E402
import ml_wf2 as W2  # noqa: E402
import ml_wide as MW  # noqa: E402
import run_record as RR  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "s43_ml_agree_4h"
REPORT = C.ROOT / "journal" / "_multi" / "s43_ml_agree_4h.md"

# ---- pre-registered (PLAN.md section 43, _multi Exp 077)
TF = MV.TF
ARM = MX.ARM                                      # ("side", "q70", 6): section 41's TRAIN choice, frozen
DIR_SCHEME = "hl12"                               # section 38 4h's TRAIN choice, frozen
FORMS = ("none", "sign")
MIN_MARGIN = 0.5                                  # TRAIN t gain sign - none
MIN_TRADES = ML.MIN_TRADES
LOCKS = MX.LOCKS + (MX.OUT,)                      # sections 31-42: one shared holdout


# --------------------------------------------------------------------------
# pure piece (test 41)
# --------------------------------------------------------------------------
def agree_arms(au: np.ndarray, ad: np.ndarray, d: np.ndarray, form: str) -> tuple[np.ndarray, np.ndarray]:
    """Section 41's per-side arms, kept only where the direction forecast's sign agrees (form sign);
    a NaN direction forecast arms nothing."""
    if form == "none":
        return au, ad
    d = np.asarray(d, float)
    with np.errstate(invalid="ignore"):
        return au & (d > 0), ad & (d < 0)


# --------------------------------------------------------------------------
def run_cell(P, pred, dirp, form, a, b, traded, stress=1.0, keep_skipped=False):
    arm_form, q, n = ARM
    fr, paths, skipped = [], {}, []
    for c in P:
        p = pred[c].reindex(P[c]["X"].index).to_numpy()
        d = dirp[c].reindex(P[c]["X"].index).to_numpy()
        tb = P[c].get("tbars", P[c]["bars"])
        hh, ll, xh, xl = MV.channels(tb, n)
        kall = P[c]["pos"]
        close_all = tb["close"].to_numpy(float)[kall]
        au, ad, ru, rd = MS.arms(p, close_all, hh[kall], ll[kall], arm_form, q)
        bu, bd = agree_arms(au, ad, d, form)
        lo, hi, rows = MH._window(P, c, a, b)
        if not len(rows):
            continue
        k = kall[rows]
        idx = P[c]["X"].index[rows]
        allowed = MW.month_mask(idx, c, traded)
        close = close_all[rows]
        desired = MS.side_path(close, hh[k], ll[k], xh[k], xl[k], bu[rows], bd[rows], allowed)
        if keep_skipped:
            ref = MS.side_path(close, hh[k], ll[k], xh[k], xl[k], au[rows], ad[rows], allowed)
            lab = MW.label_h(P[c]["bars"], MV.H_VOL)[rows]
            skipped.append(RR.skipped(idx, c, ref, desired, "direction forecast disagrees", lab))
        if not np.any(desired != 0):
            continue
        tgt = np.full(hi - lo, np.nan)
        tgt[k - lo] = desired
        t = MH.simulate(tb.iloc[lo:hi], tgt, P[c]["atr"][lo:hi], P[c]["fund"],
                        fee=C.FEE_TAKER * stress, slip=P[c]["slip"] * stress, stop_atr=WF.STOP_ATR)
        if len(t):
            kk = P[c]["X"].index.get_indexer(t["entry_time"] - pd.Timedelta(minutes=TF))
            kk0 = np.maximum(kk, 0)
            t["conf"] = np.where(kk >= 0, np.where(t["side"].to_numpy() > 0, ru[kk0], rd[kk0]), np.nan)
            t["dir_fc"] = np.where(kk >= 0, d[kk0], np.nan)
        fr.append(t.assign(coin=c))
        paths[c] = (desired, rows, lo, hi)
    t = pd.concat(fr, ignore_index=True) if fr else pd.DataFrame(
        columns=["entry_time", "exit_time", "side", "net_r", "conf", "coin"])
    out = MP.size_trades(t, ML.SIZING, ML.CAP), paths
    return (*out, pd.concat(skipped, ignore_index=True) if skipped else None) if keep_skipped else out


def judge(P, pred, dirp, form, a, b, traded, min_coins=ML.MIN_COINS):
    t, paths = run_cell(P, pred, dirp, form, a, b, traded)
    acc = MP.account(t, a, b)
    acc["stress_weekly_mean"] = MP.account(run_cell(P, pred, dirp, form, a, b, traded, 1.5)[0], a, b)["weekly_mean"]
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
               neg_weeks=int((w < 0).sum()), short_share=MR.short_share(t), hold=MX.hold_stats(t))
    return acc, t


def dir_by_year(P, dirp, a, b) -> dict:
    """Mean direction forecast and share of bars below zero, by year, over the traded coins."""
    x = pd.concat([dirp[c][(dirp[c].index >= pd.Timestamp(a, tz="UTC")) & (dirp[c].index < pd.Timestamp(b, tz="UTC"))]
                   for c in P]).dropna()
    return {str(y): {"mean": float(g.mean()), "share_below_0": float((g < 0).mean())}
            for y, g in x.groupby(x.index.year)}


def evaluate(P, pred, dirp, traded, min_coins=ML.MIN_COINS, keep=False) -> dict:
    a_tr, b_tr = WF.WINDOWS["train"]
    a_va, b_va = WF.WINDOWS["valid"]
    table, train_trades = [], {}
    for form in FORMS:
        t, _ = run_cell(P, pred, dirp, form, a_tr, b_tr, traded)
        train_trades[form] = t
        acc = MP.account(t, a_tr, b_tr)
        row = {"form": form, **{k: acc[k] for k in ("trades", "weekly_mean", "tstat", "per_year", "max_dd", "mean_r",
                                                     "long_ret", "short_ret")},
               "per_year_r": {str(y): float(g["ret"].sum()) for y, g in t.groupby(pd.to_datetime(t["exit_time"]).dt.year)},
               "short_share": MR.short_share(t), "hold": MX.hold_stats(t)}
        row["selectable"] = MR.selectable(row, MIN_TRADES)
        table.append(row)
        print(f"TRAIN-WF {form}: {acc['trades']} trades, weekly {acc['weekly_mean']:+.5f}, t {acc['tstat']:+.2f}, "
              f"years {row['per_year_r']}, selectable {row['selectable']}", flush=True)
    ok = [x for x in table if x["selectable"]]
    best = max(ok, key=lambda x: x["tstat"]) if ok else max(table, key=lambda x: x["tstat"])
    form = best["form"]
    t_none = next(x["tstat"] for x in table if x["form"] == "none")
    t_sign = next(x["tstat"] for x in table if x["form"] == "sign")
    tj, _ = judge(P, pred, dirp, form, a_tr, b_tr, traded, min_coins)
    train_checks = {k: tj[k] for k in ("trades", "weekly_mean", "ci_lo", "ci_hi", "tstat", "stress_weekly_mean",
                                       "timing", "shift_median", "shift_p95", "long_ret", "short_ret", "max_dd",
                                       "mean_r", "per_year_r", "top5_weeks_share", "hold")}
    train_checks["breadth"] = {k: tj["breadth"][k] for k in ("eligible", "share")}
    v, t = judge(P, pred, dirp, form, a_va, b_va, traded, min_coins)
    if form != "none":
        nv, nt = judge(P, pred, dirp, "none", a_va, b_va, traded, min_coins)
        v["none_same_arm"] = {k: nv[k] for k in ("trades", "weekly_mean", "ci_lo", "ci_hi", "tstat", "mean_r",
                                                 "long_ret", "short_ret", "max_dd", "short_share")}
        v["kept_share"] = {s: float(((t["side"] > 0) if s == "long" else (t["side"] < 0)).sum()
                                    / max(1, ((nt["side"] > 0) if s == "long" else (nt["side"] < 0)).sum()))
                           for s in ("long", "short")}
    v["dir_by_year"] = dir_by_year(P, dirp, a_va, b_va)
    gates = {"train_cell_selectable": bool(ok),
             "train_chose_agree": form == "sign",
             f"train_margin>={MIN_MARGIN}": t_sign - t_none >= MIN_MARGIN,
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
    res = {"chosen": {"form": form, "arm": "_".join(map(str, ARM)), "dir": DIR_SCHEME, "tf": TF,
                      "sizing": ML.SIZING, "cap": ML.CAP},
           "train_table": table, "train_margin": t_sign - t_none, "train_checks": train_checks, "valid": v,
           "verdict": "REJECT" if failed else "PASS", "gates_failed": failed,
           "model": {"tf": TF, "range_label": f"next {MV.H_VOL} bars' range / ATR",
                     "direction": f"section 38 4h {DIR_SCHEME}, horizons {MR.horizons(TF)}", "coins": list(ML.COINS),
                     "arm": list(ARM), "forms": list(FORMS), "min_margin": MIN_MARGIN}}
    if keep:
        res["_trades"] = t
        res["_train_trades"] = train_trades
    return res


# --------------------------------------------------------------------------
def _record(res, P, pred, dirp, keep, traded, started, inputs) -> None:
    feats = MH._cols(P)
    form = res["chosen"]["form"]
    lab = {c: MV.vol_label(P[c]["bars"]) for c in P}
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
        _, _, sk = run_cell(P, pred, dirp, form, a, b, traded, keep_skipped=True)
        logs = [r for r in keep["log"] if lo <= pd.Timestamp(r["month"], tz="UTC") < hi]
        ylab = pd.concat([pd.Series(lab[c][(P[c]["X"].index >= lo) & (P[c]["X"].index < hi)]) for c in P],
                         ignore_index=True)
        meta = RR.metadata(feats, list(P), logs, dict(ME.LGB_PARAMS, **MP._cfg(TF)["setting"]),
                           f"(max high - min low) of the next {MV.H_VOL} 4h bars / ATR at the decision bar",
                           (MV.H_VOL,), {"split": [a, b], "cell": form, "direction": DIR_SCHEME}, ylab)
        wk = MP.weekly(res["_trades"], a, b) if split == "valid" else None
        RR.write(OUT / "record" / split, feature_importance=imp, training_metadata=meta, predictions=preds,
                 skipped_signals=sk, run_info=RR.run_info(started, inputs),
                 holdout_power=RR.holdout_power(wk) if wk is not None else None)
        dp = RR.predictions({c: P[c]["X"].index for c in P},
                            {c: dirp[c].reindex(P[c]["X"].index).to_numpy() for c in P},
                            {c: MW.label_h(P[c]["bars"], MR.horizons(TF)[1]) for c in P}, a, b)
        dp.to_parquet(OUT / "record" / split / "direction_predictions.parquet", index=False)


def _check_dir(PT, dirp) -> bool | None:
    """The recomputed direction forecasts equal section 38 4h's recorded TRAIN forecasts."""
    f = MR.OUT / "4h" / "record" / "train" / "predictions.parquet"
    if not f.exists():
        return None
    ref = pd.read_parquet(f)
    got = pd.concat([pd.DataFrame({"time": dirp[c].index, "coin": c, "mine": dirp[c].to_numpy()}) for c in PT])
    m = ref.merge(got, on=["time", "coin"], how="inner")
    ok = np.isfinite(m["forecast"]) & np.isfinite(m["mine"])
    return bool(len(m) and ok.any() and np.allclose(m.loc[ok, "forecast"], m.loc[ok, "mine"], atol=1e-5))


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
                raise SystemExit(f"--final refused: sections 31-43 share one holdout and {o.name} used it")
    elif res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    if not (MW.OUT / "members.json").exists():
        raise SystemExit("no section 36 member sets: run  python src/ml_wide.py --build  first")
    months, traded, by_tf, core, members = MR._load()
    inputs = [WF.cache_dir(TF) / f"{c}.parquet" for c in sorted(by_tf[TF])]
    spans = [WF.WINDOWS["train"], WF.WINDOWS["valid"]] + ([WF.WINDOWS["holdout"]] if final else [])
    print(f"[ml_agree] training coins {len(by_tf[TF])}; traded {len(ML.COINS)}", flush=True)
    P = W2.prepare(by_tf, TF)
    del by_tf
    gc.collect()
    masks = {c: MW.training_mask(P[c]["X"].index, c, core, members, True) for c in P}
    keep = {}
    setting = MP._cfg(TF)["setting"]
    pred_all = MV.forecasts(P, setting, masks, spans, keep=keep)
    print("[ml_agree] range forecasts done; direction forecasts (section 38 4h hl12) next", flush=True)
    per_h = MR.forecasts_w(P, TF, setting, masks, spans, DIR_SCHEME)
    PT = {c: P[c] for c in ML.COINS if c in P}
    dirp = ML.combine_set(PT, per_h, MR.horizons(TF))
    del per_h
    gc.collect()
    pred = {c: pred_all[c] for c in PT}
    if final:
        a, b = WF.WINDOWS["holdout"]
        h, t = judge(PT, pred, dirp, res["chosen"]["form"], a, b, traded)
        h["verdict"] = ("CONFIRMED" if h["weekly_mean"] > 0 and h["ci_lo"] > 0 and h["shift_median"] is not None
                        and h["timing"] is not None and h["timing"] > h["shift_median"]
                        and h["breadth"]["share"] >= MP.BREADTH_SHARE else "FAILED")
        lock.write_text(json.dumps(h, indent=1, default=str))
        t.to_csv(OUT / "trades_holdout.csv.gz", index=False)
        write_report(res)
        print(json.dumps({k: h.get(k) for k in ("trades", "weekly_mean", "ci_lo", "verdict")}, indent=1))
        return
    res = evaluate(PT, pred, dirp, traded, keep=True)
    res["traded_from"] = {c: next((m for m in months if c in traded[m]), None) for c in ML.COINS}
    res["reproduces_s38_dir"] = _check_dir(PT, dirp)
    s41 = MS.OUT / "summary.json"
    if s41.exists():
        ref = {x["form"]: (x["trades"], round(x["tstat"], 6)) for x in json.loads(s41.read_text())["train_table"]}
        nrow = next(x for x in res["train_table"] if x["form"] == "none")
        res["reproduces_s41"] = ref.get(MS.cell_name(ARM)) == (nrow["trades"], round(nrow["tstat"], 6))
    print(f"reproduces section 41: {res.get('reproduces_s41')}; section 38 direction: {res['reproduces_s38_dir']}",
          flush=True)
    _record(res, PT, pred, dirp, keep, traded, started, inputs)
    res.pop("_trades").to_csv(OUT / "trades_valid.csv.gz", index=False)
    for form, tt in res.pop("_train_trades").items():
        tt.to_csv(OUT / f"trades_train_{form}.csv.gz", index=False)
    res_path.write_text(json.dumps(res, indent=1, default=str))
    write_report(res)
    print(f"\nML_AGREE: chose {res['chosen']['form']} -> {res['verdict']} failed {res['gates_failed']}")


def write_report(r: dict) -> None:
    v = r["valid"]
    f = (lambda x, k=5: "-" if x is None else f"{x:+.{k}f}")
    o = v.get("none_same_arm", {})
    L = ["# Range model says when, direction model must agree on the side (PLAN.md section 43)", "",
         "GENERATED by `src/ml_agree.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}** (TRAIN chose {r['chosen']['form']}; failed: {r['gates_failed'] or 'none'})", "",
         f"- reproduces section 41: {r.get('reproduces_s41')}; section 38 direction forecasts: "
         f"{r.get('reproduces_s38_dir')}; TRAIN t margin sign - none: {f(r.get('train_margin'), 2)}",
         f"- VALID {v['trades']} trades: weekly {f(v['weekly_mean'])}, 95% CI [{f(v['ci_lo'])}, {f(v['ci_hi'])}], "
         f"t {v['tstat']:+.2f}; mean R {f(v['mean_r'], 4)}; long {f(v['long_ret'], 4)} / short {f(v['short_ret'], 4)}; "
         f"max DD {v['max_dd']:.4f}",
         f"- cost x1.5 {f(v['stress_weekly_mean'])}; timing {f(v['timing'], 4)} vs shifted p95 {f(v['shift_p95'], 4)}; "
         f"breadth {len(v['breadth']['beat'])} of {v['breadth']['eligible']}; short share {v['short_share']}",
         f"- section 41 (none) on VALID: {o.get('trades')} trades, weekly {f(o.get('weekly_mean'))}, "
         f"CI [{f(o.get('ci_lo'))}, {f(o.get('ci_hi'))}], mean R {f(o.get('mean_r'), 4)}; kept share {v.get('kept_share')}",
         f"- direction forecast on VALID by year: {v.get('dir_by_year')}",
         f"- best 5 weeks = {f(v['top5_weeks_share'], 3)} of the total; weekly mean without them "
         f"{f(v['weekly_mean_without_top5'])}", "",
         "| form | TRAIN trades | weekly mean | t | mean R | long | short | by year | short share | selectable |",
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
