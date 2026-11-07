"""1.8: the rain sensor hold. A binary rain sensor that reads wet holds the due cycles of the zones that
use it (the weather hold of test_weather_hold.py); an inverted one reads on = dry; an unreadable or stuck one
never holds; a press of Run Now is never held; the area's sensor and flag are used when the zone has none."""
from __future__ import annotations

from datetime import timedelta

import homeassistant.util.dt as dt_util
import pytest
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.zoneflow import issues, setup_check
from custom_components.zoneflow.const import (
    CONF_RAIN_SENSOR_ENTITY,
    CONF_RAIN_SENSOR_INVERTED,
    DOMAIN,
    HOLD_RETRY_SECONDS,
    RAIN_SENSOR_STUCK_SECONDS,
)

from .test_pause_and_frost import _zone
from .test_scenarios_cycles import _history
from .test_smoke_setup import VALVE

SENSOR = "binary_sensor.garden_rain"


async def _wet(hass, monkeypatch, tmp_path, state="on", **overrides):
    hass.states.async_set(SENSOR, state, {"friendly_name": "Garden rain"})
    c = await _zone(hass, monkeypatch, tmp_path, **{CONF_RAIN_SENSOR_ENTITY: SENSOR, **overrides})
    _history(c, last_routine_days_ago=5, last_deep_days_ago=1)
    return c


@pytest.mark.asyncio
async def test_a_wet_sensor_holds_and_a_dry_one_releases(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _wet(hass, monkeypatch, tmp_path)
    await c.run_routine_irrigation()
    await hass.async_block_till_done()
    assert c.clock.pulses_for(VALVE) == []
    status = c.status()
    assert status["code"] == "waiting_rain" and "Garden rain reads wet" in status["text"]
    assert len(c.notes) == 1 and "rain" in c.notes[0]
    hass.states.async_set(SENSOR, "off", {"friendly_name": "Garden rain"})
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=HOLD_RETRY_SECONDS + 1))
    await hass.async_block_till_done()
    assert c.clock.pulses_for(VALVE) != []


@pytest.mark.asyncio
async def test_a_press_of_run_now_waters_through_a_wet_sensor(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _wet(hass, monkeypatch, tmp_path)
    await c.run_routine_now()
    await hass.async_block_till_done()
    assert c.clock.pulses_for(VALVE) != []


@pytest.mark.asyncio
async def test_an_inverted_sensor_reads_on_as_dry(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _wet(hass, monkeypatch, tmp_path, state="on", **{CONF_RAIN_SENSOR_INVERTED: True})
    assert c.rain_sensor_wet() is False and c._rain_sensor_hold() is None
    hass.states.async_set(SENSOR, "off")
    assert c.rain_sensor_wet() is True


@pytest.mark.asyncio
async def test_an_unreadable_sensor_never_holds(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _wet(hass, monkeypatch, tmp_path)
    assert c._rain_sensor_hold() == {"sensor": "Garden rain"}
    for state in ("unavailable", "unknown", "maybe"):
        hass.states.async_set(SENSOR, state)
        assert c.rain_sensor_wet() is None and c._rain_sensor_hold() is None
    hass.states.async_remove(SENSOR)
    assert c.rain_sensor_wet() is None


@pytest.mark.asyncio
async def test_wet_for_a_day_is_stuck_not_rain_and_raises_a_repair(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _wet(hass, monkeypatch, tmp_path)
    assert not c.rain_sensor_stuck()
    later = dt_util.utcnow() + timedelta(seconds=RAIN_SENSOR_STUCK_SECONDS + 60)
    monkeypatch.setattr(dt_util, "utcnow", lambda: later)
    assert c.rain_sensor_stuck() and c.rain_sensor_wet() is None and c._rain_sensor_hold() is None
    issues.async_check(c)
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"{c.entry.entry_id}_rain_sensor_stuck") is not None
    levels = {item["id"]: item["level"] for item in setup_check.run_checks(c)}
    assert levels["rain_sensor"] == "warn"
    hass.states.async_set(SENSOR, "off")
    issues.async_check(c)
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"{c.entry.entry_id}_rain_sensor_stuck") is None


@pytest.mark.asyncio
async def test_check_my_setup_says_when_the_sensor_works(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _wet(hass, monkeypatch, tmp_path, state="off")
    levels = {item["id"]: item["level"] for item in setup_check.run_checks(c)}
    assert levels["rain_sensor"] == "ok"


@pytest.mark.asyncio
async def test_a_sensor_stuck_wet_is_still_told_after_a_restart(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _wet(hass, monkeypatch, tmp_path)
    # Home Assistant restarted: the entity's last_changed is new, but the zone remembers when the wet spell began.
    c._track_rain_sensor_wet()
    assert c.store.state.rain_sensor_wet_start_ts is not None
    later = dt_util.utcnow() + timedelta(seconds=RAIN_SENSOR_STUCK_SECONDS + 60)
    c.store.state.rain_sensor_wet_start_ts = later.timestamp() - RAIN_SENSOR_STUCK_SECONDS - 3600
    monkeypatch.setattr(dt_util, "utcnow", lambda: later)
    assert c.rain_sensor_stuck() and c.rain_sensor_wet() is None
    hass.states.async_set(SENSOR, "off")
    c._track_rain_sensor_wet()
    assert c.store.state.rain_sensor_wet_start_ts is None
