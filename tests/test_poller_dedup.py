from __future__ import annotations

from app import poller
from app.storage.db import count_events, count_readings, db_session, init_db


def test_poller_deduplicates_same_timestamp(monkeypatch, temp_db_env):
    payload = {
        "time": "2026-01-01T10:00",
        "temperature_2m": -2.0,
        "apparent_temperature": -4.0,
        "precipitation": 0.0,
        "wind_speed_10m": 12.0,
        "weather_code": 3,
    }

    def fake_fetch(_city, retry_count=0):
        return payload

    monkeypatch.setattr(poller, "fetch_city_current", fake_fetch)
    city = poller.CITIES[0]

    poller.process_city(city)
    poller.process_city(city)

    with db_session() as conn:
        init_db(conn)
        assert count_readings(conn) == 1
        assert count_events(conn) == 0

