"""1.8: the zone aggregates its climate readings over each local day and closes every day into
an FAO-56 ET0 history entry that says where each input came from."""
from __future__ import annotations

from datetime import timedelta

import homeassistant.util.dt as dt_util
import pytest
from homeassistant.core import State

from custom_components.zoneflow.const import CONF_HUMIDITY_ENTITY, CONF_SOLAR_ENTITY, CONF_WEATHER_ENTITY, CONF_WIND_ENTITY, DOMAIN
from custom_components.zoneflow.day_aggregate import DayAggregate

from .test_smoke_setup import _seed_source_entities, make_entry

H = 3600.0
HUM, WIND, SOLAR, WEATHER = "sensor.out_humidity", "sensor.out_wind", "sensor.out_solar", "weather.home"


async def _zone(hass, **entities):
    await _seed_source_entities(hass)
    for entity, state, attrs in (
        (HUM, "70", {"unit_of_measurement": "%"}),
        (WIND, "7.2", {"unit_of_measurement": "km/h"}),
        (SOLAR, "300", {"unit_of_measurement": "W/m²"}),
        (WEATHER, "sunny", {"humidity": 65, "wind_speed": 9.0, "wind_speed_unit": "km/h"}),
    ):
        hass.states.async_set(entity, state, attrs)
    entry = make_entry(hass, **entities)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


def _day(start: float, readings: list[tuple[float, float | None]], end: float) -> dict:
    a = DayAggregate()
    a.reset(start)
    for offset, value in readings:
        a.add(start + offset, value)
    return a.as_dict()


@pytest.mark.asyncio
async def test_a_day_with_every_sensor_uses_them_all(hass):
    c = await _zone(hass, **{CONF_HUMIDITY_ENTITY: HUM, CONF_WIND_ENTITY: WIND, CONF_SOLAR_ENTITY: SOLAR})
    s = c.store.state
    day = dt_util.now().date() - timedelta(days=1)
    start = dt_util.start_of_local_day(day).timestamp()
    end = start + 24 * H
    s.day_aggregates = {
        "humidity": _day(start, [(0, 84.0), (12 * H, 63.0), (18 * H, 75.0)], end),
        "wind": _day(start, [(0, 2.0)], end),
        "solar": _day(start, [(0, 0.0), (6 * H, 500.0), (18 * H, 0.0)], end),
    }
    s.today_min_temp_c, s.today_peak_temp_c = 12.3, 21.5
    c._close_et0_day(day, end)
    e = s.et0_day_history[0]
    assert e["date"] == day.isoformat() and e["et0"] is not None and e["et0"] > 0
    assert e["sources"] == {"humidity": "rh_min_max", "wind": "measured", "solar": "measured"}
    assert e["rh_min"] == 63.0 and e["rh_max"] == 84.0
    assert e["rs"] == pytest.approx(500 * 12 * H / 1e6, abs=0.01)
    assert e["u2"] == pytest.approx(2.0, abs=0.01)  # a home station at 2 m


@pytest.mark.asyncio
async def test_the_weather_entity_fills_in_when_there_is_no_sensor(hass):
    c = await _zone(hass, **{CONF_WEATHER_ENTITY: WEATHER})
    s = c.store.state
    day = dt_util.now().date() - timedelta(days=1)
    start = dt_util.start_of_local_day(day).timestamp()
    s.day_aggregates = {"weather_humidity": _day(start, [(0, 70.0)], 0), "weather_wind": _day(start, [(0, 3.0)], 0)}
    s.today_min_temp_c, s.today_peak_temp_c = 12.3, 21.5
    c._close_et0_day(day, start + 24 * H)
    e = s.et0_day_history[0]
    assert e["sources"] == {"humidity": "weather", "wind": "weather", "solar": "estimated"}
    assert e["rh_mean"] == 70.0 and e["u2"] == pytest.approx(3.0 * 0.748, abs=0.01)  # 10 m to 2 m


@pytest.mark.asyncio
async def test_a_short_day_of_readings_falls_back_to_estimates(hass):
    c = await _zone(hass, **{CONF_HUMIDITY_ENTITY: HUM, CONF_WIND_ENTITY: WIND})
    s = c.store.state
    day = dt_util.now().date() - timedelta(days=1)
    start = dt_util.start_of_local_day(day).timestamp()
    s.day_aggregates = {"humidity": _day(start, [(22 * H, 80.0)], 0), "wind": _day(start, [(20 * H, 4.0)], 0)}
    s.today_min_temp_c, s.today_peak_temp_c = 12.3, 21.5
    c._close_et0_day(day, start + 24 * H)
    assert s.et0_day_history[0]["sources"] == {"humidity": "estimated", "wind": "default", "solar": "estimated"}


