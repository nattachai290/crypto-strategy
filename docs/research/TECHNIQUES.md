# Techniques catalogue and idea backlog

The menu for creative research. Every technique here can be tested with
`src/evaluate.py` (rules in `AGENTS.md`). Each one is marked:

- ✅ **ready**: usable today in an idea file, no code.
- 🧩 **Level 2**: needs a new building block in `src/recipes.py` (small, safe; the causality test checks it).
- 🛠 **Level 3**: needs an engine change in `src/backtest.py`. Ask the owner first.
- ⛔ **forbidden**.

---

## 1. Anatomy of a strategy

```
  TRIGGER(s)        when to act          e.g. breakout, RSI turns up
+ FILTER(s)         whether it's allowed e.g. trend up, ADX > 20, London hours
+ EXITS             how the trade ends   stop, take-profit, break-even, trail, time stop
+ EXECUTION         how you get filled   market (taker) or post-only limit (maker)
```

**The one number that decides everything:**

```
cost_r = round-trip cost / stop distance
taker round trip = 0.14% of price  ->  0.5% stop costs 0.28 R per trade, 2.5% stop costs 0.056 R
```

A technique must produce **more `gross_r` than `cost_r`**. Tight stops with
many trades almost always lose to costs; that was the main finding of
Exp 004. Prefer ATR stops of ~2.5–5x on 15m, or 15m/30m bars over 1m/3m.

---

## 2. Entry triggers

### ✅ Ready (`"triggers": [{"type": "<name>", ...params}]`)

> **The contract, and the bug that came from breaking it (Exp 024).** A trigger
> returns **one 1-D array of 0 / +1 / −1** (use `_side(long_ev, short_ev)`); a
> filter returns **two boolean arrays** `(long_ok, short_ok)`. `recipe()` does
> `np.asarray()` on whatever a trigger returns, so a trigger that returns a
> `(long, short)` tuple becomes a `(2, n)` array and is read as
> `(S > 0).any(axis=0)` — "either side fired" — which makes it **long-only**.
> `opening_range` did that for all of Exp 022 (798 long trades, 0 short). After
> adding a block, check: every trigger returns a 1-D array of 0/±1, every filter
> returns two arrays.

| type | params (defaults) | idea behind it |
|---|---|---|
| `ema_cross` | fast=20, slow=50 | trend starts |
| `donchian_break` | n=48 | breakout of the n-bar high/low |
| `range_break` | range_n=24, hours=null | breakout of the recent range, optionally only in given UTC hours (session opens) |
| `supertrend_flip` | n=10, mult=3.0 | trend flips |
| `momentum` | n=12, atr_k=1.5, atr_n=14 | impulse: move > k·ATR in n bars |
| `pullback` | fast=20, slow=50 | in a trend, dip to the fast EMA and reclaim it |
| `rsi_revert` | n=14, lo=30, hi=70 | oversold/overbought turning back |
| `bb_revert` | n=20, k=2.0 | back inside the Bollinger band |
| `zscore_revert` | n=96, z=2.0 | stretched from the mean, snapping back |
| `vwap_revert` | z=2.0, z_n=200 | stretched from the daily VWAP, snapping back |
| `funding_extreme` | thresh=0.0003 | fade a crowded side when funding is extreme |
| `failed_break` | n=48, n_bars=8 | a break of the n-bar extreme that failed (close back inside within n_bars bars): the breakout traders are trapped and must cover. **Tested in Exp 016, REJECTed at all 7 timeframes** (`gross_r` negative everywhere: −0.015 at 15m, −0.034 at 1h). Kept as a documented negative: the reclaim has already happened when the signal fires, so the fade pays the whole spread for a move that is over. |
| `prev_day_break` | days=1 | close breaks **yesterday's** UTC high/low — the level where stops sit and breakout orders queue. Only completed previous days are read. |
| `opening_range` | mins=60, hour=0 | close crosses outside the high/low of the first N minutes after a UTC hour. The window must be complete before it can be used, so it only fires after the window closes. |
| `keltner_break` | n=20, mult=2.0 | close crosses outside EMA(n) ± mult·ATR: a volatility channel that widens with volatility instead of lagging like a Donchian. |
| `flush` | k=2.0, m=1.5, lookback=96, mode follow/fade | bar range > k·ATR **and** volume > m·its own shifted average: a liquidation cascade. `mode` picks which side is the trade, because "cascades overshoot" and "cascades start trends" are opposite hypotheses and the data has to choose between them. |
| `month_turn_fade` | before=2, after=2, lookback=6 | on bars within N days of a UTC month boundary, take the side opposite to the `lookback`-bar move that got price there. A calendar window, not a price one: risk budgets, index rebalancing and benchmark rolls push price into the boundary and stop at it. Naturally both-sided, so it cannot be a disguised long. **Exp 024: INCONCLUSIVE** — a 5-day window with a 96h hold leaves under 30 VALID trades. |

