"""Train wide, trade the monthly top 20 large coins (PLAN.md section 36, re-registered)

    python src/ml_wide.py --build   # 1h/4h/1d perp klines + funding of every coin needed
    python src/ml_wide.py           # TRAIN/VALID, once
    python src/ml_wide.py --final   # HOLDOUT once, only after PASS (shared with sections 31-34)

The owner's frame (2026-10-04): the goal is an ML model that trades, and it will
trade only LARGE coins. "Large", as the owner chose: crypto only (no stock,
gold, oil perps), listed for at least a year, and each month the top TRADE_N by
mean daily quote volume over the 30 days before the month. That is exactly what
can be known when trading live, so the backtest picks no coin with hindsight.

Hypothesis: the 1h model learns more, and forecasts more steadily, when (a) it
is trained on every crypto perp that was among the TRAIN_TOP most traded at the
time (later large coins, more sell-offs, new regimes; never traded unless large)
and (b) three label horizons (12, 24, 48 bars) are averaged.

The comparison (TRAIN chooses, VALID judges once), both forms on the same coins,
the same monthly traded sets and the same account:
  * "narrow": section 30's recipe - one 24-bar model trained only on section
    30's 47 coins' rows - forecasting every traded coin;
  * "wide": one model per horizon trained on the 47 coins' rows PLUS every other
    crypto perp's rows in months when it was a monthly top-TRAIN_TOP member;
    forecast = mean of pred_h x sqrt(24 / h).
  Both: section 30's chosen 1h setting, refit monthly; features from
  ml_wf2.prepare over all training coins (perp bars for coins outside the 47).
  Agreement: one 4h model with section 30's 4h recipe (24 bars, section 30's 4h
  setting) trained on the 47 coins' rows, forecasting every traded coin, shared
  by both forms. Account: section 31's chosen cell (4h agreement, confidence
  sizing, 5% cap), its policy, stop, costs. A NEW position on a coin opens only
  in a month when the coin is in that month's traded set; holding and exits are
  untouched.
A "narrow" choice is REJECT (gate train_chose_wide). VALID gates: section 31's,
breadth over coins with >= MIN_COIN_TRADES trades (>= MIN_COINS of them).
Data-gap fix (_multi Exp 047): membership and listing age are computed per
SYMBOL from daily volume, never from rotation.split_instruments runs, so a hole
in Binance's daily files (SOL/XRP/LTC, 2022-02-26..28) no longer drops a coin.
Non-crypto: symbols whose Binance exchangeInfo underlyingType is not COIN
(fetched by --build) plus NON_CRYPTO_FALLBACK; they only exist from 2025, so
they matter for the holdout only.
Holdout: sections 31-36 share ONE holdout (the same model line).
Writes results/_multi/s36_ml_wide_1h/ and the generated journal/_multi/s36_ml_wide_1h.md.
"""
from __future__ import annotations

import argparse
import gc
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
import indicators as ta  # noqa: E402
import ml_flow as FL  # noqa: E402
import ml_hold as MH  # noqa: E402
import ml_mkt as MK  # noqa: E402
import ml_port as MP  # noqa: E402
import ml_wf as WF  # noqa: E402
import ml_wf2 as W2  # noqa: E402
import ml_wf3 as W3  # noqa: E402
import ml_xs as XS  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "s36_ml_wide_1h"
REPORT = C.ROOT / "journal" / "_multi" / "s36_ml_wide_1h.md"
SOURCE_UNIVERSE = C.ROOT / "results" / "_multi" / "s28_ml_wf" / WF.UNIVERSE_FILE

