"""Train wide, trade the top 20: more training data and a horizon ensemble for the 1h model (PLAN.md section 36)

    python src/ml_wide.py --build   # 1h/4h/1d perp klines + funding of every coin that was a monthly top-50
    python src/ml_wide.py           # TRAIN/VALID, once
    python src/ml_wide.py --final   # HOLDOUT once, only after PASS (shared with sections 31-34)

Sections 31-34 (_multi Exp 033-043) left the frozen section 31 cell as the best
book: weekly mean +0.00548, CI lower bound -0.00026. Its forecast is weak (IC
about +0.02) and was learned from 47 coins only. The owner will trade only the
large coins (top 20), so the improvement has to come from a better forecast,
not from more traded coins.

Hypothesis: the 1h model learns more, and forecasts more steadily, when it is
trained on (a) every coin that was among the 50 most traded perps at the time,
not only the 47 chosen in 2020-22 (later large coins, sell-offs, new regimes),
and (b) three label horizons (12, 24, 48 bars) whose forecasts are averaged.

Everything else is fixed (an ablation against section 31 on the same coins):
  * traded coins: the top TRADE_N of section 28's universe by 2020-22 volume
    (universe_v2.json order), the only coins that ever get a position;
  * training rows: all of section 30's rows for its 47 coins (spot history
    included), PLUS each other coin's rows only in months when it was in the
    top TRAIN_TOP perps by mean quote volume over the 30 days before the month
    (causal; zero-volume days excluded; delisted coins included). Other coins
    use their perp bars only;
  * the model: section 30's chosen 1h setting, refit every month, one model per
    horizon h in HORIZONS (label = log return over h bars in ATRs, the walk-forward
    lag = h + 1 bars); the forecast is the mean of pred_h x sqrt(24 / h);
  * the account: section 31's chosen cell (4h agreement with section 30's frozen
    4h forecasts, confidence sizing, 5% cap), its policy, stop, costs, gates.
TRAIN (2021-22) compares "base" (section 30's frozen 1h forecasts on the same
TRADE_N coins) with "wide" by the weekly account t-statistic; a "base" choice is
REJECT (gate train_chose_wide). VALID gates: section 31's (breadth over the
TRADE_N coins, MIN_COINS = 10). Diagnostic: the correlation of each forecast with
the 24-bar label on the traded coins' VALID rows (base vs wide).
Holdout: sections 31-36 share ONE holdout (the same model line).
Writes results/_multi/ml_wide/ and the generated journal/_multi/ml_wide.md.
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
import indicators as ta  # noqa: E402
import ml_flow as FL  # noqa: E402
import ml_hold as MH  # noqa: E402
import ml_mkt as MK  # noqa: E402
import ml_port as MP  # noqa: E402
import ml_wf as WF  # noqa: E402
import ml_wf2 as W2  # noqa: E402
import ml_wf3 as W3  # noqa: E402
import ml_xs as XS  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "ml_wide"
REPORT = C.ROOT / "journal" / "_multi" / "ml_wide.md"

# ---- pre-registered (PLAN.md section 36)
TRADE_N = 20
TRAIN_TOP = 50
VOL_DAYS, VOL_MIN_DAYS = 30, 20
MEMBERS_FROM = "2019-10"
HORIZONS = (12, 24, 48)
CELL = FL.CELL


# --------------------------------------------------------------------------
# pure pieces (test 32)
# --------------------------------------------------------------------------
def monthly_members(daily: pd.DataFrame, months: list[str], top: int = TRAIN_TOP) -> dict[str, list[str]]:
    """For each month 'YYYY-MM', the `top` instruments by mean quote volume over
    the VOL_DAYS days before the month starts (at least VOL_MIN_DAYS traded days).
    daily: columns inst, date (UTC), quote_volume; zero-volume rows are not trading."""
    d = daily[daily["quote_volume"] > 0]
    out = {}
    for m in months:
        m0 = pd.Timestamp(m + "-01", tz="UTC")
        w = d[(d["date"] >= m0 - pd.Timedelta(days=VOL_DAYS)) & (d["date"] < m0)]
        g = w.groupby("inst")["quote_volume"].agg(["mean", "size"])
        g = g[g["size"] >= VOL_MIN_DAYS].sort_values("mean", ascending=False)
        out[m] = list(g.index[:top])
    return out


def label_h(bars: pd.DataFrame, h: int) -> np.ndarray:
    """ml_wf.prepare's label with horizon h: log(open[i+1+h] / open[i+1]) / ATR
    fraction at i, NaN unless every label bar traded and bar i is tradable.
    `bars` are the bars prepare used (its dead tail already cut); the result is
    aligned with prepare's X (all rows but the last)."""
    live = bars["volume"].to_numpy(float) > 0
    atr = ta.atr_(bars["high"], bars["low"], bars["close"], MH.ATR_N)
    afrac = (atr / bars["close"]).to_numpy(float)
    good = live & np.isfinite(afrac) & (afrac >= WF.AFRAC_MIN)
    afrac = np.where(good, afrac, np.nan)
    o = bars["open"].to_numpy(float)
    n = len(o)
    dead = np.r_[0, np.cumsum(~live)]
    i = np.arange(n)
    hi = np.minimum(i + 2 + h, n)
    clean = (i + 1 + h < n) & (dead[hi] - dead[np.minimum(i + 1, n)] == 0)
    nxt = np.r_[o[1:], np.nan]
    fut = np.r_[o[1 + h:], np.full(min(1 + h, n), np.nan)][:n]
    with np.errstate(divide="ignore", invalid="ignore"):
        y = np.where(clean, np.log(fut / nxt) / afrac, np.nan)
    return y[:-1]


