"""Exit lab: is there skill in HOW a trade is closed? (PLAN.md section 18)

    SYMBOL=BTCUSDT python src/exit_lab.py          # 1h, primary
    SYMBOL=ETHUSDT python src/exit_lab.py          # replication
    SYMBOL=BTCUSDT python src/exit_lab.py --tf 240 # secondary, descriptive

Entries are RANDOM (fixed seed): about one bar in four, side 50/50. A random
entry has no information, so any net edge has to come from the exit: a
trailing stop wins if moves persist, a near target wins if they revert. On a
pure random walk every exit's gross R is about zero and its net R is minus
the cost, so a positive net result means the price path has structure that
an exit can harvest. Long and short are equally likely, so a bull market does
not help: drift adds to the longs exactly what it takes from the shorts.

Each entry is simulated independently (positions may overlap), with the same
fills as src/backtest.py: entry at the next open plus slippage, stop first
inside a bar, break-even and trailing moved on the PREVIOUS bar's close, a
time exit at the close, taker fee and slippage on both sides, funding on the
notional (test 14 checks it trade for trade against the engine).

The six exits are fixed in EXITS. TRAIN chooses one (highest mean net R).
VALID gives PASS/REJECT. --final runs the HOLDOUT once, and only after PASS.
Writes results/<SYMBOL>/s18_exit_lab/ and the generated journal/<SYMBOL>/s18_exit_lab.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
import indicators as ta  # noqa: E402

# ---- pre-registered (PLAN.md section 18); a change is a new test
ENTRY_P = 0.25
SEED = 18
ATR_N = 14
EXITS = {  # stop and trail in ATR; tp and be in R; max_hold in bars
    "time_only":  dict(stop_atr=3.0, tp_r=0.0, be_r=0.0, trail_at_r=0.0, trail_atr=0.0, max_hold=24),
    "tp_1r":      dict(stop_atr=2.0, tp_r=1.0, be_r=0.0, trail_at_r=0.0, trail_atr=0.0, max_hold=72),
    "tp_2r":      dict(stop_atr=2.0, tp_r=2.0, be_r=0.0, trail_at_r=0.0, trail_atr=0.0, max_hold=72),
    "tp_4r":      dict(stop_atr=2.0, tp_r=4.0, be_r=0.0, trail_at_r=0.0, trail_atr=0.0, max_hold=72),
    "be_then_3r": dict(stop_atr=2.0, tp_r=3.0, be_r=1.0, trail_at_r=0.0, trail_atr=0.0, max_hold=72),
    "trail_2atr": dict(stop_atr=2.0, tp_r=0.0, be_r=0.0, trail_at_r=1.0, trail_atr=2.0, max_hold=120),
}
SPLITS = {"train": ("2020-01-01", "2023-01-01"), "valid": ("2023-01-01", "2025-01-01"),
          "holdout": ("2025-01-01", "2026-09-01")}
BLOCK = "7D"
N_BOOT = 5000


def random_entries(index: pd.DatetimeIndex, p: float = ENTRY_P, seed: int = SEED) -> np.ndarray:
    """-1/0/+1 per bar: entered with probability p, side 50/50."""
    rng = np.random.default_rng(seed)
    pick = rng.random(len(index)) < p
    side = np.where(rng.random(len(index)) < 0.5, 1.0, -1.0)
    return np.where(pick, side, 0.0)


def simulate(bars: pd.DataFrame, side: np.ndarray, ex: dict, funding: pd.DataFrame | None = None,
             fee: float = C.FEE_TAKER, slip: float = C.SLIPPAGE) -> pd.DataFrame:
    """Net R of every entry, each on its own (signal on bar i, fill at i+1)."""
    o, h, l, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    atr = ta.atr_(bars["high"], bars["low"], bars["close"], ATR_N).to_numpy(float)
    n = len(bars)
    times = bars.index.to_numpy("datetime64[ns]")
    if funding is not None and len(funding):
        ft = pd.to_datetime(funding["calc_time"], utc=True).to_numpy("datetime64[ns]")
        fr = funding["last_funding_rate"].to_numpy(float)
        order = np.argsort(ft)
        ft, fr = ft[order], fr[order]
        step = np.median(np.diff(times))
        bar_end = np.r_[times[1:], times[-1] + step]
        lo_in = np.searchsorted(ft, times, side="left")    # events >= bar open
        lo_ex = np.searchsorted(ft, times, side="right")   # events  > bar open (entry bar)
        hi_ = np.searchsorted(ft, bar_end, side="left")
        pre = np.r_[0.0, np.cumsum(fr)]
    else:
        lo_in = lo_ex = hi_ = np.zeros(n, dtype=int)
        pre = np.zeros(1)
    rows = []
    for i in np.flatnonzero(side[:-1]):
        s, a = side[i], atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        j = i + 1
        d = ex["stop_atr"] * a
        entry = o[j] * (1 + slip * s)
        stop = entry - s * d
        tp = entry + s * ex["tp_r"] * d if ex["tp_r"] > 0 else 0.0
        fund = 0.0
        px, reason, k = None, "eod", n - 1
        for k in range(j, n):
            a0 = lo_ex[k] if k == j else lo_in[k]
            if hi_[k] > a0:
                fund += o[k] * (pre[hi_[k]] - pre[a0]) * s
            if k > j:
                ur = s * (c[k - 1] - entry) / d
                if ex["be_r"] > 0 and ur >= ex["be_r"]:
                    be_px = entry * (1 + s * (fee + slip))
                    stop = max(stop, be_px) if s > 0 else min(stop, be_px)
                if ex["trail_atr"] > 0 and ex["trail_at_r"] > 0 and ur >= ex["trail_at_r"] and atr[k - 1] > 0:
                    t_px = c[k - 1] - s * ex["trail_atr"] * atr[k - 1]
                    stop = max(stop, t_px) if s > 0 else min(stop, t_px)
            stop_hit = l[k] <= stop if s > 0 else h[k] >= stop
            tp_hit = tp > 0 and (h[k] >= tp if s > 0 else l[k] <= tp)
            if stop_hit:
                gap = o[k] < stop if s > 0 else o[k] > stop
                px, reason = (o[k] if gap else stop), "stop"
                break
            if tp_hit:
                gap = o[k] > tp if s > 0 else o[k] < tp
                px, reason = (o[k] if gap else tp), "target"
                break
            if k - j + 1 >= ex["max_hold"]:
                px, reason = c[k], "time"
                break
        if px is None:
            px = c[n - 1]
        px_adj = px * (1 - slip * s)
        gross = s * (px_adj - entry) / d
        fees = (entry + px_adj) * fee / d
        net = gross - fees - fund / d
        rows.append((bars.index[j], s, net, gross + slip * (entry + px_adj) / d, reason, k - j + 1))
    return pd.DataFrame(rows, columns=["entry_time", "side", "net_r", "gross_r", "reason", "bars"])


def block_ci(t: pd.DataFrame, n: int = N_BOOT, seed: int = 17) -> tuple[float, float]:
    """95% CI of the mean net R, resampling whole weeks (entries overlap)."""
    if len(t) < 50:
        return (np.nan, np.nan)
    g = t.groupby(t["entry_time"].dt.floor(BLOCK))["net_r"]
    sums, cnts = g.sum().to_numpy(), g.count().to_numpy()
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(sums), size=(n, len(sums)))
    m = sums[pick].sum(1) / cnts[pick].sum(1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def summarize(t: pd.DataFrame) -> dict:
    if t.empty:
        return {"trades": 0}
    lo, hi = block_ci(t)
    return {"trades": int(len(t)), "mean_r": float(t["net_r"].mean()), "ci_lo": lo, "ci_hi": hi,
            "gross_r": float(t["gross_r"].mean()),
            "long_r": float(t.loc[t.side > 0, "net_r"].mean()),
            "short_r": float(t.loc[t.side < 0, "net_r"].mean()),
            "exit_mix": t["reason"].value_counts(normalize=True).round(3).to_dict(),
            "avg_bars": float(t["bars"].mean())}


def window(t: pd.DataFrame, split: str) -> pd.DataFrame:
    a, b = (pd.Timestamp(x, tz="UTC") for x in SPLITS[split])
    return t[(t["entry_time"] >= a) & (t["entry_time"] < b)]


def run(tf: int, final: bool = False) -> None:
    import experiment as E
    bars = E.get_bars(tf)[["open", "high", "low", "close"]]
    fund = E.load_funding()
    out = C.RESULTS / "s18_exit_lab"
    out.mkdir(parents=True, exist_ok=True)
    res_path = out / f"tf{tf}.json"
    side = random_entries(bars.index)
    if final:
        res = json.loads(res_path.read_text()) if res_path.exists() else None
        if not res or res["verdict"] != "PASS":
            raise SystemExit("--final refused: needs a PASS from the TRAIN/VALID run")
        lock = out / f"holdout_tf{tf}.json"
        if lock.exists():
            raise SystemExit(f"--final refused: holdout already used ({lock})")
        h = summarize(window(simulate(bars, side, EXITS[res["chosen"]], fund), "holdout"))
        h["verdict"] = "CONFIRMED" if h.get("mean_r", -1) > 0 and (h.get("ci_lo") or -1) > 0 else "FAILED"
        lock.write_text(json.dumps(h, indent=1))
        print(json.dumps(h, indent=1))
        return
    if res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    train, valid = {}, {}
    for name, ex in EXITS.items():
        t = simulate(bars, side, ex, fund)
        train[name], valid[name] = summarize(window(t, "train")), summarize(window(t, "valid"))
        print(f"{name:11} TRAIN {train[name]['mean_r']:+.4f}  VALID {valid[name]['mean_r']:+.4f}", flush=True)
    chosen = max(EXITS, key=lambda k: train[k]["mean_r"])
    ex = EXITS[chosen]
    stress = summarize(window(simulate(bars, side, ex, fund, fee=C.FEE_TAKER * 1.5,
                                       slip=C.SLIPPAGE * 1.5), "valid"))
    v = valid[chosen]
    gates = {"train_mean>0": train[chosen]["mean_r"] > 0, "valid_mean>0": v["mean_r"] > 0,
             "valid_ci_lo>0": (v["ci_lo"] or -1) > 0, "stress_mean>0": stress["mean_r"] > 0,
             "valid_trades>=1000": v["trades"] >= 1000}
    failed = [k for k, ok in gates.items() if not ok]
    res = {"symbol": C.SYMBOL, "tf": tf, "entry_p": ENTRY_P, "seed": SEED, "chosen": chosen,
           "verdict": "REJECT" if failed else "PASS", "gates_failed": failed,
           "train": train, "valid": valid, "valid_stress": stress}
    res_path.write_text(json.dumps(res, indent=1))
    write_report(out)
    print(f"\n{C.SYMBOL} {tf}m: chosen {chosen} -> {res['verdict']}  failed {failed}")


def write_report(out: Path) -> None:
    L = [f"# {C.SYMBOL} - exit lab (PLAN.md section 18)", "",
         "GENERATED by `src/exit_lab.py`. Do not edit by hand.", "",
         "Random entries (p 0.25, side 50/50, fixed seed); each entry simulated on its own. Net R",
         "after taker fees, slippage and funding. 95% CI resamples whole weeks.", ""]
    for p in sorted(out.glob("tf*.json")):
        r = json.loads(p.read_text())
        L += [f"## {r['tf']}m: **{r['verdict']}** (TRAIN chose `{r['chosen']}`; failed: {r['gates_failed'] or 'none'})", "",
              "| exit | TRAIN mean R | VALID trades | VALID mean R | 95% CI | gross R | long / short | exits |",
              "|---|---|---|---|---|---|---|---|"]
        for k in EXITS:
            t, v = r["train"][k], r["valid"][k]
            L.append(f"| {k} | {t['mean_r']:+.4f} | {v['trades']} | {v['mean_r']:+.4f} | "
                     f"[{v['ci_lo']:+.4f}, {v['ci_hi']:+.4f}] | {v['gross_r']:+.4f} | "
                     f"{v['long_r']:+.3f} / {v['short_r']:+.3f} | {v['exit_mix']} |")
        L += ["", f"cost x1.5 on the chosen exit: VALID mean R {r['valid_stress']['mean_r']:+.4f}", ""]
        h = p.parent / f"holdout_tf{r['tf']}.json"
        if h.exists():
            hj = json.loads(h.read_text())
            L += [f"**HOLDOUT: {hj['verdict']}** - {hj['trades']} trades, mean {hj['mean_r']:+.4f}, "
                  f"CI [{hj['ci_lo']:+.4f}, {hj['ci_hi']:+.4f}]", ""]
    (C.JOURNAL / "s18_exit_lab.md").write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tf", type=int, default=60)
    ap.add_argument("--final", action="store_true")
    a = ap.parse_args()
    run(a.tf, a.final)


if __name__ == "__main__":
    main()
