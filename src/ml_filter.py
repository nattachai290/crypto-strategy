"""ML trade filter.

Idea: keep the rule strategies as the *candidate generator* (they define
where we look and how big the stop is), then use a model to decide which
candidates are actually worth taking.

Important design choices that keep this honest:

* Features are computed with information available strictly at the signal
  bar (i-1 close) - no future leakage.
* The label is the *realised net R of the trade*, produced by the same
  intrabar logic as the backtester (stop-first ambiguity, taker fees,
  slippage). A model that cannot beat "always take the signal" is useless.
* Training is strictly walk-forward: fit on [t0, t1), predict on [t1, t2).
  The model never sees a bar it will be scored on.
* Threshold is chosen on training data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
import indicators as ta
from backtest import run_backtest

# --------------------------------------------------------------------------
# Feature engineering
# --------------------------------------------------------------------------
def build_features(bars: pd.DataFrame, funding: pd.DataFrame | None = None,
                   ) -> pd.DataFrame:
    """Causal features for every bar (the signal bar is the previous close)."""
    o, h, l, c, v = (bars["open"], bars["high"], bars["low"],
                     bars["close"], bars["volume"])
    f = pd.DataFrame(index=bars.index)

    atr = ta.atr_(h, l, c, 14)
    atr_slow = ta.atr_(h, l, c, 100)
    f["atr_pct"] = atr / c
    f["atr_ratio"] = atr / atr_slow.replace(0, np.nan)
    f["range_pct"] = (h - l) / c

    for f_n, s_n in ((9, 21), (20, 50), (50, 200)):
        ef, es = ta.ema(c, f_n), ta.ema(c, s_n)
        f[f"ema_spread_{f_n}_{s_n}"] = (ef - es) / atr.replace(0, np.nan)
        f[f"ema_slope_{f_n}"] = (ef - ef.shift(5)) / atr.replace(0, np.nan)

    r = ta.rsi(c, 14)
    f["rsi"] = r
    f["rsi_slope"] = r - r.shift(5)

    a = ta.adx(h, l, c, 14)
    f["adx"] = a["adx"]
    f["di_spread"] = (a["pdi"] - a["mdi"]) / 20.0

    bb = ta.bbands(c, 48, 2.0)
    f["bb_width"] = bb["width"]
    f["bb_width_pct"] = ta.rolling_pct_rank(bb["width"], 500)
    f["bb_pos"] = (c - bb["dn"]) / (bb["up"] - bb["dn"]).replace(0, np.nan)

    vw = ta.session_vwap(h, l, c, v)
    f["vwap_dist"] = (c - vw) / atr.replace(0, np.nan)

    hi24, lo24 = h.rolling(24 * 12, min_periods=60).max(), l.rolling(24 * 12, min_periods=60).min()
    f["from_24h_high"] = (c - hi24) / atr.replace(0, np.nan)
    f["from_24h_low"] = (c - lo24) / atr.replace(0, np.nan)
    f["24h_range_pos"] = (c - lo24) / (hi24 - lo24).replace(0, np.nan)

    ret = c.pct_change()
    f["rv_12"] = ret.rolling(12, min_periods=6).std()
    f["rv_48"] = ret.rolling(48, min_periods=24).std()
    f["rv_ratio"] = f["rv_12"] / f["rv_48"].replace(0, np.nan)
    f["ret_1"] = ret
    f["ret_6"] = c.pct_change(6)
    f["ret_36"] = c.pct_change(36)

    tr = ta.taker_ratio(bars["taker_buy_base"], v, 20)
    f["taker_ratio"] = tr
    f["taker_z"] = (tr - tr.rolling(500, min_periods=100).mean()) / tr.rolling(500, min_periods=100).std().replace(0, np.nan)
    f["vol_z"] = (v - v.rolling(200, min_periods=50).mean()) / v.rolling(200, min_periods=50).std().replace(0, np.nan)
    f["trade_count"] = bars.get("trades", pd.Series(index=bars.index, dtype=float)).pct_change()

    # calendar
    hod = bars.index.hour + bars.index.minute / 60.0
    f["hod_sin"] = np.sin(2 * np.pi * hod / 24.0)
    f["hod_cos"] = np.cos(2 * np.pi * hod / 24.0)
    f["dow"] = bars.index.dayofweek.astype(float)

    # realised funding level
    if funding is not None and len(funding):
        fnd = funding.copy()
        fnd["calc_time"] = pd.to_datetime(fnd["calc_time"], utc=True)
        s = fnd.set_index("calc_time")["last_funding_rate"]
        lvl = s.reindex(bars.index, method="ffill")
        f["funding"] = lvl
        f["funding_ma"] = s.rolling(20, min_periods=5).mean().reindex(bars.index, method="ffill")
    else:
        f["funding"] = 0.0
        f["funding_ma"] = 0.0

    return f.replace([np.inf, -np.inf], np.nan)


FEATURE_COLS_CACHE: list[str] = []


# --------------------------------------------------------------------------
# Trade outcome simulation (label generation) - mirrors backtest.py logic
# --------------------------------------------------------------------------
def _median_step_secs(index: pd.DatetimeIndex) -> float:
    if len(index) < 3:
        return 300.0
    d = np.diff(index.to_numpy("datetime64[s]").astype("int64"))
    return float(np.median(d)) if len(d) else 300.0


def simulate_outcomes(bars: pd.DataFrame, sig: pd.DataFrame, *,
                      slippage: float = C.SLIPPAGE,
                      fee_taker: float = C.FEE_TAKER,
                      funding: pd.DataFrame | None = None,
                      max_bars: int = 200) -> pd.DataFrame:
    """For every bar with side != 0, compute the net R of entering next open.

    Returned frame is indexed by the SIGNAL bar (execution is next open).

    Performance note: this is the hottest loop in the project - it was
    rebuilding a fresh searchsorted over the funding array for every bar of
    every candidate, which dominated every experiment's wall clock. The
    per-bar funding index and its prefix sums are now computed once.
    """
    o = bars["open"].to_numpy(float).tolist()
    h = bars["high"].to_numpy(float).tolist()
    l = bars["low"].to_numpy(float).tolist()
    n = len(bars)

    side = sig["side"].to_numpy(float).tolist()
    sd = sig["stop_dist"].to_numpy(float).tolist()
    td = sig["tp_dist"].to_numpy(float).tolist()
    mh = sig["max_hold"].to_numpy(float).tolist()

    # ---- precompute the funding index for every bar, plus prefix sums ----
    if funding is not None and len(funding):
        fser = funding.copy()
        fser["calc_time"] = pd.to_datetime(fser["calc_time"], utc=True)
        fser = fser.sort_values("calc_time")
        ft = fser["calc_time"].to_numpy("datetime64[ns]")
        fr = fser["last_funding_rate"].to_numpy(float).tolist()
    else:
        ft, fr = np.zeros(0, dtype="datetime64[ns]"), []
    idx_int = bars.index.to_numpy("datetime64[ns]")
    if len(ft):
        # f_lo[k] = number of funding events strictly before the bar's open
        # f_hi[k] = number of funding events before the bar's close
        step = np.timedelta64(int(_median_step_secs(bars.index)), "s")
        f_lo = np.searchsorted(ft, idx_int, side="left")
        f_hi = np.searchsorted(ft, idx_int + step, side="left")
        # prefix sums so the cost of events [a, b) is one subtraction
        pre = np.concatenate(([0.0], np.cumsum(fr))).tolist()
    else:
        f_lo = np.zeros(n, dtype=np.int64)
        f_hi = np.zeros(n, dtype=np.int64)
        pre = [0.0]
    f_lo = f_lo.tolist()
    f_hi = f_hi.tolist()

    out_i, out_r, out_reason, out_bars, out_side = [], [], [], [], []
    out_sd, out_td, out_mh, out_entry = [], [], [], []
    for i in range(n - 1):
        s = side[i]
        d = sd[i]
        if s == 0 or d != d or d <= 0 or mh[i] <= 0:
            continue
        j = i + 1
        entry = o[j] * (1 + slippage * s)
        stop = entry - s * d
        tpv = td[i]
        target = entry + s * tpv if tpv > 0 else 0.0
        m = int(mh[i])
        if m > max_bars:
            m = max_bars
        if m > n - 1 - j:
            m = n - 1 - j
        fund_cost = 0.0
        r = 0.0
        reason = "time"
        held = m
        k_end = j + m
        for k in range(j, k_end + 1):
            a, b = f_lo[k], f_hi[k]
            if b > a:
                fund_cost += (pre[b] - pre[a]) * s
            hk, lk = h[k], l[k]
            if s > 0:
                stop_hit = lk <= stop
                tp_hit = target > 0 and hk >= target
            else:
                stop_hit = hk >= stop
                tp_hit = target > 0 and lk <= target
            if stop_hit:
                px = o[k] if ((o[k] < stop) if s > 0 else (o[k] > stop)) else stop
                r, reason, held = _net_r(s, entry, px, d, slippage, fee_taker,
                                         fund_cost), "stop", k - j + 1
                break
            if tp_hit:
                px = o[k] if ((o[k] > target) if s > 0 else (o[k] < target)) else target
                r, reason, held = _net_r(s, entry, px, d, slippage, fee_taker,
                                         fund_cost), "target", k - j + 1
                break
        else:
            k = k_end
            if k < n:
                r, reason, held = _net_r(s, entry, o[k], d, slippage, fee_taker,
                                         fund_cost), "time", m
        out_i.append(i)
        out_r.append(r)
        out_reason.append(reason)
        out_bars.append(held)
        out_side.append(s)
        out_sd.append(d)
        out_td.append(tpv)
        out_mh.append(int(mh[i]))
        out_entry.append(entry)

    # keep the tz-aware index; to_numpy("datetime64[ns]") drops the tz and then
    # the result cannot be joined back onto the feature frame
    idx = bars.index[np.array(out_i, dtype=int)] if out_i else bars.index[:0]
    return pd.DataFrame({
        "i": out_i, "net_r": out_r, "reason": out_reason, "bars": out_bars,
        "side": out_side, "stop_dist": out_sd, "tp_dist": out_td,
        "max_hold": out_mh, "entry_px": out_entry,
    }, index=idx)


def _net_r(side, entry, exit_px, stop_dist, slippage, fee_taker, fund_cost) -> float:
    px = exit_px * (1 - slippage * side)
    gross = side * (px - entry) / stop_dist
    # fees: entry notional + exit notional, both taker, expressed in R
    fee_r = (fee_taker * entry + fee_taker * px) / stop_dist
    fund_r = fund_cost * entry / stop_dist
    return gross - fee_r - fund_r
