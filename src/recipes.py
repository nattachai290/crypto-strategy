"""Recipe strategies: combine entry triggers, filters and exits from JSON.

A recipe lets you build a new combined strategy WITHOUT writing Python:

    {
      "triggers": [{"type": "donchian_break", "n": 48}],
      "trigger_mode": "any",
      "filters":  [{"type": "trend_ema", "fast": 50, "slow": 200},
                   {"type": "adx_min", "min": 20}],
      "direction": "both",
      "stop":  {"type": "atr", "mult": 3.0},
      "tp":    {"type": "r", "r": 2.0},
      "be_at": 1.0, "trail_at": 1.5, "trail_atr": 2.0,
      "max_hold_hours": 4, "cooldown_bars": 4, "atr_n": 14
    }

How the pieces combine (all causal - bar i uses only bars <= i):
  1. TRIGGERS say *when* to act: each returns +1 (long), -1 (short) or 0 on the
     bar where its event happens. trigger_mode "any" fires if any trigger
     fires (if two disagree on the same bar, nothing fires); "all" needs every
     trigger to fire in the same direction within `confirm_bars` bars.
  2. FILTERS say *whether* a direction is allowed on that bar. A long needs
     every filter's long_ok; a short needs every filter's short_ok.
  3. `direction` can restrict to "long" or "short" only.
  4. `cooldown_bars` suppresses new signals for N bars after one fires.
  5. EXITS: stop (ATR or swing structure), take-profit (ATR multiple, R
     multiple, or none), break-even, ATR trailing stop, and a time stop. The
     engine applies them with no look-ahead (see backtest.py).

To add a building block: write a function below, add it to TRIGGERS or
FILTERS, and document its params in AGENTS.md / docs/research/TECHNIQUES.md.
Every block must be causal. Never use .shift(-k), centred windows, or any
value from a bar after i.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import indicators as ta  # noqa: E402


def _cross_up(a: pd.Series, b) -> np.ndarray:
    a = pd.Series(a)
    b = b if np.isscalar(b) else pd.Series(b, index=a.index)
    now = (a > b)
    prev = now.shift(1, fill_value=False)
    return (now & ~prev).to_numpy()


def _cross_dn(a: pd.Series, b) -> np.ndarray:
    a = pd.Series(a)
    b = b if np.isscalar(b) else pd.Series(b, index=a.index)
    now = (a < b)
    prev = now.shift(1, fill_value=False)
    return (now & ~prev).to_numpy()


def _side(long_ev: np.ndarray, short_ev: np.ndarray) -> np.ndarray:
    long_ev = np.nan_to_num(np.asarray(long_ev, dtype=float)) > 0
    short_ev = np.nan_to_num(np.asarray(short_ev, dtype=float)) > 0
    return np.where(long_ev & ~short_ev, 1.0, np.where(short_ev & ~long_ev, -1.0, 0.0))


# ==========================================================================
# TRIGGERS  fn(bars, funding, **p) -> np.ndarray of +1 / -1 / 0
# ==========================================================================
def t_ema_cross(b, f, fast=20, slow=50):
    """Fast EMA crosses slow EMA (trend start)."""
    ef, es = ta.ema(b["close"], fast), ta.ema(b["close"], slow)
    return _side(_cross_up(ef, es), _cross_dn(ef, es))


def t_donchian_break(b, f, n=48):
    """Close breaks the previous n-bar high/low (breakout)."""
    up, dn = ta.donchian(b["high"], b["low"], n)
    c = b["close"]
    return _side(_cross_up(c, up.shift(1)), _cross_dn(c, dn.shift(1)))


def t_supertrend_flip(b, f, n=10, mult=3.0):
    """Supertrend changes direction."""
    d = ta.supertrend(b["high"], b["low"], b["close"], n, mult)["dir"].diff()
    return _side(d > 0, d < 0)


def t_rsi_revert(b, f, n=14, lo=30, hi=70):
    """RSI crosses back up through `lo` (long) / down through `hi` (short)."""
    r = ta.rsi(b["close"], n)
    return _side(_cross_up(r, lo), _cross_dn(r, hi))


def t_bb_revert(b, f, n=20, k=2.0):
    """Close comes back inside the Bollinger band after being outside."""
    bb = ta.bbands(b["close"], n, k)
    c = b["close"]
    return _side(_cross_up(c, bb["dn"]), _cross_dn(c, bb["up"]))


def t_zscore_revert(b, f, n=96, z=2.0):
    """Price z-score vs its n-bar mean crosses back inside +-z."""
    zs = ta.zscore(b["close"], n)
    return _side(_cross_up(zs, -z), _cross_dn(zs, z))


def t_vwap_revert(b, f, z=2.0, z_n=200):
    """Distance from the daily VWAP, in rolling std units, crosses back inside +-z."""
    c = b["close"]
    vw = ta.session_vwap(b["high"], b["low"], c, b["volume"])
    dev = (c - vw).rolling(z_n, min_periods=z_n // 4).std()
    zz = (c - vw) / dev.replace(0, np.nan)
    return _side(_cross_up(zz, -z), _cross_dn(zz, z))


def t_momentum(b, f, n=12, atr_k=1.5, atr_n=14):
    """n-bar price change exceeds atr_k * ATR (impulse)."""
    c = b["close"]
    atr = ta.atr_(b["high"], b["low"], c, atr_n)
    mom = (c - c.shift(n)) / atr
    return _side(_cross_up(mom, atr_k), _cross_dn(mom, -atr_k))


def t_pullback(b, f, fast=20, slow=50):
    """In an EMA uptrend, close dips to/below the fast EMA then closes back
    above it (mirror for shorts)."""
    c = b["close"]
    ef, es = ta.ema(c, fast), ta.ema(c, slow)
    up = (ef > es).to_numpy()
    dn = (ef < es).to_numpy()
    return _side(_cross_up(c, ef) & up, _cross_dn(c, ef) & dn)


def t_range_break(b, f, range_n=24, hours=None):
    """Break of the previous range_n-bar range, optionally only in given UTC hours."""
    h, l, c = b["high"], b["low"], b["close"]
    hi_p = h.rolling(range_n, min_periods=range_n // 2).max().shift(1)
    lo_p = l.rolling(range_n, min_periods=range_n // 2).min().shift(1)
    s = _side(_cross_up(c, hi_p), _cross_dn(c, lo_p))
    if hours is not None:
        s = np.where(np.isin(b.index.hour, list(hours)), s, 0.0)
    return s


def t_funding_extreme(b, f, thresh=0.0003):
    """Funding rate crosses beyond +-thresh: fade the crowded side
    (high positive funding -> short, high negative -> long)."""
    rate = _funding_on_bars(b, f)
    return _side(_cross_dn(rate, -thresh), _cross_up(rate, thresh))


def t_failed_break(b, f, n=48, n_bars=8):
    """A break of the n-bar extreme that failed: price closed outside the
    previous n-bar range within the last n_bars bars and has closed back inside
    it again, so the breakout traders are trapped and must cover. Long when the
    failed break was to the downside, short when it was to the upside.

    The level that must be reclaimed is the DEEPEST one breached inside the
    window (`rolling(n_bars).min()` of the prior lows), so the signal only
    fires when price has recovered past the whole break sequence rather than
    brushing one bar's low. Only bars <= i are used.
    """
    h, l, c = b["high"], b["low"], b["close"]
    hi_p = h.rolling(n, min_periods=n // 2).max().shift(1)
    lo_p = l.rolling(n, min_periods=n // 2).min().shift(1)
    k = max(int(n_bars), 1)
    broke_dn = (c < lo_p).astype(float)
    broke_up = (c > hi_p).astype(float)
    # deepest level breached inside the window, and whether any breach happened
    lvl_dn = lo_p.rolling(k, min_periods=1).min()
    lvl_up = hi_p.rolling(k, min_periods=1).max()
    recent_dn = broke_dn.rolling(k, min_periods=1).max() > 0
    recent_up = broke_up.rolling(k, min_periods=1).max() > 0
    back_in_up = (c > lvl_dn) & recent_dn
    back_in_dn = (c < lvl_up) & recent_up
    return _side(back_in_up, back_in_dn)


def t_trend_state(b, f, n=200):
    """Regime state, fires on EVERY bar: long while close > EMA(n), short while
    below. For 'when to be in the market' ideas (PLAN.md Round 3): with
    direction long it re-enters whenever flat and the regime is up."""
    e = ta.ema(b["close"], n)
    c = b["close"]
    return _side((c > e).to_numpy(), (c < e).to_numpy())


def t_random(b, f, p=0.01, seed=0):
    """NULL MODEL, not a strategy: fires on each bar with probability p, long or
    short at random. Used by baseline.py to ask whether an idea's entries beat
    random timing with the same exits and filters."""
    # one 2-column draw so a truncated run reproduces the same prefix (causal)
    u = np.random.default_rng(int(seed)).random((len(b), 2))
    return np.where(u[:, 0] < p, np.where(u[:, 1] < 0.5, 1.0, -1.0), 0.0)


def _daily_extremes(b: pd.DataFrame, days: int):
    """High/low of the calendar day `days` before each bar's own day (UTC).

    The level is taken from a *completed* earlier day, never from the current
    one, so a bar can never see the extreme it is about to set.
    """
    day = b.index.floor("D")
    hi = b["high"].groupby(day).max()
    lo = b["low"].groupby(day).min()
    prev = day - pd.Timedelta(days=days)
    return hi.reindex(prev).to_numpy(float), lo.reindex(prev).to_numpy(float)


def t_prev_day_break(b, f, days=1):
    """Close breaks the high (long) or the low (short) of the previous UTC day.

    Yesterday's extreme is a level people actually use: stops sit just beyond
    it and breakout orders are queued at it, so a break is where both get
    triggered. Only completed previous days are used.
    """
    c = b["close"]
    hi_p, lo_p = _daily_extremes(b, int(days))
    return _side((c.to_numpy(float) > hi_p), (c.to_numpy(float) < lo_p))


def t_opening_range(b, f, mins=60, hour=0):
    """Close breaks the high (long) or low (short) of the first `mins` minutes
    of the given UTC hour of its own day.

    The daily open resets positioning: every day, leveraged traders and market
    makers rebuild their brackets around the 00:00 UTC print, and the first
    range is the agreed reference. The window must be COMPLETE before it can be
    used, so the trigger only fires on bars at or after the window closes.
    """
    day = b.index.floor("D")
    start = day + pd.Timedelta(hours=int(hour))
    in_win = (b.index - start) < pd.Timedelta(minutes=int(mins))
    win_hi = b["high"].where(in_win).groupby(day).max().reindex(day).to_numpy(float)
    win_lo = b["low"].where(in_win).groupby(day).min().reindex(day).to_numpy(float)
    closed = (b.index - start) >= pd.Timedelta(minutes=int(mins))
    ok = closed & np.isfinite(win_hi) & np.isfinite(win_lo)
    c = b["close"].to_numpy(float)
    up = np.where(ok, _cross_up(c, win_hi), 0.0)
    dn = np.where(ok, _cross_dn(c, win_lo), 0.0)
    # ONE signed array, like every other trigger. Returning a (long, short)
    # tuple here made recipe() read "either side fired" as LONG, so this block
    # traded long-only for all of Exp 022: 798 long trades, 0 short.
    return _side(up, dn)


def t_keltner_break(b, f, n=20, mult=2.0):
    """Close crosses outside an EMA(n) +- mult*ATR channel: a volatility
    channel break, which widens with volatility instead of lagging it like a
    Donchian, so it should produce fewer false breaks in quiet regimes."""
    c = b["close"]
    mid = ta.ema(c, int(n))
    band = float(mult) * ta.atr_(b["high"], b["low"], c, 14)
    return _side(_cross_up(c, mid + band), _cross_dn(c, mid - band))


def t_flush(b, f, k=2.0, m=1.5, lookback=96, mode="follow", atr_n=14):
    """A bar whose range exceeds k*ATR while volume exceeds m*its own average:
    a liquidation cascade. `mode` decides which side is the trade - "follow"
    takes the cascade's direction, "fade" takes the opposite one, because the
    two hypotheses are opposites and the data has to choose between them.
    The volume average is shifted one bar so it never contains this bar."""
    h, l, c = b["high"], b["low"], b["close"]
    atr = ta.atr_(h, l, c, int(atr_n))
    v = b["volume"]
    vma = v.rolling(int(lookback), min_periods=int(lookback) // 2).mean().shift(1)
    wide = (h - l) > float(k) * atr
    busy = v > float(m) * vma
    hit = wide & busy & np.isfinite(vma) & (atr > 0)
    o = b["open"]
    down = hit & (c < o)
    up = hit & (c > o)
    if mode == "follow":
        return _side(up, down)
    if mode == "fade":
        return _side(down, up)
    raise ValueError("flush mode must be 'follow' or 'fade'")


def t_month_turn_fade(b, f, before=2, after=2, lookback=6):
    """Fade the move that runs into a month boundary: on bars within `before`
    days before or `after` the first of a UTC month, take the side opposite to
    the `lookback`-bar move that got price there. Month-end and month-start are
    calendar events, not price events: risk budgets, index and mandate resets and
    benchmark rebalancing all push positions in one direction for a few days,
    and the flip into the new month is when those same mandates stop pushing,
    so part of the move is given back. Bars outside the window do not fire."""
    idx = b.index
    day = idx.day.to_numpy()
    # distance in days to the nearest month boundary, from the calendar alone:
    # days left until the 1st (inclusive), or days since this month's 1st.
    # Uses the real month length (Exp 025: `32 - day` treated every month as
    # 31 days, so February never fired before the turn).
    to_next = idx.days_in_month.to_numpy() + 1 - day
    to_prev = day - 1
    in_win = (to_next <= int(before)) | (to_prev <= int(after))
    c = b["close"].to_numpy(float)
    k = max(int(lookback), 1)
    ref = np.concatenate([np.full(k, np.nan), c[:-k]])
    moved = np.isfinite(ref) & (c != ref)
    up = moved & (c > ref)
    dn = moved & (c < ref)
    win = in_win
    return _side(np.where(win, dn, 0.0), np.where(win, up, 0.0))


# --------------------------------------------------------------------------
# TradingView port T2 (PLAN.md section 13), from the Pine source the owner
# supplied: "Smart Money Concepts [LuxAlgo]" (Pine v5), (c) LuxAlgo, licensed
# CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/).
# This translation of its structure logic is a derivative under the same
# licence: attribution LuxAlgo, non-commercial use only. Only the market
# structure part is ported (leg / getCurrentStructure / displayStructure);
# order blocks, fair value gaps (which use lookahead_on), equal highs/lows and
# MTF levels are drawing features and are not used as signals.
# --------------------------------------------------------------------------
def _smc_leg(h: np.ndarray, l: np.ndarray, size: int) -> np.ndarray:
    """Pine leg(size): 0 after high[size] > highest(size) (bearish leg),
    1 after low[size] < lowest(size) (bullish leg), else unchanged."""
    s = int(size)
    hi = pd.Series(h).rolling(s, min_periods=s).max().to_numpy()
    lo = pd.Series(l).rolling(s, min_periods=s).min().to_numpy()
    hs = np.r_[np.full(s, np.nan), h[:-s]]
    ls = np.r_[np.full(s, np.nan), l[:-s]]
    new_high = hs > hi
    new_low = (ls < lo) & ~new_high
    leg = np.zeros(len(h))
    cur = 0.0
    for i in range(len(h)):
        if new_high[i]:
            cur = 0.0
        elif new_low[i]:
            cur = 1.0
        leg[i] = cur
    return leg


def _pine_ne(a: float, b: float) -> bool:
    """Pine `a != b`: false when either side is na (Python's nan != x is True)."""
    return bool(np.isfinite(a) and np.isfinite(b) and a != b)


def smc_structure(b: pd.DataFrame, swing_len: int = 50, internal_len: int = 5) -> dict:
    """LuxAlgo SMC market structure, bar by bar in the script's order:
    getCurrentStructure(swing), getCurrentStructure(internal),
    displayStructure(internal), displayStructure(swing).
    Returns boolean arrays '<swing|internal>_<bull|bear>_<bos|choch>'.
    Defaults are the script's: swing length 50, internal size 5, confluence
    filter off. A pivot is only known `size` bars after it, as in Pine."""
    h = b["high"].to_numpy(float)
    l = b["low"].to_numpy(float)
    c = b["close"].to_numpy(float)
    n = len(c)
    legs = {"swing": _smc_leg(h, l, swing_len), "internal": _smc_leg(h, l, internal_len)}
    sizes = {"swing": int(swing_len), "internal": int(internal_len)}
    lvl = {(k, s): np.nan for k in ("swing", "internal") for s in ("high", "low")}
    crossed = {key: False for key in lvl}
    prev_lvl = dict(lvl)
    bias = {"swing": 0, "internal": 0}
    out = {f"{k}_{d}_{e}": np.zeros(n, bool) for k in ("swing", "internal")
           for d in ("bull", "bear") for e in ("bos", "choch")}
    for i in range(n):
        # getCurrentStructure: a leg change confirms a pivot `size` bars back
        for k in ("swing", "internal"):
            if i >= 1:
                ch = legs[k][i] - legs[k][i - 1]
                s = sizes[k]
                if ch == 1 and i - s >= 0:      # start of bullish leg -> pivot low
                    lvl[(k, "low")] = l[i - s]
                    crossed[(k, "low")] = False
                elif ch == -1 and i - s >= 0:   # start of bearish leg -> pivot high
                    lvl[(k, "high")] = h[i - s]
                    crossed[(k, "high")] = False
        # displayStructure: internal first, then swing
        for k in ("internal", "swing"):
            hk, lk = (k, "high"), (k, "low")
            up_x = (i >= 1 and c[i] > lvl[hk] and c[i - 1] <= prev_lvl[hk])
            extra_up = True if k == "swing" else _pine_ne(lvl[hk], lvl[("swing", "high")])
            if up_x and not crossed[hk] and extra_up:
                ev = "choch" if bias[k] == -1 else "bos"
                out[f"{k}_bull_{ev}"][i] = True
                crossed[hk] = True
                bias[k] = 1
            dn_x = (i >= 1 and c[i] < lvl[lk] and c[i - 1] >= prev_lvl[lk])
            extra_dn = True if k == "swing" else _pine_ne(lvl[lk], lvl[("swing", "low")])
            if dn_x and not crossed[lk] and extra_dn:
                ev = "choch" if bias[k] == 1 else "bos"
                out[f"{k}_bear_{ev}"][i] = True
                crossed[lk] = True
                bias[k] = -1
        prev_lvl = dict(lvl)
    return out


def t_smc_structure(b, f, structure="swing", event="choch", swing_len=50, internal_len=5):
    """LuxAlgo Smart Money Concepts (TradingView, CC BY-NC-SA 4.0): a
    structure break from the script's own alert conditions. Long on a bullish
    `event` (bos / choch / any) of the `structure` (swing / internal), short on
    a bearish one. The script is an indicator; its alerts are the entries."""
    s = smc_structure(b, swing_len, internal_len)
    ev = ("bos", "choch") if event == "any" else (str(event),)
    up = np.zeros(len(b), bool)
    dn = np.zeros(len(b), bool)
    for e in ev:
        up |= s[f"{structure}_bull_{e}"]
        dn |= s[f"{structure}_bear_{e}"]
    return _side(up, dn)


def t_chartart_macd_sma(b, f, fast=12, slow=26, signal=9, veryslow=200):
    """TradingView port T3 (PLAN.md section 13), from the Pine source the owner
    supplied: "MACD + SMA 200 Strategy (by ChartArt)" v1.0. The MACD here is
    built from SIMPLE moving averages, as in the script: fastMA = SMA(close,
    fast), slowMA = SMA(close, slow), macd = fastMA - slowMA, signal =
    SMA(macd, signal), hist = macd - signal. Long when hist crosses above 0,
    macd > 0, fastMA > slowMA and close[slow] > SMA(close, veryslow); short on
    the mirror image."""
    c = b["close"]
    fma = c.rolling(int(fast), min_periods=int(fast)).mean()
    sma_ = c.rolling(int(slow), min_periods=int(slow)).mean()
    vsma = c.rolling(int(veryslow), min_periods=int(veryslow)).mean()
    macd = fma - sma_
    hist = macd - macd.rolling(int(signal), min_periods=int(signal)).mean()
    lag = c.shift(int(slow))                # close[slowLength]
    up = _cross_up(hist, 0.0) & (macd > 0).to_numpy() & (fma > sma_).to_numpy() \
        & (lag > vsma).to_numpy()
    dn = _cross_dn(hist, 0.0) & (macd < 0).to_numpy() & (fma < sma_).to_numpy() \
        & (lag < vsma).to_numpy()
    return _side(up, dn)


def _wma(x: pd.Series, n: int) -> pd.Series:
    """Pine ta.wma: linear weights n (newest) .. 1 (oldest), divided by their sum."""
    n = int(n)
    w = np.arange(n, 0, -1, dtype=float)          # weight of x[t-k] is n-k
    v = x.to_numpy(float)
    num = np.convolve(v, w, mode="full")[: len(v)]
    num[: n - 1] = np.nan
    return pd.Series(num / w.sum(), index=x.index)


def t_super_scalper(b, f, atr_len=14, mult=1.0, rsi_fast=25, rsi_slow=100):
    """TradingView port T4 (PLAN.md section 13), from the Pine v5 source the
    owner supplied: "Super Scalper - 5 Min 15 Min". Default ATR smoothing
    'WMA': band = WMA(true range, atr_len) * mult around the close. Long when
    open < close - band (a bar that rose more than the band) and RSI(rsi_fast)
    > RSI(rsi_slow); short when open > close + band and RSI(rsi_fast) <
    RSI(rsi_slow). The script's EMA 21/65 'golden cross' is only plotted, not
    traded, so it is not part of the signal."""
    o, c = b["open"], b["close"]
    band = _wma(ta.true_range(b["high"], b["low"], c), atr_len) * float(mult)
    fast, slow = ta.rsi(c, int(rsi_fast)), ta.rsi(c, int(rsi_slow))
    up = ((o < c - band) & (fast > slow)).to_numpy()
    dn = ((o > c + band) & (fast < slow)).to_numpy()
    return _side(up, dn)


TRIGGERS = {
    "ema_cross": t_ema_cross,
    "donchian_break": t_donchian_break,
    "supertrend_flip": t_supertrend_flip,
    "rsi_revert": t_rsi_revert,
    "bb_revert": t_bb_revert,
    "zscore_revert": t_zscore_revert,
    "vwap_revert": t_vwap_revert,
    "momentum": t_momentum,
    "pullback": t_pullback,
    "range_break": t_range_break,
    "funding_extreme": t_funding_extreme,
    "failed_break": t_failed_break,
    "trend_state": t_trend_state,
    "random": t_random,
    "prev_day_break": t_prev_day_break,
    "opening_range": t_opening_range,
    "keltner_break": t_keltner_break,
    "flush": t_flush,
    "month_turn_fade": t_month_turn_fade,
    "smc_structure": t_smc_structure,
    "chartart_macd_sma": t_chartart_macd_sma,
    "super_scalper": t_super_scalper,
}


# ==========================================================================
# FILTERS  fn(bars, funding, **p) -> (long_ok, short_ok) boolean arrays
# ==========================================================================
def _both(mask) -> tuple[np.ndarray, np.ndarray]:
    m = np.nan_to_num(np.asarray(mask, dtype=float)) > 0
    return m, m


def f_trend_ema(b, f, fast=50, slow=200):
    """Trade with the trend: long only if EMA(fast) > EMA(slow), short only if below."""
    ef, es = ta.ema(b["close"], fast), ta.ema(b["close"], slow)
    return (ef > es).to_numpy(), (ef < es).to_numpy()


def f_price_vs_ema(b, f, n=200):
    """Long only above EMA(n), short only below."""
    e = ta.ema(b["close"], n)
    return (b["close"] > e).to_numpy(), (b["close"] < e).to_numpy()


def f_htf_trend(b, f, n=50, mult=4):
    """Higher-timeframe trend proxy: close vs EMA(n*mult). mult=4 on 15m ~ EMA(n) on 1h."""
    e = ta.ema(b["close"], int(n * mult))
    return (b["close"] > e).to_numpy(), (b["close"] < e).to_numpy()


def f_adx_min(b, f, n=14, min=20):  # noqa: A002 - JSON key
    """Trending regime only: ADX >= min."""
    a = ta.adx(b["high"], b["low"], b["close"], n)["adx"]
    return _both(a >= min)


def f_adx_max(b, f, n=14, max=20):  # noqa: A002 - JSON key
    """Ranging regime only: ADX <= max (use with mean-reversion triggers)."""
    a = ta.adx(b["high"], b["low"], b["close"], n)["adx"]
    return _both(a <= max)


def f_di_side(b, f, n=14):
    """Long only if +DI > -DI, short only if -DI > +DI."""
    a = ta.adx(b["high"], b["low"], b["close"], n)
    return (a["pdi"] > a["mdi"]).to_numpy(), (a["mdi"] > a["pdi"]).to_numpy()


def f_rsi_side(b, f, n=14, level=50):
    """Long only if RSI > level, short only if RSI < 100-level."""
    r = ta.rsi(b["close"], n)
    return (r > level).to_numpy(), (r < 100 - level).to_numpy()


def f_vol_regime(b, f, fast=14, slow=100, lo=0.0, hi=99.0):
    """Only when ATR(fast)/ATR(slow) is within [lo, hi]. hi<1 = quiet market,
    lo>1 = expanding volatility."""
    h, l, c = b["high"], b["low"], b["close"]
    ratio = ta.atr_(h, l, c, fast) / ta.atr_(h, l, c, slow)
    return _both((ratio >= lo) & (ratio <= hi))


def f_squeeze(b, f, n=20, q=0.2, lookback=500):
    """Bollinger width was in its lowest q quantile on the previous bar (compression)."""
    w = ta.bbands(b["close"], n, 2.0)["width"]
    qq = ta.rolling_quantile(w, lookback, q)
    return _both((w <= qq).shift(1, fill_value=False))


def f_taker_flow(b, f, n=20, thresh=0.52):
    """Aggressive buyers dominate for longs (taker buy ratio > thresh), sellers for shorts."""
    r = ta.taker_ratio(b["taker_buy_base"], b["volume"], n)
    return (r > thresh).to_numpy(), (r < 1 - thresh).to_numpy()


def f_vwap_side(b, f):
    """Long only above the daily VWAP, short only below."""
    c = b["close"]
    vw = ta.session_vwap(b["high"], b["low"], c, b["volume"])
    return (c > vw).to_numpy(), (c < vw).to_numpy()


def f_funding_window(b, f, hours=2):
    """Allow a direction only within `hours` of a funding settlement (00/08/16
    UTC): positions are opened and closed around funding times, and the flow
    around them is not the flow in between. The settlement CLOCK is Binance's
    published 8-hour grid, not a value read from the data, so deriving it from
    each bar's own timestamp keeps the block causal (a truncated series sees
    the same grid as the full one) and no rate is read before it is published."""
    step = 8 * 3600 * 10**9
    tol = int(float(hours)) * 3600 * 10**9
    t = np.asarray(b.index.to_numpy(), dtype="datetime64[ns]").astype("int64")
    g = (t // step) * step                      # most recent 00/08/16 UTC
    near = ((t - g) <= tol) | ((g + step - t) <= tol)
    return near, near


def f_volume_spike(b, f, n=96, k=1.5):
    """Volume on the signal bar > k * its n-bar average (participation)."""
    v = b["volume"]
    return _both(v > k * v.rolling(n, min_periods=n // 2).mean().shift(1))


def f_funding_not_crowded(b, f, thresh=0.0003):
    """Avoid joining a crowded side: no longs when funding > thresh,
    no shorts when funding < -thresh."""
    rate = _funding_on_bars(b, f)
    return (rate <= thresh).to_numpy(), (rate >= -thresh).to_numpy()


def f_hours(b, f, hours=(13, 14, 15, 16)):
    """Only in these UTC hours of the signal bar."""
    return _both(np.isin(b.index.hour, list(hours)))


def f_weekdays(b, f, days=(0, 1, 2, 3, 4)):
    """Only on these weekdays (0 = Monday)."""
    return _both(np.isin(b.index.dayofweek, list(days)))


FILTERS = {
    "trend_ema": f_trend_ema,
    "price_vs_ema": f_price_vs_ema,
    "htf_trend": f_htf_trend,
    "adx_min": f_adx_min,
    "adx_max": f_adx_max,
    "di_side": f_di_side,
    "rsi_side": f_rsi_side,
    "vol_regime": f_vol_regime,
    "squeeze": f_squeeze,
    "taker_flow": f_taker_flow,
    "vwap_side": f_vwap_side,
    "funding_window": f_funding_window,
    "volume_spike": f_volume_spike,
    "funding_not_crowded": f_funding_not_crowded,
    "hours": f_hours,
    "weekdays": f_weekdays,
}

NEEDS_FUNDING_BLOCKS = {"funding_extreme", "funding_not_crowded"}


def _funding_on_bars(b: pd.DataFrame, f: pd.DataFrame | None) -> pd.Series:
    if f is None:
        raise ValueError("this block needs funding data (run datafeed.py)")
    s = f.set_index(pd.to_datetime(f["calc_time"], utc=True))["last_funding_rate"]
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.reindex(b.index, method="ffill")


def _block(spec: dict, table: dict, kind: str):
    spec = dict(spec)
    name = spec.pop("type", None)
    if name not in table:
        raise ValueError(f"unknown {kind} {name!r}; available: {', '.join(sorted(table))}")
    return table[name], spec


def check_trigger_output(name: str, out, n: int) -> np.ndarray:
    """A trigger must return ONE array of length n with values in {-1, 0, +1}.

    A (long, short) tuple used to be stacked by np.asarray into a (2, n)
    array and read as "either side fired" = LONG: opening_range traded
    long-only through all of Exp 022 that way (Exp 024). Refuse it loudly."""
    if isinstance(out, tuple):
        raise TypeError(f"trigger {name!r} returned a tuple; a trigger returns ONE signed "
                        f"array (+1 long, -1 short, 0 none) - use _side(long, short)")
    arr = np.nan_to_num(np.asarray(out, dtype=float))
    if arr.shape != (n,):
        raise TypeError(f"trigger {name!r} returned shape {arr.shape}, expected ({n},)")
    if not np.isin(arr, (-1.0, 0.0, 1.0)).all():
        raise TypeError(f"trigger {name!r} returned values other than -1/0/+1")
    return arr


def check_filter_output(name: str, out, n: int) -> tuple[np.ndarray, np.ndarray]:
    """A filter must return (long_ok, short_ok): two arrays of length n."""
    if not (isinstance(out, tuple) and len(out) == 2):
        raise TypeError(f"filter {name!r} must return (long_ok, short_ok)")
    lo, sh = (np.nan_to_num(np.asarray(x, dtype=float)) for x in out)
    if lo.shape != (n,) or sh.shape != (n,):
        raise TypeError(f"filter {name!r} returned shapes {lo.shape}/{sh.shape}, expected ({n},)")
    return lo, sh


def _bar_minutes(index: pd.DatetimeIndex) -> float:
    return float(pd.Series(index[:1000]).diff().dt.total_seconds().median() / 60.0)


# ==========================================================================
# The strategy
# ==========================================================================
def recipe(bars: pd.DataFrame, funding: pd.DataFrame | None = None, *,
           triggers: list[dict], filters: list[dict] | None = None,
           trigger_mode: str = "any", confirm_bars: int = 3,
           direction: str = "both",
           stop: dict | None = None, tp: dict | None = None,
           be_at: float = 0.0, trail_at: float = 0.0, trail_atr: float = 0.0,
           max_hold_hours: float = 4.0, cooldown_bars: int = 0,
           atr_n: int = 14) -> pd.DataFrame:
    """Build a signal frame from a JSON-style recipe. See the module docstring."""
    n = len(bars)
    if not triggers:
        raise ValueError("a recipe needs at least one trigger")

    # 1. triggers
    sides = []
    for t in triggers:
        fn, p = _block(t, TRIGGERS, "trigger")
        sides.append(check_trigger_output(t.get("type"), fn(bars, funding, **p), n))
    S = np.vstack(sides)
    if trigger_mode == "any":
        up, dn = (S > 0).any(axis=0), (S < 0).any(axis=0)
        side = np.where(up & ~dn, 1.0, np.where(dn & ~up, -1.0, 0.0))
    elif trigger_mode == "all":
        # every trigger fired in the same direction within the last confirm_bars
        k = max(int(confirm_bars), 1)
        recent_up = np.vstack([pd.Series(s > 0).rolling(k, min_periods=1).max().to_numpy()
                               for s in S]).all(axis=0)
        recent_dn = np.vstack([pd.Series(s < 0).rolling(k, min_periods=1).max().to_numpy()
                               for s in S]).all(axis=0)
        fired = (S != 0).any(axis=0)  # act on the bar the last one arrives
        side = np.where(fired & recent_up & ~recent_dn, 1.0,
                        np.where(fired & recent_dn & ~recent_up, -1.0, 0.0))
    else:
        raise ValueError("trigger_mode must be 'any' or 'all'")

    # 2. filters
    long_ok = np.ones(n, bool)
    short_ok = np.ones(n, bool)
    for flt in filters or []:
        fn, p = _block(flt, FILTERS, "filter")
        lo, sh = check_filter_output(flt.get("type"), fn(bars, funding, **p), n)
        long_ok &= lo > 0
        short_ok &= sh > 0
    side = np.where((side > 0) & long_ok, 1.0, np.where((side < 0) & short_ok, -1.0, 0.0))

    # 3. direction
    if direction == "long":
        side = np.where(side > 0, side, 0.0)
    elif direction == "short":
        side = np.where(side < 0, side, 0.0)
    elif direction != "both":
        raise ValueError("direction must be 'both', 'long' or 'short'")

    # 4. cooldown
    if cooldown_bars > 0:
        last = -10**9
        for i in np.flatnonzero(side):
            if i - last <= cooldown_bars:
                side[i] = 0.0
            else:
                last = i

    # 5. exits
    h, l, c = bars["high"], bars["low"], bars["close"]
    atr = ta.atr_(h, l, c, atr_n).to_numpy(float)
    stop = stop or {"type": "atr", "mult": 2.0}
    stype = stop.get("type", "atr")
    if stype == "atr":
        stop_dist = stop.get("mult", 2.0) * atr
    elif stype == "pct":
        # Stop width is a fixed FRACTION OF PRICE, not a multiple of ATR, so
        # cost_r = round_trip_cost / stop_pct stays constant across volatility
        # regimes. An ATR-multiple stop silently narrows in calm markets and
        # widens in violent ones: on BTCUSDT 15m the same 3.0x ATR was 1.28%
        # of price in 2020-2022 but only 0.78% in 2023-2024, which moved cost_r
        # from 0.109 to 0.179 and turned a +0.155 R gross edge negative
        # (journal Exp 012). The ATR clamp is only a sanity bound: it lets a
        # genuinely explosive bar widen the stop instead of placing it inside
        # the noise, but it never narrows the stop below `pct`.
        cc = c.to_numpy(float)
        raw = stop.get("pct", 0.015) * cc
        stop_dist = np.clip(raw, stop.get("min_atr", 0.0) * atr, stop.get("max_atr", 1e9) * atr)
    elif stype == "swing":
        # beyond the recent swing low (long) / high (short), plus an ATR buffer,
        # clamped to [min_atr, max_atr] ATR so one bar cannot make it absurd
        sn = int(stop.get("n", 10))
        buf = stop.get("buffer_atr", 0.2)
        lo_n = l.rolling(sn, min_periods=1).min().to_numpy(float)
        hi_n = h.rolling(sn, min_periods=1).max().to_numpy(float)
        cc = c.to_numpy(float)
        raw = np.where(side > 0, cc - lo_n, hi_n - cc) + buf * atr
        stop_dist = np.clip(raw, stop.get("min_atr", 1.0) * atr, stop.get("max_atr", 6.0) * atr)
    else:
        raise ValueError("stop.type must be 'atr', 'pct' or 'swing'")

    tp = tp or {"type": "none"}
    tpt = tp.get("type", "none")
    if tpt == "none":
        tp_dist = np.zeros(n)
    elif tpt == "atr":
        tp_dist = tp.get("mult", 3.0) * atr
    elif tpt == "r":
        tp_dist = tp.get("r", 2.0) * stop_dist
    else:
        raise ValueError("tp.type must be 'none', 'atr' or 'r'")

    max_hold = max(1, int(round(max_hold_hours * 60.0 / _bar_minutes(bars.index))))

    ok = np.isfinite(atr) & (atr > 0) & np.isfinite(stop_dist) & (stop_dist > 0)
    side = np.where(ok, side, 0.0)
    active = side != 0
    out = pd.DataFrame(index=bars.index)
    out["side"] = side
    out["stop_dist"] = np.where(active, stop_dist, np.nan)
    out["tp_dist"] = np.where(active, np.nan_to_num(tp_dist), 0.0)
    out["max_hold"] = np.where(active, float(max_hold), 0.0)
    out["atr"] = np.nan_to_num(atr, nan=0.0)  # every bar: the trail reads it in-position
    out["be_at"] = np.where(active, be_at, 0.0)
    out["trail_at"] = np.where(active, trail_at, 0.0)
    out["trail_atr"] = np.where(active, trail_atr, 0.0)
    return out


def describe() -> str:
    """Human-readable catalogue of every block (used by `evaluate.py --list`)."""
    lines = ["TRIGGERS (when to act):"]
    for k, fn in TRIGGERS.items():
        lines.append(f"  {k:<18} {(fn.__doc__ or '').strip().splitlines()[0]}")
    lines.append("\nFILTERS (whether a direction is allowed):")
    for k, fn in FILTERS.items():
        lines.append(f"  {k:<18} {(fn.__doc__ or '').strip().splitlines()[0]}")
    return "\n".join(lines)
