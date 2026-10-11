"""BTC lead-lag catch-up on the large alts (PLAN.md section 47)

    python src/leadlag.py            # TRAIN/VALID, once (uses section 36's 4h caches; no new download)
    python src/leadlag.py --final    # HOLDOUT once, only after PASS (this family's own holdout)

Why (_multi Exp 091, a TRAIN-only scan of new families on the ten coins): when
BTC makes a large 4h move and an alt lags it by more than RT of its own ATRs,
the alt tends to catch up over the next one to three days. Alts that followed
BTC on the same bars do not earn the same (TRAIN, 6 bars, BTC > 1 ATR: lagging
alts +0.137 ATR net, following alts -0.017). Mean-reversion families (fading
over-extension, failed breakouts, capitulation bars) all lost on TRAIN.

Hypothesis: news and flow reach BTC first; alt books are thinner and are
re-priced later by traders who trade the alts against BTC's move. An alt that
has not followed a large BTC move is mispriced for a while, and the gap closes
in the direction of BTC's move. Someone who trades it before the gap closes
takes the other side of the slow re-pricing.
Known risk, stated before the run: the effect was found by scanning about 7
families on TRAIN, so TRAIN overstates it. TRAIN 2022 is near zero in every
cell (2021 carries it). VALID is the first look.

The rule (no ML: the ML line on these coins is paused, Exp 090):
- leader BTC; traded: the other nine of the owner's ten coins, each from 365
  days after listing (section 37's sets); BTC itself is not traded;
- move[t] = (close[t] / close[t-1] - 1) / (ATR14[t-1] / close[t-1]), on the
  4h perp bars, for BTC and for the alt; gap[t] = move_alt[t] - move_btc[t];
- form `lag`: long when move_btc > BT and gap < -RT; short when move_btc < -BT
  and gap > RT (decided at the close, filled at the next open);
- exit (no clock): a signal exit when the alt has caught up since the event
  bar's open, side x [(alt close / alt open_e - 1) - (BTC close / BTC open_e - 1)]
  >= 0, or the stop at K x ATR14 from the fill; events are ignored while a
  position is open (one position per coin);
- section 31's account at half scale: flat 0.5% risk per trade, 2.5% cap per
  direction (one BTC bar can fire all nine alts on the same side, and at 1% /
  5% every TRAIN cell had a max drawdown of 21-32%: Exp 091); fees, slippage,
  funding as section 41.
TRAIN (2021-22) picks 1 of 8 cells: BT {1.0, 1.5} x RT {0.5, 1.0} x K {2, 3},
by section 38's rule (>= 100 trades, both TRAIN years and both legs positive,
then the weekly t). No selectable cell is REJECT.
Control (the hypothesis' own test): form `follow` with the same BT and K -
the alts that moved WITH BTC (long when move_btc > BT and gap >= -RT) - must
earn less on VALID (`valid_beats_follow`). Otherwise the book is BTC momentum,
not catch-up.
VALID gates: section 41's (>= 100 trades, weekly mean > 0, weekly-block CI lo
> 0, cost x1.5 > 0, timing above the shifted p95, >= 8 coins and half beat
their shifts, both legs > 0, max DD <= 20%) plus valid_beats_follow.
Holdout: a new family with its own one-time holdout (not the ML line's).
Writes results/_multi/s47_leadlag_4h/ and journal/_multi/s47_leadlag_4h.md.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
import indicators as ta  # noqa: E402
import ml_hold as MH  # noqa: E402
import ml_large as ML  # noqa: E402
import ml_pool as PL  # noqa: E402
import ml_port as MP  # noqa: E402
import ml_recent as MR  # noqa: E402
import ml_wf as WF  # noqa: E402
import ml_wf2 as W2  # noqa: E402
import ml_wide as MW  # noqa: E402
import run_record as RR  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "s47_leadlag_4h"
REPORT = C.ROOT / "journal" / "_multi" / "s47_leadlag_4h.md"

# ---- pre-registered (PLAN.md section 47, _multi Exp 091)
TF = 240
LEADER = "BTCUSDT"
ALTS = tuple(c for c in ML.COINS if c != LEADER)
BTS = (1.0, 1.5)
RTS = (0.5, 1.0)
STOPS = (2.0, 3.0)
SIZING, CAP = "flat", 0.05
RISK_SCALE = 0.5            # 0.5% per trade, 2.5% per direction: one BTC bar can fire all nine alts at once
MIN_TRADES, MIN_COINS = ML.MIN_TRADES, ML.MIN_COINS


# --------------------------------------------------------------------------
# pure pieces (test 45)
# --------------------------------------------------------------------------
def moves(close: np.ndarray, atr: np.ndarray) -> np.ndarray:
    """move[t] = (close[t] / close[t-1] - 1) / (atr[t-1] / close[t-1]); NaN at 0 or without an ATR."""
    c, a = np.asarray(close, float), np.asarray(atr, float)
    out = np.full(len(c), np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        out[1:] = (c[1:] - c[:-1]) / a[:-1]
    return np.where(np.isfinite(out), out, np.nan)


def events(bm: np.ndarray, gap: np.ndarray, bt: float, rt: float, form: str) -> np.ndarray:
    """+1 / -1 / 0 per bar. lag: the alt lagged BTC's large move; follow: it moved with it."""
    with np.errstate(invalid="ignore"):
        up, dn = bm > bt, bm < -bt
        if form == "lag":
            lo, sh = up & (gap < -rt), dn & (gap > rt)
        elif form == "follow":
            lo, sh = up & (gap >= -rt), dn & (gap <= rt)
        else:
            raise ValueError(form)
    return np.where(lo, 1, np.where(sh, -1, 0)).astype(int)


