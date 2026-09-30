"""Download + cache Binance USDT-M futures public data for one symbol
(C.SYMBOL, BTCUSDT by default; SYMBOL=ETHUSDT python src/datafeed.py for ETH).
The paths below show BTCUSDT as the example.

Only what's needed for intraday research:
  * 1m klines   (trades)      data/futures/um/monthly/klines/BTCUSDT/1m/
  * 1m mark klines (safe fills) .../markPriceKlines/BTCUSDT/1m/
  * funding rate              .../fundingRate/BTCUSDT/
  * metrics (open interest, long/short ratios, 5-minute rows; only with
    --metrics)                data/futures/um/daily/metrics/BTCUSDT/

Each monthly zip is cached under data/raw/ and verified against the
accompanying .CHECKSUM file. Concatenated series are written to
data/cache/*.parquet for fast reload.
"""
from __future__ import annotations

import io
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
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
            # the token holds '+', '/' and '='; unencoded, page 2 is a 400
            # (never hit by the monthly listings, which fit on one page)
            url += f"&continuation-token={quote(token, safe='')}"
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
NATIVE_TFS = [1, 3, 5, 15, 30, 60, 240]
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

    # Pin the window to config, so a fresh download reproduces the same data
    # instead of silently picking up whatever months Binance has added since.
    wanted = set(C.month_range())
    keys = [k for k in list_keys(prefix) if k[-11:-4] in wanted]
    print(f"[{dataset}] {len(keys)} files in {C.DATA_START}..{C.DATA_END}", flush=True)
    t0 = time.time()
    # Download in parallel, then read sequentially in key order. Network I/O is
    # the bottleneck (480 files); the parse stays single-threaded and the output
    # order is identical to a serial run, so the cache is byte-for-byte the same.
    workers = 8
    paths = [None] * len(keys)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_zip, k): i for i, k in enumerate(keys)}
        done = 0
        for fut, i in futs.items():
            try:
                paths[i] = fut.result()
            except Exception as e:  # noqa: BLE001 - report, never hide
                print(f"  !! {keys[i]}: {e}")
            done += 1
            if done % 20 == 0 or done == len(keys):
                print(f"  fetched {done}/{len(keys)}", flush=True)
    frames = []
    for z in paths:
        if z is None:
            continue
        try:
            frames.append(_read_one_zip(z, cols))
        except Exception as e:  # noqa: BLE001
            print(f"  !! {z.name}: {e}")
            continue

    df = pd.concat(frames, ignore_index=True)
    tcol = "open_time" if "open_time" in df.columns else "calc_time"
    df[tcol] = pd.to_datetime(df[tcol], unit="ms", utc=True)
    df = df.sort_values(tcol).drop_duplicates(subset=tcol).reset_index(drop=True)
    df.to_parquet(out, index=False)
    print(f"[{dataset}] wrote {out.name}  rows={len(df):,}  "
          f"{df[tcol].min()} .. {df[tcol].max()}  ({time.time() - t0:.0f}s)", flush=True)
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
              f"months={len(months)}/{len(C.month_range())}  dup={dup}  gaps>3x={len(big)}"
              + (f"  MISSING={missing}" if missing else ""))
        if missing or dup or len(big):
            ok = False
    if not (C.CACHE / f"{C.SYMBOL}_funding.parquet").exists():
        print("[validate] funding: MISSING")
        ok = False
    return ok


# --------------------------------------------------------------------------
# metrics: open interest and long/short ratios (PLAN.md section 14)
# --------------------------------------------------------------------------
METRICS_COLS = ["create_time", "symbol", "sum_open_interest", "sum_open_interest_value",
                "count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio",
                "count_long_short_ratio", "sum_taker_long_short_vol_ratio"]
METRICS_NUM = METRICS_COLS[2:]


def metrics_days() -> list[str]:
    """Every day from the symbol's metrics_start to the end of data_end."""
    if not C.METRICS_START:
        return []
    end = (pd.Period(C.DATA_END, "M").end_time).strftime("%Y-%m-%d")
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(C.METRICS_START, end, freq="D")]


def read_metrics_zip(path: Path) -> pd.DataFrame:
    """One daily metrics zip -> rows with a UTC create_time and float columns.

    Files carry a header row; some early ones repeat every row twice and a few
    days miss a handful of 5-minute rows. Duplicates are dropped here; gaps are
    reported by validate_metrics() and become NaN at attach time."""
    with zipfile.ZipFile(path) as z:
        with z.open(z.namelist()[0]) as fh:
            df = pd.read_csv(fh, header=None, dtype=str)
    df = df.iloc[:, :len(METRICS_COLS)]
    df.columns = METRICS_COLS[:df.shape[1]]
    df = df[df["create_time"] != "create_time"]
    for c in METRICS_NUM:
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    df["create_time"] = pd.to_datetime(df["create_time"], utc=True)
    return df.drop(columns=["symbol"]).drop_duplicates("create_time")