# ---- pre-registered (PLAN.md section 36, re-registered in _multi Exp 048)
TRADE_N = 20
TRAIN_TOP = 50
MIN_AGE_DAYS = 365
VOL_DAYS, VOL_MIN_DAYS = 30, 20
MONTHS_FROM = "2019-10"
HORIZONS = (12, 24, 48)
CELL = FL.CELL
NON_CRYPTO_FALLBACK = {
    "XAUUSDT", "XAGUSDT", "CLUSDT", "BZUSDT", "SNDKUSDT", "SKHYNIXUSDT", "SKHYUSDT", "SPCXUSDT", "SOXLUSDT",
    "SOXSUSDT", "MUUSDT", "KORUUSDT", "SNXXUSDT", "DRAMUSDT", "SAMSUNGUSDT", "CRCLUSDT", "MSTRUSDT", "NVDAUSDT",
    "AAPLUSDT", "ADBEUSDT", "AAOIUSDT", "TSLAUSDT", "AMZNUSDT", "GOOGLUSDT", "METAUSDT", "MSFTUSDT", "COINUSDT",
    "HOODUSDT", "QQQUSDT", "SPYUSDT", "PLTRUSDT", "AMDUSDT", "INTCUSDT", "NFLXUSDT", "BABAUSDT", "TSMUSDT"}


# --------------------------------------------------------------------------
# pure pieces (test 32)
# --------------------------------------------------------------------------
def monthly_sets(daily: pd.DataFrame, months: list[str], non_crypto: set,
                 train_top: int = TRAIN_TOP, trade_n: int = TRADE_N) -> tuple[dict, dict]:
    """daily: symbol, date (UTC), quote_volume. For each month 'YYYY-MM', ranked by
    mean quote volume over the VOL_DAYS days before the month (>= VOL_MIN_DAYS
    traded days), crypto only:
      members[m] = the top train_top symbols (training rows);
      traded[m]  = the top trade_n among symbols first traded >= MIN_AGE_DAYS
                   before the month (the coins that may be traded).
    Per symbol, never per split run (the data-gap fix); zero volume = no trading."""
    d = daily[(daily["quote_volume"] > 0) & ~daily["symbol"].isin(non_crypto)]
    first = d.groupby("symbol")["date"].min()
    members, traded = {}, {}
    for m in months:
        m0 = pd.Timestamp(m + "-01", tz="UTC")
        w = d[(d["date"] >= m0 - pd.Timedelta(days=VOL_DAYS)) & (d["date"] < m0)]
        g = w.groupby("symbol")["quote_volume"].agg(["mean", "size"])
        g = g[g["size"] >= VOL_MIN_DAYS].sort_values("mean", ascending=False)
        members[m] = list(g.index[:train_top])
        old = g[first.reindex(g.index) <= m0 - pd.Timedelta(days=MIN_AGE_DAYS)]
        traded[m] = list(old.index[:trade_n])
    return members, traded


def label_h(bars: pd.DataFrame, h: int) -> np.ndarray:
    """ml_wf.prepare's label with horizon h: log(open[i+1+h] / open[i+1]) / ATR
    fraction at i, NaN unless every label bar traded and bar i is tradable.
    `bars` are the bars prepare used (its dead tail already cut); the result is
    aligned with prepare's X (all rows but the last)."""
    live = bars["volume"].to_numpy(float) > 0
    atr = ta.atr_(bars["high"], bars["low"], bars["close"], MH.ATR_N)
    afrac = (atr / bars["close"]).to_numpy(float)
    good = live & np.isfinite(afrac) & (afrac >= WF.AFRAC_MIN)
    afrac = np.where(good, afrac, np.nan)
    o = bars["open"].to_numpy(float)
    n = len(o)
    dead = np.r_[0, np.cumsum(~live)]
    i = np.arange(n)
    hi = np.minimum(i + 2 + h, n)
    clean = (i + 1 + h < n) & (dead[hi] - dead[np.minimum(i + 1, n)] == 0)
    nxt = np.r_[o[1:], np.nan]
    fut = np.r_[o[1 + h:], np.full(min(1 + h, n), np.nan)][:n]
    with np.errstate(divide="ignore", invalid="ignore"):
        y = np.where(clean, np.log(fut / nxt) / afrac, np.nan)
    return y[:-1]


