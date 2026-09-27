# Project status and handoff

_Last updated: 2026-09-27, after Exp 010. Rules for agents: `AGENTS.md`._

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

Exp 010 found that every experiment before it (003–009) ran on bars shifted
one window into the past. The pipeline now loads native Binance files only.
Status of each file in `results/`:

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
| `ledger.csv` / `journal/ledger.md` | all | **mixed** | ⚠️ contains both pre- and post-fix rows without a flag |

(Trust status inferred by matching file contents against the numbers in the
journal; verify before relying on it.)

## Known issues / loose ends

1. **Stale results.** Exp 003–006 and 009 have not been re-run on native bars.
2. **Ledger has no data-version column.** Pre- and post-fix rows for Exp 008
   sit side by side (duplicate configs with different numbers). Add a
   `data_version` (`shifted` / `native`) column in `src/ledger.py`.
3. **`report.html` / `report_best.json` are pre-fix.** `src/report_data.py`
   hard-codes `BEST = reg 0.10 / stop 5.0`; that is no longer the best.
4. **Exp 009 status says "running"** in the journal but its result and verdict
   are written. The journal is append-only, so note completion in Exp 011
   rather than editing it.
5. **Raw zips are tracked in git** (480 files, ~240 MB) even though
   `.gitignore` lists `data/raw/*.zip`; they were force-added in the first
   commit so a fresh clone has data without network. `.gitignore` only
   prevents *new* zips being added. Do not add more without asking.
6. `data/cache/` is not committed: run `python src/datafeed.py` after cloning
   (it builds parquet from the zips in `data/raw/` and downloads anything
   missing, then runs `validate()`).
7. `SESSION_START_HOUR=0 / SESSION_END_HOUR=24` with `FLAT_AT_SESSION_END=True`
   — the session filter is effectively off; holding limits come from each
   strategy's `max_hold`.

## Suggested next steps (in order)

1. `pip install -r requirements.txt`, `python src/datafeed.py`,
   `python src/test_engine.py` — confirm the environment.
2. Add a `data_version` column to the ledger and tag existing rows (see table
   above), then regenerate `journal/ledger.md`.
3. Re-run the stale experiments on native bars (sweep → cost_lab →
   round2_stopwidth → run_ml → round4_holdperiod), log each as a new journal
   entry (Exp 011+), and update `report_data.py` / `report.html`.
4. Only then consider new hypotheses. The journal's own conclusion is that
   more indicator search is not worthwhile; candidates it names are:
   - an explicit multi-hour **swing** horizon (and saying so — not intraday);
   - **funding carry** / basis strategies;
   - **market making** (earning spread), which needs an order-book fill model
     the current engine does not have.
