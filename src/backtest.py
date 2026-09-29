"""Event-driven backtester for BTCUSDT USDT-M futures intraday trades.

Design goals (deliberately conservative):

* Signals are computed on bar `i` (after it closes) and executed at the
  OPEN of bar `i+1`, so there is no look-ahead and no "fill at the close I
  just used to generate the signal".
* Market entry/exit => taker fee (0.05%). Stop and target fills additionally
  pay slippage against us.
* Intrabar ambiguity: if a single bar touches both stop and target we fill
  the STOP first (pessimistic). This is the single most common way intraday
  backtests lie to you.
* Funding is charged at real funding timestamps while a position is open.
  Long pays when the rate is positive, short receives it.
* Equity is marked to market every bar so max-drawdown and Sharpe see the
  intrabar path, not just the trade closes.
* No look-ahead in funding either: the funding rate applied at time t is the
  one published at t.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402


# --------------------------------------------------------------------------
# Result containers
# --------------------------------------------------------------------------
@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    side: int
    qty: float
    entry_px: float
    exit_px: float
    stop_px: float
    target_px: float
    bars: int
    gross_pnl: float
    fees: float
    funding: float
    net_pnl: float
    r_multiple: float
    equity_after: float
    exit_reason: str
    # Everything the exchange and the market took, expressed in R.
    # This is the number that decides whether an intraday strategy is viable.
    cost_r: float = 0.0
    gross_r: float = 0.0


@dataclass
class BacktestResult:
    metrics: dict
    trades: list[Trade] = field(default_factory=list)
    equity: pd.Series | None = None
    equity_bars: pd.Series | None = None
    params: dict = field(default_factory=dict)
    name: str = ""

    def to_trades_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        d = [t.__dict__ for t in self.trades]
        df = pd.DataFrame(d)
        df["cum_r"] = df["r_multiple"].cumsum()
        return df


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _atr_fallback(df: pd.DataFrame, n: int = 14) -> np.ndarray:
    """Causal ATR computed from the bars, used when the caller did not supply
    an `atr` column."""
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean().to_numpy(float)


def _floor_step(x: float, step: float) -> float:
    return math.floor(x / step) * step if x > 0 else 0.0


def _session_mask(times: np.ndarray, start_h: int, end_h: int) -> np.ndarray:
    h = pd.DatetimeIndex(times).hour.to_numpy()
    if start_h == 0 and end_h >= 24:
        return np.ones(len(h), dtype=bool)
    if end_h > start_h:
        return (h >= start_h) & (h < end_h)
    # session wraps midnight
    return (h >= start_h) | (h < end_h)


def _align_funding(funding: pd.DataFrame | None, times: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (fund_time_ns, rate) arrays; empty if unavailable."""
    if funding is None or len(funding) == 0:
        return np.zeros(0, dtype="datetime64[ns]"), np.zeros(0)
    t = pd.DatetimeIndex(funding["calc_time"]).to_numpy("datetime64[ns]")
    r = funding["last_funding_rate"].to_numpy(dtype=float)
    order = np.argsort(t)
    return t[order], r[order]


