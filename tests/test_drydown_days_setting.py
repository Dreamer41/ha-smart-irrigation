"""Changing the dry-down holdoff sliders really changes how long watering waits
after heavy rain: Routine Dry-Down Holdoff (default 4 days) and Deep Soak
Subsoil Dry-Down Holdoff (default 8 days)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import homeassistant.util.dt as dt_util
import pytest

from custom_components.zoneflow.const import DOMAIN

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

DAY = 86400.0


async def _zone(hass, *, rain_days_ago, drydown_days=None, deep_drydown_days=None):
    for entity, value in ((VALVE, "off"), (PUMP, "999"), (RAIN_COUNTER, "0"), (OUTDOOR_TEMP, "28.0")):
        hass.states.async_set(entity, value)
    await hass.async_block_till_done()
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = hass.data[DOMAIN][entry.entry_id]
    c._run_pulses = AsyncMock(return_value=True)
    if drydown_days is not None:
        await c.numbers["routine_drydown_days"].async_set_metric_value(drydown_days)
    if deep_drydown_days is not None:
        await c.numbers["deep_soak_drydown_days"].async_set_metric_value(deep_drydown_days)
    now = dt_util.utcnow().timestamp()
    state = c.store.state
    state.last_routine_ts = now - 10 * DAY  # well overdue by the interval
    state.last_deep_soak_ts = now - 30 * DAY
    state.last_significant_rain_ts = now - rain_days_ago * DAY  # heavy rain this long ago
    state.rain_day_history_mm = [0.0] * 10  # no rain credit: only the dry-down can hold it
    return c


@pytest.mark.asyncio
async def test_a_6_day_holdoff_blocks_the_routine_5_days_after_heavy_rain(hass, fake_valve_services):
    c = await _zone(hass, rain_days_ago=5, drydown_days=6.0)

    await c.run_routine_irrigation()

    c._run_pulses.assert_not_called()
    assert c.store.state.decisions["routine"]["code"] == "skipped_drydown"
    status = c.status()
    assert status["code"] == "skipped_drydown"


@pytest.mark.asyncio
async def test_the_default_4_day_holdoff_lets_it_water_5_days_after(hass, fake_valve_services):
    c = await _zone(hass, rain_days_ago=5)
    assert c.number("routine_drydown_days") == 4.0

    await c.run_routine_irrigation()

    c._run_pulses.assert_called_once()


@pytest.mark.asyncio
async def test_after_the_6_days_it_waters_again(hass, fake_valve_services):
    c = await _zone(hass, rain_days_ago=6.1, drydown_days=6.0)

    await c.run_routine_irrigation()

    c._run_pulses.assert_called_once()


@pytest.mark.asyncio
async def test_the_next_watering_waits_for_the_6_days(hass, fake_valve_services):
    c = await _zone(hass, rain_days_ago=1, drydown_days=6.0)
    rain_ts = c.store.state.last_significant_rain_ts
    routine_next, _deep = c.next_watering()
    assert routine_next >= rain_ts + 6 * DAY - 60  # not before the holdoff ends
    assert c.status()["code"] == "waiting_drydown"


@pytest.mark.asyncio
async def test_water_now_still_waters_inside_the_holdoff(hass, fake_valve_services):
    """A person pressing Water now decides themselves (1.7.1): the dry-down does not hold it."""
    c = await _zone(hass, rain_days_ago=1, drydown_days=6.0)
    await c.run_routine_now()
    c._run_pulses.assert_called_once()


@pytest.mark.asyncio
async def test_a_longer_deep_soak_holdoff_blocks_the_deep_soak(hass, fake_valve_services):
    c = await _zone(hass, rain_days_ago=9, deep_drydown_days=10.0)
    await c.run_deep_soak()
    c._run_pulses.assert_not_called()
    assert c.store.state.decisions["deep_soak"]["code"] == "skipped_drydown"


@pytest.mark.asyncio
async def test_the_default_8_day_deep_soak_holdoff_lets_it_run_9_days_after(hass, fake_valve_services):
    c = await _zone(hass, rain_days_ago=9)
    assert c.number("deep_soak_drydown_days") == 8.0
    await c.run_deep_soak()
    c._run_pulses.assert_called_once()
