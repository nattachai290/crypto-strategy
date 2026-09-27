"""Indicator library (pure numpy/pandas, no TA dependency).

All functions return either a pandas Series aligned to the input index or a
numpy array. Everything is causal: the value at bar `i` uses only bars <= i,
so it is safe to use in a backtest without look-ahead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------
# Trend
# --------------------------------------------------------------------------
def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def donchian(high: pd.Series, low: pd.Series, n: int) -> tuple[pd.Series, pd.Series]:
    up = high.rolling(n, min_periods=n).max()
    dn = low.rolling(n, min_periods=n).min()
    return up, dn


def supertrend(
    high: pd.Series, low: pd.Series, close: pd.Series, n: int = 10, mult: float = 3.0
) -> pd.DataFrame:
    """Supertrend.

    Implemented over plain Python floats, not numpy scalars. This is inherently
    a state machine (each band depends on the previous bar's final band), but
    the *first* version did the recursion with numpy scalar indexing and
    np.isnan(), which took >15 minutes on 700k bars while every vectorised
    indicator around it ran in 0.2s. Plain floats make it ~0.3s.
    """
    atr = atr_(high, low, close, n)
    hl2 = (high + low) / 2.0
    up = ((hl2 + mult * atr).to_numpy(float)).tolist()
    dn = ((hl2 - mult * atr).to_numpy(float)).tolist()
    cv = close.to_numpy(float).tolist()
    m = len(cv)

    f_up = [float("nan")] * m
    f_dn = [float("nan")] * m
    dirn = [0.0] * m
    trend = [float("nan")] * m

    nan = float("nan")
    prev_up = nan
    prev_dn = nan
    prev_dir = 0.0
    prev_c = nan
    for i in range(m):
        u = up[i]
        d = dn[i]
        c = cv[i]
        # treat NaN as "no band yet"
        if u != u or d != d or c != c:
            continue
        # The band recurrence uses the PREVIOUS bar's close, not this one's.
        if prev_up == prev_up and prev_c == prev_c:
            fu = u if (u < prev_up or prev_c > prev_up) else prev_up
        else:
            fu = u
        if prev_dn == prev_dn and prev_c == prev_c:
            fd = d if (d > prev_dn or prev_c < prev_dn) else prev_dn
        else:
            fd = d
        if prev_dir == 0.0:
            nd = 1.0
        elif prev_dir > 0 and c < fd:
            nd = -1.0
        elif prev_dir < 0 and c > fu:
            nd = 1.0
        else:
            nd = prev_dir
        f_up[i] = fu
        f_dn[i] = fd
        dirn[i] = nd
        trend[i] = fd if nd > 0 else fu
        prev_up, prev_dn, prev_dir, prev_c = fu, fd, nd, c

    idx = close.index
    return pd.DataFrame(
        {"trend": trend, "dir": dirn, "upper": f_up, "lower": f_dn}, index=idx
    )


# --------------------------------------------------------------------------
# Volatility
# --------------------------------------------------------------------------
def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    pc = close.shift(1)
    return pd.concat(
        [high - low, (high - pc).abs(), (low - pc).abs()], axis=1
    ).max(axis=1)


def atr_(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0.0)
    dn = (-d).clip(lower=0.0)
    au = up.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    ad = dn.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    rs = au / ad.replace(0.0, np.nan)
    return 100.0 - 100.0 / (1.0 + rs)


def adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.DataFrame:
    up = high.diff()
    dn = -low.diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = true_range(high, low, close)
    atr = tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    pdi = 100.0 * pd.Series(plus, index=high.index).ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / atr
    mdi = 100.0 * pd.Series(minus, index=high.index).ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / atr
    dx = 100.0 * (pdi - mdi).abs() / (pdi + mdi).replace(0.0, np.nan)
    a = dx.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return pd.DataFrame({"adx": a, "pdi": pdi, "mdi": mdi})


def zscore(s: pd.Series, n: int = 100) -> pd.Series:
    m = s.rolling(n, min_periods=n).mean()
    sd = s.rolling(n, min_periods=n).std(ddof=0)
    return (s - m) / sd.replace(0.0, np.nan)


def bbands(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    m = close.rolling(n, min_periods=n).mean()
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    return pd.DataFrame({"mid": m, "up": m + k * sd, "dn": m - k * sd, "width": 4 * sd / m})


# --------------------------------------------------------------------------
# Volume / flow
# --------------------------------------------------------------------------
def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    return (np.sign(close.diff().fillna(0.0)) * volume).cumsum()


def cvd_proxy(close: pd.Series, taker_buy_base: pd.Series, volume: pd.Series, n: int = 1):
    """Cumulative volume delta: (2*taker_buy - volume)."""
    return (2.0 * taker_buy_base - volume).cumsum()


def taker_ratio(taker_buy_base: pd.Series, volume: pd.Series, n: int = 30) -> pd.Series:
    r = taker_buy_base / volume.replace(0.0, np.nan)
    return r.rolling(n, min_periods=n).mean()


def rolling_z(s: pd.Series, n: int) -> pd.Series:
    return zscore(s, n)


# --------------------------------------------------------------------------
# Fast rolling quantile / percentile rank
# --------------------------------------------------------------------------
def rolling_quantile(s: pd.Series, n: int, q: float, step: int = 12) -> pd.Series:
    """Approximate rolling quantile, computed on a coarser grid then upsampled.

    pandas' rolling(n).quantile() is O(n*w) with a sort per window, which takes
    minutes on 200k bars. The target quantities here (band width thresholds,
    squeeze cutoffs) vary slowly, so evaluating them every `step` bars and
    forward-filling is numerically almost identical and ~`step` times faster.
    """
    if step <= 1:
        return s.rolling(n, min_periods=max(2, n // 4)).quantile(q)
    coarse = s.iloc[::step]
    out = coarse.rolling(n // step, min_periods=max(2, n // step // 4)).quantile(q)
    return out.reindex(s.index, method="ffill")


def rolling_pct_rank(s: pd.Series, n: int, step: int = 12) -> pd.Series:
    """Percentile rank of the current value within a trailing window, in [0,1]."""
    if step <= 1:
        w = s.rolling(n, min_periods=max(2, n // 4))
        return w.rank(pct=True)
    coarse = s.iloc[::step]
    out = coarse.rolling(n // step, min_periods=max(2, n // step // 4)).rank(pct=True)
    return out.reindex(s.index, method="ffill")



# --------------------------------------------------------------------------
# VWAPs
# --------------------------------------------------------------------------
def session_vwap(high, low, close, volume, tz_hours: int = 24) -> pd.Series:
    """Rolling anchored VWAP anchored to each UTC day (crypto 24h session)."""
    idx = close.index
    tp = (high + low + close) / 3.0
    day = idx.floor(f"{tz_hours}h") if tz_hours != 24 else idx.floor("D")
    num = (tp * volume).groupby(day).cumsum()
    den = volume.groupby(day).cumsum()
    return num / den.replace(0.0, np.nan)


def anchored_vwap(high, low, close, volume, anchor: pd.Series) -> pd.Series:
    """VWAP since the last bar where `anchor` was True."""
    tp = (high + low + close) / 3.0
    grp = anchor.cumsum()
    num = (tp * volume).groupby(grp).cumsum()
    den = volume.groupby(grp).cumsum()
    return num / den.replace(0.0, np.nan)


# --------------------------------------------------------------------------
# Time-of-day / calendar
# --------------------------------------------------------------------------
def utc_hour(idx: pd.DatetimeIndex) -> np.ndarray:
    return idx.hour.to_numpy()


def day_of_week(idx: pd.DatetimeIndex) -> np.ndarray:
    return idx.dayofweek.to_numpy()
