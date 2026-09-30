# Research plan — finding BTCUSDT trading techniques

> **สรุปสำหรับเจ้าของ (Thai summary for the owner)**
> แผนวิจัยหาเทคนิคเทรด BTCUSDT อย่างเดียว แบ่งเป็น 4 รอบ รอบละ 5–6 ไอเดียที่ต่างกันจริง
> **ทุกไอเดียทดสอบครบทุก timeframe** (1m 3m 5m 15m 30m 1h 4h) ด้วย `src/tf_variants.py` ไม่ล็อก TF
> และออกแบบไอเดียให้เทรดบ่อยพอ เพราะเกณฑ์ผ่านต้องได้ค่าเฉลี่ยต่อไม้สูงขึ้นมากเมื่อจำนวนไม้น้อย
> - **รอบ 1** (แก้ใหม่หลังแก้บั๊ก engine ใน Exp 015): ฝั่ง long และแบบเข้าได้ทั้งสองทาง
>   ต่อยอดจากตัวที่มีแววจริง (005 เบรกช่วงเปิดตลาด, 006 long-only) + ไอเดีย "เบรกหลอก"
>   (เพราะ short ตอนหลุด low แพ้อย่างมีนัยสำคัญ)
> - **รอบ 2**: เทคนิคปิดไม้ (TP, SL, BE, trailing, time stop) บนจุดเข้าที่ดีที่สุดจากรอบ 1 รวมเป็น 2 การทดสอบ
> - **รอบ 3**: "ควรถือ BTC เมื่อไหร่" หากฎเลือกช่วงเวลาถือ (ถือ/ไม่ถือ/short ตามแนวโน้ม) แล้ว**เทียบกับการซื้อแล้วถือเฉยๆ**
>   ด้วย `src/benchmark.py` (วัด alpha, Sharpe, drawdown เทียบ buy & hold)
> - **รอบ 4**: เทคนิคแนวใหม่ที่ต้องเพิ่มบล็อก เช่น แท่งวันก่อนหน้า, opening range, ช่วงจ่าย funding, การล้างพอร์ต
> - **รอบ 5** (เพิ่มหลัง Exp 023): **ออกแบบจากต้นทุนก่อน** ต้นทุนราว 0.11% ของราคาต่อไม้ในทุก TF จึงต้องถือไม้หลายวัน (48–120 ชม.)
>   ใช้ stop 4–7% และเข้าได้ทั้งสองทางเพื่อตัดผลจากตลาดขาขึ้นออก ไอเดีย: funding carry, กลับตัวหลายวัน, โมเมนตัมหลายสัปดาห์, Keltner
>   ทุก TF ใช้ `--mode time` (stop % และชั่วโมงถือเท่ากันทุก TF)
> - **รอบ 6** (เพิ่มหลัง Exp 026): **ผสมเทคนิคที่ยังไม่เคยลองร่วมกัน** 5 ไอเดีย เช่น เบรก + แรงซื้อขายจริง + volume,
>   กับดักล่า stop (เบรกหลอก + liquidation), โมเมนตัมตอนฝูงชนยังไม่แน่น, ต้นเทรนด์ที่ยืนยัน 3 ทาง, บีบตัวแล้วเบรก
>   ใช้กติกาต้นทุนของรอบ 5 **ถ้ารอบ 6 ไม่มีตัวไหนผ่าน holdout ให้หยุดวิจัย BTC**
> - **BTC ปิดแล้ว** (Exp 029: 208 การทดสอบ, holdout ตก 4/4) → **ย้ายไป ETHUSDT (§11)**: รอบ E1 เอา 7 ไอเดียแนวต้นทุนต่ำ
>   (ถือหลายวัน, ทั้งสองทาง) ไฟล์เดิมไม่แก้ มารันกับข้อมูล ETH 49 การทดสอบ ถ้าไม่มีตัวไหนผ่าน holdout ของ ETH ให้หยุด ETH ด้วย
> - **ETH ปิดแล้ว** (ETH Exp 003: 49 การทดสอบ, PASS 0) → **รอบ S1/B1 (§12)**: 7 ไอเดียเดิมรันกับ SOLUSDT และ BNBUSDT เหรียญละ 49
>   ถ้าเหรียญไหนไม่มีตัวผ่าน holdout ให้หยุดเหรียญนั้น (SOL ใช้บัญชีวิจัย 20,000 USDT เพราะซื้อขายเป็นเหรียญเต็ม)
>
> ไอเดียไหน PASS → ทดสอบกับข้อมูลที่ล็อกไว้ (2025–26) ครั้งเดียว → ถ้ายืนยันผ่าน ทำใบสรุปกลยุทธ์
> และทดลองเทรดกระดาษ (สัญญาณอย่างเดียว ไม่ส่งออเดอร์) อย่างน้อย 3 เดือน ก่อนที่คุณจะตัดสินใจเรื่องเงินจริง

---

**Audience:** the AI agent that runs this plan. Read `AGENTS.md` first; every
rule there applies. `AGENTS.md` says **how** to test an idea; this plan says
**which ideas, in what order, and what to do with the results**.

Scope: BTCUSDT (closed, BTC Exp 029), ETHUSDT (closed, ETH Exp 003), and
SOLUSDT + BNBUSDT (§12, closed), and **TradingView strategy ports (§13, active)**.
Do not add other coins without the owner.
**Trading only** (owner, 2026-09-29): strategies that earn the funding fee
(funding carry, basis / cash-and-carry) are out of scope. Funding may be used
as a signal or paid as a cost, never as the thing the strategy earns.

---

## 1. Goal and what "done" looks like

**Goal:** find at least one trading technique on BTCUSDT USDT-M perpetual that
- passes `evaluate.py` (**PASS** on VALID 2023–24), then
- is **CONFIRMED** on the locked HOLDOUT (2025-01..2026-08), then
- survives paper trading (§6).

A clear negative answer is also a valid end: if all 4 rounds produce no PASS,
the deliverable is a final report of what was tried and why it failed (§7).

---

## 2. Starting point (don't repeat these)

From `journal/BTCUSDT/STATUS.md` and **Exp 015** (the engine fix). Everything
before Exp 015 that involved short trades was measured with an inverted P&L
and a 100 USDT account that could not size most trades. Only the cost
findings survive from that period.

| Settled finding | Consequence for this plan |
|---|---|
| Stop must be a **% of price** (`"stop": {"type": "pct"}`), not an ATR multiple | Use `pct` stops in every idea, unless the idea is *about* ATR stops |
| Costs ≈ 0.14% per round trip (0.09% with post-only entry); `cost_r = cost / stop%` | Stops ≥ 1.5% of price; prefer post-only entry (`"entry_mode": "post_only"`, offset 0–0.2 ATR) |
| **Short breakouts lose significantly** (Exp 015: all 7 short-only ideas negative on VALID, 6 of 7 with the whole CI below zero) | **No short-only breakout / trend ideas.** Shorts only inside both-direction ideas, or as fades of failed moves (R1.4) |
| **The leads are long / both-sided** (Exp 015): 005 session-open range break, both sides, train +0.079 / valid +0.067 on 390 trades (fails CI and ×1.5 cost); 006 long-only 30m EMA cross, valid +0.136 on 52 trades; 007's TRAIN grid picks **long** | Round 1 builds on these |
| Mean reversion (016 long, example range reversion) and squeeze→expansion (004, 013): negative on VALID after the fix | Answered. Don't repeat those structures |
| Hold time: Exp 009's "edges need 6–18 h" was measured with the sign bug | Unknown. Keep `max_hold_hours` in the grid when hold time matters to the hypothesis |
| The 18 evaluations were almost all 15m. 1m, 3m, 1h and 4h were never tested in the current workflow | Every idea now runs on all seven timeframes (§2b) |
| Research account = 1,000 USDT (`C.EVAL_EQUITY`), 1% risk; every report shows `size_skips` (TRAIN and VALID) | If `size_skips` > 0 the verdict is `UNSIZABLE` (unless REJECT): results with skipped trades are biased. Say so in the batch summary |

---

## 2a. Design ideas to trade often enough

The PASS gate needs the 95% CI lower bound above zero. With the per-trade
spread seen so far (sd ≈ 0.8 R), that means **mean R > 1.568 / √n**, where n
is the number of VALID trades (2023–2024):

| valid trades n | mean R needed to PASS |
|---|---|
| 100 | 0.157 |
| 150 | 0.128 |
| 220 | 0.106 |
| 300 | 0.091 |
| 500 | 0.070 |
| 1000 | 0.050 |

The best lead (005) made +0.067 on 390 trades; at that count it needs
≈ +0.08. So:
- **Aim for ≥ 300 valid trades** (≈ 3 per week) when you design an idea.
  Every extra filter cuts trades; add one only if it clearly raises mean R.
- An idea that raises mean R by cutting trades usually moves *away* from
  PASS. Check the table before celebrating.
