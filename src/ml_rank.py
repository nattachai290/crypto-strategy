"""Decide the side from where the forecast stands against its own recent history (PLAN.md section 39)

    python src/ml_rank.py            # TRAIN/VALID, once (uses section 36's caches; no new download)
    python src/ml_rank.py --final    # HOLDOUT once, only after PASS (shared with sections 31-38)

Diagnosis (_multi Exp 062, from section 38's per-bar forecasts): the 4h model
RANKS bars correctly in all four years - its top forecast quintile beats its
bottom quintile by +0.15 / +0.19 R (TRAIN 2021 / 2022) and +0.40 / +0.26
(VALID) - but the LEVEL of its forecasts drifts with the last regime: in
2023-24 the mean forecast was negative (-0.14 / -0.13) while prices rose. The
policy reads the forecast's sign, so a level shift picks the side.

Hypothesis: measuring the forecast against its own recent median (causal,
per coin) removes the level drift and keeps the ranking, so the side follows
what the model ranks, not the regime it was trained in.

Frozen from section 38's 4h sub-model as TRAIN chose it: the ten coins (from
365 days after listing), 4h decisions with 1h/1d features, horizons 6/12/18
bars averaged, wide training rows weighted with a 12-month half-life (hl12),
section 30's 4h setting, entry quantile and exit mode, 8-ATR stop, no clock,
agreement off, confidence sizing, 5% cap. The forecasts are therefore section
38's 4h forecasts (checked: the "raw" TRAIN row must reproduce 394 trades,
t +2.70).

TRAIN (walk-forward 2021-22) compares three forms of the forecast fed to the
unchanged policy (rolling entry threshold on |x|, side = sign of x):
  "raw"    x = forecast                                 (= section 38 4h; baseline)
  "med30"  x = forecast - its rolling median over the past 30 days of bars (180)
  "med90"  x = forecast - its rolling median over the past 90 days of bars (540)
(per coin, past and current bars only; NaN until a third of the window exists).
Selection: section 38's rule - selectable only with >= MIN_TRADES TRAIN trades,
both TRAIN years and both legs positive; the weekly t-statistic picks. No
selectable form, or a "raw" choice, is REJECT (train_cell_selectable,
train_chose_centered). VALID gates: section 37's. Reported, not gated: the short
share of entries by year and the mean centred forecast by year.
The run-time record (src/run_record.py) is written for TRAIN and VALID.
Holdout: sections 31-39 share ONE holdout.
Writes results/_multi/s39_ml_rank_4h/ and journal/_multi/s39_ml_rank_4h.md.
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
import ml_large as ML  # noqa: E402
import ml_port as MP  # noqa: E402
import ml_recent as MR  # noqa: E402
import ml_wf as WF  # noqa: E402
import ml_wf2 as W2  # noqa: E402
import ml_wide as MW  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "s39_ml_rank_4h"
REPORT = C.ROOT / "journal" / "_multi" / "s39_ml_rank_4h.md"

# ---- pre-registered (PLAN.md section 39, _multi Exp 063)
TF = 240
SCHEME = "hl12"                                         # section 38 4h's TRAIN choice, frozen
FORMS = {"raw": None, "med30": 30, "med90": 90}         # rolling-median window in days
MIN_TRADES = ML.MIN_TRADES
LOCKS = MR.LOCKS + tuple(MR.OUT / n for n in MR.TF_NAME.values())   # sections 31-38: one shared holdout


# --------------------------------------------------------------------------
# pure pieces (test 37)
# --------------------------------------------------------------------------
def center(pred: pd.Series, days: int | None, tf: int = TF) -> pd.Series:
    """forecast minus its rolling median over the past `days` (bars of tf), causal,
    over the coin's own finite forecasts; NaN until a third of the window exists."""
    if days is None:
        return pred
    n = days * 1440 // tf
    s = pred.dropna()
    med = s.rolling(n, min_periods=max(1, n // 3)).median()
    return (pred - med.reindex(pred.index)).where(med.reindex(pred.index).notna())


def forms(preds: dict, tf: int = TF) -> dict:
    """{form: {coin: Series}} from the raw forecasts."""
    return {f: {c: center(p, d, tf) for c, p in preds.items()} for f, d in FORMS.items()}


def by_year_mean(pred: dict, a: str, b: str) -> dict:
    s = pd.concat([p[(p.index >= pd.Timestamp(a, tz="UTC")) & (p.index < pd.Timestamp(b, tz="UTC"))]
                   for p in pred.values()]).dropna()
    return {str(y): float(g.mean()) for y, g in s.groupby(s.index.year)}


def evaluate(P, preds: dict, traded, q, mode, tf=TF, min_coins=ML.MIN_COINS, keep=False) -> dict:
    """preds: {form: {coin: Series}} on the traded coins."""
    a_tr, b_tr = WF.WINDOWS["train"]
    a_va, b_va = WF.WINDOWS["valid"]
    table, train_trades = [], {}
    for f in FORMS:
        if f not in preds:
            continue
        t, _ = ML.run_cell(P, preds[f], None, "off", a_tr, b_tr, traded, q, mode, tf)
        train_trades[f] = t
        acc = MP.account(t, a_tr, b_tr)
        row = {"form": f, **{k: acc[k] for k in ("trades", "weekly_mean", "tstat", "per_year", "max_dd", "mean_r",
                                                  "long_ret", "short_ret")},
               "per_year_r": {str(y): float(g["ret"].sum()) for y, g in t.groupby(pd.to_datetime(t["exit_time"]).dt.year)},
               "short_share": MR.short_share(t), "mean_x_by_year": by_year_mean(preds[f], a_tr, b_tr)}
        row["selectable"] = MR.selectable(row, MIN_TRADES)
        table.append(row)
        print(f"TRAIN-WF {f}: {acc['trades']} trades, weekly {acc['weekly_mean']:+.5f}, t {acc['tstat']:+.2f}, "
              f"years {row['per_year_r']}, selectable {row['selectable']}", flush=True)
    ok = [x for x in table if x["selectable"]]
    best = max(ok, key=lambda x: x["tstat"]) if ok else max(table, key=lambda x: x["tstat"])
    f = best["form"]
    tj, _ = ML.judge(P, preds[f], None, "off", a_tr, b_tr, traded, q, mode, tf, min_coins=min_coins)
    train_checks = {k: tj[k] for k in ("trades", "weekly_mean", "ci_lo", "ci_hi", "tstat", "stress_weekly_mean",
                                       "timing", "shift_median", "shift_p95", "long_ret", "short_ret", "max_dd",
                                       "mean_r", "per_year_r", "top5_weeks_share")}
    train_checks["breadth"] = {k: tj["breadth"][k] for k in ("eligible", "share")}
    v, t = ML.judge(P, preds[f], None, "off", a_va, b_va, traded, q, mode, tf, min_coins=min_coins)
    v["short_share"] = MR.short_share(t)
    v["mean_x_by_year"] = by_year_mean(preds[f], a_va, b_va)
    gates = {"train_cell_selectable": bool(ok),
             "train_chose_centered": f != "raw",
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
    res = {"chosen": {"form": f, "tf": tf, "weighting": SCHEME, "horizons": "1-3d", "agree": "off",
                      "sizing": ML.SIZING, "cap": ML.CAP},
           "train_table": table, "train_checks": train_checks, "valid": v,
           "verdict": "REJECT" if failed else "PASS", "gates_failed": failed,
           "model": {"q_in": q, "exit_mode": mode, "tf": tf, "horizons": list(MR.horizons(tf)),
                     "coins": list(ML.COINS), "forms": FORMS, "weighting": SCHEME}}
    if keep:
        res["_trades"] = t
        res["_train_trades"] = train_trades
    return res


# --------------------------------------------------------------------------
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
                raise SystemExit(f"--final refused: sections 31-39 share one holdout and {o.name} used it")
    elif res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    if not (MW.OUT / "members.json").exists():
        raise SystemExit("no section 36 member sets: run  python src/ml_wide.py --build  first")
    months, traded, by_tf, core, members = MR._load()
    inputs = [WF.cache_dir(TF) / f"{c}.parquet" for c in sorted(by_tf[TF])]
    spans = [WF.WINDOWS["train"], WF.WINDOWS["valid"]] + ([WF.WINDOWS["holdout"]] if final else [])
    print(f"[ml_rank] training coins {len(by_tf[TF])}; traded {len(ML.COINS)}", flush=True)
    P = W2.prepare(by_tf, TF)
    del by_tf
    gc.collect()
    masks = {c: MW.training_mask(P[c]["X"].index, c, core, members, True) for c in P}
    cfg = MP._cfg(TF)
    q, mode = cfg["q_in"], cfg["exit_mode"]
    keep = {}
    per_h = MR.forecasts_w(P, TF, cfg["setting"], masks, spans, SCHEME, keep=keep)
    PT = {c: P[c] for c in ML.COINS if c in P}
    raw = ML.combine_set(PT, per_h, MR.horizons(TF))
    del per_h
    gc.collect()
    fm = forms(raw)
    if final:
        a, b = WF.WINDOWS["holdout"]
        h, t = ML.judge(PT, fm[res["chosen"]["form"]], None, "off", a, b, traded, q, mode, TF)
        h["verdict"] = ("CONFIRMED" if h["weekly_mean"] > 0 and h["ci_lo"] > 0 and h["shift_median"] is not None
                        and h["timing"] is not None and h["timing"] > h["shift_median"]
                        and h["breadth"]["share"] >= MP.BREADTH_SHARE else "FAILED")
        lock.write_text(json.dumps(h, indent=1, default=str))
        t.to_csv(OUT / "trades_holdout.csv.gz", index=False)
        write_report(res)
        print(json.dumps({k: h.get(k) for k in ("trades", "weekly_mean", "ci_lo", "verdict")}, indent=1))
        return
    res = evaluate(PT, fm, traded, q, mode, keep=True)
    res["traded_from"] = {c: next((m for m in months if c in traded[m]), None) for c in ML.COINS}
    MR._record(res, PT, fm[res["chosen"]["form"]], keep, traded, started, inputs, TF, OUT)
    res.pop("_trades").to_csv(OUT / "trades_valid.csv.gz", index=False)
    for form, tt in res.pop("_train_trades").items():
        tt.to_csv(OUT / f"trades_train_{form}.csv.gz", index=False)
    res_path.write_text(json.dumps(res, indent=1, default=str))
    write_report(res)
    print(f"\nML_RANK: chose {res['chosen']['form']} -> {res['verdict']} failed {res['gates_failed']}")


def write_report(r: dict) -> None:
    v = r["valid"]
    f = (lambda x, k=5: "-" if x is None else f"{x:+.{k}f}")
    L = ["# Side from the forecast against its own recent median, 4h, ten large coins (PLAN.md section 39)", "",
         "GENERATED by `src/ml_rank.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}** (TRAIN chose {r['chosen']['form']}; failed: {r['gates_failed'] or 'none'})", "",
         f"- VALID {v['trades']} trades over {v['weeks']} weeks: weekly {f(v['weekly_mean'])}, 95% CI "
         f"[{f(v['ci_lo'])}, {f(v['ci_hi'])}], t {v['tstat']:+.2f}; max DD {v['max_dd']:.4f}",
         f"- mean R {f(v['mean_r'], 4)}; long {f(v['long_ret'], 4)} / short {f(v['short_ret'], 4)}; cost x1.5 "
         f"{f(v['stress_weekly_mean'])}; timing {f(v['timing'], 4)} vs shifted p95 {f(v['shift_p95'], 4)}; breadth "
         f"{len(v['breadth']['beat'])} of {v['breadth']['eligible']}",
         f"- short share by year: {v['short_share']} (section 38 4h: 2023 0.55, 2024 0.64); mean x by year "
         f"{v['mean_x_by_year']}",
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
