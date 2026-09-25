"""The five safety watchdogs, exercised with real Home Assistant time-travel
(async_fire_time_changed) instead of waiting real minutes.

These are the highest-stakes code paths in the whole integration -- they're
what protects the trees (and the water bill) if something goes wrong mid
cycle -- so they get their own file.
"""
from datetime import timedelta

import homeassistant.util.dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.zoneflow.const import DOMAIN

from .test_smoke_setup import VALVE, _seed_source_entities, make_entry


async def _setup(hass):
    await _seed_source_entities(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.asyncio
async def test_valve_stuck_on_watchdog_forces_off_after_150_minutes(hass, fake_valve_services):
    entry = await _setup(hass)
    controller = hass.data[DOMAIN][entry.entry_id]

    hass.states.async_set(VALVE, "on")
    await hass.async_block_till_done()

    # Not yet due at 149 minutes -- the valve should still be reported on.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=149))
    await hass.async_block_till_done()
    assert hass.states.get(VALVE).state == "on"

    # Due at 151 minutes.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=151))
    await hass.async_block_till_done()

    assert hass.states.get(VALVE).state == "off"
    assert controller.store.state.abort_on is True
    assert controller.store.state.lock_on is False


@pytest.mark.asyncio
async def test_power_loss_mid_cycle_aborts_after_10_minutes(hass, fake_valve_services):
    entry = await _setup(hass)
    controller = hass.data[DOMAIN][entry.entry_id]

    # Simulate a run genuinely in progress.
    await controller._set_lock(True)

    hass.states.async_set(VALVE, "unavailable")
    await hass.async_block_till_done()

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=11))
    await hass.async_block_till_done()

    assert controller.store.state.abort_on is True
    assert controller.store.state.lock_on is False


@pytest.mark.asyncio
async def test_power_loss_watchdog_is_a_no_op_when_nothing_was_running(hass, fake_valve_services):
    """The valve merely being unreachable while idle (no lock held) is not
    a mid-cycle power loss and must not trip an abort."""
    await _setup(hass)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    controller = hass.data[DOMAIN][entry.entry_id]

    hass.states.async_set(VALVE, "unavailable")
    await hass.async_block_till_done()

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=11))
    await hass.async_block_till_done()

    assert controller.store.state.abort_on is False


@pytest.mark.asyncio
async def test_power_restore_anomaly_forces_valve_off(hass, fake_valve_services):
    await _setup(hass)

    hass.states.async_set(VALVE, "unavailable")
    await hass.async_block_till_done()
    # Valve comes back online but incorrectly reports itself ON.
    hass.states.async_set(VALVE, "on")
    await hass.async_block_till_done()

    assert hass.states.get(VALVE).state == "off"


@pytest.mark.asyncio
async def test_stale_lock_watchdog_clears_after_180_minutes(hass, fake_valve_services):
    entry = await _setup(hass)
    controller = hass.data[DOMAIN][entry.entry_id]

    await controller._set_lock(True)
    assert controller.store.state.lock_on is True

    # Not yet due at 179 minutes.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=179))
    await hass.async_block_till_done()
    assert controller.store.state.lock_on is True

    # Due at 181 minutes.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=181))
    await hass.async_block_till_done()
    assert controller.store.state.lock_on is False


@pytest.mark.asyncio
async def test_stale_lock_on_startup_clears_lock_and_forces_valve_off(hass, fake_valve_services):
    """Port of avocado_stale_lock_on_startup / avocado_startup_lock_reset:
    if HA restarts mid-cycle, the persisted lock from before the restart
    must not permanently block future runs."""
    await _seed_source_entities(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    # Simulate "HA restarted while a cycle was running": lock left on, valve
    # left on, from before this (simulated) restart.
    await controller._set_lock(True)
    controller.store.state.lock_set_ts = controller._setup_ts - 600  # taken before the restart
    hass.states.async_set(VALVE, "on")
    await hass.async_block_till_done()

    await controller._on_startup(None)
    await hass.async_block_till_done()

    assert controller.store.state.lock_on is False
    assert controller.store.state.abort_on is False
    assert hass.states.get(VALVE).state == "off"


@pytest.mark.asyncio
async def test_valve_already_open_at_startup_still_gets_the_stuck_valve_cutoff(hass, fake_valve_services):
    """Regression: after a restart mid-cycle the valve is restored "on"
    before ZoneFlow starts listening, so no "turned on" event ever arrives.
    The stuck-valve watchdog must be armed at setup anyway."""
    await _seed_source_entities(hass)
    hass.states.async_set(VALVE, "on")
    await hass.async_block_till_done()
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=151))
    await hass.async_block_till_done()
    assert hass.states.get(VALVE).state == "off"


@pytest.mark.asyncio
async def test_a_planned_long_pulse_is_not_cut_off_but_a_stuck_one_still_is(hass, fake_valve_services):
    """A slow drip with 1 pulse can legitimately need more than 150 minutes.
    While ZoneFlow itself runs that pulse, the limit is the pulse + 30 min
    margin; a valve that then fails to close is still forced off."""
    entry = await _setup(hass)
    controller = hass.data[DOMAIN][entry.entry_id]

    controller._expected_pulse_minutes = 200  # what _execute_pulses sets before opening
    hass.states.async_set(VALVE, "on")
    await hass.async_block_till_done()

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=151))
    await hass.async_block_till_done()
    assert hass.states.get(VALVE).state == "on"  # still inside its planned pulse

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=231))
    await hass.async_block_till_done()
    assert hass.states.get(VALVE).state == "off"  # 200 + 30 exceeded -> stuck


@pytest.mark.asyncio
async def test_a_manually_opened_valve_keeps_the_plain_150_minute_limit(hass, fake_valve_services):
    entry = await _setup(hass)
    controller = hass.data[DOMAIN][entry.entry_id]
    assert controller._expected_pulse_minutes is None
    hass.states.async_set(VALVE, "on")
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=151))
    await hass.async_block_till_done()
    assert hass.states.get(VALVE).state == "off"



@pytest.mark.asyncio
async def test_startup_check_leaves_a_cycle_that_began_after_startup_alone(hass, fake_valve_services):
    """Regression (seen live in the sandbox): a cycle started within the
    2-minute startup grace period had its lock treated as stale -- the check
    closed the valve 13 s into the run and dropped the lock while the cycle
    carried on. A lock taken after startup must be left alone."""
    entry = await _setup(hass)
    controller = hass.data[DOMAIN][entry.entry_id]

    await controller._set_lock(True)  # a cycle starting now, after setup
    hass.states.async_set(VALVE, "on")
    await hass.async_block_till_done()

    await controller._on_startup(None)
    await hass.async_block_till_done()

    assert controller.store.state.lock_on is True
    assert hass.states.get(VALVE).state == "on"
