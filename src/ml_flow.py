"""Positioning data for section 30's 1h model, judged on section 31's account (PLAN.md section 34)

    python src/ml_flow.py --build   # Binance metrics (open interest, long/short ratios) of the 47 coins
    python src/ml_flow.py           # TRAIN/VALID, once
    python src/ml_flow.py --final   # HOLDOUT once, only after PASS (shared with sections 31-33)

Sections 31-33 (_multi Exp 033-040) located section 30's edge, if it is real:
each coin's own 1h forecast traded on that coin, and mostly SHORTS on alt-coins
in sell-offs. The model has only seen prices, volume, taker flow and the coin's
last funding rate. It has never seen POSITIONING: how much leverage is open,
which side the crowd is on, and what funding costs the whole market.

Hypothesis: sell-offs that the model catches are liquidation cascades, and they
are more likely when open interest has built up, the crowd is long and funding
is high. Adding positioning should sharpen exactly the trades that carry the
book, so the same account becomes less dependent on a few weeks.

Everything is held fixed except the features (an ablation):
  * model: section 30's chosen 1h setting, refit every month (walk-forward) on
    the 47 coins with section 30's histories; the 4h agreement forecasts are
    section 30's frozen ones (ml_port.forecasts, checked to 1e-6);
  * account: section 31's chosen cell (agreement 4h, confidence sizing, 5% cap),
    section 31's policy, stop, costs and gates (ml_port.judge).
New features (FLOW_COLS), all causal on the 1h bar close:
  per coin, from Binance metrics (experiment.attach_metrics: a row is used 5 min
  after its create_time, NaN when older than 30 min or before 2021-12):
    oi_chg_24 / oi_chg_168   log change of open interest over 24 / 168 bars
    oi_to_vol                open interest (USDT) / last 24 bars' traded value
    top_pos_ls, acct_ls      log top-trader position and all-account long/short ratio
    acct_ls_chg_24           24-bar change of the log account ratio
    fund_168                 mean of the coin's last funding rate over 168 bars
  market-wide, the same-hour mean over coins (>= MIN_XS coins):
    mkt_oi_chg_24, mkt_acct_ls, mkt_funding, mkt_fund_168, and
    rel_oi_chg_24 = coin minus market.
Funding exists from each perp's start (TRAIN has it all); metrics start in
2021-12, so TRAIN has 13 months of them. LightGBM reads NaN as missing.
TRAIN (2021-22) compares the two feature sets on the account (form "base" =
section 31 recomputed, "flow" = base + FLOW_COLS) by the weekly t-statistic; a
"base" choice is section 31 again and is REJECT (gate train_chose_flow).
VALID gates: section 31's, unchanged. Diagnostics: the share of the flow
features in the VALID refits' total gain, the best-5-week share, negative weeks.
Holdout: sections 31-34 share ONE holdout; --final refuses if any used it.
Writes results/_multi/ml_flow/ and the generated journal/_multi/ml_flow.md.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
import experiment as EX  # noqa: E402
import ml_mkt as MK  # noqa: E402
import ml_port as MP  # noqa: E402
import ml_wf as WF  # noqa: E402
import ml_wf3 as W3  # noqa: E402
import ml_xs as XS  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "ml_flow"
REPORT = C.ROOT / "journal" / "_multi" / "ml_flow.md"
MET_DIR = C.ROOT / "data" / "cache" / "_multi" / "metrics"
MET_RAW = C.ROOT / "data" / "raw" / "_multi" / "metrics"

# ---- pre-registered (PLAN.md section 34)
FORM = ("base", "flow")
CELL = {"agree": "4h", "sizing": "conf", "cap": 0.05}      # section 31's TRAIN choice, fixed
MIN_XS = 10
MET_FROM, MET_TO = "2021-12-01", "2026-08-31"
COIN_COLS = ["oi_chg_24", "oi_chg_168", "oi_to_vol", "top_pos_ls", "acct_ls", "acct_ls_chg_24", "fund_168"]
MKT_COLS = ["mkt_oi_chg_24", "mkt_acct_ls", "mkt_funding", "mkt_fund_168", "rel_oi_chg_24"]
FLOW_COLS = COIN_COLS + MKT_COLS
TOP_WEEKS = 5


# --------------------------------------------------------------------------
def build() -> None:
    import datafeed as DF
    MET_DIR.mkdir(parents=True, exist_ok=True)
    uni = json.loads((W3.OUT / "universe.json").read_text())
    days = {d.strftime("%Y-%m-%d") for d in pd.date_range(MET_FROM, MET_TO, freq="D")}
    for u in uni:
        s = u["inst"]
        out = MET_DIR / f"{s}.parquet"
        if out.exists():
            continue
        keys = [k for k in DF.list_keys(f"data/futures/um/daily/metrics/{s}/") if k[-14:-4] in days]
        with ThreadPoolExecutor(max_workers=8) as ex:
            paths = list(ex.map(lambda k: DF.fetch_zip(k, MET_RAW / s), keys))
        frames = []
        for z in paths:
            if z is None:
                continue
            try:
                frames.append(DF.read_metrics_zip(z))
            except Exception as e:  # noqa: BLE001 - report, never hide
                print(f"  !! {z.name}: {e}")
        df = (pd.concat(frames, ignore_index=True).sort_values("create_time").drop_duplicates("create_time")
              if frames else pd.DataFrame(columns=DF.METRICS_COLS[:1] + DF.METRICS_NUM))
        df.reset_index(drop=True).to_parquet(out, index=False)
        print(f"  {s}: {len(keys)} days, {len(df):,} rows", flush=True)
    print(f"BUILD OK: metrics for {len(uni)} coins in {MET_DIR}")


def load_metrics(coins) -> dict[str, pd.DataFrame]:
    out = {}
    for c in coins:
        p = MET_DIR / f"{c}.parquet"
        if not p.exists():
            raise SystemExit(f"no metrics cache for {c}: run  python src/ml_flow.py --build")
        m = pd.read_parquet(p)
        m["create_time"] = pd.to_datetime(m["create_time"], utc=True)
        out[c] = m.sort_values("create_time").rename(columns=EX.METRIC_NAMES)
    return out


# --------------------------------------------------------------------------
# features (test 30)
# --------------------------------------------------------------------------
def coin_flow(bars: pd.DataFrame, X: pd.DataFrame, metrics: pd.DataFrame | None, tf: int = 60) -> pd.DataFrame:
    """The per-coin flow features on the decision index X.index (bars[:-1])."""
    f = pd.DataFrame(index=bars.index)
    if metrics is not None and len(metrics):
        b = EX.attach_metrics(bars, metrics, tf)
        oi, oi_usd = b["oi"].where(b["oi"] > 0), b["oi_usd"].where(b["oi_usd"] > 0)
        f["oi_chg_24"] = np.log(oi / oi.shift(24))
        f["oi_chg_168"] = np.log(oi / oi.shift(168))
        val = (bars["close"] * bars["volume"]).rolling(24).sum()
        f["oi_to_vol"] = oi_usd / val.where(val > 0)
        f["top_pos_ls"] = np.log(b["top_pos_ls"].where(b["top_pos_ls"] > 0))
        f["acct_ls"] = np.log(b["acct_ls"].where(b["acct_ls"] > 0))
        f["acct_ls_chg_24"] = f["acct_ls"] - f["acct_ls"].shift(24)
    else:
        for c in COIN_COLS[:-1]:
            f[c] = np.nan
    fl = X["funding_last"] if "funding_last" in X else pd.Series(np.nan, index=X.index)
    f = f.reindex(X.index)
    f["fund_168"] = fl.rolling(168, min_periods=24).mean()
    return f.replace([np.inf, -np.inf], np.nan)


def add_flow(P: dict, metrics: dict, min_xs: int = MIN_XS) -> dict:
    """A copy of P whose X carries FLOW_COLS; the base P is not touched."""
    Q = {c: dict(p) for c, p in P.items()}
    per = {c: coin_flow(P[c]["bars"], P[c]["X"], metrics.get(c)) for c in P}
    def mkt(src):
        df = pd.DataFrame({c: src[c] for c in P})
        return df.mean(axis=1, skipna=True).where(df.notna().sum(axis=1) >= min_xs)
    fund = {c: (P[c]["X"]["funding_last"] if "funding_last" in P[c]["X"] else pd.Series(np.nan, index=P[c]["X"].index))
            for c in P}
    m_oi = mkt({c: per[c]["oi_chg_24"] for c in P})
    m_ls = mkt({c: per[c]["acct_ls"] for c in P})
    m_fu = mkt(fund)
    m_f168 = mkt({c: per[c]["fund_168"] for c in P})
    for c in P:
        idx = P[c]["X"].index
        g = per[c].copy()
        g["mkt_oi_chg_24"] = m_oi.reindex(idx).to_numpy()
        g["mkt_acct_ls"] = m_ls.reindex(idx).to_numpy()
        g["mkt_funding"] = m_fu.reindex(idx).to_numpy()
        g["mkt_fund_168"] = m_f168.reindex(idx).to_numpy()
        g["rel_oi_chg_24"] = g["oi_chg_24"] - g["mkt_oi_chg_24"]
        Q[c]["X"] = pd.concat([P[c]["X"], g[FLOW_COLS]], axis=1)
    return Q


def flow_forecasts(P: dict, spans, models: dict | None = None) -> dict[str, pd.Series]:
    cfg = MP._cfg(MP.TF_MAIN)["setting"]
    pred = {c: np.full(len(P[c]["X"]), np.nan) for c in P}
    for a, b in spans:
        p = WF.walk_forward(P, MP.TF_MAIN, cfg, a, b, models=models)
        for c in P:
            pred[c] = np.where(np.isfinite(p[c]), p[c], pred[c])
    return {c: pd.Series(pred[c], index=P[c]["X"].index) for c in P}


def flow_gain_share(models: dict, a: str, b: str) -> float | None:
    """Share of the total split gain that the flow features take, over the refits in [a, b)."""
    tot = flow = 0.0
    for m0, mdl in models.items():
        if not (pd.Timestamp(a, tz="UTC") <= m0 < pd.Timestamp(b, tz="UTC")):
            continue
        g = mdl.feature_importance("gain")
        names = mdl.feature_name()
        tot += float(g.sum())
        flow += float(sum(v for n, v in zip(names, g) if n in FLOW_COLS))
    return flow / tot if tot > 0 else None


# --------------------------------------------------------------------------
def _cell(P, pred, other, a, b, q, mode, min_coins):
    return MP.judge(P, pred, other, a, b, CELL["agree"], CELL["sizing"], CELL["cap"], q, mode, min_coins)


def evaluate(P, pred_base, P_flow, pred_flow, other, q, mode, min_coins=MP.MIN_COINS, gain=None, keep=False) -> dict:
    a_tr, b_tr = WF.WINDOWS["train"]
    a_va, b_va = WF.WINDOWS["valid"]
    table = []
    for form, PP, pr in (("base", P, pred_base), ("flow", P_flow, pred_flow)):
        t, _ = MP.run_cell(PP, pr, other, a_tr, b_tr, CELL["agree"], CELL["sizing"], CELL["cap"], q, mode)
        acc = MP.account(t, a_tr, b_tr)
        table.append({"form": form, **{k: acc[k] for k in ("trades", "weekly_mean", "tstat", "per_year", "max_dd",
                                                           "mean_r")},
                      "per_year_r": {str(y): float(g["ret"].sum())
                                     for y, g in t.groupby(pd.to_datetime(t["exit_time"]).dt.year)}})
        print(f"TRAIN-WF {form}: {acc['trades']} trades, weekly {acc['weekly_mean']:+.5f}, t {acc['tstat']:+.2f}, "
              f"dd {acc['max_dd']:.3f}", flush=True)
    ok = [x for x in table if x["trades"] >= MP.MIN_TRADES]
    best = max(ok, key=lambda x: x["tstat"]) if ok else table[0]
    PP, pr = (P, pred_base) if best["form"] == "base" else (P_flow, pred_flow)
    v, t = _cell(PP, pr, other, a_va, b_va, q, mode, min_coins)
    w = MP.weekly(t, a_va, b_va)
    tot = float(w.sum())
    v["diagnostics"] = {"flow_gain_share_valid_refits": gain,
                        "top_weeks_share": float(w.sort_values(ascending=False).iloc[:TOP_WEEKS].sum()) / tot
                        if tot > 0 else None,
                        "neg_weeks": int((w < 0).sum())}
    gates = {"train_chose_flow": best["form"] == "flow",
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
           "verdict": "REJECT" if failed else "PASS", "gates_failed": failed, "model": {"q_in": q, "exit_mode": mode}}
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
        for o in (MP.OUT, XS.OUT, MK.OUT):
            if (o / "holdout.json").exists():
                raise SystemExit(f"--final refused: sections 31-34 share one holdout and {o.name} used it")
    elif res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    by_tf, _ = W3.load_all()
    spans = [WF.WINDOWS["train"], WF.WINDOWS["valid"]] + ([WF.WINDOWS["holdout"]] if final else [])
    P_o, o4 = MP.forecasts(by_tf, 240, spans)
    del P_o
    P, pred_base = MP.forecasts(by_tf, MP.TF_MAIN, spans)
    P_flow = add_flow(P, load_metrics(list(P)))
    models = {}
    pred_flow = flow_forecasts(P_flow, spans, models)
    other = {"4h": o4}
    m = MP._cfg(MP.TF_MAIN)
    if final:
        a, b = WF.WINDOWS["holdout"]
        PP, pr = (P, pred_base) if res["chosen"]["form"] == "base" else (P_flow, pred_flow)
        h, t = _cell(PP, pr, other, a, b, m["q_in"], m["exit_mode"], MP.MIN_COINS)
        h["verdict"] = ("CONFIRMED" if h["weekly_mean"] > 0 and h["ci_lo"] > 0 and h["shift_median"] is not None
                        and h["timing"] is not None and h["timing"] > h["shift_median"]
                        and h["breadth"]["share"] >= MP.BREADTH_SHARE else "FAILED")
        lock.write_text(json.dumps(h, indent=1, default=str))
        t.to_csv(OUT / "trades_holdout.csv.gz", index=False)
        write_report(res)
        print(json.dumps({k: h.get(k) for k in ("trades", "weekly_mean", "ci_lo", "verdict")}, indent=1))
        return
    gain = flow_gain_share(models, *WF.WINDOWS["valid"])
    res = evaluate(P, pred_base, P_flow, pred_flow, other, m["q_in"], m["exit_mode"], gain=gain, keep=True)
    res.pop("_trades").to_csv(OUT / "trades_valid.csv.gz", index=False)
    res_path.write_text(json.dumps(res, indent=1, default=str))
    write_report(res)
    print(f"\nML_FLOW: chose {res['chosen']} -> {res['verdict']} failed {res['gates_failed']}")


def write_report(r: dict) -> None:
    v, d = r["valid"], r["valid"]["diagnostics"]
    f = (lambda x, k=5: "-" if x is None else f"{x:+.{k}f}")
    L = ["# Positioning data for section 30's 1h model, on section 31's account (PLAN.md section 34)", "",
         "GENERATED by `src/ml_flow.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}** (TRAIN chose {r['chosen']}; failed: {r['gates_failed'] or 'none'})", "",
         f"- VALID {v['trades']} trades over {v['weeks']} weeks: weekly account return {f(v['weekly_mean'])}, "
         f"95% CI [{f(v['ci_lo'])}, {f(v['ci_hi'])}], t {v['tstat']:+.2f}; return per year {f(v['per_year'], 4)}, "
         f"max drawdown {v['max_dd']:.4f}",
         f"- mean R per trade {f(v['mean_r'], 4)}; long {f(v['long_ret'], 4)} / short {f(v['short_ret'], 4)} "
         f"(summed return); cost x1.5 weekly {f(v['stress_weekly_mean'])}",
         f"- timing {f(v['timing'], 4)} vs shifted median {f(v['shift_median'], 4)} / p95 {f(v['shift_p95'], 4)}; "
         f"breadth {len(v['breadth']['beat'])} of {v['breadth']['eligible']} ({v['breadth']['share']:.2f}); "
         f"per year {v['per_year_r']}",
         f"- diagnostics: flow features' share of the VALID refits' gain {f(d['flow_gain_share_valid_refits'], 3)}; "
         f"best {TOP_WEEKS} weeks = {f(d['top_weeks_share'], 3)} of the total; negative weeks {d['neg_weeks']} "
         f"of {v['weeks']}", "",
         "| form | TRAIN trades | weekly mean | t | per year | max DD | mean R | summed return by year |",
         "|---|---|---|---|---|---|---|---|"]
    for x in r["train_table"]:
        L.append(f"| {x['form']} | {x['trades']} | {f(x['weekly_mean'])} | {x['tstat']:+.2f} | {f(x['per_year'], 4)} | "
                 f"{x['max_dd']:.4f} | {f(x['mean_r'], 4)} | {x['per_year_r']} |")
    hp = OUT / "holdout.json"
    if hp.exists():
        h = json.loads(hp.read_text())
        L += ["", f"**HOLDOUT: {h['verdict']}** - {h['trades']} trades, weekly {f(h['weekly_mean'])}, CI "
              f"[{f(h['ci_lo'])}, {f(h['ci_hi'])}], timing {f(h['timing'], 4)} vs median {f(h['shift_median'], 4)}, "
              f"breadth {h['breadth']['share']:.2f}"]
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
