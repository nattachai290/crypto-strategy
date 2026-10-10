# AGENTS.md — rules for any AI agent working in this repo

**Read this whole file before doing anything.** Then read
`docs/research/TECHNIQUES.md` (what to try) and `journal/<SYMBOL>/STATUS.md`
(where the coin stands). `BTCUSDT` is **closed** (Exp 029: 208 evaluations,
holdout 4/4 FAILED) and `ETHUSDT` is **closed** (ETH Exp 003: 0 PASS).
`SOLUSDT` and `BNBUSDT` are **closed** too (SOL Exp 005, BNB Exp 003).
**No active work.** The Coinbase premium confirmation (§26, `_multi` Exp
011/012) is NOT_CONFIRMED: 30m does not carry to other coins; 4h is positive
pooled but failed breadth and is weak on TRAIN. The owner decided (2026-10-02,
`_multi` Exp 013) **not** to spend the holdout on it: the premium lead is closed
and the holdout stays untouched. §27 (`ml_hold.py`) was run: REJECT (`_multi` Exp 016/017).
§28 (`ml_wf.py`, walk-forward multi-timeframe ML) was run: REJECT on 1h/4h/1d
(`_multi` Exp 022/023). §29 (`ml_wf2.py`) was run: REJECT, but its universe rule left 4 coins (`_multi`
Exp 025/026). PLAN.md §30 (`src/ml_wf3.py`, §28's 47 coins each with its own
spot history spliced on before the perp start, owner request 2026-10-03) was run
as re-registered in `_multi` Exp 029 and came out in `_multi` Exp 030:
**REJECT on 1h/4h/1d, no holdout spent.** 1h is the closest ML result in this
project and misses **one** gate — mean +0.0374 R, gross 2.9x cost, both legs
positive, breadth 34/47, timing 4x the shifted p95, still +0.0332 without the
five largest trades, but the 95% CI is [-0.0235, +0.1006]. 4h and 1d went
backwards against §28 (`_multi` Exp 030/031). PLAN.md §31 (`src/ml_port.py`, a
one-account portfolio layer on §30's frozen 1h model: 4h agreement, confidence
sizing, 5% cap per direction) was run as pre-registered in `_multi` Exp 032 and
came out in `_multi` Exp 033: **REJECT on `valid_ci_lo>0` again, no holdout
spent.** It is a real improvement - 1,588 trades at mean +0.0608 R (gross 3.9x
cost), both legs up, 2023 positive for the first time, breadth 28/46, timing
4.4x the shifted p95, max drawdown 19.77% - and the weekly CI narrowed 10.8x with
its lower bound at **-0.00026**. The risk finding matters more than the number:
uncapped, §30's 1h book loses 150% on TRAIN; capped it does not.
The planner's review (`_multi` Exp 034) corrected two points: the "10.8x" compares a per-trade CI with a weekly one, and the return is concentrated (best 5 of 105 weeks = 67%; 2023 without its best 3 weeks is -0.079). PLAN.md §32 (`src/ml_xs.py`, §31's account with market-demeaned forecasts) was run as pre-registered in `_multi` Exp 035 and came out in `_multi` Exp 036: **REJECT on `train_chose_demean` + `valid_ci_lo>0`, no holdout spent.** TRAIN chose `raw`, so §32's VALID row is §31's row (the two trade files are identical — no new look at VALID). All 12 demeaned TRAIN cells are far worse than all 12 raw ones (mean R +0.0597 -> +0.0095 at best; best t +2.40 -> +0.63). **The decisive number: §31's capped account has beta -0.05 and correlation -0.17 to the equal-weight market — it was already market-neutral, so there was no market-wide part left to remove.** The planner's review (`_multi` Exp 037) corrects the "market-neutral" reading: 89% of a week's trades are on one side and the best weeks are one-sided shorts, so the book is a market TIMER whose side changes (hence beta near 0). PLAN.md §33 (`src/ml_mkt.py`, the 47-coin mean forecast traded on BTC/ETH only) was run as pre-registered in `_multi` Exp 038 and came out in `_multi` Exp 039: **REJECT on `valid_ci_lo>0`, `timing_beats_shift_p95`, `both_legs>0`, no holdout spent.** It was dead on TRAIN, not on VALID: 5 of 6 cells lost money and the chosen one (ETH + 4h) made +0.00004 a week at t +0.05. VALID: 98 trades, weekly +0.00037, CI [-0.00111, +0.00190], the long leg LOST (-0.0398) while shorts made +0.0782, the best 5 of 105 weeks are 298% of the return (without them -0.0821), and beta to buy-and-hold is -0.006. **Conclusion: §30's signal is profitable spread over ~40 alt-coins under the cap (§31), and is not profitable concentrated into one BTC/ETH call.** The best book here is still the frozen §31 cell, a REJECT by 0.00026. The planner's review of §33 is `_multi` Exp 040. The owner chose new data over spending the holdout (a power estimate put a CONFIRM at about 39% even if §31's edge were fully real). PLAN.md §34 (`src/ml_flow.py`, positioning features for the 1h model on §31's account) was run as pre-registered in `_multi` Exp 041 and came out in `_multi` Exp 042: **REJECT on `train_chose_flow` + `valid_ci_lo>0`, no holdout spent.** TRAIN chose `base`, so §34's VALID row is §31's row (identical trade files — no new look at VALID). Flow is behind on every TRAIN measure (1,882 vs 2,425 trades, weekly +0.00445 vs +0.00694, t +1.52 vs +2.40, mean R +0.0525 vs +0.0597); the gap is -64% in 2021 (metrics only start 2021-12-01) and **-11% in 2022**, the fully covered year. **The flow features carry 45% of the model's gain and the book is still worse — usage is not usefulness.** Caveat: metrics cover only 13 of TRAIN's 24 months (HNT 498 days, TOMO 732), so the claim is "no positioning edge visible in 2021-22 data", not "no positioning edge". Four rounds (§31–§34) now end at the same frozen §31 cell (planner's review: `_multi` Exp 043). The owner chose a **new family** over the holdout. PLAN.md §35 (`src/listing.py`, short every newly listed USDT-M perp) was run as pre-registered in `_multi` Exp 044 and came out in `_multi` Exp 045: **REJECT on five gates, no holdout spent.** TRAIN looked good (85 listings, all 12 cells positive, chosen delay 1 / stop 0.3 / trail 0.6, event mean +0.3586 R against a control p95 of +0.1386). VALID reversed: 228 of 228 listings traded, mean **-0.1586 R** (gross -0.1776, funding +0.0258), total **-9.0%**, both years negative (-0.164 2023, -0.154 2024). **The shape is the finding: 48.7% of shorts stopped out at -1.01 R within 15 days, while the winners took 98 days for +0.48 R** - many small fast losses, few slow ones; without the 5 best trades it is -0.2237. New tokens lost a quarter of what established tokens lost (-0.071 vs -0.267). The VALID control "passed" only because established perps lost 0.374 R that period. **The listing family's own holdout is untouched and holds 467 events.** The planner's review (`_multi` Exp 046) corrects the control reading: a control mean of -0.439 R means established perps ROSE; new listings underperformed them by about 0.3 R in both periods, and only the absolute short failed. The owner's frame (2026-10-04): the goal is an ML model that trades, and it will trade only the top 20 large coins. A data-gap bug was found (SOL/XRP/LTC daily files miss 2022-02-26..28, so `split_instruments` dropped them from every `select_universe` universe; `_multi` Exp 047 note). PLAN.md §36 as re-registered in `_multi` Exp 048 (`src/ml_wide.py`: train wide + horizon ensemble; trade only the owner's large coins = crypto, listed >= 1 year, monthly top 20 by prior-30-day volume; sets per symbol, which fixes the gap bug) was run once and came out in `_multi` Exp 050: **REJECT on `valid_ci_lo>0` + `max_dd<=0.2`, no holdout spent.** TRAIN chose `wide` (gate `train_chose_wide` passed): 425 training coins (47 core + 378), 145 ever in a traded set, 86 traded in VALID, 1,165 trades. TRAIN more than doubled the per-trade result over §30's recipe (mean R +0.0977 vs narrow's +0.0412, t +2.62 vs +1.54). **But the VALID forecast/label correlation did not rise: wide +0.0307 vs narrow +0.0314 — the book got bigger, the signal did not get sharper.** VALID: weekly +0.00486, CI [-0.00103, +0.01086], t +1.62, mean R +0.0829, long +0.1172 / short +0.3928, cost x1.5 +0.00422, timing 3.7x the shifted p95, breadth 19/36, max DD 20.01%, both years positive. **More concentrated than §31: the best 5 of 105 weeks are 87% of the return; without them 1,103 trades average +0.0089 R.** Every check passes on TRAIN (`train_checks`) and only the CI and the DD fail on VALID. Analyzer: **FRAGILE, quality 83 vs §31's 86** — §36 is the project's best on train-vs-valid (VALID mean R is 85% of TRAIN) but worst of the line on stability (56.7 vs 74.8). **Trading only large coins did not raise the ceiling** (86 coins at +0.00486/week vs §31's 46 at +0.00548; BTC and BNB both lose), so the best book here is still the frozen §31 cell. The owner then chose to trade only BNB, BTC, ETH, XRP, SOL, DOGE, ADA, LINK, NEAR, BCH (training on any coin); §36's recorded trades on these ten made +0.00069 a week (t +0.50) with a zero short leg (`_multi` Exp 052). PLAN.md §37 as pre-registered in `_multi` Exp 053 (`src/ml_large.py`: 4h decisions, trained wide, horizon sets 1-3d / 2-6d x 1d agreement off/on, the ten coins only; no new download) was run once and came out in `_multi` Exp 054: **REJECT on `valid_ci_lo>0` + `timing_beats_shift_p95` + `both_legs>0`, no holdout spent.** TRAIN chose `1-3d_off` (4h, 6/12/18 bars, agreement off); **all four TRAIN cells were positive** (235-423 trades, mean R +0.118 to +0.210, t +1.83 to +2.22) and TRAIN's own checks all passed (CI +0.00046, both legs up, timing 2.9x its shifted p95, breadth 10/10, DD 5.9%) - the pre-registered "REJECT with a positive TRAIN" outcome. VALID was a long-only book in substance: 417 trades, weekly +0.00095, CI [-0.00312, +0.00572] (the widest of the three), t +0.41, mean R +0.0592, **long +0.2013 but the short leg LOST -0.1018** (112 longs, 305 shorts), cost x1.5 +0.00081, timing only 0.67x the shifted p95, breadth 7/10 (best of the three), **max DD 13.65% (the lowest - 4h bars and an 8-ATR 4h stop take fewer, larger stops, so sizing/risk, not signal, is what put §31/§36 on the 20% line)**. **The decisive diagnostic: the best 5 of 105 weeks are 3.87x the whole VALID return; without them the weekly mean is -0.00286.** XRP +0.402 R and ADA +0.243 carry it; BNB -0.094 and NEAR -0.113 lose. Analyzer: **FRAGILE, quality 68 - the lowest of the three** (§31 86, §36 83), below them on every dimension (train-vs-valid 72 vs 100/100, robustness 40 vs 80/80, stability 33.3 vs 74.8/56.7). **The ten large coins do not carry this model's forecastable 1-6-day move out of sample**, and the 4h model is not better than the 1h line on the same coins (+0.00095 vs +0.00069 a week). The best book here is still the frozen §31 cell. The planner's diagnostic (`_multi` Exp 059): every ML book of §28–§37 leaned short (57–78%) in 2023–24 after 2022 entered training, so the owner chose recency weighting + a TRAIN rule needing both years and both legs. PLAN.md §38 as pre-registered in `_multi` Exp 060 (`src/ml_recent.py`: §37's frozen cell as 1h / 4h / 1d sub-models, training rows weighted expanding / 12-month half-life / 24-month window; no new download; writes the `run_record` files) was run once per sub-model and came out in `_multi` Exp 061: **all three REJECT, no holdout spent** (1h failed 5 gates, 4h 2, 1d 7). The 4h `expanding` row reproduced §37 exactly (423 trades, t +2.22). **1h → REJECT** (no weighting selectable, fell back to `expanding`): 1,107 trades, weekly +0.00178, CI [-0.00412, +0.00755], mean R +0.0264, long +0.2014 / short **-0.0149**, max DD 27.88%. **4h → REJECT** (all three selectable, picked `hl12` at t +2.70): 441 trades, weekly +0.00120, CI [-0.00230, +0.00486], mean R +0.0497, long +0.1503 / short **-0.0246**, cost ×1.5 +0.00106, timing 2.96x the shifted p95, breadth 6/10, **max DD 10.75%** — the best large-coin book of the four on weekly mean, CI width and drawdown, failing only the CI and the short leg. **1d → REJECT** (nothing selectable, fell back to `roll24`; VALID lost money: 286 trades, weekly -0.00112, t -1.33, mean R -0.0809, breadth 0/10). **The short share did fall — the diagnosis was right and the fix was not enough:** 4h went from §37's 0.69/0.76 to **0.55/0.64**, but the short leg still lost. Recency weighting was actively harmful on 1h (TRAIN mean R +0.0363 expanding vs -0.0074 hl12 vs -0.0134 roll24). Analyzer: **4h FRAGILE 59, 1h FRAGILE 48, 1d OVERFIT 10** (§31 86, §36 83, §37 68). **`weekday` is in the top-10 features by mean |SHAP| on all three** (rank 7/10/9) but is never the strongest — BTC 168-bar volatility leads everywhere. **No sub-model is PASS, so under the pre-registered rule none would take the holdout** (`holdout_pick` returns None). The best book here is still the frozen §31 cell. The planner's review (`_multi` Exp 062) used the first per-bar forecasts: the 4h model ranks bars correctly in all four years (Q5-Q1 +0.15/+0.19 TRAIN, +0.40/+0.26 VALID) but its level drifts negative with the last regime, so the sign-based policy takes the wrong side. PLAN.md §39 as pre-registered in `_multi` Exp 063 (`src/ml_rank.py`: §38's 4h hl12 forecasts fed to the policy raw / minus a causal 30-day median / minus a 90-day median; no new download) was run once and came out in `_multi` Exp 064: **REJECT on `train_chose_centered` + `valid_ci_lo>0` + `both_legs>0`, no holdout spent.** The `raw` row reproduced §38 4h hl12 exactly (394 trades, t +2.70). **TRAIN kept `raw`: centring removed the level drift it was built to remove and the edge went with it.** TRAIN: raw 394 trades t +2.70 mean R +0.1757 maxDD 4.06%; med30 395 trades t +1.92 mean R +0.1338 maxDD 9.47%; med90 375 trades t +2.00 mean R +0.1219 maxDD 8.76% and **not selectable** (long leg -0.0168). The mean x column is the finding: `raw`'s forecast level went negative in 2022 (-0.2764) while `med30`'s stayed +0.0155 — **and 2022's return fell from +0.2483 to +0.1088, so the level shift was information, not bias.** Centred books also shorted more (2021 short share 0.538/0.678 vs raw's 0.359). **VALID is §38 4h's book unchanged** (TRAIN chose the baseline, so no new VALID look): 441 trades, weekly +0.00120, CI [-0.00230, +0.00486], mean R +0.0497, long +0.1503 / short -0.0246, max DD 10.75%, breadth 6/10, best-5-week share 1.92x. **Short share unchanged at 0.549 / 0.642** against §38 4h (the same book) and §37's 0.69 / 0.76. Analyzer: **FRAGILE, quality 69 vs §38 4h's 59 and §31's 86** — the +10 is entirely the sensitivity dimension (3 cells vs a weighting sweep); every other dimension is identical to §38's because the VALID book is the same one. **Conclusion: the forecast's level drift is not a bias to remove; it is what produced §38 4h's return.** The planner's review (`_multi` Exp 065) agrees: the large-coin direction forecasts are a lagging regime signal. PLAN.md §40 as pre-registered in `_multi` Exp 066 (`src/ml_vol.py`: ML forecasts the next day's range in ATRs on 4h for the ten coins; a breakout of the previous N bars is taken only when the forecast is above its rolling quantile; arm none/q70/q85 x N 6/18; no new download) was run once and came out in `_multi` Exp 067: **REJECT on `valid_ci_lo>0` + `both_legs>0`, no holdout spent — but ML beat the rule it is measured against.** TRAIN chose `q85_n6` (arm at the 85th percentile, 1-day channel), so `train_chose_ml` passed. **Volatility is forecastable where direction is not: Spearman +0.35 TRAIN / +0.39 VALID between the forecast and the realised next-day range, against +0.03 for the direction models.** **Both `arm=none` cells were unselectable on TRAIN (none_n6: 2,783 trades, weekly -0.00059, mean R -0.0044, both legs negative) and all four armed cells selectable; arming cuts trades 65% and lifts mean R from -0.0044 to +0.0122, the t from -0.50 to +0.66 and the max DD from 16.24% to 6.79%.** VALID: 1,078 trades, weekly **+0.00114**, CI [-0.00058, +0.00299] (t +1.23), mean R +0.0185, long +0.1302 / short -0.0103, cost ×1.5 +0.00076, timing 1.45x the shifted p95, breadth 6/10, **max DD 9.59%**, both years positive, only 5 stops in 1,078 trades. **ML vs the same breakout without ML on VALID: weekly +0.00114 vs -0.00037, mean R +0.0185 vs -0.0025, t +1.23 vs -0.25, max DD 9.59% vs 25.28%, CI lo -0.00058 vs -0.00310 — better on every measure.** The arming filtered out 2,382 breakouts (69% of all) whose mean signed_label was **-0.0633** with only 44.9% moving in their own direction, against the kept trades' +0.0185 R. **Short share 0.251 / 0.288 — the lowest of any large-coin book** (vs §39's 0.549/0.642 and §37's 0.69/0.76), so taking the side from price fixed the bias three rounds chased; the short leg still lost, which is why `both_legs>0` fails. Best 5 weeks 1.30x the return (the least concentrated of the line) with the weekly mean without them negative. Analyzer: **FRAGILE, quality 69 vs §38 4h's 59 and §31's 86** — best of the large-coin books on train-vs-valid (100) and decay (100), but stability 22.2 is the lowest of the project's positive books. **`weekday` is the rank-1 feature by mean |SHAP| (0.1339) for the first time, and the volatility block is the coin's own (`vol_24`, `vol_ratio`, `atr_pct`); BTC volatility fell to rank 7.** **The best book here is still the frozen §31 cell** (CI lo -0.00026 on 46 coins vs §40's -0.00058 on ten). The planner's review (`_multi` Exp 068) adds: the range forecast is about 3.5x the persistence baseline (Spearman +0.39 vs +0.10 on VALID); `weekday` leads because weekend ranges are smaller (a calendar effect, not a leak); and the side-free arm acts as a long tilt (it kept 42% of up-breaks but 18% of down-breaks), which is where most of the gain over the rule came from. PLAN.md §41 as pre-registered in `_multi` Exp 069 (`src/ml_side.py`: §40 with the arm's threshold set per side, against the coin's last 60 same-side breakouts; form pooled/side x q70/q85 x N 6/18; no new download) was run once and came out in `_multi` Exp 070: **REJECT on `valid_ci_lo>0` alone, no holdout spent — and the short leg turned positive for the first time in the ten-coin line.** All four `pooled` rows reproduce §40 (`reproduces_s40` True everywhere). TRAIN chose `side_q70_n6` at t +0.88, the best of all 8 cells (weekly +0.00075, mean R +0.0153, max DD 5.24%). VALID: 1,088 trades, weekly **+0.00133**, CI [-0.00059, +0.00331] (t +1.32), mean R +0.0222, long +0.1291 / **short +0.0109** (522 shorts), cost ×1.5 +0.00095, timing 1.84x the shifted p95, **breadth 8/10**, **max DD 8.30%**, both years positive, total return 14.01%. **The mechanism is measurable: the per-side arm equalised the keep rates (0.302 long / 0.325 short) where §40's pooled arm kept 0.548 of up-breaks but only 0.349 of down-breaks — §40's arm was a long tilt (Exp 068), and removing the tilt made the shorts earn.** Against the pooled arm at the same cell (`pooled_q70_n6`) the side arm wins on every measure but trade count: weekly +0.00133 vs +0.00109, CI lo -0.00059 vs -0.00117, t +1.32 vs +0.91, short +0.0109 vs -0.0211, max DD 8.30% vs 12.58%. **The risk stated in advance (Exp 069) did not materialise: short share rose to 0.418/0.540 from §40's 0.251/0.288, but the added shorts earned.** Best 5 weeks 1.15x the return (least concentrated of the line) and the analyzer's mean R without the top 1% of trades is **+0.0012** (positive; §40's was -0.0037); BTC carries the book (+0.0880 R), ETH and XRP lose. Analyzer: **FRAGILE, quality 72 — the best ten-coin book and the best of any round since §32** (§40 69, §38 4h 59, §31 86), the whole gain over §40 in stability (66.7 vs 22.2). Top features are identical to §40's (§41 refits no model): `weekday` rank 1 (0.1339). **The best book here is still the frozen §31 cell** (CI lo -0.00026 on 46 coins vs §41's -0.00059 on ten). The planner's review (`_multi` Exp 071) corrects "the short leg turned positive": shorts average +0.0028 R (522 trades), the leg is negative without its 5 best trades and in 2024, so per-side arming stopped shorts losing rather than finding a short edge; holdout power is 22% even if the edge were real. Option (b), sizing by the forecast, was checked on TRAIN and dropped before registration (`_multi` Exp 072: the armed ratio is 1.01-1.14 and its Spearman with R is ~0). PLAN.md §42 as pre-registered in `_multi` Exp 073 (`src/ml_exit.py`: §41's frozen entry side/q70/N6 with the exit chosen on TRAIN; no new download) was run once and came out in `_multi` Exp 074: **REJECT on `valid_ci_lo>0` + `stress_weekly_mean>0` + `timing_beats_shift_p95` + `both_legs>0`, no holdout spent — the forecast exit is worse than the exit it replaced.** `reproduces_s41` is True, so every difference is the exit, not the entry or the model. TRAIN chose `fc` (exit when the forecast falls below its causal rolling 180-bar median) at t +0.95 against `chan`'s +0.88, so `train_chose_fc_exit` passed; `fcwide` is unselectable (TRAIN long leg -0.0107). **The hypothesis was falsified on its own terms: the forecast exit holds for LESS time, not more.** Median hold fell from 8 bars to 7 and the mean from 10.8 to 9.9 on TRAIN (10.9 -> 9.3 on VALID), because the 180-bar median is crossed below far more often than a 3-bar pullback ends — the design could not have produced the intended longer hold. VALID: 1,129 trades, weekly **+0.00027**, CI [-0.00157, +0.00216] (t **+0.28**), mean R +0.0040, long +0.0913 / **short -0.0633**, **cost x1.5 -0.00013**, **timing 0.76x** the shifted p95, breadth 7/10, max DD 10.33%, total return **2.80%**, short share 0.405/0.540 (unchanged — the exit did not move the side mix, it moved the result). **Against `chan_same_arm` (= §41) it loses on every measure**: weekly +0.00027 vs +0.00133 (20% of it), t +0.28 vs +1.32, mean R +0.0040 vs +0.0222 (18%), CI lo -0.00157 vs -0.00059, total return 2.80% vs 14.01%, max DD 10.33% vs 8.30%. **Concentration returned: best 5 weeks 5.02x the VALID return** (§41 1.15x), the weekly mean without them -0.00112, and the book averages -0.0113 R without its five largest trades (+5.53, +4.50, +2.72, +2.39, +2.11 R). The short leg lost in both years (-0.0155 2023, -0.0291 2024) while longs gained in both. Analyzer: **FRAGILE, quality 57 vs §41's 72** — the lowest of the ten-coin books, driven by **train_vs_valid 39 vs 100** (VALID mean R is 28% of TRAIN, against 145% for §41: TRAIN looked better and VALID was worse, the overfit shape) and robustness 20. Holdout power is 4%, against §41's recorded 22%. Top features are §41's unchanged (§42 refits no model). **The best book here is still §41** (REJECT on `valid_ci_lo>0`, CI lo -0.00059), not §42. The owner (2026-10-09) keeps the ten coins and asked for improvement from past results. `_multi` Exp 076 (read-only, TRAIN files only): §41's TRAIN trades whose side agrees with §38 4h's recorded direction forecast average +0.039 R (563) against -0.017 R (429) when it disagrees, t +2.57 for the difference, in both years, both sides, 7/10 coins and every §41 cell. PLAN.md §43 as pre-registered in `_multi` Exp 077 (`src/ml_agree.py`: §41's frozen book with a breakout armed only where §38 4h hl12's recomputed direction forecast agrees on the side; no new download) was run once and came out in `_multi` Exp 078: **REJECT on `valid_ci_lo>0` + `both_legs>0`, no holdout spent — the filter found on TRAIN (Exp 076) generalised, and it is the best ten-coin book in the project.** `reproduces_s41` and `reproduces_s38_dir` are both True. TRAIN chose `sign` with **`train_margin` +0.84** (+1.72 against `none`'s +0.88), so the pre-registered +0.5 margin passed with room to spare (Exp 075's protocol change, first use): 992 -> 607 trades, mean R +0.0153 -> +0.0372, both legs and both years up, max DD 5.24% -> 2.13%. VALID: 658 trades, weekly **+0.00109**, CI [**-0.00039**, +0.00266] (t **+1.40**), mean R **+0.0308** (the highest of the ten-coin line), long +0.1292 / **short -0.0149**, cost ×1.5 +0.00086, timing 2.04x the shifted p95, **breadth 9/10**, **max DD 4.33%**, both years positive, total return 11.43%. **Against `none_same_arm` (= §41) it lifts the per-trade edge +0.0222 -> +0.0308 R (+39%), the t +1.32 -> +1.40, the CI lower bound -0.00059 -> -0.00039 and halves the drawdown 8.30% -> 4.33%, at 82% of the weekly return** because it takes 40% fewer trades. **`valid_ci_lo>0` is the closest miss of the whole line** (-0.00039). **The pre-registered risk happened exactly as stated**: the direction forecast is bearish on 56.0%/62.7% of 2023/2024 bars (mean -0.1360/-0.1254), so the filter kept **0.720 of shorts and only 0.498 of longs**, the short share rose to 0.519/0.621 from 0.418/0.540, and the short leg went +0.0109 -> -0.0149 (negative in both years) - which is why `both_legs>0` fails. The longs, where the book earns, are unchanged and strong. Best 5 weeks 1.10x, the analyzer's mean R without the top 1% of trades **+0.0090** (§41's +0.0012); only ETH loses (-0.0485, the one coin that got worse), BTC carries it (+0.1059 R), XRP flipped positive. Analyzer: **FRAGILE, quality 80 vs §41's 72** - the best ten-coin book and the best of any round since §31; VALID mean R is 83% of TRAIN. Holdout power 25%, the highest recorded. **§43 is now the best ten-coin book, but the project's closest record is still the frozen §31 cell** (CI lo -0.00026 on 46 coins). The planner's review (`_multi` Exp 079) shows the agreement replicated on VALID longs (+0.103 vs -0.007 R) but not shorts; Exp 080 found no short-side signal in funding or BTC's trend, and Exp 081 found that combining §38's 1h/4h/1d direction models does not improve on the 4h one (TRAIN only). PLAN.md §44 as pre-registered in `_multi` Exp 082 (`src/ml_meta.py`: meta-labeling - a LightGBM trained on every wide coin's N=6 breakouts with the label = the breakout's own chan-exit outcome capped at 18 bars, features §30's + `bo_side`; no new download) was run once, three models, ~47 minutes, and came out in `_multi` Exp 083: **REJECT on `train_chose_meta` + `train_margin>=0.5` + `valid_ci_lo>0` + `both_legs>0`, no holdout spent - TRAIN did not prefer the meta model.** `reproduces_s41` and `reproduces_s43` are both True. **TRAIN picked `agree` (= §43) and both selection gates fired before VALID**: all 4 forms selectable, `none` +0.88, **`agree` +1.72**, `meta0` +1.16, `metaq50` +1.05, so `train_margin` = **-0.5542** (the best meta form is 0.56 t BELOW `agree`, the wrong sign for the +0.5 gate); the meta forms also cut trades less (688/765 vs 607) and have weaker TRAIN long legs (+0.0100 / +0.0177 vs +0.0358). **The meta forecast nevertheless ranks breakouts correctly on both sides and out of sample**: IC +0.0477 TRAIN / **+0.0234 VALID** over all events, short IC +0.0789 TRAIN / **+0.0130 VALID** - so Exp 082's stated failure mode (VALID short IC <= 0, agreeing with Exp 079-080) did **not** happen, but ranking events well did not improve the book on TRAIN. **`bo_side` is unused**: mean |SHAP| 0.00004, rank 81 of 87; the meta model reads market volatility and breadth (`btc_vol_168`, `breadth_24`, `mkt_ret_24`), not the side, even though the side is in its feature set. **VALID is §43's book unchanged to the last decimal** (TRAIN chose the baseline, so no new VALID look): 658 trades, weekly +0.00109, CI [-0.00039, +0.00266] (t +1.40), mean R +0.0308, long +0.1292 / short -0.0149, max DD 4.33%, breadth 9/10, short share 0.519/0.621, kept share 0.498 long / 0.720 short, best 5 weeks 1.10x. **Recorded as a fact, not a choice: both meta forms have a POSITIVE short leg on VALID and a closer CI than the chosen form** (`metaq50` CI lo -0.00016, t +1.64, short +0.0178; `meta0` CI lo -0.00032, short +0.0251) - TRAIN did not select either, and switching now would be tuning on VALID. Analyzer: **FRAGILE, quality 80, identical to §43 on every dimension** (it scores the frozen book, so §44 adds nothing to it). Holdout power 24.5% / 9.3%, same as §43. **§43 remains the best risk-adjusted ten-coin book; §31's frozen cell remains the project's closest record.** No approved run is pending. Ask before starting anything else.
The exit
lab (§18) found no exit skill (BTC Exp 045). Rotation (§17) and allocation
(§16) were REJECT / NO_IMPROVEMENT. The
TradingView ports are closed (§13, BTC Exp 033/034); a new port needs Pine
Script source the owner pastes, never one written from memory. Run every command with the coin in `SYMBOL` (on Windows PowerShell:
`$env:SYMBOL="ETHUSDT"`; unset = BTCUSDT), and read that coin's
`journal/<SYMBOL>/STATUS.md`.

