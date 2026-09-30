> **Exp 008 (review, 2026-09-30):** the round's verdict stands. Corrections: the pre-registered cost floor was about 3.5× too low, so the 15m ports died on cost as `LESSONS.md` §1 predicted; T3's cost is fees and slippage, not the time cap; T3's BTC SKILL does not replicate on ETH and leans on 2023.

# ETHUSDT - status and handoff

> **Exp 007 — TradingView port round 1 is DONE on this coin: 24 evaluations,
> 0 PASS, 3 WATCH (all DRIFT, all NO_EDGE), 16 REJECT, 5 INCONCLUSIVE. No
> holdout was used, because nothing passed.** ETH is now **16 REJECT against
> BTC's 13**, and **no SKILL reading appeared on ETH at all** where BTC had two.
> ETH now has **73 evaluations**.
>
> | port | 15m | 30m | 1h | 4h |
> |---|---|---|---|---|
> | T1 044 ChartArt RSI+BB | −0.202 | −0.038 | −0.337 | −0.448 |
> | T2 045 LuxAlgo SMC | −0.199 | **+0.250** | −0.136 | **+0.200** |
> | T3 046 ChartArt MACD+SMA200 | +0.013 | −0.162 | −0.065 | −0.050 |
> | T4 047 Super Scalper | −0.142 | −0.094 | −0.035 | **+0.270** |
> | T5 048 ChartArt RSI+BB long-only | −0.062 | −0.064 | −0.422 | −0.658 |
> | T6 049 Liquidity Sweep | −0.251 | −0.126 | −0.099 | **+0.403** (7 trades) |
>
> The three WATCH rows, all DRIFT / NO_EDGE:
> **047 T4 @4h** 114 trades, gross +0.3073, cost 0.0369, mean R **+0.2704**,
> CI [−0.0224, +0.6171], CAGR +15.6%, maxDD 6.9%, **57 long / 57 short** ·
> **045 T2 @4h** 87 trades, +0.2004, CI [−0.0934, +0.5155], 43/44 ·
> **045 T2 @30m** 92 trades, +0.2500, CI [−0.2425, +0.8142], 53/39.
>
> **Two findings, and one of them corrects a lesson of mine.**
> 1. **T4 is the only port that agrees across coins**: BTC 4h +0.1001 on 141
>    trades 70/71, ETH 4h +0.2704 on 114 trades **57/57** — both DRIFT, both
>    NO_EDGE. The same lesson as 039's 21-of-21 clocks on three coins and then
>    2-of-7 on BNB: **consistency across coins is not an edge.**
> 2. **`LESSONS.md` §2's ETH long prior was wrong, in the one direction that
>    could only flatter it.** T5 is the long-only script and §2 said ETH's long
>    leg was positive in 78% of its evaluations against BTC's 56%, so T5 should
>    have had a *better* drift prior here. It is **−0.658 at 4h on ETH against
>    +1.616 on BTC**. A drift prior computed from a coin's aggregate statistics
>    is not a prior about a specific rule.
> 3. **T6's 4h row is +0.403 on 7 trades and the pre-registration predicted it**:
>    the session is UTC 12-15 and only the 12:00 bar is inside it on a 4h chart,
>    so 15 ETH signals in three years. Negative at 15m, 30m and 1h, which is where
>    the script was designed to run.
>
> Details: `journal/ETHUSDT/experiments.md` Exp 006 (pre-registration) and
> Exp 007 (results). BTC half: BTC Exp 032 / Exp 033.

> **Next (owner request): TradingView strategy ports** (`docs/research/PLAN.md` §13). Round 1 = ports T1–T6, `ideas/044_*` to `ideas/049_*` (24 files: 15m 30m 1h 4h), to be run on this coin and on the other of BTC/ETH (48 evaluations). The project's own families stay closed. **Round 1 is now complete on both coins — see the Exp 007 block above. The round's stop rule (`PLAN.md` §13): no holdout CONFIRMED ends the TradingView question unless the owner brings new scripts.**

> **CLOSED** (Exp 003 stop rule). The funding defect is fixed (Exp 004). Research continues on
> **SOLUSDT and BNBUSDT** (`docs/research/PLAN.md` §12).

_Last updated: 2026-09-30, Exp 007 (TradingView port round 1 done on ETHUSDT —
0 PASS, no holdout used). Rules: `AGENTS.md`.
Plan: `docs/research/PLAN.md` §11 and §13. BTCUSDT is closed for its own
families (BTC Exp 029); SOLUSDT and BNBUSDT are closed too._

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
