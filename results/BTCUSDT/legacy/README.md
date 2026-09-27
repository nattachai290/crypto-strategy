# BTCUSDT legacy results (Exp 003–010)

Output of the older experiment scripts, from before the `evaluate.py` workflow
(Exp 011). Kept as evidence for `journal/BTCUSDT/experiments.md`. **Don't add
new files here.** New research is recorded in `../evaluations.csv`.

Exp 010 found that experiments 003–009 ran on bars shifted one window into the
past, so most of these files are stale. Break-even/trailing variants are also
biased by the exit bugs fixed in Exp 011.

| File | Script | Exp | Data | Trust |
|---|---|---|---|---|
| `definitive_oos.csv` | `definitive.py` | 007 / 010 | fixed | ✅ headline before Exp 011 |
| `round3_maker.csv` | `round3_maker.py` | 008 / 010 | fixed | ✅ |
| `sweep_train.csv`, `sweep_test.csv`, `sweep_merged.csv` | `sweep.py` | 003 | shifted | ⚠️ stale |
| `cost_lab.csv` | `cost_lab.py` | 004 | shifted | ⚠️ stale (the stop-width mechanism still holds) |
| `round2_stopwidth_train.csv`, `_test.csv` | `round2_stopwidth.py` | 004b | shifted | ⚠️ stale |
| `ml_walkforward_15m.csv`, `_s2.0.csv` | `run_ml.py` | 006 | shifted | ⚠️ stale |
| `round4_holdperiod.csv` | `round4_holdperiod.py` | 009 | shifted | ⚠️ stale |
| `report_best.json` → `report.html` | `report_data.py`, `make_report.py` | 007 | shifted | ⚠️ report shows pre-fix numbers |
| `ledger.csv` (+ `journal/BTCUSDT/ledger.md`) | `ledger.py`, `ledger_report.py` | all | mixed | ⚠️ pre- and post-fix rows side by side |

`logs/` holds the console output of those runs, converted to UTF-8:
`definitive.log` and `round3_maker.log` are the post-fix (Exp 010) re-runs;
the others belong to the stale runs above.

Removed during the Exp 011 tidy-up (still in git history): download logs,
`show_bars` demo output, the pre-fix `definitive`/`round3` logs, `results.csv`
(early baseline) and `final_eval_15m_s2.0.csv` + `final15.log` (superseded by
`definitive_oos.csv`).
