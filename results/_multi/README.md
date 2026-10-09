# results/_multi: one folder per research round

Folders are named `s<round>_<script>_<timeframe>` (owner request 2026-10-08, `_multi` Exp 056).
`<round>` is the section of `docs/research/PLAN.md`. The timeframe is omitted when a round tested several
(§28–§30 hold `tf60` = 1h, `tf240` = 4h, `tf1440` = 1d inside the file names). Every round writes its
generated report to `journal/_multi/<same name>.md`. Journal entries before Exp 056 use the old names
in the "old folder" column.

| round | folder | old folder | script | what it tested | Exp (plan → result → review) | verdict |
|---|---|---|---|---|---|---|
| §17 | `s17_rotation_1d` | `rotation` | `rotation.py` | weekly cross-sectional momentum, spot and perp (not ML) | 001 → 002 → 003 | REJECT |
| §20 | `s20_ml_pool_1h` | `ml_pool` | `ml_pool.py` | one entry model fitted on 20 coins together | 004 → 005 → 006 | REJECT |
| §21 | `s21_ml_pool2_1h` | `ml_pool2` | `ml_pool2.py` | round 2: 4-day hold decided every 4h, cross-coin features | 007 → 008 → 009 | REJECT |
| §26 | `s26_premium_confirm` | `premium_confirm` | `premium_confirm.py` | Coinbase premium on 10 unseen coins (not ML) | 010 → 011 → 012 | NOT_CONFIRMED |
| §27 | `s27_ml_hold_1h` | `ml_hold` | `ml_hold.py` | ML decides entry AND exit, no time limit | 015 → 016 → 017 | REJECT |
| §28 | `s28_ml_wf` | `ml_wf` | `ml_wf.py` | walk-forward (monthly refit), 47 coins, 1h/4h/1d | 019/021 → 022 → 023 | REJECT ×3 |
| §29 | `s29_ml_wf2` | `ml_wf2` | `ml_wf2.py` | + spot history from 2017 (only 4 coins qualified) | 024 → 025 → 026 | REJECT ×3 |
| §30 | `s30_ml_wf3` | `ml_wf3` | `ml_wf3.py` | §28's 47 coins, each with its own spot history | 027/029 → 030 → 031 | REJECT ×3 (1h closest) |
| §31 | `s31_ml_port_1h` | `ml_port` | `ml_port.py` | §30 1h as one account: 4h agreement, confidence sizing, 5% cap | 032 → 033 → 034 | REJECT by 0.00026 (best book) |
| §32 | `s32_ml_xs_1h` | `ml_xs` | `ml_xs.py` | market-wide part removed (demeaned) | 035 → 036 → 037 | REJECT (TRAIN chose raw = §31) |
| §33 | `s33_ml_mkt_1h` | `ml_mkt` | `ml_mkt.py` | the 47-coin mean forecast traded on BTC/ETH | 038 → 039 → 040 | REJECT |
| §34 | `s34_ml_flow_1h` | `ml_flow` | `ml_flow.py` | + positioning data (OI, long/short, funding) | 041 → 042 → 043 | REJECT (TRAIN chose base = §31) |
| §35 | `s35_listing_1d` | `listing` | `listing.py` | short every newly listed perp (not ML) | 044 → 045 → 046 | REJECT |
| §36 | `s36_ml_wide_1h` | `ml_wide` | `ml_wide.py` | train on 425 coins, trade the monthly top 20 | 047/048 → 050 → 051 | REJECT (CI, DD 20.01%) |
| §37 | `s37_ml_large_4h` | `ml_large` | `ml_large.py` | 4h model for the owner's ten large coins | 053 → 054 → 055 | REJECT (CI, timing, short leg) |
| §38 | `s38_ml_recent` (`1h/`, `4h/`, `1d/`) | - | `ml_recent.py` | §37 with recency-weighted training + both-years TRAIN rule, three sub-models | 060 → 061 → 062 | REJECT ×3 (4h best) |
| §39 | `s39_ml_rank_4h` | - | `ml_rank.py` | §38 4h with the side taken from the forecast against its own 30/90-day median | 063 → pending | pending |

Not rounds: `analyzer/` (`analyzer.py`, quality score of every ML run) and `meta_lessons/` (`meta_lessons.py`).

Per coin (`results/<SYMBOL>/`, journals in `journal/<SYMBOL>/`): `s16_allocation_1d` (was `allocation`),
`s18_exit_lab` (`exit_lab`), `s19_ml_entry_1h` (`ml_entry`), `s23_stop_diag` (`stop_diag`),
`s24_level_limit` (`level_limit`). `evaluations.csv`, `holdout_log.csv`, `eval_trades/`, `baseline/`,
`benchmark/` and `legacy/` are shared by every idea and keep their names.

No round has used its holdout: no `holdout*.json` exists under `results/` (checked 2026-10-08).
