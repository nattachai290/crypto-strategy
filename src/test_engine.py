"""Correctness tests for the backtester.

The optimised hot loop in backtest.py is the one piece of code where a subtle
bug would silently produce beautiful, wrong numbers. So we check it three ways:

1. A hand-computed trade: fixed prices, fixed stop, exact expected PnL/R.
2. A differential test against a deliberately naive reference implementation
   written independently in the obvious way. Random signals, many seeds - the
   trade lists must match exactly, bar for bar.
3. Cost sensitivity: adding fees/slippage must never increase PnL.

Run:  python src\\test_engine.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
from backtest import run_backtest

FAIL = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        FAIL.append(name)


# --------------------------------------------------------------------------
# Reference implementation - intentionally naive, written from the spec
# --------------------------------------------------------------------------
def reference_backtest(bars, signals, *, init=100.0, risk=0.01, lev=10.0,
                       fee=0.0005, slip=0.0002, qty_step=0.001, min_not=5.0,
                       funding=None):
    """Straightforward, slow, spec-literal version. Returns a list of dicts."""
    out = []
    cash = init
    pos = None
    n = len(bars)
    for i in range(1, n):
        o, h, l, c = (float(bars["open"].iloc[i]), float(bars["high"].iloc[i]),
                      float(bars["low"].iloc[i]), float(bars["close"].iloc[i]))
        if pos is None:
            side = float(signals["side"].iloc[i - 1])
            sd = float(signals["stop_dist"].iloc[i - 1])
            mh = int(signals["max_hold"].iloc[i - 1])
            tpd = float(signals["tp_dist"].iloc[i - 1])
            if side == 0 or not np.isfinite(sd) or sd <= 0 or mh <= 0:
                continue
            entry = o * (1 + slip * side)
            qty = min(cash * risk / sd, cash * lev / entry)
            qty = np.floor(qty / qty_step) * qty_step
            if qty * entry < min_not:
                qty = np.floor(min_not / entry) * 0 + np.floor((min_not / entry) / qty_step) * qty_step
            if qty <= 0:
                continue
            f = qty * entry * fee
            cash -= f
            pos = dict(side=side, qty=qty, entry=entry,
                       stop=entry - side * sd,
                       tp=(entry + side * tpd) if tpd > 0 else 0.0,
                       mh=mh, i0=i, fee_in=f, funding=0.0)
        # open position: charge funding in the open interval of the bar
        # NB: this also runs on the entry bar - you can be stopped out on the
        # very bar you entered, and pretending otherwise inflates results.
        if pos is not None and funding is not None and len(funding):
            t0 = bars.index[i]
            t1 = bars.index[i + 1] if i + 1 < n else t0 + pd.Timedelta(minutes=1)
            lo = t0 if i > pos["i0"] else t0 + pd.Timedelta(nanoseconds=1)
            sel = funding[(funding["calc_time"] > lo) & (funding["calc_time"] < t1)] \
                if i == pos["i0"] else \
                funding[(funding["calc_time"] >= t0) & (funding["calc_time"] < t1)]
            for rate in sel["last_funding_rate"].to_numpy():
                # notional x rate, at the open of the bar holding the
                # settlement (the spec; this line had the engine's Exp 030 bug)
                amt = pos["qty"] * o * float(rate) * (1.0 if pos["side"] > 0 else -1.0)
                cash -= amt
                pos["funding"] -= amt
        stop_hit = (l <= pos["stop"]) if pos["side"] > 0 else (h >= pos["stop"])
        tp_hit = False
        if pos["tp"] > 0:
            tp_hit = (h >= pos["tp"]) if pos["side"] > 0 else (l <= pos["tp"])
        reason = None
        px = None
        if stop_hit:
            gap = (o < pos["stop"]) if pos["side"] > 0 else (o > pos["stop"])
            px, reason = (o if gap else pos["stop"]), "stop"
        elif tp_hit:
            gap = (o > pos["tp"]) if pos["side"] > 0 else (o < pos["tp"])
            px, reason = (o if gap else pos["tp"]), "target"
        elif i - pos["i0"] + 1 >= pos["mh"]:
            px, reason = c, "time"
        if reason:
            px_adj = px * (1 - slip) if pos["side"] > 0 else px * (1 + slip)
            fee_x = pos["qty"] * px_adj * fee
            pnl = pos["qty"] * pos["side"] * (px_adj - pos["entry"]) - fee_x
            cash += pnl
            # R must include BOTH fees, matching backtest.py
            r = (pnl - pos["fee_in"] + pos["funding"]) / (
                pos["qty"] * abs(pos["entry"] - pos["stop"]))
            out.append(dict(exit_i=i, side=pos["side"], qty=round(pos["qty"], 9),
                            entry=round(pos["entry"], 6), exit=round(px_adj, 6),
                            reason=reason, bars=i - pos["i0"] + 1,
                            pnl=round(pnl, 8), funding=round(pos["funding"], 10),
                            r=round(r, 8)))
            pos = None
    if pos is not None:
        px = float(bars["close"].iloc[-1])
        px_adj = px * (1 - slip) if pos["side"] > 0 else px * (1 + slip)
        fee_x = pos["qty"] * px_adj * fee
        pnl = pos["qty"] * pos["side"] * (px_adj - pos["entry"]) - fee_x
        cash += pnl
        r = (pnl - pos["fee_in"] + pos["funding"]) / (
            pos["qty"] * abs(pos["entry"] - pos["stop"]))
        out.append(dict(exit_i=n - 1, side=pos["side"], qty=round(pos["qty"], 9),
                        entry=round(pos["entry"], 6), exit=round(px_adj, 6),
                        reason="eod", bars=n - 1 - pos["i0"] + 1, pnl=round(pnl, 8),
                        funding=round(pos["funding"], 10), r=round(r, 8)))
    return out


# --------------------------------------------------------------------------
# 1. Hand-computed trade
# --------------------------------------------------------------------------
def test_hand_computed() -> None:
    print("\n1. hand-computed single trade")
    # flat market that drifts down into the stop of a long
    px = 50000.0
    idx = pd.date_range("2024-01-01", periods=40, freq="5min", tz="UTC")
    rows = []
    for k in range(40):
        o = px
        h = px * 1.0005
        # a decisive break down through the stop on bars 3..5
        l = px * 0.99 if 3 <= k <= 5 else px * 0.9995
        c = px
        rows.append((o, h, max(l, 1.0), c))
        px *= 0.9999
    bars = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    bars["volume"] = 100.0
    bars["trades"] = 1000.0
    bars["taker_buy_base"] = 50.0
    bars["taker_buy_quote"] = 2.5e6

    sig = pd.DataFrame(0.0, index=idx, columns=["side", "stop_dist", "tp_dist", "max_hold"])
    sig.iloc[0, sig.columns.get_loc("side")] = 1.0
    sig.iloc[0, sig.columns.get_loc("stop_dist")] = 200.0
    sig.iloc[0, sig.columns.get_loc("max_hold")] = 20
    sig.iloc[0, sig.columns.get_loc("tp_dist")] = 0.0

    res = run_backtest(bars, sig, session_start=0, session_end=24,
                       flat_at_session_end=False)
    check("one trade generated", len(res.trades) == 1, f"got {len(res.trades)}")
    if not res.trades:
        return
    t = res.trades[0]

    slip, fee, risk = 0.0002, 0.0005, 0.01
    entry_expect = bars["open"].iloc[1] * (1 + slip)
    stop_expect = entry_expect - 200.0
    check("entry at next bar open + slippage", abs(t.entry_px - entry_expect) < 1e-6,
          f"{t.entry_px:.4f} vs {entry_expect:.4f}")
    check("exit reason is stop", t.exit_reason == "stop", t.exit_reason)
    check("stop level", abs(t.stop_px - stop_expect) < 1e-6)

    # qty: risk 1% of 100 = 1 USDT over a 200 USDT stop => 0.005 BTC
    qty_expect = np.floor((1.0 / 200.0) / 0.001) * 0.001
    check("qty from stop-based risk", abs(t.qty - qty_expect) < 1e-9,
          f"{t.qty} vs {qty_expect}")

    # exit fill: stop hit, price itself is not gapped
    exit_expect = stop_expect * (1 - slip)
    check("stop exit with adverse slippage", abs(t.exit_px - exit_expect) < 1e-4,
          f"{t.exit_px:.4f} vs {exit_expect:.4f}")

    # fees: entry notional + exit notional, both taker, both on the slipped price
    fee_expect = t.qty * (t.entry_px + t.exit_px) * fee
    check("both fees charged", abs(t.fees - fee_expect) < 1e-6,
          f"{t.fees:.6f} vs {fee_expect:.6f}")

    gross = t.qty * (t.exit_px - t.entry_px)
    check("gross pnl consistent", abs(t.gross_pnl - gross) < 1e-6)

    # Analytic R for a stopped-out long:
    #   gross = -(stop_dist + entry_slippage) / stop_dist
    #   fees  = (fee*entry + fee*exit) * qty / (qty*stop_dist)
    # gross = -(stop_dist + exit_slippage*stop_px) / stop_dist
    r_expect = (-(200.0 + slip * (t.entry_px - 200.0)) / 200.0) - fee_expect / (t.qty * 200.0)
    check("R matches the analytic value", abs(t.r_multiple - r_expect) < 1e-6,
          f"{t.r_multiple:.6f} vs {r_expect:.6f}")
    check("no funding charged", abs(t.funding) < 1e-12)


def test_funding_hand_computed() -> None:
    """Funding is position NOTIONAL x rate: qty x price x rate (ETH Exp 002).

    Until Exp 030 the engine charged qty x rate, missing the price, so funding
    was understated by the price (~40,000x on BTC). The price here is flat at
    50,000, so the funding price convention does not matter: one settlement
    at 0.01% on a 0.005 BTC position is exactly 0.005 * 50,000 * 0.0001 =
    0.025 USDT, paid by the long and received by the short."""
    print("\n1b. hand-computed funding (notional x rate)")
    px, rate = 50000.0, 0.0001
    idx = pd.date_range("2024-01-01", periods=40, freq="5min", tz="UTC")
    bars = pd.DataFrame({"open": px, "high": px * 1.0005, "low": px * 0.9995,
                         "close": px, "volume": 100.0, "trades": 1000.0,
                         "taker_buy_base": 50.0, "taker_buy_quote": 2.5e6}, index=idx)
    funding = pd.DataFrame({"calc_time": [idx[10]], "last_funding_rate": [rate]})
    for side, sign in ((1.0, -1.0), (-1.0, 1.0)):
        sig = pd.DataFrame(0.0, index=idx, columns=["side", "stop_dist", "tp_dist", "max_hold"])
        sig.iloc[0] = [side, 200.0, 0.0, 20]
        res = run_backtest(bars, sig, funding=funding, session_start=0, session_end=24,
                           flat_at_session_end=False)
        if len(res.trades) != 1:
            check(f"funding: one {'long' if side > 0 else 'short'} trade", False, str(len(res.trades)))
            continue
        t = res.trades[0]
        expect = sign * t.qty * px * rate
        check(f"funding = qty x price x rate, {'long pays' if side > 0 else 'short receives'}",
              abs(t.funding - expect) < 1e-9, f"{t.funding:.6f} vs {expect:.6f}")


def test_signal_exit_hand_computed() -> None:
    """Exit on a signal (Level 3, owner-approved; PLAN.md section 13 port T5).

    Optional signal columns exit_long / exit_short: a flag set at the close
    of bar j closes a matching position at the open of bar j+1, taker fee +
    slippage, reason 'signal' - the same next-bar rule as entries. Checked
    before entries, so an entry signal on the same bar reverses the position
    at that open, as TradingView's strategy.entry does. Absent columns change
    nothing (every other test)."""
    print("\n1c. hand-computed exit on signal (and reversal)")
    px = 50000.0
    idx = pd.date_range("2024-01-01", periods=40, freq="5min", tz="UTC")
    opens = [px + 10.0 * k for k in range(40)]          # distinct open per bar
    bars = pd.DataFrame({"open": opens, "high": [p * 1.0005 for p in opens],
                         "low": [p * 0.9995 for p in opens], "close": opens,
                         "volume": 100.0, "trades": 1000.0, "taker_buy_base": 50.0,
                         "taker_buy_quote": 2.5e6}, index=idx)

    def sig_frame():
        s = pd.DataFrame(0.0, index=idx, columns=["side", "stop_dist", "tp_dist", "max_hold",
                                                   "exit_long", "exit_short"])
        s.iloc[0, s.columns.get_loc("side")] = 1.0
        s.iloc[0, s.columns.get_loc("stop_dist")] = 500.0
        s.iloc[0, s.columns.get_loc("max_hold")] = 30
        s.iloc[5, s.columns.get_loc("exit_long")] = 1.0
        return s

    res = run_backtest(bars, sig_frame(), session_start=0, session_end=24, flat_at_session_end=False)
    t = res.trades[0] if res.trades else None
    slip = 0.0002
    ok = (t is not None and t.exit_reason == "signal" and t.exit_time == idx[6]
          and abs(t.exit_px - opens[6] * (1 - slip)) < 1e-6 and t.entry_time == idx[1])
    check("exit_long at bar 5 closes the long at bar 6's open (taker, slipped)", ok,
          "no trade" if t is None else f"{t.exit_reason} at {t.exit_time}, px {t.exit_px:.2f}")

    s = sig_frame()
    s.iloc[5, s.columns.get_loc("side")] = -1.0
    s.iloc[5, s.columns.get_loc("stop_dist")] = 500.0
    s.iloc[5, s.columns.get_loc("max_hold")] = 3
    s.iloc[5, s.columns.get_loc("exit_long")] = 1.0
    res2 = run_backtest(bars, s, session_start=0, session_end=24, flat_at_session_end=False)
    tr = res2.trades
    ok2 = (len(tr) == 2 and tr[0].exit_time == idx[6] and tr[0].exit_reason == "signal"
           and tr[1].side == -1 and tr[1].entry_time == idx[6]
           and abs(tr[1].entry_px - opens[6] * (1 - slip)) < 1e-6)
    check("exit + opposite entry on the same bar reverses at the next open", ok2,
          f"{[(x.side, str(x.entry_time)[11:16], str(x.exit_time)[11:16], x.exit_reason) for x in tr]}")

    s3 = sig_frame()
    s3.iloc[0, s3.columns.get_loc("exit_long")] = 1.0      # same bar as the entry signal
    s3.iloc[5, s3.columns.get_loc("exit_long")] = 0.0
    res3 = run_backtest(bars, s3, session_start=0, session_end=24, flat_at_session_end=False)
    check("an exit flag before the position existed is ignored",
          len(res3.trades) == 1 and res3.trades[0].exit_reason != "signal",
          str([x.exit_reason for x in res3.trades]))


# --------------------------------------------------------------------------
# 2. Differential test against the reference
# --------------------------------------------------------------------------
def _random_case(seed: int, n: int = 3000):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-01", periods=n, freq="5min", tz="UTC")
    ret = rng.normal(0, 0.0012, n)
    close = 30000 * np.exp(np.cumsum(ret))
    op = np.r_[close[0], close[:-1]]
    wick = np.abs(rng.normal(0, 0.0008, n))
    high = np.maximum(op, close) * (1 + wick)
    low = np.minimum(op, close) * (1 - wick)
    bars = pd.DataFrame({"open": op, "high": high, "low": low, "close": close,
                         "volume": rng.lognormal(3, 1, n)}, index=idx)
    side = rng.choice([0.0, 1.0, -1.0], n, p=[0.7, 0.15, 0.15])
    sig = pd.DataFrame({
        "side": side,
        "stop_dist": np.where(side != 0, rng.uniform(50, 400, n), np.nan),
        "tp_dist": np.where(side != 0, rng.uniform(0, 800, n), 0.0),
        "max_hold": np.where(side != 0, rng.integers(1, 20, n), 0).astype(float),
    }, index=idx)
    # random funding events
    fidx = pd.date_range("2023-01-01", periods=n, freq="5min", tz="UTC")[::288]
    funding = pd.DataFrame({"calc_time": fidx,
                            "last_funding_rate": rng.normal(0, 0.0002, len(fidx))})
    return bars, sig, funding


def test_differential(seeds=(1, 2, 3, 7, 11, 23, 42, 99)) -> None:
    print(f"\n2. differential vs reference implementation ({len(seeds)} seeds)")
    for sd in seeds:
        bars, sig, funding = _random_case(sd)
        got = run_backtest(bars, sig, funding=funding, session_start=0,
                           session_end=24, flat_at_session_end=False)
        ref = reference_backtest(bars, sig, funding=funding)
        g = [{"entry": pd.Timestamp(t.entry_time),
              "exit": pd.Timestamp(t.exit_time),
              "side": t.side, "reason": t.exit_reason, "bars": t.bars,
              "r": round(t.r_multiple, 6)} for t in got.trades]
        ok = len(g) == len(ref)
        detail = f"count {len(g)} vs {len(ref)}" if not ok else ""
        if ok:
            worst = 0.0
            for k, (a, b) in enumerate(zip(g, ref)):
                same = (a["entry"] == bars.index[b["exit_i"] - b["bars"] + 1]
                        and a["exit"] == bars.index[b["exit_i"]]
                        and a["side"] == b["side"]
                        and a["reason"] == b["reason"]
                        and a["bars"] == b["bars"])
                if not same:
                    ok = False
                    detail = f"trade {k}: {a} vs ref exit_i={b['exit_i']} {b['reason']} bars={b['bars']}"
                    break
                worst = max(worst, abs(a["r"] - b["r"]))
            if ok:
                ok = worst < 1e-5
                detail = (f"{len(g)} trades match" if ok
                          else f"max |dR|={worst:.2e}") + (f" ({detail})" if not ok else "")
        check(f"seed {sd}", ok, detail)


# --------------------------------------------------------------------------
# 3. Cost monotonicity
# --------------------------------------------------------------------------
def test_cost_monotonicity() -> None:
    print("\n3. costs can only hurt")
    bars, sig, funding = _random_case(5, 4000)
    base = run_backtest(bars, sig, funding=funding)
    rich = run_backtest(bars, sig, funding=funding, fee_taker=0.0, slippage=0.0)
    poor = run_backtest(bars, sig, funding=funding, fee_taker=0.002, slippage=0.001)
    check("zero-cost beats real-cost", rich.metrics["net_return"] > base.metrics["net_return"],
          f"{rich.metrics['net_return']*100:.2f}% > {base.metrics['net_return']*100:.2f}%")
    check("real-cost beats heavy-cost", base.metrics["net_return"] > poor.metrics["net_return"],
          f"{base.metrics['net_return']*100:.2f}% > {poor.metrics['net_return']*100:.2f}%")
    check("fees reported", base.metrics["total_fees"] > 0, f"{base.metrics['total_fees']:.4f}U")

    # The trade *sequence* must be invariant to fees alone: fees change PnL but
    # not price levels, so the same entries/stops/targets must be hit.
    # (It is deliberately NOT invariant to slippage - slippage moves the entry
    # price, hence the stop and target levels, so different fills are correct.)
    kw = dict(initial_equity=100000.0)
    a = run_backtest(bars, sig, funding=funding, **kw)
    b = run_backtest(bars, sig, funding=funding, fee_taker=0.0, **kw)
    ka = [(pd.Timestamp(t.entry_time), t.side, t.exit_reason,
           pd.Timestamp(t.exit_time)) for t in a.trades]
    kb = [(pd.Timestamp(t.entry_time), t.side, t.exit_reason,
           pd.Timestamp(t.exit_time)) for t in b.trades]
    check("trade sequence invariant to fees", ka == kb,
          f"{len(ka)} vs {len(kb)} trades")
    check("flying PnL identical, fees only reduce it",
          abs(a.metrics["net_return"] - b.metrics["net_return"]) > 1e-9)


# --------------------------------------------------------------------------
# 4. No look-ahead: truncating the future must not change past trades
# --------------------------------------------------------------------------
def test_no_lookahead() -> None:
    print("\n4. no look-ahead")
    bars, sig, funding = _random_case(3, 2500)
    full = run_backtest(bars, sig, funding=funding)
    cut = 1500
    part = run_backtest(bars.iloc[:cut], sig.iloc[:cut], funding=funding)
    # Every trade that closed before the cut must be identical in both runs.
    # The final "eod" trade of the truncated run is excluded: it is an artefact
    # of the data ending, not a property of the strategy.
    key_full = [(pd.Timestamp(t.entry_time), t.side, round(t.r_multiple, 8),
                 t.exit_reason, pd.Timestamp(t.exit_time))
                for t in full.trades if pd.Timestamp(t.exit_time) < bars.index[cut]]
    key_part = [(pd.Timestamp(t.entry_time), t.side, round(t.r_multiple, 8),
                 t.exit_reason, pd.Timestamp(t.exit_time))
                for t in part.trades if t.exit_reason != "eod"]
    check("truncated run is a prefix of the full run", key_part == key_full,
          f"{len(key_part)} vs {len(key_full)} trades")


def main() -> None:
    print("=" * 70)
    print("BACKTEST ENGINE CORRECTNESS")
    print("=" * 70)
    test_hand_computed()
    test_funding_hand_computed()
    test_signal_exit_hand_computed()
    test_differential()
    test_cost_monotonicity()
    test_no_lookahead()
    test_post_only()
    test_dynamic_exits()
    test_recipe_blocks_causal()
    test_tf_variants()
    test_short_side()
    test_random_null_model()
    test_metrics()
    test_allocation()
    test_rotation()
    test_exit_lab()
    test_ml_entry()
    test_ml_pool()
    test_ml_pool2()
    test_candle_at_level()
    test_stop_diag()
    test_level_limit()
    test_premium()
    test_premium_confirm()
    test_ml_hold()
    test_ml_wf()
    test_ml_wf2()
    test_ml_wf3()
    test_ml_port()
    test_ml_xs()
    test_ml_mkt()
    test_ml_flow()
    test_listing()
    test_ml_wide()
    test_ml_large()
    test_result_report()
    print("\n" + "=" * 70)
    if FAIL:
        print(f"FAILED ({len(FAIL)}): " + ", ".join(FAIL))
        sys.exit(1)
    print("ALL CHECKS PASSED")


# --------------------------------------------------------------------------
# 6. Break-even / trailing stop must not see the current bar's close
# --------------------------------------------------------------------------
def _dyn_case(path, *, be_at=0.0, trail_at=0.0, trail_atr=0.0):
    """Long signalled on bar 0, filled at bar 1 open. `path` gives
    (open, high, low, close) for bars 1.. ; bar 0 is flat at 50000."""
    rows = [(50000.0, 50000.0, 50000.0, 50000.0)] + list(path)
    rows += [(50000.0, 50000.0, 50000.0, 50000.0)] * 15
    idx = pd.date_range("2024-01-01", periods=len(rows), freq="5min", tz="UTC")
    bars = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    bars["volume"] = 100.0
    sig = pd.DataFrame(0.0, index=idx, columns=["side", "stop_dist", "tp_dist", "max_hold"])
    sig.loc[idx[0], ["side", "stop_dist", "max_hold"]] = [1.0, 200.0, 50]
    sig["atr"] = 100.0
    sig["be_at"] = 0.0
    sig["trail_at"] = 0.0
    sig["trail_atr"] = 0.0
    sig.loc[idx[0], ["be_at", "trail_at", "trail_atr"]] = [be_at, trail_at, trail_atr]
    res = run_backtest(bars, sig, session_start=0, session_end=24,
                       flat_at_session_end=False)
    return idx, res.trades


def test_dynamic_exits() -> None:
    print("\n6. break-even / trailing stop use only information already known")
    slip = 0.0002
    entry = 50000.0 * (1 + slip)
    stop = entry - 200.0

    # A. bar 2 first trades through the ORIGINAL stop, then closes +1.5R.
    #    The stop can only move after bar 2 closes, so this is a full stop-out.
    idx, tr = _dyn_case([(50000, 50000, 50000, 50000),
                         (50000, 50400, 49700, 50300)], be_at=1.0)
    ok = len(tr) == 1 and tr[0].exit_reason == "stop"
    check("BE: a bar cannot move its own stop (full loss, not break-even)",
          ok and abs(tr[0].exit_px - stop * (1 - slip)) < 1e-4,
          f"exit_px={tr[0].exit_px:.2f} expected {stop * (1 - slip):.2f}" if tr else "no trade")

    # B. bar 2 closes +1.5R without touching the stop; bar 3 dips to entry.
    #    BE is armed from bar 3 on, so the exit is at the BE price on bar 3.
    idx, tr = _dyn_case([(50000, 50000, 50000, 50000),
                         (50000, 50320, 50000, 50300),
                         (50300, 50300, 49950, 50000)], be_at=1.0)
    be_px = entry * (1 + 0.0005 + slip)
    ok = len(tr) == 1
    check("BE: armed after the close that triggered it, exits on the next bar",
          ok and tr[0].exit_time == idx[3] and abs(tr[0].exit_px - be_px * (1 - slip)) < 1e-4,
          f"exit {tr[0].exit_time} @ {tr[0].exit_px:.2f}, expected {idx[3]} @ "
          f"{be_px * (1 - slip):.2f}" if ok else "no trade")

    # C. trailing: bar 2 closes +2R with a low that is below where the trail
    #    WILL be; that trail only exists from bar 3.
    idx, tr = _dyn_case([(50000, 50000, 50000, 50000),
                         (50000, 50420, 50200, 50400),
                         (50400, 50400, 50250, 50300)],
                        trail_at=1.0, trail_atr=1.0)
    ok = len(tr) == 1
    check("trail: set from the previous close, not the current one",
          ok and tr[0].exit_time == idx[3] and abs(tr[0].exit_px - 50300 * (1 - slip)) < 1e-4,
          f"exit {tr[0].exit_time} @ {tr[0].exit_px:.2f}" if ok else "no trade")

    # D. strategies must publish ATR on every bar, not only on signal bars,
    #    or the trail has nothing to move with while the position is open.
    import strategies as S
    bars, _, _ = _random_case(5)
    sig = S.donchian_breakout(bars, trail_at=1.0, trail_atr=1.5)
    warm = sig["atr"].iloc[50:]
    check("signal frame carries ATR on every bar (trail can move)",
          bool((warm > 0).all()), f"{int((warm <= 0).sum())} bars with atr<=0")


# --------------------------------------------------------------------------
# 7. Every recipe building block must be causal
# --------------------------------------------------------------------------
def test_recipe_blocks_causal() -> None:
    """Compute each trigger/filter on the full series and on a truncated one.
    A causal block gives identical values on the common prefix; any block
    that peeks at later bars (shift(-k), centred windows, full-sample stats)
    fails here."""
    print("\n7. recipe blocks are causal (full run == truncated run on the prefix)")
    import recipes as RC
    bars, _, funding = _random_case(9, n=2500)
    bars["taker_buy_base"] = bars["volume"] * 0.5 * (1 + 0.2 * np.sin(np.arange(len(bars)) / 7))
    # PLAN.md section 14 metrics columns, NaN for the first 300 bars as when
    # metrics start after the klines, so the blocks must survive a NaN prefix
    mrng = np.random.default_rng(14)
    k = np.arange(len(bars))
    oi = 1000 * np.exp(np.cumsum(mrng.normal(0, 0.02, len(bars))))
    for col, val in (("oi", oi), ("oi_usd", oi * bars["close"].to_numpy()),
                     ("top_acct_ls", np.exp(0.3 * np.sin(k / 40) + mrng.normal(0, .1, len(bars)))),
                     ("top_pos_ls", np.exp(0.3 * np.sin(k / 55) + mrng.normal(0, .1, len(bars)))),
                     ("acct_ls", np.exp(0.3 * np.cos(k / 30) + mrng.normal(0, .1, len(bars)))),
                     ("taker_ls", np.exp(mrng.normal(0, .2, len(bars))))):
        bars[col] = np.where(k < 300, np.nan, val)
    # PLAN.md section 25 Coinbase premium columns, NaN prefix as well
    for col in ("cb_prem", "cb_prem_btc"):
        bars[col] = np.where(k < 200, np.nan, 0.0005 * np.sin(k / 30) + mrng.normal(0, 3e-4, len(bars)))
    cut = 1700
    bad = []
    for kind, table in (("trigger", RC.TRIGGERS), ("filter", RC.FILTERS)):
        for name, fn in table.items():
            full = fn(bars, funding)
            part = fn(bars.iloc[:cut], funding)
            full = full if isinstance(full, tuple) else (full,)
            part = part if isinstance(part, tuple) else (part,)
            for a, b in zip(full, part):
                a = np.nan_to_num(np.asarray(a, dtype=float)[:cut], nan=-999)
                b = np.nan_to_num(np.asarray(b, dtype=float), nan=-999)
                if not np.array_equal(a, b):
                    bad.append(f"{kind}:{name}")
                    break
    check("all recipe triggers and filters are causal", not bad, ", ".join(bad))

    # Exp 025: output contract. opening_range returned a (long, short) tuple and
    # recipe() read it as "either side fired" = LONG for all of Exp 022.
    bad_shape = []
    for name, fn in RC.TRIGGERS.items():
        try:
            RC.check_trigger_output(name, fn(bars, funding), len(bars))
        except TypeError as e:
            bad_shape.append(str(e))
    for name, fn in RC.FILTERS.items():
        try:
            RC.check_filter_output(name, fn(bars, funding), len(bars))
        except TypeError as e:
            bad_shape.append(str(e))
    check("every trigger returns one -1/0/+1 array, every filter (long_ok, short_ok)",
          not bad_shape, "; ".join(bad_shape))
    RC.TRIGGERS["_tuple_bug"] = lambda b, f: (np.zeros(len(b)), np.ones(len(b)))
    try:
        RC.recipe(bars, funding, triggers=[{"type": "_tuple_bug"}], stop={"type": "pct", "pct": 0.02})
        refused = False
    except TypeError:
        refused = True
    finally:
        del RC.TRIGGERS["_tuple_bug"]
    check("recipe refuses a trigger that returns a (long, short) tuple", refused)
    idx = pd.date_range("2024-02-25", "2024-03-04", freq="D", tz="UTC")
    cal = pd.DataFrame({"close": np.arange(len(idx), 0, -1, dtype=float)}, index=idx)
    mt = np.asarray(RC.t_month_turn_fade(cal, None, before=2, after=0, lookback=1))
    fired = [d.day for d, s in zip(idx, mt) if s != 0]
    # LuxAlgo SMC port (PLAN.md section 13), hand-traced through the Pine logic
    # with pivot size 2 (leg flips confirm a pivot `size` bars back):
    #   bar 2: leg 0->1, pivot low = low[2 bars ago] = 9 (bar 0)
    #   bar 3: leg 1->0, pivot high = 12 (bar 1); close 8.5 crosses under 9,
    #          no trend yet -> bearish BOS, trend bearish
    #   bar 6: leg 0->1, pivot low = 7 (bar 4)
    #   bar 7: close 12.5 crosses over 12 in a bearish trend -> bullish CHoCH
    #   bar 9: leg 1->0, pivot high = 13 (bar 7); close 6.5 crosses under 7 in a
    #          bullish trend -> bearish CHoCH
    #   bar 11: close 13.5 crosses over 13 in a bearish trend -> bullish CHoCH
    hlc = [(10, 9, 9.5), (12, 10, 11), (11, 10, 10.5), (10, 8, 8.5), (9, 7, 8), (10, 8, 9),
           (11, 9, 10.5), (13, 11, 12.5), (12, 10, 10.5), (11, 6, 6.5), (9, 5, 8), (14, 8, 13.5)]
    smc_bars = pd.DataFrame(hlc, columns=["high", "low", "close"], dtype=float)
    ev = RC.smc_structure(smc_bars, swing_len=2, internal_len=2)
    got = {k: np.flatnonzero(v).tolist() for k, v in ev.items() if k.startswith("swing") and v.any()}
    check("smc_structure: BOS / CHoCH sequence matches a hand trace of the Pine logic",
          got == {"swing_bear_bos": [3], "swing_bull_choch": [7, 11], "swing_bear_choch": [9]}, str(got))
    # ChartArt MACD + SMA 200 port: the pandas block against a plain loop that
    # follows the Pine lines one by one (SMA-based MACD, close[slow] vs SMA)
    px = list(np.round(100 + np.random.default_rng(11).normal(0, 1, 400).cumsum(), 4))
    cm = pd.DataFrame({"close": px, "high": px, "low": px, "open": px})
    fa, sl, sg, vs = 3, 6, 4, 20

    def _sma(v, i, n):
        return sum(v[i - n + 1:i + 1]) / n if i >= n - 1 and all(x is not None for x in v[i - n + 1:i + 1]) else None
    fm = [_sma(px, i, fa) for i in range(len(px))]
    sm = [_sma(px, i, sl) for i in range(len(px))]
    vm = [_sma(px, i, vs) for i in range(len(px))]
    md = [a - b if a is not None and b is not None else None for a, b in zip(fm, sm)]
    sgl = [_sma(md, i, sg) if md[i] is not None else None for i in range(len(px))]
    hs = [m - s if m is not None and s is not None else None for m, s in zip(md, sgl)]
    exp = []
    for i in range(len(px)):
        ok = i >= sl and hs[i] is not None and hs[i - 1] is not None and vm[i] is not None
        lg = ok and hs[i] > 0 and not hs[i - 1] > 0 and md[i] > 0 and fm[i] > sm[i] and px[i - sl] > vm[i]
        st = ok and hs[i] < 0 and not hs[i - 1] < 0 and md[i] < 0 and fm[i] < sm[i] and px[i - sl] < vm[i]
        exp.append(1 if lg else -1 if st else 0)
    got_m = np.asarray(RC.t_chartart_macd_sma(cm, None, fast=fa, slow=sl, signal=sg, veryslow=vs))
    check("chartart_macd_sma matches a line-by-line loop of the Pine script",
          np.array_equal(got_m, np.array(exp, float)) and (got_m != 0).sum() > 5,
          f"{int((got_m != 0).sum())} signals, {int((got_m != np.array(exp)).sum())} mismatches")
    # Super Scalper port: WMA as Pine defines it, and the entry rule against a
    # plain loop over the Pine lines (bands from a hand-rolled WMA of TR)
    wx = pd.Series([1.0, 2.0, 4.0, 7.0, 11.0])
    check("wma (super_scalper) = sum(w_k x_k)/sum(w), newest weight n",
          abs(RC._wma(wx, 3).iloc[-1] - (3 * 11 + 2 * 7 + 1 * 4) / 6) < 1e-12 and RC._wma(wx, 3).iloc[:2].isna().all())
    rng = np.random.default_rng(21)
    cl = 100 + rng.normal(0, 1, 600).cumsum()
    op = cl + rng.normal(0, 1.2, 600)
    ss = pd.DataFrame({"open": op, "close": cl, "high": np.maximum(op, cl) + rng.uniform(0, .5, 600),
                       "low": np.minimum(op, cl) - rng.uniform(0, .5, 600)})
    trl = [ss.high[0] - ss.low[0]] + [max(ss.high[i] - ss.low[i], abs(ss.high[i] - ss.close[i - 1]),
                                           abs(ss.low[i] - ss.close[i - 1])) for i in range(1, 600)]
    r1 = RC.ta.rsi(ss.close, 5).to_numpy()
    r2 = RC.ta.rsi(ss.close, 20).to_numpy()
    exp_s = []
    for i in range(600):
        if i < 13:
            exp_s.append(0)
            continue
        bw = sum((14 - k) * trl[i - k] for k in range(14)) / 105.0
        lg = ss.open[i] < ss.close[i] - bw and r1[i] > r2[i]
        st = ss.open[i] > ss.close[i] + bw and r1[i] < r2[i]
        exp_s.append(1 if lg else -1 if st else 0)
    got_s = np.asarray(RC.t_super_scalper(ss, None, atr_len=14, mult=1.0, rsi_fast=5, rsi_slow=20))
    check("super_scalper matches a line-by-line loop of the Pine script",
          np.array_equal(got_s, np.array(exp_s, float)) and (got_s != 0).sum() > 5,
          f"{int((got_s != 0).sum())} signals, {int((got_s != np.array(exp_s)).sum())} mismatches")
    # liquidity_sweep (T6), hand trace, pivot_len 2. Flat bars (O=C=100, H 101,
    # L 99, vol 100) give ties, so no pivots, except: bar 22 low 97 -> pivot
    # low confirmed on bar 24 (bars 20,21,23,24 all 99), level 97 born bar 22.
    # Bar 26 sweeps it: low 96 < 97, close 99.8 > 97, body 0.2, lower wick
    # 3.8 >= 1.5 x 0.2, volume 300 > 1.3 x SMA20 (=110). Its mid is
    # (96 + 99.8) / 2 = 97.9 and bar 27 closes 100 > 97.9 -> long on bar 27.
    def _sweep_bars(vol26=300.0):
        k = 30
        op = np.full(k, 100.0); cl = op.copy(); hi = np.full(k, 101.0); lo = np.full(k, 99.0)
        vo = np.full(k, 100.0)
        lo[22] = 97.0
        cl[26], hi[26], lo[26], vo[26] = 99.8, 100.1, 96.0, vol26
        return pd.DataFrame({"open": op, "high": hi, "low": lo, "close": cl, "volume": vo},
                            index=pd.date_range("2024-01-01", periods=k, freq="15min"))
    sb = _sweep_bars()
    got = np.asarray(RC.t_liquidity_sweep(sb, None, pivot_len=2))
    mir = sb.copy()
    mir["open"], mir["close"] = 200 - sb["open"], 200 - sb["close"]
    mir["high"], mir["low"] = 200 - sb["low"], 200 - sb["high"]
    got_m = np.asarray(RC.t_liquidity_sweep(mir, None, pivot_len=2))
    quiet = np.asarray(RC.t_liquidity_sweep(_sweep_bars(vol26=120.0), None, pivot_len=2))
    aged = np.asarray(RC.t_liquidity_sweep(sb, None, pivot_len=2, max_age=2))
    swept_age4 = np.asarray(RC.t_liquidity_sweep(sb, None, pivot_len=2, max_age=3))
    check("liquidity_sweep hand trace: long on bar 27 only; mirrored -> short; "
          "no signal without the volume spike or after the level ages out",
          list(np.flatnonzero(got)) == [27] and got[27] == 1.0
          and list(np.flatnonzero(got_m)) == [27] and got_m[27] == -1.0
          and not quiet.any() and not aged.any() and swept_age4[27] == 1.0,
          f"long {list(np.flatnonzero(got))} short {list(np.flatnonzero(got_m))} "
          f"quiet {int(quiet.any())} aged {int(aged.any())}")
    # exit_on="opposite" (engine signal exit): exit columns = the raw trigger's
    # opposite events; exit_on="none" leaves the signal frame exactly as before
    kw = dict(triggers=[{"type": "donchian_break", "n": 20}], filters=[{"type": "trend_ema", "fast": 20, "slow": 50}],
              direction="long", stop={"type": "pct", "pct": 0.02})
    base = RC.recipe(bars, funding, **kw)
    opp = RC.recipe(bars, funding, exit_on="opposite", **kw)
    raw = np.asarray(RC.t_donchian_break(bars, funding, n=20))
    check("exit_on='opposite' flags exit_long on every raw bearish trigger, and adds nothing else",
          np.array_equal(opp["exit_long"].to_numpy() != 0, raw < 0)
          and np.array_equal(opp["exit_short"].to_numpy() != 0, raw > 0)
          and base.equals(opp.drop(columns=["exit_long", "exit_short"]))
          and "exit_long" not in base, f"{int((raw < 0).sum())} bearish triggers")
    check("month_turn_fade uses the real month length (Feb 2024: 28th, 29th, 1st)",
          fired == [28, 29, 1], str(fired))
    sig = RC.recipe(bars, funding, triggers=[{"type": "donchian_break", "n": 20}],
                    filters=[{"type": "trend_ema", "fast": 20, "slow": 50}],
                    stop={"type": "swing", "n": 10}, tp={"type": "r", "r": 2.0},
                    trail_at=1.0, trail_atr=2.0, max_hold_hours=2, cooldown_bars=3)
    act = sig[sig["side"] != 0]
    check("recipe emits signals with positive stops and tp = r * stop",
          len(act) > 0 and bool((act["stop_dist"] > 0).all())
          and np.allclose(act["tp_dist"], 2.0 * act["stop_dist"]),
          f"{len(act)} signals")
    check("recipe max_hold converts hours to bars (2h on 5m = 24)",
          bool((act["max_hold"] == 24).all()))


# --------------------------------------------------------------------------
# 8. Timeframe variants rescale the right parameters and nothing else
# --------------------------------------------------------------------------
def test_tf_variants() -> None:
    print("\n8. tf_variants: chart and time modes rescale only what they should")
    import tf_variants as TV
    idea = {"name": "t", "hypothesis": "h", "strategy": "recipe", "tf": 15,
            "params": {"triggers": [{"type": "donchian_break", "n": 48},
                                    {"type": "supertrend_flip", "n": 10, "mult": 3.0}],
                       "filters": [{"type": "htf_trend", "n": 50, "mult": 4},
                                   {"type": "adx_min", "n": 14, "min": 20}],
                       "stop": {"type": "pct", "pct": 0.02, "min_atr": 1.5, "max_atr": 8.0},
                       "tp": {"type": "r", "r": 2.0}, "be_at": 1.0, "trail_at": 1.5,
                       "trail_atr": 2.5, "max_hold_hours": 8, "cooldown_bars": 4},
            "grid": {"stop.pct": [0.015, 0.02], "triggers.0.n": [24, 48],
                     "filters.1.min": [20, 25]},
            "execution": {"entry_mode": "post_only", "entry_offset_atr": 0.1}}
    c = TV.make_variant(idea, 60, "chart")
    cp = c["params"]
    check("chart: bar counts and ATR multiples unchanged",
          cp["triggers"][0]["n"] == 48 and cp["filters"][1]["n"] == 14
          and cp["trail_atr"] == 2.5 and cp["stop"]["max_atr"] == 8.0
          and c["execution"]["entry_offset_atr"] == 0.1)
    check("chart: hold x4 and pct stop x2 going 15m -> 60m",
          cp["max_hold_hours"] == 32 and abs(cp["stop"]["pct"] - 0.04) < 1e-9
          and c["grid"]["stop.pct"] == [0.03, 0.04])
    t = TV.make_variant(idea, 5, "time")
    tp_ = t["params"]
    check("time: bar counts x3 going 15m -> 5m (params and grid)",
          tp_["triggers"][0]["n"] == 144 and tp_["filters"][0]["n"] == 150
          and tp_["cooldown_bars"] == 12 and t["grid"]["triggers.0.n"] == [72, 144])
    check("time: ATR multiples x sqrt(3), htf_trend mult untouched",
          abs(tp_["trail_atr"] - round(2.5 * 3 ** 0.5, 3)) < 1e-9
          and abs(tp_["triggers"][1]["mult"] - round(3.0 * 3 ** 0.5, 3)) < 1e-9
          and tp_["filters"][0]["mult"] == 4)
    check("both: R, %, hours and thresholds untouched in time mode",
          tp_["stop"]["pct"] == 0.02 and tp_["tp"]["r"] == 2.0 and tp_["be_at"] == 1.0
          and tp_["max_hold_hours"] == 8 and tp_["filters"][1]["min"] == 20
          and t["grid"]["filters.1.min"] == [20, 25])


# --------------------------------------------------------------------------
# 9. Shorts: the P&L sign (Exp 014)
# --------------------------------------------------------------------------
def test_short_side() -> None:
    """Every earlier test either used longs or compared against a reference
    that shared the engine's assumption, and a short's P&L had the wrong sign
    for the whole project (Exp 014). These checks need no reference and no
    remembered convention: a short is a mirror image of a long."""
    print("\n9. shorts: mirror symmetry and a hand-computed short")
    n = 30
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    c = np.linspace(100.0, 95.0, n)
    o = np.r_[c[0], c[:-1]]
    bars = pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.01,
                         "low": np.minimum(o, c) - 0.01, "close": c, "volume": 1.0},
                        index=idx)
    zero = dict(fee_taker=0.0, fee_maker=0.0, slippage=0.0, session_start=0,
                session_end=24, flat_at_session_end=False, min_notional=0.0,
                qty_step=1e-9)
    res = {}
    for side in (1, -1):
        sig = pd.DataFrame(0.0, index=idx, columns=["side", "stop_dist", "tp_dist", "max_hold"])
        sig.iloc[0] = [side, 20.0, 0.0, 10]
        res[side] = run_backtest(bars, sig, **zero)
    tl, ts = res[1].trades[0], res[-1].trades[0]
    check("A. falling market: the short profits, the long loses",
          ts.net_pnl > 0 > tl.net_pnl, f"short {ts.net_pnl:+.5f} long {tl.net_pnl:+.5f}")
    check("A. same trade, opposite side: exactly opposite P&L and R (zero costs)",
          abs(ts.net_pnl + tl.net_pnl) < 1e-12 and abs(ts.r_multiple + tl.r_multiple) < 1e-12)
    check("A. short: cash = start + net P&L",
          abs(res[-1].metrics["final_equity"] - (100.0 + ts.net_pnl)) < 1e-9)

    # B. mirror the whole market and flip every signal: every R must be identical
    bad = []
    for seed in (1, 2, 3, 7, 11):
        b, sig, _ = _random_case(seed)
        mid = 2 * float(b["close"].mean())
        m = pd.DataFrame({"open": mid - b["open"], "high": mid - b["low"],
                          "low": mid - b["high"], "close": mid - b["close"],
                          "volume": b["volume"]}, index=b.index)
        sig_m = sig.copy()
        sig_m["side"] = -sig["side"]
        r1 = run_backtest(b, sig, **zero)
        r2 = run_backtest(m, sig_m, **zero)
        a1 = [(t.entry_time, t.exit_reason, round(t.r_multiple, 9)) for t in r1.trades]
        a2 = [(t.entry_time, t.exit_reason, round(t.r_multiple, 9)) for t in r2.trades]
        if a1 != a2:
            bad.append(seed)
    check("B. mirrored market + flipped sides reproduces every trade's R (5 seeds)",
          not bad, f"seeds failing: {bad}")

    # C. hand-computed short, stopped out by a rally, with real costs
    c2 = np.linspace(50000.0, 50600.0, 40)
    o2 = np.r_[c2[0], c2[:-1]]
    idx2 = pd.date_range("2024-01-01", periods=40, freq="5min", tz="UTC")
    b2 = pd.DataFrame({"open": o2, "high": np.maximum(o2, c2) * 1.0002,
                       "low": np.minimum(o2, c2) * 0.9998, "close": c2, "volume": 1.0},
                      index=idx2)
    sig2 = pd.DataFrame(0.0, index=idx2, columns=["side", "stop_dist", "tp_dist", "max_hold"])
    sig2.iloc[0] = [-1.0, 200.0, 0.0, 30]
    r = run_backtest(b2, sig2, session_start=0, session_end=24, flat_at_session_end=False)
    ok = len(r.trades) == 1 and r.trades[0].exit_reason == "stop"
    if ok:
        t = r.trades[0]
        slip, fee = 0.0002, 0.0005
        entry = b2["open"].iloc[1] * (1 - slip)          # sell: slippage lowers the fill
        stop = entry + 200.0
        exit_ = stop * (1 + slip)                          # buy back: slippage raises it
        pnl = t.qty * (entry - exit_) - t.qty * fee * (entry + exit_)
        check("C. hand-computed short stopped out: fills, P&L and R",
              abs(t.entry_px - entry) < 1e-6 and abs(t.exit_px - exit_) < 1e-4
              and abs(t.net_pnl - pnl) < 1e-6 and abs(t.r_multiple - pnl / (t.qty * 200.0)) < 1e-9
              and t.r_multiple < -1.0,
              f"R {t.r_multiple:.6f} expected {pnl / (t.qty * 200.0):.6f}")
    else:
        check("C. hand-computed short stopped out: fills, P&L and R", False,
              f"trades {len(r.trades)}")

    # D. a trade the account cannot size is counted, never silently dropped
    r = run_backtest(b2, sig2, initial_equity=10.0, session_start=0, session_end=24,
                     flat_at_session_end=False)
    check("D. unsizable trade (10 USDT, 0.001 BTC step) is reported in size_skips",
          len(r.trades) == 0 and r.metrics.get("size_skips", 0) == 1,
          f"trades {len(r.trades)} size_skips {r.metrics.get('size_skips')}")


# --------------------------------------------------------------------------
# 10. Random-entry null model (baseline.py)
# --------------------------------------------------------------------------
def test_random_null_model() -> None:
    print("\n10. random trigger: rate, balance, seeds, and the --final baseline gate")
    import recipes as RC
    import evaluate as EV
    bars, _, _ = _random_case(3, n=20000)
    s1 = RC.t_random(bars, None, p=0.05, seed=1)
    s2 = RC.t_random(bars, None, p=0.05, seed=2)
    rate = float((s1 != 0).mean())
    longs = float((s1 > 0).sum() / max((s1 != 0).sum(), 1))
    check("fires at about rate p, long/short about 50/50",
          0.045 < rate < 0.055 and 0.45 < longs < 0.55, f"rate {rate:.4f} long share {longs:.3f}")
    check("different seeds give different entries, same seed the same",
          not np.array_equal(s1, s2) and np.array_equal(s1, RC.t_random(bars, None, p=0.05, seed=1)))
    check("--final gate: an unknown eval_id has no baseline (MISSING)",
          EV.baseline_verdict("0000000000") == "MISSING")
    check("--final gate: no baseline and no benchmark -> no holdout ticket",
          EV.benchmark_verdict("0000000000") == "MISSING" and not EV.holdout_ticket("0000000000"))
    import baseline as BL
    runs = pd.DataFrame({"mode": ["A"] * 100 + ["B"] * 100,
                         "train_mean_r": np.r_[np.linspace(-0.1, 0.1, 100), np.linspace(0.0, 0.2, 100)],
                         "valid_mean_r": np.r_[np.linspace(-0.1, 0.1, 100), np.linspace(0.0, 0.2, 100)]})
    check("SKILL needs TRAIN too: beating random on VALID only is DRIFT",
          not BL.skill_check(real_train=0.05, real_valid=0.30, runs=runs)["skill"])
    check("SKILL when the idea beats both modes' 95th pct on TRAIN and VALID",
          BL.skill_check(real_train=0.30, real_valid=0.30, runs=runs)["skill"])

    # Exp 021: a regime rule (trigger = market state) needs ALPHA; SKILL is not enough
    regime = {"triggers": [{"type": "trend_state", "n": 200}], "filters": []}
    entry = {"triggers": [{"type": "donchian_break", "n": 24}], "filters": []}
    saved = EV.baseline_verdict, EV.benchmark_verdict
    try:
        EV.baseline_verdict, EV.benchmark_verdict = (lambda _e: "SKILL"), (lambda _e: "NO_EDGE")
        check("--final gate: an entry idea with SKILL gets a ticket",
              EV.holdout_ticket("x", entry) and EV.holdout_ticket("x"))
        check("--final gate: a regime rule with SKILL but NO_EDGE gets no ticket",
              not EV.holdout_ticket("x", regime))
        EV.benchmark_verdict = lambda _e: "ALPHA"
        check("--final gate: a regime rule with ALPHA gets a ticket", EV.holdout_ticket("x", regime))
    finally:
        EV.baseline_verdict, EV.benchmark_verdict = saved

    # Exp 021: signals the account could not size make a result UNSIZABLE
    good = {"trades": 300, "mean_r": 0.2, "ci_lo": 0.05, "max_dd": 0.05, "size_skips": 0}
    tr_ok = {"mean_r": 0.1, "trades": 300, "size_skips": 0}
    stress = {"mean_r": 0.15}
    check("verdict: all gates and no skips -> PASS", EV.verdict(tr_ok, good, stress)[0] == "PASS")
    check("verdict: a PASS with VALID skips -> UNSIZABLE",
          EV.verdict(tr_ok, {**good, "size_skips": 3}, stress)[0] == "UNSIZABLE")
    check("verdict: a PASS with TRAIN skips -> UNSIZABLE",
          EV.verdict({**tr_ok, "size_skips": 1}, good, stress)[0] == "UNSIZABLE")
    check("verdict: a losing result with skips stays REJECT",
          EV.verdict(tr_ok, {**good, "mean_r": -0.1, "ci_lo": -0.2, "size_skips": 5},
                     {"mean_r": -0.2})[0] == "REJECT")
    import tf_variants as TV
    wide = {"name": "w", "tf": 240, "params": {"stop": {"type": "pct", "pct": 0.20}}, "grid": {}}
    check("tf_variants: a 20% stop at 1000 USDT is only sizable below 50,000",
          abs(TV.max_price_for_stop(0.20) - C.EVAL_EQUITY * C.RISK_PER_TRADE / (0.20 * C.QTY_STEP)) < 1e-6
          and TV.sizing_warning(wide, 100_000.0) != ""
          and TV.sizing_warning({**wide, "params": {"stop": {"type": "pct", "pct": 0.02}}}, 100_000.0) == "")


# --------------------------------------------------------------------------
# 5. Post-only execution model
# --------------------------------------------------------------------------
def test_post_only() -> None:
    print("\n5. post-only entry model")
    bars, sig, funding = _random_case(13, 2500)

    taker = run_backtest(bars, sig, funding=funding)
    po = run_backtest(bars, sig, funding=funding, entry_mode="post_only")
    po_off = run_backtest(bars, sig, funding=funding, entry_mode="post_only",
                          entry_offset_atr=0.5)
    check("post-only produces trades", po.metrics["trades"] > 0,
          f"{po.metrics['trades']} vs taker {taker.metrics['trades']}")
    # The count of executed trades is path-dependent - missing an entry shifts
    # every later decision - so the meaningful invariant is the fill rate.
    check("post-only does not fill every signal",
          0.0 < po.metrics["fill_rate"] < 1.0,
          f"fill_rate={po.metrics['fill_rate']:.3f} "
          f"({po.metrics['entry_fills']}/{po.metrics['entry_signals']})")
    check("taker always fills", taker.metrics["fill_rate"] == 1.0)
    check("post-only pays less per trade",
          po.metrics["avg_cost_r"] < taker.metrics["avg_cost_r"],
          f"{po.metrics['avg_cost_r']:.4f} < {taker.metrics['avg_cost_r']:.4f}")

    fr = []
    for off in (0.0, 0.25, 0.5, 1.0, 2.0):
        r = run_backtest(bars, sig, funding=funding, entry_mode="post_only",
                         entry_offset_atr=off)
        fr.append((off, r.metrics["fill_rate"], r.metrics["trades"]))
    mono = all(fr[i][1] >= fr[i + 1][1] for i in range(len(fr) - 1))
    check("fill rate falls monotonically as the limit moves away",
          mono, " ".join(f"off={o}:{f:.2f}/{t}t" for o, f, t in fr))

    # a post-only fill must never be better than the taker entry price for a
    # long: the limit sits at or below the signal close
    if po.trades:
        bad = [t for t in po.trades
               if t.side > 0 and t.entry_px > bars["close"].shift(1).reindex(
                   pd.DatetimeIndex([t.entry_time])).iloc[0] * 1.0001]
        check("long limit never fills above the signal close", not bad,
              f"{len(bad)} violations")

    # zero fill ratio must produce zero trades
    z = run_backtest(bars, sig, funding=funding, entry_mode="post_only",
                     entry_fill_ratio=0.0)
    check("zero queue ratio gives zero trades", z.metrics["trades"] == 0,
          str(z.metrics["trades"]))

    # a limit far away should essentially never fill
    far = run_backtest(bars, sig, funding=funding, entry_mode="post_only",
                       entry_offset_atr=50.0)
    check("an unreachable limit never fills", far.metrics["fill_rate"] == 0.0,
          f"fill_rate={far.metrics['fill_rate']:.3f} trades={far.metrics['trades']}")


# --------------------------------------------------------------------------
# 11. Metrics data (PLAN.md section 14): file reading, causal alignment, blocks
# --------------------------------------------------------------------------
def test_metrics() -> None:
    print("\n11. metrics: zip reading, causal alignment to bars, blocks vs loops")
    import io
    import tempfile
    import zipfile
    import datafeed as DF
    import experiment as E
    import recipes as RC

    # (a) a daily file with a header row and every row twice (early files)
    rows = ["create_time,symbol,sum_open_interest,sum_open_interest_value,"
            "count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,"
            "count_long_short_ratio,sum_taker_long_short_vol_ratio"]
    for t, v in (("2020-09-01 00:00:00", 10), ("2020-09-01 00:05:00", 11)):
        rows += [f"{t},BTCUSDT,{v},{v * 100},1.1,1.2,,0.9"] * 2
    with tempfile.TemporaryDirectory() as d:
        zp = Path(d) / "BTCUSDT-metrics-2020-09-01.zip"
        with zipfile.ZipFile(zp, "w") as z:
            z.writestr("BTCUSDT-metrics-2020-09-01.csv", "\n".join(rows) + "\n")
        got = DF.read_metrics_zip(zp)
    check("metrics zip: header dropped, duplicate rows dropped, UTC times, empty -> NaN",
          len(got) == 2 and list(got["sum_open_interest"]) == [10.0, 11.0]
          and str(got["create_time"].dt.tz) == "UTC"
          and got["count_long_short_ratio"].isna().all(), f"{len(got)} rows")

    # (b) alignment, hand-computed. 15m bars; metric rows at 00:00..00:20
    # (values 0..4) then a gap until 01:20 (value 9). A row is usable 5 min
    # after its create_time and only if it is at most 30 min old at the close.
    #   bar 23:30 (close 23:45) -> before the first row      -> NaN
    #   bar 00:00 (close 00:15) -> create <= 00:10           -> 2
    #   bar 00:15 (close 00:30) -> create <= 00:25 -> 00:20  -> 4
    #   bar 00:30 (close 00:45) -> 00:20, usable 00:25, 20 min old -> 4
    #   bar 00:45 (close 01:00) -> 00:20 is 35 min old       -> NaN
    #   bar 01:30 (close 01:45) -> 01:20                     -> 9
    idx = pd.DatetimeIndex(["2020-08-31 23:30", "2020-09-01 00:00", "2020-09-01 00:15",
                            "2020-09-01 00:30", "2020-09-01 00:45", "2020-09-01 01:30"], tz="UTC")
    bars = pd.DataFrame({"close": 1.0}, index=idx)
    ct = pd.to_datetime(["2020-09-01 00:00", "2020-09-01 00:05", "2020-09-01 00:10",
                         "2020-09-01 00:15", "2020-09-01 00:20", "2020-09-01 01:20"], utc=True)
    met = pd.DataFrame({"create_time": ct, **{c: [0, 1, 2, 3, 4, 9.0] for c in E.METRIC_NAMES.values()}})
    out = E.attach_metrics(bars, met, 15)
    want = [np.nan, 2, 4, 4, np.nan, 9]
    check("metrics attach: 5-min lag, as-of the bar close, stale > 30 min -> NaN (hand-computed)",
          np.allclose(out["oi"].to_numpy(), want, equal_nan=True)
          and np.allclose(out["acct_ls"].to_numpy(), want, equal_nan=True)
          and out.index.equals(bars.index), str(list(out["oi"])))

    # (c) the blocks against plain loops that follow their docstrings
    b, _, _ = _random_case(21, n=900)
    rng = np.random.default_rng(3)
    k = np.arange(len(b))
    b["oi"] = np.where(k < 100, np.nan, 1000 * np.exp(np.cumsum(rng.normal(0, 0.03, len(b)))))
    b["top_pos_ls"] = np.exp(0.4 * np.sin(k / 25) + rng.normal(0, .15, len(b)))
    b["acct_ls"] = np.exp(0.4 * np.cos(k / 35) + rng.normal(0, .15, len(b)))
    zn = 60

    def zloop(x):
        z = np.full(len(x), np.nan)
        for i in range(len(x)):
            w = x[max(0, i - zn + 1):i + 1]
            w = w[np.isfinite(w)]
            if len(w) >= int(0.9 * zn) and np.isfinite(x[i]):  # 90% of z_n present
                z[i] = (x[i] - w.mean()) / w.std(ddof=1)
        return z

    c = b["close"].to_numpy(float)
    oi = b["oi"].to_numpy(float)
    lag = lambda a, n: np.r_[np.full(n, np.nan), a[:-n]]  # noqa: E731
    zr, zo = zloop(np.log(c / lag(c, 4))), zloop(np.log(oi / lag(oi, 4)))
    lc, sc = (zo <= -1.5) & (zr <= -1.5), (zo <= -1.5) & (zr >= 1.5)
    exp = [1 if lc[i] and not (i and lc[i - 1]) else -1 if sc[i] and not (i and sc[i - 1]) else 0
           for i in range(len(b))]
    got = np.asarray(RC.t_oi_flush(b, None, n=4, z_n=zn, price_z=1.5, oi_z=1.5))
    check("oi_flush matches a loop (first bar of price z and OI z both past the line)",
          np.array_equal(got, np.array(exp, float)) and (got != 0).sum() >= 2,
          f"{int((got != 0).sum())} signals, {int((got != np.array(exp)).sum())} mismatches")
    za = zloop(np.log(b["acct_ls"].to_numpy(float)))
    exp = [0] + [1 if za[i] < -1.5 and not za[i - 1] < -1.5 else
                 -1 if za[i] > 1.5 and not za[i - 1] > 1.5 else 0 for i in range(1, len(b))]
    got = np.asarray(RC.t_crowd_fade(b, None, col="acct_ls", z_n=zn, z=1.5))
    check("crowd_fade matches a loop (long when the crowd ratio crosses below -z)",
          np.array_equal(got, np.array(exp, float)) and (got != 0).sum() >= 2,
          f"{int((got != 0).sum())} signals, {int((got != np.array(exp)).sum())} mismatches")
    dd = zloop(np.log(b["top_pos_ls"].to_numpy(float))) - za
    exp = [0] + [1 if dd[i] > 1.0 and not dd[i - 1] > 1.0 else
                 -1 if dd[i] < -1.0 and not dd[i - 1] < -1.0 else 0 for i in range(1, len(b))]
    got = np.asarray(RC.t_smart_divergence(b, None, z_n=zn, k=1.0))
    check("smart_divergence matches a loop (top-trader z minus all-account z crosses +-k)",
          np.array_equal(got, np.array(exp, float)) and (got != 0).sum() >= 2,
          f"{int((got != 0).sum())} signals, {int((got != np.array(exp)).sum())} mismatches")
    lo, sh = RC.f_oi_rising(b, None, n=10, min_pct=0.02)
    exp = np.array([np.isfinite(oi[i]) and i >= 10 and oi[i] / oi[i - 10] - 1 > 0.02 for i in range(len(b))])
    check("oi_rising = OI up more than min_pct over n bars, both sides",
          np.array_equal(np.asarray(lo, bool), exp) and np.array_equal(np.asarray(sh, bool), exp)
          and 0 < exp.sum() < len(b), f"{int(exp.sum())} bars allowed")
    try:
        RC.t_oi_flush(b.drop(columns=["oi"]), None)
        refused = False
    except ValueError:
        refused = True
    check("a metrics block on bars without metrics refuses loudly", refused)


# --------------------------------------------------------------------------
# 12. Allocation test (PLAN.md section 16): daily P&L, shorts, funding, rules
# --------------------------------------------------------------------------
def test_allocation() -> None:
    print("\n12. allocation: hand-computed daily P&L, short, funding, causal rules")
    import allocation as AL

    # (a) long one day then flat, 1% cost per side. Target at close t -> position
    # at open t+1. d1: buy with all equity, pay 1% -> 0.99; d2: +10% -> 1.089;
    # d3: price back to 110 -> 0.99, sell and pay 1% of 0.99 -> 0.9801.
    eq, pos, n = AL.simulate(np.array([100., 110, 121, 110, 100]), np.array([1., 1, 0, 0, 0]), 0.01)
    check("allocation: long, next-open fills, cost on each change (hand-computed)",
          np.allclose(eq, [1, .99, 1.089, .9801, .9801]) and list(pos) == [0, 1, 1, 0, 0] and n == 2,
          str(np.round(eq, 6)))
    # (b) a real short: units held, not rebalanced. Short 1x at 100, price
    # halves -> +50%; price doubles instead -> equity 0.
    eq, _, _ = AL.simulate(np.array([100., 100, 50, 50]), np.array([-1., -1, 0, 0]), 0.0)
    eq2, _, _ = AL.simulate(np.array([100., 100, 200, 200]), np.array([-1., -1, 0, 0]), 0.0)
    check("allocation: short gains 50% when price halves, loses 100% when it doubles",
          np.allclose(eq, [1, 1, 1.5, 1.5]) and np.allclose(eq2, [1, 1, 0, 0]), f"{eq} {eq2}")
    # (c) funding: notional x rate, long pays a positive rate, short receives it
    o, t, f = np.array([100., 100, 100]), np.array([1., 1, 1]), np.array([0, 0, 0.001])
    eql, _, _ = AL.simulate(o, t, 0.0, f)
    eqs, _, _ = AL.simulate(o, -t, 0.0, f)
    check("allocation: funding = notional x rate, long pays, short receives",
          np.isclose(eql[-1], 0.999) and np.isclose(eqs[-1], 1.001), f"{eql[-1]} {eqs[-1]}")
    # (c2) liquidation: funding of 60% of notional per day empties a 1x long
    # on day 3 (1 - 0.6 - 0.6 < 0); equity stays 0 even when price recovers
    o = np.array([100., 100, 100, 100, 300])
    eqL, posL, _ = AL.simulate(o, np.ones(5), 0.0, np.array([0, 0.6, 0.6, 0, 0]))
    check("allocation: equity <= 0 is a liquidation - 0 from then on, no recovery",
          np.allclose(eqL, [1, 0.4, 0, 0, 0]) and posL[-1] == 0, str(eqL))
    # (d) every rule is causal: the full run equals a truncated run on the prefix
    rng = np.random.default_rng(16)
    c = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0005, 0.03, 900))),
                  index=pd.date_range("2018-01-01", periods=900, freq="D", tz="UTC"))
    bad = [n for n, (fn, _) in AL.RULES.items()
           if not np.array_equal(fn(c).to_numpy()[:600], fn(c.iloc[:600]).to_numpy())]
    moved = {n: int((fn(c).diff().fillna(0) != 0).sum()) for n, (fn, _) in AL.RULES.items()}
    check("allocation rules are causal and change position at least once",
          not bad and all(v > 0 for v in moved.values()), f"bad {bad} switches {moved}")
    # (e) Binance spot files moved open_time from ms to microseconds in 2025
    t = AL.to_utc_ms(pd.Series([1735689600000, 1735689600000000]))
    check("spot open_time: ms and microseconds both give 2025-01-01 00:00 UTC",
          list(t) == [pd.Timestamp("2025-01-01", tz="UTC")] * 2, str(list(t)))
    # (e2) non-ASCII symbols (Binance lists 币安人生USDT and others) are
    # percent-encoded in every URL; urlopen refuses raw non-ASCII (_multi Exp 000)
    import datafeed as DF
    urls, saved_get = [], DF._get
    DF._get = lambda url, **k: (urls.append(url), b"<ListBucketResult xmlns='http://s3.amazonaws.com/doc/2006-03-01/'></ListBucketResult>" if "list-type" in url else b"x")[1]
    try:
        import tempfile
        DF.list_keys("data/spot/monthly/klines/币安人生USDT/1d/")
        with tempfile.TemporaryDirectory() as d:
            DF.fetch_zip("data/spot/monthly/klines/币安人生USDT/1d/币安人生USDT-1d-2026-01.zip", Path(d))
    finally:
        DF._get = saved_get
    check("datafeed: listing, download and checksum URLs are ASCII (percent-encoded symbols)",
          len(urls) == 3 and all(u.isascii() for u in urls) and "%E5%B8%81" in urls[0], str(urls[:1]))
    # (f) spot and futures daily zips share names; each market keeps its own file
    import tempfile
    import datafeed as DF
    saved = DF._get, DF._verify_sha256
    DF._get = lambda url, **k: b"spot" if "/spot/" in url else b"perp"
    DF._verify_sha256 = lambda path, key: True
    try:
        with tempfile.TemporaryDirectory() as d:
            name = "BTCUSDT-1d-2020-01.zip"
            ps = DF.fetch_zip(f"data/spot/monthly/klines/BTCUSDT/1d/{name}", Path(d) / "spot_1d")
            pp = DF.fetch_zip(f"data/futures/um/monthly/klines/BTCUSDT/1d/{name}", Path(d) / "perp_1d")
            same = (ps.read_bytes(), pp.read_bytes())
    finally:
        DF._get, DF._verify_sha256 = saved
    check("daily zips: spot and perp files with the same name do not overwrite each other",
          same == (b"spot", b"perp"), str(same))


# --------------------------------------------------------------------------
# 13. Rotation (PLAN.md section 17): universe, instruments, weekly P&L
# --------------------------------------------------------------------------
def test_rotation() -> None:
    print("\n13. rotation: symbol filter, delisting splits, hand-computed weekly P&L, causal universe")
    import rotation as RT
    allsyms = {"BTCUSDT", "SUSHIUSDT", "SUSHIUPUSDT", "JUPUSDT", "BTCDOWNUSDT", "USDCUSDT", "BNBBULLUSDT"}
    got = {x: RT.tradable(x, allsyms) for x in sorted(allsyms)}
    check("rotation: stablecoins and leveraged tokens out, JUP (a coin) in",
          got == {"BNBBULLUSDT": False, "BTCDOWNUSDT": False, "BTCUSDT": True, "JUPUSDT": True,
                  "SUSHIUPUSDT": False, "SUSHIUSDT": True, "USDCUSDT": False}, str(got))
    d = pd.DataFrame({"symbol": "LUNAUSDT", "date": pd.to_datetime(
        ["2022-05-11", "2022-05-12", "2022-05-13", "2022-05-31", "2022-06-01"], utc=True)})
    check("rotation: a >3-day hole starts a new instrument (old LUNA vs new LUNA)",
          list(RT.split_instruments(d)["inst"]) == ["LUNAUSDT"] * 3 + ["LUNAUSDT#1"] * 2)

    # hand-computed weekly P&L: 5 coins growing +2%, +1%, 0, -1%, -2% a day,
    # opens equal the previous close. Small constants so 5 coins qualify.
    saved = {k: getattr(RT, k) for k in ("UNIVERSE_N", "MIN_UNIVERSE", "MIN_AGE_DAYS", "VOLUME_DAYS",
                                         "TOP_FRACTION", "MIN_K")}
    RT.UNIVERSE_N, RT.MIN_UNIVERSE, RT.MIN_AGE_DAYS, RT.VOLUME_DAYS, RT.TOP_FRACTION, RT.MIN_K = 5, 3, 10, 5, 0.2, 1
    try:
        idx = pd.date_range("2024-01-01", periods=60, freq="D", tz="UTC")  # 2024-01-01 is a Monday
        g = {"A": .02, "B": .01, "C": 0.0, "D": -.01, "E": -.02}
        close = pd.DataFrame({k: 100 * (1 + v) ** np.arange(1, 61) for k, v in g.items()}, index=idx)
        opn = close.shift(1).fillna(100.0)
        P = {"open": opn, "close": close, "quote_volume": close * 0 + 1e6}
        w = RT.backtest(P, "spot", 7, 0.01, None, "2024-01-15", "2024-01-30")
        rA = 1.02 ** 7 - 1
        ru = np.mean([(1 + v) ** 7 - 1 for v in g.values()])
        # week 1 (01-15): buy A with all equity -> turnover 1, cost 0.01;
        # week 2 (01-22): A again, weights unchanged after drift -> no cost
        ok = (len(w) == 2 and list(w["held"]) == ["A", "A"]
              and np.isclose(w["net"].iloc[0], rA - 0.01) and np.isclose(w["net"].iloc[1], rA)
              and np.isclose(w["net_universe"].iloc[0], ru - 0.01)
              and np.isclose(w["stat"].iloc[0], (rA - 0.01) - (ru - 0.01)))
        check("rotation: weekly top-k return, turnover cost on drifted weights (hand-computed)",
              ok, w[["held", "net", "net_universe", "turnover"]].round(6).to_string())
        # perp: long A, short E, half the equity each; funding 0.1%/day on A
        # (long pays 0.5 x 0.7%) and 0.2%/day on E (short receives 0.5 x 1.4%)
        fund = pd.DataFrame([{"symbol": c, "date": d, "last_funding_rate": r}
                             for d in idx for c, r in (("A", .001), ("E", .002))])
        wp = RT.backtest(P, "perp", 7, 0.0, fund, "2024-01-15", "2024-01-23")
        rE = 0.98 ** 7 - 1
        check("rotation: perp long/short book with funding (hand-computed)",
              len(wp) == 1 and np.isclose(wp["net"].iloc[0], 0.5 * rA - 0.5 * rE - 0.5 * .007 + 0.5 * .014)
              and wp["held"].iloc[0] == "A,E", wp[["held", "net", "funding"]].to_string())
        # delisting: A's data ends on Wednesday 01-17 -> exit at that close
        P2 = {k: v.copy() for k, v in P.items()}
        for k in P2:
            P2[k].loc["2024-01-18":, "A"] = np.nan
        r_del = RT.week_return(P2, "A", pd.Timestamp("2024-01-15", tz="UTC"), pd.Timestamp("2024-01-22", tz="UTC"))
        check("rotation: a coin delisted mid-week exits at its last close",
              np.isclose(r_del, close.loc["2024-01-17", "A"] / opn.loc["2024-01-15", "A"] - 1), f"{r_del}")
        # causal universe: changing everything after the signal day changes nothing
        s = pd.Timestamp("2024-01-14", tz="UTC")
        P3 = {k: v.copy() for k, v in P.items()}
        P3["quote_volume"].loc["2024-01-15":, "E"] = 1e12
        P3["close"].loc["2024-01-15":, "C"] = 1e6
        check("rotation: the universe on Sunday uses data up to Sunday only",
              list(RT.universe(P, s, 7)) == list(RT.universe(P3, s, 7)))
    finally:
        for k, v in saved.items():
            setattr(RT, k, v)
    lo, hi = RT.block_ci(np.r_[np.full(50, 0.01), np.full(50, 0.03)])
    check("rotation: block bootstrap CI brackets the mean and is reproducible",
          lo < 0.02 < hi and (lo, hi) == RT.block_ci(np.r_[np.full(50, 0.01), np.full(50, 0.03)]), f"{lo} {hi}")


# --------------------------------------------------------------------------
# 14. Exit lab (PLAN.md section 18): the per-trade simulator == the engine
# --------------------------------------------------------------------------
def test_exit_lab() -> None:
    print("\n14. exit lab: every exit, trade for trade against run_backtest")
    import exit_lab as XL
    import indicators as ta
    bars, _, funding = _random_case(31, n=2500)
    funding = funding.assign(last_funding_rate=funding["last_funding_rate"] * 20)  # make it matter
    atr = ta.atr_(bars["high"], bars["low"], bars["close"], XL.ATR_N)
    rng = np.random.default_rng(5)
    picks = rng.choice(np.arange(50, len(bars) - 400), 25, replace=False)
    worst, n_cmp, reasons = 0.0, 0, set()
    for name, ex in XL.EXITS.items():
        for i in picks:
            s = 1.0 if rng.random() < 0.5 else -1.0
            side = np.zeros(len(bars)); side[i] = s
            got = XL.simulate(bars, side, ex, funding)
            d = ex["stop_atr"] * atr.iloc[i]
            sig = pd.DataFrame({"side": side, "stop_dist": np.where(side != 0, d, np.nan),
                                "tp_dist": np.where(side != 0, ex["tp_r"] * d, 0.0),
                                "max_hold": np.where(side != 0, ex["max_hold"], 0.0),
                                "atr": atr.to_numpy(), "be_at": np.where(side != 0, ex["be_r"], 0.0),
                                "trail_at": np.where(side != 0, ex["trail_at_r"], 0.0),
                                "trail_atr": np.where(side != 0, ex["trail_atr"], 0.0)}, index=bars.index)
            res = run_backtest(bars, sig, funding=funding, initial_equity=1e12, max_leverage=1e9,
                               qty_step=1e-12, min_notional=0.0, flat_at_session_end=False)
            if len(res.trades) != 1 or len(got) != 1:
                worst = np.inf
                continue
            worst = max(worst, abs(res.trades[0].r_multiple - got["net_r"].iloc[0]))
            reasons.add(got["reason"].iloc[0])
            n_cmp += 1
    check("exit lab simulator == engine R on every exit (stop, target, time, break-even, trailing, funding)",
          worst < 1e-6 and n_cmp == 6 * 25 and {"stop", "target", "time"} <= reasons,
          f"{n_cmp} trades, max |dR| {worst:.2e}, exits seen {sorted(reasons)}")
    side = XL.random_entries(bars.index)
    check("exit lab entries: about 1 bar in 4, half long, same seed -> same entries",
          abs((side != 0).mean() - XL.ENTRY_P) < 0.03 and abs((side > 0).sum() / (side != 0).sum() - 0.5) < 0.05
          and np.array_equal(side, XL.random_entries(bars.index)))


# --------------------------------------------------------------------------
# 15. ML entry model (PLAN.md section 19): causal features, purge, labels,
#     and the whole pipeline on a planted edge and on pure noise
# --------------------------------------------------------------------------
def _momentum_bars(k: float, seed: int = 3) -> pd.DataFrame:
    """1h bars 2020-01..2025-01 whose drift follows the sign of the last 24h:
    k > 0 plants a real, drift-neutral momentum edge; k = 0 is pure noise."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", "2025-01-10", freq="1h", tz="UTC")
    n = len(idx)
    e, r = rng.normal(0, 0.008, n), np.zeros(n)
    acc = 0.0
    for i in range(n):
        r[i] = e[i] + k * np.sign(acc)
        acc += r[i] - (r[i - 24] if i >= 24 else 0.0)
    c = 30000 * np.exp(np.cumsum(r))
    o = np.r_[c[0], c[:-1]]
    w = np.abs(rng.normal(0, 0.003, n))
    d = pd.DataFrame({"open": o, "high": np.maximum(o, c) * (1 + w), "low": np.minimum(o, c) * (1 - w),
                      "close": c, "volume": rng.lognormal(5, 0.5, n)}, index=idx)
    d["taker_buy_base"] = d["volume"] * 0.5
    return d


