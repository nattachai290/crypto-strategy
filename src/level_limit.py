"""Level limit orders: rest a limit AT support/resistance and wait (PLAN.md section 24)

    SYMBOL=BTCUSDT python src/level_limit.py --tf 60
    SYMBOL=BTCUSDT python src/level_limit.py --tf 240
    SYMBOL=ETHUSDT python src/level_limit.py --tf 60      (and --tf 240)
    ... --final   HOLDOUT once, only after PASS

The owner's idea: instead of waiting for a confirmation candle (PLAN section
22, 0 of 16), place the order in ADVANCE at the level and let price come to
it. A buy limit rests at a support level, a sell limit at a resistance level.
If the level holds, the entry is at the best price and the stop can sit just
beyond the level; the entry pays the maker fee and no slippage.

The cost of this, modelled honestly: a resting limit fills whenever price
trades to it, so every move that slices THROUGH the level fills too (adverse
selection), and the moves that turn just before the level never fill.

Mechanics (all fixed here; test 20 checks them by hand):
  * Levels, known at the close of bar i (bars <= i only):
      prev_day: the previous completed UTC day's low (support) / high (resistance);
      swing:    live pivot lows/highs, PIVOT bars each side (known PIVOT bars
                later), alive until a close beyond them or MAX_AGE bars.
  * At the close of bar i, for each side, the NEAREST level on the correct
    side of the close within MAX_DIST_ATR x ATR(i) gets an order, unless that
    level already had one. The order rests from bar i+1 for EXPIRY bars.
  * Fill: the first bar whose low (buy) / high (sell) reaches the limit. Fill
    price = the limit, or the open if the bar opens beyond it (gap). Maker fee,
    no slippage.
  * Stop: limit -/+ stop_atr x ATR(i). On the fill bar, if the bar also trades
    through the stop, the trade is stopped on that bar (pessimistic). The
    target (tp_r x R, a resting limit: maker fee, no slippage) is not allowed
    on the fill bar. Stop and time exits: taker fee + slippage. Funding on the
    notional, as everywhere.
  * Each order is simulated on its own (orders may overlap).
TRAIN chooses one cell of GRID (level kind x stop x target) by mean net R
with >= MIN_TRADES fills. VALID gates (all needed):
  TRAIN mean > 0; >= MIN_TRADES VALID fills; VALID mean > 0 and weekly-block
  CI lower bound > 0; mean > 0 at fees and slippage x1.5; and the real level
  orders beat the 95th percentile of N_CONTROL control sets on TRAIN AND on
  VALID. A control set places the same number of orders, at random bars of
  the same window, same side mix, at the same distances from the close (in
  ATR) as the real orders, with the same stop/target/expiry/hold: if the
  LEVEL matters, orders at levels must beat orders at the same distance
  anywhere.
--final: CONFIRMED = holdout mean > 0, CI lower bound > 0, above the control
median. Writes results/<SYMBOL>/level_limit/ and journal/<SYMBOL>/level_limit.md.
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
import exit_lab as XL  # noqa: E402
import indicators as ta  # noqa: E402
import recipes as RC  # noqa: E402

# ---- pre-registered (PLAN.md section 24); a change is a new test
ATR_N = 14
PIVOT = 10
MAX_AGE = 500
MAX_DIST_ATR = 3.0
EXPIRY = 24          # bars an order rests
MAX_HOLD = 48        # bars after the fill
GRID = [dict(level=lv, stop_atr=s, tp_r=t) for lv in ("prev_day", "swing")
        for s in (1.0, 2.0) for t in (2.0, 3.0)]
MIN_TRADES = 100
N_CONTROL = 200
SPLITS = XL.SPLITS


# --------------------------------------------------------------------------
# levels and orders
# --------------------------------------------------------------------------
def levels(b: pd.DataFrame, kind: str) -> tuple[list, list]:
    """Per bar i: list of live support prices and live resistance prices,
    known at the close of bar i."""
    h, l, c = (b[k].to_numpy(float) for k in ("high", "low", "close"))
    n = len(b)
    sup: list = [[] for _ in range(n)]
    res: list = [[] for _ in range(n)]
    if kind == "prev_day":
        hi_p, lo_p = RC._daily_extremes(b, 1)
        for i in range(n):
            if np.isfinite(lo_p[i]):
                sup[i] = [lo_p[i]]
            if np.isfinite(hi_p[i]):
                res[i] = [hi_p[i]]
        return sup, res
    if kind != "swing":
        raise ValueError(kind)
    ph = RC._pine_pivot(b["high"], PIVOT, True)
    pl = RC._pine_pivot(b["low"], PIVOT, False)
    lows: list = []
    highs: list = []
    for i in range(n):
        if np.isfinite(pl[i]):
            lows.append([pl[i], i - PIVOT])
        if np.isfinite(ph[i]):
            highs.append([ph[i], i - PIVOT])
        lows = [v for v in lows if c[i] >= v[0] and i - v[1] <= MAX_AGE]
        highs = [v for v in highs if c[i] <= v[0] and i - v[1] <= MAX_AGE]
        sup[i] = [v[0] for v in lows]
        res[i] = [v[0] for v in highs]
    return sup, res


def place_orders(b: pd.DataFrame, kind: str, atr: np.ndarray) -> pd.DataFrame:
    """One order per level: at bar i's close, the nearest live level on each
    side within MAX_DIST_ATR x ATR(i), if that level has not had an order."""
    c = b["close"].to_numpy(float)
    sup, res = levels(b, kind)
    used_s, used_r = set(), set()
    rows = []
    for i in range(len(b) - 1):
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        below = [p for p in sup[i] if p < c[i] and c[i] - p <= MAX_DIST_ATR * a]
        if below:
            p = max(below)
            if p not in used_s:
                used_s.add(p)
                rows.append((i, 1.0, p, (c[i] - p) / a, a))
        above = [p for p in res[i] if p > c[i] and p - c[i] <= MAX_DIST_ATR * a]
        if above:
            p = min(above)
            if p not in used_r:
                used_r.add(p)
                rows.append((i, -1.0, p, (p - c[i]) / a, a))
    return pd.DataFrame(rows, columns=["bar", "side", "limit", "dist_atr", "atr"])


# --------------------------------------------------------------------------
# simulation
# --------------------------------------------------------------------------
def _funding_arrays(times: np.ndarray, funding: pd.DataFrame | None):
    n = len(times)
    if funding is None or not len(funding):
        z = np.zeros(n, dtype=int)
        return z, z, z, np.zeros(1)
    ft = pd.to_datetime(funding["calc_time"], utc=True).to_numpy("datetime64[ns]")
    fr = funding["last_funding_rate"].to_numpy(float)
    order = np.argsort(ft)
    ft, fr = ft[order], fr[order]
    step = np.median(np.diff(times))
    bar_end = np.r_[times[1:], times[-1] + step]
    return (np.searchsorted(ft, times, side="left"), np.searchsorted(ft, times, side="right"),
            np.searchsorted(ft, bar_end, side="left"), np.r_[0.0, np.cumsum(fr)])


def simulate_orders(o, h, l, c, orders: pd.DataFrame, stop_atr: float, tp_r: float,
                    times=None, funding=None, fee_maker=C.FEE_MAKER, fee_taker=C.FEE_TAKER,
                    slip=C.SLIPPAGE, expiry=EXPIRY, max_hold=MAX_HOLD) -> pd.DataFrame:
    """Net R of every filled order, each on its own. Unfilled orders are dropped."""
    n = len(c)
    if times is None:
        times = np.arange(n).astype("datetime64[h]").astype("datetime64[ns]")
    lo_in, lo_ex, hi_, pre = _funding_arrays(np.asarray(times), funding)
    rows = []
    for i, s, L, a in orders[["bar", "side", "limit", "atr"]].itertuples(index=False):
        i = int(i)
        j = None
        for k in range(i + 1, min(i + 1 + expiry, n)):
            if (s > 0 and l[k] <= L) or (s < 0 and h[k] >= L):
                j = k
                break
        if j is None:
            continue
        entry = min(o[j], L) if s > 0 else max(o[j], L)
        d = stop_atr * a
        stop = L - s * d
        tp = entry + s * tp_r * d if tp_r > 0 else 0.0
        fund, px, reason, fee_out, slip_out = 0.0, None, "eod", fee_taker, slip
        k = j
        for k in range(j, min(j + max_hold, n)):
            a0 = lo_ex[k] if k == j else lo_in[k]
            if hi_[k] > a0:
                fund += o[k] * (pre[hi_[k]] - pre[a0]) * s
            if (s > 0 and l[k] <= stop) or (s < 0 and h[k] >= stop):
                if k == j:  # filled and stopped on the same bar; a gap fill beyond the stop exits at the fill
                    px = stop if (s > 0 and entry > stop) or (s < 0 and entry < stop) else entry
                else:
                    gap = (o[k] < stop) if s > 0 else (o[k] > stop)
                    px = o[k] if gap else stop
                reason = "stop"
                break
            if k > j and tp > 0 and ((s > 0 and h[k] >= tp) or (s < 0 and l[k] <= tp)):
                gap = (o[k] > tp) if s > 0 else (o[k] < tp)
                px, reason, fee_out, slip_out = (o[k] if gap else tp), "target", fee_maker, 0.0
                break
            if k - j + 1 >= max_hold:
                px, reason = c[k], "time"
                break
        if px is None:
            px = c[k]
        px_adj = px * (1 - slip_out * s)
        gross = s * (px - entry) / d
        cost = (entry * fee_maker + px_adj * fee_out) / d + slip_out * px / d + fund / d
        rows.append((times[j], times[k], s, gross - cost, gross, reason, k - j + 1))
    t = pd.DataFrame(rows, columns=["entry_time", "exit_time", "side", "net_r", "gross_r", "reason", "bars"])
    t["entry_time"] = pd.to_datetime(t["entry_time"], utc=True)
    t["exit_time"] = pd.to_datetime(t["exit_time"], utc=True)
    return t


def control_orders(orders: pd.DataFrame, c: np.ndarray, atr: np.ndarray, lo: int, hi: int,
                   rng: np.random.Generator) -> pd.DataFrame:
    """Same count, side mix and distances (in ATR) as the real orders, at random bars of [lo, hi)."""
    if orders.empty or hi <= lo:
        return orders.iloc[:0]
    bars = rng.integers(lo, hi, len(orders))
    a = atr[bars]
    side = orders["side"].to_numpy()
    lim = c[bars] - side * orders["dist_atr"].to_numpy() * a
    out = pd.DataFrame({"bar": bars, "side": side, "limit": lim, "dist_atr": orders["dist_atr"].to_numpy(),
                        "atr": a})
    return out[np.isfinite(out["atr"]) & (out["atr"] > 0)]


def _in(t: pd.DataFrame, split: str) -> pd.DataFrame:
    """Trades filled in the split AND closed before it ends (no split's trade uses the next split's prices)."""
    w = XL.window(t, split)
    return w[w["exit_time"] < pd.Timestamp(SPLITS[split][1], tz="UTC")]


def _idx(index: pd.DatetimeIndex, split: str) -> tuple[int, int]:
    a, b = (pd.Timestamp(x, tz="UTC") for x in SPLITS[split])
    return int(np.searchsorted(index, a)), int(np.searchsorted(index, b))


def evaluate(b: pd.DataFrame, funding=None, grid=GRID, n_control=N_CONTROL, min_trades=MIN_TRADES,
             seed: int = 24) -> dict:
    o, h, l, c = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    atr = ta.atr_(b["high"], b["low"], b["close"], ATR_N).to_numpy(float)
    times = b.index.to_numpy("datetime64[ns]")
    orders = {kind: place_orders(b, kind, atr) for kind in sorted({g["level"] for g in grid})}
    cells = []
    for g in grid:
        t = simulate_orders(o, h, l, c, orders[g["level"]], g["stop_atr"], g["tp_r"], times, funding)
        tr = XL.summarize(_in(t, "train"))
        cells.append({**g, "train": tr, "_t": t})
        print(f"  {g}: TRAIN {tr.get('trades', 0)} fills, mean {tr.get('mean_r')}", flush=True)
    ok = [x for x in cells if x["train"].get("trades", 0) >= min_trades]
    best = max(ok, key=lambda x: x["train"]["mean_r"]) if ok else max(cells, key=lambda x: x["train"].get("trades", 0))
    g = {k: best[k] for k in ("level", "stop_atr", "tp_r")}
    t = best["_t"]
    tr, v = best["train"], XL.summarize(_in(t, "valid"))
    stress = XL.summarize(_in(simulate_orders(o, h, l, c, orders[g["level"]], g["stop_atr"], g["tp_r"], times,
                                              funding, fee_maker=C.FEE_MAKER * 1.5, fee_taker=C.FEE_TAKER * 1.5,
                                              slip=C.SLIPPAGE * 1.5), "valid"))
    rng = np.random.default_rng(seed)
    ctl = {}
    for split in ("train", "valid"):
        lo, hi = _idx(b.index, split)
        real = orders[g["level"]]
        real = real[(real["bar"] >= lo) & (real["bar"] < hi)]
        means = []
        for _ in range(n_control):
            co = control_orders(real, c, atr, lo, hi - EXPIRY - MAX_HOLD, rng)
            ct = simulate_orders(o, h, l, c, co, g["stop_atr"], g["tp_r"], times, funding)
            means.append(ct["net_r"].mean() if len(ct) else np.nan)
        m = np.array(means, float)
        ctl[split] = {"median": float(np.nanmedian(m)), "p95": float(np.nanpercentile(m, 95)),
                      "orders": int(len(real))}
    gates = {"train_mean>0": (tr.get("mean_r") or -1) > 0,
             f"valid_trades>={min_trades}": v.get("trades", 0) >= min_trades,
             "valid_mean>0": v.get("mean_r", -1) > 0,
             "valid_ci_lo>0": (v.get("ci_lo") or -1) > 0,
             "stress_mean>0": stress.get("mean_r", -1) > 0,
             "beats_control_p95_train": (tr.get("mean_r") or -9) > ctl["train"]["p95"],
             "beats_control_p95_valid": v.get("mean_r", -9) > ctl["valid"]["p95"]}
    failed = [k for k, x in gates.items() if not x]
    return {"chosen": g, "train": tr, "valid": v, "valid_stress": stress, "control": ctl,
            "fill_rate_valid": (v.get("trades", 0) / ctl["valid"]["orders"]) if ctl["valid"]["orders"] else None,
            "cells": [{k: x[k] for k in ("level", "stop_atr", "tp_r", "train")} for x in cells],
            "verdict": "REJECT" if failed else "PASS", "gates_failed": failed}


# --------------------------------------------------------------------------
def run(tf: int, final: bool = False) -> None:
    import experiment as E
    bars = E.get_bars(tf)[["open", "high", "low", "close"]]
    fund = E.load_funding()
    out = C.RESULTS / "level_limit"
    out.mkdir(parents=True, exist_ok=True)
    res_path = out / f"tf{tf}.json"
    if final:
        res = json.loads(res_path.read_text()) if res_path.exists() else None
        if not res or res["verdict"] != "PASS":
            raise SystemExit("--final refused: needs a PASS from the TRAIN/VALID run")
        lock = out / f"holdout_tf{tf}.json"
        if lock.exists():
            raise SystemExit(f"--final refused: holdout already used ({lock})")
        g = res["chosen"]
        o, h, l, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        atr = ta.atr_(bars["high"], bars["low"], bars["close"], ATR_N).to_numpy(float)
        orders = place_orders(bars, g["level"], atr)
        t = simulate_orders(o, h, l, c, orders, g["stop_atr"], g["tp_r"], bars.index.to_numpy("datetime64[ns]"), fund)
        hres = XL.summarize(_in(t, "holdout"))
        lo, hi = _idx(bars.index, "holdout")
        real = orders[(orders["bar"] >= lo) & (orders["bar"] < hi)]
        rng = np.random.default_rng(25)
        m = [simulate_orders(o, h, l, c, control_orders(real, c, atr, lo, hi - EXPIRY - MAX_HOLD, rng),
                             g["stop_atr"], g["tp_r"], bars.index.to_numpy("datetime64[ns]"), fund)["net_r"].mean()
             for _ in range(N_CONTROL)]
        hres["control_median"] = float(np.nanmedian(m))
        hres["verdict"] = ("CONFIRMED" if hres.get("mean_r", -1) > 0 and (hres.get("ci_lo") or -1) > 0
                           and hres["mean_r"] > hres["control_median"] else "FAILED")
        lock.write_text(json.dumps(hres, indent=1, default=str))
        write_report(out)
        print(json.dumps(hres, indent=1, default=str))
        return
    if res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    res = {"symbol": C.SYMBOL, "tf": tf, **evaluate(bars, fund)}
    res_path.write_text(json.dumps(res, indent=1, default=str))
    write_report(out)
    print(f"\n{C.SYMBOL} {tf}m: chosen {res['chosen']} -> {res['verdict']}  failed {res['gates_failed']}")


def write_report(out: Path) -> None:
    f = (lambda x: "-" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:+.4f}")
    L = [f"# {C.SYMBOL} - limit orders resting at support/resistance (PLAN.md section 24)", "",
         "GENERATED by `src/level_limit.py`. Do not edit by hand.", ""]
    for p in sorted(out.glob("tf*.json")):
        r = json.loads(p.read_text())
        v, tr = r["valid"], r["train"]
        L += [f"## {r['tf']}m: **{r['verdict']}** (TRAIN chose {r['chosen']}; failed: {r['gates_failed'] or 'none'})", "",
              f"- TRAIN {tr.get('trades', 0)} fills, mean net R {f(tr.get('mean_r'))}; control p95 "
              f"{f(r['control']['train']['p95'])}",
              f"- VALID {v.get('trades', 0)} fills of {r['control']['valid']['orders']} orders, mean net R "
              f"{f(v.get('mean_r'))}, 95% CI [{f(v.get('ci_lo'))}, {f(v.get('ci_hi'))}], gross {f(v.get('gross_r'))}, "
              f"long {f(v.get('long_r'))} / short {f(v.get('short_r'))}, exits {v.get('exit_mix')}",
              f"- control (same distances, random bars): VALID median {f(r['control']['valid']['median'])}, "
              f"p95 {f(r['control']['valid']['p95'])}",
              f"- cost x1.5: VALID mean {f(r['valid_stress'].get('mean_r'))}", "",
              "| level | stop ATR | target R | TRAIN fills | TRAIN mean R |", "|---|---|---|---|---|"]
        for x in r["cells"]:
            L.append(f"| {x['level']} | {x['stop_atr']} | {x['tp_r']} | {x['train'].get('trades', 0)} | "
                     f"{f(x['train'].get('mean_r'))} |")
        L.append("")
        hp = p.parent / f"holdout_tf{r['tf']}.json"
        if hp.exists():
            hj = json.loads(hp.read_text())
            L += [f"**HOLDOUT: {hj['verdict']}** - {hj.get('trades', 0)} fills, mean {f(hj.get('mean_r'))}, "
                  f"CI [{f(hj.get('ci_lo'))}, {f(hj.get('ci_hi'))}], control median {f(hj.get('control_median'))}", ""]
    (C.JOURNAL / "level_limit.md").write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tf", type=int, default=60, choices=(60, 240))
    ap.add_argument("--final", action="store_true")
    a = ap.parse_args()
    run(a.tf, a.final)


if __name__ == "__main__":
    main()
