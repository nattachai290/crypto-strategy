"""Walk-forward ML with history from 2017 (PLAN.md section 29)

    python src/rotation.py --build spot     # once, if data/cache/_multi/spot_1d.parquet is missing
    python src/rotation.py --build perp     # once, if data/cache/_multi/perp_1d.parquet is missing
    python src/ml_wf2.py --build            # spot 1h/4h/1d from 2017-08 + perp 1h/4h/1d + funding
    python src/ml_wf2.py                    # TRAIN/VALID for 1h, 4h and 1d, once
    python src/ml_wf2.py --final            # HOLDOUT once, one timeframe, only after PASS

The owner's request (2026-10-03), after the section 28 review: the model saw
only three market regimes (2020-21 up, 2022 down, 2023-24 up), shorted rallies
it had learned to fade in 2021-22, and its forecasts were too weak to tell the
sign. More history adds regimes: Binance SPOT starts in 2017-08, which adds the
2017 bubble, the 2018 bear market and 2019. (2016 is not on Binance; the owner
chose Binance spot over Coinbase USD pairs.)

Section 28 exactly (ml_wf.py: features, multi-timeframe inputs, label, policy,
monthly refits, TRAIN cell choice, gates, one holdout timeframe), with ONE
change: the model's features and labels are computed on the coin's SPOT bars,
which exist from 2017-08, so every monthly refit trains on up to three more
years of history. Trades are still simulated on the coin's PERP bars with perp
costs and funding, in the same windows as section 28 (TRAIN walk-forward
2021-22, VALID 2023-24, HOLDOUT 2025-01..2026-08), so the numbers are
comparable with section 28.
  * Universe: the section 28 rule (perp listed by 2021-01-01, trading on
    2022-12-31, top UNIVERSE_N by TRAIN perp volume, zero-volume days removed),
    restricted to coins whose spot pair traded by SPOT_LISTED_BY.
  * A bar is tradable only if both its spot and its perp bar traded and the
    perp ATR fraction is at least ml_wf.AFRAC_MIN. Forecasts exist only on
    tradable bars; training rows need only a clean spot label.
  * funding_last is NaN before perp funding exists (LightGBM handles NaN).
Writes results/_multi/s29_ml_wf2/ and the generated journal/_multi/s29_ml_wf2.md.
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
import indicators as ta  # noqa: E402
import ml_hold as MH  # noqa: E402
import ml_pool as MP  # noqa: E402
import ml_wf as WF  # noqa: E402

RAW = C.ROOT / "data" / "raw" / "_multi"
OUT = C.ROOT / "results" / "_multi" / "s29_ml_wf2"
REPORT = C.ROOT / "journal" / "_multi" / "s29_ml_wf2.md"

# ---- pre-registered (PLAN.md section 29); everything else is section 28's
UNIVERSE_N = 50
SPOT_LISTED_BY = "2018-01-01"
SPOT_MONTHS = ("2017-08", "2026-08")
UNIVERSE_FILE = "universe.json"


def spot_dir(tf: int) -> Path:
    return C.ROOT / "data" / "cache" / "_multi" / f"spot_{WF.TF_NAME[tf]}"


# --------------------------------------------------------------------------
# universe and data
# --------------------------------------------------------------------------
def select_universe(perp_daily: pd.DataFrame, spot_daily: pd.DataFrame, n: int = UNIVERSE_N) -> list[dict]:
    """Section 28's perp rule, restricted to coins whose spot pair traded by SPOT_LISTED_BY."""
    sp = spot_daily[spot_daily["quote_volume"] > 0]
    first = pd.to_datetime(sp["date"], utc=True).groupby(sp["symbol"]).min()
    early = set(first[first <= pd.Timestamp(SPOT_LISTED_BY, tz="UTC")].index)
    pd_ = perp_daily[(perp_daily["quote_volume"] > 0) & perp_daily["symbol"].isin(early)]
    uni = MP.select_universe(pd_, n=n)
    for u in uni:
        u["spot_start"] = str(first[u["symbol"]].date())
    return uni


