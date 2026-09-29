# SOLUSDT - status and handoff

_Last updated: 2026-09-29, Exp 003 (Round S1 complete, holdout spent and
FAILED). Rules: `AGENTS.md`. Plan: `docs/research/PLAN.md` section 12. BTCUSDT
and ETHUSDT are closed. BNBUSDT is active._

> **Exp 003 - ROUND S1 IS DONE. 49 evaluations, 1 PASS, and the holdout FAILED.
> Research on SOLUSDT stops.**
>
> **1. The PASS, and it was the best candidate this project has ever produced.**
> **041 `momentum` + `funding_not_crowded` + `volume_spike` at 5m: PASS +
> SKILL + ALPHA**, all three at once for the first time.
>
> | split | trades | gross_r | cost_r | mean R | 95% CI | CAGR | maxDD |
> |---|---|---|---|---|---|---|---|
> | train 2020-10..2022-12 | 132 | +0.212 | 0.012 | +0.1999 | | +11.3% | 11.3% |
> | valid 2023-2024 | 112 | +0.281 | 0.016 | **+0.2656** | [+0.0195, +0.5274] | +15.2% | 7.4% |
> | valid x1.5 cost | | | | +0.2582 | | | |
> | **holdout** | 93 | **+0.076** | 0.021 | **+0.0544** | [−0.1742, +0.2975] | +2.5% | 14.8% |
>
> `baseline.py` said **SKILL** (2% of random-any-time and 1% of random-same-
> filters runs beat it, on TRAIN *and* VALID). `benchmark.py` said **ALPHA**
> (+12.95%/yr CI [+1.8, +25.9], **beta +0.0089**). All seven clocks were positive
> on both TRAIN and VALID. TRAIN was positive on all seven clocks on **all four
> coins** (28 of 28).
>
> **2. The holdout FAILED - and it is the first failure of a different kind.**
> **The entry beat random timing on the holdout data itself**: idea +0.0544
> against a random median of −0.0056 (any time) and −0.0300 (same filters). No
> earlier candidate ever did that. 039's holdout was +0.0129 against a random
> median of +0.0380 and it lost.
>
> **What failed is the size, not the skill.** The mean R fell 79% from +0.2656
> to +0.0544, and 93 trades cannot resolve that: the gate needs
> mean R > 1.568/√93 = **+0.163**. **To put a +0.05 R effect above that bar
> needs n ≈ 983 trades** - about ten times a two-year holdout, or four years of
> this idea at this frequency. That is a power problem, not a refutation.
>
> **3. "Both sides are positive" did NOT hold - the thing that made it the best
> candidate.**
>
> | leg | VALID | HOLDOUT |
> |---|---|---|
> | long | **+0.3342** (55) | **−0.0594** (48), sum −2.85 |
> | short | +0.1994 (57) | +0.1759 (45), sum +7.92 |
>
> The short leg held. **The long leg went from +0.334 to −0.059 and became the
> whole loss.** The holdout result is a short result wearing the label "both
> directions" - the same failing diagnosis as 022, 038 and 039, arriving by a
> different route. The year split inverted too: VALID was 2023 +0.361 / 2024
> +0.170; the holdout is **2025 −0.0747 (60 trades) / 2026 +0.2893 (33)**.
>
> **4. The config is spent.** It may not be re-run, and no copy of it with a
> small change may be made to get another holdout try (AGENTS.md step 7). The
> stop rule for SOLUSDT fires: no holdout CONFIRMED on SOL means research on SOL
> stops.
>
> **5. A correction this round had to make to the plan's own arithmetic.**
> `PLAN.md` §12 item 3's cost formula `(0.14% + hold_h/8 × mean |funding|) / stop`
> gives **0.1038 R** on SOL at a 6% stop and 96 h, more than double Round 5's
> 0.05 R limit. Taken literally it says the round is hopeless before it starts.
> **It is an upper bound, not an estimate**: it multiplies the *absolute* rate by
> the number of settlements, but a position pays the signed sum, and SOL's TRAIN
> funding is *negative* on average (−0.00529%). Measured: **VALID `cost_r` median
> 0.0182 R**, min 0.0123, max 0.0286. The formula overstates by about 20x - the
> same correction BTC Exp 030 found by re-running all 256 recorded evaluations
> (−0.0015 R on BTC, −0.0027 R on ETH). **I wrote the corrected number down as a
> falsifiable prediction in Exp 001 before running, and the first run confirmed
> it.** Anyone reading the plan's formula should replace it with the measured
> `cost_r` in `evaluations.csv`.
>
> **6. The data-gap caveat stands for every SOLUSDT number** (Exp 001b,
> owner-approved). Two gaps in TRAIN (2022-02-25 73 h, 2022-03-31 49 h), upper
> bound **32 of 1,430 signals = 2.2%**, split 19 long / 13 short, biased against
> shorts. VALID and HOLDOUT are clean, so it cannot manufacture a PASS. Note
> that in hindsight the bias runs *against* shorts and the holdout loss was on
> the **long** side - so the gap did not cause this failure.
>
> **7. Where the project stands: four coins, 357 evaluations, 0 CONFIRMED, five
> holdout runs, five failures.**
>
> | | BTC | ETH | BNB | SOL |
> |---|---|---|---|---|
> | evaluations | 210 | 49 | 49 | 49 |
> | PASS | 2 | 0 | 0 | **1** |
> | SKILL controls | 3 (one vacuous) | 0 | 1 | 1 |
> | holdout runs | 4 | 0 | 0 | 1 |
> | CONFIRMED | 0 | 0 | 0 | **0** |
>
> The finding that generalises is not "no edge exists". It is the one 041@5m
> forced open, and it is sharper than anything the earlier rounds could say:
>
> **On this market a both-sided multi-day rule can have a genuinely skillful
> entry - one that beats random timing on data it has never seen, in both
> control modes - and still be worth only ~+0.05 R per trade, too small to prove
> at the number of trades any two-year holdout contains.** The question this
> project could not answer is not whether skill exists. It is whether an effect
> that size can be made large enough to matter, and **nothing tested in 357
> evaluations made it larger.**