def test_ml_entry() -> None:
    print("\n15. ML entry: causal features, purge, labels, planted edge found, noise rejected")
    import contextlib
    import io
    import ml_entry as ME
    import exit_lab as XL
    bars = _momentum_bars(0.0)
    ft = pd.date_range("2020-01-01", "2025-01-10", freq="8h", tz="UTC")
    fund = pd.DataFrame({"calc_time": ft, "last_funding_rate": np.random.default_rng(1).normal(0, 1e-4, len(ft))})
    full = ME.features(bars, fund)
    cut = 20000
    part = ME.features(bars.iloc[:cut], fund)
    same = np.allclose(full.iloc[:cut].to_numpy(float), part.to_numpy(float), equal_nan=True)
    check("ml_entry features are causal (full run == truncated run on the prefix)", same)
    m = ME._span(bars.index, "2020-01-01", "2023-01-01", purge=ME.PURGE)
    last = bars.index[np.flatnonzero(m)[-1]]
    check("ml_entry purge: the last TRAIN row's label window ends inside TRAIN",
          last + pd.Timedelta(hours=ME.PURGE - 1) < pd.Timestamp("2023-01-01", tz="UTC"), str(last))
    lab = ME.labels(bars.iloc[:3000], fund)
    i = 1500
    side = np.zeros(3000); side[i] = 1.0
    one = XL.simulate(bars.iloc[:3000], side, ME.EXIT, fund)
    check("ml_entry labels = the exit lab's simulated net R of that entry",
          np.isclose(lab["long"].iloc[i], one["net_r"].iloc[0]), f"{lab['long'].iloc[i]} {one['net_r'].iloc[0]}")
    check("ml_entry decide: higher side if above threshold, else flat",
          list(ME.decide(np.array([.3, .1, -.2]), np.array([.1, .25, -.1]), 0.2)) == [1.0, -1.0, 0.0])
    with contextlib.redirect_stdout(io.StringIO()):
        noise = ME.evaluate(bars, fund)
        edge = ME.evaluate(_momentum_bars(0.0008), fund)
    check("ml_entry pipeline: a planted momentum edge is found (PASS, both legs > 0, beats random p95)",
          edge["verdict"] == "PASS" and edge["valid"]["long_r"] > 0 and edge["valid"]["short_r"] > 0,
          f"{edge['verdict']} mean {edge['valid']['mean_r']:+.3f} p95 {edge['random_p95']:+.3f}")
    check("ml_entry pipeline: pure noise is not a PASS and does not beat random",
          noise["verdict"] == "REJECT" and "beats_random_p95" in noise["gates_failed"],
          f"{noise['verdict']} mean {noise['valid'].get('mean_r', 0):+.3f} failed {noise['gates_failed']}")
    check("ml_entry: no VALID trade runs into HOLDOUT (VALID window purged)",
          pd.Timestamp(edge["valid_last_exit"]) <= pd.Timestamp(ME.SPLITS["holdout"][0], tz="UTC"),
          str(edge["valid_last_exit"]))
    acc = edge["valid_account"]
    # synthetic prices are far above what 1,000 USDT sizes at a 0.001 step, so
    # skips are expected here; the check is only that the engine run works
    check("ml_entry: the engine account run (reported, not a gate) trades",
          acc["trades"] > 100 and acc["size_skips"] is not None, str(acc))
    oof = edge["oof"]["0.0"]
    check("ml_entry: OOF trade counts include only scored labels",
          oof["trades"] > 0 and oof["mean_r"] is not None, str(oof))