### 🧩 Worth adding (Level 2 blocks)

| idea | sketch |
|---|---|
| previous-day high/low break | yesterday's high/low: `groupby(index.date)` max/min, shifted by one day, mapped back to each bar (never today's full-day value) |
| opening range breakout | high/low of the first N minutes after 00:00 / 08:00 / 13:30 UTC, then break |
| inside bar / NR7 break | compression candle, then range break |
| volatility breakout (Larry Williams) | open of day + k × yesterday's range |
| Keltner / ATR channel break | EMA ± k·ATR |
| MACD histogram turn, stochastic cross | classic oscillators as triggers |
| engulfing / pin bar at a level | candle pattern + location (near VWAP or daily extreme) |
| liquidation-cascade proxy | bar range > k·ATR **and** volume > m × average, then fade or follow |
| taker-flow imbalance flip | taker buy ratio crosses 0.5 after being extreme |
| funding change | funding sign flips or jumps by x |
| round-number reaction | price near multiples of 1,000 / 5,000 USDT |
| weekend/Monday effect | trigger at a fixed weekly time |

Rules for a new block: pure function `fn(bars, funding, **params)`, uses only
bars `<= i`, docstring's first line says what it is, add it to `TRIGGERS` or
`FILTERS`, then run `python src/test_engine.py` (test 7 fails if it peeks
at the future).

---

## 3. Filters (regime, trend, timing, flow)

### ✅ Ready (`"filters": [{"type": "<name>", ...}]`; ALL must allow the direction)

| type | params (defaults) | use it to |
|---|---|---|
| `trend_ema` | fast=50, slow=200 | trade only with the trend |
| `price_vs_ema` | n=200 | same, simpler |
| `htf_trend` | n=50, mult=4 | higher-timeframe trend (mult=4 on 15m ≈ 1h) |
| `adx_min` | n=14, min=20 | only trending markets (for breakouts / trend) |
| `adx_max` | n=14, max=20 | only ranging markets (for mean reversion) |
| `di_side` | n=14 | direction of DMI |
| `rsi_side` | n=14, level=50 | momentum side |
| `vol_regime` | fast=14, slow=100, lo=0, hi=99 | only quiet (hi<1) or expanding (lo>1) volatility |
| `squeeze` | n=20, q=0.2, lookback=500 | only right after compression |
| `taker_flow` | n=20, thresh=0.52 | aggressive buyers for longs / sellers for shorts |
| `vwap_side` | — | long above daily VWAP, short below |
| `funding_window` | hours=2 | only within N hours **of** a funding settlement. Uses Binance's published 00/08/16 UTC grid, not a value read from the data, so it stays causal |
| `volume_spike` | n=96, k=1.5 | only with participation |
| `funding_not_crowded` | thresh=0.0003 | don't join a crowded side |
| `hours` | hours=[13,14,15,16] | only some UTC hours (sessions) |
| `weekdays` | days=[0..4] | e.g. skip weekends |

Also available on every recipe: `"direction": "long" | "short" | "both"` and
`"cooldown_bars": N` (no new signal for N bars after one).

