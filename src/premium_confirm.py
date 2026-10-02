"""Confirmation of the Coinbase premium lead on unseen coins (PLAN.md section 26)

    python src/premium_confirm.py

Reads only what evaluate.py and baseline.py already recorded for idea 057
(`ideas/057_coinbase_premium_follow*.json`, unchanged) on the CONFIRM coins,
none of which this idea had seen when it was written. Runs no backtest.

Pre-registered bars (fixed 2026-10-02, before any confirmation run):
  30m: VALID mean R > 0 on >= MIN_POSITIVE of the coins AND baseline.py SKILL
       on >= MIN_SKILL of them (an UNSIZABLE / INCONCLUSIVE / missing row
       counts as a failure on both).
  4h:  the VALID trades of every sizable coin pooled: >= MIN_POOLED trades,
       pooled mean R > 0, weekly-block 95% CI lower bound > 0 (weeks shared by
       all coins are resampled together, so correlated coins do not count as
       independent), and >= MIN_POSITIVE coins with a positive mean.
LEAD_CONFIRMED on a clock = that clock's bar is met. Only a confirmed clock
may go on to a pre-registered holdout test. Writes
results/_multi/premium_confirm/ and journal/_multi/premium_confirm.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

IDEA = "057_coinbase_premium_follow"
CONFIRM = ["SOLUSDT", "LTCUSDT", "LINKUSDT", "BCHUSDT", "ETCUSDT", "ALGOUSDT", "ATOMUSDT",
           "DOGEUSDT", "ADAUSDT", "DOTUSDT"]
NAMES = {15: f"{IDEA}_tf15", 30: f"{IDEA}_tf30", 60: IDEA, 240: f"{IDEA}_tf240"}
MIN_POSITIVE = 7
MIN_SKILL = 5
MIN_POOLED = 100
N_BOOT = 5000
OUT = C.ROOT / "results" / "_multi" / "premium_confirm"
REPORT = C.ROOT / "journal" / "_multi" / "premium_confirm.md"


def coin_rows(root: Path, coin: str) -> dict:
    """tf -> the latest evaluation row of the idea on that coin, plus its baseline verdict."""
    f = root / "results" / coin / "evaluations.csv"
    out = {}
    if not f.exists():
        return out
    ev = pd.read_csv(f)
    for tf, name in NAMES.items():
        r = ev[ev["name"] == name]
        if r.empty:
            continue
        r = r.iloc[-1].to_dict()
        b = root / "results" / coin / "baseline" / f"{r['eval_id']}.json"
        r["baseline"] = json.loads(b.read_text()).get("verdict") if b.exists() else None
        t = root / "results" / coin / "eval_trades" / f"{r['eval_id']}_valid.csv.gz"
        r["trades_file"] = str(t) if t.exists() else None
        out[tf] = r
    return out


def _usable(r: dict | None) -> bool:
    return bool(r) and r.get("verdict") in ("PASS", "WATCH", "REJECT")


def pooled_ci(t: pd.DataFrame, seed: int = 26) -> tuple[float, float]:
    if len(t) < 30:
        return (np.nan, np.nan)
    g = t.groupby(pd.to_datetime(t["entry_time"], utc=True).dt.floor("7D"))["r_multiple"]
    sums, cnts = g.sum().to_numpy(), g.count().to_numpy()
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(sums), size=(N_BOOT, len(sums)))
    m = sums[pick].sum(1) / cnts[pick].sum(1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def evaluate(root: Path, coins: list[str] = CONFIRM) -> dict:
    rows = {c: coin_rows(root, c) for c in coins}
    res: dict = {"coins": coins, "per_coin": {}}
    for c in coins:
        res["per_coin"][c] = {tf: {k: rows[c][tf].get(k) for k in ("verdict", "valid_trades", "valid_mean_r",
                                                                   "valid_ci_lo", "valid_ci_hi", "baseline")}
                              for tf in rows[c]}
    # 30m
    r30 = [rows[c].get(30) for c in coins]
    pos30 = sum(1 for r in r30 if _usable(r) and (r.get("valid_mean_r") or -1) > 0)
    skill30 = sum(1 for r in r30 if _usable(r) and r.get("baseline") == "SKILL")
    res["m30"] = {"positive": pos30, "skill": skill30,
                  "confirmed": pos30 >= MIN_POSITIVE and skill30 >= MIN_SKILL}
    # 4h pooled
    frames, pos4 = [], 0
    for c in coins:
        r = rows[c].get(240)
        if not _usable(r) or not r.get("trades_file"):
            continue
        t = pd.read_csv(r["trades_file"])
        frames.append(t.assign(coin=c))
        pos4 += int(t["r_multiple"].mean() > 0) if len(t) else 0
    t4 = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["entry_time", "r_multiple"])
    lo, hi = pooled_ci(t4)
    mean4 = float(t4["r_multiple"].mean()) if len(t4) else float("nan")
    res["h4"] = {"pooled_trades": int(len(t4)), "pooled_mean_r": mean4, "ci_lo": lo, "ci_hi": hi,
                 "positive": pos4, "coins_used": len(frames),
                 "long_r": float(t4.loc[t4["side"] > 0, "r_multiple"].mean()) if len(t4) else None,
                 "short_r": float(t4.loc[t4["side"] < 0, "r_multiple"].mean()) if len(t4) else None}
    res["h4"]["confirmed"] = bool(len(t4) >= MIN_POOLED and mean4 > 0 and np.isfinite(lo) and lo > 0
                                  and pos4 >= MIN_POSITIVE)
    res["verdict"] = ("LEAD_CONFIRMED" if res["m30"]["confirmed"] or res["h4"]["confirmed"]
                      else "NOT_CONFIRMED")
    return res


def write_report(r: dict) -> None:
    f = (lambda x: "-" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:+.4f}")
    L = ["# Coinbase premium: confirmation on unseen coins (PLAN.md section 26)", "",
         "GENERATED by `src/premium_confirm.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}**", "",
         f"- 30m: VALID mean > 0 on {r['m30']['positive']} of {len(r['coins'])} (needs {MIN_POSITIVE}), "
         f"baseline SKILL on {r['m30']['skill']} (needs {MIN_SKILL}) -> "
         f"{'confirmed' if r['m30']['confirmed'] else 'not confirmed'}",
         f"- 4h pooled: {r['h4']['pooled_trades']} trades from {r['h4']['coins_used']} coins, mean "
         f"{f(r['h4']['pooled_mean_r'])}, CI [{f(r['h4']['ci_lo'])}, {f(r['h4']['ci_hi'])}], long "
         f"{f(r['h4']['long_r'])} / short {f(r['h4']['short_r'])}; coins positive {r['h4']['positive']} "
         f"(needs {MIN_POSITIVE}) -> {'confirmed' if r['h4']['confirmed'] else 'not confirmed'}", "",
         "| coin | tf | verdict | VALID trades | mean R | 95% CI | baseline |", "|---|---|---|---|---|---|---|"]
    for c, d in r["per_coin"].items():
        for tf in sorted(d):
            x = d[tf]
            L.append(f"| {c} | {tf} | {x['verdict']} | {x['valid_trades']} | {f(x['valid_mean_r'])} | "
                     f"[{f(x['valid_ci_lo'])}, {f(x['valid_ci_hi'])}] | {x['baseline'] or '-'} |")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(L) + "\n")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    r = evaluate(C.ROOT)
    (OUT / "summary.json").write_text(json.dumps(r, indent=1, default=str))
    write_report(r)
    print(json.dumps({k: r[k] for k in ("verdict", "m30", "h4")}, indent=1, default=str))


if __name__ == "__main__":
    main()
