"""ML volatility targeting: hold the ten coins long, sized by the forecast range (PLAN.md section 46)

    python src/ml_voltarget.py            # TRAIN/VALID, once (uses section 36's caches; no new download)
    python src/ml_voltarget.py --final    # HOLDOUT once, only after PASS (shared with sections 31-45)

Why (_multi Exp 087):
- The breakout line (sections 40-45) is exhausted, and its best book (section 43) works on 4h only.
- The one thing this project has shown to be forecastable is the size of the next day's range. Section 40's
  range model has a Spearman of +0.35 / +0.39 with the realised range, about 3.5x the persistence baseline
  (Exp 068).
- A volatility forecast is a risk tool before it is a timing tool. The owner chose this (2026-10-10, option 1).

Hypothesis: an equal-risk long book of the ten coins that scales each coin by target / forecast next-day range
has the following properties:
- it holds less before turbulent days and more before calm ones;
- crypto's worst days cluster in high-volatility spells, so it should beat buy-and-hold of the same coins on
  risk-adjusted return (Sharpe) and drawdown;
- if the ML forecast is better than a plain ATR estimate, it should also beat the same book sized by ATR alone.
The book is long-only, so it is measured against buy-and-hold, never against zero.

Books (all rebalanced once a day at the close of the 20:00 UTC 4h bar, filled at the next open, over the ten
coins while each is traded):
  bh      buy-and-hold: weight 1 / n per tradable coin
  naive   vol-target with the plain estimate: expected range = ATR fraction (ATR / close)
  ml      vol-target with section 40's forecast: expected range = forecast (range / ATR) x ATR fraction
For naive and ml:
- weight = min(CAP, target / expected range) / n;
- `target` is the median expected range of that estimator over TRAIN bars, which makes the average weight about
  1 / n on TRAIN (calibrated on TRAIN only, frozen for VALID/HOLDOUT);
- CAP = 2 (at most 2x a coin's equal share);
- a rebalance trades only when the weight moves by more than BAND = 20% of itself, or from or to 0.
Costs: taker fee + the coin's slippage on every traded weight. Funding: weight x rate at each settlement (a long
pays a positive rate). Returns are 4h open-to-open, with weights held between rebalances; daily returns are the
sum of the day's 4h returns.

Gates (pre-registered). PASS needs all of these on VALID:
- `ml_sharpe>bh`: Sharpe(ml) > Sharpe(bh), with the weekly-block bootstrap 95% CI lower bound of the difference
  > 0 (`ml_vs_bh_ci_lo>0`);
- `ml_dd<=0.6*bh`: max DD(ml) <= 0.6 x max DD(bh) (section 16's risk bar);
- `ml_sharpe>naive`: Sharpe(ml) > Sharpe(naive), on TRAIN too (`train_ml_sharpe>naive`): the ML must add
  something over the plain estimate;
- `stress_sharpe>bh`: with fees and slippage x1.5, Sharpe(ml) > Sharpe(bh).
No parameters are selected on TRAIN except each estimator's target.
Reported: CAGR, Sharpe, max DD, average gross exposure, turnover, by year, for all three books.
Holdout: sections 31-46 share ONE holdout.
Writes results/_multi/s46_ml_voltarget_4h/ and journal/_multi/s46_ml_voltarget_4h.md.
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
import ml_large as ML  # noqa: E402
import ml_port as MP  # noqa: E402
import ml_recent as MR  # noqa: E402
import ml_tf as MT  # noqa: E402
import ml_vol as MV  # noqa: E402
import ml_wf as WF  # noqa: E402
import ml_wf2 as W2  # noqa: E402
import ml_wide as MW  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "s46_ml_voltarget_4h"
REPORT = C.ROOT / "journal" / "_multi" / "s46_ml_voltarget_4h.md"

# ---- pre-registered (PLAN.md section 46, _multi Exp 088)
TF = MV.TF
DECISION_HOUR = 20                                # the 4h bar opening 20:00 UTC closes at midnight
CAP = 2.0
BAND = 0.20
DD_RATIO = 0.6
N_BOOT, SEED = 2000, 46
BOOKS = ("bh", "naive", "ml")
LOCKS = MT.LOCKS + (MT.OUT,)                      # sections 31-45: one shared holdout


# --------------------------------------------------------------------------
# pure pieces (test 44)
# --------------------------------------------------------------------------
def band_weights(want: np.ndarray, band: float = BAND) -> np.ndarray:
    """Held weight path: start flat; at each step move to `want` only if it differs from the held weight by more
    than band x held, or either is 0. NaN want = 0 (not tradable)."""
    want = np.nan_to_num(np.asarray(want, float))
    out, held = np.zeros(len(want)), 0.0
    for i, w in enumerate(want):
        if (held == 0) != (w == 0) or (held != 0 and abs(w - held) > band * abs(held)):
            held = w
        out[i] = held
    return out


def vt_weight(expected: np.ndarray, target: float, n: np.ndarray, cap: float = CAP) -> np.ndarray:
    """min(cap, target / expected) / n; NaN where the expected range or n is missing."""
    e = np.asarray(expected, float)
    n = np.asarray(n, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        w = np.minimum(cap, target / e) / n
    return np.where(np.isfinite(w) & (e > 0) & (n > 0), w, np.nan)


def sharpe(daily: pd.Series) -> float:
    d = pd.Series(daily).dropna()
    return float(d.mean() / d.std() * np.sqrt(365)) if len(d) > 2 and d.std() > 0 else 0.0


def max_dd(daily: pd.Series) -> float:
    eq = (1 + pd.Series(daily).fillna(0)).cumprod()
    return float((1 - eq / eq.cummax()).max()) if len(eq) else 0.0


def sharpe_diff_ci(a: pd.Series, b: pd.Series, n_boot: int = N_BOOT, seed: int = SEED) -> tuple[float, float, float]:
    """Sharpe(a) - Sharpe(b) and its weekly-block bootstrap 95% CI (the same weeks drawn for both)."""
    df = pd.concat([a, b], axis=1, keys=["a", "b"]).dropna()
    wk = df.index.tz_localize(None).to_period("W") if df.index.tz is not None else df.index.to_period("W")
    groups = [g.to_numpy() for _, g in df.groupby(wk)]
    rng = np.random.default_rng(seed)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        pick = np.concatenate([groups[j] for j in rng.integers(0, len(groups), len(groups))])
        x, y = pick[:, 0], pick[:, 1]
        sa = x.mean() / x.std() * np.sqrt(365) if x.std() > 0 else 0.0
        sb = y.mean() / y.std() * np.sqrt(365) if y.std() > 0 else 0.0
        diffs[i] = sa - sb
    return sharpe(df["a"]) - sharpe(df["b"]), float(np.quantile(diffs, 0.025)), float(np.quantile(diffs, 0.975))


# --------------------------------------------------------------------------
def panel(P, pred, traded) -> dict:
    """Per coin on its 4h trading bars: open-to-open return, ATR fraction, the ML range forecast at the decision
    bar, funding per bar, a tradable flag, and the decision-bar flag."""
    out = {}
    for c in P:
        tb = P[c].get("tbars", P[c]["bars"])
        idx = tb.index
        o = tb["open"].to_numpy(float)
        ret = np.r_[o[1:] / o[:-1] - 1.0, np.nan]                  # held through bar k: open[k] -> open[k+1]
        afrac = np.asarray(P[c]["atr"], float) / tb["close"].to_numpy(float)
        fc = np.full(len(idx), np.nan)
        k = P[c]["pos"]
        fc[k] = pred[c].reindex(P[c]["X"].index).to_numpy()
        fund = np.zeros(len(idx))
        f = P[c]["fund"]
        if f is not None and len(f):
            ft = pd.to_datetime(f["calc_time"], utc=True)
            pos = idx.searchsorted(ft, side="right") - 1              # settlement inside bar pos
            ok = (pos >= 0) & (pos < len(idx))
            np.add.at(fund, pos[ok], f["last_funding_rate"].to_numpy(float)[ok])
        allowed = MW.month_mask(idx, c, traded)
        out[c] = pd.DataFrame({"ret": ret, "afrac": afrac, "fc": fc, "fund": fund, "ok": allowed, "slip": P[c]["slip"],
                               "dec": idx.hour == DECISION_HOUR}, index=idx)
    return out


def expected_range(df: pd.DataFrame, book: str) -> np.ndarray:
    if book == "naive":
        return df["afrac"].to_numpy()
    return df["fc"].to_numpy() * df["afrac"].to_numpy()


def calibrate(pan: dict, book: str, a: str, b: str) -> float | None:
    """Median expected range over the TRAIN decision bars of every tradable coin."""
    if book == "bh":
        return None
    lo, hi = pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")
    x = np.concatenate([expected_range(d, book)[(d.index >= lo) & (d.index < hi) & d["dec"] & d["ok"]]
                        for d in pan.values()])
    x = x[np.isfinite(x) & (x > 0)]
    return float(np.median(x)) if len(x) else None


def run_book(pan: dict, book: str, target: float | None, a: str, b: str, stress: float = 1.0) -> dict:
    """Daily account returns and stats of one book on [a, b)."""
    lo, hi = pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")
    idx = sorted(set().union(*(d.index[(d.index >= lo) & (d.index < hi)] for d in pan.values())))
    idx = pd.DatetimeIndex(idx)
    # tradable coin count at each decision bar
    dec = {c: d.reindex(idx) for c, d in pan.items()}
    n = sum((d["dec"].fillna(False) & d["ok"].fillna(False)).astype(float) for d in dec.values())
    n = n.where(n > 0)
    total = pd.Series(0.0, index=idx)
    gross, turn = pd.Series(0.0, index=idx), 0.0
    for c, d in dec.items():
        isdec = d["dec"].fillna(False).to_numpy(bool)
        ok = d["ok"].fillna(False).to_numpy(bool)
        if book == "bh":
            want = np.where(ok, 1.0 / n.to_numpy(), np.nan)
        else:
            want = vt_weight(expected_range(d, book), target, n.to_numpy())
            want = np.where(ok, want, 0.0)
        # decide at decision bars, hold from the next bar until the next decision
        w_dec = np.where(isdec, np.nan_to_num(want), np.nan)
        held_dec = pd.Series(w_dec, index=idx).dropna()
        held_dec = pd.Series(band_weights(held_dec.to_numpy()), index=held_dec.index)
        w = held_dec.reindex(idx).shift(1).ffill().fillna(0.0)
        dw = w.diff().abs().fillna(w.abs())
        slip = float(pan[c]["slip"].iloc[0]) if "slip" in pan[c] else C.SLIPPAGE
        cost = dw * (C.FEE_TAKER + slip) * stress
        r = d["ret"].fillna(0.0)
        total += w * r - cost - w * d["fund"].fillna(0.0)
        gross += w.abs()
        turn += float(dw.sum())
    daily = total.groupby(total.index.floor("D")).sum()
    yrs = {str(y): float((1 + g).prod() - 1) for y, g in daily.groupby(daily.index.year)}
    n_days = len(daily)
    cagr = float((1 + daily).prod() ** (365 / n_days) - 1) if n_days else 0.0
    return {"daily": daily, "sharpe": sharpe(daily), "max_dd": max_dd(daily), "cagr": cagr, "by_year": yrs,
            "avg_gross": float(gross.mean()), "turnover_per_year": turn / max(n_days / 365, 1e-9)}


def evaluate(pan: dict) -> dict:
    a_tr, b_tr = WF.WINDOWS["train"]
    a_va, b_va = WF.WINDOWS["valid"]
    targets = {bk: calibrate(pan, bk, a_tr, b_tr) for bk in BOOKS}
    res = {"targets": targets, "train": {}, "valid": {}}
    for split, (a, b) in (("train", (a_tr, b_tr)), ("valid", (a_va, b_va))):
        books = {bk: run_book(pan, bk, targets[bk], a, b) for bk in BOOKS}
        d_bh = sharpe_diff_ci(books["ml"]["daily"], books["bh"]["daily"])
        d_nv = sharpe_diff_ci(books["ml"]["daily"], books["naive"]["daily"])
        stress = run_book(pan, "ml", targets["ml"], a, b, stress=1.5)
        stress_bh = run_book(pan, "bh", None, a, b, stress=1.5)
        res[split] = {bk: {k: v for k, v in x.items() if k != "daily"} for bk, x in books.items()}
        res[split]["ml_vs_bh"] = {"diff": d_bh[0], "ci_lo": d_bh[1], "ci_hi": d_bh[2]}
        res[split]["ml_vs_naive"] = {"diff": d_nv[0], "ci_lo": d_nv[1], "ci_hi": d_nv[2]}
        res[split]["stress"] = {"ml_sharpe": stress["sharpe"], "bh_sharpe": stress_bh["sharpe"]}
        res[split]["_daily"] = {bk: x["daily"] for bk, x in books.items()}
        print(f"{split}: " + ", ".join(f"{bk} Sharpe {x['sharpe']:+.2f} DD {x['max_dd']:.2%} CAGR {x['cagr']:+.1%}"
                                       for bk, x in books.items()), flush=True)
    v, t = res["valid"], res["train"]
    gates = {"train_ml_sharpe>naive": t["ml"]["sharpe"] > t["naive"]["sharpe"],
             "ml_sharpe>bh": v["ml"]["sharpe"] > v["bh"]["sharpe"],
             "ml_vs_bh_ci_lo>0": v["ml_vs_bh"]["ci_lo"] > 0,
             f"ml_dd<={DD_RATIO}*bh": v["ml"]["max_dd"] <= DD_RATIO * v["bh"]["max_dd"],
             "ml_sharpe>naive": v["ml"]["sharpe"] > v["naive"]["sharpe"],
             "stress_sharpe>bh": v["stress"]["ml_sharpe"] > v["stress"]["bh_sharpe"]}
    res["gates_failed"] = [k for k, g in gates.items() if not g]
    res["verdict"] = "REJECT" if res["gates_failed"] else "PASS"
    res["model"] = {"tf": TF, "coins": list(ML.COINS), "cap": CAP, "band": BAND, "decision_hour_utc": DECISION_HOUR,
                    "dd_ratio": DD_RATIO, "range_model": "section 40 (next 6 bars' range / ATR)"}
    return res


def _check_s40(PT, pred) -> bool | None:
    f = MV.OUT / "record" / "train" / "predictions.parquet"
    if not f.exists():
        return None
    ref = pd.read_parquet(f)
    got = pd.concat([pd.DataFrame({"time": pred[c].index, "coin": c, "mine": pred[c].to_numpy()}) for c in PT])
    m = ref.merge(got, on=["time", "coin"], how="inner")
    ok = np.isfinite(m["forecast"]) & np.isfinite(m["mine"])
    return bool(len(m) and ok.any() and np.allclose(m.loc[ok, "forecast"], m.loc[ok, "mine"], atol=1e-5))


def run(final: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    res_path, lock = OUT / "summary.json", OUT / "holdout.json"
    if final:
        res = json.loads(res_path.read_text()) if res_path.exists() else None
        if not res or res["verdict"] != "PASS":
            raise SystemExit("--final refused: needs a PASS from the TRAIN/VALID run")
        for o in (OUT,) + LOCKS:
            if (o / "holdout.json").exists():
                raise SystemExit(f"--final refused: sections 31-46 share one holdout and {o.name} used it")
    elif res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    if not (MW.OUT / "members.json").exists():
        raise SystemExit("no section 36 member sets: run  python src/ml_wide.py --build  first")
    months, traded, by_tf, core, members = MR._load()
    spans = [WF.WINDOWS["train"], WF.WINDOWS["valid"]] + ([WF.WINDOWS["holdout"]] if final else [])
    print(f"[ml_voltarget] training coins {len(by_tf[TF])}; traded {len(ML.COINS)}", flush=True)
    P = W2.prepare(by_tf, TF)
    del by_tf
    gc.collect()
    masks = {c: MW.training_mask(P[c]["X"].index, c, core, members, True) for c in P}
    pred_all = MV.forecasts(P, MP._cfg(TF)["setting"], masks, spans)
    PT = {c: P[c] for c in ML.COINS if c in P}
    pred = {c: pred_all[c] for c in PT}
    pan = panel(PT, pred, traded)
    if final:
        a, b = WF.WINDOWS["holdout"]
        books = {bk: run_book(pan, bk, res["targets"][bk], a, b) for bk in BOOKS}
        d = sharpe_diff_ci(books["ml"]["daily"], books["bh"]["daily"])
        h = {bk: {k: v for k, v in x.items() if k != "daily"} for bk, x in books.items()}
        h["ml_vs_bh"] = {"diff": d[0], "ci_lo": d[1], "ci_hi": d[2]}
        h["verdict"] = ("CONFIRMED" if books["ml"]["sharpe"] > books["bh"]["sharpe"]
                        and books["ml"]["max_dd"] <= DD_RATIO * books["bh"]["max_dd"]
                        and books["ml"]["sharpe"] > books["naive"]["sharpe"] else "FAILED")
        lock.write_text(json.dumps(h, indent=1, default=str))
        write_report(res)
        print(json.dumps({k: h[k] for k in ("verdict", "ml_vs_bh")}, indent=1, default=str))
        return
    res = evaluate(pan)
    res["reproduces_s40"] = _check_s40(PT, pred)
    print(f"reproduces section 40's range forecasts: {res['reproduces_s40']}", flush=True)
    for split in ("train", "valid"):
        daily = res[split].pop("_daily")
        pd.DataFrame(daily).to_csv(OUT / f"daily_{split}.csv.gz")
    res_path.write_text(json.dumps(res, indent=1, default=str))
    write_report(res)
    print(f"\nML_VOLTARGET: {res['verdict']} failed {res['gates_failed']}")


def write_report(r: dict) -> None:
    f = (lambda x, k=2: "-" if x is None else f"{x:+.{k}f}")
    L = ["# ML volatility targeting: the ten coins long, sized by the forecast range (PLAN.md section 46)", "",
         "GENERATED by `src/ml_voltarget.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}** (failed: {r['gates_failed'] or 'none'})", "",
         f"- reproduces section 40's range forecasts: {r.get('reproduces_s40')}; targets (TRAIN medians): "
         f"{r['targets']}", ""]
    for split in ("train", "valid"):
        s = r[split]
        L += [f"### {split.upper()}", "", "| book | Sharpe | max DD | CAGR | avg gross | turnover / yr | by year |",
              "|---|---|---|---|---|---|---|"]
        for bk in BOOKS:
            x = s[bk]
            L.append(f"| {bk} | {x['sharpe']:+.2f} | {x['max_dd']:.1%} | {x['cagr']:+.1%} | {x['avg_gross']:.2f} | "
                     f"{x['turnover_per_year']:.1f} | {{{', '.join(f'{k}: {v:+.1%}' for k, v in x['by_year'].items())}}} |")
        L += ["", f"- Sharpe ml - bh {f(s['ml_vs_bh']['diff'])} (95% CI [{f(s['ml_vs_bh']['ci_lo'])}, "
                  f"{f(s['ml_vs_bh']['ci_hi'])}]); ml - naive {f(s['ml_vs_naive']['diff'])} (CI "
                  f"[{f(s['ml_vs_naive']['ci_lo'])}, {f(s['ml_vs_naive']['ci_hi'])}]); costs x1.5: ml "
                  f"{f(s['stress']['ml_sharpe'])} vs bh {f(s['stress']['bh_sharpe'])}", ""]
    hp = OUT / "holdout.json"
    if hp.exists():
        h = json.loads(hp.read_text())
        L += [f"## HOLDOUT: **{h['verdict']}** - ml Sharpe {h['ml']['sharpe']:+.2f} vs bh {h['bh']['sharpe']:+.2f}, "
              f"DD {h['ml']['max_dd']:.1%} vs {h['bh']['max_dd']:.1%}"]
    REPORT.write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--final", action="store_true", help="run the holdout once (needs PASS)")
    run(ap.parse_args().final)


if __name__ == "__main__":
    main()