def test_ml_pool() -> None:
    print("\n16. Pooled ML entry: universe from TRAIN only, planted edge found on every coin, noise rejected")
    import contextlib
    import io
    import ml_pool as MP
    # universe: daily rows of five coins
    days = pd.date_range("2020-01-01", "2026-08-31", freq="D", tz="UTC")
    rows = []
    def coin(sym, start, end, vol, gap=None):
        for d in days[(days >= pd.Timestamp(start, tz="UTC")) & (days <= pd.Timestamp(end, tz="UTC"))]:
            if gap and pd.Timestamp(gap[0], tz="UTC") <= d < pd.Timestamp(gap[1], tz="UTC"):
                continue
            rows.append((sym, d, 1.0, 1.0, vol))
    coin("AAAUSDT", "2020-01-01", "2026-08-31", 100.0)
    coin("BBBUSDT", "2020-06-01", "2023-06-30", 90.0)     # delisted in VALID: kept
    coin("CCCUSDT", "2021-06-01", "2026-08-31", 500.0)    # listed too late: out
    coin("DDDUSDT", "2020-01-01", "2022-05-31", 900.0)    # died inside TRAIN: out
    coin("EEEUSDT", "2020-01-01", "2026-08-31", 80.0, gap=("2022-05-20", "2022-09-01"))  # relisted: out
    daily = pd.DataFrame(rows, columns=["symbol", "date", "open", "close", "quote_volume"])
    u = MP.select_universe(daily, n=10)
    names = [x["inst"] for x in u]
    check("ml_pool universe: listed by 2021, trading at TRAIN end, ranked by TRAIN volume; delisted-later kept",
          names == ["AAAUSDT", "BBBUSDT"] and u[1]["end"] == "2023-06-30", str(names))
    later = daily.copy()
    later.loc[later["date"] >= pd.Timestamp("2023-01-01", tz="UTC"), "quote_volume"] = 1e9
    check("ml_pool universe: volume after TRAIN does not change the choice",
          [x["inst"] for x in MP.select_universe(later, n=10)] == names)
    ft = pd.date_range("2020-01-01", "2025-01-10", freq="8h", tz="UTC")
    fund = pd.DataFrame({"calc_time": ft, "last_funding_rate": np.zeros(len(ft))})
    with contextlib.redirect_stdout(io.StringIO()):
        edge = MP.evaluate(MP.prepare({f"C{i}USDT": (_momentum_bars(0.0008, seed=10 + i), fund)
                                       for i in range(3)}), min_coins=3)
        noise = MP.evaluate(MP.prepare({f"N{i}USDT": (_momentum_bars(0.0, seed=20 + i), fund)
                                        for i in range(3)}), min_coins=3)
    check("ml_pool pipeline: a planted edge is found (PASS, all 3 coins beat their random p95)",
          edge["verdict"] == "PASS" and edge["breadth"]["share"] == 1.0,
          f"{edge['verdict']} mean {edge['valid'].get('mean_r', 0):+.3f} failed {edge['gates_failed']}")
    check("ml_pool pipeline: pure noise is not a PASS, fails breadth and random",
          noise["verdict"] == "REJECT" and "beats_random_p95" in noise["gates_failed"]
          and any(g.startswith("breadth") for g in noise["gates_failed"]),
          f"{noise['verdict']} mean {noise['valid'].get('mean_r', 0):+.3f} failed {noise['gates_failed']}")
    with contextlib.redirect_stdout(io.StringIO()):
        one = MP.evaluate(MP.prepare({"E0USDT": (_momentum_bars(0.0008, seed=10), fund),
                                      "N0USDT": (_momentum_bars(0.0, seed=20), fund),
                                      "N1USDT": (_momentum_bars(0.0, seed=21), fund)}), min_coins=3)
    check("ml_pool breadth: an edge on one coin of three is not a PASS",
          one["verdict"] == "REJECT" and any(g.startswith("breadth") for g in one["gates_failed"]),
          f"{one['verdict']} beat {one['breadth']['beat']} failed {one['gates_failed']}")
    check("ml_pool: no VALID trade runs into HOLDOUT",
          pd.Timestamp(edge["valid_last_exit"]) <= pd.Timestamp(MP.SPLITS["holdout"][0], tz="UTC"),
          str(edge["valid_last_exit"]))
    check("ml_pool: alt slippage for alts, the normal one for BTC/ETH",
          MP.slippage("BTCUSDT") == C.SLIPPAGE and MP.slippage("C0USDT") == MP.ALT_SLIPPAGE)