def month_mask(idx: pd.DatetimeIndex, coin: str, sets: dict[str, list[str]]) -> np.ndarray:
    """True on rows whose month lists the coin."""
    mem = [m for m, lst in sets.items() if coin in lst]
    return np.asarray(idx.strftime("%Y-%m").isin(mem), bool) if len(idx) else np.zeros(0, bool)


def training_mask(idx: pd.DatetimeIndex, coin: str, core: set, members: dict, wide: bool) -> np.ndarray:
    """narrow: every row of a core coin, nothing else; wide: also another coin's
    rows in its member months."""
    if coin in core:
        return np.ones(len(idx), bool)
    return month_mask(idx, coin, members) if wide else np.zeros(len(idx), bool)


def combine(preds: dict[int, np.ndarray]) -> np.ndarray:
    """Mean of the horizon forecasts on the 24-bar scale (pred_h x sqrt(24 / h));
    NaN unless every horizon has a forecast."""
    st = np.vstack([preds[h] * np.sqrt(24.0 / h) for h in sorted(preds)])
    return np.where(np.isfinite(st).all(axis=0), st.mean(axis=0), np.nan)


def member_filter(desired: np.ndarray, allowed: np.ndarray) -> np.ndarray:
    """Desired path with NEW positions (and reversals) only where allowed; holding
    and exiting untouched."""
    out, pos = np.zeros(len(desired)), 0.0
    for t, want in enumerate(desired):
        if want == pos:
            pass
        elif want == 0:
            pos = 0.0
        else:
            pos = want if allowed[t] else 0.0
        out[t] = pos
    return out


def forecasts(P: dict, tf: int, cfg: dict, masks: dict, horizons, spans, step: int = 1) -> dict[str, pd.Series]:
    """Walk-forward forecasts (mean over horizons) for every coin in P, each model
    trained only on rows where masks[c] is True."""
    per_h = {}
    saved = WF.H_BARS
    try:
        for h in horizons:
            Ph = {c: {**P[c], "y": pd.Series(np.where(masks[c], label_h(P[c]["bars"], h), np.nan),
                                             index=P[c]["X"].index)} for c in P}
            WF.H_BARS = h                                  # the walk-forward lag is h + 1 bars
            pred = {c: np.full(len(P[c]["X"]), np.nan) for c in P}
            for a, b in spans:
                p = WF.walk_forward(Ph, tf, cfg, a, b, step=step)
                for c in P:
                    pred[c] = np.where(np.isfinite(p[c]), p[c], pred[c])
            per_h[h] = pred
            del Ph
            gc.collect()
    finally:
        WF.H_BARS = saved
    return {c: pd.Series(combine({h: per_h[h][c] for h in horizons}), index=P[c]["X"].index) for c in P}


def forecast_corr(P: dict, pred: dict, a: str, b: str) -> float | None:
    """Pooled correlation of a forecast with the 24-bar label on [a, b) rows."""
    xs, ys = [], []
    for c in P:
        idx = P[c]["X"].index
        w = (idx >= pd.Timestamp(a, tz="UTC")) & (idx < pd.Timestamp(b, tz="UTC"))
        p = pred[c].reindex(idx).to_numpy()[w]
        y = label_h(P[c]["bars"], 24)[w]
        ok = np.isfinite(p) & np.isfinite(y)
        xs.append(p[ok])
        ys.append(y[ok])
    x = np.concatenate(xs) if xs else np.zeros(0)
    y = np.concatenate(ys) if ys else np.zeros(0)
    return float(np.corrcoef(x, y)[0, 1]) if len(x) > 2 and x.std() > 0 and y.std() > 0 else None


