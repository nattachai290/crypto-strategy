"""Section 43's book on more coins (PLAN.md section 48)

    python src/ml_agree_wide.py            # TRAIN/VALID, once (uses section 36's caches; no new download)
    python src/ml_agree_wide.py --final    # HOLDOUT once, only after PASS (shared with sections 31-47's ML line)

Why (_multi Exp 095, a TRAIN-only diagnosis of section 43): no entry filter,
exit or sizing change raises section 43's t; a tighter stop scales return, not
evidence. Across the project the one lever that shrank the CI by sample size
was trading more coins (section 31 on 46 coins is the closest record, CI lo
-0.00026). Section 43 is the best ten-coin book (VALID CI lo -0.00039, t +1.40)
on only ten coins.

Hypothesis: section 43's mechanism - a breakout armed by the ML range forecast
per side (section 41) and kept only where section 38 4h's direction forecast
agrees - is not specific to the ten coins. Traded on every month's large
coins, it keeps its per-trade edge and the larger sample narrows the weekly CI.
Known risks, stated before the run:
- the added coins are smaller and noisier (more slippage, wider moves); if
  their per-trade edge is lower the CI may not narrow at all;
- the 5% per-direction cap binds more often with more coins, so more signals
  are skipped;
- section 36 traded the same large-coin sets with the 1h model and failed on
  the CI and the drawdown; the line's short leg has lost on VALID in every
  ten-coin book.

The book, frozen at section 43's TRAIN choices (nothing is re-chosen):
- section 40's range model and section 38 4h hl12's direction model, both as
  section 43 computes them (wide rows, monthly walk-forward), forecasting
  every prepared coin;
- section 41's side arm (q70, N 6), the N/2 channel exit, the 8-ATR stop, no
  clock; form `sign` (section 43); form `none` (section 41) for the margin;
- section 31's account: conf sizing 0.5-1%, 5% cap per direction.
Traded each month: section 43's ten coins (each from 365 days after listing)
plus section 36's monthly large-coin set (crypto, listed >= 1 year, top 20 by
prior-30-day volume; results/_multi/s36_ml_wide_1h/traded.json, causal).
TRAIN gates (no selection; REJECT if they fail): `sign` selectable by section
38's rule (>= 100 trades, both years and both legs positive) and its TRAIN t
at least +0.5 above `none` on the same coins.
VALID gates: section 43's (>= 100 trades, weekly mean > 0, weekly-block CI lo
> 0, cost x1.5 > 0, timing above the shifted p95, >= 8 coins and half beat
their shifts, both legs > 0, max DD <= 20%) plus `valid_added_mean_r>0` (the
trades on coins outside the ten must earn on their own).
Reported: the ten-coin and added-coin parts of the book, coins traded per
month, cap skips.
The run-time record (src/run_record.py) is written for the traded coins.
Holdout: sections 31-48 share ONE holdout.
Writes results/_multi/s48_ml_agree_wide_4h/ and journal/_multi/s48_ml_agree_wide_4h.md.
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
import ml_agree as MA  # noqa: E402
import ml_entry as ME  # noqa: E402
import ml_hold as MH  # noqa: E402
import ml_large as ML  # noqa: E402
import ml_port as MP  # noqa: E402
import ml_recent as MR  # noqa: E402
import ml_vol as MV  # noqa: E402
import ml_voltarget as VT  # noqa: E402
import ml_wf as WF  # noqa: E402
import ml_wf2 as W2  # noqa: E402
import ml_wide as MW  # noqa: E402
import run_record as RR  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "s48_ml_agree_wide_4h"
REPORT = C.ROOT / "journal" / "_multi" / "s48_ml_agree_wide_4h.md"

# ---- pre-registered (PLAN.md section 48, _multi Exp 096)
TF = MA.TF
FORM = "sign"
MIN_MARGIN = MA.MIN_MARGIN
MIN_TRADES = ML.MIN_TRADES
TEN = tuple(ML.COINS)
LOCKS = VT.LOCKS + (VT.OUT,)          # sections 31-46: one shared holdout (section 47 has its own)


# --------------------------------------------------------------------------
# pure pieces (test 46)
# --------------------------------------------------------------------------
def merge_sets(ten_sets: dict, large_sets: dict) -> dict:
    """Each month: the ten coins' set plus the large-coin set, ten first, no duplicates."""
    out = {}
    for m in sorted(set(ten_sets) | set(large_sets)):
        a = list(ten_sets.get(m, []))
        out[m] = a + [c for c in large_sets.get(m, []) if c not in a]
    return out


