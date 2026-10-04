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

## 15. Replication of `051_retail_crowd_fade @30m` on SOLUSDT and BNBUSDT (owner-approved 2026-10-01)

**Why this, and why now.**
- BTC Exp 038 recorded `051_retail_crowd_fade_tf30` as the first configuration
  in the project with SKILL on two coins:
  - BTC: +0.106 R on 198 VALID trades;
  - ETH: +0.080 R on 197;
  - beta ≈ 0 on both, WATCH and NO_EDGE on both.
- It missed PASS only on the CI gate. The question is whether that is skill or
  one lucky cell out of 438 evaluations.
- SOL and BNB have the same Binance metrics from 2021-12-01. Their VALID data
  has never been seen by this configuration. A replication there is new
  evidence available now, without waiting for post-2026-08 data.

**Correction, before any run (BTC Exp 039).** Exp 038 said TRAIN chose the
same parameters "independently" on BTC and ETH. On ETH only **1 of the 4**
grid cells had ≥ the minimum TRAIN trades (`n_eligible` = 1). So ETH's choice
was not a selection. The agreement is weaker than stated: BTC chose z 1.5 /
24 h from 2 eligible cells.

**What is run: the same file, unchanged, on the two new coins.**
- `ideas/051_retail_crowd_fade_tf30.json`, with no edit and no new file. TRAIN
  picks from the same grid (z 1.5/2.5 × hold 24/72 h), exactly as it did on
  BTC and ETH. No other idea, timeframe or variant is run.
- `SYMBOL=SOLUSDT` and `SYMBOL=BNBUSDT`. On both coins, TRAIN with metrics is
  13 months (2021-12 → 2022-12), the same as ETH. SOL keeps its
  `eval_equity` of 20,000.
- **2 evaluations.** `baseline.py` and `benchmark.py` are run on **both,
  whatever the verdict**. The replication question is SKILL, and a REJECT or
  INCONCLUSIVE row still has a skill reading.

**Pass criterion, written before any run.** The replication **succeeds only
if, on SOL and on BNB, both:**
1. VALID mean R > 0, and
2. `baseline.py` says **SKILL**.

One coin out of two is **not** a replication. If TRAIN on a coin has no
eligible cell (INCONCLUSIVE with no SKILL reading), that coin counts as
**failed**, not as missing. Reported next to the criterion, but not part of
it:
- the parameters TRAIN chose, and how many cells were eligible;
- long and short legs;
- beta and alpha;
- per-year results;
- the 4-coin pooled VALID mean R with a trade-level bootstrap CI (computed in
  the review from `eval_trades/`).

**What each outcome means.**
- **Succeeds:** the strongest evidence of entry timing the project has
  produced.
  - Still no holdout: the verdict is not PASS, and AGENTS.md rule 4 stands.
  - The next step is a **forward test**: freeze the config and judge it only
    on Binance data after 2026-08, with a criterion written before reading
    that data. That needs the owner's decision.
- **Fails:** M2's two-coin SKILL is read as chance. The metrics question is
  closed, as PLAN §14's stop rule already says, and no M2 variant is tried.

**Pre-registration** goes in SOL journal **Exp 006** and BNB journal **Exp
004**, before the first run. It must include:
- `METRICS VALIDATION` output for each coin;
- the `acct_ls` NaN share per split;
- the TRAIN signal count per grid cell.

Everything else follows AGENTS.md. `--final` is not run.

## 16. Allocation test: hold in uptrends, step aside in downtrends (owner-approved 2026-10-01)

**The owner's question.** Most profit came from up-markets. But buying near a
top means waiting a year or more to get back to break-even, and some traders
profit in down-markets too.

The project has answered "does an entry beat holding?" 440 times: no.
It has never fairly answered **"does a slow trend rule keep most of holding's
upside with much less of its downside?"** The regime ideas 023–026 tried, but
three things made that test unfair:
- they were judged on VALID 2023–24, a bull market with no bear to avoid;
- they were sized at 1% risk per trade, not as a holding;
- futures data starts in 2020, so it misses the 2018 bear.

### The test (`src/allocation.py`, Level 3, BTC Exp 040)
- **Daily bars.** Exposure is 1× equity or nothing (−1× for the short rule
  on perps). The position is decided at day t's close and traded at day t+1's
  open. Units are held between changes, so a short is a real short.
- **Two markets:**
  - **spot:** Binance spot daily klines from the first published month
    (BTC/ETH 2017-08, BNB 2017-11, SOL 2020-08). Cost is 0.10% VIP0 taker +
    0.02% slippage per side. No funding, no short. This is the main market,
    because it is the only one that covers the 2018 bear.
  - **perp:** Binance USDT-M daily klines from 2020-01. Cost is 0.05% +
    0.02% per side, plus funding on the notional (long pays a positive rate).
- **Every run starts on day 200** of its data, with buy-and-hold starting the
  same day. Results are reported for the full run and per segment: 2018 bear,
  2019, 2020–21 bull, 2022 bear, 2023–24, 2025–26, and the halves before and
  after 2022.

### The four rules, pre-registered, textbook parameters, nothing fitted
| rule | position |
|---|---|
| `sma200` | long while the close is above its 200-day average, else flat |
| `golden_cross` | long while the 50-day average is above the 200-day, else flat |
| `breakout_20w` | long on a close above the prior 140-day high, flat on a close below the prior 70-day low |
| `sma200_long_short` | long above the 200-day average, short below (perp only) |

**Nothing is fitted, so no period is a training period, and every period
including 2025–26 is reported in one run.** The holdout lock of the
evaluate.py workflow guards selected configurations. These rules were not
selected on any data, and they cannot be changed or added to after the run.
The script refuses to overwrite its results (`--rerun` only after a code fix,
recorded in the journal).

### Verdict, written before any run (in the code: `allocation.verdict`)
**IMPROVES** only if:
- on the full run, **and on each half separately** (before and after
  2022-01-01),
- the rule's Sharpe ≥ buy-and-hold's,
- **and** its max drawdown ≤ 0.6 × buy-and-hold's.

Anything else is **NO_IMPROVEMENT**. Reported next to the verdict, but not
part of it: CAGR, longest time under water, exposure, number of switches,
and every segment.

**What to expect, stated now.** In bull runs the rules should earn **less**
than holding, because they enter late and get whipsawed. Their value, if
any, is in the bears (2018, 2022). A rule that only works in one half fails
by design.

### Run (the research agent, not the planner)
- Coins: **BTCUSDT and ETHUSDT primary**; SOLUSDT and BNBUSDT secondary (SOL
  spot starts 2020-08, so it has no 2018).
- Command, per coin: `SYMBOL=<coin> python src/allocation.py`. The first run
  downloads the daily files and needs the existing funding cache (`python
  src/datafeed.py`).
- Output: `results/<SYMBOL>/allocation/summary.json` and the generated
  `journal/<SYMBOL>/allocation.md`.
- Record it in each coin's `experiments.md`: the full table, the verdict per
  rule and market, and the 2018 and 2022 segments.
- **Do not run anything else and do not change a rule.** If a rule IMPROVES,
  report it to the owner. That is not a trading recommendation yet; how to act
  on it is the owner's decision.

## 17. Rotation: cross-sectional momentum across Binance coins (owner-approved 2026-10-01)

**Why a different question.** The owner's goal is profitable trading. 440
evaluations asked *when* to trade one coin, and none survived. The allocation
test (§16) asked *whether to be in the market*: trend rules cut the bears but
failed the drawdown criterion. Two of the project's own findings point at a
different question:
- cost decides everything at short holds;
- samples were too small for the CIs to clear zero.

**Which coins to hold each week** answers both:
- weekly rebalancing keeps cost low;
- dozens of coins over hundreds of weeks give a large sample;
- a long/short book on perps is market-neutral, so a bull market cannot pass
  for skill.

The academic crypto-factor literature reports a 1–4 week cross-sectional
momentum effect. It may have weakened since; that is what VALID and HOLDOUT
are for.

### Data (checked 2026-10-01)
- data.binance.vision keeps **delisted** pairs: LUNA, FTT, UST, SRM, WAVES,
  BCC (2018) and others. That gives 735 spot USDT pairs and 864 perp USDT
  pairs.
- `python src/rotation.py --build spot` / `--build perp` downloads every
  tradable USDT pair's daily klines (and, for perps, their funding) into
  `data/cache/_multi/`.
- That is roughly 40,000+ small monthly zips per market, checksum-verified.
  Expect an hour or more.
- **Symbol reuse:** `LUNAUSDT` is old LUNA until 2022-05-13 and a new coin
  from 2022-05-31. Any gap of more than 3 days splits a symbol into separate
  instruments.
- Excluded: stablecoins and fiat, wrapped duplicates (WBTC, WBETH, BETH),
  PAXG, and leveraged tokens (xxxUP/DOWN/BULL/BEAR, but not coins such as JUP).