---

## 4. Trade management: TP / SL / "แก้ไม้"

This is where many retail systems gain or lose most of their edge. Test exits
as their **own hypothesis**: keep the entry fixed and grid only the exit keys.

### ✅ Ready

| technique | JSON | notes |
|---|---|---|
| ATR stop | `"stop": {"type": "atr", "mult": 3}` | wider = cheaper in R (see §1) |
| **% of price** stop | `"stop": {"type": "pct", "pct": 0.02, "min_atr": 1.5, "max_atr": 8}` | **prefer this.** An ATR multiple is not a constant price distance: the same 3.0x ATR was 1.28% of price in 2020-22 and 0.78% in 2023-24, which moved `cost_r` from 0.109 to 0.179 and turned a +0.155 R gross edge negative (Exp 012). `pct` makes `cost_r` regime-independent. The ATR clamp only stops a violent bar from making the stop absurd. |
| Structure (swing) stop | `"stop": {"type": "swing", "n": 12, "buffer_atr": 0.3, "min_atr": 1.5, "max_atr": 5}` | beyond the recent swing low/high, clamped |
| TP as R-multiple | `"tp": {"type": "r", "r": 2}` | TP = r × stop distance |
| TP as ATR multiple | `"tp": {"type": "atr", "mult": 4}` | |
| No TP (let it run) | `"tp": {"type": "none"}` + trailing | for trend ideas |
| Break-even | `"be_at": 1.0` | after +1R (on a bar close), stop → entry + costs |
| ATR trailing stop | `"trail_at": 1.5, "trail_atr": 2.5` | after +1.5R, trail 2.5 ATR behind the close |
| Time stop | `"max_hold_hours": 4` | cut trades that don't work; also keeps it intraday |
| Cooldown (no revenge trading) | `"cooldown_bars": 8` | |
| Confirmation entry | `"trigger_mode": "all", "confirm_bars": 3` | wait for a second trigger to agree |
| Better entry price | `"execution": {"entry_mode": "post_only", "entry_offset_atr": 0.2}` | limit order below/above the close. Fills less often and tends to fill on the trades that go against you (adverse selection) |

Good exit comparisons to run (each is one idea with a small grid):
1. `TP 1.5R` vs `TP 3R` vs `no TP + trail`, same entry.
2. Break-even at 0.5R / 1R / never. BE often **hurts**, because it turns
   winners into scratches. Measure it; don't assume.
3. Time stop 2h / 4h / 8h. The original brief was intraday (≤ 4h); longer
   holds must be labelled "swing".
4. ATR stop vs swing stop at similar average width.

### 🛠 Level 3 (engine change, ask the owner, test first)

| technique | how it must work to be allowed |
|---|---|
| Partial take-profit (scale out) | e.g. close 50% at 1R, trail the rest. Total risk never exceeds the original 1% |
| Scale-in on winners (pyramiding into profit) | add only after +1R, with the stop of the **whole** position moved so total open risk ≤ 1% |
| Stop-and-reverse | on stop-out, open the opposite side if the reverse signal is valid; a new 1% risk trade |
| Re-entry after stop-out | re-enter the same direction if the setup is still valid within N bars; a new 1% risk trade, counted as a trade |
| Early-failure exit | exit if not at +x R after N bars |
| Planned ladder entry | split **one** planned 1% risk into 2–3 limit entries decided at signal time, one shared stop. Total risk fixed in advance |

### ⛔ Forbidden

| technique | why |
|---|---|
| Martingale (double size after a loss) | risk of ruin → 100%; breaks the 1% rule |
| Unlimited averaging down / "DCA until it comes back" | unbounded risk; one trend wipes the account |
| Moving the stop further away when price approaches it | same as having no stop |
| Hedging long + short at once | meaningless in one-way mode; pays costs twice |
| Grid with no stop | same as unlimited averaging down |

---

## 5. Ways to combine techniques