Talk to the owner **in Thai**. Write code, idea files and the journal in English.

---

## 0. Your job

Find trading techniques for Binance USDT-M perpetual futures that make money
**after realistic costs**. That includes creative entries, combinations of
several techniques, and trade-management techniques (TP/SL, break-even,
trailing, "แก้ไม้"). Test every one of them **honestly** with
`src/evaluate.py`.

This is a research harness, not a trading bot. For BTCUSDT, 100+ earlier
configurations found **no proven edge** (see STATUS.md). So:

- A result that looks great is a **bug or luck** until the gates say
  otherwise.
- A clear REJECT is a useful result. Record it and move on to a different
  idea.
- Never make a result look better than it is. Owner money depends on it.

### Start-of-session checklist (Python 3.12+; run these in order)

```bash
pip install -r requirements.txt
python src/test_engine.py        # must end with: ALL CHECKS PASSED
python src/datafeed.py                  # BTCUSDT; first time ~3 min; must end with: VALIDATION: OK
SYMBOL=ETHUSDT python src/datafeed.py   # same, for ETH
python src/datafeed.py --metrics        # PLAN.md section 14; must end with: METRICS VALIDATION: OK
SYMBOL=ETHUSDT python src/datafeed.py --metrics
python src/datafeed.py --premium        # PLAN.md section 25; must end with: PREMIUM VALIDATION: OK
SYMBOL=ETHUSDT python src/datafeed.py --premium
python src/evaluate.py --list    # the building blocks you can combine
cat journal/BTCUSDT/STATUS.md journal/ETHUSDT/STATUS.md   # where things stand (PLAN.md section 13)
```