def test_ml_pool2() -> None:
    print("\n17. Pooled ML round 2: cross features causal, 4-day labels, gross control, planted edge found, noise rejected")
    import contextlib
    import io
    import ml_pool2 as M2
    import exit_lab as XL
    ft = pd.date_range("2020-01-01", "2025-01-10", freq="8h", tz="UTC")
    fund = pd.DataFrame({"calc_time": ft, "last_funding_rate": np.zeros(len(ft))})
    coins = {f"C{i}USDT": (_momentum_bars(0.0008, seed=30 + i), fund) for i in range(3)}
    full = M2.cross_features(coins)["C0USDT"]
    cut = 20000
    part = M2.cross_features({c: (b.iloc[:cut], f) for c, (b, f) in coins.items()})["C0USDT"]
    check("ml_pool2 cross features are causal (full run == truncated run on the prefix)",
          np.allclose(full.iloc[:cut].to_numpy(float), part.to_numpy(float), equal_nan=True))
    b = coins["C0USDT"][0]
    lab = M2.labels(b.iloc[:3000], fund, C.SLIPPAGE)
    i = int(np.flatnonzero(M2.decision_mask(b.index[:3000]))[200])
    side = np.zeros(3000); side[i] = -1.0
    one = XL.simulate(b.iloc[:3000], side, M2.EXIT, fund)
    check("ml_pool2 labels: decision bars only, net and gross = the simulated 4-day trade",
          np.isclose(lab["short"].iloc[i], one["net_r"].iloc[0])
          and np.isclose(lab["g_short"].iloc[i], one["gross_r"].iloc[0])
          and lab["long"].iloc[i + 1:i + M2.STEP].isna().all(),
          f"{lab['short'].iloc[i]} {one['net_r'].iloc[0]}")
    with contextlib.redirect_stdout(io.StringIO()):
        edge = M2.evaluate(M2.prepare(coins), grid=M2.GRID[:2], min_coins=3)
        noise = M2.evaluate(M2.prepare({f"N{i}USDT": (_momentum_bars(0.0, seed=40 + i), fund)
                                        for i in range(3)}), grid=M2.GRID[:2], min_coins=3)
    check("ml_pool2 pipeline: a planted edge is found (PASS, gross above the shifted p95)",
          edge["verdict"] == "PASS",
          f"{edge['verdict']} mean {edge['valid'].get('mean_r', 0):+.3f} gross {edge['valid'].get('gross_r', 0):+.3f} "
          f"p95 {edge['shift_gross_p95']} failed {edge['gates_failed']}")
    check("ml_pool2 pipeline: pure noise is not a PASS and its gross does not beat the shifted p95",
          noise["verdict"] == "REJECT" and "gross_beats_shift_p95" in noise["gates_failed"],
          f"{noise['verdict']} gross {noise['valid'].get('gross_r', 0):+.3f} p95 {noise['shift_gross_p95']} "
          f"failed {noise['gates_failed']}")
    check("ml_pool2: no VALID trade runs into HOLDOUT",
          pd.Timestamp(edge["valid_last_exit"]) <= pd.Timestamp(M2.SPLITS["holdout"][0], tz="UTC"),
          str(edge["valid_last_exit"]))


