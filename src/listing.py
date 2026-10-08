"""Short newly listed perpetuals (PLAN.md section 35)

    python src/listing.py --build   # daily OHLC + funding of every USDT-M perp, delisted ones included
    python src/listing.py           # TRAIN/VALID, once
    python src/listing.py --final   # HOLDOUT once, only after PASS

Hypothesis: a coin newly listed on Binance USDT-M futures tends to fall for
weeks after the listing. Its holders who got it cheaply (airdrop recipients,
early investors, the team, unlocks) sell into the new liquidity, and the
first-day attention fades. That is a seller with a reason, not a chart pattern.
It is untested here: section 17 explicitly dropped coins younger than 60 days.

Events. One event per perp symbol: its FIRST daily bar on Binance USDT-M (the
listing day), if that day is after LISTED_AFTER (so the 2019-2020 founding
contracts are not "listings"). A relaunch after a gap of more than
rotation.MAX_GAP_DAYS is not an event. Delisted symbols are included.
Trade. Short at the open of day (listing + DELAY); daily bars.
  * protective stop: entry x (1 + STOP); a day whose high reaches it closes the
    trade at max(stop, that day's open) (a gap fills at the open), slippage added;
  * trailing exit (a signal, no clock): when a daily close is above the lowest
    close since entry x (1 + TRAIL), cover at the next open;
  * otherwise the trade is closed at the end of its window ("eod"), or at the
    last traded close if the contract was delisted first ("delisted").
  Funding is counted for every day the short is held past that day's open.
  Costs: taker fee each side, alt slippage (ml_pool.ALT_SLIPPAGE) each side, and
  funding on the short (receives a positive rate, pays a negative one), the
  daily sum of rates x the position's notional at that day's open.
  R = STOP (the stop distance); net R = return on entry notional / STOP.
Account: section 31's accounting at RISK = 0.25% per listing and a CAP of 10%
open risk (about 40 shorts at once, so the cap rarely decides which listing is
taken; one it skips is not retried), weekly returns, bootstrap CI, drawdown.
TRAIN (2021-22) picks 1 of 12 cells (DELAY x STOP x TRAIL) by the weekly account
t-statistic (>= MIN_TRAIN_TRADES trades). VALID (2023-24) judges it once:
  TRAIN weekly mean > 0; >= MIN_TRADES trades; weekly mean > 0 and its 95%
  bootstrap CI lower bound > 0; weekly mean > 0 at cost x1.5; mean net R of all
  events above the 95th percentile of N_CONTROL control draws on TRAIN AND on
  VALID (control: for every event, an ESTABLISHED perp - listed >= CONTROL_AGE
  days before - shorted on the same day with the same exits; this removes the
  market's own move and the general drift of alt-coins); mean net R without the
  5 best trades > 0; each VALID year's summed return > 0; max drawdown <= 20%.
--final: CONFIRMED = holdout weekly mean > 0, CI lower bound > 0, event mean
above the control's 95th percentile.
Diagnostic (not a gate): the event mean for NEW tokens (no Binance spot pair
before the listing month) and for EXISTING tokens that only got a new perp.
Frozen bars after a delisting (zero volume) are cut; an entry or a control
needs a traded day.
Writes results/_multi/s35_listing_1d/ and the generated journal/_multi/s35_listing_1d.md.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
import ml_pool as MPL  # noqa: E402
import ml_port as MP  # noqa: E402
import ml_wf as WF  # noqa: E402
import rotation as R  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "s35_listing_1d"
REPORT = C.ROOT / "journal" / "_multi" / "s35_listing_1d.md"
CACHE = C.ROOT / "data" / "cache" / "_multi" / "listing"
RAW = C.ROOT / "data" / "raw" / "_multi" / "listing"

# ---- pre-registered (PLAN.md section 35)
LISTED_AFTER = "2020-02-01"
DELAY = (1, 3, 7)
STOP = (0.3, 0.5)
TRAIL = (0.3, 0.6)
RISK, CAP = 0.0025, 0.10       # 0.25% per listing, at most 10% open: ~40 at once, so the cap rarely chooses
SLIP = MPL.ALT_SLIPPAGE
MIN_TRAIN_TRADES, MIN_TRADES = 30, 100
CONTROL_AGE, N_CONTROL = 365, 200
WINDOWS = WF.WINDOWS


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
def _read_ohlc(path: Path) -> pd.DataFrame:
    import datafeed as DF
    df = DF._read_one_zip(path, C.KLINE_COLS)
    t = df["open_time"].astype("int64")
    df["date"] = pd.to_datetime(np.where(t > 10**14, t // 1000, t), unit="ms", utc=True).floor("D")
    return df[["date", "open", "high", "low", "close", "quote_volume"]]


def build() -> None:
    import datafeed as DF
    CACHE.mkdir(parents=True, exist_ok=True)
    out, fout = CACHE / "perp_1d.parquet", CACHE / "perp_funding.parquet"
    months = set(C.month_range("2019-09", C.DATA_END))
    syms = R._symbols("perp")
    print(f"[listing] {len(syms)} USDT-M perp symbols (delisted included)", flush=True)
    if not out.exists():
        def one(sym):
            keys = [k for k in DF.list_keys(f"data/futures/{C.MARKET}/monthly/klines/{sym}/1d/")
                    if k[-11:-4] in months]
            fr = [_read_ohlc(p) for p in (DF.fetch_zip(k, RAW / "perp_1d" / sym) for k in keys) if p]
            return pd.concat(fr, ignore_index=True).assign(symbol=sym) if fr else None
        frames = []
        with ThreadPoolExecutor(max_workers=8) as ex:
            for i, d in enumerate(ex.map(one, syms), 1):
                if d is not None:
                    frames.append(d)
                if i % 100 == 0 or i == len(syms):
                    print(f"  klines {i}/{len(syms)}", flush=True)
        df = (pd.concat(frames, ignore_index=True).drop_duplicates(["symbol", "date"])
              .sort_values(["symbol", "date"]).reset_index(drop=True))
        df.to_parquet(out, index=False)
        print(f"[listing] wrote {out.name}: {len(df):,} rows, {df['symbol'].nunique()} symbols", flush=True)
    if not fout.exists():
        symbols = sorted(pd.read_parquet(out, columns=["symbol"])["symbol"].unique())
        def onef(sym):
            keys = [k for k in DF.list_keys(f"data/futures/{C.MARKET}/monthly/fundingRate/{sym}/")
                    if k[-11:-4] in months]
            fr = [DF._read_one_zip(p, C.FUNDING_COLS)
                  for p in (DF.fetch_zip(k, RAW / "perp_funding" / sym) for k in keys) if p]
            return pd.concat(fr, ignore_index=True).assign(symbol=sym) if fr else None
        with ThreadPoolExecutor(max_workers=8) as ex:
            frames = [d for d in ex.map(onef, symbols) if d is not None]
        f = pd.concat(frames, ignore_index=True)
        t = f["calc_time"].astype("int64")
        f["date"] = pd.to_datetime(np.where(t > 10**14, t // 1000, t), unit="ms", utc=True).floor("D")
        f = f.groupby(["symbol", "date"], as_index=False)["last_funding_rate"].sum()
        f.to_parquet(fout, index=False)
        print(f"[listing] wrote {fout.name}: {len(f):,} rows", flush=True)
    sp = CACHE / "spot_first.json"
    if not sp.exists():
        symbols = sorted(pd.read_parquet(out, columns=["symbol"])["symbol"].unique())
        def first_spot(sym):
            k = [x for x in DF.list_keys(f"data/spot/monthly/klines/{sym}/1d/") if x.endswith(".zip")]
            return sym, (min(x[-11:-4] for x in k) if k else None)
        with ThreadPoolExecutor(max_workers=8) as ex:
            sp.write_text(json.dumps(dict(ex.map(first_spot, symbols)), indent=1))
        print(f"[listing] wrote {sp.name}", flush=True)
    print("BUILD OK")


def load() -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    p = CACHE / "perp_1d.parquet"
    if not p.exists():
        raise SystemExit("no daily cache: run  python src/listing.py --build")
    df = R.split_instruments(pd.read_parquet(p))
    fund = pd.read_parquet(CACHE / "perp_funding.parquet")
    bars = {}
    for inst, g in df.groupby("inst"):
        g = g.set_index("date").sort_index()
        live = (g["quote_volume"] > 0).to_numpy()
        if not live.any():
            continue
        g = g.iloc[:int(np.flatnonzero(live)[-1]) + 1]      # frozen bars after a delisting are not a market
        fr = fund[fund["symbol"] == g["symbol"].iloc[0]].set_index("date")["last_funding_rate"]
        g["funding"] = fr.reindex(g.index).fillna(0.0).to_numpy()
        bars[inst] = g[["open", "high", "low", "close", "quote_volume", "funding"]]
    ev = listings(bars)
    sp = CACHE / "spot_first.json"
    first = json.loads(sp.read_text()) if sp.exists() else {}
    ev["new_token"] = [new_token(first.get(i.split("#")[0]), d) for i, d in zip(ev["inst"], ev["listed"])]
    return bars, ev


def new_token(spot_first_month: str | None, listed: pd.Timestamp) -> bool:
    """True when Binance spot had no such pair before the perp's listing month
    (month precision: a spot pair first traded in the listing month counts as new)."""
    return spot_first_month is None or spot_first_month >= listed.strftime("%Y-%m")


# --------------------------------------------------------------------------
# pure pieces (test 31)
# --------------------------------------------------------------------------
def listings(bars: dict[str, pd.DataFrame], after: str = LISTED_AFTER) -> pd.DataFrame:
    """One row per first run of a symbol whose first bar is after `after`."""
    rows = [{"inst": i, "listed": b.index[0]} for i, b in bars.items()
            if "#" not in i and len(b) and b.index[0] >= pd.Timestamp(after, tz="UTC")]
    return pd.DataFrame(rows, columns=["inst", "listed"]).sort_values("listed").reset_index(drop=True)


def short_trade(b: pd.DataFrame, entry_day: pd.Timestamp, end: pd.Timestamp, stop: float, trail: float,
                fee: float = C.FEE_TAKER, slip: float = SLIP) -> dict | None:
    """One short entered at the open of entry_day, on daily bars, until end (exclusive)."""
    i0 = b.index.searchsorted(entry_day)
    if i0 >= len(b) or b.index[i0] != entry_day or b.index[i0] >= end:
        return None
    o, h, c = b["open"].to_numpy(float), b["high"].to_numpy(float), b["close"].to_numpy(float)
    fu = b["funding"].to_numpy(float)
    if not (o[i0] > 0) or not (b["quote_volume"].iloc[i0] > 0):
        return None
    entry = o[i0]
    stop_px = entry * (1 + stop)
    n_end = b.index.searchsorted(end)
    low_close, fund_sum, pending = np.inf, 0.0, False
    exit_px, reason, j = None, "eod", n_end - 1
    for jj in range(i0, n_end):
        if pending:                                       # yesterday's close crossed the trail: cover at the open
            exit_px, reason, j = o[jj], "signal", jj
            break
        fund_sum += fu[jj] * o[jj] / entry                # held through this day: its funding, on today's notional
        if h[jj] >= stop_px:
            exit_px, reason, j = max(stop_px, o[jj]), "stop", jj
            break
        low_close = min(low_close, c[jj])
        pending = c[jj] > low_close * (1 + trail)
    if exit_px is None:
        exit_px = c[j]
        if b.index[-1] + pd.Timedelta(days=1) < end and j == len(b) - 1:
            reason = "delisted"                           # settled at the last traded close
    e_fill, x_fill = entry * (1 - slip), exit_px * (1 + slip)
    gross = (entry - exit_px) / entry
    ret = (e_fill - x_fill) / e_fill - 2 * fee + fund_sum
    return {"entry_time": b.index[i0], "exit_time": b.index[j] + (pd.Timedelta(days=1) if reason in ("eod", "delisted") else pd.Timedelta(0)),
            "side": -1.0, "entry_px": entry, "exit_px": exit_px, "reason": reason, "days": int(j - i0 + 1),
            "gross_r": gross / stop, "net_r": ret / stop, "funding_r": fund_sum / stop}


def year_of_exit(exit_time: pd.Series) -> pd.Series:
    """Calendar year a trade's exit belongs to. An `eod` exit is stamped at the window
    end (00:00 of the next year), so one microsecond is taken off (_multi Exp 046)."""
    return (pd.to_datetime(exit_time, utc=True) - pd.Timedelta(microseconds=1)).dt.year


def event_trades(bars, ev, a, b, delay, stop, trail, stress=1.0) -> pd.DataFrame:
    end = pd.Timestamp(b, tz="UTC")
    rows = []
    for x in ev.itertuples():
        day = x.listed + pd.Timedelta(days=delay)
        if not (pd.Timestamp(a, tz="UTC") <= day < end):
            continue
        t = short_trade(bars[x.inst], day, end, stop, trail, C.FEE_TAKER * stress, SLIP * stress)
        if t:
            rows.append({**t, "coin": x.inst})
    t = pd.DataFrame(rows)
    if len(t):
        t["conf"] = np.nan
    return t


def control_means(bars, ev, a, b, delay, stop, trail, n=N_CONTROL, seed=35) -> np.ndarray:
    """For each draw, the mean net R of shorting, on every event's entry day, one
    random ESTABLISHED perp (listed >= CONTROL_AGE days before, trading that day)."""
    rng = np.random.default_rng(seed)
    end = pd.Timestamp(b, tz="UTC")
    first = {i: bk.index[0] for i, bk in bars.items()}
    days = [x.listed + pd.Timedelta(days=delay) for x in ev.itertuples()]
    days = [d for d in days if pd.Timestamp(a, tz="UTC") <= d < end]
    pools = []
    for d in days:
        pools.append([i for i, f in first.items()
                      if f <= d - pd.Timedelta(days=CONTROL_AGE) and d in bars[i].index
                      and bars[i].at[d, "quote_volume"] > 0])
    cache, out = {}, np.full(n, np.nan)
    for k in range(n):
        vals = []
        for d, pool in zip(days, pools):
            if not pool:
                continue
            inst = pool[int(rng.integers(len(pool)))]
            key = (inst, d)
            if key not in cache:
                t = short_trade(bars[inst], d, end, stop, trail)
                cache[key] = t["net_r"] if t else np.nan
            vals.append(cache[key])
        v = np.asarray(vals, float)
        out[k] = np.nanmean(v) if np.isfinite(v).any() else np.nan
    return out


def _acct(t, a, b):
    """section 31's sizing at RISK per trade (size_trades works in units of its 1%)."""
    k = RISK / MP.BASE_RISK
    if not len(t):
        s = t.assign(risk=[], ret=[])
    else:
        s = MP.size_trades(t, "flat", CAP / k)
        s["risk"] = s["risk"] * k
        s["ret"] = s["net_r"] * s["risk"]
    return s, MP.account(s, a, b)


