"""Cross-sectional (market-demeaned) forecasts on section 31's account (PLAN.md section 32)

    python src/ml_xs.py           # TRAIN/VALID, once (needs ml_wf3.py --build caches)
    python src/ml_xs.py --final   # HOLDOUT once, only after PASS

Section 31 (ml_port.py, _multi Exp 033) failed one gate by 0.00026 (weekly CI
lower bound) and its return was concentrated: the 5 best of 105 weeks gave 67%
of it, and 2023 without its 3 best weeks was -0.079 (_multi Exp 034). Section
30's top WHY reasons were market-wide features 78-100% of the time, and the 47
coins behave like about 1.6 independent coins (correlation 0.61): the book is
mostly ONE bet on the market's next move, so its weeks swing together.

Hypothesis: the models carry a coin-RELATIVE signal (which coins will do
better or worse than the others) under a market-wide one that is mostly noise.
Removing the market-wide part at each hour - the cross-sectional mean of the
47 forecasts - should leave the relative signal, spread the book over long and
short at the same time, and cut the common weekly swing.

Nothing is refitted. Section 30's three frozen walk-forward models are
recomputed and checked exactly as in section 31 (ml_port.forecasts). Then:
  F  form   "raw" (section 31) | "demean": forecast minus the mean of every
            coin's forecast at the same open time (>= MIN_XS coins with a
            forecast, else no forecast). The same transform is applied to the
            4h and 1d forecasts used for agreement. The entry bar (rolling
            quantile of |forecast|) and confidence are then computed on the
            transformed forecast, per coin, exactly as before.
  plus section 31's switches: agreement off|4h|1d, sizing flat|conf, cap 5%|10%
  (uncapped dropped: it lost 150% on TRAIN in section 31).
TRAIN walk-forward (2021-22) picks 1 of 24 cells by the weekly account
t-statistic (>= MIN_TRADES trades), as in section 31. A "raw" choice is section
31 again and is REJECT (gate train_chose_demean). VALID gates are section 31's,
unchanged. Diagnostics (not gates): the share of the total from the best 5
weeks, negative weeks, and beta/correlation of the weekly account return to the
equal-weight weekly market return of the 47 coins.
Holdout: sections 31 and 32 share ONE holdout; --final refuses if section 31's
holdout file exists. CONFIRMED = section 31's rule.
Writes results/_multi/s32_ml_xs_1h/ and the generated journal/_multi/s32_ml_xs_1h.md.
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
import ml_port as MP  # noqa: E402
import ml_wf as WF  # noqa: E402
import ml_wf3 as W3  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "s32_ml_xs_1h"
REPORT = C.ROOT / "journal" / "_multi" / "s32_ml_xs_1h.md"

# ---- pre-registered (PLAN.md section 32)
FORM = ("raw", "demean")
AGREE = MP.AGREE
SIZING = MP.SIZING
CAP = (0.05, 0.10)
MIN_XS = 10
TOP_WEEKS = 5


# --------------------------------------------------------------------------
# pure pieces (test 28)
# --------------------------------------------------------------------------
def demean(pred: dict[str, pd.Series], min_coins: int = MIN_XS) -> dict[str, pd.Series]:
    """Each coin's forecast minus the mean of all coins' forecasts at the same
    open time; NaN where fewer than min_coins coins have a forecast. Uses only
    forecasts made at that time (causal)."""
    df = pd.DataFrame(pred)
    n = df.notna().sum(axis=1)
    m = df.mean(axis=1, skipna=True).where(n >= min_coins)
    out = df.sub(m, axis=0)
    return {c: out[c].reindex(pred[c].index) for c in pred}


def transform(form: str, pred1: dict, other: dict, min_coins: int = MIN_XS) -> tuple[dict, dict]:
    if form == "raw":
        return pred1, other
    return demean(pred1, min_coins), {k: demean(v, min_coins) for k, v in other.items()}


def market_weekly(P: dict, a: str, b: str) -> pd.Series:
    """Equal-weight mean of the coins' weekly log returns on [a, b), from the
    last traded close at or before each week start (traded bars only)."""
    weeks = pd.date_range(pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC"), freq=MP.BLOCK)
    rets = []
    for c in P:
        tb = P[c].get("tbars", P[c]["bars"])
        cl = tb["close"].where(tb["volume"] > 0).dropna()
        if cl.empty:
            continue
        close_t = cl.index + pd.Timedelta(minutes=MP.TF_MAIN)
        k = close_t.searchsorted(weeks, side="right") - 1
        px = np.where(k >= 0, cl.to_numpy()[np.maximum(k, 0)], np.nan)
        px = np.where((k >= 0) & (close_t[np.maximum(k, 0)] > weeks - pd.Timedelta(days=1)), px, np.nan)
        rets.append(np.diff(np.log(px)))
    r = np.nanmean(np.vstack(rets), axis=0) if rets else np.full(len(weeks) - 1, np.nan)
    return pd.Series(r, index=weeks[:-1])


def diagnostics(t: pd.DataFrame, P: dict, a: str, b: str) -> dict:
    w = MP.weekly(t, a, b)
    tot = float(w.sum())
    top = float(w.sort_values(ascending=False).iloc[:TOP_WEEKS].sum())
    mk = market_weekly(P, a, b).reindex(w.index)
    ok = mk.notna().to_numpy()
    x, y = mk.to_numpy()[ok], w.to_numpy()[ok]
    beta = float(np.cov(y, x)[0, 1] / np.var(x, ddof=1)) if ok.sum() > 2 and np.var(x) > 0 else None
    corr = float(np.corrcoef(y, x)[0, 1]) if ok.sum() > 2 and np.std(y) > 0 and np.std(x) > 0 else None
    return {"top_weeks_share": top / tot if tot > 0 else None, "top_weeks_sum": top,
            "neg_weeks": int((w < 0).sum()), "beta_to_market": beta, "corr_to_market": corr}


# --------------------------------------------------------------------------
def evaluate(P, pred1, other, q, mode, min_coins=MP.MIN_COINS, min_xs=MIN_XS, keep=False) -> dict:
    a_tr, b_tr = WF.WINDOWS["train"]
    a_va, b_va = WF.WINDOWS["valid"]
    forms = {f: transform(f, pred1, other, min_xs) for f in FORM}
    table = []
    for form, agree, sizing, cap in itertools.product(FORM, AGREE, SIZING, CAP):
        t, _ = MP.run_cell(P, forms[form][0], forms[form][1], a_tr, b_tr, agree, sizing, cap, q, mode)
        acc = MP.account(t, a_tr, b_tr)
        table.append({"form": form, "agree": agree, "sizing": sizing, "cap": cap, **{k: acc[k] for k in
                      ("trades", "weekly_mean", "tstat", "per_year", "max_dd", "mean_r")}})
        print(f"TRAIN-WF {form:>6} {agree:>3} {sizing:>4} cap {cap}: {acc['trades']} trades, weekly "
              f"{acc['weekly_mean']:+.5f}, t {acc['tstat']:+.2f}, dd {acc['max_dd']:.3f}", flush=True)
    ok = [x for x in table if x["trades"] >= MP.MIN_TRADES]
    best = max(ok, key=lambda x: x["tstat"]) if ok else table[0]
    p1, ot = forms[best["form"]]
    v, t = MP.judge(P, p1, ot, a_va, b_va, best["agree"], best["sizing"], best["cap"], q, mode, min_coins)
    v["diagnostics"] = diagnostics(t, P, a_va, b_va)
    gates = {"train_chose_demean": best["form"] == "demean",
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
    res = {"chosen": {k: best[k] for k in ("form", "agree", "sizing", "cap")}, "train_best": best,
           "train_table": table, "valid": v, "verdict": "REJECT" if failed else "PASS", "gates_failed": failed,
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
        if (MP.OUT / "holdout.json").exists():
            raise SystemExit("--final refused: sections 31 and 32 share one holdout and section 31 used it")
    elif res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    by_tf, _ = W3.load_all()
    spans = [WF.WINDOWS["train"], WF.WINDOWS["valid"]] + ([WF.WINDOWS["holdout"]] if final else [])
    other = {}
    for name, tf in MP.AGREE_TF.items():
        P_o, other[name] = MP.forecasts(by_tf, tf, spans)
        del P_o
    P, pred1 = MP.forecasts(by_tf, MP.TF_MAIN, spans)
    m = MP._cfg(MP.TF_MAIN)
    if final:
        ch = res["chosen"]
        p1, ot = transform(ch["form"], pred1, other)
        a, b = WF.WINDOWS["holdout"]
        h, t = MP.judge(P, p1, ot, a, b, ch["agree"], ch["sizing"], ch["cap"], m["q_in"], m["exit_mode"])
        h["diagnostics"] = diagnostics(t, P, a, b)
        h["verdict"] = ("CONFIRMED" if h["weekly_mean"] > 0 and h["ci_lo"] > 0 and h["shift_median"] is not None
                        and h["timing"] is not None and h["timing"] > h["shift_median"]
                        and h["breadth"]["share"] >= MP.BREADTH_SHARE else "FAILED")
        lock.write_text(json.dumps(h, indent=1, default=str))
        t.to_csv(OUT / "trades_holdout.csv.gz", index=False)
        write_report(res)
        print(json.dumps({k: h.get(k) for k in ("trades", "weekly_mean", "ci_lo", "verdict")}, indent=1))
        return
    res = evaluate(P, pred1, other, m["q_in"], m["exit_mode"], keep=True)
    res.pop("_trades").to_csv(OUT / "trades_valid.csv.gz", index=False)
    res_path.write_text(json.dumps(res, indent=1, default=str))
    write_report(res)
    print(f"\nML_XS: chose {res['chosen']} -> {res['verdict']} failed {res['gates_failed']}")


def write_report(r: dict) -> None:
    v, d = r["valid"], r["valid"]["diagnostics"]
    f = (lambda x, k=5: "-" if x is None else f"{x:+.{k}f}")
    L = ["# Cross-sectional (market-demeaned) forecasts on section 31's account (PLAN.md section 32)", "",
         "GENERATED by `src/ml_xs.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}** (TRAIN chose {r['chosen']}; failed: {r['gates_failed'] or 'none'})", "",
         f"- VALID {v['trades']} trades over {v['weeks']} weeks: weekly account return {f(v['weekly_mean'])}, "
         f"95% CI [{f(v['ci_lo'])}, {f(v['ci_hi'])}], t {v['tstat']:+.2f}; return per year {f(v['per_year'], 4)}, "
         f"max drawdown {v['max_dd']:.4f}",
         f"- mean R per trade {f(v['mean_r'], 4)}, risk-weighted {f(v['risk_weighted_r'], 4)}, average risk "
         f"{f(v['avg_risk'], 4)}; long {f(v['long_ret'], 4)} / short {f(v['short_ret'], 4)} (summed return)",
         f"- cost x1.5 weekly {f(v['stress_weekly_mean'])}; timing {f(v['timing'], 4)} vs shifted median "
         f"{f(v['shift_median'], 4)} / p95 {f(v['shift_p95'], 4)}; breadth {len(v['breadth']['beat'])} of "
         f"{v['breadth']['eligible']} ({v['breadth']['share']:.2f}); per year {v['per_year_r']}",
         f"- diagnostics: best {TOP_WEEKS} weeks = {f(d['top_weeks_share'], 3)} of the total; negative weeks "
         f"{d['neg_weeks']} of {v['weeks']}; beta to the equal-weight market {f(d['beta_to_market'], 3)}, "
         f"correlation {f(d['corr_to_market'], 3)}", "",
         "| form | agree | sizing | cap | TRAIN trades | weekly mean | t | per year | max DD |",
         "|---|---|---|---|---|---|---|---|---|"]
    for x in r["train_table"]:
        L.append(f"| {x['form']} | {x['agree']} | {x['sizing']} | {x['cap']} | {x['trades']} | "
                 f"{f(x['weekly_mean'])} | {x['tstat']:+.2f} | {f(x['per_year'], 4)} | {x['max_dd']:.4f} |")
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
    ap.add_argument("--final", action="store_true")
    run(ap.parse_args().final)


if __name__ == "__main__":
    main()
