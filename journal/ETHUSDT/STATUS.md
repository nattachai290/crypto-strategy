# ETHUSDT - status and handoff

> **Next (owner request): TradingView strategy ports** (`docs/research/PLAN.md` §13). Round 1 = ports T1–T6, `ideas/044_*` to `ideas/049_*` (42 files), to be run on this coin and on the other of BTC/ETH (84 evaluations). The project's own families stay closed.

> **CLOSED** (Exp 003 stop rule). The funding defect is fixed (Exp 004). Research continues on
> **SOLUSDT and BNBUSDT** (`docs/research/PLAN.md` §12).

_Last updated: 2026-09-29, Exp 003 (Round E1 complete). Rules: `AGENTS.md`.
Plan: `docs/research/PLAN.md` §11. BTCUSDT is closed (BTC Exp 029)._

> **Exp 003 - ROUND E1 IS DONE. 0 PASS, 0 CONFIRMED, the ETH holdout is
> untouched.** 49 evaluations: **0 PASS, 32 WATCH, 14 REJECT, 3 INCONCLUSIVE.**
> `baseline.py` and `benchmark.py` ran on all 32 WATCHes.
>
> **The stop rule agreed in Exp 001 is live: no holdout CONFIRMED on ETH means
> ETH research stops too, and the answer stands for both coins.**
>
> **1. The controls were uniform, and that is the result.**
> `baseline.py` said **DRIFT on 32 of 32** WATCHes - not one entry beat random
> timing. `benchmark.py` said 31 NO_EDGE and 1 ALPHA. Thirty-two independent
> configurations on a second coin, and the entry beats random timing in none.
>
> **2. Every near-miss failed the same gate: the 95% CI lower bound.**
> The effects are the right size (mean R clears the `1.568/sqrt(n)` bar in most
> rows) and the samples are 54-103 trades, which cannot put a bootstrap CI above
> zero. Nothing failed on drawdown or on the x1.5 cost stress. This is a power
> problem, not a finding.
>
> **3. The one ALPHA is 041 `momentum` + `funding_not_crowded` + `volume_spike`
> at 1m: WATCH, DRIFT, ALPHA.** valid 77 trades, `gross_r` +0.2954, `cost_r`
> 0.0194, mean R **+0.2760**, CI [-0.0033, +0.6057], CAGR +10.8%, maxDD 6.9%,
> 41 long / 36 short, **beta -0.004**, alpha +10.8%/yr CI [+0.004, +0.218],
> Sharpe 1.37 vs buy & hold 1.18, maxDD 6.9% vs 45.4%.
> Two things about it are the healthiest in the project: **beta ~0** (it is not
> a disguised long) and **per-year 2023 +0.2773 on 38 trades against 2024
> +0.2749 on 39** - 50.5% / 49.5%, the only result in the project not leaning on
> the bull year. Every earlier positive was lopsided (022: +0.35 vs +0.14; 038:
> +0.09 vs +0.26; 039: +0.32 vs +0.14).
> It is still **DRIFT**: on TRAIN it sits below the 95th percentile of random
> entries with the same stop, hold and filters. **And it fails two gates** (77
> trades against a floor of 100, CI low -0.0033), so it is a WATCH.
>
> **4. DRIFT + ALPHA is now the third time, and the first two died on the
> holdout.**
>
> | config | coin | verdict | baseline | benchmark | holdout |
> |---|---|---|---|---|---|
> | 038 opening range @4h | BTC | PASS | DRIFT | ALPHA | **FAILED** -0.1118 R |
> | 039 breakout+flow @5m | BTC | PASS | DRIFT | ALPHA | **FAILED** +0.0129 R, beaten by a random entry |
> | 041 impulse @1m | ETH | WATCH | DRIFT | ALPHA | not run - a WATCH cannot be |
>
> **`--final` is refused and was not run** (AGENTS.md rule 4 is absolute).
> Spending the ETH holdout on 041@1m is the owner's decision (`PLAN.md` §5). On
> the evidence of the other two, my recommendation is **not to** - but the
> holdout is sealed and untouched.
>
> **5. What ETH adds that BTC did not.**
>
> | paired over all 49 identical configs | |
> |---|---|
> | ETH higher on **17**, lower on **32** | mean diff **-0.0179 R**, 95% CI [-0.0441, +0.0082] |
> | BTC's 2 PASSes on ETH | **both become WATCH** |
> | BTC REJECT -> ETH WATCH / BTC WATCH -> ETH REJECT | 14 / 5 |
> | **correlation between the coins' VALID results** | **+0.52 Pearson, +0.43 Spearman** |
>
> **My own first impression was wrong and the paired test corrected it.** Read
> off the top rows, ETH looked much better than BTC; paired over all 49 there is
> **no detectable difference, and if anything ETH is slightly worse**. ETH's 38%
> larger moves buy nothing once the structure is the same. And the +0.5
> correlation means the 210 BTC evaluations could not have been "reused" for ETH
> - the ETH results are substantially independent evidence, not a rerun.
>
> **6. 039 is positive on all fourteen clocks across both coins** - the most
> robust positive result this project has produced - and its BTC version is the
> one that PASSed, got ALPHA, and then failed the holdout because a random entry
> matched it. **Robustness across coins and clocks is not what separates an edge
> from a period effect. Only the holdout did that, twice.**
>
> **7. 034 multi-day reversal is now dead on both coins** (BTC 0/7 clocks
> positive, ETH 3/7, and the ETH positives are the round's smallest at +0.004 to
> +0.058). Fourth coin-clock to close that family.
>
> **8. [FIXED in ETH Exp 004 / BTC Exp 030, owner-approved: 7 of 242 verdicts change, 6 of them down, no new PASS.]** A defect in the engine, found and NOT fixed (Exp 002).
> `src/backtest.py:441` charges funding as `qty x rate` against a USDT cash
> balance, missing the mark price, so funding is understated by the price
> (**3,890x on ETH, ~40,000x on BTC**). Every other money line in that function
> (fee, move, slip_drag) multiplies by the price; only this one does not.
> **It changes no verdict on either coin** - the missing funding is worth 0.0037 R
> median on BTC and 0.0045 R on ETH, because funding is near zero in expectation
> and its sign alternates - and understating a cost can only make a result look
> better, so every negative conclusion is safe a fortiori. **Fixing it is Level 3
> and needs the owner's approval; `backtest.py` and `test_engine.py` are
> untouched and no failing test was added.**
>
> **9. A correction to my own Exp 001.** I wrote that ETH's cost line is 17%
> higher than BTC's and that Rounds 5-6 understated funding 1.9x. **Both are
> retracted** - they assumed funding was being charged. Measured, ETH `cost_r` is
> 0.0186 R median against BTC's 0.0190 R: identical. **The cost of a multi-day
> trade is ~0.02 R and it is fees almost entirely, not funding.** Rounds 5-6's
> conclusion survives on a narrower basis: it rests on the fee structure and the
> stop width, not on funding.