### The test (`src/rotation.py`, Level 3, BTC Exp 042)
- **Every Monday:**
  - The universe is the 30 most liquid coins: average quote volume over the
    previous 30 days, at least 60 days of history, using data up to Sunday
    only. A week with fewer than 15 eligible coins is skipped.
  - Coins are ranked by their past `L`-day return.
  - Fills are at Monday's open. A coin whose data ends mid-week (delisted)
    exits at its last close.
- **Spot (primary):**
  - long the top fifth (6 coins), equal weight;
  - **statistic = weekly net return of the top fifth minus the equal-weight
    universe** (the momentum premium, net of the market);
  - cost 0.10% fee + 0.05% slippage per side on turnover against drifted
    weights.
- **Perp:**
  - long the top fifth, short the bottom fifth, half the equity each;
  - **statistic = the book's weekly net return**;
  - cost 0.05% + 0.05% per side, plus each coin's own funding.
- **Splits** (as in the rest of the project):
  - TRAIN 2018–2022 (perp data starts 2019-09);
  - VALID 2023–2024;
  - HOLDOUT 2025-01 → 2026-08.
  - A week counts in a split only if it ends inside it.

### Pre-registered choices and gates
- **The only choice is `L` ∈ {7, 14, 28} days**, picked by the highest TRAIN
  Sharpe of the statistic. Everything else is fixed in the code: N 30, top
  fifth, age 60, volume window 30, costs. Changing any of it is a new test
  that needs the owner.
- **PASS on VALID** needs all of these:
  - TRAIN mean > 0;
  - ≥ 100 VALID weeks;
  - VALID mean > 0;
  - 95% block-bootstrap CI lower bound > 0 (4-week blocks);
  - mean > 0 at cost ×1.5;
  - drawdown of the statistic's cumulative curve ≤ 30%.
- **HOLDOUT** runs with `--final`, once per market, and only after PASS.
  **CONFIRMED** means the holdout mean > 0 with its CI lower bound > 0.
  The script keeps a lock file and refuses a second run.
- The script also refuses to redo a TRAIN/VALID run whose results exist.

### What it is not
- Not a guarantee. The literature's effect may be gone.
- Spot long-only results are still exposed to the crypto market. The
  statistic removes that by subtracting the universe. The perp book removes
  it by construction.

### Run (the research agent)
1. `python src/test_engine.py` → ALL CHECKS PASSED (test 13 covers this tool).
2. Pre-register in `journal/_multi/experiments.md` (new file, Exp 000)
   **before** step 4. Include the number of symbols and instruments built,
   the universe size per year, and how many delisted coins were ever in the
   universe.
3. `python src/rotation.py --build spot`, then `--build perp`.
4. `python src/rotation.py spot`, then `python src/rotation.py perp`.
5. **Stop and report to the owner.** `--final` only with the owner's
   approval, and only on a PASS.

## 18. Exit lab: is there skill in how a trade is closed? (owner-approved 2026-10-01)

**The owner's direction:** train entry and exit timing. Stage 1 is exits,
because they have never been measured on their own. Every exit tested so far
rode on an entry, so an exit's effect could not be separated from the entry's.

**The method (`src/exit_lab.py`, BTC Exp 043).**
- **Random entries:** each 1h bar is entered with probability 0.25, side
  50/50, fixed seed 18. That is roughly 13,000 entries over 2020–2026.
  - A random entry carries no information. On a pure random walk every exit's
    gross R is about zero and its net is minus the cost; the smoke test on
    synthetic random-walk data confirms it.
  - **So a positive net R can only come from structure in the price path that
    the exit harvests.** Persistent moves favour a trailing stop; reverting
    moves favour a near target.
  - Longs and shorts are equally likely, so market drift cancels.
- **Each entry is simulated on its own** (positions overlap), with the
  engine's exact rules:
  - next-open fill plus slippage;
  - stop first inside a bar;
  - break-even and trailing moved on the previous close;
  - time exit at the close;
  - taker fee and slippage on both sides;
  - funding on the notional.
  - Test 14 checks it trade for trade against `run_backtest`: 150 trades over
    all six exits, max |ΔR| 3e-14.
- **The six exits, fixed** (ATR 14 on 1h; stop and trail in ATR; target and
  break-even in R):

  | exit | stop | target | other | max hold |
  |---|---|---|---|---|
  | `time_only` | 3 ATR | – | – | 24 bars |
  | `tp_1r` | 2 ATR | 1 R | – | 72 |
  | `tp_2r` | 2 ATR | 2 R | – | 72 |
  | `tp_4r` | 2 ATR | 4 R | – | 72 |
  | `be_then_3r` | 2 ATR | 3 R | break-even at 1 R | 72 |
  | `trail_2atr` | 2 ATR | – | trail 2 ATR from 1 R | 120 |

- **Splits:** TRAIN 2020–22, VALID 2023–24, HOLDOUT 2025-01 → 2026-08. Each
  trade belongs to the split of its entry time.

**Pre-registered choice and gates.** TRAIN chooses the exit with the highest
mean net R. **PASS** on VALID needs all of:
- TRAIN mean > 0;
- VALID mean > 0;
- the 95% CI lower bound > 0 (resampling whole weeks, because the entries
  overlap);
- mean > 0 with fees and slippage ×1.5;
- at least 1,000 VALID trades.

`--final` runs the holdout once (lock file), and only after PASS.
**CONFIRMED** = holdout mean > 0 with CI lower bound > 0.

**Runs:**
- BTCUSDT 1h is primary.
- ETHUSDT 1h is replication: a PASS counts only if ETH also passes with the
  same exit.
- BTCUSDT `--tf 240` is descriptive only.
- `SYMBOL=<coin> python src/exit_lab.py [--tf 240]`. Each run happens once.

**What happens next.** If an exit passes on both coins, Stage 2 (an ML entry
model) uses it as its exit. If none passes, Stage 2 still runs, with the exit
TRAIN chose, and the result is read knowing that exits alone carry no edge.
**Prior:** most likely every net mean is near minus the cost (−0.03 to
−0.1 R). Any exit whose gross R is clearly positive on both TRAIN and VALID
is worth reporting even if the net fails.

## 19. ML entry model: can a trained model time entries better than chance? (owner-approved 2026-10-01)

**Stage 2 of the owner's "train the timing" request.** Stage 1 (§18, BTC
Exp 043–045) found no tradable skill in six exits. At 1h, the price path's
structure was smaller than one round-trip cost.

**The model (`src/ml_entry.py`, BTC Exp 046).**
- **Two LightGBM regressors**, one for longs and one for shorts. Each
  predicts the **net R** (after fees, slippage and funding) of entering at the
  next 1h open with **one fixed, symmetric exit**: `time_only` (3-ATR stop,
  out after 24 bars).
  - The exit is symmetric on purpose. BTC Exp 045 showed that a
    path-dependent exit turns market drift into profit.
- **Features** (bar i uses bars ≤ i):
  - returns over 1–168 bars;
  - volatility over 24 and 168 bars and their ratio;
  - ATR as % of price;
  - position in the 24- and 168-bar range;
  - candle body and wicks;
  - volume z-score;
  - taker buy ratio;
  - distance to EMA 20/50/200 in ATR;
  - hour and weekday;
  - the last settled funding rate.
  - The metrics columns are **not** used: they are NaN for much of TRAIN.
- **Hyper-parameters are fixed:** 300 rounds, learning rate 0.03, 15 leaves,
  ≥ 200 rows per leaf, bagging and feature fraction 0.8, L2 1.0, seed 7,
  deterministic. They are not tuned anywhere.

**Protocol.**
1. TRAIN 2020–22 only. Rows whose 24-bar label window would reach past a fit
   window are **purged** (26 bars).
2. **The threshold** (predicted net R needed to trade, from {0, 0.05, 0.10,
   0.20}) is chosen on **TRAIN out-of-fold predictions** from 3 expanding,
   purged walk-forward folds: fit 2020-01 → 2021-07 / 2022-01 / 2022-07 and
   predict the next half-year. The choice needs ≥ 300 OOF trades.
3. The final models are refit on all of TRAIN and frozen.
4. On VALID 2023–24, each bar takes the side with the higher prediction if it
   clears the threshold. Each signal is one trade, simulated on its own with
   the engine's rules.

**Gates (PASS on VALID needs all):**
- TRAIN OOF mean > 0;
- ≥ 300 VALID trades;
- VALID mean > 0;
- weekly-block CI lower bound > 0;
- mean > 0 with fees and slippage ×1.5;
- **beats the 95th percentile of 200 random signal sets with the same long
  and short counts.** Drift helps them exactly as much as the model, so this
  is the BTC Exp 045 rule.