If any of these fails, **stop and fix that first** (see §9). Do not research
on a broken setup.

---

## 1. The research loop — how to find a technique

Repeat this loop. One loop = one idea = one hypothesis.

**Step 1 — Pick an idea.** Read `docs/research/LESSONS.md` first (what 354
evaluations taught: cost, holding time, long bias, luck). Take one from the backlog in
`docs/research/TECHNIQUES.md` §6, or invent a new one. First check
`journal/<SYMBOL>/evaluations.md` and `results/<SYMBOL>/evaluations.csv` to
make sure it was not already tried.

**Step 2 — Write the hypothesis first.** Explain in 1–3 sentences **why**
this should make money: who is on the other side, or what market behaviour
you are exploiting. "Try RSI 14 with 3 filters" is not a hypothesis.

**Step 3 — Write an idea file** `ideas/NNN_short_name.json`. NNN is the next
free number. Copy the format from `ideas/example_trend_breakout.json` and
read `ideas/README.md`. Usually you need **no Python**: combine triggers,
filters and exits in the `recipe` format.

**Step 3b — Exits: no time exit (owner's rule, 2026-10-02, `_multi` Exp 014).**
Every new idea exits on **price or a signal only**, never on the clock:
- Set `"max_hold_hours": 100000` (no time limit; the engine caps a hold at
  100,000 bars and closes at the end of each period, reason `eod`). Never put
  `max_hold_hours` in the grid.
- The idea must have at least one exit that can fire on its own, besides the
  initial stop: a trailing stop (`trail_at` > 0 and `trail_atr` > 0),
  `exit_on: "opposite"`, or a `tp`. A fixed stop alone is not allowed (it can
  hold for years).
- A position open for months blocks new entries (one position at a time). That
  is the accepted cost of this rule; report the average hold.
- This applies to **new** ideas only. Never re-run an old idea with its time
  exit removed: that is retrying a tested idea until it passes (§3 rule 3).

**Step 4 — Keep the grid small.** At most 4 grid keys and at most 64
combinations (enforced). Sweep the things the hypothesis is actually about.
Fix everything else at a sensible value.

**Step 4b — Make the timeframe variants.** Every idea is tested on four
timeframes, **15m 30m 1h 4h**, never just one:
`python src/tf_variants.py ideas/NNN_short_name.json` writes the three other
files. 1m, 3m and 5m are no longer tested (owner's decision 2026-09-29,
`docs/research/LESSONS.md` §1: cost made them negative on TRAIN and VALID);
use them only if the owner asks (`--tfs 1,3,5`) (add `--mode time` when `docs/research/PLAN.md` says so, as in Round 5). Evaluate each. Read the docstring of `src/tf_variants.py` for what it
rescales, and never rescale by hand.

**Step 5 — Run it:**
```bash
python src/evaluate.py ideas/NNN_short_name.json
```
It selects parameters on TRAIN (2020–2022), tests the frozen choice on VALID
(2023–2024), and appends the result to `results/<SYMBOL>/evaluations.csv` and
`journal/<SYMBOL>/evaluations.md`. It prints a verdict.

**Step 6 — Read the verdict and act on it:**

| Verdict | Meaning | What you do |
|---|---|---|
| `PASS` | All gates passed on VALID | Run `--final` **once** (step 7) |
| `WATCH` | Positive on train, valid and cost stress, but CI touches 0 or DD too big | You may make **up to 2** improved versions (`NNN_name_v2.json`, `_v3`). Each change must be explained by a diagnosis (step 8), not by trying numbers |
| `REJECT` | Failed | Record one line of *why* (step 8). Move to a **different** idea |
| `INCONCLUSIVE` | Fewer than 30 validation trades | Make the idea trade more (looser filter, lower tf) or drop it |
| `DUPLICATE` | Validation result identical to an earlier evaluation: your change affected no trade | Not new evidence. Record why the change was inert and move on. It can never go to `--final` |
| `UNSIZABLE` | `size_skips` > 0 on TRAIN or VALID: the 1,000 USDT research account could not size some signals (stop too wide for BTC's 0.001 qty step at high prices), so the trade list is not the rule's | No evidence either way, never goes to `--final`, and no baseline/benchmark. Usually a `pct` stop above ≈ 9% (4h variants in chart mode double the stop): narrow the stop in a new idea file, or drop that timeframe. A losing result with skips stays `REJECT` |

**Step 6b — Random-entry baseline (every WATCH and every PASS):**
```bash
python src/baseline.py ideas/NNN_short_name.json
```
It re-runs the idea's frozen exits and filters with **random entries** (200
seeds, about the same number of signals) and asks whether the real entries
beat random timing: **SKILL** only if the idea's mean R is above the 95th
percentile of both "random at any time" and "random within the same
filters", on **both TRAIN and VALID** (VALID alone let a bull-market drift
pass as skill: idea 022, Exp 019). Otherwise **DRIFT**: the result comes from the market's move (e.g.
being long in the 2023–24 bull market) or from the filters, not from the
entry. Report both numbers. A DRIFT idea is not a strategy, whatever its
verdict. Written to `results/<SYMBOL>/baseline/` and
`journal/<SYMBOL>/baselines.md`.

