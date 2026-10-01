"""Allocation test: hold in uptrends, step aside (or short) in downtrends?

    python src/allocation.py                      # C.SYMBOL (BTCUSDT by default)
    SYMBOL=ETHUSDT python src/allocation.py

Owner question (PLAN.md section 16): buying near a top and waiting a year to
get back to break-even is the real problem, so test whether a slow trend rule
gives most of buy-and-hold's upside with much less of its downside. This is a
different question from evaluate.py's ("does an entry beat costs, random
timing and buy-and-hold?"), so it is a different, much simpler test:

  * daily bars, exposure 1x of equity (no leverage) or 0; short only on perps;
  * the position is decided on day t's close and applied from day t+1's open;
  * cost on every change of position: fee + slippage on the traded notional;
    perps also pay or receive funding while a position is open;
  * the four rules are fixed textbook rules (RULES). Nothing is fitted, so no
    period is a training period, and every period is reported. Changing a
    rule, or adding one, needs the owner: the script refuses to overwrite its
    own results (--rerun only after a code fix, as with evaluate.py).

Markets:
  spot  Binance spot daily klines (data/spot/monthly/klines/<SYMBOL>/1d),
        from the first published month; VIP0 taker 0.10% + 0.02% slippage.
  perp  Binance USDT-M daily klines from config data_start, taker 0.05% +
        0.02% slippage, plus funding (notional x rate, long pays a positive
        rate) from the funding cache.
Both end at config data_end.

Writes results/<SYMBOL>/allocation/summary.json and the generated report
journal/<SYMBOL>/allocation.md.
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
import datafeed as DF  # noqa: E402

OUT = C.RESULTS / "allocation"
REPORT = C.JOURNAL / "allocation.md"

# Calendar segments, reported separately so a rule cannot hide a bad cycle
# behind a good one. Each segment is measured on the same continuous run.
SEGMENTS = [
    ("2018 bear", "2018-01-01", "2018-12-31"),
    ("2019", "2019-01-01", "2019-12-31"),
    ("2020-21 bull", "2020-01-01", "2021-12-31"),
    ("2022 bear", "2022-01-01", "2022-12-31"),
    ("2023-24", "2023-01-01", "2024-12-31"),
    ("2025-26", "2025-01-01", "2026-12-31"),
    ("first half", "2017-01-01", "2021-12-31"),
    ("second half", "2022-01-01", "2026-12-31"),
]


# --------------------------------------------------------------------------
# rules: target position from closes up to and including day t
# --------------------------------------------------------------------------
def r_sma200(c: pd.Series) -> pd.Series:
    """Long while the close is above its 200-day simple average, else flat."""
    return (c > c.rolling(200).mean()).astype(float)


def r_golden_cross(c: pd.Series) -> pd.Series:
    """Long while the 50-day average is above the 200-day average, else flat."""
    sma200 = c.rolling(200).mean()
    return (c.rolling(50).mean() > sma200).astype(float).where(sma200.notna(), 0.0)


def r_breakout_20w(c: pd.Series) -> pd.Series:
    """Enter long on a close above the highest close of the previous 140 days
    (20 weeks); exit on a close below the lowest close of the previous 70 days
    (10 weeks). Otherwise keep the previous position."""
    hi = c.shift(1).rolling(140).max()
    lo = c.shift(1).rolling(70).min()
    pos, cur = np.zeros(len(c)), 0.0
    for i, (x, h, l) in enumerate(zip(c.to_numpy(), hi.to_numpy(), lo.to_numpy())):
        if cur == 0 and np.isfinite(h) and x > h:
            cur = 1.0
        elif cur == 1 and np.isfinite(l) and x < l:
            cur = 0.0
        pos[i] = cur
    return pd.Series(pos, index=c.index)


def r_sma200_long_short(c: pd.Series) -> pd.Series:
    """Long above the 200-day average, short below it (perps only)."""
    sma = c.rolling(200).mean()
    return pd.Series(np.where(sma.isna(), 0.0, np.where(c > sma, 1.0, -1.0)), index=c.index)


RULES = {  # name: (function, markets)
    "sma200": (r_sma200, ("spot", "perp")),
    "golden_cross": (r_golden_cross, ("spot", "perp")),
    "breakout_20w": (r_breakout_20w, ("spot", "perp")),
    "sma200_long_short": (r_sma200_long_short, ("perp",)),
}
WARMUP_DAYS = 200  # every rule is defined from day 200 on; all runs start there


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
def to_utc_ms(t: pd.Series) -> pd.Series:
    """Binance spot files switched open_time from milliseconds to microseconds
    in 2025. A value above 1e14 cannot be milliseconds (that is year 5138)."""
    t = t.astype("int64")
    return pd.to_datetime(np.where(t > 10**14, t // 1000, t), unit="ms", utc=True)


def load_daily(market: str) -> pd.DataFrame:
    """Native Binance daily klines for C.SYMBOL, cached. Never resampled."""
    out = C.CACHE / f"{C.SYMBOL}_{market}_1d.parquet"
    if not out.exists():
        prefix = (f"data/spot/monthly/klines/{C.SYMBOL}/1d/" if market == "spot"
                  else f"data/futures/{C.MARKET}/monthly/klines/{C.SYMBOL}/1d/")
        start = "2017-01" if market == "spot" else C.DATA_START
        months = set(C.month_range(start, C.DATA_END))
        keys = [k for k in DF.list_keys(prefix) if k[-11:-4] in months]
        raw = C.RAW / f"{market}_1d"  # own folder: spot and perp zips share names
        frames = [DF._read_one_zip(p, C.KLINE_COLS)
                  for p in (DF.fetch_zip(k, raw) for k in keys) if p]
        df = pd.concat(frames, ignore_index=True)
        df["open_time"] = to_utc_ms(df["open_time"])
        df = df.sort_values("open_time").drop_duplicates("open_time")
        df[["open_time", "open", "high", "low", "close", "volume"]].to_parquet(out, index=False)
        print(f"[{market}] {len(keys)} monthly files -> {out.name}")
    df = pd.read_parquet(out).set_index("open_time").sort_index()
    gaps = int((df.index.to_series().diff().dt.days > 1).sum())
    if gaps:
        raise SystemExit(f"[{market}] {gaps} missing days in the daily klines")
    return df[["open", "close"]].astype(float)


def daily_funding(index: pd.DatetimeIndex) -> np.ndarray:
    """Sum of funding rates settling inside each day [open, next open)."""
    import experiment as E
    f = E.load_funding()
    if f is None:
        raise SystemExit("no funding cache: run python src/datafeed.py")
    day = f["calc_time"].dt.floor("D")
    s = f.groupby(day)["last_funding_rate"].sum()
    return s.reindex(index).fillna(0.0).to_numpy(float)


# --------------------------------------------------------------------------
# the backtest
# --------------------------------------------------------------------------
def simulate(o: np.ndarray, target: np.ndarray, cost: float,
             funding: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, int]:
    """Equity at each day's open, 1.0 at the start.

    target[t] is decided on day t's close and becomes the position at day
    t+1's open. A change of position trades |new - old| x equity of notional
    at that open and pays `cost` on it. Units are held between changes (no
    daily rebalancing), so a short is a real short: it loses more than it
    gains on equal moves. Funding for day d is paid on the position held
    during day d: units x open[d] x rate, long pays a positive rate."""
    n = len(o)
    eq = np.ones(n)
    pos = np.zeros(n)
    cash, units, cur, trades = 1.0, 0.0, 0.0, 0
    for d in range(n):
        equity = cash + units * o[d]
        want = target[d - 1] if d > 0 else 0.0
        if want != cur:
            notional = abs(want - cur) * equity
            cash -= notional * cost
            equity -= notional * cost
            new_units = want * equity / o[d]
            cash -= (new_units - units) * o[d]
            units, cur = new_units, want
            trades += 1
        if funding is not None and units != 0:
            cash -= units * o[d] * funding[d]
        eq[d] = cash + units * o[d]
        pos[d] = cur
    return eq, pos, trades


def metrics(eq: pd.Series, pos: pd.Series | None = None) -> dict:
    eq = eq.dropna()
    if len(eq) < 30:
        return {}
    days = (eq.index[-1] - eq.index[0]).days or 1
    r = eq.pct_change().dropna()
    peak = eq.cummax()
    dd = eq / peak - 1
    under, longest = 0, 0
    for x in (eq < peak).to_numpy():
        under = under + 1 if x else 0
        longest = max(longest, under)
    m = {
        "start": str(eq.index[0].date()), "end": str(eq.index[-1].date()),
        "total": float(eq.iloc[-1] / eq.iloc[0] - 1),
        "cagr": float((eq.iloc[-1] / eq.iloc[0]) ** (365 / days) - 1),
        "max_dd": float(-dd.min()),
        "sharpe": float(r.mean() / r.std() * np.sqrt(365)) if r.std() > 0 else 0.0,
        "longest_underwater_days": int(longest),
    }
    if pos is not None:
        p = pos.loc[eq.index]
        m["exposure"] = float((p != 0).mean())
        m["switches"] = int((p.diff().fillna(0) != 0).sum())
    return m


def run_market(market: str) -> dict:
    bars = load_daily(market)
    o, c = bars["open"].to_numpy(), bars["close"]
    cost = (C.SPOT_FEE_TAKER if market == "spot" else C.FEE_TAKER) + C.SLIPPAGE
    fund = daily_funding(bars.index) if market == "perp" else None
    start = bars.index[WARMUP_DAYS]
    hold_t = np.where(np.arange(len(bars)) >= WARMUP_DAYS - 1, 1.0, 0.0)
    runs = {"buy_hold": hold_t}
    for name, (fn, markets) in RULES.items():
        if market in markets:
            t = fn(c).to_numpy(float).copy()
            t[: WARMUP_DAYS - 1] = 0.0  # every run starts on the same day
            runs[name] = t
    res = {"market": market, "cost_per_side": cost, "start": str(start.date()),
           "end": str(bars.index[-1].date()), "rules": {}}
    for name, t in runs.items():
        eq, pos, trades = simulate(o, t, cost, fund)
        eq = pd.Series(eq, index=bars.index).loc[start:]
        pos = pd.Series(pos, index=bars.index)
        seg = {"full": metrics(eq, pos)}
        for label, a, b in SEGMENTS:
            part = eq.loc[a:b]
            if len(part) >= 30:
                seg[label] = metrics(part / part.iloc[0], pos)
        res["rules"][name] = {"trades": trades, "segments": seg}
    return res


# --------------------------------------------------------------------------
# verdict (pre-registered in PLAN.md section 16)
# --------------------------------------------------------------------------
def verdict(rule: dict, hold: dict) -> dict:
    """IMPROVES only if, on the full run AND on each half separately, the
    rule's Sharpe >= buy-and-hold's and its max drawdown <= 0.6 x buy-and-
    hold's. Each half must hold on its own, so one lucky cycle cannot carry
    it."""
    out = {}
    for part in ("full", "first half", "second half"):
        a, b = rule["segments"].get(part), hold["segments"].get(part)
        if not a or not b:
            out[part] = None
            continue
        out[part] = bool(a["sharpe"] >= b["sharpe"] and a["max_dd"] <= 0.6 * b["max_dd"])
    checked = [v for v in out.values() if v is not None]
    out["verdict"] = "IMPROVES" if checked and all(checked) else "NO_IMPROVEMENT"
    return out


def write_report(all_res: dict) -> None:
    L = [f"# {C.SYMBOL} - allocation test (PLAN.md section 16)", "",
         "GENERATED by `src/allocation.py`. Do not edit by hand.", "",
         "Daily bars, 1x exposure, position decided at the close and traded at the next",
         "open. Every rule starts on the same day as buy-and-hold (day 200 of the data).",
         "**IMPROVES** = Sharpe >= buy-and-hold's and max drawdown <= 0.6 x buy-and-",
         "hold's, on the full run and on each half separately.", ""]
    for market, res in all_res.items():
        hold = res["rules"]["buy_hold"]
        L += [f"## {market} ({res['start']} .. {res['end']}, cost {res['cost_per_side']:.2%} per side"
              + (", plus funding" if market == "perp" else "") + ")", "",
              "| rule | verdict | CAGR | max DD | Sharpe | longest underwater (days) | exposure | switches |",
              "|---|---|---|---|---|---|---|---|"]
        for name, r in res["rules"].items():
            f = r["segments"]["full"]
            v = "-" if name == "buy_hold" else r["verdict"]["verdict"]
            L.append(f"| {name} | {v} | {f['cagr']:+.1%} | {f['max_dd']:.1%} | {f['sharpe']:.2f} | "
                     f"{f['longest_underwater_days']} | {f.get('exposure', 1):.0%} | {f.get('switches', 0)} |")
        L += ["", "By segment (total return / max drawdown):", "",
              "| rule | " + " | ".join(lab for lab, _, _ in SEGMENTS) + " |",
              "|---|" + "---|" * len(SEGMENTS)]
        for name, r in res["rules"].items():
            cells = []
            for lab, _, _ in SEGMENTS:
                m = r["segments"].get(lab)
                cells.append(f"{m['total']:+.0%} / {m['max_dd']:.0%}" if m else "-")
            L.append(f"| {name} | " + " | ".join(cells) + " |")
        L.append("")
    REPORT.write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rerun", action="store_true",
                    help="overwrite earlier results - only after a code fix (journal it)")
    a = ap.parse_args()
    summary = OUT / "summary.json"
    if summary.exists() and not a.rerun:
        raise SystemExit(f"{summary} exists: the rules are pre-registered and run once. "
                         "--rerun only after a code fix, recorded in the journal.")
    all_res = {}
    for market in ("spot", "perp"):
        res = run_market(market)
        hold = res["rules"]["buy_hold"]
        for name, r in res["rules"].items():
            if name != "buy_hold":
                r["verdict"] = verdict(r, hold)
        all_res[market] = res
    OUT.mkdir(parents=True, exist_ok=True)
    summary.write_text(json.dumps(all_res, indent=1))
    write_report(all_res)
    for market, res in all_res.items():
        for name, r in res["rules"].items():
            f = r["segments"]["full"]
            print(f"{market:4} {name:18} CAGR {f['cagr']:+7.1%}  maxDD {f['max_dd']:6.1%}  "
                  f"Sharpe {f['sharpe']:5.2f}  " + (r["verdict"]["verdict"] if "verdict" in r else ""))
    print(f"wrote {summary} and {REPORT}")


if __name__ == "__main__":
    main()