# --------------------------------------------------------------------------
# the account: section 31's cell, with the monthly traded set
# --------------------------------------------------------------------------
def run_cell(P, pred, o4, a, b, traded, q, mode, stress=1.0):
    fr, paths = [], {}
    for c in P:
        p = pred[c].reindex(P[c]["X"].index).to_numpy()
        ok = np.isfinite(p)
        des, ebar = np.full(len(p), np.nan), np.full(len(p), np.nan)
        if ok.any():
            ebar[ok] = MH.entry_bar(p[ok], q)
            des[ok] = MH.policy(p[ok], ebar[ok], mode)
        lo, hi, rows = MH._window(P, c, a, b)
        rows = rows[np.isfinite(des[rows])]
        if not len(rows):
            continue
        idx = P[c]["X"].index[rows]
        o = o4.get(c)
        if o is None or o.empty:
            ov = np.full(len(rows), np.nan)
        else:
            pos = WF.asof_positions(idx, MP.TF_MAIN, o.index, 240)
            ov = np.where(pos >= 0, o.to_numpy()[np.maximum(pos, 0)], np.nan)
        desired = member_filter(MP.agree_filter(des[rows], ov), month_mask(idx, c, traded))
        if not np.any(desired != 0):
            continue
        tgt = np.full(hi - lo, np.nan)
        tgt[P[c]["pos"][rows] - lo] = desired
        tb = P[c].get("tbars", P[c]["bars"])
        t = MH.simulate(tb.iloc[lo:hi], tgt, P[c]["atr"][lo:hi], P[c]["fund"],
                        fee=C.FEE_TAKER * stress, slip=P[c]["slip"] * stress, stop_atr=WF.STOP_ATR)
        if len(t):
            k = P[c]["X"].index.get_indexer(t["entry_time"] - pd.Timedelta(minutes=MP.TF_MAIN))
            t["conf"] = np.where(k >= 0, np.abs(p[np.maximum(k, 0)]) / ebar[np.maximum(k, 0)], np.nan)
        fr.append(t.assign(coin=c))
        paths[c] = (desired, rows, lo, hi)
    t = pd.concat(fr, ignore_index=True) if fr else pd.DataFrame(
        columns=["entry_time", "exit_time", "side", "net_r", "conf", "coin"])
    return MP.size_trades(t, CELL["sizing"], CELL["cap"]), paths


def judge(P, pred, o4, a, b, traded, q, mode, min_coins=MP.MIN_COINS):
    t, paths = run_cell(P, pred, o4, a, b, traded, q, mode)
    acc = MP.account(t, a, b)
    acc["stress_weekly_mean"] = MP.account(run_cell(P, pred, o4, a, b, traded, q, mode, 1.5)[0], a, b)["weekly_mean"]
    timing, per, pooled = MH.control({c: P[c] for c in paths}, paths)
    coins = {}
    for c in paths:
        tc = t[t["coin"] == c]
        coins[c] = {"trades": int(len(tc)), "mean_r": float(tc["net_r"].mean()) if len(tc) else None,
                    "timing": per[c]["timing"], "shift_median": MH._q(per[c]["shifts"], 50)}
    elig = {c: x for c, x in coins.items() if x["trades"] >= MP.MIN_COIN_TRADES}
    beat = [c for c, x in elig.items() if x["mean_r"] > 0 and x["timing"] is not None
            and x["shift_median"] is not None and x["timing"] > x["shift_median"]]
    acc.update(timing=timing, shift_median=MH._q(pooled, 50), shift_p95=MH._q(pooled, 95), per_coin=coins,
               breadth={"eligible": len(elig), "beat": beat, "share": len(beat) / len(elig) if elig else 0.0},
               per_year_r={str(y): float(g["ret"].sum()) for y, g in t.groupby(pd.to_datetime(t["exit_time"]).dt.year)})
    return acc, t


