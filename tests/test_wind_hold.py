"""1.8: the wind hold. A sprinkler zone waits while the wind is above its limit (a wind sensor, else the
weather entity); drip zones, a limit of 0, and a reading that is missing, stale or from nowhere never hold.
Rides on the weather hold of test_weather_hold.py (hourly re-checks, one message, Run Now not held)."""
from __future__ import annotations

from datetime import timedelta

import homeassistant.util.dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.zoneflow import setup_check, units, visibility
from custom_components.zoneflow.const import (
    CONF_IRRIGATION_METHOD,
    CONF_WEATHER_ENTITY,
    CONF_WIND_ENTITY,
    HOLD_RETRY_SECONDS,
    NUMBER_DEFS,
)

from .test_pause_and_frost import _zone
from .test_scenarios_cycles import _history
from .test_smoke_setup import VALVE

WIND = "sensor.garden_wind"
WEATHER = "weather.home"


async def _windy(hass, monkeypatch, tmp_path, *, method="sprinkler", limit=20.0, **overrides):
    hass.states.async_set(WIND, "9.0", {"unit_of_measurement": "m/s"})  # 32.4 km/h
    c = await _zone(hass, monkeypatch, tmp_path, **{CONF_IRRIGATION_METHOD: method, CONF_WIND_ENTITY: WIND, **overrides})
    await c.numbers["wind_hold_kmh"].async_set_metric_value(limit)
    _history(c, last_routine_days_ago=5, last_deep_days_ago=1)
    return c


@pytest.mark.asyncio
async def test_a_sprinkler_waits_in_strong_wind_and_waters_when_it_drops(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _windy(hass, monkeypatch, tmp_path)
    await c.run_routine_irrigation()
    await hass.async_block_till_done()
    assert c.clock.pulses_for(VALVE) == []
    status = c.status()
    assert status["code"] == "waiting_wind" and "wind 32 km/h, above the limit (20 km/h)" in status["text"]
    assert len(c.notes) == 1 and "wind" in c.notes[0]
    hass.states.async_set(WIND, "3.0", {"unit_of_measurement": "m/s"})
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=HOLD_RETRY_SECONDS + 1))
    await hass.async_block_till_done()
    assert c.clock.pulses_for(VALVE) != []


@pytest.mark.asyncio
async def test_a_drip_zone_never_holds_and_hides_the_limit(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _windy(hass, monkeypatch, tmp_path, method="drip")
    assert c._wind_hold() is None
    assert ("number", "wind_hold_kmh") in visibility.hidden_for(c)


@pytest.mark.asyncio
async def test_a_zero_limit_is_off(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _windy(hass, monkeypatch, tmp_path, method="sprinkler", limit=0.0)
    assert c._wind_hold() is None
    assert ("number", "wind_hold_kmh") not in visibility.hidden_for(c)


@pytest.mark.asyncio
async def test_a_press_of_run_now_is_not_held_by_wind(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _windy(hass, monkeypatch, tmp_path)
    await c.run_routine_now()
    await hass.async_block_till_done()
    assert c.clock.pulses_for(VALVE) != []


@pytest.mark.asyncio
async def test_a_stale_or_missing_reading_never_holds(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _windy(hass, monkeypatch, tmp_path)
    assert c._wind_hold() is not None
    hass.states.async_set(WIND, "unavailable")
    assert c._wind_hold() is None
    hass.states.async_set(WIND, "9.0", {"unit_of_measurement": "m/s"})
    assert c._wind_hold() is not None
    later = dt_util.utcnow() + timedelta(hours=2)
    monkeypatch.setattr(dt_util, "utcnow", lambda: later)
    assert c._wind_hold() is None  # not updated for two hours: stuck, not wind


@pytest.mark.asyncio
async def test_the_weather_entity_is_the_wind_when_there_is_no_sensor(hass, fake_valve_services, monkeypatch, tmp_path):
    hass.states.async_set(WEATHER, "sunny", {"temperature": 20, "wind_speed": 35.0, "wind_speed_unit": "km/h", "humidity": 50})
    c = await _zone(hass, monkeypatch, tmp_path, **{CONF_IRRIGATION_METHOD: "micro_sprinkler", CONF_WEATHER_ENTITY: WEATHER})
    await c.numbers["wind_hold_kmh"].async_set_metric_value(25.0)
    hold = c._wind_hold()
    assert hold == {"wind_kmh": 35.0, "limit_kmh": 25.0}


@pytest.mark.asyncio
async def test_imperial_zone_shows_the_limit_in_mph(hass, fake_valve_services, monkeypatch, tmp_path):
    assert units.to_display("wind_hold_kmh", 32.18688, True) == pytest.approx(20.0)
    assert units.to_metric("wind_hold_kmh", 20.0, True) == pytest.approx(32.18688)
    assert units.unit("wind_hold_kmh", "km/h", True) == "mph"
    assert NUMBER_DEFS["wind_hold_kmh"][1:3] == (0.0, 60.0)


@pytest.mark.asyncio
async def test_check_my_setup_on_the_wind_limit(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _zone(hass, monkeypatch, tmp_path, **{CONF_IRRIGATION_METHOD: "sprinkler"})
    await c.numbers["wind_hold_kmh"].async_set_metric_value(20.0)
    ids = {item["id"]: item["level"] for item in setup_check.run_checks(c)}
    assert ids.get("wind_hold") == "warn"  # a limit but nothing to read the wind from
