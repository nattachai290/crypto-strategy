# FINAL REPORT — BTCUSDT USDT-M intraday & swing strategy research

> ### สรุปสำหรับเจ้าของ (Thai summary)
>
> **คำตอบสั้น ๆ: ยังไม่มีเทคนิคใดที่พิสูจน์ได้ว่าทำกำไรหลังหักต้นทุนจริง**
> และ **ไม่มีกฎจังหวะเวลาใดที่ชนะการแค่ถือ BTC** ครับ
>
> ผลรวม **131 การทดสอบ** 130 ไฟล์ idea บนข้อมูล Binance จริงทุก timeframe
> (1m, 3m, 5m, 15m, 30m, 1h, 4h) ช่วงปี 2020-01 ถึง 2026-08 ~80 เดือน คิดต้นทุนจริง
> (taker 0.05% / maker 0.02%, slippage 0.02%, funding จ่ายตามเวลาจริง, 1% ความเสี่ยงต่อไม้)
>
> | ผลลัพธ์ | จำนวน |
> |---|---|
> | PASS | 5 แถว (เป็น config เดียวกันบางตัวซ้ำ) |
> | WATCH | 18 |
> | REJECT | 97 |
> | INCONCLUSIVE | 11 |
> | **ยืนยันบน holdout (CONFIRMED)** | **0** |
>
> **มี 5 ครั้งที่ผ่านทุกเกตบน VALID แต่ไม่มีครั้งไหนรอด:**
> - 022 ผ่านเกต (mean R +0.2276) และ `baseline.py` บอก SKILL → **ใช้ holdout → ได้ −0.0102 R = FAILED**
> - 023, 027 ผ่านเกต แต่ `baseline.py` บอก DRIFT → `--final` ปฏิเสธ
> - 029 ที่ 4h ผ่านเกต (mean R +0.1131) แต่ DRIFT บน TRAIN → `--final` ปฏิเสธ
>
> **holdout ถูกใช้ไป 2 ครั้งในทั้งโปรเจคต์ และทั้งสองครั้งล้มเหลว**
>
> **สิ่งที่เรียนรู้แล้วใช้ต่อได้จริง 3 ข้อ** (นี่คือผลที่มีค่าที่สุดของงานนี้):
> 1. **stop ต้องเป็น "ระยะราคา" ไม่ใช่ "เท่า ATR"** — `cost_r = ต้นทุน ÷ stop%`
>    stop แบบเท่า ATR แอบบางลงตามรีเจม (2.83% → 0.78% ของราคา ระหว่าง 2020-22 กับ 2023-24)
>    ทำให้ `cost_r` พุ่ง 0.109 → 0.179 และกิน edge ทั้งหมด
> 2. **ความกว้าง stop เปลี่ยน "หน่วยวัด" ไม่ใช่แค่ความเสี่ยง** — สูตรเดียวกันให้ `gross_r` ต่างกัน 2.3 เท่า
>    ระหว่าง stop 1% กับ 2.83% ดังนั้น **ห้ามเทียบ `gross_r` ข้ามความกว้าง stop**
> 3. **ทุกไอเดียลที่ผ่านเกตในโปรเจคต์นี้ เป็น drift** — การสุ่มเวลาเข้าในฟิลเตอร์เดียวกัน
>    ทำได้ดีพอๆ กัน ตัวควบคุม `baseline.py` และ `benchmark.py` คือสิ่งที่ทำให้เห็นเรื่องนี้
>
> **คำแนะนำ: อย่าใช้เงินจริงกับสิ่งใดในโปรเจคต์นี้** และถ้าจะเดินหน้าต่อ ควรเริ่มจาก
> ตัวเลขเรื่องต้นทุนข้อ 1-2 ข้างบน ไม่ใช่จากการหา indicator ที่ดีกว่าเดิม
> (รายละเอียดทั้งหมดด้านล่าง)

---

**Scope:** BTCUSDT USDT-M perpetual only, Binance public data, 1m/3m/5m/15m/30m/1h/4h
native bars, 2020-01 .. 2026-08. Costs at VIP0 retail. Risk 1% per trade.
Splits: TRAIN 2020-2022, VALID 2023-2024, HOLDOUT 2025-01..2026-08 (locked,
used twice, both times failed).

**Records:** `results/BTCUSDT/evaluations.csv` (131 rows),
`journal/BTCUSDT/experiments.md` (Exp 000-022), `journal/BTCUSDT/evaluations.md`,
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
| **Regime** | trend state (long/flat, long/short), +ADX, +volatility ceiling, squeeze→expansion | PASS on gates but NO_EDGE against buy & hold (20/20 benchmarks) |
| **Timing** | session opens (London/NY), funding windows, daily open (00:00 UTC), weekdays, entry hour | no filter survived; weekday and hour effects were noise at 60-70 trades |
| **Exit management** | fixed TP, TP in R, break-even, ATR trailing (early and late), time stop 2h-24h, stop width 1-4%, stop kind pct/swing | moved mean R from +0.102 to +0.228 on VALID and to **-0.010 on the holdout** |
| **Timeframe** | all seven native timeframes on every idea | monotone gradient; a real signal is unaffordable below 30m |
| **Execution** | taker vs post-only at offsets 0-0.3 ATR | post-only worth ~+0.015 R at a 92% fill rate |

## 2. Every PASS, and what happened to it

Five rows have ever read PASS. None survived.

| config | verdict on VALID | baseline | benchmark | holdout |
|---|---|---|---|---|
| **022** long Donchian, 30m, 1% stop | mean R +0.2276, CI [+0.002, +0.468], 258 trades | SKILL | NO_EDGE | **FAILED: -0.0102 R**, gross +0.098 vs cost 0.108 |
| **023** long/flat regime, 1h | mean R +0.1148, CI [+0.014, +0.220], 198 trades, maxDD 4.8% | SKILL (vacuous: modes A and B are the same experiment) | **NO_EDGE** | refused (regime rule needs ALPHA) |
| **027** multi-day pullback, 30m | mean R +0.1967, CI [+0.025, +0.373], 175 trades | **DRIFT** (TRAIN below random entries) | NO_EDGE | refused |
| **029** opening range, 4h | mean R +0.1131, CI [+0.006, +0.223], 286 trades | **DRIFT** (TRAIN below random entries) | NO_EDGE | refused |

Plus the two long-form rows for 022 (the pre- and post-`--final` runs).

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

The signal did not change. `gross_r` is positive at **all seven** timeframes and
the net is negative at six, purely because R is a smaller unit of price on a
finer chart. Any verdict below 30m in this project is that arithmetic, not a
statement about the hypothesis.

Two corollaries that cost real money to learn:

- **A stop measured in ATR multiples is not a constant price distance.** The same
  3.0× ATR was 1.28% of price in 2020-2022 and 0.78% in 2023-2024, moving
  `cost_r` 0.109 → 0.179 for one unchanged configuration. Use a `pct` stop.
- **A stop's width changes the units of the measurement, not just the risk.**
  `gross_r` is not comparable across stop widths. This is how 022 passed.

## 4. Two engine defects found and fixed

Both were found by the agent rather than by a test, and both invalidated work
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
  alpha per year with a 95% CI, CAGR, max drawdown, Sharpe. **All 20 runs in the
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
   from direction is closed: 6 long entries, 7 short entries, 4 regime rules, 20
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

## 7. What would change the answer

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
