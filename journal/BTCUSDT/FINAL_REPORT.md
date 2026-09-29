# FINAL REPORT — BTCUSDT USDT-M intraday & swing strategy research

> ### สรุปสำหรับเจ้าของ (Thai summary)
>
> **คำตอบสั้น ๆ: ยังไม่มีเทคนิคใดที่พิสูจน์ได้ว่าทำกำไรหลังหักต้นทุนจริง**
> และ **ไม่มีกฎจังหวะเวลาใดที่ชนะการแค่ถือ BTC** ครับ
>
> ผลรวม **210 การทดสอบ** 207 ไฟล์ idea บนข้อมูล Binance จริงทุก timeframe
> (1m, 3m, 5m, 15m, 30m, 1h, 4h) ช่วงปี 2020-01 ถึง 2026-08 ~80 เดือน คิดต้นทุนจริง
> (taker 0.05% / maker 0.02%, slippage 0.02%, funding จ่ายตามเวลาจริง, 1% ความเสี่ยงต่อไม้)
>
> | ผลลัพธ์ | จำนวน |
> |---|---|
> | PASS | 9 แถว (เป็น config เดียวกันบางตัวซ้ำ) |
> | WATCH | 39 |
> | REJECT | 132 |
> | INCONCLUSIVE | 30 |
> | **ยืนยันบน holdout (CONFIRMED)** | **0** |
>
> **มี 7 config ที่ผ่านทุกเกตบน VALID แต่ไม่มีตัวไหนรอด:**
> - 022 ผ่านเกต (mean R +0.2276) และ `baseline.py` บอก SKILL → **ใช้ holdout → ได้ −0.0102 R = FAILED**
> - 023 ผ่านเกตและ `baseline.py` บอก SKILL แต่เป็นกฎแบบ regime ซึ่งต้องได้ ALPHA (benchmark บอก NO_EDGE) → `--final` ปฏิเสธ
> - 027 ผ่านเกต แต่ `baseline.py` บอก DRIFT → `--final` ปฏิเสธ
> - 029 ที่ 4h ผ่านเกต (mean R +0.1131) แต่ DRIFT บน TRAIN → `--final` ปฏิเสธ
> - 038 ที่ 4h ผ่านเกต **และเป็น ALPHA ครั้งแรกของโปรเจคต์** (alpha +10.2%/ปี, beta 0.01) → **ใช้ holdout → gross เป็นลบ −0.090 = FAILED**
> - 039 ที่ 5m ผ่านเกต และเป็น ALPHA (alpha +10.0%/ปี, beta 0.01) บวกทั้ง 7 timeframe → **ใช้ holdout → +0.0129 R = FAILED**
>
> **holdout ถูกใช้ 4 ครั้ง ล้มเหลวทั้ง 4 ครั้ง** (ครั้งแรก example_trend_breakout เป็นการทดสอบระบบล็อกตอนตั้ง repo ไม่ใช่งานวิจัย)
>
> **สิ่งที่เรียนรู้แล้วใช้ต่อได้จริง 4 ข้อ** (นี่คือผลที่มีค่าที่สุดของงานนี้):
> 1. **stop ต้องเป็น "ระยะราคา" ไม่ใช่ "เท่า ATR"** — `cost_r = ต้นทุน ÷ stop%`
>    stop แบบเท่า ATR แอบบางลงตามรีเจม ทำให้ `cost_r` พุ่ง 0.109 → 0.179 และกิน edge ทั้งหมด
> 2. **ความกว้าง stop เปลี่ยน "หน่วยวัด" ไม่ใช่แค่ความเสี่ยง** — สูตรเดียวกันให้ `gross_r` ต่างกัน 2.3 เท่า
>    ดังนั้น **ห้ามเทียบ `gross_r` ข้ามความกว้าง stop**
> 3. **ต้นทุนไม่ใช่ฟ้า — เป็นเรื่องของการออกแบบ** — ต้นทุนคงที่ ≈ 0.11% ของราคาต่อไม้ทุก timeframe
>    เมื่อใช้ stop 6% + ถือหลายวัน (`--mode time`) `cost_r` แบนที่ 0.02 R ทั้ง 7 timeframe
>    เดิมต่างกัน 26 เท่า (0.505 R ที่ 1m) — เป็นผลของวิธีสร้าง variant ไม่ใช่ความจริงของตลาด
> 4. **"ราคาขยับจริง" ≠ "จุดเข้ามีค่า"** — 039 มี gross บวก 12.5 เท่าของต้นทุน และยังบวก
>    ทั้งสองปีของ holdout แต่จุดเข้าไม่ชนะการสุ่มเวลา (ดูข้อ 8 ด้านล่าง)
>
> **คำแนะนำ: อย่าใช้เงินจริงกับสิ่งใดในโปรเจคต์นี้** — holdout ไม่เคยยืนยันอะไรได้แม้แต่ครั้งเดียว
> (รายละเอียดทั้งหมดด้านล่าง)

