# Idea files

One JSON file = one hypothesis = one run of `src/evaluate.py`.
Idea files are shared by all coins (`SYMBOL=ETHUSDT python src/evaluate.py ideas/x.json`).

Name: `NNN_short_name.json` (next free number; `example_*` are examples).
Improved versions: `NNN_short_name_v2.json` (max 3 versions). Never edit a file
after it was evaluated.

## Format

```json
{
  "name": "012_trend_breakout",
  "hypothesis": "WHY this should make money, 1-3 sentences, written before running.",
  "strategy": "recipe",
  "tf": 15,
  "params": {
    "triggers": [{"type": "donchian_break", "n": 48}],
    "trigger_mode": "any",
    "confirm_bars": 3,
    "filters": [{"type": "htf_trend", "n": 50, "mult": 4},
                {"type": "adx_min", "min": 20}],
    "direction": "both",
    "stop": {"type": "atr", "mult": 3.0},
    "tp": {"type": "r", "r": 2.0},
    "be_at": 0,
    "trail_at": 1.5,
    "trail_atr": 2.5,
    "max_hold_hours": 8,
    "cooldown_bars": 4,
    "atr_n": 14
  },
  "grid": {
    "stop.mult": [2.5, 4.0],
    "tp.r": [2.0, 3.0],
    "filters.1.min": [20, 25]
  },
  "execution": {"entry_mode": "taker"}
}
```

| field | required | meaning |
|---|---|---|
| `name` | yes | same as the file name without `.json` |
| `hypothesis` | yes | why it should work |
| `strategy` | no (default `recipe`) | `recipe`, or a name from `strategies.REGISTRY` (see `evaluate.py --list`) |
| `tf` | yes | bar minutes: 1, 3, 5, 15, 30, 60, 240. Write the idea at one of them, then make the others with `python src/tf_variants.py ideas/<file>.json` |
| `params` | yes | recipe fields below, or the strategy's keyword arguments |
| `grid` | no | parameters to choose on TRAIN; ≤ 64 combinations, keep ≤ 4 keys |
| `execution` | no | `entry_mode` (`taker` / `post_only`), `entry_offset_atr`, `entry_fill_ratio` |

### Recipe fields (`params` when `strategy` = `recipe`)

| field | default | values |
|---|---|---|
| `triggers` | required | list of `{"type": ..., params}`, see `docs/research/TECHNIQUES.md` §2 |
| `trigger_mode` | `any` | `any` = any trigger fires; `all` = all fire in the same direction within `confirm_bars` |
| `confirm_bars` | 3 | window for `all` |
| `filters` | [] | list of `{"type": ..., params}`, ALL must allow the direction (§3) |
| `direction` | `both` | `both`, `long`, `short` |
| `stop` | atr 2.0 | `{"type":"atr","mult":x}` or `{"type":"swing","n":12,"buffer_atr":0.3,"min_atr":1.5,"max_atr":5}` |
| `tp` | none | `{"type":"none"}`, `{"type":"r","r":x}`, `{"type":"atr","mult":x}` |
| `be_at` | 0 (off) | move stop to break-even after +x R (on a bar close) |
| `trail_at`, `trail_atr` | 0 (off) | after +`trail_at` R, trail `trail_atr` × ATR behind the close |
| `max_hold_hours` | 4 | time stop |
| `cooldown_bars` | 0 | ignore new signals for N bars after one |
| `atr_n` | 14 | ATR period for stops/TP/trail |

### Grid keys

Dotted paths into `params`: `"stop.mult"`, `"tp.r"`, `"filters.0.min"`
(first filter's `min`), `"triggers.1.n"`, `"be_at"`. Keys starting with
`exec.` go to `execution`, e.g. `"exec.entry_offset_atr": [0, 0.2]`.

## Run

```bash
python src/evaluate.py ideas/012_trend_breakout.json          # TRAIN select -> VALID verdict
python src/evaluate.py ideas/012_trend_breakout.json --final  # only after PASS, one time
```
