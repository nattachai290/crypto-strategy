# BTCUSDT — status and handoff

_Last updated: 2026-09-27, after Exp 011. Rules for agents: `AGENTS.md`._

> **How research is done from Exp 011 on:** write an idea file in `ideas/`,
> run `python src/evaluate.py ideas/<file>.json`, follow the verdict
> (AGENTS.md §1). Ideas to try: `docs/research/TECHNIQUES.md` §6. Every
> evaluation so far: `journal/BTCUSDT/evaluations.md`.

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

## Which result files can be trusted

- `results/BTCUSDT/evaluations.csv` and `holdout_log.csv`: current workflow,
  fixed engine, native data. ✅
- `results/BTCUSDT/legacy/`: Exp 003–010 outputs. Mostly stale (shifted
  data). A per-file trust table is in `results/BTCUSDT/legacy/README.md`.

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

1. Run the start-of-session checklist in `AGENTS.md` §0.
2. Work through the ★★★ ideas in `docs/research/TECHNIQUES.md` §6 with
   `evaluate.py`: trend breakout with a wide stop, the exit study (exits
   were mis-simulated before Exp 011), range mean reversion, and crowded
   funding.
3. Batch-summarise every ~5 ideas in `experiments.md` (Exp 012+).
4. Optional housekeeping, lower priority: the stale Exp 003–009 result files
   and the ledger `data_version` column (see above). New work does not depend
   on them.
