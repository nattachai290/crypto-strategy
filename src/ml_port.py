"""Portfolio layer on section 30's 1h model: agreement, sizing, risk cap (PLAN.md section 31)

    python src/ml_port.py           # TRAIN/VALID, once (needs ml_wf3.py --build caches)
    python src/ml_port.py --final   # HOLDOUT once, only after PASS

Section 30's 1h book (_multi Exp 030/031) failed one gate, the weekly-block CI
(mean +0.0374 R, CI [-0.0235, +0.1006]): dozens of same-direction positions on
coins that move together made the weekly result swing. The model is NOT
changed here. Section 30's three frozen walk-forward models (1h, 4h, 1d, each
with the cell its own TRAIN walk-forward chose) are recomputed exactly (and
checked against section 30's recorded VALID forecasts), and three portfolio
switches are added on top of the 1h book, all simulated as ONE account:
  A  agreement   "off" | "4h" | "1d": a NEW 1h position is opened only if the
                 last CLOSED 4h (or 1d) forecast of that coin has the same sign;
                 exits are unchanged (section 30's policy).
  S  sizing      "flat" (1% risk) | "conf": risk = 1% x w, w = 0.5 at the entry
                 bar and rising linearly to 1.0 at twice the entry bar (never > 1%).
  K  risk cap    None | 5% | 10%: total open risk per direction; a new entry
                 gets at most the remaining room, and is skipped under 0.1%.
Simplifications, stated before the run: a trade the cap skips is not retried
when room frees (the coin stays out until its desired position next changes);
entries at the same hour are sized in coin-name order; the timing control reads
the agreement-filtered desired path and ignores cap skips.
TRAIN walk-forward (2021-22) chooses 1 of the 18 cells by the t-statistic of the
weekly account return (>= MIN_TRADES trades). VALID (2023-24) judges it once.
Account return per trade = net R x risk fraction (additive, of starting
equity); a week's return = the trades that closed in it (empty weeks count 0).
Gates on VALID (all needed):
  TRAIN weekly mean > 0; >= MIN_TRADES trades; weekly mean > 0 and its 95%
  bootstrap CI lower bound > 0; weekly mean > 0 at cost x1.5; timing of the
  filtered desired path above the 95th percentile of 200 shifts (ml_hold.control);
  >= MIN_COINS coins with >= MIN_COIN_TRADES trades, at least half net > 0 AND
  above their own shifted median; both legs' summed return > 0; max drawdown of
  the account <= 20%.
--final: CONFIRMED = holdout weekly mean > 0, CI lower bound > 0, timing above
the shifted median, breadth >= half. Writes results/_multi/ml_port/ and the
generated journal/_multi/ml_port.md.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
import ml_hold as MH  # noqa: E402
import ml_wf as WF  # noqa: E402
import ml_wf2 as W2  # noqa: E402
import ml_wf3 as W3  # noqa: E402

OUT = C.ROOT / "results" / "_multi" / "ml_port"
REPORT = C.ROOT / "journal" / "_multi" / "ml_port.md"
SRC = C.ROOT / "results" / "_multi" / "ml_wf3"

# ---- pre-registered (PLAN.md section 31)
TF_MAIN, TF_OTHER = 60, (240, 1440)
AGREE = ("off", "4h", "1d")
SIZING = ("flat", "conf")
CAP = (None, 0.05, 0.10)
BASE_RISK, MIN_RISK = 0.01, 0.001
MAX_DD = 0.20
MIN_TRADES, MIN_COIN_TRADES, MIN_COINS, BREADTH_SHARE = 300, 10, 10, 0.5
N_BOOT, BLOCK = 5000, "7D"
REPRO_TOL = 1e-6
AGREE_TF = {"4h": 240, "1d": 1440}


# --------------------------------------------------------------------------
# pure pieces (test 27)
# --------------------------------------------------------------------------
def agree_filter(desired: np.ndarray, other: np.ndarray) -> np.ndarray:
    """Desired path with NEW entries allowed only where sign(other) equals the
    new side; holding and exiting are untouched. NaN other = no agreement."""
    out, pos = np.zeros(len(desired)), 0.0
    for t, want in enumerate(desired):
        if want == pos:
            pass
        elif want == 0:
            pos = 0.0
        else:
            ok = np.isfinite(other[t]) and np.sign(other[t]) == want
            pos = want if ok else 0.0
        out[t] = pos
    return out


def conf_weight(ratio: np.ndarray) -> np.ndarray:
    """|forecast| / entry bar -> risk weight: 0.5 at the bar, 1.0 at twice the bar."""
    r = np.asarray(ratio, float)
    return np.where(np.isfinite(r), 0.5 + 0.5 * np.clip(r - 1.0, 0.0, 1.0), 0.5)


def size_trades(t: pd.DataFrame, sizing: str, cap: float | None) -> pd.DataFrame:
    """Risk fraction of every trade, in entry order, one account. A trade is
    open from its entry_time to its exit_time; the cap counts open same-side risk."""
    t = t.sort_values(["entry_time", "coin"]).reset_index(drop=True)
    want = BASE_RISK * (conf_weight(t["conf"].to_numpy()) if sizing == "conf" else np.ones(len(t)))
    risk = np.zeros(len(t))
    open_ = []                                           # (exit_time, side, risk)
    for i, (et, xt, s) in enumerate(zip(t["entry_time"], t["exit_time"], t["side"])):
        open_ = [o for o in open_ if o[0] >= et]
        r = want[i]
        if cap is not None:
            room = cap - sum(o[2] for o in open_ if o[1] == s)
            r = min(r, max(room, 0.0))
        if r < MIN_RISK:
            continue
        risk[i] = r
        open_.append((xt, s, r))
    t["risk"] = risk
    t["ret"] = t["net_r"] * t["risk"]
    return t[t["risk"] > 0].reset_index(drop=True)


def weekly(t: pd.DataFrame, a: str, b: str) -> pd.Series:
    """Account return per week of [a, b), by exit time; empty weeks are 0."""
    weeks = pd.date_range(pd.Timestamp(a, tz="UTC"), pd.Timestamp(b, tz="UTC"), freq=BLOCK, inclusive="left")
    if t.empty:
        return pd.Series(0.0, index=weeks)
    k = weeks.searchsorted(pd.to_datetime(t["exit_time"], utc=True), side="right") - 1
    w = np.bincount(np.clip(k, 0, len(weeks) - 1), weights=t["ret"].to_numpy(), minlength=len(weeks))
    return pd.Series(w, index=weeks)


def account(t: pd.DataFrame, a: str, b: str, seed: int = 31) -> dict:
    w = weekly(t, a, b)
    x = w.to_numpy()
    rng = np.random.default_rng(seed)
    boots = x[rng.integers(0, len(x), size=(N_BOOT, len(x)))].mean(1) if len(x) else np.array([np.nan])
    eq = np.cumsum(np.r_[0.0, t.sort_values("exit_time")["ret"].to_numpy()]) if len(t) else np.zeros(1)
    dd = float(np.max(np.maximum.accumulate(1 + eq) - (1 + eq))) if len(eq) else 0.0
    se = x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else np.nan
    years = len(x) * 7 / 365.25
    return {"trades": int(len(t)), "weeks": int(len(x)), "weekly_mean": float(x.mean()) if len(x) else 0.0,
            "ci_lo": float(np.percentile(boots, 2.5)), "ci_hi": float(np.percentile(boots, 97.5)),
            "tstat": float(x.mean() / se) if se and np.isfinite(se) and se > 0 else 0.0,
            "total_return": float(x.sum()), "per_year": float(x.sum() / years) if years else 0.0,
            "max_dd": dd, "mean_r": float(t["net_r"].mean()) if len(t) else None,
            "risk_weighted_r": float((t["ret"].sum() / t["risk"].sum())) if len(t) else None,
            "avg_risk": float(t["risk"].mean()) if len(t) else None,
            "long_ret": float(t.loc[t["side"] > 0, "ret"].sum()), "short_ret": float(t.loc[t["side"] < 0, "ret"].sum())}


# --------------------------------------------------------------------------
# forecasts: section 30's frozen models, recomputed
# --------------------------------------------------------------------------
def _cfg(tf: int) -> dict:
    r = json.loads((SRC / f"tf{tf}.json").read_text())
    return {"setting": {k: r["setting"][k] for k in ("num_leaves", "min_data_in_leaf", "rounds")},
            "q_in": r["q_in"], "exit_mode": r["exit_mode"]}


def forecasts(by_tf: dict, tf: int, spans: list[tuple[str, str]], check: bool = True):
    """Walk-forward forecasts of section 30's chosen cell for tf over the spans,
    returned per coin as a Series on the decision index; VALID checked against
    section 30's recorded forecasts."""
    P = W2.prepare(by_tf, tf)
    cfg = _cfg(tf)["setting"]
    pred = {c: np.full(len(P[c]["X"]), np.nan) for c in P}
    for a, b in spans:
        p = WF.walk_forward(P, tf, cfg, a, b)
        for c in P:
            pred[c] = np.where(np.isfinite(p[c]), p[c], pred[c])
    out = {c: pd.Series(pred[c], index=P[c]["X"].index) for c in P}
    if check:
        rec = pd.read_csv(SRC / f"desired_valid_tf{tf}.csv.gz", parse_dates=["time"])
        worst = 0.0
        if set(rec["coin"]) - set(out):                  # a coin section 30 traded is missing here
            raise SystemExit(f"forecasts for {tf}m miss coins {sorted(set(rec['coin']) - set(out))}; stop and report")
        for c, g in rec.groupby("coin"):
            mine = out[c].reindex(pd.DatetimeIndex(g["time"])).to_numpy()
            d = np.abs(mine - g["pred"].to_numpy())
            worst = max(worst, float(np.nanmax(d)) if np.isfinite(d).any() else np.inf)
        if not worst <= REPRO_TOL:
            raise SystemExit(f"forecasts for {tf}m do not reproduce section 30 (max |diff| {worst:.3g}); stop and report")
    return P, out