**Step 6c — Buy-and-hold benchmark (every WATCH and every PASS):**
```bash
python src/benchmark.py ideas/NNN_short_name.json
```
Daily account returns vs holding BTC: beta, alpha per year with a 95% CI,
CAGR, max drawdown and Sharpe next to buy & hold's. **ALPHA** = return beyond
the rule's BTC exposure (alpha > 0 on TRAIN and VALID, VALID CI above 0).
**RISK_EDGE** = better Sharpe and under half of buy & hold's drawdown on both
periods, without proven alpha: report it to the owner. **NO_EDGE** = holding
BTC does as well. Compare Sharpe and alpha, not CAGR (1% risk sizing keeps
exposure small).

**Step 7 — Holdout (only after PASS + (SKILL or ALPHA)):**
```bash
python src/evaluate.py ideas/NNN_short_name.json --final
```
`--final` refuses unless the verdict is PASS **and** `baseline.py` said SKILL
or `benchmark.py` said ALPHA. **A regime rule** (trigger `trend_state`, or any
trigger in `evaluate.REGIME_TRIGGERS`: it fires on every bar of a market
state) **needs ALPHA**: its trigger is its filter, so SKILL only says "long in
up-regimes beats long at random", and the question it must answer is whether
it beats holding BTC (Exp 021). The holdout run also runs the random-entry
control on the holdout itself: `CONFIRMED` additionally requires the idea to
beat the median random entry (modes A and B) on the holdout.
This runs the frozen choice **one time** on HOLDOUT (2025-01 → 2026-08),
data nothing has been tuned on. `CONFIRMED` = a real candidate: tell the owner
right away. `FAILED` = it was luck: record it and move on. The script refuses
a second holdout run for the same config. **Never** work around that. Never
make a copy with a tiny change just to get another holdout try.

