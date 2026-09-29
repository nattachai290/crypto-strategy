"""Random-entry baseline: does an idea's ENTRY beat random timing?

    python src/baseline.py ideas/018_trend_breakout_long_tf30.json
    python src/baseline.py ideas/018_trend_breakout_long_tf30.json --n 200

A long-only idea evaluated on 2023-24 (a strong BTC bull market) can look good
because the market went up, not because its entries were good. This tool
takes the idea's recorded, frozen choice from evaluations.csv and compares it
with random entries that keep everything else identical: same direction,
stop, take-profit, break-even, trail, time stop, cooldown and execution, and
about the same number of signals.

  A. random entries at any time            -> what the market's drift pays
  B. random entries where the filters allow -> what the regime filter pays
                                               without the trigger's timing

For each of N seeds it records the mean R on TRAIN and VALID. The idea shows
SKILL only if its mean R is above the 95th percentile of BOTH random
distributions on BOTH TRAIN and VALID (TRAIN includes the 2022 bear market;
VALID alone let a bull-market drift pass as skill, Exp 019). Otherwise its result is explained by drift or by the filters
(DRIFT), and `evaluate.py --final` refuses to spend the holdout on it.

Output: results/<SYMBOL>/baseline/<eval_id>.json (summary, read by
evaluate.py --final) and <eval_id>_runs.csv.gz (every random run), plus a block
appended to journal/<SYMBOL>/baselines.md. Recipe ideas only.
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import copy  # noqa: E402
import datetime as dt  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
from concurrent.futures import ProcessPoolExecutor  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
import evaluate as V  # noqa: E402
import recipes as R  # noqa: E402

OUT = C.RESULTS / "baseline"
MD = C.JOURNAL / "baselines.md"
SKILL_PCTL = 95.0


def _count(sig: pd.DataFrame, start, end) -> int:
    s = sig["side"]
    return int(((s != 0) & (s.index >= start) & (s.index < end)).sum())


def _mean_r(res) -> tuple[float, int]:
    t = res.to_trades_df()
    return (float(t["r_multiple"].mean()) if len(t) else float("nan")), len(t)


def _random_params(params: dict, p: float, seed: int, keep_filters: bool) -> dict:
    q = copy.deepcopy(params)
    q["triggers"] = [{"type": "random", "p": p, "seed": seed}]
    q["trigger_mode"] = "any"
    if not keep_filters:
        q["filters"] = []
    return q


def _calibrate(params: dict, target: int, keep_filters: bool, start=None, end=None) -> float:
    """p so that the random frame has about as many signals in [start, end)
    as the idea (default window: VALID)."""
    start = V.T_VALID if start is None else start
    end = V.T_HOLD if end is None else end
    bars = V._G["bars"]
    n_win = int(((bars.index >= start) & (bars.index < end)).sum())
    p = max(target, 1) / max(n_win, 1)
    for _ in range(4):  # filters and cooldown remove signals; scale p up to match
        got = _count(R.recipe(bars, V._G["funding"], **_random_params(params, p, 0, keep_filters)),
                     start, end)
        if got == 0:
            p = min(p * 4, 0.5)
            continue
        p = min(p * target / got, 0.5)
    return p


def _one(args) -> dict:
    mode, seed, params, ex, p = args
    sig = R.recipe(V._G["bars"], V._G["funding"],
                   **_random_params(params, p, seed, keep_filters=(mode == "B")))
    tr_r, tr_n = _mean_r(V.backtest(sig, V.T0, V.T_VALID, ex))
    va_r, va_n = _mean_r(V.backtest(sig, V.T_VALID, V.T_HOLD, ex))
    return {"mode": mode, "seed": seed, "p": p, "train_mean_r": tr_r, "train_trades": tr_n,
            "valid_mean_r": va_r, "valid_trades": va_n}


def _one_window(args) -> dict:
    mode, seed, params, ex, p, start, end = args
    sig = R.recipe(V._G["bars"], V._G["funding"],
                   **_random_params(params, p, seed, keep_filters=(mode == "B")))
    r, n = _mean_r(V.backtest(sig, start, end, ex))
    return {"mode": mode, "seed": seed, "mean_r": r, "trades": n}


def skill_check(real_train: float, real_valid: float, runs: pd.DataFrame) -> dict:
    """SKILL needs the idea above the 95th percentile of BOTH random modes on
    BOTH periods. VALID alone is not enough: in a one-directional period
    (2023-24) every long entry gets the same tailwind, so beating random
    timing there can still be drift (Exp 019, idea 022). TRAIN contains the
    2022 bear market."""
    out = {"modes": {}, "skill": True}
    for mode in ("A", "B"):
        r = runs[runs["mode"] == mode]
        res = {}
        for per, real in (("train", real_train), ("valid", real_valid)):
            x = r[f"{per}_mean_r"].dropna()
            p95 = float(np.percentile(x, SKILL_PCTL)) if len(x) else float("nan")
            ok = bool(len(x)) and np.isfinite(real) and real > p95
            res[per] = {"median": float(x.median()) if len(x) else float("nan"), "p95": p95,
                        "share_ge_idea": float((x >= real).mean()) if len(x) else float("nan"),
                        "idea_beats_p95": ok}
            out["skill"] &= ok
        out["modes"][mode] = res
    return out


def holdout_control(params: dict, ex: dict, tf: int, n: int = 200, workers: int = 1) -> dict:
    """Random-entry control on the HOLDOUT, run inside evaluate.py --final's one
    permitted holdout run. Uses no information the holdout run itself doesn't.
    Returns the median and 95th percentile of mean R for modes A and B."""
    V._init_worker(tf)
    real = R.recipe(V._G["bars"], V._G["funding"], **params)
    target = _count(real, V.T_HOLD, V.T_END)
    jobs = []
    for mode, keep in (("A", False), ("B", True)):
        p = _calibrate(params, target, keep, V.T_HOLD, V.T_END)
        jobs += [(mode, s, params, ex, p, V.T_HOLD, V.T_END) for s in range(1, n + 1)]
    if workers > 1:
        with ProcessPoolExecutor(workers, initializer=V._init_worker, initargs=(tf,)) as pool:
            runs = pd.DataFrame(list(pool.map(_one_window, jobs, chunksize=4)))
    else:
        runs = pd.DataFrame([_one_window(j) for j in jobs])
    out = {}
    for mode in ("A", "B"):
        x = runs.loc[runs["mode"] == mode, "mean_r"].dropna()
        out[mode] = {"median": float(x.median()) if len(x) else float("nan"),
                     "p95": float(np.percentile(x, SKILL_PCTL)) if len(x) else float("nan")}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("idea")
    ap.add_argument("--n", type=int, default=200, help="random runs per mode")
    ap.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    a = ap.parse_args()

    idea = V.load_idea(Path(a.idea))
    if idea["strategy"] != "recipe":
        raise SystemExit("baseline.py supports recipe ideas only")
    tf = int(idea["tf"])
    eval_id = V._hash(C.SYMBOL, idea["strategy"], tf, idea["params"], idea["grid"],
                      idea["execution"], C.DATA_START, C.VALID_START, C.HOLDOUT_START)
    prior = pd.read_csv(V.EVAL_CSV) if V.EVAL_CSV.exists() else pd.DataFrame()
    if not (len(prior) and eval_id in set(prior["eval_id"])):
        raise SystemExit(f"{eval_id} has not been evaluated; run evaluate.py first")
    rec = prior[prior["eval_id"] == eval_id].iloc[-1]
    params, ex = json.loads(rec["chosen_params"]), json.loads(rec["chosen_exec"])

    V._init_worker(tf)
    real = R.recipe(V._G["bars"], V._G["funding"], **params)
    real_tr, real_tr_n = _mean_r(V.backtest(real, V.T0, V.T_VALID, ex))
    real_va, real_va_n = _mean_r(V.backtest(real, V.T_VALID, V.T_HOLD, ex))
    target = _count(real, V.T_VALID, V.T_HOLD)
    print(f"{C.SYMBOL} {tf}m {idea['name']} ({eval_id}): idea VALID mean R {real_va:+.4f} "
          f"on {real_va_n} trades, TRAIN {real_tr:+.4f} on {real_tr_n}; {target} VALID signals")

    p_a = _calibrate(params, target, keep_filters=False)
    p_b = _calibrate(params, target, keep_filters=True)
    jobs = ([("A", s, params, ex, p_a) for s in range(1, a.n + 1)]
            + [("B", s, params, ex, p_b) for s in range(1, a.n + 1)])
    if a.workers > 1:
        with ProcessPoolExecutor(a.workers, initializer=V._init_worker, initargs=(tf,)) as pool:
            runs = pd.DataFrame(list(pool.map(_one, jobs, chunksize=4)))
    else:
        runs = pd.DataFrame([_one(j) for j in jobs])

    summ = {"eval_id": eval_id, "name": idea["name"], "tf": tf, "n_per_mode": a.n,
            "timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "idea_valid_mean_r": real_va, "idea_valid_trades": real_va_n,
            "idea_train_mean_r": real_tr, "idea_train_trades": real_tr_n}
    chk = skill_check(real_tr, real_va, runs)
    skill = chk["skill"]
    lines = []
    for mode, label in (("A", "random entries, any time"),
                        ("B", "random entries, same filters")):
        r = runs[runs["mode"] == mode]
        m = chk["modes"][mode]
        summ[mode] = {"label": label, "p": float(r["p"].iloc[0]),
                      "valid_median": m["valid"]["median"], "valid_p95": m["valid"]["p95"],
                      "share_random_ge_idea": m["valid"]["share_ge_idea"],
                      "valid_trades_median": float(r["valid_trades"].median()),
                      "train_median": m["train"]["median"], "train_p95": m["train"]["p95"],
                      "train_share_random_ge_idea": m["train"]["share_ge_idea"],
                      "idea_beats_p95_valid": m["valid"]["idea_beats_p95"],
                      "idea_beats_p95_train": m["train"]["idea_beats_p95"],
                      "idea_beats_p95": m["valid"]["idea_beats_p95"] and m["train"]["idea_beats_p95"]}
        tick = lambda ok: "✅" if ok else "❌"  # noqa: E731
        lines.append(f"| {mode}: {label} | {m['train']['median']:+.4f} / {m['train']['p95']:+.4f} "
                     f"{tick(m['train']['idea_beats_p95'])} | "
                     f"{m['valid']['median']:+.4f} / {m['valid']['p95']:+.4f} "
                     f"{tick(m['valid']['idea_beats_p95'])} | {m['valid']['share_ge_idea']:.0%} |")
    summ["verdict"] = "SKILL" if skill else "DRIFT"
    summ["rule"] = "idea > 95th pct of modes A and B on TRAIN and VALID (Exp 019)"

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{eval_id}.json").write_text(json.dumps(summ, indent=2) + "\n", encoding="utf-8")
    runs.round(6).to_csv(OUT / f"{eval_id}_runs.csv.gz", index=False,
                         compression={"method": "gzip", "mtime": 0})
    block = "\n".join([
        f"### {eval_id} — {idea['name']} ({C.SYMBOL} {tf}m) — **{summ['verdict']}**", "",
        f"- {summ['timestamp']} · {a.n} random runs per mode · idea VALID mean R "
        f"**{real_va:+.4f}** on {real_va_n} trades (TRAIN {real_tr:+.4f} on {real_tr_n})", "",
        "| baseline | TRAIN median / 95th pct | VALID median / 95th pct | share of random runs ≥ idea (VALID) |",
        "|---|---|---|---|", *lines, "",
        ("- SKILL: the entries beat random timing with the same exits and filters, on TRAIN and VALID."
         if skill else
         "- DRIFT: random entries with the same exits (and filters) do about as well; "
         "the result is explained by the market's move or the filters, not by the entry. "
         "`evaluate.py --final` will refuse this config."), ""])
    if not MD.exists():
        MD.write_text(f"# {C.SYMBOL} random-entry baselines\n\nGenerated by `src/baseline.py`, "
                      "appended on every run. Do not edit by hand.\n", encoding="utf-8")
    with MD.open("a", encoding="utf-8") as fh:
        fh.write("\n---\n\n" + block + "\n")
    print("\n" + block)


if __name__ == "__main__":
    main()
