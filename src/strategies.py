"""Rule-based intraday strategy zoo for BTCUSDT USDT-M futures.

Every strategy is a function

    fn(bars, **params) -> pd.DataFrame[side, stop_dist, tp_dist, max_hold]

where the row for bar `i` is the order we would like to have filled at the
open of bar `i+1`. All indicators are causal (see indicators.py), so there
is no look-ahead by construction.

Stop distance defaults to k * ATR so that position sizing translates the
1%-of-equity risk rule into a consistent "R" per trade.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import indicators as ta

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _blank(n: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "side": np.zeros(n),
            "stop_dist": np.full(n, np.nan),
            "tp_dist": np.zeros(n),
            "max_hold": np.zeros(n),
            "atr": np.zeros(n),
            "be_at": np.zeros(n),
            "trail_at": np.zeros(n),
            "trail_atr": np.zeros(n),
        }
    )


def _pack(
    df: pd.DataFrame,
    side: pd.Series,
    atr: pd.Series,
    *,
    stop_mult: float,
    tp_mult: float = 0.0,
    max_hold: int = 12,
    risk_scale: pd.Series | None = None,
    be_at: float = 0.0,
    trail_at: float = 0.0,
    trail_atr: float = 0.0,
) -> pd.DataFrame:
    """Build the signal frame. `side != 0` marks an entry opportunity."""
    out = _blank(len(df))
    out.index = df.index  # MUST carry the time index, not a RangeIndex
    a = atr.to_numpy(float)
    s = side.to_numpy(float)
    out["side"] = np.where(np.isfinite(a) & (a > 0), s, 0.0)
    scale = (risk_scale.to_numpy(float) if risk_scale is not None
             else np.ones(len(df)))
    scale = np.where(np.isfinite(scale) & (scale > 0), scale, 1.0)
    dist = stop_mult * a * scale
    active = out["side"] != 0
    out["stop_dist"] = np.where(active, dist, np.nan)
    out["tp_dist"] = np.where(active, tp_mult * a * scale, 0.0)
    out["max_hold"] = np.where(active, float(max_hold), 0.0)
    # exit management. ATR is set on EVERY bar, not only signal bars: the
    # engine reads it on each bar of an open position to move the trailing
    # stop, and a 0 there silently froze the trail (journal Exp 011).
    out["atr"] = np.nan_to_num(a, nan=0.0)
    out["be_at"] = np.where(active, be_at, 0.0)
    out["trail_at"] = np.where(active, trail_at, 0.0)
    out["trail_atr"] = np.where(active, trail_atr, 0.0)
    return out


def _atr(df: pd.DataFrame, n: int) -> pd.Series:
    return ta.atr_(df["high"], df["low"], df["close"], n)


# --------------------------------------------------------------------------
# 1. EMA trend cross with pullback filter  (trend baseline)
# --------------------------------------------------------------------------
def ema_trend(bars: pd.DataFrame, fast=20, slow=50, stop_mult=2.0, tp_mult=4.0,
              max_hold=36, atr_n=14, be_at=0.0, trail_at=0.0,
              trail_atr=0.0) -> pd.DataFrame:
    c = bars["close"]
    ef, es = ta.ema(c, fast), ta.ema(c, slow)
    trend = (ef > es).astype(float)
    # entry when trend flips OR price pulls back to the fast EMA in trend
    cross_up = (trend.diff() == 1)
    cross_dn = (trend.diff() == -1)
    pull_long = (c <= ef) & (trend == 1) & (ef > es)
    pull_short = (c >= ef) & (trend == -1) & (ef < es)
    side = np.where(cross_up | pull_long, 1.0, np.where(cross_dn | pull_short, -1.0, 0.0))
    return _pack(bars, pd.Series(side, index=bars.index), _atr(bars, atr_n),
                 stop_mult=stop_mult, tp_mult=tp_mult, max_hold=max_hold,
                 be_at=be_at, trail_at=trail_at, trail_atr=trail_atr)


# --------------------------------------------------------------------------
# 2. Donchian channel breakout
# --------------------------------------------------------------------------
def donchian_breakout(bars: pd.DataFrame, n=60, stop_mult=2.0, tp_mult=3.0,
                      max_hold=48, atr_n=14, be_at=0.0, trail_at=0.0,
                      trail_atr=0.0) -> pd.DataFrame:
    h, l, c = bars["high"], bars["low"], bars["close"]
    up, dn = ta.donchian(h, l, n)
    prev_up, prev_dn = up.shift(1), dn.shift(1)
    side = np.where(c > prev_up, 1.0, np.where(c < prev_dn, -1.0, 0.0))
    # only take breakouts with some expansion, not inside a dead range
    rng = (up - dn) / c
    rng_min = np.nanmedian(rng) * 0.6
    side = np.where(rng > rng_min, side, 0.0)
    return _pack(bars, pd.Series(side, index=bars.index), _atr(bars, atr_n),
                 stop_mult=stop_mult, tp_mult=tp_mult, max_hold=max_hold,
                 be_at=be_at, trail_at=trail_at, trail_atr=trail_atr)


# --------------------------------------------------------------------------
# 3. Session VWAP mean reversion
# --------------------------------------------------------------------------
def vwap_reversion(bars: pd.DataFrame, n_z=2.0, stop_mult=2.0, tp_mult=2.0,
                   max_hold=36, atr_n=14, session_hours=24, be_at=0.0,
                   trail_at=0.0, trail_atr=0.0, z_n=200) -> pd.DataFrame:
    """Fade the session VWAP.

    The stretch is measured against a rolling standard deviation, NOT against
    ATR. Dividing by a 14-period ATR on a 3m chart makes |z| exceed 2 on most
    bars, so the "signal" fires nearly every bar and means nothing.
    """
    c = bars["close"]
    vw = ta.session_vwap(bars["high"], bars["low"], c, bars["volume"],
                         tz_hours=session_hours)
    dev = (c - vw).rolling(z_n, min_periods=z_n // 4).std()
    z = (c - vw) / dev.replace(0, np.nan)
    side = np.where(z < -n_z, 1.0, np.where(z > n_z, -1.0, 0.0))
    return _pack(bars, pd.Series(side, index=bars.index), _atr(bars, atr_n),
                 stop_mult=stop_mult, tp_mult=tp_mult, max_hold=max_hold,
                 be_at=be_at, trail_at=trail_at, trail_atr=trail_atr)


# --------------------------------------------------------------------------
# 4. Bollinger band reversion with RSI confirmation
# --------------------------------------------------------------------------
def bb_reversion(bars: pd.DataFrame, n=48, k=2.2, rsi_lo=28, rsi_hi=72,
                 stop_mult=1.8, tp_mult=1.6, max_hold=24, atr_n=14, be_at=0.0,
                 trail_at=0.0, trail_atr=0.0) -> pd.DataFrame:
    c = bars["close"]
    bb = ta.bbands(c, n, k)
    r = ta.rsi(c, 14)
    side = np.zeros(len(c))
    side = np.where((c < bb["dn"]) & (r < rsi_lo), 1.0, side)
    side = np.where((c > bb["up"]) & (r > rsi_hi), -1.0, side)
    return _pack(bars, pd.Series(side, index=bars.index), _atr(bars, atr_n),
                 stop_mult=stop_mult, tp_mult=tp_mult, max_hold=max_hold,
                 be_at=be_at, trail_at=trail_at, trail_atr=trail_atr)


# --------------------------------------------------------------------------
# 5. Supertrend flip
# --------------------------------------------------------------------------
def supertrend_flip(bars: pd.DataFrame, n=10, mult=3.0, stop_mult=2.0,
                    tp_mult=4.0, max_hold=48, atr_n=14, be_at=0.0,
                    trail_at=0.0, trail_atr=0.0) -> pd.DataFrame:
    st = ta.supertrend(bars["high"], bars["low"], bars["close"], n, mult)
    d = st["dir"].diff()
    # dir is -1/+1, so a flip produces a change of +/-2, not +/-1.
    side = np.where(d > 0, 1.0, np.where(d < 0, -1.0, 0.0))
    return _pack(bars, pd.Series(side, index=bars.index), _atr(bars, atr_n),
                 stop_mult=stop_mult, tp_mult=tp_mult, max_hold=max_hold,
                 be_at=be_at, trail_at=trail_at, trail_atr=trail_atr)


# --------------------------------------------------------------------------
# 6. Volatility squeeze expansion (NR7 / BB width squeeze)
# --------------------------------------------------------------------------
def squeeze_expansion(bars: pd.DataFrame, bb_n=48, squeeze_q=0.15, stop_mult=2.0,
                      tp_mult=3.0, max_hold=36, atr_n=14, be_at=0.0,
                      trail_at=0.0, trail_atr=0.0) -> pd.DataFrame:
    c = bars["close"]
    bb = ta.bbands(c, bb_n, 2.0)
    width = bb["width"]
    q = ta.rolling_quantile(width, 500, squeeze_q)
    squeeze = width <= q
    h, l = bars["high"], bars["low"]
    prev_h, prev_l = h.shift(1), l.shift(1)
    rng = (h - l) / c
    nr7 = rng <= rng.rolling(20, min_periods=20).min()
    fire = (squeeze.shift(1).fillna(False)) & (rng > rng.shift(1).rolling(5, min_periods=2).mean())
    brk_up = fire & (c > prev_h.rolling(10, min_periods=3).max())
    brk_dn = fire & (c < prev_l.rolling(10, min_periods=3).min())
    side = np.where(brk_up, 1.0, np.where(brk_dn, -1.0, 0.0))
    del nr7
    return _pack(bars, pd.Series(side, index=bars.index), _atr(bars, atr_n),
                 stop_mult=stop_mult, tp_mult=tp_mult, max_hold=max_hold,
                 be_at=be_at, trail_at=trail_at, trail_atr=trail_atr)


# --------------------------------------------------------------------------
# 7. Session range breakout (London / New York opens)
# --------------------------------------------------------------------------
def session_breakout(bars: pd.DataFrame, session_hours=(8,), stop_mult=1.8,
                     tp_mult=2.5, max_hold=24, atr_n=14, range_hours=8,
                     be_at=0.0, trail_at=0.0, trail_atr=0.0) -> pd.DataFrame:
    h, l, c = bars["high"], bars["low"], bars["close"]
    idx = bars.index
    side = np.zeros(len(c))
    for sh in session_hours:
        day = idx.floor("D")
        is_open = (idx.hour == sh)
        # range of the preceding `range_hours` bars
        hi_prev = h.shift(1).rolling(range_hours * 12, min_periods=6).max()
        lo_prev = l.shift(1).rolling(range_hours * 12, min_periods=6).min()
        trig_up = is_open & (c > hi_prev)
        trig_dn = is_open & (c < lo_prev)
        side = np.where(trig_up, 1.0, side)
        side = np.where(trig_dn, -1.0, side)
        del day
    return _pack(bars, pd.Series(side, index=bars.index), _atr(bars, atr_n),
                 stop_mult=stop_mult, tp_mult=tp_mult, max_hold=max_hold,
                 be_at=be_at, trail_at=trail_at, trail_atr=trail_atr)


# --------------------------------------------------------------------------
# 8. Taker-imbalance momentum
# --------------------------------------------------------------------------
def flow_momentum(bars: pd.DataFrame, ratio_n=20, thresh=0.56, stop_mult=2.0,
                  tp_mult=3.0, max_hold=24, atr_n=14, ema_n=100, be_at=0.0,
                  trail_at=0.0, trail_atr=0.0) -> pd.DataFrame:
    ratio = ta.taker_ratio(bars["taker_buy_base"], bars["volume"], ratio_n)
    c = bars["close"]
    trend = ta.ema(c, ema_n)
    mom = c.diff(12)
    side = np.zeros(len(c))
    long_ok = (ratio > thresh) & (c > trend) & (mom > 0)
    short_ok = (ratio < 1 - thresh) & (c < trend) & (mom < 0)
    side = np.where(long_ok, 1.0, np.where(short_ok, -1.0, 0.0))
    return _pack(bars, pd.Series(side, index=bars.index), _atr(bars, atr_n),
                 stop_mult=stop_mult, tp_mult=tp_mult, max_hold=max_hold,
                 be_at=be_at, trail_at=trail_at, trail_atr=trail_atr)


# --------------------------------------------------------------------------
# 9. Funding-rate fade (extreme funding -> mean reversion)
# --------------------------------------------------------------------------
def funding_fade(bars: pd.DataFrame, funding: pd.DataFrame, thresh=0.0003,
                 hold_hours=4, stop_mult=2.0, tp_mult=2.5, atr_n=14, be_at=0.0,
                 trail_at=0.0, trail_atr=0.0) -> pd.DataFrame:
    c = bars["close"]
    f = funding.copy()
    f["calc_time"] = pd.to_datetime(f["calc_time"], utc=True)
    rate = ta.ema(f["last_funding_rate"], 20)
    r = f[["calc_time", "last_funding_rate"]].copy()
    r["rate"] = rate
    s = r.set_index("calc_time")["last_funding_rate"]
    rate_on_bar = s.reindex(c.index, method="ffill")
    side = np.where(rate_on_bar > thresh, -1.0, np.where(rate_on_bar < -thresh, 1.0, 0.0))
    # hold a signal for hold_hours after the funding print
    side_s = pd.Series(side, index=c.index).replace(0.0, np.nan).ffill(limit=int(hold_hours * 12)).fillna(0.0)
    return _pack(bars, side_s, _atr(bars, atr_n), stop_mult=stop_mult,
                 tp_mult=tp_mult, max_hold=int(hold_hours * 12), be_at=be_at,
                 trail_at=trail_at, trail_atr=trail_atr)


# --------------------------------------------------------------------------
# 10. ADX trend pullback (only trade with real trend strength)
# --------------------------------------------------------------------------
def adx_trend(bars: pd.DataFrame, adx_min=22, fast=20, slow=50, stop_mult=2.0,
              tp_mult=3.5, max_hold=36, atr_n=14, be_at=0.0, trail_at=0.0,
              trail_atr=0.0) -> pd.DataFrame:
    h, l, c = bars["high"], bars["low"], bars["close"]
    a = ta.adx(h, l, c, 14)
    ef, es = ta.ema(c, fast), ta.ema(c, slow)
    side = np.zeros(len(c))
    strong = a["adx"] > adx_min
    side = np.where(strong & (ef > es) & (c <= ef), 1.0, side)
    side = np.where(strong & (ef < es) & (c >= ef), -1.0, side)
    return _pack(bars, pd.Series(side, index=bars.index), _atr(bars, atr_n),
                 stop_mult=stop_mult, tp_mult=tp_mult, max_hold=max_hold,
                 be_at=be_at, trail_at=trail_at, trail_atr=trail_atr)


# ==========================================================================
# GENERATION 2 - combined-indicator strategies
#
# The single-indicator versions above are baselines. These combine several
# independent pieces of evidence so that a trade only fires when trend,
# momentum, volatility regime and participation all agree. The idea is that
# most intraday losses come from trading one indicator in isolation inside a
# regime where it does not work.
# ==========================================================================
def _trend_regime(c: pd.Series, fast: int, slow: int, atr: pd.Series) -> pd.Series:
    """+1 uptrend, -1 downtrend, 0 undecided."""
    ef, es = ta.ema(c, fast), ta.ema(c, slow)
    slope = (es - es.shift(max(2, slow // 4))) / atr.replace(0, np.nan)
    out = pd.Series(0.0, index=c.index)
    out[(ef > es) & (slope > 0.02)] = 1.0
    out[(ef < es) & (slope < -0.02)] = -1.0
    return out


def _vol_regime(atr: pd.Series, slow_n: int = 100) -> pd.Series:
    """Slow/fast ATR ratio: >1 expanding vol, <1 quiet, extreme >2.2."""
    return atr / atr.rolling(slow_n, min_periods=20).mean()


def _hour_mask(index: pd.DatetimeIndex, hours: tuple[int, ...] | None) -> np.ndarray:
    if not hours:
        return np.ones(len(index), dtype=bool)
    h = index.hour.to_numpy()
    return np.isin(h, np.array(hours))


def _weekday_mask(index: pd.DatetimeIndex, days: tuple[int, ...] | None) -> np.ndarray:
    if not days:
        return np.ones(len(index), dtype=bool)
    return np.isin(index.dayofweek.to_numpy(), np.array(days))


# --------------------------------------------------------------------------
# 11. Trend + pullback + momentum + volume confirmation
# --------------------------------------------------------------------------
def combo_trend_pullback(
    bars: pd.DataFrame, fast: int = 21, slow: int = 55, rsi_lo: float = 42,
    rsi_hi: float = 58, adx_min: float = 20, vol_ratio_min: float = 0.8,
    pullback_ema: int = 9, stop_mult: float = 1.8, tp_mult: float = 3.0,
    max_hold: int = 36, atr_n: int = 14, be_at: float = 0.0,
    trail_at: float = 0.0, trail_atr: float = 0.0,
    hours: tuple[int, ...] | None = None, weekdays: tuple[int, ...] | None = None,
    vol_max: float = 2.4,
) -> pd.DataFrame:
    """Pull back to a fast EMA inside a confirmed trend, with RSI not yet
    exhausted, trend strength present, and participation not abnormally low."""
    c = bars["close"]
    h, l = bars["high"], bars["low"]
    atr = _atr(bars, atr_n)
    reg = _trend_regime(c, fast, slow, atr)
    ep = ta.ema(c, pullback_ema)
    r = ta.rsi(c, 14)
    a = ta.adx(h, l, c, 14)
    vr = _vol_regime(atr)
    touched_long = (l <= ep) & (c > ep)
    touched_short = (h >= ep) & (c < ep)
    ok = (a["adx"] > adx_min) & (vr > vol_ratio_min) & (vr < vol_max)
    long_ok = (reg == 1) & touched_long & (r > rsi_lo) & (r < 58) & ok
    short_ok = (reg == -1) & touched_short & (r < rsi_hi) & (r > 42) & ok
    side = np.where(long_ok, 1.0, np.where(short_ok, -1.0, 0.0))
    side = np.where(_hour_mask(bars.index, hours) & _weekday_mask(bars.index, weekdays),
                    side, 0.0)
    return _pack(bars, pd.Series(side, index=bars.index), atr, stop_mult=stop_mult,
                 tp_mult=tp_mult, max_hold=max_hold, be_at=be_at,
                 trail_at=trail_at, trail_atr=trail_atr)


# --------------------------------------------------------------------------
# 12. VWAP reversion gated by trend agreement (avoids fading a real trend)
# --------------------------------------------------------------------------
def combo_vwap_trend_aware(
    bars: pd.DataFrame, n_z: float = 1.8, ema_n: int = 100, adx_max: float = 28,
    stop_mult: float = 1.8, tp_mult: float = 2.2, max_hold: int = 30,
    atr_n: int = 14, be_at: float = 0.0, trail_at: float = 0.0,
    trail_atr: float = 0.0, hours: tuple[int, ...] | None = None,
    z_n: int = 200,
) -> pd.DataFrame:
    """Fade the session VWAP, but only while the market is NOT trending hard."""
    c = bars["close"]
    h, l = bars["high"], bars["low"]
    atr = _atr(bars, atr_n)
    vw = ta.session_vwap(h, l, c, bars["volume"])
    dev = (c - vw).rolling(z_n, min_periods=z_n // 4).std()
    z = (c - vw) / dev.replace(0, np.nan)
    a = ta.adx(h, l, c, 14)
    calm = a["adx"] < adx_max
    side = np.where((z < -n_z) & calm, 1.0, np.where((z > n_z) & calm, -1.0, 0.0))
    side = np.where(_hour_mask(bars.index, hours), side, 0.0)
    return _pack(bars, pd.Series(side, index=bars.index), atr, stop_mult=stop_mult,
                 tp_mult=tp_mult, max_hold=max_hold, be_at=be_at,
                 trail_at=trail_at, trail_atr=trail_atr)


# --------------------------------------------------------------------------
# 13. Breakout with regime + participation + anti-chop confirmation
# --------------------------------------------------------------------------
def combo_breakout_confirmed(
    bars: pd.DataFrame, n: int = 48, adx_min: float = 18, vol_expand: float = 1.0,
    ema_n: int = 100, stop_mult: float = 1.8, tp_mult: float = 3.5,
    max_hold: int = 48, atr_n: int = 14, be_at: float = 0.0,
    trail_at: float = 0.0, trail_atr: float = 0.0,
    hours: tuple[int, ...] | None = None, vol_max: float = 2.5,
) -> pd.DataFrame:
    """Donchian breakout, but only when trend strength is rising and volatility
    is expanding - i.e. not breaking out of a dead range."""
    h, l, c = bars["high"], bars["low"], bars["close"]
    atr = _atr(bars, atr_n)
    up = h.rolling(n, min_periods=n).max().shift(1)
    dn = l.rolling(n, min_periods=n).min().shift(1)
    a = ta.adx(h, l, c, 14)
    a_ok = (a["adx"] > adx_min) & (a["adx"] > a["adx"].shift(6))
    vr = _vol_regime(atr)
    v_ok = (vr > vol_expand) & (vr < vol_max)
    ef = ta.ema(c, ema_n)
    long_ok = (c > up) & a_ok & v_ok & (c > ef)
    short_ok = (c < dn) & a_ok & v_ok & (c < ef)
    side = np.where(long_ok, 1.0, np.where(short_ok, -1.0, 0.0))
    side = np.where(_hour_mask(bars.index, hours), side, 0.0)
    return _pack(bars, pd.Series(side, index=bars.index), atr, stop_mult=stop_mult,
                 tp_mult=tp_mult, max_hold=max_hold, be_at=be_at,
                 trail_at=trail_at, trail_atr=trail_atr)


# --------------------------------------------------------------------------
# 14. Volatility expansion continuation with taker-flow agreement
# --------------------------------------------------------------------------
def combo_vol_flow(
    bars: pd.DataFrame, squeeze_q: float = 0.2, ratio_n: int = 20,
    flow_thresh: float = 0.53, stop_mult: float = 1.8, tp_mult: float = 3.0,
    max_hold: int = 30, atr_n: int = 14, be_at: float = 0.0,
    trail_at: float = 0.0, trail_atr: float = 0.0,
    hours: tuple[int, ...] | None = None,
) -> pd.DataFrame:
    """Squeeze releases, confirmed by aggressive taker flow in the same
    direction. Volatility tells us *when*, flow tells us *which way*."""
    h, l, c, v = bars["high"], bars["low"], bars["close"], bars["volume"]
    atr = _atr(bars, atr_n)
    bb = ta.bbands(c, 48, 2.0)
    q = ta.rolling_quantile(bb["width"], 500, squeeze_q)
    squeeze = bb["width"] <= q
    flow = ta.taker_ratio(bars["taker_buy_base"], v, ratio_n)
    hi_prev = h.rolling(8, min_periods=4).max().shift(1)
    lo_prev = l.rolling(8, min_periods=4).min().shift(1)
    fire = squeeze.shift(1).fillna(False)
    long_ok = fire & (c > hi_prev) & (flow > flow_thresh)
    short_ok = fire & (c < lo_prev) & (flow < 1 - flow_thresh)
    side = np.where(long_ok, 1.0, np.where(short_ok, -1.0, 0.0))
    side = np.where(_hour_mask(bars.index, hours), side, 0.0)
    return _pack(bars, pd.Series(side, index=bars.index), atr, stop_mult=stop_mult,
                 tp_mult=tp_mult, max_hold=max_hold, be_at=be_at,
                 trail_at=trail_at, trail_atr=trail_atr)


# --------------------------------------------------------------------------
# 15. Funding-aware mean reversion (carry + reversion)
# --------------------------------------------------------------------------
def combo_funding_reversion(
    bars: pd.DataFrame, funding: pd.DataFrame, rate_thresh: float = 0.0002,
    z_thresh: float = 1.5, z_n: int = 96, stop_mult: float = 1.8,
    tp_mult: float = 2.2, max_hold: int = 30, atr_n: int = 14,
    be_at: float = 0.0, trail_at: float = 0.0, trail_atr: float = 0.0,
    hours: tuple[int, ...] | None = None,
) -> pd.DataFrame:
    """When funding is stretched, the crowd is one-sided. Fade it, but only
    when price is also stretched from its own recent mean."""
    c = bars["close"]
    atr = _atr(bars, atr_n)
    mean = c.rolling(z_n, min_periods=z_n // 2).mean()
    sd = c.rolling(z_n, min_periods=z_n // 2).std()
    z = (c - mean) / sd.replace(0, np.nan)
    f = funding.copy()
    f["calc_time"] = pd.to_datetime(f["calc_time"], utc=True)
    rate = f.set_index("calc_time")["last_funding_rate"].reindex(c.index, method="ffill")
    crowded_long = (rate > rate_thresh) & (z > z_thresh)
    crowded_short = (rate < -rate_thresh) & (z < -z_thresh)
    side = np.where(crowded_long, -1.0, np.where(crowded_short, 1.0, 0.0))
    side = np.where(_hour_mask(bars.index, hours), side, 0.0)
    return _pack(bars, pd.Series(side, index=bars.index), atr, stop_mult=stop_mult,
                 tp_mult=tp_mult, max_hold=max_hold, be_at=be_at,
                 trail_at=trail_at, trail_atr=trail_atr)


# --------------------------------------------------------------------------
# 16. Confluence vote - several independent rules must agree
# --------------------------------------------------------------------------
def combo_vote(bars: pd.DataFrame, funding: pd.DataFrame | None = None,
               n_votes: int = 3, stop_mult: float = 1.8, tp_mult: float = 3.0,
               max_hold: int = 36, atr_n: int = 14, be_at: float = 0.0,
               trail_at: float = 0.0, trail_atr: float = 0.0,
               hours: tuple[int, ...] | None = None) -> pd.DataFrame:
    """Count how many independent families agree on direction; trade only when
    at least `n_votes` do. Fewer, higher-conviction trades."""
    c, h, l = bars["close"], bars["high"], bars["low"]
    atr = _atr(bars, atr_n)
    votes = []

    ef, es = ta.ema(c, 21), ta.ema(c, 55)
    votes.append(np.where(ef > es, 1.0, -1.0))

    st = ta.supertrend(h, l, c, 10, 3.0)
    votes.append(np.where(st["dir"] > 0, 1.0, -1.0))

    a = ta.adx(h, l, c, 14)
    votes.append(np.where((a["pdi"] > a["mdi"]) & (a["adx"] > 20), 1.0, -1.0))

    tr = ta.taker_ratio(bars["taker_buy_base"], bars["volume"], 20)
    votes.append(np.where(tr > 0.53, 1.0, -1.0))

    hi48 = h.rolling(48, min_periods=24).max()
    lo48 = l.rolling(48, min_periods=24).min()
    votes.append(np.where(c > lo48 + 0.5 * (hi48 - lo48), 1.0, -1.0))

    r = ta.rsi(c, 14)
    votes.append(np.where(r > 50, 1.0, -1.0))

    V = np.vstack([np.nan_to_num(v, nan=0.0) for v in votes])
    n_up = (V > 0).sum(axis=0)
    n_dn = (V < 0).sum(axis=0)
    # Fire only on the CROSS of the vote threshold. Without this the "confluence"
    # strategy signals on essentially every bar, which is just a disguised
    # always-in-market trend follower and pays full spread every cycle.
    up = n_up >= n_votes
    dn = n_dn >= n_votes
    up_x = up & ~np.r_[False, up[:-1]]
    dn_x = dn & ~np.r_[False, dn[:-1]]
    side = np.where(up_x, 1.0, np.where(dn_x, -1.0, 0.0))
    side = np.where(np.isfinite(atr.to_numpy()) & (atr.to_numpy() > 0), side, 0.0)
    side = np.where(_hour_mask(bars.index, hours), side, 0.0)
    return _pack(bars, pd.Series(side, index=bars.index), atr, stop_mult=stop_mult,
                 tp_mult=tp_mult, max_hold=max_hold, be_at=be_at,
                 trail_at=trail_at, trail_atr=trail_atr)


# --------------------------------------------------------------------------
# 17. Time-window breakout, Asia -> London -> New York
# --------------------------------------------------------------------------
def combo_session_window(
    bars: pd.DataFrame, hours: tuple[int, ...] = (13, 14, 15), range_n: int = 24,
    stop_mult: float = 1.6, tp_mult: float = 2.5, max_hold: int = 18,
    atr_n: int = 14, be_at: float = 0.0, trail_at: float = 0.0,
    trail_atr: float = 0.0, weekdays: tuple[int, ...] | None = None,
) -> pd.DataFrame:
    """Break of the pre-window range, taken only during fixed UTC hours - the
    classic London/NY intraday window, filtered to weekdays."""
    h, l, c = bars["high"], bars["low"], bars["close"]
    atr = _atr(bars, atr_n)
    hi_p = h.rolling(range_n, min_periods=range_n // 2).max().shift(1)
    lo_p = l.rolling(range_n, min_periods=range_n // 2).min().shift(1)
    in_h = _hour_mask(bars.index, hours) & _weekday_mask(bars.index, weekdays)
    side = np.where(in_h & (c > hi_p), 1.0, np.where(in_h & (c < lo_p), -1.0, 0.0))
    return _pack(bars, pd.Series(side, index=bars.index), atr, stop_mult=stop_mult,
                 tp_mult=tp_mult, max_hold=max_hold, be_at=be_at,
                 trail_at=trail_at, trail_atr=trail_atr)


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------
REGISTRY = {
    # generation 1 - single-indicator baselines
    "ema_trend": ema_trend,
    "donchian_breakout": donchian_breakout,
    "vwap_reversion": vwap_reversion,
    "bb_reversion": bb_reversion,
    "supertrend_flip": supertrend_flip,
    "squeeze_expansion": squeeze_expansion,
    "session_breakout": session_breakout,
    "flow_momentum": flow_momentum,
    "funding_fade": funding_fade,
    "adx_trend": adx_trend,
    # generation 2 - combined indicators + exit management
    "combo_trend_pullback": combo_trend_pullback,
    "combo_vwap_trend_aware": combo_vwap_trend_aware,
    "combo_breakout_confirmed": combo_breakout_confirmed,
    "combo_vol_flow": combo_vol_flow,
    "combo_funding_reversion": combo_funding_reversion,
    "combo_vote": combo_vote,
    "combo_session_window": combo_session_window,
}

NEEDS_FUNDING = {"funding_fade", "combo_funding_reversion"}