def split_parts(t: pd.DataFrame, ten=TEN) -> dict:
    """Trades, mean net R and summed account return of the ten-coin and added-coin parts of a book."""
    out = {}
    for name, m in (("ten", t["coin"].isin(ten)), ("added", ~t["coin"].isin(ten))):
        x = t[m]
        out[name] = {"trades": int(len(x)), "coins": int(x["coin"].nunique()),
                     "mean_r": float(x["net_r"].mean()) if len(x) else None,
                     "ret": float(x["ret"].sum()) if len(x) else 0.0,
                     "long_ret": float(x.loc[x["side"] > 0, "ret"].sum()) if len(x) else 0.0,
                     "short_ret": float(x.loc[x["side"] < 0, "ret"].sum()) if len(x) else 0.0}
    return out


# --------------------------------------------------------------------------
def _row(t, a, b, form):
    acc = MP.account(t, a, b)
    row = {"form": form, **{k: acc[k] for k in ("trades", "weekly_mean", "tstat", "max_dd", "mean_r",
                                                 "long_ret", "short_ret")},
           "per_year_r": {str(y): float(g["ret"].sum()) for y, g in t.groupby(pd.to_datetime(t["exit_time"]).dt.year)},
           "short_share": MR.short_share(t), "parts": split_parts(t)}
    row["selectable"] = MR.selectable(row, MIN_TRADES)
    return row


def evaluate(P, pred, dirp, traded, min_coins=ML.MIN_COINS, keep=False) -> dict:
    a_tr, b_tr = WF.WINDOWS["train"]
    a_va, b_va = WF.WINDOWS["valid"]
    table, train_trades = [], {}
    for form in MA.FORMS:
        t, _ = MA.run_cell(P, pred, dirp, form, a_tr, b_tr, traded)
        train_trades[form] = t
        row = _row(t, a_tr, b_tr, form)
        table.append(row)
        print(f"TRAIN-WF {form}: {row['trades']} trades, weekly {row['weekly_mean']:+.5f}, t {row['tstat']:+.2f}, "
              f"years {row['per_year_r']}, selectable {row['selectable']}, parts {row['parts']}", flush=True)
    srow = next(x for x in table if x["form"] == FORM)
    nrow = next(x for x in table if x["form"] == "none")
    margin = srow["tstat"] - nrow["tstat"]
    tj, _ = MA.judge(P, pred, dirp, FORM, a_tr, b_tr, traded, min_coins)
    train_checks = {k: tj[k] for k in ("trades", "weekly_mean", "ci_lo", "ci_hi", "tstat", "stress_weekly_mean",
                                       "timing", "shift_median", "shift_p95", "long_ret", "short_ret", "max_dd",
                                       "mean_r", "per_year_r", "top5_weeks_share", "hold")}
    train_checks["breadth"] = {k: tj["breadth"][k] for k in ("eligible", "share")}
    v, t = MA.judge(P, pred, dirp, FORM, a_va, b_va, traded, min_coins)
    v["parts"] = split_parts(t)
    v["coins_traded"] = int(t["coin"].nunique())
    nv, nt = MA.judge(P, pred, dirp, "none", a_va, b_va, traded, min_coins)
    v["none_same_coins"] = {k: nv[k] for k in ("trades", "weekly_mean", "ci_lo", "ci_hi", "tstat", "mean_r",
                                               "long_ret", "short_ret", "max_dd", "short_share")}
    s43 = MA.OUT / "summary.json"
    if s43.exists():
        r43 = json.loads(s43.read_text())["valid"]
        v["s43_ten_coins"] = {k: r43.get(k) for k in ("trades", "weekly_mean", "ci_lo", "ci_hi", "tstat", "mean_r",
                                                       "long_ret", "short_ret", "max_dd")}
    added = v["parts"]["added"]
    gates = {"train_sign_selectable": srow["selectable"],
             f"train_margin>={MIN_MARGIN}": margin >= MIN_MARGIN,
             "train_weekly_mean>0": srow["weekly_mean"] > 0,
             f"valid_trades>={MIN_TRADES}": v["trades"] >= MIN_TRADES,
             "valid_weekly_mean>0": v["weekly_mean"] > 0,
             "valid_ci_lo>0": v["ci_lo"] > 0,
             "stress_weekly_mean>0": v["stress_weekly_mean"] > 0,
             "timing_beats_shift_p95": v["shift_p95"] is not None and v["timing"] is not None
             and v["timing"] > v["shift_p95"],
             f"coins>={min_coins}": v["breadth"]["eligible"] >= min_coins,
             f"breadth>={MP.BREADTH_SHARE}": v["breadth"]["share"] >= MP.BREADTH_SHARE,
             "both_legs>0": v["long_ret"] > 0 and v["short_ret"] > 0,
             f"max_dd<={MP.MAX_DD}": v["max_dd"] <= MP.MAX_DD,
             "valid_added_mean_r>0": added["mean_r"] is not None and added["mean_r"] > 0}
    failed = [k for k, g in gates.items() if not g]
    res = {"chosen": {"form": FORM, "arm": "_".join(map(str, MA.ARM)), "dir": MA.DIR_SCHEME, "tf": TF,
                      "sizing": ML.SIZING, "cap": ML.CAP, "universe": "ten + section 36 monthly large-coin sets"},
           "train_table": table, "train_margin": margin, "train_checks": train_checks, "valid": v,
           "verdict": "REJECT" if failed else "PASS", "gates_failed": failed,
           "model": {"tf": TF, "range_label": f"next {MV.H_VOL} bars' range / ATR",
                     "direction": f"section 38 4h {MA.DIR_SCHEME}, horizons {MR.horizons(TF)}",
                     "arm": list(MA.ARM), "min_margin": MIN_MARGIN}}
    if keep:
        res["_trades"] = t
        res["_train_trades"] = train_trades
    return res


