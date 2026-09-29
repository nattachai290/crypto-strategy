"""What the recorded evaluations teach, across every coin (owner request).

    python src/meta_lessons.py

Reads only what evaluate.py / baseline.py / benchmark.py already wrote -
results/<SYMBOL>/evaluations.csv, holdout_log.csv, baseline/*.json,
benchmark/*.json and eval_trades/*_valid.csv.gz - for every symbol in
config.SYMBOL_SPECS. It runs no backtest and loads no market data.

Writes (cross-coin output, AGENTS.md section 6):
    results/_multi/meta_lessons/summary.json   every table, machine-readable
    journal/_multi/meta_lessons.md             GENERATED, do not edit by hand

Read it with two cautions, which the report repeats:
  * Rows are not independent. The 7 timeframe variants of one idea, and the
    same idea on several coins, are one hypothesis seen many times. Every
    table therefore also shows `ideas` (distinct idea files after stripping
    the _tfN suffix) and `idea_mean` (each idea counted once).
  * Most outcomes here are VALID results. Choosing the next ideas by what did
    well on VALID is a mild form of tuning on VALID, so a lesson is marked
    robust only when TRAIN points the same way, and the holdout stays the
    only test that counts.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

OUT_DIR = C.ROOT / "results" / "_multi" / "meta_lessons"
MD = C.ROOT / "journal" / "_multi" / "meta_lessons.md"


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------
def _idea_base(name: str) -> str:
    return re.sub(r"_tf\d+(_time)?$", "", str(name))


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, holds = [], []
    for sym in C.SYMBOL_SPECS:
        res = C.ROOT / "results" / sym
        f = res / "evaluations.csv"
        if not f.exists():
            continue
        d = pd.read_csv(f)
        # a --final run appends a second row for the same eval_id: keep the last
        d = d.drop_duplicates("eval_id", keep="last").copy()
        d["symbol"] = sym
        for kind in ("baseline", "benchmark"):
            got = {}
            for j in (res / kind).glob("*.json"):
                try:
                    got[j.stem] = json.loads(j.read_text())
                except (OSError, ValueError):
                    continue
            d[kind] = d["eval_id"].map(lambda e: (got.get(e) or {}).get("verdict"))
        rows.append(d)
        h = res / "holdout_log.csv"
        if h.exists():
            hl = pd.read_csv(h)
            hl["symbol"] = sym
            holds.append(hl)
    ev = pd.concat(rows, ignore_index=True)
    ev["idea"] = ev["name"].map(_idea_base)
    parts = ev["structure"].fillna("").str.split("|")
    ev["trigger"] = parts.str[2].fillna("?")
    ev["filters"] = parts.str[3].fillna("")
    ev["n_filters"] = ev["filters"].map(lambda s: 0 if not s else len(s.split("+")))
    ev["direction"] = parts.str[4].fillna("?")
    p = ev["chosen_params"].map(lambda s: json.loads(s) if isinstance(s, str) else {})
    ev["stop_type"] = p.map(lambda q: (q.get("stop") or {}).get("type", "atr"))
    ev["tp_type"] = p.map(lambda q: (q.get("tp") or {}).get("type", "none"))
    ev["trailing"] = p.map(lambda q: bool(q.get("trail_at", 0) and q.get("trail_atr", 0)))
    ev["valid_se"] = (ev["valid_ci_hi"] - ev["valid_ci_lo"]) / 3.92
    ev["valid_z"] = ev["valid_mean_r"] / ev["valid_se"].replace(0, np.nan)
    hold = pd.concat(holds, ignore_index=True) if holds else pd.DataFrame()
    return ev, hold


# --------------------------------------------------------------------------
# tables
# --------------------------------------------------------------------------
def group_table(ev: pd.DataFrame, key: str, order=None) -> pd.DataFrame:
    """Per group: rows, distinct ideas, mean/median VALID R, share VALID > 0,
    mean TRAIN R, and the idea-weighted mean (each idea once)."""
    d = ev.dropna(subset=["valid_mean_r"])
    g = d.groupby(key, observed=True)
    t = pd.DataFrame({
        "rows": g.size(),
        "ideas": g["idea"].nunique(),
        "train_mean": g["train_mean_r"].mean(),
        "valid_mean": g["valid_mean_r"].mean(),
        "valid_median": g["valid_mean_r"].median(),
        "valid_pos_share": g["valid_mean_r"].apply(lambda s: (s > 0).mean()),
        "idea_mean": d.groupby([key, "idea"], observed=True)["valid_mean_r"].mean()
                      .groupby(level=0, observed=True).mean(),
        "cost_r": g["valid_cost_r"].median(),
        "pass_watch": g["verdict"].apply(lambda s: s.isin(["PASS", "WATCH"]).sum()),
    })
    t["robust"] = np.where((t["train_mean"] > 0) & (t["valid_mean"] > 0) & (t["idea_mean"] > 0)
                           & (t["ideas"] >= 3), "yes", "")
    if order is not None:
        t = t.reindex([o for o in order if o in t.index])
    return t


def _bucket(s: pd.Series, edges, labels) -> pd.Series:
    return pd.cut(s, edges, labels=labels, right=False)


def side_and_year(ev: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pooled VALID trades per evaluation: mean R by side and by year."""
    side_rows, year_rows = [], []
    for r in ev.itertuples():
        f = C.ROOT / "results" / r.symbol / "eval_trades" / f"{r.eval_id}_valid.csv.gz"
        if not f.exists():
            continue
        t = pd.read_csv(f, usecols=["entry_time", "side", "r_multiple"])
        if t.empty:
            continue
        for s, lab in ((1, "long"), (-1, "short")):
            x = t.loc[t["side"] == s, "r_multiple"]
            if len(x):
                side_rows.append({"symbol": r.symbol, "idea": r.idea, "side": lab,
                                  "trades": len(x), "mean_r": x.mean()})
        yr = pd.to_datetime(t["entry_time"], utc=True).dt.year
        for y, x in t.groupby(yr)["r_multiple"]:
            year_rows.append({"symbol": r.symbol, "idea": r.idea, "year": int(y),
                              "trades": len(x), "mean_r": x.mean()})
    return pd.DataFrame(side_rows), pd.DataFrame(year_rows)