# --------------------------------------------------------------------------
# Core backtest
# --------------------------------------------------------------------------
def run_backtest(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    initial_equity: float = C.INITIAL_EQUITY,
    risk_per_trade: float = C.RISK_PER_TRADE,
    max_leverage: float = C.MAX_LEVERAGE,
    fee_taker: float = C.FEE_TAKER,
    fee_maker: float = C.FEE_MAKER,
    slippage: float = C.SLIPPAGE,
    qty_step: float = C.QTY_STEP,
    min_notional: float = C.MIN_NOTIONAL,
    max_hold_cap: int = 100000,
    session_start: int = C.SESSION_START_HOUR,
    session_end: int = C.SESSION_END_HOUR,
    flat_at_session_end: bool = C.FLAT_AT_SESSION_END,
    pessimistic_intrabar: bool = C.PESSIMISTIC_INTRABAR,
    entry_mode: str = "taker",
    entry_offset_atr: float = 0.0,
    entry_fill_ratio: float = 1.0,
    funding: pd.DataFrame | None = None,
    start_time: pd.Timestamp | None = None,
    end_time: pd.Timestamp | None = None,
    name: str = "",
    params: dict | None = None,
) -> BacktestResult:
    """bars: index=DatetimeIndex, cols open/high/low/close/volume(+aux)
    signals: index aligned with bars, cols:
        side      (+1/-1/0) desired direction for the NEXT bar open
        stop_dist stop distance in price (required when side != 0)
        tp_dist   take-profit distance in price (0 = none)
        max_hold  max bars to hold (required when side != 0)
    """
    df = bars
    if start_time is not None:
        df = df[df.index >= start_time]
        signals = signals[signals.index >= start_time]
    if end_time is not None:
        df = df[df.index < end_time]
        signals = signals[signals.index < end_time]

    n = len(df)
    if n < 10:
        return BacktestResult(metrics=_empty_metrics(n), name=name, params=params or {})

    # ---- hot-loop prep -----------------------------------------------------
    # Python list indexing is ~5-10x faster than numpy scalar indexing, and this
    # loop runs once per bar, so convert everything up front.
    o = df["open"].to_numpy(float).tolist()
    h = df["high"].to_numpy(float).tolist()
    l = df["low"].to_numpy(float).tolist()
    c = df["close"].to_numpy(float).tolist()
    times = df.index.to_numpy("datetime64[ns]")

    side_a = signals["side"].to_numpy(float)
    stop_a = signals["stop_dist"].to_numpy(float)
    tp_a = signals["tp_dist"].to_numpy(float) if "tp_dist" in signals else np.zeros(n)
    hold_a = signals["max_hold"].to_numpy(float) if "max_hold" in signals else np.full(n, 12.0)

    # Optional exit-management columns. Absent => pure fixed stop/target.
    #   be_at      : move stop to break-even once unrealised >= this many R
    #   trail_at   : start an ATR trail once unrealised >= this many R
    #   trail_atr  : trail distance in ATR
    #   atr        : per-bar ATR in price, needed by the trail
    def _opt(name: str, fill: float) -> np.ndarray:
        return (signals[name].to_numpy(float) if name in signals
                else np.full(n, fill))

    be_a = _opt("be_at", 0.0)
    trail_at_a = _opt("trail_at", 0.0)
    trail_atr_a = _opt("trail_atr", 0.0)
    if "atr" in signals:
        atr_a = signals["atr"].to_numpy(float)
    else:
        # Fall back to an internally computed ATR. Without this the post-only
        # entry offset silently collapses to zero and every limit rests exactly
        # at the close, which quietly turns the experiment into the taker case.
        atr_a = _atr_fallback(df, 14)
    use_dyn = bool(np.any(be_a != 0) or np.any(trail_atr_a != 0))
    be_l = be_a.tolist()
    trail_at_l = trail_at_a.tolist()
    trail_atr_l = trail_atr_a.tolist()
    atr_l = atr_a.tolist()

    # ---------------- execution model -------------------------------------
    # "taker"     : market order at the next open, plus slippage. Default.
    # "post_only" : rest a limit order and hope. The limit is placed at the
    #              signal bar's close, offset into the market by
    #              entry_offset_atr. It fills only if the NEXT bar's range
    #              trades through it - which, by construction, means it fills
    #              when the market is moving against the entry. That adverse
    #              selection is the whole reason maker fills are not free, and
    #              this model reproduces it instead of assuming it away.
    entry_mode = str(entry_mode)
    if entry_mode not in ("taker", "post_only"):
        raise ValueError(f"unknown entry_mode {entry_mode!r}")
    fee_entry = fee_taker if entry_mode == "taker" else fee_maker
    slip_entry = slippage if entry_mode == "taker" else 0.0
    c_close = df["close"].to_numpy(float).tolist()

    # precompute validity instead of calling np.isfinite per bar
    sig_ok = np.isfinite(stop_a) & (stop_a > 0) & (hold_a > 0) & (side_a != 0)
    side_s = side_a.astype(np.int8).tolist()
    stop_s = stop_a.tolist()
    tp_s = tp_a.tolist()
    mh_s = np.minimum(hold_a.astype(np.int64), max_hold_cap).tolist()
    sig_ok = sig_ok.tolist()

    in_sess_a = _session_mask(times, session_start, session_end)
    # Distance (in bars) to the next session boundary. The final segment has
    # no boundary inside the data, so treat it as open: otherwise every
    # backtest window would silently refuse to open trades near its own end
    # (a real bias, and one that shows up in every walk-forward fold).
    sess_change = np.r_[in_sess_a[1:] != in_sess_a[:-1], False]
    dist_to_end_a = np.zeros(n, dtype=np.int64)
    run = 0
    for i in range(n - 1, -1, -1):
        if sess_change[i]:
            run = 0
        else:
            run += 1
        dist_to_end_a[i] = run
    trailing = ~sess_change[n - 1:]
    # walk back and mark the whole trailing run as unbounded
    j = n - 1
    while j >= 0 and not sess_change[j]:
        dist_to_end_a[j] = n
        j -= 1
    del trailing
    last_of_seg_a = dist_to_end_a == 0
    in_sess = in_sess_a.tolist()
    dist_to_end = dist_to_end_a.tolist()
    last_of_seg = last_of_seg_a.tolist()

    ft, fr = _align_funding(funding, times)
    # Precompute, for every bar, how many funding events fall inside it. The
    # pointer only ever moves forward, so this removes the inner while-loop.
    if len(ft):
        bar_end = np.empty(n, dtype="datetime64[ns]")
        bar_end[:-1] = times[1:]
        step = np.timedelta64(int(_median_secs(df.index)), "s")
        bar_end[-1] = times[-1] + step
        f_end = np.searchsorted(ft, bar_end, side="left")
    else:
        f_end = np.zeros(n, dtype=np.int64)
    f_end_l = f_end.tolist()
    fr_l = fr.tolist()
    n_ft = len(ft)
    # Keep the DatetimeIndex object and pull Timestamps out lazily. Materialising
    # a list of 3.5M Timestamps costs ~4s and ~1GB on the 1m series, for two
    # lookups per trade.
    idx_obj = df.index
    fi = 0  # pointer into funding arrays

    cash = initial_equity
    pos_side = 0
    pos_qty = 0.0
    pos_entry = 0.0
    pos_stop = 0.0
    pos_tp = 0.0
    pos_entry_i = 0
    pos_fees = 0.0
    pos_funding = 0.0
    pos_mh = 0
    pos_risk = 0.0
    pos_r_unit = 0.0
    pos_be = 0.0
    pos_trail_at = 0.0
    pos_trail_atr = 0.0

    eq_curve = np.empty(n, dtype=float)
    trades: list[Trade] = []
    total_fees = 0.0
    total_funding = 0.0
    exposure_bars = 0
    entry_signals = 0   # signals that reached the entry decision
    entry_fills = 0     # of those, the ones that actually got filled
    size_skips = 0      # filled signals too small to trade (qty step / min notional)

    def close_position(i: int, px: float, reason: str) -> None:
        nonlocal cash, pos_side, pos_qty, pos_fees, pos_funding
        nonlocal total_fees, pos_entry, pos_mh
        px_adj = px * (1.0 - slippage) if pos_side > 0 else px * (1.0 + slippage)
        # The fee is charged on the price we actually traded at, i.e. after
        # slippage - same as the entry side does.
        fee = pos_qty * px_adj * fee_taker
        # Signed by side: a short gains when price falls. This line had no
        # pos_side until Exp 014 (Sep 2026), so every short's P&L was
        # inverted; test_engine section 9 now checks long/short symmetry.
        move = pos_qty * pos_side * (px_adj - pos_entry)
        cash += move - fee
        total_fees += fee
        # net MUST include the entry fee, otherwise sum(net_pnl) != equity
        # change and every expectancy/R statistic downstream is wrong.
        net = move - fee - pos_fees + pos_funding
        r = net / (pos_risk if pos_risk > 0 else 1.0)
        risk_u = pos_risk if pos_risk > 0 else 1.0
        # slippage drag: we cross the spread on entry and on exit
        slip_drag = pos_qty * slippage * (pos_entry + px_adj)
        cost_total = (pos_fees + fee) + slip_drag - pos_funding
        gross_r = (move + slip_drag) / risk_u
        trades.append(
            Trade(
                entry_time=idx_obj[pos_entry_i],
                exit_time=idx_obj[i],
                side=pos_side,
                qty=pos_qty,
                entry_px=pos_entry,
                exit_px=px_adj,
                stop_px=pos_stop,
                target_px=pos_tp,
                bars=i - pos_entry_i + 1,
                gross_pnl=move,
                fees=pos_fees + fee,
                funding=pos_funding,
                net_pnl=net,
                r_multiple=r,
                equity_after=cash,
                exit_reason=reason,
                cost_r=cost_total / risk_u,
                gross_r=gross_r,
            )
        )
        pos_side = 0
        pos_qty = 0.0
        pos_fees = 0.0
        pos_funding = 0.0

    _step = qty_step
    _msn = min_notional
    _lev = max_leverage
    _rpt = risk_per_trade
    _ftc = fee_taker
    _slip = slippage
    _slip_e = slippage if entry_mode == "taker" else 0.0
    fee_entry = fee_taker if entry_mode == "taker" else fee_maker
    _flat_end = flat_at_session_end
    _pess = pessimistic_intrabar

    for i in range(n):
        # ---------------- entry at this bar's open -------------------------
        if pos_side == 0 and i > 0:
            j = i - 1
            if sig_ok[j] and in_sess[i]:
                mh = mh_s[j]
                if not (_flat_end and dist_to_end[i] < mh):
                    want = side_s[j]
                    sd = stop_s[j]
                    if entry_mode == "taker":
                        entry = o[i] * (1.0 + _slip_e * want)
                        fill = True
                    else:
                        entry_signals += 1
                        # rest a limit at the signal close, pushed
                        # entry_offset_atr into the market
                        a_j = atr_l[j]
                        off = entry_offset_atr * a_j
                        if want > 0:
                            limit_px = c_close[j] - off
                            # fills only if the market trades down to it
                            fill = l[i] <= limit_px
                            entry = min(o[i], limit_px) if fill else 0.0
                        else:
                            limit_px = c_close[j] + off
                            fill = h[i] >= limit_px
                            entry = max(o[i], limit_px) if fill else 0.0
                    if fill and entry > 0:
                        entry_fills += 1
                        risk_cash = cash * _rpt
                        qty = _floor_step(
                            min(risk_cash / sd, (cash * _lev) / entry), _step)
                        if entry_mode == "post_only" and entry_fill_ratio != 1.0:
                            # Queue reality: you sit behind the resting book,
                            # so a touch does not guarantee your full size.
                            # The min-notional bump is deliberately NOT applied
                            # after this - you cannot coerce a bigger fill.
                            qty = _floor_step(qty * entry_fill_ratio, _step)
                        elif qty * entry < _msn:
                            qty = _floor_step(_msn / entry, _step)
                        if qty > 0 and qty * entry >= _msn:
                            fee = qty * entry * fee_entry
                            cash -= fee
                            total_fees += fee
                            tpd = tp_s[j]
                            pos_side = want
                            pos_qty = qty
                            pos_entry = entry
                            pos_entry_i = i
                            pos_risk = qty * sd
                            pos_stop = entry - want * sd
                            pos_tp = entry + want * tpd if tpd > 0 else 0.0
                            pos_fees = fee
                            pos_funding = 0.0
                            pos_mh = mh
                            pos_r_unit = sd
                            pos_be = be_l[j]
                            pos_trail_at = trail_at_l[j]
                            pos_trail_atr = trail_atr_l[j]
                            # skip funding events already behind us
                            while fi < n_ft and ft[fi] <= times[i]:
                                fi += 1
                            if cash <= 0:
                                # Account blown. Stop trading rather than
                                # sizing off a meaningless equity.
                                pos_side = 0
                                pos_qty = 0.0
                        else:
                            # Dust: the stop is too wide for this equity at the
                            # contract's qty step. Counted, because a skip that
                            # depends on equity silently truncates a losing run
                            # (Exp 014: 100 USDT could not size most 2024 trades).
                            size_skips += 1
                        # unfilled or dust - no position, no fee. The bar is
                        # still marked to market below, so this must NOT
                        # `continue` past the end of the loop body.

        # ---------------- manage open position -----------------------------
        if pos_side != 0:
            exposure_bars += 1
            fe = f_end_l[i]
            if fi < fe:
                sgn = 1.0 if pos_side > 0 else -1.0
                amt = pos_qty * sum(fr_l[fi:fe]) * sgn
                cash -= amt
                pos_funding -= amt
                total_funding += amt
                fi = fe

            hi, lo, op = h[i], l[i], o[i]

            # ---- dynamic exit management ("fixing the trade") -------------
            # Applied at the START of bar i using the PREVIOUS bar's close
            # (and ATR): a rule evaluated on bar i-1's close is only active
            # from bar i onward. An earlier version used c[i] here - the close
            # of the very bar whose high/low is then checked - which let a bar
            # that ran through the stop and closed higher exit at break-even
            # instead of -1R (look-ahead; journal Exp 011).
            # Not on the entry bar: there is no in-position close before it.
            if use_dyn and pos_r_unit > 0 and i > pos_entry_i:
                unreal_r = pos_side * (c[i - 1] - pos_entry) / pos_r_unit
                if pos_be > 0 and unreal_r >= pos_be:
                    # a true break-even stop must also cover the round-trip
                    # cost, otherwise "break-even" quietly loses money
                    if pos_side > 0:
                        be_px = pos_entry * (1.0 + _ftc + _slip)
                    else:
                        be_px = pos_entry * (1.0 - _ftc - _slip)
                    if pos_side > 0:
                        if be_px > pos_stop:
                            pos_stop = be_px
                    else:
                        if be_px < pos_stop:
                            pos_stop = be_px
                if pos_trail_atr > 0 and pos_trail_at > 0 and unreal_r >= pos_trail_at:
                    a_i = atr_l[i - 1]
                    if a_i > 0:
                        t_px = c[i - 1] - pos_side * pos_trail_atr * a_i
                        if pos_side > 0:
                            if t_px > pos_stop:
                                pos_stop = t_px
                        else:
                            if t_px < pos_stop:
                                pos_stop = t_px

            if pos_side > 0:
                stop_hit = lo <= pos_stop
                tp_hit = pos_tp > 0 and hi >= pos_tp
            else:
                stop_hit = hi >= pos_stop
                tp_hit = pos_tp > 0 and lo <= pos_tp

            if stop_hit:
                gap = (op < pos_stop) if pos_side > 0 else (op > pos_stop)
                close_position(i, op if gap else pos_stop, "stop")
            elif tp_hit:
                gap = (op > pos_tp) if pos_side > 0 else (op < pos_tp)
                close_position(i, op if gap else pos_tp, "target")
            elif i - pos_entry_i + 1 >= pos_mh:
                close_position(i, c[i], "time")
            elif _flat_end and last_of_seg[i]:
                close_position(i, c[i], "session")

        # ---------------- mark to market -----------------------------------
        eq_curve[i] = cash + pos_qty * pos_side * (c[i] - pos_entry) if pos_side != 0 else cash

    # close anything still open at the final bar
    if pos_side != 0:
        close_position(n - 1, c[n - 1], "eod")
        eq_curve[n - 1] = cash

    metrics = compute_metrics(
        eq_curve,
        trades,
        df.index,
        bars_per_year=int(C.MINUTES_PER_YEAR / max(1, _median_secs(df.index))),
        exposure_bars=exposure_bars,
        total_fees=total_fees,
        total_funding=total_funding,
        initial_equity=initial_equity,
    )
    metrics["entry_mode"] = entry_mode
    metrics["entry_signals"] = entry_signals
    metrics["entry_fills"] = entry_fills
    metrics["fill_rate"] = (entry_fills / entry_signals) if entry_signals else 1.0
    metrics["size_skips"] = size_skips
    return BacktestResult(
        metrics=metrics,
        trades=trades,
        equity=pd.Series(eq_curve, index=df.index, name="equity"),
        params=params or {},
        name=name,
    )