# --------------------------------------------------------------------------
# one cell
# --------------------------------------------------------------------------
def run_cell(P, pred1, other, a, b, agree, sizing, cap, q, mode, stress=1.0):
    fr, paths = [], {}
    for c in P:
        p = pred1[c].to_numpy()
        ok = np.isfinite(p)
        des, ebar = np.full(len(p), np.nan), np.full(len(p), np.nan)
        if ok.any():
            ebar[ok] = MH.entry_bar(p[ok], q)
            des[ok] = MH.policy(p[ok], ebar[ok], mode)
        lo, hi, rows = MH._window(P, c, a, b)
        rows = rows[np.isfinite(des[rows])]
        desired = des[rows]
        if agree != "off":
            o = other[agree].get(c)
            idx = P[c]["X"].index[rows]
            if o is None or o.empty:
                ov = np.full(len(rows), np.nan)
            else:
                pos = WF.asof_positions(idx, TF_MAIN, o.index, AGREE_TF[agree])
                ov = np.where(pos >= 0, o.to_numpy()[np.maximum(pos, 0)], np.nan)
            desired = agree_filter(desired, ov)
        tgt = np.full(hi - lo, np.nan)
        tgt[P[c]["pos"][rows] - lo] = desired
        tb = P[c].get("tbars", P[c]["bars"])
        t = MH.simulate(tb.iloc[lo:hi], tgt, P[c]["atr"][lo:hi], P[c]["fund"],
                        fee=C.FEE_TAKER * stress, slip=P[c]["slip"] * stress, stop_atr=WF.STOP_ATR)
        if len(t):
            k = P[c]["X"].index.get_indexer(t["entry_time"] - pd.Timedelta(minutes=TF_MAIN))
            t["conf"] = np.where(k >= 0, np.abs(p[np.maximum(k, 0)]) / ebar[np.maximum(k, 0)], np.nan)
        fr.append(t.assign(coin=c))
        paths[c] = (desired, rows, lo, hi)
    t = pd.concat(fr, ignore_index=True)
    return size_trades(t, sizing, cap), paths


