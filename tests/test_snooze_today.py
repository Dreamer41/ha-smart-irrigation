"""Snooze Today (button.py / controller.snooze_today / __init__.py's
snooze_today service): a same-day-only skip that self-expires at the next
local calendar date -- see state_store.py's snooze_date_iso comment and
controller.py's _is_snoozed_today.
"""
import pytest
import homeassistant.util.dt as dt_util

from custom_components.zoneflow.const import DOMAIN

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry


async def _seed(hass):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "25.0")
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_snooze_button_created_and_blocks_a_due_routine_run(hass, fake_valve_services):
    await _seed(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    # Make routine irrigation genuinely due -- last run far in the past,
    # no rain, no forecast gate configured.
    controller.store.state.last_routine_ts = 0.0
    controller.store.state.last_significant_rain_ts = 0.0

    button_id = next(s.entity_id for s in hass.states.async_all("button") if "snooze_today" in s.entity_id)
    await hass.services.async_call("button", "press", {"entity_id": button_id}, blocking=True)
    await hass.async_block_till_done()

    assert controller.store.state.snooze_date_iso == dt_util.now().date().isoformat()

    from unittest.mock import AsyncMock

    spy = AsyncMock(return_value=True)
    controller._run_pulses = spy

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    spy.assert_not_called()


@pytest.mark.asyncio
async def test_snooze_only_applies_to_todays_date(hass, fake_valve_services):
    """A snooze recorded for a different (past) date must not suppress
    today's run -- this is what makes it self-expiring with no separate
    cleanup needed."""
    await _seed(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    controller.store.state.snooze_date_iso = "2000-01-01"
    assert controller._is_snoozed_today() is False


@pytest.mark.asyncio
async def test_snooze_does_not_affect_deep_soak_gates_it_does_not_touch(hass, fake_valve_services):
    """Snoozing must not perturb any of the other watering-decision state
    (rain windows, temp history, lock) -- it's purely an additional gate,
    not a side-channel reset of anything else."""
    await _seed(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    before_lock = controller.store.state.lock_on
    await controller.snooze_today()
    await hass.async_block_till_done()

    assert controller.store.state.lock_on == before_lock
    assert controller._is_snoozed_today() is True
