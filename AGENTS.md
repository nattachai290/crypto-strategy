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
Exp 025/026). **One approved run is pending:** PLAN.md §30 (`src/ml_wf3.py`,
§28's 47 coins each with its own spot history, owner request 2026-10-03,
`_multi` Exp 027; the first attempt aborted on a spot pair delisted before VALID,
Exp 028; fixed and re-registered as Exp 029). Ask before starting anything else.
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
| `allocation.py` | PLAN.md §16: four fixed trend rules on daily spot/perp bars against buy-and-hold (1x exposure, next-open fills, fees, funding). Writes `results/<SYMBOL>/allocation/` and the generated `journal/<SYMBOL>/allocation.md`; runs once (`--rerun` only after a code fix) |
| `rotation.py` | PLAN.md §17: weekly cross-sectional momentum over every USDT pair (spot long-only vs the universe; perp long/short with funding). `--build spot|perp` downloads to `data/*/_multi/`. TRAIN chooses the lookback, VALID gives PASS/REJECT, `--final` runs the holdout once. Writes `results/_multi/rotation/` and the generated `journal/_multi/rotation.md` |
| `exit_lab.py` | PLAN.md §18: six fixed exits on random entries (p 0.25, seed 18), each trade simulated on its own with the engine's exact rules (test 14). TRAIN chooses the exit, VALID gives PASS/REJECT, `--final` runs the holdout once. Writes `results/<SYMBOL>/exit_lab/` and the generated `journal/<SYMBOL>/exit_lab.md` |
| `ml_entry.py` | PLAN.md §19: LightGBM long/short models predict the net R of a fixed symmetric exit; the threshold comes from purged TRAIN walk-forward OOF; VALID gates include beating random signals with the same long/short counts; `--final` runs the holdout once. Writes `results/<SYMBOL>/ml_entry/` and the generated `journal/<SYMBOL>/ml_entry.md` |
| `ml_pool.py` | PLAN.md §20: the §19 model fitted once on 20 coins together (universe chosen on TRAIN volume, survivorship-free). `--build` downloads 1h perp klines + funding to `data/*/_multi/pool_1h`; gates add breadth (half the coins beat their own control). Writes `results/_multi/ml_pool/` and the generated `journal/_multi/ml_pool.md` |
| `ml_pool2.py` | PLAN.md §21: round 2 of the pooled model on the same 20 coins: 4-day hold decided every 4 h, cross-coin/BTC features, LightGBM settings tuned on TRAIN OOF, control on GROSS R, both legs must be net positive. Writes `results/_multi/ml_pool2/` and the generated `journal/_multi/ml_pool2.md` |
| `ml_hold.py` | PLAN.md §27: one pooled LightGBM forecast (next 24 h in ATRs) every 4 h on the same 20 coins; a hysteresis policy decides entry AND exit, no time limit (8-ATR protective stop only); TRAIN OOF picks setting, entry quantile and exit mode; control = 200 time-shifts of the desired-position path, timing before costs; simulator matches the engine (test 23). Writes `results/_multi/ml_hold/` and the generated `journal/_multi/ml_hold.md` |
| `ml_wf.py` | PLAN.md §28: §27's model and policy refit every month (walk-forward) on 50 coins, traded on 1h, 4h or 1d with the other two timeframes' closed-bar features as inputs (multi-timeframe); `--build` downloads native 1h/4h/1d klines + funding to `data/cache/_multi/pool_<tf>`; TRAIN walk-forward picks the cell, VALID judges each timeframe, ONE timeframe may take the holdout. Writes `results/_multi/ml_wf/` and the generated `journal/_multi/ml_wf.md` |
| `ml_wf2.py` | PLAN.md §29: §28 unchanged except that features and labels come from each coin's SPOT bars from 2017-08 (more market regimes in every refit); trades still simulated on PERP bars with perp costs and funding in §28's windows; universe = §28's rule restricted to spot listed by 2018-01-01; `--build` adds spot 1h/4h/1d to `data/cache/_multi/spot_<tf>`. Writes `results/_multi/ml_wf2/` and the generated `journal/_multi/ml_wf2.md` |
| `ml_wf3.py` | PLAN.md §30: §28's exact 47 coins; each coin's features and labels from its own spot bars from the pair's first month (perp bars if no earlier spot), trades on perp bars; otherwise §29/§28 unchanged. `--build` adds the missing spot caches. Writes `results/_multi/ml_wf3/` and the generated `journal/_multi/ml_wf3.md` |
| `stop_diag.py` | PLAN.md §23: from the VALID trade files, asks whether entries were on the wrong side or right and then stopped out, against random fills with the same side, stop fraction and hold. Read-only; writes `results/<SYMBOL>/stop_diag/` and the generated `journal/<SYMBOL>/stop_diag.md` |
| `level_limit.py` | PLAN.md §24: limit orders resting AT support/resistance (previous-day extremes or live swing pivots), maker entry, stop just beyond the level; each order simulated on its own; TRAIN picks 1 of 8 cells; gates include beating control orders at the same distance from price at random bars, on TRAIN and VALID. Writes `results/<SYMBOL>/level_limit/` and the generated `journal/<SYMBOL>/level_limit.md` |
| `premium_confirm.py` | PLAN.md §26: reads the recorded 057 results on the 10 confirmation coins (no backtest) and applies the pre-registered bars (30m: positive on ≥7, SKILL on ≥5; 4h: pooled ≥100 trades, mean > 0, weekly-block CI > 0, ≥7 coins positive). Writes `results/_multi/premium_confirm/` and the generated `journal/_multi/premium_confirm.md` |
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
