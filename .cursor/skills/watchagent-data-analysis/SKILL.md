---
name: watchagent-data-analysis
description: Queries WatchAgent SQLite readings and events, runs trend and per-city analysis, and returns structured JSON. Use when the user asks about stored weather data, event counts, city comparisons, time windows, or whether detection is too noisy.
---

# WatchAgent data analysis

## Quick start

Run the analysis script from the repository root (stdlib only):

```bash
python .cursor/skills/watchagent-data-analysis/scripts/analyze_data.py --question "YOUR QUESTION"
```

Optional flags:

| Flag | Default | Purpose |
|------|---------|---------|
| `--db` | `WATCHAGENT_DB_PATH` or `./data/watchagent.db` | SQLite database path |
| `--hours` | `24` | Lookback window for time-based analyses |
| `--city` | (all) | Restrict to `Ottawa`, `Toronto`, or `Vancouver` |

Output is **JSON on stdout** with `status`, `summary`, `findings`, and `data`. Parse it and answer the user in prose; cite numbers from `findings`.

## When to use

- Questions about **collected** readings or events (not live Open-Meteo).
- Per-city stats, trends, cross-city gaps, event frequency, dedup sanity checks.
- Before tuning detection: "Are we firing too many `temp_*` events this week?"

## Database contract

The app should persist to SQLite with tables `readings` and `events`. Column details: [reference.md](reference.md).

If the DB is missing or empty, the script returns `status: error` with a clear message — report that and suggest `docker compose up` or waiting for polls.

## Workflow

1. Confirm the question is about **stored** data (not implementing new features).
2. Run `analyze_data.py` with the user's question verbatim in `--question`.
3. Add `--city` or `--hours` when the question implies them.
4. On `status: ok`, summarize `summary` and bullet key items from `findings`.
5. On `status: error`, explain the error and next step (path, migrations, poller).

## Example invocations

```bash
python .cursor/skills/watchagent-data-analysis/scripts/analyze_data.py \
  --question "How many readings per city in the last 48 hours?" --hours 48

python .cursor/skills/watchagent-data-analysis/scripts/analyze_data.py \
  --question "Latest temperature and cross-city spread" --city Ottawa

python .cursor/skills/watchagent-data-analysis/scripts/analyze_data.py \
  --question "Event counts by type in the last 7 days" --hours 168
```

## Do not

- Call the live Open-Meteo API from this skill.
- Guess numbers if the script failed — fix the DB path or stack first.
