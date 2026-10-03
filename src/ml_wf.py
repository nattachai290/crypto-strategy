"""Walk-forward ML on many coins: refit every month, decide entry AND exit (PLAN.md section 28)

    python src/rotation.py --build perp     # once, if data/cache/_multi has no perp_1d.parquet
    python src/ml_wf.py --build             # 50 coins x (1h, 4h, 1d) klines + funding
    python src/ml_wf.py                     # TRAIN/VALID for 1h, 4h and 1d, once
    python src/ml_wf.py --final             # HOLDOUT once, one timeframe, only after PASS

The owner's request (2026-10-02): walk-forward on many coins, timeframes 1h,
4h and 1d only. Section 27's model was fitted once on 2020-2022 and frozen
for 2023-2024; it wanted to be short 27% of the time and long 4.5% in a rising
market, and its long leg lost. Here the model is REFIT AT THE START OF EVERY
MONTH on all rows known by then (all coins, all earlier months), and only the
next month is predicted with it - as it would run live. Everything else is
section 27's design, scaled in bars ("chart mode") to each timeframe:
  * Universe: UNIVERSE_N coins by TRAIN volume, survivorship-free
    (ml_pool.select_universe, listed by 2021-01-01, trading on 2022-12-31,
    later delistings kept). Native Binance klines per timeframe, never resampled.
  * Features: section 19's per-coin set and section 21's cross-coin/BTC set,
    computed on that timeframe's bars, at the bar close. Funding as-of the close.
  * MULTI-TIMEFRAME (owner, 2026-10-02): the model trading one timeframe also
    sees the section 19 per-coin set computed on the OTHER two timeframes'
    native bars (prefixes h1_, h4_, d1_), taken from the last bar of that
    timeframe that has CLOSED by the decision bar's close (asof_positions).
    A 1h decision sees the last closed 4h and 1d bars; a 1d decision sees the
    1h and 4h bars that closed at the same daily close.
  * Label at decision bar i: log(open[i+1+H] / open[i+1]) / (ATR14 / close),
    H = 24 bars (24 h, 4 days, 24 days). A decision at every bar.
  * Policy (ml_hold.policy, entry_bar): hysteresis on the forecast; e_in is the
    rolling q_in quantile of the coin's own last 180 |forecasts|. Exits: the
    desired position changes, an 8-ATR protective stop, or the period end.
    No time limit.
  * Refit training rows: every row whose label is complete before the month
    starts (time + (H + 1) bars < month start). Nothing after it.
  * TRAIN tuning (per timeframe): the walk-forward run over 2021-01..2022-12
    (24 monthly refits per setting) gives out-of-sample forecasts for TRAIN;
    4 LightGBM settings x Q_IN x EXIT_MODES = 24 cells; the cell with the
    highest net mean R per trade (>= MIN_OOF_TRADES) is chosen.
  * VALID: the chosen cell, walk-forward over 2023-01..2024-12. Gates (all):
    TRAIN walk-forward mean > 0; >= MIN_VALID_TRADES; net mean > 0 and weekly-
    block CI lower bound > 0; mean > 0 at cost x1.5; pooled timing above the
    95th percentile of 200 circular shifts of the desired path; >= MIN_COINS
    coins with >= MIN_COIN_TRADES trades, at least half net > 0 AND above their
    own shifted median; both legs net > 0.
  * Three timeframes are three tries. --final runs ONE: among the PASS
    timeframes, the one with the highest TRAIN walk-forward mean. It continues
    the monthly refits over 2025-01..2026-08. CONFIRMED = net mean > 0, CI
    lower bound > 0, timing above the shifted median, breadth >= half.
  * Every trade file also carries WHY: the forecast at the opening decision
    (and at a signal exit), the entry bar at that moment, and the 3 features
    that pushed the forecast most toward the decision (LightGBM per-feature
    contributions; explain()). Reported only, never a gate.
Writes results/_multi/ml_wf/ (universe.json, tf<N>.json, trades_valid_tf<N>.csv.gz,
desired_valid_tf<N>.csv.gz, holdout files) and the generated journal/_multi/ml_wf.md.
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
import ml_hold as MH  # noqa: E402
import ml_pool as MP  # noqa: E402
import ml_pool2 as M2  # noqa: E402

RAW = C.ROOT / "data" / "raw" / "_multi"
OUT = C.ROOT / "results" / "_multi" / "ml_wf"
REPORT = C.ROOT / "journal" / "_multi" / "ml_wf.md"
TF_NAME = {60: "1h", 240: "4h", 1440: "1d"}

# ---- pre-registered (PLAN.md section 28); a change is a new test
UNIVERSE_N = 50
TFS = (60, 240, 1440)
H_BARS = 24
STOP_ATR = MH.STOP_ATR
Q_IN, EXIT_MODES, GRID = MH.Q_IN, MH.EXIT_MODES, MH.GRID
CROSS_K = (24, 72, 168)                     # bars
WINDOWS = {"train": ("2021-01-01", "2023-01-01"), "valid": ("2023-01-01", "2025-01-01"),
           "holdout": ("2025-01-01", "2026-09-01")}
MIN_OOF_TRADES = 300
MIN_VALID_TRADES = 300
MIN_COIN_TRADES = 10
MIN_COINS = 10
BREADTH_SHARE = 0.5
N_RANDOM = 200
UNIVERSE_FILE = "universe_v2.json"   # v1 (universe.json, Exp 020) counted zero-volume days as trading
AFRAC_MIN = 1e-4                     # ATR14 / close below 0.01%: no market, no label, no entry (Exp 020)


def cache_dir(tf: int) -> Path:
    return C.ROOT / "data" / "cache" / "_multi" / f"pool_{TF_NAME[tf]}"


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
def build() -> None:
    import datafeed as DF
    import rotation as RO
    p = RO.CACHE / "perp_1d.parquet"
    if not p.exists():
        raise SystemExit(f"no {p}: run  python src/rotation.py --build perp  first")
    OUT.mkdir(parents=True, exist_ok=True)
    uni_path = OUT / UNIVERSE_FILE
    if uni_path.exists():
        uni = json.loads(uni_path.read_text())
        print(f"universe fixed earlier: {uni_path}")
    else:
        daily = pd.read_parquet(p)
        daily = daily[daily["quote_volume"] > 0]        # a zero-volume day is not trading (Exp 020)
        uni = MP.select_universe(daily, n=UNIVERSE_N)
        uni_path.write_text(json.dumps(uni, indent=1))
    months = set(C.month_range(*MP.MONTHS))
    for tf in TFS:
        cache_dir(tf).mkdir(parents=True, exist_ok=True)
    for u in uni:
        s = u["symbol"]
        lo = pd.Timestamp(u["start"], tz="UTC")
        hi = pd.Timestamp(u["end"], tz="UTC") + pd.Timedelta(days=1)
        for tf in TFS:
            kp = cache_dir(tf) / f"{u['inst']}.parquet"
            if kp.exists():
                continue
            keys = [k for k in DF.list_keys(f"data/futures/{C.MARKET}/monthly/klines/{s}/{TF_NAME[tf]}/")
                    if k[-11:-4] in months]
            k = pd.concat([DF._read_one_zip(z, C.KLINE_COLS)
                           for z in (DF.fetch_zip(x, RAW / f"perp_{TF_NAME[tf]}" / s) for x in keys) if z],
                          ignore_index=True)
            k["open_time"] = MP._ms(k["open_time"])
            k = (k[(k["open_time"] >= lo) & (k["open_time"] < hi)]
                 .drop_duplicates("open_time").sort_values("open_time"))
            k.to_parquet(kp, index=False)
        fp = cache_dir(60) / f"{u['inst']}_funding.parquet"
        if not fp.exists():
            fkeys = [x for x in DF.list_keys(f"data/futures/{C.MARKET}/monthly/fundingRate/{s}/")
                     if x[-11:-4] in months]
            f = pd.concat([DF._read_one_zip(z, C.FUNDING_COLS)
                           for z in (DF.fetch_zip(x, RAW / "perp_funding" / s) for x in fkeys) if z],
                          ignore_index=True)
            f["calc_time"] = MP._ms(f["calc_time"])
            f = f[(f["calc_time"] >= lo) & (f["calc_time"] < hi)].sort_values("calc_time")
            f.to_parquet(fp, index=False)
        print(f"  {u['inst']}: cached", flush=True)
    print(f"BUILD OK: {len(uni)} coins x {[TF_NAME[t] for t in TFS]}")


def load_all() -> dict[int, dict]:
    return {tf: load(tf) for tf in TFS}


def load(tf: int) -> dict[str, tuple[pd.DataFrame, pd.DataFrame]]:
    uni_path = OUT / UNIVERSE_FILE
    if not uni_path.exists():
        raise SystemExit("no universe: run  python src/ml_wf.py --build")
    coins = {}
    for u in json.loads(uni_path.read_text()):
        k = pd.read_parquet(cache_dir(tf) / f"{u['inst']}.parquet").set_index("open_time").sort_index()
        k.index.name = "time"
        bars = k[["open", "high", "low", "close", "volume", "taker_buy_base"]].astype("float64")
        coins[u["inst"]] = (bars, pd.read_parquet(cache_dir(60) / f"{u['inst']}_funding.parquet"))
    return coins


# --------------------------------------------------------------------------
# features and labels (causal: bar i uses bars <= i; funding as-of the bar close)
# --------------------------------------------------------------------------
def features_tf(b: pd.DataFrame, funding, tf: int) -> pd.DataFrame:
    f = ME.features(b, None)
    if funding is not None and len(funding):
        fr = funding[["calc_time", "last_funding_rate"]].copy()
        fr["calc_time"] = pd.to_datetime(fr["calc_time"], utc=True).astype("datetime64[ns, UTC]")
        close_t = pd.DataFrame({"t": (b.index + pd.Timedelta(minutes=tf)).astype("datetime64[ns, UTC]")})
        got = pd.merge_asof(close_t, fr.sort_values("calc_time"), left_on="t", right_on="calc_time",
                            direction="backward")
        f["funding_last"] = got["last_funding_rate"].to_numpy()
    else:
        f["funding_last"] = np.nan
    return f


PREFIX = {60: "h1_", 240: "h4_", 1440: "d1_"}


def asof_positions(main_idx: pd.DatetimeIndex, tf_main: int, other_idx: pd.DatetimeIndex, tf_other: int) -> np.ndarray:
    """For each main bar, the position of the last OTHER bar whose close
    (open + tf_other) is at or before the main bar's close (open + tf_main);
    -1 if none. Closed bars only: never a bar still forming."""
    mc = (main_idx + pd.Timedelta(minutes=tf_main)).asi8
    oc = (other_idx + pd.Timedelta(minutes=tf_other)).asi8
    return np.searchsorted(oc, mc, side="right") - 1


def mtf_features(main: pd.DataFrame, tf_main: int, other: pd.DataFrame, tf_other: int) -> pd.DataFrame:
    """Section 19's per-coin features on another timeframe's native bars, aligned
    to the main bars by asof_positions (hour/weekday dropped)."""
    f = ME.features(other, None).drop(columns=["hour", "weekday"], errors="ignore")
    pos = asof_positions(main.index, tf_main, other.index, tf_other)
    vals = f.to_numpy(float)
    out = np.full((len(main), vals.shape[1]), np.nan)
    ok = pos >= 0
    out[ok] = vals[pos[ok]]
    return pd.DataFrame(out, index=main.index, columns=[PREFIX[tf_other] + c for c in f.columns])


def cross_features(coins: dict, tf: int) -> dict[str, pd.DataFrame]:
    """ml_pool2.cross_features on any timeframe (windows in bars)."""
    lo = min(b.index[0] for b, _ in coins.values())
    hi = max(b.index[-1] for b, _ in coins.values())
    full = pd.date_range(lo, hi, freq=f"{tf}min")
    close = pd.DataFrame({c: b["close"].where(b["volume"] > 0).reindex(full)      # dead bars are not prices
                          for c, (b, _) in coins.items()})
    lr = {k: np.log(close / close.shift(k)) for k in CROSS_K}
    mkt = {k: lr[k].mean(axis=1, skipna=True) for k in CROSS_K}
    n = lr[CROSS_K[0]].notna().sum(axis=1)
    breadth = ((lr[CROSS_K[0]] > 0).sum(axis=1) / n.where(n > 0)).astype(float)
    anchor = "BTCUSDT" if "BTCUSDT" in coins else None
    out = {}
    for c, (b, _) in coins.items():
        f = pd.DataFrame(index=full)
        for k in CROSS_K:
            f[f"mkt_ret_{k}"] = mkt[k]
            f[f"rel_ret_{k}"] = lr[k][c] - mkt[k]
            f[f"btc_ret_{k}"] = lr[k][anchor] if anchor else np.nan
        f[f"breadth_{CROSS_K[0]}"] = breadth
        f["btc_vol_168"] = np.log(close[anchor]).diff().rolling(168).std() if anchor else np.nan
        out[c] = f.reindex(b.index)
    return out


def prepare(by_tf: dict, tf: int) -> dict:
    """by_tf: {timeframe: {coin: (bars, funding)}}; the traded timeframe is tf,
    every other timeframe in by_tf adds its features (multi-timeframe)."""
    coins = by_tf[tf]
    cross = cross_features(coins, tf)
    P = {}
    for c, (bars, fund) in coins.items():
        live = bars["volume"].to_numpy(float) > 0
        if not live.any():
            continue
        bars = bars.iloc[:int(np.flatnonzero(live)[-1]) + 1]     # cut the dead tail after the last trade
        live = live[:len(bars)]
        parts = [features_tf(bars, fund, tf), cross[c].iloc[:len(bars)]]
        for tf2, coins2 in by_tf.items():
            if tf2 != tf and c in coins2:
                parts.append(mtf_features(bars, tf, coins2[c][0], tf2))
        X = pd.concat(parts, axis=1)
        atr = ta.atr_(bars["high"], bars["low"], bars["close"], MH.ATR_N)
        afrac = (atr / bars["close"]).to_numpy(float)
        # Exp 020: frozen zero-volume bars (halted / delisted contracts) have zero true
        # range; ATR then reaches 0 and every ATR-scaled number diverges. A bar is
        # tradable only if it traded and its ATR fraction is at least AFRAC_MIN.
        good = live & np.isfinite(afrac) & (afrac >= AFRAC_MIN)
        afrac = np.where(good, afrac, np.nan)
        o = bars["open"].to_numpy(float)
        n = len(o)
        dead = np.r_[0, np.cumsum(~live)]                       # dead bars in [i, j) = dead[j] - dead[i]
        i = np.arange(n)
        hi = np.minimum(i + 2 + H_BARS, n)
        clean = (i + 1 + H_BARS < n) & (dead[hi] - dead[np.minimum(i + 1, n)] == 0)   # label bars all traded
        nxt = np.r_[o[1:], np.nan]
        fut = np.r_[o[1 + H_BARS:], np.full(min(1 + H_BARS, n), np.nan)][:n]
        with np.errstate(divide="ignore", invalid="ignore"):
            y = np.where(clean, np.log(fut / nxt) / afrac, np.nan)
            rn = np.r_[np.log(o[1:] / o[:-1]), np.nan] / np.r_[np.nan, afrac[:-1]]
        rn = np.where(np.r_[live[1:], False] & live, rn, np.nan)
        P[c] = {"bars": bars, "fund": fund, "slip": MP.slippage(c.split("#")[0]),
                "atr": np.where(good, atr.to_numpy(float), np.nan),          # no entry on a non-tradable bar
                "X": X.iloc[:-1], "y": pd.Series(y[:-1], index=bars.index[:-1]),
                "pos": np.arange(n - 1), "rn": rn, "tradable": good[:-1]}
        print(f"  prepared {c} ({TF_NAME.get(tf, tf)}): {n - 1:,} rows", flush=True)
    return P


# --------------------------------------------------------------------------
# walk-forward
# --------------------------------------------------------------------------
def month_starts(a: str, b: str, step: int = 1) -> list[pd.Timestamp]:
    return list(pd.date_range(pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC"),
                              freq=f"{step}MS", inclusive="left"))


def walk_forward(P: dict, tf: int, cfg: dict, a: str, b: str, step: int = 1, log: list | None = None,
                 models: dict | None = None) -> dict:
    """Forecasts on [a, b): for each month m, a model fitted on every row whose
    label is complete before m (time + (H+1) bars < m), predicting [m, m+step)."""
    cols = MH._cols(P)
    pred = {c: np.full(len(P[c]["X"]), np.nan) for c in P}
    lag = pd.Timedelta(minutes=tf * (H_BARS + 1))
    starts = month_starts(a, b, step) + [pd.Timestamp(b, tz="UTC")]
    for m0, m1 in zip(starts[:-1], starts[1:]):
        Xs, ys = [], []
        for c in P:
            idx = P[c]["X"].index
            tr = idx + lag < m0
            Xs.append(P[c]["X"].reindex(columns=cols)[tr])
            ys.append(P[c]["y"][tr])
        X, y = pd.concat(Xs, ignore_index=True), pd.concat(ys, ignore_index=True)
        if y.notna().sum() < 1000:
            continue
        model = M2.fit(X, y, cfg)
        if models is not None:
            models[m0] = model
        if log is not None:
            log.append({"month": str(m0.date()), "train_rows": int(y.notna().sum()),
                        "last_train_label_end": str(max(P[c]["X"].index[P[c]["X"].index + lag < m0].max()
                                                        for c in P if (P[c]["X"].index + lag < m0).any()) + lag)})
        for c in P:
            idx = P[c]["X"].index
            w = (idx >= m0) & (idx < m1) & P[c].get("tradable", np.ones(len(idx), bool))
            if w.any():
                pred[c][w] = model.predict(P[c]["X"].reindex(columns=cols)[w])
    return pred


def run_cell(P, pred, a, b, q, mode, stress=1.0):
    """Trades and desired paths of every coin on [a, b) from walk-forward forecasts.
    The rolling entry bar reads the forecasts before a as well (they are out of sample)."""
    fr, paths = [], {}
    for c in P:
        p = pred[c]
        ok = np.isfinite(p)
        des_all = np.full(len(p), np.nan)
        if ok.any():
            pv = p[ok]
            des_all[ok] = MH.policy(pv, MH.entry_bar(pv, q), mode)
        lo, hi, rows = MH._window(P, c, a, b)
        rows = rows[np.isfinite(des_all[rows])]
        desired = des_all[rows]
        tgt = np.full(hi - lo, np.nan)
        tgt[P[c]["pos"][rows] - lo] = desired
        tb = P[c].get("tbars", P[c]["bars"])          # ml_wf2: features on spot bars, trades on perp bars
        t = MH.simulate(tb.iloc[lo:hi], tgt, P[c]["atr"][lo:hi], P[c]["fund"],
                        fee=C.FEE_TAKER * stress, slip=P[c]["slip"] * stress, stop_atr=STOP_ATR)
        fr.append(t.assign(coin=c))
        paths[c] = (desired, rows, lo, hi)
    return pd.concat(fr, ignore_index=True), paths


TOP_WHY = 3


def explain(P: dict, tf: int, t: pd.DataFrame, pred: dict, models: dict, q: float) -> pd.DataFrame:
    """Reported only, never used by a gate: for every trade, the decision that
    opened it and (for a signal exit) the decision that closed it - the
    forecast, the entry bar e_in at that moment, and the TOP_WHY features that
    pushed the forecast most in the direction of the decision (LightGBM
    pred_contrib: per-feature contributions that add up to the forecast)."""
    if t.empty:
        return t
    cols = MH._cols(P)
    step = pd.Timedelta(minutes=tf)
    keys = sorted(models)
    starts = np.array([k.tz_convert(None).to_datetime64() for k in keys], dtype="datetime64[ns]")
    t = t.copy()
    for k in ("entry_pred", "entry_bar", "entry_why", "exit_pred", "exit_why"):
        t[k] = None
    ebar = {}
    for c in P:
        p = pred[c]
        ok = np.isfinite(p)
        e = np.full(len(p), np.nan)
        e[ok] = MH.entry_bar(p[ok], q)
        ebar[c] = e
    for i, r in t.iterrows():
        c, side = r["coin"], r["side"]
        idx = P[c]["X"].index
        for what, when, sign in (("entry", r["entry_time"] - step, side),
                                 ("exit", r["exit_time"] if r["reason"] == "signal" else None, -side)):
            if when is None:
                continue
            k = idx.get_indexer([when])[0]
            if k < 0 or not np.isfinite(pred[c][k]):
                continue
            mi = np.searchsorted(starts, np.datetime64(when.tz_convert(None)), side="right") - 1
            if mi < 0:
                continue
            row = P[c]["X"].reindex(columns=cols).iloc[[k]]
            contrib = models[keys[mi]].predict(row, pred_contrib=True)[0][:-1]
            order = np.argsort(-sign * contrib)[:TOP_WHY]
            why = [[cols[j], None if not np.isfinite(row.iat[0, j]) else round(float(row.iat[0, j]), 5),
                    round(float(contrib[j]), 4)] for j in order]
            t.at[i, f"{what}_pred"] = round(float(pred[c][k]), 4)
            t.at[i, f"{what}_why"] = json.dumps(why)
            if what == "entry":
                t.at[i, "entry_bar"] = round(float(ebar[c][k]), 4) if np.isfinite(ebar[c][k]) else None
    return t


def judge(P, pred, a, b, q, mode, min_coins=MIN_COINS) -> tuple[dict, pd.DataFrame, dict]:
    t, paths = run_cell(P, pred, a, b, q, mode)
    s = MH._summ(t)
    stress = MH._summ(run_cell(P, pred, a, b, q, mode, stress=1.5)[0])
    timing, per, pooled = MH.control(P, paths)
    coins = {}
    for c in P:
        tc = t[t["coin"] == c]
        coins[c] = {"trades": int(len(tc)), "mean_r": float(tc["net_r"].mean()) if len(tc) else None,
                    "timing": per[c]["timing"], "shift_median": MH._q(per[c]["shifts"], 50),
                    "shift_p95": MH._q(per[c]["shifts"], 95)}
    elig = {c: x for c, x in coins.items() if x["trades"] >= MIN_COIN_TRADES}
    beat = [c for c, x in elig.items() if x["mean_r"] > 0 and x["timing"] is not None
            and x["shift_median"] is not None and x["timing"] > x["shift_median"]]
    held = sum(MH.timing_sums(MH.held_hours(hi - lo, P[c]["pos"][rows] - lo, des), np.ones(hi - lo))[1]
               for c, (des, rows, lo, hi) in paths.items())
    span = sum(hi - lo for (_, _, lo, hi) in paths.values())
    s.update(stress_mean_r=stress.get("mean_r"), timing=timing, shift_median=MH._q(pooled, 50),
             shift_p95=MH._q(pooled, 95), per_coin=coins, time_in_market=held / span if span else None,
             breadth={"eligible": len(elig), "beat": beat, "share": len(beat) / len(elig) if elig else 0.0},
             last_exit=str(t["exit_time"].max()) if len(t) else None)
    des = pd.concat([pd.DataFrame({"coin": c, "time": P[c]["X"].index[rows], "pred": pred[c][rows],
                                   "desired": d}) for c, (d, rows, _, _) in paths.items()], ignore_index=True)
    return s, t, {"desired": des}


def evaluate(P: dict, tf: int, grid: list = GRID, min_coins: int = MIN_COINS, step: int = 1,
             keep: bool = False) -> dict:
    a_tr, b_tr = WINDOWS["train"]
    a_va, b_va = WINDOWS["valid"]
    table, preds, refits = [], {}, []
    for gi, cfg in enumerate(grid):
        preds[gi] = walk_forward(P, tf, cfg, a_tr, b_tr, step, log=refits if gi == 0 else None)
        for q in Q_IN:
            for mode in EXIT_MODES:
                t, _ = run_cell(P, preds[gi], a_tr, b_tr, q, mode)
                table.append({"setting": gi, **cfg, "q_in": q, "exit": mode, "trades": int(len(t)),
                              "mean_r": float(t["net_r"].mean()) if len(t) else None})
                print(f"[{TF_NAME.get(tf, tf)}] TRAIN-WF setting {gi} q {q} {mode}: {table[-1]['trades']} trades, "
                      f"mean {table[-1]['mean_r']}", flush=True)
    ok = [x for x in table if x["trades"] >= MIN_OOF_TRADES and x["mean_r"] is not None]
    best = max(ok, key=lambda x: x["mean_r"]) if ok else table[0]
    gi, q, mode = best["setting"], best["q_in"], best["exit"]
    cfg = grid[gi]
    vmodels = {}
    vpred = walk_forward(P, tf, cfg, a_va, b_va, step, log=refits, models=vmodels)
    pred = {c: np.where(np.isfinite(vpred[c]), vpred[c], preds[gi][c]) for c in P}
    v, t, extra = judge(P, pred, a_va, b_va, q, mode, min_coins)
    if keep:
        t = explain(P, tf, t, pred, vmodels, q)
    gates = {"train_wf_mean>0": (best["mean_r"] or -1) > 0 and best in ok,
             f"valid_trades>={MIN_VALID_TRADES}": v.get("trades", 0) >= MIN_VALID_TRADES,
             "valid_mean>0": v.get("mean_r", -1) > 0,
             "valid_ci_lo>0": (v.get("ci_lo") or -1) > 0,
             "stress_mean>0": (v.get("stress_mean_r") or -1) > 0,
             "timing_beats_shift_p95": v["shift_p95"] is not None and v["timing"] is not None
             and v["timing"] > v["shift_p95"],
             f"coins>={min_coins}": v["breadth"]["eligible"] >= min_coins,
             f"breadth>={BREADTH_SHARE}": v["breadth"]["share"] >= BREADTH_SHARE,
             "both_legs>0": (v.get("long_r") or -1) > 0 and (v.get("short_r") or -1) > 0}
    failed = [k for k, g in gates.items() if not g]
    res = {"tf": tf, "coins_n": len(P), "horizon_bars": H_BARS, "stop_atr": STOP_ATR, "setting": cfg,
           "q_in": q, "exit_mode": mode, "train_wf_best": best, "train_wf_table": table, "valid": v,
           "refits": refits, "verdict": "REJECT" if failed else "PASS", "gates_failed": failed}
    if keep:
        res["_trades"], res["_desired"] = t, extra["desired"]
    return res


def holdout(P: dict, tf: int, res: dict, step: int = 1) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    cfg = {k: res["setting"][k] for k in ("num_leaves", "min_data_in_leaf", "rounds")}
    a_tr, _ = WINDOWS["train"]
    a_h, b_h = WINDOWS["holdout"]
    warm = walk_forward(P, tf, cfg, WINDOWS["valid"][0], a_h, step)       # forecasts before the holdout,
    hmodels = {}
    hp = walk_forward(P, tf, cfg, a_h, b_h, step, models=hmodels)          # warm: only for the rolling bar
    pred = {c: np.where(np.isfinite(hp[c]), hp[c], warm[c]) for c in P}
    h, t, extra = judge(P, pred, a_h, b_h, res["q_in"], res["exit_mode"])
    t = explain(P, tf, t, pred, hmodels, res["q_in"])
    h["verdict"] = ("CONFIRMED" if h.get("mean_r", -1) > 0 and (h.get("ci_lo") or -1) > 0
                    and h["shift_median"] is not None and h["timing"] is not None
                    and h["timing"] > h["shift_median"] and h["breadth"]["share"] >= BREADTH_SHARE
                    else "FAILED")
    return h, t, extra["desired"]


# --------------------------------------------------------------------------
def holdout_choice(results: dict) -> int | None:
    """Pre-registered: among PASS timeframes, the highest TRAIN walk-forward mean."""
    ok = [r for r in results.values() if r["verdict"] == "PASS"]
    return max(ok, key=lambda r: r["train_wf_best"]["mean_r"])["tf"] if ok else None


def run(final: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lock = OUT / "holdout.json"
    if final:
        res = {tf: json.loads((OUT / f"tf{tf}.json").read_text()) for tf in TFS if (OUT / f"tf{tf}.json").exists()}
        if len(res) != len(TFS):
            raise SystemExit("--final refused: run the TRAIN/VALID step for every timeframe first")
        tf = holdout_choice(res)
        if tf is None:
            raise SystemExit("--final refused: no timeframe is PASS")
        if lock.exists():
            raise SystemExit(f"--final refused: holdout already used ({lock})")
        h, t, des = holdout(prepare(load_all(), tf), tf, res[tf])
        h["tf"] = tf
        lock.write_text(json.dumps(h, indent=1, default=str))
        t.to_csv(OUT / f"trades_holdout_tf{tf}.csv.gz", index=False)
        des.to_csv(OUT / f"desired_holdout_tf{tf}.csv.gz", index=False)
        write_report()
        print(json.dumps({k: h.get(k) for k in ("tf", "trades", "mean_r", "ci_lo", "verdict")}, indent=1))
        return
    by_tf = None
    for tf in TFS:
        path = OUT / f"tf{tf}.json"
        if path.exists():
            print(f"{path} exists: pre-registered, run once (delete only after a journaled code fix)")
            continue
        by_tf = by_tf or load_all()
        r = evaluate(prepare(by_tf, tf), tf, keep=True)
        r.pop("_trades").to_csv(OUT / f"trades_valid_tf{tf}.csv.gz", index=False)
        r.pop("_desired").to_csv(OUT / f"desired_valid_tf{tf}.csv.gz", index=False)
        path.write_text(json.dumps(r, indent=1, default=str))
        write_report()
        print(f"\nML_WF {TF_NAME[tf]}: {r['verdict']} failed {r['gates_failed']}")


def write_report() -> None:
    f = (lambda x: "-" if x is None else f"{x:+.4f}")
    nan = float("nan")
    L = ["# Walk-forward ML on many coins, entry and exit, no time limit (PLAN.md section 28)", "",
         "GENERATED by `src/ml_wf.py`. Do not edit by hand.", ""]
    res = {}
    for tf in TFS:
        p = OUT / f"tf{tf}.json"
        if not p.exists():
            L += [f"## {TF_NAME[tf]}: not run", ""]
            continue
        r = res[tf] = json.loads(p.read_text())
        v = r["valid"]
        L += [f"## {TF_NAME[tf]}: **{r['verdict']}** (failed: {r['gates_failed'] or 'none'})", "",
              f"- {r['coins_n']} coins, monthly refits, forecast {r['horizon_bars']} bars, stop {r['stop_atr']} ATR, "
              f"no clock; TRAIN walk-forward chose {r['setting']}, q_in {r['q_in']}, exit {r['exit_mode']} "
              f"({r['train_wf_best']['trades']} trades, mean {f(r['train_wf_best']['mean_r'])})",
              f"- VALID {v.get('trades', 0)} trades: mean net R {v.get('mean_r', nan):+.4f}, CI "
              f"[{v.get('ci_lo', nan):+.4f}, {v.get('ci_hi', nan):+.4f}], gross {v.get('gross_r', nan):+.4f}, "
              f"long {v.get('long_r', nan):+.3f} / short {v.get('short_r', nan):+.3f}, avg hold "
              f"{v.get('avg_hold_h', nan):.1f} bars, exits {v.get('exit_mix')}, time in market {v.get('time_in_market')}",
              f"- timing {f(v.get('timing'))} vs shifted median {f(v.get('shift_median'))} / p95 {f(v.get('shift_p95'))}; "
              f"cost x1.5 mean {f(v.get('stress_mean_r'))}; breadth {len(v['breadth']['beat'])} of "
              f"{v['breadth']['eligible']} ({v['breadth']['share']:.2f}); per year {v.get('per_year')}", "",
              "| coin | trades | net R | timing | shifted median | shifted p95 |", "|---|---|---|---|---|---|"]
        for c, x in v["per_coin"].items():
            L.append(f"| {c} | {x['trades']} | {f(x['mean_r'])} | {f(x['timing'])} | {f(x['shift_median'])} | "
                     f"{f(x['shift_p95'])} |")
        L += ["", "| setting | leaves | rounds | q_in | exit | TRAIN-WF trades | TRAIN-WF mean |",
              "|---|---|---|---|---|---|---|"]
        for x in r["train_wf_table"]:
            L.append(f"| {x['setting']} | {x['num_leaves']} | {x['rounds']} | {x['q_in']} | {x['exit']} | "
                     f"{x['trades']} | {f(x['mean_r'])} |")
        L.append("")
    if len(res) == len(TFS):
        ch = holdout_choice(res)
        L += [f"Holdout choice (pre-registered rule): {TF_NAME[ch] if ch else 'none - no timeframe is PASS'}", ""]
    hp = OUT / "holdout.json"
    if hp.exists():
        h = json.loads(hp.read_text())
        L += [f"**HOLDOUT ({TF_NAME[h['tf']]}): {h['verdict']}** - {h.get('trades', 0)} trades, mean "
              f"{f(h.get('mean_r'))}, CI [{f(h.get('ci_lo'))}, {f(h.get('ci_hi'))}], timing {f(h.get('timing'))} "
              f"vs shifted median {f(h.get('shift_median'))}, breadth {h['breadth']['share']:.2f}", ""]
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
