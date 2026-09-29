# BNBUSDT research log

Append-only. Rules: `AGENTS.md`. Plan: `docs/research/PLAN.md` §12.
History: `journal/BTCUSDT/` (closed), `journal/ETHUSDT/` (closed).

---

## Exp 000 — Setup

**Date:** 2026-09-29
**Status:** complete (config only; no data, no evaluation, holdout untouched)

The owner asked to try BNBUSDT after ETH closed, and said the research agent,
not the planner, runs it. Only configuration was prepared:
- `src/config.py` `SYMBOL_SPECS["BNBUSDT"]`: step 0.01 BNB, min notional 5 USDT, data 2020-03..2026-08 (listed 2020-02-10), research account 1,000 USDT. These are Binance's
  published contract specs; the exchange-info endpoint was not reachable
  from the setup machine.
- Data is **not** downloaded. The research agent runs `datafeed.py` and
  records VALIDATION in Exp 001.

Next: **Exp 001, pre-registration** (`PLAN.md` §12).