`--final` runs the HOLDOUT once (lock file), and only after PASS.
**CONFIRMED** = holdout mean > 0, CI lower bound > 0, and above the random
median.

**The pipeline is proven on synthetic data** (test 15):
- On bars with a planted, drift-neutral momentum edge it says **PASS**: mean
  +0.37 R, both legs positive, random 95th percentile +0.12.
- On pure noise it says **REJECT**, and does not beat random.
- Its features are causal, the purge holds, and its labels equal the exit
  lab's.

**Runs:**
- `SYMBOL=BTCUSDT python src/ml_entry.py` (primary);
- `SYMBOL=ETHUSDT python src/ml_entry.py` (replication: a PASS counts only if
  ETH also passes).
- One run each. No new feature, parameter or exit after seeing a result.

**Prior:** low. Stage 1 says the structure at 1h is smaller than the cost.
The model can only win where it finds bars whose expected move clears about
0.1 R of cost.

**Change before the first run (2026-10-01, test 16).** The random control
used to pick scattered random bars. Model signals come in runs: neighbouring
bars give the same side, and their 24-bar trades overlap. A set of scattered
bars therefore has much less spread than the model's set. The model could
then beat the 95th percentile on pure noise. The control is now **200 random
circular time-shifts of the model's own signal sequence** inside the window,
each at least 168 bars away from the real timing. A shift keeps the long and
short counts and the clustering. It breaks only the alignment with the
market. `--final` uses the same control.

## 20. Pooled ML entry model: one model on many coins (owner-approved 2026-10-01)

**Stage 3 of "train the timing".** One coin gives the model about 26,000
TRAIN rows. The owner asked for more data. Stock charts were rejected: they
trade different hours and have different participants. Instead,
`src/ml_pool.py` (`journal/_multi/` Exp 004) fits **one long model and one
short model on the rows of 20 coins together**.

- The coin is **not** a feature. A pattern must hold across coins to be
  learned, and the features are already scale-free.
- Model, features, labels, exit, folds, thresholds and hyper-parameters are
  **exactly** those of §19.
- This was written before any §19 result was seen. It runs whatever §19
  says.

**Universe (TRAIN data only).** Taken from rotation's daily perp table:
- perp instruments listed by 2021-01-01 and still trading on 2022-12-31;
- ranked by mean daily quote volume over 2021-07 → 2022-12;
- the top 20 are taken.

Rules for edge cases:
- A coin delisted later **stays in**. Its data ends where it ends, so the
  universe is survivorship-free from the selection date.
- A symbol relisted after a gap of more than 3 days counts as a different
  instrument (LUNA).
- The list is fixed in `results/_multi/ml_pool/universe.json` at build time.

**Costs.**
- BTC and ETH: the normal slippage, 0.02%.
- Every other coin: **0.05%**, the same as rotation, because alt books are
  thinner.
- Stress test: fee and slippage ×1.5.

**Gates (PASS needs all):**
- pooled TRAIN OOF mean > 0;
- ≥ 3,000 VALID trades;
- pooled VALID mean > 0, and weekly-block CI lower bound > 0;
- mean > 0 at cost ×1.5;
- pooled mean above the 95th percentile of the time-shift control (per coin,
  trade-weighted);
- **breadth:**
  - at least 10 coins have ≥ 100 VALID trades;
  - at least half of those beat **their own** shift-control 95th percentile
    with a positive mean.

  An edge carried by one or two coins is not a pooled edge. Test 16 checks
  this: a single planted coin out of three is REJECT.

**`--final`** runs the holdout once (lock file), and only after PASS.
**CONFIRMED** needs all of:
- pooled mean > 0;
- CI lower bound > 0;
- above the pooled shift-control median;
- at least half of the coins above their own shift-control median.

**Runs, in order.** Stop at the first crash or a number that looks wrong.
1. `SYMBOL=BTCUSDT python src/ml_entry.py`
2. `SYMBOL=ETHUSDT python src/ml_entry.py`
3. If `data/cache/_multi/perp_1d.parquet` is missing:
   `python src/rotation.py --build perp`.
4. `python src/ml_pool.py --build`
5. `python src/ml_pool.py`

Each runs once. No `--final` without a PASS. No new feature, parameter, coin
or exit after a result.

**Prior:** low. More rows make the model's estimates less noisy. They cannot
make a pattern bigger than it is, and every round so far found the 1h pattern
smaller than one round-trip cost.

## 21. Pooled ML model, round 2: smarter training on the same data (owner-approved 2026-10-02)

**Why.** Round 1 (§20, `_multi` Exp 005) failed only on its CI: +0.060 R,
CI [−0.037, +0.170]. The owner asked whether the same data could train a
smarter model. It can, on one condition: **every choice is made on TRAIN
(2020–22) out-of-fold, and VALID is looked at once.** VALID has already been
seen three times by this line of work, so round 2's gates are stricter than
round 1's.

**What changes (`src/ml_pool2.py`, `_multi` Exp 007).** Each change was
chosen from lessons that hold on TRAIN, or from a design flaw. None was
chosen from a VALID number.

1. **Longer hold, so cost is a smaller share of each trade** (`LESSONS.md` §1).
   - A decision every 4 hours.
   - Symmetric exit: an 8 × 1h-ATR stop, closed after 96 bars (4 days).
2. **Cross-coin features**, all taken at the same bar close:
   - the equal-weight market return over 24/72/168 h;
   - the coin's return relative to the market;
   - market breadth: the share of coins up over 24 h;
   - BTC's return over 24/72/168 h, and BTC's 168 h volatility.
3. **Hyper-parameters tuned on TRAIN only.**
   - 8 LightGBM settings: leaves {7, 31} × minimum leaf {300, 3000} ×
     rounds {150, 500}, each × 4 thresholds.
   - The cell is chosen by the best out-of-fold net mean over 3 purged,
     expanding folds, with ≥ 2,000 OOF trades.
4. **A fairer control** (the flaw found in `_multi` Exp 006).
   - The model's **gross** R (price move only, before every cost) is compared
     with the gross R of 200 circular time-shifts of its own decision
     sequence.
   - Picking high-volatility bars lowers cost per R. It cannot raise gross R
     by itself, so this comparison no longer rewards it.

**Unchanged:**
- the same 20 coins (`results/_multi/ml_pool/universe.json`) and the same
  cache, so no download is needed;
- the 0.05% alt slippage, and 0.02% for BTC/ETH;
- the coin is not a feature;
- folds and split dates.

**Gates on VALID** (PASS needs all):
- TRAIN OOF mean > 0;
- ≥ 2,000 trades;
- net mean > 0, and weekly-block CI lower bound > 0;
- net mean > 0 at cost ×1.5;
- pooled gross above the 95th percentile of the shifted copies' gross;
- ≥ 10 coins with ≥ 50 trades;
- at least half of those coins with a positive net mean **and** a gross mean
  above their own shifted 95th percentile;
- **both legs net > 0**, so a long-only bull-market result cannot pass.

**`--final`** runs the holdout once, and only after PASS. CONFIRMED needs all of:
- net mean > 0, and CI lower bound > 0;
- gross above the shifted median;
- at least half of the coins above their own shifted median.

**Test 17** (synthetic data):
- cross features are causal;
- labels are the simulated 4-day trades, net and gross, on decision bars only;
- a planted edge on 3 coins gives **PASS**;
- noise gives **REJECT**, and noise does not beat the gross control;
- no VALID trade reaches the holdout.

**Run:** `python src/ml_pool2.py`, once.
- It needs `results/_multi/ml_pool/universe.json` and
  `data/cache/_multi/pool_1h/`. If the cache is missing, run
  `python src/ml_pool.py --build`; the universe file is reused.
- After a result, do not change any setting, coin, feature or gate.

**Prior:** low to medium-low.
- The longer hold attacks the main cost problem directly.
- A wide CI on 104 VALID weeks is likely to stay wide.
- The both-legs gate is strict in a bull-market VALID.

## 22. Candle pattern at a support/resistance level (owner request, 2026-10-02)

**Why.** The owner asked for "candle pattern + location + support and
resistance". Candle patterns had never been tested as a rule. ML round 1 saw
candle anatomy as features, and `liquidity_sweep` (T6) is the nearest past
idea: a wick through a pivot on a volume spike. A pattern on its own has
little published evidence, so the location is part of the hypothesis.

**The block (`recipes.candle_at_level`, Level 2):**
- **Patterns**, using bars i and i−1 only:
  - bullish/bearish **engulfing**;
  - **pin**: a hammer or shooting star, with the long wick ≥ 2 × body, the
    other wick ≤ half of it, and the close in the favourable half of the range.
- **Levels** (`level`):
  - `prev_day`: the previous completed UTC day's low is support, its high is
    resistance;
  - `swing`: live pivot lows/highs (10 bars each side, known 10 bars later),
    each alive until a close beyond it or 500 bars;
  - `both`: either kind.
