"""Cross-check the resampler against Binance's natively published bars.

Downloading only 1m and deriving every other timeframe is a deliberate choice,
but it is a choice that can be wrong. This verifies the derived data against
the source, because "we resampled it ourselves" is exactly the kind of
assumption that silently produces a research programme built on shifted data.

For each timeframe it downloads one month of the NATIVE file and diffs every
OHLCV column against the resampled version. Any mismatch is a real defect.
"""
from __future__ import annotations

import io
import sys
import zipfile
from urllib.request import urlopen

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent)) if False else None
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import config as C
import experiment as E

MONTH = "2024-03"
# Binance names the hourly files "1h", not "60m"
TFS = [1, 3, 5, 15, 30, 60]
TF_NAME = {60: "1h"}
COLS = ["open", "high", "low", "close", "volume", "quote_volume", "trades",
        "taker_buy_base"]


def native(tf: int) -> pd.DataFrame:
    name = TF_NAME.get(tf, f"{tf}m")
    key = (f"data/futures/um/monthly/klines/{C.SYMBOL}/{name}/"
           f"{C.SYMBOL}-{name}-{MONTH}.zip")
    with urlopen(f"{C.S3}/{key}", timeout=120) as r:
        blob = r.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        df = pd.read_csv(z.open(z.namelist()[0]), header=None,
                         names=C.KLINE_COLS, dtype=str)
    for c in C.KLINE_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[pd.to_numeric(df["open_time"], errors="coerce").notna()]
    df["t"] = pd.to_datetime(df["open_time"].astype(float), unit="ms", utc=True)
    return df.set_index("t").sort_index()


def main() -> None:
    print(f"verifying the cached native files against a fresh download, {MONTH}\n")
    print("This project no longer resamples. get_bars(tf) reads Binance's own")
    print("published file, so this check guards against a corrupted, truncated or")
    print("mislabelled cache rather than against a transformation.\n")
    all_ok = True
    for tf in TFS:
        try:
            nat = native(tf)
        except Exception as e:  # noqa: BLE001
            print(f"  {TF_NAME.get(tf, str(tf) + 'm'):>4}  SKIP  ({type(e).__name__})")
            all_ok = False
            continue
        mine = E.get_bars(tf)
        lo = pd.Timestamp(f"{MONTH}-01", tz="UTC")
        hi = pd.Timestamp(f"{MONTH}-01", tz="UTC") + pd.offsets.MonthBegin(1)
        mine = mine[(mine.index >= lo) & (mine.index < hi)]
        same_idx = nat.index.equals(mine.index)
        bad = []
        for col in COLS:
            a = nat[col].astype(float).reindex(mine.index)
            b = mine[col].astype(float)
            n_bad = int(((a - b).abs() > 1e-6).sum())
            if n_bad:
                bad.append(f"{col}:{n_bad}")
        ok = same_idx and not bad
        all_ok &= ok
        name = TF_NAME.get(tf, f"{tf}m")
        print(f"  {name:>4}  {'OK  ' if ok else 'FAIL'}  "
              f"bars cached={len(mine):>6} fresh={len(nat):>6}  "
              f"index_match={same_idx}  "
              f"{'all columns match' if not bad else 'MISMATCH ' + ', '.join(bad)}")
    print()
    print("RESULT:", "cached data matches Binance exactly" if all_ok
          else "CACHE DISAGREES WITH BINANCE - do not trust any result")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
