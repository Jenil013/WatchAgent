from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import requests

from app.events.detect import detect_events
from app.storage.db import (
    Reading,
    db_session,
    get_latest_reading_per_city,
    get_latest_reading_time,
    get_previous_reading,
    init_db,
    insert_events,
    insert_reading_if_new,
    normalize_iso,
    parse_iso,
)

BASE_URL = "https://api.open-meteo.com/v1/forecast"
CURRENT_FIELDS = "temperature_2m,apparent_temperature,precipitation,wind_speed_10m,weather_code"


@dataclass(frozen=True)
class CityConfig:
    name: str
    latitude: float
    longitude: float


CITIES: tuple[CityConfig, ...] = (
    CityConfig("Ottawa", 45.4112, -75.6981),
    CityConfig("Toronto", 43.7064, -79.3986),
    CityConfig("Vancouver", 49.2497, -123.1193),
)

POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "300"))
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "20"))
MAX_RETRIES = int(os.environ.get("POLL_MAX_RETRIES", "3"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("watchagent.poller")


def fetch_city_current(city: CityConfig, retry_count: int = 0) -> dict[str, Any]:
    params = {
        "latitude": city.latitude,
        "longitude": city.longitude,
        "current": CURRENT_FIELDS,
        "wind_speed_unit": "kmh",
        "timezone": "auto",
    }
    response = requests.get(BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()
    current = payload.get("current")
    if not isinstance(current, dict):
        raise ValueError("Missing current object in Open-Meteo response")
    for required in (
        "time",
        "temperature_2m",
        "apparent_temperature",
        "precipitation",
        "wind_speed_10m",
        "weather_code",
    ):
        if required not in current:
            raise ValueError(f"Missing current.{required}")
    return current


def _log_fetch_failure(city: str, status: str, retry_count: int, error: str) -> None:
    logger.warning(
        "poll_fetch_failed city=%s http_status=%s retry_count=%s error=%s",
        city,
        status,
        retry_count,
        error,
    )


def process_city(city: CityConfig) -> None:
    current: dict[str, Any] | None = None
    for retry_count in range(MAX_RETRIES + 1):
        try:
            current = fetch_city_current(city, retry_count=retry_count)
            break
        except requests.HTTPError as exc:
            status = str(exc.response.status_code) if exc.response is not None else "none"
            _log_fetch_failure(city.name, status, retry_count, str(exc))
        except requests.RequestException as exc:
            _log_fetch_failure(city.name, "none", retry_count, str(exc))
        except ValueError as exc:
            _log_fetch_failure(city.name, "none", retry_count, str(exc))
            break
        except Exception as exc:
            _log_fetch_failure(city.name, "none", retry_count, str(exc))
            break

    if current is None:
        return

    reading_time = normalize_iso(str(current["time"]))
    with db_session() as conn:
        init_db(conn)
        latest = get_latest_reading_time(conn, city.name)
        if latest is not None and parse_iso(reading_time) <= parse_iso(latest):
            logger.info("poll_skipped_duplicate city=%s recorded_at=%s", city.name, reading_time)
            return

        reading = Reading(
            city=city.name,
            recorded_at=reading_time,
            temperature_2m=float(current["temperature_2m"]),
            apparent_temperature=float(current["apparent_temperature"]),
            precipitation=float(current["precipitation"]),
            wind_speed_10m=float(current["wind_speed_10m"]),
            weather_code=int(current["weather_code"]),
        )
        inserted = insert_reading_if_new(conn, reading)
        if not inserted:
            logger.info("poll_skipped_db_duplicate city=%s recorded_at=%s", city.name, reading_time)
            return

        previous = get_previous_reading(conn, city.name, reading_time)
        latest_by_city = get_latest_reading_per_city(conn)
        events = detect_events(city.name, reading.as_dict(), previous, latest_by_city)
        inserted_events = insert_events(conn, events)
        logger.info(
            "poll_saved city=%s recorded_at=%s events_inserted=%s",
            city.name,
            reading_time,
            inserted_events,
        )


def run_forever() -> None:
    logger.info("poller_started cities=%s poll_interval_seconds=%s", ",".join(c.name for c in CITIES), POLL_INTERVAL_SECONDS)
    while True:
        for city in CITIES:
            process_city(city)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_forever()