def judge(bars, ev, a, b, cell) -> tuple[dict, pd.DataFrame]:
    t_all = event_trades(bars, ev, a, b, cell["delay"], cell["stop"], cell["trail"])
    t, acc = _acct(t_all, a, b)
    acc["stress_weekly_mean"] = _acct(event_trades(bars, ev, a, b, cell["delay"], cell["stop"], cell["trail"], 1.5),
                                      a, b)[1]["weekly_mean"]
    ctl = control_means(bars, ev, a, b, cell["delay"], cell["stop"], cell["trail"])
    srt = np.sort(t["net_r"].to_numpy())[::-1] if len(t) else np.zeros(0)
    acc.update(events=int(len(t_all)), event_mean_r=float(t_all["net_r"].mean()) if len(t_all) else None,
               control_p95=float(np.nanpercentile(ctl, 95)) if np.isfinite(ctl).any() else None,
               mean_r_wo_top5=float(srt[5:].mean()) if len(srt) > 5 else None,
               gross_r=float(t["gross_r"].mean()) if len(t) else None,
               funding_r=float(t["funding_r"].mean()) if len(t) else None,
               exits={k: int(v) for k, v in t["reason"].value_counts().items()} if len(t) else {},
               avg_days=float(t["days"].mean()) if len(t) else None,
               per_year_r={str(y): float(g["ret"].sum()) for y, g in t.groupby(year_of_exit(t["exit_time"]))}
               if len(t) else {})
    if "new_token" in ev and len(t_all):
        nt = dict(zip(ev["inst"], ev["new_token"]))
        is_new = t_all["coin"].map(nt).fillna(True).astype(bool)
        acc["by_token"] = {"new": {"events": int(is_new.sum()), "mean_r": float(t_all.loc[is_new, "net_r"].mean())
                                   if is_new.any() else None},
                           "existing": {"events": int((~is_new).sum()), "mean_r": float(t_all.loc[~is_new, "net_r"].mean())
                                        if (~is_new).any() else None}}
    acc["control_p50"] = float(np.nanpercentile(ctl, 50)) if np.isfinite(ctl).any() else None
    acc["control_events"] = int(np.isfinite(ctl).sum())
    return acc, t