- **Long** = a bullish pattern whose low comes within `near_atr` × ATR of
  support and whose close stays above it. **Short** = the mirror at
  resistance.

**Tests:**
- Test 18 is hand-built:
  - an engulfing at yesterday's low gives a long on that bar only;
  - a shooting star at yesterday's high gives a short;
  - the same candles far from a level give nothing;
  - no level exists on the first day;
  - a swing low works as support, and a level that has been closed through
    is dead.
- Test 7 checks causality and the output shape.

**Ideas** (written at 1h, chart-mode variants at 15m, 30m and 4h):
- `054_candle_at_prev_day_level`, with `level` = `prev_day`;
- `055_candle_at_swing_level`, with `level` = `swing`.

Both use the same exits:
- a swing stop beyond the candle: n 2, 0.5 ATR buffer, **at least 2.5 ATR**,
  so that cost stays near 0.1 R at 1h (`LESSONS.md` §1);
- no break-even or trailing stop;
- out after 48 h at 1h.

The grid is chosen on TRAIN only, 8 cells: `pattern` {engulfing, pin} ×
`near_atr` {0.25, 0.5} × `tp.r` {1.5, 3}.

**Runs:**
- BTCUSDT: all 8 files, each one `evaluate.py` run.
- Then ETHUSDT: the same 8 files, as a replication.
- Every WATCH/PASS gets `baseline.py` and `benchmark.py`.
- `--final` only per AGENTS.md step 7 (PASS + SKILL or ALPHA).
- Report the long and short legs separately (`LESSONS.md` §2).
- No v2 unless the verdict is WATCH, and only with a diagnosis.

**Prior:** low. 15m will pay ~0.3 R in cost and is expected to lose. A
positive result must beat random entries within the same exits
(`baseline.py`) to count.

## 23. Stop diagnosis: wrong direction, or shaken out? (owner request, 2026-10-02)

**The owner's question.** Do the strategies enter the wrong way, or the right
way and then get stopped out by a fake move ("โดนลากไส้")?

**How it is answered.** `src/stop_diag.py` is read-only research.
- It reruns no strategy and tunes nothing.
- It never reads HOLDOUT.
- It writes only `results/<SYMBOL>/stop_diag/` and the generated
  `journal/<SYMBOL>/stop_diag.md`. This new output folder was requested by
  the owner (AGENTS.md rule 11).

**Which trades.** Every evaluation with all of the following:
- a VALID trade file;
- timeframe 15m, 30m, 1h or 4h;
- verdict PASS, WATCH or REJECT;
- 0 size skips;
- at least 30 VALID trades.

**What is measured for each trade.** H is the idea's maximum hold in bars. R
is the trade's exact initial stop distance.
- **right_at_h**: was the close H bars after the fill on the trade's side?
  This is the direction call with the stop ignored.
- **move_h**: that move, in R.
- **shaken**: the trade was stopped, and right_at_h is true.

**Control.** Each real trade gets 20 random fills inside VALID, with the same
side, the same stop as a fraction of price, and the same H. Drift helps the
control exactly as much as the real trade.

**Pooled reading.** Results are trade-weighted across evaluations. The 95% CI
comes from resampling whole evaluations.
- **direction skill** = right_at_h, real minus random.
- **shakeout excess** = P(right_at_h | stopped), real minus random.
- **no-stop move** = move_h, real minus random.

**Verdicts:**
- **WRONG_DIRECTION**: the direction-skill CI is below 0.
- **SHAKEN_OUT**: the direction-skill CI is above 0 **and** the
  shakeout-excess CI is above 0.
- **RIGHT_NOT_SHAKEN**: the direction-skill CI is above 0 and nothing more.
- **COIN_FLIP**: anything else.

**Test 19** uses synthetic data:
- planted momentum with tight stops gives SHAKEN_OUT (skill +10 points);
- the same entries reversed give WRONG_DIRECTION;
- noise gives COIN_FLIP.

**Runs:**
- `SYMBOL=BTCUSDT python src/stop_diag.py`
- `SYMBOL=ETHUSDT python src/stop_diag.py`

Run each once. A rerun gives the same numbers (the seed is fixed), so reruns
are harmless.

**Prior: COIN_FLIP.** 102 of 108 WATCH/PASS results were DRIFT against random
entries (`LESSONS.md` §2), and widening the stop to 8 ATR in ML round 2 left
gross at ~0. This is a diagnosis, not a strategy. A SHAKEN_OUT result would
point to a new pre-registered idea about stop placement. It would not be a
reason to rerun old ideas on VALID.

## 24. Limit orders resting at support/resistance (owner request, 2026-10-02)

**Why.** The owner asked whether we had tried placing the order *in advance*
at support or resistance and letting price come to it.
- Every earlier level idea waited for confirmation:
  - §22 candle at a level: 0 of 16;
  - the T6 liquidity sweep;
  - the engine's `post_only` mode, which rests one bar near the close and
    never at a level.
- None of them rested a limit at the level itself.
- A resting limit enters at the best price, pays the maker fee and no
  slippage, and lets the stop sit just beyond the level. It attacks entry and
  cost together.
- The price: every move that slices through the level fills too (adverse
  selection), and moves that turn just before the level never fill.

**Tool.** `src/level_limit.py`, a standalone simulator like `exit_lab.py`. The
engine is not changed.

**Levels**, known at bar i's close:
- `prev_day`: the previous completed UTC day's low (support) and high
  (resistance).
- `swing`: live pivots, 10 bars each side, until price closes through them or
  500 bars pass.

**Orders:**
- At each close, the nearest level on each side within 3 ATR gets one order,
  and each level gets only one order ever.
- The order rests for 24 bars.
- Fill: at the limit, or at the open on a gap.

**Exits:**
- Stop: limit ∓ stop_atr × ATR.
- On the fill bar, a touch of the stop means the trade is stopped.
  - A gap fill beyond the stop exits at the fill.
  - The target is not allowed on the fill bar.
- Target: tp_r × R, as a resting maker order.
- Stop and time exits pay taker fee + slippage.
- Funding is charged as everywhere.
- Out after 48 bars.
- Trades are simulated independently.
- A trade counts in a split only if it is both filled and closed inside it.

**Grid.** TRAIN chooses 1 of 8 cells: level {prev_day, swing} × stop_atr
{1, 2} × tp_r {2, 3}.

**Gates.** PASS needs all of these:
- TRAIN mean > 0.
- At least 100 VALID fills.
- VALID mean > 0, with CI lower bound > 0.
- Mean > 0 with fees and slippage ×1.5.
- **Above the 95th percentile of 200 control sets on TRAIN and on VALID.**
  A control set places the same number of orders, with the same side mix, at
  the same distances from the close (in ATR), at random bars, with the same
  exits. So "the level" must beat "any price at that distance".

**Holdout.** `--final` runs the holdout once, and only after PASS. CONFIRMED
needs all of:
- mean > 0;
- CI lower bound > 0;
- above the control median.

**Test 20.**
- Hand-computed cases:
  - fill at the level, with a maker target;
  - gap fill at the open;
  - filled and stopped on the same bar;
  - gap below the stop;
  - expiry with no fill.
- Causal orders for both level kinds.
- A planted "levels hold" market gives PASS, and noise gives REJECT.

**Runs.** One run each, in this order:
1. `SYMBOL=BTCUSDT python src/level_limit.py --tf 60`
2. `--tf 240`
3. `SYMBOL=ETHUSDT`, both timeframes.

A PASS on one coin is not a candidate unless the other coin at the same
timeframe also passes (`LESSONS.md` §5, §8). No change after a result.

**Prior:** low. §22 used the same levels and they did not hold more often than
random. The new parts are the entry price, the maker fee and the tight stop.

## 25. Coinbase premium: the first data from outside Binance (owner-approved 2026-10-02)

**Why.** Every entry tested so far was built from Binance's own data, and all
of them called direction about as well as a coin flip (§23). The owner asked
for a way to find better entries. Price patterns are used up, so this test
asks a different question: **who is buying.**

The Coinbase premium is the gap between Coinbase's USD price and Binance's
USDT price. Coinbase is where US institutions and ETF-related flow trade spot.
When they pay up, the premium rises, and their large orders are worked over
hours to days.

**Data** (`python src/datafeed.py --premium`, per coin):
- Coinbase `{BASE}-USD` hourly candles, from the public API (300 hours per
  request).
- Binance spot `{SYMBOL}` hourly klines (data.binance.vision).
- Premium = cb_close / bn_close − 1. This is the standard "Coinbase Premium
  Index" definition.
  - It has no USDT/USD correction, because Coinbase's USDT-USD pair only
    starts on 2021-05-04.
  - Signals use a z-score against the premium's own recent bars, which
    removes slow USDT drift.