def test_candle_at_level() -> None:
    print("\n18. candle_at_level: hand-built engulfing at yesterday's low, pin at yesterday's high, and misses")
    import recipes as RC
    idx = pd.date_range("2024-01-01", periods=48, freq="1h", tz="UTC")
    o = np.full(48, 105.0); c = np.full(48, 105.0); h = np.full(48, 106.0); l = np.full(48, 104.0)
    l[5] = 100.0    # day 1 low  = 100
    h[9] = 110.0    # day 1 high = 110
    # day 2: a red bar, then a bullish engulfing whose low tags 100.2 (support 100)
    o[30], c[30], h[30], l[30] = 103.0, 101.5, 103.2, 101.3
    o[31], c[31], h[31], l[31] = 101.4, 103.5, 103.6, 100.2
    # day 2: a shooting star whose high tags 109.8 (resistance 110)
    o[40], c[40], h[40], l[40] = 108.0, 107.8, 109.8, 107.7
    b = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 1.0}, index=idx)
    s_any = RC.t_candle_at_level(b, None, pattern="any", level="prev_day", near_atr=0.5)
    s_eng = RC.t_candle_at_level(b, None, pattern="engulfing", level="prev_day", near_atr=0.5)
    s_pin = RC.t_candle_at_level(b, None, pattern="pin", level="prev_day", near_atr=0.5)
    check("candle_at_level: bullish engulfing at yesterday's low -> long on that bar only",
          s_eng[31] == 1.0 and (np.flatnonzero(s_eng) == [31]).all(), str(np.flatnonzero(s_eng)))
    check("candle_at_level: shooting star at yesterday's high -> short (pattern pin)",
          s_pin[40] == -1.0 and s_pin[31] == 0.0, str(np.flatnonzero(s_pin)))
    check("candle_at_level: pattern any = both", s_any[31] == 1.0 and s_any[40] == -1.0
          and int((s_any != 0).sum()) == 2, str(np.flatnonzero(s_any)))
    far = b.copy(); far.iloc[9, far.columns.get_loc("high")] = 120.0; far.iloc[5, far.columns.get_loc("low")] = 90.0
    s_far = RC.t_candle_at_level(far, None, pattern="any", level="prev_day", near_atr=0.5)
    check("candle_at_level: the same candles far from any level -> no signal", not s_far.any(),
          str(np.flatnonzero(s_far)))
    day1 = RC.t_candle_at_level(b.iloc[:24], None, pattern="any", level="prev_day")
    check("candle_at_level: no level on the first day (no completed previous day)", not day1.any())
    # swing level: a pivot low at bar 12 (pivot_len 3) is support for later bars
    o2 = np.full(48, 105.0); c2 = np.full(48, 105.0); h2 = np.full(48, 106.0); l2 = np.full(48, 104.0)
    l2[12] = 100.0
    o2[30], c2[30], h2[30], l2[30] = 103.0, 101.5, 103.2, 101.3
    o2[31], c2[31], h2[31], l2[31] = 101.4, 103.5, 103.6, 100.2
    b2 = pd.DataFrame({"open": o2, "high": h2, "low": l2, "close": c2, "volume": 1.0}, index=idx)
    sw = RC.t_candle_at_level(b2, None, pattern="engulfing", level="swing", pivot_len=3, near_atr=0.5)
    check("candle_at_level: engulfing at a live swing low -> long", sw[31] == 1.0 and int((sw != 0).sum()) == 1,
          str(np.flatnonzero(sw)))
    broke = b2.copy()
    for k in (20, 21):  # two equal lows: a close through the level that is not itself a pivot (ties)
        broke.iloc[k, broke.columns.get_loc("close")] = 99.0
        broke.iloc[k, broke.columns.get_loc("low")] = 98.9
    sb = RC.t_candle_at_level(broke, None, pattern="engulfing", level="swing", pivot_len=3, near_atr=0.5)
    check("candle_at_level: a swing level closed through is dead", sb[31] == 0.0, str(np.flatnonzero(sb)))


def test_stop_diag() -> None:
    print("\n19. stop_diag: planted momentum + tight stops = SHAKEN_OUT, reversed = WRONG_DIRECTION, noise = COIN_FLIP")
    import json as _json
    import tempfile
    import stop_diag as SD

    def case(k, flip, seed):
        bars = _momentum_bars(k, seed=seed)
        lr = np.log(bars["close"]).diff(24).to_numpy()
        rng = np.random.default_rng(seed)
        o, l, h = bars["open"].to_numpy(), bars["low"].to_numpy(), bars["high"].to_numpy()
        win = SD.valid_window()
        lo, hi = np.searchsorted(bars.index, win[0]), np.searchsorted(bars.index, win[1]) - 30
        H, rows_ev = 24, []
        tmp = Path(tempfile.mkdtemp())
        for e in range(8):  # 8 "evaluations" of 150 trades each
            rows = []
            for j in rng.integers(lo, hi, 150):
                side = (1.0 if lr[j - 1] > 0 else -1.0) * (-1 if flip else 1)
                entry, d = o[j], o[j] * 0.003  # tight 0.3% stop: noise hits it often
                stop = entry - side * d
                hit = (l[j:j + H] <= stop).any() if side > 0 else (h[j:j + H] >= stop).any()
                rows.append({"entry_time": bars.index[j], "side": side, "entry_px": entry, "qty": 1.0,
                             "net_pnl": -d, "r_multiple": -1.0, "exit_reason": "stop" if hit else "time"})
            eid = f"e{e}"
            pd.DataFrame(rows).to_csv(tmp / f"{eid}_valid.csv.gz", index=False)
            rows_ev.append({"eval_id": eid, "name": f"case{e}", "tf": 60, "verdict": "REJECT",
                            "valid_trades": 150, "valid_size_skips": 0,
                            "chosen_params": _json.dumps({"max_hold_hours": H})})
        per = SD.diagnose(lambda tf: bars, pd.DataFrame(rows_ev), tmp, win)
        return SD.summarize(per)

    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        good = case(0.0008, False, 51)
        bad = case(0.0008, True, 52)
        flat = case(0.0, False, 53)
    check("stop_diag: right direction + tight stops -> SHAKEN_OUT", good["verdict"] == "SHAKEN_OUT",
          f"{good['verdict']} skill {good['direction_skill']:+.3f} shake {good['shakeout_excess']:+.3f}")
    check("stop_diag: reversed entries -> WRONG_DIRECTION", bad["verdict"] == "WRONG_DIRECTION",
          f"{bad['verdict']} skill {bad['direction_skill']:+.3f}")
    check("stop_diag: noise -> COIN_FLIP", flat["verdict"] == "COIN_FLIP",
          f"{flat['verdict']} skill {flat['direction_skill']:+.3f} ci {flat['ci']['direction_skill']}")


def _level_bars(k: float, seed: int) -> pd.DataFrame:
    """1h bars 2020-01..2025-01. k > 0 plants 'levels hold': after a bar trades
    below the previous UTC day's low, price drifts up by k per bar for 24 bars;
    after one trades above the previous day's high, it drifts down. k = 0 is noise."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", "2025-01-10", freq="1h", tz="UTC")
    n = len(idx)
    o, h, l, c = (np.zeros(n) for _ in range(4))
    px, push, until = 30000.0, 0.0, -1
    day_hi = day_lo = prev_hi = prev_lo = np.nan
    for i in range(n):
        if idx[i].hour == 0:
            prev_hi, prev_lo, day_hi, day_lo = day_hi, day_lo, -np.inf, np.inf
        drift = push if i <= until else 0.0
        r = rng.normal(0, 0.006) + drift
        o[i] = px
        px = px * np.exp(r)
        c[i] = px
        w = abs(rng.normal(0, 0.003, 2))
        h[i], l[i] = max(o[i], c[i]) * (1 + w[0]), min(o[i], c[i]) * (1 - w[1])
        if k > 0 and np.isfinite(prev_lo) and l[i] < prev_lo and i > until:
            push, until = k, i + 24
        elif k > 0 and np.isfinite(prev_hi) and h[i] > prev_hi and i > until:
            push, until = -k, i + 24
        day_hi, day_lo = max(day_hi, h[i]), min(day_lo, l[i])
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c}, index=idx)


def test_level_limit() -> None:
    print("\n20. level_limit: hand-computed fills, gaps, same-bar stop, expiry; planted levels found, noise rejected")
    import contextlib
    import io
    import level_limit as LL
    import indicators as ta
    t = np.array(["2024-01-01T00", "2024-01-01T01", "2024-01-01T02", "2024-01-01T03", "2024-01-01T04"],
                 dtype="datetime64[ns]")

    def bars(o2, l2):
        o = np.array([103, 102, o2, 101, 104.0]); h = np.array([103.5, 102.5, 101.2, 104.5, 104.5])
        l = np.array([102.5, 101, l2, 100.3, 103.5]); c = np.array([103, 101.5, 100.5, 104, 104.0])
        return o, h, l, c
    order = pd.DataFrame({"bar": [0], "side": [1.0], "limit": [100.0], "dist_atr": [1.5], "atr": [2.0]})
    fm, ft, sl = C.FEE_MAKER, C.FEE_TAKER, C.SLIPPAGE
    r = LL.simulate_orders(*bars(101, 99.8), order, 1.0, 2.0, t)
    want = 2.0 - (100 * fm + 104 * fm) / 2
    check("level_limit: limit fills at the level, target is a maker exit (hand-computed)",
          len(r) == 1 and r["reason"].iloc[0] == "target" and np.isclose(r["net_r"].iloc[0], want),
          f"{r.to_dict('records')} want {want}")
    r = LL.simulate_orders(*bars(99.5, 99.4), order, 1.0, 2.0, t)
    check("level_limit: a bar that opens below the limit fills at the open",
          len(r) == 1 and np.isclose(r["gross_r"].iloc[0], (103.5 - 99.5) / 2), r.to_dict("records"))
    r = LL.simulate_orders(*bars(101, 97.5), order, 1.0, 2.0, t)
    px_adj = 98 * (1 - sl)
    want = (px_adj - 100) / 2 - (100 * fm + px_adj * ft) / 2
    check("level_limit: filled and stopped on the same bar -> stopped (pessimistic, hand-computed)",
          len(r) == 1 and r["reason"].iloc[0] == "stop" and np.isclose(r["net_r"].iloc[0], want),
          f"{r.to_dict('records')} want {want}")
    r = LL.simulate_orders(*bars(97.0, 96.8), order, 1.0, 2.0, t)
    check("level_limit: a gap fill below the stop exits at the fill (gross 0, not a gain)",
          len(r) == 1 and np.isclose(r["gross_r"].iloc[0], 0.0), r.to_dict("records"))
    r = LL.simulate_orders(*bars(101, 99.8), order, 1.0, 2.0, t, expiry=1)
    check("level_limit: an order not reached before expiry never fills", len(r) == 0)
    b = _level_bars(0.0, 7).iloc[:6000]
    atr = ta.atr_(b["high"], b["low"], b["close"], 14).to_numpy(float)
    for kind in ("prev_day", "swing"):
        full = LL.place_orders(b, kind, atr)
        part = LL.place_orders(b.iloc[:4000], kind, atr[:4000])
        check(f"level_limit: {kind} orders are causal (full run == truncated run on the prefix)",
              full[full["bar"] < 3999].reset_index(drop=True).equals(part[part["bar"] < 3999].reset_index(drop=True)))
    grid = [dict(level="prev_day", stop_atr=1.0, tp_r=2.0)]
    with contextlib.redirect_stdout(io.StringIO()):
        edge = LL.evaluate(_level_bars(0.0015, 11), None, grid=grid, n_control=60)
        noise = LL.evaluate(_level_bars(0.0, 12), None, grid=grid, n_control=60)
    check("level_limit pipeline: planted 'levels hold' -> PASS, above the control p95",
          edge["verdict"] == "PASS",
          f"{edge['verdict']} mean {edge['valid'].get('mean_r', 0):+.3f} p95 {edge['control']['valid']['p95']:+.3f} "
          f"failed {edge['gates_failed']}")
    check("level_limit pipeline: noise -> REJECT, not above the control p95",
          noise["verdict"] == "REJECT" and "beats_control_p95_valid" in noise["gates_failed"],
          f"{noise['verdict']} mean {noise['valid'].get('mean_r', 0):+.3f} failed {noise['gates_failed']}")


def test_premium() -> None:
    print("\n21. Coinbase premium: parse, causal attach (hour H used only after H+1h), blocks")
    import datafeed as DF
    import experiment as E
    import recipes as RC
    rows = [[1577923200, 1, 2, 1.5, 7181.99, 9.0], [1577919600, 1, 2, 1.5, 7174.33, 8.0],
            [1577919600, 1, 2, 1.5, 7174.33, 8.0]]
    p = DF.parse_coinbase(rows)
    check("premium: Coinbase rows parsed, sorted, de-duplicated",
          len(p) == 2 and p["time"].iloc[0] == pd.Timestamp("2020-01-01 23:00", tz="UTC")
          and p["cb_close"].iloc[1] == 7181.99)
    hrs = pd.date_range("2024-01-01", periods=6, freq="1h", tz="UTC")
    prem = pd.DataFrame({"time": hrs, "premium": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]})
    b1 = pd.DataFrame({"close": 1.0}, index=hrs)
    a1 = E.attach_premium(b1, prem, 60, "cb_prem")["cb_prem"].to_numpy()
    check("premium: a 1h bar sees the PREVIOUS hour (the current one closes 2 min too late)",
          np.isnan(a1[0]) and list(a1[1:]) == [1.0, 2.0, 3.0, 4.0, 5.0], str(a1))
    q = pd.date_range("2024-01-01", periods=8, freq="15min", tz="UTC")
    a15 = E.attach_premium(pd.DataFrame({"close": 1.0}, index=q), prem, 15, "cb_prem")["cb_prem"].to_numpy()
    check("premium: 15m bars before 01:02 see nothing, from the 01:15 close on they see hour 00",
          np.isnan(a15[:4]).all() and (a15[4:] == 1.0).all(), str(a15))
    far = prem.copy(); far["time"] = far["time"] - pd.Timedelta(hours=10)
    a_old = E.attach_premium(b1, far, 60, "cb_prem")["cb_prem"].to_numpy()
    check("premium: a value older than 3h is NaN, never stale", np.isnan(a_old).all(), str(a_old))
    n = 400
    x = np.r_[np.zeros(300), np.full(100, 0.01)] + np.random.default_rng(2).normal(0, 1e-4, n)
    bb = pd.DataFrame({"close": 1.0, "cb_prem": x}, index=pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC"))
    sig = RC.t_premium_cross(bb, None, n=168, z=4.0)  # z 4: plain noise rarely crosses it
    check("premium_cross: a jump in the premium -> one long on the jump bar",
          sig[300] == 1.0 and int((sig != 0).sum()) == 1, str(np.flatnonzero(sig)))
    try:
        RC.t_premium_cross(bb.drop(columns="cb_prem"), None)
        refused = False
    except ValueError:
        refused = True
    check("premium blocks refuse bars without the premium column", refused)


def test_premium_confirm() -> None:
    print("\n22. premium_confirm: pre-registered bars on synthetic records (30m counts, 4h pooled CI)")
    import json as _json
    import tempfile
    import premium_confirm as PC
    import config as C

    def make(root, coin, m30, base30, m4, n4=40, seed=0, verdict30="REJECT"):
        d = root / "results" / coin
        (d / "eval_trades").mkdir(parents=True, exist_ok=True)
        (d / "baseline").mkdir(parents=True, exist_ok=True)
        rng = np.random.default_rng(seed)
        rows = []
        for tf, m, v in ((30, m30, verdict30), (240, m4, "WATCH")):
            eid = f"{coin}{tf}"
            rows.append({"eval_id": eid, "name": PC.NAMES[tf], "tf": tf, "verdict": v, "valid_trades": n4,
                         "valid_mean_r": m, "valid_ci_lo": m - 0.2, "valid_ci_hi": m + 0.2})
            et = pd.date_range("2023-01-02", periods=n4, freq="5D", tz="UTC")
            pd.DataFrame({"entry_time": et, "side": np.where(np.arange(n4) % 2, 1, -1),
                          "r_multiple": m + rng.normal(0, 0.3, n4)}).to_csv(d / "eval_trades" / f"{eid}_valid.csv.gz",
                                                                             index=False)
        (d / "baseline" / f"{coin}30.json").write_text(_json.dumps({"verdict": base30}))
        pd.DataFrame(rows).to_csv(d / "evaluations.csv", index=False)

    good = Path(tempfile.mkdtemp())
    for i, c in enumerate(PC.CONFIRM):
        make(good, c, 0.05, "SKILL" if i < 6 else "DRIFT", 0.3, seed=i)
    rg = PC.evaluate(good)
    check("premium_confirm: 10/10 positive, 6 SKILL, 4h pooled +0.3 -> LEAD_CONFIRMED on both clocks",
          rg["verdict"] == "LEAD_CONFIRMED" and rg["m30"]["confirmed"] and rg["h4"]["confirmed"]
          and rg["h4"]["pooled_trades"] == 400, str({k: rg[k] for k in ("m30", "h4")}))
    bad = Path(tempfile.mkdtemp())
    for i, c in enumerate(PC.CONFIRM):
        make(bad, c, 0.05 if i < 6 else -0.05, "SKILL", -0.02 if i % 2 else 0.02, seed=i,
             verdict30="UNSIZABLE" if i == 0 else "REJECT")
    rb = PC.evaluate(bad)
    check("premium_confirm: 5 usable positive (one UNSIZABLE) and a ~0 pooled 4h -> NOT_CONFIRMED",
          rb["verdict"] == "NOT_CONFIRMED" and rb["m30"]["positive"] == 5 and not rb["h4"]["confirmed"],
          str({k: rb[k] for k in ("m30", "h4")}))
    check("premium_confirm: the CONFIRM coins are configured and exclude BTC/ETH (already seen)",
          all(c in C.SYMBOL_SPECS for c in PC.CONFIRM) and not {"BTCUSDT", "ETHUSDT"} & set(PC.CONFIRM))


# --------------------------------------------------------------------------
# 23. ML that decides entry and exit, no clock (PLAN.md section 27)
# --------------------------------------------------------------------------
def test_ml_hold() -> None:
    print("\n23. ML hold: hysteresis policy, causal entry bar, simulator == engine, planted edge found, noise rejected")
    import contextlib
    import io
    import indicators as ta
    import ml_hold as MH
    p = np.array([0.0, 2.0, 0.5, -0.1, 0.5, -2.0, -0.6, 0.1, np.nan, 3.0])
    e = np.full(len(p), 1.0)
    check("ml_hold policy 'flip': enter past e_in, hold through weak forecasts, exit when the sign turns, reverse past -e_in",
          list(MH.policy(p, e, "flip")) == [0, 1, 1, 0, 0, -1, -1, 0, 0, 1])
    check("ml_hold policy 'half': exit when the forecast falls under e_in / 2",
          list(MH.policy(p, e, "half")) == [0, 1, 1, 0, 0, -1, -1, 0, 0, 1])
    p2 = np.array([0.0, 2.0, 0.7, 0.3, -0.7, -2.0, -0.4])
    check("ml_hold policy 'flip' vs 'half' differ only on the exit bar",
          list(MH.policy(p2, np.ones(7), "flip")) == [0, 1, 1, 1, 0, -1, -1]
          and list(MH.policy(p2, np.ones(7), "half")) == [0, 1, 1, 0, 0, -1, 0])
    rng = np.random.default_rng(4)
    x = rng.normal(size=500)
    check("ml_hold entry bar is causal (full run == truncated run on the prefix) and warms up",
          np.allclose(MH.entry_bar(x, 0.75)[:300], MH.entry_bar(x[:300], 0.75), equal_nan=True)
          and np.isnan(MH.entry_bar(x, 0.75)[MH.MIN_ROLL - 2]))

    bars, _, funding = _random_case(53, n=3000)
    funding = funding.assign(last_funding_rate=funding["last_funding_rate"] * 20)
    atr = ta.atr_(bars["high"], bars["low"], bars["close"], MH.ATR_N).to_numpy(float)
    n = len(bars)
    dec = np.zeros(n, bool); dec[40::4] = True; dec[-1] = False
    path = np.zeros(n); state = 0.0
    for i in np.flatnonzero(dec):
        r = rng.random()
        state = 1.0 if r < 0.08 else -1.0 if r < 0.16 else 0.0 if r < 0.22 else state
        path[i] = state
    tgt = np.where(dec, path, np.nan)
    got = MH.simulate(bars, tgt, atr, funding, stop_atr=2.0)
    sig = pd.DataFrame({"side": np.where(dec, path, 0.0), "stop_dist": 2.0 * atr, "tp_dist": 0.0,
                        "max_hold": 100000.0, "atr": atr,
                        "exit_long": (dec & (path <= 0)).astype(float),
                        "exit_short": (dec & (path >= 0)).astype(float)}, index=bars.index)
    res = run_backtest(bars, sig, funding=funding, initial_equity=1e12, max_leverage=1e9, qty_step=1e-12,
                       min_notional=0.0, flat_at_session_end=False)
    eng = [t for t in res.trades]
    k = min(len(eng), len(got))
    same_t = all(eng[i].entry_time == got["entry_time"].iloc[i] for i in range(k))
    worst = max([abs(eng[i].r_multiple - got["net_r"].iloc[i]) for i in range(k - 1)] or [np.inf])
    reasons = set(got["reason"])
    check("ml_hold simulator == engine (exit signals, reversals, stops, funding), trade for trade",
          len(eng) == len(got) and same_t and worst < 1e-6 and {"signal", "stop"} <= reasons,
          f"engine {len(eng)} sim {len(got)} max |dR| {worst:.2e} exits {sorted(reasons)}")

    ft = pd.date_range("2020-01-01", "2025-01-10", freq="8h", tz="UTC")
    fund = pd.DataFrame({"calc_time": ft, "last_funding_rate": np.zeros(len(ft))})
    with contextlib.redirect_stdout(io.StringIO()):
        edge = MH.evaluate(MH.prepare({f"C{i}USDT": (_momentum_bars(0.0008, seed=60 + i), fund) for i in range(3)}),
                           grid=MH.GRID[:1], min_coins=3)
        noise = MH.evaluate(MH.prepare({f"N{i}USDT": (_momentum_bars(0.0, seed=70 + i), fund) for i in range(3)}),
                            grid=MH.GRID[:1], min_coins=3)
    check("ml_hold pipeline: a planted edge is found (PASS, timing above the shifted p95)",
          edge["verdict"] == "PASS",
          f"{edge['verdict']} mean {edge['valid'].get('mean_r', 0):+.3f} timing {edge['timing']} "
          f"p95 {edge['shift_p95']} hold {edge['valid'].get('avg_hold_h')} failed {edge['gates_failed']}")
    check("ml_hold pipeline: pure noise is not a PASS and its timing does not beat the shifted p95",
          noise["verdict"] == "REJECT" and "timing_beats_shift_p95" in noise["gates_failed"],
          f"{noise['verdict']} timing {noise['timing']} p95 {noise['shift_p95']} failed {noise['gates_failed']}")
    check("ml_hold: no VALID trade runs into HOLDOUT, and no trade is closed by a clock",
          pd.Timestamp(edge["valid_last_exit"]) < pd.Timestamp(MH.SPLITS["holdout"][0], tz="UTC")
          and "time" not in (edge["valid"].get("exit_mix") or {}),
          f"{edge['valid_last_exit']} {edge['valid'].get('exit_mix')}")


# --------------------------------------------------------------------------
# 24. Walk-forward, multi-timeframe ML (PLAN.md section 28)
# --------------------------------------------------------------------------
def _agg(b: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Synthetic higher-timeframe bars for the TEST only (research never resamples)."""
    return b.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
         "taker_buy_base": "sum"}).dropna()