def evaluate(bars, ev, keep=False) -> dict:
    a_tr, b_tr = WINDOWS["train"]
    a_va, b_va = WINDOWS["valid"]
    table = []
    for delay, stop, trail in itertools.product(DELAY, STOP, TRAIL):
        t, acc = _acct(event_trades(bars, ev, a_tr, b_tr, delay, stop, trail), a_tr, b_tr)
        table.append({"delay": delay, "stop": stop, "trail": trail, **{k: acc[k] for k in
                      ("trades", "weekly_mean", "tstat", "per_year", "max_dd", "mean_r")}})
        print(f"TRAIN delay {delay} stop {stop} trail {trail}: {acc['trades']} trades, weekly "
              f"{acc['weekly_mean']:+.5f}, t {acc['tstat']:+.2f}, dd {acc['max_dd']:.3f}", flush=True)
    ok = [x for x in table if x["trades"] >= MIN_TRAIN_TRADES]
    best = max(ok, key=lambda x: x["tstat"]) if ok else table[0]
    cell = {k: best[k] for k in ("delay", "stop", "trail")}
    tr, _ = judge(bars, ev, a_tr, b_tr, cell)
    v, t = judge(bars, ev, a_va, b_va, cell)
    yrs = [str(y) for y in range(int(a_va[:4]), int(b_va[:4]))]
    gates = {"train_weekly_mean>0": best["weekly_mean"] > 0 and best in ok,
             f"valid_trades>={MIN_TRADES}": v["trades"] >= MIN_TRADES,
             "valid_weekly_mean>0": v["weekly_mean"] > 0,
             "valid_ci_lo>0": v["ci_lo"] > 0,
             "stress_weekly_mean>0": v["stress_weekly_mean"] > 0,
             "train_beats_control_p95": tr["control_p95"] is not None and tr["event_mean_r"] is not None
             and tr["event_mean_r"] > tr["control_p95"],
             "valid_beats_control_p95": v["control_p95"] is not None and v["event_mean_r"] is not None
             and v["event_mean_r"] > v["control_p95"],
             "mean_r_without_top5>0": v["mean_r_wo_top5"] is not None and v["mean_r_wo_top5"] > 0,
             "each_valid_year>0": all(v["per_year_r"].get(y, 0.0) > 0 for y in yrs),
             f"max_dd<={MP.MAX_DD}": v["max_dd"] <= MP.MAX_DD}
    failed = [k for k, g in gates.items() if not g]
    res = {"chosen": cell, "train_table": table, "train_control": {k: tr[k] for k in
           ("events", "event_mean_r", "control_p50", "control_p95")}, "valid": v,
           "verdict": "REJECT" if failed else "PASS", "gates_failed": failed}
    if keep:
        res["_trades"] = t
    return res