def lag_path(o, h, l, c, bo, bc, ev, atr, k: float, slip: float) -> tuple[np.ndarray, np.ndarray]:
    """(target, held). target[t] is a decision at the close of bar t (NaN = none): the event's side
    when flat, 0 when the gap has closed. The stop (k x atr at the event bar, from the fill at
    o[t+1] x (1 + slip x side), stop-first from the fill bar) is tracked as MH.simulate does, so a
    stopped position is not re-entered. held[t] = the position after bar t's decision."""
    n = len(c)
    target, held = np.full(n, np.nan), np.zeros(n)
    pos, stop, ra, rb, fill = 0, 0.0, 0.0, 0.0, -1
    for t in range(n):
        if pos != 0 and t >= fill:
            if (l[t] <= stop) if pos > 0 else (h[t] >= stop):
                pos = 0                                  # stopped inside bar t; may re-enter below
            else:
                rel = (c[t] / ra - 1.0) - (bc[t] / rb - 1.0)
                if pos * rel >= 0:
                    target[t], pos = 0.0, 0
                    held[t] = 0
                    continue
        if pos == 0 and ev[t] != 0 and t + 1 < n and np.isfinite(atr[t]) and atr[t] > 0 \
                and np.isfinite(bo[t]) and np.isfinite(bc[t]):
            s = int(ev[t])
            entry = o[t + 1] * (1 + slip * s)
            pos, stop, ra, rb, fill = s, entry - s * k * atr[t], o[t], bo[t], t + 1
            target[t] = float(s)
        held[t] = pos
    return target, held


def cells() -> list[tuple[float, float, float]]:
    return [(bt, rt, k) for bt in BTS for rt in RTS for k in STOPS]


def cell_name(cell, form: str = "lag") -> str:
    return f"{form}_bt{cell[0]:g}_rt{cell[1]:g}_k{cell[2]:g}"


