"""Walk-forward ML on section 28's 47 coins, each with all the spot history it has (PLAN.md section 30)

    python src/ml_wf3.py --build            # spot 1h/4h/1d of the 47 coins (perp caches from ml_wf.py --build)
    python src/ml_wf3.py                    # TRAIN/VALID for 1h, 4h and 1d, once
    python src/ml_wf3.py --final            # HOLDOUT once, one timeframe, only after PASS

Section 29 (ml_wf2.py) was meant to ask "does a longer history help?", but its
universe rule (spot pair by 2018-01-01) left 4 coins, so it changed the history
and the universe at once and the breadth gates were unreachable (_multi Exp
025/026, the planner's error). This round asks the question cleanly:
  * Universe: EXACTLY section 28's 47 coins (results/_multi/ml_wf/universe_v2.json).
  * Each coin's features and labels come from its Binance SPOT bars from the
    pair's own first month (as early as 2017-08) UNTIL its perp starts, and from
    its perp bars after that (history_source, "splice"; Exp 028 fix). A coin with
    no earlier spot uses its perp bars, as in section 28.
  * Everything else is section 29 = section 28: trades on perp bars with perp
    costs and funding, the same windows, cell grid, gates and one holdout
    timeframe (ml_wf2.prepare, ml_wf.evaluate / holdout).
So the only difference from section 28 is the length of each coin's history.
Writes results/_multi/ml_wf3/ and the generated journal/_multi/ml_wf3.md.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
import ml_pool as MP  # noqa: E402
import ml_wf as WF  # noqa: E402
import ml_wf2 as W2  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "ml_wf3"
REPORT = C.ROOT / "journal" / "_multi" / "ml_wf3.md"
SOURCE_UNIVERSE = C.ROOT / "results" / "_multi" / "ml_wf" / WF.UNIVERSE_FILE


def build() -> None:
    import datafeed as DF
    OUT.mkdir(parents=True, exist_ok=True)
    uni_path = OUT / "universe.json"
    if not uni_path.exists():
        shutil.copyfile(SOURCE_UNIVERSE, uni_path)          # section 28's coins, unchanged
    uni = json.loads(uni_path.read_text())
    months = set(C.month_range(*W2.SPOT_MONTHS))
    for tf in WF.TFS:
        W2.spot_dir(tf).mkdir(parents=True, exist_ok=True)
        for u in uni:
            if not (WF.cache_dir(tf) / f"{u['inst']}.parquet").exists():
                raise SystemExit(f"no perp cache for {u['inst']} {WF.TF_NAME[tf]}: run  python src/ml_wf.py --build")
    for u in uni:
        s = u["symbol"]
        for tf in WF.TFS:
            path = W2.spot_dir(tf) / f"{s}.parquet"
            if path.exists():
                continue
            keys = [k for k in DF.list_keys(f"data/spot/monthly/klines/{s}/{WF.TF_NAME[tf]}/") if k[-11:-4] in months]
            zips = [z for z in (DF.fetch_zip(x, W2.RAW / f"spot_{WF.TF_NAME[tf]}" / s) for x in keys) if z]
            if not zips:                                    # no spot pair: an empty file records that
                pd.DataFrame(columns=["open_time"] + [c for c in C.KLINE_COLS if c != "open_time"]).to_parquet(path, index=False)
                continue
            k = pd.concat([DF._read_one_zip(z, C.KLINE_COLS) for z in zips], ignore_index=True)
            k["open_time"] = MP._ms(k["open_time"])
            k.drop_duplicates("open_time").sort_values("open_time").to_parquet(path, index=False)
        print(f"  {u['inst']}: cached", flush=True)
    print(f"BUILD OK: {len(uni)} coins x {[WF.TF_NAME[t] for t in WF.TFS]} (spot from each pair's first month)")


def history_source(spot: pd.DataFrame | None, perp: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """The bars a coin's features and labels come from (Exp 028 fix): the coin's
    traded SPOT bars from before its perp's first bar, then the PERP bars from
    the perp's first bar on ("splice"). From the perp start the frame is
    exactly section 28's, so a spot pair that was delisted early (HNT spot ended
    2022-10, XMR 2024-02) can no longer cut the trading window short. A coin with
    no traded spot bar before its perp uses its perp bars only ("perp")."""
    if spot is None or spot.empty:
        return perp, "perp"
    early = spot[(spot.index < perp.index[0]) & (spot["volume"] > 0)]
    if early.empty:
        return perp, "perp"
    early = spot[(spot.index >= early.index[0]) & (spot.index < perp.index[0])]
    return pd.concat([early, perp]), "splice"


def load_all() -> tuple[dict[int, dict], dict[str, dict]]:
    uni_path = OUT / "universe.json"
    if not uni_path.exists():
        raise SystemExit("no universe: run  python src/ml_wf3.py --build")
    uni = json.loads(uni_path.read_text())
    out, info = {}, {}
    for tf in WF.TFS:
        out[tf] = {}
        for u in uni:
            perp = W2._read(WF.cache_dir(tf) / f"{u['inst']}.parquet")
            sp_path = W2.spot_dir(tf) / f"{u['symbol']}.parquet"
            spot = W2._read(sp_path) if sp_path.exists() and pd.read_parquet(sp_path).shape[0] else None
            hist, src = history_source(spot, perp)
            out[tf][u["inst"]] = {"spot": hist, "perp": perp,
                                  "fund": pd.read_parquet(WF.cache_dir(60) / f"{u['inst']}_funding.parquet")}
            if tf == 60:
                info[u["inst"]] = {"source": src, "history_from": str(hist.index[0].date())}
    return out, info


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
        by_tf, _ = load_all()
        h, t, des = WF.holdout(W2.prepare(by_tf, tf), tf, res[tf])
        h["tf"] = tf
        lock.write_text(json.dumps(h, indent=1, default=str))
        t.to_csv(OUT / f"trades_holdout_tf{tf}.csv.gz", index=False)
        des.to_csv(OUT / f"desired_holdout_tf{tf}.csv.gz", index=False)
        write_report()
        print(json.dumps({k: h.get(k) for k in ("tf", "trades", "mean_r", "ci_lo", "verdict")}, indent=1))
        return
    by_tf = info = None
    for tf in WF.TFS:
        path = OUT / f"tf{tf}.json"
        if path.exists():
            print(f"{path} exists: pre-registered, run once (delete only after a journaled code fix)")
            continue
        if by_tf is None:
            by_tf, info = load_all()
            (OUT / "history.json").write_text(json.dumps(info, indent=1))
        r = WF.evaluate(W2.prepare(by_tf, tf), tf, keep=True)
        r.pop("_trades").to_csv(OUT / f"trades_valid_tf{tf}.csv.gz", index=False)
        r.pop("_desired").to_csv(OUT / f"desired_valid_tf{tf}.csv.gz", index=False)
        r["history"] = info
        path.write_text(json.dumps(r, indent=1, default=str))
        write_report()
        print(f"\nML_WF3 {WF.TF_NAME[tf]}: {r['verdict']} failed {r['gates_failed']}")


def write_report() -> None:
    saved = WF.OUT, WF.REPORT
    try:
        WF.OUT, WF.REPORT = OUT, REPORT
        WF.write_report()
    finally:
        WF.OUT, WF.REPORT = saved
    txt = REPORT.read_text().replace(
        "# Walk-forward ML on many coins, entry and exit, no time limit (PLAN.md section 28)",
        "# Walk-forward ML, section 28's 47 coins with all their spot history (PLAN.md section 30)").replace(
        "GENERATED by `src/ml_wf.py`.", "GENERATED by `src/ml_wf3.py` (section 28's design and coins, spot history).")
    hp = OUT / "history.json"
    if hp.exists():
        info = json.loads(hp.read_text())
        n_spot = sum(1 for x in info.values() if x["source"] == "splice")
        txt += (f"\nHistory: {n_spot} of {len(info)} coins use spot bars; earliest "
                f"{min(x['history_from'] for x in info.values())}.\n")
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
