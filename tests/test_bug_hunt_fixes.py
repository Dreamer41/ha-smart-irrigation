"""1.8: findings of the outside bug hunt: implausible readings, a save that never happens, a valve
that is slow to close, the stuck-valve clock."""
from __future__ import annotations

import asyncio
from datetime import timedelta

import homeassistant.util.dt as dt_util
import pytest
from homeassistant.core import State

from custom_components.zoneflow.const import DOMAIN
from custom_components.zoneflow.controller import ZoneFlowController as Z

from .test_smoke_setup import VALVE, _seed_source_entities, make_entry


async def _zone(hass):
    await _seed_source_entities(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


@pytest.mark.asyncio
@pytest.mark.parametrize("t_min,t_max", [(60.0, 95.0), (12.0, 85.0), (float("nan"), 20.0), (-90.0, 10.0)])
async def test_an_impossible_temperature_gives_no_et0_for_the_day(hass, t_min, t_max):
    c = await _zone(hass)
    s = c.store.state
    s.today_min_temp_c, s.today_peak_temp_c = t_min, t_max
    c._close_et0_day(dt_util.now().date() - timedelta(days=1), dt_util.utcnow().timestamp())
    assert s.et0_day_history[0]["et0"] is None


def test_a_wind_sentinel_is_not_wind():
    for value in ("6553.5", "655.35", "inf", "-1"):
        assert Z._et0_reading("wind", State("sensor.w", value, {"unit_of_measurement": "m/s"})) is None
    assert Z._et0_reading("weather_wind", State("weather.h", "sunny", {"wind_speed": 6553, "wind_speed_unit": "km/h"})) is None
    assert Z._et0_reading("wind", State("sensor.w", "12", {"unit_of_measurement": "m/s"})) == 12.0


@pytest.mark.asyncio
async def test_a_sensor_that_reports_every_few_seconds_still_gets_saved(hass, monkeypatch):
    c = await _zone(hass)
    store = c.store
    store._save_asked_at = None
    calls = []
    monkeypatch.setattr(store._store, "async_delay_save", lambda fn, delay: calls.append((fn, delay)))
    for _ in range(500):
        store.schedule_save()
    assert len(calls) == 1  # asked once: Home Assistant would have pushed the deadline back each time
    calls[0][0]()  # the write happens and clears the flag
    store.schedule_save()
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_a_valve_that_takes_a_while_to_close_is_waited_for(hass):
    c = await _zone(hass)
    hass.states.async_set(VALVE, "closing")
    hass.loop.call_later(1.2, lambda: hass.states.async_set(VALVE, "closed"))
    assert await c._valve_confirmed_closed(VALVE, seconds=0.5) is True
    hass.states.async_set(VALVE, "open")
    assert await c._valve_confirmed_closed(VALVE, seconds=0.5) is False
    hass.states.async_set(VALVE, "unavailable")
    assert await c._valve_confirmed_closed(VALVE, seconds=0.5) is False


@pytest.mark.asyncio
async def test_the_stuck_valve_clock_runs_from_the_first_opening(hass):
    c = await _zone(hass)
    hass.states.async_set(VALVE, "off")
    await hass.async_block_till_done()
    hass.states.async_set(VALVE, "opening")
    await hass.async_block_till_done()
    first = c._valve_open_since
    assert first is not None
    await asyncio.sleep(0.05)
    for state in ("open", "closing", "open"):
        hass.states.async_set(VALVE, state)
        await hass.async_block_till_done()
        assert c._valve_open_since == first
    hass.states.async_set(VALVE, "closed")
    await hass.async_block_till_done()
    assert c._valve_open_since is None