def test_ml_wf() -> None:
    print("\n24. Walk-forward ML: closed-bar multi-timeframe alignment, refits use the past only, planted edge found, noise rejected")
    import contextlib
    import io
    import ml_wf as WF
    b1 = _momentum_bars(0.0, seed=81).iloc[:3000]
    b4, bd = _agg(b1, "4h"), _agg(b1, "1D")
    for main, tfm, other, tfo in ((b1, 60, b4, 240), (b1, 60, bd, 1440), (bd, 1440, b1, 60), (b4, 240, bd, 1440)):
        pos = WF.asof_positions(main.index, tfm, other.index, tfo)
        mc = main.index + pd.Timedelta(minutes=tfm)
        oc = other.index + pd.Timedelta(minutes=tfo)
        ok = pos >= 0
        closed = bool((oc[pos[ok]] <= mc[ok]).all())
        latest = bool(all(p + 1 >= len(oc) or oc[p + 1] > m for p, m in zip(pos[ok], mc[ok])))
        check(f"ml_wf multi-timeframe: a {tfm}m bar sees only {tfo}m bars closed by its own close, and the latest one",
              closed and latest and ok.mean() > 0.9)
    f = WF.mtf_features(b1, 60, b4, 240)
    i = 1000
    j = WF.asof_positions(b1.index[i:i + 1], 60, b4.index, 240)[0]
    import ml_entry as ME
    part = ME.features(b4.iloc[:j + 1], None).iloc[-1]
    check("ml_wf multi-timeframe features: the row equals the other timeframe's features computed on bars up to that closed bar",
          np.allclose(f.iloc[i][[c for c in f.columns if c.startswith("h4_ret_")]].to_numpy(float),
                      part[[c for c in part.index if c.startswith("ret_")]].to_numpy(float), equal_nan=True))

    ft = pd.date_range("2020-01-01", "2025-01-10", freq="8h", tz="UTC")
    fund = pd.DataFrame({"calc_time": ft, "last_funding_rate": np.zeros(len(ft))})

    def by_tf(k, seeds):
        out = {60: {}, 240: {}}
        for n, sd in seeds:
            b = _momentum_bars(k, seed=sd)
            out[60][n], out[240][n] = (b, fund), (_agg(b, "4h"), fund)
        return out
    with contextlib.redirect_stdout(io.StringIO()):
        Pe = WF.prepare(by_tf(0.0008, [(f"C{i}USDT", 90 + i) for i in range(3)]), 60)
        edge = WF.evaluate(Pe, 60, grid=WF.GRID[:1], min_coins=3, step=3, keep=True)
        noise = WF.evaluate(WF.prepare(by_tf(0.0, [(f"N{i}USDT", 95 + i) for i in range(3)]), 60), 60,
                            grid=WF.GRID[:1], min_coins=3, step=3)
    past = all(pd.Timestamp(r["last_train_label_end"]) < pd.Timestamp(r["month"], tz="UTC") for r in edge["refits"])
    check("ml_wf refits: every training label ends before the month it predicts",
          past and len(edge["refits"]) >= 12, f"{len(edge['refits'])} refits")
    check("ml_wf features include the other timeframe (h4_ columns) when trading 1h",
          any(c.startswith("h4_") for c in Pe["C0USDT"]["X"].columns))
    check("ml_wf pipeline: a planted edge is found (PASS, timing above the shifted p95)",
          edge["verdict"] == "PASS",
          f"{edge['verdict']} mean {edge['valid'].get('mean_r', 0):+.3f} timing {edge['valid'].get('timing')} "
          f"p95 {edge['valid'].get('shift_p95')} failed {edge['gates_failed']}")
    check("ml_wf pipeline: pure noise is not a PASS and its timing does not beat the shifted p95",
          noise["verdict"] == "REJECT" and "timing_beats_shift_p95" in noise["gates_failed"],
          f"{noise['verdict']} timing {noise['valid'].get('timing')} p95 {noise['valid'].get('shift_p95')} "
          f"failed {noise['gates_failed']}")
    tr = edge.get("_trades")
    ok_why = tr is not None and len(tr) > 0
    if ok_why:
        import json as _json
        e = tr.dropna(subset=["entry_why"])
        good_side = bool(((e["side"] > 0) == (e["entry_pred"].astype(float) > 0)).all())
        above = bool((e["entry_pred"].astype(float).abs() >= e["entry_bar"].astype(float) - 1e-9).all())
        sig = tr[tr["reason"] == "signal"]
        n_why = all(len(_json.loads(w)) == WF.TOP_WHY for w in e["entry_why"])
        ok_why = len(e) > 0.9 * len(tr) and good_side and above and n_why and sig["exit_why"].notna().mean() > 0.9
    check("ml_wf WHY: every opening decision is explained (forecast on the trade's side, past the entry bar, 3 features); signal exits too",
          ok_why)
    # Exp 020: frozen zero-volume bars (a halted, then delisted contract) must not reach a label,
    # a forecast or an entry, and must not blow up the R of a trade
    bz = _momentum_bars(0.0008, seed=99).copy()
    k0, k1, kend = 20000, 21500, len(bz) - 3000
    for lo_, hi_ in ((k0, k1), (kend, len(bz))):
        px = bz["close"].iloc[lo_ - 1]
        bz.iloc[lo_:hi_, [bz.columns.get_loc(x) for x in ("open", "high", "low", "close")]] = px
        bz.iloc[lo_:hi_, bz.columns.get_loc("volume")] = 0.0
        bz.iloc[lo_:hi_, bz.columns.get_loc("taker_buy_base")] = 0.0
    with contextlib.redirect_stdout(io.StringIO()):
        Pz = WF.prepare({60: {"ZUSDT": (bz, fund), "C0USDT": (_momentum_bars(0.0008, seed=90), fund)}}, 60)
        tz = WF.evaluate(Pz, 60, grid=WF.GRID[:1], min_coins=1, step=3, keep=True)["_trades"]
    z = Pz["ZUSDT"]
    yz = z["y"].to_numpy()
    dead_rows = np.zeros(len(yz), bool); dead_rows[k0 - WF.H_BARS - 2:k1] = True
    zt = tz[tz["coin"] == "ZUSDT"]
    check("ml_wf zero-volume bars (Exp 020): dead tail cut, no label touches a dead bar, all labels finite, "
          "no entry on a dead bar, every trade's R bounded",
          len(z["bars"]) == kend and np.isnan(yz[k0 - 1:k1]).all() and np.isfinite(yz[np.isfinite(yz)]).all()
          and not z["tradable"][k0:k1].any()
          and not ((zt["entry_time"] >= bz.index[k0]) & (zt["entry_time"] <= bz.index[k1 - 1])).any()
          and tz["net_r"].abs().max() < 50,
          f"bars {len(z['bars'])} vs {kend}, max |R| {tz['net_r'].abs().max():.2f}, ZUSDT trades {len(zt)}")
    check("ml_wf: no VALID trade runs into HOLDOUT, no clock exit, one holdout timeframe by the TRAIN rule",
          pd.Timestamp(edge["valid"]["last_exit"]) < pd.Timestamp(WF.WINDOWS["holdout"][0], tz="UTC")
          and "time" not in (edge["valid"].get("exit_mix") or {})
          and WF.holdout_choice({60: {"tf": 60, "verdict": "PASS", "train_wf_best": {"mean_r": 0.01}},
                                 240: {"tf": 240, "verdict": "PASS", "train_wf_best": {"mean_r": 0.03}},
                                 1440: {"tf": 1440, "verdict": "REJECT", "train_wf_best": {"mean_r": 0.09}}}) == 240)


# --------------------------------------------------------------------------
# 25. Walk-forward ML with spot history from 2017 (PLAN.md section 29)
# --------------------------------------------------------------------------
def test_ml_wf2() -> None:
    print("\n25. ML walk-forward with spot history: universe rule, trains on spot before perps exist, trades only on perp bars")
    import contextlib
    import io
    import ml_wf2 as W2
    days = pd.date_range("2017-08-01", "2023-01-01", freq="1D", tz="UTC")
    def daily(sym, start, vol=1e6):
        d = days[days >= pd.Timestamp(start, tz="UTC")]
        return pd.DataFrame({"symbol": sym, "date": d, "open": 1.0, "close": 1.0, "quote_volume": vol})
    spot = pd.concat([daily("AUSDT", "2017-09-01"), daily("BUSDT", "2019-03-01"), daily("CUSDT", "2017-09-01")])
    perp = pd.concat([daily("AUSDT", "2020-03-01", 5e6), daily("BUSDT", "2020-03-01", 9e6), daily("CUSDT", "2020-03-01", 1e6)])
    uni = W2.select_universe(perp, spot, n=10)
    check("ml_wf2 universe: only coins whose spot traded by 2018-01-01, ranked by perp TRAIN volume",
          [u["symbol"] for u in uni] == ["AUSDT", "CUSDT"], str([u["symbol"] for u in uni]))
    ft = pd.date_range("2020-01-01", "2025-01-10", freq="8h", tz="UTC")
    fund = pd.DataFrame({"calc_time": ft, "last_funding_rate": np.zeros(len(ft))})

    def coins(k, seeds):
        out = {60: {}}
        for n, sd in seeds:
            b = _momentum_bars(k, seed=sd)
            sp = b.copy()
            sp.index = sp.index - pd.Timedelta(days=730)                 # spot history two years longer
            sp = pd.concat([sp[sp.index < b.index[0]], b])
            out[60][n] = {"spot": sp, "perp": b * 1.0005, "fund": fund}  # perp: same path, a small basis
        return out
    with contextlib.redirect_stdout(io.StringIO()):
        Pe = W2.prepare(coins(0.0008, [(f"C{i}USDT", 110 + i) for i in range(3)]), 60)
        edge = __import__("ml_wf").evaluate(Pe, 60, grid=__import__("ml_wf").GRID[:1], min_coins=3, step=3, keep=True)
        noise = __import__("ml_wf").evaluate(W2.prepare(coins(0.0, [(f"N{i}USDT", 120 + i) for i in range(3)]), 60), 60,
                                             grid=__import__("ml_wf").GRID[:1], min_coins=3, step=3)
    z = Pe["C0USDT"]
    pre = z["X"].index < pd.Timestamp("2020-01-01", tz="UTC")
    rows0 = int(edge["refits"][0]["train_rows"])
    check("ml_wf2 trains on spot rows from before the perp existed, but never forecasts or trades there",
          np.isfinite(z["y"][pre]).sum() > 10000 and not z["tradable"][pre].any() and rows0 > 3 * 17000,
          f"spot label rows before perps {int(np.isfinite(z['y'][pre]).sum())}, first refit rows {rows0}")
    t = edge["_trades"]
    tb = z["tbars"]
    k = tb.index.get_indexer(t[t["coin"] == "C0USDT"]["entry_time"])
    fills = t[t["coin"] == "C0USDT"]["entry_px"].to_numpy() / tb["open"].to_numpy()[k]
    check("ml_wf2 trades fill on the PERP bars (entry = perp open +/- slippage), none before 2021",
          (k >= 0).all() and np.allclose(np.abs(fills - 1.0), __import__("ml_pool").slippage("C0USDT"), atol=1e-9)
          and t["entry_time"].min() >= pd.Timestamp("2021-01-01", tz="UTC"))
    check("ml_wf2 pipeline: a planted edge is found (PASS), pure noise is not (timing gate fails)",
          edge["verdict"] == "PASS" and noise["verdict"] == "REJECT" and "timing_beats_shift_p95" in noise["gates_failed"],
          f"edge {edge['verdict']} {edge['gates_failed']} / noise {noise['verdict']} {noise['gates_failed']}")


# --------------------------------------------------------------------------
# 26. Walk-forward ML, section 28's coins with all their spot history (PLAN.md section 30)
# --------------------------------------------------------------------------
def test_ml_wf3() -> None:
    print("\n26. ML walk-forward, each coin's own spot history: source rule, mixed coins, same universe as section 28")
    import contextlib
    import io
    import json as _json
    import ml_wf2 as W2
    import ml_wf3 as W3
    b = _momentum_bars(0.0008, seed=130)
    perp = b[b.index >= pd.Timestamp("2021-01-01", tz="UTC")]
    early, late = b.copy(), b[b.index >= pd.Timestamp("2022-01-01", tz="UTC")]
    dead = b.assign(volume=0.0)
    sp_hist, sp_src = W3.history_source(early, perp)
    gone = b[b.index < pd.Timestamp("2022-06-01", tz="UTC")]              # spot delisted before VALID (HNT, Exp 028)
    gone_hist, gone_src = W3.history_source(gone, perp)
    check("ml_wf3 history source: spot before the perp, then the perp itself (splice); perp only when no earlier spot",
          sp_src == "splice" and sp_hist.index[0] < perp.index[0] and sp_hist.loc[perp.index].equals(perp)
          and sp_hist.index.is_unique and W3.history_source(None, perp)[1] == "perp"
          and W3.history_source(late, perp)[1] == "perp" and W3.history_source(dead, perp)[1] == "perp"
          and W3.history_source(b.iloc[:0], perp)[1] == "perp")
    check("ml_wf3 history source (Exp 028): a spot pair delisted before VALID still leaves the whole perp window",
          gone_src == "splice" and gone_hist.index[-1] == perp.index[-1] and gone_hist.loc[perp.index].equals(perp))
    ft = pd.date_range("2020-01-01", "2025-01-10", freq="8h", tz="UTC")
    fund = pd.DataFrame({"calc_time": ft, "last_funding_rate": np.zeros(len(ft))})
    by = {60: {"SUSDT": {"spot": W3.history_source(early, perp)[0], "perp": perp * 1.0005, "fund": fund},
               "PUSDT": {"spot": W3.history_source(None, _momentum_bars(0.0008, seed=131).loc["2021":])[0],
                         "perp": _momentum_bars(0.0008, seed=131).loc["2021":], "fund": fund}}}
    by[60]["GUSDT"] = {"spot": gone_hist, "perp": perp, "fund": fund}
    with contextlib.redirect_stdout(io.StringIO()):
        P = W2.prepare(by, 60)
        r = __import__("ml_wf").evaluate(P, 60, grid=__import__("ml_wf").GRID[:1], min_coins=1, step=3, keep=True)
    lo, hi, _ = __import__("ml_hold")._window(P, "GUSDT", "2023-01-01", "2025-01-01")
    check("ml_wf3 (Exp 028): the full pipeline runs with a coin whose spot ended early, and its VALID window is whole",
          hi - lo > 15000 and len(P["GUSDT"]["tbars"].iloc[lo:hi]) == hi - lo and (r["_trades"]["coin"] == "GUSDT").any(),
          f"window {hi - lo}, GUSDT trades {(r['_trades']['coin'] == 'GUSDT').sum()}")
    s_pre = P["SUSDT"]["X"].index[0] < pd.Timestamp("2021-01-01", tz="UTC")
    p_pre = P["PUSDT"]["X"].index[0] >= pd.Timestamp("2021-01-01", tz="UTC")
    no_trade_pre = not P["SUSDT"]["tradable"][P["SUSDT"]["X"].index < pd.Timestamp("2021-01-01", tz="UTC")].any()
    check("ml_wf3 mixed coins: a spot coin's rows start before its perp (not tradable there), a perp-only coin starts at its perp",
          s_pre and p_pre and no_trade_pre)
    src = _json.loads(W3.SOURCE_UNIVERSE.read_text()) if W3.SOURCE_UNIVERSE.exists() else None
    check("ml_wf3 universe source is section 28's universe_v2.json (47 coins)", src is not None and len(src) == 47,
          str(None if src is None else len(src)))