def judge(P, pred1, other, a, b, agree, sizing, cap, q, mode, min_coins=MIN_COINS):
    t, paths = run_cell(P, pred1, other, a, b, agree, sizing, cap, q, mode)
    acc = account(t, a, b)
    stress = account(run_cell(P, pred1, other, a, b, agree, sizing, cap, q, mode, stress=1.5)[0], a, b)
    timing, per, pooled = MH.control(P, paths)
    coins = {}
    for c in P:
        tc = t[t["coin"] == c]
        coins[c] = {"trades": int(len(tc)), "mean_r": float(tc["net_r"].mean()) if len(tc) else None,
                    "timing": per[c]["timing"], "shift_median": MH._q(per[c]["shifts"], 50)}
    elig = {c: x for c, x in coins.items() if x["trades"] >= MIN_COIN_TRADES}
    beat = [c for c, x in elig.items() if x["mean_r"] > 0 and x["timing"] is not None
            and x["shift_median"] is not None and x["timing"] > x["shift_median"]]
    acc.update(stress_weekly_mean=stress["weekly_mean"], timing=timing, shift_median=MH._q(pooled, 50),
               shift_p95=MH._q(pooled, 95), per_coin=coins,
               breadth={"eligible": len(elig), "beat": beat, "share": len(beat) / len(elig) if elig else 0.0},
               per_year_r={str(y): float(g["ret"].sum()) for y, g in t.groupby(pd.to_datetime(t["exit_time"]).dt.year)})
    return acc, t