## Where things stand

- **SOLUSDT: 49 evaluations, 1 PASS, 0 CONFIRMED.** Holdout spent once, FAILED.
  Research on SOL stops.
- **BNBUSDT: active.** Round B1 in progress; see `journal/BNBUSDT/`.
- **BTCUSDT closed** (210 evaluations, holdout 4/4 FAILED). **ETHUSDT closed**
  (49 evaluations, 0 PASS, 32/32 controls DRIFT).
- ETH sizing is a non-issue; SOL's whole-coin step rounds a 6% stop by up to
  5.6% of intended risk, and its 27-month TRAIN leaves three of seven families
  under the 150-signal floor.

## Next step

**None on SOLUSDT.** The stop rule agreed in the Exp 001 pre-registration and
confirmed by the owner in Exp 001b has fired.

Two things for the owner, neither of which is mine to decide:

1. **The `cost_r` formula in `PLAN.md` §12 item 3 is an upper bound presented as
   an estimate**, and it reads as "0.10 R, this round is hopeless" on the two
   new coins when the measured figure is 0.018 R. I would replace it with
   `(0.09% post-only + 0.05% taker) / stop + a small measured funding term`, or
   simply with "read `valid_cost_r` from `evaluations.csv`". Editing `PLAN.md` is
   not my call.
2. **Whether a hypothesis worth ~+0.05 R per trade is worth pursuing at all.**
   It needs roughly 10x the trades to prove, i.e. a longer history or several
   coins pooled, and the BTC/ETH/SOL paired work already showed the correlation
   between coins' results is only +0.52 - so pooling is not free. The other
   honest option is to stop.

## What BTC, ETH and SOL taught (method, not verdicts)

- Cost for a multi-day trade is **~0.02 R and it is fees almost entirely, not
  funding** (SOL Exp 003 item 5). The `pct` stop and the fee structure, not the
  funding rate, are what make multi-day holds affordable.
- Use `pct` stops, `--mode time` from a 4h source, both directions, no trend
  filter.
- **Run `baseline.py` and `benchmark.py` on every WATCH and PASS, and treat
  DRIFT as a disqualifier rather than a footnote.** Every genuine PASS before
  041@5m was DRIFT, and every one of them died on the holdout.
- **A both-sided result is not a both-sided edge.** 041@5m had positive legs on
  both sides on VALID and a negative long leg on the holdout. Read the two legs
  separately, on every split, every time.
- **Robustness across clocks and coins is not proof.** 039 was positive on all
  fourteen BTC+ETH clocks and failed its holdout; on BNB the same family was
  2/7.
- **A thin CI is a thin pass.** 041@5m cleared the gate at +0.0195 against a
  requirement of > 0, and the holdout came in at +0.0544 with 93 trades.
