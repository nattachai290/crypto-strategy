"""Meta-labeling: an ML model learns which breakouts follow through (PLAN.md section 44)

    python src/ml_meta.py            # TRAIN/VALID, once (uses section 36's caches; no new download)
    python src/ml_meta.py --final    # HOLDOUT once, only after PASS (shared with sections 31-43)

Why (_multi Exp 079-081):
- Section 43 takes section 41's armed breakouts only where section 38's direction model agrees. On VALID the
  agreement replicated on longs (+0.103 vs -0.007 R) but not on shorts.
- Section 41/43's losses are mostly breakouts that fail within a day: trades under one day average -0.18 R and win
  7% of the time (owner's question, 2026-10-09).
- The direction model answers a broad question (where is price in 1-3 days?), not the one the book asks
  (does THIS breakout follow through?).
- Recombining section 38's 1h/4h/1d models did not help (Exp 081).
The owner chose meta-labeling (2026-10-10).

Hypothesis: a model trained directly on breakout events - "given this breakout and the market state, how far does
it run before the exit channel closes it?" - separates follow-throughs from false breaks better than a general
direction forecast. It learns from every breakout of every wide-training coin (section 36's members), not only
the ten traded coins.

Meta label (event bars only; every other row is NaN): a breakout at bar k is close[k] beyond the previous
N = 6 bars' extreme, with side s = +1 / -1. The trade is entered at open[k+1] and exits at open[j+1], where j is
the first bar in k+1..k+L whose close crosses the previous N/2 bars' opposite extreme (section 41's exit). If no
bar does, the exit is open[k+1+L], with L = 18 bars (3 days). The label is
    y = s * log(exit / entry) / ATR fraction at k.
It is NaN unless every bar from k+1 to the exit traded. The walk-forward lag is L + 1 bars, so no label overlaps
its refit month.

Features: section 30's 4h features plus `bo_side` (+1 / -1 at an up / down breakout, 0 otherwise). The model
setting is section 30's 4h setting, and refits are monthly and expanding.

Unchanged from section 41:
- the range forecasts;
- the arm (side / q70 / N = 6);
- the chan exit, the 8-ATR stop, no clock;
- section 31's account.

Forms (an armed breakout is taken only if ...):
  none     always (= section 41, `reproduces_s41`)
  agree    section 38's direction forecast agrees (= section 43, `reproduces_s43`)
  meta0    the meta forecast at that breakout is > 0
  metaq50  the meta forecast is above the median of the meta forecasts at the coin's last 60 same-side
           breakouts (the bar included, at least 20)

TRAIN picks by section 38's rule. These are REJECT:
- `none` or `agree` chosen (`train_chose_meta`);
- a meta form whose TRAIN t beats the better of none/agree by less than +0.5 (`train_margin>=0.5`).

VALID gates: section 41's. Reported:
- none and agree on VALID;
- the meta forecast vs label Spearman at events, by split and side;
- the kept share per side.

Holdout: sections 31-44 share ONE holdout.
Writes results/_multi/s44_ml_meta_4h/ and journal/_multi/s44_ml_meta_4h.md.
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
import ml_port as MP  # noqa: E402
import ml_recent as MR  # noqa: E402
import ml_side as MS  # noqa: E402
import ml_vol as MV  # noqa: E402
import ml_wf as WF  # noqa: E402
import ml_wf2 as W2  # noqa: E402
import ml_wide as MW  # noqa: E402
import run_record as RR  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "s44_ml_meta_4h"
REPORT = C.ROOT / "journal" / "_multi" / "s44_ml_meta_4h.md"

# ---- pre-registered (PLAN.md section 44, _multi Exp 082)
TF = MV.TF
ARM = MX.ARM                                      # ("side", "q70", 6): section 41's TRAIN choice, frozen
N_BO = ARM[2]
L_META = 18                                       # label cap: 3 days of 4h bars
FORMS = ("none", "agree", "meta0", "metaq50")
SIDE_ROLL, SIDE_MIN = MS.SIDE_ROLL, MS.SIDE_MIN
MIN_MARGIN = MA.MIN_MARGIN
MIN_TRADES = ML.MIN_TRADES
LOCKS = MA.LOCKS + (MA.OUT,)                      # sections 31-43: one shared holdout


# --------------------------------------------------------------------------
# pure pieces (test 42)
# --------------------------------------------------------------------------
def bo_side(bars: pd.DataFrame, n: int = N_BO) -> np.ndarray:
    """+1 where close breaks above the previous n bars' high, -1 below their low, else 0 (aligned with X)."""
    hh, ll, _, _ = MV.channels(bars, n)
    c = bars["close"].to_numpy(float)
    with np.errstate(invalid="ignore"):
        s = np.where(c > hh, 1.0, np.where(c < ll, -1.0, 0.0))
    return s[:-1]