def evaluate(P, pred_narrow, pred_wide, o4, traded, q, mode, min_coins=MP.MIN_COINS, keep=False, corr=None) -> dict:
    a_tr, b_tr = WF.WINDOWS["train"]
    a_va, b_va = WF.WINDOWS["valid"]
    table, train_trades = [], {}
    for form, pr in (("narrow", pred_narrow), ("wide", pred_wide)):
        t, _ = run_cell(P, pr, o4, a_tr, b_tr, traded, q, mode)
        train_trades[form] = t
        acc = MP.account(t, a_tr, b_tr)
        table.append({"form": form, **{k: acc[k] for k in ("trades", "weekly_mean", "tstat", "per_year", "max_dd",
                                                           "mean_r")},
                      "per_year_r": {str(y): float(g["ret"].sum())
                                     for y, g in t.groupby(pd.to_datetime(t["exit_time"]).dt.year)}})
        print(f"TRAIN-WF {form}: {acc['trades']} trades, weekly {acc['weekly_mean']:+.5f}, t {acc['tstat']:+.2f}, "
              f"dd {acc['max_dd']:.3f}", flush=True)
    ok = [x for x in table if x["trades"] >= MP.MIN_TRADES]
    best = max(ok, key=lambda x: x["tstat"]) if ok else table[0]
    pr = pred_narrow if best["form"] == "narrow" else pred_wide
    # output only (Exp 049): the VALID checks repeated on TRAIN for the chosen form, for the Result Analyzer;
    # computed after the choice, so they cannot change it
    tj, _ = judge(P, pr, o4, a_tr, b_tr, traded, q, mode, min_coins)
    train_checks = {k: tj[k] for k in ("trades", "weekly_mean", "ci_lo", "ci_hi", "tstat", "stress_weekly_mean",
                                       "timing", "shift_median", "shift_p95", "long_ret", "short_ret", "max_dd",
                                       "mean_r", "per_year_r") if k in tj}
    train_checks["breadth"] = {k: tj["breadth"][k] for k in ("eligible", "share")}
    v, t = judge(P, pr, o4, a_va, b_va, traded, q, mode, min_coins)
    w = MP.weekly(t, a_va, b_va)
    tot = float(w.sum())
    v["diagnostics"] = {"forecast_corr_valid": corr,
                        "top_weeks_share": float(w.sort_values(ascending=False).iloc[:5].sum()) / tot if tot > 0 else None,
                        "neg_weeks": int((w < 0).sum())}
    gates = {"train_chose_wide": best["form"] == "wide",
             "train_weekly_mean>0": best["weekly_mean"] > 0 and best in ok,
             f"valid_trades>={MP.MIN_TRADES}": v["trades"] >= MP.MIN_TRADES,
             "valid_weekly_mean>0": v["weekly_mean"] > 0,
             "valid_ci_lo>0": v["ci_lo"] > 0,
             "stress_weekly_mean>0": v["stress_weekly_mean"] > 0,
             "timing_beats_shift_p95": v["shift_p95"] is not None and v["timing"] is not None
             and v["timing"] > v["shift_p95"],
             f"coins>={min_coins}": v["breadth"]["eligible"] >= min_coins,
             f"breadth>={MP.BREADTH_SHARE}": v["breadth"]["share"] >= MP.BREADTH_SHARE,
             "both_legs>0": v["long_ret"] > 0 and v["short_ret"] > 0,
             f"max_dd<={MP.MAX_DD}": v["max_dd"] <= MP.MAX_DD}
    failed = [k for k, g in gates.items() if not g]
    res = {"chosen": {"form": best["form"], **CELL}, "train_table": table, "valid": v,
           "verdict": "REJECT" if failed else "PASS", "gates_failed": failed,
           "model": {"q_in": q, "exit_mode": mode, "horizons_wide": list(HORIZONS)}, "train_checks": train_checks}
    if keep:
        res["_trades"] = t
        res["_train_trades"] = train_trades
    return res


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
def _daily() -> pd.DataFrame:
    import rotation as RO
    p = RO.CACHE / "perp_1d.parquet"
    if not p.exists():
        raise SystemExit(f"no {p}: run  python src/rotation.py --build perp  first")
    d = pd.read_parquet(p, columns=["symbol", "date", "quote_volume"])
    d["date"] = pd.to_datetime(d["date"], utc=True)
    return d


def _non_crypto() -> set:
    p = OUT / "non_crypto.json"
    return set(json.loads(p.read_text())) if p.exists() else set(NON_CRYPTO_FALLBACK)


