"""Download + cache Binance USDT-M futures public data for BTCUSDT.

Only what's needed for intraday research:
  * 1m klines   (trades)      data/futures/um/monthly/klines/BTCUSDT/1m/
  * 1m mark klines (safe fills) .../markPriceKlines/BTCUSDT/1m/
  * funding rate              .../fundingRate/BTCUSDT/

Each monthly zip is cached under data/raw/ and verified against the
accompanying .CHECKSUM file. Concatenated series are written to
data/cache/*.parquet for fast reload.
"""
from __future__ import annotations

import io
import sys
import time
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}


def _get(url: str, tries: int = 4, timeout: int = 90) -> bytes:
    last: Exception | None = None
    for i in range(tries):
        try:
            with urlopen(url, timeout=timeout) as r:
                return r.read()
        except (HTTPError, URLError, TimeoutError) as e:  # pragma: no cover
            last = e
            code = getattr(e, "code", None)
            if code == 404:
                raise
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"failed to GET {url}: {last}")


def list_keys(prefix: str) -> list[str]:
    """List all object keys under a prefix (handles pagination)."""
    keys: list[str] = []
    token = None
    while True:
        url = f"{C.S3}?list-type=2&prefix={prefix}"
        if token:
            url += f"&continuation-token={token}"
        root = ET.fromstring(_get(url))
        trunc = root.find("s3:IsTruncated", NS)
        for ck in root.findall("s3:Contents/s3:Key", NS):
            k = ck.text
            if k.endswith(".CHECKSUM") or k.endswith("/"):
                continue
            keys.append(k)
        if trunc is not None and trunc.text == "true":
            token = root.find("s3:NextContinuationToken", NS).text
        else:
            break
    return sorted(keys)


def _verify_sha256(path: Path, key: str) -> bool:
    try:
        raw = _get(f"{C.S3}/{key}.CHECKSUM").decode().strip()
    except Exception:
        return True  # no checksum published; skip verification
    import hashlib

    want = raw.split()[0].lower()
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    return want == h


def fetch_zip(key: str) -> Path | None:
    """Download one monthly zip into data/raw (skipping existing)."""
    dest = C.RAW / Path(key).name
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    try:
        blob = _get(f"{C.S3}/{key}")
    except HTTPError as e:
        if e.code == 404:
            return None
        raise
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(blob)
    tmp.replace(dest)
    if not _verify_sha256(dest, key):
        dest.unlink(missing_ok=True)
        print(f"  !! checksum mismatch, dropped {dest.name}")
        return None
    return dest


def _read_one_zip(path: Path, cols: list[str]) -> pd.DataFrame:
    """Read one monthly zip.

    Binance added a header row inside the monthly zips (klines from 2022-01,
    fundingRate from 2024-01). Read everything as text, drop the header, then
    coerce to float. A naive dtype='float64' read dies on that header row and
    silently loses every month after it, which is exactly what happened once.
    """
    with zipfile.ZipFile(path) as z:
        name = z.namelist()[0]
        with z.open(name) as fh:
            df = pd.read_csv(fh, header=None, names=cols, dtype=str)
    df = df.replace({"": None, "None": None, "null": None})
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    n0 = len(df)
    df = df.dropna(how="all")
    if len(df) and not np.isfinite(df.iloc[0, 0]):
        df = df.iloc[1:].reset_index(drop=True)
    if len(df) != n0:
        print(f"     (stripped {n0 - len(df)} header/blank row(s) in {path.name})")
    return df


# Timeframes fetched natively from Binance. NOTHING is resampled: every
# timeframe below is downloaded exactly as Binance published it. Deriving our
# own bars cost a silent one-bar labelling error that invalidated nine
# experiments (journal Exp 010), so the pipeline no longer offers to do it.
# Binance's own naming: hourly is "1h", not "60m".
NATIVE_TFS = [1, 3, 5, 15, 30]
TF_NAME = {1: "1m", 3: "3m", 5: "5m", 15: "15m", 30: "30m",
           60: "1h", 120: "2h", 240: "4h", 360: "6h", 480: "8h", 720: "12h"}


def tf_name(tf: int) -> str:
    return TF_NAME.get(tf, f"{tf}m")


