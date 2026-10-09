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
        t = _read(M / "s30_ml_wf3" / f"trades_valid_tf{tf}.csv.gz")
        r = json.loads((M / "s30_ml_wf3" / f"tf{tf}.json").read_text())
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
    t = _read(M / "s31_ml_port_1h" / "trades_valid.csv.gz")
    out["s31"] = daily_cum(t, "ret")
    t = _read(M / "s35_listing_1d" / "trades_valid.csv.gz")
    out["s35"] = daily_cum(t, "ret")
    rounds = [(27, None, "s27_ml_hold_1h/trades_valid.csv.gz", "§27 ตัดสินเข้า-ออกเอง · 20 เหรียญ")]
    for sec, d in ((28, "s28_ml_wf"), (29, "s29_ml_wf2"), (30, "s30_ml_wf3")):
        for tf, nm in ((60, "1h"), (240, "4h"), (1440, "1d")):
            rounds.append((sec, nm, f"{d}/trades_valid_tf{tf}.csv.gz", f"§{sec} {nm}"))
    rounds += [(31, None, "s31_ml_port_1h/trades_valid.csv.gz", "§31 1h + จัดพอร์ต"),
               (32, None, "s32_ml_xs_1h/trades_valid.csv.gz", "§32 ตัดทิศตลาด (= §31)"),
               (33, None, "s33_ml_mkt_1h/trades_valid.csv.gz", "§33 ทั้งตลาด → ETH"),
               (34, None, "s34_ml_flow_1h/trades_valid.csv.gz", "§34 เพิ่ม OI/funding (= §31)"),
               (36, None, "s36_ml_wide_1h/trades_valid.csv.gz", "§36 เทรนกว้าง · เทรดเหรียญใหญ่"),
               (37, "4h", "s37_ml_large_4h/trades_valid.csv.gz", "§37 โมเดล 4h · เหรียญใหญ่ 10 ตัว")]
    rounds += [(38, n, f"s38_ml_recent/{n}/trades_valid.csv.gz", f"§38 {n} ให้น้ำหนักข้อมูลใหม่") for n in ("1h", "4h", "1d")]
    out["rounds"] = []
    for sec, tf, f, label in rounds:
        t = _read(M / f)
        if "ret" in t:                                  # one account: return share of starting equity
            ser = [[d, round(1000 * (1 + v), 1)] for d, v in daily_cum(t, "ret")]
        else:                                           # 1% risk per trade, every coin in one account, additive
            ser = [[d, round(1000 + 10 * v, 1)] for d, v in daily_cum(t, "net_r")]
        out["rounds"].append({"sec": sec, "tf": tf, "label": label, "trades": int(len(t)),
                              "mean_r": round(float(t["net_r"].mean()), 4), "series": ser})
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
