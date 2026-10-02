> **§26 confirmation on 10 unseen coins: `NOT_CONFIRMED` — the 4h lead holds its
> direction and loses on breadth, and the 30m SKILL does not travel.** BTCUSDT was
> not rerun. `premium_confirm.py`, run once: 30m positive on **2 of 10** coins with
> SKILL on **1** (bars: 7 and 5) → **not confirmed**; 4h pooled over the 5
> admissible coins: **475 trades, mean +0.2368 R, weekly-block CI [+0.1023, +0.3830],
> long +0.2269 / short +0.2481**, but only 5 positive coins against 7 required →
> **not confirmed**. 2 of the 10 coins (SOL, LTC) failed data validation and 3 of
> the 8 that ran had no admissible 4h cell, so breadth was structurally out of
> reach. **14 of 16 random-entry controls are DRIFT.** Details: `_multi` Exp 011,
> `journal/_multi/premium_confirm.md`. **The premium lead is closed like `051`;
> no pooled holdout and no 057 variant.**
>
> **What this does to §25's reading below: the +0.4233 R at 4h was directionally
> right and its size was not a BTC/ETH accident — 8 of 8 coins that ran have a
> positive 4h gross above cost, and the pooled mean is +0.2368 R. What did not
> hold is that it is timing: DRIFT on 14 of 16 controls.** Also: BTC's and ETH's
> `train_positive_share` of 8 of 8 cells at 30m/1h does **not** hold on altcoins
> (median near 50%), so that part of §25 was two coins moving together.

> **Coinbase premium (§25, Exp 058): 2 WATCH, 2 REJECT. The largest gross R in
> the project, and still not a candidate.** The first data from outside Binance
> (`python src/datafeed.py --premium`, **PREMIUM VALIDATION: OK**, 58,393 hourly
> rows per coin, coverage 99.8–100.0% every year, median abs premium
> 0.028–0.078%), read by the new block `premium_cross` (the premium's z-score
> against its own last n bars crosses ±z). 8-cell grid on TRAIN, ATR 3 stop,
> out after 48 h. BTCUSDT now has **262 evaluations**.
>
> | tf | verdict | trades | gross_r | cost_r | mean R | 95% CI | long/short | CAGR | maxDD |
> |---|---|---|---|---|---|---|---|---|---|
> | 15m | REJECT | 328 | +0.1107 | 0.1254 | **-0.0147** | [-0.1517, +0.1267] | 146/182 | -3.8% | 24.4% |
> | 30m | **WATCH** | 207 | +0.1501 | 0.0906 | **+0.0595** | [-0.1123, +0.2409] | 99/108 | +5.3% | 18.1% |
> | 1h | REJECT | 220 | +0.0830 | 0.0660 | +0.0171 | [-0.1621, +0.2003] | 98/122 | +1.0% | 23.0% |
> | **4h** | **WATCH** | **72** | **+0.4603** | **0.0370** | **+0.4233** | **[+0.0404, +0.8236]** | **37/35** | **+13.6%** | **7.0%** |
>
> Cost x1.5: 15m -0.0800 · 30m **+0.0173** · 1h -0.0142 · **4h +0.4074**.
> `size_skips` 0 on every row. TRAIN chose 4h **z 1.5 / n 336 / 4R**.
> TRAIN breadth: **8 of 8 cells positive on TRAIN at 30m and 1h**, 4 of 4
> eligible at 4h, 4 of 8 at 15m. Exits VALID 4h: stop 44.4% / time 41.7% /
> target 12.5%, avg hold 131 h.
>
> | row | baseline | benchmark |
> |---|---|---|
> | 057 4h | **DRIFT** (idea TRAIN +0.2109 < random TRAIN p95 +0.2338; 6.5% of random sets beat it) | **NO_EDGE** (alpha +0.1138, CI [-0.0098, +0.2533]; Sharpe 1.60 vs 2.01) |
> | 057 30m | **SKILL** (TRAIN +0.1383 > p95 +0.0768; VALID +0.0595 > p95 +0.0255) | **NO_EDGE** (alpha CI [-0.1333, +0.2012]) |
>
> 1. **THE FIRST SIGNAL HERE THAT IS WORTH MORE THAN IT COSTS.** BTC 4h **gross
>    +0.4603 R against cost 0.0370 R** — 12x. §22's best was +0.2240 gross at
>    0.0376 cost and was unsizable; pooled ML round 1's best was +0.1475. Cost by
>    clock 0.1254 / 0.0906 / 0.0660 / 0.0370 against gross 0.1107 / 0.1501 /
>    0.0830 / **0.4603**.
> 2. **Not a look-ahead artefact, checked three ways.** Test 21 (parse, causal
>    attach from H + 1 h 2 min, staleness to NaN, one crossing = one long) and
>    test 7 pass; **ALL CHECKS PASSED**. Independently, rebuilding `premium_cross`
>    from each trade file: **499 of 499 BTC fills sit on the bar immediately after
>    a signal bar of the same side, with a live premium on that bar**, and each
>    row's mean of `r_multiple` equals its reported mean R.
> 3. **The distribution is not one lucky outlier.** 4h median trade **+0.2557**,
>    win rate **52.8%**, PF **1.83**, 38 of 72 positive, entries spread evenly
>    (34 in 2023, 38 in 2024, median 224 h apart), **both years positive**
>    (+0.301, +0.527), time exits alone averaging **+0.9312** over 30 trades.
>    `AGENTS.md` §9's "mean R > 0.3" warning was checked against the trade list,
>    not assumed away.
> 4. **It fails on the count and the controls, not the sign.** The only gate the
>    4h row fails is **`valid_trades>=100`** — 72 against the floor — and 100 is
>    not reachable here: at 4h only 4 of 8 cells produce 100 TRAIN trades, and
>    the loosest cell TRAIN chose anywhere in the round gave 86 VALID trades on
>    ETH. **DRIFT and NO_EDGE both stand.**
> 5. **The long leg wins at every clock and the short leg loses at three of four**
>    (+0.1168 / +0.1268 / +0.2552 / **+0.7047** against -0.1202 / -0.0022 /
>    -0.1742 / +0.1260) — §2's bull-market reading, and the same "short is the
>    losing half" shape as §23 and §24.
> 6. **The signal is strongest where it is slowest, which inverts every earlier
>    round.** 15m is the worst clock, 4h the best. §25's prior said the 4h
>    variants matter most because the premium is described over days — right.
>
> Details: Exp 058. ETH half: ETH Exp 021.