---

**Scope:** BTCUSDT USDT-M perpetual only, Binance public data, 1m/3m/5m/15m/30m/1h/4h
native bars, 2020-01 .. 2026-08. Costs at VIP0 retail. Risk 1% per trade.
Splits: TRAIN 2020-2022, VALID 2023-2024, HOLDOUT 2025-01..2026-08 (locked,
used four times, failed four times; the first use was the lock test during repo
setup).

**Records:** `results/BTCUSDT/evaluations.csv` (210 rows),
`journal/BTCUSDT/experiments.md` (Exp 000-028), `journal/BTCUSDT/evaluations.md`,
`baselines.md`, `benchmarks.md`.

## 1. The question and the answer

The brief was: find a trading technique on BTCUSDT USDT-M perpetual that makes
money after realistic costs.

**Answer: none was found, and the search was thorough enough to be useful.**

The project tested, and closed:

| dimension | what was tested | result |
|---|---|---|
| **Direction** | long-only, short-only, both sides | short breakouts lose significantly (7/7 negative on VALID, 6 of 7 with the whole CI below zero) |
| **Entry family** | Donchian, EMA cross, pullback, Supertrend, Keltner, momentum, RSI, Bollinger, z-score, VWAP, failed-break, previous-day break, opening range, liquidation flush, random | 6 long entries DRIFT, 1 holdout FAILED, 4 new market-structure blocks REJECT |
| **Regime** | trend state (long/flat, long/short), +ADX, +volatility ceiling, squeeze→expansion | PASS on gates but NO_EDGE against buy & hold (22/22 benchmarks in the project) |
| **Timing** | session opens (London/NY), funding windows, daily open (00:00 UTC), weekdays, entry hour | no filter survived; weekday and hour effects were noise at 60-70 trades |
| **Exit management** | fixed TP, TP in R, break-even, ATR trailing (early and late), time stop 2h-24h, stop width 1-7%, stop kind pct/swing | moved mean R from +0.102 to +0.228 on VALID and to **-0.010 on the holdout** |
| **Timeframe** | all seven native timeframes on every idea, in two variant modes | the monotone gradient of Rounds 1-4 was an artefact of `tf_variants` chart mode; `--mode time` holds `cost_r` at 0.02 R on all seven |
| **Hold length** | 4h to 120h, both directions, no trend filter (Round 5) | the only way to make the gross move exceed the flat 0.11% cost line; it produced the project's first ALPHA results, and the holdout killed them |
| **Block combinations** | `taker_flow`+`volume_spike`, `failed_break`+`flush`, `momentum`+`funding_not_crowded`, `ema_cross`+`supertrend_flip`+`di_side`, `donchian_break`+`squeeze` (Round 6) | one clean family kill, one untestable-by-construction, one PASS that failed the holdout with a *positive* gross |
| **Execution** | taker vs post-only at offsets 0-0.3 ATR | post-only worth ~+0.015 R at a 92% fill rate |