def evaluate(P, pred1, other, q, mode, min_coins=MIN_COINS, keep=False) -> dict:
    a_tr, b_tr = WF.WINDOWS["train"]
    a_va, b_va = WF.WINDOWS["valid"]
    table = []
    for agree, sizing, cap in itertools.product(AGREE, SIZING, CAP):
        t, _ = run_cell(P, pred1, other, a_tr, b_tr, agree, sizing, cap, q, mode)
        acc = account(t, a_tr, b_tr)
        table.append({"agree": agree, "sizing": sizing, "cap": cap, **{k: acc[k] for k in
                      ("trades", "weekly_mean", "tstat", "per_year", "max_dd", "mean_r")}})
        print(f"TRAIN-WF {agree:>3} {sizing:>4} cap {cap}: {acc['trades']} trades, weekly {acc['weekly_mean']:+.5f}, "
              f"t {acc['tstat']:+.2f}, dd {acc['max_dd']:.3f}", flush=True)
    ok = [x for x in table if x["trades"] >= MIN_TRADES]
    best = max(ok, key=lambda x: x["tstat"]) if ok else table[0]
    v, t = judge(P, pred1, other, a_va, b_va, best["agree"], best["sizing"], best["cap"], q, mode, min_coins)
    gates = {"train_weekly_mean>0": best["weekly_mean"] > 0 and best in ok,
             f"valid_trades>={MIN_TRADES}": v["trades"] >= MIN_TRADES,
             "valid_weekly_mean>0": v["weekly_mean"] > 0,
             "valid_ci_lo>0": v["ci_lo"] > 0,
             "stress_weekly_mean>0": v["stress_weekly_mean"] > 0,
             "timing_beats_shift_p95": v["shift_p95"] is not None and v["timing"] is not None
             and v["timing"] > v["shift_p95"],
             f"coins>={min_coins}": v["breadth"]["eligible"] >= min_coins,
             f"breadth>={BREADTH_SHARE}": v["breadth"]["share"] >= BREADTH_SHARE,
             "both_legs>0": v["long_ret"] > 0 and v["short_ret"] > 0,
             f"max_dd<={MAX_DD}": v["max_dd"] <= MAX_DD}
    failed = [k for k, g in gates.items() if not g]
    res = {"chosen": {k: best[k] for k in ("agree", "sizing", "cap")}, "train_best": best, "train_table": table,
           "valid": v, "verdict": "REJECT" if failed else "PASS", "gates_failed": failed,
           "model": {"q_in": q, "exit_mode": mode}}
    if keep:
        res["_trades"] = t
    return res


