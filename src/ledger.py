"""Experiment ledger - one queryable table of every test ever run.

The prose journal is for reasoning; this is for evidence. It reads the result
CSVs that the other scripts actually wrote and normalises everything into one
long-format table, so nothing can drift between "what I concluded" and "what
the run produced".

Schema (one row per configuration x evaluation window):

    exp        which experiment produced it
    strategy   strategy name
    tf         bar timeframe in minutes
    params     parameter dict as JSON
    split      train | test | oos  (oos = walk-forward, unseen)
    trades     executed trades
    gross_r    edge produced by price before costs   (R/trade)
    cost_r     fees + slippage + funding              (R/trade)
    exp_r      gross_r - cost_r                       (R/trade)
    ci_lo/hi   bootstrap CI on exp_r, when available
    sharpe, sortino, max_dd, cagr, win_rate, profit_factor, net_return

Because `exp_r` is arithmetically the difference of the two cost columns, any
row where it disagrees is a bug in the engine or the harness, and
`verify_arithmetic()` checks exactly that.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

LEDGER_CSV = C.LEGACY / "ledger.csv"
LEDGER_JSONL = C.LEGACY / "ledger.jsonl"

# metric name in source CSVs -> ledger column
METRIC_MAP = {
    "trades": "trades",
    "avg_gross_r": "gross_r",
    "avg_cost_r": "cost_r",
    "expectancy_r": "exp_r",
    "sharpe": "sharpe",
    "sortino": "sortino",
    "max_dd": "max_dd",
    "cagr": "cagr",
    "win_rate": "win_rate",
    "profit_factor": "profit_factor",
    "net_return": "net_return",
    "exposure": "exposure",
    "avg_bars": "avg_bars",
    "fees_pct_equity": "fees_pct_eq",
    "n_signals": "signals",
    "candidates": "candidates",
}

PARAM_KEYS = [
    "fast", "slow", "n", "k", "n_z", "adx_min", "adx_max", "rsi_lo", "rsi_hi",
    "stop_mult", "tp_mult", "max_hold", "atr_n", "bb_n", "squeeze_q",
    "ratio_n", "thresh", "ema_n", "flow_thresh", "n_votes", "z_thresh",
    "z_n", "rate_thresh", "vol_expand", "vol_ratio_min", "vol_max",
    "be_at", "trail_at", "trail_atr", "range_n", "pullback_ema", "rsi_lo",
    "stop_scale", "hold_hours", "session_hours", "hours", "weekdays",
    "weekday", "p_tp", "p_sl", "rsi_target",
]


def _params_from_row(row: pd.Series) -> dict:
    out = {}
    for k in PARAM_KEYS:
        if k in row.index and pd.notna(row[k]):
            v = row[k]
            if isinstance(v, (np.integer,)):
                v = int(v)
            elif isinstance(v, (np.floating,)):
                v = float(v)
            elif isinstance(v, str) and v.startswith("("):
                v = v
            out[k] = v
    return out


def _blank_ci(lo, hi):
    return lo, hi


# --------------------------------------------------------------------------
# Collectors: one per source file
# --------------------------------------------------------------------------
def collect_sweep() -> pd.DataFrame:
    """Exp 003 - 82 configs, train then a shortlist on test."""
    tr = pd.read_csv(C.LEGACY / "sweep_train.csv")
    te = pd.read_csv(C.LEGACY / "sweep_test.csv")
    frames = []
    for df, split, tag in ((tr, "train", "tr_"), (te, "test", "")):
        if df.empty or "error" in df.columns and df["error"].notna().all():
            continue
        cols = {"strategy": "strategy", "tf": "tf"}
        for src, dst in METRIC_MAP.items():
            cols[tag + src] = dst
        have = [c for c in cols if c in df.columns]
        sub = df[have].rename(columns=cols)
        sub["split"] = split
        sub["exp"] = "003"
        sub["params"] = sub.apply(_params_from_row, axis=1)
        frames.append(sub)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def collect_cost_lab() -> pd.DataFrame:
    """Exp 004 - stop width x execution scenario, full history."""
    df = pd.read_csv(C.LEGACY / "cost_lab.csv")
    cols = {"strategy": "strategy", "tf": "tf", "exec": "note",
            "stop_mult": "sm", "stop_pct": "stop_pct"}
    for src, dst in METRIC_MAP.items():
        cols[src] = dst
    have = [c for c in cols if c in df.columns]
    sub = df[have].rename(columns=cols)
    sub["split"] = "full"
    sub["exp"] = "004"
    sub["params"] = sub.apply(_params_from_row, axis=1)
    return sub


def collect_stopwidth() -> pd.DataFrame:
    """Exp 004b - stop width chosen on train, frozen, then tested."""
    frames = []
    # (file, split, experiment, column prefix)
    specs = [("round2_stopwidth_train.csv", "train", "004b", ""),
             ("round2_stopwidth_test.csv", "test", "004b", "te_")]
    for fn, split, exp, pre in specs:
        p = C.LEGACY / fn
        if not p.exists():
            continue
        df = pd.read_csv(p)
        cols = {"strategy": "strategy", "tf": "tf", "stop_mult": "sm"}
        for src, dst in METRIC_MAP.items():
            cols[pre + src] = dst
        have = {}
        for c, dst in cols.items():
            if c in df.columns and dst not in have.values():
                have[c] = dst
        sub = df[list(have)].rename(columns=have)
        sub["split"] = split
        sub["exp"] = exp
        sub["params"] = sub.apply(_params_from_row, axis=1)
        frames.append(sub)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def collect_ml() -> pd.DataFrame:
    """Exp 006/007 - rules vs ML, walk-forward, at two stop scales."""
    frames = []
    for fn, sc in (("ml_walkforward_15m.csv", 1.0),
                   ("ml_walkforward_15m_s2.0.csv", 2.0)):
        p = C.LEGACY / fn
        if not p.exists():
            continue
        df = pd.read_csv(p)
        cols = {"method": "method", "thr": "thr"}
        for src, dst in METRIC_MAP.items():
            cols[src] = dst
        have = [c for c in cols if c in df.columns]
        sub = df[have].rename(columns=cols)
        sub["strategy"] = "ml_candidate_pool"
        sub["tf"] = 15
        sub["split"] = "oos"
        sub["exp"] = "006" if sc == 1.0 else "007"
        sub["stop_scale"] = sc
        sub["params"] = sub.apply(_params_from_row, axis=1)
        frames.append(sub)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def collect_definitive() -> pd.DataFrame:
    """Exp 007 - the 24 headline configurations, pooled executed trades."""
    p = C.LEGACY / "definitive_oos.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p)
    df = df.rename(columns={
        "trades": "trades", "mean_R": "exp_r", "ci_lo": "ci_lo", "ci_hi": "ci_hi",
        "p_gt_0": "p_gt_0", "win_rate": "win_rate", "gross_r": "gross_r",
        "cost_r": "cost_r", "end": "end_equity", "cagr": "cagr",
        "max_dd": "max_dd", "years": "years", "method": "method", "thr": "thr",
        "stop_scale": "stop_scale", "tf": "tf",
    })
    df["split"] = "oos"
    df["exp"] = "007"
    df["strategy"] = "ml_candidate_pool"
    df["params"] = df.apply(
        lambda r: {"stop_scale": float(r["stop_scale"]), "method": r["method"],
                   "thr": float(r["thr"])}, axis=1)
    return df


def collect_maker() -> pd.DataFrame:
    """Exp 008 - post-only execution model, walk-forward, pooled trades."""
    p = C.LEGACY / "round3_maker.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p).rename(columns={
        "mean_R": "exp_r", "gross_r": "gross_r", "cost_r": "cost_r",
        "ci_lo": "ci_lo", "ci_hi": "ci_hi", "p_gt_0": "p_gt_0",
        "win_rate": "win_rate", "max_dd": "max_dd", "cagr": "cagr",
        "end": "end_equity", "years": "years", "tf": "tf",
        "stop_scale": "stop_scale", "mode": "note", "trades": "trades",
        "fill_rate": "fill_rate",
    })
    df["strategy"] = "ml_candidate_pool"
    df["method"] = "reg0.10"
    df["thr"] = 0.10
    df["split"] = "oos"
    df["exp"] = "008"
    df["params"] = df.apply(
        lambda r: json.dumps({"stop_scale": float(r["stop_scale"]),
                              "mode": r["note"],
                              "offset": float(r["offset"]),
                              "fill_ratio": float(r["fill_ratio"])}),
        axis=1)
    return df


def collect_holdperiod() -> pd.DataFrame:
    """Exp 009 - holding period sweep, post-only, 5m and 15m."""
    p = C.LEGACY / "round4_holdperiod.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p).rename(columns={
        "mean_R": "exp_r", "gross_r": "gross_r", "cost_r": "cost_r",
        "ci_lo": "ci_lo", "ci_hi": "ci_hi", "p_gt_0": "p_gt_0",
        "win_rate": "win_rate", "max_dd": "max_dd", "cagr": "cagr",
        "end": "end_equity", "trades": "trades", "tf": "tf",
        "stop_scale": "stop_scale", "avg_bars": "avg_bars",
    })
    df["strategy"] = "ml_candidate_pool"
    df["method"] = "reg0.10"
    df["thr"] = 0.10
    df["split"] = "oos"
    df["exp"] = "009"
    df["note"] = df.apply(
        lambda r: f"{r['note']} hold={r['hold_hours']:.0f}h "
                  f"({int(r['max_hold_bars'])} bars)", axis=1)
    df["params"] = df.apply(
        lambda r: json.dumps({"tf": int(r["tf"]),
                              "stop_scale": float(r["stop_scale"]),
                              "hold_hours": float(r["hold_hours"]),
                              "max_hold_bars": int(r["max_hold_bars"])}),
        axis=1)
    return df


def collect_json_extras() -> pd.DataFrame:
    """Anything a script reported as JSON (e.g. cost-in-R diagnostics)."""
    rows = []
    for p in C.LEGACY.glob("diag_*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        d["exp"] = p.stem.replace("diag_", "")
        rows.append(d)
    return pd.DataFrame(rows)


COLUMNS = [
    "exp", "strategy", "method", "thr", "tf", "split", "params", "note",
    "signals", "candidates", "trades", "gross_r", "cost_r", "exp_r",
    "ci_lo", "ci_hi", "p_gt_0", "sharpe", "sortino", "max_dd", "cagr",
    "win_rate", "profit_factor", "net_return", "end_equity", "exposure",
    "fees_pct_eq", "years", "sm", "stop_pct",
]

# Columns that only some experiments produce. They are appended after the main
# block rather than being mixed in, because adding them to COLUMNS silently
# dropped them: `out[COLUMNS]` selects by name, and a missing name is a
# KeyError, not a null column.
EXTRA_COLUMNS = ["fill_rate", "offset", "fill_ratio", "entry_mode",
                 "entry_signals", "entry_fills", "stop_scale",
                 "avg_bars", "hold_hours", "max_hold_bars"]


def build() -> pd.DataFrame:
    parts = []
    for fn in (collect_sweep, collect_cost_lab, collect_stopwidth,
               collect_ml, collect_definitive, collect_maker, collect_holdperiod):
        try:
            d = fn()
            if d is not None and len(d):
                parts.append(d)
        except Exception as e:  # noqa: BLE001
            print(f"  [ledger] {fn.__name__} failed: {type(e).__name__}: {e}")
    if not parts:
        return pd.DataFrame(columns=COLUMNS + EXTRA_COLUMNS)
    out = pd.concat(parts, ignore_index=True, sort=False)
    for c in COLUMNS + EXTRA_COLUMNS:
        if c not in out.columns:
            out[c] = np.nan
    out = out[COLUMNS + EXTRA_COLUMNS]
    out["params"] = out["params"].apply(
        lambda p: p if isinstance(p, str) else json.dumps(p, default=str))
    out["source"] = "csv"
    out["recorded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return out


# --------------------------------------------------------------------------
def verify_arithmetic(df: pd.DataFrame, tol: float = 5e-4) -> pd.DataFrame:
    """exp_r must equal gross_r - cost_r wherever all three are present."""
    m = df.dropna(subset=["gross_r", "cost_r", "exp_r"])
    m = m[np.isfinite(m["gross_r"]) & np.isfinite(m["cost_r"]) & np.isfinite(m["exp_r"])]
    m = m.assign(diff=(m["gross_r"] - m["cost_r"]) - m["exp_r"])
    bad = m[m["diff"].abs() > tol]
    return bad[["exp", "strategy", "tf", "split", "gross_r", "cost_r", "exp_r", "diff"]]


# --------------------------------------------------------------------------
def append_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Merge new rows into the persisted ledger, de-duplicating on the key."""
    if df is None or not len(df):
        return load()
    if LEDGER_CSV.exists():
        old = pd.read_csv(LEDGER_CSV)
        key = ["exp", "strategy", "method", "thr", "tf", "split", "params",
               "trades", "exp_r"]
        new = pd.concat([old, df], ignore_index=True, sort=False)
        new = new.drop_duplicates(subset=[k for k in key if k in new.columns],
                                  keep="last")
    else:
        new = df
    new.to_csv(LEDGER_CSV, index=False)
    return new


