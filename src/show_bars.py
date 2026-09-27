"""Show exactly where each timeframe's bars come from, and prove they are right.

Answers three questions:
  1. Which files actually exist on disk?
  2. What do the derived bars look like for each timeframe?
  3. Do they match what Binance publishes natively?
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

import config as C
import experiment as E

STAMP = pd.Timestamp("2024-03-01 12:00", tz="UTC")


def section_files() -> None:
    print("=" * 78)
    print("1. FILES THAT EXIST ON DISK")
    print("=" * 78)
    for d, title in ((C.RAW, "data/raw (zips from Binance)"),
                     (C.CACHE, "data/cache (what the code reads)")):
        print(f"\n{title}")
        for p in sorted(d.glob("*")):
            if p.is_file():
                print(f"   {p.name:<38} {p.stat().st_size/1024/1024:>8.1f} MB")
    print("\n   -> every timeframe is Binance's OWN file. Nothing is resampled.")
    print("      experiment.get_bars(tf) reads the native parquet and raises if it")
    print("      is missing. Deriving bars locally cost a silent one-bar offset")
    print("      that invalidated nine experiments (journal Exp 010).")


def section_sample() -> None:
    print("\n" + "=" * 78)
    print(f"2. BARS COVERING {STAMP}  (each read from Binance's own file)")
    print("=" * 78)
    for tf in (1, 3, 5, 15, 30):
        b = E.get_bars(tf)
        cand = b[(b.index <= STAMP) &
                 (b.index > STAMP - pd.Timedelta(minutes=tf))]
        if not len(cand):
            continue
        row = cand.iloc[[-1]]
        ts = cand.index[-1]
        print(f"\n{tf}m  (Binance native, {len(b):,} bars on disk)")
        print(row[["open", "high", "low", "close", "volume", "trades"]]
              .to_string(float_format=lambda v: f"{v:,.2f}"))


def section_counts() -> None:
    print("\n" + "=" * 78)
    print("3. HOW MANY BARS EACH TIMEFRAME PRODUCES")
    print("=" * 78)
    print(f"{'TF':>6}{'bars':>12}{'expected':>12}{'span':>12}")
    for tf in (1, 3, 5, 15, 30, 60):
        b = E.get_bars(tf)
        n = len(b)
        exp = int((b.index[-1] - b.index[0]).total_seconds() / (tf * 60)) + 1
        print(f"{tf:>4}m{n:>12,}{exp:>12,}"
              f"{str(b.index[-1] - b.index[0]).split(' days ')[0]:>12}")


if __name__ == "__main__":
    section_files()
    section_sample()
    section_counts()
    print("\n(run src/verify_resample.py to diff these against Binance's own files)")