1. **Stack filters** (AND): trigger + trend filter + regime filter + time
   filter. Every filter needs a reason and cuts trades. Stop adding once
   validation trades approach 100.
2. **Confirmation**: `trigger_mode: "all"` means two different triggers must
   agree within `confirm_bars` (e.g. `bb_revert` + `rsi_revert`).
3. **Ensemble**: `trigger_mode: "any"` fires on any of several related
   triggers (e.g. three breakout definitions). More trades, smaller CI.
4. **Regime switch**: one idea for trending regimes (`adx_min`) and one for
   ranging (`adx_max`), evaluated separately. Running both at once needs
   more than one position: 🛠.
5. **Multi-timeframe**: signal on 15m, filter with `htf_trend` (1h/4h proxy).
6. **Flow + price**: price trigger confirmed by `taker_flow` or
   `volume_spike`.
7. **Crowding**: `funding_extreme` trigger, or `funding_not_crowded` filter
   on any trend idea.
8. **ML filter** (advanced, existing `src/run_ml.py`): a model chooses which
   signals to take. It helped trade selection in Exp 006 but not enough to
   beat costs. Only revisit with a new idea.

---

## 6. Idea backlog (start here)

Priority ★★★ = most promising given past results. Suggested timeframe in
brackets. Write each as `ideas/NNN_name.json`.

| # | ★ | idea | recipe hint |
|---|---|---|---|
| 1 | ★★★ | Trend breakout, wide stop, trail winners [15m] | `donchian_break` + `htf_trend` + `adx_min`; stop atr 3–5; tp none; trail |
| 2 | ★★★ | Exit study on idea 1: TP vs trail vs BE | same entry; grid `tp.r`, `be_at`, `trail_atr` |
| 3 | ★★★ | Range mean reversion only when ADX low [15m] | `bb_revert` + `rsi_revert` (all) + `adx_max`; swing stop; tp 1–2R |
| 4 | ★★★ | Crowded funding fade with price stretch [15m/30m] | `funding_extreme` + `zscore_revert` (all, confirm 8) |
| 5 | ★★ | Session open breakout (London 07–09, NY 13–15 UTC) [5m/15m] | `range_break` with `hours`, + `volume_spike` |
| 6 | ★★ | Squeeze → expansion [15m] | `momentum` or `donchian_break` + `squeeze` + `vol_regime lo>1` |
| 7 | ★★ | Trend pullback with flow confirmation [15m] | `pullback` + `trend_ema` + `taker_flow` |
| 8 | ★★ | VWAP reversion in quiet markets [5m/15m] | `vwap_revert` + `vol_regime hi<1` + `adx_max` |
| 9 | ★★ | Impulse continuation with participation [15m] | `momentum` + `volume_spike` + `di_side` |
| 10 | ★★ | Weekday-only trend following [30m] | `ema_cross` + `weekdays [0..4]` + `adx_min` |
| 11 | ★★ | Post-only version of the best WATCH idea | same idea + `execution.entry_mode = post_only`, grid `exec.entry_offset_atr` [0, 0.15, 0.3] |
| 12 | ★★ | Supertrend flip filtered by HTF + no-crowding [30m] | `supertrend_flip` + `htf_trend` + `funding_not_crowded` |
| 13 | ★ | Long-only trend (BTC drift) vs short-only | any trend idea with `direction` long / short |
| 14 | ★ | Ensemble breakout (any of 3 definitions) | `donchian_break` + `range_break` + `momentum`, mode any |
| 15 | ★ | Previous-day high/low break | 🧩 new trigger |
| 16 | ★ | Opening range breakout 00:00 UTC | 🧩 new trigger |
| 17 | ★ | Liquidation-cascade fade | 🧩 new trigger |
| 18 | ★ | Keltner channel trend | 🧩 new trigger |
| 19 | ★ | Partial TP 50% at 1R + trail rest | 🛠 engine |
| 20 | ★ | Stop-and-reverse on breakout failure | 🛠 engine |

---

## 7. Already tried: don't repeat (BTCUSDT)

