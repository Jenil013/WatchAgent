from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, Query

from app.storage.db import count_events, count_readings, db_session, init_db, list_events, list_readings

app = FastAPI(title="WatchAgent: Weather Monitor & AI Assistant")


@app.get("/health")
def health_check() -> dict[str, int | str]:
    with db_session() as conn:
        init_db(conn)
        return {
            "status": "ok",
            "readings_stored": count_readings(conn),
            "events_stored": count_events(conn),
        }


@app.get("/readings")
def get_readings(
    city: Literal["Ottawa", "Toronto", "Vancouver"] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, list[dict]]:
    with db_session() as conn:
        init_db(conn)
        return {"readings": list_readings(conn, city, limit)}


@app.get("/events")
def get_events(
    city: Literal["Ottawa", "Toronto", "Vancouver"] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, list[dict]]:
    with db_session() as conn:
        init_db(conn)
        return {"events": list_events(conn, city, limit)}

