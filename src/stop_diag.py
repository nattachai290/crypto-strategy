"""Stop diagnosis: wrong direction, or right direction and shaken out? (PLAN.md section 23)

    SYMBOL=BTCUSDT python src/stop_diag.py
    SYMBOL=ETHUSDT python src/stop_diag.py

The owner's question: do the strategies enter in the WRONG direction, or in
the RIGHT direction and then get stopped out by a fake move ("โดนลากไส้")?
This tool answers it from the VALID trade lists already on disk
(results/<SYMBOL>/eval_trades/<eval_id>_valid.csv.gz) and the price bars. It
runs no strategy, tunes nothing and never reads HOLDOUT; it only measures what
happened after each recorded entry.

For every trade, with H = the idea's max hold in bars and R = the trade's
initial stop distance (net_pnl / (r_multiple x qty), exact):
  * right_at_h   - was the close H bars after the fill on the trade's side of
                   the entry price? (direction call, stop ignored)
  * move_h       - that move in R: side x (close[fill + H - 1] - entry) / R
                   (the "no stop, hold to the time limit" gross, before costs)
  * shaken       - the trade exited on its stop AND right_at_h.
The same numbers are computed for a CONTROL: for each real trade, CONTROL_K
random fills in the same VALID window, same side, same stop as a fraction of
price, same H. Because the control has the same side mix and the same window,
market drift helps it exactly as much (BTC Exp 045 rule).

Reading (pooled over every eligible evaluation on the coin, CI from
resampling whole evaluations):
  * direction skill  = right_at_h(real) - right_at_h(control)
  * shakeout excess  = P(right_at_h | stopped)(real) - same for the control
  * no-stop gross    = mean move_h(real) - mean move_h(control)
  WRONG_DIRECTION  direction skill CI entirely below 0 (worse than random);
  SHAKEN_OUT       direction skill CI above 0 AND shakeout excess CI above 0
                   (right more often than random, and the stops throw it away);
  RIGHT_NOT_SHAKEN direction skill CI above 0, shakeout not shown;
  COIN_FLIP        otherwise: right about as often as random entries. Writes results/<SYMBOL>/s23_stop_diag/ and journal/<SYMBOL>/s23_stop_diag.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

TFS = (15, 30, 60, 240)
CONTROL_K = 20
SEED = 23
N_BOOT = 2000


def valid_window() -> tuple[pd.Timestamp, pd.Timestamp]:
    s = C.SPEC
    a = pd.Timestamp(s["valid_start"] + "-01", tz="UTC")
    b = pd.Timestamp(s["holdout_start"] + "-01", tz="UTC")
    return a, b


def trade_paths(bars: pd.DataFrame, t: pd.DataFrame, H: int) -> pd.DataFrame:
    """right_at_h, move_h (in R) and stopped for each recorded trade."""
    idx = bars.index
    o, c = bars["open"].to_numpy(float), bars["close"].to_numpy(float)
    pos = idx.get_indexer(pd.to_datetime(t["entry_time"], utc=True))
    R = (t["net_pnl"] / (t["r_multiple"] * t["qty"])).abs().to_numpy(float)
    side = t["side"].to_numpy(float)
    entry = t["entry_px"].to_numpy(float)
    end = pos + H - 1
    ok = (pos >= 0) & (end < len(c)) & np.isfinite(R) & (R > 0)
    move = np.full(len(t), np.nan)
    move[ok] = side[ok] * (c[end[ok]] - entry[ok]) / R[ok]
    return pd.DataFrame({"right": move > 0, "move_r": move, "stopped": (t["exit_reason"] == "stop").to_numpy(),
                         "side": side, "frac": R / entry, "ok": ok})


def control_paths(bars: pd.DataFrame, real: pd.DataFrame, H: int, window: tuple, k: int = CONTROL_K,
                  seed: int = SEED) -> pd.DataFrame:
    """k random fills per real trade: same side, same stop fraction, same H,
    fill at a random bar's open inside the VALID window (path must end inside it)."""
    idx = bars.index
    o, h, l, c = (bars[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    lo = int(np.searchsorted(idx, window[0]))
    hi = int(np.searchsorted(idx, window[1])) - H
    rng = np.random.default_rng(seed)
    rows = []
    for side, frac in real.loc[real["ok"], ["side", "frac"]].itertuples(index=False):
        if hi <= lo:
            break
        for j in rng.integers(lo, hi, size=k):
            e = o[j]
            d = frac * e
            stop = e - side * d
            seg_l, seg_h = l[j:j + H], h[j:j + H]
            hit = (seg_l <= stop).any() if side > 0 else (seg_h >= stop).any()
            mv = side * (c[j + H - 1] - e) / d
            rows.append((mv > 0, mv, hit, side))
    return pd.DataFrame(rows, columns=["right", "move_r", "stopped", "side"])


def _stats(df: pd.DataFrame) -> dict:
    s = df[df["stopped"]]
    return {"n": int(len(df)), "right": float(df["right"].mean()) if len(df) else np.nan,
            "move_r": float(df["move_r"].mean()) if len(df) else np.nan,
            "stop_rate": float(df["stopped"].mean()) if len(df) else np.nan,
            "right_if_stopped": float(s["right"].mean()) if len(s) else np.nan}


def eligible(ev: pd.DataFrame) -> pd.DataFrame:
    e = ev[ev["tf"].isin(TFS) & ev["verdict"].isin(["PASS", "WATCH", "REJECT"])]
    e = e[(e.get("valid_size_skips", 0).fillna(0) == 0) & (e["valid_trades"] >= 30)]
    return e.drop_duplicates("eval_id")


def diagnose(get_bars, ev: pd.DataFrame, trades_dir: Path, window: tuple) -> pd.DataFrame:
    out = []
    for r in eligible(ev).itertuples():
        f = trades_dir / f"{r.eval_id}_valid.csv.gz"
        if not f.exists():
            continue
        p = json.loads(r.chosen_params)
        H = max(1, int(round(float(p.get("max_hold_hours", 4)) * 60 / int(r.tf))))
        bars = get_bars(int(r.tf))
        t = pd.read_csv(f)
        if t.empty:
            continue
        real = trade_paths(bars, t, H)
        ctl = control_paths(bars, real, H, window)
        rs, cs = _stats(real[real["ok"]]), _stats(ctl)
        out.append({"eval_id": r.eval_id, "name": r.name, "tf": int(r.tf), "H": H, "verdict": r.verdict,
                    **{f"real_{k}": v for k, v in rs.items()}, **{f"ctl_{k}": v for k, v in cs.items()}})
        print(f"  {r.name} tf{r.tf}: right {rs['right']:.3f} vs {cs['right']:.3f} | "
              f"right-if-stopped {rs['right_if_stopped']:.3f} vs {cs['right_if_stopped']:.3f}", flush=True)
    return pd.DataFrame(out)


def summarize(per: pd.DataFrame, seed: int = SEED) -> dict:
    """Trade-weighted pooled differences, 95% CI by resampling evaluations."""
    def pooled(d: pd.DataFrame) -> tuple[float, float, float]:
        w = d["real_n"].to_numpy(float)
        ws = (d["real_n"] * d["real_stop_rate"]).to_numpy(float)
        dir_ = np.average(d["real_right"] - d["ctl_right"], weights=w)
        mv = np.average(d["real_move_r"] - d["ctl_move_r"], weights=w)
        ok = np.isfinite(d["real_right_if_stopped"] - d["ctl_right_if_stopped"]).to_numpy() & (ws > 0)
        sh = (np.average((d["real_right_if_stopped"] - d["ctl_right_if_stopped"]).to_numpy()[ok], weights=ws[ok])
              if ok.any() else np.nan)
        return dir_, sh, mv
    if per.empty:
        return {"evaluations": 0, "verdict": "NO_DATA"}
    est = pooled(per)
    rng = np.random.default_rng(seed)
    boots = np.array([pooled(per.iloc[rng.integers(0, len(per), len(per))]) for _ in range(N_BOOT)])
    ci = {k: (float(np.nanpercentile(boots[:, i], 2.5)), float(np.nanpercentile(boots[:, i], 97.5)))
          for i, k in enumerate(("direction_skill", "shakeout_excess", "no_stop_gross_excess"))}
    res = {"evaluations": int(len(per)), "trades": int(per["real_n"].sum()),
           "real_right": float(np.average(per["real_right"], weights=per["real_n"])),
           "ctl_right": float(np.average(per["ctl_right"], weights=per["real_n"])),
           "real_stop_rate": float(np.average(per["real_stop_rate"], weights=per["real_n"])),
           "direction_skill": est[0], "shakeout_excess": est[1], "no_stop_gross_excess": est[2], "ci": ci}
    if ci["direction_skill"][1] < 0:
        res["verdict"] = "WRONG_DIRECTION"
    elif ci["direction_skill"][0] > 0 and ci["shakeout_excess"][0] > 0:
        res["verdict"] = "SHAKEN_OUT"
    elif ci["direction_skill"][0] > 0:
        res["verdict"] = "RIGHT_NOT_SHAKEN"
    else:
        res["verdict"] = "COIN_FLIP"
    return res


def write_report(res: dict, per: pd.DataFrame) -> None:
    pc = lambda x: "-" if x is None or not np.isfinite(x) else f"{100 * x:.1f}%"  # noqa: E731
    pp = lambda x: "-" if x is None or not np.isfinite(x) else f"{100 * x:+.1f} pts"  # noqa: E731
    L = [f"# {C.SYMBOL} - stop diagnosis (PLAN.md section 23)", "",
         "GENERATED by `src/stop_diag.py`. Do not edit by hand.", ""]
    if res.get("verdict") == "NO_DATA":
        L.append("No eligible evaluations.")
    else:
        ci = res["ci"]
        L += [f"## **{res['verdict']}** ({res['evaluations']} evaluations, {res['trades']} VALID trades)", "",
              f"- direction right at the time limit: real {pc(res['real_right'])} vs random {pc(res['ctl_right'])}"
              f" -> skill {pp(res['direction_skill'])}, 95% CI [{pp(ci['direction_skill'][0])}, "
              f"{pp(ci['direction_skill'][1])}]",
              f"- stopped trades that would have been right at the time limit, real minus random: "
              f"{pp(res['shakeout_excess'])}, 95% CI [{pp(ci['shakeout_excess'][0])}, {pp(ci['shakeout_excess'][1])}]",
              f"- no-stop move to the time limit, real minus random: {res['no_stop_gross_excess']:+.4f} R, 95% CI "
              f"[{ci['no_stop_gross_excess'][0]:+.4f}, {ci['no_stop_gross_excess'][1]:+.4f}]",
              f"- real stop rate {pc(res['real_stop_rate'])}", "",
              "| idea | tf | H | verdict | trades | right (real / random) | right if stopped (real / random) | "
              "no-stop move R (real / random) |", "|---|---|---|---|---|---|---|---|"]
        for r in per.sort_values(["name", "tf"]).itertuples():
            L.append(f"| {r.name} | {r.tf} | {r.H} | {r.verdict} | {r.real_n} | {pc(r.real_right)} / {pc(r.ctl_right)} | "
                     f"{pc(r.real_right_if_stopped)} / {pc(r.ctl_right_if_stopped)} | "
                     f"{r.real_move_r:+.3f} / {r.ctl_move_r:+.3f} |")
    (C.JOURNAL / "s23_stop_diag.md").write_text("\n".join(L) + "\n")


def run() -> None:
    import experiment as E
    out = C.RESULTS / "s23_stop_diag"
    out.mkdir(parents=True, exist_ok=True)
    ev = pd.read_csv(C.RESULTS / "evaluations.csv")
    per = diagnose(E.get_bars, ev, C.RESULTS / "eval_trades", valid_window())
    res = summarize(per)
    per.to_csv(out / "per_evaluation.csv", index=False)
    (out / "summary.json").write_text(json.dumps(res, indent=1))
    write_report(res, per)
    print(json.dumps({k: v for k, v in res.items() if k != "ci"}, indent=1))


def main() -> None:
    argparse.ArgumentParser(description=__doc__.split("\n")[0]).parse_args()
    run()


if __name__ == "__main__":
    main()
