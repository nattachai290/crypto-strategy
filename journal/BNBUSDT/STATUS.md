> **Exp 005 — the `051_retail_crowd_fade_tf30` replication is DONE on this coin:
> REJECT on 5 of 7 gates, and the replication FAILS. BNBUSDT now has 50
> evaluations. No holdout used (`--final` not run, not a candidate).**
>
> | | trades | gross_r | cost_r | mean R | 95% CI | CAGR | maxDD | L/S |
> |---|---|---|---|---|---|---|---|---|
> | **TRAIN** | 103 | −0.070 | 0.063 | **−0.1326** | | | 20.7% | |
> | **VALID** | **215** | −0.063 | 0.064 | **−0.1272** | [−0.2745, +0.0219] | **−13.3%** | **31.0%** | 109/106 |
> | x1.5 cost | | | | −0.1595 | | | | |
>
> 2023 −0.1793 / 2024 −0.0835 · exits 38% stop / 61% time · hold 18.4 h · 0 skips
> · **grid 4 cells, only 1 eligible, and 0% of the eligible ones positive on
> TRAIN** · chose z 1.5 / 24 h.
>
> **Both controls: `baseline.py` DRIFT, `benchmark.py` NO_EDGE.**
> - baseline: idea **−0.1272** against the random p95 of +0.0183; **73.5% of
>   random runs beat it.**
> - benchmark: VALID **beta −0.0024**, alpha **−0.1338/yr CI [−0.3074, +0.0281]**,
>   Sharpe −1.102 against buy & hold's +1.272.
>
> **Against `PLAN.md` §15's criterion — VALID mean R > 0 AND baseline SKILL:
> BOTH are NOT MET. This coin FAILS, and so does the replication.** The
> pre-registration's specific worry is what happened: 1 eligible cell of 4, and
> that single cell was negative on TRAIN, so no selection happened at all.
>
> **The loss is not a long/short asymmetry and not a cost artefact:** legs are
> long −0.1409 / short −0.1131, **both negative**, and `gross_r` is −0.063 before
> costs. `cost_r` 0.0644, in line with the other three coins.
>
> **The four coins together (846 pooled VALID trades, per-coin resampled): mean R
> +0.0391, 95% CI [−0.0562, +0.1325], P(>0) = 0.79.** Leaving BNB out gives
> +0.0958 with CI [−0.0156, +0.2136] — so the whole case rests on excluding BNB,
> and even that interval touches zero. **Long legs +0.167 / +0.133 / +0.174
> against short legs +0.055 / +0.031 / +0.027 on the three coins that made money,
> with beta ≈ 0 on all four: the configuration is a way of being long in
> 2023-24, not a way of fading a crowd.** The two-coin SKILL margins were +0.048
> and +0.043 on BTC and ETH, **and −0.027 on SOL and −0.146 on BNB — the sign
> flipped on both** — a two-coin coincidence, now established with 440 evaluations
> and five failed holdouts behind it.
>
> Per `PLAN.md` §15: **the metrics question is closed, and no M2 variant is
> tried.** Details: Exp 004 (pre-registration) and Exp 005 (this result).

> **Reopened for one replication (owner-approved 2026-10-01, `docs/research/PLAN.md` §15):** run `ideas/051_retail_crowd_fade_tf30.json` unchanged on this coin. **Done — see Exp 005 above. The replication failed.**

# BNBUSDT - status and handoff

_Last updated: 2026-10-01, Exp 005 (the `051_retail_crowd_fade_tf30` replication
failed on this coin — REJECT on 5 of 7 gates — and the replication failed on both
coins). Rules: `AGENTS.md`. Plan: `docs/research/PLAN.md` §12 and §15. BTCUSDT,
ETHUSDT and SOLUSDT are all closed. The metrics question is closed: 32
evaluations in §14 plus these 2 replications, 0 PASS._

