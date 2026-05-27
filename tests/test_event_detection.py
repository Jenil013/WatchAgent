from __future__ import annotations

from app.events.detect import detect_events


def _reading(city: str, recorded_at: str, temp: float, apparent: float, precip: float, wind: float, code: int):
    return {
        "city": city,
        "recorded_at": recorded_at,
        "temperature_2m": temp,
        "apparent_temperature": apparent,
        "precipitation": precip,
        "wind_speed_10m": wind,
        "weather_code": code,
    }


def _types(events):
    return {e.event_type for e in events}


def test_context_heat_extreme_fires():
    curr = _reading("Ottawa", "2026-07-01T10:00:00+00:00", 32, 36, 0, 15, 1)
    events = detect_events("Ottawa", curr, None, {"Ottawa": curr})
    assert "context_heat_extreme" in _types(events)


def test_context_cold_extreme_fires():
    curr = _reading("Toronto", "2026-01-10T10:00:00+00:00", -18, -21, 0, 12, 3)
    events = detect_events("Toronto", curr, None, {"Toronto": curr})
    assert "context_cold_extreme" in _types(events)


def test_temp_drop_spike_fires_with_precipitation():
    prev = _reading("Ottawa", "2026-01-01T09:00:00+00:00", 3, 1, 0, 15, 61)
    curr = _reading("Ottawa", "2026-01-01T10:00:00+00:00", -3, -5, 2, 18, 61)
    events = detect_events("Ottawa", curr, prev, {"Ottawa": curr})
    assert "temp_drop_spike" in _types(events)


def test_temp_drop_spike_not_fire_without_precipitation():
    prev = _reading("Ottawa", "2026-01-01T09:00:00+00:00", 3, 1, 0, 15, 61)
    curr = _reading("Ottawa", "2026-01-01T10:00:00+00:00", -3, -5, 0, 18, 61)
    events = detect_events("Ottawa", curr, prev, {"Ottawa": curr})
    assert "temp_drop_spike" not in _types(events)


def test_wind_spike_fires():
    prev = _reading("Ottawa", "2026-01-01T09:00:00+00:00", 5, 4, 0, 18, 2)
    curr = _reading("Ottawa", "2026-01-01T10:00:00+00:00", 5, 4, 0, 42, 2)
    events = detect_events("Ottawa", curr, prev, {"Ottawa": curr})
    assert "wind_spike" in _types(events)


def test_rain_to_snow_transition_fires():
    prev = _reading("Toronto", "2026-01-01T09:00:00+00:00", 2, 0, 1, 20, 63)
    curr = _reading("Toronto", "2026-01-01T10:00:00+00:00", -1, -4, 1, 22, 71)
    events = detect_events("Toronto", curr, prev, {"Toronto": curr})
    assert "rain_to_snow_transition" in _types(events)


def test_thunderstorm_transition_fires():
    prev = _reading("Toronto", "2026-06-01T09:00:00+00:00", 24, 26, 0, 18, 3)
    curr = _reading("Toronto", "2026-06-01T10:00:00+00:00", 23, 25, 2, 35, 95)
    events = detect_events("Toronto", curr, prev, {"Toronto": curr})
    assert "thunderstorm_transition" in _types(events)


def test_freezing_rain_transition_fires():
    prev = _reading("Ottawa", "2026-02-01T09:00:00+00:00", -2, -4, 0, 10, 3)
    curr = _reading("Ottawa", "2026-02-01T10:00:00+00:00", -3, -6, 1, 16, 66)
    events = detect_events("Ottawa", curr, prev, {"Ottawa": curr})
    assert "freezing_rain_transition" in _types(events)


def test_blizzard_like_conditions_fire():
    curr = _reading("Vancouver", "2026-01-03T10:00:00+00:00", -1, -6, 1, 45, 71)
    events = detect_events("Vancouver", curr, None, {"Vancouver": curr})
    assert "blizzard_like_conditions" in _types(events)


def test_humidex_gap_high_fires():
    curr = _reading("Toronto", "2026-07-05T10:00:00+00:00", 28, 34, 0, 10, 2)
    events = detect_events("Toronto", curr, None, {"Toronto": curr})
    assert "humidex_gap_high" in _types(events)


def test_cross_city_divide_fires_when_all_cities_aligned():
    ts = "2026-07-01T16:00:00+00:00"
    ott = _reading("Ottawa", ts, 35, 38, 0, 20, 1)
    tor = _reading("Toronto", ts, 33, 36, 0, 22, 1)
    van = _reading("Vancouver", ts, 8, 7, 1, 36, 63)
    latest = {"Ottawa": ott, "Toronto": tor, "Vancouver": van}
    events = detect_events("Ottawa", ott, None, latest)
    assert "cross_city_temp_divide" in _types(events)


def test_national_storm_signal_fires_when_all_cities_wet_or_windy():
    ts = "2026-10-01T16:00:00+00:00"
    ott = _reading("Ottawa", ts, 8, 6, 1.2, 20, 63)
    tor = _reading("Toronto", ts, 10, 9, 0.0, 36, 3)
    van = _reading("Vancouver", ts, 11, 10, 0.4, 22, 61)
    latest = {"Ottawa": ott, "Toronto": tor, "Vancouver": van}
    events = detect_events("Ottawa", ott, None, latest)
    assert "national_storm_signal" in _types(events)


def test_cross_city_rules_do_not_fire_when_timestamps_misaligned():
    ott = _reading("Ottawa", "2026-10-01T16:00:00+00:00", 8, 6, 1.2, 20, 63)
    tor = _reading("Toronto", "2026-10-01T15:00:00+00:00", 10, 9, 0.0, 36, 3)
    van = _reading("Vancouver", "2026-10-01T16:00:00+00:00", 11, 10, 0.4, 22, 61)
    latest = {"Ottawa": ott, "Toronto": tor, "Vancouver": van}
    events = detect_events("Ottawa", ott, None, latest)
    event_types = _types(events)
    assert "cross_city_temp_divide" not in event_types
    assert "national_storm_signal" not in event_types

