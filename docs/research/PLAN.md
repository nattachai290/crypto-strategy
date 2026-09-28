# Research plan — finding BTCUSDT trading techniques

> **สรุปสำหรับเจ้าของ (Thai summary for the owner)**
> แผนวิจัยหาเทคนิคเทรด BTCUSDT อย่างเดียว แบ่งเป็น 4 รอบ รอบละ 5–6 ไอเดียที่ต่างกันจริง
> **ทุกไอเดียทดสอบครบทุก timeframe** (1m 3m 5m 15m 30m 1h 4h) ด้วย `src/tf_variants.py` ไม่ล็อก TF
> และออกแบบไอเดียให้เทรดบ่อยพอ เพราะเกณฑ์ผ่านต้องได้ค่าเฉลี่ยต่อไม้สูงขึ้นมากเมื่อจำนวนไม้น้อย
> - **รอบ 1**: หาจุดเข้าฝั่ง short แบบใหม่ (ฝั่งเดียวที่เคยเห็นกำไร) + ทำความเข้าใจว่าไอเดีย 010 ได้กำไรเพราะอะไร
>   โดยเฉพาะ: ทำไม short ถึงกำไรในปี 2023–24 ที่ BTC เป็นขาขึ้นแรง
> - **รอบ 2**: เทคนิคปิดไม้ (TP, SL, BE, trailing, time stop) บนจุดเข้าที่ดีที่สุดจากรอบ 1 รวมเป็น 2 การทดสอบ
> - **รอบ 3**: ถือนานขึ้นแบบ swing (หลายชั่วโมงถึงหลายวัน) และทดสอบฝั่ง long อีกครั้งที่ระยะนี้
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

From `journal/BTCUSDT/STATUS.md` and Exp 011–013:

| Settled finding | Consequence for this plan |
|---|---|
| Stop must be a **% of price** (`"stop": {"type": "pct"}`), not an ATR multiple | Use `pct` stops in every idea, unless the idea is *about* ATR stops |
| Costs ≈ 0.14% per round trip (0.09% with post-only entry); `cost_r = cost / stop%` | Stops ≥ 1.5% of price; prefer post-only entry (`"entry_mode": "post_only"`, offset 0–0.2 ATR) |
| **Long side**: nothing found in 16 evaluations, almost all at 15m (continuation, reversion, trend) | No new long-only ideas in Rounds 1–2. Long returns in Round 3 (swing), and its timeframe variants cover the rest |
| **Short side**: the only positive results (ideas 007/010) | Round 1 explores *other* short structures |
| Edges need **6–18 h holds**; ≤ 4 h holds were negative (Exp 009) | Design source ideas with holds ≥ 6 h; Round 3 is about multi-day holds |
| The 16 evaluations were **15m ×14, 30m ×1, 5m ×1**. 1m, 3m, 1h and 4h were never tested in the current workflow | Every idea now runs on all seven timeframes (§2b) |
| Idea 010's structure (15m `donchian_break` + `htf_trend` + `adx_min`, short) used ~8 versions | **No more variants of that structure.** It stays WATCH |
| Filters `taker_flow`, `funding_not_crowded` were inert on 010 | Don't use them as "confirmation" on breakouts again |
| Mean reversion (ideas 003, 016, example) and funding crowding (003, 014) | Answered. Don't repeat |

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

Idea 010 made +0.085 on 219 trades: a good number, too few trades. So:
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
4. **Act on each verdict** (AGENTS.md §1 step 6). WATCH may get ≤ 2 diagnosed
   versions. PASS → §5 immediately.
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

### Round 1 — New short-side structures + understanding idea 010 (≈ 3 h)

**Why:** the short side is the only place with any positive signal. Test
whether *other* short structures work, which would show that the short edge
is real and not one lucky pattern.

