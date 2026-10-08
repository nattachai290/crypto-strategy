"""Run-time record for every ML round from section 38 on (owner request 2026-10-08)

A library, not a script: a round's own run() calls it while the models still
exist, so the record holds what can never be rebuilt from trade files later.
It changes nothing a round computes (test 35 checks that recording leaves the
forecasts identical). Files, in the round's folder under record/<split>/:

  feature_importance.json  per refit month: LightGBM gain and split importance
                           (each normalised to sum 1), their mean over months,
                           and mean |SHAP| with the mean positive and negative
                           contribution, on a fixed-seed sample of the rows
                           each month's model actually forecast
  training_metadata.json   features (count and list), coins, training rows per
                           refit, label definition and horizon(s), the label's
                           distribution on training rows, LightGBM parameters,
                           seed, date windows
  predictions.parquet      every forecast bar of the traded coins: time, coin,
                           forecast, realised label (the same definition)
  skipped_signals.csv.gz   entries the policy wanted but a filter removed
                           (agreement, traded set, cap): time, coin, side,
                           reason, and the realised label signed by the side
  run_info.json            Python / library versions, git commit, start/end
                           time, a fingerprint of the input caches
  holdout_power.json       from the VALID weekly returns: the chance a holdout
                           of N weeks would CONFIRM if the edge is as large as
                           on VALID, and if it is half as large
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import time
from math import erf, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

HOLDOUT_WEEKS = int((pd.Timestamp("2026-09-01") - pd.Timestamp("2025-01-01")).days // 7)   # 2025-01 .. 2026-08
SHAP_ROWS, SEED = 2000, 38


def _norm(x: np.ndarray) -> np.ndarray:
    s = float(np.sum(x))
    return x / s if s > 0 else x


def importance(models: dict) -> dict:
    """{month: Booster} -> gain and split importance per month and their mean."""
    per, gains, splits, names = {}, [], [], None
    for m, b in sorted(models.items()):
        names = b.feature_name()
        g = _norm(b.feature_importance("gain").astype(float))
        s = _norm(b.feature_importance("split").astype(float))
        per[str(pd.Timestamp(m).date())] = {"gain": dict(zip(names, g.round(6).tolist())),
                                            "split": dict(zip(names, s.round(6).tolist()))}
        gains.append(g)
        splits.append(s)
    if names is None:
        return {"months": {}, "mean_gain": {}, "mean_split": {}}
    mg, ms = np.mean(gains, axis=0), np.mean(splits, axis=0)
    order = np.argsort(-mg)
    return {"months": per, "mean_gain": {names[i]: float(mg[i]) for i in order},
            "mean_split": {names[i]: float(ms[i]) for i in order}}


def shap_summary(models: dict, X_by_month: dict, rows: int = SHAP_ROWS, seed: int = SEED) -> dict:
    """mean |SHAP|, mean positive and mean negative contribution per feature, over a
    fixed-seed sample of up to `rows` forecast rows per month (X_by_month: {month: X})."""
    rng = np.random.default_rng(seed)
    acc, n, names = None, 0, None
    for m, b in sorted(models.items()):
        X = X_by_month.get(m)
        if X is None or not len(X):
            continue
        if len(X) > rows:
            X = X.iloc[np.sort(rng.choice(len(X), rows, replace=False))]
        names = b.feature_name()
        con = b.predict(X.reindex(columns=names), pred_contrib=True)[:, :-1]      # last column = bias
        part = np.vstack([np.abs(con).sum(0), np.where(con > 0, con, 0).sum(0), np.where(con < 0, con, 0).sum(0)])
        acc = part if acc is None else acc + part
        n += len(con)
    if acc is None:
        return {"rows": 0}
    acc = acc / n
    order = np.argsort(-acc[0])
    return {"rows": int(n), "mean_abs_shap": {names[i]: float(acc[0, i]) for i in order},
            "mean_positive": {names[i]: float(acc[1, i]) for i in order},
            "mean_negative": {names[i]: float(acc[2, i]) for i in order}}


def label_stats(y: pd.Series) -> dict:
    y = pd.Series(y).dropna()
    if not len(y):
        return {"rows": 0}
    q = y.quantile([0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99])
    return {"rows": int(len(y)), "mean": float(y.mean()), "std": float(y.std()), "share_positive": float((y > 0).mean()),
            "quantiles": {f"{k:g}": float(v) for k, v in q.items()}}


def metadata(features: list[str], coins: list[str], log: list | None, params: dict, label: str,
             horizons, windows: dict, train_labels: pd.Series | None = None, extra: dict | None = None) -> dict:
    return {"n_features": len(features), "features": sorted(features), "n_coins": len(coins), "coins": sorted(coins),
            "refits": log or [], "label": label, "horizons": list(horizons), "lightgbm_params": params,
            "seed": params.get("seed"), "windows": windows,
            "label_distribution": label_stats(train_labels) if train_labels is not None else None, **(extra or {})}


def predictions(index_by_coin: dict, pred_by_coin: dict, label_by_coin: dict, a: str, b: str) -> pd.DataFrame:
    """Every finite forecast in [a, b): time, coin, forecast, label."""
    fr = []
    lo, hi = pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC")
    for c, idx in index_by_coin.items():
        p = np.asarray(pred_by_coin[c], float)
        y = np.asarray(label_by_coin[c], float)
        w = (idx >= lo) & (idx < hi) & np.isfinite(p)
        if w.any():
            fr.append(pd.DataFrame({"time": idx[w], "coin": c, "forecast": p[w].astype("float32"),
                                    "label": y[w].astype("float32")}))
    return pd.concat(fr, ignore_index=True) if fr else pd.DataFrame(columns=["time", "coin", "forecast", "label"])


def skipped(times: pd.DatetimeIndex, coin: str, wanted: np.ndarray, taken: np.ndarray, reason: str,
            label: np.ndarray) -> pd.DataFrame:
    """Bars where the wanted path opens (or reverses into) a side that the taken
    path does not hold: the signal a filter removed, with its realised label x side."""
    wanted, taken = np.nan_to_num(np.asarray(wanted, float)), np.nan_to_num(np.asarray(taken, float))
    prev = np.r_[0.0, wanted[:-1]]
    new = (wanted != 0) & (wanted != prev) & (taken != wanted)
    k = np.flatnonzero(new)
    return pd.DataFrame({"time": times[k], "coin": coin, "side": wanted[k].astype(int), "reason": reason,
                         "signed_label": wanted[k] * np.asarray(label, float)[k]})


def _phi(x: float) -> float:
    return 0.5 * (1 + erf(x / sqrt(2)))


def holdout_power(weekly: pd.Series, weeks: int = HOLDOUT_WEEKS) -> dict:
    """Normal approximation: P(lower 95% bound of the holdout weekly mean > 0) =
    Phi(sqrt(weeks) * mu / sd - 1.96), with mu = VALID's weekly mean (and half of it)."""
    x = pd.Series(weekly).dropna()
    mu, sd = float(x.mean()), float(x.std(ddof=1))
    if not np.isfinite(sd) or sd <= 0:
        return {"weeks": weeks, "if_edge_real": None, "if_half": None}
    return {"weeks": weeks, "valid_weekly_mean": mu, "valid_weekly_sd": sd,
            "if_edge_real": _phi(sqrt(weeks) * mu / sd - 1.96), "if_half": _phi(sqrt(weeks) * mu / 2 / sd - 1.96)}


