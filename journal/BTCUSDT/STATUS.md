# BTCUSDT — status and handoff

_Last updated: 2026-09-29, after Exp 014. Rules for agents: `AGENTS.md`._

> 🛑 # READ THIS FIRST — the engine is WRONG for short trades (Exp 014)
>
> `src/backtest.py` `close_position()` computes realised PnL as
> `pos_qty * (px_adj - pos_entry)` **without `pos_side`**. For a short that
> inverts the sign of the P&L. Entry slippage, stop/target placement, funding
> and the mark-to-market equity line all carry the sign correctly, so this is an
> oversight in one place, not a convention.
>
> **Consequence: every evaluation that traded the short side is wrong.** 16 of
> the 18 evaluations on record did, and 13 of them have the sign of their edge
> flipped. The best candidate of Exp 012-013 (idea 010, WATCH at +0.085 R) is
> really **−0.1721 R**, CI [−0.274, −0.057] — significantly *losing*.
>
> The trade *lists* are still valid (entry/exit decisions never used the P&L),
> and a short trade's true R is recoverable exactly from them:
> `r_true = -r_reported - 2*(fees - funding)/(qty*stop_dist)`.
>
> `test_engine.py` passes and cannot catch this: its hand-computed test is a
> long, and the "independent" reference implementation at `test_engine.py:100`
> contains the identical wrong line, so the differential test only proves the
> two agree.
>
> **The fix is a Level 3 change and is waiting on the owner. Do not run
> `evaluate.py` again until it is decided — every new number would be built on
> a wrong engine.** Full evidence and the corrected table for all 18
> evaluations: `experiments.md`, Exp 014.

> **How research is done from Exp 011 on:** write an idea file in `ideas/`,
> run `python src/evaluate.py ideas/<file>.json`, follow the verdict
> (AGENTS.md §1). Ideas to try: `docs/research/TECHNIQUES.md` §6. Every
> evaluation so far: `journal/BTCUSDT/evaluations.md`.

> **Research plan:** `docs/research/PLAN.md` (Rounds 1–4). Native 1h and 4h data
> are now available (7 timeframes in total), and every idea is run on all of them via
> `src/tf_variants.py`. The Windows
> `--workers` crash is fixed. `evaluate.py` now also refuses a 4th evaluation
> of the same idea structure, so idea 010's structure is closed, and flags
> results identical to an earlier one as `DUPLICATE`.

> **New stop type: `{"type": "pct", "pct": 0.02, "min_atr": .., "max_atr": ..}`.**
> A stop as a fraction of PRICE, not a multiple of ATR. See Exp 012 — this is
> now the default choice for any new idea, because an ATR multiple makes
> `cost_r` a function of the volatility regime.

## One-paragraph summary

Intraday BTCUSDT USDT-M perpetual research on Binance public data
(2020-01 .. 2026-08), 100 USDT account, 1% risk per trade, VIP0 taker costs.
Across 106+ configurations (hand-written rules and an ML filter on top of
them), **no configuration has a 95% CI on expectancy that excludes zero.**
The one robust finding is that **stop width dominates**: `cost_r =
round_trip_cost / stop_distance`, so wider stops cut cost per R roughly
linearly while the gross edge barely moves. Holding for the 1–4 h the brief
asked for makes every configuration negative (Exp 009): any marginal edge
needs 6–18 h holds, i.e. it is not day trading.

## Current headline (post-fix, Exp 010)

Definitive walk-forward, 15m, 9 folds (2022-01 .. 2026-08), native Binance bars:

| stop scale | method | thr | trades | gross_r | cost_r | net R | 95% CI | CAGR |
|---|---|---|---|---|---|---|---|---|
| 1.0 | reg | 0.10 | 767 | +0.020 | 0.149 | -0.129 | [-0.196, -0.063] | -17.0% |
| 2.0 | reg | 0.00 | 883 | +0.067 | 0.085 | -0.018 | [-0.066, +0.030] | -3.2% |
| 5.0 | reg | 0.00 | 289 | +0.060 | 0.050 | +0.009 | [-0.046, +0.063] | +0.7% |
| 5.0 | clf | 0.10 | 72 | +0.101 | 0.050 | +0.051 | [-0.065, +0.168] | +0.9% |

Post-only entry (taker exit) improves net R by +0.01..+0.10 but no CI
excludes zero.

## Best candidate so far (Exp 012, idea 010) — **WITHDRAWN, see Exp 014**

~~15m, `donchian_break(48)` + `htf_trend(50,4)` + `adx_min(20)`, **short only**,
`pct` stop 2.0%, no TP, ATR trail 1.5R / 2.5 ATR, 8h hold, post-only @ 0.1 ATR.~~

**This is not a candidate. The engine inverted every short trade's P&L (Exp 014).**
Its reported valid +0.0850 R is really **−0.1721 R**, CI [−0.274, −0.057]. Its TRAIN
parameter selection was made on inverted expectancy too, so nothing about it survives.
The same applies to ideas 001, 002, 003, 004, 005, 007, 008, 009, 011, 012, 013, 014,
`example_trend_breakout` and `example_range_reversion`.

The **only** evaluations that stand as recorded are the two that never took a short:

| eval_id | idea | n valid | mean R | 95% CI | verdict |
|---|---|---|---|---|---|
| c208dafd61 | 006 long-only trend, 30m EMA cross | 42 | +0.2437 | [−0.110, +0.645] | INCONCLUSIVE (too few) |
| dc08ab8828 | 016 long mean reversion, 15m | 74 | −0.0614 | [−0.279, +0.164] | REJECT |

