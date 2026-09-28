# BTCUSDT — status and handoff

_Last updated: 2026-09-28, after Exp 012. Rules for agents: `AGENTS.md`._

> **How research is done from Exp 011 on:** write an idea file in `ideas/`,
> run `python src/evaluate.py ideas/<file>.json`, follow the verdict
> (AGENTS.md §1). Ideas to try: `docs/research/TECHNIQUES.md` §6. Every
> evaluation so far: `journal/BTCUSDT/evaluations.md`.

> **Run with `--workers 1` on Windows.** `evaluate.py` assumes `fork`; Windows
> spawns, the child processes get an empty `_G`, and every combo dies with
> `KeyError: 'bars'`. Known platform bug, not patched (AGENTS.md §5).

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

## Best candidate so far (Exp 012, idea 010, eval 70fb497bcf) — WATCH

15m, `donchian_break(48)` + `htf_trend(50,4)` + `adx_min(20)`, **short only**,
`pct` stop 2.0%, no TP, ATR trail 1.5R / 2.5 ATR, 8h hold, post-only @ 0.1 ATR.

| split | trades | gross_r | cost_r | mean R | 95% CI | CAGR | maxDD |
|---|---|---|---|---|---|---|---|
| train 2020-2022 | 631 | +0.140 | 0.056 | +0.0839 | | | 12.1% |
| valid 2023-2024 | 219 | +0.153 | 0.068 | +0.0850 | [−0.030, +0.186] | +6.2% | 8.5% |
| valid ×1.5 cost | | | | +0.0736 | | | |

Fails **one** gate: `valid_ci_lo > 0`. HOLDOUT 2025-01..2026-08 is still
**completely unused** — nothing has passed, and only a PASS may spend it.
Not a profitable strategy; a candidate that has not been proven.

**Exp 013 weakened this case rather than strengthening it.** Three neighbouring
hypotheses all failed to move it, and one of them is direct evidence against a
general explanation: a Supertrend short entry on the same trades and the same
costs gives train mean R **−0.0212 with 0% of combos positive** (vs **+0.0839
with 100%** for the Donchian version). Funding-crowding and taker-flow filters
are inert at any threshold that keeps ~100 trades. So the effect is specific to
the 12h Donchian break, short, in a downtrend — and it is **unexplained**. Treat
it as a candidate, never as an edge. See Exp 013 in `experiments.md`.

## What is actually settled (reusable, any symbol)

- **A stop must be a price distance, not a volatility multiple.** `cost_r =
  round_trip_cost / stop_pct`. The same 3.0x ATR was 1.28% of price in
  2020-22 and 0.78% in 2023-24, moving cost_r 0.109 → 0.179 across a single
  configuration. Use `"stop": {"type": "pct", ...}`.
- **`gross_r` is not comparable across stop widths** and must never be read as
  "edge" on its own. A narrow ATR stop inflates R and produces large gross_r
  *because* it stops out most of the trades.
- **Post-only entry is worth ~+0.015 R** at a 92% fill rate (cost_r 0.086 →
  0.068), confirmed on native data. The 8% unfilled signals are mildly
  adverse-selected.
- **The long side of intraday BTCUSDT has produced nothing** in 16 evaluations:
  continuation negative, mean reversion gross_r ≈ +0.02, long-only trend
  +0.0015 on train.
- **Lower timeframes no longer carry a cost penalty** (a `pct` stop makes
  cost_r timeframe-independent) — and 5m still did not produce more trades or
  better mean R than 15m.

## Which result files can be trusted

Exp 010 found that every experiment before it (003–009) ran on bars shifted
one window into the past. The pipeline now loads native Binance files only.
Status of each file in `results/BTCUSDT/`:

| File | Experiment | Data | Trust |
|---|---|---|---|
| `definitive_oos.csv` | 007 / 010 | fixed | ✅ current headline |
| `round3_maker.csv` | 008 / 010 | fixed | ✅ |
| `sweep_train.csv`, `sweep_test.csv`, `sweep_merged.csv` | 003 | shifted | ⚠️ stale — rerun |
| `results.csv` | early baseline | shifted | ⚠️ stale |
| `cost_lab.csv` | 004 | shifted | ⚠️ stale (mechanism still valid) |
| `round2_stopwidth_train.csv`, `_test.csv` | 004b | shifted | ⚠️ stale |
| `ml_walkforward_15m*.csv` | 006 | shifted | ⚠️ stale |
| `final_eval_15m_s2.0.csv` | 007 | shifted | ⚠️ stale |
| `round4_holdperiod.csv` | 009 | shifted | ⚠️ stale |
| `report_best.json` → `report.html` | 007 best (154 trades, +0.038 R) | shifted | ⚠️ stale — report shows pre-fix numbers |
| `ledger.csv` / `journal/BTCUSDT/ledger.md` | all | **mixed** | ⚠️ contains both pre- and post-fix rows without a flag |

(Trust status inferred by matching file contents against the numbers in the
journal; verify before relying on it.)

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

## Suggested next steps (in order)

1. Run the start-of-session checklist in `AGENTS.md` §0, with
   `--workers 1` on Windows (see the top of this file).
2. Do **not** grind more variants of idea 010. Exp 012 showed why: raising
   mean R always cut the trade count, and PASS needs mean R > 1.568/sqrt(n),
   so precision got worse, not better. A genuinely different mechanism is
   needed, not a better parameter.
3. Untested backlog items that the Exp 012–013 findings now make interesting:
   idea 7 trend pullback on the short side (`pullback` + `trend_ema`), since
   every short idea so far has been a breakout; and idea 13 long-vs-short on
   the Donchian entry with a `pct` stop, to check whether the short/long
   asymmetry of idea 007 holds on native data. Use a `pct` stop in both.
   **Do not** re-run mean reversion or funding crowding: ideas 003, 014 and 016
   have now answered them.
4. The open question worth more than another sweep: idea 010's 82% time-exit
   rate and its unexplained nature. If the answer turns out to be "BTC drifts
   down over 8 hours", that is a statement about the asset, not an edge, and it
   should be recorded as such rather than traded.
5. Housekeeping, lower priority: the stale Exp 003–009 result files and the
   ledger `data_version` column (see above).