## 2. Every PASS, and what happened to it

Nine rows have ever read PASS, across seven distinct configurations. None
survived.

| config | verdict on VALID | baseline | benchmark | holdout |
|---|---|---|---|---|
| **022** long Donchian, 30m, 1% stop | mean R +0.2276, CI [+0.002, +0.468], 258 trades | SKILL | NO_EDGE | **FAILED: -0.0102 R**, gross +0.098 vs cost 0.108 |
| **023** long/flat regime, 1h | mean R +0.1148, CI [+0.014, +0.220], 198 trades, maxDD 4.8% | SKILL (vacuous: modes A and B are the same experiment) | **NO_EDGE** | refused (regime rule needs ALPHA) |
| **027** multi-day pullback, 30m | mean R +0.1967, CI [+0.025, +0.373], 175 trades | **DRIFT** (TRAIN below random entries) | NO_EDGE | refused |
| **029** opening range, 4h | mean R +0.1131, CI [+0.006, +0.223], 286 trades | **DRIFT** (TRAIN below random entries) | NO_EDGE | refused |
| **038** opening range both sides, 4h | mean R +0.1753, CI [+0.032, +0.327], 155 trades, gross +0.99% of price vs 0.11% cost | **DRIFT** | **ALPHA** +10.2%/yr, beta +0.01 | **FAILED: -0.1118 R**, gross **-0.090** |
| **039** breakout + taker flow + volume, 5m | mean R +0.2223, CI [+0.073, +0.379], 106 trades, gross +1.45% of price vs 0.12% cost, positive on all 7 clocks | **DRIFT** | **ALPHA** +10.0%/yr, beta +0.01 | **FAILED: +0.0129 R**, gross **+0.032** |

Plus the pre- and post-`--final` duplicate rows for 022, 038 and 039.

**The single most instructive failure is 022**, because it passed everything
available at the time and the mechanism is fully understood:

- It differed from a DRIFT configuration by **one parameter**: the stop, 2.83% of
  price → **1.0%**.
- A 1% stop makes the R unit 2.8× smaller, so the *same* price move scores 2.8×
  more R. `gross_r` went 0.145 → 0.334 **with no new information**, and
  `cost_r` went 0.043 → 0.106.
- VALID was carried by 2023 (+0.3496) over 2024 (+0.1355), and the CI lower
  bound was **+0.0023** - one bootstrap resample from failing.
- On the holdout, `gross_r` collapsed 71% to +0.098 while the cost stayed at
  0.108. 0.098 - 0.108 = -0.0102, exactly what the holdout reported.

There was never an edge. There was a temporarily large gross number divided by a
small R.

## 3. The one mechanism that reproducibly works

`cost_r = round_trip_cost / stop_pct`

Everything positive in this project came from making `cost_r` small, and
everything negative came from failing to. The evidence is unusually clean because
the same idea was measured at every timeframe:

| | 1m | 3m | 5m | 15m | 30m | 1h | 4h |
|---|---|---|---|---|---|---|---|
| **cost_r**, 1h source, pct stop (Exp 016) | 0.505 | 0.176 | 0.119 | 0.061 | 0.043 | 0.038 | 0.019 |
| **valid mean R**, 029 opening range | -0.486 | -0.276 | -0.184 | -0.061 | -0.038 | +0.000 | **+0.113** |
| **valid gross_r**, 029 opening range | +0.049 | +0.030 | +0.019 | +0.029 | +0.023 | +0.041 | **+0.141** |

Read the 029 rows with care (corrected in Exp 023): the opening-range window
cannot be shorter than one bar, so at 4h the "first 30/60/120 minutes" is the
whole 00:00-04:00 bar, and at 1h every `mins` value is the 00:00 bar. The 4h
row therefore tests "break of the first 4h bar", not the pre-registered first
hour, and its grid was inert. The signal is **not** identical across the
columns, so this table is not a clean cost-only comparison. The cost gradient
itself is real and is measured cleanly on the same-signal families of Exp 016
(first row). `gross_r` is positive at all seven timeframes for 029 and the net
is negative at six; below 30m the verdict is dominated by that arithmetic.

