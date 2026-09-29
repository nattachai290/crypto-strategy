# BTCUSDT — status and handoff

_Last updated: 2026-09-29, after Exp 017 (random-entry baseline). Rules for agents: `AGENTS.md`.
Research plan: `docs/research/PLAN.md`._

> **Exp 017 — read before anything below.** All 5 Round 1 WATCHes (018@30m,
> 018@1h, 019@30m, 019@1h, 017@1h) are **DRIFT**: random long entries inside
> the same trend filters, with the same exits, earn about the same (median
> +0.05..+0.10 R on VALID, and 25–80% of random runs match or beat the idea).
> The profits came from being long while BTC trended up in 2023–24, not from
> the entries. Every WATCH/PASS must now pass `src/baseline.py` (SKILL), and
> `evaluate.py --final` refuses without it. Details: `experiments.md` Exp 017,
> `journal/BTCUSDT/baselines.md`.
>
> **Exp 018:** Round 3 (PLAN.md) now asks "when to be long BTC" and judges ideas
> against **buy & hold** with `src/benchmark.py` (alpha, Sharpe, drawdown).
> 018@30m and 019@1h: alpha ≈ 0, Sharpe below buy & hold → NO_EDGE.
>
> **STOP — the only PASS in 61 evaluations failed its holdout.** Idea 022
> (018@30m's entry, risk side) changed one thing: the stop from 2.83% of price
> to **1.0%**. That passed every VALID gate — 258 trades, gross +0.334,
> cost 0.106, mean R **+0.2276**, CI [+0.002, +0.468], CAGR +30.5%, maxDD 12.7%
> — and `baseline.py` said **SKILL** (0% of random runs beat it). On the locked
> HOLDOUT 2025-01..2026-08: **−0.0102 R**, CI [−0.202, +0.199], gross
> **+0.098** against cost 0.108. **FAILED**, holdout spent, and the structure is
> also at `EVAL_MAX_VERSIONS`. **Do not make a copy of it for another try.**
> The mechanism is understood: a 1% stop makes the R unit 2.8x smaller, so the
> same price move scores 2.8x more R and `gross_r` went 0.145 → 0.334 without
> any new information. VALID was carried by 2023 (+0.3496) over 2024 (+0.1355),
> and a CI lower bound of +0.0023 is indistinguishable from zero. See
> `experiments.md` Exp 017.

## Where things stand

- **Round 1 is done: 40 evaluations, 0 PASS, 5 WATCH, 29 REJECT, 6 INCONCLUSIVE.**
  Project total 58. Pre-registration and full results: `experiments.md` Exp 016.
- **Round 2 is done: 2 evaluations, 1 WATCH (DRIFT/NO_EDGE), 1 PASS whose holdout
  FAILED.** Project total 61. Details: `experiments.md` Exp 017.
- **The cost finding holds and is the most reusable thing here.** Every long
  structure tested is negative at 1m/3m/5m and positive at 30m/1h/4h, on TRAIN
  as well as on VALID, for two different entries. The cause is measured, not
  guessed:
  `cost_r` is **0.505 R on 1m** and **0.019 R on 4h** for the same 0.09% round
  trip, because `tf_variants` chart mode scales the `pct` stop by sqrt(tf/15).
  A low-timeframe REJECT in this project is that arithmetic, not a verdict on
  the hypothesis.

- **The engine is fixed (Exp 015).** Two defects were found and repaired:
  1. **Short P&L had the wrong sign** (found by the agent in Exp 014). Every
     short trade in the project's history was booked inverted.
  2. **A 100 USDT account couldn't size most trades** at BTC's 0.001 qty step
     once BTC was above ~50k, so trades were silently skipped, and skipped
     *more* as a strategy lost money. `evaluate.py` now uses a 1,000 USDT
     research account (`C.EVAL_EQUITY`, owner-approved; still 1% risk per
     trade), and the engine reports `size_skips` (0 in every Round 1 report).
- **All 18 earlier ideas were re-evaluated** on the fixed engine:
  **0 PASS, 0 WATCH, 16 REJECT, 2 INCONCLUSIVE.** The old records are kept,
  unchanged, in `results/BTCUSDT/legacy/pre_signfix/`.
- **HOLDOUT 2025-01..2026-08:** used once only, by `example_trend_breakout`
  (the lock test in Exp 011). Every other config's holdout is untouched.

## What the corrected results say (Exp 015)

| finding | evidence |
|---|---|
| **Shorting breakouts loses, significantly.** All 7 short-only ideas (008–012, 014, 015) are negative on VALID; 6 of 7 have the whole 95% CI below zero | e.g. 010: valid −0.120 R, CI [−0.206, −0.027], 339 trades |
| When TRAIN may choose the direction, it now **picks long** | 007: direction grid → long; train −0.031, valid +0.051 (418 trades) |
| **The only leads** (none passes) | **005** session-open range break, both sides: train **+0.079**, valid **+0.067** on 390 trades, CI [−0.079, +0.214]; fails the ×1.5 cost gate (−0.002). **006** long-only 30m EMA cross: valid +0.136 on 52 trades (too few), train +0.002 |
| Mean reversion (long 016, example range reversion) | negative on VALID |
| Squeeze → expansion (004, 013) | negative on VALID |

## What is settled (reusable, any symbol)

- **A stop must be a price distance, not an ATR multiple.** `cost_r =
  round_trip_cost / stop_pct`; an ATR stop makes cost_r follow the
  volatility regime (Exp 012). Use `"stop": {"type": "pct", ...}`.
- **Never compare `gross_r` across stop widths.** Compare net mean R.
- **Post-only entry** cuts the round trip from 0.14% to 0.09% of price at
  80–95% fill. The per-idea benefit in R must be re-measured on the fixed engine.
- **Trade count decides whether anything can PASS**: mean R must exceed
  ≈ 1.568/√n (PLAN.md §2a). Design ideas for ≥ 300 valid trades.
- **The research account must be able to size every trade**; check
  `size_skips` = 0 in every evaluation report.

## Best configuration so far (Exp 016, idea 018 at 30m) — WATCH

30m, `donchian_break(24)` + `htf_trend(50,4)` + `adx_min(20)`, **long only**,
`pct` stop 2.83% (ATR clamp 1.5–8.0), no TP, ATR trail armed 1.5R trailing
2.5 ATR, 24h time stop, post-only entry at 0.1 ATR.

| split | trades | gross_r | cost_r | mean R | 95% CI | CAGR | maxDD |
|---|---|---|---|---|---|---|---|
| train 2020-2022 | 347 | | | +0.0612 | | | |
| valid 2023-2024 | 234 | +0.1451 | 0.0427 | **+0.1024** | [−0.031, +0.243] | +11.5% | 9.8% |
| valid ×1.5 cost | | | | +0.0849 | | | |

Fails **exactly one** gate, `valid_ci_lo > 0`, and misses it by 0.0001: PASS at
n=234 needs mean R > 1.568/√234 = 0.1025. Win 48.3%, PF 1.28, `size_skips` 0.
Neighbouring timeframes agree (1h: train +0.099 / valid +0.110; 4h: +0.058 /
+0.532 but on 37 trades), which is the robustness test the plan asks for.
**Not a strategy, and nothing here has seen the holdout.** Its exits are inert
— TP 0%, time exit 69%, average hold 20.8h — which is what Round 2 studies.

## Which files can be trusted

| file | status |
|---|---|
| `results/BTCUSDT/evaluations.csv`, `eval_trades/`, `journal/BTCUSDT/evaluations.md` | ✅ fixed engine, native data, 1,000 USDT research account |
| `results/BTCUSDT/holdout_log.csv` | ✅ (one old row: the example's holdout, consumed under the old engine; the lock still applies) |
| `results/BTCUSDT/legacy/pre_signfix/` | ❌ Exp 011–014 records: short P&L inverted and 100 USDT sizing. History only |
| `results/BTCUSDT/legacy/*` (Exp 003–010) | ❌ shifted data, short sign bug, and 100 USDT sizing. History only |
| `journal/BTCUSDT/experiments.md` Exp 003–014 | the reasoning is history; **any number involving shorts before Exp 015 is wrong** |

## Known issues (low priority)

1. The legacy scripts (`sweep.py`, `run_ml.py`, `definitive.py`, …) still size
   with the 100 USDT `INITIAL_EQUITY`. Don't use them for new research; use
   `evaluate.py`.
2. `report.html` is pre-fix history.
3. Data is not in git: run `python src/datafeed.py` after cloning (≈ 3 min,
   needs `data.binance.vision`).

## Next step

**Round 2 is next** (`PLAN.md` §4): two exit-only evaluations on idea 018 at
30m, grids as the plan specifies, entry frozen. The diagnosis to act on is that
the exits are inert — `trail_at` 1.5R with a 2.83% stop needs a 4.2% move, so
the TP never triggers and 69% of trades are closed by a 24h clock, which means
its +0.102 R is measuring drift rather than managing a trade.

Then Round 3 (swing horizons, written at 1h) and Round 4 (new blocks). Exp 016
adds three instructions for those rounds:

1. Write swing ideas at **1h, not 15m** — every long structure is negative
   below 30m and the reason is `cost_r`, which is 0.505 R on 1m.
2. Re-test 005's long leg as its own idea **keeping the `volume_spike` filter
   and the 8-hour range**. Its gross edge of +0.309 R is the largest in the
   project and idea 017 destroyed it by loosening the entry.
3. Never build a weekday or session-hour filter, never retry mean reversion,
   squeeze→expansion, funding crowding, `taker_flow`/`funding_not_crowded`, or
   any short-only breakout.
