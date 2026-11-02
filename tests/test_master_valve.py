"""1.8: a master (backup) shut-off valve upstream of several zones. It opens before a run's first pulse and
closes after its last; zones that share it keep it open while any of them waters. It closes for safety,
and stays closed until Reset Lock, when a zone valve doesn't confirm it closed, when the stuck-valve
watchdog fires, or when water still flows or the pump still runs while every zone valve is closed."""
from __future__ import annotations

import pytest

from custom_components.zoneflow import master_valve
from custom_components.zoneflow.config_flow import _duplicate_errors
from custom_components.zoneflow.const import (
    CONF_FLOW_METER_ENTITY,
    CONF_MASTER_VALVE_ENTITY,
    CONF_PUMP_POWER_ENTITY,
    CONF_VALVE_ENTITY,
    CONF_ZONE_NAME,
    DOMAIN,
)

from .test_scenarios_cycles import _history, _zone
from .test_smoke_setup import PUMP, VALVE, make_entry

MASTER = "switch.master_valve"
METER = "sensor.water_meter"
VALVE_2 = "switch.second_valve"


def _sequence(hass):
    """The on/off changes of the zone valve and the master, in order."""
    seen: list[tuple[str, str]] = []

    def listener(event):
        new = event.data.get("new_state")
        if new is not None and event.data["entity_id"] in (VALVE, MASTER, VALVE_2):
            old = event.data.get("old_state")
            if old is None or old.state != new.state:
                seen.append((event.data["entity_id"], new.state))

    hass.bus.async_listen("state_changed", listener)
    return seen


async def _master_zone(hass, monkeypatch, tmp_path, **extra):
    hass.states.async_set(MASTER, "off")
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path, **{CONF_MASTER_VALVE_ENTITY: MASTER, **extra})
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    return controller, clock, events