def build() -> None:
    import datafeed as DF
    import rotation as RO
    pp, sp = RO.CACHE / "perp_1d.parquet", RO.CACHE / "spot_1d.parquet"
    for p, m in ((pp, "perp"), (sp, "spot")):
        if not p.exists():
            raise SystemExit(f"no {p}: run  python src/rotation.py --build {m}  first")
    OUT.mkdir(parents=True, exist_ok=True)
    uni_path = OUT / UNIVERSE_FILE
    if uni_path.exists():
        uni = json.loads(uni_path.read_text())
        print(f"universe fixed earlier: {uni_path}")
    else:
        uni = select_universe(pd.read_parquet(pp), pd.read_parquet(sp))
        uni_path.write_text(json.dumps(uni, indent=1))
    pmonths, smonths = set(C.month_range(*MP.MONTHS)), set(C.month_range(*SPOT_MONTHS))
    for tf in WF.TFS:
        WF.cache_dir(tf).mkdir(parents=True, exist_ok=True)
        spot_dir(tf).mkdir(parents=True, exist_ok=True)
    for u in uni:
        s = u["symbol"]
        lo = pd.Timestamp(u["start"], tz="UTC")
        hi = pd.Timestamp(u["end"], tz="UTC") + pd.Timedelta(days=1)
        for tf in WF.TFS:
            for path, base, months, keep in (
                    (WF.cache_dir(tf) / f"{u['inst']}.parquet", f"data/futures/{C.MARKET}/monthly/klines/{s}/", pmonths,
                     (lo, hi)),
                    (spot_dir(tf) / f"{s}.parquet", "data/spot/monthly/klines/{s}/".format(s=s), smonths, None)):
                if path.exists():
                    continue
                keys = [k for k in DF.list_keys(base + f"{WF.TF_NAME[tf]}/") if k[-11:-4] in months]
                sub = "perp" if "futures" in base else "spot"
                k = pd.concat([DF._read_one_zip(z, C.KLINE_COLS)
                               for z in (DF.fetch_zip(x, RAW / f"{sub}_{WF.TF_NAME[tf]}" / s) for x in keys) if z],
                              ignore_index=True)
                k["open_time"] = MP._ms(k["open_time"])
                if keep:
                    k = k[(k["open_time"] >= keep[0]) & (k["open_time"] < keep[1])]
                k.drop_duplicates("open_time").sort_values("open_time").to_parquet(path, index=False)
        fp = WF.cache_dir(60) / f"{u['inst']}_funding.parquet"
        if not fp.exists():
            fkeys = [x for x in DF.list_keys(f"data/futures/{C.MARKET}/monthly/fundingRate/{s}/")
                     if x[-11:-4] in pmonths]
            f = pd.concat([DF._read_one_zip(z, C.FUNDING_COLS)
                           for z in (DF.fetch_zip(x, RAW / "perp_funding" / s) for x in fkeys) if z],
                          ignore_index=True)
            f["calc_time"] = MP._ms(f["calc_time"])
            f[(f["calc_time"] >= lo) & (f["calc_time"] < hi)].sort_values("calc_time").to_parquet(fp, index=False)
        print(f"  {u['inst']}: cached", flush=True)
    print(f"BUILD OK: {len(uni)} coins x {[WF.TF_NAME[t] for t in WF.TFS]} (spot from {SPOT_MONTHS[0]})")


def _read(path: Path) -> pd.DataFrame:
    k = pd.read_parquet(path).set_index("open_time").sort_index()
    k.index.name = "time"
    return k[["open", "high", "low", "close", "volume", "taker_buy_base"]].astype("float64")


def load_all() -> dict[int, dict]:
    uni_path = OUT / UNIVERSE_FILE
    if not uni_path.exists():
        raise SystemExit("no universe: run  python src/ml_wf2.py --build")
    uni = json.loads(uni_path.read_text())
    out = {}
    for tf in WF.TFS:
        out[tf] = {u["inst"]: {"spot": _read(spot_dir(tf) / f"{u['symbol']}.parquet"),
                               "perp": _read(WF.cache_dir(tf) / f"{u['inst']}.parquet"),
                               "fund": pd.read_parquet(WF.cache_dir(60) / f"{u['inst']}_funding.parquet")}
                   for u in uni}
    return out


