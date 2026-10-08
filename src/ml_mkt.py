"""Market timing on BTC/ETH from the 47-coin mean forecast (PLAN.md section 33)

    python src/ml_mkt.py           # TRAIN/VALID, once (needs ml_wf3.py --build caches)
    python src/ml_mkt.py --final   # HOLDOUT once, only after PASS (shared with sections 31/32)

Sections 31 and 32 showed what section 30's 1h model is: a MARKET TIMER. Its
usable content is the market-wide part of the forecast (demeaning it removed the
edge, _multi Exp 036), and section 31's book put 89% of a week's trades on one
side and earned most of its return from a few market-wide moves, mostly
sell-offs (_multi Exp 037). Spreading one market call over ~40 alt-coins pays
alt-coin costs (slippage 0.05% vs 0.02%) ~40 times for one bet.

Hypothesis: the same call, made once on the market's most liquid contracts,
keeps the timing and sheds most of the cost and alt-coin noise.

Nothing is refitted. Section 30's frozen 1h (and 4h) walk-forward models are
recomputed and checked as in section 31 (ml_port.forecasts). Then:
  signal   m(t) = mean of the 47 coins' 1h forecasts at open time t (>= MIN_XS
           coins with a forecast, else none). Causal: only forecasts made at t.
  policy   section 30's own hysteresis on m: entry bar = rolling q_in quantile of
           |m| (section 30's q_in), exit mode = section 30's; 8-ATR protective
           stop; no clock. Trades on perp bars with perp costs and funding.
  I  instrument  BTC | ETH | BTC+ETH (both, each at half risk, total <= 1%)
  A  agreement   off | 4h (a new position only if the 4h mean forecast, last
                 closed bar, has the same sign; section 31's rule)
TRAIN walk-forward (2021-22) picks 1 of 6 cells by the weekly account
t-statistic (>= MIN_TRADES trades). VALID (2023-24) judges it once:
  TRAIN weekly mean > 0; >= MIN_TRADES trades; weekly mean > 0 and its 95%
  bootstrap CI lower bound > 0; weekly mean > 0 at cost x1.5; timing above the
  95th percentile of 200 circular shifts of the desired path; both legs' summed
  return > 0; max drawdown <= 20%.
Diagnostics (not gates): share of time long/short/flat, top-5-week share,
buy-and-hold weekly mean of the instrument(s), beta/correlation to it.
Holdout: sections 31, 32 and 33 share ONE holdout (--final refuses if 31 or 32
used it). CONFIRMED = weekly mean > 0, CI lower bound > 0, timing above the
shifted median.
Writes results/_multi/s33_ml_mkt_1h/ and the generated journal/_multi/s33_ml_mkt_1h.md.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
import ml_hold as MH  # noqa: E402
import ml_port as MP  # noqa: E402
import ml_wf as WF  # noqa: E402
import ml_wf3 as W3  # noqa: E402
import ml_xs as XS  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "s33_ml_mkt_1h"
REPORT = C.ROOT / "journal" / "_multi" / "s33_ml_mkt_1h.md"

# ---- pre-registered (PLAN.md section 33)
INSTRUMENT = {"BTC": ("BTCUSDT",), "ETH": ("ETHUSDT",), "BTC+ETH": ("BTCUSDT", "ETHUSDT")}
AGREE = ("off", "4h")
MIN_XS = 10
MIN_TRADES = 30
TOP_WEEKS = 5


# --------------------------------------------------------------------------
# pure pieces (test 29)
# --------------------------------------------------------------------------
def market_signal(pred: dict[str, pd.Series], min_coins: int = MIN_XS) -> pd.Series:
    """Mean of every coin's forecast at the same open time; NaN under min_coins."""
    df = pd.DataFrame(pred)
    n = df.notna().sum(axis=1)
    return df.mean(axis=1, skipna=True).where(n >= min_coins)


def book(P: dict, pred1: dict, other: dict, inst: str, min_xs: int = MIN_XS) -> tuple[dict, dict, dict]:
    """The instrument(s) of a cell, each driven by the market signal."""
    m1 = market_signal(pred1, min_xs)
    coins = [c for c in INSTRUMENT[inst] if c in P]
    Pi = {c: P[c] for c in coins}
    p1 = {c: m1.reindex(P[c]["X"].index) for c in coins}
    ot = {k: {c: market_signal(v, min_xs) for c in coins} for k, v in other.items()}
    return Pi, p1, ot


