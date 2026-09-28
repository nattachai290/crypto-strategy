"""The standard research gate: one idea file in, one honest verdict out.

    python src/evaluate.py ideas/my_idea.json           # train -> validation
    python src/evaluate.py ideas/my_idea.json --final   # + the locked holdout
    python src/evaluate.py --list                       # recipe building blocks

What it does, always the same way, so no step can be skipped or fudged:

  1. Load the idea (strategy + params + a small parameter grid).
  2. TRAIN  [data_start, valid_start): run every grid combination, keep those
     with enough trades, pick the one with the best mean R per trade.
  3. VALID  [valid_start, holdout_start): run ONLY that frozen choice. Report
     trades, gross_r, cost_r, mean R, bootstrap 95% CI, a cost-stress run
     (fees and slippage x1.5), CAGR, max drawdown, per-year mean R.
  4. Apply fixed gates -> PASS / WATCH / REJECT / INCONCLUSIVE.
  5. --final (only after PASS): run the frozen choice ONCE on the HOLDOUT
     [holdout_start, data_end]. Each (symbol, strategy, params) gets exactly
     one holdout run, ever - it is recorded and a second attempt is refused.
     Re-using the holdout until something passes would turn it into a
     training set.

Everything is appended to results/<SYMBOL>/evaluations.csv and to the
generated log journal/<SYMBOL>/evaluations.md.

Idea file (JSON):
{
  "name": "trend_breakout_adx",
  "hypothesis": "Breakouts in the direction of the 1h trend, only when ADX
                 says the market is trending, follow through for a few hours.",
  "strategy": "recipe",                  # or any name in strategies.REGISTRY
  "tf": 15,                              # bar minutes: 1, 3, 5, 15, 30
  "params": { ... recipe or strategy params ... },
  "grid": { "stop.mult": [2, 3, 4], "tp.r": [1.5, 2.5], "be_at": [0, 1] },
  "execution": { "entry_mode": "taker" } # optional: post_only, entry_offset_atr, entry_fill_ratio
}
Grid keys are dotted paths into params ("filters.1.min" = second filter's
"min"); keys starting with "exec." go into execution.
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import copy  # noqa: E402
import datetime as dt  # noqa: E402
import hashlib  # noqa: E402
import itertools  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
from concurrent.futures import ProcessPoolExecutor  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
import experiment as E  # noqa: E402
import recipes as R  # noqa: E402
import strategies as S  # noqa: E402
from backtest import run_backtest  # noqa: E402

EVAL_CSV = C.RESULTS / "evaluations.csv"
HOLDOUT_CSV = C.RESULTS / "holdout_log.csv"
TRADES_DIR = C.RESULTS / "eval_trades"
EVAL_MD = C.JOURNAL / "evaluations.md"

T0 = pd.Timestamp(C.mstart(C.DATA_START))
T_VALID = pd.Timestamp(C.mstart(C.VALID_START))
T_HOLD = pd.Timestamp(C.mstart(C.HOLDOUT_START))
T_END = pd.Timestamp(C.mend(C.DATA_END))

_G: dict = {}  # bars/funding shared with worker processes (fork)


# --------------------------------------------------------------------------
# idea handling
# --------------------------------------------------------------------------
def _set_path(d: dict, path: str, value) -> None:
    keys = path.split(".")
    cur = d
    for k in keys[:-1]:
        cur = cur[int(k)] if isinstance(cur, list) else cur.setdefault(k, {})
    last = keys[-1]
    if isinstance(cur, list):
        cur[int(last)] = value
    else:
        cur[last] = value


def load_idea(path: Path) -> dict:
    idea = json.loads(path.read_text(encoding="utf-8"))
    for k in ("name", "hypothesis", "tf", "params"):
        if k not in idea:
            raise SystemExit(f"idea file is missing '{k}'")
    idea.setdefault("strategy", "recipe")
    idea.setdefault("grid", {})
    idea.setdefault("execution", {})
    if idea["strategy"] != "recipe" and idea["strategy"] not in S.REGISTRY:
        raise SystemExit(f"unknown strategy {idea['strategy']!r}; use 'recipe' or one of "
                         f"{', '.join(S.REGISTRY)}")
    if int(idea["tf"]) not in (1, 3, 5, 15, 30, 60, 240):
        raise SystemExit("tf must be one of 1, 3, 5, 15, 30, 60, 240 (native Binance files)")
    for k, v in idea["grid"].items():
        if not isinstance(v, list) or not v:
            raise SystemExit(f"grid '{k}' must be a non-empty list")
    allowed = {"entry_mode", "entry_offset_atr", "entry_fill_ratio"}
    ex_keys = set(idea["execution"]) | {k[5:] for k in idea["grid"] if k.startswith("exec.")}
    if ex_keys - allowed:
        raise SystemExit(f"execution keys {sorted(ex_keys - allowed)} not allowed; "
                         f"only {sorted(allowed)}. Costs are fixed in config.py.")
    return idea


def combos(idea: dict) -> list[tuple[dict, dict]]:
    keys = list(idea["grid"])
    out = []
    for values in itertools.product(*(idea["grid"][k] for k in keys)):
        p = copy.deepcopy(idea["params"])
        ex = copy.deepcopy(idea["execution"])
        for k, v in zip(keys, values):
            if k.startswith("exec."):
                ex[k[5:]] = v
            else:
                _set_path(p, k, v)
        out.append((p, ex))
    if len(out) > C.EVAL_MAX_GRID:
        raise SystemExit(f"grid has {len(out)} combinations; the limit is {C.EVAL_MAX_GRID}. "
                         f"Fewer values per key - a big grid is data mining, not research.")
    return out


def _hash(*parts) -> str:
    s = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha1(s.encode()).hexdigest()[:10]


def signature(strategy: str, tf: int, params: dict) -> str:
    """The STRUCTURE of an idea: timeframe, trigger types, filter types and
    direction - not its numbers. Two ideas that differ only in stop width,
    thresholds or execution are versions of one idea, whatever their file
    names say, and share a version budget (EVAL_MAX_VERSIONS)."""
    if strategy != "recipe":
        return f"{strategy}|{tf}m"
    trig = "+".join(sorted(t.get("type", "?") for t in params.get("triggers", [])))
    filt = "+".join(sorted(f.get("type", "?") for f in params.get("filters", []) or []))
    return f"recipe|{tf}m|{trig}|{filt or '-'}|{params.get('direction', 'both')}"


def _prior_signature(row: pd.Series) -> str:
    try:
        return signature(row["strategy"], int(row["tf"]), json.loads(row["chosen_params"]))
    except (TypeError, ValueError, KeyError):
        return ""


# --------------------------------------------------------------------------
# running
# --------------------------------------------------------------------------
def _init_worker(tf: int) -> None:
    """Load the data in each worker. With fork (Linux) the parent's _G is
    already copied in; with spawn (Windows, macOS) it starts empty and every
    combo would die with KeyError: 'bars'."""
    if "bars" not in _G:
        _G["bars"] = E.get_bars(tf)
        _G["funding"] = E.load_funding()


def save_trades(res, eval_id: str, split: str) -> Path:
    """Trade list of one run -> results/<SYMBOL>/eval_trades/<eval_id>_<split>.csv.gz

    Floats are rounded to 6 decimals and the file is gzip-compressed (about 1/5
    of the plain size), so every evaluation's trades can live in git.
    Read it back with pd.read_csv(path) - pandas decompresses by itself."""
    TRADES_DIR.mkdir(parents=True, exist_ok=True)
    path = TRADES_DIR / f"{eval_id}_{split}.csv.gz"
    df = res.to_trades_df()
    if len(df):
        num = df.select_dtypes("float").columns
        df[num] = df[num].round(6)
    df.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})
    return path


def signals_for(strategy: str, params: dict) -> pd.DataFrame:
    bars, funding = _G["bars"], _G["funding"]
    if strategy == "recipe":
        return R.recipe(bars, funding, **params)
    return E.build_signals(strategy, bars, params, funding)


def backtest(sig: pd.DataFrame, start, end, execution: dict, cost_mult: float = 1.0):
    return run_backtest(
        _G["bars"], sig, funding=_G["funding"], start_time=start, end_time=end,
        fee_taker=C.FEE_TAKER * cost_mult, fee_maker=C.FEE_MAKER * cost_mult,
        slippage=C.SLIPPAGE * cost_mult, **execution)


def _train_one(args) -> dict:
    i, strategy, p, ex = args
    try:
        m = backtest(signals_for(strategy, p), T0, T_VALID, ex).metrics
        return {"i": i, "trades": m["trades"], "mean_r": m.get("avg_r", float("nan")),
                "gross_r": m.get("avg_gross_r", float("nan")),
                "cost_r": m.get("avg_cost_r", float("nan")), "max_dd": m["max_dd"]}
    except Exception as e:  # noqa: BLE001 - report, never hide
        return {"i": i, "error": f"{type(e).__name__}: {e}"}


def bootstrap(r: np.ndarray, n: int = C.EVAL_BOOTSTRAP, seed: int = 0):
    if len(r) < 2:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    means = r[rng.integers(0, len(r), size=(n, len(r)))].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi), float((means > 0).mean())


def summarise(res, tf: int) -> dict:
    m = res.metrics
    t = res.to_trades_df()
    r = t["r_multiple"].to_numpy() if len(t) else np.array([])
    lo, hi, p = bootstrap(r)
    years = {}
    if len(t):
        years = t.groupby(pd.to_datetime(t["exit_time"]).dt.year)["r_multiple"].agg(["mean", "count"])
        years = {int(y): (round(float(v["mean"]), 4), int(v["count"])) for y, v in years.iterrows()}
    return {
        "trades": int(m["trades"]), "mean_r": float(r.mean()) if len(r) else float("nan"),
        "ci_lo": lo, "ci_hi": hi, "p_gt_0": p,
        "gross_r": m.get("avg_gross_r", float("nan")), "cost_r": m.get("avg_cost_r", float("nan")),
        "win_rate": m.get("win_rate", float("nan")), "profit_factor": m.get("profit_factor", float("nan")),
        "cagr": m["cagr"], "max_dd": m["max_dd"],
        "avg_hold_h": m.get("avg_bars", float("nan")) * tf / 60.0,
        "long_trades": m.get("long_trades", 0), "short_trades": m.get("short_trades", 0),
        "stop_rate": m.get("stop_rate", float("nan")), "tp_rate": m.get("tp_rate", float("nan")),
        "time_rate": m.get("time_rate", float("nan")),
        "fill_rate": m.get("fill_rate", 1.0), "per_year": years,
    }


def verdict(train: dict, v: dict, stress: dict) -> tuple[str, dict]:
    gates = {
        "valid_trades>=%d" % C.EVAL_MIN_VALID_TRADES: v["trades"] >= C.EVAL_MIN_VALID_TRADES,
        "train_mean_r>0": train["mean_r"] > 0,
        "valid_mean_r>0": v["mean_r"] > 0,
        "valid_ci_lo>0": v["ci_lo"] > 0,
        "stress_mean_r>0": stress["mean_r"] > 0,
        "valid_max_dd<=%.0f%%" % (C.EVAL_MAX_DD * 100): v["max_dd"] <= C.EVAL_MAX_DD,
    }
    if v["trades"] < C.EVAL_MIN_ANY_TRADES:
        return "INCONCLUSIVE", gates
    if all(gates.values()):
        return "PASS", gates
    if gates["train_mean_r>0"] and gates["valid_mean_r>0"] and gates["stress_mean_r>0"]:
        return "WATCH", gates
    return "REJECT", gates


# --------------------------------------------------------------------------
# records
# --------------------------------------------------------------------------
def _append_csv(path: Path, row: dict) -> None:
    df = pd.DataFrame([row])
    if path.exists():
        df = pd.concat([pd.read_csv(path), df], ignore_index=True)
    df.to_csv(path, index=False)


def _fmt(x, f="{:+.4f}"):
    try:
        return "n/a" if x is None or not np.isfinite(float(x)) else f.format(float(x))
    except (TypeError, ValueError):
        return str(x)


def report_block(row: dict, v: dict, gates: dict, hold: dict | None) -> str:
    L = [f"### {row['eval_id']} — {row['name']} ({C.SYMBOL} {row['tf']}m) — **{row['verdict']}**",
         "",
         f"- {row['timestamp']} · idea `{row['idea_file']}` · strategy `{row['strategy']}`",
         f"- hypothesis: {row['hypothesis']}",
         f"- grid: {row['n_combos']} combos, {row['n_eligible']} with ≥{C.EVAL_MIN_TRAIN_TRADES} train trades, "
         f"{_fmt(row['train_positive_share'], '{:.0%}')} of those positive on train",
         f"- chosen params: `{row['chosen_params']}` exec `{row['chosen_exec']}`",
         "",
         "| split | trades | gross_r | cost_r | mean R | 95% CI | CAGR | maxDD |",
         "|---|---|---|---|---|---|---|---|",
         f"| train | {row['train_trades']} | {_fmt(row['train_gross_r'], '{:+.3f}')} | "
         f"{_fmt(row['train_cost_r'], '{:.3f}')} | {_fmt(row['train_mean_r'])} | | | {_fmt(row['train_max_dd'], '{:.1%}')} |",
         f"| valid | {v['trades']} | {_fmt(v['gross_r'], '{:+.3f}')} | {_fmt(v['cost_r'], '{:.3f}')} | "
         f"{_fmt(v['mean_r'])} | [{_fmt(v['ci_lo'])}, {_fmt(v['ci_hi'])}] | {_fmt(v['cagr'], '{:+.1%}')} | "
         f"{_fmt(v['max_dd'], '{:.1%}')} |",
         f"| valid ×{C.EVAL_STRESS_COST} cost | | | | {_fmt(row['stress_mean_r'])} | | | |"]
    if hold:
        L.append(f"| **holdout** | {hold['trades']} | {_fmt(hold['gross_r'], '{:+.3f}')} | "
                 f"{_fmt(hold['cost_r'], '{:.3f}')} | {_fmt(hold['mean_r'])} | "
                 f"[{_fmt(hold['ci_lo'])}, {_fmt(hold['ci_hi'])}] | {_fmt(hold['cagr'], '{:+.1%}')} | "
                 f"{_fmt(hold['max_dd'], '{:.1%}')} |")
    L += ["",
          f"- valid: win {_fmt(v['win_rate'], '{:.0%}')}, PF {_fmt(v['profit_factor'], '{:.2f}')}, "
          f"avg hold {_fmt(v['avg_hold_h'], '{:.1f}')} h, long/short {v['long_trades']}/{v['short_trades']}, "
          f"exits stop/tp/time {_fmt(v['stop_rate'], '{:.0%}')}/{_fmt(v['tp_rate'], '{:.0%}')}/"
          f"{_fmt(v['time_rate'], '{:.0%}')}, fill {_fmt(v['fill_rate'], '{:.0%}')}",
          f"- valid per year (mean R, trades): {v['per_year']}",
          "- gates: " + ", ".join(f"{k} {'✅' if ok else '❌'}" for k, ok in gates.items())]
    if hold:
        L.append(f"- holdout verdict: **{row['holdout_verdict']}**")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("idea", nargs="?", help="path to an idea JSON file")
    ap.add_argument("--final", action="store_true", help="also run the one-time HOLDOUT (PASS only)")
    ap.add_argument("--rerun", action="store_true", help="evaluate again even if this exact idea was run")
    ap.add_argument("--list", action="store_true", help="list recipe building blocks and strategies")
    ap.add_argument("--trades-only", action="store_true",
                    help="re-create the VALID trade file of an idea that was already evaluated; "
                         "records nothing and never touches the holdout")
    ap.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    a = ap.parse_args()

    if a.list:
        print(R.describe())
        print("\nREGISTRY strategies:", ", ".join(S.REGISTRY))
        return
    if not a.idea:
        ap.error("give an idea file, or --list")

    idea_path = Path(a.idea)
    idea = load_idea(idea_path)
    tf = int(idea["tf"])
    grid = combos(idea)
    eval_id = _hash(C.SYMBOL, idea["strategy"], tf, idea["params"], idea["grid"],
                    idea["execution"], C.DATA_START, C.VALID_START, C.HOLDOUT_START)

    prior = pd.read_csv(EVAL_CSV) if EVAL_CSV.exists() else pd.DataFrame()

    if a.trades_only:
        # Re-run only the recorded, frozen choice on VALID and write its trades.
        # No grid, no record, no holdout. The trade count and mean R must match
        # the recorded row, or the code has changed since the evaluation.
        if not (len(prior) and eval_id in set(prior["eval_id"])):
            raise SystemExit(f"{eval_id} has not been evaluated; run it normally first")
        r = prior[prior["eval_id"] == eval_id].iloc[-1]
        _G["bars"] = E.get_bars(tf)
        _G["funding"] = E.load_funding()
        p_rec, ex_rec = json.loads(r["chosen_params"]), json.loads(r["chosen_exec"])
        res = backtest(signals_for(idea["strategy"], p_rec), T_VALID, T_HOLD, ex_rec)
        path = save_trades(res, eval_id, "valid")
        t = res.to_trades_df()
        n, m = len(t), (float(t["r_multiple"].mean()) if len(t) else float("nan"))
        same = n == int(r["valid_trades"]) and (n == 0 or abs(m - float(r["valid_mean_r"])) < 1e-9)
        print(f"{eval_id} {idea['name']}: {n} trades, mean R {m:+.4f} -> {path.name}"
              + ("" if same else f"  !! MISMATCH with the record ({int(r['valid_trades'])} trades, "
                                 f"{float(r['valid_mean_r']):+.4f}): code changed since the evaluation"))
        return

    if len(prior) and eval_id in set(prior["eval_id"]):
        r = prior[prior["eval_id"] == eval_id].iloc[-1]
        if a.final and r["verdict"] != "PASS":
            print(f"--final refused: {eval_id} was evaluated as {r['verdict']}; "
                  f"the holdout is only for PASS.")
            return
        if not (a.rerun or a.final):
            print(f"already evaluated as {eval_id}: verdict {r['verdict']} "
                  f"(valid mean R {r['valid_mean_r']:+.4f}, CI [{r['valid_ci_lo']:+.4f}, "
                  f"{r['valid_ci_hi']:+.4f}]). Change the idea, or pass --rerun.")
            return

    # ---- version budget: same structure = same idea, whatever the file name --
    sig_id = signature(idea["strategy"], tf, idea["params"])
    if len(prior) and not a.rerun and not a.final:
        same = prior[prior.apply(_prior_signature, axis=1) == sig_id]
        if len(same) >= C.EVAL_MAX_VERSIONS:
            names = ", ".join(f"{n} ({v})" for n, v in zip(same["name"], same["verdict"]))
            print(f"refused: {len(same)} evaluations already share this idea's structure\n"
                  f"  {sig_id}\n  {names}\n"
                  f"Changing only numbers (stop, thresholds, offsets, holding time) is a new "
                  f"VERSION, and the limit is {C.EVAL_MAX_VERSIONS} - more would be tuning on "
                  f"the validation period. Test a structurally different hypothesis: another "
                  f"trigger, a different filter set, another direction or timeframe.")
            return

    print(f"{C.SYMBOL} {tf}m  idea={idea['name']}  combos={len(grid)}  eval_id={eval_id}")
    print(f"structure {sig_id}")
    print(f"TRAIN {T0.date()}..{T_VALID.date()}  VALID {T_VALID.date()}..{T_HOLD.date()}  "
          f"HOLDOUT {T_HOLD.date()}..{T_END.date()} (locked)")
    print(f"this is evaluation #{len(prior) + 1} for {C.SYMBOL} - the more ideas are tried, "
          f"the more likely one passes by luck; that is what the holdout is for.\n")

    _G["bars"] = E.get_bars(tf)
    _G["funding"] = E.load_funding()

    # ---- 1. TRAIN: every combo -------------------------------------------
    jobs = [(i, idea["strategy"], p, ex) for i, (p, ex) in enumerate(grid)]
    if a.workers > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(a.workers, initializer=_init_worker, initargs=(tf,)) as pool:
            rows = list(pool.map(_train_one, jobs))
    else:
        rows = [_train_one(j) for j in jobs]
    errors = [r for r in rows if "error" in r]
    if errors:
        raise SystemExit(f"{len(errors)} combos crashed, first: {errors[0]['error']}")
    tr = pd.DataFrame(rows)
    elig = tr[tr["trades"] >= C.EVAL_MIN_TRAIN_TRADES]
    print(f"train: {len(elig)}/{len(tr)} combos have >= {C.EVAL_MIN_TRAIN_TRADES} trades")
    if elig.empty:
        best_i = int(tr.sort_values("trades").iloc[-1]["i"])
        print("  none eligible - using the most active combo only to report; verdict will be INCONCLUSIVE")
    else:
        best_i = int(elig.sort_values("mean_r").iloc[-1]["i"])
    bt = tr.set_index("i").loc[best_i]
    p_best, ex_best = grid[best_i]
    print(f"chosen on train: mean R {bt['mean_r']:+.4f} over {int(bt['trades'])} trades")

    # ---- 2. VALID: the frozen choice --------------------------------------
    sig = signals_for(idea["strategy"], p_best)
    res_v = backtest(sig, T_VALID, T_HOLD, ex_best)
    v = summarise(res_v, tf)
    stress = summarise(backtest(sig, T_VALID, T_HOLD, ex_best, C.EVAL_STRESS_COST), tf)
    train_s = {"mean_r": float(bt["mean_r"]), "trades": int(bt["trades"])}
    verd, gates = verdict(train_s, v, stress)
    if elig.empty:
        verd = "INCONCLUSIVE"

    # A change that did nothing (e.g. a filter loose enough to block no trade)
    # reproduces an earlier validation result exactly. It is not new evidence,
    # and it must not become a second ticket to the holdout.
    duplicate_of = ""
    if len(prior) and "valid_trades" in prior:
        hit = prior[(prior["valid_trades"] == v["trades"])
                    & ((prior["valid_mean_r"] - v["mean_r"]).abs() < 1e-12)
                    & (prior["eval_id"] != eval_id)]
        if len(hit):
            duplicate_of = str(hit.iloc[0]["eval_id"])
            verd = "DUPLICATE"
            print(f"\nDUPLICATE: validation result is identical to {duplicate_of} "
                  f"({hit.iloc[0]['name']}) - the change had no effect on any trade.")

    save_trades(res_v, eval_id, "valid")

    row = {
        "eval_id": eval_id, "timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "symbol": C.SYMBOL, "idea_file": str(idea_path), "name": idea["name"],
        "hypothesis": " ".join(str(idea["hypothesis"]).split()), "strategy": idea["strategy"], "tf": tf,
        "n_combos": len(grid), "n_eligible": len(elig),
        "train_positive_share": float((elig["mean_r"] > 0).mean()) if len(elig) else float("nan"),
        "chosen_params": json.dumps(p_best, sort_keys=True), "chosen_exec": json.dumps(ex_best, sort_keys=True),
        "train_trades": int(bt["trades"]), "train_mean_r": float(bt["mean_r"]),
        "train_gross_r": float(bt["gross_r"]), "train_cost_r": float(bt["cost_r"]),
        "train_max_dd": float(bt["max_dd"]),
        **{f"valid_{k}": (json.dumps(val) if isinstance(val, dict) else val) for k, val in v.items()},
        "stress_mean_r": stress["mean_r"], "verdict": verd,
        "gates_failed": ";".join(k for k, ok in gates.items() if not ok),
        "holdout_verdict": "", "data_version": "native", "structure": sig_id,
        "duplicate_of": duplicate_of,
        "splits": f"{C.DATA_START}|{C.VALID_START}|{C.HOLDOUT_START}|{C.DATA_END}",
    }

    # ---- 3. HOLDOUT: once, only after PASS --------------------------------
    hold = None
    if a.final:
        hkey = _hash(C.SYMBOL, idea["strategy"], tf, p_best, ex_best)
        used = pd.read_csv(HOLDOUT_CSV) if HOLDOUT_CSV.exists() else pd.DataFrame()
        if verd != "PASS":
            print(f"\n--final refused: verdict is {verd}, the holdout is only for PASS.")
        elif len(used) and hkey in set(used["holdout_key"]):
            print(f"\n--final refused: holdout already used for this exact config ({hkey}). "
                  f"Result stands; see {HOLDOUT_CSV.name}.")
        else:
            res_h = backtest(sig, T_HOLD, T_END, ex_best)
            hold = summarise(res_h, tf)
            h_stress = summarise(backtest(sig, T_HOLD, T_END, ex_best, C.EVAL_STRESS_COST), tf)
            ok = (hold["trades"] >= C.EVAL_MIN_ANY_TRADES and hold["mean_r"] > 0
                  and h_stress["mean_r"] > 0 and hold["p_gt_0"] >= 0.90
                  and hold["max_dd"] <= C.EVAL_MAX_DD)
            row["holdout_verdict"] = "CONFIRMED" if ok else "FAILED"
            save_trades(res_h, eval_id, "holdout")
            _append_csv(HOLDOUT_CSV, {
                "holdout_key": hkey, "eval_id": eval_id, "timestamp": row["timestamp"],
                "name": idea["name"], "tf": tf, "params": row["chosen_params"], "exec": row["chosen_exec"],
                **{f"holdout_{k}": (json.dumps(val) if isinstance(val, dict) else val)
                   for k, val in hold.items()},
                "holdout_stress_mean_r": h_stress["mean_r"], "holdout_verdict": row["holdout_verdict"]})

    _append_csv(EVAL_CSV, row)
    block = report_block(row, v, gates, hold)
    if not EVAL_MD.exists():
        EVAL_MD.write_text(f"# {C.SYMBOL} evaluation log\n\nGenerated by `src/evaluate.py`, "
                           "appended on every run. Do not edit by hand.\n\n", encoding="utf-8")
    with EVAL_MD.open("a", encoding="utf-8") as fh:
        fh.write("\n---\n\n" + block)
    print("\n" + block)
    print(f"recorded -> {EVAL_CSV}, {EVAL_MD}")


if __name__ == "__main__":
    main()