> **Limit orders resting at support/resistance (§24, Exp 055): `REJECT` on 1h
> and 4h. Not a candidate, no `--final`, HOLDOUT untouched.** `src/level_limit.py`
> rests a maker limit AT the level (previous UTC day's high/low or a live 10-bar
> pivot), stop just beyond it, each order simulated on its own; TRAIN picks 1 of 8
> cells; gates include beating 200 control order sets at random bars with the same
> distance in ATR and the same side mix. BTCUSDT still has **258 evaluations** -
> this tool writes no evaluation row.
>
> | run | verdict | TRAIN chose | VALID fills / orders | fill rate | mean R | 95% CI | gross_r | cost_r |
> |---|---|---|---|---|---|---|---|---|
> | BTC 240m | REJECT | `prev_day` 2 ATR 3R | **871 / 1313** | **66.3%** | **-0.0334** | [-0.1271, +0.0589] | **-0.0030** | 0.0304 |
> | BTC 60m | REJECT | `swing` 2 ATR 3R | **542 / 975** | **55.6%** | **-0.0957** | [-0.2262, +0.0386] | **-0.0191** | 0.0766 |
>
> Gates failed on both: `train_mean>0`, `valid_mean>0`, `valid_ci_lo>0`,
> `stress_mean>0`, `beats_control_p95_train`, `beats_control_p95_valid`.
> Cost x1.5 (VALID): 240m -0.0334 -> **-0.0495**; 60m -0.0957 -> **-0.1348**.
>
> | | control median | control p95 | real mean |
> |---|---|---|---|
> | 240m TRAIN / VALID | -0.0161 / -0.0295 | **+0.0469 / +0.0511** | -0.0236 / -0.0334 |
> | 60m TRAIN / VALID | -0.0505 / -0.0707 | **+0.0375 / +0.0199** | -0.0739 / -0.0957 |
>
> Exit mix VALID: **stop 64.6% / 64.9%**, time 19.7% / 19.9%, target 15.6% /
> 15.1%, avg 21.6 / 19.6 bars.
>
> 1. **Not one of the 16 cells was positive on TRAIN** (best -0.0236, worst
>    -0.2723). Best was 240m `prev_day` 2 ATR 3R; worst 60m `swing` 1 ATR 3R.
> 2. **The maker entry worked and it was still not enough.** `cost_r` 0.0304 R at
>    4h and 0.0766 at 1h, against Exp 049's 0.041 / 0.097 for wide-stop market
>    entries on the same clocks - **the resting limit really is cheaper.** But
>    **gross is -0.0030 and -0.0191**, i.e. zero, because a level is not better
>    support than any other price. **Nothing for the better entry to harvest.**
> 3. **The real orders came in below the control's median on all four splits.**
>    A limit at yesterday's low is worth slightly *less* than a limit at the same
>    distance at a random bar. This is the **second independent test of the §22
>    levels with the opposite entry logic; both say the level carries nothing.**
> 4. **The short leg loses on both clocks and both splits** (240m VALID long
>    **+0.1038** / short **-0.1542**; 60m -0.0185 / -0.1598). Same sign, same
>    coin as the stop diagnosis in Exp 052, independent method.
> 5. **A resting limit cannot filter its own fills.** 55.6-66.3% of orders fill
>    and ~65% of fills are stopped against ~15% at target: the orders that fill
>    are the ones price ran through, and price running through the level is the
>    stop being hit.
>
> Details: Exp 055. ETH half: ETH Exp 019. Per-run tables:
> `journal/BTCUSDT/level_limit.md` (generated), `results/BTCUSDT/level_limit/`.

> **Stop diagnosis (§23, Exp 052): `WRONG_DIRECTION`. Read-only - nothing was
> re-tuned, no new evaluation, no holdout touched.** `src/stop_diag.py` re-read
> every recorded VALID trade file (15m/30m/1h/4h, PASS/WATCH/REJECT, 0 size
> skips, ≥ 30 trades) and asked the owner's question - wrong way, or right way
> then shaken out? **138 evaluations, 44,057 VALID trades.**

> | measure | real | random (same side/stop/hold) | excess | 95% CI |
> |---|---|---|---|---|
> | right direction at the time limit | **49.01%** | 50.55% | **-1.54 pts** | **[-2.48, -0.62]** |
> | right, among stopped trades | | | **+2.47 pts** | **[+1.25, +3.74]** |
> | no-stop move to the time limit | +0.0596 R | +0.0180 R | +0.0202 R | [-0.00006, +0.0406] |
> | real stop rate | 24.27% | | | |

> **The owner's answer: both, but the bad one dominates.** On the direction call
> alone these entries are *worse* than a random fill, and the CI clears 0 by a
> factor of 4. It is visible on the 89 REJECT and 44 WATCH rows too, not just
> the 5 PASSes. **Prior was `COIN_FLIP`; it was wrong for BTC.**
>
> 1. **The 15m short-breakout cluster is the worst block in the project.** Four
>    of the five worst ideas (`010`, `012`, `014`, `015`) are right **36.9-38.6%**
>    of the time where random is right 48.0-48.6% - **-9.8 to -11.4 points.** Six
>    short-named evaluations, trade-weighted **-8.67 pts**, against -1.39 for
>    long-named and -1.22 for everything else. That is an inverted signal, not a
>    weak edge. Only 6 of 138 evaluations are short-named, so this is a real
>    pattern in a small identifiable block.
> 2. **The shakeout effect is real but 1.6x too small.** Among stopped trades,
>    real entries were right +2.47 pts more often than random (CI above 0), so
>    something is there - and it points the opposite way to the -1.54 pts
>    direction skill.
> 3. **The no-stop move agrees with §1 and §10:** +0.0202 R against random, CI
>    touching 0 from above. The structure is real and it is the size of the cost.
> 4. **By clock, the damage is at 15m** (-2.02 pts; 30m +0.22, 1h -0.59, 4h
>    +0.29) - and 15m is also where `cost_r` is 0.177-0.213 R (Exp 049).
>
> **Does not carry to ETH:** ETH is `COIN_FLIP`, -0.48 pts, CI [-1.47, +0.47]
> (ETH Exp 017). Same sign, four times smaller, and the short-breakout block was
> never traded there.
>
> Details: Exp 052. Per-idea table: `journal/BTCUSDT/stop_diag.md` (generated),
> `results/BTCUSDT/stop_diag/`. This is a diagnosis, not a candidate.

> **Candle pattern at a support/resistance level (§22, Exp 049): 0 PASS, 0 WATCH,
> 7 REJECT, 1 INCONCLUSIVE. No controls, no v2, no holdout.** The owner's request
> for "candle pattern + location + support and resistance", as the new block
> `recipes.candle_at_level` (engulfing or pin at the previous UTC day's low/high,
> or at a live 10-bar pivot), exits on a swing stop 2 bars beyond the candle with
> a 2.5-5 ATR floor, 8-cell grid chosen on TRAIN. BTCUSDT now has **258
> evaluations**.
>
> | idea | tf | verdict | trades | gross_r | cost_r | mean R | 95% CI | long/short |
> |---|---|---|---|---|---|---|---|---|
> | 054 `prev_day` | 15m | REJECT | 341 | -0.0106 | 0.1771 | -0.1878 | [-0.3190, -0.0544] | 174/167 |
> | 054 `prev_day` | 30m | REJECT | 290 | -0.0393 | 0.1298 | -0.1691 | [-0.2936, -0.0419] | 138/152 |
> | 054 `prev_day` | 1h | REJECT | 227 | -0.0280 | 0.0974 | -0.1254 | [-0.3014, +0.0542] | 96/131 |
> | 054 `prev_day` | 4h | REJECT | 100 | +0.0571 | 0.0412 | +0.0159 | [-0.2496, +0.3003] | 45/55 |
> | 055 `swing` | 15m | REJECT | 475 | -0.0709 | 0.2128 | -0.2837 | [-0.4030, -0.1635] | 247/228 |
> | 055 `swing` | 30m | REJECT | 242 | -0.0338 | 0.1415 | -0.1753 | [-0.3383, -0.0025] | 126/116 |
> | **055 `swing`** | **1h** | **REJECT** | 166 | **+0.1291** | 0.0995 | **+0.0296** | [-0.1896, +0.2551] | 94/72 |
> | 055 `swing` | 4h | INCONCLUSIVE | 61 | -0.0325 | 0.0409 | -0.0734 | [-0.3502, +0.2057] | 32/29 |
>
> `size_skips` is 0 on every row. TRAIN chose **engulfing in 7 of 8** files.
>
> **The finding, and it is a good one for a negative result: the pattern carries
> information, and the cost is the same size.**
> 1. **`055_swing` @1h produced +0.1291 R gross and +0.0296 R net** - cost took
>    0.0995 R, **77% of the gross.** The stop floor of 2.5-5 ATR is what bought
>    that readable gross number; a stop just beyond the candle would have cost
>    ~0.3 R and said nothing. A well-designed experiment that returned a clean
>    negative.
> 2. **The 2.5-5 ATR floor does not make 15m tradeable.** Measured `cost_r` by
>    clock: **15m 0.177-0.213, 30m 0.130-0.142, 1h 0.097-0.100, 4h 0.041.**
>    `LESSONS.md` section 1 predicted 15m would pay ~0.3 R and lose; the ranking
>    was right, the magnitude optimistic.
> 3. **Every long/short split is near-balanced and both legs lose** - this is
>    **not** section 2's long-in-a-bull-market shape. The family is two-sided, so
>    there is no drift to remove, and it is still negative.
> 4. **Only two rows fail just the CI, and both go negative at cost x1.5**
>    (+0.0296 -> **-0.0142**; +0.0159 -> -0.0031). The entire edge is smaller than
>    a 50% worse execution. **The 4h files are the cheapest clock (0.041 R) and
>    the only ones that cannot produce 100 VALID trades** - the same wall as
>    every other round, reached by a different road: **the cheap clock is the
>    illiquid clock.**
>
> Details: Exp 049. ETH half: ETH Exp 015. The ML line (sections 19-21) is closed.