Two corollaries that cost real money to learn:

- **A stop measured in ATR multiples is not a constant price distance.** The same
  3.0× ATR was 1.28% of price in 2020-2022 and 0.78% in 2023-2024, moving
  `cost_r` 0.109 → 0.179 for one unchanged configuration. Use a `pct` stop.
- **A stop's width changes the units of the measurement, not just the risk.**
  `gross_r` is not comparable across stop widths. This is how 022 passed.

## 4. Two engine defects found and fixed

Both were found during review rather than by a test (the sign bug by the research agent, the sizing bias while verifying its fix), and both invalidated work
that had already been recorded.

**Exp 014 - short P&L had the wrong sign.** `close_position()` computed realised
P&L as `qty * (exit - entry)` with no `pos_side`. For a long that is correct; for
a short it inverts the sign. Entry slippage, stop and target placement, funding
and the mark-to-market equity line all carried the sign correctly, so it was an
oversight in one place rather than a convention. 16 of the 18 evaluations then on
record traded the short side, and 13 had the sign of their edge flipped: the
project's "best strategy" at the time was really **-0.1721 R**, CI
[-0.274, -0.057] - significantly losing.

`test_engine.py` passed throughout, and could not have caught it:
the hand-computed test is a long, and the "independent" reference implementation
contained the identical wrong line, so the differential test only proved the two
agreed. Both are fixed, and the suite now has a mirror-symmetry test and a
hand-computed short.

**Exp 015 - a 100 USDT account could not size most trades.** BTC's minimum is
0.001 BTC; at 2024 prices with a 2% stop one step already risks more than 1% of
100 USDT, so the engine floored the size to zero and skipped. It was worse than a
sample-size problem, because a *losing* strategy's equity falls and so skips more
of its own trades. Research now runs on a 1,000 USDT account (1% risk unchanged),
and `size_skips` is reported on every run.

## 5. What the controls are for

Two controls were added during the project, and between them they are what turned
a list of plausible backtests into an answer.

- **`baseline.py`** re-runs an idea's frozen exits and filters with **random
  entries** and asks whether the real entries beat random timing. SKILL requires
  beating the 95th percentile of both "random at any time" and "random within the
  same filters", **on both TRAIN and VALID**. Every idea in this project that
  passed the gates was DRIFT on this test, except the regime rules, whose SKILL is
  vacuous because the trigger *is* the filter.
- **`benchmark.py`** compares the rule with 1× buy & hold on daily returns: beta,
  alpha per year with a 95% CI, CAGR, max drawdown, Sharpe. **All 22 runs in the
  project are NO_EDGE.** No configuration has alpha; none is RISK_EDGE.

The lesson they encode: **a long-only rule in a bull market makes money without
needing an edge, and only a comparison against random timing and against holding
the asset can tell the difference.** Sharpe and alpha, never CAGR - at 1% risk
with a wide stop, beta is 0.03-0.22 and CAGR is small by construction.

## 6. Three directions worth a future programme

Not "more indicators". Each of these follows from a specific measurement.

1. **Treat cost as the design constraint, not the outcome.** The only
   configurations with small `cost_r` were a regime rule with a 10% stop
   (0.022 R) and a pullback with a 4% stop held 2-4 days (0.036 R), both reached
   by making the stop wide and the hold long. A programme that designs for
   `cost_r < 0.05 R` first and picks entries second would start from a
   fundamentally better position than this one did. Carryover: the `pct` stop, the
   cost arithmetic, and the warning that a verdict below 30m is a cost artefact.
