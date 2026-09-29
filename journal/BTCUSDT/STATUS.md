# BTCUSDT — status and handoff

_Last updated: 2026-09-29, after Exp 025 (Round 5 review). Rules for agents:
`AGENTS.md`. Research plan: `docs/research/PLAN.md` (all five rounds done)._

> **Owner decision (2026-09-29): trading only.** The project studies trades that earn from price moves. Funding carry, basis / cash-and-carry and any other strategy that earns the funding fee are **out of scope**: do not propose, build or test them. Funding may still be used as a *signal* or paid as a cost.
>
> **Exp 025 (review of Round 5):** `recipe()` now refuses a trigger that
> returns anything but one -1/0/+1 array (and a filter that is not
> `(long_ok, short_ok)`), and `test_engine.py` checks every block, so the
> `opening_range` tuple bug cannot recur silently. `month_turn_fade` now uses
> the real month length (037's recorded rows predate the fix). Corrections to
> Exp 024 are in `experiments.md` Exp 025. The next direction is the owner's.
>
> **Exp 024 — Round 5 is done, the plan is finished, and the answer did not
> change.** 42 evaluations: 1 PASS, 9 WATCH, 17 REJECT, 15 INCONCLUSIVE. Project
> total **173**.
>
> 1. **A Round 4 bug: `opening_range` traded long-only for all of Exp 022.** It
>    returned a `(long, short)` tuple where every trigger returns one signed
>    array, so `recipe()` read "either side fired" as LONG — 798 valid long
>    trades, **0 short**. Fixed to a single `_side()` call; the corrected idea
>    (038) can now trade both sides. The control verdicts on 029 (DRIFT,
>    NO_EDGE) still stand and the round's conclusion is unchanged, but 029 was
>    never a both-sided result. **Check after adding any block: every trigger
>    returns a 1-D array of 0/+1/-1, every filter returns two boolean arrays.**
> 2. **`--mode time` is the fix for the cost problem of multi-day holds (Exp 025:
>    not for short holds, which still pay ≈ 0.11% of price per trade).**
>    With 4h source files and `--mode time`, `cost_r` is **0.016–0.023 R on all
>    seven timeframes** instead of chart mode's 0.505 R (1m) to 0.019 R (4h) — a
>    26:1 spread becomes 1.4:1. Use it for anything with a multi-day hold.
> 3. **038 (00:00 opening-range break, 4h) was the project's first and only
>    PASS + ALPHA** — valid 155 trades, `gross_r` +0.197 (**+0.99% of price per
>    trade** against a 0.11% cost), 77 long / 78 short, **beta +0.01**, alpha
>    +10.2%/yr CI [+1.4, +18.3]. **It FAILED the holdout**: 135 trades,
>    `gross_r` **−0.090**, mean R −0.1118, CAGR −6.4%. The gross edge was
>    2023-24. **The holdout is now used three times and has failed three times.**
> 4. **DRIFT and ALPHA at the same time is the project's sharpest result.** 038's
>    entry has no timing skill (TRAIN −0.005, below random entries' 95th pct
>    +0.107) and its return is not BTC's direction (beta 0.01) — yet it made
>    money on VALID. The only remaining mechanism is *being in the market with a
>    cheap cost structure*, which is an exposure decision, not an edge.
> 5. **Mean reversion is refuted at a real horizon too.** 034 (z-score over 5-10
>    days) had the best reversion gross measured here (+0.32% of price vs 0.108%
>    cost) and went to VALID at **−0.098**, REJECT at all seven timeframes.
> 6. **Funding carry (033) is INCONCLUSIVE, not refuted** — the one hypothesis
>    left untested. A 96h hold plus a 0.015%-per-8h funding threshold cannot reach 100
>    VALID trades. It earns from funding rather than from price, and measuring it
>    needs a different instrument, not another idea file.
> 7. **Turn-of-month fade (037, my own idea) is unmeasurable in this design**,
>    not rejected: a 5-day calendar window and a 96h hold leave under 30 VALID
>    trades.
>
> **Nothing in this project is a profitable strategy and the holdout has never
> confirmed anything.** Read `journal/BTCUSDT/FINAL_REPORT.md` §7.

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
- **Round 4 is done: 35 evaluations, 1 PASS, 1 WATCH, 33 REJECT.** Four new
  Level 2 blocks built for it (`prev_day_break`, `opening_range`, `keltner_break`,
  `flush`) plus the `funding_window` filter. The round's PASS (029 opening range
  at 4h, valid +0.1131, CI [+0.006, +0.223]) is **DRIFT** and NO_EDGE, so
  `--final` refused it. `flush` failed on **gross** in both follow and fade
  modes, which closes the liquidation-cascade family. Details: Exp 022.
