# ETHUSDT research log

Append-only. Rules: `AGENTS.md`. Plan: `docs/research/PLAN.md` §11. The BTCUSDT
history (Exp 000–029, closed) is in `journal/BTCUSDT/`.

---

## Exp 000 — Setup

**Date:** 2026-09-29
**Status:** complete (no evaluation; holdout untouched)

After BTCUSDT closed (BTC Exp 029), the owner approved moving the research to
ETHUSDT.

- `src/config.py` `SYMBOL_SPECS["ETHUSDT"]` (Binance USDT-M ETHUSDT):
  - quantity step 0.001 ETH, minimum order notional 20 USDT;
  - data 2020-01..2026-08;
  - TRAIN 2020–2022, VALID 2023–2024, HOLDOUT 2025-01..2026-08, the same
    calendar split as BTC.
- The exchange-info endpoint could not be reached from the setup machine, so
  the step and notional are Binance's published values for ETHUSDT. They only
  affect sizing. At 1,000 USDT, 1% risk and a 6% stop, one trade is about
  170 USDT, far above both limits.
- `SYMBOL=ETHUSDT python src/datafeed.py`: **VALIDATION: OK**. All seven
  timeframes have 80/80 months, 0 duplicates and 0 gaps > 3 bars (1m: 3,506,400
  rows; 4h: 14,610). Funding: 7,305 rows, 2020-01..2026-08.
- **Round E1 signal counts, 4h, ETH TRAIN 2020–2022 only** (long/short, every
  trigger/filter grid value of each source file):

  | family | grid value → signals |
  |---|---|
  | 034 | n30 110/135 · n60 71/94 |
  | 035 | n30 161/99 · n60 120/64 |
  | 036 | n20 m2.0 120/82 · n50 m2.0 155/109 |
  | 038 | 339/310 |
  | 039 | n20 k1.2 111/138 · n20 k1.5 75/114 · n30 k1.2 89/106 · n30 k1.5 65/88 |
  | 041 | atr_k1.5 74–76/128 · atr_k2.0 59–63/101 |
  | 043 | q0.2 87/66 · q0.3 107/84 |

  Every value is at least 150, so nothing is dropped.
- **Disclosure: one smoke run.** To check the pipeline on ETH, the setup ran
  `039_breakout_flow_confirm.json` (4h) once into a scratch directory. It is
  **not recorded**: `results/ETHUSDT/` stays empty.
  - Result: TRAIN +0.263 (114 trades); VALID +0.102, CI [−0.099, +0.317],
    89 trades; size_skips 0 on both periods.
  - The plan was written **before** this run and was not changed after it.
  - Round E1 runs the same file for the record.
- `src/benchmark.py` now names the symbol's asset ("ETH", "BTC") in its
  report text instead of a fixed "BTC". The numbers were already per symbol.
- `test_engine.py`: ALL CHECKS PASSED.

Next: **Exp 001, Round E1 pre-registration** (`PLAN.md` §11).
