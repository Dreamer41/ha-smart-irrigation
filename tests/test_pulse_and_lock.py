"""Does a real pulse actually flip the valve, and does the mutex lock really
stop a second run from stepping on a first one?

test_pulse is the integration's own bench-test helper (see its docstring in
controller.py) -- a single short pulse that still goes through the full
lock + watchdog machinery, specifically so this can be checked before ever
trusting the daily-schedule path against a real valve.
"""
import asyncio
from unittest.mock import AsyncMock

import pytest

from custom_components.zoneflow.const import DOMAIN, NUMBER_DEFAULTS

from .test_smoke_setup import PUMP, VALVE, _seed_source_entities, make_entry


async def _setup_with_pump_ready(hass):
    await _seed_source_entities(hass)
    # Pump power above the default minimum so the pump-power wait resolves
    # immediately instead of polling for 45s.
    hass.states.async_set(PUMP, NUMBER_DEFAULTS["pump_min_watts"] + 50)
    await hass.async_block_till_done()
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.asyncio
async def test_pulse_cycles_the_real_valve_and_releases_the_lock(hass, fake_valve_services):
    entry = await _setup_with_pump_ready(hass)
    controller = hass.data[DOMAIN][entry.entry_id]

    seen_states: list[str] = []

    unsub = hass.bus.async_listen(
        "state_changed",
        lambda event: seen_states.append(event.data["new_state"].state)
        if event.data.get("entity_id") == VALVE
        else None,
    )
    try:
        await hass.services.async_call(DOMAIN, "test_pulse", {"seconds": 1}, blocking=True)
        await hass.async_block_till_done()
    finally:
        unsub()

    assert "on" in seen_states, "the valve never actually turned on during the pulse"
    assert hass.states.get(VALVE).state == "off"
    assert controller.store.state.lock_on is False
    assert controller.store.state.abort_on is False


@pytest.mark.asyncio
async def test_concurrent_test_pulse_calls_do_not_both_run(hass, fake_valve_services):
    """This is exactly the bug that used to exist here: run_deep_soak and
    run_routine_irrigation were once wrapped in an asyncio.Lock, which would
    make a second call WAIT and then run anyway, rather than being skipped
    like the YAML's simple `if lock_on: return` does. Confirms the fix
    holds: a second call while locked must be skipped, not merely delayed.
    """
    entry = await _setup_with_pump_ready(hass)
    controller = hass.data[DOMAIN][entry.entry_id]

    spy = AsyncMock(wraps=controller._run_pulses)
    controller._run_pulses = spy

    await asyncio.gather(controller.test_pulse(1), controller.test_pulse(1))
    await hass.async_block_till_done()

    assert spy.call_count == 1, "a second concurrent call ran a pulse instead of being skipped by the lock"
    assert controller.store.state.lock_on is False
    assert hass.states.get(VALVE).state == "off"


@pytest.mark.asyncio
async def test_reset_lock_service_clears_lock_and_abort(hass, fake_valve_services):
    entry = await _setup_with_pump_ready(hass)
    controller = hass.data[DOMAIN][entry.entry_id]

    await controller._set_lock(True)
    await controller._set_abort(True)
    assert controller.store.state.lock_on is True
    assert controller.store.state.abort_on is True

    await hass.services.async_call(DOMAIN, "reset_lock", {}, blocking=True)
    await hass.async_block_till_done()

    assert controller.store.state.lock_on is False
    assert controller.store.state.abort_on is False