@pytest.mark.asyncio
async def test_the_master_opens_before_the_zone_valve_and_closes_after_it(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _master_zone(hass, monkeypatch, tmp_path)
    seen = _sequence(hass)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert "Routine Irrigation Completed" in events
    assert seen[0] == (MASTER, "on") and seen[-1] == (MASTER, "off")
    assert all(entity == VALVE for entity, _ in seen[1:-1]) and (VALVE, "on") in seen
    assert hass.states.get(MASTER).state == "off"
    assert not controller.store.state.lock_on


@pytest.mark.asyncio
async def test_a_zone_without_a_master_never_touches_one(hass, fake_valve_services, monkeypatch, tmp_path):
    hass.states.async_set(MASTER, "off")
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    seen = _sequence(hass)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert controller.master_valve_entity is None
    assert all(entity != MASTER for entity, _ in seen)


@pytest.mark.asyncio
async def test_zones_sharing_a_master_keep_it_open_until_the_last_run_ends(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _master_zone(hass, monkeypatch, tmp_path)
    hass.states.async_set(VALVE_2, "off")
    second = make_entry(hass, **{CONF_ZONE_NAME: "Second", CONF_VALVE_ENTITY: VALVE_2, CONF_MASTER_VALVE_ENTITY: MASTER,
                                 "csv_path": str(tmp_path / "second.csv")})
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()
    other = hass.data[DOMAIN][second.entry_id]
    master = master_valve.get(hass, MASTER)
    await master.async_acquire(controller)
    await master.async_acquire(other)
    assert hass.states.get(MASTER).state == "on"
    await master.async_release(controller, valve_closed=True)
    assert hass.states.get(MASTER).state == "on"  # the second zone still waters
    await master.async_release(other, valve_closed=True)
    assert hass.states.get(MASTER).state == "off"


@pytest.mark.asyncio
async def test_a_zone_valve_that_does_not_close_closes_the_master_until_reset(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _master_zone(hass, monkeypatch, tmp_path)
    master = master_valve.get(hass, MASTER)
    await master.async_acquire(controller)
    hass.states.async_set(VALVE, "on")  # stuck
    await master.async_release(controller, valve_closed=False)
    await hass.async_block_till_done()
    assert hass.states.get(MASTER).state == "off"
    assert controller.store.state.master_valve_latch == master_valve.REASON_VALVE_NOT_CLOSED
    assert "Master Valve Closed" in events
    # Nothing waters behind it until Reset Lock.
    hass.states.async_set(VALVE, "off")
    events.clear()
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert "Routine Irrigation Refused (Master Valve Closed)" in events
    assert hass.states.get(MASTER).state == "off" and not controller.store.state.lock_on
    await controller.reset_lock()
    assert controller.store.state.master_valve_latch is None
    events.clear()
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert "Routine Irrigation Completed" in events


@pytest.mark.asyncio
async def test_the_stuck_valve_watchdog_closes_the_master(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _master_zone(hass, monkeypatch, tmp_path)
    hass.states.async_set(MASTER, "on")
    await controller._fire_valve_stuck()
    await hass.async_block_till_done()
    assert hass.states.get(MASTER).state == "off"
    assert controller.store.state.master_valve_latch == master_valve.REASON_VALVE_STUCK


@pytest.mark.asyncio
async def test_pump_power_in_a_soak_closes_the_master_and_stops_the_run(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _master_zone(hass, monkeypatch, tmp_path)
    master = master_valve.get(hass, MASTER)
    await master.async_acquire(controller)
    controller.store.state.lock_on = True
    hass.states.async_set(VALVE, "on")
    hass.states.async_set(VALVE, "off")  # a soak between pulses
    await hass.async_block_till_done()
    assert master.holders and not master.open_valves
    hass.states.async_set(PUMP, "999")  # the pump still runs: water goes somewhere
    await master._async_check()
    await hass.async_block_till_done()
    assert hass.states.get(MASTER).state == "off"
    assert controller.store.state.master_valve_latch == master_valve.REASON_PUMP_POWER
    assert controller.store.state.abort_on and not controller.store.state.lock_on


@pytest.mark.asyncio
async def test_a_quiet_pump_in_a_soak_leaves_the_master_open(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _master_zone(hass, monkeypatch, tmp_path)
    master = master_valve.get(hass, MASTER)
    await master.async_acquire(controller)
    hass.states.async_set(VALVE, "on")
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "0")
    await hass.async_block_till_done()
    await master._async_check()
    await master._async_check()
    assert hass.states.get(MASTER).state == "on" and controller.store.state.master_valve_latch is None
    await master.async_release(controller, valve_closed=True)
    assert hass.states.get(MASTER).state == "off" and master._unsub_check is None


@pytest.mark.asyncio
async def test_a_flow_meter_counting_in_a_soak_closes_the_master(hass, fake_valve_services, monkeypatch, tmp_path):
    hass.states.async_set(METER, "100", {"unit_of_measurement": "L"})
    controller, clock, events = await _master_zone(
        hass, monkeypatch, tmp_path, **{CONF_FLOW_METER_ENTITY: METER, CONF_PUMP_POWER_ENTITY: None}
    )
    master = master_valve.get(hass, MASTER)
    await master.async_acquire(controller)
    hass.states.async_set(VALVE, "on")
    hass.states.async_set(VALVE, "off")
    await hass.async_block_till_done()
    await master._async_check()  # the first reading after the valve settled
    hass.states.async_set(METER, "101", {"unit_of_measurement": "L"})
    await master._async_check()
    assert hass.states.get(MASTER).state == "on"  # 1 L: a meter reporting late, not a leak
    hass.states.async_set(METER, "103.5", {"unit_of_measurement": "L"})
    await master._async_check()
    await hass.async_block_till_done()
    assert hass.states.get(MASTER).state == "off"
    assert controller.store.state.master_valve_latch == master_valve.REASON_FLOW


@pytest.mark.asyncio
async def test_a_rate_meter_showing_flow_in_a_soak_closes_the_master(hass, fake_valve_services, monkeypatch, tmp_path):
    hass.states.async_set(METER, "0", {"unit_of_measurement": "L/min"})
    controller, clock, events = await _master_zone(
        hass, monkeypatch, tmp_path, **{CONF_FLOW_METER_ENTITY: METER, CONF_PUMP_POWER_ENTITY: None}
    )
    master = master_valve.get(hass, MASTER)
    await master.async_acquire(controller)
    hass.states.async_set(VALVE, "on")
    hass.states.async_set(VALVE, "off")
    await hass.async_block_till_done()
    await master._async_check()
    assert hass.states.get(MASTER).state == "on"
    hass.states.async_set(METER, "4.2", {"unit_of_measurement": "L/min"})
    await master._async_check()
    await hass.async_block_till_done()
    assert controller.store.state.master_valve_latch == master_valve.REASON_FLOW


@pytest.mark.asyncio
async def test_a_master_left_open_by_a_restart_is_closed(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _master_zone(hass, monkeypatch, tmp_path)
    hass.states.async_set(MASTER, "on")
    await master_valve.get(hass, MASTER).async_close_if_idle()
    assert hass.states.get(MASTER).state == "off"


@pytest.mark.asyncio
async def test_the_latch_survives_a_restart(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _master_zone(hass, monkeypatch, tmp_path)
    master = master_valve.get(hass, MASTER)
    await master.async_acquire(controller)
    await master.async_release(controller, valve_closed=False)
    entry_id = controller.entry.entry_id
    assert await hass.config_entries.async_reload(entry_id)
    await hass.async_block_till_done()
    reloaded = hass.data[DOMAIN][entry_id]
    assert reloaded.store.state.master_valve_latch == master_valve.REASON_VALVE_NOT_CLOSED
    assert master_valve.get(hass, MASTER).latched


@pytest.mark.asyncio
async def test_the_setup_refuses_a_master_that_is_a_zone_valve(hass):
    assert _duplicate_errors(hass, {CONF_VALVE_ENTITY: VALVE, CONF_MASTER_VALVE_ENTITY: VALVE}) == {
        CONF_MASTER_VALVE_ENTITY: "master_is_zone_valve"
    }
    make_entry(hass, **{CONF_VALVE_ENTITY: VALVE_2, CONF_MASTER_VALVE_ENTITY: MASTER, "csv_path": "/tmp/a.csv"})
    assert _duplicate_errors(hass, {CONF_VALVE_ENTITY: MASTER})[CONF_VALVE_ENTITY] == "valve_is_a_master"
    assert _duplicate_errors(hass, {CONF_VALVE_ENTITY: VALVE, CONF_MASTER_VALVE_ENTITY: VALVE_2})[
        CONF_MASTER_VALVE_ENTITY
    ] == "master_is_zone_valve"
