#!/usr/bin/env python3
"""
WatchAgent data analysis skill — query readings/events and return structured JSON.

Usage:
  python analyze_data.py --question "How many events per city?"
  python analyze_data.py --question "temperature trend" --hours 48 --city Toronto
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CITIES = ("Ottawa", "Toronto", "Vancouver")
DEFAULT_DB = Path("data") / "watchagent.db"


def parse_iso(ts: str) -> datetime:
    """Parse ISO timestamps from Open-Meteo / SQLite."""
    ts = ts.replace("Z", "+00:00")
    if "+" not in ts and len(ts) == 16:  # 2024-01-01T12:00
        ts += "+00:00"
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def count_rows(conn: sqlite3.Connection, table: str, city: str | None, since: datetime | None) -> int:
    clauses: list[str] = []
    params: list[Any] = []
    if city:
        clauses.append("city = ?")
        params.append(city)
    time_col = "recorded_at" if table == "readings" else "occurred_at"
    if since:
        clauses.append(f"{time_col} >= ?")
        params.append(since.isoformat())
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return conn.execute(f"SELECT COUNT(*) FROM {table}{where}", params).fetchone()[0]


def readings_per_city(conn: sqlite3.Connection, since: datetime | None) -> dict[str, int]:
    clauses, params = [], []
    if since:
        clauses.append("recorded_at >= ?")
        params.append(since.isoformat())
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT city, COUNT(*) AS n FROM readings{where} GROUP BY city ORDER BY city",
        params,
    ).fetchall()
    return {r["city"]: r["n"] for r in rows}


def events_by_type(conn: sqlite3.Connection, since: datetime | None, city: str | None) -> dict[str, int]:
    clauses, params = [], []
    if since:
        clauses.append("occurred_at >= ?")
        params.append(since.isoformat())
    if city:
        clauses.append("city = ?")
        params.append(city)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT event_type, COUNT(*) AS n FROM events{where} GROUP BY event_type ORDER BY n DESC",
        params,
    ).fetchall()
    return {r["event_type"]: r["n"] for r in rows}


def latest_readings(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for city in CITIES:
        row = conn.execute(
            """
            SELECT city, recorded_at, temperature_2m, apparent_temperature,
                   precipitation, wind_speed_10m, weather_code
            FROM readings
            WHERE city = ?
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            (city,),
        ).fetchone()
        if row:
            out.append(dict(row))
    return out


def temperature_stats(
    conn: sqlite3.Connection, since: datetime, city: str | None
) -> dict[str, Any]:
    clauses = ["recorded_at >= ?"]
    params: list[Any] = [since.isoformat()]
    if city:
        clauses.append("city = ?")
        params.append(city)
    where = " AND ".join(clauses)
    rows = conn.execute(
        f"""
        SELECT city,
               MIN(temperature_2m) AS t_min,
               MAX(temperature_2m) AS t_max,
               AVG(temperature_2m) AS t_avg,
               COUNT(*) AS n
        FROM readings
        WHERE {where}
        GROUP BY city
        ORDER BY city
        """,
        params,
    ).fetchall()
    return {r["city"]: dict(r) for r in rows}


def cross_city_spread(latest: list[dict[str, Any]]) -> dict[str, Any] | None:
    temps = [(r["city"], r["temperature_2m"]) for r in latest if r.get("temperature_2m") is not None]
    if len(temps) < 2:
        return None
    values = [t[1] for t in temps]
    return {
        "by_city": dict(temps),
        "max_city": max(temps, key=lambda x: x[1])[0],
        "min_city": min(temps, key=lambda x: x[1])[0],
        "spread_c": round(max(values) - min(values), 2),
    }