def build(dataset: str) -> Path:
    """dataset in {'klines1m', 'klines5m', ..., 'mark1m', 'funding'}"""
    if dataset.startswith("klines") and dataset != "klines1m":
        tf = int(dataset[len("klines"):].rstrip("m"))
        name = tf_name(tf)
        prefix = f"data/futures/{C.MARKET}/monthly/klines/{C.SYMBOL}/{name}/"
        cols = C.KLINE_COLS
        out = C.CACHE / f"{C.SYMBOL}_klines_{name}.parquet"
    elif dataset == "klines1m":
        prefix = f"data/futures/{C.MARKET}/monthly/klines/{C.SYMBOL}/1m/"
        cols = C.KLINE_COLS
        out = C.CACHE / f"{C.SYMBOL}_klines_1m.parquet"
    elif dataset == "mark1m":
        prefix = f"data/futures/{C.MARKET}/monthly/markPriceKlines/{C.SYMBOL}/1m/"
        cols = C.KLINE_COLS
        out = C.CACHE / f"{C.SYMBOL}_mark_1m.parquet"
    elif dataset == "funding":
        prefix = f"data/futures/{C.MARKET}/monthly/fundingRate/{C.SYMBOL}/"
        cols = C.FUNDING_COLS
        out = C.CACHE / f"{C.SYMBOL}_funding.parquet"
    else:
        raise ValueError(dataset)

    if out.exists():
        print(f"[{dataset}] cached -> {out.name}")
        return out

    keys = list_keys(prefix)
    print(f"[{dataset}] {len(keys)} files found")
    frames = []
    for i, key in enumerate(keys, 1):
        z = fetch_zip(key)
        if z is None:
            continue
        try:
            frames.append(_read_one_zip(z, cols))
        except Exception as e:  # noqa: BLE001
            print(f"  !! {z.name}: {e}")
            continue
        if i % 10 == 0 or i == len(keys):
            print(f"  [{i}/{len(keys)}] {z.name}")

    df = pd.concat(frames, ignore_index=True)
    tcol = "open_time" if "open_time" in df.columns else "calc_time"
    df[tcol] = pd.to_datetime(df[tcol], unit="ms", utc=True)
    df = df.sort_values(tcol).drop_duplicates(subset=tcol).reset_index(drop=True)
    df.to_parquet(out, index=False)
    print(f"[{dataset}] wrote {out.name}  rows={len(df):,}  "
          f"{df[tcol].min()} .. {df[tcol].max()}")
    return out


def validate() -> bool:
    """Coverage, duplicates and gap report for every native timeframe cache.

    Returns True only if every timeframe is complete. This is the gate: a
    silently short series is how the original 58-of-80-month data loss shipped
    in the first place.
    """
    ok = True
    for tf in NATIVE_TFS:
        name = tf_name(tf)
        p = C.CACHE / f"{C.SYMBOL}_klines_{name}.parquet"
        if not p.exists():
            print(f"[validate] {name}: MISSING")
            ok = False
            continue
        df = pd.read_parquet(p, columns=["open_time"])
        t = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        months = set(t.dt.strftime("%Y-%m"))
        missing = sorted(set(C.month_range()) - months)
        dup = int(t.duplicated().sum())
        step = t.sort_values().diff().dt.total_seconds().div(60)
        big = step[step > tf * 3]
        print(f"[validate] {name:>4}: rows={len(t):>9,}  "
              f"{t.min().date()} .. {t.max().date()}  "
              f"months={len(months)}/80  dup={dup}  gaps>3x={len(big)}"
              + (f"  MISSING={missing}" if missing else ""))
        if missing or dup or len(big):
            ok = False
    if not (C.CACHE / f"{C.SYMBOL}_funding.parquet").exists():
        print("[validate] funding: MISSING")
        ok = False
    return ok


def main() -> None:
    for tf in NATIVE_TFS:
        try:
            build(f"klines{tf}")
        except Exception as e:  # noqa: BLE001
            print(f"[klines{tf}] FAILED: {e}", file=sys.stderr)
    try:
        build("funding")
    except Exception as e:  # noqa: BLE001
        print(f"[funding] FAILED: {e}", file=sys.stderr)
    print()
    print("VALIDATION:", "OK" if validate() else "PROBLEMS FOUND (see above)")
    if not validate():
        sys.exit(1)


if __name__ == "__main__":
    main()
