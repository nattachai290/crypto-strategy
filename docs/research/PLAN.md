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
>
> ไอเดียไหน PASS → ทดสอบกับข้อมูลที่ล็อกไว้ (2025–26) ครั้งเดียว → ถ้ายืนยันผ่าน ทำใบสรุปกลยุทธ์
> และทดลองเทรดกระดาษ (สัญญาณอย่างเดียว ไม่ส่งออเดอร์) อย่างน้อย 3 เดือน ก่อนที่คุณจะตัดสินใจเรื่องเงินจริง

---

**Audience:** the AI agent that runs this plan. Read `AGENTS.md` first; every
rule there applies. `AGENTS.md` says **how** to test an idea; this plan says
**which ideas, in what order, and what to do with the results**.

Scope: **BTCUSDT only.** Do not add other coins.

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
5. Optional: `--mode time --tfs <neighbours>` tests "the same trade on a finer
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
| §6 | 3–4 h to build + ≥ 3 months of paper trading | only after a CONFIRMED |