# --------------------------------------------------------------------------
def run(final: bool = False) -> None:
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
    by_tf, _ = W3.load_all()
    spans = [WF.WINDOWS["train"], WF.WINDOWS["valid"]] + ([WF.WINDOWS["holdout"]] if final else [])
    other = {}
    for name, tf in AGREE_TF.items():
        P_o, other[name] = forecasts(by_tf, tf, spans)
        del P_o
    P, pred1 = forecasts(by_tf, TF_MAIN, spans)
    m = _cfg(TF_MAIN)
    if final:
        ch = res["chosen"]
        a, b = WF.WINDOWS["holdout"]
        h, t = judge(P, pred1, other, a, b, ch["agree"], ch["sizing"], ch["cap"], m["q_in"], m["exit_mode"])
        h["verdict"] = ("CONFIRMED" if h["weekly_mean"] > 0 and h["ci_lo"] > 0 and h["shift_median"] is not None
                        and h["timing"] is not None and h["timing"] > h["shift_median"]
                        and h["breadth"]["share"] >= BREADTH_SHARE else "FAILED")
        lock.write_text(json.dumps(h, indent=1, default=str))
        t.to_csv(OUT / "trades_holdout.csv.gz", index=False)
        write_report(res)
        print(json.dumps({k: h.get(k) for k in ("trades", "weekly_mean", "ci_lo", "verdict")}, indent=1))
        return
    res = evaluate(P, pred1, other, m["q_in"], m["exit_mode"], keep=True)
    res.pop("_trades").to_csv(OUT / "trades_valid.csv.gz", index=False)
    res_path.write_text(json.dumps(res, indent=1, default=str))
    write_report(res)
    print(f"\nML_PORT: chose {res['chosen']} -> {res['verdict']} failed {res['gates_failed']}")


def write_report(r: dict) -> None:
    v = r["valid"]
    f = (lambda x, d=5: "-" if x is None else f"{x:+.{d}f}")
    L = ["# Portfolio layer on section 30's 1h model (PLAN.md section 31)", "",
         "GENERATED by `src/ml_port.py`. Do not edit by hand.", "",
         f"## **{r['verdict']}** (TRAIN chose {r['chosen']}; failed: {r['gates_failed'] or 'none'})", "",
         f"- VALID {v['trades']} trades over {v['weeks']} weeks: weekly account return {f(v['weekly_mean'])}, "
         f"95% CI [{f(v['ci_lo'])}, {f(v['ci_hi'])}], t {v['tstat']:+.2f}; return per year {f(v['per_year'], 4)}, "
         f"max drawdown {v['max_dd']:.4f}",
         f"- mean R per trade {f(v['mean_r'], 4)}, risk-weighted {f(v['risk_weighted_r'], 4)}, average risk "
         f"{f(v['avg_risk'], 4)}; long {f(v['long_ret'], 4)} / short {f(v['short_ret'], 4)} (summed return)",
         f"- cost x1.5 weekly {f(v['stress_weekly_mean'])}; timing {f(v['timing'], 4)} vs shifted median "
         f"{f(v['shift_median'], 4)} / p95 {f(v['shift_p95'], 4)}; breadth {len(v['breadth']['beat'])} of "
         f"{v['breadth']['eligible']} ({v['breadth']['share']:.2f}); per year {v['per_year_r']}", "",
         "| agree | sizing | cap | TRAIN trades | weekly mean | t | per year | max DD |", "|---|---|---|---|---|---|---|---|"]
    for x in r["train_table"]:
        L.append(f"| {x['agree']} | {x['sizing']} | {x['cap']} | {x['trades']} | {f(x['weekly_mean'])} | "
                 f"{x['tstat']:+.2f} | {f(x['per_year'], 4)} | {x['max_dd']:.4f} |")
    hp = OUT / "holdout.json"
    if hp.exists():
        h = json.loads(hp.read_text())
        L += ["", f"**HOLDOUT: {h['verdict']}** - {h['trades']} trades, weekly {f(h['weekly_mean'])}, CI "
              f"[{f(h['ci_lo'])}, {f(h['ci_hi'])}], timing {f(h['timing'], 4)} vs median {f(h['shift_median'], 4)}, "
              f"breadth {h['breadth']['share']:.2f}"]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--final", action="store_true")
    run(ap.parse_args().final)


if __name__ == "__main__":
    main()
