"""Section 40's range forecast armed per side (PLAN.md section 41)

    python src/ml_side.py            # TRAIN/VALID, once (uses section 36's caches; no new download)
    python src/ml_side.py --final    # HOLDOUT once, only after PASS (shared with sections 31-40)

Why (_multi Exp 068): section 40's arm is side-free but behaves as a long tilt.
On VALID it kept 787 of 1,884 up-breaks (42%) but only 291 of 1,576 down-breaks
(18%), because the range forecast was higher around up-moves in 2023-24. Most
of its gain over the rule came from removing shorts, and its short leg still
lost.

Hypothesis: if each side is armed against its OWN history (an up-break must
carry a range forecast above the q-quantile of the forecasts at that coin's
recent up-breaks; a down-break the same against its recent down-breaks), each
side keeps the breakouts with the largest expected move for that side. The
long tilt then stops coming from the threshold, and both legs earn.
Known risk, stated before the run: in a rising market, equal keep rates add
shorts, and section 40's VALID down-breaks were the losing ones. A worse VALID
book is a possible honest result.

Unchanged from section 40 (src/ml_vol.py):
- the model: ten coins, 4h, wide rows, section 30's 4h setting, expanding
  monthly walk-forward;
- the label: next 6 bars' range / ATR;
- the breakout and exit channels, the 8-ATR stop, no clock;
- section 31's account: conf sizing 0.5-1%, 5% cap per direction.

New: the arm.
  pooled  section 40's arm: forecast > its rolling q-quantile over the last
          MH.ROLL bars (must reproduce section 40 cell for cell)
  side    long side armed when forecast > the rolling q-quantile of the
          forecasts at the coin's last SIDE_ROLL up-breaks (close > previous-N
          high, the bar included, min SIDE_MIN); short side the same over
          down-breaks; confidence = forecast / that side's threshold
TRAIN (walk-forward 2021-22) picks 1 of 8 cells: arm form {pooled, side} x
q {0.70, 0.85} x N {6, 18}. Selection: section 38's rule (>= 100 trades, both
TRAIN years and both legs positive, then the weekly t). These are REJECT:
- no selectable cell (train_cell_selectable);
- a pooled choice (train_chose_side; it is section 40).
VALID gates: section 40's. Reported:
- section 40's pooled cell with the same q and N on VALID (the comparison
  this round is about);
- each side's keep rate (trades / (trades + skipped breakouts));
- the short share by year.
The run-time record (src/run_record.py) is written; skipped signals are the
breakouts the chosen arm filtered out.
Holdout: sections 31-41 share ONE holdout.
Writes results/_multi/s41_ml_side_4h/ and journal/_multi/s41_ml_side_4h.md.
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
import ml_vol as MV  # noqa: E402
import ml_wf as WF  # noqa: E402
import ml_wf2 as W2  # noqa: E402
import ml_wide as MW  # noqa: E402
import run_record as RR  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "s41_ml_side_4h"
REPORT = C.ROOT / "journal" / "_multi" / "s41_ml_side_4h.md"

# ---- pre-registered (PLAN.md section 41, _multi Exp 069)
TF = MV.TF
FORMS = ("pooled", "side")
QS = {"q70": 0.70, "q85": 0.85}
CHANNELS = MV.CHANNELS
SIDE_ROLL = 60                                    # last 60 same-side breakouts (~ a few months per coin)
SIDE_MIN = 20
MIN_TRADES = ML.MIN_TRADES
LOCKS = MV.LOCKS + (MV.OUT,)                      # sections 31-40: one shared holdout


# --------------------------------------------------------------------------
# pure pieces (test 39)
# --------------------------------------------------------------------------
def side_arm(p: np.ndarray, event: np.ndarray, q: float) -> tuple[np.ndarray, np.ndarray]:
    """(armed, ratio) for one side: the threshold at bar t is the q-quantile of the
    forecasts at the last SIDE_ROLL event bars up to and including t (causal)."""
    p = np.asarray(p, float)
    ev = np.flatnonzero(np.asarray(event, bool) & np.isfinite(p))
    thr = np.full(len(p), np.nan)
    if len(ev):
        thr[ev] = pd.Series(p[ev]).rolling(SIDE_ROLL, min_periods=SIDE_MIN).quantile(q).to_numpy()
        thr = pd.Series(thr).ffill().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(np.isfinite(thr) & (thr > 0), p / thr, np.nan)
    return np.isfinite(ratio) & (ratio > 1.0), ratio


def side_path(close, hh, ll, xh, xl, armed_up, armed_dn, allowed) -> np.ndarray:
    """Section 40's breakout path with a separate arm per side (equal arms = MV.breakout_path)."""
    out, pos = np.zeros(len(close)), 0.0
    for t in range(len(close)):
        c = close[t]
        up = armed_up[t] and allowed[t] and np.isfinite(hh[t]) and c > hh[t]
        dn = armed_dn[t] and allowed[t] and np.isfinite(ll[t]) and c < ll[t]
        if pos > 0 and ((np.isfinite(xl[t]) and c < xl[t]) or dn):
            pos = -1.0 if dn else 0.0
        elif pos < 0 and ((np.isfinite(xh[t]) and c > xh[t]) or up):
            pos = 1.0 if up else 0.0
        elif pos == 0:
            pos = 1.0 if up else (-1.0 if dn else 0.0)
        out[t] = pos
    return out