# --------------------------------------------------------------------------
# 27. Portfolio layer on section 30's 1h model (PLAN.md section 31)
# --------------------------------------------------------------------------
def test_ml_port() -> None:
    print("\n27. ML portfolio layer: agreement filter, confidence size, risk cap, weekly account, planted edge / noise")
    import contextlib
    import io
    import ml_port as MP_
    import ml_wf as WF_
    import ml_wf2 as W2
    d = np.array([0, 1, 1, 0, -1, -1, 1, 1, 0], float)
    o = np.array([1, -1, 1, 1, np.nan, -1, 1, 1, 1], float)
    check("ml_port agreement: a new side opens only when the other forecast agrees; holding and exits untouched",
          list(MP_.agree_filter(d, o)) == [0, 0, 1, 0, 0, -1, 1, 1, 0])
    check("ml_port confidence weight: 0.5 at the entry bar, 0.75 at 1.5x, 1.0 at 2x and above, 0.5 if unknown",
          np.allclose(MP_.conf_weight(np.array([1.0, 1.5, 2.0, 3.0, np.nan])), [0.5, 0.75, 1.0, 1.0, 0.5]))
    T = lambda h: pd.Timestamp("2023-01-02", tz="UTC") + pd.Timedelta(hours=h)
    tr = pd.DataFrame({"entry_time": [T(0), T(1), T(2), T(3), T(50)], "exit_time": [T(10), T(10), T(10), T(10), T(60)],
                       "side": [1.0, 1.0, 1.0, -1.0, 1.0], "net_r": [1.0, -1.0, 2.0, 0.5, 1.0],
                       "conf": [2.0, 1.0, 1.5, 2.0, 2.0], "coin": ["A", "B", "C", "D", "A"]})
    s1 = MP_.size_trades(tr, "flat", 0.025)
    s2 = MP_.size_trades(tr, "conf", None)
    s3 = MP_.size_trades(tr, "flat", 0.02)
    check("ml_port risk cap: open same-side risk never exceeds the cap; a short is not limited by longs; room reopens after exits",
          np.allclose(s1["risk"], [0.01, 0.01, 0.005, 0.01, 0.01]) and len(s3) == 4
          and np.allclose(s3["risk"], [0.01, 0.01, 0.01, 0.01]) and list(s3["coin"]) == ["A", "B", "D", "A"])
    check("ml_port confidence sizing and return = net R x risk",
          np.allclose(s2["risk"], [0.01, 0.005, 0.0075, 0.01, 0.01]) and np.allclose(s2["ret"], s2["net_r"] * s2["risk"]))
    w = MP_.weekly(s1, "2023-01-02", "2023-01-30")
    acc = MP_.account(s1, "2023-01-02", "2023-01-30")
    check("ml_port weekly account: every week counted (empty weeks 0), sums match, drawdown from the running total",
          len(w) == 4 and np.isclose(w.sum(), s1["ret"].sum()) and (w.iloc[1:] == 0).sum() >= 2
          and acc["weeks"] == 4 and 0 <= acc["max_dd"] < 0.05)

    ft = pd.date_range("2020-01-01", "2025-01-10", freq="8h", tz="UTC")
    fund = pd.DataFrame({"calc_time": ft, "last_funding_rate": np.zeros(len(ft))})
    cfg = WF_.GRID[0]

    # the reproduction guard and the agreement filter on a REAL 4h forecast series
    import json as _json
    import shutil
    import tempfile
    by2 = {60: {}, 240: {}}
    for i in range(2):
        b = _momentum_bars(0.0008, seed=200 + i)
        by2[60][f"C{i}USDT"] = {"spot": b, "perp": b, "fund": fund}
        by2[240][f"C{i}USDT"] = {"spot": _agg(b, "4h"), "perp": _agg(b, "4h"), "fund": fund}
    tmp = Path(tempfile.mkdtemp())
    saved = MP_.SRC
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            P4 = W2.prepare(by2, 240)
            p4 = WF_.walk_forward(P4, 240, cfg, *WF_.WINDOWS["valid"], step=3)
        pd.concat([pd.DataFrame({"coin": c, "time": P4[c]["X"].index[np.isfinite(p4[c])],
                                 "pred": p4[c][np.isfinite(p4[c])], "desired": 0.0}) for c in P4]
                  ).to_csv(tmp / "desired_valid_tf240.csv.gz", index=False)
        (tmp / "tf240.json").write_text(_json.dumps({"setting": cfg, "q_in": 0.9, "exit_mode": "flip"}))
        MP_.SRC = tmp
        orig_wf = WF_.walk_forward
        WF_.walk_forward = lambda *a_, **k_: orig_wf(*a_, **{**k_, "step": 3})
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                _, o4 = MP_.forecasts(by2, 240, [WF_.WINDOWS["valid"]])
            accepted = True
            rec = pd.read_csv(tmp / "desired_valid_tf240.csv.gz")
            rec.loc[3, "pred"] += 0.01
            rec.to_csv(tmp / "desired_valid_tf240.csv.gz", index=False)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    MP_.forecasts(by2, 240, [WF_.WINDOWS["valid"]])
                stopped = False
            except SystemExit:
                stopped = True
        finally:
            WF_.walk_forward = orig_wf
    finally:
        MP_.SRC = saved
        shutil.rmtree(tmp, ignore_errors=True)
    check("ml_port reproduction guard: accepts section 30's own forecasts, stops on any mismatch", accepted and stopped)
    with contextlib.redirect_stdout(io.StringIO()):
        P1 = W2.prepare(by2, 60)
        p1 = WF_.walk_forward(P1, 60, cfg, *WF_.WINDOWS["valid"], step=3)
    pred1 = {c: pd.Series(p1[c], index=P1[c]["X"].index) for c in P1}
    t_on, _ = MP_.run_cell(P1, pred1, {"4h": o4, "1d": o4}, *WF_.WINDOWS["valid"], "4h", "flat", None, 0.9, "flip")
    bad = 0
    for x in t_on.itertuples():
        sr = o4[x.coin]
        pos = WF_.asof_positions(pd.DatetimeIndex([x.entry_time - pd.Timedelta(hours=1)]), 60, sr.index, 240)[0]
        v = sr.iloc[pos] if pos >= 0 else np.nan
        bad += not (np.isfinite(v) and np.sign(v) == x.side)
    check("ml_port agreement on a real 4h series: every new 1h entry agrees with the last CLOSED 4h forecast",
          len(t_on) > 50 and bad == 0, f"{len(t_on)} trades, {bad} disagree")

    def setup(k, seeds):
        by = {60: {}}
        for n, sd in seeds:
            b = _momentum_bars(k, seed=sd)
            by[60][n] = {"spot": b, "perp": b, "fund": fund}
        P = W2.prepare(by, 60)
        pred = {c: np.full(len(P[c]["X"]), np.nan) for c in P}
        for a, b_ in (WF_.WINDOWS["train"], WF_.WINDOWS["valid"]):
            pw = WF_.walk_forward(P, 60, cfg, a, b_, step=3)
            for c in P:
                pred[c] = np.where(np.isfinite(pw[c]), pw[c], pred[c])
        pred1 = {c: pd.Series(pred[c], index=P[c]["X"].index) for c in P}
        other = {"4h": pred1, "1d": pred1}                 # agreement logic is tested above
        return P, pred1, other
    with contextlib.redirect_stdout(io.StringIO()):
        edge = MP_.evaluate(*setup(0.0008, [(f"C{i}USDT", 140 + i) for i in range(3)]), 0.9, "flip", min_coins=3)
        noise = MP_.evaluate(*setup(0.0, [(f"N{i}USDT", 150 + i) for i in range(3)]), 0.9, "flip", min_coins=3)
    check("ml_port pipeline: a planted edge is found (PASS) as one account",
          edge["verdict"] == "PASS", f"{edge['verdict']} {edge['gates_failed']} chose {edge['chosen']} "
          f"weekly {edge['valid']['weekly_mean']:+.5f} dd {edge['valid']['max_dd']:.3f}")
    check("ml_port pipeline: pure noise is not a PASS and its timing does not beat the shifted p95",
          noise["verdict"] == "REJECT" and "timing_beats_shift_p95" in noise["gates_failed"],
          f"{noise['verdict']} {noise['gates_failed']}")


# --------------------------------------------------------------------------
# 28. Cross-sectional (market-demeaned) forecasts (PLAN.md section 32)
# --------------------------------------------------------------------------
def test_ml_xs() -> None:
    print("\n28. ML cross-sectional: demeaned forecasts, causal, raw cells = section 31, weekly market, pipeline")
    import contextlib
    import io
    import ml_port as MP_
    import ml_wf as WF_
    import ml_wf2 as W2
    import ml_xs as XS
    ix = pd.date_range("2023-01-01", periods=4, freq="1h", tz="UTC")
    pr = {"A": pd.Series([1.0, 2.0, np.nan, 4.0], index=ix), "B": pd.Series([3.0, 0.0, 1.0, 0.0], index=ix),
          "C": pd.Series([2.0, 1.0, 5.0], index=ix[:3])}
    dm = XS.demean(pr, min_coins=2)
    check("ml_xs demean: minus the same-hour mean of every coin; NaN under min_coins; each coin keeps its index",
          np.allclose(dm["A"].to_numpy(), [-1.0, 1.0, np.nan, 2.0], equal_nan=True)
          and np.allclose(dm["B"].to_numpy(), [1.0, -1.0, -2.0, -2.0]) and np.allclose(dm["C"].to_numpy(), [0.0, 0.0, 2.0])
          and dm["C"].index.equals(ix[:3]))
    check("ml_xs demean: below min_coins there is no forecast",
          XS.demean(pr, min_coins=3)["B"].isna().to_numpy().tolist() == [False, False, True, True])
    pr2 = {k: v.copy() for k, v in pr.items()}
    pr2["A"].iloc[3] = 100.0
    dm2 = XS.demean(pr2, min_coins=2)
    check("ml_xs demean is causal: a later forecast never changes an earlier value",
          all(np.allclose(dm[c].iloc[:3], dm2[c].iloc[:3], equal_nan=True) for c in pr))
    p1, o1 = XS.transform("raw", pr, {"4h": pr})
    check("ml_xs raw form passes the forecasts through unchanged", p1 is pr and o1["4h"] is pr)

    wk = pd.date_range("2023-01-01", periods=23 * 24, freq="1h", tz="UTC")     # a day before the first week
    def bars(px):
        return pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": 1.0}, index=wk)
    pa = np.where(np.arange(len(wk)) < 8 * 24 - 1, 100.0, 110.0)      # the bar closing at 2023-01-09 00:00 is 110
    pa = np.where(np.arange(len(wk)) < 15 * 24 - 1, pa, 121.0)
    Pm = {"A": {"bars": bars(pa)}, "B": {"bars": bars(np.full(len(wk), 50.0))}}
    mw = XS.market_weekly(Pm, "2023-01-02", "2023-01-23")
    check("ml_xs weekly market return: equal-weight mean of weekly log returns from the last close before each week",
          len(mw) == 3 and np.isclose(mw.iloc[0], np.log(1.1) / 2) and np.isclose(mw.iloc[1], np.log(1.1) / 2)
          and np.isclose(mw.iloc[2], 0.0), f"{mw.to_numpy()}")

    ft = pd.date_range("2020-01-01", "2025-01-10", freq="8h", tz="UTC")
    fund = pd.DataFrame({"calc_time": ft, "last_funding_rate": np.zeros(len(ft))})
    cfg = WF_.GRID[0]

    def setup(k, seeds):
        by = {60: {}}
        for n, sd in seeds:
            b = _momentum_bars(k, seed=sd)
            by[60][n] = {"spot": b, "perp": b, "fund": fund}
        P = W2.prepare(by, 60)
        pred = {c: np.full(len(P[c]["X"]), np.nan) for c in P}
        for a, b_ in (WF_.WINDOWS["train"], WF_.WINDOWS["valid"]):
            pw = WF_.walk_forward(P, 60, cfg, a, b_, step=3)
            for c in P:
                pred[c] = np.where(np.isfinite(pw[c]), pw[c], pred[c])
        pred1 = {c: pd.Series(pred[c], index=P[c]["X"].index) for c in P}
        return P, pred1, {"4h": pred1, "1d": pred1}
    with contextlib.redirect_stdout(io.StringIO()):
        S = setup(0.0008, [(f"C{i}USDT", 140 + i) for i in range(3)])
        port = MP_.evaluate(*S, 0.9, "flip", min_coins=3)
        xs = XS.evaluate(*S, 0.9, "flip", min_coins=3, min_xs=2)
        noise = XS.evaluate(*setup(0.0, [(f"N{i}USDT", 150 + i) for i in range(3)]), 0.9, "flip", min_coins=3, min_xs=2)
    key = lambda x: (x["agree"], x["sizing"], x["cap"])
    pt = {key(x): x for x in port["train_table"]}
    raw = [x for x in xs["train_table"] if x["form"] == "raw"]
    same = all(np.isclose(x["weekly_mean"], pt[key(x)]["weekly_mean"]) and x["trades"] == pt[key(x)]["trades"] for x in raw)
    check("ml_xs raw cells reproduce section 31's TRAIN cells exactly (24 cells = 2 forms x 12)",
          len(xs["train_table"]) == 24 and len(raw) == 12 and same)
    dem = [x for x in xs["train_table"] if x["form"] == "demean"]
    check("ml_xs demeaned cells trade and differ from raw",
          all(x["trades"] > 0 for x in dem) and any(x["trades"] != r["trades"] or not np.isclose(x["weekly_mean"], r["weekly_mean"])
                                                    for x, r in zip(dem, raw)))
    check("ml_xs gate: a raw choice is section 31 again and cannot PASS",
          (xs["chosen"]["form"] == "demean") == ("train_chose_demean" not in xs["gates_failed"])
          and "diagnostics" in xs["valid"], f"{xs['chosen']} {xs['verdict']} {xs['gates_failed']}")
    check("ml_xs pipeline: pure noise is not a PASS", noise["verdict"] == "REJECT", f"{noise['gates_failed']}")


# --------------------------------------------------------------------------
# 29. Market timing on BTC/ETH from the mean forecast (PLAN.md section 33)
# --------------------------------------------------------------------------
def test_ml_mkt() -> None:
    print("\n29. ML market timing: mean forecast, instruments, shared risk budget, shared holdout lock, planted edge / noise")
    import contextlib
    import io
    import json as _json
    import shutil
    import tempfile
    import ml_mkt as MK
    import ml_port as MP_
    import ml_wf as WF_
    import ml_wf2 as W2
    import ml_xs as XS
    ix = pd.date_range("2023-01-01", periods=3, freq="1h", tz="UTC")
    pr = {"A": pd.Series([1.0, 2.0, np.nan], index=ix), "B": pd.Series([3.0, np.nan, 1.0], index=ix),
          "C": pd.Series([2.0, 0.0, 5.0], index=ix)}
    ms = MK.market_signal(pr, min_coins=2)
    check("ml_mkt market signal: same-hour mean over coins with a forecast; NaN under min_coins",
          np.allclose(ms.to_numpy(), [2.0, 1.0, 3.0]) and MK.market_signal(pr, min_coins=3).isna().tolist() == [False, True, True])
    pr2 = {k: v.copy() for k, v in pr.items()}
    pr2["C"].iloc[2] = 99.0
    check("ml_mkt market signal is causal: a later forecast never changes an earlier value",
          np.allclose(MK.market_signal(pr2, 2).iloc[:2], ms.iloc[:2]))

    ft = pd.date_range("2020-01-01", "2025-01-10", freq="8h", tz="UTC")
    fund = pd.DataFrame({"calc_time": ft, "last_funding_rate": np.zeros(len(ft))})

    def setup(k, seeds):
        by = {60: {}}
        for n, sd in seeds:
            b = _momentum_bars(k, seed=sd)
            by[60][n] = {"spot": b, "perp": b, "fund": fund}
        P = W2.prepare(by, 60)
        pred = {}
        for c in P:                                      # the planted edge's own causal forecast: last 24h, in ATRs
            cl = P[c]["bars"]["close"]
            f = np.log(cl / cl.shift(24)) / (P[c]["atr"] / cl)
            pred[c] = pd.Series(f.to_numpy()[:-1], index=P[c]["X"].index).where(P[c]["tradable"])
        return P, pred, {"4h": pred}
    with contextlib.redirect_stdout(io.StringIO()):
        S = setup(0.0008, [("BTCUSDT", 160), ("ETHUSDT", 160)])
        Sn = setup(0.0, [("BTCUSDT", 170), ("ETHUSDT", 171)])
    a, b = WF_.WINDOWS["valid"]
    t1, _, P1 = MK.run_cell(*S, a, b, "BTC", "off", 0.9, "flip", min_xs=1)
    t2, _, P2 = MK.run_cell(*S, a, b, "BTC+ETH", "off", 0.9, "flip", min_xs=1)
    check("ml_mkt instruments: BTC trades one contract at 1% risk; BTC+ETH trades both at half risk each",
          list(P1) == ["BTCUSDT"] and set(t1["coin"]) == {"BTCUSDT"} and np.allclose(t1["risk"], 0.01)
          and set(t2["coin"]) == {"BTCUSDT", "ETHUSDT"} and np.allclose(t2["risk"], 0.005)
          and np.allclose(t2["ret"], t2["net_r"] * t2["risk"]), f"{len(t1)} / {len(t2)} trades")
    Pi, p1, _ = MK.book(*S, "ETH", min_xs=1)
    check("ml_mkt book: the instrument is driven by the market signal on its own decision index",
          list(Pi) == ["ETHUSDT"] and p1["ETHUSDT"].index.equals(S[0]["ETHUSDT"]["X"].index)
          and np.allclose(p1["ETHUSDT"].dropna(), MK.market_signal(S[1], 1).reindex(p1["ETHUSDT"].index).dropna()))
    with contextlib.redirect_stdout(io.StringIO()):
        edge = MK.evaluate(*S, 0.9, "flip", min_xs=1)
        noise = MK.evaluate(*Sn, 0.9, "flip", min_xs=1)
    check("ml_mkt pipeline: a planted market-timing edge is found (PASS); 6 TRAIN cells",
          edge["verdict"] == "PASS" and len(edge["train_table"]) == 6,
          f"{edge['verdict']} {edge['gates_failed']} chose {edge['chosen']} weekly {edge['valid']['weekly_mean']:+.5f}")
    check("ml_mkt pipeline: pure noise is not a PASS", noise["verdict"] == "REJECT", f"{noise['gates_failed']}")

    tmp = Path(tempfile.mkdtemp())
    saved = (MK.OUT, MP_.OUT, XS.OUT)
    try:
        MK.OUT, MP_.OUT, XS.OUT = tmp / "mkt", tmp / "port", tmp / "xs"
        for o in (MK.OUT, MP_.OUT):
            o.mkdir(parents=True)
        (MK.OUT / "summary.json").write_text(_json.dumps({"verdict": "PASS"}))
        (MP_.OUT / "holdout.json").write_text("{}")
        try:
            MK.run(final=True)
            refused = False
        except SystemExit as e:
            refused = "share one holdout" in str(e)
    finally:
        MK.OUT, MP_.OUT, XS.OUT = saved
        shutil.rmtree(tmp, ignore_errors=True)
    check("ml_mkt holdout: refused when section 31 (or 32) already used the shared holdout", refused)


# --------------------------------------------------------------------------
# 30. Positioning features for the 1h model (PLAN.md section 34)
# --------------------------------------------------------------------------
def _metrics_frame(idx_from, idx_to, seed, oi0=1000.0):
    """Synthetic 5-minute Binance metrics rows (already renamed), for the TEST only."""
    rng = np.random.default_rng(seed)
    ct = pd.date_range(idx_from, idx_to, freq="5min", tz="UTC")
    oi = oi0 * np.exp(np.cumsum(rng.normal(0, 0.002, len(ct))))
    ls = np.exp(rng.normal(0, 0.1, len(ct)))
    return pd.DataFrame({"create_time": ct, "oi": oi, "oi_usd": oi * 30000, "top_acct_ls": ls,
                         "top_pos_ls": ls * 1.1, "acct_ls": ls, "taker_ls": ls})


def test_ml_flow() -> None:
    print("\n30. ML positioning features: causal coin and market features, base untouched, base = section 31, pipeline")
    import contextlib
    import io
    import json as _json
    import shutil
    import tempfile
    import ml_flow as FL
    import ml_mkt as MK
    import ml_port as MP_
    import ml_wf as WF_
    import ml_wf2 as W2
    import ml_xs as XS

    ft = pd.date_range("2020-01-01", "2025-01-10", freq="8h", tz="UTC")
    fund = pd.DataFrame({"calc_time": ft, "last_funding_rate": np.random.default_rng(5).normal(1e-4, 1e-4, len(ft))})
    by = {60: {}}
    for n, sd in (("C0USDT", 140), ("C1USDT", 141), ("C2USDT", 142)):
        b = _momentum_bars(0.0008, seed=sd)
        by[60][n] = {"spot": b, "perp": b, "fund": fund}
    with contextlib.redirect_stdout(io.StringIO()):
        P = W2.prepare(by, 60)
    met = {c: _metrics_frame("2021-12-01", "2025-01-10", 300 + i) for i, c in enumerate(P)}
    cols0 = {c: list(P[c]["X"].columns) for c in P}
    Q = FL.add_flow(P, met, min_xs=2)
    check("ml_flow add_flow: base X untouched; the copy carries every flow column",
          all(list(P[c]["X"].columns) == cols0[c] for c in P)
          and all(list(Q[c]["X"].columns) == cols0[c] + FL.FLOW_COLS for c in P)
          and all(Q[c]["X"].index.equals(P[c]["X"].index) for c in P))
    c0 = "C0USDT"
    X = Q[c0]["X"]
    t = pd.Timestamp("2023-06-01 12:00", tz="UTC")
    m = met[c0].set_index("create_time")
    def oi_at(ts):                                   # last row available 5 min before the bar close
        close = ts + pd.Timedelta(hours=1)
        return m.loc[m.index + pd.Timedelta(minutes=5) <= close, "oi"].iloc[-1]
    want = np.log(oi_at(t) / oi_at(t - pd.Timedelta(hours=24)))
    check("ml_flow oi_chg_24 = log OI change over 24 bars, each OI the last row 5 min before that bar's close",
          np.isclose(X.loc[t, "oi_chg_24"], want), f"{X.loc[t, 'oi_chg_24']} vs {want}")
    check("ml_flow metrics features are NaN before the metrics start; funding features exist earlier",
          X.loc[:"2021-11-30", "oi_chg_24"].isna().all() and X.loc["2021-06-01":"2021-11-30", "fund_168"].notna().any())
    mk = pd.concat([Q[c]["X"]["oi_chg_24"] for c in P], axis=1).mean(axis=1)
    check("ml_flow market features: same-hour mean over coins; relative = coin minus market",
          np.allclose(X.loc[t, "mkt_oi_chg_24"], mk.loc[t]) and np.isclose(X.loc[t, "rel_oi_chg_24"],
                                                                         X.loc[t, "oi_chg_24"] - mk.loc[t]))
    met2 = {c: v.copy() for c, v in met.items()}
    met2[c0].loc[met2[c0]["create_time"] > t + pd.Timedelta(hours=1), ["oi", "oi_usd", "acct_ls", "top_pos_ls"]] *= 3.0
    Q2 = FL.add_flow(P, met2, min_xs=2)
    same = all(np.allclose(Q2[c]["X"].loc[:t, FL.FLOW_COLS].to_numpy(float), Q[c]["X"].loc[:t, FL.FLOW_COLS].to_numpy(float),
                           equal_nan=True) for c in P)
    check("ml_flow features are causal: metrics after a bar's close never change that bar or earlier", same)

    a, b = WF_.WINDOWS["train"][0], WF_.WINDOWS["valid"][1]
    orig = WF_.walk_forward
    WF_.walk_forward = lambda *a_, **k_: orig(*a_, **{**k_, "step": 3})
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            spans = [WF_.WINDOWS["train"], WF_.WINDOWS["valid"]]
            cfg = WF_.GRID[0]
            saved_cfg = MP_._cfg
            MP_._cfg = lambda tf: {"setting": cfg, "q_in": 0.9, "exit_mode": "flip"}
            try:
                pb = {}
                for a_, b_ in spans:
                    pw = WF_.walk_forward(P, 60, cfg, a_, b_)
                    for c in P:
                        pb[c] = np.where(np.isfinite(pw[c]), pw[c], pb.get(c, np.full(len(pw[c]), np.nan)))
                pred_base = {c: pd.Series(pb[c], index=P[c]["X"].index) for c in P}
                models = {}
                pred_flow = FL.flow_forecasts(Q, spans, models)
                gain = FL.flow_gain_share(models, *WF_.WINDOWS["valid"])
                res = FL.evaluate(P, pred_base, Q, pred_flow, {"4h": pred_base}, 0.9, "flip", min_coins=3, gain=gain)
            finally:
                MP_._cfg = saved_cfg
    finally:
        WF_.walk_forward = orig
    t_b, _ = MP_.run_cell(P, pred_base, {"4h": pred_base}, *WF_.WINDOWS["train"], "4h", "conf", 0.05, 0.9, "flip")
    acc_b = MP_.account(t_b, *WF_.WINDOWS["train"])
    base_row = [x for x in res["train_table"] if x["form"] == "base"][0]
    check("ml_flow base form is section 31's cell exactly (same trades and weekly mean on TRAIN)",
          base_row["trades"] == acc_b["trades"] and np.isclose(base_row["weekly_mean"], acc_b["weekly_mean"]))
    check("ml_flow flow forecasts differ from base and the gain share is measured in [0, 1]",
          any(not np.allclose(pred_flow[c].dropna(), pred_base[c].reindex(pred_flow[c].dropna().index), equal_nan=True)
              for c in P) and gain is not None and 0.0 <= gain <= 1.0, f"gain {gain}")
    check("ml_flow gate: a base choice is section 31 again and cannot PASS",
          (res["chosen"]["form"] == "flow") == ("train_chose_flow" not in res["gates_failed"])
          and len(res["train_table"]) == 2 and "diagnostics" in res["valid"],
          f"{res['chosen']} {res['verdict']} {res['gates_failed']}")

    tmp = Path(tempfile.mkdtemp())
    saved = (FL.OUT, MP_.OUT, XS.OUT, MK.OUT)
    try:
        FL.OUT, MP_.OUT, XS.OUT, MK.OUT = tmp / "flow", tmp / "port", tmp / "xs", tmp / "mkt"
        for o in (FL.OUT, MK.OUT):
            o.mkdir(parents=True)
        (FL.OUT / "summary.json").write_text(_json.dumps({"verdict": "PASS"}))
        (MK.OUT / "holdout.json").write_text("{}")
        try:
            FL.run(final=True)
            refused = False
        except SystemExit as e:
            refused = "share one holdout" in str(e)
    finally:
        FL.OUT, MP_.OUT, XS.OUT, MK.OUT = saved
        shutil.rmtree(tmp, ignore_errors=True)
    check("ml_flow holdout: refused when sections 31-33 already used the shared holdout", refused)