> **ML entry model done (§19, Exp 046): REJECT, 5 of 6 gates failed. `--final`
> not run.** A LightGBM model on 26,000 TRAIN rows, 27 causal features (corrected, Exp 047) and a
> net-of-cost label **cannot time 1h entries better than chance on this coin** —
> and its top feature is volatility.
>
> | | value |
> |---|---|
> | threshold (purged OOF) | **0.0** |
> | TRAIN OOF mean at 0.0 / 0.05 / 0.10 / 0.20 | **−0.0615** / −0.0727 / −0.0843 / −0.1070 |
> | VALID trades / mean R / **gross R** | **12,994 / −0.0299 / +0.0479** |
> | 95% CI (weekly blocks) | [−0.1008, +0.0394] |
> | long / short | +0.0560 / **−0.1037** |
> | cost ×1.5 | **−0.0687** |
> | **one position at a time** | **850 trades, avg R −0.0419, CAGR −15.4%, maxDD 44.3%, win 41.1%, skips 0** |
> | random shift control | mean −0.0573, **p95 +0.0020** |
> | top feature | **`vol_168` (1252)**, then `funding_last` (790) |
> | gates failed | `oof_mean>0`, `valid_mean>0`, `valid_ci_lo>0`, `stress_mean>0`, `beats_random_p95` |
>
> **The OOF curve is monotone *down*, measured on TRAIN before VALID was
> touched: the stricter the threshold, the worse the out-of-fold mean.** That is
> the opposite of a real signal and it is why this is REJECT rather than WATCH —
> the model's top-ranked bars are its worst bars. **The top two features are
> 168-bar volatility and the last funding rate; neither is a direction**, and the
> legs show the trap in both directions (long +0.056, short −0.104).
>
> **Three things worth keeping.**
> 1. **The structure is there and the cost is bigger.** `gross_r` **+0.0479**
>    against `mean_r` **−0.0299** — the label was already net of fees, slippage
>    and funding, so the model was *asked* to find bars worth more than the cost
>    and returned +0.048 R gross and nothing after. `LESSONS.md` §1 in its
>    clearest instance: **+0.0479 R of structure, −0.0778 R of cost.**
> 2. **The sequential number is the tradable one and it is worse:** 850 trades,
>    **CAGR −15.4%, maxDD 44.3%**. The every-signal figure is the research
>    measurement; one position at a time is what an account would face.
> 3. _Corrected in BTC Exp 047: the model did **not** beat the random control
>    (−0.0299 against a p95 of +0.0020; `beats_random_p95` is in the failed list)._
>    **Beating the random control and still losing is a gate working, not a
>    result.** The model clears the drift-adjusted p95 by 0.028 R and is still
>    REJECT. The control removed the "a bull market did this" objection; the
>    other four gates are what refuse the strategy.
>
> **The pooled 20-coin model (§20, `_multi` Exp 005) is the closest anything here
> has come to a PASS and is still REJECT on the CI: +0.0601 R on 34,467 VALID
> trades, gross +0.1475, above its control p95, positive at cost x1.5, 10 of 20
> coins beating their own control — and CI [−0.0373, +0.1698] contains zero.**
> More data fixed the OOF curve (monotone *up*) and did not create an edge.
> Details: Exp 046. ETH half: ETH Exp 010. Exit lab: Exp 043/044.

> **Exit lab done (PLAN.md §18, Exp 043/044): 1h REJECT on both coins, and the
> 4h cell PASSED and is a bull market. `--final` not run.**
> **There is no skill in how a trade is closed.** Six fixed exits on random
> entries (p 0.25, seed 18), each trade simulated on its own with the engine's
> exact rules — **test 14 checks all six trade-for-trade against `run_backtest`,
> max |ΔR| 3e-14**, so these are the engine's numbers.
>
> **1h primary (Exp 043), 6,639 TRAIN / 4,486 VALID trades per exit — REJECT,
> four gates failed** (`train_mean>0`, `valid_mean>0`, `valid_ci_lo>0`,
> `stress_mean>0`):
>
> | exit | TRAIN mean R | gross R | VALID mean R | 95% CI | gross R | long / short | exits |
> |---|---|---|---|---|---|---|---|
> | **`time_only`** *(TRAIN's choice)* | **−0.0214** | +0.0344 | **−0.0792** | **[−0.1179, −0.0406]** | +0.0038 | −0.012 / **−0.147** | time 65% / stop 35% |
> | `tp_1r` | −0.0870 | −0.0035 | −0.1380 | [−0.1661, −0.1095] | −0.0138 | −0.078 / −0.198 | stop 51% / target 48% |
> | `tp_2r` | −0.0968 | −0.0128 | −0.1495 | [−0.2009, −0.0972] | −0.0253 | −0.064 / −0.236 | stop 65% / target 29% |
> | `tp_4r` | −0.0873 | −0.0019 | −0.1027 | [−0.1890, −0.0159] | +0.0222 | +0.028 / −0.234 | stop 71% / time 16% |
> | `be_then_3r` | −0.0905 | −0.0062 | −0.1223 | [−0.1856, −0.0574] | +0.0022 | −0.027 / −0.218 | stop 76% / target 17% |
> | `trail_2atr` | −0.0696 | **+0.0155** | −0.0983 | [−0.1843, −0.0079] | +0.0263 | +0.048 / −0.245 | **stop 99.5%** |
>
> cost x1.5 on the chosen exit: **−0.1206**.
>
> **The 4h cell PASSED all five gates and it is not skill (Exp 044).**
> `trail_2atr` @4h: 1,684 TRAIN / 1,087 VALID trades, mean R **+0.3451**,
> CI **[+0.0265, +0.7471]**, gross +0.4108, cost x1.5 +0.3139 — **long leg
> +0.8140, short leg −0.1333.** BTC rose **466%** over VALID. A 50/50 long-short
> book on a rising market has a positive mean whatever the exit does, and here
> **the exit is losing money on half its trades.** Three further reasons it is not
> evidence: the CI's lower bound is +0.027 against a mean of +0.345 (8% of the
> mean, on the smallest sample in the project); it was never replicated, because
> the plan makes 4h descriptive only; and **the identical exit on the same coin
> one clock down, same seed, same entries, is −0.0983 R.** The exit did not
> change; the drift did.
>
> **What the lab settles, in the order that matters.**
> 1. **The mechanism `PLAN.md` §18 proposed is real and not tradable.** Gross R is
>    positive for three exits on BTC's TRAIN and two on VALID, best **+0.0344 R** —
>    against a 0.05–0.09 R round trip. **Structure exists in the price path; it
>    does not survive the cost of harvesting it at a 1h-to-24h hold.** `LESSONS.md`
>    §1 in its cleanest form: the question was never whether price has structure.
> 2. **A trailing stop is a cost failure, not a logic failure.** `trail_2atr` has
>    the best gross R of the round on both periods, works exactly as designed
>    (**99.5% of exits are the moved stop**), has the lowest turnover of the six —
>    and still loses 0.098 R. **If a trailing stop cannot pay for itself on random
>    1h entries, nothing can.**
> 3. **Near targets are the worst exits and the mix says why.** `tp_1r` and `tp_2r`
>    fill target and stop about half the time each (51/48, 65/29) — **a coin flip
>    paying 1 R against 1 R with two taker fees on top.** On random entries a
>    target is a cost, not a strategy.
> 4. **The short leg is the loser on every row of both coins** (BTC VALID shorts
>    −0.147 to −0.245) — the 50/50 design cancels drift in the mean, and what is
>    left is the exit.
> 5. **TRAIN picked a different exit on each coin** (`time_only` on BTC,
>    `trail_2atr` on ETH) **and it changed nothing.** The selection is not where
>    the failure is.
>
> **Stage 2's premise — a good exit is worth finding before training an entry —
> has no support at 1h on either coin.** Details: Exp 043 (1h), Exp 044 (4h).
> ETH half: ETH Exp 009. Rotation (§17) REJECT; allocation (§16) NO_IMPROVEMENT.