def run_cell(P, pred1, other, a, b, inst, agree, q, mode, stress=1.0, min_xs=MIN_XS):
    Pi, p1, ot = book(P, pred1, other, inst, min_xs)
    t, paths = MP.run_cell(Pi, p1, ot, a, b, agree, "flat", None, q, mode, stress)
    if len(Pi) > 1:                                     # two contracts share the 1% budget
        t["risk"] = t["risk"] / len(Pi)
        t["ret"] = t["net_r"] * t["risk"]
    return t, paths, Pi


def buy_hold_weekly(Pi: dict, a: str, b: str) -> pd.Series:
    return XS.market_weekly(Pi, a, b)


def judge(P, pred1, other, a, b, inst, agree, q, mode, min_xs=MIN_XS):
    t, paths, Pi = run_cell(P, pred1, other, a, b, inst, agree, q, mode, min_xs=min_xs)
    acc = MP.account(t, a, b)
    acc["stress_weekly_mean"] = MP.account(run_cell(P, pred1, other, a, b, inst, agree, q, mode, 1.5, min_xs)[0],
                                           a, b)["weekly_mean"]
    timing, per, pooled = MH.control(Pi, paths)
    w = MP.weekly(t, a, b)
    bh = buy_hold_weekly(Pi, a, b).reindex(w.index)
    ok = bh.notna().to_numpy()
    x, y = bh.to_numpy()[ok], w.to_numpy()[ok]
    des = np.concatenate([p[0] for p in paths.values()]) if paths else np.zeros(0)
    tot = float(w.sum())
    acc.update(timing=timing, shift_median=MH._q(pooled, 50), shift_p95=MH._q(pooled, 95),
               per_year_r={str(yr): float(g["ret"].sum()) for yr, g in t.groupby(pd.to_datetime(t["exit_time"]).dt.year)},
               diagnostics={"time_long": float((des > 0).mean()) if len(des) else None,
                            "time_short": float((des < 0).mean()) if len(des) else None,
                            "top_weeks_share": float(w.sort_values(ascending=False).iloc[:TOP_WEEKS].sum()) / tot
                            if tot > 0 else None,
                            "neg_weeks": int((w < 0).sum()),
                            "buy_hold_weekly_logret": float(np.nanmean(bh)) if ok.any() else None,
                            "beta_to_buy_hold": float(np.cov(y, x)[0, 1] / np.var(x, ddof=1))
                            if ok.sum() > 2 and np.var(x) > 0 else None,
                            "corr_to_buy_hold": float(np.corrcoef(y, x)[0, 1])
                            if ok.sum() > 2 and np.std(x) > 0 and np.std(y) > 0 else None})
    return acc, t


def evaluate(P, pred1, other, q, mode, min_xs=MIN_XS, keep=False) -> dict:
    a_tr, b_tr = WF.WINDOWS["train"]
    a_va, b_va = WF.WINDOWS["valid"]
    table = []
    for inst, agree in itertools.product(INSTRUMENT, AGREE):
        t, _, _ = run_cell(P, pred1, other, a_tr, b_tr, inst, agree, q, mode, min_xs=min_xs)
        acc = MP.account(t, a_tr, b_tr)
        table.append({"instrument": inst, "agree": agree, **{k: acc[k] for k in
                      ("trades", "weekly_mean", "tstat", "per_year", "max_dd", "mean_r")}})
        print(f"TRAIN-WF {inst:>7} {agree:>3}: {acc['trades']} trades, weekly {acc['weekly_mean']:+.5f}, "
              f"t {acc['tstat']:+.2f}, dd {acc['max_dd']:.3f}", flush=True)
    ok = [x for x in table if x["trades"] >= MIN_TRADES]
    best = max(ok, key=lambda x: x["tstat"]) if ok else table[0]
    v, t = judge(P, pred1, other, a_va, b_va, best["instrument"], best["agree"], q, mode, min_xs)
    gates = {"train_weekly_mean>0": best["weekly_mean"] > 0 and best in ok,
             f"valid_trades>={MIN_TRADES}": v["trades"] >= MIN_TRADES,
             "valid_weekly_mean>0": v["weekly_mean"] > 0,
             "valid_ci_lo>0": v["ci_lo"] > 0,
             "stress_weekly_mean>0": v["stress_weekly_mean"] > 0,
             "timing_beats_shift_p95": v["shift_p95"] is not None and v["timing"] is not None
             and v["timing"] > v["shift_p95"],
             "both_legs>0": v["long_ret"] > 0 and v["short_ret"] > 0,
             f"max_dd<={MP.MAX_DD}": v["max_dd"] <= MP.MAX_DD}
    failed = [k for k, g in gates.items() if not g]
    res = {"chosen": {k: best[k] for k in ("instrument", "agree")}, "train_best": best, "train_table": table,
           "valid": v, "verdict": "REJECT" if failed else "PASS", "gates_failed": failed,
           "model": {"q_in": q, "exit_mode": mode}}
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
        for o in (MP.OUT, XS.OUT):
            if (o / "holdout.json").exists():
                raise SystemExit(f"--final refused: sections 31-33 share one holdout and {o.name} used it")
    elif res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    by_tf, _ = W3.load_all()
    spans = [WF.WINDOWS["train"], WF.WINDOWS["valid"]] + ([WF.WINDOWS["holdout"]] if final else [])
    P_o, o4 = MP.forecasts(by_tf, 240, spans)
    del P_o
    P, pred1 = MP.forecasts(by_tf, MP.TF_MAIN, spans)
    other = {"4h": o4}
    m = MP._cfg(MP.TF_MAIN)
    if final:
        ch = res["chosen"]
        a, b = WF.WINDOWS["holdout"]
        h, t = judge(P, pred1, other, a, b, ch["instrument"], ch["agree"], m["q_in"], m["exit_mode"])
        h["verdict"] = ("CONFIRMED" if h["weekly_mean"] > 0 and h["ci_lo"] > 0 and h["shift_median"] is not None
                        and h["timing"] is not None and h["timing"] > h["shift_median"] else "FAILED")
        lock.write_text(json.dumps(h, indent=1, default=str))
        t.to_csv(OUT / "trades_holdout.csv.gz", index=False)
        write_report(res)
        print(json.dumps({k: h.get(k) for k in ("trades", "weekly_mean", "ci_lo", "verdict")}, indent=1))
        return
    res = evaluate(P, pred1, other, m["q_in"], m["exit_mode"], keep=True)
    res.pop("_trades").to_csv(OUT / "trades_valid.csv.gz", index=False)
    res_path.write_text(json.dumps(res, indent=1, default=str))
    write_report(res)
    print(f"\nML_MKT: chose {res['chosen']} -> {res['verdict']} failed {res['gates_failed']}")