def analyse(ev: pd.DataFrame, hold: pd.DataFrame) -> dict:
    out: dict = {}
    v = ev.dropna(subset=["valid_mean_r"])
    out["overview"] = {
        "evaluations": int(len(ev)), "ideas": int(ev["idea"].nunique()),
        "by_symbol": ev.groupby("symbol").size().to_dict(),
        "verdicts": ev["verdict"].value_counts().to_dict(),
        "baseline": ev["baseline"].value_counts().to_dict(),
        "benchmark": ev["benchmark"].value_counts().to_dict(),
        "holdouts": int(len(hold)),
        "holdout_verdicts": (hold["holdout_verdict"].value_counts().to_dict()
                             if len(hold) else {}),
    }
    # 1. costs: how often a gross edge is eaten by cost
    out["cost"] = {
        "gross_pos_share": float((v["valid_gross_r"] > 0).mean()),
        "net_pos_share": float((v["valid_mean_r"] > 0).mean()),
        "gross_pos_net_neg_share": float(((v["valid_gross_r"] > 0) & (v["valid_mean_r"] <= 0)).mean()),
        "median_cost_r": float(v["valid_cost_r"].median()),
    }
    # 2. luck: if nothing had an edge, about 2.5% of z-scores would clear +1.96
    z = v["valid_z"].dropna()
    out["luck"] = {
        "n": int(len(z)), "z_gt_1_96": int((z > 1.96).sum()),
        "expected_if_no_edge": round(0.025 * len(z), 1),
        "z_mean": float(z.mean()), "z_sd": float(z.std()),
    }
    lo = v[v["valid_cost_r"] < 0.03]
    zl = lo["valid_z"].dropna()
    out["luck"].update({"low_cost_n": int(len(zl)), "low_cost_z_gt_1_96": int((zl > 1.96).sum()),
                        "low_cost_ideas": int(lo["idea"].nunique())})
    # 3. does TRAIN predict VALID?
    tv = v.dropna(subset=["train_mean_r"])
    out["train_predicts_valid"] = {
        "all": {"n": int(len(tv)), "spearman": float(tv["train_mean_r"].corr(tv["valid_mean_r"], "spearman"))},
        **{s: {"n": int(len(g)), "spearman": float(g["train_mean_r"].corr(g["valid_mean_r"], "spearman"))}
           for s, g in tv.groupby("symbol") if len(g) > 10},
        "low_cost": {"n": int(len(lo)),
                     "spearman": float(lo["train_mean_r"].corr(lo["valid_mean_r"], "spearman"))},
        "valid_pos_share_if_train_pos": float((tv.loc[tv["train_mean_r"] > 0, "valid_mean_r"] > 0).mean()),
        "valid_pos_share_if_train_neg": float((tv.loc[tv["train_mean_r"] <= 0, "valid_mean_r"] > 0).mean()),
    }
    # 4. the same idea file on two coins
    pv = v.pivot_table(index="name", columns="symbol", values="valid_mean_r")
    pairs = {}
    cols = list(pv.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            x = pv[[a, b]].dropna()
            if len(x) > 10:
                pairs[f"{a}-{b}"] = {"n": int(len(x)), "spearman": float(x[a].corr(x[b], "spearman")),
                                     "same_sign_share": float((np.sign(x[a]) == np.sign(x[b])).mean())}
    out["cross_coin"] = pairs
    # 5. feature tables
    ev = ev.copy()
    ev["hold_bucket"] = _bucket(ev["valid_avg_hold_h"], [0, 4, 24, 72, 1e9],
                                ["<4h", "4-24h", "1-3d", ">3d"])
    ev["cost_bucket"] = _bucket(ev["valid_cost_r"], [0, 0.03, 0.1, 0.3, 1e9],
                                ["<0.03R", "0.03-0.1R", "0.1-0.3R", ">0.3R"])
    ev["exit_mix"] = np.select(
        [ev["valid_time_rate"] >= 0.5, ev["valid_tp_rate"] >= 0.3, ev["valid_stop_rate"] >= 0.5],
        ["mostly time", "tp often", "mostly stop"], "mixed")
    ev["exits"] = ev["tp_type"].map({"none": "no TP"}).fillna("TP") + np.where(ev["trailing"], " + trail", "")
    tables = {
        "timeframe": group_table(ev, "tf", sorted(ev["tf"].dropna().unique())),
        "avg hold": group_table(ev, "hold_bucket", ["<4h", "4-24h", "1-3d", ">3d"]),
        "cost per trade": group_table(ev, "cost_bucket", ["<0.03R", "0.03-0.1R", "0.1-0.3R", ">0.3R"]),
        "trigger": group_table(ev, "trigger").sort_values("idea_mean", ascending=False),
        "direction": group_table(ev, "direction"),
        "stop type": group_table(ev, "stop_type"),
        "exits": group_table(ev, "exits"),
        "exit mix": group_table(ev, "exit_mix"),
        "number of filters": group_table(ev, "n_filters"),
        "symbol": group_table(ev, "symbol"),
    }
    out["tables"] = {k: t.reset_index().to_dict("records") for k, t in tables.items()}
    # 6. long vs short and 2023 vs 2024 (pooled VALID trades)
    sides, years = side_and_year(ev)
    if len(sides):
        # each evaluation counts once: a 1m run's thousands of trades would
        # otherwise outweigh every 4h run
        out["side"] = (sides.groupby(["symbol", "side"])
                       .agg(evals=("mean_r", "size"), trades=("trades", "sum"),
                            mean_r=("mean_r", "mean"), pos_share=("mean_r", lambda x: float((x > 0).mean())))
                       .reset_index().to_dict("records"))
    if len(years):
        # each evaluation counts once: a 1m run's thousands of trades would
        # otherwise outweigh every 4h run
        out["year"] = (years.groupby(["symbol", "year"])
                       .agg(evals=("mean_r", "size"), trades=("trades", "sum"),
                            mean_r=("mean_r", "mean"), pos_share=("mean_r", lambda x: float((x > 0).mean())))
                       .reset_index().to_dict("records"))
    # 7. controls and holdout on what reached them
    ctl = ev[ev["baseline"].notna() | ev["benchmark"].notna()]
    out["controls"] = {
        "evaluated": int(len(ctl)),
        "baseline_x_benchmark": ctl.groupby(["baseline", "benchmark"]).size()
                                   .rename("n").reset_index().to_dict("records"),
    }
    if len(hold):
        vm = ev.set_index("eval_id")["valid_mean_r"]
        out["holdout"] = [{
            "symbol": r.symbol, "name": r.name, "tf": int(r.tf),
            "valid_mean_r": float(vm.get(r.eval_id, np.nan)),
            "holdout_mean_r": float(r.holdout_mean_r), "holdout_ci_lo": float(r.holdout_ci_lo),
            "verdict": r.holdout_verdict,
            "note": "" if pd.isna(getattr(r, "note", np.nan)) else str(r.note),
        } for r in hold.itertuples()]
    out["_tables_df"] = tables
    return out


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------
def _fmt(t: pd.DataFrame) -> str:
    t = t.copy()
    for c in ("train_mean", "valid_mean", "valid_median", "idea_mean", "cost_r"):
        t[c] = t[c].map(lambda x: f"{x:+.3f}" if pd.notna(x) else "")
    t["valid_pos_share"] = t["valid_pos_share"].map(lambda x: f"{x:.0%}")
    t = t.reset_index()
    cols = list(t.columns)
    rows = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    rows += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for _, r in t.iterrows()]
    return "\n".join(rows)