def build_metrics() -> Path | None:
    """Download the daily metrics files for C.SYMBOL and cache one parquet."""
    out = C.CACHE / f"{C.SYMBOL}_metrics.parquet"
    if out.exists():
        print(f"[metrics] cached -> {out.name}")
        return out
    days = set(metrics_days())
    if not days:
        print(f"[metrics] {C.SYMBOL} has no metrics_start in config.SYMBOL_SPECS")
        return None
    prefix = f"data/futures/{C.MARKET}/daily/metrics/{C.SYMBOL}/"
    keys = [k for k in list_keys(prefix) if k[-14:-4] in days]
    print(f"[metrics] {len(keys)} of {len(days)} daily files in "
          f"{min(days)}..{max(days)}", flush=True)
    t0 = time.time()
    paths = [None] * len(keys)
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_zip, k): i for i, k in enumerate(keys)}
        for n, (fut, i) in enumerate(futs.items(), 1):
            try:
                paths[i] = fut.result()
            except Exception as e:  # noqa: BLE001 - report, never hide
                print(f"  !! {keys[i]}: {e}")
            if n % 200 == 0 or n == len(keys):
                print(f"  fetched {n}/{len(keys)}", flush=True)
    frames = []
    for z in paths:
        if z is None:
            continue
        try:
            frames.append(read_metrics_zip(z))
        except Exception as e:  # noqa: BLE001
            print(f"  !! {z.name}: {e}")
    df = (pd.concat(frames, ignore_index=True).sort_values("create_time")
          .drop_duplicates("create_time").reset_index(drop=True))
    df.to_parquet(out, index=False)
    print(f"[metrics] wrote {out.name}  rows={len(df):,}  {df['create_time'].min()} .. "
          f"{df['create_time'].max()}  ({time.time() - t0:.0f}s)", flush=True)
    return out


def validate_metrics(max_missing_share: float = 0.01) -> bool:
    """Coverage report for the metrics cache. OK when every day of the window
    has rows, open interest is always > 0, and under 1% of the 5-minute slots
    are missing. NaN long/short ratios are reported, not failed: Binance left
    whole days empty (e.g. top-trader ratios on 2022-11-09, the FTX crash), and
    blocks treat NaN as 'no signal'."""
    p = C.CACHE / f"{C.SYMBOL}_metrics.parquet"
    if not p.exists():
        print("[metrics] MISSING - run: python src/datafeed.py --metrics")
        return False
    df = pd.read_parquet(p)
    t = pd.to_datetime(df["create_time"], utc=True)
    days = set(metrics_days())
    have = set(t.dt.strftime("%Y-%m-%d"))
    miss_days = sorted(days - have)
    slots = pd.date_range(min(days), pd.Timestamp(max(days)) + pd.Timedelta("23:55:00"),
                          freq="5min", tz="UTC")
    miss_slots = len(slots.difference(pd.DatetimeIndex(t)))
    dup = int(t.duplicated().sum())
    bad_oi = int((df["sum_open_interest"].fillna(0) <= 0).sum())
    nan = {c: int(df[c].isna().sum()) for c in METRICS_NUM if df[c].isna().any()}
    share = miss_slots / len(slots)
    print(f"[metrics] rows={len(df):,}  {t.min()} .. {t.max()}  days={len(have & days)}/{len(days)}  "
          f"missing 5m slots={miss_slots:,} ({share:.2%})  dup={dup}  oi<=0={bad_oi}"
          + (f"  MISSING DAYS={miss_days[:10]}" if miss_days else ""))
    if nan:
        print(f"[metrics] NaN (kept, read as no signal): {nan}")
    return not miss_days and not dup and not bad_oi and share <= max_missing_share


def main() -> None:
    if "--metrics" in sys.argv[1:]:
        try:
            build_metrics()
        except Exception as e:  # noqa: BLE001
            print(f"[metrics] FAILED: {e}", file=sys.stderr)
        ok = validate_metrics()
        print("METRICS VALIDATION:", "OK" if ok else "PROBLEMS FOUND (see above)")
        sys.exit(0 if ok else 1)
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