2. **Look for edges that do not depend on BTC's direction.** Everything that came
   from direction is closed: 6 long entries, 7 short entries, 4 regime rules, 22
   benchmarks, 1 holdout failure. The untested space in crypto perps is
   structural and mechanical - cross-exchange basis, funding carry as a position
   rather than a filter, liquidation cascades measured properly (this project's
   `flush` block was a proxy, and it found no gross edge in either direction),
   session microstructure at sub-minute resolution, and order-book imbalance.
3. **A different asset, or accept the answer.** Every finding here is specific to
   BTCUSDT at VIP0 costs on 1-4h horizons, and BTC is the most efficient and most
   arbitraged market in existence. The same harness on a slower or less liquid
   market is a genuinely different research problem, and the tooling
   (`evaluate.py`, `baseline.py`, `benchmark.py`, the locked holdout) transfers
   unchanged. Adding a symbol is a Level 3 change and needs the owner's approval.


## 7. Round 5 (added after Exp 023): cost first, multi-day, both-sided

Rounds 1-4 designed the signal first and measured cost afterwards. Exp 023
converted gross and cost to % of price per trade and found the whole story in two
rows: cost is **flat at ~0.11% of price per trade at every timeframe**, and only a
longer hold makes the gross move bigger than that. Round 5 therefore fixed the
cost side first - 4h source, `--mode time` variants, 4-7% stops, 48-120h holds,
both directions, no directional filter, >=150 TRAIN signals counted before
running - and removed the drift by construction.

**42 evaluations: 1 PASS, 9 WATCH, 17 REJECT, 15 INCONCLUSIVE.** The design
delivered what it promised:

| | Exp 016, chart mode | **Round 5, `--mode time`** |
|---|---|---|
| `cost_r` across the 7 timeframes | 0.505 R (1m) to 0.019 R (4h), a **26:1 spread** | 0.016-0.023 R on **all seven**, a 1.4:1 spread |

That is the round's methodological result, with its limit stated (corrected in
Exp 025): **for a multi-day hold, `--mode time` keeps cost at ≈ 0.02 R on every
timeframe**, so a multi-day signal can be compared across timeframes without
cost deciding the answer. It does not make short-horizon trading affordable:
a trade held for minutes or hours still pays ≈ 0.11% of price against a small
move, exactly as in Rounds 1-4.

With cost solved the answer did not change. **038 (00:00 opening-range break, 4h)
became the project's first and only PASS + ALPHA** - valid 155 trades, gross
**+0.99% of price per trade** against a cost of 0.11% (a 9:1 ratio no earlier
idea reached), 77 long and 78 short trades, **beta +0.01**, alpha **+10.2%/yr with
CI [+1.4, +18.3]**. Its return was demonstrably not BTC's direction, which is the
first time that has been true here.

**It failed the holdout.** 135 trades, `gross_r` **-0.090**, mean R **-0.1118**,
CI [-0.244, +0.021], CAGR -6.4%. The gross edge was 2023-24.

| config | verdict | baseline | benchmark | holdout |
|---|---|---|---|---|
| 038 opening range, 4h | **PASS** | DRIFT | **ALPHA** | **FAILED** (-0.1118 R) |
| 035 multi-day momentum, 4h | WATCH | DRIFT | ALPHA | not eligible (not a PASS) |
| the other 9 WATCHes | WATCH | DRIFT | NO_EDGE | - |

**The most useful single result in the project is that 038 was DRIFT and ALPHA at
the same time.** `baseline.py` said its entry has no timing skill: on TRAIN its
-0.005 sat below the 95th percentile of random entries with the same stop and hold
(+0.107). `benchmark.py` said its return is not BTC's direction. Both are true,
and the only mechanism left for a strategy that made money on VALID is *being in
the market with a cheap cost structure* - an exposure decision, not an edge. It is
the cleanest separation of the three things a backtest can produce: **skill,
drift, and cost.**

Round 5 also settled three more things:

- **Mean reversion is refuted at a real horizon, not just intraday.** 034 (z-score
  over 5-10 days) had the best reversion gross ever measured here, +0.32% of
  price against a 0.108% cost, and went to VALID at **-0.098**, REJECT at all
  seven timeframes. BTC's multi-day overshoots do not come back within five days.
