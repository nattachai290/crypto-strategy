"""Display data for docs/ml.html (no research): reads the recorded VALID trade
files of the ML rounds (PLAN.md sections 30-35) and writes docs/ml_data.json.

    python src/ml_page_data.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

M = C.ROOT / "results" / "_multi"
OUT = C.ROOT / "docs" / "ml_data.json"


def _read(p: Path) -> pd.DataFrame:
    t = pd.read_csv(p, parse_dates=["entry_time", "exit_time"])
    t["exit_time"] = pd.to_datetime(t["exit_time"], utc=True)
    return t.sort_values("exit_time")


def daily_cum(t: pd.DataFrame, col: str) -> list:
    d = t.groupby(t["exit_time"].dt.floor("D"))[col].sum().cumsum()
    return [[x.strftime("%Y-%m-%d"), round(float(v), 4)] for x, v in d.items()]


def main() -> None:
    out = {"s30": {}, "s30_side": {}, "s30_month": [], "s31": [], "s35": []}
    for tf, name in ((60, "1h"), (240, "4h"), (1440, "1d")):
        t = _read(M / "ml_wf3" / f"trades_valid_tf{tf}.csv.gz")
        r = json.loads((M / "ml_wf3" / f"tf{tf}.json").read_text())
        v = r["valid"]
        out["s30"][name] = {"series": daily_cum(t, "net_r"), "trades": int(len(t)), "mean_r": v["mean_r"],
                            "ci": [v["ci_lo"], v["ci_hi"]], "verdict": r["verdict"], "failed": r["gates_failed"]}
        if tf == 60:
            for side, k in ((1, "long"), (-1, "short")):
                s = t[t["side"] == side]
                out["s30_side"][k] = {"series": daily_cum(s, "net_r"), "trades": int(len(s)),
                                      "mean_r": float(s["net_r"].mean())}
            mo = t.groupby(t["exit_time"].dt.strftime("%Y-%m"))["net_r"].sum()
            out["s30_month"] = [[k, round(float(v), 3)] for k, v in mo.items()]
    t = _read(M / "ml_port" / "trades_valid.csv.gz")
    out["s31"] = daily_cum(t, "ret")
    t = _read(M / "listing" / "trades_valid.csv.gz")
    out["s35"] = daily_cum(t, "ret")
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