def training_mask(idx: pd.DatetimeIndex, coin: str, core: set, members: dict[str, list[str]]) -> np.ndarray:
    """True where a row may train the model: every row of a core coin (section 30's
    47), and another coin's rows only in months when it was a member."""
    if coin in core:
        return np.ones(len(idx), bool)
    mem = {m for m, lst in members.items() if coin in lst}
    return np.asarray(idx.strftime("%Y-%m").isin(list(mem)) if len(idx) else np.zeros(0, bool), bool)


def combine(preds: dict[int, np.ndarray]) -> np.ndarray:
    """Mean of the horizon forecasts on the 24-bar scale (pred_h x sqrt(24 / h));
    NaN unless every horizon has a forecast."""
    st = np.vstack([preds[h] * np.sqrt(24.0 / h) for h in sorted(preds)])
    return np.where(np.isfinite(st).all(axis=0), st.mean(axis=0), np.nan)


def wide_forecasts(P: dict, members: dict, core: set, spans, horizons=HORIZONS, step: int = 1) -> dict[str, pd.Series]:
    """Walk-forward forecasts of the wide ensemble for every coin in P."""
    cfg = MP._cfg(MP.TF_MAIN)["setting"]
    masks = {c: training_mask(P[c]["X"].index, c, core, members) for c in P}
    per_h = {}
    saved = WF.H_BARS
    try:
        for h in horizons:
            Ph = {}
            for c in P:
                y = label_h(P[c]["bars"], h)
                Ph[c] = {**P[c], "y": pd.Series(np.where(masks[c], y, np.nan), index=P[c]["X"].index)}
            WF.H_BARS = h                                  # the walk-forward lag is h + 1 bars
            pred = {c: np.full(len(P[c]["X"]), np.nan) for c in P}
            for a, b in spans:
                p = WF.walk_forward(Ph, MP.TF_MAIN, cfg, a, b, step=step)
                for c in P:
                    pred[c] = np.where(np.isfinite(p[c]), p[c], pred[c])
            per_h[h] = pred
            del Ph
            gc.collect()
    finally:
        WF.H_BARS = saved
    return {c: pd.Series(combine({h: per_h[h][c] for h in horizons}), index=P[c]["X"].index) for c in P}


def forecast_corr(P: dict, pred: dict, a: str, b: str) -> float | None:
    """Pooled correlation of a forecast with the 24-bar label on [a, b) rows."""
    xs, ys = [], []
    for c in P:
        idx = P[c]["X"].index
        w = (idx >= pd.Timestamp(a, tz="UTC")) & (idx < pd.Timestamp(b, tz="UTC"))
        p = pred[c].reindex(idx).to_numpy()[w]
        y = P[c]["y"].to_numpy()[w]
        ok = np.isfinite(p) & np.isfinite(y)
        xs.append(p[ok])
        ys.append(y[ok])
    x, y = np.concatenate(xs) if xs else np.zeros(0), np.concatenate(ys) if ys else np.zeros(0)
    return float(np.corrcoef(x, y)[0, 1]) if len(x) > 2 and x.std() > 0 and y.std() > 0 else None


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
def _daily() -> pd.DataFrame:
    import rotation as RO
    p = RO.CACHE / "perp_1d.parquet"
    if not p.exists():
        raise SystemExit(f"no {p}: run  python src/rotation.py --build perp  first")
    return RO.split_instruments(pd.read_parquet(p))


