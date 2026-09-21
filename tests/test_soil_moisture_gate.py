"""End-to-end: an optional soil-moisture sensor becomes the direct decider
of routine irrigation, ahead of the plain time-interval estimate -- see
calculations.routine_due_with_soil_moisture (unit-tested in
test_calculations.py) and controller.run_routine_irrigation's gate. These
tests exercise the real config-entry/controller wiring, including the
dropout fallback.
"""
from unittest.mock import AsyncMock

import pytest

from custom_components.zoneflow.const import DOMAIN

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

SOIL_MOISTURE = "sensor.soil_moisture_zone1"


async def _seed(hass, moisture: str | None = None):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "25.0")
    if moisture is not None:
        hass.states.async_set(SOIL_MOISTURE, moisture)
    await hass.async_block_till_done()


async def _make_due_but_not_yet_by_interval(controller, hass):
    """last_routine_ts = now (interval clearly NOT elapsed) so any run
    that still happens must be because soil moisture forced it, not the
    time interval."""
    import homeassistant.util.dt as dt_util

    controller.store.state.last_routine_ts = dt_util.utcnow().timestamp()
    controller.store.state.last_significant_rain_ts = 0.0
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_dry_soil_moisture_forces_a_run_even_though_interval_isnt_due(hass, fake_valve_services):
    await _seed(hass, moisture="10")  # well below the 20% default dry threshold
    entry = make_entry(hass, soil_moisture_entity=SOIL_MOISTURE)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    await _make_due_but_not_yet_by_interval(controller, hass)

    spy = AsyncMock(return_value=True)
    controller._run_pulses = spy
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    spy.assert_called_once()


@pytest.mark.asyncio
async def test_wet_soil_moisture_skips_even_though_interval_says_overdue(hass, fake_valve_services):
    await _seed(hass, moisture="80")  # well above the 60% default wet threshold
    entry = make_entry(hass, soil_moisture_entity=SOIL_MOISTURE)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    # Overdue by the plain time interval -- last run 30 days ago.
    controller.store.state.last_routine_ts = 0.0
    controller.store.state.last_significant_rain_ts = 0.0

    spy = AsyncMock(return_value=True)
    controller._run_pulses = spy
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    spy.assert_not_called()


@pytest.mark.asyncio
async def test_soil_moisture_dropout_falls_back_to_the_modeled_interval(hass, fake_valve_services):
    """A configured-but-currently-unreadable soil-moisture sensor must
    degrade to "no override" -- same dropout pattern as temp/rain/pump --
    not to a numeric guess in either direction."""
    await _seed(hass, moisture="unavailable")
    entry = make_entry(hass, soil_moisture_entity=SOIL_MOISTURE)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    assert await controller._soil_moisture_pct() is None

    # Overdue by the plain interval -- should proceed exactly as if no
    # soil-moisture sensor were configured at all.
    controller.store.state.last_routine_ts = 0.0
    controller.store.state.last_significant_rain_ts = 0.0

    spy = AsyncMock(return_value=True)
    controller._run_pulses = spy
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    spy.assert_called_once()


@pytest.mark.asyncio
async def test_unconfigured_soil_moisture_behaves_exactly_as_before(hass, fake_valve_services):
    """No soil_moisture_entity in the config at all -- the feature must be
    fully inert, not just gracefully degraded."""
    await _seed(hass)
    entry = make_entry(hass)  # no soil_moisture_entity
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    assert controller.soil_moisture_entity is None
    assert await controller._soil_moisture_pct() is None
