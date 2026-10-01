"""Pooled ML entry model: one model trained on many coins (PLAN.md section 20)

    python src/rotation.py --build perp   # once: daily perp bars of every coin (the universe source)
    python src/ml_pool.py --build         # 1h perp klines + funding of the chosen coins
    python src/ml_pool.py                 # TRAIN/VALID, once
    python src/ml_pool.py --final         # HOLDOUT once, only after PASS

Stage 3 of the owner's "train the timing" request. Same model, features,
labels, exit, threshold rule and hyper-parameters as src/ml_entry.py (PLAN
section 19). The only change is the data: ONE long model and ONE short model
are fitted on the rows of UNIVERSE_N coins together, so the model sees about
twenty times more examples than on one coin. The coin's name is not a
feature: a pattern must hold across coins to be learned.

Pre-registered, written before any result of section 19 or 20 was seen:
  * Universe, from TRAIN data only (survivorship-free from the selection
    date): perp instruments listed by MIN_LISTED, still trading on the last
    TRAIN day, ranked by mean daily quote volume over [SELECT_FROM,
    SELECT_TO). A coin delisted later stays in. A relisted symbol after a gap
    of more than 3 days is a different instrument (rotation.split_instruments,
    LUNA).
  * Costs: taker fee as everywhere; slippage C.SLIPPAGE for BTC and ETH,
    ALT_SLIPPAGE for every other coin (thinner books). Stress: both x1.5.
  * Gates (PASS needs all): pooled TRAIN OOF mean > 0; >= MIN_VALID_TRADES
    VALID trades; pooled VALID mean > 0 and weekly-block CI lower bound > 0;
    mean > 0 at cost x1.5; pooled mean above the 95th percentile of 200
    random circular time-shifts of the model's own signals in each coin
    (same long/short counts and clustering, ml_entry.shifted_means); and
    BREADTH: at least MIN_COINS coins with >= MIN_COIN_TRADES VALID trades,
    and at least BREADTH_SHARE of them beat their own random 95th percentile
    with a positive mean.
  * --final: CONFIRMED = holdout pooled mean > 0, CI lower bound > 0, above
    the pooled random median, and at least BREADTH_SHARE of the coins above
    their own random median.
Writes results/_multi/ml_pool/ and the generated journal/_multi/ml_pool.md.
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
import rotation as RO  # noqa: E402

RAW = C.ROOT / "data" / "raw" / "_multi"
CACHE = C.ROOT / "data" / "cache" / "_multi" / "pool_1h"
OUT = C.ROOT / "results" / "_multi" / "ml_pool"
REPORT = C.ROOT / "journal" / "_multi" / "ml_pool.md"

# ---- pre-registered (PLAN.md section 20); a change is a new test
UNIVERSE_N = 20
SELECT_FROM, SELECT_TO = "2021-07-01", "2023-01-01"   # volume ranking window, inside TRAIN
MIN_LISTED = "2021-01-01"                             # >= 2 years of TRAIN rows
MONTHS = ("2020-01", "2026-08")
ALT_SLIPPAGE = 0.0005
MAJORS = {"BTCUSDT", "ETHUSDT"}
MIN_OOF_TRADES = 3000
MIN_VALID_TRADES = 3000
MIN_COIN_TRADES = 100
MIN_COINS = 10
BREADTH_SHARE = 0.5
N_RANDOM = ME.N_RANDOM
SPLITS, FOLDS, PURGE, THRESHOLDS = ME.SPLITS, ME.FOLDS, ME.PURGE, ME.THRESHOLDS


def slippage(sym: str) -> float:
    return C.SLIPPAGE if sym in MAJORS else ALT_SLIPPAGE


# --------------------------------------------------------------------------
# universe (TRAIN data only)
# --------------------------------------------------------------------------
def select_universe(daily: pd.DataFrame, n: int = UNIVERSE_N) -> list[dict]:
    """daily: rotation's long table (symbol, date, open, close, quote_volume).
    Only rows before SELECT_TO are read for the choice; the instrument's end
    date (a later delisting) is kept so its 1h data can be cut there."""
    d = RO.split_instruments(daily)
    end_all = d.groupby("inst")["date"].max()
    pre = d[d["date"] < pd.Timestamp(SELECT_TO, tz="UTC")]
    first = pre.groupby("inst")["date"].min()
    last = pre.groupby("inst")["date"].max()
    last_day = pd.Timestamp(SELECT_TO, tz="UTC") - pd.Timedelta(days=1)
    ok = first[(first <= pd.Timestamp(MIN_LISTED, tz="UTC")) & (last >= last_day)].index
    win = pre[(pre["date"] >= pd.Timestamp(SELECT_FROM, tz="UTC")) & pre["inst"].isin(ok)]
    vol = win.groupby("inst")["quote_volume"].mean().sort_values(ascending=False)
    sym = d.drop_duplicates("inst").set_index("inst")["symbol"]
    return [{"inst": i, "symbol": sym[i], "start": str(first[i].date()),
             "end": str(end_all[i].date()), "mean_quote_volume": float(vol[i])}
            for i in vol.index[:n]]


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
def _ms(t: pd.Series) -> pd.Series:
    t = t.astype("int64")
    return pd.to_datetime(np.where(t > 10**14, t // 1000, t), unit="ms", utc=True)


def build() -> None:
    import datafeed as DF
    p = RO.CACHE / "perp_1d.parquet"
    if not p.exists():
        raise SystemExit(f"no {p}: run  python src/rotation.py --build perp  first")
    OUT.mkdir(parents=True, exist_ok=True)
    uni_path = OUT / "universe.json"
    if uni_path.exists():
        uni = json.loads(uni_path.read_text())
        print(f"universe fixed earlier: {uni_path}")
    else:
        uni = select_universe(pd.read_parquet(p))
        uni_path.write_text(json.dumps(uni, indent=1))
    CACHE.mkdir(parents=True, exist_ok=True)
    months = set(C.month_range(*MONTHS))
    for u in uni:
        s = u["symbol"]
        kp, fp = CACHE / f"{u['inst']}.parquet", CACHE / f"{u['inst']}_funding.parquet"
        if kp.exists() and fp.exists():
            print(f"  {u['inst']}: cached")
            continue
        keys = [k for k in DF.list_keys(f"data/futures/{C.MARKET}/monthly/klines/{s}/1h/")
                if k[-11:-4] in months]
        k = pd.concat([DF._read_one_zip(z, C.KLINE_COLS)
                       for z in (DF.fetch_zip(x, RAW / "perp_1h" / s) for x in keys) if z],
                      ignore_index=True)
        k["open_time"] = _ms(k["open_time"])
        lo = pd.Timestamp(u["start"], tz="UTC")
        hi = pd.Timestamp(u["end"], tz="UTC") + pd.Timedelta(days=1)
        k = (k[(k["open_time"] >= lo) & (k["open_time"] < hi)]
             .drop_duplicates("open_time").sort_values("open_time"))
        k.to_parquet(kp, index=False)
        fkeys = [x for x in DF.list_keys(f"data/futures/{C.MARKET}/monthly/fundingRate/{s}/")
                 if x[-11:-4] in months]
        f = pd.concat([DF._read_one_zip(z, C.FUNDING_COLS)
                       for z in (DF.fetch_zip(x, RAW / "perp_funding" / s) for x in fkeys) if z],
                      ignore_index=True)
        f["calc_time"] = _ms(f["calc_time"])
        f = f[(f["calc_time"] >= lo) & (f["calc_time"] < hi)].sort_values("calc_time")
        f.to_parquet(fp, index=False)
        print(f"  {u['inst']}: {len(k):,} bars {k['open_time'].min()} .. {k['open_time'].max()}, "
              f"{len(f):,} funding rows", flush=True)
    print(f"BUILD OK: {len(uni)} coins")


def load() -> dict[str, tuple[pd.DataFrame, pd.DataFrame]]:
    uni_path = OUT / "universe.json"
    if not uni_path.exists():
        raise SystemExit("no universe: run  python src/ml_pool.py --build")
    coins = {}
    for u in json.loads(uni_path.read_text()):
        k = pd.read_parquet(CACHE / f"{u['inst']}.parquet").set_index("open_time").sort_index()
        k.index.name = "time"
        bars = k[["open", "high", "low", "close", "volume", "taker_buy_base"]].astype("float64")
        coins[u["inst"]] = (bars, pd.read_parquet(CACHE / f"{u['inst']}_funding.parquet"))
    return coins


# --------------------------------------------------------------------------
# the pooled model
# --------------------------------------------------------------------------
def prepare(coins: dict) -> dict:
    """Per coin: bars, funding, slippage, features, labels (each coin on its own)."""
    out = {}
    for inst, (bars, fund) in coins.items():
        slip = slippage(inst.split("#")[0])
        X = ME.features(bars, fund)
        if "funding_last" not in X:
            X["funding_last"] = np.nan
        out[inst] = {"bars": bars, "fund": fund, "slip": slip, "X": X,
                     "lab": ME.labels(bars, fund, slip=slip)}
        print(f"  prepared {inst}: {len(bars):,} bars", flush=True)
    return out


def _cols(P: dict) -> list[str]:
    return sorted(set().union(*(p["X"].columns for p in P.values())))


def _stack(P: dict, masks: dict, what: str):
    cols = _cols(P)
    if what == "X":
        return pd.concat([P[c]["X"].reindex(columns=cols)[masks[c]] for c in P], ignore_index=True)
    return pd.concat([P[c]["lab"][what][masks[c]] for c in P], ignore_index=True)


def _masks(P: dict, a: str, b: str, purge: int = PURGE) -> dict:
    return {c: ME._span(P[c]["bars"].index, a, b, purge=purge) for c in P}


def _fit(P: dict, m: dict):
    X = _stack(P, m, "X")
    return ME.fit(X, _stack(P, m, "long")), ME.fit(X, _stack(P, m, "short"))


def _predict(P: dict, ml, ms, c: str) -> tuple[np.ndarray, np.ndarray]:
    X = P[c]["X"].reindex(columns=_cols(P))
    return ml.predict(X), ms.predict(X)


def _random(P: dict, sides: dict, windows: dict, n: int = N_RANDOM, seed: int = 19):
    """Per coin and pooled: mean net R of n random time-shifts of the model's
    own signals (ml_entry.shifted_means); draw j uses the same seed stream per
    coin, and the pooled draw j is the trade-weighted mean of the coins' draw j."""
    per, sums, cnts = {}, np.zeros(n), np.zeros(n)
    for c in P:
        idx = np.flatnonzero(windows[c][:-1])
        sw = sides[c][idx]
        m = ME.shifted_means(sw, P[c]["lab"]["long"].to_numpy()[idx],
                             P[c]["lab"]["short"].to_numpy()[idx], n=n, seed=seed)
        per[c] = m
        k = int((sw != 0).sum())
        ok = np.isfinite(m)
        sums[ok] += m[ok] * k
        cnts[ok] += k
    pooled = np.where(cnts > 0, sums / np.maximum(cnts, 1), np.nan)
    return per, pooled


