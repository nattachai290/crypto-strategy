"""Pooled ML entry model, round 2: smarter training on the same coins (PLAN.md section 21)

    python src/ml_pool2.py           # TRAIN/VALID, once (uses ml_pool.py's cached 20 coins)
    python src/ml_pool2.py --final   # HOLDOUT once, only after PASS

Round 1 (section 20, _multi Exp 005/006) was REJECT on its CI. Its review found
three things a smarter model could change WITHOUT looking at VALID again:
  1. the 24-bar hold made cost a large share of each trade (LESSONS section 1:
     longer holds pay less cost per unit of move);
  2. each coin only saw its own chart: nothing about BTC or the whole market;
  3. the hyper-parameters were fixed defaults, never tuned (on TRAIN).
It also found a weakness in the control: a time shift keeps counts and
clustering but not volatility, and a model that only learned "trade when
volatility is high" pays less cost per R than its shifted copies. Round 2
therefore compares GROSS R (price move only, before fees, slippage and
funding) with the shifted copies' GROSS R.

Everything below is fixed before the run. Every choice is made on TRAIN
(2020-2022) out-of-fold; VALID is used once.
  * Same 20 coins (results/_multi/ml_pool/universe.json, chosen on TRAIN volume)
    and the same 1h cache; no new download.
  * Decisions every 4 hours (signal at the close of hours 3, 7, ..., 23 UTC).
  * Exit: symmetric, 8 x 1h-ATR stop, out after 96 bars (4 days).
  * Features: the section 19 set, plus cross-coin features at the same bar
    close: the equal-weight market return (24/72/168 h), the coin's return
    relative to it, market breadth (share of coins up over 24 h), BTC's return
    (24/72/168 h) and BTC's 168 h volatility.
  * Tuning on TRAIN: 8 LightGBM settings x 4 thresholds, chosen by the highest
    out-of-fold net mean over 3 purged expanding folds (>= MIN_OOF_TRADES).
  * Gates on VALID (all needed), stricter than round 1 because this is the
    fourth ML attempt on the same VALID:
      TRAIN OOF mean > 0; >= MIN_VALID_TRADES trades; net mean > 0 and
      weekly-block CI lower bound > 0; net mean > 0 at cost x1.5; pooled GROSS
      mean above the 95th percentile of 200 time-shifted copies' GROSS mean;
      >= 10 coins with >= MIN_COIN_TRADES trades and at least half of them
      with a positive net mean AND a gross mean above their own shifted p95;
      both legs (long and short) net > 0.
  * --final: CONFIRMED = holdout net mean > 0, CI lower bound > 0, gross above
    the shifted copies' median, and at least half the coins above their own.
Writes results/_multi/ml_pool2/ and the generated journal/_multi/ml_pool2.md.
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
import ml_entry as ME  # noqa: E402
import ml_pool as MP  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "ml_pool2"
REPORT = C.ROOT / "journal" / "_multi" / "ml_pool2.md"

# ---- pre-registered (PLAN.md section 21); a change is a new test
STEP = 4                                   # decide every 4 hours
EXIT = dict(stop_atr=8.0, tp_r=0.0, be_r=0.0, trail_at_r=0.0, trail_atr=0.0, max_hold=96)
PURGE_ROWS = (EXIT["max_hold"] + 2) // STEP + 2   # decision rows dropped before a split end
CROSS_K = (24, 72, 168)
THRESHOLDS = (0.0, 0.05, 0.10, 0.20)
GRID = [dict(num_leaves=nl, min_data_in_leaf=md, rounds=r)
        for nl in (7, 31) for md in (300, 3000) for r in (150, 500)]
MIN_OOF_TRADES = 2000
MIN_VALID_TRADES = 2000
MIN_COIN_TRADES = 50
MIN_COINS = 10
BREADTH_SHARE = 0.5
N_RANDOM = 200
SPLITS, FOLDS = ME.SPLITS, ME.FOLDS


# --------------------------------------------------------------------------
# features and labels
# --------------------------------------------------------------------------
def cross_features(coins: dict) -> dict[str, pd.DataFrame]:
    """Per coin, market-wide features at each bar close (bars <= i only)."""
    lo = min(b.index[0] for b, _ in coins.values())
    hi = max(b.index[-1] for b, _ in coins.values())
    full = pd.date_range(lo, hi, freq="1h")
    close = pd.DataFrame({c: b["close"].reindex(full) for c, (b, _) in coins.items()})
    lr = {k: np.log(close / close.shift(k)) for k in CROSS_K}
    mkt = {k: lr[k].mean(axis=1, skipna=True) for k in CROSS_K}
    up = (lr[24] > 0).sum(axis=1)
    n = lr[24].notna().sum(axis=1)
    breadth = (up / n.where(n > 0)).astype(float)
    anchor = "BTCUSDT" if "BTCUSDT" in coins else None
    out = {}
    for c, (b, _) in coins.items():
        f = pd.DataFrame(index=full)
        for k in CROSS_K:
            f[f"mkt_ret_{k}"] = mkt[k]
            f[f"rel_ret_{k}"] = lr[k][c] - mkt[k]
            f[f"btc_ret_{k}"] = lr[k][anchor] if anchor else np.nan
        f["breadth_24"] = breadth
        f["btc_vol_168"] = (np.log(close[anchor]).diff().rolling(168).std() if anchor else np.nan)
        out[c] = f.reindex(b.index)
    return out


def decision_mask(index: pd.DatetimeIndex) -> np.ndarray:
    return np.asarray(index.hour % STEP == STEP - 1)


def labels(b: pd.DataFrame, funding, slip: float) -> pd.DataFrame:
    """Net and gross R of a long and a short at every decision bar (signal-bar index)."""
    d = decision_mask(b.index)
    d[-1] = False
    out = pd.DataFrame(np.nan, index=b.index, columns=["long", "short", "g_long", "g_short"])
    for col, s in (("long", 1.0), ("short", -1.0)):
        t = XL.simulate(b, np.where(d, s, 0.0), EXIT, funding, fee=C.FEE_TAKER, slip=slip)
        pos = b.index.get_indexer(t["entry_time"]) - 1
        out.iloc[pos, out.columns.get_loc(col)] = t["net_r"].to_numpy()
        out.iloc[pos, out.columns.get_loc("g_" + col)] = t["gross_r"].to_numpy()
    return out


def prepare(coins: dict) -> dict:
    """Per coin, decision rows only: features (own + cross) and labels."""
    cross = cross_features(coins)
    P = {}
    for c, (bars, fund) in coins.items():
        slip = MP.slippage(c.split("#")[0])
        X = ME.features(bars, fund)
        if "funding_last" not in X:
            X["funding_last"] = np.nan
        X = pd.concat([X, cross[c]], axis=1)
        lab = labels(bars, fund, slip)
        d = decision_mask(bars.index)
        P[c] = {"bars": bars, "fund": fund, "slip": slip, "X": X[d], "lab": lab[d],
                "pos": np.flatnonzero(d)}
        print(f"  prepared {c}: {int(d.sum()):,} decision rows", flush=True)
    return P


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------
def fit(X: pd.DataFrame, y: pd.Series, cfg: dict):
    import lightgbm as lgb
    params = dict(ME.LGB_PARAMS, num_leaves=cfg["num_leaves"], min_data_in_leaf=cfg["min_data_in_leaf"])
    ok = y.notna()
    return lgb.train(params, lgb.Dataset(X[ok], y[ok]), num_boost_round=cfg["rounds"])


def _cols(P):
    return sorted(set().union(*(p["X"].columns for p in P.values())))


def _masks(P, a, b):
    return {c: ME._span(P[c]["X"].index, a, b, purge=PURGE_ROWS) for c in P}


def _fit(P, m, cfg):
    cols = _cols(P)
    X = pd.concat([P[c]["X"].reindex(columns=cols)[m[c]] for c in P], ignore_index=True)
    yl = pd.concat([P[c]["lab"]["long"][m[c]] for c in P], ignore_index=True)
    ys = pd.concat([P[c]["lab"]["short"][m[c]] for c in P], ignore_index=True)
    return fit(X, yl, cfg), fit(X, ys, cfg)


def _pred(P, models, c):
    X = P[c]["X"].reindex(columns=_cols(P))
    return models[0].predict(X), models[1].predict(X)


def _sides(P, models, thr, w):
    return {c: np.where(w[c], ME.decide(*_pred(P, models, c), thr), 0.0) for c in P}


def _trades(P, sides, stress=1.0):
    fr = []
    for c in P:
        full = np.zeros(len(P[c]["bars"]))
        full[P[c]["pos"]] = sides[c]
        t = XL.simulate(P[c]["bars"], full, EXIT, P[c]["fund"],
                        fee=C.FEE_TAKER * stress, slip=P[c]["slip"] * stress)
        fr.append(t.assign(coin=c))
    return pd.concat(fr, ignore_index=True)


def _control(P, sides, w, n=N_RANDOM, seed=19):
    """GROSS mean R of n circular time-shifts of the model's decision sequence,
    per coin and pooled (trade-weighted per draw)."""
    per, sums, cnts = {}, np.zeros(n), np.zeros(n)
    for c in P:
        idx = np.flatnonzero(w[c])
        sw = sides[c][idx]
        m = ME.shifted_means(sw, P[c]["lab"]["g_long"].to_numpy()[idx],
                             P[c]["lab"]["g_short"].to_numpy()[idx], n=n, seed=seed)
        per[c] = m
        k = int((sw != 0).sum())
        ok = np.isfinite(m)
        sums[ok] += m[ok] * k
        cnts[ok] += k
    return per, np.where(cnts > 0, sums / np.maximum(cnts, 1), np.nan)


def _q(x, q):
    x = x[np.isfinite(x)]
    return float(np.percentile(x, q)) if len(x) else None


def _per_coin(t, per):
    res = {}
    for c, rnd in per.items():
        tc = t[t["coin"] == c]
        res[c] = {"trades": int(len(tc)),
                  "mean_r": float(tc["net_r"].mean()) if len(tc) else None,
                  "gross_r": float(tc["gross_r"].mean()) if len(tc) else None,
                  "ctrl_gross_median": _q(rnd, 50), "ctrl_gross_p95": _q(rnd, 95)}
    return res


def evaluate(P: dict, grid: list = GRID, min_coins: int = MIN_COINS) -> dict:
    # 1. tune (setting, threshold) on purged TRAIN folds, out-of-fold
    table = []
    for gi, cfg in enumerate(grid):
        oof = {c: (np.full(len(P[c]["X"]), np.nan), np.full(len(P[c]["X"]), np.nan)) for c in P}
        for a, b_, c_ in FOLDS:
            fm, pm = _masks(P, a, b_), _masks(P, b_, c_)
            if sum(m.sum() for m in fm.values()) == 0:
                continue
            models = _fit(P, fm, cfg)
            for c in P:
                if pm[c].any():
                    pl, ps = _pred(P, models, c)
                    oof[c][0][pm[c]], oof[c][1][pm[c]] = pl[pm[c]], ps[pm[c]]
        for thr in THRESHOLDS:
            rs = []
            for c in P:
                pl, ps = oof[c]
                side = np.where(np.isfinite(pl), ME.decide(np.nan_to_num(pl, nan=-9),
                                                           np.nan_to_num(ps, nan=-9), thr), 0.0)
                L, S = P[c]["lab"]["long"].to_numpy(), P[c]["lab"]["short"].to_numpy()
                r = np.where(side > 0, L, np.where(side < 0, S, np.nan))
                rs.append(r[(side != 0) & np.isfinite(r)])
            r = np.concatenate(rs)
            table.append({"setting": gi, **cfg, "threshold": thr, "trades": int(len(r)),
                          "mean_r": float(r.mean()) if len(r) else None})
            print(f"OOF setting {gi} {cfg} thr {thr:.2f}: {table[-1]['trades']} trades, "
                  f"mean {table[-1]['mean_r']}", flush=True)
    ok = [x for x in table if x["trades"] >= MIN_OOF_TRADES and x["mean_r"] is not None]
    best = max(ok, key=lambda x: x["mean_r"]) if ok else table[0]
    cfg = grid[best["setting"]]
    thr = best["threshold"]

    # 2. final models on all of TRAIN, frozen; VALID once
    models = _fit(P, _masks(P, *SPLITS["train"]), cfg)
    w = _masks(P, *SPLITS["valid"])
    sides = _sides(P, models, thr, w)
    t = _trades(P, sides)
    v = XL.summarize(t)
    stress = XL.summarize(_trades(P, sides, stress=1.5))
    per, pooled = _control(P, sides, w)
    p95 = _q(pooled, 95)
    coins = _per_coin(t, per)
    elig = {c: x for c, x in coins.items() if x["trades"] >= MIN_COIN_TRADES}
    beat = [c for c, x in elig.items() if x["ctrl_gross_p95"] is not None
            and x["mean_r"] > 0 and x["gross_r"] > x["ctrl_gross_p95"]]
    share = len(beat) / len(elig) if elig else 0.0
    gates = {"oof_mean>0": (best["mean_r"] or -1) > 0 and best in ok,
             f"valid_trades>={MIN_VALID_TRADES}": v.get("trades", 0) >= MIN_VALID_TRADES,
             "valid_mean>0": v.get("mean_r", -1) > 0,
             "valid_ci_lo>0": (v.get("ci_lo") or -1) > 0,
             "stress_mean>0": stress.get("mean_r", -1) > 0,
             "gross_beats_shift_p95": p95 is not None and v.get("gross_r", -9) > p95,
             f"coins>={min_coins}": len(elig) >= min_coins,
             f"breadth>={BREADTH_SHARE}": share >= BREADTH_SHARE,
             "both_legs>0": (v.get("long_r") or -1) > 0 and (v.get("short_r") or -1) > 0}
    failed = [k for k, g in gates.items() if not g]
    imp = sorted(zip(_cols(P), models[0].feature_importance("gain") + models[1].feature_importance("gain")),
                 key=lambda x: -x[1])[:12]
    last = t.loc[t["entry_time"].idxmax()] if len(t) else None
    return {"coins_n": len(P), "step_hours": STEP, "exit": EXIT, "setting": cfg, "threshold": thr,
            "oof_best": best, "oof_table": table, "valid": v, "valid_stress": stress,
            "shift_gross_mean": _q(pooled, 50), "shift_gross_p95": p95, "per_coin": coins,
            "breadth": {"eligible": len(elig), "beat": beat, "share": share},
            "valid_last_exit": str(last["entry_time"] + pd.Timedelta(hours=1) * int(last["bars"]))
            if last is not None else None,
            "verdict": "REJECT" if failed else "PASS", "gates_failed": failed,
            "top_features_gain": [[k, round(float(s), 1)] for k, s in imp]}


def holdout(P: dict, res: dict) -> dict:
    cfg = {k: res["setting"][k] for k in ("num_leaves", "min_data_in_leaf", "rounds")}
    models = _fit(P, _masks(P, *SPLITS["train"]), cfg)
    w = _masks(P, *SPLITS["holdout"])
    sides = _sides(P, models, res["threshold"], w)
    t = _trades(P, sides)
    h = XL.summarize(t)
    per, pooled = _control(P, sides, w)
    coins = _per_coin(t, per)
    elig = {c: x for c, x in coins.items() if x["trades"] >= MIN_COIN_TRADES}
    above = [c for c, x in elig.items() if x["ctrl_gross_median"] is not None
             and x["gross_r"] > x["ctrl_gross_median"]]
    share = len(above) / len(elig) if elig else 0.0
    med = _q(pooled, 50)
    h.update(shift_gross_median=med, per_coin=coins, breadth={"eligible": len(elig), "above": above,
                                                              "share": share})
    h["verdict"] = ("CONFIRMED" if h.get("mean_r", -1) > 0 and (h.get("ci_lo") or -1) > 0
                    and med is not None and h.get("gross_r", -9) > med and share >= BREADTH_SHARE
                    else "FAILED")
    return h


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
        h = holdout(prepare(MP.load()), res)
        lock.write_text(json.dumps(h, indent=1, default=str))
        write_report(res)
        print(json.dumps({k: h.get(k) for k in ("trades", "mean_r", "ci_lo", "verdict")}, indent=1))
        return
    if res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    res = evaluate(prepare(MP.load()))
    res_path.write_text(json.dumps(res, indent=1, default=str))
    write_report(res)
    print(f"\nPOOL2 ({res['coins_n']} coins): setting {res['setting']} threshold {res['threshold']} -> "
          f"{res['verdict']}  failed {res['gates_failed']}\nVALID {res['valid']}")


def write_report(r: dict) -> None:
    v, nan = r["valid"], float("nan")
    f = (lambda x: "-" if x is None else f"{x:+.4f}")
    L = ["# Pooled ML entry model, round 2 (PLAN.md section 21)", "",
         "GENERATED by `src/ml_pool2.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}** ({r['coins_n']} coins, decisions every {r['step_hours']} h, exit 8 ATR / 96 bars; "
         f"TRAIN chose {r['setting']}, threshold {r['threshold']}; failed: {r['gates_failed'] or 'none'})", "",
         f"- TRAIN out-of-fold at the chosen cell: {r['oof_best']['trades']} trades, mean {f(r['oof_best']['mean_r'])}",
         f"- VALID {v.get('trades', 0)} trades: mean net R {v.get('mean_r', nan):+.4f}, 95% weekly-block CI "
         f"[{v.get('ci_lo', nan):+.4f}, {v.get('ci_hi', nan):+.4f}], gross {v.get('gross_r', nan):+.4f}, "
         f"long {v.get('long_r', nan):+.3f} / short {v.get('short_r', nan):+.3f}",
         f"- shifted copies, GROSS mean R: median {f(r['shift_gross_mean'])}, 95th pct {f(r['shift_gross_p95'])}",
         f"- cost x1.5: mean {r['valid_stress'].get('mean_r', nan):+.4f}",
         f"- breadth: {len(r['breadth']['beat'])} of {r['breadth']['eligible']} coins (share "
         f"{r['breadth']['share']:.2f}, needs {BREADTH_SHARE})", "",
         "| coin | VALID trades | net R | gross R | shifted gross median | shifted gross p95 |",
         "|---|---|---|---|---|---|"]
    for c, x in r["per_coin"].items():
        L.append(f"| {c} | {x['trades']} | {f(x['mean_r'])} | {f(x['gross_r'])} | "
                 f"{f(x['ctrl_gross_median'])} | {f(x['ctrl_gross_p95'])} |")
    L += ["", "| setting | leaves | min leaf | rounds | threshold | OOF trades | OOF mean net R |",
          "|---|---|---|---|---|---|---|"]
    for x in r["oof_table"]:
        L.append(f"| {x['setting']} | {x['num_leaves']} | {x['min_data_in_leaf']} | {x['rounds']} | "
                 f"{x['threshold']} | {x['trades']} | {f(x['mean_r'])} |")
    L += ["", "Top features (gain): " + ", ".join(f"{k} ({s})" for k, s in r["top_features_gain"]), ""]
    h = OUT / "holdout.json"
    if h.exists():
        hj = json.loads(h.read_text())
        L += [f"**HOLDOUT: {hj['verdict']}** - {hj.get('trades', 0)} trades, mean {f(hj.get('mean_r'))}, "
              f"CI [{f(hj.get('ci_lo'))}, {f(hj.get('ci_hi'))}], gross {f(hj.get('gross_r'))} vs shifted "
              f"median {f(hj.get('shift_gross_median'))}, breadth {hj['breadth']['share']:.2f}", ""]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--final", action="store_true")
    run(ap.parse_args().final)


if __name__ == "__main__":
    main()