- The cache is `data/cache/<SYMBOL>/<SYMBOL>_premium.parquet`.
- `validate_premium` requires ≥ 97% hourly coverage per year and a median
  |premium| < 0.5%.
- Tool check: March 2023 gave 740 of 744 hours, a median premium of +0.10%,
  and a range of ±1.5% (the USDC depeg).

**Causality.** The hourly candle that opens at H is used only from
H + 1h + 2 min. A bar sees only candles that are available at its own close.
A value more than 3 h old becomes NaN. `get_bars` attaches two columns:
`cb_prem` (the coin's own premium) and `cb_prem_btc` (BTC's premium).

**Blocks:**
- `premium_cross(col, n, z)` triggers when the premium's z-score against its
  last n bars crosses above +z (long) or below −z (short).
- `premium_side(col, n, z)` is the matching filter.

**Test 21:**
- the Coinbase rows are parsed correctly;
- a 1h bar sees the *previous* hour;
- 15m bars before 01:02 see nothing;
- stale values become NaN;
- a jump in the premium gives exactly one long;
- the blocks refuse to run without the column.

Test 7 checks causality and shape.

**Ideas.** Both are written at 1h, with chart-mode variants at 15m, 30m and 4h.
- `057_coinbase_premium_follow`: the coin's own premium. Run on **BTCUSDT
  and ETHUSDT**.
- `058_btc_premium_follow_eth`: BTC's premium used as the signal for
  **ETHUSDT only**. On BTC it would be identical to 057.

Both use the same exits: ATR 3 stop, out after 48 h, 4-bar cooldown. The
TRAIN grid has 8 cells: z {1.5, 2.5} × n {72, 336} × target {2R, 4R}.

**Runs:**
1. `python src/datafeed.py --premium`
2. `SYMBOL=ETHUSDT python src/datafeed.py --premium`
3. 057 on BTC (4 files).
4. 057 on ETH (4 files).
5. 058 on ETH (4 files).

Every WATCH/PASS also runs `baseline.py` and `benchmark.py`. Use `--final`
only as AGENTS.md step 7 allows. A candidate needs the same direction on both
coins (`LESSONS.md` §5).

**Prior:** low to medium-low. It is the only new information source the
project has tested. Published accounts of the Coinbase premium describe it
over days, not hours, so the 4h variants matter most.

## 26. Confirming the Coinbase premium on coins it has never seen (owner-approved 2026-10-02)

**Why.** §25 produced the best lead in the project: 30m was SKILL on BTC and
ETH, and 4h gross was far above cost. But BTC and ETH premiums move together,
and `051` already showed this "two-coin SKILL" shape failing on new coins
(`LESSONS.md` §8). The only honest next step is to run **the same frozen idea
on coins whose data it has never seen.** Tuning it further on BTC/ETH is not
honest.

**Coins (Level 3, owner-approved).** They were chosen by a fixed rule before
any run:
- Coinbase `{BASE}-USD` history starts by 2021-07, with no gap longer than
  30 days;
- a Binance USDT-M perp was listed by 2020-09.

| | coins |
|---|---|
| Full TRAIN history | LTC, LINK, BCH, ETC, ALGO, ATOM |
| Coinbase only from mid-2021 | SOL (already configured), DOGE, ADA, DOT |
| Excluded by the rule | XRP: Coinbase had no trading 2021-01 → 2023-06<br>AVAX: Coinbase from 2021-10<br>BNB: not on Coinbase |

- The new specs are in `src/config.py`.
- `data_start` is the first full month of the perp.
- `datafeed.py --tfs 15,30,60,240` skips the 1–5 minute files.
- `validate_premium` measures coverage from the coin's first Coinbase hour.

**Runs (research agent), per coin:**
1. `SYMBOL=<C> python src/datafeed.py --tfs 15,30,60,240`
2. `SYMBOL=<C> python src/datafeed.py --premium`
3. `evaluate.py` on the four `057_coinbase_premium_follow*` files, unchanged.
4. `baseline.py` on the **30m and 4h** rows (all of them, not only WATCH/PASS).

Then run `python src/premium_confirm.py` once. It reads only the recorded
results.

**Bars, fixed now (`premium_confirm.py`, test 22):**
- **30m:** VALID mean > 0 on ≥ 7 of 10 coins **and** baseline SKILL on ≥ 5 of
  10. An UNSIZABLE, INCONCLUSIVE or missing row counts as a failure.
- **4h:** pool the VALID trades of every sizable coin. Pass needs all of:
  - ≥ 100 trades;
  - pooled mean > 0;
  - weekly-block 95% CI lower bound > 0. Weeks are resampled across all coins
    together, so correlated coins do not count twice;
  - ≥ 7 coins with a positive mean.
- **LEAD_CONFIRMED** on a clock means that clock's bar is met.

**After the verdict:**
- **LEAD_CONFIRMED:** write a new pre-registered plan for a single **pooled
  holdout** test on that clock (2025-01 → 2026-08, across the 10 coins plus
  BTC/ETH). Nothing is changed in between.
- **NOT_CONFIRMED:** the premium lead is closed like `051`.
- Either way, no 057 variant is tried on these coins.

**Prior:** low to medium-low. This is the first idea with a positive TRAIN
mean in every cell, but altcoin premiums are noisier than BTC's.

---

## 27. ML decides entry AND exit, with no time limit (owner request, 2026-10-02)

**Why.** Every ML round so far (§19–21) let the model choose entries only and
closed each trade on a clock: 24 bars, or 4 days in §21. The owner has since
ruled out time exits (`AGENTS.md` step 3b). They asked for a model that, at
every bar it holds, decides whether to keep the position or close it, with no
time limit. This is the first test in the project in which the model also
owns the exit.

**Design (`src/ml_hold.py`, test 23).** Every value below is fixed before the
run.
- **Data and features.** The same 20 coins and 1h cache as §20–21
  (`ml_pool.py --build`; no new download). The features are §21's set (the
  coin's own bars, cross-coin and BTC), read at the bar close.
- **One pooled LightGBM regression.** Every 4 hours (the close of hours
  3, 7, …, 23 UTC) it forecasts
  `log(open[i+1+24] / open[i+1]) / (ATR14 / close)`: the next 24 h move in
  ATRs.
- **Policy, with hysteresis.** `e_in` is the rolling `q_in` quantile of the
  coin's own last 180 |forecasts| (causal; no entries during the first 60
  decisions of a period).
  - Flat → long when the forecast is above `e_in`; flat → short when it is
    below −`e_in`.
  - Long → short (or short → long) directly when the forecast crosses to the
    other side's `e_in`.
  - Long → flat when the forecast falls under `e_out`, and short → flat
    likewise. `e_out` is 0 ("flip") or `e_in`/2 ("half").
- **Exits.** A position ends only when:
  - the desired position changes (next open, taker + slippage, reason
    `signal`);
  - the protective stop of 8 × ATR at entry is hit (stop-first, gaps at the
    open); or
  - the period ends (`eod`).

  There is **no maximum hold**. After a stop, the next decision can re-enter.
- **Tuning on TRAIN only.** 4 LightGBM settings × `q_in` {0.6, 0.75, 0.9} ×
  exit {flip, half} = 24 cells. The cell with the highest out-of-fold net mean
  R per trade (≥ 300 trades) is chosen, over the 3 purged expanding folds of
  §19.
- **Timing control.** This replaces the trade-shift control of §21, because
  holds are not fixed.
  - The statistic is the return held per hour, in ATRs, before stops and
    costs: pure timing.
  - The model's desired-position sequence is shifted circularly 200 times per
    coin. Each copy keeps the same long, short and flat durations, so market
    drift helps the copies exactly as much as it helps the model.
- **Simulator.** `ml_hold.simulate` is checked trade-for-trade against
  `run_backtest`, with exit signals, reversals, stops and funding (test 23).

**Gates on VALID (all needed):**
- TRAIN OOF mean > 0.
- ≥ 300 VALID trades.
- Net mean > 0, and weekly-block 95% CI lower bound > 0.
- Net mean > 0 at cost ×1.5.
- Pooled timing above the shifted copies' 95th percentile.
- ≥ 10 coins with ≥ 15 trades. At least half of those must be net > 0
  **and** above their own shifted median.
- Both legs net > 0.

**Holdout (`--final`, once, only after PASS).** CONFIRMED needs all of:
- net mean > 0;
- CI lower bound > 0;
- timing above the shifted median;
- at least half the coins above their own shifted median.

**Outputs.**
- `results/_multi/ml_hold/`:
  - `summary.json`;
  - `trades_valid.csv.gz` and `desired_valid.csv.gz`, which are for the
    results-page chart;
  - the holdout files, if any.
- `journal/_multi/ml_hold.md` (generated).