def dedup_check(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT city, recorded_at, COUNT(*) AS n
        FROM readings
        GROUP BY city, recorded_at
        HAVING n > 1
        ORDER BY n DESC
        LIMIT 10
        """
    ).fetchall()
    return [dict(r) for r in rows]


def classify_question(question: str) -> list[str]:
    q = question.lower()
    modes: list[str] = []
    if any(w in q for w in ("event", "notable", "detection", "fire", "alarm")):
        modes.append("events")
    if any(w in q for w in ("reading", "temperature", "wind", "precip", "weather", "trend", "latest")):
        modes.append("readings")
    if any(w in q for w in ("compare", "cross", "spread", "gap", "between cities")):
        modes.append("cross_city")
    if any(w in q for w in ("dedup", "duplicate", "timestamp")):
        modes.append("dedup")
    if any(w in q for w in ("count", "how many", "total", "summary", "overview")):
        modes.append("counts")
    if not modes:
        modes = ["counts", "readings", "events"]
    return modes


def build_response(
    question: str,
    db_path: Path,
    hours: int,
    city: str | None,
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    modes = classify_question(question)

    readings_total = count_rows(conn, "readings", city, None)
    events_total = count_rows(conn, "events", city, None)
    readings_window = count_rows(conn, "readings", city, since)
    events_window = count_rows(conn, "events", city, since)

    findings: list[str] = []
    data: dict[str, Any] = {
        "window_hours": hours,
        "window_since_utc": since.isoformat(),
        "totals": {
            "readings": readings_total,
            "events": events_total,
            "readings_in_window": readings_window,
            "events_in_window": events_window,
        },
    }

    if "counts" in modes or "readings" in modes:
        per_city = readings_per_city(conn, since)
        data["readings_per_city_in_window"] = per_city
        for c in CITIES:
            n = per_city.get(c, 0)
            findings.append(f"{c}: {n} reading(s) in the last {hours}h")

    if "readings" in modes:
        data["temperature_stats_in_window"] = temperature_stats(conn, since, city)
        latest = latest_readings(conn)
        data["latest_reading_per_city"] = latest
        spread = cross_city_spread(latest)
        if spread:
            data["cross_city_temperature"] = spread
            findings.append(
                f"Latest cross-city temperature spread: {spread['spread_c']}°C "
                f"({spread['min_city']} → {spread['max_city']})"
            )

    if "events" in modes:
        by_type = events_by_type(conn, since, city)
        data["events_by_type_in_window"] = by_type
        if by_type:
            top = max(by_type.items(), key=lambda x: x[1])
            findings.append(f"Most common event type in window: {top[0]} ({top[1]} times)")
        else:
            findings.append(f"No events in the last {hours}h" + (f" for {city}" if city else ""))

    if "dedup" in modes or "dedup" in question.lower():
        dupes = dedup_check(conn)
        data["duplicate_reading_keys"] = dupes
        if dupes:
            findings.append(f"WARNING: {len(dupes)} duplicate (city, recorded_at) keys found")
        else:
            findings.append("No duplicate (city, recorded_at) pairs detected")

    if readings_total == 0:
        summary = "Database has no readings yet; start the poller or wait for hourly Open-Meteo updates."
    elif not findings:
        summary = f"Analyzed {readings_total} readings and {events_total} events over the last {hours}h."
    else:
        summary = findings[0]

    return {
        "question": question,
        "db_path": str(db_path.resolve()),
        "status": "ok",
        "summary": summary,
        "findings": findings,
        "data": data,
        "analysis_modes": modes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="WatchAgent stored-data analysis")
    parser.add_argument("--question", "-q", required=True, help="Natural-language question about stored data")
    parser.add_argument("--db", type=Path, default=None, help="SQLite database path")
    parser.add_argument("--hours", type=int, default=24, help="Lookback window in hours")
    parser.add_argument("--city", choices=CITIES, default=None, help="Optional city filter")
    args = parser.parse_args()

    db_path = args.db or Path(os.environ.get("WATCHAGENT_DB_PATH", DEFAULT_DB))

    if not db_path.exists():
        out = {
            "question": args.question,
            "db_path": str(db_path.resolve()),
            "status": "error",
            "summary": f"Database not found at {db_path}",
            "findings": [
                "Set WATCHAGENT_DB_PATH or pass --db to your SQLite file.",
                "Run docker compose up and wait for the poller, or align app schema with reference.md.",
            ],
            "data": {},
        }
        print(json.dumps(out, indent=2))
        return 1

    try:
        conn = connect(db_path)
    except sqlite3.Error as exc:
        print(json.dumps({"status": "error", "summary": str(exc)}, indent=2))
        return 1

    if not table_exists(conn, "readings"):
        out = {
            "question": args.question,
            "db_path": str(db_path.resolve()),
            "status": "error",
            "summary": "Table 'readings' not found",
            "findings": ["Create schema per .cursor/skills/watchagent-data-analysis/reference.md"],
            "data": {},
        }
        print(json.dumps(out, indent=2))
        conn.close()
        return 1

    try:
        result = build_response(args.question, db_path, args.hours, args.city, conn)
    except sqlite3.Error as exc:
        result = {
            "question": args.question,
            "db_path": str(db_path.resolve()),
            "status": "error",
            "summary": f"Query failed: {exc}",
            "findings": [],
            "data": {},
        }
        print(json.dumps(result, indent=2))
        conn.close()
        return 1

    conn.close()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
