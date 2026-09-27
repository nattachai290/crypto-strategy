"""Extra artefacts the HTML report needs: equity curve, per-fold table, and
per-year breakdown for the single best configuration found."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
import definitive as D
import experiment as E
import run_ml

BEST = dict(method="reg", thr=0.10, stop_scale=5.0, tf=15)


def main() -> None:
    tf = BEST["tf"]
    sc = BEST["stop_scale"]
    bars = E.get_bars(tf)
    funding = E.load_funding()
    run_ml.CANDIDATES = [
        (nm, {**pr, **{k: v * sc for k, v in pr.items()
                       if k in ("stop_mult", "tp_mult") and v > 0}})
        for nm, pr in run_ml.CANDIDATES
    ]
    sig = run_ml.build_candidates(bars, funding)
    ds = run_ml.make_dataset(bars, sig, funding).dropna(subset=["net_r"])
    feats = [c for c in ds.columns
             if c not in ("net_r", "reason", "bars", "side", "src", "i",
                          "stop_dist", "tp_dist", "max_hold", "entry_px")]
    r = D.run(tf, sc, BEST["method"], BEST["thr"], ds, feats, bars, funding)
    tdf: pd.DataFrame = r.pop("tdf")

    # rebuild the chained equity path bar-by-bar for a smooth chart
    equity = C.INITIAL_EQUITY
    path = []
    for te0, te1 in D.get_folds():
        tr0 = te0 - pd.DateOffset(months=24)
        dtr = ds[(ds.index >= tr0) & (ds.index < te0)]
        dte = ds[(ds.index >= te0) & (ds.index < te1)]
        if len(dtr) < 2000 or len(dte) < 10:
            continue
        ptr = run_ml._fit_predict(dtr[feats].fillna(0.0), dtr["net_r"].to_numpy(),
                                  dte[feats].fillna(0.0), kind=BEST["method"])
        sub = dte[ptr >= BEST["thr"]]
        res = E.__dict__  # noqa: F841
        from backtest import run_backtest
        rr = run_backtest(bars, D.signal_frame(bars, sub), start_time=te0,
                          end_time=te1, funding=funding, initial_equity=equity)
        if rr.equity is not None and len(rr.equity):
            e = rr.equity
            step = max(1, len(e) // 400)
            for ts, v in e.iloc[::step].items():
                path.append({"t": str(pd.Timestamp(ts).date()), "eq": round(float(v), 3)})
            last = float(e.iloc[-1])
            if not path or path[-1]["eq"] != round(last, 3):
                path.append({"t": str(pd.Timestamp(e.index[-1]).date()),
                              "eq": round(last, 3)})
        equity = rr.metrics["final_equity"]

    tdf["year"] = tdf["entry_time"].dt.year
    by_year = []
    for y, g in tdf.groupby("year"):
        by_year.append({
            "year": int(y), "trades": int(len(g)),
            "mean_r": round(float(g["r_multiple"].mean()), 4),
            "win": round(float((g["r_multiple"] > 0).mean()) * 100, 1),
            "long": int((g["side"] > 0).sum()), "short": int((g["side"] < 0).sum()),
            "long_r": round(float(g[g["side"] > 0]["r_multiple"].mean()), 4),
            "short_r": round(float(g[g["side"] < 0]["r_multiple"].mean()), 4),
            "cost_r": round(float(g["cost_r"].mean()), 4),
            "gross_r": round(float(g["gross_r"].mean()), 4),
        })
    exit_mix = {k: int(v) for k, v in tdf["exit_reason"].value_counts().items()}

    payload = {
        "best": {k: v for k, v in r.items() if k != "folds"},
        "folds": r["folds"],
        "equity_path": path,
        "by_year": by_year,
        "exit_mix": exit_mix,
    }
    (C.LEGACY / "report_best.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items()
                      if k not in ("equity_path", "folds")}, indent=1)[:1600])
    print(f"\nfold rows: {len(r['folds'])}, equity points: {len(path)}")


if __name__ == "__main__":
    main()
