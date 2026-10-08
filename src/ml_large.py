"""A model for the owner's ten large coins: trained wide, decided on 4h (PLAN.md section 37)

    python src/ml_large.py            # TRAIN/VALID, once (uses section 36's caches; no new download)
    python src/ml_large.py --final    # HOLDOUT once, only after PASS (shared with sections 31-36)

The owner's frame (2026-10-08): trade ONLY BNB, BTC, ETH, XRP, SOL, DOGE, ADA,
LINK, NEAR and BCH; train on any coin. Section 36's VALID trades on exactly
these coins made +0.0297 R per trade, +0.00069 a week (t +0.50) and their short
leg made nothing (_multi Exp 052): the 1h line's edge is crash-week shorts in
alt-coins, which large coins do not have. So section 37 changes what is
forecast, not only what is traded:

  * decided on 4h bars (1h and 1d closed-bar features as inputs), so a large
    coin's slower moves are the target and the 8-ATR stop is a 4h ATR (wider,
    cheaper in R);
  * one model per label horizon, averaged as in section 36: horizon set
    "1-3d" = (6, 12, 18) 4h bars or "2-6d" = (12, 24, 36);
  * trained wide: section 30's 47 coins' rows plus every crypto perp's rows in
    months it was a section 36 monthly top-50 member (members.json);
  * section 30's chosen 4h LightGBM setting, entry quantile and exit mode,
    refit monthly (walk-forward), 8-ATR protective stop, no clock;
  * agreement (switch): "off", or "1d" = a new 1d model (section 30's 1d
    setting, 24-bar label, trained wide) must agree with a NEW position's side;
  * account: confidence sizing up to 1% per trade, 5% cap per direction, costs
    and funding (section 31's cell otherwise).
A coin is traded from the first month it has been listed >= MIN_AGE_DAYS.
TRAIN (walk-forward 2021-22) picks 1 of 4 cells (horizon set x agreement) by
the weekly account t-statistic among cells with >= MIN_TRADES trades. VALID
(2023-24) judges the chosen cell once. Gates: section 31's, with breadth over
these coins (>= MIN_COINS with >= MIN_COIN_TRADES trades, half beating their own
shifted control) and >= MIN_TRADES VALID trades. Diagnostics: best-5-week share,
weekly mean without the best 5 weeks, per coin.
TRAIN trades of all four cells and the chosen cell's TRAIN checks are written too
(for src/analyzer.py). Holdout: sections 31-37 share ONE holdout.
Writes results/_multi/s37_ml_large_4h/ and the generated journal/_multi/s37_ml_large_4h.md.
"""
from __future__ import annotations

import argparse
import gc
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
import ml_flow as FL  # noqa: E402
import ml_hold as MH  # noqa: E402
import ml_mkt as MK  # noqa: E402
import ml_port as MP  # noqa: E402
import ml_wf as WF  # noqa: E402
import ml_wf2 as W2  # noqa: E402
import ml_wide as MW  # noqa: E402
import ml_xs as XS  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "s37_ml_large_4h"
REPORT = C.ROOT / "journal" / "_multi" / "s37_ml_large_4h.md"

# ---- pre-registered (PLAN.md section 37, _multi Exp 053)
COINS = ("BNBUSDT", "BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "NEARUSDT",
         "BCHUSDT")
TF_MAIN, TF_AGREE = 240, 1440
HORIZON_SETS = {"1-3d": (6, 12, 18), "2-6d": (12, 24, 36)}
AGREE = ("off", "1d")
SIZING, CAP = "conf", 0.05
MIN_AGE_DAYS = 365
MIN_TRADES, MIN_COIN_TRADES, MIN_COINS = 100, 10, 8
LOCKS = (MP.OUT, XS.OUT, MK.OUT, FL.OUT, MW.OUT)          # sections 31-36: one shared holdout