def meta_label(bars: pd.DataFrame, n: int = N_BO, cap: int = L_META) -> np.ndarray:
    """Signed log move of a breakout entered at open[k+1] and closed at open[j+1] (first close beyond the
    previous n//2 bars' opposite extreme in k+1..k+cap) or open[k+1+cap], over the ATR fraction at k.
    NaN at non-breakout rows and wherever a bar from k+1 to the exit did not trade. Aligned with X."""
    live = bars["volume"].to_numpy(float) > 0
    atr = ta.atr_(bars["high"], bars["low"], bars["close"], MH.ATR_N)
    close = bars["close"].to_numpy(float)
    afrac = (atr / bars["close"]).to_numpy(float)
    afrac = np.where(live & np.isfinite(afrac) & (afrac >= WF.AFRAC_MIN), afrac, np.nan)
    o = bars["open"].to_numpy(float)
    hh, ll, xh, xl = MV.channels(bars, n)
    m = len(o)
    s = np.r_[bo_side(bars, n), 0.0]
    y = np.full(m, np.nan)
    dead = np.r_[0, np.cumsum(~live)]
    for k in np.flatnonzero(s != 0):
        if k + 2 + cap > m or not np.isfinite(afrac[k]):
            continue
        j = np.arange(k + 1, k + 1 + cap)
        hit = (close[j] < xl[j]) if s[k] > 0 else (close[j] > xh[j])
        with np.errstate(invalid="ignore"):
            first = int(np.argmax(hit)) if hit.any() else cap
        xi = k + 1 + first + (1 if first < cap else 0)          # exit at open[j+1], or open[k+1+cap]
        if dead[xi + 1] - dead[k + 1] != 0:
            continue
        y[k] = s[k] * np.log(o[xi] / o[k + 1]) / afrac[k]
    return y[:-1]


def side_median_arm(mp: np.ndarray, event: np.ndarray) -> np.ndarray:
    """True where the meta forecast exceeds the median of the meta forecasts at the last SIDE_ROLL events of
    that side (the bar included, at least SIDE_MIN); causal."""
    mp = np.asarray(mp, float)
    ev = np.flatnonzero(np.asarray(event, bool) & np.isfinite(mp))
    thr = np.full(len(mp), np.nan)
    if len(ev):
        thr[ev] = pd.Series(mp[ev]).rolling(SIDE_ROLL, min_periods=SIDE_MIN).median().to_numpy()
        thr = pd.Series(thr).ffill().to_numpy()
    with np.errstate(invalid="ignore"):
        return np.isfinite(thr) & np.isfinite(mp) & (mp > thr)


def gate(au, ad, form, d=None, mp=None, up_ev=None, dn_ev=None):
    """Section 41's arms kept by form."""
    if form == "none":
        return au, ad
    if form == "agree":
        return MA.agree_arms(au, ad, d, "sign")
    mp = np.asarray(mp, float)
    if form == "meta0":
        with np.errstate(invalid="ignore"):
            ok = np.isfinite(mp) & (mp > 0)
        return au & ok, ad & ok
    if form == "metaq50":
        return au & side_median_arm(mp, up_ev), ad & side_median_arm(mp, dn_ev)
    raise ValueError(form)