- **Round 5 is done: 42 evaluations, 1 PASS, 9 WATCH, 17 REJECT, 15
  INCONCLUSIVE.** 4h source files with `--mode time` variants, 4-7% stops,
  48-120h holds, both directions, no directional filter. The design worked
  (`cost_r` flat at 0.016-0.023 R on all seven timeframes) and the answer did
  not: the round's PASS was the project's first PASS + ALPHA (beta +0.01, alpha
  +10.2%/yr) and it **FAILED the holdout with a negative gross**. Details:
  `experiments.md` Exp 024.
- 🏁 **The plan is complete. Read `journal/BTCUSDT/FINAL_REPORT.md`.** Project
  total **173 evaluations**, 136 idea files, all 7 native timeframes. 6 rows ever
  read PASS, **0 CONFIRMED**, holdout used three times and FAILED all three. The
  answer: **no tested technique on BTCUSDT at VIP0 costs has an edge that
  survives a random-entry control and a buy-and-hold benchmark.**
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
- **Use `tf_variants.py --mode time` for anything with a multi-day hold**
  (Exp 024). It keeps the stop's % of price and the hold's hours constant across
  timeframes, so `cost_r` is comparable and a fine entry clock can be tested at
  all. Chart mode rescales the stop and makes 1m variants lose on arithmetic
  (0.505 R) rather than on the hypothesis.
- **A big gross-to-cost ratio is not protection** (Exp 024). 038 had gross
  +0.99% of price against 0.11% cost, a 9:1 ratio, and its `gross_r` went
  +0.197 on VALID to **−0.090** on the holdout. Compare per-year splits before
  believing a gross edge.
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

**All five rounds of `PLAN.md` are done.** 173 evaluations, 6 rows ever read
PASS, 0 CONFIRMED, holdout spent three times and failed three times. The
deliverable is `journal/BTCUSDT/FINAL_REPORT.md` and its §8 lists what would
count as new information. Per `PLAN.md` §7 the remaining choices are the
owner's, and none of them is another round on BTCUSDT.

**Owner decision (2026-09-29): trading only.** The project studies trades that earn from price moves. Funding carry, basis / cash-and-carry and any other strategy that earns the funding fee are **out of scope**: do not propose, build or test them. Funding may still be used as a *signal* or paid as a cost. Item 1 below is therefore closed.

Three things to raise with the owner 🛑:
1. **Funding carry (033) is the one hypothesis untested rather than refuted.**
   It earns from funding instead of from price, and it cannot be measured in
   this engine because a 96h hold plus a 0.015%-per-8h threshold cannot reach 100 VALID
   trades. Measuring it means a different instrument — a rolling funding
   position held for weeks, with the stop and the time stop removed because
   carry is not a price trade. That is a Level 3 proposal and needs approval.
2. **A different coin, or a different market.** Every finding here is specific
   to BTCUSDT at VIP0 costs, and BTC is the most arbitraged market in
   existence. The harness transfers unchanged. Adding a symbol to
   `SYMBOL_SPECS` is also a Level 3 change and needs the owner's approval.
3. **Whether to continue at all on this market.** 173 evaluations is a complete
   answer, and the evidence is consistent rather than inconclusive: cost is the
   first-order term and it is a design choice; with cost solved, several
   both-sided structures produce a positive gross of ~1% of price per trade and
   **none of them has timing skill**, so the gross belongs to the period and not
   to the entry.

Never build a weekday or session-hour filter, never retry mean reversion,
squeeze→expansion, funding crowding, `taker_flow`/`funding_not_crowded`, any
short-only breakout, or any long Donchian/pullback entry on 15m-30m.

**Exp 024 update to that ban.** Exp 016's mean-reversion and funding-crowding
bans were measured at ≤ 16h holds, where the gross move was under the cost.
Round 5 retested both at the horizon where that objection does not apply and
both are now closed for real: multi-day mean reversion (034) is REJECT at all
seven timeframes despite a 3:1 gross-to-cost ratio, and funding carry (033) is
INCONCLUSIVE because the sample cannot be built. Turn-of-month fade (037) is
unmeasurable in this design. **Do not add a sixth round on BTCUSDT.**