**Step 8 — Diagnose, don't guess.** Before a v2, look at the numbers in the
report: `gross_r` vs `cost_r`, exit mix (stop/tp/time %), avg hold,
long vs short, per-year R. Also look at the trades file
`results/<SYMBOL>/eval_trades/<eval_id>_valid.csv.gz` (gzip, written by
`evaluate.py`; `pd.read_csv` opens it directly). Typical diagnoses:
- `cost_r` ≥ `gross_r` → stop too tight or too many trades: widen the stop, add a filter, use a higher tf.
- `time_rate` very high → trades go nowhere: shorter `max_hold_hours`, or a better trigger.
- TP rarely hit, stop often hit → TP too far, or the trigger is late.
- One side (long or short) loses → `direction` or a trend filter.
- One year carries everything → a regime effect, not an edge. Say so.

**Step 9 — Every 5 ideas**, append a short batch summary to
`journal/<SYMBOL>/experiments.md` (template §8). Update
`journal/<SYMBOL>/STATUS.md` when something important changes.

---

## 2. What counts as good — the gates (fixed in `src/config.py`)

A technique is a **candidate** only if `evaluate.py` says `PASS` and then
`--final` says `CONFIRMED`. PASS requires, on VALID:

| Gate | Why |
|---|---|
| ≥ 100 validation trades | fewer is noise |
| mean R > 0 on TRAIN too | an edge should exist in both periods |
| mean R > 0 on VALID | |
| 95% bootstrap CI lower bound > 0 | not just lucky |
| mean R > 0 with fees and slippage ×1.5 | survives worse execution |
| max drawdown ≤ 20% | survivable at 1% risk per trade |

Always report `trades, gross_r, cost_r, mean R, 95% CI, CAGR, maxDD`
together. Never report only a return, a win rate, or a Sharpe.

---

## 3. Hard rules — NEVER

1. **Never** change costs, risk, splits or gates in `src/config.py` (fees
   0.05%/0.02%, slippage 0.02%, 1% risk, stop-first fills, `EVAL_*`,
   `valid_start`, `holdout_start`) to make something pass. If you believe one
   is wrong, ask the owner.
2. **Never** use future data. A signal on bar `i` is filled at the open of
   bar `i+1`. Indicators may only use bars `<= i`. No `.shift(-k)`, no
   `center=True`, no mean/std/quantile over the whole series, no "best
   parameter for this year".
3. **Never** tune on VALID or HOLDOUT by hand: no picking parameters after
   looking at validation, no running many near-identical ideas until one
   passes. The small grid runs on TRAIN only; that is the only place
   parameters are chosen.
4. **Never** run `--final` on anything that is not `PASS`. Never delete or
   edit `results/<SYMBOL>/holdout_log.csv` or `evaluations.csv`.
5. **Never** edit an idea file after it was evaluated. Make `_v2` instead.
   Maximum 3 versions per idea; after that, move on. `evaluate.py` enforces
   this by **structure** (timeframe + trigger types + filter types +
   direction), not by file name: an idea that changes only numbers (stop,
   thresholds, offsets, hold time) counts as a version of the earlier one
   and is refused after 3. Renaming a file does not get around it.
6. **Never** weaken, skip or delete a test to make it pass. Never edit past
   journal entries (append-only). Never edit generated files
   (`evaluations.md`, `ledger.md`, `ledger.csv`) by hand.
7. **Never** implement martingale (bigger size after a loss), unlimited
   averaging down, or anything that risks more than 1% of equity per idea.
   (TECHNIQUES.md §4 explains which trade-fixing methods are allowed.)
8. **Never** resample bars. Load native Binance files with
   `experiment.get_bars(tf)` only (Exp 010: resampling shifted every bar).
9. **Never** commit data (`data/raw/`, `data/cache/`), `__pycache__`, API
   keys or secrets. Never add live trading or order-placement code unless
   the owner asks.
10. **Never** report a number you did not produce or cannot point to in
    `results/<SYMBOL>/`.
11. **Never** add files to `results/<SYMBOL>/legacy/`, and never add loose
    CSVs or logs next to `evaluations.csv`. All new research goes through
    `evaluate.py`, `baseline.py` and `benchmark.py`, which write only
    `evaluations.csv`, `holdout_log.csv`, `eval_trades/`, `baseline/`,
    `benchmark/` and `journal/<SYMBOL>/evaluations.md` / `baselines.md` /
    `benchmarks.md`. If a new script
    really needs its own output, ask the owner first and write it to
    `results/<SYMBOL>/<script_name>/`.

## 4. Hard rules — ALWAYS

12. **Always** run `python src/test_engine.py` after changing anything in
    `src/` and before committing. It must print `ALL CHECKS PASSED`.
13. **Always** write the hypothesis before running.
14. **Always** keep a REJECT in the records. Negative results stop the next
    agent from repeating your work.
15. **Always** say how many ideas you tried when you report a PASS. Out of 50
    ideas, a couple can pass by luck; that is why the holdout exists.
16. **Always** commit your work at the end of a session (§10).

---

## 5. How much code you may change — levels

| Level | You may | Requirements |
|---|---|---|
| **1 — idea files** (default, do this most) | Write `ideas/*.json` using existing blocks and strategies | None beyond §1 |
| **2 — new building block** | Add a trigger or filter function to `src/recipes.py` (or a strategy to `src/strategies.py` + `REGISTRY`) | Docstring with a one-line description. Causal. A trigger returns **one** array of -1/0/+1 (use `_side(long, short)`, never a tuple); a filter returns `(long_ok, short_ok)`. `python src/test_engine.py` passes: test 7 automatically checks that every block is causal and has that output shape. Mention it in TECHNIQUES.md |
| **3 — engine change** | Change `src/backtest.py` (e.g. partial TP, scale-in, stop-and-reverse) | **Ask the owner first.** New behaviour must be off by default. Add a hand-computed test in `test_engine.py` that fails before your change and passes after. All old tests unchanged and passing. Journal entry explaining it |

`src/config.py` costs/gates, `src/evaluate.py` gates and the split dates are
not yours to change at any level.