# --------------------------------------------------------------------------
def run_cell(P, pred, dirp, metp, form, a, b, traded, stress=1.0, keep_skipped=False):
    arm_form, q, n = ARM
    fr, paths, skipped = [], {}, []
    for c in P:
        idx_all = P[c]["X"].index
        p = pred[c].reindex(idx_all).to_numpy()
        d = dirp[c].reindex(idx_all).to_numpy()
        mp = metp[c].reindex(idx_all).to_numpy()
        tb = P[c].get("tbars", P[c]["bars"])
        hh, ll, xh, xl = MV.channels(tb, n)
        kall = P[c]["pos"]
        close_all = tb["close"].to_numpy(float)[kall]
        au, ad, ru, rd = MS.arms(p, close_all, hh[kall], ll[kall], arm_form, q)
        with np.errstate(invalid="ignore"):
            up_ev, dn_ev = close_all > hh[kall], close_all < ll[kall]
        bu, bd = gate(au, ad, form, d, mp, up_ev, dn_ev)
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
            lab = MW.label_h(P[c]["bars"], MV.H_VOL)[rows]
            skipped.append(RR.skipped(idx, c, ref, desired, f"filtered by {form}", lab))
        if not np.any(desired != 0):
            continue
        tgt = np.full(hi - lo, np.nan)
        tgt[k - lo] = desired
        t = MH.simulate(tb.iloc[lo:hi], tgt, P[c]["atr"][lo:hi], P[c]["fund"],
                        fee=C.FEE_TAKER * stress, slip=P[c]["slip"] * stress, stop_atr=WF.STOP_ATR)
        if len(t):
            kk = idx_all.get_indexer(t["entry_time"] - pd.Timedelta(minutes=TF))
            kk0 = np.maximum(kk, 0)
            t["conf"] = np.where(kk >= 0, np.where(t["side"].to_numpy() > 0, ru[kk0], rd[kk0]), np.nan)
            t["dir_fc"] = np.where(kk >= 0, d[kk0], np.nan)
            t["meta_fc"] = np.where(kk >= 0, mp[kk0], np.nan)
        fr.append(t.assign(coin=c))
        paths[c] = (desired, rows, lo, hi)
    t = pd.concat(fr, ignore_index=True) if fr else pd.DataFrame(
        columns=["entry_time", "exit_time", "side", "net_r", "conf", "coin"])
    out = MP.size_trades(t, ML.SIZING, ML.CAP), paths
    return (*out, pd.concat(skipped, ignore_index=True) if skipped else None) if keep_skipped else out


def judge(P, pred, dirp, metp, form, a, b, traded, min_coins=ML.MIN_COINS):
    t, paths = run_cell(P, pred, dirp, metp, form, a, b, traded)
    acc = MP.account(t, a, b)
    acc["stress_weekly_mean"] = MP.account(run_cell(P, pred, dirp, metp, form, a, b, traded, 1.5)[0],
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
               side_mean_r={("long" if s > 0 else "short"): float(g["net_r"].mean()) for s, g in t.groupby("side")})
    return acc, t


def meta_ic(P, metp, a, b) -> dict:
    """Spearman of the meta forecast vs the meta label at breakout events in [a, b), all and by side."""
    xs, ys, ss = [], [], []
    lo, hi = pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")
    for c in P:
        idx = P[c]["X"].index
        w = (idx >= lo) & (idx < hi)
        y = meta_label(P[c]["bars"])[w]
        s = bo_side(P[c]["bars"])[w]
        x = metp[c].reindex(idx).to_numpy()[w]
        ok = np.isfinite(x) & np.isfinite(y)
        xs.append(x[ok]), ys.append(y[ok]), ss.append(s[ok])
    x, y, s = np.concatenate(xs), np.concatenate(ys), np.concatenate(ss)
    sp = (lambda u, v: float(pd.Series(u).rank().corr(pd.Series(v).rank())) if len(u) > 10 else None)
    return {"all": sp(x, y), "long": sp(x[s > 0], y[s > 0]), "short": sp(x[s < 0], y[s < 0]), "events": int(len(x))}


def evaluate(P, pred, dirp, metp, traded, min_coins=ML.MIN_COINS, keep=False) -> dict:
    a_tr, b_tr = WF.WINDOWS["train"]
    a_va, b_va = WF.WINDOWS["valid"]
    table, train_trades = [], {}
    for form in FORMS:
        t, _ = run_cell(P, pred, dirp, metp, form, a_tr, b_tr, traded)
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
    t_of = {x["form"]: x["tstat"] for x in table}
    t_old = max(t_of["none"], t_of["agree"])
    margin = max(t_of["meta0"], t_of["metaq50"]) - t_old
    tj, _ = judge(P, pred, dirp, metp, form, a_tr, b_tr, traded, min_coins)
    train_checks = {k: tj[k] for k in ("trades", "weekly_mean", "ci_lo", "ci_hi", "tstat", "stress_weekly_mean",
                                       "timing", "shift_median", "shift_p95", "long_ret", "short_ret", "max_dd",
                                       "mean_r", "per_year_r", "top5_weeks_share", "hold", "side_mean_r")}
    train_checks["breadth"] = {k: tj["breadth"][k] for k in ("eligible", "share")}
    v, t = judge(P, pred, dirp, metp, form, a_va, b_va, traded, min_coins)
    v["other_forms"] = {}
    nt = None
    for f in FORMS:
        if f == form:
            continue
        ov, ot = judge(P, pred, dirp, metp, f, a_va, b_va, traded, min_coins)
        if f == "none":
            nt = ot
        v["other_forms"][f] = {k: ov[k] for k in ("trades", "weekly_mean", "ci_lo", "ci_hi", "tstat", "mean_r",
                                                  "long_ret", "short_ret", "max_dd", "short_share", "side_mean_r")}
    if nt is not None:
        v["kept_share"] = {s: float(((t["side"] > 0) if s == "long" else (t["side"] < 0)).sum()
                                    / max(1, ((nt["side"] > 0) if s == "long" else (nt["side"] < 0)).sum()))
                           for s in ("long", "short")}
    v["meta_ic"] = {"train": meta_ic(P, metp, a_tr, b_tr), "valid": meta_ic(P, metp, a_va, b_va)}
    gates = {"train_cell_selectable": bool(ok),
             "train_chose_meta": form in ("meta0", "metaq50"),
             f"train_margin>={MIN_MARGIN}": form in ("meta0", "metaq50") and t_of[form] - t_old >= MIN_MARGIN,
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
           "train_table": table, "train_margin": margin, "train_checks": train_checks, "valid": v,
           "verdict": "REJECT" if failed else "PASS", "gates_failed": failed,
           "model": {"tf": TF, "meta_label": f"breakout N={N_BO}, chan exit N/2, cap {L_META} bars, signed log move / ATR",
                     "features": "section 30's 4h features + bo_side", "coins": list(ML.COINS), "arm": list(ARM),
                     "forms": list(FORMS), "min_margin": MIN_MARGIN}}
    if keep:
        res["_trades"] = t
        res["_train_trades"] = train_trades
    return res


