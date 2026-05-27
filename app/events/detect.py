from __future__ import annotations

from typing import Any

from app.storage.db import Event


CITY_EXTREME_THRESHOLDS: dict[str, dict[str, float]] = {
    "Ottawa": {"high_apparent": 35.0, "low_apparent": -20.0},
    "Toronto": {"high_apparent": 35.0, "low_apparent": -20.0},
    "Vancouver": {"high_apparent": 28.0, "low_apparent": -10.0},
}

RAIN_CODES = set(range(61, 66))
SNOW_CODES = set(range(71, 76))
THUNDER_CODES = set(range(95, 100))
FREEZING_RAIN_CODES = {66, 67}


def _build_event(
    city: str,
    occurred_at: str,
    event_type: str,
    summary: str,
    reason: str,
    details: dict[str, Any],
) -> Event:
    return Event(
        city=city,
        occurred_at=occurred_at,
        event_type=event_type,
        summary=summary,
        reason=reason,
        details=details,
    )


def detect_events(
    city: str,
    new_reading: dict[str, Any],
    previous_city_reading: dict[str, Any] | None,
    latest_readings_all_cities: dict[str, dict[str, Any]],
) -> list[Event]:
    occurred_at = new_reading["recorded_at"]
    events: list[Event] = []

    events.extend(_detect_context_extremes(city, new_reading, occurred_at))
    events.extend(_detect_sudden_changes(city, new_reading, previous_city_reading, occurred_at))
    events.extend(_detect_wmo_transitions(city, new_reading, previous_city_reading, occurred_at))
    events.extend(_detect_multivariable(city, new_reading, occurred_at))
    events.extend(_detect_cross_city(city, new_reading, latest_readings_all_cities, occurred_at))
    return events


def _detect_context_extremes(city: str, reading: dict[str, Any], occurred_at: str) -> list[Event]:
    threshold = CITY_EXTREME_THRESHOLDS[city]
    apparent = float(reading["apparent_temperature"])
    out: list[Event] = []

    if apparent >= threshold["high_apparent"]:
        out.append(
            _build_event(
                city,
                occurred_at,
                "context_heat_extreme",
                f"{city} apparent temperature reached {apparent:.1f}C.",
                "This exceeded the city-specific high-impact heat threshold.",
                {
                    "apparent_temperature": apparent,
                    "threshold": threshold["high_apparent"],
                    "city_profile": city,
                },
            )
        )

    if apparent <= threshold["low_apparent"]:
        out.append(
            _build_event(
                city,
                occurred_at,
                "context_cold_extreme",
                f"{city} apparent temperature dropped to {apparent:.1f}C.",
                "This crossed the city-specific deep-cold threshold.",
                {
                    "apparent_temperature": apparent,
                    "threshold": threshold["low_apparent"],
                    "city_profile": city,
                },
            )
        )

    return out


def _detect_sudden_changes(
    city: str,
    reading: dict[str, Any],
    previous: dict[str, Any] | None,
    occurred_at: str,
) -> list[Event]:
    if previous is None:
        return []

    temp_now = float(reading["temperature_2m"])
    temp_prev = float(previous["temperature_2m"])
    wind_now = float(reading["wind_speed_10m"])
    wind_prev = float(previous["wind_speed_10m"])
    precip_now = float(reading["precipitation"])
    delta_temp = temp_now - temp_prev

    out: list[Event] = []

    if delta_temp <= -5.0 and precip_now > 0:
        out.append(
            _build_event(
                city,
                occurred_at,
                "temp_drop_spike",
                f"{city} temperature fell {abs(delta_temp):.1f}C in one hour.",
                "Rapid cooling with precipitation can indicate sudden icing risk.",
                {
                    "delta_temperature": round(delta_temp, 2),
                    "previous_temperature": temp_prev,
                    "current_temperature": temp_now,
                    "precipitation": precip_now,
                },
            )
        )

    if wind_prev > 0 and wind_now >= 40 and wind_now >= (2 * wind_prev):
        out.append(
            _build_event(
                city,
                occurred_at,
                "wind_spike",
                f"{city} wind speed spiked to {wind_now:.1f} km/h.",
                "Wind more than doubled and crossed the storm-impact threshold.",
                {
                    "previous_wind": wind_prev,
                    "current_wind": wind_now,
                    "ratio": round(wind_now / wind_prev, 2),
                    "min_threshold": 40,
                },
            )
        )

    return out