> **Exp 015 changed this section.** Until Exp 015 the engine booked every short
> trade's P&L with the wrong sign, and the 100 USDT account skipped many trades.
> Anything below that describes a *result* from before Exp 015 is unreliable
> where shorts were involved; the *cost* lessons still hold. Corrected results
> for all 18 ideas: `journal/BTCUSDT/experiments.md` Exp 015.

**Random-entry baseline (Exp 017):** the Round 1 long entries (Donchian
breakout, pullback, session-open break, at 30m/1h) are **DRIFT**: random
entries inside the same trend filters do as well. A long-only result on
2023–24 must always be checked with `src/baseline.py` before it's believed.

**After the fix (Exp 015, reliable):**
- **Short-only breakout / trend ideas lose significantly** (ideas 008–012,
  014, 015; 6 of 7 have the whole CI below zero). Don't try more of them.
  Shorts belong in both-direction ideas or in fades of failed moves.
- Mean reversion long (016), range reversion both sides (example) and
  squeeze → expansion (004, 013): negative on VALID.
- Leads, not passing: session-open range break both sides (005: train
  +0.079, valid +0.067 on 390 trades); long-only 30m EMA cross (006: +0.136 on
  52 trades); 007's direction grid picks long.

**After Round 1 (Exp 016, 40 evaluations, 0 PASS / 5 WATCH):**

- **The edge is not intraday. It is 30 minutes and above.** Every long
  structure tested is negative at 1m/3m/5m and positive at 30m/1h/4h, on TRAIN
  as well as on VALID, and for two different entries. The mechanism is
  measured, not guessed: chart-mode `tf_variants` scales the `pct` stop by
  sqrt(tf/15), so `cost_r` is **0.505 R on 1m and 0.019 R on 4h** for the same
  0.09% post-only round trip. A 1m/3m/5m REJECT in this project is almost
  always that arithmetic, not a verdict on the hypothesis.
- **Best configuration: 018 at 30m** - `donchian_break(24)` + `htf_trend(50,4)`
  + `adx_min(20)`, long only, `pct` stop 2.83%, no TP, ATR trail 1.5R/2.5,
  24h hold, post-only. valid 234 trades, gross +0.145, cost 0.043, mean R
  **+0.1024**, CI [-0.031, +0.243], CAGR +11.5%, maxDD 9.8%. Misses the PASS
  gate by 0.0001 (needs > 0.1025). WATCH.
- **Fading a failed breakdown does not pay** (`failed_break`, idea 020, all 7
  timeframes REJECT, `gross_r` negative everywhere). Idea 010's breakdowns do
  fail, but by the time a close back inside confirms it, the move is over.
- **Loosening 005's entry destroys its edge.** 005's long leg grossed +0.309 R
  with a 8-hour range and a `volume_spike` filter; 017 dropped the filter and
  used a 4-hour range and its valid `gross_r` fell to -0.005. Keep the
  participation filter on session breaks.
- **Do not build a weekday or session-hour filter.** In 005's 390 trades, Mon
  was +0.425 (n=67) and Sun -0.426 (n=60); entry-hour means ranged +0.365 to
  +0.436 on 16-28 trades. Noise at those counts, and a filter halves the
  sample.
- `taker_flow` and `funding_not_crowded` remain inert as confirmation (012, 014).

**After Round 2 (Exp 017, the only PASS in 61 evaluations, and its holdout):**

- **A stop width changes the units of the measurement, not just the risk.** The
  same long Donchian entry at 30m scored `gross_r` +0.145 with a 2.83% stop and
  **+0.334 with a 1.0% stop** — the R unit is 2.8x smaller, so the same price
  move counts 2.8x more R, with no new information. That configuration passed
  every VALID gate (mean R +0.2276, CI [+0.002, +0.468]) and `baseline.py` said
  **SKILL**; its holdout returned **−0.0102 R** with `gross_r` collapsed to
  +0.098 against a cost of 0.108. **A tight stop magnifies a temporary gross
  number; it does not create an edge, and it raises `cost_r` at the same time.**
  Never compare `gross_r`, or a mean R, across different stop widths.
