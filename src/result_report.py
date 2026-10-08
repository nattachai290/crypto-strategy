"""Standard analysis files for every recorded round (read-only; owner request 2026-10-08)

    python src/result_report.py

Reads ONLY recorded trade files (results/_multi/s*/trades_*.csv.gz). It runs no
backtest, refits nothing and never touches a holdout. For each round and each
recorded split (VALID always; TRAIN where the round saved TRAIN trades, i.e.
from section 36 on) it writes results/_multi/<round>/analysis/<split>_<book>/:

  trades_summary.json        total trades, win rate, avg win / avg loss (R),
                             profit factor, expectancy (mean R), median R, max
                             consecutive wins / losses, hold, exit reasons, cost
  prediction_analysis.json   trades bucketed by the model's confidence at entry
                             (|forecast| / its entry threshold; >= 1 by
                             construction): count, mean / median R, win rate, PF.
                             Does a more confident entry do better?
  walkforward_folds.json     one fold per month (the models refit monthly):
                             trades, return, win rate, PF, max DD inside the
                             month, plus the refit's training rows where recorded
  performance_by_period.json by month, year, coin, side: return, trades, win
                             rate, PF, max DD
  feature_drivers.json       where the round recorded each trade's top-3 SHAP
                             contributions at entry (entry_why; sections 28-30):
                             how often each feature was a top-3 driver and its
                             mean |SHAP|, for winners and losers apart. Partial
                             feature importance for rounds that saved no model
  error_analysis.json        the losing trades: by side and coin, by market
                             regime at entry (BTC 30-day trend up/down, BTC
                             30-day realised volatility high/low against its own
                             past year - causal), confidence of losers vs winners

Returns are account returns where the round recorded them (`ret`, one account);
otherwise 1% risk per trade (0.01 x net R). A trade belongs to the month and the
year of its EXIT, as in every round's weekly statistics.

IMPORTANT (AGENTS.md section 3 rule 3): these files describe; they do not
choose. An idea read off VALID here (e.g. "drop the losing regime") is a new
hypothesis that must be pre-registered and chosen on TRAIN, never applied to VALID.

The BTC regime series comes from Binance's native 1d BTCUSDT perp klines,
downloaded once to data/raw/_multi/display_1d/ (display/diagnostic only).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

M = C.ROOT / "results" / "_multi"
SPLITS = {"train": ("2021-01-01", "2023-01-01"), "valid": ("2023-01-01", "2025-01-01")}
CONF_EDGES = (1.0, 1.25, 1.5, 2.0, 3.0, np.inf)


# --------------------------------------------------------------------------
# pure pieces (test 34)
# --------------------------------------------------------------------------
def returns(t: pd.DataFrame) -> pd.Series:
    return t["ret"] if "ret" in t else 0.01 * t["net_r"]


def profit_factor(r: pd.Series) -> float | None:
    win, loss = r[r > 0].sum(), -r[r < 0].sum()
    return float(win / loss) if loss > 0 else None


def streaks(r: pd.Series) -> tuple[int, int]:
    """Longest run of wins (> 0) and of losses (<= 0), in exit order."""
    best_w = best_l = cur_w = cur_l = 0
    for x in r:
        if x > 0:
            cur_w, cur_l = cur_w + 1, 0
        else:
            cur_w, cur_l = 0, cur_l + 1
        best_w, best_l = max(best_w, cur_w), max(best_l, cur_l)
    return best_w, best_l


def max_dd(ret: pd.Series) -> float:
    """Largest fall of the cumulative (additive) return, in exit order."""
    eq = np.r_[0.0, np.cumsum(ret.to_numpy(float))]
    return float(np.max(np.maximum.accumulate(eq) - eq)) if len(eq) else 0.0


def block(t: pd.DataFrame) -> dict:
    """The standard numbers for any group of trades."""
    if t.empty:
        return {"trades": 0}
    r, ret = t["net_r"], returns(t)
    return {"trades": int(len(t)), "return": float(ret.sum()), "mean_r": float(r.mean()),
            "median_r": float(r.median()), "win_rate": float((r > 0).mean()), "profit_factor": profit_factor(r),
            "max_dd": max_dd(ret)}


def confidence(t: pd.DataFrame) -> pd.Series | None:
    """|forecast| / entry threshold at entry, where the round recorded it."""
    if "conf" in t and t["conf"].notna().any():
        return t["conf"]
    if {"entry_pred", "entry_bar"} <= set(t.columns):
        with np.errstate(divide="ignore", invalid="ignore"):
            return (t["entry_pred"].abs() / t["entry_bar"]).replace([np.inf, -np.inf], np.nan)
    return None


def summary(t: pd.DataFrame) -> dict:
    t = t.sort_values("exit_time")
    r = t["net_r"]
    w, lo = r[r > 0], r[r <= 0]
    sw, sl = streaks(r)
    out = {**block(t), "avg_win_r": float(w.mean()) if len(w) else None,
           "avg_loss_r": float(lo.mean()) if len(lo) else None, "expectancy_r": float(r.mean()),
           "max_consecutive_wins": sw, "max_consecutive_losses": sl,
           "longs": int((t["side"] > 0).sum()), "shorts": int((t["side"] < 0).sum()),
           "exit_reasons": {str(k): int(v) for k, v in t["reason"].value_counts().items()} if "reason" in t else None}
    if "gross_r" in t:
        out["gross_r"], out["cost_r"] = float(t["gross_r"].mean()), float((t["gross_r"] - t["net_r"]).mean())
    hold = "bars" if "bars" in t else ("days" if "days" in t else None)
    if hold:
        out[f"median_hold_{hold}"] = float(t[hold].median())
    return out


def prediction_analysis(t: pd.DataFrame) -> dict:
    c = confidence(t)
    if c is None:
        return {"available": False, "note": "this round did not record the forecast at entry"}
    rows = []
    for lo, hi in zip(CONF_EDGES[:-1], CONF_EDGES[1:]):
        g = t[(c >= lo) & (c < hi)]
        rows.append({"bucket": f"{lo:g}-{hi:g}" if np.isfinite(hi) else f">={lo:g}", **block(g)})
    ok = c.notna()
    rho = float(pd.Series(c[ok]).rank().corr(t.loc[ok, "net_r"].rank())) if ok.sum() > 2 else None
    return {"available": True, "measure": "|forecast| / entry threshold at entry", "buckets": rows,
            "spearman_conf_vs_r": rho}


def by_group(t: pd.DataFrame, key: pd.Series) -> dict:
    return {str(k): block(g) for k, g in t.groupby(key)}


def periods(t: pd.DataFrame) -> dict:
    ex = pd.to_datetime(t["exit_time"], utc=True)
    side = t["side"].map({1: "long", -1: "short", 1.0: "long", -1.0: "short"})
    return {"month": by_group(t, ex.dt.strftime("%Y-%m")), "year": by_group(t, ex.dt.year),
            "coin": by_group(t, t["coin"]), "side": by_group(t, side)}


def folds(t: pd.DataFrame, refits: list | None) -> list:
    rows = {r["month"]: r.get("train_rows") for r in (refits or []) if isinstance(r, dict) and "month" in r}
    ex = pd.to_datetime(t["exit_time"], utc=True).dt.strftime("%Y-%m")
    out = []
    for m, g in t.groupby(ex):
        out.append({"month": m, **block(g), "weekly_sharpe_note": "4 weeks per fold: noisy, do not judge on it",
                    "train_rows": rows.get(m)})
    return out


def feature_drivers(t: pd.DataFrame, top: int = 15) -> dict:
    """Top-3 SHAP drivers recorded at entry (entry_why = [[name, value, contribution], ...])."""
    if "entry_why" not in t:
        return {"available": False, "note": "this round did not record per-trade SHAP; see record/ from section 38 on"}
    rows = []
    for why, r in zip(t["entry_why"], t["net_r"]):
        if isinstance(why, str):
            for name, _, con in json.loads(why):
                if con is not None:
                    rows.append((name, abs(float(con)), r > 0))
    if not rows:
        return {"available": False, "note": "entry_why is empty"}
    d = pd.DataFrame(rows, columns=["feature", "abs_shap", "win"])
    n = int(t["entry_why"].notna().sum())

    def tab(x):
        g = x.groupby("feature")["abs_shap"].agg(["size", "mean"]).sort_values("size", ascending=False).head(top)
        return [{"feature": k, "top3_share": float(v["size"] / n), "mean_abs_shap": float(v["mean"])}
                for k, v in g.iterrows()]
    return {"available": True, "trades_with_why": n, "all": tab(d), "winners": tab(d[d["win"]]),
            "losers": tab(d[~d["win"]])}


def regimes(btc: pd.DataFrame) -> pd.DataFrame:
    """Daily BTC regime, causal: 30-day trend sign; 30-day realised volatility
    above / below its own median over the previous 365 days."""
    c = btc["close"]
    trend = np.sign(c / c.shift(30) - 1)
    vol = np.log(c).diff().rolling(30).std()
    hi = vol > vol.rolling(365, min_periods=180).median().shift(1)
    return pd.DataFrame({"trend": np.where(trend > 0, "up", "down"), "vol": np.where(hi, "high", "low")},
                        index=btc.index).where(vol.notna())


def error_analysis(t: pd.DataFrame, reg: pd.DataFrame | None) -> dict:
    loss = t["net_r"] <= 0
    out = {"losers": int(loss.sum()), "losing_r_sum": float(t.loc[loss, "net_r"].sum()),
           "by_side": {k: {"losers": int(((t["side"] == s) & loss).sum()),
                           "loser_share": float(loss[t["side"] == s].mean()) if (t["side"] == s).any() else None,
                           "mean_r": float(t.loc[t["side"] == s, "net_r"].mean()) if (t["side"] == s).any() else None}
                       for k, s in (("long", 1), ("short", -1))},
           "worst_coins": sorted(({"coin": c, "trades": int(len(g)), "losers": int((g["net_r"] <= 0).sum()),
                                   "sum_r": float(g["net_r"].sum())} for c, g in t.groupby("coin")),
                                 key=lambda x: x["sum_r"])[:10]}
    c = confidence(t)
    if c is not None:
        out["confidence"] = {"losers_median": float(c[loss].median()) if loss.any() else None,
                             "winners_median": float(c[~loss].median()) if (~loss).any() else None}
    if reg is not None:
        day = pd.to_datetime(t["entry_time"], utc=True).dt.floor("D") - pd.Timedelta(days=1)  # yesterday's close
        r = reg.reindex(day.to_numpy())
        r.index = t.index
        out["regime_at_entry"] = {
            f"{a}_{b}": {**block(t[(r["trend"] == a) & (r["vol"] == b)]),
                         "long": block(t[(r["trend"] == a) & (r["vol"] == b) & (t["side"] > 0)]),
                         "short": block(t[(r["trend"] == a) & (r["vol"] == b) & (t["side"] < 0)])}
            for a in ("up", "down") for b in ("high", "low")}
        out["regime_note"] = "BTC 30-day trend and volatility at the close before entry; describes, never chooses"
    return out


# --------------------------------------------------------------------------
def _btc_daily() -> pd.DataFrame | None:
    try:
        import datafeed as DF
        raw = C.ROOT / "data" / "raw" / "_multi" / "display_1d" / "BTCUSDT"
        cols = ["open_time", "open", "high", "low", "close", "volume", "close_time", "qv", "n", "tbv", "tbqv", "ig"]
        parts = []
        for m in pd.period_range("2019-12", "2024-12", freq="M"):
            z = DF.fetch_zip(f"data/futures/um/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-{m}.zip", raw)
            if z is not None:
                parts.append(DF._read_one_zip(z, cols))
        b = pd.concat(parts).drop_duplicates("open_time").sort_values("open_time")
        unit = "ms" if b["open_time"].max() < 1e14 else "us"
        b.index = pd.to_datetime(b["open_time"].astype("int64"), unit=unit, utc=True)
        return b[["close"]]
    except Exception as e:  # noqa: BLE001 - the report still writes, without regimes
        print(f"  (no BTC regime series: {e.__class__.__name__}: {e})")
        return None


def books() -> list[tuple[str, str, str, Path, list | None]]:
    """(round folder, split, book name, trade file, refits) for every recorded trade file."""
    out = []
    for d in sorted(p for p in M.glob("s*_*") if p.is_dir()):
        for f in sorted(d.glob("trades_*.csv.gz")) + sorted(d.glob("[0-9][hd]/trades_*.csv.gz")):
            name = f.name[len("trades_"):-len(".csv.gz")]
            split = name.split("_")[0]
            if split not in SPLITS:
                continue                                   # trades_holdout* is never read here
            book = name[len(split) + 1:] or "main"
            if f.parent != d:                              # sub-model folders (section 38 on): 1h/ 4h/ 1d/
                book = f"{f.parent.name}_{book}"
            refits = None
            if book.startswith("tf") and (d / f"{book}.json").exists():
                refits = json.loads((d / f"{book}.json").read_text()).get("refits")
            out.append((d.name, split, book, f, refits))
    return out


def main() -> None:
    btc = _btc_daily()
    reg = regimes(btc) if btc is not None else None
    n = 0
    for rnd, split, book, f, refits in books():
        t = pd.read_csv(f)
        if t.empty:
            continue
        out = M / rnd / "analysis" / f"{split}_{book}"
        out.mkdir(parents=True, exist_ok=True)
        files = {"trades_summary": {"source": f.name, **summary(t)}, "prediction_analysis": prediction_analysis(t),
                 "walkforward_folds": folds(t, refits), "performance_by_period": periods(t),
                 "error_analysis": error_analysis(t, reg), "feature_drivers": feature_drivers(t)}
        for k, v in files.items():
            (out / f"{k}.json").write_text(json.dumps(v, indent=1, default=str))
        n += 1
        s = files["trades_summary"]
        print(f"  {rnd}/{split}_{book}: {s['trades']} trades, win {s['win_rate']:.2f}, PF {s['profit_factor']}, "
              f"mean R {s['mean_r']:+.4f}")
    print(f"wrote analysis for {n} trade files")


if __name__ == "__main__":
    main()