# --------------------------------------------------------------------------
def meta_forecasts(P, cfg, masks, spans, keep=None, step: int = 1) -> dict:
    """Walk-forward meta forecasts. Adds the `bo_side` column to every P[c]["X"] in place (call this after
    every other forecast that reads P's columns)."""
    for c in P:
        P[c]["X"]["bo_side"] = bo_side(P[c]["bars"])
    Ph = {c: {**P[c], "y": pd.Series(np.where(masks[c], meta_label(P[c]["bars"]), np.nan), index=P[c]["X"].index)}
          for c in P}
    saved = WF.H_BARS
    WF.H_BARS = L_META + 1
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


def _record(res, P, pred, dirp, metp, keep, traded, started, inputs) -> None:
    feats = MH._cols(P)
    form = res["chosen"]["form"]
    lab = {c: meta_label(P[c]["bars"]) for c in P}
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
                               {c: np.where(np.isfinite(lab[c]), metp[c].reindex(P[c]["X"].index).to_numpy(), np.nan)
                                for c in P}, lab, a, b)
        _, _, sk = run_cell(P, pred, dirp, metp, form, a, b, traded, keep_skipped=True)
        logs = [r for r in keep["log"] if lo <= pd.Timestamp(r["month"], tz="UTC") < hi]
        ylab = pd.concat([pd.Series(lab[c][(P[c]["X"].index >= lo) & (P[c]["X"].index < hi)]) for c in P],
                         ignore_index=True)
        meta = RR.metadata(feats, list(P), logs, dict(ME.LGB_PARAMS, **MP._cfg(TF)["setting"]),
                           f"meta label: breakout N={N_BO}, chan exit, cap {L_META} bars, signed log move / ATR",
                           (L_META,), {"split": [a, b], "cell": form}, ylab)
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
                raise SystemExit(f"--final refused: sections 31-44 share one holdout and {o.name} used it")
    elif res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    if not (MW.OUT / "members.json").exists():
        raise SystemExit("no section 36 member sets: run  python src/ml_wide.py --build  first")
    months, traded, by_tf, core, members = MR._load()
    inputs = [WF.cache_dir(TF) / f"{c}.parquet" for c in sorted(by_tf[TF])]
    spans = [WF.WINDOWS["train"], WF.WINDOWS["valid"]] + ([WF.WINDOWS["holdout"]] if final else [])
    print(f"[ml_meta] training coins {len(by_tf[TF])}; traded {len(ML.COINS)}", flush=True)
    P = W2.prepare(by_tf, TF)
    del by_tf
    gc.collect()
    masks = {c: MW.training_mask(P[c]["X"].index, c, core, members, True) for c in P}
    setting = MP._cfg(TF)["setting"]
    pred_all = MV.forecasts(P, setting, masks, spans)
    print("[ml_meta] 1/3 range forecasts done", flush=True)
    per_h = MR.forecasts_w(P, TF, setting, masks, spans, MA.DIR_SCHEME)
    PT = {c: P[c] for c in ML.COINS if c in P}
    dirp = ML.combine_set(PT, per_h, MR.horizons(TF))
    del per_h
    gc.collect()
    print("[ml_meta] 2/3 direction forecasts done; meta model next", flush=True)
    keep = {}
    met_all = meta_forecasts(P, setting, masks, spans, keep=keep)       # adds bo_side to X: must run last
    pred = {c: pred_all[c] for c in PT}
    metp = {c: met_all[c] for c in PT}
    if final:
        a, b = WF.WINDOWS["holdout"]
        h, t = judge(PT, pred, dirp, metp, res["chosen"]["form"], a, b, traded)
        h["verdict"] = ("CONFIRMED" if h["weekly_mean"] > 0 and h["ci_lo"] > 0 and h["shift_median"] is not None
                        and h["timing"] is not None and h["timing"] > h["shift_median"]
                        and h["breadth"]["share"] >= MP.BREADTH_SHARE else "FAILED")
        lock.write_text(json.dumps(h, indent=1, default=str))
        t.to_csv(OUT / "trades_holdout.csv.gz", index=False)
        write_report(res)
        print(json.dumps({k: h.get(k) for k in ("trades", "weekly_mean", "ci_lo", "verdict")}, indent=1))
        return
    res = evaluate(PT, pred, dirp, metp, traded, keep=True)
    res["traded_from"] = {c: next((m for m in months if c in traded[m]), None) for c in ML.COINS}
    tab = {x["form"]: (x["trades"], round(x["tstat"], 6)) for x in res["train_table"]}
    for key, path, ref_form, my_form in (("reproduces_s41", MS.OUT, MS.cell_name(ARM), "none"),
                                         ("reproduces_s43", MA.OUT, "sign", "agree")):
        s = path / "summary.json"
        if s.exists():
            ref = {x["form"]: (x["trades"], round(x["tstat"], 6)) for x in json.loads(s.read_text())["train_table"]}
            res[key] = ref.get(ref_form) == tab[my_form]
    print(f"reproduces section 41: {res.get('reproduces_s41')}; section 43: {res.get('reproduces_s43')}", flush=True)
    _record(res, PT, pred, dirp, metp, keep, traded, started, inputs)
    res.pop("_trades").to_csv(OUT / "trades_valid.csv.gz", index=False)
    for form, tt in res.pop("_train_trades").items():
        tt.to_csv(OUT / f"trades_train_{form}.csv.gz", index=False)
    res_path.write_text(json.dumps(res, indent=1, default=str))
    write_report(res)
    print(f"\nML_META: chose {res['chosen']['form']} -> {res['verdict']} failed {res['gates_failed']}")