- **A CI lower bound of +0.0023 is not evidence.** It passed because the gate is
  a threshold. Read it as "indistinguishable from zero", which is what the
  holdout then confirmed. VALID per year was 2023 +0.3496 against 2024 +0.1355:
  a result carried by one year of two is a regime, not an edge.
- **`baseline.py` measures skill *within* the period it is given.** A drift
  that is stable across all of 2023-24 will read as SKILL, because every long
  entry in a bull market gets the same tailwind. SKILL is a necessary condition,
  not a sufficient one, and it cannot see a period effect.
- **Exit management cannot create information the entry does not contain.** Two
  exit studies on one frozen entry moved VALID from +0.102 to +0.228 and the
  holdout to −0.010. The grid redistributes outcomes; it does not add edge.
- **Six configurations of "long + trend filter" are now closed**: five DRIFT
  (018@30m, 018@1h, 019@30m, 019@1h, 017@1h) and one holdout FAILED (022@30m,
  whose holdout is spent). Do not open this family again.

**After Round 3 (Exp 020, 35 evaluations, 2 PASS, 20/20 NO_EDGE; 4h variants UNSIZABLE per Exp 021):**

- **No tested timing rule beats simply holding BTC after costs.** Every
  `benchmark.py` run in the project is NO_EDGE: no configuration has alpha, and
  none is RISK_EDGE. If you are comparing a rule to buy & hold, compare **Sharpe
  and alpha**, never CAGR — 1% risk sizing with a wide stop keeps beta at
  0.03-0.13 and caps CAGR by construction.
- **Two configurations have real positive expectancy and are still not
  strategies.** `trend_regime` long/flat on 1h (long while close > EMA(200),
  10% stop, 24-72h re-check): valid +0.1148, CI [+0.014, +0.220], `cost_r`
  **0.022**, maxDD 4.8% — and Sharpe 1.59 against buy & hold's 2.01.
  `pullback` + `trend_ema` on 30m held 2-4 days: valid +0.1967, CI
  [+0.025, +0.373], `cost_r` 0.036 — and DRIFT, because its TRAIN mean R
  (+0.0712) is below random entries at any time (+0.0792).
- **`cost_r` is what produced every positive expectancy in this project**, and
  only two configurations ever got it small: a 10% stop (0.022 R) and a 4% stop
  at a 2-4 day hold (0.036 R). Both were reached by making the stop *wide* and
  the hold *long*, never by a better signal.
- **Filters on a regime rule make it worse.** Adding `adx_min` or a
  `vol_regime` ceiling to the plain EMA regime cut 1h VALID from +0.115 to
  +0.037 and +0.047. Both filters are meant to remove the whipsaw; both just
  miss the early part of every real trend.
- **Shorting the down-regime does not pay.** `direction: both` on the same
  regime rule is worse at every shared timeframe and negative on VALID at 15m
  and 4h. Re-confirmed on a correct engine, and it is a regime rule this time,
  not a breakout.
- **`SKILL` is near-vacuous for a regime rule**: when the trigger *is* the
  filter, `baseline.py`'s mode A and mode B come out identical and the control
  cannot discriminate. For `trend_state` ideas the benchmark is the real test.
- **A regime rule's `max_hold_hours` is a re-check interval, not a holding
  period** - the engine has no "exit when the regime ends", so each interval
  boundary pays a real round trip when the rule re-enters. `cost_r` per re-entry
  is 0.009 R at a 10% stop, which is why the interval is cheap enough to ignore
  and why `cost_r` 0.022 is achievable at all.

**After Round 4 (Exp 022, 35 evaluations, 1 PASS, 33 REJECT, 20/20 NO_EDGE):**