---

## 6. One folder per coin

- Everything coin-specific lives under `<SYMBOL>/` (Binance symbol, upper
  case): `data/raw/<SYMBOL>/`, `data/cache/<SYMBOL>/`, `results/<SYMBOL>/`,
  `journal/<SYMBOL>/`.
- Code in `src/` and idea files in `ideas/` are shared by all coins. Never
  hard-code a symbol or path. Use `config.py` (`C.SYMBOL`, `C.RESULTS`,
  `C.JOURNAL`, …).
- Choose the coin per run: `SYMBOL=ETHUSDT python src/evaluate.py ideas/x.json`
  (default `BTCUSDT`).
- **Adding a coin:** (a) add it to `SYMBOL_SPECS` in `src/config.py` with the
  real `qty_step`, `min_notional`, `data_start`, `data_end`, `valid_start`,
  `holdout_start`; (b) `SYMBOL=X python src/datafeed.py` until
  `VALIDATION: OK`; (c) create `journal/X/STATUS.md` and
  `journal/X/experiments.md` (starts at Exp 000); (d) run `test_engine.py`.
  Adding a new coin is a Level 3 change: ask the owner first.
- A config found on one coin must be re-evaluated on the other coin's own
  data. Never assume it transfers.
- Cross-coin comparisons go to `results/_multi/` and `journal/_multi/`.

---

## 7. Repository map

```
AGENTS.md / CLAUDE.md       these rules (CLAUDE.md imports this file)
docs/research/TECHNIQUES.md catalogue of techniques + idea backlog  <- read for ideas
ideas/                      idea files (JSON), shared by all coins; ideas/README.md = format
src/                        all code (flat; scripts import each other via sys.path)
journal/<SYMBOL>/
    STATUS.md               where the coin stands, next steps
    experiments.md          research log, append-only
    evaluations.md          GENERATED by evaluate.py, one block per evaluation
    baselines.md            GENERATED by baseline.py
    benchmarks.md           GENERATED by benchmark.py
    ledger.md               GENERATED by ledger_report.py (older experiments)
results/<SYMBOL>/
    evaluations.csv         every evaluate.py run (one row each)
    holdout_log.csv         every holdout use (the lock)
    baseline/               baseline.py output: <eval_id>.json (SKILL/DRIFT), <eval_id>_runs.csv.gz
    benchmark/              benchmark.py output: <eval_id>.json (ALPHA/RISK_EDGE/NO_EDGE)
    eval_trades/            trade list per evaluation, <eval_id>_valid.csv.gz (committed;
                            re-create a missing one with evaluate.py <idea> --trades-only)
    legacy/                 Exp 003–010 outputs + logs/, and pre_signfix/ (Exp 011–014
                            records made before the short-sign fix). Read-only history
data/{raw,cache}/<SYMBOL>/  Binance zips, parquet (both git-ignored)
```

