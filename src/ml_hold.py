"""ML that decides entry AND exit, with no time limit (PLAN.md section 27)

    python src/ml_hold.py           # TRAIN/VALID, once (uses ml_pool.py's cached 20 coins)
    python src/ml_hold.py --final   # HOLDOUT once, only after PASS

The owner's request (2026-10-02): "the model decides, at every bar it holds,
whether to keep the position or close it; no time limit". Every earlier ML
round (sections 19-21) chose entries only and closed every trade on a clock
(24 bars or 4 days); the owner has since ruled out time exits (AGENTS.md step
3b). Here one pooled LightGBM model is asked one question every 4 hours on 20
coins: how far will price move over the next H hours, in ATRs? A fixed rule
with hysteresis turns that forecast into a desired position:
    flat  -> long  when the forecast is above the entry bar e_in,
             short when it is below -e_in;
    long  -> flat  when the forecast falls under the exit bar e_out
             (e_out = 0 "flip", or e_in / 2 "half"), short likewise;
    long  -> short when the forecast is below -e_in (and the reverse).
e_in is a rolling quantile q of the coin's own recent |forecast| (the last
ROLL decisions, causal), so the bar has the same meaning in every fold and
for the final model. A position ends ONLY when the desired position changes,
when the fixed protective stop (STOP_ATR x 1h ATR at entry) is hit, or at the
end of the period. There is no maximum holding time.

Everything is fixed before the run; every choice is made on TRAIN out-of-fold.
  * Same 20 coins and 1h cache as sections 20-21 (ml_pool.py --build).
  * Features: section 21's set (own bars + cross-coin + BTC), at the bar close.
  * Label: log(open[i+1+H] / open[i+1]) / (ATR14 / close) at decision bar i.
  * TRAIN tuning: GRID (4 LightGBM settings) x Q_IN x EXIT_MODES, chosen by
    the highest out-of-fold net mean R per trade (>= MIN_OOF_TRADES trades)
    over the 3 purged expanding folds of section 19.
  * Timing control: the desired-position sequence is shifted in time (200
    circular shifts per coin, same long/short/flat durations, so market drift
    helps the copies as much as the model). The statistic is the position-held
    return per hour in ATR units, before stops and costs: pure timing.
  * Gates on VALID (all needed): TRAIN OOF mean > 0; >= MIN_VALID_TRADES
    trades; net mean > 0 and weekly-block CI lower bound > 0; net mean > 0 at
    cost x1.5; pooled timing above the shifted copies' 95th percentile;
    >= MIN_COINS coins with >= MIN_COIN_TRADES trades and at least half of them
    net > 0 AND timing above their own shifted median; both legs net > 0.
  * --final: CONFIRMED = holdout net mean > 0, CI lower bound > 0, timing
    above the shifted median, and at least half the coins above their own.
Writes results/_multi/ml_hold/ (summary.json, trades_<split>.csv.gz,
desired_<split>.csv.gz for the charts) and the generated journal/_multi/ml_hold.md.
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
import ml_entry as ME  # noqa: E402
import ml_pool as MP  # noqa: E402
import ml_pool2 as M2  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "ml_hold"
REPORT = C.ROOT / "journal" / "_multi" / "ml_hold.md"

# ---- pre-registered (PLAN.md section 27); a change is a new test
STEP = 4                        # decide every 4 hours (hours 3, 7, ..., 23 UTC close)
H = 24                          # label horizon, hours
STOP_ATR = 8.0                  # protective stop only; no trailing, no target, no clock
ATR_N = 14
ROLL, MIN_ROLL = 180, 60        # rolling window (decision rows) for the entry bar
Q_IN = (0.6, 0.75, 0.9)
EXIT_MODES = ("flip", "half")
GRID = [dict(num_leaves=nl, min_data_in_leaf=1000, rounds=r) for nl in (7, 31) for r in (150, 500)]
PURGE_ROWS = H // STEP + 2
MIN_OOF_TRADES = 300
MIN_VALID_TRADES = 300
MIN_COIN_TRADES = 15
MIN_COINS = 10
BREADTH_SHARE = 0.5
N_RANDOM = 200
SPLITS, FOLDS = ME.SPLITS, ME.FOLDS


# --------------------------------------------------------------------------
# the policy and the simulator
# --------------------------------------------------------------------------
def entry_bar(p: np.ndarray, q: float) -> np.ndarray:
    """Rolling q-quantile of |p| over the last ROLL values (causal; NaN while warming up)."""
    return pd.Series(np.abs(p)).rolling(ROLL, min_periods=MIN_ROLL).quantile(q).to_numpy()


def policy(p: np.ndarray, e_in: np.ndarray, mode: str) -> np.ndarray:
    """Desired position (-1/0/+1) after each decision, with hysteresis."""
    out, s = np.zeros(len(p)), 0.0
    for t in range(len(p)):
        x, e = p[t], e_in[t]
        if np.isfinite(x) and np.isfinite(e):
            e_out = 0.0 if mode == "flip" else 0.5 * e
            if x > e:
                s = 1.0
            elif x < -e:
                s = -1.0
            elif s > 0 and x < e_out:
                s = 0.0
            elif s < 0 and x > -e_out:
                s = 0.0
        out[t] = s
    return out


def simulate(b: pd.DataFrame, target: np.ndarray, atr: np.ndarray, funding: pd.DataFrame | None = None,
             fee: float = C.FEE_TAKER, slip: float = C.SLIPPAGE, stop_atr: float = STOP_ATR) -> pd.DataFrame:
    """Trades of a desired-position path on bars `b` (already cut to one period).

    target[i] (NaN = no decision) is decided at the close of bar i and acted on
    at the open of bar i+1: close the open position (reason 'signal') if it
    differs, then open the new side if it is not flat. The stop (stop_atr x
    atr[i] from the fill) is checked from the fill bar on, stop-first, gaps
    filled at the open. Whatever is open at the last bar closes at its close
    ('eod'). Costs as exit_lab.simulate: taker fee and slippage per side,
    funding as notional x rate. R = the stop distance at entry."""
    o, h, l, c = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    n = len(b)
    times = b.index.to_numpy("datetime64[ns]")
    if funding is not None and len(funding):
        ft = pd.to_datetime(funding["calc_time"], utc=True).to_numpy("datetime64[ns]")
        fr = funding["last_funding_rate"].to_numpy(float)
        order = np.argsort(ft)
        ft, fr = ft[order], fr[order]
        step = np.median(np.diff(times)) if n > 1 else np.timedelta64(1, "h")
        bar_end = np.r_[times[1:], times[-1] + step]
        lo_in = np.searchsorted(ft, times, side="left")
        lo_ex = np.searchsorted(ft, times, side="right")
        hi_ = np.searchsorted(ft, bar_end, side="left")
        pre = np.r_[0.0, np.cumsum(fr)]
    else:
        lo_in = lo_ex = hi_ = np.zeros(n, dtype=int)
        pre = np.zeros(1)
    rows = []
    pos, entry, stop, d, j, fund = 0.0, 0.0, 0.0, 0.0, 0, 0.0

    def close(k, px, reason):
        px_adj = px * (1 - slip * pos)
        gross = pos * (px_adj - entry) / d
        fees = (entry + px_adj) * fee / d
        rows.append((b.index[j], b.index[k], pos, entry, px_adj, stop, gross - fees - fund / d,
                     gross + slip * (entry + px_adj) / d, reason, k - j + 1))

    for k in range(1, n):
        want = target[k - 1]
        if np.isfinite(want) and want != pos:
            if pos != 0:
                close(k - 1, o[k], "signal")   # exit at the open of k: the trade's last bar is k-1
                pos = 0.0
            a = atr[k - 1]
            if want != 0 and np.isfinite(a) and a > 0:
                pos, j, fund = want, k, 0.0
                d = stop_atr * a
                entry = o[k] * (1 + slip * pos)
                stop = entry - pos * d
        if pos == 0:
            continue
        a0 = lo_ex[k] if k == j else lo_in[k]
        if hi_[k] > a0:
            fund += o[k] * (pre[hi_[k]] - pre[a0]) * pos
        if (l[k] <= stop) if pos > 0 else (h[k] >= stop):
            gap = o[k] < stop if pos > 0 else o[k] > stop
            close(k, o[k] if gap else stop, "stop")
            pos = 0.0
    if pos != 0:
        close(n - 1, c[n - 1], "eod")
    return pd.DataFrame(rows, columns=["entry_time", "exit_time", "side", "entry_px", "exit_px", "stop_px",
                                       "net_r", "gross_r", "reason", "bars"])


def held_hours(n: int, dec_pos: np.ndarray, desired: np.ndarray) -> np.ndarray:
    """Hourly position implied by the decisions (held during bar k = the last
    decision at a bar <= k-1); 0 before the first decision."""
    x = np.full(n, np.nan)
    ok = dec_pos + 1 < n
    x[dec_pos[ok] + 1] = desired[ok]
    return pd.Series(x).ffill().fillna(0.0).to_numpy()


def timing_sums(pos_h: np.ndarray, rn: np.ndarray) -> tuple[float, int]:
    m = (pos_h != 0) & np.isfinite(rn)
    return float((pos_h[m] * rn[m]).sum()), int(m.sum())


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
def prepare(coins: dict) -> dict:
    """Per coin: bars, ATR, features and labels at decision rows, hourly normalised returns."""
    cross = M2.cross_features(coins)
    P = {}
    for c, (bars, fund) in coins.items():
        X = ME.features(bars, fund)
        if "funding_last" not in X:
            X["funding_last"] = np.nan
        X = pd.concat([X, cross[c]], axis=1)
        atr = ta.atr_(bars["high"], bars["low"], bars["close"], ATR_N)
        afrac = (atr / bars["close"]).to_numpy(float)
        o = bars["open"].to_numpy(float)
        nxt = np.r_[o[1:], np.nan]                                   # open[i+1]
        fut = np.r_[o[1 + H:], np.full(min(1 + H, len(o)), np.nan)][:len(o)]   # open[i+1+H]
        y = np.log(fut / nxt) / afrac
        rn = np.r_[np.log(o[1:] / o[:-1]), np.nan] / np.r_[np.nan, afrac[:-1]]   # hour k: open k -> k+1
        d = M2.decision_mask(bars.index) if STEP == M2.STEP else np.asarray(bars.index.hour % STEP == STEP - 1)
        d[-1] = False
        P[c] = {"bars": bars, "fund": fund, "slip": MP.slippage(c.split("#")[0]), "atr": atr.to_numpy(float),
                "X": X[d], "y": pd.Series(y[d], index=bars.index[d]), "pos": np.flatnonzero(d), "rn": rn}
        print(f"  prepared {c}: {int(d.sum()):,} decision rows", flush=True)
    return P


def _cols(P):
    return sorted(set().union(*(p["X"].columns for p in P.values())))


def _masks(P, a, b, purge=PURGE_ROWS):
    return {c: ME._span(P[c]["X"].index, a, b, purge=purge) for c in P}


def _fit(P, m, cfg):
    cols = _cols(P)
    X = pd.concat([P[c]["X"].reindex(columns=cols)[m[c]] for c in P], ignore_index=True)
    y = pd.concat([P[c]["y"][m[c]] for c in P], ignore_index=True)
    return M2.fit(X, y, cfg)


def _pred(P, model, c):
    return model.predict(P[c]["X"].reindex(columns=_cols(P)))


def _window(P, c, a, b):
    """Bar slice [a, b) of a coin and the decision rows inside it (positions within the slice)."""
    idx = P[c]["bars"].index
    lo, hi = idx.searchsorted(pd.Timestamp(a, tz="UTC")), idx.searchsorted(pd.Timestamp(b, tz="UTC"))
    rows = np.flatnonzero((P[c]["pos"] >= lo) & (P[c]["pos"] < hi))
    return lo, hi, rows


def run_window(P, c, pred, a, b, q, mode, stress=1.0):
    """Desired path and trades of one coin on [a, b) from predictions at its decision rows."""
    lo, hi, rows = _window(P, c, a, b)
    p = pred[rows]
    desired = policy(p, entry_bar(p, q), mode)
    tgt = np.full(hi - lo, np.nan)
    tgt[P[c]["pos"][rows] - lo] = desired
    t = simulate(P[c]["bars"].iloc[lo:hi], tgt, P[c]["atr"][lo:hi], P[c]["fund"],
                 fee=C.FEE_TAKER * stress, slip=P[c]["slip"] * stress)
    return desired, rows, lo, hi, t.assign(coin=c)


def control(P, paths, n=N_RANDOM, seed=27):
    """Timing statistic of the model and of n circular shifts of its desired path, per coin and pooled."""
    rng = np.random.default_rng(seed)
    per, S, N = {}, np.zeros(n), np.zeros(n)
    model_s, model_n = 0.0, 0
    for c, (desired, rows, lo, hi) in paths.items():
        dec = P[c]["pos"][rows] - lo
        rn = P[c]["rn"][lo:hi]
        s0, n0 = timing_sums(held_hours(hi - lo, dec, desired), rn)
        model_s, model_n = model_s + s0, model_n + n0
        shifts = np.empty(n)
        for k in range(n):
            r = int(rng.integers(1, max(len(desired), 2)))
            s, m = timing_sums(held_hours(hi - lo, dec, np.roll(desired, r)), rn)
            shifts[k] = s / m if m else np.nan
            if m:
                S[k] += s
                N[k] += m
        per[c] = {"timing": s0 / n0 if n0 else None, "shifts": shifts}
    pooled = np.where(N > 0, S / np.maximum(N, 1), np.nan)
    return (model_s / model_n if model_n else None), per, pooled


def _q(x, q):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return float(np.percentile(x, q)) if len(x) else None


def _summ(t):
    s = XL.summarize(t.rename(columns={}))
    if len(t):
        s["avg_hold_h"] = float(t["bars"].mean())
        s["per_year"] = {str(y): float(g["net_r"].mean()) for y, g in t.groupby(t["entry_time"].dt.year)}
    return s


def evaluate(P: dict, grid: list = GRID, min_coins: int = MIN_COINS, keep: bool = False) -> dict:
    # 1. TRAIN out-of-fold: one model per fold per setting, then every policy cell
    table, oof_paths = [], {}
    for gi, cfg in enumerate(grid):
        preds = {}
        for a, b_, c_ in FOLDS:
            fm = _masks(P, a, b_)
            if sum(m.sum() for m in fm.values()) == 0:
                continue
            model = _fit(P, fm, cfg)
            preds[(b_, c_)] = {c: _pred(P, model, c) for c in P}
        for q in Q_IN:
            for mode in EXIT_MODES:
                rs = []
                for (b_, c_), pr in preds.items():
                    for c in P:
                        rs.append(run_window(P, c, pr[c], b_, c_, q, mode)[4]["net_r"].to_numpy())
                r = np.concatenate(rs) if rs else np.array([])
                table.append({"setting": gi, **cfg, "q_in": q, "exit": mode, "trades": int(len(r)),
                              "mean_r": float(r.mean()) if len(r) else None})
                print(f"OOF setting {gi} {cfg} q {q} {mode}: {table[-1]['trades']} trades, "
                      f"mean {table[-1]['mean_r']}", flush=True)
    ok = [x for x in table if x["trades"] >= MIN_OOF_TRADES and x["mean_r"] is not None]
    best = max(ok, key=lambda x: x["mean_r"]) if ok else table[0]
    cfg, q, mode = grid[best["setting"]], best["q_in"], best["exit"]

    # 2. final model on all of TRAIN, frozen; VALID once
    model = _fit(P, _masks(P, *SPLITS["train"]), cfg)
    a, b = SPLITS["valid"]
    fr, paths, stress_fr, desired_rows = [], {}, [], []
    for c in P:
        pr = _pred(P, model, c)
        desired, rows, lo, hi, t = run_window(P, c, pr, a, b, q, mode)
        fr.append(t)
        stress_fr.append(run_window(P, c, pr, a, b, q, mode, stress=1.5)[4])
        paths[c] = (desired, rows, lo, hi)
        desired_rows.append(pd.DataFrame({"coin": c, "time": P[c]["X"].index[rows], "pred": pr[rows],
                                          "desired": desired}))
    t = pd.concat(fr, ignore_index=True)
    v, stress = _summ(t), _summ(pd.concat(stress_fr, ignore_index=True))
    timing, per, pooled = control(P, paths)
    p95 = _q(pooled, 95)
    coins = {}
    for c in P:
        tc = t[t["coin"] == c]
        coins[c] = {"trades": int(len(tc)), "mean_r": float(tc["net_r"].mean()) if len(tc) else None,
                    "timing": per[c]["timing"], "shift_median": _q(per[c]["shifts"], 50),
                    "shift_p95": _q(per[c]["shifts"], 95), "avg_hold_h": float(tc["bars"].mean()) if len(tc) else None}
    elig = {c: x for c, x in coins.items() if x["trades"] >= MIN_COIN_TRADES}
    beat = [c for c, x in elig.items() if x["mean_r"] > 0 and x["timing"] is not None
            and x["shift_median"] is not None and x["timing"] > x["shift_median"]]
    share = len(beat) / len(elig) if elig else 0.0
    gates = {"oof_mean>0": (best["mean_r"] or -1) > 0 and best in ok,
             f"valid_trades>={MIN_VALID_TRADES}": v.get("trades", 0) >= MIN_VALID_TRADES,
             "valid_mean>0": v.get("mean_r", -1) > 0,
             "valid_ci_lo>0": (v.get("ci_lo") or -1) > 0,
             "stress_mean>0": stress.get("mean_r", -1) > 0,
             "timing_beats_shift_p95": p95 is not None and timing is not None and timing > p95,
             f"coins>={min_coins}": len(elig) >= min_coins,
             f"breadth>={BREADTH_SHARE}": share >= BREADTH_SHARE,
             "both_legs>0": (v.get("long_r") or -1) > 0 and (v.get("short_r") or -1) > 0}
    failed = [k for k, g in gates.items() if not g]
    imp = sorted(zip(_cols(P), model.feature_importance("gain")), key=lambda x: -x[1])[:12]
    in_mkt = sum(timing_sums(held_hours(hi - lo, P[c]["pos"][rows] - lo, des),
                             np.ones(hi - lo))[1] for c, (des, rows, lo, hi) in paths.items())
    total_h = sum(hi - lo for _, (_, _, lo, hi) in paths.items())
    res = {"coins_n": len(P), "step_hours": STEP, "horizon_h": H, "stop_atr": STOP_ATR, "setting": cfg,
           "q_in": q, "exit_mode": mode, "oof_best": best, "oof_table": table, "valid": v,
           "valid_stress": stress, "timing": timing, "shift_median": _q(pooled, 50), "shift_p95": p95,
           "time_in_market": in_mkt / total_h if total_h else None, "per_coin": coins,
           "breadth": {"eligible": len(elig), "beat": beat, "share": share},
           "valid_last_exit": str(t["exit_time"].max()) if len(t) else None,
           "verdict": "REJECT" if failed else "PASS", "gates_failed": failed,
           "top_features_gain": [[k, round(float(s), 1)] for k, s in imp]}
    if keep:
        res["_trades"], res["_desired"] = t, pd.concat(desired_rows, ignore_index=True)
    return res


def holdout(P: dict, res: dict) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    cfg = {k: res["setting"][k] for k in ("num_leaves", "min_data_in_leaf", "rounds")}
    model = _fit(P, _masks(P, *SPLITS["train"]), cfg)
    a, b = SPLITS["holdout"]
    fr, paths, des = [], {}, []
    for c in P:
        pr = _pred(P, model, c)
        desired, rows, lo, hi, t = run_window(P, c, pr, a, b, res["q_in"], res["exit_mode"])
        fr.append(t)
        paths[c] = (desired, rows, lo, hi)
        des.append(pd.DataFrame({"coin": c, "time": P[c]["X"].index[rows], "pred": pr[rows], "desired": desired}))
    t = pd.concat(fr, ignore_index=True)
    h = _summ(t)
    timing, per, pooled = control(P, paths)
    elig = [c for c in P if (t["coin"] == c).sum() >= MIN_COIN_TRADES]
    above = [c for c in elig if per[c]["timing"] is not None and _q(per[c]["shifts"], 50) is not None
             and per[c]["timing"] > _q(per[c]["shifts"], 50)]
    share = len(above) / len(elig) if elig else 0.0
    med = _q(pooled, 50)
    h.update(timing=timing, shift_median=med, breadth={"eligible": len(elig), "above": above, "share": share})
    h["verdict"] = ("CONFIRMED" if h.get("mean_r", -1) > 0 and (h.get("ci_lo") or -1) > 0 and med is not None
                    and timing is not None and timing > med and share >= BREADTH_SHARE else "FAILED")
    return h, t, pd.concat(des, ignore_index=True)


# --------------------------------------------------------------------------
def run(final: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    res_path, lock = OUT / "summary.json", OUT / "holdout.json"
    if final:
        res = json.loads(res_path.read_text()) if res_path.exists() else None
        if not res or res["verdict"] != "PASS":
            raise SystemExit("--final refused: needs a PASS from the TRAIN/VALID run")
        if lock.exists():
            raise SystemExit(f"--final refused: holdout already used ({lock})")
        h, t, des = holdout(prepare(MP.load()), res)
        lock.write_text(json.dumps(h, indent=1, default=str))
        t.to_csv(OUT / "trades_holdout.csv.gz", index=False)
        des.to_csv(OUT / "desired_holdout.csv.gz", index=False)
        write_report(res)
        print(json.dumps({k: h.get(k) for k in ("trades", "mean_r", "ci_lo", "verdict")}, indent=1))
        return
    if res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    res = evaluate(prepare(MP.load()), keep=True)
    res.pop("_trades").to_csv(OUT / "trades_valid.csv.gz", index=False)
    res.pop("_desired").to_csv(OUT / "desired_valid.csv.gz", index=False)
    res_path.write_text(json.dumps(res, indent=1, default=str))
    write_report(res)
    print(f"\nML_HOLD ({res['coins_n']} coins): setting {res['setting']} q {res['q_in']} exit {res['exit_mode']} "
          f"-> {res['verdict']}  failed {res['gates_failed']}\nVALID {res['valid']}")


def write_report(r: dict) -> None:
    v, nan = r["valid"], float("nan")
    f = (lambda x: "-" if x is None else f"{x:+.4f}")
    L = ["# ML decides entry and exit, no time limit (PLAN.md section 27)", "",
         "GENERATED by `src/ml_hold.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}** ({r['coins_n']} coins, decisions every {r['step_hours']} h, forecast {r['horizon_h']} h, "
         f"stop {r['stop_atr']} ATR, no clock; TRAIN chose {r['setting']}, q_in {r['q_in']}, exit {r['exit_mode']}; "
         f"failed: {r['gates_failed'] or 'none'})", "",
         f"- TRAIN out-of-fold at the chosen cell: {r['oof_best']['trades']} trades, mean {f(r['oof_best']['mean_r'])}",
         f"- VALID {v.get('trades', 0)} trades: mean net R {v.get('mean_r', nan):+.4f}, 95% weekly-block CI "
         f"[{v.get('ci_lo', nan):+.4f}, {v.get('ci_hi', nan):+.4f}], gross {v.get('gross_r', nan):+.4f}, "
         f"long {v.get('long_r', nan):+.3f} / short {v.get('short_r', nan):+.3f}, average hold "
         f"{v.get('avg_hold_h', nan):.1f} h, exits {v.get('exit_mix')}, time in market {r['time_in_market']}",
         f"- timing (held return per hour, ATR units, before stops and costs): model {f(r['timing'])}, "
         f"shifted copies median {f(r['shift_median'])}, 95th pct {f(r['shift_p95'])}",
         f"- cost x1.5: mean {r['valid_stress'].get('mean_r', nan):+.4f}",
         f"- breadth: {len(r['breadth']['beat'])} of {r['breadth']['eligible']} coins (share "
         f"{r['breadth']['share']:.2f}, needs {BREADTH_SHARE})",
         f"- per year: {v.get('per_year')}", "",
         "| coin | VALID trades | net R | avg hold h | timing | shifted median | shifted p95 |",
         "|---|---|---|---|---|---|---|"]
    for c, x in r["per_coin"].items():
        L.append(f"| {c} | {x['trades']} | {f(x['mean_r'])} | "
                 f"{'-' if x['avg_hold_h'] is None else round(x['avg_hold_h'], 1)} | {f(x['timing'])} | "
                 f"{f(x['shift_median'])} | {f(x['shift_p95'])} |")
    L += ["", "| setting | leaves | rounds | q_in | exit | OOF trades | OOF mean net R |",
          "|---|---|---|---|---|---|---|"]
    for x in r["oof_table"]:
        L.append(f"| {x['setting']} | {x['num_leaves']} | {x['rounds']} | {x['q_in']} | {x['exit']} | "
                 f"{x['trades']} | {f(x['mean_r'])} |")
    L += ["", "Top features (gain): " + ", ".join(f"{k} ({s})" for k, s in r["top_features_gain"]), ""]
    hp = OUT / "holdout.json"
    if hp.exists():
        hj = json.loads(hp.read_text())
        L += [f"**HOLDOUT: {hj['verdict']}** - {hj.get('trades', 0)} trades, mean {f(hj.get('mean_r'))}, "
              f"CI [{f(hj.get('ci_lo'))}, {f(hj.get('ci_hi'))}], timing {f(hj.get('timing'))} vs shifted "
              f"median {f(hj.get('shift_median'))}, breadth {hj['breadth']['share']:.2f}", ""]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--final", action="store_true")
    run(ap.parse_args().final)


if __name__ == "__main__":
    main()