def _months(a: str, b: str) -> list[str]:
    return [str(p) for p in pd.period_range(a, b, freq="M")]


def build() -> None:
    import datafeed as DF
    import ml_pool as MPL
    OUT.mkdir(parents=True, exist_ok=True)
    d = _daily()
    mp = OUT / "members.json"
    if not mp.exists():
        mem = monthly_members(d, _months(MEMBERS_FROM, C.DATA_END))
        mp.write_text(json.dumps(mem, indent=1))
    mem = json.loads(mp.read_text())
    uni = json.loads(SOURCE_UNIVERSE.read_text())
    core = {u["inst"] for u in uni}
    (OUT / "trade.json").write_text(json.dumps([u["inst"] for u in uni[:TRADE_N]], indent=1))
    extra = sorted(set().union(*map(set, mem.values())) - core)
    rng = d.groupby("inst")["date"].agg(["min", "max"])
    sym = d.drop_duplicates("inst").set_index("inst")["symbol"]
    months = set(C.month_range(*MPL.MONTHS))
    print(f"[ml_wide] {len(extra)} coins beyond section 30's {len(core)} were a monthly top-{TRAIN_TOP}", flush=True)
    for n, inst in enumerate(extra, 1):
        s = sym[inst]
        lo, hi = rng.at[inst, "min"], rng.at[inst, "max"] + pd.Timedelta(days=1)
        for tf in WF.TFS:
            kp = WF.cache_dir(tf) / f"{inst}.parquet"
            if kp.exists():
                continue
            WF.cache_dir(tf).mkdir(parents=True, exist_ok=True)
            keys = [k for k in DF.list_keys(f"data/futures/{C.MARKET}/monthly/klines/{s}/{WF.TF_NAME[tf]}/")
                    if k[-11:-4] in months]
            zs = [z for z in (DF.fetch_zip(x, WF.RAW / f"perp_{WF.TF_NAME[tf]}" / s) for x in keys) if z]
            if not zs:
                continue
            k = pd.concat([DF._read_one_zip(z, C.KLINE_COLS) for z in zs], ignore_index=True)
            k["open_time"] = MPL._ms(k["open_time"])
            k = k[(k["open_time"] >= lo) & (k["open_time"] < hi)].drop_duplicates("open_time").sort_values("open_time")
            k.to_parquet(kp, index=False)
        fp = WF.cache_dir(60) / f"{inst}_funding.parquet"
        if not fp.exists():
            fkeys = [x for x in DF.list_keys(f"data/futures/{C.MARKET}/monthly/fundingRate/{s}/") if x[-11:-4] in months]
            fz = [z for z in (DF.fetch_zip(x, WF.RAW / "perp_funding" / s) for x in fkeys) if z]
            f = (pd.concat([DF._read_one_zip(z, C.FUNDING_COLS) for z in fz], ignore_index=True) if fz
                 else pd.DataFrame(columns=C.FUNDING_COLS))
            if len(f):
                f["calc_time"] = MPL._ms(f["calc_time"])
                f = f[(f["calc_time"] >= lo) & (f["calc_time"] < hi)].sort_values("calc_time")
            f.to_parquet(fp, index=False)
        print(f"  {n}/{len(extra)} {inst}: cached", flush=True)
    print(f"BUILD OK: {len(core)} + {len(extra)} coins")


SOURCE_UNIVERSE = C.ROOT / "results" / "_multi" / "ml_wf" / WF.UNIVERSE_FILE


def load_wide() -> tuple[dict, set, dict, list[str]]:
    mem = json.loads((OUT / "members.json").read_text())
    trade = json.loads((OUT / "trade.json").read_text())
    by_tf, _ = W3.load_all()
    core = set(by_tf[60])
    extra = sorted(set().union(*map(set, mem.values())) - core)
    for inst in extra:
        if not all((WF.cache_dir(tf) / f"{inst}.parquet").exists() for tf in WF.TFS):
            continue
        fund = pd.read_parquet(WF.cache_dir(60) / f"{inst}_funding.parquet")
        for tf in WF.TFS:
            b = W2._read(WF.cache_dir(tf) / f"{inst}.parquet")
            if len(b):
                by_tf[tf][inst] = {"spot": b, "perp": b, "fund": fund}
    return by_tf, core, mem, trade


