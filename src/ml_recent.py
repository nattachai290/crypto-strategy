"""Recency-weighted training for the ten large coins (PLAN.md section 38)

    python src/ml_recent.py              # TRAIN/VALID of the 1h, 4h and 1d sub-models, each once
    python src/ml_recent.py --tf 240     # one sub-model only (resumable: finished ones are skipped)
    python src/ml_recent.py --final      # HOLDOUT once for ONE sub-model, only after PASS (shared with 31-37)

Diagnosis (_multi Exp 059): every ML book of sections 28-37 leaned SHORT in
2023-24 (57-78% of entries) in a two-year bull market, after 2022's bear year
entered the training set, and stayed short through 2024 although 2023's rally
was already being trained on. The expanding window (every row since 2017,
equally weighted) lets the last bear regime dominate for years. And TRAIN
(2021 bull + 2022 bear) picked whichever cell shorted 2022 hardest.

Hypothesis: weighting training rows by recency lets the model's side follow
the current regime within months, and a TRAIN selection rule that needs BOTH
years and BOTH legs positive stops one year from choosing the cell.

Three sub-models (owner, 2026-10-08), one per decision timeframe - 1h, 4h,
1d - each with the other two timeframes' closed-bar features as inputs and the
same 1-3 day horizons (1h: 24/48/72 bars, 4h: 6/12/18, 1d: 1/2/3, averaged).
Everything else is section 37's chosen cell, frozen: the ten coins (from 365
days after listing), wide training rows (section 30's 47 coins + section
36's monthly top-50 members), section 30's LightGBM setting, entry quantile
and exit mode for that timeframe, 8-ATR stop, no clock, agreement off, confidence sizing, 5% cap.

TRAIN (walk-forward 2021-22) compares three weightings of the training rows:
  "expanding"  every row weight 1 (the baseline; on 4h it IS section 37's chosen cell)
  "hl12"       weight 0.5 ** (age in months / 12)
  "roll24"     weight 1 for rows up to 24 months old, else 0
A cell is SELECTABLE only if on TRAIN it has >= MIN_TRADES trades, both years
(2021, 2022) have a positive summed return and both legs are positive; the
weekly t-statistic picks among the selectable. No selectable cell, or a choice
of "expanding", is REJECT (gates train_cell_selectable, train_chose_recency).
VALID gates: section 37's, per sub-model; each sub-model has its own verdict.
Holdout: at most ONE sub-model may take it - among the PASS sub-models, the one
whose chosen TRAIN weighting has the highest weekly t-statistic. Reported, not gated: the short share of entries by
year (the hypothesis says it falls in 2023-24 against section 37's 0.69/0.76).
The run-time record (src/run_record.py) is written for TRAIN and VALID.
Holdout: sections 31-38 share ONE holdout.
Writes results/_multi/s38_ml_recent/{1h,4h,1d}/ and journal/_multi/s38_ml_recent.md.
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
import ml_hold as MH  # noqa: E402
import ml_large as ML  # noqa: E402
import ml_port as MP  # noqa: E402
import ml_wf as WF  # noqa: E402
import ml_wf2 as W2  # noqa: E402
import ml_wide as MW  # noqa: E402
import run_record as RR  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "s38_ml_recent"
REPORT = C.ROOT / "journal" / "_multi" / "s38_ml_recent.md"

# ---- pre-registered (PLAN.md section 38, _multi Exp 060)
TFS = (60, 240, 1440)
TF_NAME = {60: "1h", 240: "4h", 1440: "1d"}
HORIZON_DAYS = (1, 2, 3)
WEIGHTINGS = ("expanding", "hl12", "roll24")
HALF_LIFE_M, ROLL_M = 12, 24
MIN_TRADES = ML.MIN_TRADES
LOCKS = ML.LOCKS + (ML.OUT,)                            # sections 31-37: one shared holdout


# --------------------------------------------------------------------------
# pure pieces (test 36)
# --------------------------------------------------------------------------
def horizons(tf: int) -> tuple[int, ...]:
    """The 1-3 day horizons in bars of tf."""
    return tuple(d * 1440 // tf for d in HORIZON_DAYS)


def holdout_pick(results: dict) -> int | None:
    """Among PASS sub-models {tf: summary}, the one whose chosen TRAIN cell has the
    highest weekly t-statistic; None if no sub-model is PASS."""
    ok = {tf: r for tf, r in results.items() if r.get("verdict") == "PASS"}
    if not ok:
        return None
    t = {tf: next(x["tstat"] for x in r["train_table"] if x["form"] == r["chosen"]["form"]) for tf, r in ok.items()}
    return max(t, key=t.get)


def row_weights(times: pd.DatetimeIndex, m0: pd.Timestamp, scheme: str) -> np.ndarray:
    """Training weight of rows at `times` for the model refit at month start m0."""
    age = (m0 - times) / pd.Timedelta(days=30.4375)       # months
    if scheme == "expanding":
        return np.ones(len(times))
    if scheme == "hl12":
        return np.power(0.5, np.asarray(age, float) / HALF_LIFE_M)
    if scheme == "roll24":
        return (np.asarray(age, float) <= ROLL_M).astype(float)
    raise ValueError(scheme)


def fit_w(X: pd.DataFrame, y: pd.Series, w: np.ndarray, cfg: dict):
    """ml_pool2.fit with row weights (same parameters, same seed)."""
    import lightgbm as lgb
    params = dict(ME.LGB_PARAMS, num_leaves=cfg["num_leaves"], min_data_in_leaf=cfg["min_data_in_leaf"])
    ok = (y.notna() & (w > 0)).to_numpy() if isinstance(y, pd.Series) else (np.isfinite(y) & (w > 0))
    return lgb.train(params, lgb.Dataset(X[ok], y[ok], weight=w[ok]), num_boost_round=cfg["rounds"])


def walk_forward_w(P: dict, tf: int, cfg: dict, a: str, b: str, scheme: str, step: int = 1,
                   log: list | None = None, models: dict | None = None) -> dict:
    """ml_wf.walk_forward with recency weights: for each month m, a model fitted on
    every row whose label is complete before m, weighted by row_weights(.., m)."""
    cols = MH._cols(P)
    pred = {c: np.full(len(P[c]["X"]), np.nan) for c in P}
    lag = pd.Timedelta(minutes=tf * (WF.H_BARS + 1))
    starts = WF.month_starts(a, b, step) + [pd.Timestamp(b, tz="UTC")]
    for m0, m1 in zip(starts[:-1], starts[1:]):
        Xs, ys, ws = [], [], []
        for c in P:
            idx = P[c]["X"].index
            tr = idx + lag < m0
            Xs.append(P[c]["X"].reindex(columns=cols)[tr])
            ys.append(P[c]["y"][tr])
            ws.append(row_weights(idx[tr], m0, scheme))
        X, y, w = pd.concat(Xs, ignore_index=True), pd.concat(ys, ignore_index=True), np.concatenate(ws)
        if (y.notna() & (w > 0)).sum() < 1000:
            continue
        model = fit_w(X, y, w, cfg)
        if models is not None:
            models[m0] = model
        if log is not None:
            ok = y.notna().to_numpy() & (w > 0)
            log.append({"month": str(m0.date()), "train_rows": int(ok.sum()),
                        "effective_rows": float(w[ok].sum() ** 2 / (w[ok] ** 2).sum()), "scheme": scheme})
        for c in P:
            idx = P[c]["X"].index
            ww = (idx >= m0) & (idx < m1) & P[c].get("tradable", np.ones(len(idx), bool))
            if ww.any():
                pred[c][ww] = model.predict(P[c]["X"].reindex(columns=cols)[ww])
    return pred


def selectable(row: dict, min_trades: int = MIN_TRADES) -> bool:
    """TRAIN rule: enough trades, both TRAIN years and both legs positive."""
    yr = row.get("per_year_r") or {}
    return (row["trades"] >= min_trades and len(yr) >= 2 and all(v > 0 for v in yr.values())
            and row["long_ret"] > 0 and row["short_ret"] > 0)


def short_share(t: pd.DataFrame) -> dict:
    if t.empty:
        return {}
    y = pd.to_datetime(t["entry_time"], utc=True).dt.year
    return {str(k): float((g["side"] < 0).mean()) for k, g in t.groupby(y)}


# --------------------------------------------------------------------------
def forecasts_w(P: dict, tf: int, cfg: dict, masks: dict, spans, scheme: str, step: int = 1,
                keep: dict | None = None) -> dict:
    """Horizon-averaged forecasts (section 36's ensemble) with one weighting scheme;
    keep: {h: (log, models)} receives the record of every horizon's refits."""
    per_h = {}
    saved = WF.H_BARS
    try:
        for h in horizons(tf):
            Ph = {c: {**P[c], "y": pd.Series(np.where(masks[c], MW.label_h(P[c]["bars"], h), np.nan),
                                             index=P[c]["X"].index)} for c in P}
            WF.H_BARS = h
            pred = {c: np.full(len(P[c]["X"]), np.nan) for c in P}
            for a, b in spans:
                log, models = ([], {}) if keep is not None else (None, None)
                p = walk_forward_w(Ph, tf, cfg, a, b, scheme, step=step, log=log, models=models)
                if keep is not None:
                    keep.setdefault(h, ([], {}))
                    keep[h][0].extend(log)
                    keep[h][1].update(models)
                for c in P:
                    pred[c] = np.where(np.isfinite(p[c]), p[c], pred[c])
            per_h[h] = pred
            del Ph
            gc.collect()
    finally:
        WF.H_BARS = saved
    return per_h


def evaluate(P, preds: dict, traded, q, mode, tf, min_coins=ML.MIN_COINS, keep=False) -> dict:
    """preds: {scheme: {coin: Series}} on the traded coins."""
    a_tr, b_tr = WF.WINDOWS["train"]
    a_va, b_va = WF.WINDOWS["valid"]
    table, train_trades = [], {}
    for s in WEIGHTINGS:
        if s not in preds:
            continue
        t, _ = ML.run_cell(P, preds[s], None, "off", a_tr, b_tr, traded, q, mode, tf)
        train_trades[s] = t
        acc = MP.account(t, a_tr, b_tr)
        row = {"form": s, **{k: acc[k] for k in ("trades", "weekly_mean", "tstat", "per_year", "max_dd", "mean_r",
                                                  "long_ret", "short_ret")},
               "per_year_r": {str(y): float(g["ret"].sum()) for y, g in t.groupby(pd.to_datetime(t["exit_time"]).dt.year)},
               "short_share": short_share(t)}
        row["selectable"] = selectable(row)
        table.append(row)
        print(f"TRAIN-WF {s}: {acc['trades']} trades, weekly {acc['weekly_mean']:+.5f}, t {acc['tstat']:+.2f}, "
              f"years {row['per_year_r']}, selectable {row['selectable']}", flush=True)
    ok = [x for x in table if x["selectable"]]
    best = max(ok, key=lambda x: x["tstat"]) if ok else max(table, key=lambda x: x["tstat"])
    tj, _ = ML.judge(P, preds[best["form"]], None, "off", a_tr, b_tr, traded, q, mode, tf, min_coins=min_coins)
    train_checks = {k: tj[k] for k in ("trades", "weekly_mean", "ci_lo", "ci_hi", "tstat", "stress_weekly_mean",
                                       "timing", "shift_median", "shift_p95", "long_ret", "short_ret", "max_dd",
                                       "mean_r", "per_year_r", "top5_weeks_share")}
    train_checks["breadth"] = {k: tj["breadth"][k] for k in ("eligible", "share")}
    v, t = ML.judge(P, preds[best["form"]], None, "off", a_va, b_va, traded, q, mode, tf, min_coins=min_coins)
    v["short_share"] = short_share(t)
    gates = {"train_cell_selectable": bool(ok),
             "train_chose_recency": best["form"] != "expanding",
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
    res = {"chosen": {"form": best["form"], "tf": tf, "horizons": "1-3d", "agree": "off", "sizing": ML.SIZING,
                      "cap": ML.CAP},
           "train_table": table, "train_checks": train_checks, "valid": v,
           "verdict": "REJECT" if failed else "PASS", "gates_failed": failed,
           "model": {"q_in": q, "exit_mode": mode, "tf": tf, "horizons": list(horizons(tf)), "coins": list(ML.COINS),
                     "half_life_months": HALF_LIFE_M, "roll_months": ROLL_M}}
    if keep:
        res["_trades"] = t
        res["_train_trades"] = train_trades
    return res


# --------------------------------------------------------------------------
def _record(res: dict, P: dict, pred: dict, keep: dict, traded, started: float, inputs, tf: int, out: Path) -> None:
    """run_record files for the chosen weighting of one sub-model, TRAIN and VALID."""
    feats = MH._cols(P)
    hs = horizons(tf)
    mid = hs[len(hs) // 2]
    models = {(h, m): mdl for h, (_, ms) in keep.items() for m, mdl in ms.items()}
    lab = {c: MW.label_h(P[c]["bars"], mid) for c in P}
    for split in ("train", "valid"):
        a, b = WF.WINDOWS[split]
        lo, hi = pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")
        ms = {m: mdl for (h, m), mdl in models.items() if lo <= m < hi and h == mid}
        Xm = {}
        for m in ms:
            m1 = m + pd.offsets.MonthBegin(1)
            Xm[m] = pd.concat([P[c]["X"].reindex(columns=feats)[(P[c]["X"].index >= m) & (P[c]["X"].index < m1)]
                               for c in P], ignore_index=True)
        imp = RR.importance(ms)
        imp["shap"] = RR.shap_summary(ms, Xm)
        imp["note"] = f"horizon {mid} bars of {TF_NAME[tf]} (the middle of the averaged set)"
        preds = RR.predictions({c: P[c]["X"].index for c in P},
                               {c: pred[c].reindex(P[c]["X"].index).to_numpy() for c in P}, lab, a, b)
        sk = []
        for c in P:
            p = pred[c].reindex(P[c]["X"].index).to_numpy()
            okp = np.isfinite(p)
            if not okp.any():
                continue
            des = np.full(len(p), np.nan)
            des[okp] = MH.policy(p[okp], MH.entry_bar(p[okp], res["model"]["q_in"]), res["model"]["exit_mode"])
            _, _, rows = MH._window(P, c, a, b)
            rows = rows[np.isfinite(des[rows])]
            if not len(rows):
                continue
            idx = P[c]["X"].index[rows]
            taken = MW.member_filter(des[rows], MW.month_mask(idx, c, traded))
            sk.append(RR.skipped(idx, c, des[rows], taken, "not in traded set", lab[c][rows]))
        logs = [r for h, (lg, _) in keep.items() for r in lg if lo <= pd.Timestamp(r["month"], tz="UTC") < hi]
        ylab = pd.concat([pd.Series(lab[c][(P[c]["X"].index >= lo) & (P[c]["X"].index < hi)]) for c in P],
                         ignore_index=True)
        meta = RR.metadata(feats, list(P), logs, dict(ME.LGB_PARAMS, **MP._cfg(tf)["setting"]),
                           f"log(open[i+1+h]/open[i+1]) / ATR fraction at i, h in bars of {TF_NAME[tf]}", hs,
                           {"split": [a, b], "train_rows_weighting": res["chosen"]["form"]}, ylab)
        wk = MP.weekly(res["_trades"], a, b) if split == "valid" else None
        RR.write(out / "record" / split, feature_importance=imp, training_metadata=meta, predictions=preds,
                 skipped_signals=pd.concat(sk, ignore_index=True) if sk else None,
                 run_info=RR.run_info(started, inputs), holdout_power=RR.holdout_power(wk) if wk is not None else None)


def _load():
    months = [str(p) for p in pd.period_range("2020-01", C.DATA_END, freq="M")]
    traded = ML.traded_sets(ML._first_traded(), months)
    by_tf, core, members, _ = MW.load_wide()
    for tf in TFS:
        miss = [c for c in ML.COINS if c not in by_tf[tf]]
        if miss:
            raise SystemExit(f"no cached {TF_NAME[tf]} bars for {miss}: run  python src/ml_wide.py --build  first")
    return months, traded, by_tf, core, members


def run_tf(tf: int, months, traded, by_tf, core, members, final_res: dict | None = None) -> None:
    """One sub-model: TRAIN/VALID once, or (final_res given) its holdout once."""
    started = time.time()
    out = OUT / TF_NAME[tf]
    out.mkdir(parents=True, exist_ok=True)
    inputs = [WF.cache_dir(tf) / f"{c}.parquet" for c in sorted(by_tf[tf])]
    spans = [WF.WINDOWS["train"], WF.WINDOWS["valid"]] + ([WF.WINDOWS["holdout"]] if final_res else [])
    print(f"[ml_recent {TF_NAME[tf]}] training coins {len(by_tf[tf])}; traded {len(ML.COINS)}; horizons "
          f"{horizons(tf)}", flush=True)
    P = W2.prepare(by_tf, tf)
    masks = {c: MW.training_mask(P[c]["X"].index, c, core, members, True) for c in P}
    cfg = MP._cfg(tf)
    q, mode = cfg["q_in"], cfg["exit_mode"]
    schemes = (final_res["chosen"]["form"],) if final_res else WEIGHTINGS
    preds, keeps = {}, {}
    for s in schemes:
        keeps[s] = {}
        per_h = forecasts_w(P, tf, cfg["setting"], masks, spans, s, keep=keeps[s])
        preds[s] = ML.combine_set({c: P[c] for c in ML.COINS if c in P}, per_h, horizons(tf))
        del per_h
        gc.collect()
        print(f"[ml_recent {TF_NAME[tf]}] forecasts done: {s}", flush=True)
    PT = {c: P[c] for c in ML.COINS if c in P}
    if final_res:
        a, b = WF.WINDOWS["holdout"]
        h, t = ML.judge(PT, preds[schemes[0]], None, "off", a, b, traded, q, mode, tf)
        h["verdict"] = ("CONFIRMED" if h["weekly_mean"] > 0 and h["ci_lo"] > 0 and h["shift_median"] is not None
                        and h["timing"] is not None and h["timing"] > h["shift_median"]
                        and h["breadth"]["share"] >= MP.BREADTH_SHARE else "FAILED")
        h["tf"] = tf
        (out / "holdout.json").write_text(json.dumps(h, indent=1, default=str))
        t.to_csv(out / "trades_holdout.csv.gz", index=False)
        print(json.dumps({k: h.get(k) for k in ("tf", "trades", "weekly_mean", "ci_lo", "verdict")}, indent=1))
        return
    res = evaluate(PT, preds, traded, q, mode, tf, keep=True)
    res["traded_from"] = {c: next((m for m in months if c in traded[m]), None) for c in ML.COINS}
    ch = res["chosen"]["form"]
    _record(res, PT, preds[ch], keeps[ch], traded, started, inputs, tf, out)
    res.pop("_trades").to_csv(out / "trades_valid.csv.gz", index=False)
    for form, tt in res.pop("_train_trades").items():
        tt.to_csv(out / f"trades_train_{form}.csv.gz", index=False)
    (out / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    print(f"\nML_RECENT {TF_NAME[tf]}: chose {res['chosen']['form']} -> {res['verdict']} failed {res['gates_failed']}")


def _locks_used() -> list[str]:
    return [o.name for o in LOCKS if (o / "holdout.json").exists()] + \
        [f"{OUT.name}/{TF_NAME[tf]}" for tf in TFS if (OUT / TF_NAME[tf] / "holdout.json").exists()]


def run(tf: int | None = None, final: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if final:
        res = {t: json.loads((OUT / TF_NAME[t] / "summary.json").read_text()) for t in TFS
               if (OUT / TF_NAME[t] / "summary.json").exists()}
        if len(res) != len(TFS):
            raise SystemExit("--final refused: run the TRAIN/VALID step of all three sub-models first")
        pick = holdout_pick(res)
        if pick is None:
            raise SystemExit("--final refused: no sub-model is PASS")
        if _locks_used():
            raise SystemExit(f"--final refused: sections 31-38 share one holdout, used by {_locks_used()}")
        months, traded, by_tf, core, members = _load()
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
    months, traded, by_tf, core, members = _load()
    for t in todo:
        run_tf(t, months, traded, by_tf, core, members)
        gc.collect()
        write_report()


def write_report() -> None:
    f = (lambda x, k=5: "-" if x is None else f"{x:+.{k}f}")
    L = ["# Recency-weighted training for the ten large coins, 1h / 4h / 1d sub-models (PLAN.md section 38)", "",
         "GENERATED by `src/ml_recent.py`. Do not edit by hand.", ""]
    for tf in TFS:
        sp = OUT / TF_NAME[tf] / "summary.json"
        if not sp.exists():
            L += [f"## {TF_NAME[tf]}: not run yet", ""]
            continue
        r = json.loads(sp.read_text())
        v = r["valid"]
        L += [f"## {TF_NAME[tf]}: **{r['verdict']}** (TRAIN chose {r['chosen']['form']}; failed: "
              f"{r['gates_failed'] or 'none'})", "",
              f"- horizons {r['model']['horizons']} bars; VALID {v['trades']} trades over {v['weeks']} weeks: weekly "
              f"{f(v['weekly_mean'])}, 95% CI [{f(v['ci_lo'])}, {f(v['ci_hi'])}], t {v['tstat']:+.2f}; max DD "
              f"{v['max_dd']:.4f}",
              f"- mean R {f(v['mean_r'], 4)}; long {f(v['long_ret'], 4)} / short {f(v['short_ret'], 4)}; cost x1.5 "
              f"{f(v['stress_weekly_mean'])}; timing {f(v['timing'], 4)} vs shifted p95 {f(v['shift_p95'], 4)}; "
              f"breadth {len(v['breadth']['beat'])} of {v['breadth']['eligible']}",
              f"- short share of entries by year: {v['short_share']} (section 37, 4h: 2023 0.69, 2024 0.76)",
              f"- best 5 weeks = {f(v['top5_weeks_share'], 3)} of the total; weekly mean without them "
              f"{f(v['weekly_mean_without_top5'])}", "",
              "| weighting | TRAIN trades | weekly mean | t | mean R | long | short | by year | short share | selectable |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for x in r["train_table"]:
            L.append(f"| {x['form']} | {x['trades']} | {f(x['weekly_mean'])} | {x['tstat']:+.2f} | "
                     f"{f(x['mean_r'], 4)} | {f(x['long_ret'], 4)} | {f(x['short_ret'], 4)} | {x['per_year_r']} | "
                     f"{x['short_share']} | {x['selectable']} |")
        hp = OUT / TF_NAME[tf] / "holdout.json"
        if hp.exists():
            h = json.loads(hp.read_text())
            L += ["", f"**HOLDOUT ({TF_NAME[tf]}): {h['verdict']}** - {h['trades']} trades, weekly "
                      f"{f(h['weekly_mean'])}, CI lo {f(h['ci_lo'])}"]
        L.append("")
    REPORT.write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tf", type=int, choices=TFS, help="run one sub-model only")
    ap.add_argument("--final", action="store_true", help="run the holdout once for the one picked sub-model")
    a = ap.parse_args()
    run(a.tf, a.final)


if __name__ == "__main__":
    main()
