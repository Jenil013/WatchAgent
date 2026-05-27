from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional


CITIES: tuple[str, ...] = ("Ottawa", "Toronto", "Vancouver")


def _default_db_path() -> Path:
    return Path("data") / "watchagent.db"


def get_db_path() -> Path:
    return Path(os.environ.get("WATCHAGENT_DB_PATH", str(_default_db_path())))


def ensure_parent_dir(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)


def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    ensure_parent_dir(path)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def db_session(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            temperature_2m REAL NOT NULL,
            apparent_temperature REAL NOT NULL,
            precipitation REAL NOT NULL,
            wind_speed_10m REAL NOT NULL,
            weather_code INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            UNIQUE(city, recorded_at)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            event_type TEXT NOT NULL,
            summary TEXT NOT NULL,
            reason TEXT NOT NULL,
            details TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_readings_city_time ON readings(city, recorded_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_city_time ON events(city, occurred_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)")


def parse_iso(ts: str) -> datetime:
    ts = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_iso(ts: str) -> str:
    # Persist UTC ISO strings; Open-Meteo usually returns local offset.
    return parse_iso(ts).isoformat()


@dataclass(frozen=True)
class Reading:
    city: str
    recorded_at: str
    temperature_2m: float
    apparent_temperature: float
    precipitation: float
    wind_speed_10m: float
    weather_code: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Event:
    city: str
    occurred_at: str
    event_type: str
    summary: str
    reason: str
    details: dict[str, Any]


def get_latest_reading_time(conn: sqlite3.Connection, city: str) -> Optional[str]:
    row = conn.execute(
        "SELECT recorded_at FROM readings WHERE city = ? ORDER BY recorded_at DESC LIMIT 1",
        (city,),
    ).fetchone()
    return row["recorded_at"] if row else None


def insert_reading_if_new(conn: sqlite3.Connection, reading: Reading) -> bool:
    # Dedup is enforced both by gate in poller and by UNIQUE constraint here.
    try:
        conn.execute(
            """
            INSERT INTO readings (
              city, recorded_at, temperature_2m, apparent_temperature,
              precipitation, wind_speed_10m, weather_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reading.city,
                reading.recorded_at,
                reading.temperature_2m,
                reading.apparent_temperature,
                reading.precipitation,
                reading.wind_speed_10m,
                int(reading.weather_code),
            ),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def insert_events(conn: sqlite3.Connection, events: Iterable[Event]) -> int:
    rows = [
        (
            e.city,
            e.occurred_at,
            e.event_type,
            e.summary,
            e.reason,
            __import__("json").dumps(e.details, separators=(",", ":"), sort_keys=True),
        )
        for e in events
    ]
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT INTO events (city, occurred_at, event_type, summary, reason, details)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def list_readings(conn: sqlite3.Connection, city: Optional[str], limit: int) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    if city:
        rows = conn.execute(
            """
            SELECT id, city, recorded_at, temperature_2m, apparent_temperature,
                   precipitation, wind_speed_10m, weather_code
            FROM readings
            WHERE city = ?
            ORDER BY recorded_at DESC
            LIMIT ?
            """,
            (city, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, city, recorded_at, temperature_2m, apparent_temperature,
                   precipitation, wind_speed_10m, weather_code
            FROM readings
            ORDER BY recorded_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_events(conn: sqlite3.Connection, city: Optional[str], limit: int) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    if city:
        rows = conn.execute(
            """
            SELECT id, city, occurred_at, event_type, summary, reason, details
            FROM events
            WHERE city = ?
            ORDER BY occurred_at DESC, id DESC
            LIMIT ?
            """,
            (city, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, city, occurred_at, event_type, summary, reason, details
            FROM events
            ORDER BY occurred_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    out: list[dict[str, Any]] = []
    import json

    for r in rows:
        d = dict(r)
        try:
            d["details"] = json.loads(d["details"])
        except Exception:
            d["details"] = {"raw": d.get("details")}
        out.append(d)
    return out


def get_previous_reading(conn: sqlite3.Connection, city: str, before_time: str) -> Optional[dict[str, Any]]:
    row = conn.execute(
        """
        SELECT id, city, recorded_at, temperature_2m, apparent_temperature,
               precipitation, wind_speed_10m, weather_code
        FROM readings
        WHERE city = ? AND recorded_at < ?
        ORDER BY recorded_at DESC
        LIMIT 1
        """,
        (city, before_time),
    ).fetchone()
    return dict(row) if row else None


def get_latest_reading_per_city(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for city in CITIES:
        row = conn.execute(
            """
            SELECT id, city, recorded_at, temperature_2m, apparent_temperature,
                   precipitation, wind_speed_10m, weather_code
            FROM readings
            WHERE city = ?
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            (city,),
        ).fetchone()
        if row:
            latest[city] = dict(row)
    return latest


def count_readings(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0])


def count_events(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])