- **A positive `gross_r` is not an edge.** The 00:00 UTC opening-range break has a
  positive `gross_r` at **all seven timeframes** (+0.019 to +0.141) and is
  negative on net at six of them, because `cost_r` is above 0.5 R on 1m. The
  same idea is **-0.486 R at 1m and +0.113 R at 4h** with no change in the
  signal. Read `gross_r` as "a small predictable move exists", never as "the
  entry is timed well" - the random-entry control is what separates the two.
- **Yesterday's extremes, funding windows and Keltner breaks add nothing that a
  random entry does not also have.** 028 grossed +0.02..+0.07, 030 +0.02..+0.06,
  032 +0.091 at 1h and was DRIFT. A Keltner band (volatility-scaled) does not
  beat a Donchian band (price-lagged) by enough to matter.
- **Liquidation cascades have no exploitable side on gross.** `flush` at 2× ATR
  range and 1.5× volume was negative in **both** `follow` and `fade` modes at
  30m and 4h. That closes the family on gross, not on net, and it means the
  `mode` parameter is not a knob to re-tune.
- **A positive alpha CI on one period is a period, not an edge.** 032's TRAIN
  alpha was +13.3% with CI [+0.9, +26.4] - the only alpha CI in 131 evaluations
  that excludes zero - and its VALID alpha was -0.7%. Same shape as 022's
  2023/2024 split. **Check per-year before believing any alpha.**
- **The 00:00 UTC opening range is the only structure that reached PASS on more
  than one timeframe's worth of trades, and it still failed the control on
  TRAIN** (its +0.0313 sat below the 95th percentile of random entries at any
  time, +0.0719). Its benchmark: alpha -1.7% TRAIN, -0.9% VALID.

**Before the fix (Exp 003–014, history; results unreliable where shorts were involved):**

- Single-indicator strategies (EMA, Donchian, BB, VWAP, Supertrend, ADX,
  flow, funding) with **1.5–2x ATR stops** on 3m–30m: all negative after
  costs.
- Tight stops in general: cost_r 0.15–0.25 R ate the edge.
- ML filter over 12 strategies (Exp 006/007/010): better selection, still no
  CI above zero.
- Post-only entries (Exp 008/010): +0.01 to +0.10 R improvement, not enough
  alone.
- Holds of 1–4h with the Exp 009 candidate pool: negative. Positive traces
  needed 6–18h holds.
- `combo_funding_reversion`: positive out-of-sample but regime-dependent
  (few signals in quiet years). Worth retesting with the new gate (idea 4).
- Break-even/trailing results **before Exp 011** were distorted by an
  engine bug. Retest exit techniques with the fixed engine.
- Squeeze → expansion (Exp 012, ideas 004/013): the squeeze entry shows a huge `gross_r` (+0.269) that is
  **not** a large edge — it is a narrow ATR stop in a low-volatility window
  inflating R while 71% of trades are stopped out. Widen the stop and `gross_r`
  collapses to +0.129. Compare net R across ideas, never gross R.
- `taker_flow` as a filter looked inert on idea 012 (measured before the fix;
  worth one fresh test in a long or both-sided idea).
- `funding_extreme` as a trigger: 23 train trades (idea 003). It is a crossing
  on 8h data, so it almost never fires on 15m bars. Use `funding_not_crowded`
  as a filter on a price trigger instead.

## TradingView ports (PLAN.md §13; only from Pine source the owner supplies)

- ChartArt RSI + Bollinger (T1): the existing `rsi_revert` + `bb_revert`, with
  `trigger_mode: all`.
- `smc_structure(structure, event, swing_len, internal_len)` (T2): LuxAlgo
  Smart Money Concepts market structure. BOS/CHoCH follow the script's alert
  conditions. CC BY-NC-SA 4.0: attribution LuxAlgo, non-commercial use only.
- `chartart_macd_sma(fast, slow, signal, veryslow)` (T3): ChartArt's MACD + SMA 200 strategy (SMA-based MACD).
- `super_scalper(atr_len, mult, rsi_fast, rsi_slow)` (T4): a big bar (body > WMA-ATR band) in the direction of RSI 25 vs RSI 100.
