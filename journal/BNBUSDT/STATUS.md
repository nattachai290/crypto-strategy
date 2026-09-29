# BNBUSDT - status and handoff

> **Review note (SOL Exp 004, planner):** Round B1 **has run**: 49 evaluations recorded, **0 PASS**, 10 WATCH, 33 REJECT, 6 INCONCLUSIVE. The holdout is untouched. By the stop rule, BNB research stops. The text below is out of date. Still missing: the results entry in `experiments.md`, and `baseline.py`/`benchmark.py` on 041@3m and 043@1m.

_Last updated: 2026-09-29, Exp 000 (setup). Rules: `AGENTS.md`. Plan:
`docs/research/PLAN.md` section 12._

## Where things stand

- **Nothing has been evaluated on BNBUSDT, and no data has been downloaded yet.**
  The holdout (2025-01..2026-08) is untouched.
- Spec in `src/config.py`: step 0.01 BNB, min notional 5 USDT, data 2020-03..2026-08 (listed 2020-02-10), research account 1,000 USDT. Splits are the same as BTC/ETH.
- Run everything with `SYMBOL=BNBUSDT`.

## Next step

1. `python src/test_engine.py`: must include test **1b** (the funding fix,
   BTC Exp 030) and end with ALL CHECKS PASSED.
2. `SYMBOL=BNBUSDT python src/datafeed.py` until `VALIDATION: OK`.
3. **Exp 001, pre-registration**, then the round: the seven cost-first
   families, run unchanged, 49 evaluations (`PLAN.md` section 12).

Stop rule: no holdout CONFIRMED on BNBUSDT means research on BNBUSDT stops.

## What BTC and ETH taught (method, not verdicts)

- BTC: 208 evaluations, holdout 4/4 FAILED. ETH: 49 evaluations, 0 PASS,
  32/32 controls DRIFT.
- Cost is ~0.11% of price per trade at every timeframe. Only multi-day holds
  leave room for an edge.
- Trade both directions with no trend filter, or the 2023-24 bull market
  passes as skill. Run the random-entry baseline and the buy & hold
  benchmark on every WATCH/PASS.
- A result positive on every clock (BTC 039) still failed its holdout.
  Robustness is not proof: only the holdout is.
