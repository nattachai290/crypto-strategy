# LTCUSDT - experiments (append-only)

---

## Exp 000 - Coin added for the Coinbase premium confirmation (PLAN.md section 26)

**Date:** 2026-10-02
**Status:** set up, not run.

Added by a fixed rule written before any confirmation result:
- Coinbase USD history starts by 2021-07 with no gap of more than 30 days;
- a Binance USDT-M perp listed by 2020-09.

Specs are in `src/config.py`. Only idea 057 runs here, unchanged.


---

## Exp 001 - Coinbase premium (PLAN.md section 26): data validation failed, coin skipped

**Date:** 2026-10-02
**Status:** skipped by the owner's rule. **No evaluation was run on this coin**,
no idea file or code was changed, `--final` was not run, HOLDOUT was never read.
**This coin counts as a failure in the pre-registered bars.**

**Why it was skipped.** `SYMBOL=LTCUSDT python src/datafeed.py --tfs
15,30,60,240` printed **`VALIDATION: PROBLEMS FOUND`**, same defect as SOLUSDT:
**2 gaps longer than 3x the bar interval on every timeframe** (15m 230,304 rows /
30m 115,152 / 1h 57,576 / 4h 14,394, 2020-02-01 .. 2026-08-31, 79 of 79 months
present, 0 duplicates). Funding downloaded cleanly (7,212 rows). **Per the
owner's rule the coin is recorded and skipped and counts as a failure. Nothing
was changed to make it pass.** **No evaluation was run on LTCUSDT.**

LTC was one of the six coins the plan listed as having full TRAIN history, so the
confirmation ran on **8 of the 10 planned coins**, and only 5 of those 8 produced
an admissible 4h row.

**Files.** none for this coin. The round's summary is
`journal/_multi/experiments.md` Exp 011, `journal/_multi/premium_confirm.md`
(generated), `results/_multi/premium_confirm/`.