def _trades(P: dict, sides: dict, stress: float = 1.0) -> pd.DataFrame:
    fr = []
    for c in P:
        t = XL.simulate(P[c]["bars"], sides[c], ME.EXIT, P[c]["fund"],
                        fee=C.FEE_TAKER * stress, slip=P[c]["slip"] * stress)
        fr.append(t.assign(coin=c))
    return pd.concat(fr, ignore_index=True) if fr else pd.DataFrame()


def _sides(P: dict, ml, ms, thr: float, windows: dict) -> dict:
    out = {}
    for c in P:
        pl, ps = _predict(P, ml, ms, c)
        out[c] = np.where(windows[c], ME.decide(pl, ps, thr), 0.0)
    return out


def _per_coin(t: pd.DataFrame, per_rand: dict, P: dict) -> dict:
    res = {}
    for c in P:
        tc = t[t["coin"] == c] if len(t) else t
        rnd = per_rand[c]
        ok = np.isfinite(rnd)
        res[c] = {"trades": int(len(tc)),
                  "mean_r": float(tc["net_r"].mean()) if len(tc) else None,
                  "random_median": float(np.median(rnd[ok])) if ok.any() else None,
                  "random_p95": float(np.percentile(rnd[ok], 95)) if ok.any() else None}
    return res


