from __future__ import annotations

from fastapi.testclient import TestClient

from app.app import app
from app.storage.db import Event, Reading, db_session, init_db, insert_events, insert_reading_if_new


def seed_data():
    with db_session() as conn:
        init_db(conn)
        insert_reading_if_new(
            conn,
            Reading(
                city="Ottawa",
                recorded_at="2026-01-01T10:00:00+00:00",
                temperature_2m=-2.0,
                apparent_temperature=-4.0,
                precipitation=0.0,
                wind_speed_10m=10.0,
                weather_code=3,
            ),
        )
        insert_reading_if_new(
            conn,
            Reading(
                city="Ottawa",
                recorded_at="2026-01-01T11:00:00+00:00",
                temperature_2m=-1.0,
                apparent_temperature=-3.0,
                precipitation=0.2,
                wind_speed_10m=11.0,
                weather_code=61,
            ),
        )
        insert_events(
            conn,
            [
                Event(
                    city="Ottawa",
                    occurred_at="2026-01-01T11:00:00+00:00",
                    event_type="sample_event",
                    summary="Sample event",
                    reason="For API shape test.",
                    details={"k": 1},
                )
            ],
        )


def test_health_and_shape(temp_db_env):
    seed_data()
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["readings_stored"], int)
    assert isinstance(body["events_stored"], int)


def test_readings_endpoint_filters_and_orders(temp_db_env):
    seed_data()
    client = TestClient(app)
    response = client.get("/readings", params={"city": "Ottawa", "limit": 2})
    assert response.status_code == 200
    readings = response.json()["readings"]
    assert len(readings) == 2
    assert readings[0]["recorded_at"] > readings[1]["recorded_at"]
    assert set(readings[0].keys()) == {
        "id",
        "city",
        "recorded_at",
        "temperature_2m",
        "apparent_temperature",
        "precipitation",
        "wind_speed_10m",
        "weather_code",
    }


def test_events_endpoint_shape(temp_db_env):
    seed_data()
    client = TestClient(app)
    response = client.get("/events", params={"city": "Ottawa", "limit": 10})
    assert response.status_code == 200
    events = response.json()["events"]
    assert len(events) == 1
    assert set(events[0].keys()) == {"id", "city", "occurred_at", "event_type", "summary", "reason", "details"}