def _median_secs(index: pd.DatetimeIndex) -> float:
    if len(index) < 3:
        return 300.0
    d = np.diff(index.to_numpy("datetime64[s]").astype("int64"))
    return float(np.median(d)) if len(d) else 300.0


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------
def _empty_metrics(n: int) -> dict:
    m = {
        "bars": n, "trades": 0, "net_return": 0.0, "cagr": 0.0, "sharpe": 0.0,
        "sortino": 0.0, "max_dd": 0.0, "calmar": 0.0, "win_rate": 0.0,
        "profit_factor": 0.0, "expectancy_r": 0.0, "avg_r": 0.0, "best_r": 0.0,
        "worst_r": 0.0, "avg_bars": 0.0, "total_fees": 0.0, "total_funding": 0.0,
        "fees_pct_equity": 0.0, "exposure": 0.0, "final_equity": 0.0,
        "long_trades": 0, "short_trades": 0, "long_pnl": 0.0, "short_pnl": 0.0,
        "stop_rate": 0.0, "tp_rate": 0.0, "time_rate": 0.0, "max_dd_days": 0.0,
        "avg_cost_r": 0.0, "avg_gross_r": 0.0, "edge_r": 0.0,
        "entry_mode": "", "entry_signals": 0, "entry_fills": 0, "fill_rate": 0.0,
    }
    return m


