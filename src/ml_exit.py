"""Section 41's book with an exit decided by the range forecast (PLAN.md section 42)

    python src/ml_exit.py            # TRAIN/VALID, once (uses section 36's caches; no new download)
    python src/ml_exit.py --final    # HOLDOUT once, only after PASS (shared with sections 31-41)

Why (_multi Exp 071/072):
- section 41 fails one gate, `valid_ci_lo>0`;
- its edge per trade is small (+0.0222 R), and it exits on the N/2 = 3-bar opposite channel after a median of
  about 8 bars;
- sizing cannot fix the CI (Exp 072): the t-statistic does not change when trades are rescaled, and the
  forecast says nothing about the result of an armed trade.

What is left is the per-trade edge, and the exit is the untested lever.

Hypothesis: the range forecast says when a coin is in a large-move state. A breakout taken in that state should
be held while the state lasts and closed when it ends, rather than closed on the first 3-bar pullback. Holding
through the noise of a still-volatile move lets the winners run. The exit then follows the model's own state
signal, not the clock.

Unchanged from section 41 (src/ml_side.py):
- the forecasts;
- the entry: the arm frozen at section 41's TRAIN choice, side / q70 / N = 6;
- the 8-ATR protective stop, no clock;
- an armed opposite breakout still reverses the position;
- section 31's account: conf sizing, 5% cap per direction.

New: the exit (each fills at the next bar's open).
  chan    section 41's: close beyond the previous N/2 bars' opposite extreme (must reproduce section 41's
          TRAIN row side_q70_n6)
  fc      the forecast falls below its own causal rolling median (the last MH.ROLL = 180 bars, the bar
          included); price exits only by the 8-ATR stop or an armed reversal
  fcwide  the forecast falls below that median, or the close goes beyond the previous N bars' opposite
          extreme (a wider price guard than chan's N/2)

TRAIN (walk-forward 2021-22) picks 1 of 3 forms by section 38's rule (>= 100 trades, both TRAIN years and both
legs positive, then the weekly t). These are REJECT:
- no selectable form (train_cell_selectable);
- a `chan` choice (train_chose_fc_exit; it is section 41).

VALID gates: section 41's. Reported:
- the `chan` book on VALID (= section 41's recorded book, no new look);
- the mean hold in bars and the exit mix for every form;
- the short share by year.

The run-time record (src/run_record.py) is written.
Holdout: sections 31-42 share ONE holdout.
Writes results/_multi/s42_ml_exit_4h/ and journal/_multi/s42_ml_exit_4h.md.
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
import ml_recent as MR  # noqa: E402
import ml_side as MS  # noqa: E402
import ml_vol as MV  # noqa: E402
import ml_wf as WF  # noqa: E402
import ml_wf2 as W2  # noqa: E402
import ml_wide as MW  # noqa: E402
import run_record as RR  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "s42_ml_exit_4h"
REPORT = C.ROOT / "journal" / "_multi" / "s42_ml_exit_4h.md"

# ---- pre-registered (PLAN.md section 42, _multi Exp 073)
TF = MV.TF
ARM = ("side", "q70", 6)                          # section 41's TRAIN choice, frozen
EXITS = ("chan", "fc", "fcwide")
MED_ROLL, MED_MIN = MH.ROLL, MH.MIN_ROLL          # forecast median window (bars)
MIN_TRADES = ML.MIN_TRADES
LOCKS = MS.LOCKS + (MS.OUT,)                      # sections 31-41: one shared holdout


# --------------------------------------------------------------------------
# pure pieces (test 40)
# --------------------------------------------------------------------------
def fc_low(p: np.ndarray) -> np.ndarray:
    """True where the forecast is below its causal rolling median (bar included); False while warming up."""
    p = np.asarray(p, float)
    med = np.full(len(p), np.nan)
    ok = np.isfinite(p)
    if ok.any():
        med[ok] = pd.Series(p[ok]).rolling(MED_ROLL, min_periods=MED_MIN).median().to_numpy()
    with np.errstate(invalid="ignore"):
        return np.isfinite(med) & (p < med)


def exit_path(close, hh, ll, xh, xl, armed_up, armed_dn, allowed, low, form) -> np.ndarray:
    """Desired position after each decision bar. Entries and reversals as section 41; the exit by form."""
    if form == "chan":
        return MS.side_path(close, hh, ll, xh, xl, armed_up, armed_dn, allowed)
    out, pos = np.zeros(len(close)), 0.0
    for t in range(len(close)):
        c = close[t]
        up = armed_up[t] and allowed[t] and np.isfinite(hh[t]) and c > hh[t]
        dn = armed_dn[t] and allowed[t] and np.isfinite(ll[t]) and c < ll[t]
        guard_l = form == "fcwide" and np.isfinite(ll[t]) and c < ll[t]
        guard_s = form == "fcwide" and np.isfinite(hh[t]) and c > hh[t]
        if pos > 0 and (low[t] or guard_l or dn):
            pos = -1.0 if dn else 0.0
        elif pos < 0 and (low[t] or guard_s or up):
            pos = 1.0 if up else 0.0
        elif pos == 0:
            pos = 1.0 if up else (-1.0 if dn else 0.0)
        out[t] = pos
    return out


# --------------------------------------------------------------------------
def run_cell(P, pred, form, a, b, traded, stress=1.0, keep_skipped=False):
    arm_form, q, n = ARM
    fr, paths, skipped = [], {}, []
    for c in P:
        p = pred[c].reindex(P[c]["X"].index).to_numpy()
        tb = P[c].get("tbars", P[c]["bars"])
        hh, ll, xh, xl = MV.channels(tb, n)
        kall = P[c]["pos"]
        close_all = tb["close"].to_numpy(float)[kall]
        au, ad, ru, rd = MS.arms(p, close_all, hh[kall], ll[kall], arm_form, q)
        low = fc_low(p)
        lo, hi, rows = MH._window(P, c, a, b)
        if not len(rows):
            continue
        k = kall[rows]
        idx = P[c]["X"].index[rows]
        allowed = MW.month_mask(idx, c, traded)
        close = close_all[rows]
        desired = exit_path(close, hh[k], ll[k], xh[k], xl[k], au[rows], ad[rows], allowed, low[rows], form)
        if keep_skipped:
            one = np.ones(len(rows), bool)
            ref = exit_path(close, hh[k], ll[k], xh[k], xl[k], one, one, allowed, low[rows], form)
            lab = MW.label_h(P[c]["bars"], MV.H_VOL)[rows]
            skipped.append(RR.skipped(idx, c, ref, desired, "breakout not armed for its side", lab))
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
        fr.append(t.assign(coin=c))
        paths[c] = (desired, rows, lo, hi)
    t = pd.concat(fr, ignore_index=True) if fr else pd.DataFrame(
        columns=["entry_time", "exit_time", "side", "net_r", "conf", "coin"])
    out = MP.size_trades(t, ML.SIZING, ML.CAP), paths
    return (*out, pd.concat(skipped, ignore_index=True) if skipped else None) if keep_skipped else out


def hold_stats(t: pd.DataFrame) -> dict:
    if t.empty:
        return {}
    bars = t["bars"] if "bars" in t else (pd.to_datetime(t["exit_time"]) - pd.to_datetime(t["entry_time"])) \
        / pd.Timedelta(minutes=TF)
    return {"mean_bars": float(bars.mean()), "median_bars": float(bars.median()),
            "exit_mix": {str(k): int(v) for k, v in t["reason"].value_counts().items()} if "reason" in t else {}}


def judge(P, pred, form, a, b, traded, min_coins=ML.MIN_COINS):
    t, paths = run_cell(P, pred, form, a, b, traded)
    acc = MP.account(t, a, b)
    acc["stress_weekly_mean"] = MP.account(run_cell(P, pred, form, a, b, traded, 1.5)[0], a, b)["weekly_mean"]
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
               neg_weeks=int((w < 0).sum()), short_share=MR.short_share(t), hold=hold_stats(t))
    return acc, t


def evaluate(P, pred, traded, min_coins=ML.MIN_COINS, keep=False) -> dict:
    a_tr, b_tr = WF.WINDOWS["train"]
    a_va, b_va = WF.WINDOWS["valid"]
    table, train_trades = [], {}
    for form in EXITS:
        t, _ = run_cell(P, pred, form, a_tr, b_tr, traded)
        train_trades[form] = t
        acc = MP.account(t, a_tr, b_tr)
        row = {"form": form, **{k: acc[k] for k in ("trades", "weekly_mean", "tstat", "per_year", "max_dd", "mean_r",
                                                     "long_ret", "short_ret")},
               "per_year_r": {str(y): float(g["ret"].sum()) for y, g in t.groupby(pd.to_datetime(t["exit_time"]).dt.year)},
               "short_share": MR.short_share(t), "hold": hold_stats(t)}
        row["selectable"] = MR.selectable(row, MIN_TRADES)
        table.append(row)
        print(f"TRAIN-WF {form}: {acc['trades']} trades, weekly {acc['weekly_mean']:+.5f}, t {acc['tstat']:+.2f}, "
              f"years {row['per_year_r']}, hold {row['hold'].get('median_bars')}, selectable {row['selectable']}",
              flush=True)
    ok = [x for x in table if x["selectable"]]
    best = max(ok, key=lambda x: x["tstat"]) if ok else max(table, key=lambda x: x["tstat"])
    form = best["form"]
    tj, _ = judge(P, pred, form, a_tr, b_tr, traded, min_coins)
    train_checks = {k: tj[k] for k in ("trades", "weekly_mean", "ci_lo", "ci_hi", "tstat", "stress_weekly_mean",
                                       "timing", "shift_median", "shift_p95", "long_ret", "short_ret", "max_dd",
                                       "mean_r", "per_year_r", "top5_weeks_share", "hold")}
    train_checks["breadth"] = {k: tj["breadth"][k] for k in ("eligible", "share")}
    v, t = judge(P, pred, form, a_va, b_va, traded, min_coins)
    if form != "chan":
        cv, _ = judge(P, pred, "chan", a_va, b_va, traded, min_coins)
        v["chan_same_arm"] = {k: cv[k] for k in ("trades", "weekly_mean", "ci_lo", "ci_hi", "tstat", "mean_r",
                                                 "long_ret", "short_ret", "max_dd", "short_share", "hold")}
    gates = {"train_cell_selectable": bool(ok),
             "train_chose_fc_exit": form != "chan",
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
    res = {"chosen": {"form": form, "arm": "_".join(map(str, ARM)), "tf": TF, "sizing": ML.SIZING, "cap": ML.CAP},
           "train_table": table, "train_checks": train_checks, "valid": v,
           "verdict": "REJECT" if failed else "PASS", "gates_failed": failed,
           "model": {"tf": TF, "label": f"next {MV.H_VOL} bars' range / ATR", "coins": list(ML.COINS),
                     "arm": list(ARM), "exits": list(EXITS), "median_window": MED_ROLL}}
    if keep:
        res["_trades"] = t
        res["_train_trades"] = train_trades
    return res


# --------------------------------------------------------------------------
def _record(res, P, pred, keep, traded, started, inputs) -> None:
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
        _, _, sk = run_cell(P, pred, form, a, b, traded, keep_skipped=True)
        logs = [r for r in keep["log"] if lo <= pd.Timestamp(r["month"], tz="UTC") < hi]
        ylab = pd.concat([pd.Series(lab[c][(P[c]["X"].index >= lo) & (P[c]["X"].index < hi)]) for c in P],
                         ignore_index=True)
        meta = RR.metadata(feats, list(P), logs, dict(ME.LGB_PARAMS, **MP._cfg(TF)["setting"]),
                           f"(max high - min low) of the next {MV.H_VOL} 4h bars / ATR at the decision bar",
                           (MV.H_VOL,), {"split": [a, b], "cell": form}, ylab)
        wk = MP.weekly(res["_trades"], a, b) if split == "valid" else None
        RR.write(OUT / "record" / split, feature_importance=imp, training_metadata=meta, predictions=preds,
                 skipped_signals=sk, run_info=RR.run_info(started, inputs),
                 holdout_power=RR.holdout_power(wk) if wk is not None else None)


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
                raise SystemExit(f"--final refused: sections 31-42 share one holdout and {o.name} used it")
    elif res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    if not (MW.OUT / "members.json").exists():
        raise SystemExit("no section 36 member sets: run  python src/ml_wide.py --build  first")
    months, traded, by_tf, core, members = MR._load()
    inputs = [WF.cache_dir(TF) / f"{c}.parquet" for c in sorted(by_tf[TF])]
    spans = [WF.WINDOWS["train"], WF.WINDOWS["valid"]] + ([WF.WINDOWS["holdout"]] if final else [])
    print(f"[ml_exit] training coins {len(by_tf[TF])}; traded {len(ML.COINS)}", flush=True)
    P = W2.prepare(by_tf, TF)
    del by_tf
    gc.collect()
    masks = {c: MW.training_mask(P[c]["X"].index, c, core, members, True) for c in P}
    keep = {}
    pred_all = MV.forecasts(P, MP._cfg(TF)["setting"], masks, spans, keep=keep)
    PT = {c: P[c] for c in ML.COINS if c in P}
    pred = {c: pred_all[c] for c in PT}
    if final:
        a, b = WF.WINDOWS["holdout"]
        h, t = judge(PT, pred, res["chosen"]["form"], a, b, traded)
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
    s41 = MS.OUT / "summary.json"
    if s41.exists():                                  # reproduction check: chan is section 41's chosen row
        ref = {x["form"]: (x["trades"], round(x["tstat"], 6)) for x in json.loads(s41.read_text())["train_table"]}
        chan = next(x for x in res["train_table"] if x["form"] == "chan")
        res["reproduces_s41"] = ref.get(MS.cell_name(ARM)) == (chan["trades"], round(chan["tstat"], 6))
        print(f"reproduces section 41: {res['reproduces_s41']}", flush=True)
    _record(res, PT, pred, keep, traded, started, inputs)
    res.pop("_trades").to_csv(OUT / "trades_valid.csv.gz", index=False)
    for form, tt in res.pop("_train_trades").items():
        tt.to_csv(OUT / f"trades_train_{form}.csv.gz", index=False)
    res_path.write_text(json.dumps(res, indent=1, default=str))
    write_report(res)
    print(f"\nML_EXIT: chose {res['chosen']['form']} -> {res['verdict']} failed {res['gates_failed']}")


def write_report(r: dict) -> None:
    v = r["valid"]
    f = (lambda x, k=5: "-" if x is None else f"{x:+.{k}f}")
    o = v.get("chan_same_arm", {})
    L = ["# Section 41's book with an exit decided by the range forecast (PLAN.md section 42)", "",
         "GENERATED by `src/ml_exit.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}** (TRAIN chose {r['chosen']['form']}; failed: {r['gates_failed'] or 'none'})", "",
         f"- reproduces section 41 (chan TRAIN row): {r.get('reproduces_s41')}",
         f"- VALID {v['trades']} trades: weekly {f(v['weekly_mean'])}, 95% CI [{f(v['ci_lo'])}, {f(v['ci_hi'])}], "
         f"t {v['tstat']:+.2f}; mean R {f(v['mean_r'], 4)}; long {f(v['long_ret'], 4)} / short {f(v['short_ret'], 4)}; "
         f"max DD {v['max_dd']:.4f}; hold {v.get('hold')}",
         f"- cost x1.5 {f(v['stress_weekly_mean'])}; timing {f(v['timing'], 4)} vs shifted p95 {f(v['shift_p95'], 4)}; "
         f"breadth {len(v['breadth']['beat'])} of {v['breadth']['eligible']}; short share {v['short_share']}",
         f"- section 41's chan exit, same arm (VALID): {o.get('trades')} trades, weekly {f(o.get('weekly_mean'))}, "
         f"CI [{f(o.get('ci_lo'))}, {f(o.get('ci_hi'))}], mean R {f(o.get('mean_r'), 4)}, hold {o.get('hold')}",
         f"- best 5 weeks = {f(v['top5_weeks_share'], 3)} of the total; weekly mean without them "
         f"{f(v['weekly_mean_without_top5'])}", "",
         "| exit | TRAIN trades | weekly mean | t | mean R | long | short | by year | hold | selectable |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for x in r["train_table"]:
        L.append(f"| {x['form']} | {x['trades']} | {f(x['weekly_mean'])} | {x['tstat']:+.2f} | {f(x['mean_r'], 4)} | "
                 f"{f(x['long_ret'], 4)} | {f(x['short_ret'], 4)} | {x['per_year_r']} | {x['hold']} | "
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