# --------------------------------------------------------------------------
def _record(res, P, pred, dirp, keep, traded, started, inputs) -> None:
    feats = MH._cols(P)
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
        _, _, sk = MA.run_cell(P, pred, dirp, FORM, a, b, traded, keep_skipped=True)
        logs = [r for r in keep["log"] if lo <= pd.Timestamp(r["month"], tz="UTC") < hi]
        ylab = pd.concat([pd.Series(lab[c][(P[c]["X"].index >= lo) & (P[c]["X"].index < hi)]) for c in P],
                         ignore_index=True)
        meta = RR.metadata(feats, list(P), logs, dict(ME.LGB_PARAMS, **MP._cfg(TF)["setting"]),
                           f"(max high - min low) of the next {MV.H_VOL} 4h bars / ATR at the decision bar",
                           (MV.H_VOL,), {"split": [a, b], "cell": FORM, "direction": MA.DIR_SCHEME}, ylab)
        wk = MP.weekly(res["_trades"], a, b) if split == "valid" else None
        RR.write(OUT / "record" / split, feature_importance=imp, training_metadata=meta, predictions=preds,
                 skipped_signals=sk, run_info=RR.run_info(started, inputs),
                 holdout_power=RR.holdout_power(wk) if wk is not None else None)
        dp = RR.predictions({c: P[c]["X"].index for c in P},
                            {c: dirp[c].reindex(P[c]["X"].index).to_numpy() for c in P},
                            {c: MW.label_h(P[c]["bars"], MR.horizons(TF)[1]) for c in P}, a, b)
        dp.to_parquet(OUT / "record" / split / "direction_predictions.parquet", index=False)


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
                raise SystemExit(f"--final refused: sections 31-48 share one holdout and {o.name} used it")
    elif res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    if not (MW.OUT / "traded.json").exists():
        raise SystemExit("no section 36 traded sets: run  python src/ml_wide.py --build  first")
    months, ten_sets, by_tf, core, members = MR._load()
    large = json.loads((MW.OUT / "traded.json").read_text())
    traded = merge_sets(ten_sets, large)
    names = sorted({c for lst in traded.values() for c in lst})
    missing = [c for c in names if c not in by_tf[TF]]
    inputs = [WF.cache_dir(TF) / f"{c}.parquet" for c in sorted(by_tf[TF])]
    spans = [WF.WINDOWS["train"], WF.WINDOWS["valid"]] + ([WF.WINDOWS["holdout"]] if final else [])
    print(f"[ml_agree_wide] training coins {len(by_tf[TF])}; coins ever traded {len(names)} "
          f"(no cache: {missing})", flush=True)
    P = W2.prepare(by_tf, TF)
    del by_tf
    gc.collect()
    masks = {c: MW.training_mask(P[c]["X"].index, c, core, members, True) for c in P}
    keep = {}
    setting = MP._cfg(TF)["setting"]
    pred_all = MV.forecasts(P, setting, masks, spans, keep=keep)
    print("[ml_agree_wide] range forecasts done; direction forecasts (section 38 4h hl12) next", flush=True)
    per_h = MR.forecasts_w(P, TF, setting, masks, spans, MA.DIR_SCHEME)
    PT = {c: P[c] for c in names if c in P}
    dirp = ML.combine_set(PT, per_h, MR.horizons(TF))
    del per_h
    gc.collect()
    pred = {c: pred_all[c] for c in PT}
    if final:
        a, b = WF.WINDOWS["holdout"]
        h, t = MA.judge(PT, pred, dirp, FORM, a, b, traded)
        h["parts"] = split_parts(t)
        h["verdict"] = ("CONFIRMED" if h["weekly_mean"] > 0 and h["ci_lo"] > 0 and h["shift_median"] is not None
                        and h["timing"] is not None and h["timing"] > h["shift_median"]
                        and h["breadth"]["share"] >= MP.BREADTH_SHARE else "FAILED")
        lock.write_text(json.dumps(h, indent=1, default=str))
        t.to_csv(OUT / "trades_holdout.csv.gz", index=False)
        write_report(res)
        print(json.dumps({k: h.get(k) for k in ("trades", "weekly_mean", "ci_lo", "verdict")}, indent=1))
        return
    res = evaluate(PT, pred, dirp, traded, keep=True)
    res["coins_no_cache"] = missing
    res["reproduces_s38_dir"] = MA._check_dir({c: PT[c] for c in TEN if c in PT}, dirp)
    print(f"reproduces section 38 direction: {res['reproduces_s38_dir']}", flush=True)
    _record(res, PT, pred, dirp, keep, traded, started, inputs)
    res.pop("_trades").to_csv(OUT / "trades_valid.csv.gz", index=False)
    for form, tt in res.pop("_train_trades").items():
        tt.to_csv(OUT / f"trades_train_{form}.csv.gz", index=False)
    res_path.write_text(json.dumps(res, indent=1, default=str))
    write_report(res)
    print(f"\nML_AGREE_WIDE: {res['verdict']} failed {res['gates_failed']}")


