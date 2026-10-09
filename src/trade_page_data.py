"""Display data for docs/trade.html (no research): the recorded VALID trades of
PLAN.md section 30 (1h, per coin) and section 31 (one account, per coin), with
the candles already published for the same coins (docs/trades/wf60_<COIN>.json).

    python src/trade_page_data.py
    python src/trade_page_data.py --candles   # first download + publish 1h candles for traded coins that have none

Coins outside section 28's 47 (e.g. section 36's large coins) get their own candle file
docs/trades/c60_<COIN>.json, built from Binance's native monthly 1h perp klines (display only).
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
DOCS = C.ROOT / "docs" / "trades"


def _ts(s: pd.Series) -> np.ndarray:
    t = pd.to_datetime(s, utc=True)
    return ((t - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)).to_numpy()   # unit-safe


def _why(s) -> list | None:
    if not isinstance(s, str):
        return None
    return [[n, None if v is None else float(v), None if c is None else float(c)] for n, v, c in json.loads(s)]


def build_coin(t: pd.DataFrame, why: pd.DataFrame | None, risk_col: str | None, dec: int) -> tuple[list, float]:
    """Trade tuples in trade.html's format and the coin's ending equity (start 1,000)."""
    t = t.sort_values("entry_time").reset_index(drop=True)
    eq, rows = 1000.0, []
    look = {}
    if why is not None:
        for w in why.itertuples():
            look[(w.coin, pd.Timestamp(w.entry_time))] = w
    e_ts, x_ts = _ts(t["entry_time"]), _ts(t["exit_time"])
    for i, x in enumerate(t.itertuples()):
        if risk_col:
            eq += 1000.0 * float(getattr(x, risk_col)) * float(x.net_r)      # section 31: additive account share
        else:
            eq *= 1 + 0.01 * float(x.net_r)                                 # 1% risk per trade, compounding
        w = look.get((x.coin, pd.Timestamp(x.entry_time))) if look else (x if hasattr(x, "entry_why") else None)
        info = None
        if w is not None and isinstance(getattr(w, "entry_why", None), str):
            info = {"ep": None if pd.isna(w.entry_pred) else round(float(w.entry_pred), 4),
                    "eb": None if pd.isna(w.entry_bar) else round(float(w.entry_bar), 4),
                    "ew": _why(w.entry_why),
                    "xp": None if pd.isna(w.exit_pred) else round(float(w.exit_pred), 4),
                    "xw": _why(w.exit_why)}
        rows.append([int(e_ts[i]), int(x_ts[i]), int(x.side), round(float(x.entry_px), dec), round(float(x.exit_px), dec),
                     round(float(x.stop_px), dec) if pd.notna(x.stop_px) else 0.0, 0.0, round(float(x.net_r), 3),
                     x.reason, round(eq, 1), info])
    return rows, eq


SEC = {"ml": 27, "wf": 28, "s29": 29, "s30": 30, "s31": 31, "s32": 32, "s33": 33, "s34": 34, "s36": 36, "s37": 37, "s38": 38}
# group, tf, trades file, summary file, name, verdict pill, why from (None = the file's own columns), account risk column
SPECS = [("s29", tf, f"s29_ml_wf2/trades_valid_tf{tf}.csv.gz", f"s29_ml_wf2/tf{tf}.json", "ML §29 (spot from 2017, 4 coins)",
          "ML §29: ไม่ผ่าน (เหลือ 4 เหรียญ)", None, None) for tf in (60, 240, 1440)] + \
        [("s30", tf, f"s30_ml_wf3/trades_valid_tf{tf}.csv.gz", f"s30_ml_wf3/tf{tf}.json", "ML §30 (spot history, 47 coins)",
          "ML §30 1h: เกือบผ่าน (ตกด่านช่วงความเชื่อมั่น)" if tf == 60 else f"ML §30 {'4h' if tf == 240 else '1d'}: ไม่ผ่าน",
          None, None) for tf in (60, 240, 1440)] + \
        [("s31", 60, "s31_ml_port_1h/trades_valid.csv.gz", "s31_ml_port_1h/summary.json", "ML §31 1h + portfolio",
          "ML §31 พอร์ตบัญชีเดียว: ขาดเกณฑ์อีก 0.00026", "s30", "risk"),
         ("s32", 60, "s32_ml_xs_1h/trades_valid.csv.gz", "s32_ml_xs_1h/summary.json", "ML §32 market-demeaned",
          "ML §32: TRAIN เลือกแบบเดิม = เทรดชุดเดียวกับ §31", "s30", "risk"),
         ("s33", 60, "s33_ml_mkt_1h/trades_valid.csv.gz", "s33_ml_mkt_1h/summary.json", "ML §33 market timing on ETH",
          "ML §33 ค่าเฉลี่ยทั้งตลาด เทรดแค่ ETH: ไม่ผ่าน", None, "risk"),
         ("s34", 60, "s34_ml_flow_1h/trades_valid.csv.gz", "s34_ml_flow_1h/summary.json", "ML §34 positioning data",
          "ML §34: TRAIN เลือกแบบเดิม = เทรดชุดเดียวกับ §31", "s30", "risk"),
         ("s36", 60, "s36_ml_wide_1h/trades_valid.csv.gz", "s36_ml_wide_1h/summary.json", "ML §36 train wide, trade large coins",
          "ML §36 เทรนกว้าง เทรดเหรียญใหญ่: ไม่ผ่าน (CI + DD 20.01%)", None, "risk"),
         ("s37", 240, "s37_ml_large_4h/trades_valid.csv.gz", "s37_ml_large_4h/summary.json", "ML §37 4h model, ten large coins",
          "ML §37 โมเดล 4h เหรียญใหญ่ 10 ตัว: ไม่ผ่าน (CI, จังหวะ, ฝั่ง short ขาดทุน)", None, "risk")] + \
        [("s38", tf, f"s38_ml_recent/{n}/trades_valid.csv.gz", f"s38_ml_recent/{n}/summary.json",
          f"ML §38 {n} recency-weighted", f"ML §38 {n} ให้น้ำหนักข้อมูลใหม่: ไม่ผ่าน", None, "risk")
         for tf, n in ((60, "1h"), (240, "4h"), (1440, "1d"))]


CANDLE_SPAN = ("2022-11", "2024-12")          # the same window as the published wf60 candle files
KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "qv", "n", "tbv", "tbqv", "ig"]


def publish_candles(coin: str, tf: int = 60) -> bool:
    """Download the coin's native tf USDT-M klines for CANDLE_SPAN and write docs/trades/c<tf>_<coin>.json."""
    import datafeed as DF
    name = {60: "1h", 240: "4h", 1440: "1d"}[tf]
    raw = C.ROOT / "data" / "raw" / "_multi" / f"display_{name}" / coin
    parts = []
    for m in pd.period_range(*CANDLE_SPAN, freq="M"):
        key = f"data/futures/um/monthly/klines/{coin}/{name}/{coin}-{name}-{m}.zip"
        z = DF.fetch_zip(key, raw)
        if z is not None:
            parts.append(DF._read_one_zip(z, KLINE_COLS))
    if not parts:
        return False
    b = pd.concat(parts).drop_duplicates("open_time").sort_values("open_time")
    t = (b["open_time"].astype("int64") // (1000 if b["open_time"].max() < 1e14 else 1_000_000)).astype(int)
    lo = float(b["low"][b["low"] > 0].min())
    dec = int(np.clip(3 - np.floor(np.log10(lo)), 1, 8))
    bars = {"t": t.tolist(), **{k: b[c].round(dec).tolist() for k, c in (("o", "open"), ("h", "high"), ("l", "low"),
                                                                           ("c", "close"))}}
    meta = {"id": f"c{tf}_{coin}", "sym": coin, "tf": tf, "dec": dec, "candles_only": True}
    (DOCS / f"c{tf}_{coin}.json").write_text(json.dumps({"meta": meta, "bars": bars}, separators=(",", ":")))
    return True


def candles_needed() -> None:
    for grp, tf, tfile, *_ in SPECS:
        for coin in sorted(pd.read_csv(M / tfile, usecols=["coin"])["coin"].unique()):
            if not (DOCS / f"wf{tf}_{coin}.json").exists() and not (DOCS / f"c{tf}_{coin}.json").exists():
                print(f"  candles {tf} {coin}: {'ok' if publish_candles(coin, tf) else 'NO DATA'}", flush=True)


def main() -> None:
    idx_path = DOCS / "index.json"
    idx = [r for r in json.loads(idx_path.read_text()) if r.get("group") not in SEC or r.get("group") in ("ml", "wf")]
    for r in idx:
        if r.get("group") in SEC:
            r["sec"] = SEC[r["group"]]
    s30_1h = pd.read_csv(M / "s30_ml_wf3" / "trades_valid_tf60.csv.gz")
    n = 0
    for grp, tf, tfile, sfile, name, pill, why_from, risk in SPECS:
        t_all = pd.read_csv(M / tfile)
        summ = json.loads((M / sfile).read_text())
        beat = set(summ["valid"].get("breadth", {}).get("beat", []))
        why = s30_1h if why_from == "s30" else None
        for coin in sorted(t_all["coin"].unique()):
            src = DOCS / f"wf{tf}_{coin}.json"
            if not src.exists():
                src = DOCS / f"c{tf}_{coin}.json"
            if not src.exists():
                print(f"  skip {grp} {tf} {coin}: no candles published")
                continue
            dec = json.loads(src.read_text())["meta"]["dec"]
            t = t_all[t_all["coin"] == coin]
            rows, end = build_coin(t, why, risk, dec)
            fid = f"{grp}_{coin}" if tf == 60 else f"{grp}_{tf}_{coin}"
            pills = [["r", pill]]
            if "breadth" in summ["valid"]:
                pills.append(["g" if coin in beat else "", "จังหวะชนะสุ่ม (เหรียญนี้)" if coin in beat else "จังหวะไม่ชนะสุ่ม (เหรียญนี้)"])
            meta = {"id": fid, "sym": coin, "name": name, "tf": tf, "dtf": tf, "base": None, "hold": False, "hv": None,
                    "n": len(rows), "mr": round(float(t["net_r"].mean()), 3), "end": round(end, 1), "dec": dec,
                    "period": "valid", "verdict": "REJECT", "group": grp, "sec": SEC[grp], "pills": pills,
                    "bars_from": src.stem}                 # candles are read from the published file, not copied
            (DOCS / f"{fid}.json").write_text(json.dumps({"meta": meta, "trades": rows}, separators=(",", ":")))
            idx.append({k: meta[k] for k in ("id", "sym", "name", "tf", "n", "mr", "end", "base", "hold", "hv", "group", "sec")}
                       | {"hasHold": False})
            n += 1
    idx_path.write_text(json.dumps(idx, separators=(",", ":")))
    print(f"wrote {n} files; index has {len(idx)} rows")


if __name__ == "__main__":
    if "--candles" in sys.argv:
        candles_needed()
    main()
