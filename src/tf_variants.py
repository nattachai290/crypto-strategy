"""Make timeframe variants of an idea file, so every idea is tested on every TF.

    python src/tf_variants.py ideas/020_short_pullback.json               # mode chart (default)
    python src/tf_variants.py ideas/020_short_pullback.json --mode time --tfs 5,30
    python src/tf_variants.py ideas/020_short_pullback.json --tfs 60,240

writes ideas/020_short_pullback_tf1.json, _tf3, ... (every native timeframe
except the source's own, unless --tfs is given). Then evaluate each file.

Two ways to move an idea to another timeframe:

--mode chart (default) - "the same setup on the other chart"
  * bar counts unchanged: a 48-bar Donchian is 12 h on 15m and 8 days on 4h
  * ATR multiples unchanged (ATR is measured on that chart's bars)
  * max_hold_hours x (tf / source_tf): hold the same number of BARS
  * stop.pct x sqrt(tf / source_tf): a bar's range grows roughly with the
    square root of its duration, so the stop keeps the same size relative to
    that chart's noise
  Works for every timeframe. This is what "test it on the 1h chart" means.

--mode time - "the same trade on a finer or coarser clock"
  * bar counts x (source_tf / tf): 48 bars on 15m = 12 h = 720 bars on 1m
  * ATR multiples x sqrt(source_tf / tf): keep the same PRICE distance
    (without this a 2% pct stop's ATR clamp would squeeze it to ~0.4% on 1m)
  * hours and % of price unchanged
  Only meaningful near the source timeframe: bar counts are floored at 5
  (indicator periods) or 1 (cooldown / confirm), and the tool refuses a
  target where max_hold_hours would be under 3 bars.

Never rescaled, in either mode: anything in R (be_at, trail_at, tp.r),
thresholds on indicator values (RSI levels, z, ADX levels, band k), UTC hours
and weekdays, and htf_trend's `mult` (a multiple of its own n).
Grid values follow the same rules, then are de-duplicated.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import datafeed  # noqa: E402

BAR_KEYS = {"n", "fast", "slow", "range_n", "atr_n", "z_n", "lookback",
            "cooldown_bars", "confirm_bars"}
ATR_KEYS = {"min_atr", "max_atr", "buffer_atr", "trail_atr", "atr_k",
            "entry_offset_atr"}
# `mult` is an ATR multiple in these places only (in htf_trend it multiplies n)
ATR_MULT_TYPES = {"atr", "supertrend_flip"}


def _kind(key: str, parent: dict | None) -> str:
    if key == "max_hold_hours":
        return "hold"
    if key == "pct" and parent is not None and parent.get("type") == "pct":
        return "pct"
    if key in BAR_KEYS:
        return "bar"
    if key in ATR_KEYS:
        return "atr"
    if key == "mult" and parent is not None and parent.get("type") in ATR_MULT_TYPES:
        return "atr"
    return ""


PERIOD_FLOOR = {"cooldown_bars": 1, "confirm_bars": 1}  # everything else: 5


def _scale(value, kind: str, f_bar: float, f_atr: float, key: str = ""):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    if kind == "bar" and f_bar != 1.0:
        return max(PERIOD_FLOOR.get(key, 5), int(round(value * f_bar)))
    if kind == "atr" and f_atr != 1.0:
        return round(value * f_atr, 3)
    if kind == "hold" and f_bar != 1.0:
        return round(value * f_bar, 2)
    if kind == "pct" and f_atr != 1.0:
        return round(value * f_atr, 4)
    return value


def _walk(obj, factors: dict, parent: dict | None = None):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                out[k] = _walk(v, factors, obj)
            else:
                kind = _kind(k, obj)
                out[k] = _scale(v, kind, *factors.get(kind, (1.0, 1.0)), key=k)
        return out
    if isinstance(obj, list):
        return [_walk(v, factors, parent) for v in obj]
    return obj


def _resolve_parent(params: dict, execution: dict, path: str) -> tuple[str, dict | None]:
    """For a grid key like 'triggers.0.n' return ('n', params['triggers'][0])."""
    if path.startswith("exec."):
        return path[5:], execution
    keys = path.split(".")
    cur = params
    for k in keys[:-1]:
        try:
            cur = cur[int(k)] if isinstance(cur, list) else cur[k]
        except (KeyError, IndexError, ValueError, TypeError):
            return keys[-1], None
    return keys[-1], cur if isinstance(cur, dict) else None


def _factors(mode: str, src_tf: int, tf: int) -> dict:
    """kind -> (f_bar, f_atr) arguments for _scale."""
    if mode == "chart":
        return {"hold": (tf / src_tf, 1.0), "pct": (1.0, math.sqrt(tf / src_tf))}
    if mode == "time":
        return {"bar": (src_tf / tf, 1.0), "atr": (1.0, math.sqrt(src_tf / tf))}
    raise SystemExit("mode must be 'chart' or 'time'")


def make_variant(idea: dict, tf: int, mode: str = "chart") -> dict:
    src_tf = int(idea["tf"])
    fac = _factors(mode, src_tf, tf)
    if mode == "time":
        hold_bars = idea["params"].get("max_hold_hours", 4) * 60 / tf
        if hold_bars < 3:
            raise SystemExit(f"--mode time to {tf}m: max_hold_hours is only {hold_bars:.1f} bars. "
                             f"Use --mode chart for timeframes this far from {src_tf}m.")
    out = copy.deepcopy(idea)
    out["tf"] = tf
    out["name"] = f"{idea['name']}_tf{tf}"
    out["variant_of"] = idea["name"]
    out["variant_mode"] = mode
    how = ("same bar counts and ATR multiples, hold x%g, pct stop x%.3f"
           % (tf / src_tf, math.sqrt(tf / src_tf)) if mode == "chart" else
           "bar counts x%g, ATR multiples x%.3f, same hours and %% stops"
           % (src_tf / tf, math.sqrt(src_tf / tf)))
    out["hypothesis"] = (f"{idea['hypothesis']} [Timeframe variant of {idea['name']}, "
                         f"{src_tf}m -> {tf}m, mode {mode}: {how}.]")
    out["params"] = _walk(idea["params"], fac)
    ex = idea.get("execution", {})
    out["execution"] = _walk(ex, fac, ex)
    grid = {}
    for path, values in idea.get("grid", {}).items():
        key, parent = _resolve_parent(idea["params"], ex, path)
        kind = _kind(key, parent)
        f = fac.get(kind, (1.0, 1.0))
        grid[path] = list(dict.fromkeys(_scale(v, kind, *f, key=key) for v in values))
    out["grid"] = grid
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("idea")
    ap.add_argument("--tfs", help="comma list, default: every native timeframe")
    ap.add_argument("--mode", default="chart", choices=["chart", "time"])
    a = ap.parse_args()
    src = Path(a.idea)
    idea = json.loads(src.read_text(encoding="utf-8"))
    tfs = ([int(x) for x in a.tfs.split(",")] if a.tfs else datafeed.NATIVE_TFS)
    for tf in tfs:
        if tf == int(idea["tf"]):
            continue
        if tf not in datafeed.NATIVE_TFS:
            raise SystemExit(f"tf {tf} is not a native timeframe {datafeed.NATIVE_TFS}")
        v = make_variant(idea, tf, a.mode)
        suffix = f"_tf{tf}" if a.mode == "chart" else f"_tf{tf}_time"
        v["name"] = f"{idea['name']}{suffix}"
        dst = src.with_name(f"{src.stem}{suffix}.json")
        if dst.exists():
            print(f"exists, not overwritten: {dst}")
            continue
        dst.write_text(json.dumps(v, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {dst}")


if __name__ == "__main__":
    main()