- **Funding carry is the one hypothesis untested rather than refuted.** It is
  INCONCLUSIVE (100 TRAIN trades, 28 VALID) because a 96h hold and a 0.015%-per-8h
  extreme-funding threshold cannot produce 100 VALID trades. It is the only idea
  in 173 evaluations that earns from funding instead of from price, and measuring
  it needs a different instrument, not another idea file.
- **Turn-of-month fade is unmeasurable in this design**, not rejected: a 5-day
  calendar window and a 96h hold leave fewer than 30 VALID trades.

## 8. Round 6 (added after Exp 027): five untested combinations, cost first

Rounds 1-5 tested one idea family at a time. Round 6 combined blocks that were
barely used or never used together - `taker_flow`, `funding_not_crowded`,
`di_side`, `squeeze`, `supertrend_flip`, `momentum` and `trigger_mode: "all"` -
each for one stated reason, with 2-3 blocks per idea and Round 5's cost design
(4h sources, `--mode time`, 6% stops, 48-120 h holds, both directions, no trend
filter, >=150 TRAIN signals counted before running).

**35 evaluations: 1 PASS, 12 WATCH, 18 REJECT, 4 INCONCLUSIVE.**

### The holdout, a fourth time

**039 `donchian_break` + `taker_flow` + `volume_spike` at 5m: PASS, DRIFT,
ALPHA.** Valid 106 trades, `gross_r` **+0.242** against a cost of 0.019, mean R
**+0.2223**, CI [+0.0728, +0.3786], CAGR +10.9%, maxDD 3.4%, 53 long / 53 short,
and a **12.5:1 gross-to-cost ratio, the highest measured in this project**. It
was positive on **all seven clocks**, not one. `--final` was permitted and run.

| split | trades | gross_r | cost_r | mean R | 95% CI | CAGR | maxDD |
|---|---|---|---|---|---|---|---|
| train 2020-2022 | 177 | +0.053 | 0.018 | +0.0351 | | +1.6% | 10.4% |
| valid 2023-2024 | 106 | +0.242 | 0.019 | +0.2223 | [+0.0728, +0.3786] | +10.9% | 3.4% |
| **holdout** | 95 | **+0.032** | 0.019 | **+0.0129** | [−0.158, +0.204] | +0.6% | 8.4% |

**FAILED** - the holdout's own random-entry control is the reason: the idea's
+0.0129 against a random median of −0.0187 (any time) and **+0.0380 (same
filters)**.

### The distinction this forces open, which the earlier rounds could not draw

| | 038 opening range @4h | **039 breakout + flow @5m** |
|---|---|---|
| VALID `gross_r` | +0.197 | +0.242 |
| HOLDOUT `gross_r` | **−0.090** | **+0.032** |
| holdout per year | 2025 −0.166, 2026 −0.028 | **2025 +0.0077, 2026 +0.0187** |
| holdout ×1.5 cost | −0.121 | **+0.0052** |
| verdict | FAILED - the edge was fake | FAILED - no demonstrable edge: +0.013 R, CI [−0.158, +0.204], below the random median in the same filters |

038's gross went negative: its structure produced nothing and the VALID number
was a two-year artefact. 039's gross stayed slightly positive (+0.032) in both holdout years
and under ×1.5 cost, but that is **not a measured edge** (corrected in Exp 029):
mean R +0.013 with CI [−0.158, +0.204] and P(>0) 0.55 is indistinguishable
from zero, and random entries with the same stop, hold and filters did better
(median +0.038). VALID's +0.242 was 8× the holdout's gross.

**So the answer (corrected in Exp 029): no tested entry adds anything over a
random entry with the same exits, once costs are paid.** With a 6% stop and a 96h
hold, being in BTC both ways is cheap enough that any entry - including a random
one - captures the small positive drift of holding it. The value, if there is
any, sits in the cost structure, which is an execution and position-sizing
decision rather than a trading technique, and the plan has no instrument for it.