def fingerprint(paths) -> str:
    """sha256 over (relative name, size) of every input file: same inputs, same print."""
    h = hashlib.sha256()
    for p in sorted(Path(x) for x in paths):
        if p.exists():
            h.update(f"{p.name}:{p.stat().st_size}\n".encode())
    return h.hexdigest()[:16]


def run_info(started: float, inputs=()) -> dict:
    vers = {}
    for mod in ("numpy", "pandas", "lightgbm", "pyarrow"):
        try:
            vers[mod] = __import__(mod).__version__
        except Exception:  # noqa: BLE001
            vers[mod] = None
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=C.ROOT, capture_output=True, text=True).stdout.strip()
    except Exception:  # noqa: BLE001
        commit = None
    return {"python": platform.python_version(), "platform": platform.platform(), "libraries": vers,
            "git_commit": commit, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
            "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "seconds": round(time.time() - started, 1),
            "inputs_fingerprint": fingerprint(inputs) if inputs else None}


def write(out: Path, **files) -> None:
    """json for dicts/lists, parquet for 'predictions', csv.gz for other DataFrames."""
    out.mkdir(parents=True, exist_ok=True)
    for name, v in files.items():
        if v is None:
            continue
        if isinstance(v, pd.DataFrame):
            if name == "predictions":
                v.to_parquet(out / f"{name}.parquet", index=False, compression="zstd")
            else:
                v.to_csv(out / f"{name}.csv.gz", index=False)
        else:
            (out / f"{name}.json").write_text(json.dumps(v, indent=1, default=str))