def compute_metrics(
    eq: np.ndarray,
    trades: list[Trade],
    index: pd.DatetimeIndex,
    *,
    bars_per_year: int,
    exposure_bars: int,
    total_fees: float,
    total_funding: float,
    initial_equity: float,
) -> dict:
    m = _empty_metrics(len(eq))
    if len(eq) == 0:
        return m
    eq = np.asarray(eq, dtype=float)
    final = float(eq[-1])
    m["final_equity"] = final
    m["net_return"] = final / initial_equity - 1.0

    span_days = (index[-1] - index[0]).total_seconds() / 86400.0
    if span_days > 1:
        m["cagr"] = (final / initial_equity) ** (365.25 / span_days) - 1.0

    rets = np.diff(eq) / np.where(eq[:-1] == 0, np.nan, eq[:-1])
    rets = rets[np.isfinite(rets)]
    if len(rets) > 2 and rets.std() > 0:
        m["sharpe"] = float(rets.mean() / rets.std() * math.sqrt(bars_per_year))
        dn = rets[rets < 0]
        m["sortino"] = float(
            rets.mean() / (dn.std() if len(dn) > 2 and dn.std() > 0 else np.nan)
            * math.sqrt(bars_per_year)
        ) if len(dn) > 2 and dn.std() > 0 else 0.0

    peak = np.maximum.accumulate(eq)
    dd = 1.0 - eq / np.where(peak == 0, np.nan, peak)
    dd = np.nan_to_num(dd, nan=0.0)
    m["max_dd"] = float(dd.max()) if len(dd) else 0.0
    if m["max_dd"] > 0 and m["cagr"] > 0:
        m["calmar"] = m["cagr"] / m["max_dd"]

    # longest underwater stretch in days. Vectorised: this used to be a Python
    # loop over every bar, which is 3.5M iterations on the 1m series.
    if len(dd):
        under = (dd > 1e-9).astype(np.int8)
        # run-length of consecutive 1s
        grp = np.cumsum(np.concatenate(([0], under)))
        # bar i belongs to run grp[i]; a run id present in `under` is underwater
        starts = np.flatnonzero(np.diff(grp) != 0) + 1
        ends = np.append(starts, len(under))
        best_len = 0
        best_start = 0
        for s0, s1 in zip(starts, ends):
            if s1 - s0 > best_len and under[s0] == 1:
                best_len = int(s1 - s0)
                best_start = int(s0)
        if best_len > 1:
            d = (index[min(best_start + best_len, len(index) - 1)]
                 - index[best_start]).total_seconds() / 86400.0
            m["max_dd_days"] = float(d)

    m["trades"] = len(trades)
    m["total_fees"] = float(total_fees)
    m["total_funding"] = float(total_funding)
    m["fees_pct_equity"] = float(total_fees / max(initial_equity, 1e-9))
    m["exposure"] = float(exposure_bars / max(len(eq), 1))

    if trades:
        r = np.array([t.r_multiple for t in trades], dtype=float)
        net = np.array([t.net_pnl for t in trades], dtype=float)
        wins = r > 0
        m["win_rate"] = float(wins.mean())
        m["avg_r"] = float(r.mean())
        m["expectancy_r"] = m["avg_r"]
        m["best_r"] = float(r.max())
        m["worst_r"] = float(r.min())
        m["avg_bars"] = float(np.mean([t.bars for t in trades]))
        gp = float(net[net > 0].sum())
        gl = float(-net[net < 0].sum())
        m["profit_factor"] = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0.0)
        m["long_trades"] = int(sum(1 for t in trades if t.side > 0))
        m["short_trades"] = int(sum(1 for t in trades if t.side < 0))
        m["long_pnl"] = float(sum(t.net_pnl for t in trades if t.side > 0))
        m["short_pnl"] = float(sum(t.net_pnl for t in trades if t.side < 0))
        reasons = [t.exit_reason for t in trades]
        m["stop_rate"] = reasons.count("stop") / len(reasons)
        m["tp_rate"] = reasons.count("target") / len(reasons)
        m["time_rate"] = reasons.count("time") / len(reasons)
        m["avg_cost_r"] = float(np.mean([t.cost_r for t in trades]))
        m["avg_gross_r"] = float(np.mean([t.gross_r for t in trades]))
        m["edge_r"] = m["avg_gross_r"] - m["avg_cost_r"]
    return m


def fmt_metrics(m: dict) -> str:
    def p(x, d=2):
        if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
            return "  n/a"
        return f"{x:.{d}f}"

    return (
        f"ret={p(m['net_return']*100,2)}% cagr={p(m['cagr']*100,2)}% "
        f"sharpe={p(m['sharpe'])} sortino={p(m['sortino'])} "
        f"maxDD={p(m['max_dd']*100,2)}% calmar={p(m['calmar'])} "
        f"trades={m['trades']} win={p(m['win_rate']*100,1)}% "
        f"PF={p(m['profit_factor'])} expR={p(m['expectancy_r'],3)} "
        f"grossR={p(m['avg_gross_r'],3)} costR={p(m['avg_cost_r'],3)} "
        f"fees={p(m['total_fees'],2)}U({p(m['fees_pct_equity']*100,1)}%) "
        f"fund={p(m['total_funding'],2)}U expo={p(m['exposure']*100,1)}% "
        f"hold={p(m['avg_bars'],0)}bars final={p(m['final_equity'],2)}U"
    )