- The number of trades an idea produces is a design choice. Adjust it on
  TRAIN (e.g. a looser threshold in the grid), never after seeing VALID.

## 2b. Every idea is tested on every timeframe

Native BTCUSDT data exists for **1m, 3m, 5m, 15m, 30m, 1h (60) and 4h (240)**.
Don't fix one timeframe; run each idea on all seven:

1. Write the idea once, at the timeframe it's most naturally described in
   (the "source" file).
2. Generate the other six: `python src/tf_variants.py ideas/NNN_name.json`.
   Default **chart mode** = the same setup on the other chart: the same bar
   counts and ATR multiples, the hold time scaled to the same number of bars,
   the `pct` stop scaled by √(tf ratio). Read the docstring of
   `src/tf_variants.py` once.
3. Evaluate all seven files. Each is its own evaluation (its own structure,
   its own version budget).
4. Read the **seven results together**:
   - A real effect usually shows on **neighbouring timeframes too**
     (e.g. 15m and 30m both positive on TRAIN). A single positive TF among
     negative neighbours is most likely luck: say so in the round summary,
     even if it PASSES.
   - Higher timeframes produce fewer trades; 4h ideas often end INCONCLUSIVE
     (see §2a). That is a result, not a failure. If a structure looks
     promising on 1h/4h but lacks trades, the fix is a new idea *designed*
     for that timeframe (looser filters, both directions), not a smaller
     grid on VALID.
   - 1m/3m variants are slow (3.5M / 1.2M bars): keep their grid ≤ 16 combos
     and use `--workers`.
5. **Round 5 uses `--mode time` for all six variants** (see Round 5 for
   why). In other rounds it is optional: `--mode time --tfs <neighbours>` tests "the same trade on a finer
   clock" (same hours, same price distances) for timeframes close to the
   source. Use it when chart mode shows a pattern and you want to know
   whether it's about *time* or about *bars*.

Counting: 7 timeframes × 6 ideas = 42 evaluations per round. The more
evaluations, the more likely one PASSES by luck. Report the total count
with every PASS (AGENTS.md rule 15). The holdout exists for exactly this.

---

## 3. How every round runs (same protocol each time)

1. **Pre-register the round.** Before running anything, append to
   `journal/BTCUSDT/experiments.md` an entry "Exp NNN — Round X
   pre-registration" listing each idea: file name, one-line hypothesis, and
   *what result would kill it*. Commit it. This stops ideas from being
   invented after seeing results.
2. **Write the idea files** (`ideas/NNN_name.json`, next free numbers),
   exactly as pre-registered. Grid ≤ 4 keys; sweep only what the hypothesis
   is about. Then generate the timeframe variants of each (§2b).
3. **Run each** (source + 6 variants): `python src/evaluate.py ideas/<file>.json`.
4. **Act on each verdict** (AGENTS.md §1 step 6). Run `python src/baseline.py`
   on **every WATCH and PASS** (AGENTS.md step 6b) and put SKILL/DRIFT next to
   it in the round summary. WATCH may get ≤ 2 diagnosed versions; a DRIFT
   WATCH should get a *different entry*, not a tuned one. PASS → §5.