def evaluate(P: dict, min_coins: int = MIN_COINS) -> dict:
    """TRAIN out-of-fold threshold -> final pooled model -> VALID verdict (no files)."""
    # 1. threshold from the same purged walk-forward folds, pooled
    oof = {c: (np.full(len(P[c]["bars"]), np.nan), np.full(len(P[c]["bars"]), np.nan)) for c in P}
    for a, b_, c_ in FOLDS:
        fm, pm = _masks(P, a, b_), _masks(P, b_, c_)
        if sum(m.sum() for m in fm.values()) == 0:
            continue
        ml, ms = _fit(P, fm)
        for c in P:
            if pm[c].any():
                pl, ps = _predict(P, ml, ms, c)
                oof[c][0][pm[c]], oof[c][1][pm[c]] = pl[pm[c]], ps[pm[c]]
    thr_table = {}
    for thr in THRESHOLDS:
        rs = []
        for c in P:
            pl, ps = oof[c]
            side = np.where(np.isfinite(pl), ME.decide(np.nan_to_num(pl, nan=-9), np.nan_to_num(ps, nan=-9), thr), 0.0)
            r = np.where(side > 0, P[c]["lab"]["long"], np.where(side < 0, P[c]["lab"]["short"], np.nan))
            rs.append(r[(side != 0) & ~np.isnan(r)])
        r = np.concatenate(rs)
        thr_table[str(thr)] = {"trades": int(len(r)), "mean_r": float(r.mean()) if len(r) else None}
        print(f"OOF thr {thr:.2f}: {thr_table[str(thr)]}", flush=True)
    ok = {k: v for k, v in thr_table.items() if v["trades"] >= MIN_OOF_TRADES}
    thr = float(max(ok, key=lambda k: ok[k]["mean_r"])) if ok else THRESHOLDS[0]

    # 2. final pooled model on all of TRAIN, frozen, applied to VALID (purged end)
    ml, ms = _fit(P, _masks(P, *SPLITS["train"]))
    vw = _masks(P, *SPLITS["valid"])
    sides = _sides(P, ml, ms, thr, vw)
    t = _trades(P, sides)
    v = XL.summarize(t)
    stress = XL.summarize(_trades(P, sides, stress=1.5))
    per_rand, pooled_rand = _random(P, sides, vw)
    p95 = float(np.nanpercentile(pooled_rand, 95)) if np.isfinite(pooled_rand).any() else np.inf
    coins = _per_coin(t, per_rand, P)
    elig = {c: x for c, x in coins.items() if x["trades"] >= MIN_COIN_TRADES}
    beat = [c for c, x in elig.items() if x["random_p95"] is not None
            and x["mean_r"] > 0 and x["mean_r"] > x["random_p95"]]
    share = len(beat) / len(elig) if elig else 0.0
    oof_mean = ok.get(str(thr), {}).get("mean_r") if ok else None
    gates = {"oof_mean>0": (oof_mean or -1) > 0,
             f"valid_trades>={MIN_VALID_TRADES}": v.get("trades", 0) >= MIN_VALID_TRADES,
             "valid_mean>0": v.get("mean_r", -1) > 0,
             "valid_ci_lo>0": (v.get("ci_lo") or -1) > 0,
             "stress_mean>0": stress.get("mean_r", -1) > 0,
             "beats_random_p95": v.get("mean_r", -9) > p95,
             f"coins>={min_coins}": len(elig) >= min_coins,
             f"breadth>={BREADTH_SHARE}": share >= BREADTH_SHARE}
    failed = [k for k, g in gates.items() if not g]
    imp = sorted(zip(_cols(P), ml.feature_importance() + ms.feature_importance()), key=lambda x: -x[1])[:10]
    last = t.loc[t["entry_time"].idxmax()] if len(t) else None
    return {"coins_n": len(P), "tf": ME.TF, "exit": "time_only", "threshold": thr, "oof": thr_table,
            "valid": v, "valid_stress": stress, "random_mean": float(np.nanmean(pooled_rand)),
            "random_p95": p95, "per_coin": coins, "breadth": {"eligible": len(elig), "beat": beat,
                                                              "share": share},
            "valid_last_exit": str(last["entry_time"] + pd.Timedelta(minutes=ME.TF) * int(last["bars"]))
            if last is not None else None,
            "verdict": "REJECT" if failed else "PASS", "gates_failed": failed,
            "top_features": [[k, int(s)] for k, s in imp]}


