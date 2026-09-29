# ETHUSDT — status and handoff

_Last updated: 2026-09-29, Exp 000 (setup). Rules: `AGENTS.md`. Plan:
`docs/research/PLAN.md` §11._

## Where things stand

- **Nothing has been evaluated on ETH yet.** The ETH holdout
  (2025-01..2026-08) is untouched.
- Setup done in Exp 000:
  - `SYMBOL_SPECS["ETHUSDT"]`: qty step 0.001 ETH, min notional 20 USDT,
    the same splits as BTC;
  - native data downloaded and validated;
  - `test_engine.py` passes.
- Run everything with `SYMBOL=ETHUSDT`. Without it the tools default to
  BTCUSDT, which is **closed** (BTC Exp 029).

## Next step

**Round E1** (`PLAN.md` §11): the seven cost-first families (034, 035, 036,
038, 039, 041, 043), run as the existing idea files, unchanged, on ETH data.
That is 7 × 7 timeframes = 49 evaluations, with a pre-registration first
(Exp 001).

Stop rule: no holdout CONFIRMED on ETH → ETH research stops too.

## What BTC taught that applies here (method, not verdicts)

- Cost is ≈ 0.11% of price per trade at every timeframe. Only multi-day holds
  leave room for an edge, and intraday verdicts are cost arithmetic.
- Use `pct` stops. Use `--mode time` from a 4h source, so cost is equal on
  every timeframe.
- Trade both directions with no trend filter. Otherwise the 2023–24 bull
  market passes as skill.
- The random-entry baseline (SKILL/DRIFT) and the buy & hold benchmark decide
  whether a PASS means anything. On BTC, four PASSes went to the holdout, and
  all four failed.
- ETH moves with BTC, so ETH's VALID period is not independent of the BTC
  work. Only the ETH holdout is.