5. **Round summary:** append "Exp NNN — Round X results" (template: AGENTS.md
   §8), plus a section **"What this round tells the next round"**: 2–4
   bullets that feed §4 of the next round. Update `STATUS.md` and
   `docs/research/TECHNIQUES.md` §7 (tried / don't repeat).
6. **Report to the owner in Thai** (§8), then start the next round.

A round is finished when all its ideas have a final verdict.

---

## 4. The rounds

Idea numbers below are working names. Use the next free number in `ideas/`.
Every idea: `pct` stop, post-only entry, designed for ≥ 300 valid trades
(§2a), and run on **all seven timeframes** (§2b). The "tf" in the sketches
below is only the source timeframe the idea is written in.

### Round 1 — Long and both-sided structures, built on the leads (≈ 6 h)

**Why:** after the engine fix (Exp 015), every positive signal is on the long
side or in a both-direction idea, and shorting breakouts loses
significantly. Test whether the leads (005, 006, 007-long) are real, and
whether the losing short breakouts can be turned into a *fade* of failed
breakdowns.

**R1.0 — Analysis, no new evaluation.** Load the trade lists with
`pd.read_csv("results/BTCUSDT/eval_trades/<eval_id>_valid.csv.gz")`:
005 `cdde91ae48`, 007 `93ef5c196c`, 010 `70fb497bcf` (if one is missing,
`python src/evaluate.py ideas/<idea>.json --trades-only` re-creates it
without recording anything). Write the findings in the Round 1
pre-registration entry:
- **005:** R by side (long vs short), by session hour (7, 8, 13, 14 UTC), by
  weekday, by year. Does its edge come from one side, or one session?
- **007 (long):** R by the 30-day trend of BTC at entry (up / flat / down).
  Is it just "long in a bull market"? 2023–24 was a strong bull market, so
  a long idea must also hold up on TRAIN, which includes the 2022 bear.
- **010 (short, losing):** how many bars after entry does price turn back
  up? If most losing shorts reverse within a few hours, the break below the
  12 h low was a *failed breakdown*, and R1.4 tests fading it.
- **Use:** each finding becomes a hypothesis for a new structure in this
  round or in Round 4. Never bolt it onto an existing idea as a filter.

| # | Idea | Recipe sketch | Kill if |
|---|---|---|---|
| R1.1 | **Session-open break, long only.** Does 005's edge come from the long side of the London/NY open? | trigger `range_break` (range_n 16–32, `hours` [7,8,13,14]), filter `htf_trend`; **long**; pct stop 1.5–2.5%; hold 4–12 h | train mean R ≤ 0 |
| R1.2 | **Breakout with the trend, long only** (007's TRAIN choice as its own hypothesis) | `donchian_break` (24–96) + `htf_trend` + `adx_min`; long; pct stop 2%; no TP, trail | train mean R ≤ 0 |
| R1.3 | **Pullback in an uptrend, long** | `pullback` (20/50) + `trend_ema` (50/200); long; pct stop 1.5–2.5%; TP 2R or trail | train mean R ≤ 0 |
| R1.4 | **Fade a failed breakdown** (from the losing short breakouts): price breaks below the n-bar low, then closes back above it within k bars → long. Mirror for failed breakouts → short | needs a Level 2 trigger `failed_break` (n, k) in `src/recipes.py`, causal (test 7 checks it); both directions; pct stop | fewer than 300 train trades, or train mean R ≤ 0 |
| R1.5 | **Idea 006 on every timeframe** (long-only EMA cross: +0.136 on only 52 trades at 30m). Lower timeframes give more trades | `python src/tf_variants.py ideas/006_long_only_trend.json` | positive TRAIN on neighbouring timeframes = real; one positive timeframe alone = luck |
| R1.6 | **Idea 005 on every timeframe** (session-open break, both sides) | `python src/tf_variants.py ideas/005_session_open_break.json` | same as R1.5 |

**What to take into Round 2:** the one entry + timeframe with mean R > 0 on
**both** train and valid, ≥ 150 valid trades, and a positive TRAIN result on
at least one neighbouring timeframe; if several qualify, the highest train
mean R (never pick by valid). If none qualifies, skip Round 2 and go to
Round 3; exits are studied there instead, on the first swing idea that
qualifies.

### Round 2 — Trade management: TP / SL / break-even / trailing / time (≈ 3 h)

**Why:** with the same entry, the exit decides how much of the gross edge
is kept. Exits were mis-simulated before Exp 011 and have never been studied
properly.

**Read first (Exp 017):** every Round 1 WATCH, including 018@30m, is
**DRIFT**: random long entries inside the same trend filters earn about the
same (+0.05..+0.10 R). The exit study is still worth running, because exits
decide what is kept from whatever the entries catch. But judge every exit
result with `baseline.py` too: an exit that "improves" the idea but improves
random entries just as much is an exit improvement, not an entry edge. Say
which it is.

Take the chosen entry from Round 1, **at the timeframe where it did best on
TRAIN**, and keep it exactly as it is. Run **2
evaluations** on it whose grids are exits only, so TRAIN picks the exit and
VALID judges it. With the entry's own evaluation that makes 3, the version
limit in AGENTS.md rule 5. Don't split them into more files.

| # | Exit question | Grid (≤ 4 keys, ≤ 64 combos) |
|---|---|---|
| R2.1 | **Profit side:** fixed TP or let it run; does break-even help or hurt; when should the trail start | `tp.type` ["none", "r"], `tp.r` [1.5, 3], `be_at` [0, 0.5, 1.0], `trail_at` [0, 1.0, 2.0] (with `trail_atr` 2.5) |
| R2.2 | **Risk side:** stop width, stop kind, and how long a trade may live | `stop.pct` [0.01, 0.015, 0.02, 0.03], `stop.type` ["pct", "swing"] (put `n` 16, `buffer_atr` 0.3, `min_atr` 1.5, `max_atr` 6 in the stop dict so swing works), `max_hold_hours` [4, 8, 16, 24] |

For both, read beyond the verdict: in the evaluation report, compare the
train results across the grid (`n_eligible`, `train_positive_share`) and the
exit mix (stop / tp / time %) of the chosen combo.

**Use of the results:**
- Put a table "exit technique → effect on mean R, gross_r, cost_r, stop/tp/time
  mix" in `TECHNIQUES.md` §4. That becomes the default exit set for Rounds 3–4.
- If one exit study PASSES, it goes to §5 like any PASS.
- 🛑 If the data says partial take-profit or scale-in would help (e.g. many
  trades reach +1R and then come back to the stop), write a proposal and
  **ask the owner** before any engine change (AGENTS.md §5 Level 3).

### Round 3 — When to be long BTC: regime rules vs buy & hold (≈ 6 h)

**Why:** Exp 017 showed that Round 1's profits came from *being long while
BTC trended up*, not from entry timing: random entries inside the same trend
filters did as well. So the real question is a regime question: **is there a
rule for when to be in BTC (long, flat, or short) that beats simply holding
BTC?** For that kind of strategy the opponent isn't random entries, it's
**buy & hold**, so this round is judged by `src/benchmark.py`.

**Tools for this round**
- Trigger `trend_state` (n): fires on **every bar**, long while close > EMA(n),
  short while below. With `"direction": "long"` the idea is long whenever
  the regime is up and flat otherwise.
- The engine only exits on stop / take-profit / time; it has no "exit when
  the regime ends". So `max_hold_hours` is the **re-check interval**: at the
  time exit, if the regime is still on, the next bar re-enters, paying a
  real round trip each interval. Use 24–72 h. The stop (`pct` 8–15%) is
  crash protection, not a trading stop.
- `python src/benchmark.py ideas/<idea>.json`, after `evaluate.py`: daily
  account returns vs 1x buy & hold on TRAIN and VALID. It reports **beta**
  (how much BTC exposure the rule carries), **alpha per year** with a 95% CI
  (return beyond that exposure), CAGR, max drawdown and Sharpe next to buy &
  hold's. Verdicts:
  - **ALPHA**: alpha > 0 on TRAIN and VALID, VALID CI above 0. The rule adds
    return beyond its exposure. A PASS with ALPHA may go to `--final`. **A
    regime rule (`trend_state`) goes to `--final` only with ALPHA**: SKILL
    does not count for it, and `evaluate.py` enforces this (Exp 021).
  - **RISK_EDGE**: no proven alpha, but on both periods Sharpe beats buy &
    hold **and** max drawdown is under half of buy & hold's. That's a calmer
    way to hold BTC, not an edge. 🛑 Report it to the owner, who decides.
  - **NO_EDGE**: holding (a fraction of) BTC does as well.
- Sizing: 1% risk with a 10% stop means only ~10% of the account in BTC, so
  beta is small and **CAGR will look tiny next to buy & hold. That is a sizing
  choice, not a result.** Compare Sharpe and alpha (and its CI), never CAGR.
  For reference, Round 1's 018@30m and 019@1h scored alpha ≈ 0, beta
  0.05–0.12, Sharpe below buy & hold → NO_EDGE (`journal/BTCUSDT/benchmarks.md`).
- `baseline.py` is nearly meaningless for regime ideas: the trigger is the
  filter, so its modes A and B are the same experiment, and it said SKILL for
  023 at 1h (Exp 020). For this round the benchmark is the test that matters.
  Still run both and report both.
- The stop must be sizable: a 10% stop can be sized by the 1,000 USDT research
  account only while BTC < 100,000, and the 4h variant in chart mode doubles it
  to 20% (sizable only below 50,000). Such results are `UNSIZABLE` (Exp 021).

| # | Idea (source tf 1h) | Recipe sketch |
|---|---|---|
| R3.1 | **Trend regime, long / flat.** Being long only while BTC is above its multi-day trend avoids most of the big drawdowns (2022 −64%) for a small cost in upside | trigger `trend_state` (n 100–400 on 1h ≈ 4–16 days); long; `max_hold_hours` [24, 72]; pct stop 10% |
| R3.2 | **Trend regime, long / short.** Does shorting the down-regime add return (2022), or just costs (whipsaw)? | as R3.1 with direction both |
| R3.3 | **Regime + trend strength.** Stay out of the trend regime when ADX says it's chop | `trend_state` + filter `adx_min` (20–25); long |
| R3.4 | **Regime without panic periods.** Long in the up-regime, flat when volatility spikes (crashes come with volatility) | `trend_state` + `vol_regime` (hi 1.2–1.5); long |
| R3.5 | **Multi-day pullback in the up-regime** (entry-based, judged by baseline *and* benchmark) | `pullback` + `trend_ema` (50/200); long; hold 2–4 days; pct stop 4% |
| R3.6 | **Reference table, no new idea:** run `benchmark.py` on the best configurations of Rounds 1–2, so every Round 3 result has a comparison | — |

**Use of the results**
- **ALPHA + PASS** → holdout (§5).
- **RISK_EDGE** → 🛑 report to the owner with the table (Sharpe, max
  drawdown, time in market vs buy & hold). It could be worth a strategy card
  as a "risk-managed BTC holding" rule, but only the owner decides; it is not
  a trading edge.
- **All NO_EDGE** → write it down plainly in `STATUS.md` and `README.md`:
  "no tested timing rule beats holding BTC after costs". That's a strong and
  useful result, and Round 4 should then look for edges that don't come from
  BTC's direction at all (e.g. funding, session effects).
- 🛑 If regime ideas look promising but the re-entry cost from the time-exit
  workaround is a large share of `cost_r`, propose a Level 3 engine change,
  "exit when the trigger's regime ends", to the owner instead of working
  around it.

### Round 4 — New building blocks (≈ 4 h)

**Why:** the existing 11 triggers and 15 filters are classic indicators. These
blocks test market-structure ideas that classic indicators miss. Each is a
Level 2 addition to `src/recipes.py` (causality is checked by test 7), then
evaluated like any idea. Pick the 4–5 most promising after Rounds 1–3; the
Round 3 summary should say which.

| # | New block | Hypothesis to test with it |
|---|---|---|
| R4.1 | trigger `prev_day_break` (yesterday's high/low: `groupby(date)` shifted one day) | Breaking yesterday's extreme draws in stops and breakout traders; continuation for some hours |
| R4.2 | trigger `opening_range` (high/low of the first N minutes after 00:00 UTC, then a break) | The daily candle open resets positioning; the first range break shows the day's direction |
| R4.3 | filter `funding_window` (only N hours before/after 00/08/16 UTC funding settlements) | Positions are opened/closed around funding times; the behaviour differs there |
| R4.4 | trigger `flush` (bar range > k·ATR **and** volume > m × average): fade or follow | Liquidation cascades overshoot (fade), or start trends (follow). Test both directions as 2 ideas |
| R4.5 | trigger `keltner_break` (EMA ± k·ATR) | A volatility channel break vs Donchian: fewer false breaks in quiet regimes |
| R4.6 | filter `after_drop` (BTC fell more than x% in the previous N hours) | Built from the R1.0 analysis if it showed a pre-entry drop effect |

For each block: implement → `python src/test_engine.py` (must pass) → one
line in `TECHNIQUES.md` §2/§3 → pre-registered idea file → `evaluate.py`.

### Round 5 — Cost first: multi-day, both-sided trades (≈ 6 h; added after Exp 023)

**Why.** Rounds 1–4 designed the signal first and measured the cost after.
The records show why that failed. Net mean R has the sign of
**(gross move per trade − cost per trade), both in % of price**; the stop
width only changes the unit. Median over the 105 pct-stop evaluations, on
TRAIN (`evaluations.csv`, gross_r × stop and cost_r × stop):

| tf | 1m | 3m | 5m | 15m | 30m | 1h | 4h |
|---|---|---|---|---|---|---|---|
| gross move per trade, % of price | 0.020 | 0.022 | 0.026 | 0.053 | 0.195 | 0.361 | 0.237 |
| cost per trade, % of price | 0.155 | 0.134 | 0.129 | 0.113 | 0.112 | 0.112 | 0.110 |

The cost is about 0.11% of price per trade at every timeframe. Only a longer
hold makes the gross move bigger than that. But up to now every long hold was
long-only, and a long-only hold in 2023–24 earns the drift, not an edge
(Exp 017, 019, 020). So this round fixes the cost side first and removes the
drift by design:

**Design constraints (all five, in every idea; state them in the
pre-registration):**
1. **Source file at 4h. Make the variants with `--mode time`:**
   `python src/tf_variants.py ideas/NNN.json --mode time`. The stop stays the
   same % of price and the hold stays the same number of hours on every
   timeframe, so `cost_r` is about the same on all seven and the timeframe
   comparison asks one thing only: does a finer entry clock help? (Chart
   mode would shrink a 5% stop to 0.3% at 1m and lose to cost again, the
   same result as every 1m variant in Rounds 1–4.)
2. **`pct` stop 4–7%.** Cost ≈ 0.14% taker round trip / 4% = 0.035 R, plus
   funding. Above ≈ 7.9% the 1,000 USDT account cannot size a trade at the
   2025 price peak (125,986; AGENTS.md §7), so ≤ 7% keeps every timeframe
   and the holdout sizable. `tf_variants.py` warns if you get this wrong.
3. **Hold 48–120 h** (`max_hold_hours`), no TP or TP ≥ 2R. Before running,
   write the expected cost: `(0.14% + hold_h / 8 × 0.01% funding) / stop`.
   It must be ≤ 0.05 R. After running, report the actual `cost_r`.
4. **`direction: "both"` and no directional trend filter** (`htf_trend`,
   `trend_ema`, `price_vs_ema`). A trend filter makes a both-sided idea long
   in 2023–24 again. Filters that are not directional (`adx_min`,
   `vol_regime`, `volume_spike`, `funding_window`) are allowed.
5. **Enough trades.** Count the trigger's signals on **TRAIN only**
   (2020–2022) in the pre-registration. You need ≥ 150 to hope for ≥ 100
   VALID trades once holds overlap. If one grid value is below that, drop it
   **before** running, never after.

| # | Idea (source 4h) | Recipe sketch (grid ≤ 12 combos: the 1m variant has 3.4M bars) | Kill if |
|---|---|---|---|
| R5.1 | **Funding carry.** When funding is high, longs pay shorts every 8 h; the crowded side pays, and its unwind takes days, not hours. Short the payer, collect the funding while holding. Idea 003 (15m, 12 h) never got past 13 trades, so this was never really tested | trigger `funding_extreme` alone, thresh [0.00015, 0.0002, 0.0003]; both; stop 5%; hold [72, 120]. On TRAIN, 0.00015 gives 46 long / 108 short signals: likely short-heavy. Report long and short separately | TRAIN gross_r ≤ 0 |
| R5.2 | **Multi-day reversal.** After a 5–10 day move of more than 2σ, late trend followers and forced liquidations have pushed price past fair value, and it partly comes back over days. The Exp 016 "never retry mean reversion" ban was about 15m / 12 h holds, whose gross move was below cost; this is a different horizon and is allowed here | trigger `zscore_revert`, n [30, 60] (5–10 days), z [2.0, 2.5]; both; stop 5%; hold [48, 96] | TRAIN gross_r ≤ 0 |
| R5.3 | **Multi-week time-series momentum, both sides.** A 5–20 day high or low is where trend-following funds add risk; it continued in 2022 (down) and 2023–24 (up), so a both-sided rule should work in both periods if the effect is real, and not only in the bull market | trigger `donchian_break`, n [30, 60, 120]; both; stop 6%; hold [72, 120] | TRAIN gross_r ≤ 0, or one side carries all of it in the period where it matches the drift (short in 2022, long in 2023–24) |
| R5.4 | **Volatility-channel break at a multi-day hold.** 032 (Keltner, 1h, 12 h hold) had the largest TRAIN gross of Round 4 (+0.157 R) but was DRIFT with its `htf_trend` filter; test the channel alone, both sides, held for days | trigger `keltner_break`, n [20, 50], mult [2.0, 3.0]; both; stop 6%; hold [48, 96] | TRAIN gross_r ≤ 0 |
| R5.5 | **Your own idea**, under all five constraints, with a written hypothesis about who is on the other side | — | pre-register it |

**Judge.** As always: PASS + `baseline.py` SKILL (TRAIN and VALID) →
`--final`. Because the ideas are both-sided, SKILL is meaningful here: random
entries with the same stop and hold take both sides too. Run `benchmark.py`
on every WATCH/PASS and report beta: it should be near 0; a beta above 0.1
means the idea is secretly long.

**Read these in the round summary:** `cost_r` per timeframe (should be flat,
about 0.03–0.05); gross % per trade vs the 0.11% line; long vs short mean R
and trade count; the per-year split (2020, 2021, 2022 vs 2023, 2024).

**Use of the results.** A PASS goes through §5. If nothing survives, add a
short "Round 5" section to `FINAL_REPORT.md`: cost-first multi-day both-sided
trading on BTCUSDT also has no edge. With that the plan is complete, and the
next step (other markets, VIP fees; funding/basis strategies are out of
scope by the owner's decision) is the owner's
decision, not the agent's.

### Round 6 — Combinations nobody has tested, cost-first (≈ 6 h; owner-approved after Exp 026)

**Why.** Rounds 1–5 tested one idea family at a time. Several blocks were
barely used or never combined: `taker_flow`, `funding_not_crowded`,
`di_side`, `squeeze` (only with a trend filter at 15m), `supertrend_flip`,
`momentum`, and `trigger_mode: "all"` (used once). Each idea below
**combines 2–3 blocks for one stated reason**. Round 5's cost design is kept,
because it is the only one where cost does not decide the answer.

**Hard limits for this round (write them into the pre-registration):**
- **Exactly the five ideas below**, × 7 timeframes = 35 evaluations, plus
  `_v2` / `_v3` only for a WATCH, with a diagnosis (AGENTS.md step 8). No sixth
  idea, and no ensemble or vote of earlier WATCHes (035, 036, 038): they were
  picked by their VALID results, which is the selection that made 038 fail.
- **Motivate everything from TRAIN numbers or from the hypothesis, never from
  a VALID number** (Exp 025, item 4).
- **Stop rule, agreed in advance:** if Round 6 ends with no holdout
  `CONFIRMED`, research on BTCUSDT stops. The next step is the owner's.

**Design constraints (Round 5's, unchanged):**
- 4h source files, variants made with `--mode time`;
- `pct` stop 4–7% (use **6%**: with a 96 h hold, 5% breaks the cost limit);
- hold 48–120 h;
- expected cost `(0.14% + hold_h / 8 × 0.01%) / stop` ≤ 0.05 R, written
  before running;
- `direction: "both"`, and no `htf_trend` / `trend_ema` / `price_vs_ema`;
- ≥ 150 TRAIN signals for every grid value, counted before running.

**Bans lifted for this round, and why.** `taker_flow` and
`funding_not_crowded` were banned after short-only 15m breakouts (idea
012/014), and short-only breakouts lose whatever the filter. Squeeze →
expansion was banned at 15m / ≤ 12 h holds, where the gross move was under
the cost. None of those tests was both-sided at a multi-day hold. Every other
ban stands.

**Signal counts.** Taken with `recipe()` on 4h bars, TRAIN 2020–2022 only,
`direction: both`, when this plan was written. The agent re-counts in the
pre-registration and drops any grid value under 150 **before** running.

| # | Idea: what is combined, and who is on the other side | Recipe sketch (4h source) | TRAIN signals (long / short) | Kill if |
|---|---|---|---|---|
| R6.1 | **Breakout with real aggressive flow.** A breakout that aggressive buyers (sellers) keep hitting, on above-average volume, is new positioning, and it continues. A breakout without that flow is a stop run that fills the breakout traders and reverses. The other side: resting liquidity and short-term faders | trigger `donchian_break` n [20, 30]; filters `taker_flow` (n 6, thresh 0.5) + `volume_spike` (n 30, k [1.2, 1.5]) | n20: k1.2 121/132, k1.5 89/100; n30: k1.2 103/103, k1.5 78/80 (all ≥ 150) | TRAIN gross_r ≤ 0 |
| R6.2 | **Stop-hunt trap.** Price pierces an n-bar extreme and closes back inside (`failed_break`), and within a few bars there is a liquidation-sized bar (`flush`, fade mode). Forced sellers (buyers) have been cleared at the extreme, and whoever took the other side of the cascade holds the better price. Both blocks exist; they were only ever tested apart | triggers `failed_break` (n 30, n_bars 6) + `flush` (mode fade, k [1.5, 2.0], m 1.5, lookback 30), `trigger_mode: "all"`, `confirm_bars` 3 | k1.5 214/270, k2.0 122/178 | TRAIN gross_r ≤ 0 |
| R6.3 | **Impulse before the crowd.** Follow a strong multi-bar move (`momentum`) with volume, but only while funding shows the crowd is **not** already on that side. Momentum fails when it is crowded, because the late side is who gets squeezed. Funding is used as a signal here, not earned (Exp 026) | trigger `momentum` (n 6, atr_k [1.5, 2.0]); filters `funding_not_crowded` (thresh [0.0002, 0.0003]) + `volume_spike` (n 30, k 1.5) | atr_k 1.5: 85–88 / 109–110; atr_k 2.0: 66–70 / 94 | TRAIN gross_r ≤ 0, or all of it is on one side |
| R6.4 | **Trend start confirmed three ways.** An EMA cross and a Supertrend flip in the same direction within 3 days, with +DI/−DI agreeing. Each indicator's false starts are mostly its own noise and do not coincide. Both directions, which Rounds 1–2 never tried for these blocks | triggers `ema_cross` (10, 30) + `supertrend_flip` (n 10, mult 2.0), `trigger_mode: "all"`, `confirm_bars` 18; filter `di_side` (n 14). Only this confirm value reaches 150 (confirm 12 gives 145, 6 gives 132), so the grid is exits only: stop [0.05, 0.06] × hold [48, 96] | 72 / 80 | TRAIN gross_r ≤ 0 |
| R6.5 | **Compression, then a both-sided break, held for days.** A Donchian break straight out of a Bollinger squeeze. Volatility clusters, so the break of a quiet range starts a larger move. The earlier test had a trend filter and 12 h holds; this one has neither | trigger `donchian_break` n 20; filter `squeeze` (n 20, q [0.2, 0.3], lookback 180). No `volume_spike`: with it, n 20 gives only 103–122 signals | q0.2 93/68, q0.3 104/84 | TRAIN gross_r ≤ 0 |

Grids stay ≤ 8 combos: the 1m `--mode time` variant scales bar counts ×240
(for example, squeeze's lookback 180 becomes 43,200 bars), so 1m is slow.

**Before any `--final` (Exp 025, item 3):**
- write the idea's seven timeframe results in the journal;
- in `--mode time` every timeframe is the same trade on a finer clock, so a
  PASS on one clock while the others are negative is most likely luck: say so;
- one-line check that the block did what the idea says: long/short counts in
  the trade file, and that the filter changed the trade list (not DUPLICATE).

**Judge.** PASS + `baseline.py` SKILL (TRAIN and VALID), or ALPHA, then
`--final`, as always. With both-sided, filter-light ideas, SKILL is
meaningful: mode B (random entries within the same filters) is the real test
of whether the *combination* adds anything over its filters.

**Use of the results.** A CONFIRMED goes to §6 (strategy card and paper trading,
never real money first). Otherwise, add a "Round 6" section to
`FINAL_REPORT.md` and stop, per the stop rule.

---

## 5. What to do with a PASS

1. `python src/baseline.py ideas/<idea>.json` and `python src/benchmark.py ideas/<idea>.json`.
   Neither SKILL (entries beat random timing) nor ALPHA (beats buy & hold
   beyond its BTC exposure) → stop here: it is not a strategy. Record it and
   continue the plan. SKILL or ALPHA → step 2. A regime rule (`trend_state`)
   needs ALPHA; its SKILL does not count (Exp 021).
2. `python src/evaluate.py ideas/<idea>.json --final` (one time; refused
   without PASS + (SKILL or ALPHA), and for a regime rule without ALPHA).
   SKILL is judged on TRAIN and VALID. The
   holdout run includes a random-entry control on the holdout, and
   CONFIRMED needs the idea to beat its median (Exp 019).
3. **FAILED** on holdout → record it (it's now spent for that config), lesson
   into `TECHNIQUES.md`, continue the plan.
4. **CONFIRMED** → tell the owner right away (Thai, full table), then build the
   strategy card and paper trading (§6). Continue the research rounds in
   parallel only if the owner wants.

There is no WATCH result at the moment (Exp 015). If one appears, it stays
WATCH: only the owner can decide to spend the holdout on a WATCH result.
Propose it only when an independent structure (e.g. the same idea on
neighbouring timeframes) is also positive, and let the owner decide.

---

## 6. Using a confirmed technique

### 6.1 Strategy card `strategies/<name>/CARD.md`

One page; every number traceable to `results/BTCUSDT/`:
- The rules in plain language (entry, stop, TP/trail, time exit, filters) and
  the frozen JSON.
- Evidence: train / valid / holdout, each with `trades, gross_r, cost_r,
  mean R, 95% CI, CAGR, maxDD`.
- Expectations: trades per month, win rate, average hold, longest losing
  streak in the backtest, maxDD.
- Sizing at 1% risk on the owner's account (e.g. 100 USDT with a 2% stop →
  50 USDT notional); the leverage it implies; min notional check.
- **Can the owner's real account take every trade?** Research runs use a
  1,000 USDT account (Exp 015). Re-run the frozen config once with
  `initial_equity` = the owner's capital and report its `size_skips`. BTC's
  minimum size is 0.001 BTC: at 100k with a 2% stop that one step already
  risks 2 USD, i.e. 2% of 100 USDT. If trades get skipped, state the minimum
  capital needed for 1% risk (≈ 0.001 × price × stop% ÷ 1%) instead of
  pretending the account can trade it.
- Weaknesses: how many ideas were tried in total before this one, regime
  dependence (per-year R), the unexplained parts.
- Kill criteria (6.3).

### 6.2 Paper trading `src/paper.py`, signals only (no orders, no API keys)

- Every bar close: fetch the latest closed klines + funding from Binance
  public REST, compute the signal with **the same** `recipes.recipe()` code,
  simulate fills with the engine's rules (post-only fill check, stop, trail,
  time exit, fees, slippage).
- Append to `results/BTCUSDT/paper/<name>_signals.csv` and `<name>_trades.csv`.
  State lives in the CSVs so restarts are safe. Run from cron / Task Scheduler.
- `python src/paper.py --report`: forward trades, mean R, CI, drawdown vs the
  card's expectations.
- Test: replaying one historical month through `paper.py` gives exactly the
  same trades as `run_backtest`.

### 6.3 Kill criteria and review (in the card, before paper trading starts)

- Stop and mark FAILED-FORWARD if, after ≥ 30 trades, forward mean R is below
  the backtest CI lower bound, or forward drawdown > 1.5 × backtest maxDD.
- Review with the owner after ≥ 50 trades or 3 months (whichever is later).
- Real money is the owner's decision and a separate plan. Never place orders
  or handle API keys under this plan.

---

## 7. If nothing passes

After Round 4 with no PASS, write `journal/BTCUSDT/FINAL_REPORT.md` (Thai
summary + English body):
- every round, idea count, verdicts
- the best result of each round with its full table
- what the evidence says about BTCUSDT (e.g. "no intraday edge after costs;
  swing horizon: …; short side: …")
- 3 recommended directions for a future research program, with reasons

That is a complete, useful result. Don't keep producing variants to avoid
writing it.

---

## 8. Reporting to the owner (end of every round)

In Thai, short:
1. Round X finished: N ideas, verdict counts (PASS / WATCH / REJECT / INCONCLUSIVE).
2. The best idea of the round: `trades, gross_r, cost_r, mean R, 95% CI, CAGR, maxDD`.
3. What the round taught, and what the next round will test.
4. Whether you need a decision from the owner (engine change, holdout, …).

Never say "profitable" unless the holdout is CONFIRMED.

---

## 9. Owner checkpoints 🛑

| When | Ask |
|---|---|
| An engine change would help (partial TP, scale-in, stop-and-reverse) | proposal + evidence; wait for yes |
| A WATCH result has independent support and you think it deserves the holdout | show both results; the owner decides |
| A holdout CONFIRMED | report right away, before building §6 |
| Anything involving real orders, keys or money | always; it's outside this plan |

---

## 10. Time estimate

| Round | Work | Notes |
|---|---|---|
| 1 | ≈ 6 h | 6 ideas × 7 timeframes + analysis of 005/007/010, + one Level 2 block (1m/3m runs are the slow part) |
| 2 | ≈ 2 h | 2 exit studies (combined grids) at the best timeframe |
| 3 | ≈ 6 h | 5 regime ideas × 7 timeframes + benchmark.py on each + a reference table |
| 4 | ≈ 6 h | 4–5 new blocks + ideas × 7 timeframes |
| 5 | ≈ 6 h | 4–5 cost-first ideas × 7 timeframes (`--mode time`); the 1m variants are the slow part |
| 6 | ≈ 6 h | 5 combination ideas × 7 timeframes (`--mode time`), then stop unless something is CONFIRMED |
| E1 | ≈ 7 h | ETHUSDT: 7 cost-first families × 7 timeframes (§11), then stop unless something is CONFIRMED |
| S1 + B1 | ≈ 14 h | SOLUSDT and BNBUSDT: the same 7 families × 7 timeframes each (§12), then stop per coin unless something is CONFIRMED |
| §6 | 3–4 h to build + ≥ 3 months of paper trading | only after a CONFIRMED |

---

## 11. ETHUSDT (owner-approved after Exp 029)

BTCUSDT is closed. Every rule in AGENTS.md and every protocol above (§2b–§5) applies
unchanged; this section says what is different on ETH. Everything ETH-specific
goes to `results/ETHUSDT/` and `journal/ETHUSDT/` automatically when you run with
`SYMBOL=ETHUSDT`. The ETH journal starts at Exp 000 (setup, written).

**What carries over from BTC, and what does not.**
- **Carries over, as method:**
  - cost is ≈ 0.11% of price per trade at every timeframe, so only multi-day
    holds leave room for an edge;
  - use `pct` stops;
  - use `--mode time` from a 4h source;
  - include both directions, and no trend filter, so the bull-market drift
    cannot pass as an edge;
  - run the random-entry baseline and the buy & hold benchmark on every
    WATCH/PASS.
- **Does not carry over, as evidence:** BTC's verdicts. ETH must earn its own
  verdict on its own data (AGENTS.md §6). ETH moves with BTC (daily
  correlation ≈ 0.8), so ETH's VALID 2023–24 is **not independent** of the
  BTC VALID that shaped these ideas. The ETH **holdout** (2025-01..2026-08) is
  untouched, and it is the test that counts.
- ETH is more volatile than BTC. At the same hold, a bigger gross move meets
  the same ≈ 0.11% cost, so the cost line sits a little lower. It does not
  move far enough to reopen short-horizon trading: do not add intraday ideas
  in Round E1.

### Round E1 — the cost-first families, re-measured on ETH (≈ 7 h)

**The ideas are the existing files, run unchanged** with `SYMBOL=ETHUSDT`. An
idea file is shared by all coins, and the eval_id includes the symbol, so ETH
gets its own records and its own version budget. Do not edit the files and do
not write new ones in this round. For each family, the 4h source and its six
`_tfN_time` variants are already in `ideas/`:

| family | files (source + 6 variants) | hypothesis (from its BTC pre-registration) |
|---|---|---|
| 034 multi-day reversal | `034_multiday_reversal*.json` | a > 2σ multi-day move partly comes back |
| 035 multi-day momentum | `035_multiday_momentum*.json` | 5–20 day extremes continue, both ways |
| 036 Keltner multi-day | `036_keltner_multiday*.json` | a volatility-channel break continues for days |
| 038 opening range | `038_opening_range_both_sides*.json` | the 00:00 UTC range break sets the day's direction (at 4h: the first 4h bar) |
| 039 breakout + flow | `039_breakout_flow_confirm*.json` | a breakout with aggressive flow and volume continues |
| 041 impulse, not crowded | `041_impulse_not_crowded*.json` | follow an impulse only while funding shows the crowd is not on that side |
| 043 squeeze break | `043_squeeze_multiday_break*.json` | a break out of compression runs for days |

Left out, with the reason:
- 033 funding carry: out of scope (Exp 026).
- 037 turn-of-month: unmeasurable at a multi-day hold.
- 040 stop-hunt trap: negative on TRAIN and VALID at all seven BTC clocks.
- 042 three-way trend start: too rare to measure.

These are hypotheses that are refuted or unmeasurable, not ones that looked
bad on VALID.

**Before running (pre-registration, `journal/ETHUSDT/experiments.md` Exp 001):**
1. Re-count each 4h source's signals on **ETH TRAIN only**. A family whose
   source is under 150 is still run, but it will likely be INCONCLUSIVE; say so
   in advance and never change its file.
2. Check the sizing: `tf_variants.py` prints no `!!` warning for 6% stops on
   ETH. The 1,000 USDT account sizes ETH down to its 0.001 step, and 20 USDT
   is the minimum notional.
3. Write the expected `cost_r` per family. It is the same formula as Round 5,
   using ETH's funding.

**Run:** 7 families × 7 files = **49 evaluations**, each with
`SYMBOL=ETHUSDT python src/evaluate.py ideas/<file>`. Then run `baseline.py`
and `benchmark.py` (also with `SYMBOL=ETHUSDT`) on every WATCH and PASS. The
benchmark compares with holding **ETH**.

**Before any `--final`:** the same three written checks as Round 6:
- the seven clocks, and whether the PASS is the best one of them;
- the per-year split;
- the long/short counts.

In addition, **the same config's BTC result**. A family that PASSes on ETH but
failed its BTC holdout (038, 039) is one more reason for suspicion, not a
reason to hurry.

**Stop rule, agreed in advance:** if Round E1 ends with no holdout CONFIRMED on
ETH, ETH research stops too, and the project's answer stands for both coins.
A CONFIRMED goes to §6 (strategy card and paper trading, never real money
first) and must be reported to the owner at once.

---

## 12. SOLUSDT and BNBUSDT (owner-approved after ETH Exp 004)

ETHUSDT is closed. Round E1 found 0 PASS, and 32 of 32 controls were DRIFT.
The owner asked for two more coins, **to be run by the research agent, not
by the planner**. Every rule in AGENTS.md and every protocol in §2b–§5 and
§11 applies unchanged. Run everything with `SYMBOL=SOLUSDT` or
`SYMBOL=BNBUSDT`.

### Before anything else (session start, both coins)
1. **Check that the funding fix is on main.** `python src/test_engine.py`
   must show test **1b** ("hand-computed funding (notional x rate)") and end
   with ALL CHECKS PASSED.
   - Without the fix, funding is charged at about 0 (BTC Exp 030).
   - Stop and tell the owner if 1b is missing.
2. `SYMBOL=SOLUSDT python src/datafeed.py` and `SYMBOL=BNBUSDT python src/datafeed.py`,
   each until `VALIDATION: OK`. Nothing has been downloaded for these coins
   yet. Record the row counts in each coin's Exp 001.

### What is different on these two coins
| | SOLUSDT | BNBUSDT |
|---|---|---|
| contract step / min notional | **1 SOL** / 5 USDT | 0.01 BNB / 5 USDT |
| data | 2020-10..2026-08 (listed 2020-09-14) | 2020-03..2026-08 (listed 2020-02-10) |
| TRAIN | **27 months** (2020-10..2022-12) | 34 months |
| VALID / HOLDOUT | 2023–24 / 2025-01..2026-08 | same |
| research account (`C.EVAL_EQUITY`) | **20,000 USDT** (per-symbol `eval_equity`) | 1,000 USDT |

- **Why SOL uses 20,000 USDT.** Its step is a whole coin. At 1,000 USDT, 1%
  risk and a 6% stop, a trade is about 166 USDT, less than one SOL whenever
  SOL is above 166. That would make almost every result UNSIZABLE. 20,000
  keeps about 10 SOL or more per trade. R, CI, drawdown % and CAGR do not
  depend on the account size. Risk per trade is still 1%.
- **Liquidity.** Costs are the same global 0.05% taker and 0.02% slippage.
  SOL and BNB perpetuals are liquid, but thinner than BTC/ETH, so real
  slippage is likely higher. The ×1.5 cost-stress gate is the protection. In
  the pre-registration, say that any PASS must survive it with room to spare.
- **Correlation.** Both coins move with BTC. Their VALID periods are not
  independent of the BTC/ETH work that shaped these ideas. **Each coin's
  holdout is untouched** and is the only fresh test.

### Rounds S1 and B1: the same seven families, unchanged
Same as §11 Round E1: the files `034_multiday_reversal*`,
`035_multiday_momentum*`, `036_keltner_multiday*`,
`038_opening_range_both_sides*`, `039_breakout_flow_confirm*`,
`041_impulse_not_crowded*` and `043_squeeze_multiday_break*` (a 4h source
and six `_tfN_time` variants each), run **unchanged**:
- 49 evaluations on SOL;
- 49 evaluations on BNB.

Do not edit the files and do not write new ones in this round.

**Pre-registration**, one per coin (`journal/<SYMBOL>/experiments.md`
Exp 001), written before its first evaluation:
1. Signal counts of each 4h source, on that coin's TRAIN only. A family under
   150 is still run, but say in advance that it may be INCONCLUSIVE.
2. The sizing check: `tf_variants.py` must print no `!!` line for the 6%
   stops.
3. Expected `cost_r` per family, now with real funding: `(0.14% + hold_h/8 ×
   the coin's TRAIN mean |funding|) / stop`.
4. **The coin's own ETH/BTC result for each family.** It is context, not a
   reason: a family that failed its BTC holdout (038, 039) and reads PASS on
   SOL/BNB is one more reason for suspicion.

**Run:** `SYMBOL=<coin> python src/evaluate.py ideas/<file>` for all 49
files, then `baseline.py` and `benchmark.py` (same `SYMBOL`) on every WATCH
and PASS. The benchmark compares with holding that coin.

**Before any `--final`:** write the three checks from Round 6 / §11:
- the seven clocks, and whether the PASS is the best one of them;
- the per-year split;
- the long/short counts;
- plus the family's result on BTC and ETH.

**Stop rule, agreed in advance, per coin:** if a coin's round ends with no
holdout CONFIRMED, research on that coin stops. If both stop, the project's
answer stands for all four coins. **Do not add a fifth coin**; that decision
belongs to the owner. A CONFIRMED goes to §6 and to the owner at once.

---

## 13. TradingView strategy ports (owner request, after SOL Exp 005 / BNB Exp 003)

> **Round 1 is DONE (2026-09-30): 48 evaluations, 0 PASS, no holdout used.**
> BTC Exp 033, ETH Exp 007, reviewed in BTC Exp 034. The stop rule (rule 6
> below) has fired: the TradingView question is closed unless the owner brings
> new scripts.

All four coins are closed for the project's own idea families. The owner asked
for a different question: **do published TradingView strategies survive honest
testing?** A TradingView backtest usually has three things wrong with it:
- the default commission is 0;
- `request.security()` or intrabar fills can see the future;
- nothing is held out.

This harness fixes all three. The research agent runs the ports; the planner
writes them.

**Engine feature for ports (BTC Exp 031, owner-approved Level 3):**
`exit_on: "opposite"` in a recipe closes a position at the next open when the
entry trigger fires the other way, before filters and direction. If the other
side is allowed, it re-enters that way on the same open, which is
TradingView's reversal. `strategy.close` on a signal is ported the same way.
It is off by default, and every earlier record is unaffected.

**Rules for every port** (on top of AGENTS.md):
0. **Only from source code the owner supplies.** A port is written from the
   Pine Script the owner pastes, and nothing else. No agent (planner or
   researcher) writes a port from memory, from a description or from another
   website's copy (owner's decision; ports T2–T5 written from memory were
   withdrawn before any run). The pasted source is saved with the idea: quote
   the script name and version in the hypothesis.
1. **Faithful.** The author's parameters are kept exactly. The only grid keys
   are what the engine forces us to invent: usually a `pct` stop and a time
   stop, because the engine has no stop-and-reverse and every trade must risk
   1%. Every deviation from the Pine script is listed in the idea's
   hypothesis.
2. **Chart mode.** Variants use `tf_variants.py` default chart mode: the same
   bar counts on every chart, as a TradingView user applies a script. The 4h
   file is the source, and all seven timeframes are run.
3. **Coins:** BTCUSDT and ETHUSDT (`SYMBOL=...`). Their records and version
   budgets are separate. A port is a new structure, so a PASS may use that
   coin's holdout for that config, under the usual `--final` rule.
4. **Refused:** grid, martingale, and averaging down without a limit
   (AGENTS.md rule 7). A port that needs one is recorded as "not portable",
   with the reason.
5. **Report per port:** what TradingView claims (if the owner supplies it)
   next to what is left after costs, controls and, for a PASS, the holdout.
6. **Budget:** at most 5 ports per round (the owner's scripts), pre-registered together.
   **Round 1 is 6 ports (T1–T6): the owner's decision, 2026-09-29, before any run.** **Stop
   rule:** a round with no holdout CONFIRMED ends the TradingView question
   unless the owner brings new scripts.

### Port T1 — `044_tv_chartart_rsi_bb` (ChartArt, "Bollinger + RSI, Double Strategy" v1.1)
- Pine logic:
  - **long** when `crossover(RSI(6), 50)` and `crossover(close, BB200 lower)` on
    the same bar;
  - **short** when `crossunder(RSI(6), 50)` and `crossunder(close, BB200 upper)`.

  The entry is a stop order at the band, which price has already crossed, so
  it fills at the next open.
- The port uses the existing blocks `rsi_revert(n 6, lo 50, hi 50)` and
  `bb_revert(n 200, k 2.0)`, with `trigger_mode: all` and `confirm_bars: 1`
  (both on the same bar). They match Pine exactly:
  - RSI with Wilder smoothing (RMA);
  - SMA with a population stdev;
  - `crossover` meaning now above and the previous bar not above.
- **Exit, as the original does:** it reverses on the opposite signal
  (`exit_on: "opposite"`, BTC Exp 031).
- **Added** (every trade must risk 1%): a `pct` stop of 4% / 6%, plus a long
  time cap of 480 h / 1920 h at 4h, scaled by chart mode.
- Files: `ideas/044_tv_chartart_rsi_bb.json` (4h) plus `_tf15`, `_tf30`, `_tf60`,
  already generated. **Run each on BTCUSDT and on ETHUSDT: 8 evaluations.**
- The author writes that v1.1 was "made more successful in backtesting". It
  was tuned on the chart it is shown on, which is one more reason to expect
  VALID to disappoint.
- This is mean reversion, which the project closed for its own ideas (BTC Exp
  016, Exp 024). It is run anyway because the owner asked for this script.
  Record it as a port, not as a retry.

### Port T2 — `045_tv_luxalgo_smc` (Smart Money Concepts [LuxAlgo], Pine v5, from the owner's source)
- **Licence: CC BY-NC-SA 4.0**, © LuxAlgo. The port (`smc_structure` in
  `src/recipes.py`) is a derivative under the same licence: attribution is in
  the code, and use is non-commercial only.
- **Ported:** the market-structure engine, line by line:
  - `leg(size)`;
  - `getCurrentStructure` (a pivot is confirmed `size` bars late);
  - `displayStructure`: a close crosses the last pivot not yet crossed; CHoCH
    if against the structure trend, BOS if with it. Internal breaks are
    ignored when the internal level equals the swing level; the confluence
    filter is off, as in the defaults.
- Defaults are kept: swing length 50, internal size 5. The script's
  evaluation order is kept: swing, then internal pivots; internal, then swing
  breaks. Pine's `na != x` (false) is reproduced.
- **Not ported (not signals):** order blocks, fair value gaps (they use
  `request.security(..., lookahead_on)`), equal highs/lows, MTF levels,
  premium/discount zones.
- **It is an indicator.** The entries are **its own alert conditions**: long
  on a bullish BOS/CHoCH, short on a bearish one. Which alert
  (`structure` swing/internal × `event` CHoCH/BOS) is a grid key chosen on
  TRAIN, together with the invented exits (stop 4%/6%, hold 120/480 h at 4h).
  That makes 16 combos.
- Test 7: causal, correct output shape, and an 11-bar hand trace of the Pine
  logic (bearish BOS → bullish CHoCH → bearish CHoCH → bullish CHoCH).
- Files: `ideas/045_tv_luxalgo_smc.json` plus 3 chart-mode variants.
  **Run on BTCUSDT and ETHUSDT: 8 evaluations.**

### Port T3 — `046_tv_chartart_macd_sma` (ChartArt "MACD + SMA 200 Strategy" v1.0, from the owner's source)
- Pine logic, author defaults 12 / 26 / 9 / 200, **all simple moving
  averages** (it is not the usual EMA MACD):
  - `macd = SMA12 − SMA26`, `hist = macd − SMA9(macd)`;
  - **long** when `crossover(hist, 0)` and `macd > 0` and `SMA12 > SMA26`
    and `close[26] > SMA200`;
  - **short** on the mirror image.
- New block `chartart_macd_sma`. Test 7 checks it against a plain loop that
  follows the Pine lines one by one (0 mismatches), plus causality and
  output shape.
- **Deviations:**
  - The script only reverses. The port reverses too (`exit_on: "opposite"`).
    The stop (4%/6%) and a long time cap (480/1920 h at 4h) are ours. The
    script's 50% intraday-loss halt is not modelled: at 1% risk it cannot
    bind.
  - Its stop-order entry at the signal bar's low/high fills at the next open
    unless the next bar gaps through that level.
  - The `strategy.cancel` lines only remove unfilled orders.
- Files: `ideas/046_tv_chartart_macd_sma.json` plus 3 chart-mode variants.
  **Run on BTCUSDT and ETHUSDT: 8 evaluations.**

### Port T4 — `047_tv_super_scalper` ("Super Scalper - 5 Min 15 Min", Pine v5, from the owner's source)
- Pine logic, defaults kept:
  - ATR 14 smoothed with **WMA**, multiplier 1.0, bands = close ± band;
  - **long** when `open < close − band` (a bar that rose more than the band)
    and `RSI(25) > RSI(100)`;
  - **short** on the mirror image.
- The EMA 21/65 "golden cross" in the script is **only plotted**, so it is
  not part of the signal.
- New block `super_scalper`. Test 7 checks the WMA against Pine's definition,
  checks the block against a plain loop of the Pine lines (0 mismatches),
  and checks causality and output shape.
- **Deviations:**
  - The script computes a stop (2 ATR beyond the signal bar's low/high) and a
    take-profit (5 ATR) but **never uses them**; on TradingView it only
    reverses. The port reverses (`exit_on: "opposite"`). It keeps the
    author's 2-ATR stop (`swing` n 1 + 2 ATR) as the mandatory stop and drops
    the never-executed target.
  - A long time cap is the only grid key (48 / 192 h at 15m).
- **Source chart 15m** (the author's timeframe), chart-mode variants on the
  other six. The ATR stop grows with the timeframe: the 1h/4h variants on BTC
  may be `UNSIZABLE` at 2024–25 prices. That is a recorded outcome, not a
  reason to change the file.
- Files: `ideas/047_tv_super_scalper.json` plus 3 variants. **Run on BTCUSDT
  and ETHUSDT: 8 evaluations.** (The author's other chart, 5m, is dropped with
  1m–5m.)

### Port T5 — `048_tv_chartart_rsi_bb_long_v12` (ChartArt "Bollinger + RSI, Double Strategy Long-Only" v1.2, from the owner's source)
- Same entry as T1, **long only**. The exit is the script's own
  `strategy.close`: RSI(6) crosses below 50 on the same bar that the close
  crosses down through the upper band, i.e. T1's short trigger. It is ported
  with `exit_on: "opposite"` and `direction: long`.
- The author says long-only "made it more successful in backtesting". On a
  rising market that is what being long does, and baseline and benchmark are
  there to catch it.
- **Added:** a pct stop of 4%/6% (the script has none) and a long time cap.
- Files: `ideas/048_tv_chartart_rsi_bb_long_v12.json` plus 3 variants.
  **Run on BTCUSDT and ETHUSDT: 8 evaluations.** It differs from T1 in
  direction, so it has its own structure and version budget.

**The round is full: T1–T6 = 48 evaluations (4 timeframes, owner's decision 2026-09-29) (T6 below, added by the owner
before any run). No port is added after it starts.**

**Pre-registration** (BTC journal **Exp 032** and ETH journal Exp 006, before the
first run):
1. TRAIN signal counts of the 4h source on each coin. The same-bar coincidence
   of the two crosses may be rare. Under 150 means expect INCONCLUSIVE; run
   it anyway and do not change the file.
2. List the deviations above.
3. The expected `cost_r` per timeframe (15m 30m 1h 4h; 1m–5m were dropped by
   the owner on 2026-09-29, before any run, and their files deleted).

### Port T6 — `049_tv_liquidity_sweep` ("Liquidity Sweep Reversal Strategy", Pine v6, Mozilla Public License 2.0, from the owner's source)
**In round 1 (owner's decision, 2026-09-29, before any run): round 1 is
T1–T6, 48 evaluations.** T6 is pre-registered with the others in BTC Exp 032
and ETH Exp 006.

- New trigger `liquidity_sweep` (Level 2, `src/recipes.py`). Pivot highs/lows
  (7/7) become levels, deduplicated within 0.25 ATR and dropped after 150
  bars. A sweep is a bar that wicks through a level and closes back inside,
  with volume > 1.3 × SMA20 and wick ≥ 1.5 × body. It is confirmed on the next
  bar past the sweep bar's midpoint. The session is the `hours` filter with
  UTC 12–15 (the script's 1200-1600 in exchange time, which is UTC on
  Binance).
- **The script has its own exits, and they are ported as they are:** stop
  1.2 ATR beyond the sweep wick (swing stop n 2 + 1.2 ATR buffer), TP 1.5 R,
  break-even at 50% of the way to TP (`be_at` 0.75). This is the first port
  with a real stop and target, so it needs no `exit_on`.
- Deviations (full list in the idea file):
  - the stop is measured from the fill, not from the confirmation close. It
    is wider only when the confirmation bar trades below the sweep wick;
  - break-even reacts to a close, not an intrabar touch;
  - a sweep that happens during an open trade is dropped, not kept pending;
  - a time cap is added (the only grid key, 48/192 h at 15m);
  - costs: 0.05% + 0.02% instead of TradingView's 0.04% + 1 tick.
- Source 15m (the script names no timeframe; it is an intraday session
  strategy), chart mode, 4 files. **Run on BTCUSDT and ETHUSDT: 8
  evaluations.**
- In the pre-registration, add for T6: the TRAIN signal count
  per timeframe on each coin, and `cost_r` per timeframe. On 4h only the 12:00
  bar is in the session, so expect few trades there.

## 14. New data: open interest and long/short ratios (owner-approved 2026-09-30)

402 evaluations of price-and-volume ideas and 6 published TradingView scripts
have produced no holdout CONFIRMED (`LESSONS.md`). The one direction never
tested is data the project has not used. The owner approved this round on
2026-09-30.

### What the data is (checked 2026-09-30, BTC Exp 035)
- **Binance `futures/um/daily/metrics`**, one zip per day, one row per 5
  minutes. Columns: open interest in coins and in USDT; top-trader long/short
  ratio by accounts and by position size; all-account long/short ratio; taker
  buy/sell volume ratio.
- **Coverage:** BTCUSDT from **2020-09-01**. ETH, SOL and BNB from
  **2021-12-01**. No day is missing in either range.
- **Quality:** early files repeat every row twice, and a few days miss some
  5-minute rows. Binance left the top-trader ratios empty for 2022-11-08..10
  (the FTX crash).
- **Liquidations: not available.** `liquidationSnapshot` is empty on
  data.binance.vision. Paid sources are out of scope. `oi_flush` is the proxy:
  a large price move while open interest drops sharply.

### How it enters the harness (Level 3, BTC Exp 035)
- `python src/datafeed.py --metrics` downloads the files, caches
  `data/cache/<SYMBOL>/<SYMBOL>_metrics.parquet`, and validates it: every day
  present, OI > 0, under 1% of 5-minute slots missing. It must print
  `METRICS VALIDATION: OK`.
- When that cache exists, `experiment.get_bars(tf)` adds six columns to the
  bars: `oi`, `oi_usd`, `top_acct_ls`, `top_pos_ls`, `acct_ls`, `taker_ls`.
  **They are attached causally:**
  - a row is used only 5 minutes after its `create_time` (Binance does not say
    whether that time is the start or the end of the sample);
  - a bar sees a row only if it is usable by the bar's close;
  - a row older than 30 minutes at the close gives NaN, never a stale value;
  - bars before `metrics_start` are NaN.
- The engine never reads these columns. Without the cache the bars are exactly
  as before.
- New blocks: triggers `oi_flush`, `crowd_fade`, `smart_divergence`, filter
  `oi_rising`. They refuse to run on bars without metrics, and read NaN as no
  signal.
- Test 11 in `test_engine.py` covers:
  - zip reading;
  - a hand-computed alignment (lag, as-of the close, stale → NaN);
  - each block against a plain loop.

### The shorter TRAIN, stated before any run
The split dates do not move (AGENTS.md rule 1). With metrics starting later,
TRAIN has less data:

| coin | TRAIN with metrics | VALID | role |
|---|---|---|---|
| BTCUSDT | 2020-09 → 2022-12, **28 months** | 2023–24, full | **primary** |
| ETHUSDT | 2021-12 → 2022-12, **13 months**, almost all bear market | 2023–24, full | replication only |

- A 13-month, one-regime TRAIN is thin, so an ETH result counts only as
  replication of a BTC result. It is never a finding on its own.
- The rolling z-scores need 90% of 720 bars before they fire, so each coin's
  first ~27 days of metrics give no signal (at 1h; chart mode keeps 720 bars
  on every timeframe).

### The round: M1–M4 (ideas 050–053), pre-registered
Source 1h. Chart-mode variants at 15m, 30m and 4h (AGENTS.md step 4b). Stop
3% at 1h. Holds of 2–6 days at 1h. Cooldown 12 bars.

| # | file | hypothesis in one line | grid |
|---|---|---|---|
| M1 | `050_oi_flush_reversal` | price move + sharp OI drop = forced liquidation; fade it after the flush | OI z 1.5/2.5 × hold |
| M2 | `051_retail_crowd_fade` | all-account L/S ratio at an extreme = crowded retail; fade it | z 1.5/2.5 × hold |
| M3 | `052_smart_money_divergence` | top traders lean against the crowd; follow them | k 1.5/2.5 × hold |
| M4 | `053_oi_confirmed_breakout` | a Donchian break with OI rising = new money; take only those | OI growth 0%/5% × hold |

**16 files × 2 coins = 32 evaluations.** No idea, file or timeframe is added
after the first run.

**Pre-registration** (BTC journal **Exp 036**, ETH journal **Exp 009**,
before the first run):
1. `python src/datafeed.py --metrics` gives `METRICS VALIDATION: OK` on both
   coins. Record its missing-slot share and NaN counts.
2. TRAIN signal counts per idea and timeframe, on each coin. Under 150 means
   expect INCONCLUSIVE. Run it anyway and do not change the file.
3. The expected `cost_r` per timeframe, using ≈ 0.14% of price per round trip
   (BTC Exp 034): 3% stop ≈ 0.05 R at 1h, 1.5% ≈ 0.09 R at 15m, 6% ≈ 0.02 R
   at 4h.
4. What each idea should do in a falling market (already stated in each
   hypothesis). Check it on VALID's long/short split afterwards.

**Controls, as always:** `baseline.py` and `benchmark.py` on every
WATCH/PASS. `--final` only with the owner's approval.

**Stop rule:** if no config reaches a holdout CONFIRMED, the new-data
question is closed for these four signals. Any other use of the metrics
needs a new owner decision.
