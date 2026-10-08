"""Cross-sectional momentum (rotation) across Binance coins - PLAN.md section 17.

    python src/rotation.py --build spot     # download + cache every USDT spot pair, daily
    python src/rotation.py --build perp     # same for USDT-M perps, plus their funding
    python src/rotation.py spot             # TRAIN select -> VALID verdict
    python src/rotation.py perp
    python src/rotation.py spot --final     # one-time HOLDOUT, only after PASS

The question is not "when to trade BTC" (440 evaluations: no) but "which coins
to hold this week". Every Monday, rank the most liquid coins by their past
return and hold the strongest (spot: long-only top fifth; perp: long the top
fifth, short the bottom fifth, market-neutral).

Honesty rules built in:
  * Survivorship: the universe is every USDT pair Binance ever listed,
    delisted ones included (LUNA, FTT, ...). It is chosen each week from data
    before that week only: 30-day average quote volume, top N.
  * A symbol whose daily file has a gap of more than MAX_GAP_DAYS is split
    into separate instruments: LUNAUSDT is old LUNA until 2022-05-13 and a new
    coin from 2022-05-31, and joining them would show a 2,000,000% jump.
  * A coin whose data ends mid-week (delisted) is exited at its last close.
  * Signals use closes up to Sunday; trades fill at Monday's open.
  * Costs on turnover against drifted weights; perps pay or receive funding.
  * Lookback is the only choice, made on TRAIN; VALID gives the verdict;
    HOLDOUT runs once (--final), and only after PASS.

Outputs: results/_multi/s17_rotation_1d/<market>.json, <market>_weeks.csv.gz,
holdout_<market>.json, and the generated journal/_multi/s17_rotation_1d.md.
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
import datafeed as DF  # noqa: E402

RAW = C.ROOT / "data" / "raw" / "_multi"
CACHE = C.ROOT / "data" / "cache" / "_multi"
OUT = C.ROOT / "results" / "_multi" / "s17_rotation_1d"
REPORT = C.ROOT / "journal" / "_multi" / "s17_rotation_1d.md"

# ---- pre-registered design (PLAN.md section 17); changing any of these is a
# ---- new test that needs the owner, not a tweak
LOOKBACKS = (7, 14, 28)        # days of past return; chosen on TRAIN only
UNIVERSE_N = 30                # most liquid coins each week
MIN_UNIVERSE = 15              # fewer eligible coins -> the week is skipped
TOP_FRACTION = 0.2             # top (and bottom) fifth
MIN_K = 3
MIN_AGE_DAYS = 60              # no fresh listings
VOLUME_DAYS = 30
MAX_GAP_DAYS = 3               # a longer hole starts a new instrument
SPOT_COST = C.SPOT_FEE_TAKER + 0.0005   # 0.10% fee + 0.05% slippage (alts)
PERP_COST = C.FEE_TAKER + 0.0005        # 0.05% fee + 0.05% slippage
SPLITS = {"train": ("2018-01-01", "2023-01-01"), "valid": ("2023-01-01", "2025-01-01"),
          "holdout": ("2025-01-01", "2026-09-01")}
BLOCK_WEEKS = 4
N_BOOT = 5000
MAX_STAT_DD = 0.30

STABLE = {"USDC", "BUSD", "TUSD", "UST", "USTC", "USDP", "PAX", "DAI", "FDUSD", "USDD",
          "USDS", "USDSB", "SUSD", "AEUR", "EURI", "XUSD", "USD1", "BFUSD", "USDE", "PYUSD",
          "RLUSD", "EUR", "GBP", "AUD", "TRY", "BRL", "RUB", "BIDR", "IDRT", "UAH", "NGN",
          "ZAR", "PLN", "RON", "ARS", "JPY", "MXN", "COP", "CZK", "BKRW", "BVND", "PAXG",
          "WBTC", "WBETH", "BETH"}


def tradable(symbol: str, all_symbols: set[str]) -> bool:
    """A USDT pair that is a coin: not a stablecoin, fiat, wrapped duplicate
    or leveraged token (BTCUP/BTCDOWN, BNBBULL/BNBBEAR)."""
    if not symbol.endswith("USDT"):
        return False
    base = symbol[:-4]
    if not base or base in STABLE:
        return False
    if base.endswith(("DOWN", "BULL", "BEAR")):
        return False
    if base.endswith("UP") and len(base) > 3 and base[:-2] + "USDT" in all_symbols:
        return False  # SUSHIUP is a leveraged token; JUP is a coin
    return True


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
def _symbols(market: str) -> list[str]:
    from urllib.parse import quote
    from xml.etree import ElementTree as ET
    prefix = ("data/spot/monthly/klines/" if market == "spot"
              else f"data/futures/{C.MARKET}/monthly/klines/")
    out, token = [], None
    while True:
        url = f"{C.S3}?list-type=2&delimiter=/&prefix={prefix}"
        if token:
            url += f"&continuation-token={quote(token, safe='')}"
        root = ET.fromstring(DF._get(url))
        out += [p.text.split("/")[-2] for p in root.findall("s3:CommonPrefixes/s3:Prefix", DF.NS)]
        t = root.find("s3:IsTruncated", DF.NS)
        if t is None or t.text != "true":
            break
        token = root.find("s3:NextContinuationToken", DF.NS).text
    allset = set(out)
    return sorted(s for s in out if tradable(s, allset))


def _read_daily(path: Path) -> pd.DataFrame:
    df = DF._read_one_zip(path, C.KLINE_COLS)
    t = df["open_time"].astype("int64")
    df["date"] = pd.to_datetime(np.where(t > 10**14, t // 1000, t), unit="ms", utc=True).floor("D")
    return df[["date", "open", "close", "quote_volume"]]


def build(market: str) -> Path:
    """Download every tradable USDT pair's daily klines into one long parquet."""
    out = CACHE / f"{market}_1d.parquet"
    if out.exists():
        print(f"[{market}] cached -> {out}")
        return out
    CACHE.mkdir(parents=True, exist_ok=True)
    syms = _symbols(market)
    months = set(C.month_range("2017-01", C.DATA_END))
    base = ("data/spot/monthly/klines/{s}/1d/" if market == "spot"
            else f"data/futures/{C.MARKET}/monthly/klines/{{s}}/1d/")
    print(f"[{market}] {len(syms)} tradable USDT symbols", flush=True)

    def one(sym: str) -> pd.DataFrame | None:
        keys = [k for k in DF.list_keys(base.format(s=sym)) if k[-11:-4] in months]
        frames = []
        for k in keys:
            p = DF.fetch_zip(k, RAW / f"{market}_1d" / sym)
            if p is not None:
                frames.append(_read_daily(p))
        if not frames:
            return None
        d = pd.concat(frames, ignore_index=True)
        d["symbol"] = sym
        return d

    frames = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, d in enumerate(ex.map(one, syms), 1):
            if d is not None:
                frames.append(d)
            if i % 50 == 0 or i == len(syms):
                print(f"  {i}/{len(syms)} symbols", flush=True)
    df = (pd.concat(frames, ignore_index=True).drop_duplicates(["symbol", "date"])
          .sort_values(["symbol", "date"]).reset_index(drop=True))
    df.to_parquet(out, index=False)
    print(f"[{market}] wrote {out}  rows={len(df):,}  symbols={df['symbol'].nunique()}")
    if market == "perp":
        build_funding(sorted(df["symbol"].unique()))
    return out