def _download(symbol: str, lo, hi) -> None:
    import datafeed as DF
    import ml_pool as MPL
    months = set(C.month_range(*MPL.MONTHS))
    for tf in WF.TFS:
        kp = WF.cache_dir(tf) / f"{symbol}.parquet"
        if kp.exists():
            continue
        WF.cache_dir(tf).mkdir(parents=True, exist_ok=True)
        keys = [k for k in DF.list_keys(f"data/futures/{C.MARKET}/monthly/klines/{symbol}/{WF.TF_NAME[tf]}/")
                if k[-11:-4] in months]
        zs = [z for z in (DF.fetch_zip(x, WF.RAW / f"perp_{WF.TF_NAME[tf]}" / symbol) for x in keys) if z]
        if not zs:
            continue
        k = pd.concat([DF._read_one_zip(z, C.KLINE_COLS) for z in zs], ignore_index=True)
        k["open_time"] = MPL._ms(k["open_time"])
        k = k[(k["open_time"] >= lo) & (k["open_time"] < hi)].drop_duplicates("open_time").sort_values("open_time")
        k.to_parquet(kp, index=False)
    fp = WF.cache_dir(60) / f"{symbol}_funding.parquet"
    if not fp.exists():
        fkeys = [x for x in DF.list_keys(f"data/futures/{C.MARKET}/monthly/fundingRate/{symbol}/") if x[-11:-4] in months]
        fz = [z for z in (DF.fetch_zip(x, WF.RAW / "perp_funding" / symbol) for x in fkeys) if z]
        f = (pd.concat([DF._read_one_zip(z, C.FUNDING_COLS) for z in fz], ignore_index=True) if fz
             else pd.DataFrame(columns=C.FUNDING_COLS))
        if len(f):
            f["calc_time"] = MPL._ms(f["calc_time"])
            f = f[(f["calc_time"] >= lo) & (f["calc_time"] < hi)].sort_values("calc_time")
        f.to_parquet(fp, index=False)


def build() -> None:
    import urllib.request
    OUT.mkdir(parents=True, exist_ok=True)
    nc = OUT / "non_crypto.json"
    if not nc.exists():
        try:
            with urllib.request.urlopen("https://fapi.binance.com/fapi/v1/exchangeInfo", timeout=30) as r:
                info = json.loads(r.read())
            api = {s["symbol"] for s in info["symbols"] if s.get("underlyingType", "COIN") != "COIN"}
            src = "exchangeInfo"
        except Exception as e:  # noqa: BLE001 - recorded, never hidden
            api, src = set(), f"exchangeInfo unavailable ({e.__class__.__name__}); fallback list only"
        nc.write_text(json.dumps(sorted(api | NON_CRYPTO_FALLBACK), indent=1))
        print(f"[ml_wide] non-crypto symbols: {len(api | NON_CRYPTO_FALLBACK)} ({src})", flush=True)
    d = _daily()
    months = [str(p) for p in pd.period_range(MONTHS_FROM, C.DATA_END, freq="M")]
    members, traded = monthly_sets(d, months, _non_crypto())
    (OUT / "members.json").write_text(json.dumps(members, indent=1))
    (OUT / "traded.json").write_text(json.dumps(traded, indent=1))
    core = {u["inst"] for u in json.loads(SOURCE_UNIVERSE.read_text())}
    need = sorted((set().union(*map(set, members.values())) | set().union(*map(set, traded.values()))) - core)
    rng = d[d["quote_volume"] > 0].groupby("symbol")["date"].agg(["min", "max"])
    print(f"[ml_wide] {len(need)} coins beyond section 30's {len(core)}", flush=True)
    for n, s in enumerate(need, 1):
        _download(s, rng.at[s, "min"], rng.at[s, "max"] + pd.Timedelta(days=1))
        print(f"  {n}/{len(need)} {s}: cached", flush=True)
    print(f"BUILD OK: {len(core)} + {len(need)} coins")


