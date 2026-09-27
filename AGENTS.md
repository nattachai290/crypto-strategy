# AGENTS.md — rules for any AI agent working in this repo

**Read this whole file before doing anything.** Then read
`docs/research/TECHNIQUES.md` (what to try) and `journal/<SYMBOL>/STATUS.md`
(where the coin stands). Today only `BTCUSDT` exists.

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

### Start-of-session checklist (run these, in order)

```bash
pip install -r requirements.txt
python src/test_engine.py        # must end with: ALL CHECKS PASSED
python src/datafeed.py           # first time ~3 min; must end with: VALIDATION: OK
python src/evaluate.py --list    # the building blocks you can combine
tail -n 60 journal/BTCUSDT/evaluations.md   # what was already tried
```

If any of these fails, **stop and fix that first** (see §9). Do not research
on a broken setup.

---

## 1. The research loop — how to find a technique

Repeat this loop. One loop = one idea = one hypothesis.

**Step 1 — Pick an idea.** Take one from the backlog in
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

**Step 4 — Keep the grid small.** At most 4 grid keys and at most 64
combinations (enforced). Sweep the things the hypothesis is actually about.
Fix everything else at a sensible value.

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

**Step 7 — Holdout (only after PASS):**
```bash
python src/evaluate.py ideas/NNN_short_name.json --final
```
This runs the frozen choice **one time** on HOLDOUT (2025-01 → 2026-08),
data nothing has been tuned on. `CONFIRMED` = a real candidate: tell the owner
right away. `FAILED` = it was luck: record it and move on. The script refuses
a second holdout run for the same config. **Never** work around that. Never
make a copy with a tiny change just to get another holdout try.

**Step 8 — Diagnose, don't guess.** Before a v2, look at the numbers in the
report: `gross_r` vs `cost_r`, exit mix (stop/tp/time %), avg hold,
long vs short, per-year R. Also look at the trades file
`results/<SYMBOL>/eval_trades/<eval_id>_valid.csv`. Typical diagnoses:
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
   Maximum 3 versions per idea; after that, move on.
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

## 4. Hard rules — ALWAYS

11. **Always** run `python src/test_engine.py` after changing anything in
    `src/` and before committing. It must print `ALL CHECKS PASSED`.
12. **Always** write the hypothesis before running.
13. **Always** keep a REJECT in the records. Negative results stop the next
    agent from repeating your work.
14. **Always** say how many ideas you tried when you report a PASS. Out of 50
    ideas, a couple can pass by luck; that is why the holdout exists.
15. **Always** commit your work at the end of a session (§10).

---

## 5. How much code you may change — levels

| Level | You may | Requirements |
|---|---|---|
| **1 — idea files** (default, do this most) | Write `ideas/*.json` using existing blocks and strategies | None beyond §1 |
| **2 — new building block** | Add a trigger or filter function to `src/recipes.py` (or a strategy to `src/strategies.py` + `REGISTRY`) | Docstring with a one-line description. Causal. `python src/test_engine.py` passes: test 7 automatically checks that every block is causal. Mention it in TECHNIQUES.md |
| **3 — engine change** | Change `src/backtest.py` (e.g. partial TP, scale-in, stop-and-reverse) | **Ask the owner first.** New behaviour must be off by default. Add a hand-computed test in `test_engine.py` that fails before your change and passes after. All old tests unchanged and passing. Journal entry explaining it |

`src/config.py` costs/gates, `src/evaluate.py` gates and the split dates are
not yours to change at any level.

---

## 6. One folder per coin

- Everything coin-specific lives under `<SYMBOL>/` (Binance symbol, upper
  case): `data/raw/<SYMBOL>/`, `data/cache/<SYMBOL>/`, `data/logs/<SYMBOL>/`,
  `results/<SYMBOL>/`, `journal/<SYMBOL>/`.
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
    ledger.md               GENERATED by ledger_report.py (older experiments)
results/<SYMBOL>/
    evaluations.csv         every evaluate.py run (one row each)
    holdout_log.csv         every holdout use (the lock)
    eval_trades/            trade lists per evaluation (git-ignored, regenerable)
    *.csv, report.html      output of older experiment scripts (Exp 003–010)
data/{raw,cache,logs}/<SYMBOL>/   zips, parquet (both git-ignored), run logs
```

| `src/` file | Role |
|---|---|
| `evaluate.py` | **the research gate**: idea file → TRAIN select → VALID verdict → optional one-time HOLDOUT |
| `recipes.py` | building blocks: `TRIGGERS`, `FILTERS`, and `recipe()` that combines them with exits |
| `strategies.py` | older hand-written strategies (`REGISTRY`), also usable in idea files |
| `backtest.py` | the engine (`run_backtest`): next-bar-open fills, taker/maker fees, slippage, funding, stop-first, BE/trailing, post-only entries |
| `indicators.py` | causal indicators (EMA, ATR, RSI, ADX, BB, VWAP, supertrend, …) |
| `config.py` | symbol specs, paths, costs, risk, split dates, gates |
| `experiment.py` | `get_bars(tf)`, `load_funding()`, older helpers |
| `datafeed.py` | download + cache + `validate()` |
| `test_engine.py` | engine and block tests; must pass |
| `ml_filter.py`, `run_ml.py`, `definitive.py`, `sweep.py`, `cost_lab.py`, `round*.py`, `diagnose.py` | older experiments (Exp 003–010), see journal |
| `ledger*.py`, `report_data.py`, `make_report.py` | reporting for the older experiments |

Engine facts to remember:
- R = stop distance. `gross_r - cost_r = mean R` per trade. At a 0.5%
  stop, costs alone are ≈ 0.28 R per trade. **Wide stops are cheap stops**
  (the main finding so far, Exp 004).
- One position at a time. Position size = 1% equity ÷ stop distance (max 10x
  leverage).
- Break-even and trailing stops move using the **previous** bar's close
  (fixed in Exp 011).

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