def holdout(P: dict, res: dict) -> dict:
    ml, ms = _fit(P, _masks(P, *SPLITS["train"]))
    w = _masks(P, *SPLITS["holdout"])
    sides = _sides(P, ml, ms, res["threshold"], w)
    t = _trades(P, sides)
    h = XL.summarize(t)
    per_rand, pooled_rand = _random(P, sides, w)
    coins = _per_coin(t, per_rand, P)
    elig = {c: x for c, x in coins.items() if x["trades"] >= MIN_COIN_TRADES}
    above = [c for c, x in elig.items() if x["random_median"] is not None
             and x["mean_r"] > x["random_median"]]
    share = len(above) / len(elig) if elig else 0.0
    h.update(random_median=float(np.nanmedian(pooled_rand)), per_coin=coins,
             breadth={"eligible": len(elig), "above_median": above, "share": share})
    h["verdict"] = ("CONFIRMED" if h.get("mean_r", -1) > 0 and (h.get("ci_lo") or -1) > 0
                    and h["mean_r"] > h["random_median"] and share >= BREADTH_SHARE else "FAILED")
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
        h = holdout(prepare(load()), res)
        lock.write_text(json.dumps(h, indent=1, default=str))
        write_report(res)
        print(json.dumps({k: h[k] for k in ("trades", "mean_r", "ci_lo", "random_median", "verdict")}, indent=1))
        return
    if res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    res = evaluate(prepare(load()))
    res_path.write_text(json.dumps(res, indent=1, default=str))
    write_report(res)
    print(f"\nPOOL ({res['coins_n']} coins): threshold {res['threshold']} -> {res['verdict']}  "
          f"failed {res['gates_failed']}\nVALID {res['valid']}")


