"""Result Analyzer: a quality report card for every recorded ML run (read-only)

    python src/analyzer.py

Reads ONLY recorded results (summary/tf JSON files and VALID trade files under
results/). It runs no backtest, refits nothing and never reads the holdout. It
scores every ML run on seven dimensions, each 0-100 (None when the recorded
data cannot support it), and gives a verdict:

  1 Train vs Valid      VALID mean R as a share of the chosen TRAIN cell's mean R
  2 OOS robustness      share of the recorded robustness checks passed: CI lower
                        bound > 0, cost x1.5 > 0, timing above the control's p95,
                        breadth >= half, both legs > 0
  3 Stability           concentration (best 5 weeks' share of the total), coin
                        breadth (coins with >= 10 trades and a positive sum), and
                        the mean without the top 1% of trades
  4 Fold consistency    the walk-forward refits monthly, so each VALID month is
                        one fold: share of positive months, both years positive
  5 Parameter sens.     the TRAIN grid: share of cells with a positive selection
                        metric, and whether the chosen cell is an isolated peak
  6 Performance decay   VALID by entry year (2023, 2024): both positive?
  7 Overfit check       penalties: TRAIN > 0 but VALID <= 0, VALID < 30% of
                        TRAIN, an isolated peak, a return carried by a few weeks

  Quality score = mean of the available dimensions. Runs without a recorded VALID
  trade file (§19-§21) have only 3-4 dimensions; they are listed after the others.
  Verdict (a score never overrides a failed gate):
    NO_EDGE  the chosen TRAIN cell itself was not positive
    OVERFIT  positive on TRAIN, not on VALID (or the overfit check < 40)
    ACCEPT   every pre-registered gate passed AND the quality score >= 70
    FRAGILE  everything else: positive on VALID but a gate failed or the score < 70

Limits stated: TRAIN trades were never saved, so fold consistency covers VALID
only; TRAIN grids have 2-32 coarse cells, so sensitivity is rough; no ML run has
used the holdout, so decay is measured inside VALID only.
Writes results/_multi/analyzer/report.json, journal/_multi/analyzer.md (both
GENERATED) and docs/analyzer_data.json for docs/analyzer.html.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

R = C.ROOT / "results"
M = R / "_multi"
OUT = M / "analyzer"
REPORT = C.ROOT / "journal" / "_multi" / "analyzer.md"
DOCS = C.ROOT / "docs" / "analyzer_data.json"
VALID = ("2023-01-01", "2025-01-01")
ACCEPT_SCORE = 70

# id, section, label, summary file, VALID trades file (or None), kind
RUNS = [("s19_btc", 19, "§19 ML entry · BTC", R / "BTCUSDT/ml_entry/summary.json", None, "entry"),
        ("s19_eth", 19, "§19 ML entry · ETH", R / "ETHUSDT/ml_entry/summary.json", None, "entry"),
        ("s20", 20, "§20 pooled · 20 coins", M / "ml_pool/summary.json", None, "entry"),
        ("s21", 21, "§21 pooled round 2", M / "ml_pool2/summary.json", None, "pool2"),
        ("s27", 27, "§27 entry + exit · 20 coins", M / "ml_hold/summary.json", M / "ml_hold/trades_valid.csv.gz", "hold")]
for sec, d in ((28, "ml_wf"), (29, "ml_wf2"), (30, "ml_wf3")):
    for tf, nm in ((60, "1h"), (240, "4h"), (1440, "1d")):
        RUNS.append((f"s{sec}_{nm}", sec, f"§{sec} {nm}", M / d / f"tf{tf}.json", M / d / f"trades_valid_tf{tf}.csv.gz", "wf"))
RUNS += [("s31", 31, "§31 1h + portfolio", M / "ml_port/summary.json", M / "ml_port/trades_valid.csv.gz", "account"),
         ("s32", 32, "§32 demeaned (= §31)", M / "ml_xs/summary.json", M / "ml_xs/trades_valid.csv.gz", "account"),
         ("s33", 33, "§33 market timing → ETH", M / "ml_mkt/summary.json", M / "ml_mkt/trades_valid.csv.gz", "account"),
         ("s34", 34, "§34 positioning data (= §31)", M / "ml_flow/summary.json", M / "ml_flow/trades_valid.csv.gz", "account"),
         ("s36", 36, "§36 train wide · top 20 large coins", M / "ml_wide/summary.json", M / "ml_wide/trades_valid.csv.gz",
          "account"),
         ("s37", 37, "§37 4h model · 10 large coins", M / "ml_large/summary.json", M / "ml_large/trades_valid.csv.gz",
          "account")]
# TRAIN trade files exist from §36 on (trades_train_<form>.csv.gz, the chosen form is read)
TRAIN = ("2021-01-01", "2023-01-01")


def _clip(x: float) -> float:
    return float(min(max(x, 0.0), 1.0))


# --------------------------------------------------------------------------
# read one recorded run into a common shape
# --------------------------------------------------------------------------
def extract(kind: str, r: dict) -> dict:
    """Common fields from one recorded summary."""
    v = r.get("valid", {})
    e = {"verdict": r.get("verdict", "REJECT"), "gates_failed": r.get("gates_failed", []),
         "valid_mean": v.get("mean_r"), "ci_lo": v.get("ci_lo"), "checks": {}, "table": [], "chosen_metric": None,
         "train_mean": None, "per_year": v.get("per_year")}
    if kind == "wf":
        best, table, key = r.get("train_wf_best", {}), r.get("train_wf_table", []), "mean_r"
        e["train_mean"] = best.get("mean_r")
        e["checks"] = {"ci_lo>0": v.get("ci_lo", -1) > 0, "stress>0": (v.get("stress_mean_r") or -1) > 0,
                       "timing>p95": v.get("timing") is not None and v.get("shift_p95") is not None
                       and v["timing"] > v["shift_p95"],
                       "breadth>=0.5": v.get("breadth", {}).get("share", 0) >= 0.5,
                       "both_legs>0": (v.get("long_r") or -1) > 0 and (v.get("short_r") or -1) > 0}
    elif kind == "hold":
        best, table, key = r.get("oof_best", {}), r.get("oof_table", []), "mean_r"
        e["train_mean"] = best.get("mean_r")
        e["checks"] = {"ci_lo>0": v.get("ci_lo", -1) > 0, "stress>0": r.get("valid_stress", {}).get("mean_r", -1) > 0,
                       "timing>p95": r.get("timing") is not None and r.get("shift_p95") is not None
                       and r["timing"] > r["shift_p95"],
                       "breadth>=0.5": r.get("breadth", {}).get("share", 0) >= 0.5,
                       "both_legs>0": v.get("long_r", -1) > 0 and v.get("short_r", -1) > 0}
    elif kind == "account":
        table, key = r.get("train_table", []), "tstat"
        ch = r.get("chosen", {})
        best = r.get("train_best") or next((x for x in table if all(x.get(k) == ch.get(k) for k in ch if k in x)), {})
        e["train_mean"] = best.get("mean_r")
        e["ci_lo"] = v.get("ci_lo")
        e["checks"] = {"ci_lo>0": v.get("ci_lo", -1) > 0, "stress>0": (v.get("stress_weekly_mean") or -1) > 0,
                       "timing>p95": v.get("timing") is not None and v.get("shift_p95") is not None
                       and v["timing"] > v["shift_p95"],
                       "both_legs>0": v.get("long_ret", -1) > 0 and v.get("short_ret", -1) > 0}
        if "breadth" in v:
            e["checks"]["breadth>=0.5"] = v["breadth"].get("share", 0) >= 0.5
    elif kind == "pool2":
        best, table, key = r.get("oof_best", {}), r.get("oof_table", []), "mean_r"
        e["train_mean"] = best.get("mean_r")
        e["checks"] = {"ci_lo>0": v.get("ci_lo", -1) > 0, "stress>0": r.get("valid_stress", {}).get("mean_r", -1) > 0,
                       "timing>p95": r.get("shift_gross_p95") is not None and v.get("gross_r", -1) > r["shift_gross_p95"],
                       "breadth>=0.5": r.get("breadth", {}).get("share", 0) >= 0.5,
                       "both_legs>0": v.get("long_r", -1) > 0 and v.get("short_r", -1) > 0}
    else:                                                    # entry: oof = {threshold: {trades, mean_r}}
        oof, th = r.get("oof") or {}, r.get("threshold")
        table = [{"cell": k, "mean_r": x.get("mean_r")} for k, x in oof.items()] if isinstance(oof, dict) else []
        key = "mean_r"
        best = (oof.get(str(th)) or oof.get(f"{th}") or {}) if isinstance(oof, dict) else {}
        if not best and isinstance(oof, dict) and th is not None:
            best = next((x for k, x in oof.items() if abs(float(k) - float(th)) < 1e-9), {})
        e["train_mean"] = best.get("mean_r")
        e["checks"] = {"ci_lo>0": v.get("ci_lo", -1) > 0, "stress>0": r.get("valid_stress", {}).get("mean_r", -1) > 0,
                       "timing>p95": r.get("random_p95") is not None and (v.get("mean_r") or -1) > r["random_p95"],
                       "both_legs>0": v.get("long_r", -1) > 0 and v.get("short_r", -1) > 0}
        if "breadth" in r:
            e["checks"]["breadth>=0.5"] = r["breadth"].get("share", 0) >= 0.5
    vals = [x.get(key) for x in table if x.get(key) is not None]
    e["table"] = [float(x) for x in vals]
    e["chosen_metric"] = best.get(key) if isinstance(best, dict) else None
    e["select_key"] = key
    return e


# --------------------------------------------------------------------------
# the seven dimensions
# --------------------------------------------------------------------------
def weekly_returns(t: pd.DataFrame, win=VALID) -> pd.Series:
    """Account return per VALID week by exit time (empty weeks 0); a trade without
    a recorded risk counts at 1% risk."""
    ret = t["ret"] if "ret" in t else 0.01 * t["net_r"]
    weeks = pd.date_range(pd.Timestamp(win[0], tz="UTC"), pd.Timestamp(win[1], tz="UTC"), freq="7D", inclusive="left")
    k = np.clip(weeks.searchsorted(pd.to_datetime(t["exit_time"], utc=True), side="right") - 1, 0, len(weeks) - 1)
    return pd.Series(np.bincount(k, weights=ret.to_numpy(float), minlength=len(weeks)), index=weeks)


def train_vs_valid(train_mean, valid_mean) -> tuple[float | None, dict]:
    if train_mean is None or valid_mean is None:
        return None, {}
    ratio = valid_mean / train_mean if train_mean > 0 else None
    score = 0.0 if (train_mean <= 0 or valid_mean <= 0) else 100 * _clip(ratio / 0.7)
    return score, {"train_mean_r": train_mean, "valid_mean_r": valid_mean, "valid_over_train": ratio}


def robustness(checks: dict) -> tuple[float | None, dict]:
    if not checks:
        return None, {}
    return 100 * sum(bool(x) for x in checks.values()) / len(checks), {k: bool(x) for k, x in checks.items()}


def stability(t: pd.DataFrame | None) -> tuple[float | None, dict]:
    if t is None or t.empty:
        return None, {}
    w = weekly_returns(t)
    tot = float(w.sum())
    conc = float(w.sort_values(ascending=False).iloc[:5].sum()) / tot if tot > 0 else None
    by = t.groupby("coin")["net_r"].agg(["sum", "size"])
    by = by[by["size"] >= 10]
    coin_share = float((by["sum"] > 0).mean()) if len(by) >= 2 else None
    r = np.sort(t["net_r"].to_numpy())[::-1]
    k = max(1, int(round(len(r) * 0.01)))
    trim = float(r[k:].mean()) if len(r) > k else None
    parts = [0.0 if conc is None else 100 * _clip((1.0 - conc) / 0.7),
             None if coin_share is None else 100 * _clip((coin_share - 0.4) / 0.3),
             None if trim is None else (100.0 if trim > 0 else 0.0)]
    parts = [p for p in parts if p is not None]
    return float(np.mean(parts)), {"top5_weeks_share": conc, "coins_positive_share": coin_share,
                                   "mean_r_without_top1pct": trim, "valid_total_return": tot}


def fold_consistency(t: pd.DataFrame | None, win=VALID) -> tuple[float | None, dict]:
    if t is None or t.empty:
        return None, {}
    ex = pd.to_datetime(t["exit_time"], utc=True)
    m = (t["ret"] if "ret" in t else 0.01 * t["net_r"]).groupby(ex.dt.strftime("%Y-%m")).sum()
    months = [str(p) for p in pd.period_range(win[0], pd.Timestamp(win[1]) - pd.Timedelta(days=1), freq="M")]
    m = m.reindex(months, fill_value=0.0)
    share = float((m > 0).mean())
    yrs = m.groupby([k[:4] for k in m.index]).sum()
    both = bool((yrs > 0).all())
    streak = cur = 0
    for v in m:
        cur = cur + 1 if v < 0 else 0
        streak = max(streak, cur)
    score = 70 * _clip((share - 0.4) / 0.4) + (30 if both else 0)
    return score, {"months_positive": int((m > 0).sum()), "months": len(m), "years_positive": both,
                   "longest_losing_months": streak}


def sensitivity(table: list, chosen) -> tuple[float | None, dict]:
    if len(table) < 2 or chosen is None:
        return None, {}
    x = np.asarray(table, float)
    share = float((x > 0).mean())
    sd = float(x.std())
    z = (float(chosen) - float(np.median(x))) / sd if sd > 0 else 0.0
    isolated = z > 2.0
    return 100 * _clip(share) * (0.5 if isolated else 1.0), {"cells": len(x), "cells_positive_share": share,
                                                            "chosen_z_vs_grid": z, "isolated_peak": isolated}


def decay(t: pd.DataFrame | None, per_year: dict | None) -> tuple[float | None, dict]:
    if t is not None and not t.empty:
        y = t.groupby(pd.to_datetime(t["entry_time"], utc=True).dt.year)["net_r"].mean()
        yr = {str(k): float(v) for k, v in y.items() if 2023 <= k <= 2024}
    elif per_year:
        yr = {k: float(v) for k, v in per_year.items() if k in ("2023", "2024")}
    else:
        return None, {}
    if not yr:
        return None, {}
    return 100 * sum(v > 0 for v in yr.values()) / len(yr), {"mean_r_by_entry_year": yr}


def overfit(train_mean, valid_mean, tv: dict, sens: dict, stab: dict) -> tuple[float | None, dict]:
    if train_mean is None or valid_mean is None:
        return None, {}
    flags = []
    if train_mean > 0 and valid_mean <= 0:
        flags.append(("positive on TRAIN, not on VALID", 60))
    ratio = tv.get("valid_over_train")
    if ratio is not None and 0 < ratio < 0.3:
        flags.append(("VALID under 30% of TRAIN", 20))
    if sens.get("isolated_peak"):
        flags.append(("chosen cell is an isolated peak", 20))
    if stab.get("top5_weeks_share") is not None and stab["top5_weeks_share"] > 0.6:
        flags.append(("best 5 weeks carry > 60% of the return", 20))
    return float(max(0, 100 - sum(p for _, p in flags))), {"flags": [f for f, _ in flags]}


def verdict(e: dict, score: float | None, of: float | None) -> str:
    tm, vm = e.get("train_mean"), e.get("valid_mean")
    if tm is not None and tm <= 0:
        return "NO_EDGE"
    if (vm is not None and vm <= 0) or (of is not None and of < 40):
        return "OVERFIT"
    if e.get("verdict") == "PASS" and score is not None and score >= ACCEPT_SCORE:
        return "ACCEPT"
    return "FRAGILE"


def train_side(summary: dict, tt: pd.DataFrame | None) -> dict | None:
    """Where TRAIN trades / TRAIN checks were recorded (§36 on): the same measures on TRAIN, to set beside VALID."""
    tc = summary.get("train_checks")
    if tt is None and not tc:
        return None
    out = {}
    if tt is not None and not tt.empty:
        w = weekly_returns(tt, TRAIN)
        tot = float(w.sum())
        out["top5_weeks_share"] = float(w.sort_values(ascending=False).iloc[:5].sum()) / tot if tot > 0 else None
        out["folds"] = fold_consistency(tt, TRAIN)[1]
        out["fold_score"] = fold_consistency(tt, TRAIN)[0]
    if tc:
        out["checks"] = {"ci_lo>0": (tc.get("ci_lo") or -1) > 0, "stress>0": (tc.get("stress_weekly_mean") or -1) > 0,
                         "timing>p95": tc.get("timing") is not None and tc.get("shift_p95") is not None
                         and tc["timing"] > tc["shift_p95"],
                         "breadth>=0.5": tc.get("breadth", {}).get("share", 0) >= 0.5,
                         "both_legs>0": (tc.get("long_ret") or -1) > 0 and (tc.get("short_ret") or -1) > 0}
    return out


def analyze_one(kind: str, summary: dict, trades: pd.DataFrame | None, train_trades: pd.DataFrame | None = None) -> dict:
    e = extract(kind, summary)
    dims = {}
    dims["train_vs_valid"] = train_vs_valid(e["train_mean"], e["valid_mean"])
    dims["robustness"] = robustness(e["checks"])
    dims["stability"] = stability(trades)
    dims["fold_consistency"] = fold_consistency(trades)
    ts = train_side(summary, train_trades)
    if ts and ts.get("fold_score") is not None and dims["fold_consistency"][0] is not None:
        # both periods recorded: the score is the mean of TRAIN's and VALID's monthly folds
        sc_, det = dims["fold_consistency"]
        dims["fold_consistency"] = ((sc_ + ts["fold_score"]) / 2, {**det, "train": ts["folds"]})
    dims["sensitivity"] = sensitivity(e["table"], e["chosen_metric"])
    dims["decay"] = decay(trades, e["per_year"])
    dims["overfit"] = overfit(e["train_mean"], e["valid_mean"], dims["train_vs_valid"][1], dims["sensitivity"][1],
                              dims["stability"][1])
    sc = [d[0] for d in dims.values() if d[0] is not None]
    score = float(np.mean(sc)) if sc else None
    return {"scores": {k: (None if d[0] is None else round(d[0], 1)) for k, d in dims.items()},
            "details": {k: d[1] for k, d in dims.items()}, "quality": None if score is None else round(score, 1),
            "verdict": verdict(e, score, dims["overfit"][0]), "gate_verdict": e["verdict"],
            "gates_failed": e["gates_failed"], "valid_mean_r": e["valid_mean"], "train_mean_r": e["train_mean"],
            "trades_recorded": trades is not None, "dims_available": len(sc), "train_side": ts}


def _order(r: dict) -> tuple:
    return (not r["trades_recorded"], -(r["quality"] or -1))


# --------------------------------------------------------------------------
def main() -> None:
    rows = []
    for rid, sec, label, sfile, tfile, kind in RUNS:
        if not sfile.exists():
            continue
        s = json.loads(sfile.read_text())
        t = pd.read_csv(tfile) if tfile is not None and tfile.exists() else None
        form = (s.get("chosen") or {}).get("form")
        tr = sfile.parent / f"trades_train_{form}.csv.gz"
        a = analyze_one(kind, s, t, pd.read_csv(tr) if form and tr.exists() else None)
        rows.append({"id": rid, "sec": sec, "label": label, **a})
    OUT.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=_order)
    payload = {"generated_by": "src/analyzer.py", "accept_score": ACCEPT_SCORE, "runs": rows}
    txt = json.dumps(payload, indent=1, default=lambda o: o if not isinstance(o, (np.floating, np.bool_)) else o.item())
    (OUT / "report.json").write_text(txt)
    DOCS.write_text(json.dumps(payload, separators=(",", ":"), default=lambda o: o.item()))
    f = lambda x: "-" if x is None else f"{x:.0f}"
    L = ["# Result Analyzer: quality report card of every ML run", "", "GENERATED by `src/analyzer.py` (read-only: "
         "recorded results only, no backtest, no holdout). Do not edit by hand.", "",
         "| run | verdict | quality | train vs valid | robustness | stability | folds | sensitivity | decay | overfit | gates |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=_order):
        s = r["scores"]
        L.append(f"| {r['label']} | **{r['verdict']}** | {f(r['quality'])} | {f(s['train_vs_valid'])} | {f(s['robustness'])} | "
                 f"{f(s['stability'])} | {f(s['fold_consistency'])} | {f(s['sensitivity'])} | {f(s['decay'])} | "
                 f"{f(s['overfit'])} | {r['gate_verdict']} |")
    REPORT.write_text("\n".join(L) + "\n")
    print(f"analyzed {len(rows)} runs -> {OUT / 'report.json'}, {DOCS}")
    for r in sorted(rows, key=_order):
        print(f"  {r['label']:<32} {r['verdict']:<8} {f(r['quality']):>4}  {r['scores']}")


if __name__ == "__main__":
    main()