def write(out: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MD.parent.mkdir(parents=True, exist_ok=True)
    tables = out.pop("_tables_df")
    (OUT_DIR / "summary.json").write_text(json.dumps(out, indent=1, default=str))
    o, c, lk, tp = out["overview"], out["cost"], out["luck"], out["train_predicts_valid"]
    L = ["# Meta lessons - every recorded evaluation, all coins", "",
         "GENERATED by `src/meta_lessons.py`. Do not edit by hand; re-run it.", "",
         "Reads only recorded results (no backtest, no market data). Two cautions:",
         "rows are not independent (timeframe variants and coins repeat one idea: see",
         "`ideas` and `idea_mean`, where each idea counts once), and most outcomes are",
         "VALID results, so a lesson is `robust` only when TRAIN agrees. The holdout",
         "stays the only test that counts.", "",
         "## Overview", "",
         f"- {o['evaluations']} evaluations of {o['ideas']} ideas: {o['by_symbol']}",
         f"- verdicts: {o['verdicts']}",
         f"- baseline: {o['baseline']} · benchmark: {o['benchmark']}",
         f"- holdouts: {o['holdouts']} {o['holdout_verdicts']}", "",
         "## Cost", "",
         f"- VALID gross R > 0 in **{c['gross_pos_share']:.0%}** of evaluations, net R > 0 in "
         f"**{c['net_pos_share']:.0%}**; cost turned a gross win into a net loss in "
         f"**{c['gross_pos_net_neg_share']:.0%}**. Median cost {c['median_cost_r']:.3f} R per trade.", "",
         "## Luck", "",
         f"- VALID z-scores (mean R / its bootstrap SE): mean {lk['z_mean']:+.2f}, sd {lk['z_sd']:.2f}, "
         f"n {lk['n']}. **{lk['z_gt_1_96']}** clear +1.96; with no edge anywhere about "
         f"**{lk['expected_if_no_edge']}** would (and the rows are correlated, so fewer are independent). "
         f"Among the {lk['low_cost_n']} evaluations with cost < 0.03 R ({lk['low_cost_ideas']} ideas): "
         f"{lk['low_cost_z_gt_1_96']} clear +1.96.", "",
         "## Does TRAIN predict VALID?", "",
         f"- Spearman(TRAIN mean R, VALID mean R) = **{tp['all']['spearman']:+.2f}** (n {tp['all']['n']}); "
         + ", ".join(f"{k} {v['spearman']:+.2f}" for k, v in tp.items()
                     if isinstance(v, dict) and k not in ("all", "low_cost")),
         f"- Only evaluations with cost < 0.03 R: **{tp['low_cost']['spearman']:+.2f}** (n {tp['low_cost']['n']}). "
         "The overall figure includes the cost effect, which is the same on both periods.",
         f"- VALID > 0 in {tp['valid_pos_share_if_train_pos']:.0%} of evaluations whose TRAIN was > 0, "
         f"and in {tp['valid_pos_share_if_train_neg']:.0%} of those whose TRAIN was <= 0.", "",
         "## The same idea file on two coins", "",
         "| pair | n | Spearman | same sign |", "|---|---|---|---|"]
    L += [f"| {k} | {v['n']} | {v['spearman']:+.2f} | {v['same_sign_share']:.0%} |"
          for k, v in out["cross_coin"].items()]
    for name, t in tables.items():
        L += ["", f"## By {name}", "", _fmt(t)]
    if "side" in out:
        L += ["", "## Long vs short (VALID, each evaluation once)", "", "| symbol | side | evals | trades | mean R (per eval) | evals > 0 |",
              "|---|---|---|---|---|---|"]
        L += [f"| {r['symbol']} | {r['side']} | {r['evals']} | {r['trades']} | {r['mean_r']:+.4f} | {r['pos_share']:.0%} |"
              for r in out["side"]]
    if "year" in out:
        L += ["", "## 2023 vs 2024 (VALID, each evaluation once)", "", "| symbol | year | evals | trades | mean R (per eval) | evals > 0 |",
              "|---|---|---|---|---|---|"]
        L += [f"| {r['symbol']} | {r['year']} | {r['evals']} | {r['trades']} | {r['mean_r']:+.4f} | {r['pos_share']:.0%} |"
              for r in out["year"]]
    L += ["", "## Controls on what reached them", "", f"{out['controls']['evaluated']} evaluations:", "",
          "| baseline | benchmark | n |", "|---|---|---|"]
    L += [f"| {r['baseline']} | {r['benchmark']} | {r['n']} |" for r in out["controls"]["baseline_x_benchmark"]]
    if "holdout" in out:
        L += ["", "## Holdout", "", "| symbol | idea | tf | VALID R | HOLDOUT R | CI lo | verdict | note |",
              "|---|---|---|---|---|---|---|---|"]
        L += [f"| {r['symbol']} | {r['name']} | {r['tf']} | {r['valid_mean_r']:+.3f} | "
              f"{r['holdout_mean_r']:+.3f} | {r['holdout_ci_lo']:+.3f} | {r['verdict']} | {r['note'][:60]} |"
              for r in out["holdout"]]
    MD.write_text("\n".join(L) + "\n")
    print(f"wrote {MD.relative_to(C.ROOT)} and {(OUT_DIR / 'summary.json').relative_to(C.ROOT)}")


def main() -> None:
    ev, hold = load()
    write(analyse(ev, hold))


if __name__ == "__main__":
    main()