# --------------------------------------------------------------------------
def prepare(bars: dict, fund: dict) -> dict:
    """Per coin: perp 4h bars, ATR14 (NaN where the market is absent), BTC aligned, moves, rn."""
    btc = bars[LEADER]
    b_atr = ta.atr_(btc["high"], btc["low"], btc["close"], MH.ATR_N)
    D = {}
    for c, b in bars.items():
        atr = ta.atr_(b["high"], b["low"], b["close"], MH.ATR_N)
        with np.errstate(divide="ignore", invalid="ignore"):
            afrac = (atr / b["close"]).to_numpy(float)
        good = (b["volume"].to_numpy(float) > 0) & np.isfinite(afrac) & (afrac >= WF.AFRAC_MIN)
        a = np.where(good, atr.to_numpy(float), np.nan)
        bb = btc.reindex(b.index)
        ba = b_atr.reindex(b.index).to_numpy(float)
        o = b["open"].to_numpy(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            rn = np.r_[np.log(o[1:] / o[:-1]), np.nan] / np.r_[np.nan, np.where(good, afrac, np.nan)[:-1]]
        bm = moves(bb["close"].to_numpy(float), ba)
        D[c] = {"bars": b, "atr": a, "fund": fund[c], "slip": PL.slippage(c), "rn": rn,
                "pos": np.arange(len(b)), "bo": bb["open"].to_numpy(float), "bc": bb["close"].to_numpy(float),
                "bm": bm, "gap": moves(b["close"].to_numpy(float), a) - bm}
    return D


def run_cell(D, cell, a, b, traded, form="lag", stress=1.0):
    bt, rt, k = cell
    fr, paths = [], {}
    for c in ALTS:
        if c not in D:
            continue
        d = D[c]
        lo, hi, _ = _window(d, a, b)
        if hi - lo < 2:
            continue
        sl = slice(lo, hi)
        allowed = MW.month_mask(d["bars"].index[sl], c, traded)
        ev = np.where(allowed, events(d["bm"][sl], d["gap"][sl], bt, rt, form), 0)
        bars = d["bars"].iloc[sl]
        slip = d["slip"] * stress
        tgt, held = lag_path(*(bars[x].to_numpy(float) for x in ("open", "high", "low", "close")),
                             d["bo"][sl], d["bc"][sl], ev, d["atr"][sl], k, slip)
        if not np.any(held != 0):
            continue
        t = MH.simulate(bars, tgt, d["atr"][sl], d["fund"], fee=C.FEE_TAKER * stress, slip=slip, stop_atr=k)
        fr.append(t.assign(coin=c, conf=1.0))
        paths[c] = (held, np.arange(hi - lo), lo, hi)
    t = pd.concat(fr, ignore_index=True) if fr else pd.DataFrame(
        columns=["entry_time", "exit_time", "side", "net_r", "conf", "coin", "reason", "bars"])
    t = MP.size_trades(t, SIZING, CAP)
    t["risk"] *= RISK_SCALE
    t["ret"] *= RISK_SCALE
    return t, paths


def _window(d, a, b):
    idx = d["bars"].index
    lo, hi = idx.searchsorted(pd.Timestamp(a, tz="UTC")), idx.searchsorted(pd.Timestamp(b, tz="UTC"))
    return lo, hi, np.arange(hi - lo)


def judge(D, cell, a, b, traded, form="lag", min_coins=MIN_COINS):
    t, paths = run_cell(D, cell, a, b, traded, form)
    acc = MP.account(t, a, b)
    acc["stress_weekly_mean"] = MP.account(run_cell(D, cell, a, b, traded, form, 1.5)[0], a, b)["weekly_mean"]
    Pc = {c: {"pos": np.arange(paths[c][3] - paths[c][2]) + paths[c][2], "rn": D[c]["rn"]} for c in paths}
    timing, per, pooled = MH.control(Pc, paths)
    coins = {}
    for c in paths:
        tc = t[t["coin"] == c]
        coins[c] = {"trades": int(len(tc)), "mean_r": float(tc["net_r"].mean()) if len(tc) else None,
                    "timing": per[c]["timing"], "shift_median": MH._q(per[c]["shifts"], 50)}
    elig = {c: x for c, x in coins.items() if x["trades"] >= ML.MIN_COIN_TRADES}
    beat = [c for c, x in elig.items() if x["mean_r"] > 0 and x["timing"] is not None
            and x["shift_median"] is not None and x["timing"] > x["shift_median"]]
    w = MP.weekly(t, a, b)
    tot = float(w.sum())
    top = w.sort_values(ascending=False).iloc[:5]
    acc.update(timing=timing, shift_median=MH._q(pooled, 50), shift_p95=MH._q(pooled, 95), per_coin=coins,
               breadth={"eligible": len(elig), "beat": beat, "share": len(beat) / len(elig) if elig else 0.0},
               per_year_r={str(y): float(g["ret"].sum()) for y, g in t.groupby(pd.to_datetime(t["exit_time"]).dt.year)},
               top5_weeks_share=float(top.sum()) / tot if tot > 0 else None,
               weekly_mean_without_top5=float(w.drop(top.index).mean()) if len(w) > 5 else None,
               neg_weeks=int((w < 0).sum()), short_share=MR.short_share(t),
               hold_bars={"median": float(t["bars"].median()) if len(t) else None,
                          "mean": float(t["bars"].mean()) if len(t) else None},
               exit_mix={k: float(v) for k, v in t["reason"].value_counts(normalize=True).items()} if len(t) else {})
    return acc, t


def _row(t, a, b, cell, form):
    acc = MP.account(t, a, b)
    row = {"form": cell_name(cell, form), "bt": cell[0], "rt": cell[1], "k": cell[2],
           **{x: acc[x] for x in ("trades", "weekly_mean", "tstat", "max_dd", "mean_r", "long_ret", "short_ret")},
           "per_year_r": {str(y): float(g["ret"].sum()) for y, g in t.groupby(pd.to_datetime(t["exit_time"]).dt.year)},
           "short_share": MR.short_share(t)}
    row["selectable"] = MR.selectable(row, MIN_TRADES)
    return row


def evaluate(D, traded, min_coins=MIN_COINS, keep=False) -> dict:
    a_tr, b_tr = WF.WINDOWS["train"]
    a_va, b_va = WF.WINDOWS["valid"]
    table, follow_train, train_trades = [], [], {}
    for cell in cells():
        t, _ = run_cell(D, cell, a_tr, b_tr, traded)
        train_trades[cell_name(cell)] = t
        row = _row(t, a_tr, b_tr, cell, "lag")
        table.append(row)
        print(f"TRAIN {row['form']}: {row['trades']} trades, weekly {row['weekly_mean']:+.5f}, t {row['tstat']:+.2f}, "
              f"mean R {row['mean_r']:+.4f}, years {row['per_year_r']}, selectable {row['selectable']}", flush=True)
        fr = _row(run_cell(D, cell, a_tr, b_tr, traded, "follow")[0], a_tr, b_tr, cell, "follow")
        fr.pop("selectable")
        follow_train.append(fr)
    ok = [x for x in table if x["selectable"]]
    best = max(ok, key=lambda x: x["tstat"]) if ok else max(table, key=lambda x: x["tstat"])
    cell = (best["bt"], best["rt"], best["k"])
    tj, _ = judge(D, cell, a_tr, b_tr, traded, min_coins=min_coins)
    train_checks = {x: tj[x] for x in ("trades", "weekly_mean", "ci_lo", "ci_hi", "tstat", "stress_weekly_mean",
                                       "timing", "shift_median", "shift_p95", "long_ret", "short_ret", "max_dd",
                                       "mean_r", "per_year_r", "top5_weeks_share", "hold_bars", "exit_mix")}
    train_checks["breadth"] = {x: tj["breadth"][x] for x in ("eligible", "share")}
    v, t = judge(D, cell, a_va, b_va, traded, min_coins=min_coins)
    fv, _ = judge(D, cell, a_va, b_va, traded, "follow", min_coins)
    v["follow_same_cell"] = {"form": cell_name(cell, "follow"),
                             **{x: fv[x] for x in ("trades", "weekly_mean", "ci_lo", "ci_hi", "tstat", "mean_r",
                                                   "long_ret", "short_ret", "max_dd", "short_share", "per_year_r")}}
    gates = {"train_cell_selectable": bool(ok),
             "train_weekly_mean>0": best["weekly_mean"] > 0,
             f"valid_trades>={MIN_TRADES}": v["trades"] >= MIN_TRADES,
             "valid_weekly_mean>0": v["weekly_mean"] > 0,
             "valid_ci_lo>0": v["ci_lo"] > 0,
             "stress_weekly_mean>0": v["stress_weekly_mean"] > 0,
             "timing_beats_shift_p95": v["shift_p95"] is not None and v["timing"] is not None
             and v["timing"] > v["shift_p95"],
             f"coins>={min_coins}": v["breadth"]["eligible"] >= min_coins,
             f"breadth>={MP.BREADTH_SHARE}": v["breadth"]["share"] >= MP.BREADTH_SHARE,
             "both_legs>0": v["long_ret"] > 0 and v["short_ret"] > 0,
             f"max_dd<={MP.MAX_DD}": v["max_dd"] <= MP.MAX_DD,
             "valid_beats_follow": v["weekly_mean"] > fv["weekly_mean"]}
    failed = [x for x, g in gates.items() if not g]
    res = {"chosen": {"form": best["form"], "bt": cell[0], "rt": cell[1], "k": cell[2], "tf": TF,
                      "sizing": SIZING, "cap": CAP, "risk_scale": RISK_SCALE},
           "train_table": table, "follow_train_table": follow_train, "train_checks": train_checks, "valid": v,
           "verdict": "REJECT" if failed else "PASS", "gates_failed": failed,
           "rule": {"leader": LEADER, "traded": list(ALTS), "bts": BTS, "rts": RTS, "stops": STOPS,
                    "exit": "gap closed since the event bar's open, or the K-ATR stop; no clock"}}
    if keep:
        res["_trades"] = t
        res["_train_trades"] = train_trades
    return res


# --------------------------------------------------------------------------
def _load():
    months = [str(p) for p in pd.period_range("2020-01", C.DATA_END, freq="M")]
    traded = ML.traded_sets(ML._first_traded(), months)
    bars, fund, inputs = {}, {}, []
    for c in ML.COINS:
        p, f = WF.cache_dir(TF) / f"{c}.parquet", WF.cache_dir(60) / f"{c}_funding.parquet"
        if not (p.exists() and f.exists()):
            raise SystemExit(f"no cached 4h bars / funding for {c}: run  python src/ml_wide.py --build  first")
        bars[c], fund[c] = W2._read(p), pd.read_parquet(f)
        inputs += [p, f]
    return traded, bars, fund, inputs


def run(final: bool = False) -> None:
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    res_path, lock = OUT / "summary.json", OUT / "holdout.json"
    if final:
        res = json.loads(res_path.read_text()) if res_path.exists() else None
        if not res or res["verdict"] != "PASS":
            raise SystemExit("--final refused: needs a PASS from the TRAIN/VALID run")
        if lock.exists():
            raise SystemExit(f"--final refused: holdout already used ({lock})")
    elif res_path.exists():
        raise SystemExit(f"{res_path} exists: pre-registered, run once (delete only after a journaled code fix)")
    traded, bars, fund, inputs = _load()
    D = prepare(bars, fund)
    print(f"[leadlag] leader {LEADER}; traded {list(ALTS)}", flush=True)
    if final:
        a, b = WF.WINDOWS["holdout"]
        ch = res["chosen"]
        h, t = judge(D, (ch["bt"], ch["rt"], ch["k"]), a, b, traded)
        h["verdict"] = ("CONFIRMED" if h["weekly_mean"] > 0 and h["ci_lo"] > 0 and h["shift_median"] is not None
                        and h["timing"] is not None and h["timing"] > h["shift_median"]
                        and h["breadth"]["share"] >= MP.BREADTH_SHARE else "FAILED")
        lock.write_text(json.dumps(h, indent=1, default=str))
        t.to_csv(OUT / "trades_holdout.csv.gz", index=False)
        write_report(res)
        print(json.dumps({x: h.get(x) for x in ("trades", "weekly_mean", "ci_lo", "verdict")}, indent=1))
        return
    res = evaluate(D, traded, keep=True)
    tv = res.pop("_trades")
    tv.to_csv(OUT / "trades_valid.csv.gz", index=False)
    for form, tt in res.pop("_train_trades").items():
        tt.to_csv(OUT / f"trades_train_{form}.csv.gz", index=False)
    a, b = WF.WINDOWS["valid"]
    RR.write(OUT / "record" / "valid", run_info=RR.run_info(started, inputs),
             holdout_power=RR.holdout_power(MP.weekly(tv, a, b)))
    res_path.write_text(json.dumps(res, indent=1, default=str))
    write_report(res)
    print(f"\nLEADLAG: chose {res['chosen']['form']} -> {res['verdict']} failed {res['gates_failed']}")


def write_report(r: dict) -> None:
    v, fo = r["valid"], r["valid"]["follow_same_cell"]
    f = (lambda x, k=5: "-" if x is None else f"{x:+.{k}f}")
    L = ["# BTC lead-lag catch-up on the large alts (PLAN.md section 47)", "",
         "GENERATED by `src/leadlag.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}** (TRAIN chose {r['chosen']['form']}; failed: {r['gates_failed'] or 'none'})", "",
         f"- VALID {v['trades']} trades: weekly {f(v['weekly_mean'])}, 95% CI [{f(v['ci_lo'])}, {f(v['ci_hi'])}], "
         f"t {v['tstat']:+.2f}; mean R {f(v['mean_r'], 4)}; long {f(v['long_ret'], 4)} / short {f(v['short_ret'], 4)}; "
         f"max DD {v['max_dd']:.4f}; by year {v['per_year_r']}",
         f"- cost x1.5 {f(v['stress_weekly_mean'])}; timing {f(v['timing'], 4)} vs shifted p95 {f(v['shift_p95'], 4)}; "
         f"breadth {len(v['breadth']['beat'])} of {v['breadth']['eligible']}; short share {v['short_share']}",
         f"- hold (4h bars) {v['hold_bars']}; exits {v['exit_mix']}",
         f"- control `{fo['form']}` (alts that moved WITH BTC, same cell) on VALID: {fo['trades']} trades, weekly "
         f"{f(fo['weekly_mean'])}, CI [{f(fo['ci_lo'])}, {f(fo['ci_hi'])}], mean R {f(fo['mean_r'], 4)}, "
         f"long {f(fo['long_ret'], 4)} / short {f(fo['short_ret'], 4)}",
         f"- best 5 weeks = {f(v['top5_weeks_share'], 3)} of the total; weekly mean without them "
         f"{f(v['weekly_mean_without_top5'])}", "",
         "| cell | TRAIN trades | weekly mean | t | mean R | long | short | by year | selectable | follow twin weekly |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for x, y in zip(r["train_table"], r["follow_train_table"]):
        L.append(f"| {x['form']} | {x['trades']} | {f(x['weekly_mean'])} | {x['tstat']:+.2f} | {f(x['mean_r'], 4)} | "
                 f"{f(x['long_ret'], 4)} | {f(x['short_ret'], 4)} | {x['per_year_r']} | {x['selectable']} | "
                 f"{f(y['weekly_mean'])} |")
    hp = OUT / "holdout.json"
    if hp.exists():
        h = json.loads(hp.read_text())
        L += ["", f"## HOLDOUT: **{h['verdict']}** - {h['trades']} trades, weekly {f(h['weekly_mean'])}, "
                  f"CI lo {f(h['ci_lo'])}"]
    REPORT.write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--final", action="store_true", help="run the holdout once (needs PASS)")
    run(ap.parse_args().final)


if __name__ == "__main__":
    main()