> **Allocation test done (§16): every rule NO_IMPROVEMENT. Next (owner-approved 2026-10-01): rotation across all Binance coins, `docs/research/PLAN.md` §17, `src/rotation.py`.** The record lives in `journal/_multi/`.

> **Next (owner-approved 2026-10-01): the allocation test, `docs/research/PLAN.md` §16.** Run `SYMBOL=BTCUSDT python src/allocation.py` once. Do trend rules (200-day average, golden cross, 20-week breakout) cut buy-and-hold's drawdowns on daily spot (from 2017) and perp bars? Primary coin.

> **Exp 038, review of the metrics round (2026-10-01):** the verdict stands: 0 PASS, the stop rule fired, and no holdout was used. Correction: M1's losing short leg fades a short squeeze (OI falling), not a rally on rising OI. **Noted: `051_retail_crowd_fade @30m` is the project's first configuration with SKILL on two coins.** TRAIN chose the same parameters on both, beta is ~0, it is WATCH + NO_EDGE, and the CI includes 0. **Proposed, waiting for the owner:** freeze it and judge it only on Binance data after 2026-08, with a pass criterion written down before that data is read.

> **Exp 037 — the new-data round M1-M4 is DONE on this coin: 16 evaluations,
> 0 PASS, 7 WATCH (3 SKILL, 4 DRIFT, 7 of 7 NO_EDGE), 4 REJECT, 5 INCONCLUSIVE.
> No holdout was used, because nothing passed.** BTCUSDT now has **250
> evaluations**.
>
> **The answer to the owner's question — does the one data source this project
> had never read carry an edge? — is no.** Open interest and the long/short ratios
> produced 7 positive-but-NO_EDGE configurations. Three of them beat random
> entry timing and all three were dominated by simply holding BTC.
>
> | idea | 15m | 30m | 1h | 4h | verdicts |
> |---|---|---|---|---|---|
> | M1 050 `oi_flush_reversal` | −0.173 | −0.064 | −0.167 | +0.182 | 3 REJ, 1 INC |
> | M2 051 `retail_crowd_fade` | **+0.150** | **+0.106** | **+0.239** | **+0.334** | 3 WATCH, 1 INC |
> | M3 052 `smart_money_divergence` | **+0.109** | **+0.080** | **+0.249** | +0.038 | 3 WATCH, 1 INC |
> | M4 053 `oi_confirmed_breakout` | +0.800 | +0.489 | −0.009 | −0.069 | 1 WATCH, 1 REJ, 2 INC |
>
> **Four findings worth keeping:**
> 1. **M1's short leg is the loser, not its long leg — and my pre-registration
>    asked about the wrong leg.** The long leg after an OI flush is flat to
>    slightly negative (−0.116 to +0.018) and the short leg is **−0.165 to
>    -0.261 at every clock, in 2023 and in 2024**. **Fading a *short squeeze*
>    is the losing trade** — `oi_flush` fires short when price rises while open
>    interest **falls** sharply, i.e. shorts forced out. _Mechanism corrected in
>    Exp 038/039; this line first said "rising" OI, which is the opposite of what
>    the block tests. The measured numbers are unchanged._ That is a new
>    statement:
>    no earlier idea had a column that could tell "a rally on new positions"
>    from "a rally on short covering". M1's TRAIN is negative at all four clocks
>    too, so it is a clean REJECT, not a VALID artefact. It replicates on ETH
>    (short leg −0.278 to −0.010).
> 2. **The paired test came out the way the pre-registration said it would, and
>    that is the round's most important negative result.** M2 "fade the all-account
>    crowd" and M3 "follow the top traders against the crowd" are two different
>    Binance columns and two different stories about who is smarter — **and they
>    are the same trade: be long.** Both have a positive long leg at all four
>    clocks and a negative or flat short leg (M2 long +0.167..+0.609, M3 long
>    +0.251..+0.805, M3 short −0.089..−0.263). The "smart money versus retail"
>    framing is not what is being measured; `LESSONS.md` §2 again, in a data
>    source the project had never read.
> 3. **M4's +0.8000 on 29 trades is 27 long and 2 short** (CI [+0.0803, +1.5880],
>    maxDD 5.6%) and **+0.4892 on 59 trades at 30m** — the two largest VALID
>    numbers of the round, both ~90% long, both under the 100-trade gate, the
>    30m one DRIFT / NO_EDGE, and **both negative on ETH at the same clocks**.
> 4. **Cost: the pre-registered funding worry was the right place to look and it
>    turned out small.** VALID `cost_r` 0.0349–0.1082, median 0.0634, against a
>    fee-only floor of 0.023–0.093 — at 15m the floor is 0.093 and the
>    measurement 0.095, so **funding added ~0.002 R**. The 12–36 h caps are not
>    reached, unlike the port round's 120 h cap. **15m is again the worst clock
>    and the only one above the 0.1 R line, for the seventh time.**
>
> **The data limitation, recorded by owner decision 2026-10-01:**
> `datafeed.py --metrics` prints `METRICS VALIDATION: PROBLEMS FOUND` on both
> coins, because Binance reports `sum_open_interest = 0` on 473 BTC rows (0.075%)
> and 208 ETH rows (0.042%). **No code was changed.** The impact was measured
> rather than assumed: `t_oi_flush` produced 137 / 80 signals on BTC TRAIN 1h
> with the zeros kept and **exactly 137 / 80 with them read as missing — zero
> spurious signals** — because the 720-bar z-score cannot be moved by 11 zeros in
> 26,304 bars. (BTC's 3 missing days from the download were repaired by
> re-fetching those zips; it is now 2,191/2,191 days.) The other limitation is
> structural: **the top-trader columns are 37.6% NaN in this coin's TRAIN and
> 0.013% in VALID** (80.8% and 0.014% on ETH), so M3 is trained on 62% of TRAIN
> here and 19% on ETH while being tested on essentially all of VALID.
>
> Details: `journal/BTCUSDT/experiments.md` Exp 036 (pre-registration) and
> Exp 037 (results). ETH half: ETH Exp 009 / Exp 010.

> **Exp 034 (review, 2026-09-30):** the round's verdict stands. Corrections: the pre-registered cost floor was about 3.5× too low, so the 15m ports died on cost as `LESSONS.md` §1 predicted; T3's cost is fees and slippage, not the time cap; T3's BTC SKILL does not replicate on ETH and leans on 2023.

