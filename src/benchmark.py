"""Buy-and-hold benchmark: does an idea beat simply holding BTC?

    python src/benchmark.py ideas/030_trend_regime_long.json

Mean R per trade can't be compared with holding BTC. This tool runs the idea's
recorded, frozen choice over TRAIN and VALID, takes the account's DAILY
returns, and compares them with BTC's daily returns (1x buy & hold of the same
account):

  beta   how much of BTC's daily move the strategy carries (0.3 = like holding
         30% of the account in BTC)
  alpha  annual return NOT explained by that exposure:
         mean(r_strategy - beta * r_btc) * 365, with a 95% block-bootstrap CI
         (20-day blocks, so volatility clusters stay together)
  plus CAGR, max drawdown, Sharpe and time in market, next to buy & hold's.

Verdicts:
  ALPHA      alpha > 0 on TRAIN and VALID, and the VALID alpha CI is above 0.
             The rule adds return beyond its BTC exposure.
  RISK_EDGE  not ALPHA, but on BOTH periods Sharpe beats buy & hold and max
             drawdown is under half of buy & hold's. Similar or lower return,
             much less pain: useful, but not an edge. The owner decides.
  NO_EDGE    anything else. Holding (a fraction of) BTC does as well.

`evaluate.py --final` accepts ALPHA (or a baseline.py SKILL) for a PASS;
RISK_EDGE goes to the owner. Output: results/<SYMBOL>/benchmark/<eval_id>.json
and a block in journal/<SYMBOL>/benchmarks.md. Recipe ideas only.

Note: the daily figures are sampled from the engine's bar-level equity curve
(last value of each UTC day). That samples the ACCOUNT, not price bars;
signals are still computed on native bars only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
import evaluate as V  # noqa: E402
import recipes as R  # noqa: E402

OUT = C.RESULTS / "benchmark"
MD = C.JOURNAL / "benchmarks.md"
BLOCK = 20
N_BOOT = 5000


def _daily(series: pd.Series) -> pd.Series:
    return series.groupby(series.index.floor("D")).last()


def _stats(r: pd.Series, equity: pd.Series) -> dict:
    years = max(len(r) / 365.0, 1e-9)
    total = float(equity.iloc[-1] / equity.iloc[0])
    dd = float((1 - equity / equity.cummax()).max())
    sd = float(r.std())
    return {"cagr": total ** (1 / years) - 1, "max_dd": dd,
            "sharpe": float(r.mean() / sd * math.sqrt(365)) if sd > 0 else float("nan")}


def _alpha_ci(rs: np.ndarray, rb: np.ndarray, beta: float, seed: int = 0) -> tuple[float, float]:
    e = rs - beta * rb
    n = len(e)
    if n < 2 * BLOCK:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    nb = int(math.ceil(n / BLOCK))
    starts = rng.integers(0, n - BLOCK + 1, size=(N_BOOT, nb))
    idx = (starts[:, :, None] + np.arange(BLOCK)[None, None, :]).reshape(N_BOOT, -1)[:, :n]
    means = e[idx].mean(axis=1) * 365
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def period(sig, start, end, ex) -> dict:
    res = V.backtest(sig, start, end, ex)
    eq = _daily(res.equity)
    btc = _daily(V._G["bars"]["close"][(V._G["bars"].index >= start) & (V._G["bars"].index < end)])
    df = pd.concat({"s": eq, "b": btc}, axis=1).dropna()
    rs, rb = df["s"].pct_change().dropna(), df["b"].pct_change().dropna()
    beta = float(np.cov(rs, rb)[0, 1] / np.var(rb, ddof=1)) if len(rb) > 2 else float("nan")
    alpha = float((rs - beta * rb).mean() * 365)
    lo, hi = _alpha_ci(rs.to_numpy(), rb.to_numpy(), beta)
    s = _stats(rs, df["s"])
    b = _stats(rb, df["b"])
    return {"days": len(rs), "trades": int(res.metrics["trades"]),
            "time_in_market": float(res.metrics.get("exposure", float("nan"))),
            "beta": beta, "alpha": alpha, "alpha_ci_lo": lo, "alpha_ci_hi": hi,
            "cagr": s["cagr"], "max_dd": s["max_dd"], "sharpe": s["sharpe"],
            "bh_cagr": b["cagr"], "bh_max_dd": b["max_dd"], "bh_sharpe": b["sharpe"],
            "size_skips": int(res.metrics.get("size_skips", 0))}


def verdict(tr: dict, va: dict) -> str:
    if tr["alpha"] > 0 and va["alpha"] > 0 and va["alpha_ci_lo"] > 0:
        return "ALPHA"
    if all(p["sharpe"] > p["bh_sharpe"] and p["max_dd"] < 0.5 * p["bh_max_dd"] for p in (tr, va)):
        return "RISK_EDGE"
    return "NO_EDGE"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("idea")
    a = ap.parse_args()
    idea = V.load_idea(Path(a.idea))
    if idea["strategy"] != "recipe":
        raise SystemExit("benchmark.py supports recipe ideas only")
    tf = int(idea["tf"])
    eval_id = V._hash(C.SYMBOL, idea["strategy"], tf, idea["params"], idea["grid"],
                      idea["execution"], C.DATA_START, C.VALID_START, C.HOLDOUT_START)
    prior = pd.read_csv(V.EVAL_CSV) if V.EVAL_CSV.exists() else pd.DataFrame()
    if not (len(prior) and eval_id in set(prior["eval_id"])):
        raise SystemExit(f"{eval_id} has not been evaluated; run evaluate.py first")
    rec = prior[prior["eval_id"] == eval_id].iloc[-1]
    params, ex = json.loads(rec["chosen_params"]), json.loads(rec["chosen_exec"])

    V._init_worker(tf)
    sig = R.recipe(V._G["bars"], V._G["funding"], **params)
    tr = period(sig, V.T0, V.T_VALID, ex)
    va = period(sig, V.T_VALID, V.T_HOLD, ex)
    verd = verdict(tr, va)
    summ = {"eval_id": eval_id, "name": idea["name"], "tf": tf,
            "timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "train": tr, "valid": va, "verdict": verd}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{eval_id}.json").write_text(json.dumps(summ, indent=2) + "\n", encoding="utf-8")

    def row(lbl, p):
        return (f"| {lbl} | {p['trades']} | {p['time_in_market']:.0%} | {p['beta']:.2f} | "
                f"{p['alpha']:+.1%} [{p['alpha_ci_lo']:+.1%}, {p['alpha_ci_hi']:+.1%}] | "
                f"{p['cagr']:+.1%} / {p['bh_cagr']:+.1%} | {p['max_dd']:.1%} / {p['bh_max_dd']:.1%} | "
                f"{p['sharpe']:.2f} / {p['bh_sharpe']:.2f} |")
    asset = C.SYMBOL.removesuffix("USDT")
    block = "\n".join([
        f"### {eval_id} — {idea['name']} ({C.SYMBOL} {tf}m) — **{verd}**", "",
        f"- {summ['timestamp']} · daily account returns vs 1x buy & hold of {asset}",
        "", "| period | trades | time in market | beta | alpha / yr [95% CI] | CAGR idea / B&H | maxDD idea / B&H | Sharpe idea / B&H |",
        "|---|---|---|---|---|---|---|---|", row("TRAIN 2020–22", tr), row("VALID 2023–24", va), "",
        {"ALPHA": f"- ALPHA: return beyond the strategy's {asset} exposure, on both periods, CI above 0 on VALID.",
         "RISK_EDGE": "- RISK_EDGE: no proven alpha, but better Sharpe and under half of buy & hold's drawdown "
                      "on both periods. Report to the owner; not a holdout ticket by itself.",
         "NO_EDGE": f"- NO_EDGE: holding (a fraction of) {asset} does as well."}[verd], ""])
    if not MD.exists():
        MD.write_text(f"# {C.SYMBOL} buy-and-hold benchmarks\n\nGenerated by `src/benchmark.py`, "
                      "appended on every run. Do not edit by hand.\n", encoding="utf-8")
    with MD.open("a", encoding="utf-8") as fh:
        fh.write("\n---\n\n" + block + "\n")
    print(block)


if __name__ == "__main__":
    main()