def write_report(r: dict) -> None:
    v = r["valid"]
    f = (lambda x, k=5: "-" if x is None else f"{x:+.{k}f}")
    o, s = v.get("none_same_coins", {}), v.get("s43_ten_coins", {})
    L = ["# Section 43's book on more coins (PLAN.md section 48)", "",
         "GENERATED by `src/ml_agree_wide.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}** (failed: {r['gates_failed'] or 'none'})", "",
         f"- TRAIN margin (sign t - none t): {r['train_margin']:+.2f}; section 38 direction reproduced: "
         f"{r.get('reproduces_s38_dir')}; coins without a cache: {r.get('coins_no_cache')}",
         f"- VALID {v['trades']} trades on {v['coins_traded']} coins: weekly {f(v['weekly_mean'])}, 95% CI "
         f"[{f(v['ci_lo'])}, {f(v['ci_hi'])}], t {v['tstat']:+.2f}; mean R {f(v['mean_r'], 4)}; long "
         f"{f(v['long_ret'], 4)} / short {f(v['short_ret'], 4)}; max DD {v['max_dd']:.4f}",
         f"- cost x1.5 {f(v['stress_weekly_mean'])}; timing {f(v['timing'], 4)} vs shifted p95 {f(v['shift_p95'], 4)}; "
         f"breadth {len(v['breadth']['beat'])} of {v['breadth']['eligible']}; short share {v['short_share']}",
         f"- parts: {v['parts']}",
         f"- section 43 on the ten coins (VALID): {s}",
         f"- form none on the same coins (VALID): {o}",
         f"- best 5 weeks = {f(v['top5_weeks_share'], 3)} of the total; weekly mean without them "
         f"{f(v['weekly_mean_without_top5'])}", "",
         "| form | TRAIN trades | weekly mean | t | mean R | long | short | by year | selectable | parts |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for x in r["train_table"]:
        L.append(f"| {x['form']} | {x['trades']} | {f(x['weekly_mean'])} | {x['tstat']:+.2f} | {f(x['mean_r'], 4)} | "
                 f"{f(x['long_ret'], 4)} | {f(x['short_ret'], 4)} | {x['per_year_r']} | {x['selectable']} | "
                 f"{x['parts']} |")
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