**R1.0 — Analysis of idea 010, no new evaluation.** Load its trades with
`pd.read_csv("results/BTCUSDT/eval_trades/70fb497bcf_valid.csv.gz")` (in git;
if it is ever missing, `python src/evaluate.py ideas/010_short_breakout_post_only.json --trades-only`
re-creates it without recording anything). Write a short analysis in the
Round 1 pre-registration entry:
- R by hour of day (UTC), by weekday, by month
- R vs the 8h return of BTC *before* entry (is it just "short after a drop"?)
- R vs the funding rate at entry
- R of trades held to the time stop vs trades stopped/trailed
- **The key question: why does a short strategy make money in 2023–24,
  when BTC rose from ~16k to ~95k?** It can't be "BTC drifts down". Measure:
  R by the 30-day trend of BTC at entry (up / flat / down); R by how far
  price had fallen in the 12 h before entry; how many bars after entry the
  low of the trade came. If the wins come from short dips inside a bull
  market (sell-offs that continue for a few hours), write it down as the
  mechanism. That is an explanation, and it gives new ideas (e.g. "short
  the first break of a 12 h low after a strong rally")
- **Use:** any pattern you find becomes a *hypothesis for a new structure*
  in Round 1 or 4. **Never** add it as a filter to 010 itself (010's
  structure is closed).

| # | Idea | Recipe sketch | Kill if |
|---|---|---|---|
| R1.1 | Short pullback in a downtrend: price bounces to the fast EMA, fails, continues down | trigger `pullback` (fast 20 / slow 50), filters `trend_ema` (50/200) + `adx_min`; direction short; stop pct 1.5–2.5%; trail; hold 8–12 h | train mean R ≤ 0 |
| R1.2 | Short momentum impulse: a sharp drop (> k·ATR in n bars) keeps going | trigger `momentum` (n 8–16, atr_k 1.5–2.5), filter `htf_trend`; short; pct stop | train mean R ≤ 0 |
| R1.3 | Short after a failed bounce: in a downtrend, a fast EMA crosses down again while price is below the daily VWAP | trigger `ema_cross` (fast 8 / slow 21), filters `vwap_side` + `htf_trend`; short | fewer than 100 train trades |
| R1.4 | Short on a Supertrend flip **with** ADX + HTF (idea 015 had no ADX) | trigger `supertrend_flip`, filters `htf_trend` + `adx_min` + `di_side` | train mean R ≤ 0 (it's a different filter set from 015, so a separate structure) |
| R1.5 | **Idea 010 on every other timeframe** (no new idea file to write: `python src/tf_variants.py ideas/010_short_breakout_post_only.json`, both modes). Tests whether 010's effect exists beyond 15m | generated by the tool | positive TRAIN on the neighbours 5m/30m = support for 010's mechanism; negative neighbours = 010 is a 15m-only fluke |
| R1.6 | Short-side range break at the London/NY opens only | trigger `range_break` with `hours` [7,8,13,14], filter `htf_trend`; short | fewer than 100 valid trades → INCONCLUSIVE |

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

### Round 3 — Swing horizons, and the long side again (≈ 6 h)

**Why:** every hint of an edge needed 6–18 h holds, and the long side has
only been tested with short holds. These ideas are *designed* for holds of
many hours to several days. Write them at 1h and let §2b carry them to
every other timeframe.

⚠️ Swing ideas trade less. Design for ≥ 300 valid trades **at 1h** (both
directions, few filters). The 4h variants will usually be INCONCLUSIVE; that
is fine and expected (§2b).

| # | Idea (source tf 1h) | Recipe sketch |
|---|---|---|
| R3.1 | Donchian breakout both sides, HTF trend | `donchian_break` 24–48, `htf_trend` (n 50, mult 4), pct stop 3–5%, no TP, trail, hold 2–4 days |
| R3.2 | Trend pullback, **long** (the long side has never been tested at swing horizons) | `pullback` + `trend_ema` (50/200); long; pct stop 3%; TP 2–3R or trail |
| R3.3 | Round 1's best short structure, redesigned for multi-day holds | copy the structure, hold 1–3 days, wider pct stop |
| R3.4 | Squeeze → expansion, both sides | `donchian_break` + `squeeze` + `vol_regime lo>1`; pct stop 4%; trail |
| R3.5 | Weekday-only trend (skip weekend chop) | `ema_cross` + `weekdays` [0..4] + `adx_min` |
| R3.6 | Supertrend trend following, both sides | `supertrend_flip` + `adx_min`; pct stop 4–6%; hold up to 10 days |

**Use:** compare these seven-timeframe tables with Rounds 1–2. If the edge
appears only from 1h upwards, the project's answer is "BTC has a
multi-hour/multi-day edge, not an intraday one". Update `STATUS.md` and
`README.md` accordingly.

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

1. Immediately: `python src/evaluate.py ideas/<idea>.json --final` (one time,
   allowed by AGENTS.md for a PASS).
2. **FAILED** on holdout → record it (it's now spent for that config), lesson
   into `TECHNIQUES.md`, continue the plan.
3. **CONFIRMED** → tell the owner right away (Thai, full table), then build the
   strategy card and paper trading (§6). Continue the research rounds in
   parallel only if the owner wants.

Idea 010 (WATCH): it stays WATCH. Only the owner can decide to spend the
holdout on a WATCH result. Don't propose it unless Round 1's R1.5 (30m) or
another independent short structure also comes out PASS/WATCH positive; in
that case, report both to the owner with the evidence and let them decide.

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
| 1 | ≈ 6 h | 6 ideas × 7 timeframes + analysis of 010 (1m/3m runs are the slow part) |
| 2 | ≈ 2 h | 2 exit studies (combined grids) at the best timeframe |
| 3 | ≈ 6 h | 6 swing ideas × 7 timeframes |
| 4 | ≈ 6 h | 4–5 new blocks + ideas × 7 timeframes |
| §6 | 3–4 h to build + ≥ 3 months of paper trading | only after a CONFIRMED |