# --------------------------------------------------------------------------
def prepare(by_tf: dict, tf: int) -> dict:
    """ml_wf.prepare on the SPOT bars (features, labels, multi-timeframe), then
    the trade side from the PERP bars on the same timestamps."""
    spot = {t: {c: (d["spot"], d["fund"]) for c, d in coins.items()} for t, coins in by_tf.items()}
    P = WF.prepare(spot, tf)
    for c in list(P):
        idx = P[c]["bars"].index
        perp = by_tf[tf][c]["perp"]
        tb = perp.reindex(idx)
        have = tb["close"].notna().to_numpy() & (tb["volume"].fillna(0).to_numpy() > 0)
        fill = tb["close"].ffill()
        for k in ("open", "high", "low", "close"):
            tb[k] = tb[k].where(tb[k].notna(), fill)
        tb["volume"] = tb["volume"].fillna(0.0)
        atr = ta.atr_(perp["high"], perp["low"], perp["close"], MH.ATR_N).reindex(idx)
        afrac = (atr / tb["close"]).to_numpy(float)
        good = have & np.isfinite(afrac) & (afrac >= WF.AFRAC_MIN)
        o = tb["open"].to_numpy(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            rn = np.r_[np.log(o[1:] / o[:-1]), np.nan] / np.r_[np.nan, np.where(good, afrac, np.nan)[:-1]]
        rn = np.where(np.r_[have[1:], False] & have, rn, np.nan)
        P[c].update(tbars=tb, atr=np.where(good, atr.to_numpy(float), np.nan), rn=rn,
                    tradable=P[c]["tradable"] & good[:-1])
    return P


def run(final: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lock = OUT / "holdout.json"
    if final:
        res = {tf: json.loads((OUT / f"tf{tf}.json").read_text()) for tf in WF.TFS if (OUT / f"tf{tf}.json").exists()}
        if len(res) != len(WF.TFS):
            raise SystemExit("--final refused: run the TRAIN/VALID step for every timeframe first")
        tf = WF.holdout_choice(res)
        if tf is None:
            raise SystemExit("--final refused: no timeframe is PASS")
        if lock.exists():
            raise SystemExit(f"--final refused: holdout already used ({lock})")
        h, t, des = WF.holdout(prepare(load_all(), tf), tf, res[tf])
        h["tf"] = tf
        lock.write_text(json.dumps(h, indent=1, default=str))
        t.to_csv(OUT / f"trades_holdout_tf{tf}.csv.gz", index=False)
        des.to_csv(OUT / f"desired_holdout_tf{tf}.csv.gz", index=False)
        write_report()
        print(json.dumps({k: h.get(k) for k in ("tf", "trades", "mean_r", "ci_lo", "verdict")}, indent=1))
        return
    by_tf = None
    for tf in WF.TFS:
        path = OUT / f"tf{tf}.json"
        if path.exists():
            print(f"{path} exists: pre-registered, run once (delete only after a journaled code fix)")
            continue
        by_tf = by_tf or load_all()
        r = WF.evaluate(prepare(by_tf, tf), tf, keep=True)
        r.pop("_trades").to_csv(OUT / f"trades_valid_tf{tf}.csv.gz", index=False)
        r.pop("_desired").to_csv(OUT / f"desired_valid_tf{tf}.csv.gz", index=False)
        r["history_from"] = SPOT_MONTHS[0]
        path.write_text(json.dumps(r, indent=1, default=str))
        write_report()
        print(f"\nML_WF2 {WF.TF_NAME[tf]}: {r['verdict']} failed {r['gates_failed']}")


def write_report() -> None:
    """ml_wf's report, read from this tool's folder, under this section's title."""
    saved = WF.OUT, WF.REPORT
    try:
        WF.OUT, WF.REPORT = OUT, REPORT
        WF.write_report()
    finally:
        WF.OUT, WF.REPORT = saved
    txt = REPORT.read_text().replace(
        "# Walk-forward ML on many coins, entry and exit, no time limit (PLAN.md section 28)",
        "# Walk-forward ML with spot history from 2017-08 (PLAN.md section 29)").replace(
        "GENERATED by `src/ml_wf.py`.", "GENERATED by `src/ml_wf2.py` (section 28's design, spot history from 2017-08).")
    REPORT.write_text(txt)


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
