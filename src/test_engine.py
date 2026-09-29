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
                amt = pos["qty"] * float(rate) * (1.0 if pos["side"] > 0 else -1.0)
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
    test_differential()
    test_cost_monotonicity()
    test_no_lookahead()
    test_post_only()
    test_dynamic_exits()
    test_recipe_blocks_causal()
    test_tf_variants()
    test_short_side()
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


if __name__ == "__main__":
    main()
