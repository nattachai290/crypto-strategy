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
>    −0.261 at every clock, in 2023 and in 2024**. Fading a rally that arrives
>    with *rising* open interest is the losing trade. That is a new statement:
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