# --------------------------------------------------------------------------
# 31. Short newly listed perpetuals (PLAN.md section 35)
# --------------------------------------------------------------------------
def _listing_market(decline: float, seed: int, n_new: int = 320, n_old: int = 40) -> dict:
    """Synthetic daily perps for the TEST only: n_old established coins from 2020-01, n_new coins
    listed uniformly 2020-06..2024-12; a new coin drifts by `decline` a day for its first 40 days."""
    rng = np.random.default_rng(seed)
    end = pd.Timestamp("2025-01-10", tz="UTC")
    starts = [pd.Timestamp("2020-01-01", tz="UTC")] * n_old + list(
        pd.Timestamp("2020-06-01", tz="UTC") + pd.to_timedelta(np.sort(rng.integers(0, 1650, n_new)), unit="D"))
    bars = {}
    for k, st in enumerate(starts):
        idx = pd.date_range(st, end, freq="D", tz="UTC")
        n = len(idx)
        drift = np.where((np.arange(n) < 40) & (k >= n_old), decline, 0.0)
        r = rng.normal(0, 0.03, n) + drift
        c = 10 * np.exp(np.cumsum(r))
        o = np.r_[10.0, c[:-1]]
        hi = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.01, n)))
        lo = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.01, n)))
        bars[f"{'OLD' if k < n_old else 'NEW'}{k}USDT"] = pd.DataFrame(
            {"open": o, "high": hi, "low": lo, "close": c, "quote_volume": 1e6, "funding": 0.0}, index=idx)
    return bars


def test_listing() -> None:
    print("\n31. Listing short: events, daily short with stop / trailing signal / eod / delisting, funding, control, pipeline")
    import contextlib
    import io
    import listing as LS
    D = lambda d: pd.Timestamp("2023-01-01", tz="UTC") + pd.Timedelta(days=d)
    idx = pd.date_range(D(0), periods=8, freq="D", tz="UTC")
    def mk(o, h, c, f=None):
        return pd.DataFrame({"open": o, "high": h, "low": np.minimum(o, c), "close": c, "quote_volume": 1.0,
                             "funding": f if f is not None else np.zeros(len(o))}, index=idx[:len(o)])
    # trailing: lowest close 80, then a close of 105 > 80 x 1.3 = 104 -> cover at the next open (106)
    b1 = mk([100, 95, 85, 90, 106, 100], [101, 96, 90, 106, 107, 101], [95, 85, 80, 105, 100, 99])
    t1 = LS.short_trade(b1, D(0), D(30), stop=0.5, trail=0.3, fee=0.0, slip=0.0)
    check("listing trailing exit: a close above the lowest close x (1 + trail) covers at the next open",
          t1["reason"] == "signal" and t1["exit_px"] == 106 and t1["exit_time"] == D(4)
          and np.isclose(t1["net_r"], (100 - 106) / 100 / 0.5), f"{t1}")
    # stop with a gap: open 140 above the 130 stop -> filled at the open
    b2 = mk([100, 140], [110, 150], [120, 145])
    t2 = LS.short_trade(b2, D(0), D(30), stop=0.3, trail=0.6, fee=0.0, slip=0.0)
    b3 = mk([100, 120], [110, 131], [120, 125])
    t3 = LS.short_trade(b3, D(0), D(30), stop=0.3, trail=0.6, fee=0.0, slip=0.0)
    check("listing stop: filled at the stop, or at the open when the day gaps through it",
          t2["reason"] == "stop" and t2["exit_px"] == 140 and np.isclose(t2["net_r"], -0.4 / 0.3)
          and t3["exit_px"] == 130 and np.isclose(t3["net_r"], -1.0))
    b4 = mk([100, 99, 98], [101, 100, 99], [99, 98, 97], f=np.array([0.001, 0.001, -0.002]))
    t4 = LS.short_trade(b4, D(0), D(30), stop=0.5, trail=0.6, fee=0.0005, slip=0.0005)
    want = ((100 * 0.9995 - 97 * 1.0005) / (100 * 0.9995) - 0.001 + (0.001 * 100 + 0.001 * 99 - 0.002 * 98) / 100) / 0.5
    check("listing delisted/eod exit with fees, slippage and funding (a short receives a positive rate)",
          t4["reason"] == "delisted" and np.isclose(t4["net_r"], want), f"{t4['net_r']} vs {want}")
    t5 = LS.short_trade(b4, D(0), D(2), stop=0.5, trail=0.6, fee=0.0, slip=0.0)
    check("listing window end: an open trade closes at the last close inside the window ('eod')",
          t5["reason"] == "eod" and t5["exit_px"] == 98 and t5["exit_time"] == D(2))

    bars = {"AUSDT": mk([1] * 3, [1] * 3, [1] * 3), "BUSDT": b1, "BUSDT#1": b1}
    bars["AUSDT"].index = pd.date_range("2020-01-01", periods=3, freq="D", tz="UTC")
    ev = LS.listings(bars)
    check("listing events: first run only, after LISTED_AFTER (founding contracts and relaunches are not listings)",
          list(ev["inst"]) == ["BUSDT"])

    ys = LS.year_of_exit(pd.Series([pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2024-06-03", tz="UTC")]))
    check("listing per-year: an eod exit stamped at the window end (next 00:00) counts in the last year of the window",
          list(ys) == [2024, 2024])
    L = pd.Timestamp("2023-05-20", tz="UTC")
    check("listing new-token flag: no spot pair, or spot first traded in the listing month or later",
          LS.new_token(None, L) and LS.new_token("2023-05", L) and LS.new_token("2023-06", L)
          and not LS.new_token("2023-04", L))
    with contextlib.redirect_stdout(io.StringIO()):
        good = _listing_market(-0.015, seed=7)
        null = _listing_market(0.0, seed=8)
        r_good = LS.evaluate(good, LS.listings(good))
        r_null = LS.evaluate(null, LS.listings(null))
    v = r_good["valid"]
    check("listing pipeline: a planted post-listing decline is found (PASS) and beats the established-coin control",
          r_good["verdict"] == "PASS" and v["event_mean_r"] > v["control_p95"],
          f"{r_good['verdict']} {r_good['gates_failed']} chose {r_good['chosen']} trades {v['trades']} "
          f"weekly {v['weekly_mean']:+.5f} event {v['event_mean_r']:+.3f} ctl p95 {v['control_p95']}")
    check("listing pipeline: no decline -> REJECT, and the event mean does not beat the control p95",
          r_null["verdict"] == "REJECT" and "valid_beats_control_p95" in r_null["gates_failed"],
          f"{r_null['gates_failed']}")


# --------------------------------------------------------------------------
# 32. Train wide, trade the monthly top 20 large coins (PLAN.md section 36)
# --------------------------------------------------------------------------
def test_ml_wide() -> None:
    print("\n32. ML wide: monthly sets (per symbol, crypto, age), labels per horizon = prepare's, masks, ensemble, member filter, pipeline")
    import contextlib
    import io
    import ml_port as MP_
    import ml_wf as WF_
    import ml_wf2 as W2
    import ml_wide as MW
    days = pd.date_range("2021-01-01", "2023-03-31", freq="D", tz="UTC")
    rows = []
    for d in days:
        young = d >= pd.Timestamp("2022-12-01", tz="UTC")
        gap = pd.Timestamp("2023-02-26", tz="UTC") <= d <= pd.Timestamp("2023-02-28", tz="UTC")
        rows += [("AUSDT", d, 300.0), ("XAUUSDT", d, 999.0)]
        if not gap:
            rows.append(("BUSDT", d, 200.0))                       # a 3-day hole must not drop it
        if young:
            rows.append(("NEWUSDT", d, 500.0))
        rows.append(("CUSDT", d, 100.0 if d.day % 2 else 0.0))   # 15 traded days of 30: too few
    daily = pd.DataFrame(rows, columns=["symbol", "date", "quote_volume"])
    mem, tr = MW.monthly_sets(daily, ["2023-01", "2023-03"], {"XAUUSDT"}, train_top=3, trade_n=2)
    check("ml_wide sets: per symbol (a data hole does not drop a coin), crypto only, >= 20 traded days; "
          "traded = top-N listed >= 365 days; members may be young",
          mem["2023-01"] == ["NEWUSDT", "AUSDT", "BUSDT"] and tr["2023-01"] == ["AUSDT", "BUSDT"]
          and tr["2023-03"] == ["AUSDT", "BUSDT"], f"{mem} {tr}")

    ft = pd.date_range("2020-01-01", "2025-01-10", freq="8h", tz="UTC")
    fund = pd.DataFrame({"calc_time": ft, "last_funding_rate": np.zeros(len(ft))})
    b = _momentum_bars(0.0008, seed=210).copy()
    b.iloc[5000:5010, b.columns.get_loc("volume")] = 0.0              # dead bars inside the history
    with contextlib.redirect_stdout(io.StringIO()):
        P1 = W2.prepare({60: {"AUSDT": {"spot": b, "perp": b, "fund": fund}}}, 60)
    y24 = MW.label_h(P1["AUSDT"]["bars"], 24)
    y12 = MW.label_h(P1["AUSDT"]["bars"], 12)
    o = P1["AUSDT"]["bars"]["open"].to_numpy()
    i = 7000
    af = P1["AUSDT"]["y"].iloc[i] / np.log(o[i + 25] / o[i + 1])        # = 1 / ATR fraction at i
    check("ml_wide label_h(24) equals ml_wf.prepare's label exactly; label_h(12) uses 12 bars and the same ATR",
          np.allclose(y24, P1["AUSDT"]["y"].to_numpy(), equal_nan=True)
          and np.isclose(y12[i], np.log(o[i + 13] / o[i + 1]) * af) and np.isnan(y12[4995]))

    idx = pd.date_range("2023-01-30", "2023-03-02", freq="1D", tz="UTC")
    feb = [d.strftime("%Y-%m") == "2023-02" for d in idx]
    check("ml_wide masks: narrow trains on core rows only; wide adds a coin's member months",
          MW.training_mask(idx, "CORE", {"CORE"}, {}, False).all()
          and not MW.training_mask(idx, "X", {"CORE"}, {"2023-02": ["X"]}, False).any()
          and list(MW.training_mask(idx, "X", {"CORE"}, {"2023-02": ["X"], "2023-03": []}, True)) == feb)
    cb = MW.combine({12: np.array([1.0, np.nan]), 24: np.array([2.0, 1.0]), 48: np.array([4.0, 1.0])})
    check("ml_wide ensemble: mean of pred_h x sqrt(24/h); NaN unless every horizon forecasts",
          np.isclose(cb[0], (np.sqrt(2) + 2 + 4 / np.sqrt(2)) / 3) and np.isnan(cb[1]))
    d = np.array([0, 1, 1, 1, 0, -1, -1, 1], float)
    al = np.array([1, 0, 1, 0, 0, 0, 1, 0], bool)
    check("ml_wide member filter: a new position (or reversal) only where allowed; holding and exits untouched",
          list(MW.member_filter(d, al)) == [0, 0, 1, 1, 0, 0, -1, 0])

    cfg = WF_.GRID[0]
    saved_cfg = MP_._cfg
    MP_._cfg = lambda tf: {"setting": cfg, "q_in": 0.9, "exit_mode": "flip"}
    try:
        by = {60: {}}
        for n, sd in (("C0USDT", 140), ("C1USDT", 141), ("C2USDT", 142), ("N0USDT", 143)):
            bb = _momentum_bars(0.0008, seed=sd)
            by[60][n] = {"spot": bb, "perp": bb, "fund": fund}
        months = [str(p) for p in pd.period_range("2020-01", "2024-12", freq="M")]
        members = {m: ["N0USDT"] for m in months}
        core = {"C0USDT", "C1USDT", "C2USDT"}
        with contextlib.redirect_stdout(io.StringIO()):
            P = W2.prepare(by, 60)
            h0 = WF_.H_BARS
            spans = [WF_.WINDOWS["train"], WF_.WINDOWS["valid"]]
            pw = MW.forecasts(P, 60, cfg, {c: MW.training_mask(P[c]["X"].index, c, core, members, True) for c in P},
                              MW.HORIZONS, spans, step=3)
        va = [(s.index >= pd.Timestamp(WF_.WINDOWS["valid"][0], tz="UTC")) for s in pw.values()]
        check("ml_wide forecasts: every coin forecast in VALID (the non-core coin too), horizon setting restored",
              WF_.H_BARS == h0 and all(np.isfinite(s.to_numpy()[m]).mean() > 0.5 for s, m in zip(pw.values(), va)))
        traded = {m: ["C0USDT", "C1USDT", "C2USDT"] for m in months}
        noise = {c: pd.Series(np.random.default_rng(9).normal(size=len(P[c]["X"])), index=P[c]["X"].index) for c in P}
        with contextlib.redirect_stdout(io.StringIO()):
            r1 = MW.evaluate(P, noise, pw, pw, traded, 0.9, "flip", min_coins=3)
            r2 = MW.evaluate(P, pw, noise, pw, traded, 0.9, "flip", min_coins=3)
            t_off, _ = MW.run_cell(P, pw, pw, *WF_.WINDOWS["valid"], {m: ["C0USDT"] for m in months}, 0.9, "flip")
        check("ml_wide pipeline: a real edge in the wide forecast is chosen and PASSes; a narrow choice cannot PASS",
              r1["chosen"]["form"] == "wide" and r1["verdict"] == "PASS"
              and r2["chosen"]["form"] == "narrow" and "train_chose_wide" in r2["gates_failed"],
              f"{r1['verdict']} {r1['gates_failed']} / {r2['chosen']} {r2['gates_failed']}")
        tw = next(x for x in r1["train_table"] if x["form"] == "wide")
        check("ml_wide train_checks (output only): the chosen form's TRAIN account repeated with the VALID checks",
              r1["train_checks"]["trades"] == tw["trades"] and np.isclose(r1["train_checks"]["weekly_mean"],
                                                                          tw["weekly_mean"])
              and {"timing", "shift_p95", "stress_weekly_mean", "breadth"} <= set(r1["train_checks"]))
        check("ml_wide traded sets: a coin outside every month's traded set never gets a position",
              len(t_off) > 0 and set(t_off["coin"]) == {"C0USDT"})
    finally:
        MP_._cfg = saved_cfg


def test_ml_large() -> None:
    """Test 33 (PLAN.md section 37): the ten-coin model's traded sets, cells, agreement switch and pipeline."""
    print("\n33. ml_large: fixed large-coin sets, horizon-set x agreement cells, pipeline on planted edge / noise")
    import contextlib
    import io
    import ml_port as MP_
    import ml_wf as WF_
    import ml_wf2 as W2
    import ml_large as ML
    first = {"BTCUSDT": pd.Timestamp("2019-09-08", tz="UTC"), "NEARUSDT": pd.Timestamp("2020-10-14", tz="UTC")}
    ts = ML.traded_sets(first, ["2020-09", "2020-10", "2021-10", "2021-11"])
    check("ml_large traded sets: a listed coin from 365 days after its first day; unlisted coins never",
          ts["2020-09"] == [] and ts["2020-10"] == ["BTCUSDT"] and ts["2021-10"] == ["BTCUSDT"] and ts["2021-11"] == ["BTCUSDT", "NEARUSDT"],
          f"{ts}")
    check("ml_large cells: 2 horizon sets x agreement off/1d", [ML.cell_name(c) for c in ML.cells()] ==
          ["1-3d_off", "1-3d_1d", "2-6d_off", "2-6d_1d"])

    ft = pd.date_range("2020-01-01", "2025-01-10", freq="8h", tz="UTC")
    fund = pd.DataFrame({"calc_time": ft, "last_funding_rate": np.zeros(len(ft))})
    cfg = WF_.GRID[0]
    by = {60: {}}
    for n, sd in (("C0USDT", 150), ("C1USDT", 151), ("C2USDT", 152), ("N0USDT", 153)):
        bb = _momentum_bars(0.0008, seed=sd)
        by[60][n] = {"spot": bb, "perp": bb, "fund": fund}
    with contextlib.redirect_stdout(io.StringIO()):
        P = W2.prepare(by, 60)
        spans = [WF_.WINDOWS["train"], WF_.WINDOWS["valid"]]
        masks = {c: np.ones(len(P[c]["X"]), bool) for c in P}
        ph = ML.per_horizon(P, 60, cfg, masks, (12, 24), spans, step=3)
    edge = ML.combine_set(P, ph, (12, 24))
    noise = {c: pd.Series(np.random.default_rng(11).normal(size=len(P[c]["X"])), index=P[c]["X"].index) for c in P}
    months = [str(p) for p in pd.period_range("2020-01", "2024-12", freq="M")]
    traded = {m: ["C0USDT", "C1USDT", "C2USDT"] for m in months}
    with contextlib.redirect_stdout(io.StringIO()):
        r1 = ML.evaluate(P, {"1-3d": edge, "2-6d": noise}, edge, traded, 0.9, "flip", tf=60, tf_agree=60, min_coins=3)
        r2 = ML.evaluate(P, {"1-3d": noise, "2-6d": noise}, noise, traded, 0.9, "flip", tf=60, tf_agree=60,
                         min_coins=3)
        a, b = WF_.WINDOWS["valid"]
        t_nan, _ = ML.run_cell(P, edge, {c: s * np.nan for c, s in edge.items()}, "1d", a, b, traded, 0.9, "flip",
                               tf=60, tf_agree=60)
        t_off, _ = ML.run_cell(P, edge, None, "off", a, b, {m: ["C0USDT"] for m in months}, 0.9, "flip",
                               tf=60, tf_agree=60)
    check("ml_large pipeline: the planted edge's horizon set is chosen on TRAIN and PASSes; pure noise is REJECT",
          r1["chosen"]["horizons"] == "1-3d" and r1["verdict"] == "PASS" and r2["verdict"] == "REJECT",
          f"{r1['chosen']} {r1['verdict']} {r1['gates_failed']} / {r2['verdict']} {r2['gates_failed']}")
    check("ml_large outputs: four TRAIN rows, TRAIN checks of the chosen cell, best-5-week diagnostics",
          len(r1["train_table"]) == 4 and {"timing", "shift_p95", "breadth"} <= set(r1["train_checks"])
          and r1["valid"]["top5_weeks_share"] is not None and "weekly_mean_without_top5" in r1["valid"])
    check("ml_large agreement: with no agreeing forecast (all NaN) no position opens; a coin outside every "
          "month's set never trades", len(t_nan) == 0 and len(t_off) > 0 and set(t_off["coin"]) == {"C0USDT"})



def test_result_report() -> None:
    """Test 34: the read-only analysis files (streaks, profit factor, drawdown, buckets, causal regimes)."""
    print("\n34. result_report: summary numbers, confidence buckets, causal BTC regimes")
    import result_report as RR
    r = pd.Series([1.0, 2.0, -1.0, -0.5, -0.5, 3.0])
    check("result_report streaks / PF / drawdown by hand: 2 wins, 3 losses in a row; PF 6/2; DD 2 (additive)",
          RR.streaks(r) == (2, 3) and np.isclose(RR.profit_factor(r), 3.0) and np.isclose(RR.max_dd(r), 2.0))
    t = pd.DataFrame({"entry_time": pd.date_range("2023-01-01", periods=6, freq="D", tz="UTC"),
                      "exit_time": pd.date_range("2023-01-02", periods=6, freq="D", tz="UTC"),
                      "side": [1, -1, 1, -1, 1, -1], "net_r": r, "conf": [1.0, 1.1, 1.3, 1.6, 2.5, 4.0],
                      "coin": ["A", "A", "B", "B", "A", "B"], "reason": "signal"})
    s = RR.summary(t)
    pa = RR.prediction_analysis(t)
    check("result_report summary: 6 trades, win rate 0.5, avg win 2, avg loss -2/3, longs 3",
          s["trades"] == 6 and np.isclose(s["win_rate"], 0.5) and np.isclose(s["avg_win_r"], 2.0)
          and np.isclose(s["avg_loss_r"], -2 / 3) and s["longs"] == 3 and np.isclose(s["return"], 0.01 * r.sum()))
    check("result_report confidence buckets cover every trade once",
          sum(b["trades"] for b in pa["buckets"]) == 6 and [b["trades"] for b in pa["buckets"]] == [2, 1, 1, 1, 1])
    idx = pd.date_range("2020-01-01", periods=800, freq="D", tz="UTC")
    c = pd.Series(np.exp(np.cumsum(np.random.default_rng(5).normal(0, 0.03, 800))) * 1e4, index=idx)
    g1 = RR.regimes(pd.DataFrame({"close": c}))
    c2 = c.copy()
    c2.iloc[600:] *= 3.0
    g2 = RR.regimes(pd.DataFrame({"close": c2}))
    check("result_report regimes are causal: changing prices from day 600 changes no regime before day 600",
          g1.iloc[:600].equals(g2.iloc[:600]) and set(g1["trend"].dropna()) <= {"up", "down"})


if __name__ == "__main__":
    main()