def write_report(r: dict) -> None:
    v = r["valid"]
    f = (lambda x, k=5: "-" if x is None else f"{x:+.{k}f}")
    L = ["# Meta-labeling: an ML model learns which breakouts follow through (PLAN.md section 44)", "",
         "GENERATED by `src/ml_meta.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}** (TRAIN chose {r['chosen']['form']}; failed: {r['gates_failed'] or 'none'})", "",
         f"- reproduces section 41: {r.get('reproduces_s41')}; section 43: {r.get('reproduces_s43')}; "
         f"TRAIN t margin (best meta - best of none/agree): {f(r.get('train_margin'), 2)}",
         f"- meta forecast vs label Spearman at breakouts: {v.get('meta_ic')}",
         f"- VALID {v['trades']} trades: weekly {f(v['weekly_mean'])}, 95% CI [{f(v['ci_lo'])}, {f(v['ci_hi'])}], "
         f"t {v['tstat']:+.2f}; mean R {f(v['mean_r'], 4)}; long {f(v['long_ret'], 4)} / short {f(v['short_ret'], 4)}; "
         f"per-trade by side {v.get('side_mean_r')}; max DD {v['max_dd']:.4f}",
         f"- cost x1.5 {f(v['stress_weekly_mean'])}; timing {f(v['timing'], 4)} vs shifted p95 {f(v['shift_p95'], 4)}; "
         f"breadth {len(v['breadth']['beat'])} of {v['breadth']['eligible']}; short share {v['short_share']}; "
         f"kept share vs none {v.get('kept_share')}",
         f"- best 5 weeks = {f(v['top5_weeks_share'], 3)} of the total; weekly mean without them "
         f"{f(v['weekly_mean_without_top5'])}", "",
         "Other forms on VALID:", ""]
    for k, o in v.get("other_forms", {}).items():
        L.append(f"- {k}: {o['trades']} trades, weekly {f(o['weekly_mean'])}, CI [{f(o['ci_lo'])}, {f(o['ci_hi'])}], "
                 f"mean R {f(o['mean_r'], 4)}, by side {o.get('side_mean_r')}, max DD {o['max_dd']:.4f}")
    L += ["", "| form | TRAIN trades | weekly mean | t | mean R | long | short | by year | short share | selectable |",
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