### The rest of the round

- **040 `failed_break` + `flush` fade is closed, cleanly.** Negative at all seven
  clocks, −0.079 to −0.157, a spread of 0.078 R over five years. Both blocks were
  individually inert on gross and **together they are worse than either alone** -
  a caution worth keeping: a combination of two inert blocks is not
  automatically inert, because the second selects the subset of the first where
  the first is most wrong.
- **042 `ema_cross` + `supertrend_flip` + `di_side` cannot be measured.** 152
  TRAIN signals, the bare minimum, and four of seven clocks are INCONCLUSIVE on
  49-71 VALID trades. The strictness that is the point of the hypothesis is what
  makes it untestable at this frequency.
- **043 `donchian_break` + `squeeze`** is positive on all seven clocks
  (+0.043 to +0.144) and every one of them is DRIFT and NO_EDGE.
- **041@15m is the only SKILL since 022 and 023** - valid +0.1738, CI [+0.0041,
  +0.3510], 88 trades, entry beating random timing on both TRAIN and VALID. It is
  a **WATCH**, so `--final` is refused and the plan reserves the holdout for the
  owner. Its benchmark is NO_EDGE and 2023 carries it.

### The stop rule has fired

`PLAN.md` Round 6, agreed in the pre-registration: *"if Round 6 ends with no
holdout `CONFIRMED`, research on BTCUSDT stops."* It did not, so by the rule I
wrote down in advance, **BTCUSDT research stops here.**

**Final counts: 208 evaluations, 7 rows ever read PASS, 0 CONFIRMED, holdout used
four times and failed four times. Nothing in this project is a profitable
strategy, and the holdout has never confirmed anything.**

## 9. What would change the answer



Stated in advance, so the next agent knows what counts as new information:

- An idea that is **SKILL on TRAIN and VALID** and **ALPHA or better-Sharpe than
  buy & hold on both periods**, and then survives the holdout *including* the
  random-entry control that runs inside the holdout test.
- A `cost_r` below 0.05 R **and** a gross edge that the random-entry control
  cannot reproduce. Those two together are the only combination that has ever
  mattered in this project.
- A regime rule with proven ALPHA. Not SKILL: for a `trend_state` rule the
  trigger is the filter, so SKILL only says "long in up-regimes beats long at
  random times".

**Nothing in this report is a profitable strategy, and the holdout has never
confirmed anything.**

---

_Corrections (Exp 023, 2026-09-29): the Thai summary's reasons for 023's refusal,
the ATR stop figures and the holdout count; 20 → 22 benchmarks; the 029
opening-range column in §3 is not a same-signal comparison. No verdict changed._

_Corrections (Exp 025, 2026-09-29): the funding threshold is 0.015% per 8 h
(0.00015), not 0.15%; `--mode time` removes the cross-timeframe cost spread for
multi-day holds only. 038 is a single positive timeframe (1h −0.022, 30m
+0.016, 15m −0.042) whose 4h opening range is the whole 00:00–04:00 bar, and its
selection cited 029's VALID gross. No verdict changed._

_Owner decision (2026-09-29): trading only. Funding carry and basis strategies
(§6 item 2, and the "carry" line of §7) are out of scope for this project._

_Corrections (Exp 029, 2026-09-29): Round 6's "the edge was real" and "the moves
are real" are withdrawn. 039's holdout (+0.013 R, CI [−0.158, +0.204]) is no
evidence of an edge, and random entries in the same filters did better. **BTCUSDT
research is closed by the Round 6 stop rule.**_

_Engine note (Exp 030, 2026-09-29): funding was charged at ~0 (qty × rate, no price) in every evaluation above. Fixed; a re-check of all 242 BTC+ETH configs moves VALID mean R by a median of −0.002 R and changes 7 verdicts, 6 downward (022 PASS→WATCH), with no new PASS. No conclusion changes._
