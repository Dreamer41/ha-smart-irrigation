"""The "Water now" / Run Routine Irrigation Now press waters even when the
routine is not due, and counts as the routine watering done. It skips the
due, soil-wet, dry-down and forecast gates; pause, snooze, the lock, frost
and the runtime caps still apply."""
from unittest.mock import AsyncMock

import homeassistant.util.dt as dt_util
import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.zoneflow.const import DOMAIN

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

SOIL_MOISTURE = "sensor.soil_moisture_zone1"


async def _zone(hass, moisture=None, **overrides):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "25.0")
    if moisture is not None:
        hass.states.async_set(SOIL_MOISTURE, moisture)
    await hass.async_block_till_done()
    entry = make_entry(hass, **overrides)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    controller._run_pulses = AsyncMock(return_value=True)
    return controller


def _just_watered(controller):
    controller.store.state.last_routine_ts = dt_util.utcnow().timestamp() - 3600
    controller.store.state.last_significant_rain_ts = 0.0


@pytest.mark.asyncio
async def test_press_waters_when_not_due_and_marks_it_done(hass, fake_valve_services):
    c = await _zone(hass)
    _just_watered(c)
    before = c.store.state.last_routine_ts

    await c.run_routine_now()
    await hass.async_block_till_done()

    c._run_pulses.assert_called_once()
    assert c.store.state.last_routine_ts > before


@pytest.mark.asyncio
async def test_the_scheduled_run_still_waits_until_due(hass, fake_valve_services):
    c = await _zone(hass)
    _just_watered(c)

    await c.run_routine_irrigation()
    await hass.async_block_till_done()

    c._run_pulses.assert_not_called()


@pytest.mark.asyncio
async def test_press_waters_through_a_wet_soil_probe(hass, fake_valve_services):
    c = await _zone(hass, moisture="90", soil_moisture_entity=SOIL_MOISTURE)
    _just_watered(c)

    await c.run_routine_now()
    await hass.async_block_till_done()

    c._run_pulses.assert_called_once()


@pytest.mark.asyncio
async def test_press_waters_inside_the_dry_down_wait(hass, fake_valve_services):
    c = await _zone(hass)
    c.store.state.last_routine_ts = 0.0
    c.store.state.last_significant_rain_ts = dt_util.utcnow().timestamp() - 3600

    await c.run_routine_irrigation()  # the scheduled run: held back
    c._run_pulses.assert_not_called()

    await c.run_routine_now()
    await hass.async_block_till_done()
    c._run_pulses.assert_called_once()


@pytest.mark.asyncio
async def test_press_is_refused_while_paused(hass, fake_valve_services):
    c = await _zone(hass)
    _just_watered(c)
    await c.set_paused(True)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError):
        await c.run_routine_now()

    c._run_pulses.assert_not_called()


@pytest.mark.asyncio
async def test_press_does_nothing_while_the_zone_is_busy(hass, fake_valve_services):
    c = await _zone(hass)
    _just_watered(c)
    c.store.state.lock_on = True

    await c.run_routine_now()
    await hass.async_block_till_done()

    c._run_pulses.assert_not_called()


@pytest.mark.asyncio
async def test_press_does_nothing_when_snoozed_today(hass, fake_valve_services):
    c = await _zone(hass)
    _just_watered(c)
    await c.snooze_today()
    await hass.async_block_till_done()

    await c.run_routine_now()
    await hass.async_block_till_done()

    c._run_pulses.assert_not_called()


@pytest.mark.asyncio
async def test_an_interrupted_press_is_not_marked_done(hass, fake_valve_services):
    c = await _zone(hass)
    _just_watered(c)
    before = c.store.state.last_routine_ts
    c._run_pulses = AsyncMock(return_value=False)

    await c.run_routine_now()
    await hass.async_block_till_done()

    assert c.store.state.last_routine_ts == before