def cells() -> list[tuple[str, str, int]]:
    return [(f, q, n) for f in FORMS for q in QS for n in CHANNELS]


def cell_name(cell) -> str:
    return f"{cell[0]}_{cell[1]}_n{cell[2]}"


def arms(p, close, hh, ll, form, q):
    """(armed_up, armed_dn, ratio_up, ratio_dn) over every row of one coin."""
    if form == "pooled":
        a, r = MV.arm(p, QS[q])
        return a, a, r, r
    with np.errstate(invalid="ignore"):
        up_ev, dn_ev = close > hh, close < ll
    au, ru = side_arm(p, up_ev, QS[q])
    ad, rd = side_arm(p, dn_ev, QS[q])
    return au, ad, ru, rd


# --------------------------------------------------------------------------
def run_cell(P, pred, cell, a, b, traded, stress=1.0, keep_skipped=False):
    form, q, n = cell
    fr, paths, skipped = [], {}, []
    for c in P:
        p = pred[c].reindex(P[c]["X"].index).to_numpy()
        tb = P[c].get("tbars", P[c]["bars"])
        hh, ll, xh, xl = MV.channels(tb, n)
        kall = P[c]["pos"]
        close_all = tb["close"].to_numpy(float)[kall]
        au, ad, ru, rd = arms(p, close_all, hh[kall], ll[kall], form, q)
        lo, hi, rows = MH._window(P, c, a, b)
        if not len(rows):
            continue
        k = kall[rows]
        idx = P[c]["X"].index[rows]
        allowed = MW.month_mask(idx, c, traded)
        close = close_all[rows]
        desired = side_path(close, hh[k], ll[k], xh[k], xl[k], au[rows], ad[rows], allowed)
        if keep_skipped:
            ref = side_path(close, hh[k], ll[k], xh[k], xl[k], np.ones(len(rows), bool), np.ones(len(rows), bool),
                            allowed)
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


def keep_rates(t: pd.DataFrame, sk: pd.DataFrame | None) -> dict:
    """Per side: trades taken / (taken + breakouts the arm filtered out)."""
    out = {}
    for s, name in ((1, "long"), (-1, "short")):
        n_t = int((t["side"] > 0).sum() if s > 0 else (t["side"] < 0).sum())
        n_s = int((sk["side"] == s).sum()) if sk is not None and len(sk) else 0
        out[name] = {"taken": n_t, "skipped": n_s, "keep_rate": n_t / (n_t + n_s) if n_t + n_s else None}
    return out