@pytest.mark.asyncio
async def test_a_day_without_temperatures_has_no_et0(hass):
    c = await _zone(hass)
    s = c.store.state
    s.today_min_temp_c = s.today_peak_temp_c = None
    day = dt_util.now().date() - timedelta(days=1)
    c._close_et0_day(day, dt_util.start_of_local_day().timestamp())
    assert s.et0_day_history[0] == {"date": day.isoformat(), "et0": None, "sources": {}}


def test_readings_are_converted_to_fao56_units():
    from custom_components.zoneflow.controller import ZoneFlowController as Z

    assert Z._et0_reading("wind", State(WIND, "36", {"unit_of_measurement": "km/h"})) == pytest.approx(10.0)
    assert Z._et0_reading("wind", State(WIND, "10", {"unit_of_measurement": "mph"})) == pytest.approx(4.4704)
    assert Z._et0_reading("wind", State(WIND, "-1", {"unit_of_measurement": "m/s"})) is None
    assert Z._et0_reading("wind", State(WIND, "3", {"unit_of_measurement": "furlongs"})) is None
    assert Z._et0_reading("humidity", State(HUM, "120", {})) is None
    assert Z._et0_reading("humidity", State(HUM, "unavailable", {})) is None
    assert Z._et0_reading("solar", State(SOLAR, "40000", {"unit_of_measurement": "lx"})) is None
    assert Z._et0_reading("solar", State(SOLAR, "640", {"unit_of_measurement": "W/m²"})) == 640.0
    assert Z._et0_reading("weather_wind", State(WEATHER, "sunny", {"wind_speed": 10, "wind_speed_unit": "mph"})) == pytest.approx(4.4704)
    assert Z._et0_reading("weather_humidity", State(WEATHER, "sunny", {})) is None


@pytest.mark.asyncio
async def test_sensor_changes_are_aggregated_and_a_new_day_starts_fresh(hass):
    c = await _zone(hass, **{CONF_HUMIDITY_ENTITY: HUM})
    s = c.store.state
    assert "humidity" in s.day_aggregates  # seeded at setup
    hass.states.async_set(HUM, "55", {"unit_of_measurement": "%"})
    await hass.async_block_till_done()
    agg = DayAggregate.from_dict(s.day_aggregates["humidity"])
    assert agg.last_value == 55.0 and agg.minimum == 55.0 and agg.maximum == 70.0
    hass.states.async_set(HUM, "unavailable", {})
    await hass.async_block_till_done()
    assert DayAggregate.from_dict(s.day_aggregates["humidity"]).last_value is None
    c._reset_et0_inputs(dt_util.utcnow().timestamp())
    assert DayAggregate.from_dict(s.day_aggregates["humidity"]).covered_seconds == 0.0


@pytest.mark.asyncio
async def test_a_missed_shift_closes_the_open_day_and_marks_whole_missed_days_empty(hass):
    c = await _zone(hass)
    s = c.store.state
    today = dt_util.now().date()
    s.today_date_iso = (today - timedelta(days=2)).isoformat()
    s.last_shift_date_iso = None
    s.today_min_temp_c, s.today_peak_temp_c = 14.0, 27.0
    s.et0_day_history = []
    c._start_new_day()
    dates = [e["date"] for e in s.et0_day_history]
    assert dates == [(today - timedelta(days=1)).isoformat(), (today - timedelta(days=2)).isoformat()]
    assert s.et0_day_history[0]["et0"] is None and s.et0_day_history[1]["et0"] > 0


@pytest.mark.asyncio
async def test_a_crash_is_not_covered_past_the_last_heartbeat(hass):
    c = await _zone(hass, **{CONF_HUMIDITY_ENTITY: HUM})
    s = c.store.state
    now = dt_util.utcnow().timestamp()
    agg = DayAggregate()
    agg.reset(now - 10 * H)
    agg.add(now - 10 * H, 60.0)
    s.day_aggregates = {"humidity": agg.as_dict()}
    s.last_alive_ts = now - 6 * H  # crashed 6 hours ago
    c._pause_et0_inputs(min(s.last_alive_ts, now))
    summary = DayAggregate.from_dict(s.day_aggregates["humidity"]).close(now)
    assert summary.covered_seconds == pytest.approx(4 * H)


@pytest.mark.asyncio
async def test_the_history_keeps_two_weeks_and_one_entry_per_day(hass):
    c = await _zone(hass)
    s = c.store.state
    s.today_min_temp_c, s.today_peak_temp_c = 14.0, 27.0
    today = dt_util.now().date()
    for back in range(20, 0, -1):
        c._close_et0_day(today - timedelta(days=back), dt_util.utcnow().timestamp())
    c._close_et0_day(today - timedelta(days=1), dt_util.utcnow().timestamp())
    dates = [e["date"] for e in s.et0_day_history]
    assert len(dates) == 14 and len(set(dates)) == 14 and dates[0] == (today - timedelta(days=1)).isoformat()