## Where things stand

- **ETHUSDT: 49 evaluations, 0 PASS, 0 CONFIRMED.** Holdout sealed.
- **BTCUSDT: 210 evaluations, 7 configurations ever read PASS, 0 CONFIRMED, the
  holdout used 4 times and failed 4 times.** Closed (BTC Exp 029).
- **The project has no profitable strategy and no confirmed technique on either
  coin.** The deliverable is `journal/BTCUSDT/FINAL_REPORT.md`.
- ETH sizing is a non-issue where BTC's was a real constraint: a 6% stop sizes
  while ETH < 166,667 and the holdout peak is 4,832, so **34x headroom**. No ETH
  evaluation can be `UNSIZABLE`.

## Next step

**None on this market.** The stop rule in Exp 001 has fired: Round E1 ended
without a holdout CONFIRMED, so ETH research stops, and the project's answer
stands for both coins. **Do not start an ETH round 2.**

Two things to raise with the owner (neither is mine to decide):

1. **The funding defect (Exp 002).** Fix it or leave it? A one-line change
   (`qty x price x rate`, as the fee and slippage lines already do) plus a
   hand-computed test that fails before and passes after. My recommendation is
   **fix it** - a research tool whose value is that its costs are honest should
   not have a cost it does not charge. **Re-running anything: no.** 0 verdicts
   change on either coin and the ETH near-misses move by 0.005 R while failing a
   gate by 0.0033-0.01.
2. **041@1m is the closest the project has come since 038** - WATCH, DRIFT,
   ALPHA, beta -0.004, per-year 50.5/49.5, Sharpe above buy & hold. It cannot go
   to the holdout without a PASS. If the owner wants it tested on the holdout
   anyway, that is a decision against AGENTS.md rule 4 and I will not take it
   silently; it would need an explicit instruction. My recommendation is not to.

## What BTC taught that applies here (method, not verdicts)

- Cost is ~0.02 R for a multi-day trade at a 6% stop, and it is **fees almost
  entirely, not funding** (Exp 002). Only multi-day holds leave room for an edge.
- Use `pct` stops, `--mode time` from a 4h source, so cost is equal on every
  clock.
- Trade both directions with no trend filter, or the 2023-24 bull market passes
  as skill.
- The random-entry baseline and the buy & hold benchmark decide whether a result
  means anything. On ETH, 32 of 32 were DRIFT and 31 of 32 NO_EDGE.
- ETH moves with BTC (correlation ~0.8), but the *results* correlate only +0.5,
  so one coin's VALID cannot be used to choose for the other.