def load_wide() -> tuple[dict, set, dict, dict]:
    members = json.loads((OUT / "members.json").read_text())
    traded = json.loads((OUT / "traded.json").read_text())
    by_tf, _ = W3.load_all()
    core = set(by_tf[60])
    need = sorted((set().union(*map(set, members.values())) | set().union(*map(set, traded.values()))) - core)
    for s in need:
        if not all((WF.cache_dir(tf) / f"{s}.parquet").exists() for tf in WF.TFS):
            continue
        fund = pd.read_parquet(WF.cache_dir(60) / f"{s}_funding.parquet")
        bars = {tf: W2._read(WF.cache_dir(tf) / f"{s}.parquet") for tf in WF.TFS}
        if all(len(b) for b in bars.values()):
            for tf in WF.TFS:
                by_tf[tf][s] = {"spot": bars[tf], "perp": bars[tf], "fund": fund}
    return by_tf, core, members, traded


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
        for o in (MP.OUT, XS.OUT, MK.OUT, FL.OUT):
            if (o / "holdout.json").exists():
                raise SystemExit(f"--final refused: sections 31-36 share one holdout and {o.name} used it")
    elif res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    if not (OUT / "traded.json").exists():
        raise SystemExit("no traded sets: run  python src/ml_wide.py --build")
    spans = [WF.WINDOWS["train"], WF.WINDOWS["valid"]] + ([WF.WINDOWS["holdout"]] if final else [])
    by_tf, core, members, traded = load_wide()
    tcoins = sorted({c for m, lst in traded.items() for c in lst} & set(by_tf[60]))
    print(f"[ml_wide] training coins {len(by_tf[60])} ({len(core)} core); coins ever traded {len(tcoins)}", flush=True)
    # 4h agreement: section 30's 4h recipe, trained on the core rows, forecasting the traded coins
    P4 = W2.prepare({tf: {c: v for c, v in by_tf[tf].items() if c in core or c in tcoins} for tf in WF.TFS}, 240)
    cfg4 = MP._cfg(240)["setting"]
    o4 = forecasts(P4, 240, cfg4, {c: training_mask(P4[c]["X"].index, c, core, members, False) for c in P4},
                   (WF.H_BARS,), spans)
    o4 = {c: o4[c] for c in tcoins if c in o4}
    del P4
    gc.collect()
    P = W2.prepare(by_tf, MP.TF_MAIN)
    del by_tf
    gc.collect()
    cfg1 = MP._cfg(MP.TF_MAIN)["setting"]
    pn = forecasts(P, MP.TF_MAIN, cfg1, {c: training_mask(P[c]["X"].index, c, core, members, False) for c in P},
                   (WF.H_BARS,), spans)
    pw = forecasts(P, MP.TF_MAIN, cfg1, {c: training_mask(P[c]["X"].index, c, core, members, True) for c in P},
                   HORIZONS, spans)
    PT = {c: P[c] for c in tcoins if c in P}
    pred_n = {c: pn[c] for c in PT}
    pred_w = {c: pw[c] for c in PT}
    corr = {"narrow": forecast_corr(PT, pred_n, *WF.WINDOWS["valid"]),
            "wide": forecast_corr(PT, pred_w, *WF.WINDOWS["valid"])}
    del P, pn, pw
    gc.collect()
    m = MP._cfg(MP.TF_MAIN)
    if final:
        a, b = WF.WINDOWS["holdout"]
        pr = pred_n if res["chosen"]["form"] == "narrow" else pred_w
        h, t = judge(PT, pr, o4, a, b, traded, m["q_in"], m["exit_mode"])
        h["verdict"] = ("CONFIRMED" if h["weekly_mean"] > 0 and h["ci_lo"] > 0 and h["shift_median"] is not None
                        and h["timing"] is not None and h["timing"] > h["shift_median"]
                        and h["breadth"]["share"] >= MP.BREADTH_SHARE else "FAILED")
        lock.write_text(json.dumps(h, indent=1, default=str))
        t.to_csv(OUT / "trades_holdout.csv.gz", index=False)
        write_report(res)
        print(json.dumps({k: h.get(k) for k in ("trades", "weekly_mean", "ci_lo", "verdict")}, indent=1))
        return
    res = evaluate(PT, pred_n, pred_w, o4, traded, m["q_in"], m["exit_mode"], keep=True, corr=corr)
    res["coins"] = {"core": len(core), "training": len(set().union(*map(set, members.values())) | core),
                    "ever_traded_valid": sorted({c for mo, lst in traded.items()
                                                 if "2023-01" <= mo < "2025-01" for c in lst})}
    res.pop("_trades").to_csv(OUT / "trades_valid.csv.gz", index=False)
    for form, tt in res.pop("_train_trades").items():          # TRAIN trades of both forms (output only)
        tt.to_csv(OUT / f"trades_train_{form}.csv.gz", index=False)
    res_path.write_text(json.dumps(res, indent=1, default=str))
    write_report(res)
    print(f"\nML_WIDE: chose {res['chosen']} -> {res['verdict']} failed {res['gates_failed']}")