**Prior:** low. Three ML rounds found no entry timing (§19–21), and adding the
exit gives the model more freedom to fit noise. Two things make this round
different, not just bigger:
- the model now owns the exit;
- the control is built for variable holds.

A REJECT closes ML on this data.

---

## 28. Walk-forward, multi-timeframe ML on 50 coins (owner request, 2026-10-02)

**Why.** §27's model was fitted once on 2020–22, a year that ended in a bear
market, and then frozen for 2023–24. It wanted to be short 27% of the time and
long only 4.5%, and its long leg lost. Its timing beat the shifted copies
(the first ML timing pass), but it was worth only +0.009 R gross against
0.022 R of cost.

The owner asked for three changes:
- **Walk-forward on many coins:** refit every month on everything known by
  then, as it would run live.
- **Timeframes 1h, 4h and 1d only.** 1d is allowed here by the owner's
  request; the evaluate.py rule of 15m–4h is unchanged.
- **Multi-timeframe input.** The model trading one timeframe also sees the
  others.

**Design (`src/ml_wf.py`, test 24).** Every value below is fixed before the
run.
- **Universe.** 50 coins by TRAIN volume, chosen by
  `ml_pool.select_universe(n=50)` (listed by 2021-01-01, trading on
  2022-12-31). Later delistings stay in. Native Binance 1h, 4h and 1d klines
  and funding come from `ml_wf.py --build`; they are never resampled.
- **Features at the bar close of the traded timeframe:**
  - §19's per-coin set;
  - §21's cross-coin/BTC set (windows in bars);
  - funding as-of the close;
  - **the §19 per-coin set of the other two timeframes, from their last bar
    that has closed by this bar's close** (prefixes `h1_`, `h4_`, `d1_`).
    Test 24 checks closed bars only, the latest one, and equality with
    features computed on the truncated series.
- **Label, policy and exits.** As §27, in bars of the traded timeframe:
  - the label is the next 24 bars (24 h, 4 days, 24 days) in ATRs;
  - a decision is taken at every bar;
  - the hysteresis policy uses a rolling 180-forecast entry bar;
  - exits are the signal, the 8-ATR stop, and the period end. There is no
    clock.
- **Monthly refits.**
  - **Training rows:** a model fitted at the start of month m trains on every
    row whose label is complete before m, across all coins, and predicts only
    month m. Test 24 checks that every training label ends before its month.
  - **TRAIN choice:** a walk-forward over 2021-01 → 2022-12 (24 refits per
    setting) gives out-of-sample forecasts. It picks 1 of 24 cells (4
    LightGBM settings × `q_in` {0.6, 0.75, 0.9} × exit {flip, half}) by net
    mean R per trade (≥ 300 trades).
  - **VALID:** a walk-forward over 2023-01 → 2024-12 with that cell.
- **Gates on VALID, per timeframe, all needed:**
  - TRAIN walk-forward mean > 0;
  - ≥ 300 trades;
  - net mean > 0 and weekly-block CI lower bound > 0;
  - cost ×1.5 mean > 0;
  - pooled timing above the 95th percentile of 200 shifts of the desired
    path;
  - ≥ 10 coins with ≥ 10 trades, at least half of them net > 0 **and** above
    their own shifted median;
  - both legs > 0.
- **Holdout, one only.** The three timeframes are three tries, so only one may
  use the holdout: among the PASS timeframes, the one with the highest TRAIN
  walk-forward mean. `--final` continues the monthly refits over
  2025-01 → 2026-08. CONFIRMED needs all of:
  - net mean > 0 and CI lower bound > 0;
  - timing above the shifted median;
  - breadth ≥ half.

**Why each trade (reported, never a gate).** Every trade file carries:
- the forecast at the decision that opened the trade, and at the decision that
  closed it when the exit was a signal;
- the entry bar at that moment;
- the 3 features that pushed the forecast most toward the decision. These are
  LightGBM per-feature contributions, which add up to the forecast. Test 24
  checks that each opening forecast is on the trade's side and past the entry
  bar.

The results page shows them as the reason for each entry and exit.

**Outputs.**
- `results/_multi/ml_wf/`:
  - `universe.json`;
  - `tf<N>.json`;
  - `trades_valid_tf<N>.csv.gz` and `desired_valid_tf<N>.csv.gz`;
  - the holdout files, if any.
- `journal/_multi/ml_wf.md` (generated).

**Prior:** low. VALID has now judged five ML attempts. Monthly refits address
§27's stale-regime problem. They do not obviously make the timing larger than
cost. A REJECT on all three timeframes closes ML in this project.

**Addendum (2026-10-02, after Exp 020 aborted; code fix, then re-registered as
Exp 021).** The first run stopped with means of about −1e30 R. The cause was
frozen zero-volume bars in halted or delisted contracts, where open = high =
low = close. Their true range is 0, so ATR14 reaches 0 and every ATR-scaled
label and R diverges. This was a defect in `ml_wf.py`, not a market result.

Fixed in code, with test 24 extended:
- **Tradable bars.** A bar is tradable only if its volume is > 0 and
  ATR14/close ≥ 0.01% (`AFRAC_MIN`).
  - No forecast, no decision and no entry on a non-tradable bar.
  - A label is NaN if any bar of its window did not trade.
  - The timing statistic skips dead bars.
- **Dead tail.** Each coin's series is cut after its last traded bar.
- **Cross-coin features.** A dead bar's close is not a price.
- **Universe.** It is re-chosen with zero-volume days removed
  (`universe_v2.json`), because v1 counted a frozen day as "trading on the last
  TRAIN day". The v1 file stays as the record of Exp 020.

Every other value of §28 is unchanged. Because the data and the universe
changed, the run counts as a new registered run (Exp 021), not a re-run of a
result: none existed.

---

## 29. Walk-forward ML with spot history from 2017 (owner request, 2026-10-03)

**Why.** The planner's review of §28 (`_multi` Exp 023 and the analysis given
to the owner) found three things:
- The forecasts are almost unrelated to outcomes. The information coefficient
  on VALID was +0.02 at 1h and −0.06 at 4h and 1d.
- The model relies on market-wide features: 78–100% of top entry reasons are
  BTC or market variables. With coins correlated at about 0.61, 47 coins carry
  about 1.6 coins' worth of independent market information.
- The training data held only three market regimes, and the model learned to
  fade rallies (2021–22) in a rising market (2023–24).

The owner asked for longer history. 2016 is not on Binance; the owner chose
Binance **spot**, which starts in 2017-08. That adds the 2017 bubble, the 2018
bear market and 2019.

**Design (`src/ml_wf2.py`, test 25).** This is §28 exactly, with one change:
**features and labels are computed on each coin's spot bars**, so every monthly
refit trains on up to about three more years of history.
- Trades are simulated on the coin's **perp** bars on the same timestamps, with
  perp costs and funding.
- The windows are §28's: TRAIN walk-forward 2021–22, VALID 2023–24, HOLDOUT
  2025-01 → 2026-08. The results are therefore comparable with §28.
- **Universe.** §28's perp rule, restricted to coins whose spot pair traded by
  2018-01-01.
- **Tradable bars.** A bar is tradable only if both its spot and its perp bar
  traded and the perp ATR fraction is at least 0.01%.
  - Forecasts and entries exist only on tradable bars.
  - Training rows need only a clean spot label.
- `funding_last` is NaN before perp funding exists.

Every other value (features, multi-timeframe inputs, label, policy, grid,
gates, and the single holdout timeframe) is §28's.

**What it can show.**
- If the extra regimes are what was missing, TRAIN walk-forward and VALID
  should improve over §28 on the same windows.
- If not, the conclusion of §27–28 (timing smaller than cost) stands with
  twice the history behind it.

**Prior:** low. It is the seventh ML look at VALID. The holdout remains the
only clean judge, and only a PASS may use it.

---

## 30. Walk-forward ML on §28's 47 coins, each with all its spot history (owner request, 2026-10-03)

**Why.** §29 meant to ask "does a longer history help?". Its universe rule
(spot pair by 2018-01-01) left 4 coins. It therefore changed the history and
the universe at once, and its breadth gates could not be met. This was the
planner's error (`_multi` Exp 025/026). On those 4 coins, a like-for-like IC
check showed the longer history improving the forecasts slightly. The owner
asked for the clean test.

**Design (`src/ml_wf3.py`, test 26).** The one difference from §28 is the
length of each coin's history.
- **Universe.** Exactly §28's 47 coins (`results/_multi/ml_wf/universe_v2.json`,
  copied unchanged).
- **History source.** Each coin's features and labels come from its Binance
  spot bars, from the pair's own first month, when the spot pair traded
  before the perp started. Otherwise they come from the perp bars, as in §28.
  Checked before registration against the real archive:
  - 46 of 47 coins have a spot pair; DEFIUSDT has none.
  - 35 of the 47 get history from before their perp started. The earliest are
    BTC and ETH (2017-08), BNB and NEO (2017-11), QTUM (2018-03), ADA (2018-04)
    and EOS (2018-05).
  - The median spot start is 2019-09.