# BTCUSDT — status and handoff

> **Exp 033 — TradingView port round 1 is DONE on this coin: 24 evaluations,
> 0 PASS, 5 WATCH (2 of them SKILL), 14 REJECT, 5 INCONCLUSIVE. No holdout was
> used, because nothing passed.** The round's own stop rule (`PLAN.md` §13): a
> round with no holdout CONFIRMED ends the TradingView question unless the owner
> brings new scripts. BTCUSDT now has **234 evaluations**.
>
> **The answer to the owner's question — do published TradingView strategies
> survive honest testing? — is no, and not one of the six came close to the
> gates on the timeframe its author published it for.**
>
> | port | TradingView presents it as | BTC best clock | controls |
> |---|---|---|---|
> | T1 044 ChartArt RSI+BB v1.1 | "double strategy", "made more successful in backtesting" | +0.353 on **28** trades, INCONCLUSIVE | — |
> | T2 045 LuxAlgo SMC | a free indicator with alert conditions | +0.219 on 75 trades | **DRIFT** / NO_EDGE |
> | T3 046 ChartArt MACD+SMA200 | trend strategy with a 200-SMA filter | +0.482 on 33 trades; +0.217 on 161 | **SKILL** / **NO_EDGE** |
> | T4 047 Super Scalper | a 5m/15m scalper | **−0.215 on its own 15m chart**; +0.100 on 141 at 4h, 70/71 | **DRIFT** / NO_EDGE |
> | T5 048 ChartArt RSI+BB long-only v1.2 | "long-only made it more successful" | +1.616 on **11** trades, 11 long / 0 short, INCONCLUSIVE | — |
> | T6 049 Liquidity Sweep | intraday session reversal | negative at 15m/30m/1h; +0.077 on 10 trades at 4h | — |
>
> **Three findings worth keeping:**
> 1. **T3 is the only port positive at all four timeframes on BTC** (+0.166,
>    +0.217, +0.251, +0.482) and the only one that reads SKILL — and it is also
>    the most expensive (`cost_r` 0.115–0.151 R, the invented time cap being
>    reached because the reversals do not come on a frequent-signal chart) and it
>    is **NO_EDGE**. A published strategy can be a real timing signal and still
>    not be worth trading. That is the `SKILL + NO_EDGE` shape of BTC 022, which
>    spent a holdout and returned −0.0102 R.
> 2. **T4 works only on a timeframe its author did not publish it for**: negative
>    on the 15m source chart, positive at 4h, and the 4h row is balanced
>    70 long / 71 short. `LESSONS.md` §1's cost rule, showing up again.
> 3. **T5's +1.616 on 11 trades is the largest VALID number in the project and is
>    worthless** — the same-bar RSI+Bollinger coincidence fires 15 times in three
>    years on the 4h chart. Reported because a TradingView screenshot never shows
>    a number that large next to a trade count that small.
>
> **Also confirmed, fifth time on a fresh idea set: 15m is the worst clock and 4h
> the best.** And the pre-registration's cost ceiling was approached rather than
> exceeded (T3 measured 0.115–0.151 R against a predicted 0.048–0.284), which
> validates writing both a floor and a ceiling down before running.
>
> Details: `journal/BTCUSDT/experiments.md` Exp 032 (pre-registration) and
> Exp 033 (results). ETH half: ETH Exp 006 / Exp 007.

> **Exp 030: engine funding fix** (notional × rate; before, funding was ~0). Re-checked on every record: 7 of 242 verdicts change, 6 downward, no new PASS (022 PASS→WATCH).
>
> **CLOSED (Exp 029).** The Round 6 stop rule fired: 208 evaluations, holdout
> 4/4 FAILED, 0 CONFIRMED. Do not add rounds on BTCUSDT. Research continues on
> **ETHUSDT** (`journal/ETHUSDT/STATUS.md`, `docs/research/PLAN.md` §11).