> **Exp 003 - ROUND B1 IS DONE. 49 evaluations, 0 PASS, 0 CONFIRMED. The BNB
> HOLDOUT was never touched. Research on BNBUSDT stops.**
>
> | | |
> |---|---|
> | evaluations | **49**: 0 PASS, 10 WATCH, 33 REJECT, 6 INCONCLUSIVE |
> | controls | on **all 10** WATCH rows - **9 DRIFT, 1 SKILL**; **9 NO_EDGE, 1 ALPHA** |
> | `size_skips` | 0 on every row, TRAIN and VALID |
> | VALID `cost_r` | min 0.0097, median 0.0173, max 0.0261 |
> | holdout | **never used** - no PASS, so `--final` was never a candidate |
>
> **1. Every one of the ten WATCHes failed the same gate: the 95% CI lower
> bound**, and eight of ten also failed the 100-trade floor. **Not one failed on
> drawdown and not one on the x1.5 cost stress.** BNB produced effects of the
> right size on 54-97 trades and could not put a single CI above zero.
>
> **2. The round's two most eye-catching rows are both disqualified, in
> opposite directions. That is the finding.**
> - **034 @3m: +0.1864 VALID, the round's largest number, and the only ALPHA -
>   but DRIFT.**
> - **035 @1h: the only SKILL - but NO_EDGE.**
>
> `PLAN.md` §5 step 1 stops a configuration with neither SKILL nor ALPHA, and
> stops one that has one without the other. Neither of these is a strategy.
>
> **3. The most robust result the project ever produced did not survive a third
> coin - and that is now measured, not argued.** 039 was positive on **7/7 BTC
> clocks and 7/7 ETH clocks (fourteen of fourteen)**, and **7/7 on SOLUSDT again
> (twenty-one of twenty-one)**. On BNBUSDT the same frozen idea file is **2/7**.
> 036 Keltner is **0/7** here (4/7 on BTC, 4/7 on ETH), and 038 opening range -
> the BTC PASS that got ALPHA and then failed its holdout - is **1/7**.
> **Robustness across clocks and across three coins is not evidence of an edge.**
>
> **4. 035 is the only family broadly positive on all four coins** (7/7 BTC, 4/7
> ETH, 5/7 BNB, 6/7 SOL), and its BNB 1h configuration is the only SKILL reading
> on a third or fourth coin. Recorded as the most consistent *family* in the
> project. Not worth trading: no BNB configuration is a PASS, the SKILL one is
> NO_EDGE, and BTC's 035 was never better than a WATCH.
>
> **5. Both Exp 001 predictions held.** The cost formula, taken literally, gives
> 0.0775 R at a 6% stop and 96 h; measured median is 0.0173 R, because the
> formula multiplies the *absolute* funding rate by the number of settlements
> where a position pays the signed sum. And the prediction that 039, 041 and 043
> would trade about half of what they trade on BTC: 6 INCONCLUSIVE rows here
> against 3 on BTC and 0 on ETH, with best VALID samples of 88, 97 and 70 trades
> against 103-132 on the 36-month coins.
>
> **6. 035@1h in full, recorded and not pursued.** TRAIN 113 trades +0.2931;
> VALID 70 trades, gross +0.2132, cost 0.0171, mean R **+0.1961**, CI [−0.0103,
> +0.4172], CAGR +6.8%, maxDD 4.7%, stress +0.1885, 42 long / 28 short, per-year
> 2023 +0.1007 and 2024 +0.2916 on 35 trades each. `baseline.py` **SKILL**,
> `benchmark.py` **NO_EDGE** (alpha +0.0467/yr VALID CI [−0.0185, +0.1201] and
> +0.0510 TRAIN CI [−0.0715, +0.2047], both containing zero; Sharpe 1.27 equals
> buy & hold's 1.27). **It is a WATCH, so `--final` is refused by AGENTS.md rule
> 4, and no holdout was run or is warranted.**
>
> **7. Four coins, 357 evaluations, 5 holdout runs, 5 FAILED, 0 CONFIRMED.**
>
> | | BTC | ETH | BNB | SOL |
> |---|---|---|---|---|
> | evaluations | 210 | 49 | 49 | 49 |
> | PASS | 2 | 0 | **0** | 1 |
> | SKILL controls | 3 (one vacuous) | 0 | **1** | 1 |
> | holdout runs | 4 | 0 | **0** | 1 |
> | CONFIRMED | 0 | 0 | **0** | 0 |
>
> **The stop rules have now fired on all four coins.** Nothing in this project is
> a tested strategy and no real money should follow from it.

## Where things stand

- **BNBUSDT: 49 evaluations, 0 PASS, 0 CONFIRMED, holdout sealed.** Research on
  BNB stops.
- BTCUSDT closed (210 evaluations, holdout 4/4 FAILED), ETHUSDT closed (49, 0
  PASS, 32/32 controls DRIFT), SOLUSDT closed (49, 1 PASS whose holdout FAILED).
- BNB data is the cleanest of the four: `VALIDATION: OK`, all 71 months on all
  seven timeframes, no duplicates, **no gaps over 3x the bar step**.
- Sizing was never a constraint on any of the four coins: a 6% stop sizes while
  BNB < 16,667 against a holdout peak of 1,342, and `size_skips` is 0 everywhere.

## Next step

**None on BNBUSDT**, and none on the other three: every per-coin stop rule has
fired. The deliverable is `journal/SOLUSDT/experiments.md` Exp 004 for the
cross-coin table and `journal/BTCUSDT/FINAL_REPORT.md` for the BTC rounds.

Three things for the owner, none of which is the agent's to decide:

1. **The `cost_r` formula in `PLAN.md` §12 item 3 is an upper bound presented as
   an estimate.** It reads as "0.078 R, the round is hopeless" on BNB and "0.104
   R" on SOL, when the measured medians are 0.017 R and 0.018 R. The honest
   version is the fee round trip over the stop plus a small measured funding
   term, or simply "read `valid_cost_r` from `evaluations.csv`". Editing
   `PLAN.md` is the owner's call. **Anyone starting a fifth coin should not use
   that formula to decide the round is pointless.**
2. **Whether a fifth coin is worth it at all.** The BTC/ETH/SOL paired work
   found the correlation between coins' results is only +0.52, so a new coin is
   a genuinely new sample - but the 357 evaluations so far say the answer is
   probably the same, and 039's 21-of-21 then 2-of-7 shows the project cannot
   predict which coin a family will work on.
3. **Whether the two SKILL readings that are not PASSes are worth anything.**
   BTC 041@15m and BNB 035@1h both read SKILL, both are WATCHes, and neither can
   go to the holdout without breaking AGENTS.md rule 4. My recommendation is no
   - SOL's 041@5m was also SKILL and its holdout came in at +0.054 R with a CI
   from −0.174 to +0.298.

## What the four coins taught (method, not verdicts)

- **Cost for a multi-day trade is ~0.02 R and it is fees almost entirely, not
  funding.** The `pct` stop and the fee structure, not the funding rate, are
  what make multi-day holds affordable. Measure it; do not formula it.
- Use `pct` stops, `--mode time` from a 4h source, both directions, no trend
  filter.
- **Run both controls on every WATCH and every PASS, and treat the two verdicts
  as independent disqualifiers.** On BNB the only ALPHA was DRIFT and the only
  SKILL was NO_EDGE. A configuration needs both.
- **A both-sided result is not a both-sided edge.** SOL 041@5m had positive legs
  on both sides on VALID and a negative long leg on the holdout. Read the two
  legs separately, on every split, every time.
- **Robustness across clocks and coins is not proof.** 039 was 21/21 across BTC,
  ETH and SOL and 2/7 on BNB, and its BTC version failed its holdout.
- **A thin CI is a thin pass.** SOL 041@5m cleared at +0.0195 against a gate of
  > 0, and its holdout was +0.054 with 93 trades.
- **Signal count, not parameter choice, is what limits a short-history coin.**
  BNB's 34 months and SOL's 27 produced 6 INCONCLUSIVE rows each, against BTC's
  36 months and 3.