- **Everything else is §28, via §29's code.**
  - Trades run on perp bars with perp costs and funding.
  - The windows are the same: TRAIN walk-forward 2021–22, VALID 2023–24,
    HOLDOUT 2025-01 → 2026-08.
  - So are the cell grid, the gates and the single holdout timeframe.

**Expectation, stated before the run.**
- The gain in history is real but uneven. About 10 coins add the 2018 bear
  market; most add roughly one year.
- If longer history helps, TRAIN walk-forward and VALID should beat §28 on
  the same 47 coins and windows. The VALID IC and gross R can be compared
  coin for coin.

**Prior:** low. This is the eighth ML look at VALID. Only a PASS may use the
holdout, and only once.

**Addendum (2026-10-03, after Exp 028 aborted; code fix, re-registered as
Exp 029).**

**The defect.** The first run crashed entering 1h VALID. The cause was my
history rule, not the shared window code:
- A coin used its spot bars for the whole history if the spot pair started
  before the perp.
- HNT's spot pair ended in 2022-10, so its history frame stopped before VALID
  and the trading window was empty. That is the crash.
- XMR's spot ended in 2024-02, so it would silently have traded only part of
  VALID.
- MATIC's and TOMO's spot ended with their perps.

**The fix.** Each coin's history is now its spot bars from before the perp's
first bar, followed by the perp bars themselves (`history_source`,
"splice").
- From the perp start, the frame is §28's frame exactly.
- Only the training rows before the perp start are new.

**Tests.** Test 26 now checks:
- the splice;
- a spot pair delisted before VALID;
- the full pipeline on such a coin.

Everything else in §30 is unchanged.

---

## 31. Portfolio layer on §30's 1h model: agreement, sizing, risk cap (owner request, 2026-10-03)

**Why.** §30's 1h book failed one gate, the weekly-block CI. Its mean was
+0.0374 R and its CI [-0.024, +0.101] (`_multi` Exp 030/031). Two things drove
the weekly swing:
- dozens of same-direction positions were open together on coins that move
  together (correlation about 0.61);
- every trade carried the same 1% risk whatever the model's confidence.

The owner asked to work on the portfolio side. The model is **not** changed.

**Design (`src/ml_port.py`, test 27).**
- **Forecasts.** §30's three frozen walk-forward models (1h, 4h and 1d, each
  with the cell its own TRAIN walk-forward chose) are recomputed. The run
  stops unless the recomputed VALID forecasts match §30's recorded ones within
  1e-6.
- **One account for all 47 coins.** Three switches are added on top of the
  1h book:
  - **A, agreement** (`off`, `4h`, `1d`). A new 1h position opens only if the
    last closed 4h (or 1d) forecast for that coin has the same sign. Exits are
    unchanged.
  - **S, sizing** (`flat`, `conf`). `flat` is 1% risk. `conf` is 1% × w, with
    w = 0.5 at the entry bar rising linearly to 1.0 at twice the entry bar.
    Risk is never above 1%.
  - **K, cap** (none, 5%, 10%). This caps total open risk per direction. A new
    entry gets at most the remaining room and is skipped below 0.1%.
- **Account accounting.** Each trade returns net R × its risk fraction, added
  to starting equity. A week's return is the trades that closed in it; empty
  weeks count as 0.
- **Cell choice on TRAIN only.** The TRAIN walk-forward (2021–22) chooses 1 of
  the 18 cells by the t-statistic of the weekly account return, with at least
  300 trades.
- **Gates on VALID (all needed):**
  - TRAIN weekly mean > 0;
  - ≥ 300 trades;
  - weekly mean > 0, and its 95% bootstrap CI lower bound > 0;
  - weekly mean > 0 at cost ×1.5;
  - timing of the filtered desired path above the shifted p95;
  - ≥ 10 coins with ≥ 10 trades, at least half of them net > 0 and above their
    own shifted median;
  - both legs' summed return > 0;
  - account max drawdown ≤ 20%.
- **Holdout (once, only after PASS).** CONFIRMED needs all of:
  - weekly mean > 0;
  - CI lower bound > 0;
  - timing above the shifted median;
  - breadth ≥ half.

**What it can show.** If the CI failure came from correlated, equally sized
bets, a capped or confidence-sized account should narrow the weekly CI at
little cost to the mean. If not, the 1h result was the 2024 regime.

**Prior:** low to moderate. It is built on the nearest miss so far. It is
still a further look at VALID, and only the holdout can settle it.

## 32. Cross-sectional (market-demeaned) forecasts on §31's account (owner request, 2026-10-04)

**Why.** §31 failed one gate by 0.00026, the weekly CI lower bound
(`_multi` Exp 033). The review (`_multi` Exp 034) found that its return was
concentrated:
- the 5 best of 105 weeks gave 67% of the total;
- 2023 without its 3 best weeks was -0.079.

Two earlier findings point at the same cause:
- §30's top WHY reasons were market-wide features 78–100% of the time;
- the 47 coins behave like about 1.6 independent coins.

So the book is mostly one bet on the market's next move, and the owner saw
it: "it goes short while the trend is up".

**Hypothesis.** The models carry a coin-relative signal (which coins will do
better or worse than the others) under a market-wide part that is mostly
noise. Removing the market-wide part should do three things:
- leave the relative signal;
- hold long and short at the same time;
- cut the common weekly swing that widens the CI.

Each trade is still one coin on its own, with no hedge leg, so this is not
pairs trading (which the owner excluded).

**Design (`src/ml_xs.py`, test 28).**
- **No model is refitted.** §31's recomputation and its 1e-6 reproduction
  check are reused (`ml_port.forecasts`).
- **F, form** (`raw`, `demean`). `demean` means: at each open time, a coin's
  forecast minus the mean of every coin's forecast at that time.
  - It needs ≥ 10 coins with a forecast; otherwise there is no forecast.
  - The same transform is applied to the 4h and 1d agreement forecasts.
  - The entry bar and confidence are then computed per coin on the transformed
    forecast, exactly as before.
- **§31's switches:** agreement off, 4h or 1d; sizing flat or conf; cap 5% or
  10%. Uncapped is dropped because it lost 150% on TRAIN in §31.
  This gives 24 cells.
- **Cell choice on TRAIN only.** The TRAIN walk-forward (2021–22) chooses one
  cell by the weekly account t-statistic, with ≥ 300 trades. A `raw` choice is
  §31 again and is REJECT (gate `train_chose_demean`).
- **VALID gates** are §31's, unchanged.
- **Diagnostics (not gates):**
  - the share of the total from the best 5 weeks;
  - the number of negative weeks;
  - beta and correlation of the weekly account return to the equal-weight
    weekly market return of the 47 coins.
- **Holdout.** §31 and §32 share one holdout; `--final` refuses if §31 used
  it. CONFIRMED uses §31's rule.

**What it can show.**
- **Supports the hypothesis:** TRAIN chooses `demean`, VALID beta and the
  top-5-week share fall, and the CI moves above 0.
- **Answers it the other way:** TRAIN chooses `raw`, or `demean` loses the
  mean. Then §30's signal was the market-wide part, and §31's 2024 result was
  a market regime.

**Prior:** low to moderate. This is another look at VALID 2023–24, the 7th ML
look in `_multi` (§27–§32). Even a PASS needs the holdout, and the record
must state the number of looks.

## 33. Market timing on BTC/ETH from the 47-coin mean forecast (owner request, 2026-10-04)

**Why.** §32 and its review showed what §30's 1h model is.
- **The usable signal is market-wide.** Demeaning the forecasts across coins
  removed the edge (`_multi` Exp 036).
- **§31's book is a market timer** (`_multi` Exp 037):
  - in an average week, 89% of the trades that close are on one side;
  - the best weeks are one-sided shorts across many coins that won together;
  - beta is near 0 only because the side changes over time.

One market call spread over about 40 alt-coins pays alt-coin costs about 40
times (slippage 0.05% against 0.02%) and adds alt-coin noise.

**Hypothesis.** The same call, made once on the most liquid contracts, keeps
the timing and sheds most of the cost and noise.

**Design (`src/ml_mkt.py`, test 29).**
- **No refit.** §30's frozen 1h and 4h models are recomputed and checked to
  1e-6 (`ml_port.forecasts`).
- **Signal:** m(t) = the mean of the 47 coins' 1h forecasts at open time t,
  with ≥ 10 coins. It uses only forecasts made at t, so it is causal.
- **Policy:** §30's own hysteresis on m.
  - The entry bar is the rolling q_in = 0.9 quantile of |m|.
  - The exit mode is §30's `flip`.
  - An 8-ATR protective stop; no clock.
  - Perp bars, perp costs and funding.