def run(final: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    res_path, lock = OUT / "summary.json", OUT / "holdout.json"
    if final:
        res = json.loads(res_path.read_text()) if res_path.exists() else None
        if not res or res["verdict"] != "PASS":
            raise SystemExit("--final refused: needs a PASS from the TRAIN/VALID run")
        if lock.exists():
            raise SystemExit(f"--final refused: holdout already used ({lock})")
    elif res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    bars, ev = load()
    if final:
        a, b = WINDOWS["holdout"]
        h, t = judge(bars, ev, a, b, res["chosen"])
        h["verdict"] = ("CONFIRMED" if h["weekly_mean"] > 0 and h["ci_lo"] > 0 and h["control_p95"] is not None
                        and h["event_mean_r"] > h["control_p95"] else "FAILED")
        lock.write_text(json.dumps(h, indent=1, default=str))
        t.to_csv(OUT / "trades_holdout.csv.gz", index=False)
        write_report(res)
        print(json.dumps({k: h.get(k) for k in ("trades", "weekly_mean", "ci_lo", "verdict")}, indent=1))
        return
    print(f"[listing] {len(ev)} listings after {LISTED_AFTER}; by year "
          f"{ev['listed'].dt.year.value_counts().sort_index().to_dict()}", flush=True)
    res = evaluate(bars, ev, keep=True)
    res["listings_by_year"] = {str(k): int(v) for k, v in ev["listed"].dt.year.value_counts().sort_index().items()}
    res.pop("_trades").to_csv(OUT / "trades_valid.csv.gz", index=False)
    res_path.write_text(json.dumps(res, indent=1, default=str))
    write_report(res)
    print(f"\nLISTING: chose {res['chosen']} -> {res['verdict']} failed {res['gates_failed']}")


def write_report(r: dict) -> None:
    v = r["valid"]
    f = (lambda x, k=5: "-" if x is None else f"{x:+.{k}f}")
    tc = r["train_control"]
    L = ["# Short newly listed perpetuals (PLAN.md section 35)", "",
         "GENERATED by `src/listing.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}** (TRAIN chose {r['chosen']}; failed: {r['gates_failed'] or 'none'})", "",
         f"- listings by year: {r.get('listings_by_year')}",
         f"- VALID {v['trades']} trades taken of {v['events']} events, {v['weeks']} weeks: weekly account return "
         f"{f(v['weekly_mean'])}, 95% CI [{f(v['ci_lo'])}, {f(v['ci_hi'])}], t {v['tstat']:+.2f}; per year "
         f"{f(v['per_year'], 4)}; max drawdown {v['max_dd']:.4f}; by year {v['per_year_r']}",
         f"- mean net R {f(v['mean_r'], 4)} (gross {f(v['gross_r'], 4)}, funding {f(v['funding_r'], 4)}), without the 5 "
         f"best {f(v['mean_r_wo_top5'], 4)}; exits {v['exits']}; average {f(v['avg_days'], 1)} days; cost x1.5 weekly "
         f"{f(v['stress_weekly_mean'])}",
         f"- control (an established perp shorted the same day): VALID event mean {f(v['event_mean_r'], 4)} vs control "
         f"median {f(v['control_p50'], 4)} / p95 {f(v['control_p95'], 4)}; TRAIN {f(tc['event_mean_r'], 4)} vs "
         f"{f(tc['control_p50'], 4)} / {f(tc['control_p95'], 4)}",
         f"- diagnostic, VALID events by token (new = no Binance spot pair before the listing month): "
         f"{v.get('by_token')}", "",
         "| delay | stop | trail | TRAIN trades | weekly mean | t | per year | max DD | mean R |",
         "|---|---|---|---|---|---|---|---|---|"]
    for x in r["train_table"]:
        L.append(f"| {x['delay']} | {x['stop']} | {x['trail']} | {x['trades']} | {f(x['weekly_mean'])} | "
                 f"{x['tstat']:+.2f} | {f(x['per_year'], 4)} | {x['max_dd']:.4f} | {f(x['mean_r'], 4)} |")
    hp = OUT / "holdout.json"
    if hp.exists():
        h = json.loads(hp.read_text())
        L += ["", f"**HOLDOUT: {h['verdict']}** - {h['trades']} trades, weekly {f(h['weekly_mean'])}, CI "
              f"[{f(h['ci_lo'])}, {f(h['ci_hi'])}], event mean {f(h['event_mean_r'], 4)} vs control p95 "
              f"{f(h['control_p95'], 4)}"]
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
