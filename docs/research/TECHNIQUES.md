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

## 7. Already tried: don't repeat (BTCUSDT, Exp 003–011)

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
- Squeeze → expansion and session-open breakouts (Exp 012, ideas 004/005/013):
  REJECT / negative. The squeeze entry shows a huge `gross_r` (+0.269) that is
  **not** a large edge — it is a narrow ATR stop in a low-volatility window
  inflating R while 71% of trades are stopped out. Widen the stop and `gross_r`
  collapses to +0.129. Compare net R across ideas, never gross R.
- `taker_flow` as a filter: inert at any threshold that still leaves ~100
  trades (idea 012) — the taker buy ratio does not deviate far enough from 0.5.
- `funding_extreme` as a trigger: 23 train trades (idea 003). It is a crossing
  on 8h data, so it almost never fires on 15m bars. Use `funding_not_crowded`
  as a filter on a price trigger instead.