def build_funding(symbols: list[str]) -> Path:
    """Funding history of every perp symbol, one long parquet."""
    out = CACHE / "perp_funding.parquet"
    if out.exists():
        return out
    months = set(C.month_range("2019-09", C.DATA_END))

    def one(sym: str) -> pd.DataFrame | None:
        keys = [k for k in DF.list_keys(f"data/futures/{C.MARKET}/monthly/fundingRate/{sym}/")
                if k[-11:-4] in months]
        frames = [DF._read_one_zip(p, C.FUNDING_COLS)
                  for p in (DF.fetch_zip(k, RAW / "perp_funding" / sym) for k in keys) if p]
        if not frames:
            return None
        d = pd.concat(frames, ignore_index=True)
        d["symbol"] = sym
        return d

    with ThreadPoolExecutor(max_workers=8) as ex:
        frames = [d for d in ex.map(one, symbols) if d is not None]
    f = pd.concat(frames, ignore_index=True)
    f["date"] = pd.to_datetime(f["calc_time"], unit="ms", utc=True).dt.floor("D")
    f = f.groupby(["symbol", "date"], as_index=False)["last_funding_rate"].sum()
    f.to_parquet(out, index=False)
    print(f"[funding] wrote {out}  rows={len(f):,}")
    return out


def split_instruments(df: pd.DataFrame, max_gap: int = MAX_GAP_DAYS) -> pd.DataFrame:
    """Rename runs separated by more than max_gap days: SYM, SYM#1, SYM#2 ..."""
    df = df.sort_values(["symbol", "date"]).copy()
    gap = df.groupby("symbol")["date"].diff().dt.days.fillna(0)
    run = (gap > max_gap).astype(int).groupby(df["symbol"]).cumsum()
    df["inst"] = np.where(run > 0, df["symbol"] + "#" + run.astype(str), df["symbol"])
    return df