def _detect_wmo_transitions(
    city: str,
    reading: dict[str, Any],
    previous: dict[str, Any] | None,
    occurred_at: str,
) -> list[Event]:
    if previous is None:
        return []

    prev_code = int(previous["weather_code"])
    now_code = int(reading["weather_code"])
    if prev_code == now_code:
        return []

    out: list[Event] = []

    if prev_code in RAIN_CODES and now_code in SNOW_CODES:
        out.append(
            _build_event(
                city,
                occurred_at,
                "rain_to_snow_transition",
                f"{city} shifted from rain to snow.",
                "A rain-to-snow transition can quickly change road traction conditions.",
                {"previous_weather_code": prev_code, "current_weather_code": now_code},
            )
        )

    if now_code in THUNDER_CODES:
        out.append(
            _build_event(
                city,
                occurred_at,
                "thunderstorm_transition",
                f"{city} entered thunderstorm conditions (WMO {now_code}).",
                "Transitioning into thunderstorm codes indicates high-impact convective weather.",
                {"previous_weather_code": prev_code, "current_weather_code": now_code},
            )
        )

    if now_code in FREEZING_RAIN_CODES:
        out.append(
            _build_event(
                city,
                occurred_at,
                "freezing_rain_transition",
                f"{city} entered freezing-rain conditions (WMO {now_code}).",
                "Freezing rain codes indicate elevated transport and infrastructure hazards.",
                {"previous_weather_code": prev_code, "current_weather_code": now_code},
            )
        )

    return out


def _detect_multivariable(city: str, reading: dict[str, Any], occurred_at: str) -> list[Event]:
    out: list[Event] = []
    code = int(reading["weather_code"])
    wind = float(reading["wind_speed_10m"])
    apparent = float(reading["apparent_temperature"])
    temp = float(reading["temperature_2m"])

    if code in SNOW_CODES and wind > 40:
        out.append(
            _build_event(
                city,
                occurred_at,
                "blizzard_like_conditions",
                f"{city} has snow with strong winds ({wind:.1f} km/h).",
                "Combined active snow and strong wind can create reduced visibility and drifting risk.",
                {"weather_code": code, "wind_speed_10m": wind, "wind_threshold": 40},
            )
        )

    humidex_gap = apparent - temp
    if humidex_gap >= 5:
        out.append(
            _build_event(
                city,
                occurred_at,
                "humidex_gap_high",
                f"{city} feels {humidex_gap:.1f}C hotter than measured air temperature.",
                "Large apparent-vs-air temperature spread suggests high humidity stress conditions.",
                {
                    "temperature_2m": temp,
                    "apparent_temperature": apparent,
                    "gap": round(humidex_gap, 2),
                    "threshold": 5,
                },
            )
        )

    return out


def _detect_cross_city(
    city: str,
    new_reading: dict[str, Any],
    latest_by_city: dict[str, dict[str, Any]],
    occurred_at: str,
) -> list[Event]:
    # Only evaluate cross-city rules when all cities have data at the same timestamp.
    if len(latest_by_city) < 3:
        return []

    current_time = new_reading["recorded_at"]
    if any(row["recorded_at"] != current_time for row in latest_by_city.values()):
        return []

    out: list[Event] = []
    temps = {c: float(row["temperature_2m"]) for c, row in latest_by_city.items()}
    warmest_city = max(temps, key=temps.get)
    coldest_city = min(temps, key=temps.get)
    spread = temps[warmest_city] - temps[coldest_city]

    if spread >= 25:
        out.append(
            _build_event(
                city,
                occurred_at,
                "cross_city_temp_divide",
                f"Cross-city temperature spread reached {spread:.1f}C.",
                "The warmest and coldest monitored cities diverged beyond the national spread threshold.",
                {
                    "spread_c": round(spread, 2),
                    "warmest_city": warmest_city,
                    "coldest_city": coldest_city,
                    "temperatures": temps,
                    "threshold": 25,
                },
            )
        )

    windy_or_wet_all = all(
        float(row["precipitation"]) > 0 or float(row["wind_speed_10m"]) >= 35 for row in latest_by_city.values()
    )
    if windy_or_wet_all:
        out.append(
            _build_event(
                city,
                occurred_at,
                "national_storm_signal",
                "All monitored cities are simultaneously wet or very windy.",
                "Concurrent weather stress across Ottawa, Toronto, and Vancouver suggests a broad system.",
                {
                    "cities": {
                        c: {
                            "precipitation": float(row["precipitation"]),
                            "wind_speed_10m": float(row["wind_speed_10m"]),
                        }
                        for c, row in latest_by_city.items()
                    },
                    "wind_threshold": 35,
                },
            )
        )

    return out

