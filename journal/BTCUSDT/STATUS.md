# BTCUSDT — status and handoff

_Last updated: 2026-09-29, after Exp 021 (Round 3 review). Rules for agents: `AGENTS.md`.
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
> **Exp 019 (after Round 2):** Round 2's idea 022 was the first PASS; it spent the
> holdout and FAILED (−0.010 R). `baseline.py` SKILL now needs TRAIN *and* VALID
> (under that rule 022 is DRIFT), and `--final` also runs a random-entry control
> on the holdout (CONFIRMED must beat its median). **Journal numbering:** the two
> Round 2 entries headed "Exp 017" are 017b/017c; the next entry is **Exp 020**.
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
>
> **Exp 020 (Round 3) - the headline answer to the project's question.**
> 35 evaluations on "when to be in BTC", 13 `baseline.py` + 13 `benchmark.py`
> runs. **Two PASSes** - 023 (long/flat regime, 1h: valid +0.1148, CI
> [+0.014, +0.220], cost_r **0.022**, maxDD 4.8%) and 027 (multi-day pullback,
> 30m: valid +0.1967, CI [+0.025, +0.373], cost_r 0.036) - and **every
> `benchmark.py` run in the project is NO_EDGE: 20 of 20** (Exp 021 correction; Exp 020 said 21). No configuration has
> alpha and none is RISK_EDGE. **No tested timing rule beats simply holding BTC
> after costs.** 027 is DRIFT (its TRAIN sits below random entries, caught by
> the Exp 019 tightening); 023 is NO_EDGE by its own benchmark, Sharpe 1.59
> against buy & hold's 2.01 on VALID despite a sixth of its drawdown. The
> holdout was **not** spent - see the owner question in `experiments.md`
> Exp 020.
>
> **Exp 021 (review of Round 3) - owner decision: 023 does NOT go to the
> holdout.** A regime rule (`trend_state`) now needs benchmark **ALPHA** for
> `--final`; SKILL does not count for it, and `evaluate.py` enforces this.
> New verdict **`UNSIZABLE`**: any `size_skips` on TRAIN or VALID (the 1,000
> USDT account could not size a signal) turns PASS/WATCH/INCONCLUSIVE into
> UNSIZABLE. The four Round 3 4h variants (023/025/026/027@4h, 20% stops,
> sizable only below BTC 50,000) and 019@4h are UNSIZABLE, not evidence.
> Benchmark count corrected: **20/20** NO_EDGE. `tf_variants.py` now warns when
> a stop is too wide to size. **Next: Round 4.**

## Where things stand

- **Round 1 is done: 40 evaluations, 0 PASS, 5 WATCH, 29 REJECT, 6 INCONCLUSIVE.**
  Project total 58. Pre-registration and full results: `experiments.md` Exp 016.
- **Round 2 is done: 2 evaluations, 1 WATCH (DRIFT/NO_EDGE), 1 PASS whose holdout
  FAILED.** Details: `experiments.md` Exp 017.
- **Round 3 is done: 35 evaluations, 2 PASS, 11 WATCH, 19 REJECT, 3 INCONCLUSIVE.**
  Project total 96. **Answer: no timing rule beats holding BTC.** Every
  `benchmark.py` run in the project is NO_EDGE (20/20; Exp 020 said 21).
  The 4h variants are UNSIZABLE (Exp 021). Details: Exp 020, Exp 021.
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

Round 3's answer is negative and it closes the whole "when to be long BTC"
family: 96 evaluations, 20/20 NO_EDGE on the benchmark, one PASS whose holdout
failed, and two PASSes that the benchmark says are dominated by owning the asset.

Round 4 is the last round and the plan says it should look for edges that do
**not** come from BTC's direction: previous-day high/low, the opening range,
funding windows, liquidation flushes. `benchmark.py` stays the judge — a rule
that cannot beat holding BTC is not worth a strategy card however good its own
mean R looks.

Three things to raise with the owner 🛑:
1. **Whether to spend the holdout on 023** (PASS + SKILL but NO_EDGE). The plan
   sends only ALPHA + PASS to the holdout; the benchmark says NO_EDGE. My
   recommendation is not to spend it, and I have not.
2. Whether partial take-profit or scale-in is worth an engine proposal — Round 2
   measured that exit management redistributes outcomes but adds none, so the
   answer looks like no, and I would not bring it again without evidence.
3. Whether to run Round 4 at all, or stop and write `FINAL_REPORT.md` now: 96
   evaluations is already a complete answer to the question the project was
   asked.

Never build a weekday or session-hour filter, never retry mean reversion,
squeeze→expansion, funding crowding, `taker_flow`/`funding_not_crowded`, any
short-only breakout, or any long Donchian/pullback entry on 15m-30m.