def panels(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    df = split_instruments(df)
    p = {c: df.pivot(index="date", columns="inst", values=c).sort_index()
         for c in ("open", "close", "quote_volume")}
    full = pd.date_range(p["close"].index[0], p["close"].index[-1], freq="D", tz="UTC")
    return {k: v.reindex(full) for k, v in p.items()}


# --------------------------------------------------------------------------
# the weekly backtest
# --------------------------------------------------------------------------
def universe(P: dict, s: pd.Timestamp, lookback: int) -> pd.Index:
    """Coins eligible on signal day s (Sunday), from data up to s only."""
    c, qv = P["close"], P["quote_volume"]
    if s not in c.index:
        return pd.Index([])
    i = c.index.get_loc(s)
    age_ok = c.iloc[max(0, i - MIN_AGE_DAYS + 1): i + 1].notna().sum() >= MIN_AGE_DAYS
    has = c.iloc[i].notna() & (c.iloc[i - lookback].notna() if i >= lookback else False)
    vol = qv.iloc[max(0, i - VOLUME_DAYS + 1): i + 1]
    vol_ok = vol.notna().sum() >= VOLUME_DAYS - 5
    ok = age_ok & has & vol_ok
    ranked = vol.mean()[ok[ok].index].sort_values(ascending=False)
    return ranked.index[:UNIVERSE_N]


def week_return(P: dict, inst: str, r: pd.Timestamp, nxt: pd.Timestamp) -> float:
    """Open of Monday r to open of the next Monday; if the coin's data ends in
    between (delisted), out at its last close."""
    o, c = P["open"][inst], P["close"][inst]
    entry = o.get(r, np.nan)
    if not np.isfinite(entry) or entry <= 0:
        return np.nan
    exit_ = o.get(nxt, np.nan)
    if not np.isfinite(exit_):
        last = c.loc[r: nxt - pd.Timedelta(days=1)].dropna()
        exit_ = last.iloc[-1] if len(last) else entry
    return float(exit_ / entry - 1)


def backtest(P: dict, market: str, lookback: int, cost: float,
             funding: pd.DataFrame | None = None, start=None, end=None) -> pd.DataFrame:
    """One row per rebalance week: portfolio net return, equal-weight universe
    net return, and the test statistic (spot: top minus universe; perp: the
    long/short book)."""
    dates = P["close"].index
    mondays = [d for d in dates if d.weekday() == 0
               and (start is None or d >= pd.Timestamp(start, tz="UTC"))
               and (end is None or d < pd.Timestamp(end, tz="UTC"))]
    fund = None
    if funding is not None:
        fund = funding.pivot(index="date", columns="symbol", values="last_funding_rate")
    rows, w_prev, w_prev_u = [], pd.Series(dtype=float), pd.Series(dtype=float)
    for r, nxt in zip(mondays[:-1], mondays[1:]):
        s = r - pd.Timedelta(days=1)
        uni = universe(P, s, lookback)
        uni = pd.Index([u for u in uni if np.isfinite(P["open"][u].get(r, np.nan))])
        if len(uni) < MIN_UNIVERSE:
            w_prev = w_prev_u = pd.Series(dtype=float)
            continue
        i = dates.get_loc(s)
        score = (P["close"][uni].iloc[i] / P["close"][uni].iloc[i - lookback] - 1).sort_values()
        k = max(MIN_K, int(round(len(uni) * TOP_FRACTION)))
        w = pd.Series(1.0 / k, index=score.index[-k:])
        if market == "perp":
            w = pd.concat([w * 0.5, pd.Series(-0.5 / k, index=score.index[:k])])
        wu = pd.Series(1.0 / len(uni), index=uni)
        rets = pd.Series({u: week_return(P, u, r, nxt) for u in uni}).fillna(0.0)

        def step(w_t, w_old):
            turn = w_t.sub(w_old, fill_value=0).abs().sum()
            gross = float((w_t * rets.reindex(w_t.index)).sum())
            fcost, nofund = 0.0, 0
            if fund is not None:
                fwin = fund.loc[r: nxt - pd.Timedelta(days=1)]
                base = pd.Index([x.split("#")[0] for x in w_t.index])
                win = fwin.reindex(columns=base)
                # a position with no funding row in the week pays 0; counted
                # and reported, because it can only flatter the book (_multi Exp 000)
                nofund = int(win.notna().sum().eq(0).sum()) if len(fwin) else len(w_t)
                rate = win.sum().to_numpy() if len(fwin) else np.zeros(len(w_t))
                fcost = float((w_t.to_numpy() * np.nan_to_num(rate)).sum())
            net = gross - turn * cost - fcost
            # weights at the end of the week: each position's value moved with
            # its coin (a short's notional too), equity moved by the gross return
            tot = 1 + gross
            drift = w_t * (1 + rets.reindex(w_t.index)) / tot if tot > 0 else w_t * 0
            return net, turn, fcost, drift, nofund

        net, turn, fcost, w_prev, nofund = step(w, w_prev)
        net_u, _, _, w_prev_u, _ = step(wu, w_prev_u)
        rows.append({"week": r, "n_universe": len(uni), "k": k, "net": net, "net_universe": net_u,
                     "turnover": turn, "funding": fcost, "no_funding_positions": nofund,
                     "stat": net - net_u if market == "spot" else net,
                     "held": ",".join(w.index)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# statistics and verdict
# --------------------------------------------------------------------------
def block_ci(x: np.ndarray, block: int = BLOCK_WEEKS, n: int = N_BOOT, seed: int = 17) -> tuple:
    x = np.asarray(x, float)
    if len(x) < 2 * block:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(len(x) / block))
    starts = rng.integers(0, len(x) - block + 1, size=(n, nb))
    idx = (starts[:, :, None] + np.arange(block)).reshape(n, -1)[:, :len(x)]
    m = x[idx].mean(axis=1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def summarize(w: pd.DataFrame) -> dict:
    if w.empty:
        return {"weeks": 0}
    x = w["stat"].to_numpy()
    eq = np.cumprod(1 + x)
    eq_p = np.cumprod(1 + w["net"].to_numpy())
    lo, hi = block_ci(x)
    return {"weeks": int(len(w)), "mean_stat": float(x.mean()), "ci_lo": lo, "ci_hi": hi,
            "sharpe_stat": float(x.mean() / x.std() * np.sqrt(52)) if x.std() > 0 else 0.0,
            "stat_max_dd": float(1 - (eq / np.maximum.accumulate(eq)).min()),
            "portfolio_cagr": float(eq_p[-1] ** (52 / len(eq_p)) - 1),
            "portfolio_max_dd": float(1 - (eq_p / np.maximum.accumulate(eq_p)).min()),
            "universe_cagr": float(np.prod(1 + w["net_universe"]) ** (52 / len(w)) - 1),
            "mean_turnover": float(w["turnover"].mean()), "mean_funding": float(w["funding"].mean()),
            "weeks_with_unfunded_positions": int((w["no_funding_positions"] > 0).sum())}


def verdict(train: dict, valid: dict, valid_stress: dict) -> tuple[str, list[str]]:
    gates = {
        "train_mean>0": train.get("mean_stat", -1) > 0,
        "valid_weeks>=100": valid.get("weeks", 0) >= 100,
        "valid_mean>0": valid.get("mean_stat", -1) > 0,
        "valid_ci_lo>0": (valid.get("ci_lo") or -1) > 0,
        "stress_mean>0": valid_stress.get("mean_stat", -1) > 0,
        f"stat_max_dd<={MAX_STAT_DD:.0%}": valid.get("stat_max_dd", 1) <= MAX_STAT_DD,
    }
    failed = [k for k, v in gates.items() if not v]
    return ("PASS" if not failed else "REJECT"), failed


def load(market: str):
    p = CACHE / f"{market}_1d.parquet"
    if not p.exists():
        raise SystemExit(f"no {p}: run  python src/rotation.py --build {market}")
    P = panels(pd.read_parquet(p))
    fund = pd.read_parquet(CACHE / "perp_funding.parquet") if market == "perp" else None
    return P, fund


def run(market: str, final: bool = False) -> None:
    P, fund = load(market)
    cost = SPOT_COST if market == "spot" else PERP_COST
    OUT.mkdir(parents=True, exist_ok=True)
    res_path = OUT / f"{market}.json"
    if final:
        if not res_path.exists():
            raise SystemExit("--final refused: run the TRAIN/VALID step first")
        res = json.loads(res_path.read_text())
        if res["verdict"] != "PASS":
            raise SystemExit(f"--final refused: verdict is {res['verdict']}, not PASS")
        lock = OUT / f"holdout_{market}.json"
        if lock.exists():
            raise SystemExit(f"--final refused: the holdout was already used ({lock})")
        L = res["chosen_lookback"]
        h = backtest(P, market, L, cost, fund, *SPLITS["holdout"])
        hs = summarize(h)
        hs["verdict"] = "CONFIRMED" if hs.get("mean_stat", -1) > 0 and (hs.get("ci_lo") or -1) > 0 else "FAILED"
        lock.write_text(json.dumps({"lookback": L, **hs}, indent=1))
        print(json.dumps(hs, indent=1))
        return
    if res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a "
                         "journaled code fix)")
    train = {}
    for L in LOOKBACKS:
        train[L] = summarize(backtest(P, market, L, cost, fund, *SPLITS["train"]))
        print(f"TRAIN L={L:2d}: {train[L]}", flush=True)
    L = max(LOOKBACKS, key=lambda x: train[x].get("sharpe_stat", -9))
    vw = backtest(P, market, L, cost, fund, *SPLITS["valid"])
    valid = summarize(vw)
    stress = summarize(backtest(P, market, L, cost * 1.5, fund, *SPLITS["valid"]))
    v, failed = verdict(train[L], valid, stress)
    res = {"market": market, "cost_per_side": cost, "chosen_lookback": L,
           "train": {str(k): t for k, t in train.items()}, "valid": valid,
           "valid_stress": stress, "verdict": v, "gates_failed": failed}
    res_path.write_text(json.dumps(res, indent=1))
    vw.to_csv(OUT / f"{market}_weeks.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    write_report()
    print(f"\n{market}: lookback {L} -> {v}  failed: {failed}\nVALID {valid}")


def write_report() -> None:
    L = ["# Rotation (cross-sectional momentum) - PLAN.md section 17", "",
         "GENERATED by `src/rotation.py`. Do not edit by hand.", ""]
    for market in ("spot", "perp"):
        p = OUT / f"{market}.json"
        if not p.exists():
            continue
        r = json.loads(p.read_text())
        v = r["valid"]
        L += [f"## {market}: **{r['verdict']}** (lookback {r['chosen_lookback']} d chosen on TRAIN)", "",
              f"- gates failed: {r['gates_failed'] or 'none'}",
              f"- VALID {v['weeks']} weeks: mean weekly stat {v['mean_stat']:+.4f}, "
              f"95% block CI [{v['ci_lo']:+.4f}, {v['ci_hi']:+.4f}], Sharpe {v['sharpe_stat']:.2f}, "
              f"stat maxDD {v['stat_max_dd']:.1%}",
              f"- portfolio CAGR {v['portfolio_cagr']:+.1%}, maxDD {v['portfolio_max_dd']:.1%}; "
              f"equal-weight universe CAGR {v['universe_cagr']:+.1%}; turnover {v['mean_turnover']:.2f}/week",
              f"- cost x1.5: mean stat {r['valid_stress']['mean_stat']:+.4f}", "",
              "| TRAIN lookback | weeks | mean stat | CI | Sharpe |", "|---|---|---|---|---|"]
        for k, t in r["train"].items():
            L.append(f"| {k} | {t['weeks']} | {t['mean_stat']:+.4f} | [{t['ci_lo']:+.4f}, {t['ci_hi']:+.4f}] | {t['sharpe_stat']:.2f} |")
        h = OUT / f"holdout_{market}.json"
        if h.exists():
            hj = json.loads(h.read_text())
            L += ["", f"**HOLDOUT: {hj['verdict']}** - {hj['weeks']} weeks, mean {hj['mean_stat']:+.4f}, "
                      f"CI [{hj['ci_lo']:+.4f}, {hj['ci_hi']:+.4f}]"]
        L.append("")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("market", nargs="?", choices=["spot", "perp"])
    ap.add_argument("--build", choices=["spot", "perp"])
    ap.add_argument("--final", action="store_true")
    a = ap.parse_args()
    if a.build:
        build(a.build)
    elif a.market:
        run(a.market, a.final)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