def write_report(r: dict) -> None:
    v, d = r["valid"], r["valid"]["diagnostics"]
    f = (lambda x, k=5: "-" if x is None else f"{x:+.{k}f}")
    L = ["# Market timing on BTC/ETH from the 47-coin mean forecast (PLAN.md section 33)", "",
         "GENERATED by `src/ml_mkt.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}** (TRAIN chose {r['chosen']}; failed: {r['gates_failed'] or 'none'})", "",
         f"- VALID {v['trades']} trades over {v['weeks']} weeks: weekly account return {f(v['weekly_mean'])}, "
         f"95% CI [{f(v['ci_lo'])}, {f(v['ci_hi'])}], t {v['tstat']:+.2f}; return per year {f(v['per_year'], 4)}, "
         f"max drawdown {v['max_dd']:.4f}",
         f"- mean R per trade {f(v['mean_r'], 4)}; long {f(v['long_ret'], 4)} / short {f(v['short_ret'], 4)} "
         f"(summed return); cost x1.5 weekly {f(v['stress_weekly_mean'])}",
         f"- timing {f(v['timing'], 4)} vs shifted median {f(v['shift_median'], 4)} / p95 {f(v['shift_p95'], 4)}; "
         f"per year {v['per_year_r']}",
         f"- diagnostics: time long {f(d['time_long'], 3)} / short {f(d['time_short'], 3)}; best {TOP_WEEKS} weeks = "
         f"{f(d['top_weeks_share'], 3)} of the total; negative weeks {d['neg_weeks']} of {v['weeks']}; buy-and-hold "
         f"weekly log return {f(d['buy_hold_weekly_logret'], 5)}; beta {f(d['beta_to_buy_hold'], 3)}, "
         f"correlation {f(d['corr_to_buy_hold'], 3)}", "",
         "| instrument | agree | TRAIN trades | weekly mean | t | per year | max DD | mean R |",
         "|---|---|---|---|---|---|---|---|"]
    for x in r["train_table"]:
        L.append(f"| {x['instrument']} | {x['agree']} | {x['trades']} | {f(x['weekly_mean'])} | {x['tstat']:+.2f} | "
                 f"{f(x['per_year'], 4)} | {x['max_dd']:.4f} | {f(x['mean_r'], 4)} |")
    hp = OUT / "holdout.json"
    if hp.exists():
        h = json.loads(hp.read_text())
        L += ["", f"**HOLDOUT: {h['verdict']}** - {h['trades']} trades, weekly {f(h['weekly_mean'])}, CI "
              f"[{f(h['ci_lo'])}, {f(h['ci_hi'])}], timing {f(h['timing'], 4)} vs median {f(h['shift_median'], 4)}"]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--final", action="store_true")
    run(ap.parse_args().final)


if __name__ == "__main__":
    main()
