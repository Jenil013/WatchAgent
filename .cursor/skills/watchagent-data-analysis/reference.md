# WatchAgent SQLite schema (skill contract)

The data analysis script expects these tables. Application code should match this so the skill works without changes.

## `readings`

| Column | Type | Notes |
|--------|------|--------|
| `id` | INTEGER PK | Auto-increment |
| `city` | TEXT | `Ottawa`, `Toronto`, `Vancouver` |
| `recorded_at` | TEXT | ISO 8601 from Open-Meteo `current.time` |
| `temperature_2m` | REAL | °C |
| `apparent_temperature` | REAL | °C |
| `precipitation` | REAL | mm (preceding hour) |
| `wind_speed_10m` | REAL | km/h |
| `weather_code` | INTEGER | WMO code |

**Unique:** `(city, recorded_at)` — deduplication per challenge.

## `events`

| Column | Type | Notes |
|--------|------|--------|
| `id` | INTEGER PK | |
| `city` | TEXT | |
| `occurred_at` | TEXT | ISO, aligned with triggering reading |
| `event_type` | TEXT | Stable id, e.g. `temp_rapid_rise` |
| `summary` | TEXT | Short human line |
| `reason` | TEXT | Why notable |
| `details` | TEXT | JSON object with metrics |

## Environment

| Variable | Purpose |
|----------|---------|
| `WATCHAGENT_DB_PATH` | Overrides default `./data/watchagent.db` |

Docker Compose should mount a volume so this file survives restarts (e.g. `./data:/app/data`).