| `src/` file | Role |
|---|---|
| `evaluate.py` | **the research gate**: idea file → TRAIN select → VALID verdict → optional one-time HOLDOUT |
| `baseline.py` | random-entry control for a WATCH/PASS: SKILL or DRIFT |
| `benchmark.py` | buy-and-hold comparison for a WATCH/PASS: ALPHA, RISK_EDGE or NO_EDGE. `--final` needs SKILL or ALPHA (regime rules: ALPHA) |
| `recipes.py` | building blocks: `TRIGGERS`, `FILTERS`, and `recipe()` that combines them with exits |
| `tf_variants.py` | writes an idea's variants for every other timeframe (chart mode default, `--mode time` optional) |
| `strategies.py` | older hand-written strategies (`REGISTRY`), also usable in idea files |
| `backtest.py` | the engine (`run_backtest`): next-bar-open fills, taker/maker fees, slippage, funding, stop-first, BE/trailing, post-only entries |
| `indicators.py` | causal indicators (EMA, ATR, RSI, ADX, BB, VWAP, supertrend, …) |
| `config.py` | symbol specs, paths, costs, risk, split dates, gates |
| `experiment.py` | `get_bars(tf)`, `load_funding()`, older helpers |
| `datafeed.py` | download + cache + `validate()` |
| `test_engine.py` | engine and block tests; must pass |
| `ml_filter.py`, `run_ml.py`, `definitive.py`, `sweep.py`, `cost_lab.py`, `round*.py`, `diagnose.py` | older experiments (Exp 003–010); they write to `results/<SYMBOL>/legacy/` (`C.LEGACY`) |
| `ledger*.py`, `report_data.py`, `make_report.py` | reporting for the older experiments |
| `allocation.py` | PLAN.md §16: four fixed trend rules on daily spot/perp bars against buy-and-hold (1x exposure, next-open fills, fees, funding). Writes `results/<SYMBOL>/s16_allocation_1d/` and the generated `journal/<SYMBOL>/s16_allocation_1d.md`; runs once (`--rerun` only after a code fix) |
| `rotation.py` | PLAN.md §17: weekly cross-sectional momentum over every USDT pair (spot long-only vs the universe; perp long/short with funding). `--build spot|perp` downloads to `data/*/_multi/`. TRAIN chooses the lookback, VALID gives PASS/REJECT, `--final` runs the holdout once. Writes `results/_multi/s17_rotation_1d/` and the generated `journal/_multi/s17_rotation_1d.md` |
| `exit_lab.py` | PLAN.md §18: six fixed exits on random entries (p 0.25, seed 18), each trade simulated on its own with the engine's exact rules (test 14). TRAIN chooses the exit, VALID gives PASS/REJECT, `--final` runs the holdout once. Writes `results/<SYMBOL>/s18_exit_lab/` and the generated `journal/<SYMBOL>/s18_exit_lab.md` |
| `ml_entry.py` | PLAN.md §19: LightGBM long/short models predict the net R of a fixed symmetric exit; the threshold comes from purged TRAIN walk-forward OOF; VALID gates include beating random signals with the same long/short counts; `--final` runs the holdout once. Writes `results/<SYMBOL>/s19_ml_entry_1h/` and the generated `journal/<SYMBOL>/s19_ml_entry_1h.md` |
| `ml_pool.py` | PLAN.md §20: the §19 model fitted once on 20 coins together (universe chosen on TRAIN volume, survivorship-free). `--build` downloads 1h perp klines + funding to `data/*/_multi/pool_1h`; gates add breadth (half the coins beat their own control). Writes `results/_multi/s20_ml_pool_1h/` and the generated `journal/_multi/s20_ml_pool_1h.md` |
| `ml_pool2.py` | PLAN.md §21: round 2 of the pooled model on the same 20 coins: 4-day hold decided every 4 h, cross-coin/BTC features, LightGBM settings tuned on TRAIN OOF, control on GROSS R, both legs must be net positive. Writes `results/_multi/s21_ml_pool2_1h/` and the generated `journal/_multi/s21_ml_pool2_1h.md` |
| `ml_hold.py` | PLAN.md §27: one pooled LightGBM forecast (next 24 h in ATRs) every 4 h on the same 20 coins; a hysteresis policy decides entry AND exit, no time limit (8-ATR protective stop only); TRAIN OOF picks setting, entry quantile and exit mode; control = 200 time-shifts of the desired-position path, timing before costs; simulator matches the engine (test 23). Writes `results/_multi/s27_ml_hold_1h/` and the generated `journal/_multi/s27_ml_hold_1h.md` |
| `ml_wf.py` | PLAN.md §28: §27's model and policy refit every month (walk-forward) on 50 coins, traded on 1h, 4h or 1d with the other two timeframes' closed-bar features as inputs (multi-timeframe); `--build` downloads native 1h/4h/1d klines + funding to `data/cache/_multi/pool_<tf>`; TRAIN walk-forward picks the cell, VALID judges each timeframe, ONE timeframe may take the holdout. Writes `results/_multi/s28_ml_wf/` and the generated `journal/_multi/s28_ml_wf.md` |
| `ml_wf2.py` | PLAN.md §29: §28 unchanged except that features and labels come from each coin's SPOT bars from 2017-08 (more market regimes in every refit); trades still simulated on PERP bars with perp costs and funding in §28's windows; universe = §28's rule restricted to spot listed by 2018-01-01; `--build` adds spot 1h/4h/1d to `data/cache/_multi/spot_<tf>`. Writes `results/_multi/s29_ml_wf2/` and the generated `journal/_multi/s29_ml_wf2.md` |
| `ml_wf3.py` | PLAN.md §30: §28's exact 47 coins; each coin's features and labels from its own spot bars from the pair's first month (perp bars if no earlier spot), trades on perp bars; otherwise §29/§28 unchanged. `--build` adds the missing spot caches. Writes `results/_multi/s30_ml_wf3/` and the generated `journal/_multi/s30_ml_wf3.md` |
| `ml_port.py` | PLAN.md §31: §30's three frozen walk-forward models recomputed (checked against §30's VALID forecasts); the 1h book run as ONE account with agreement (4h/1d), confidence sizing and a per-direction risk cap; TRAIN walk-forward picks 1 of 18 cells by the weekly account t-statistic; account gates incl. max drawdown. Writes `results/_multi/s31_ml_port_1h/` and the generated `journal/_multi/s31_ml_port_1h.md` |
| `ml_xs.py` | PLAN.md §32: §31's account with each 1h/4h/1d forecast demeaned across the 47 coins at each hour (the market-wide part removed); no refit (§31's reproduction check); TRAIN picks 1 of 24 cells (form raw/demean x §31's switches, capped), a raw choice is REJECT; §31's gates; diagnostics: top-5-week share, beta to the market. Shares one holdout with §31. Writes `results/_multi/s32_ml_xs_1h/` and the generated `journal/_multi/s32_ml_xs_1h.md` |
| `ml_mkt.py` | PLAN.md §33: the mean of the 47 coins' frozen §30 1h forecasts used as one market-timing signal on BTC, ETH or both (half risk each); §30's hysteresis policy, 8-ATR stop, no clock; TRAIN picks 1 of 6 cells (instrument x 4h agreement); gates as §31 without breadth (>= 30 trades). Shares one holdout with §31/§32. Writes `results/_multi/s33_ml_mkt_1h/` and the generated `journal/_multi/s33_ml_mkt_1h.md` |
| `ml_flow.py` | PLAN.md §34: §30's 1h model refit with positioning features (Binance metrics: OI change, OI/volume, long/short ratios; funding; their same-hour market means) and judged on §31's fixed account cell; TRAIN compares base vs flow (a base choice is REJECT); §31's gates; `--build` downloads metrics for the 47 coins to `data/cache/_multi/metrics/`. Shares one holdout with §31-§33. Writes `results/_multi/s34_ml_flow_1h/` and the generated `journal/_multi/s34_ml_flow_1h.md` |
| `listing.py` | PLAN.md §35: short every newly listed USDT-M perp (first daily bar after 2020-02-01, delisted included) at listing + DELAY days on daily bars; stop, trailing signal exit, no clock; costs + funding; 0.25% risk each, 10% cap; TRAIN picks 1 of 12 cells; gates incl. beating an established-perp control on TRAIN and VALID, both VALID years > 0, mean without the top 5 > 0; `--build` downloads daily OHLC + funding of every perp to `data/cache/_multi/listing/`. Own one-time holdout. Writes `results/_multi/s35_listing_1d/` and the generated `journal/_multi/s35_listing_1d.md` |
| `ml_wide.py` | PLAN.md §36: train the 1h model wide (§30's 47 coins + every perp while it was a monthly top-50 by prior-30-day volume, causal) with a 12/24/48-bar horizon ensemble, trade only the monthly top 20 large coins (crypto, listed >= 1 year, prior-30-day volume, per symbol) with §31's fixed cell and a core-trained 4h agreement model; TRAIN compares narrow (§30's recipe) vs wide (narrow = REJECT); §31's gates; `--build` downloads the extra coins' 1h/4h/1d klines + funding into §28's caches. Shares one holdout with §31-§34's ML line. Writes `results/_multi/s36_ml_wide_1h/` and the generated `journal/_multi/s36_ml_wide_1h.md` |
| `ml_large.py` | PLAN.md §37: a model for the owner's ten large coins (BNB BTC ETH XRP SOL DOGE ADA LINK NEAR BCH, each from 365 days after listing): 4h decisions with 1h/1d features, trained wide on §36's monthly top-50 members, one model per horizon averaged (sets 1-3d = 6/12/18 bars, 2-6d = 12/24/36), §30's 4h setting/policy, 8-ATR stop, no clock; agreement off or a wide-trained 1d model; conf sizing, 5% cap; TRAIN picks 1 of 4 cells; §31's gates with >= 100 trades and breadth >= 8 coins; writes TRAIN trades of all cells. Uses §36's caches. Shares one holdout with §31-§36. Writes `results/_multi/s37_ml_large_4h/` and the generated `journal/_multi/s37_ml_large_4h.md` |
| `ml_recent.py` | PLAN.md §38: §37's frozen cell (ten large coins, 1-3 day horizons, wide rows, agreement off) as three sub-models decided on 1h / 4h / 1d (`--tf` runs one; resumable), each monthly refit's training rows weighted `expanding` (on 4h = §37, must reproduce it) / `hl12` (12-month half-life) / `roll24` (24-month window); a weighting is selectable only with both TRAIN years and both legs positive, the t-statistic picks; an `expanding` choice is REJECT; §37's VALID gates per sub-model; reports the short share by year; writes `run_record` files; ONE sub-model may take the holdout (PASS, highest TRAIN t). Uses §36's caches. Shares one holdout with §31-§37. Writes `results/_multi/s38_ml_recent/{1h,4h,1d}/` and the generated `journal/_multi/s38_ml_recent.md` |
| `ml_rank.py` | PLAN.md §39: §38's 4h sub-model as TRAIN chose it (hl12, ten coins, 6/12/18 bars) with the forecast fed to the unchanged policy as `raw` (= §38 4h, must reproduce it) / minus its causal rolling median over 30 days (`med30`) / 90 days (`med90`), per coin; §38's TRAIN rule (both years, both legs, then t); a `raw` choice is REJECT; §37's VALID gates; reports short share and mean centred forecast by year; writes `run_record` files. Uses §36's caches. Shares one holdout with §31-§38. Writes `results/_multi/s39_ml_rank_4h/` and the generated `journal/_multi/s39_ml_rank_4h.md` |
| `ml_vol.py` | PLAN.md §40: LightGBM forecasts the next day's range in ATRs (no side) on 4h for the ten large coins (wide rows, §30's 4h setting, expanding monthly walk-forward); a breakout of the previous N bars is taken only when the forecast is above its causal rolling q-quantile (arm none / q70 / q85 x N 6 / 18 bars), exit on the N/2 opposite channel or the 8-ATR stop, no clock; §31's account; §38's TRAIN rule; an arm=none choice (rule without ML) is REJECT; §37's VALID gates; reports the same breakout without ML on VALID and the forecast-vs-range Spearman; writes `run_record` files. Uses §36's caches. Shares one holdout with §31-§39. Writes `results/_multi/s40_ml_vol_4h/` and the generated `journal/_multi/s40_ml_vol_4h.md` |
| `ml_side.py` | PLAN.md §41: §40 unchanged except the arm: `pooled` (= §40, must reproduce it) or `side` (long armed against the q-quantile of the forecasts at the coin's last 60 up-breaks, short against its last 60 down-breaks); TRAIN picks 1 of 8 cells (form x q70/q85 x N 6/18) by §38's rule; a pooled choice is REJECT; §40's VALID gates; reports the other form on VALID and the keep rate per side; writes `run_record` files. Uses §36's caches. Shares one holdout with §31-§40. Writes `results/_multi/s41_ml_side_4h/` and the generated `journal/_multi/s41_ml_side_4h.md` |
| `ml_exit.py` | PLAN.md §42: §41's entry frozen at its TRAIN choice (side arm, q70, N 6) with the exit chosen on TRAIN from `chan` (§41's N/2 channel, must reproduce it) / `fc` (forecast falls below its causal rolling 180-bar median) / `fcwide` (that, or a close beyond the previous N bars' opposite extreme); 8-ATR stop, armed reversals, no clock; §38's TRAIN rule; a chan choice is REJECT; §41's VALID gates; reports hold length and exit mix per form and the chan book on VALID; writes `run_record` files. Uses §36's caches. Shares one holdout with §31-§41. Writes `results/_multi/s42_ml_exit_4h/` and the generated `journal/_multi/s42_ml_exit_4h.md` |
| `ml_agree.py` | PLAN.md §43: two ML models - §41's frozen range-armed breakout (side, q70, N 6, chan exit) taken only where §38 4h's direction forecast (hl12, 6/12/18 bars, recomputed and checked against §38's record) has the same sign as the breakout side; forms `none` (= §41, must reproduce it) / `sign`; §38's TRAIN rule plus a pre-registered TRAIN t margin of +0.5; a none choice is REJECT; §41's VALID gates; reports the none book on VALID, kept share per side and the direction forecast by year; writes `run_record` files and `direction_predictions.parquet`. Uses §36's caches. Shares one holdout with §31-§42. Writes `results/_multi/s43_ml_agree_4h/` and the generated `journal/_multi/s43_ml_agree_4h.md` |
| `ml_meta.py` | PLAN.md §44: meta-labeling on §41's frozen book - a LightGBM (§30's 4h setting, monthly expanding walk-forward, wide rows, features §30's + `bo_side`) predicts each N=6 breakout's own outcome (entry next open, exit at §41's N/2 opposite channel or 18 bars, signed log move / ATR; lag 19 bars); forms `none` (= §41) / `agree` (= §43) / `meta0` (forecast > 0) / `metaq50` (above the median at the coin's last 60 same-side breakouts); §38's TRAIN rule plus a +0.5 t margin over the better of none/agree; §41's VALID gates; reports the other forms on VALID, meta IC at events by side, kept share; writes `run_record` files for the meta model. Uses §36's caches. Shares one holdout with §31-§43. Writes `results/_multi/s44_ml_meta_4h/` and the generated `journal/_multi/s44_ml_meta_4h.md` |
| `analyzer.py` | Result Analyzer (read-only): scores every recorded ML run (§19-§36) on 7 dimensions (train vs valid, OOS robustness, stability, monthly folds, parameter sensitivity, decay, overfit check) from summaries and trade files (TRAIN trade files too, from §36 on); verdict ACCEPT (all gates + score >= 70) / FRAGILE / OVERFIT / NO_EDGE. No backtest, no holdout. Writes `results/_multi/analyzer/`, the generated `journal/_multi/analyzer.md` and `docs/analyzer_data.json` (web page `docs/analyzer.html`). Re-run after every ML round |
| `result_report.py` | Standard analysis files for every round (read-only, recorded trade files only, never a holdout): `results/_multi/<round>/analysis/<split>_<book>/` with `trades_summary.json` (win rate, avg win/loss, PF, expectancy, median, streaks, costs), `prediction_analysis.json` (confidence at entry vs result), `walkforward_folds.json` (one fold per refit month), `performance_by_period.json` (month, year, coin, side) and `error_analysis.json` (losers by side, coin, causal BTC trend/volatility regime) and, where trades recorded their top-3 SHAP (§28-§30), `feature_drivers.json`. Describes, never chooses. Re-run after every round. Result folders are named by round (`results/_multi/README.md`, `_multi` Exp 056) |
| `run_record.py` | Library for every ML round from §38 on (no script): called inside a round's run() while the models exist, writes `<round>/record/<split>/` with `feature_importance.json` (gain/split per refit + mean |SHAP|), `training_metadata.json`, `predictions.parquet` (every forecast bar + label), `skipped_signals.csv.gz` (entries a filter removed), `run_info.json` (versions, commit, input fingerprint) and `holdout_power.json`. Recording never changes a forecast (test 35). A §38+ registration must call it |
| `stop_diag.py` | PLAN.md §23: from the VALID trade files, asks whether entries were on the wrong side or right and then stopped out, against random fills with the same side, stop fraction and hold. Read-only; writes `results/<SYMBOL>/s23_stop_diag/` and the generated `journal/<SYMBOL>/s23_stop_diag.md` |
| `level_limit.py` | PLAN.md §24: limit orders resting AT support/resistance (previous-day extremes or live swing pivots), maker entry, stop just beyond the level; each order simulated on its own; TRAIN picks 1 of 8 cells; gates include beating control orders at the same distance from price at random bars, on TRAIN and VALID. Writes `results/<SYMBOL>/s24_level_limit/` and the generated `journal/<SYMBOL>/s24_level_limit.md` |
| `premium_confirm.py` | PLAN.md §26: reads the recorded 057 results on the 10 confirmation coins (no backtest) and applies the pre-registered bars (30m: positive on ≥7, SKILL on ≥5; 4h: pooled ≥100 trades, mean > 0, weekly-block CI > 0, ≥7 coins positive). Writes `results/_multi/s26_premium_confirm/` and the generated `journal/_multi/s26_premium_confirm.md` |
| `meta_lessons.py` | reads every coin's recorded results (no backtest) and writes `journal/_multi/meta_lessons.md` + `results/_multi/meta_lessons/`; lessons summarised by hand in `docs/research/LESSONS.md` |

Engine facts to remember:
- R = stop distance. `gross_r - cost_r = mean R` per trade. At a 0.5%
  stop, costs alone are ≈ 0.28 R per trade. **Wide stops are cheap stops**
  (the main finding so far, Exp 004).
- One position at a time. Position size = 1% equity ÷ stop distance (max 10x
  leverage).
- Break-even and trailing stops move using the **previous** bar's close
  (fixed in Exp 011).
- **Exit on a signal** (BTC Exp 031, owner-approved): optional signal
  columns `exit_long` / `exit_short`, made by `recipe(..., exit_on="opposite")`,
  close a position at the next bar's open (taker + slippage, reason
  `signal`). They are checked before entries, so an opposite entry on the same
  bar reverses. Off unless an idea sets `exit_on`.
- **Metrics columns** (PLAN.md §14, BTC Exp 035): when
  `data/cache/<SYMBOL>/<SYMBOL>_metrics.parquet` exists, `get_bars(tf)` adds
  `oi`, `oi_usd`, `top_acct_ls`, `top_pos_ls`, `acct_ls`, `taker_ls`. A row
  is used 5 min after its `create_time`, as-of the bar close. A row more than
  30 min stale is NaN, and bars before `metrics_start` are NaN. The engine
  never reads them. The blocks `oi_flush`, `crowd_fade`, `smart_divergence`
  and `oi_rising` need them and refuse without them.
- **Coinbase premium columns** (PLAN.md §25): when
  `data/cache/<SYMBOL>/<SYMBOL>_premium.parquet` exists, `get_bars(tf)` adds
  `cb_prem` (own coin) and, from BTCUSDT's cache, `cb_prem_btc`. The hourly
  candle opening at H is used from H + 1h + 2 min; older than 3 h is NaN. Only
  `premium_cross` / `premium_side` read them.
- Funding is charged as **position notional × rate** (qty × price at the open
  of the bar holding the settlement). Before BTC Exp 030 it was qty × rate,
  i.e. almost zero; every record made before that has near-zero funding
  (found in ETH Exp 002, fixed in BTC Exp 030).
- Short P&L is signed by side (fixed in Exp 015; before that every short was
  inverted). `evaluate.py` runs on a 1,000 USDT research account
  (`C.EVAL_EQUITY`) so every trade can be sized. Each report shows
  `size_skips` for TRAIN and VALID: it must be 0, and since Exp 021 a
  non-REJECT result with skips is `UNSIZABLE`. 1,000 USDT × 1% = 10 USDT of
  risk; with a 0.001 BTC step a stop of `s` can be sized only while
  BTC < 10 / (0.001 × s): a 10% stop stops sizing at 100,000, a 20% stop at
  50,000. `tf_variants.py` warns when a variant's stop is past that line.
- The research account is `C.EVAL_EQUITY` = 1,000 USDT, except where a
  symbol's spec sets `eval_equity`: **SOLUSDT uses 20,000**, because its step is
  a whole SOL. Never change it to make something pass.

---

## 8. Journal and reporting

`evaluate.py` writes `evaluations.md` for you. You write, by hand, only a
**batch summary** in `journal/<SYMBOL>/experiments.md` every ~5 ideas, or
when something important happens. Use the next Exp number:

```markdown
---

## Exp NNN — <batch title>

**Date:** YYYY-MM-DD
**Status:** complete

### Ideas tested
| idea file | eval_id | verdict | valid mean R | 95% CI | note |
|---|---|---|---|---|---|

### What we learned
2–5 bullets: which hypotheses died and why, which block combinations look
promising, what to try next.

### Verdict
KEEP | WATCH | REJECT | INCONCLUSIVE — one paragraph.
```

**Reporting to the owner (in Thai):** number of ideas tried, how many were
PASS / WATCH / REJECT, the best one with `trades, mean R, 95% CI, CAGR,
maxDD`, and the holdout result if any. Never say "profitable" unless the
holdout is `CONFIRMED`.

---

## 9. When something goes wrong

| Symptom | Fix |
|---|---|
| `FileNotFoundError ... native ... klines` | `python src/datafeed.py` |
| `unknown SYMBOL` | add it to `SYMBOL_SPECS` (§6) or unset `SYMBOL` |
| `unknown trigger/filter 'x'` | check names with `python src/evaluate.py --list` |
| `grid has N combinations; the limit is 64` | fewer values per grid key |
| `already evaluated as ...` | the exact idea exists. Change the idea (new file) — `--rerun` only after a code fix |
| `--final refused` | working as intended. Do not bypass it |
| Verdict `UNSIZABLE`, or `tf_variants.py` prints `!! ... can be sized only while` | the stop is too wide for the research account at BTC's price. Narrow the `pct` stop in the source idea (new file), or leave that timeframe out with `--tfs`. Never raise `EVAL_EQUITY` or the risk |
| `refused: N evaluations already share this idea's structure` | the version budget for this idea is used up. Test a structurally different hypothesis. Never add a do-nothing filter just to change the structure |
| Windows: every combo crashed | fixed; if it recurs, run with `--workers 1` and report it |
| `test_engine.py` shows FAIL | undo your last change to `src/`, or fix it. Never edit the test to pass |
| A result looks amazing (mean R > 0.3, win rate > 70%, DD < 2%) | assume a bug: look-ahead, a too-small sample, or a single year. Check the trades file |
| Unsure what to do | re-read §1. Still unsure: ask the owner. Never guess on rules §3 |

---

## 10. End of session — definition of done

1. `python src/test_engine.py` → `ALL CHECKS PASSED`.
2. Every evaluation is in `evaluations.csv` / `evaluations.md` (automatic).
3. A batch summary is in `experiments.md` if you tested ≥ 3 ideas.
4. `journal/<SYMBOL>/STATUS.md` is updated if the picture changed.
5. `git add` your idea files, `src/` changes, journal and results (not
   `data/`), then commit with a message that says what was tested and the
   verdicts.
6. Tell the owner (in Thai) what you did (§8).