# --------------------------------------------------------------------------
# pure pieces (test 33)
# --------------------------------------------------------------------------
def traded_sets(first: dict[str, pd.Timestamp], months: list[str], coins=COINS,
                min_age: int = MIN_AGE_DAYS) -> dict[str, list[str]]:
    """Each month 'YYYY-MM': the coins first traded >= min_age days before the month."""
    out = {}
    for m in months:
        m0 = pd.Timestamp(m + "-01", tz="UTC")
        out[m] = [c for c in coins if c in first and first[c] <= m0 - pd.Timedelta(days=min_age)]
    return out


def cells() -> list[tuple[str, str]]:
    return [(h, a) for h in HORIZON_SETS for a in AGREE]


def cell_name(cell: tuple[str, str]) -> str:
    return f"{cell[0]}_{cell[1]}"


def per_horizon(P: dict, tf: int, cfg: dict, masks: dict, horizons, spans, step: int = 1) -> dict:
    """Walk-forward forecasts per horizon {h: {coin: array}}, each model trained only
    where masks[c] is True (section 36's forecasts() without the averaging)."""
    out = {}
    saved = WF.H_BARS
    try:
        for h in sorted(set(horizons)):
            Ph = {c: {**P[c], "y": pd.Series(np.where(masks[c], MW.label_h(P[c]["bars"], h), np.nan),
                                             index=P[c]["X"].index)} for c in P}
            WF.H_BARS = h
            pred = {c: np.full(len(P[c]["X"]), np.nan) for c in P}
            for a, b in spans:
                p = WF.walk_forward(Ph, tf, cfg, a, b, step=step)
                for c in P:
                    pred[c] = np.where(np.isfinite(p[c]), p[c], pred[c])
            out[h] = pred
            del Ph
            gc.collect()
    finally:
        WF.H_BARS = saved
    return out


def combine_set(P: dict, per_h: dict, horizons) -> dict[str, pd.Series]:
    """Section 36's ensemble (mean of pred_h x sqrt(24 / h)) for one horizon set."""
    return {c: pd.Series(MW.combine({h: per_h[h][c] for h in horizons}), index=P[c]["X"].index) for c in P}


# --------------------------------------------------------------------------
# the account
# --------------------------------------------------------------------------
def run_cell(P, pred, other, agree, a, b, traded, q, mode, tf=TF_MAIN, tf_agree=TF_AGREE, stress=1.0):
    fr, paths = [], {}
    for c in P:
        p = pred[c].reindex(P[c]["X"].index).to_numpy()
        ok = np.isfinite(p)
        des, ebar = np.full(len(p), np.nan), np.full(len(p), np.nan)
        if ok.any():
            ebar[ok] = MH.entry_bar(p[ok], q)
            des[ok] = MH.policy(p[ok], ebar[ok], mode)
        lo, hi, rows = MH._window(P, c, a, b)
        rows = rows[np.isfinite(des[rows])]
        if not len(rows):
            continue
        idx = P[c]["X"].index[rows]
        d = des[rows]
        if agree != "off":
            o = (other or {}).get(c)
            if o is None or o.empty:
                ov = np.full(len(rows), np.nan)
            else:
                pos = WF.asof_positions(idx, tf, o.index, tf_agree)
                ov = np.where(pos >= 0, o.to_numpy()[np.maximum(pos, 0)], np.nan)
            d = MP.agree_filter(d, ov)
        desired = MW.member_filter(d, MW.month_mask(idx, c, traded))
        if not np.any(desired != 0):
            continue
        tgt = np.full(hi - lo, np.nan)
        tgt[P[c]["pos"][rows] - lo] = desired
        tb = P[c].get("tbars", P[c]["bars"])
        t = MH.simulate(tb.iloc[lo:hi], tgt, P[c]["atr"][lo:hi], P[c]["fund"],
                        fee=C.FEE_TAKER * stress, slip=P[c]["slip"] * stress, stop_atr=WF.STOP_ATR)
        if len(t):
            k = P[c]["X"].index.get_indexer(t["entry_time"] - pd.Timedelta(minutes=tf))
            t["conf"] = np.where(k >= 0, np.abs(p[np.maximum(k, 0)]) / ebar[np.maximum(k, 0)], np.nan)
        fr.append(t.assign(coin=c))
        paths[c] = (desired, rows, lo, hi)
    t = pd.concat(fr, ignore_index=True) if fr else pd.DataFrame(
        columns=["entry_time", "exit_time", "side", "net_r", "conf", "coin"])
    return MP.size_trades(t, SIZING, CAP), paths