def load() -> pd.DataFrame:
    if LEDGER_CSV.exists():
        return pd.read_csv(LEDGER_CSV)
    return pd.DataFrame(columns=COLUMNS + EXTRA_COLUMNS)


def append_new(experiment: dict) -> None:
    """Append a single new experiment result to the JSONL ledger."""
    experiment.setdefault("recorded_at",
                          datetime.now(timezone.utc).isoformat(timespec="seconds"))
    with LEDGER_JSONL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(experiment, default=str) + "\n")


# --------------------------------------------------------------------------
def _row_line(r: pd.Series) -> str:
    def g(k, fmt="{:+.3f}", d=3):
        v = r.get(k)
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            return "-"
        return fmt.format(v, d)

    t = r.get("trades")
    t = "-" if (t is None or (isinstance(t, float) and np.isnan(t))) else f"{int(t)}"
    tf = r.get("tf")
    tf = "-" if (tf is None or (isinstance(tf, float) and np.isnan(tf))) else f"{int(tf)}m"
    return (f"| {r['strategy']} | {tf} | {t} | {g('gross_r')} | {g('cost_r')} | "
            f"{g('exp_r', '{:+.4f}', 4)} | {g('sharpe')} | {g('max_dd', '{:.1f}%', 1)} |")


def main() -> None:
    df = build()
    if not len(df):
        print("no result files found")
        return
    bad = verify_arithmetic(df)
    print(f"rows: {len(df)}")
    if len(bad):
        print(f"\nARITHMETIC MISMATCH in {len(bad)} rows "
              f"(exp_r != gross_r - cost_r):")
        print(bad.to_string(index=False))
    else:
        print("arithmetic check: OK (exp_r == gross_r - cost_r everywhere)")
    df = append_rows(df)
    print(f"\nledger  -> {LEDGER_CSV}")
    try:
        import ledger_report
        (C.JOURNAL / "ledger.md").write_text(
            ledger_report.summarise(df), encoding="utf-8")
        print(f"summary -> {C.JOURNAL / 'ledger.md'}")
    except Exception as e:  # noqa: BLE001
        print(f"summary step failed: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