def write_report(r: dict) -> None:
    v, nan = r["valid"], float("nan")
    L = ["# Pooled ML entry model (PLAN.md section 20)", "",
         "GENERATED by `src/ml_pool.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}** ({r['coins_n']} coins, threshold {r['threshold']} R chosen on TRAIN "
         f"out-of-fold; failed: {r['gates_failed'] or 'none'})", "",
         f"- VALID {v.get('trades', 0)} trades: mean net R {v.get('mean_r', nan):+.4f}, 95% weekly-block CI "
         f"[{v.get('ci_lo', nan):+.4f}, {v.get('ci_hi', nan):+.4f}], gross {v.get('gross_r', nan):+.4f}, "
         f"long {v.get('long_r', nan):+.3f} / short {v.get('short_r', nan):+.3f}",
         f"- the model's signals shifted in time, per coin (same counts and clustering): mean "
         f"{r['random_mean']:+.4f}, "
         f"95th pct {r['random_p95']:+.4f}",
         f"- cost x1.5: mean {r['valid_stress'].get('mean_r', nan):+.4f}",
         f"- breadth: {len(r['breadth']['beat'])} of {r['breadth']['eligible']} coins beat their own random "
         f"95th pct (share {r['breadth']['share']:.2f}, needs {BREADTH_SHARE})", "",
         "| coin | VALID trades | mean net R | random median | random p95 |", "|---|---|---|---|---|"]
    f = (lambda x: "-" if x is None else f"{x:+.4f}")
    for c, x in r["per_coin"].items():
        L.append(f"| {c} | {x['trades']} | {f(x['mean_r'])} | {f(x['random_median'])} | {f(x['random_p95'])} |")
    L += ["", "| threshold | OOF trades | OOF mean net R |", "|---|---|---|"]
    for k, t in r["oof"].items():
        L.append(f"| {k} | {t['trades']} | {f(t['mean_r'])} |")
    L += ["", "Top features: " + ", ".join(f"{k} ({s})" for k, s in r["top_features"]), ""]
    h = OUT / "holdout.json"
    if h.exists():
        hj = json.loads(h.read_text())
        L += [f"**HOLDOUT: {hj['verdict']}** - {hj.get('trades', 0)} trades, mean {f(hj.get('mean_r'))}, "
              f"CI [{f(hj.get('ci_lo'))}, {f(hj.get('ci_hi'))}], random median {f(hj['random_median'])}, "
              f"coins above their random median: share {hj['breadth']['share']:.2f}", ""]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--final", action="store_true")
    a = ap.parse_args()
    build() if a.build else run(a.final)


if __name__ == "__main__":
    main()