# --------------------------------------------------------------------------
def evaluate(P20, pred_base, pred_wide, other, q, mode, min_coins=MP.MIN_COINS, keep=False, corr=None) -> dict:
    a_tr, b_tr = WF.WINDOWS["train"]
    a_va, b_va = WF.WINDOWS["valid"]
    table = []
    for form, pr in (("base", pred_base), ("wide", pred_wide)):
        t, _ = MP.run_cell(P20, pr, other, a_tr, b_tr, CELL["agree"], CELL["sizing"], CELL["cap"], q, mode)
        acc = MP.account(t, a_tr, b_tr)
        table.append({"form": form, **{k: acc[k] for k in ("trades", "weekly_mean", "tstat", "per_year", "max_dd",
                                                           "mean_r")},
                      "per_year_r": {str(y): float(g["ret"].sum())
                                     for y, g in t.groupby(pd.to_datetime(t["exit_time"]).dt.year)}})
        print(f"TRAIN-WF {form}: {acc['trades']} trades, weekly {acc['weekly_mean']:+.5f}, t {acc['tstat']:+.2f}, "
              f"dd {acc['max_dd']:.3f}", flush=True)
    ok = [x for x in table if x["trades"] >= MP.MIN_TRADES]
    best = max(ok, key=lambda x: x["tstat"]) if ok else table[0]
    pr = pred_base if best["form"] == "base" else pred_wide
    v, t = MP.judge(P20, pr, other, a_va, b_va, CELL["agree"], CELL["sizing"], CELL["cap"], q, mode, min_coins)
    w = MP.weekly(t, a_va, b_va)
    tot = float(w.sum())
    v["diagnostics"] = {"forecast_corr_valid": corr,
                        "top_weeks_share": float(w.sort_values(ascending=False).iloc[:5].sum()) / tot if tot > 0 else None,
                        "neg_weeks": int((w < 0).sum())}
    gates = {"train_chose_wide": best["form"] == "wide",
             "train_weekly_mean>0": best["weekly_mean"] > 0 and best in ok,
             f"valid_trades>={MP.MIN_TRADES}": v["trades"] >= MP.MIN_TRADES,
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
    res = {"chosen": {"form": best["form"], **CELL}, "train_table": table, "valid": v,
           "verdict": "REJECT" if failed else "PASS", "gates_failed": failed,
           "model": {"q_in": q, "exit_mode": mode, "horizons": list(HORIZONS)}}
    if keep:
        res["_trades"] = t
    return res


def run(final: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    res_path, lock = OUT / "summary.json", OUT / "holdout.json"
    if final:
        res = json.loads(res_path.read_text()) if res_path.exists() else None
        if not res or res["verdict"] != "PASS":
            raise SystemExit("--final refused: needs a PASS from the TRAIN/VALID run")
        if lock.exists():
            raise SystemExit(f"--final refused: holdout already used ({lock})")
        for o in (MP.OUT, XS.OUT, MK.OUT, FL.OUT):
            if (o / "holdout.json").exists():
                raise SystemExit(f"--final refused: sections 31-36 share one holdout and {o.name} used it")
    elif res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    if not (OUT / "members.json").exists():
        raise SystemExit("no members: run  python src/ml_wide.py --build")
    spans = [WF.WINDOWS["train"], WF.WINDOWS["valid"]] + ([WF.WINDOWS["holdout"]] if final else [])
    trade = json.loads((OUT / "trade.json").read_text())
    by_tf0, _ = W3.load_all()
    P_o, o4 = MP.forecasts(by_tf0, 240, spans)
    del P_o
    P0, pred0 = MP.forecasts(by_tf0, MP.TF_MAIN, spans)
    P20 = {c: P0[c] for c in trade if c in P0}
    pred_base = {c: pred0[c] for c in P20}
    other = {"4h": {c: o4[c] for c in P20 if c in o4}}
    del P0, pred0, by_tf0
    gc.collect()
    by_tf, core, mem, _ = load_wide()
    print(f"[ml_wide] training coins: {len(by_tf[60])} ({len(core)} core); traded: {len(P20)}", flush=True)
    P = W2.prepare(by_tf, MP.TF_MAIN)
    del by_tf
    gc.collect()
    pw = wide_forecasts(P, mem, core, spans)
    pred_wide = {c: pw[c].reindex(P20[c]["X"].index) for c in P20}
    corr = {"base": forecast_corr(P20, pred_base, *WF.WINDOWS["valid"]),
            "wide": forecast_corr(P20, pred_wide, *WF.WINDOWS["valid"])}
    del P, pw
    gc.collect()
    m = MP._cfg(MP.TF_MAIN)
    if final:
        a, b = WF.WINDOWS["holdout"]
        pr = pred_base if res["chosen"]["form"] == "base" else pred_wide
        h, t = MP.judge(P20, pr, other, a, b, CELL["agree"], CELL["sizing"], CELL["cap"], m["q_in"], m["exit_mode"])
        h["verdict"] = ("CONFIRMED" if h["weekly_mean"] > 0 and h["ci_lo"] > 0 and h["shift_median"] is not None
                        and h["timing"] is not None and h["timing"] > h["shift_median"]
                        and h["breadth"]["share"] >= MP.BREADTH_SHARE else "FAILED")
        lock.write_text(json.dumps(h, indent=1, default=str))
        t.to_csv(OUT / "trades_holdout.csv.gz", index=False)
        write_report(res)
        print(json.dumps({k: h.get(k) for k in ("trades", "weekly_mean", "ci_lo", "verdict")}, indent=1))
        return
    res = evaluate(P20, pred_base, pred_wide, other, m["q_in"], m["exit_mode"], keep=True, corr=corr)
    res["training_coins"] = {"core": len(core), "members_union": len(set().union(*map(set, mem.values())))}
    res["traded"] = list(P20)
    res.pop("_trades").to_csv(OUT / "trades_valid.csv.gz", index=False)
    res_path.write_text(json.dumps(res, indent=1, default=str))
    write_report(res)
    print(f"\nML_WIDE: chose {res['chosen']} -> {res['verdict']} failed {res['gates_failed']}")


def write_report(r: dict) -> None:
    v, d = r["valid"], r["valid"]["diagnostics"]
    f = (lambda x, k=5: "-" if x is None else f"{x:+.{k}f}")
    corr = d.get("forecast_corr_valid") or {}
    L = ["# Train wide, trade the top 20: more data and a horizon ensemble (PLAN.md section 36)", "",
         "GENERATED by `src/ml_wide.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}** (TRAIN chose {r['chosen']}; failed: {r['gates_failed'] or 'none'})", "",
         f"- traded coins ({len(r.get('traded', []))}): {', '.join(c.replace('USDT', '') for c in r.get('traded', []))}",
         f"- training coins: {r.get('training_coins')}",
         f"- VALID {v['trades']} trades over {v['weeks']} weeks: weekly account return {f(v['weekly_mean'])}, "
         f"95% CI [{f(v['ci_lo'])}, {f(v['ci_hi'])}], t {v['tstat']:+.2f}; return per year {f(v['per_year'], 4)}, "
         f"max drawdown {v['max_dd']:.4f}",
         f"- mean R per trade {f(v['mean_r'], 4)}; long {f(v['long_ret'], 4)} / short {f(v['short_ret'], 4)} "
         f"(summed return); cost x1.5 weekly {f(v['stress_weekly_mean'])}",
         f"- timing {f(v['timing'], 4)} vs shifted median {f(v['shift_median'], 4)} / p95 {f(v['shift_p95'], 4)}; "
         f"breadth {len(v['breadth']['beat'])} of {v['breadth']['eligible']} ({v['breadth']['share']:.2f}); "
         f"per year {v['per_year_r']}",
         f"- diagnostics: forecast/label correlation on VALID base {f(corr.get('base'), 4)} vs wide "
         f"{f(corr.get('wide'), 4)}; best 5 weeks = {f(d['top_weeks_share'], 3)} of the total; negative weeks "
         f"{d['neg_weeks']} of {v['weeks']}", "",
         "| form | TRAIN trades | weekly mean | t | per year | max DD | mean R | summed return by year |",
         "|---|---|---|---|---|---|---|---|"]
    for x in r["train_table"]:
        L.append(f"| {x['form']} | {x['trades']} | {f(x['weekly_mean'])} | {x['tstat']:+.2f} | {f(x['per_year'], 4)} | "
                 f"{x['max_dd']:.4f} | {f(x['mean_r'], 4)} | {x['per_year_r']} |")
    hp = OUT / "holdout.json"
    if hp.exists():
        h = json.loads(hp.read_text())
        L += ["", f"**HOLDOUT: {h['verdict']}** - {h['trades']} trades, weekly {f(h['weekly_mean'])}, CI "
              f"[{f(h['ci_lo'])}, {f(h['ci_hi'])}], timing {f(h['timing'], 4)} vs median {f(h['shift_median'], 4)}"]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--final", action="store_true")
    a = ap.parse_args()
    if a.build:
        build()
    else:
        run(a.final)


if __name__ == "__main__":
    main()