def evaluate(P, pred, traded, min_coins=ML.MIN_COINS, keep=False) -> dict:
    a_tr, b_tr = WF.WINDOWS["train"]
    a_va, b_va = WF.WINDOWS["valid"]
    table, train_trades = [], {}
    for cell in cells():
        t, _ = run_cell(P, pred, cell, a_tr, b_tr, traded)
        train_trades[cell_name(cell)] = t
        acc = MP.account(t, a_tr, b_tr)
        row = {"form": cell_name(cell), "arm": cell[0], "q": cell[1], "channel": cell[2],
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
    cell = (best["arm"], best["q"], best["channel"])
    tj, _ = judge(P, pred, cell, a_tr, b_tr, traded, min_coins)
    train_checks = {k: tj[k] for k in ("trades", "weekly_mean", "ci_lo", "ci_hi", "tstat", "stress_weekly_mean",
                                       "timing", "shift_median", "shift_p95", "long_ret", "short_ret", "max_dd",
                                       "mean_r", "per_year_r", "top5_weeks_share")}
    train_checks["breadth"] = {k: tj["breadth"][k] for k in ("eligible", "share")}
    v, t = judge(P, pred, cell, a_va, b_va, traded, min_coins)
    _, _, sk = run_cell(P, pred, cell, a_va, b_va, traded, keep_skipped=True)
    v["keep_rate"] = keep_rates(t, sk)
    other = ("pooled" if cell[0] == "side" else "side", cell[1], cell[2])
    ov, ot = judge(P, pred, other, a_va, b_va, traded, min_coins)
    _, _, osk = run_cell(P, pred, other, a_va, b_va, traded, keep_skipped=True)
    v["other_form_same_cell"] = {"form": cell_name(other), "keep_rate": keep_rates(ot, osk),
                                 **{k: ov[k] for k in ("trades", "weekly_mean", "ci_lo", "ci_hi", "tstat", "mean_r",
                                                       "long_ret", "short_ret", "max_dd", "short_share")}}
    gates = {"train_cell_selectable": bool(ok),
             "train_chose_side": cell[0] == "side",
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
    res = {"chosen": {"form": best["form"], "arm": cell[0], "q": cell[1], "channel": cell[2], "tf": TF,
                      "sizing": ML.SIZING, "cap": ML.CAP},
           "train_table": table, "train_checks": train_checks, "valid": v,
           "verdict": "REJECT" if failed else "PASS", "gates_failed": failed,
           "model": {"tf": TF, "label": f"next {MV.H_VOL} bars' range / ATR", "coins": list(ML.COINS),
                     "forms": list(FORMS), "qs": QS, "channels": list(CHANNELS), "side_roll": SIDE_ROLL,
                     "side_min": SIDE_MIN}}
    if keep:
        res["_trades"] = t
        res["_train_trades"] = train_trades
    return res


# --------------------------------------------------------------------------
def _record(res, P, pred, keep, traded, started, inputs) -> None:
    feats = MH._cols(P)
    cell = (res["chosen"]["arm"], res["chosen"]["q"], res["chosen"]["channel"])
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
        _, _, sk = run_cell(P, pred, cell, a, b, traded, keep_skipped=True)
        logs = [r for r in keep["log"] if lo <= pd.Timestamp(r["month"], tz="UTC") < hi]
        ylab = pd.concat([pd.Series(lab[c][(P[c]["X"].index >= lo) & (P[c]["X"].index < hi)]) for c in P],
                         ignore_index=True)
        meta = RR.metadata(feats, list(P), logs, dict(ME.LGB_PARAMS, **MP._cfg(TF)["setting"]),
                           f"(max high - min low) of the next {MV.H_VOL} 4h bars / ATR at the decision bar",
                           (MV.H_VOL,), {"split": [a, b], "cell": res["chosen"]["form"]}, ylab)
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
                raise SystemExit(f"--final refused: sections 31-41 share one holdout and {o.name} used it")
    elif res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    if not (MW.OUT / "members.json").exists():
        raise SystemExit("no section 36 member sets: run  python src/ml_wide.py --build  first")
    months, traded, by_tf, core, members = MR._load()
    inputs = [WF.cache_dir(TF) / f"{c}.parquet" for c in sorted(by_tf[TF])]
    spans = [WF.WINDOWS["train"], WF.WINDOWS["valid"]] + ([WF.WINDOWS["holdout"]] if final else [])
    print(f"[ml_side] training coins {len(by_tf[TF])}; traded {len(ML.COINS)}", flush=True)
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
        h, t = judge(PT, pred, (res["chosen"]["arm"], res["chosen"]["q"], res["chosen"]["channel"]), a, b, traded)
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
    s40 = MV.OUT / "summary.json"
    if s40.exists():                                  # reproduction check: the pooled rows are section 40's
        ref = {x["form"]: (x["trades"], round(x["tstat"], 6)) for x in json.loads(s40.read_text())["train_table"]}
        res["reproduces_s40"] = {x["form"]: ref.get(f"{x['q']}_n{x['channel']}") == (x["trades"], round(x["tstat"], 6))
                                 for x in res["train_table"] if x["arm"] == "pooled"}
        print(f"reproduces section 40: {res['reproduces_s40']}", flush=True)
    _record(res, PT, pred, keep, traded, started, inputs)
    res.pop("_trades").to_csv(OUT / "trades_valid.csv.gz", index=False)
    for form, tt in res.pop("_train_trades").items():
        tt.to_csv(OUT / f"trades_train_{form}.csv.gz", index=False)
    res_path.write_text(json.dumps(res, indent=1, default=str))
    write_report(res)
    print(f"\nML_SIDE: chose {res['chosen']['form']} -> {res['verdict']} failed {res['gates_failed']}")


def write_report(r: dict) -> None:
    v = r["valid"]
    f = (lambda x, k=5: "-" if x is None else f"{x:+.{k}f}")
    o = v.get("other_form_same_cell", {})
    L = ["# Section 40's range forecast armed per side (PLAN.md section 41)", "",
         "GENERATED by `src/ml_side.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}** (TRAIN chose {r['chosen']['form']}; failed: {r['gates_failed'] or 'none'})", "",
         f"- reproduces section 40 (pooled TRAIN rows): {r.get('reproduces_s40')}",
         f"- VALID {v['trades']} trades: weekly {f(v['weekly_mean'])}, 95% CI [{f(v['ci_lo'])}, {f(v['ci_hi'])}], "
         f"t {v['tstat']:+.2f}; mean R {f(v['mean_r'], 4)}; long {f(v['long_ret'], 4)} / short {f(v['short_ret'], 4)}; "
         f"max DD {v['max_dd']:.4f}",
         f"- cost x1.5 {f(v['stress_weekly_mean'])}; timing {f(v['timing'], 4)} vs shifted p95 {f(v['shift_p95'], 4)}; "
         f"breadth {len(v['breadth']['beat'])} of {v['breadth']['eligible']}; short share {v['short_share']}",
         f"- keep rate by side: {v.get('keep_rate')}",
         f"- the other arm form, same q and N (VALID): {o.get('form')} {o.get('trades')} trades, weekly "
         f"{f(o.get('weekly_mean'))}, CI [{f(o.get('ci_lo'))}, {f(o.get('ci_hi'))}], mean R {f(o.get('mean_r'), 4)}, "
         f"long {f(o.get('long_ret'), 4)} / short {f(o.get('short_ret'), 4)}, keep rate {o.get('keep_rate')}",
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