_Last updated: 2026-10-01, after Exp 037 (the new-data round M1–M4 is done on
BTCUSDT — 0 PASS, no holdout used, the open-interest and long/short-ratio
question is closed for these four signals per `PLAN.md` §14's stop rule). Rules
for agents: `AGENTS.md`. Research plan: `docs/research/PLAN.md` (six BTC rounds
done, ports in §13, new data in §14)._

> **Exp 028 — ROUND 6 IS DONE AND THE STOP RULE HAS FIRED. BTCUSDT research
> stops here.** 35 evaluations: 1 PASS, 12 WATCH, 18 REJECT, 4 INCONCLUSIVE.
> Project total **210 evaluations**, 207 idea files. **The holdout has been used
> four times and failed four times. 0 CONFIRMED. Nothing in this project is a
> profitable strategy.**
>
> The rule was written into the Round 6 pre-registration in advance
> (`PLAN.md` §4): *"if Round 6 ends with no holdout `CONFIRMED`, research on
> BTCUSDT stops."* It ended without one, so this is the stopping point the plan
> called for. Do not start a seventh round.
>
> **The one result worth carrying forward is a distinction the earlier rounds
> could not draw, and it comes from 039's holdout:**
>
> | | 038 opening range @4h | **039 breakout + flow @5m** |
> |---|---|---|
> | VALID `gross_r` | +0.197 | +0.242 |
> | HOLDOUT `gross_r` | **−0.090** | **+0.032** |
> | holdout per year | 2025 −0.166, 2026 −0.028 | **2025 +0.0077, 2026 +0.0187** |
> | holdout ×1.5 cost | −0.121 | **+0.0052** |
> | why it failed | the edge was fake | no demonstrable edge (+0.0129 R, CI [−0.158, +0.204]) and **not better than random entries** (random median +0.0380 in the same filters; corrected in Exp 029) |
>
> So (corrected in Exp 029): **no tested entry beats a random entry with the
> same exits once costs are paid.** With a 6% stop and a 96 h hold, being in BTC both ways is cheap
> enough that *any* entry, including a random one, captures the small positive
> drift of holding it. 039 was a PASS, DRIFT, ALPHA, positive at all seven
> clocks, at a **12.5:1 gross-to-cost ratio** - the best ratio in the project -
> and it still failed, for that reason and not because the structure was fake.
>
> **Also settled in Round 6:**
> - **The stop-hunt family is closed (040).** `failed_break` + `flush` fade is
>   negative at all seven clocks, -0.079 to -0.157, a spread of 0.078 R over
>   five years. Both blocks were individually inert on gross; **together they are
>   worse than either alone.** Keep this as a general caution: a combination of
>   two inert blocks is not automatically inert, because the second selects the
>   subset of the first where the first is most wrong.
> - **`ema_cross` + `supertrend_flip` + `di_side` (042) cannot be measured.**
>   152 TRAIN signals, the bare minimum, and four of seven clocks are
>   INCONCLUSIVE on 49-71 VALID trades. The strictness that is the point of the
>   hypothesis is what makes it untestable at this frequency.
> - **041@15m is the only SKILL since 022/023** - valid +0.1738, CI [+0.0041,
>   +0.3510], 88 trades, entry beating random timing on both TRAIN and VALID.
>   It is a **WATCH**, so `--final` is refused; spending a holdout on a WATCH is
>   the owner's decision (`PLAN.md` §5). Its benchmark is NO_EDGE and 2023
>   carries it. **Not my call.**
> - **Round 6 used `cooldown_bars: 0`.** The plan's signal counts were taken that
>   way; Round 5's cooldown of 6 bars was my own addition and it pushed four
>   grid values under the 150-signal floor. With a 48-120 h hold the engine's
>   one-position-at-a-time rule already prevents re-entry, so it adds nothing.
>
> **The best configuration the project ever produced, for the record:**
> **039 `donchian_break(960)` + `taker_flow(n 288, thresh 0.5)` +
> `volume_spike(n 1440, k 1.5)`, 5m clock, 6% stop, no TP, trail armed 2R
> trailing 20.8 ATR, 96 h hold, both directions** (TRAIN 177 trades +0.0351;
> VALID 106 trades `gross_r` +0.2416, `cost_r` 0.0193, mean R **+0.2223**, CI
> [+0.0728, +0.3786], CAGR +10.9%, maxDD 3.4%; HOLDOUT 95 trades, `gross_r`
> **+0.032**, mean R **+0.0129**, CAGR +0.6% - **FAILED**). It is not a strategy:
> the entry does not beat a random one.

> **Round 6 was the last round** (`PLAN.md` §4, Exp 027): five combination ideas, then stop unless one is CONFIRMED (Exp 027).
>
> **Owner decision (2026-09-29): trading only.** The project studies trades that earn from price moves. Funding carry, basis / cash-and-carry and any other strategy that earns the funding fee are **out of scope**: do not propose, build or test them. Funding may still be used as a *signal* or paid as a cost.
>
> **Exp 025 (review of Round 5):** `recipe()` now refuses a trigger that
> returns anything but one -1/0/+1 array (and a filter that is not
> `(long_ok, short_ok)`), and `test_engine.py` checks every block, so the
> `opening_range` tuple bug cannot recur silently. `month_turn_fade` now uses
> the real month length (037's recorded rows predate the fix). Corrections to
> Exp 024 are in `experiments.md` Exp 025. The next direction is the owner's.
>
> **Exp 024 — Round 5 is done, the plan is finished, and the answer did not
> change.** 42 evaluations: 1 PASS, 9 WATCH, 17 REJECT, 15 INCONCLUSIVE. Project
> total **173**.
>
> 1. **A Round 4 bug: `opening_range` traded long-only for all of Exp 022.** It
>    returned a `(long, short)` tuple where every trigger returns one signed
>    array, so `recipe()` read "either side fired" as LONG — 798 valid long
>    trades, **0 short**. Fixed to a single `_side()` call; the corrected idea
>    (038) can now trade both sides. The control verdicts on 029 (DRIFT,
>    NO_EDGE) still stand and the round's conclusion is unchanged, but 029 was
>    never a both-sided result. **Check after adding any block: every trigger
>    returns a 1-D array of 0/+1/-1, every filter returns two boolean arrays.**
> 2. **`--mode time` is the fix for the cost problem of multi-day holds (Exp 025:
>    not for short holds, which still pay ≈ 0.11% of price per trade).**
>    With 4h source files and `--mode time`, `cost_r` is **0.016–0.023 R on all
>    seven timeframes** instead of chart mode's 0.505 R (1m) to 0.019 R (4h) — a
>    26:1 spread becomes 1.4:1. Use it for anything with a multi-day hold.
> 3. **038 (00:00 opening-range break, 4h) was the project's first and only
>    PASS + ALPHA** — valid 155 trades, `gross_r` +0.197 (**+0.99% of price per
>    trade** against a 0.11% cost), 77 long / 78 short, **beta +0.01**, alpha
>    +10.2%/yr CI [+1.4, +18.3]. **It FAILED the holdout**: 135 trades,
>    `gross_r` **−0.090**, mean R −0.1118, CAGR −6.4%. The gross edge was
>    2023-24. **The holdout is now used three times and has failed three times.**
> 4. **DRIFT and ALPHA at the same time is the project's sharpest result.** 038's
>    entry has no timing skill (TRAIN −0.005, below random entries' 95th pct
>    +0.107) and its return is not BTC's direction (beta 0.01) — yet it made
>    money on VALID. The only remaining mechanism is *being in the market with a
>    cheap cost structure*, which is an exposure decision, not an edge.
> 5. **Mean reversion is refuted at a real horizon too.** 034 (z-score over 5-10
>    days) had the best reversion gross measured here (+0.32% of price vs 0.108%
>    cost) and went to VALID at **−0.098**, REJECT at all seven timeframes.
> 6. **Funding carry (033) is INCONCLUSIVE, not refuted** — the one hypothesis
>    left untested. A 96h hold plus a 0.015%-per-8h funding threshold cannot reach 100
>    VALID trades. It earns from funding rather than from price, and measuring it
>    needs a different instrument, not another idea file.
> 7. **Turn-of-month fade (037, my own idea) is unmeasurable in this design**,
>    not rejected: a 5-day calendar window and a 96h hold leave under 30 VALID
>    trades.
>
> **Nothing in this project is a profitable strategy and the holdout has never
> confirmed anything.** Read `journal/BTCUSDT/FINAL_REPORT.md` §7.

> **Exp 017 — read before anything below.** All 5 Round 1 WATCHes (018@30m,
> 018@1h, 019@30m, 019@1h, 017@1h) are **DRIFT**: random long entries inside
> the same trend filters, with the same exits, earn about the same (median
> +0.05..+0.10 R on VALID, and 25–80% of random runs match or beat the idea).
> The profits came from being long while BTC trended up in 2023–24, not from
> the entries. Every WATCH/PASS must now pass `src/baseline.py` (SKILL), and
> `evaluate.py --final` refuses without it. Details: `experiments.md` Exp 017,
> `journal/BTCUSDT/baselines.md`.
>
> **Exp 019 (after Round 2):** Round 2's idea 022 was the first PASS; it spent the
> holdout and FAILED (−0.010 R). `baseline.py` SKILL now needs TRAIN *and* VALID
> (under that rule 022 is DRIFT), and `--final` also runs a random-entry control
> on the holdout (CONFIRMED must beat its median). **Journal numbering:** the two
> Round 2 entries headed "Exp 017" are 017b/017c; the next entry is **Exp 020**.
>
> **Exp 018:** Round 3 (PLAN.md) now asks "when to be long BTC" and judges ideas
> against **buy & hold** with `src/benchmark.py` (alpha, Sharpe, drawdown).
> 018@30m and 019@1h: alpha ≈ 0, Sharpe below buy & hold → NO_EDGE.
>
> **STOP — the only PASS in 61 evaluations failed its holdout.** Idea 022
> (018@30m's entry, risk side) changed one thing: the stop from 2.83% of price
> to **1.0%**. That passed every VALID gate — 258 trades, gross +0.334,
> cost 0.106, mean R **+0.2276**, CI [+0.002, +0.468], CAGR +30.5%, maxDD 12.7%
> — and `baseline.py` said **SKILL** (0% of random runs beat it). On the locked
> HOLDOUT 2025-01..2026-08: **−0.0102 R**, CI [−0.202, +0.199], gross
> **+0.098** against cost 0.108. **FAILED**, holdout spent, and the structure is
> also at `EVAL_MAX_VERSIONS`. **Do not make a copy of it for another try.**
> The mechanism is understood: a 1% stop makes the R unit 2.8x smaller, so the
> same price move scores 2.8x more R and `gross_r` went 0.145 → 0.334 without
> any new information. VALID was carried by 2023 (+0.3496) over 2024 (+0.1355),
> and a CI lower bound of +0.0023 is indistinguishable from zero. See
> `experiments.md` Exp 017.
>
> **Exp 020 (Round 3) - the headline answer to the project's question.**
> 35 evaluations on "when to be in BTC", 13 `baseline.py` + 13 `benchmark.py`
> runs. **Two PASSes** - 023 (long/flat regime, 1h: valid +0.1148, CI
> [+0.014, +0.220], cost_r **0.022**, maxDD 4.8%) and 027 (multi-day pullback,
> 30m: valid +0.1967, CI [+0.025, +0.373], cost_r 0.036) - and **every
> `benchmark.py` run in the project is NO_EDGE: 20 of 20** (Exp 021 correction; Exp 020 said 21). No configuration has
> alpha and none is RISK_EDGE. **No tested timing rule beats simply holding BTC
> after costs.** 027 is DRIFT (its TRAIN sits below random entries, caught by
> the Exp 019 tightening); 023 is NO_EDGE by its own benchmark, Sharpe 1.59
> against buy & hold's 2.01 on VALID despite a sixth of its drawdown. The
> holdout was **not** spent - see the owner question in `experiments.md`
> Exp 020.
>
> **Exp 021 (review of Round 3) - owner decision: 023 does NOT go to the
> holdout.** A regime rule (`trend_state`) now needs benchmark **ALPHA** for
> `--final`; SKILL does not count for it, and `evaluate.py` enforces this.
> New verdict **`UNSIZABLE`**: any `size_skips` on TRAIN or VALID (the 1,000
> USDT account could not size a signal) turns PASS/WATCH/INCONCLUSIVE into
> UNSIZABLE. The four Round 3 4h variants (023/025/026/027@4h, 20% stops,
> sizable only below BTC 50,000) and 019@4h are UNSIZABLE, not evidence.
> Benchmark count corrected: **20/20** NO_EDGE. `tf_variants.py` now warns when
> a stop is too wide to size. **Next: Round 4.**

## Where things stand

- **Round 1 is done: 40 evaluations, 0 PASS, 5 WATCH, 29 REJECT, 6 INCONCLUSIVE.**
  Project total 58. Pre-registration and full results: `experiments.md` Exp 016.
- **Round 2 is done: 2 evaluations, 1 WATCH (DRIFT/NO_EDGE), 1 PASS whose holdout
  FAILED.** Details: `experiments.md` Exp 017.
- **Round 3 is done: 35 evaluations, 2 PASS, 11 WATCH, 19 REJECT, 3 INCONCLUSIVE.**
  Project total 96. **Answer: no timing rule beats holding BTC.** Every
  `benchmark.py` run in the project is NO_EDGE (20/20; Exp 020 said 21).
  The 4h variants are UNSIZABLE (Exp 021). Details: Exp 020, Exp 021.
- **Round 4 is done: 35 evaluations, 1 PASS, 1 WATCH, 33 REJECT.** Four new
  Level 2 blocks built for it (`prev_day_break`, `opening_range`, `keltner_break`,
  `flush`) plus the `funding_window` filter. The round's PASS (029 opening range
  at 4h, valid +0.1131, CI [+0.006, +0.223]) is **DRIFT** and NO_EDGE, so
  `--final` refused it. `flush` failed on **gross** in both follow and fade
  modes, which closes the liquidation-cascade family. Details: Exp 022.
- **Round 5 is done: 42 evaluations, 1 PASS, 9 WATCH, 17 REJECT, 15
  INCONCLUSIVE.** 4h source files with `--mode time` variants, 4-7% stops,
  48-120h holds, both directions, no directional filter. The design worked
  (`cost_r` flat at 0.016-0.023 R on all seven timeframes) and the answer did
  not: the round's PASS was the project's first PASS + ALPHA (beta +0.01, alpha
  +10.2%/yr) and it **FAILED the holdout with a negative gross**. Details:
  `experiments.md` Exp 024.
- **Round 6 is done: 35 evaluations, 1 PASS, 12 WATCH, 18 REJECT, 4
  INCONCLUSIVE.** Five untested block combinations, cost-first. One clean family
  kill (040, stop-hunt, negative at all seven clocks), one untestable-by-
  construction (042), one PASS (039) that **failed the holdout with a positive
  gross** and the project's first-ever 12.5:1 gross-to-cost ratio. Details:
  `experiments.md` Exp 028.
- 🏁 **The plan is complete and the stop rule has fired. Read
  `journal/BTCUSDT/FINAL_REPORT.md`.** Project total **210 evaluations**, 207
  idea files, all 7 native timeframes. 7 distinct configurations have read
  PASS, **0 CONFIRMED**, holdout used four times and FAILED all four. The
  answer: **no tested technique on BTCUSDT at VIP0 costs has an edge that
  survives a random-entry control and a buy-and-hold benchmark.**
- **The cost finding holds and is the most reusable thing here.** Every long
  structure tested is negative at 1m/3m/5m and positive at 30m/1h/4h, on TRAIN
  as well as on VALID, for two different entries. The cause is measured, not
  guessed:
  `cost_r` is **0.505 R on 1m** and **0.019 R on 4h** for the same 0.09% round
  trip, because `tf_variants` chart mode scales the `pct` stop by sqrt(tf/15).
  A low-timeframe REJECT in this project is that arithmetic, not a verdict on
  the hypothesis.

- **The engine is fixed (Exp 015).** Two defects were found and repaired:
  1. **Short P&L had the wrong sign** (found by the agent in Exp 014). Every
     short trade in the project's history was booked inverted.
  2. **A 100 USDT account couldn't size most trades** at BTC's 0.001 qty step
     once BTC was above ~50k, so trades were silently skipped, and skipped
     *more* as a strategy lost money. `evaluate.py` now uses a 1,000 USDT
     research account (`C.EVAL_EQUITY`, owner-approved; still 1% risk per
     trade), and the engine reports `size_skips` (0 in every Round 1 report).
- **All 18 earlier ideas were re-evaluated** on the fixed engine:
  **0 PASS, 0 WATCH, 16 REJECT, 2 INCONCLUSIVE.** The old records are kept,
  unchanged, in `results/BTCUSDT/legacy/pre_signfix/`.
- **HOLDOUT 2025-01..2026-08:** used once only, by `example_trend_breakout`
  (the lock test in Exp 011). Every other config's holdout is untouched.

## What the corrected results say (Exp 015)

| finding | evidence |
|---|---|
| **Shorting breakouts loses, significantly.** All 7 short-only ideas (008–012, 014, 015) are negative on VALID; 6 of 7 have the whole 95% CI below zero | e.g. 010: valid −0.120 R, CI [−0.206, −0.027], 339 trades |
| When TRAIN may choose the direction, it now **picks long** | 007: direction grid → long; train −0.031, valid +0.051 (418 trades) |
| **The only leads** (none passes) | **005** session-open range break, both sides: train **+0.079**, valid **+0.067** on 390 trades, CI [−0.079, +0.214]; fails the ×1.5 cost gate (−0.002). **006** long-only 30m EMA cross: valid +0.136 on 52 trades (too few), train +0.002 |
| Mean reversion (long 016, example range reversion) | negative on VALID |
| Squeeze → expansion (004, 013) | negative on VALID |

## What is settled (reusable, any symbol)

- **A stop must be a price distance, not an ATR multiple.** `cost_r =
  round_trip_cost / stop_pct`; an ATR stop makes cost_r follow the
  volatility regime (Exp 012). Use `"stop": {"type": "pct", ...}`.
- **Use `tf_variants.py --mode time` for anything with a multi-day hold**
  (Exp 024). It keeps the stop's % of price and the hold's hours constant across
  timeframes, so `cost_r` is comparable and a fine entry clock can be tested at
  all. Chart mode rescales the stop and makes 1m variants lose on arithmetic
  (0.505 R) rather than on the hypothesis.
- **A big gross-to-cost ratio is not protection** (Exp 024). 038 had gross
  +0.99% of price against 0.11% cost, a 9:1 ratio, and its `gross_r` went
  +0.197 on VALID to **−0.090** on the holdout. Compare per-year splits before
  believing a gross edge.
- **Never compare `gross_r` across stop widths.** Compare net mean R.
- **Post-only entry** cuts the round trip from 0.14% to 0.09% of price at
  80–95% fill. The per-idea benefit in R must be re-measured on the fixed engine.
- **Trade count decides whether anything can PASS**: mean R must exceed
  ≈ 1.568/√n (PLAN.md §2a). Design ideas for ≥ 300 valid trades.
- **The research account must be able to size every trade**; check
  `size_skips` = 0 in every evaluation report.

## Best configuration so far (Exp 016, idea 018 at 30m) — WATCH

30m, `donchian_break(24)` + `htf_trend(50,4)` + `adx_min(20)`, **long only**,
`pct` stop 2.83% (ATR clamp 1.5–8.0), no TP, ATR trail armed 1.5R trailing
2.5 ATR, 24h time stop, post-only entry at 0.1 ATR.

| split | trades | gross_r | cost_r | mean R | 95% CI | CAGR | maxDD |
|---|---|---|---|---|---|---|---|
| train 2020-2022 | 347 | | | +0.0612 | | | |
| valid 2023-2024 | 234 | +0.1451 | 0.0427 | **+0.1024** | [−0.031, +0.243] | +11.5% | 9.8% |
| valid ×1.5 cost | | | | +0.0849 | | | |

Fails **exactly one** gate, `valid_ci_lo > 0`, and misses it by 0.0001: PASS at
n=234 needs mean R > 1.568/√234 = 0.1025. Win 48.3%, PF 1.28, `size_skips` 0.
Neighbouring timeframes agree (1h: train +0.099 / valid +0.110; 4h: +0.058 /
+0.532 but on 37 trades), which is the robustness test the plan asks for.
**Not a strategy, and nothing here has seen the holdout.** Its exits are inert
— TP 0%, time exit 69%, average hold 20.8h — which is what Round 2 studies.

## Which files can be trusted

| file | status |
|---|---|
| `results/BTCUSDT/evaluations.csv`, `eval_trades/`, `journal/BTCUSDT/evaluations.md` | ✅ fixed engine, native data, 1,000 USDT research account |
| `results/BTCUSDT/holdout_log.csv` | ✅ (one old row: the example's holdout, consumed under the old engine; the lock still applies) |
| `results/BTCUSDT/legacy/pre_signfix/` | ❌ Exp 011–014 records: short P&L inverted and 100 USDT sizing. History only |
| `results/BTCUSDT/legacy/*` (Exp 003–010) | ❌ shifted data, short sign bug, and 100 USDT sizing. History only |
| `journal/BTCUSDT/experiments.md` Exp 003–014 | the reasoning is history; **any number involving shorts before Exp 015 is wrong** |

## Known issues (low priority)

1. The legacy scripts (`sweep.py`, `run_ml.py`, `definitive.py`, …) still size
   with the 100 USDT `INITIAL_EQUITY`. Don't use them for new research; use
   `evaluate.py`.
2. `report.html` is pre-fix history.
3. Data is not in git: run `python src/datafeed.py` after cloning (≈ 3 min,
   needs `data.binance.vision`).

## Next step

**None, on this market. The stop rule agreed in the Round 6 pre-registration
has fired:** `PLAN.md` §4 says research on BTCUSDT stops when Round 6 ends
without a holdout CONFIRMED. It did. 210 evaluations, 7 configurations ever read
PASS, 0 CONFIRMED, holdout spent four times and failed four times. The
deliverable is `journal/BTCUSDT/FINAL_REPORT.md`; its §9 lists what would count
as new information. **Do not start a seventh round.**

**Owner decision (2026-09-29): trading only.** The project studies trades that earn from price moves. Funding carry, basis / cash-and-carry and any other strategy that earns the funding fee are **out of scope**: do not propose, build or test them. Funding may still be used as a *signal* or paid as a cost. This closes what Exp 024 left open.

The evidence is consistent rather than inconclusive, and it says something more specific than "no edge":
- cost is the first-order term and it is a **design choice**, not a fate (`--mode time` + a 6% stop puts `cost_r` at ~0.02 R on every timeframe);
- with cost solved, several both-sided multi-day structures produce a **real** positive gross move — 039's held on unseen data, in both holdout years, through a ×1.5 cost stress, at 12.5:1 gross-to-cost;
- and **none of them has timing skill**: random entries with the same stop, hold and filters do as well or better.

So the value is not in the entry, and this harness cannot test where it would be instead — that is execution and position sizing, not a trading technique.

Two things to raise with the owner 🛑 (neither is mine to decide):
1. **041@15m is the only SKILL since 022/023** — `momentum` +
   `funding_not_crowded` + `volume_spike`, valid +0.1738, CI [+0.0041, +0.3510],
   88 trades, and the entry beat random timing on **both** TRAIN and VALID. It is
   a WATCH, so `--final` refuses it; `PLAN.md` §5 reserves spending a holdout on
   a WATCH for the owner. Its benchmark is NO_EDGE and 2023 carries it (+0.2815
   on 41 trades against +0.08 on 47). I did not run it and I do not recommend
   it: the prior from 022, 038 and 039 is that a WATCH's VALID does not survive.
2. **A different coin, or a different market.** Every finding here is specific
   to BTCUSDT at VIP0 costs, and BTC is the most arbitraged market in
   existence. The harness transfers unchanged. Adding a symbol to
   `SYMBOL_SPECS` is a Level 3 change and needs the owner's approval.

Never build a weekday or session-hour filter, never retry mean reversion,
squeeze→expansion, funding crowding, `taker_flow`/`funding_not_crowded`, any
short-only breakout, or any long Donchian/pullback entry on 15m-30m.

**Exp 024 update to that ban.** Exp 016's mean-reversion and funding-crowding
bans were measured at ≤ 16h holds, where the gross move was under the cost.
Round 5 retested both at the horizon where that objection does not apply and
both are now closed for real: multi-day mean reversion (034) is REJECT at all
seven timeframes despite a 3:1 gross-to-cost ratio, and funding carry (033) is
INCONCLUSIVE because the sample cannot be built. Turn-of-month fade (037) is
unmeasurable in this design. **Do not add a sixth round on BTCUSDT.**

**Exp 027 — owner decision: Round 6 is approved** (`PLAN.md` §4, Round 6):
five combination ideas with Round 5's cost design, hard-capped, and with a
stop rule agreed in advance. If Round 6 ends with no holdout CONFIRMED,
BTCUSDT research stops.

**Exp 028 — Round 6 is done, and the stop rule fired.** The ban above is now
also backed by Round 6:
- **The stop-hunt family is closed.** `failed_break` + `flush` fade (040) is
  negative at all seven clocks (−0.079 to −0.157, spread 0.078 R over five
  years). Both blocks were individually inert on gross; together they are
  *worse* than either alone. The general lesson, worth keeping: a combination of
  two inert blocks is not automatically inert, because the second block selects
  the subset of the first where the first is most wrong.
- **`taker_flow` and `funding_not_crowded` are no longer banned** — Round 6
  lifted that ban to test them both-sided at a multi-day hold, and they are the
  two ideas that produced Round 6's only PASS and its only SKILL. The old ban
  was a 15m short-only artefact and does not apply at this horizon.
- `ema_cross` + `supertrend_flip` + `di_side` (042) is too rare to measure, not
  refuted: 152 TRAIN signals, four of seven clocks INCONCLUSIVE on 49-71 VALID
  trades. Do not retry it with a looser confirmation - the strictness is the
  hypothesis.

**No further round on BTCUSDT.** The plan's six rounds are done and the stop
rule has fired.

> **Allocation test (PLAN.md section 16, 2026-10-01):** all rules, spot and perp, NO_IMPROVEMENT vs buy-and-hold (Exp 041; `journal/BTCUSDT/allocation.md`). 

> **Allocation test rerun (PLAN.md section 16, 2026-10-01):** after the liquidation fix every rule is still NO_IMPROVEMENT; spot identical to the first run, perp changed only for buy_hold (Exp 042).