def write_report(r: dict) -> None:
    v, d = r["valid"], r["valid"]["diagnostics"]
    f = (lambda x, k=5: "-" if x is None else f"{x:+.{k}f}")
    corr = d.get("forecast_corr_valid") or {}
    cs = r.get("coins", {})
    L = ["# Train wide, trade the monthly top 20 large coins (PLAN.md section 36)", "",
         "GENERATED by `src/ml_wide.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}** (TRAIN chose {r['chosen']}; failed: {r['gates_failed'] or 'none'})", "",
         f"- coins: {cs.get('core')} core, {cs.get('training')} training in all; traded at some point in VALID: "
         f"{', '.join(c.replace('USDT', '') for c in cs.get('ever_traded_valid', []))}",
         f"- VALID {v['trades']} trades over {v['weeks']} weeks: weekly account return {f(v['weekly_mean'])}, "
         f"95% CI [{f(v['ci_lo'])}, {f(v['ci_hi'])}], t {v['tstat']:+.2f}; return per year {f(v['per_year'], 4)}, "
         f"max drawdown {v['max_dd']:.4f}",
         f"- mean R per trade {f(v['mean_r'], 4)}; long {f(v['long_ret'], 4)} / short {f(v['short_ret'], 4)} "
         f"(summed return); cost x1.5 weekly {f(v['stress_weekly_mean'])}",
         f"- timing {f(v['timing'], 4)} vs shifted median {f(v['shift_median'], 4)} / p95 {f(v['shift_p95'], 4)}; "
         f"breadth {len(v['breadth']['beat'])} of {v['breadth']['eligible']} ({v['breadth']['share']:.2f}); "
         f"per year {v['per_year_r']}",
         f"- diagnostics: forecast/label correlation on VALID narrow {f(corr.get('narrow'), 4)} vs wide "
         f"{f(corr.get('wide'), 4)}; best 5 weeks = {f(d['top_weeks_share'], 3)} of the total; negative weeks "
         f"{d['neg_weeks']} of {v['weeks']}", "",
         "| form | TRAIN trades | weekly mean | t | per year | max DD | mean R | summed return by year |",
         "|---|---|---|---|---|---|---|---|"]
    for x in r["train_table"]:
        L.append(f"| {x['form']} | {x['trades']} | {f(x['weekly_mean'])} | {x['tstat']:+.2f} | {f(x['per_year'], 4)} | "
                 f"{x['max_dd']:.4f} | {f(x['mean_r'], 4)} | {x['per_year_r']} |")
    hp = OUT / "holdout.json"
    if hp.exists():
        h = json.loads(hp.read_text())
        L += ["", f"**HOLDOUT: {h['verdict']}** - {h['trades']} trades, weekly {f(h['weekly_mean'])}, CI "
              f"[{f(h['ci_lo'])}, {f(h['ci_hi'])}], timing {f(h['timing'], 4)} vs median {f(h['shift_median'], 4)}"]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--final", action="store_true")
    a = ap.parse_args()
    if a.build:
        build()
    else:
        run(a.final)


if __name__ == "__main__":
    main()