Idea 006 is now the most interesting number in the project and the natural starting
point once the engine is fixed — but 42 validation trades is far too few, and its TRAIN
mean R was +0.0015, so it is a lead, not a result.

**Exp 013's comparison was also void** (both legs were inverted): a Supertrend
short on the same trades gave TRAIN −0.0212 with 0% of combos positive, but every
number in that comparison was an inverted P&L, so it carried no information.

## What is actually settled (reusable, any symbol)

These survive Exp 014 because they are about the cost side of a trade, not the
sign of its P&L.

- **A stop must be a price distance, not a volatility multiple.** `cost_r =
  round_trip_cost / stop_pct`. The same 3.0x ATR was 1.28% of price in
  2020-22 and 0.78% in 2023-24, moving cost_r 0.109 → 0.179 across a single
  configuration. Use `"stop": {"type": "pct", ...}`.
- **`gross_r` is not comparable across stop widths** and must never be read as
  "edge" on its own. A narrow ATR stop inflates R and produces large gross_r
  *because* it stops out most of the trades.
- **Post-only entry cuts the round trip from 0.14% to 0.09%** of price
  (measured in Exp 008/010), at a ~92% fill rate; the unfilled signals are
  mildly adverse-selected. The per-trade saving is real; the "+0.015 R" figure
  in Exp 012 was measured on inverted P&L and should be re-measured.
- **Lower timeframes no longer carry a cost penalty** (a `pct` stop makes
  cost_r timeframe-independent). The 5m comparison that "failed" was on
  inverted P&L and should be re-run.

## Which result files can be trusted

- `results/BTCUSDT/eval_trades/*.csv.gz`: the trade *lists* are valid — entry
  and exit decisions never used the P&L. A short trade's true R is recoverable
  exactly: `r_true = -r_reported - 2*(fees - funding)/(qty*stop_dist)`.
- `results/BTCUSDT/evaluations.csv` and `holdout_log.csv`: native data and the
  Exp 011 exit fixes are fine, but **every row that traded the short side has a
  wrong mean R, wrong CI, wrong CAGR and wrong verdict.** Only the two long-only
  rows stand. Do not edit this file (AGENTS.md rule 4); the corrected table is
  in `experiments.md` Exp 014.
- `results/BTCUSDT/legacy/`: Exp 003–010 outputs. Mostly stale (shifted data)
  and, where they traded shorts, affected by the same bug. A per-file trust
  table is in `results/BTCUSDT/legacy/README.md`.

## Known issues / loose ends

0. **Exit-management results before Exp 011 are biased** (break-even /
   trailing bugs, now fixed). Any `be_at` / `trail_*` numbers in Exp 003
   files are too pessimistic.

1. **Stale results.** Exp 003–006 and 009 have not been re-run on native bars.
2. **Ledger has no data-version column.** Pre- and post-fix rows for Exp 008
   sit side by side (duplicate configs with different numbers). Add a
   `data_version` (`shifted` / `native`) column in `src/ledger.py`.
3. **`report.html` / `report_best.json` are pre-fix.** `src/report_data.py`
   hard-codes `BEST = reg 0.10 / stop 5.0`; that is no longer the best.
4. **Exp 009 status says "running"** in the journal but its result and verdict
   are written. The journal is append-only, so note completion in Exp 011
   rather than editing it.
5. **Data is not in git.** Neither `data/raw/BTCUSDT/*.zip` (~240 MB, 480 files)
   nor `data/cache/BTCUSDT/*.parquet` is committed. After cloning run
   `python src/datafeed.py`: it downloads only the months missing from
   `data/raw/BTCUSDT/` (checksum-verified, limited to `DATA_START..DATA_END`), builds
   the parquet cache and runs `validate()`. Needs network access to
   `data.binance.vision` / its S3 bucket. (The zips still exist in old git
   history, so `.git` stays large unless history is rewritten.)
6. `SESSION_START_HOUR=0 / SESSION_END_HOUR=24` with `FLAT_AT_SESSION_END=True`
   — the session filter is effectively off; holding limits come from each
   strategy's `max_hold`.
7. 🛑 **The short-side P&L sign bug (Exp 014) is still unfixed and is waiting
   on the owner.** It is a Level 3 change to `src/backtest.py`
   (AGENTS.md §5, PLAN.md §9).

## Suggested next steps (in order)

1. 🛑 **Fix the engine first.** Nothing else is worth doing until
   `close_position()` carries `pos_side`, and until `test_engine.py` has a
   test that a long and a short on the same bar series produce exactly
   opposite P&Ls. Owner approval required.
2. Re-run the two surviving long-only ideas (006, 016) to confirm the
   corrected engine reproduces their numbers — that is the acceptance test for
   the fix, and 006 (+0.2437 on 42 valid trades) is the only lead left.
3. **Revise `docs/research/PLAN.md` before starting Round 1.** §2 of the plan
   rests on two statements that Exp 014 falsified: "the short side is the
   only positive signal" (it is the only side that loses significantly) and
   "no new long-only ideas in Rounds 1–2". The research direction is now the
   opposite of what the plan says.
4. Re-measure, on the fixed engine, the two cost findings that survive:
   post-only's per-trade benefit, and the 5m-vs-15m comparison. Both were
   reported as differences between inverted P&Ls.
5. Housekeeping, lower priority: the stale Exp 003–009 result files and the
   ledger `data_version` column (see above).