def judge(P, pred, other, agree, a, b, traded, q, mode, tf=TF_MAIN, tf_agree=TF_AGREE, min_coins=MIN_COINS):
    t, paths = run_cell(P, pred, other, agree, a, b, traded, q, mode, tf, tf_agree)
    acc = MP.account(t, a, b)
    acc["stress_weekly_mean"] = MP.account(run_cell(P, pred, other, agree, a, b, traded, q, mode, tf, tf_agree,
                                                    1.5)[0], a, b)["weekly_mean"]
    timing, per, pooled = MH.control({c: P[c] for c in paths}, paths)
    coins = {}
    for c in paths:
        tc = t[t["coin"] == c]
        coins[c] = {"trades": int(len(tc)), "mean_r": float(tc["net_r"].mean()) if len(tc) else None,
                    "timing": per[c]["timing"], "shift_median": MH._q(per[c]["shifts"], 50)}
    elig = {c: x for c, x in coins.items() if x["trades"] >= MIN_COIN_TRADES}
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
               neg_weeks=int((w < 0).sum()))
    return acc, t


def evaluate(P, preds: dict, other: dict | None, traded, q, mode, tf=TF_MAIN, tf_agree=TF_AGREE,
             min_coins=MIN_COINS, keep=False) -> dict:
    """preds: {horizon set: {coin: Series}}; other: the agreement forecasts."""
    a_tr, b_tr = WF.WINDOWS["train"]
    a_va, b_va = WF.WINDOWS["valid"]
    table, train_trades = [], {}
    for cell in cells():
        hs, ag = cell
        t, _ = run_cell(P, preds[hs], other, ag, a_tr, b_tr, traded, q, mode, tf, tf_agree)
        train_trades[cell_name(cell)] = t
        acc = MP.account(t, a_tr, b_tr)
        table.append({"form": cell_name(cell), "horizons": hs, "agree": ag,
                      **{k: acc[k] for k in ("trades", "weekly_mean", "tstat", "per_year", "max_dd", "mean_r",
                                             "long_ret", "short_ret")}})
        print(f"TRAIN-WF {cell_name(cell)}: {acc['trades']} trades, weekly {acc['weekly_mean']:+.5f}, "
              f"t {acc['tstat']:+.2f}", flush=True)
    ok = [x for x in table if x["trades"] >= MIN_TRADES]
    best = max(ok, key=lambda x: x["tstat"]) if ok else max(table, key=lambda x: x["tstat"])
    hs, ag = best["horizons"], best["agree"]
    tj, _ = judge(P, preds[hs], other, ag, a_tr, b_tr, traded, q, mode, tf, tf_agree, min_coins)
    train_checks = {k: tj[k] for k in ("trades", "weekly_mean", "ci_lo", "ci_hi", "tstat", "stress_weekly_mean",
                                       "timing", "shift_median", "shift_p95", "long_ret", "short_ret", "max_dd",
                                       "mean_r", "per_year_r", "top5_weeks_share")}
    train_checks["breadth"] = {k: tj["breadth"][k] for k in ("eligible", "share")}
    v, t = judge(P, preds[hs], other, ag, a_va, b_va, traded, q, mode, tf, tf_agree, min_coins)
    gates = {"train_weekly_mean>0": best["weekly_mean"] > 0 and best in ok,
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
    res = {"chosen": {"form": best["form"], "horizons": hs, "agree": ag, "sizing": SIZING, "cap": CAP},
           "train_table": table, "train_checks": train_checks, "valid": v,
           "verdict": "REJECT" if failed else "PASS", "gates_failed": failed,
           "model": {"q_in": q, "exit_mode": mode, "tf": tf, "horizon_sets": HORIZON_SETS, "coins": list(COINS)}}
    if keep:
        res["_trades"] = t
        res["_train_trades"] = train_trades
    return res


# --------------------------------------------------------------------------
def _first_traded() -> dict[str, pd.Timestamp]:
    d = MW._daily()
    d = d[(d["quote_volume"] > 0) & d["symbol"].isin(COINS)]
    return d.groupby("symbol")["date"].min().to_dict()


def _forecast_all(by_tf, core, members, spans):
    """4h forecasts per horizon set and the 1d agreement forecasts, for COINS (trained wide)."""
    P = W2.prepare(by_tf, TF_MAIN)
    masks = {c: MW.training_mask(P[c]["X"].index, c, core, members, True) for c in P}
    cfg = MP._cfg(TF_MAIN)
    per_h = per_horizon(P, TF_MAIN, cfg["setting"], masks, sorted({h for s in HORIZON_SETS.values() for h in s}),
                        spans)
    PT = {c: P[c] for c in COINS if c in P}
    preds = {k: combine_set(PT, per_h, hs) for k, hs in HORIZON_SETS.items()}
    del P, per_h
    gc.collect()
    P1 = W2.prepare(by_tf, TF_AGREE)
    m1 = {c: MW.training_mask(P1[c]["X"].index, c, core, members, True) for c in P1}
    o1 = MW.forecasts(P1, TF_AGREE, MP._cfg(TF_AGREE)["setting"], m1, (WF.H_BARS,), spans)
    other = {c: o1[c] for c in COINS if c in o1}
    del P1
    gc.collect()
    return PT, preds, other, cfg


def run(final: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    res_path, lock = OUT / "summary.json", OUT / "holdout.json"
    if final:
        res = json.loads(res_path.read_text()) if res_path.exists() else None
        if not res or res["verdict"] != "PASS":
            raise SystemExit("--final refused: needs a PASS from the TRAIN/VALID run")
        for o in (OUT,) + LOCKS:
            if (o / "holdout.json").exists():
                raise SystemExit(f"--final refused: sections 31-37 share one holdout and {o.name} used it")
    elif res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    if not (MW.OUT / "members.json").exists():
        raise SystemExit("no section 36 member sets: run  python src/ml_wide.py --build  first")
    months = [str(p) for p in pd.period_range("2020-01", C.DATA_END, freq="M")]
    traded = traded_sets(_first_traded(), months)
    by_tf, core, members, _ = MW.load_wide()
    miss = [c for c in COINS if c not in by_tf[TF_MAIN]]
    if miss:
        raise SystemExit(f"no cached bars for {miss}: run  python src/ml_wide.py --build  first")
    spans = [WF.WINDOWS["train"], WF.WINDOWS["valid"]] + ([WF.WINDOWS["holdout"]] if final else [])
    print(f"[ml_large] training coins {len(by_tf[TF_MAIN])}; traded {len(COINS)}", flush=True)
    P, preds, other, cfg = _forecast_all(by_tf, core, members, spans)
    del by_tf
    gc.collect()
    q, mode = cfg["q_in"], cfg["exit_mode"]
    if final:
        a, b = WF.WINDOWS["holdout"]
        ch = res["chosen"]
        h, t = judge(P, preds[ch["horizons"]], other, ch["agree"], a, b, traded, q, mode)
        h["verdict"] = ("CONFIRMED" if h["weekly_mean"] > 0 and h["ci_lo"] > 0 and h["shift_median"] is not None
                        and h["timing"] is not None and h["timing"] > h["shift_median"]
                        and h["breadth"]["share"] >= MP.BREADTH_SHARE else "FAILED")
        lock.write_text(json.dumps(h, indent=1, default=str))
        t.to_csv(OUT / "trades_holdout.csv.gz", index=False)
        write_report(res)
        print(json.dumps({k: h.get(k) for k in ("trades", "weekly_mean", "ci_lo", "verdict")}, indent=1))
        return
    res = evaluate(P, preds, other, traded, q, mode, keep=True)
    res["traded_from"] = {c: next((m for m in months if c in traded[m]), None) for c in COINS}
    res.pop("_trades").to_csv(OUT / "trades_valid.csv.gz", index=False)
    for form, tt in res.pop("_train_trades").items():
        tt.to_csv(OUT / f"trades_train_{form}.csv.gz", index=False)
    res_path.write_text(json.dumps(res, indent=1, default=str))
    write_report(res)
    print(f"\nML_LARGE: chose {res['chosen']} -> {res['verdict']} failed {res['gates_failed']}")


def write_report(r: dict) -> None:
    v = r["valid"]
    f = (lambda x, k=5: "-" if x is None else f"{x:+.{k}f}")
    L = ["# A model for the ten large coins: trained wide, decided on 4h (PLAN.md section 37)", "",
         "GENERATED by `src/ml_large.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}** (TRAIN chose {r['chosen']}; failed: {r['gates_failed'] or 'none'})", "",
         f"- coins: {', '.join(c.replace('USDT', '') for c in r['model']['coins'])}; traded from "
         f"{ {c.replace('USDT', ''): m for c, m in r.get('traded_from', {}).items()} }",
         f"- VALID {v['trades']} trades over {v['weeks']} weeks: weekly account return {f(v['weekly_mean'])}, "
         f"95% CI [{f(v['ci_lo'])}, {f(v['ci_hi'])}], t {v['tstat']:+.2f}; return per year {f(v['per_year'], 4)}, "
         f"max drawdown {v['max_dd']:.4f}",
         f"- mean R per trade {f(v['mean_r'], 4)}; long {f(v['long_ret'], 4)} / short {f(v['short_ret'], 4)} "
         f"(summed return); cost x1.5 weekly {f(v['stress_weekly_mean'])}",
         f"- timing {f(v['timing'], 4)} vs shifted median {f(v['shift_median'], 4)} / p95 {f(v['shift_p95'], 4)}; "
         f"breadth {len(v['breadth']['beat'])} of {v['breadth']['eligible']} ({v['breadth']['share']:.2f}); "
         f"per year {v['per_year_r']}",
         f"- best 5 weeks = {f(v['top5_weeks_share'], 3)} of the total; weekly mean without them "
         f"{f(v['weekly_mean_without_top5'])}; negative weeks {v['neg_weeks']} of {v['weeks']}", "",
         "| cell | TRAIN trades | weekly mean | t | per year | max DD | mean R | long | short |",
         "|---|---|---|---|---|---|---|---|---|"]
    for x in r["train_table"]:
        L.append(f"| {x['form']} | {x['trades']} | {f(x['weekly_mean'])} | {x['tstat']:+.2f} | {f(x['per_year'], 4)} | "
                 f"{x['max_dd']:.4f} | {f(x['mean_r'], 4)} | {f(x['long_ret'], 4)} | {f(x['short_ret'], 4)} |")
    L += ["", "| coin | VALID trades | mean R | timing | shifted median |", "|---|---|---|---|---|"]
    for c, x in sorted(v["per_coin"].items()):
        L.append(f"| {c.replace('USDT', '')} | {x['trades']} | {f(x['mean_r'], 4)} | {f(x['timing'], 4)} | "
                 f"{f(x['shift_median'], 4)} |")
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