- **Cells (6):**
  - **I, instrument:** BTC, ETH, or BTC+ETH. For BTC+ETH each contract gets
    0.5% risk, so the total stays ≤ 1%.
  - **A, agreement:** off or 4h. §31's rule, using the 4h mean forecast.
- **Cell choice on TRAIN only.** The TRAIN walk-forward (2021–22) chooses one
  cell by the weekly account t-statistic, with ≥ 30 trades.
- **VALID gates (all needed):**
  - TRAIN weekly mean > 0;
  - ≥ 30 trades;
  - weekly mean > 0, and its 95% bootstrap CI lower bound > 0;
  - weekly mean > 0 at cost ×1.5;
  - timing above the shifted p95;
  - both legs > 0;
  - max drawdown ≤ 20%.

  Breadth does not apply with 1–2 contracts.
- **Diagnostics (not gates):**
  - time spent long, short and flat;
  - the share of the total from the best 5 weeks;
  - the number of negative weeks;
  - buy-and-hold weekly return;
  - beta and correlation to buy-and-hold.
- **Holdout.** §31, §32 and §33 share one holdout; `--final` refuses if either
  of the others used it. CONFIRMED needs a weekly mean > 0, a CI lower bound
  > 0, and timing above the shifted median.

**What it can show.**
- **Supports the hypothesis:** the timing survives on 1–2 contracts and the
  costs fall.
- **Answers it the other way:** the edge needs the alt-coin moves (alts fall
  harder in sell-offs), which a BTC/ETH-only book cannot capture.

**Prior:** low to moderate. This is the 8th ML look at VALID 2023–24. A
1–2-contract book has fewer trades, so the weekly CI may be wider.

## 34. Positioning data for §30's 1h model, judged on §31's account (owner request, 2026-10-04)

**Why.** §31–§33 located §30's edge, if it is real (`_multi` Exp 033–040):
- it needs each coin's own forecast, traded on that coin;
- it comes mostly from shorts on alt-coins in sell-offs.

The model has only ever seen prices, volume, taker flow and the coin's last
funding rate. It has never seen positioning: how much leverage is open, which
side the crowd is on, and what funding costs the whole market.

The owner chose new data over spending the holdout now. The planner's power
estimate: at §31's VALID edge and weekly volatility, the 87-week holdout would
CONFIRM only about 39% of the time even if the edge were fully real, and
about 13% at half that edge.

**Hypothesis.** The sell-offs the model catches are liquidation cascades. They
are more likely when open interest has built up, the crowd is long and funding
is high. Positioning should sharpen exactly the trades that carry the book.

**Design (`src/ml_flow.py`, test 30). An ablation: only the features change.**
- **Data.** `--build` downloads Binance daily metrics files for the 47 coins
  (2021-12 → 2026-08) to `data/cache/_multi/metrics/`. Metrics start
  2021-12-01 for every coin in the universe (checked by the planner).
- **New features, all causal on the 1h bar close.** A metrics row is used 5 min
  after its `create_time` and is NaN when more than 30 min stale
  (`experiment.attach_metrics`).
  - Per coin: `oi_chg_24`, `oi_chg_168`, `oi_to_vol`, `top_pos_ls`, `acct_ls`,
    `acct_ls_chg_24`, `fund_168`.
  - Market-wide (same-hour mean, ≥ 10 coins): `mkt_oi_chg_24`, `mkt_acct_ls`,
    `mkt_funding`, `mkt_fund_168`, `rel_oi_chg_24`.
  - Funding exists through all of TRAIN. Metrics exist for 13 of TRAIN's 24
    months. LightGBM reads NaN as missing.
- **Fixed:**
  - §30's chosen 1h setting (refit monthly on the 47 coins' histories), q_in
    0.9 and `flip`;
  - §30's frozen 4h forecasts for agreement;
  - §31's chosen account cell (agreement 4h, conf sizing, 5% cap), with §31's
    stop, costs and gates.
- **Cell choice on TRAIN only.** The TRAIN walk-forward (2021–22) compares
  `base` (§31 recomputed) with `flow` (base + the new features) by the weekly
  account t-statistic. A `base` choice is REJECT (gate `train_chose_flow`).
- **Diagnostics (not gates):**
  - the flow features' share of the VALID refits' total gain;
  - the share of the total from the best 5 weeks;
  - the number of negative weeks;
  - TRAIN return by year.
- **Holdout.** §31–§34 share one holdout; `--final` refuses if any used it.

**What it can show.**
- **Supports the hypothesis:** TRAIN prefers `flow`, the model uses the new
  features (gain share), and the VALID weekly CI clears 0 with less
  concentration.
- **Answers it the other way:** `base` wins, or `flow` matches it with little
  gain share. Then positioning adds nothing the price features did not
  already carry.

**Prior:** low to moderate. This is the 9th ML look at VALID 2023–24. TRAIN
saw only 13 months of metrics, so the TRAIN comparison leans on 2022.

## 35. Short newly listed perpetuals (owner request, 2026-10-04)

**Why a new family.** §31–§34 did not move the frozen §31 cell, and the holdout
has low power for it (Exp 041). The owner chose to start a family that differs
from the ML line. It was ranked first of four candidates by the planner, for
three reasons:
- it has a seller with a reason;
- its costs are low against a hold of days to weeks;
- the holdout has enough events to judge it.

It is untested here. §17 explicitly dropped coins younger than 60 days.

**Hypothesis.** A coin newly listed on Binance USDT-M tends to fall for weeks
after the listing. Holders who got it cheaply (airdrops, early investors, the
team, unlocks) sell into the new liquidity, and the first-day attention fades.

**What happens in a rising market:** the short side is the only side, and it
is what loses in a bull run. That is why each VALID year must be positive and
the control removes the market's own move.

**Data, checked by the planner.**
- About 900 USDT-M perp symbols on data.binance.vision, delisted ones
  included.
- First daily bars by year: 2020 81 (mostly founding contracts, excluded by
  `LISTED_AFTER` 2020-02-01), 2021 59, 2022 26, 2023 97, 2024 131, 2025 241,
  2026 262.
- So TRAIN has about 85 listings, VALID about 228, and the holdout about 500.
- Frozen zero-volume bars after a delisting are cut.
- `api.binance.com` is blocked here, so the listing day is the first daily bar
  in Binance's files. For FTTUSDT, for example, that is 2022-04-15.

**Design (`src/listing.py`, test 31).**
- **Event.** One per symbol: the first run of its first daily bar, after
  2020-02-01. A relaunch after a gap is not an event.
- **Trade.** Short at the open of listing + DELAY days, on daily bars.
  - **Stop:** entry × (1 + STOP), filled at the stop, or at the open on a gap.
  - **Trailing signal exit:** a close above the lowest close since entry ×
    (1 + TRAIL) covers at the next open.
  - **Otherwise:** the window end (`eod`), or the last traded close if the
    contract was delisted first.
  - No clock.
  - **Costs:** taker fee and alt slippage on each side, plus funding (a short
    receives a positive rate).
  - R = STOP.
- **Account.** §31's accounting at 0.25% risk per listing, with at most 10%
  open (about 40 shorts at once, so the cap rarely decides which listing is
  taken).
- **Cell choice on TRAIN only.** TRAIN (2021–22) picks 1 of 12 cells (DELAY
  1/3/7 × STOP 0.3/0.5 × TRAIL 0.3/0.6) by the weekly account t-statistic, with
  ≥ 30 trades.
- **VALID gates (all needed):**
  - TRAIN weekly mean > 0;
  - ≥ 100 trades;
  - weekly mean > 0 and its CI lower bound > 0;
  - cost ×1.5 > 0;
  - the event mean net R beats the 95th percentile of 200 control draws, on
    TRAIN and on VALID. A control draw shorts an established perp (listed
    ≥ 365 days earlier, trading that day) on each event's day with the same
    exits;
  - mean R without the 5 best trades > 0;
  - both VALID years > 0;
  - max drawdown ≤ 20%.
- **Diagnostic (not a gate):** the event mean for new tokens (no Binance spot
  pair before the listing month) against existing tokens that only got a new
  perp.
- **Holdout.** Its own one-time holdout (a different family from §31–§34).
  CONFIRMED needs a weekly mean > 0, a CI lower bound > 0, and the event mean
  above the control's p95.

**What it can show.**
- **Supports the hypothesis:** newly listed coins fall more than established
  coins shorted on the same days, in both VALID years, after costs and
  funding.
- **Answers it the other way:** the event mean sits inside the control. Then
  shorting new listings is just shorting alt-coins.

**Prior:** moderate. The mechanism is plausible and the effect is widely
discussed, which is exactly why it may already be priced in (in funding, for
example). The holdout's ~500 listings would give it real power.
