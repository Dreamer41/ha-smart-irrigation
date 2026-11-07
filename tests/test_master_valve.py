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
    controller, clock, events = await _master_zone(hass, monkeypatch, tmp_path, **{CONF_PUMP_POWER_ENTITY: None})  # no self-test
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
    monkeypatch.setattr(master_valve, "RATE_LEAK_SUSTAIN_SECONDS", 0.0)  # (held rates: see the test below)
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


# --- normally open ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_normally_open_relay_is_switched_on_to_close_it(hass, fake_valve_services, monkeypatch, tmp_path):
    from custom_components.zoneflow.const import CONF_MASTER_VALVE_NORMALLY_OPEN

    controller, clock, events = await _master_zone(
        hass, monkeypatch, tmp_path, **{CONF_MASTER_VALVE_NORMALLY_OPEN: True, CONF_PUMP_POWER_ENTITY: None}
    )
    hass.states.async_set(MASTER, "on")  # relay on: closed
    seen = _sequence(hass)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert "Routine Irrigation Completed" in events
    assert seen[0] == (MASTER, "off") and seen[-1] == (MASTER, "on")
    master = master_valve.get(hass, MASTER)
    assert master.normally_open and master.is_closed(hass.states.get(MASTER))


def test_a_valve_entity_is_never_turned_round(hass):
    assert master_valve.MasterValve(hass, "valve.main_line").normally_open is False


# --- monthly self-test ----------------------------------------------------------------------


async def _test_zone(hass, monkeypatch, tmp_path, **extra):
    controller, clock, events = await _master_zone(hass, monkeypatch, tmp_path, **extra)
    return controller, events


@pytest.mark.asyncio
async def test_the_self_test_passes_when_the_master_stops_the_water(hass, fake_valve_services, monkeypatch, tmp_path):
    hass.states.async_set(METER, "100", {"unit_of_measurement": "L"})
    controller, events = await _test_zone(hass, monkeypatch, tmp_path, **{CONF_FLOW_METER_ENTITY: METER, CONF_PUMP_POWER_ENTITY: None})
    seen = _sequence(hass)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert "Master Valve Test Passed" in events and "Routine Irrigation Completed" in events
    assert controller.store.state.master_test_ok is True and controller.store.state.master_test_ts is not None
    # The test: master closed, then the zone valve opened and closed again with it shut.
    tail = seen[-3:]
    assert tail == [(VALVE, "on"), (VALVE, "off"), (MASTER, "off")] or (MASTER, "off") in seen[-4:]
    assert hass.states.get(VALVE).state == "off" and hass.states.get(MASTER).state == "off"
    # Not again until a month has passed.
    events.clear()
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert not any(e.startswith("Master Valve Test") for e in events)


@pytest.mark.asyncio
async def test_the_self_test_fails_when_the_pump_keeps_running(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, events = await _test_zone(hass, monkeypatch, tmp_path)  # pump power reads 999 W throughout
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert "Master Valve Test Failed" in events
    assert controller.store.state.master_test_ok is False
    assert hass.states.get(VALVE).state == "off" and hass.states.get(MASTER).state == "off"
    assert not controller.store.state.lock_on


@pytest.mark.asyncio
async def test_the_zone_valve_is_closed_even_when_the_self_test_breaks(hass, fake_valve_services, monkeypatch, tmp_path):
    hass.states.async_set(METER, "100", {"unit_of_measurement": "L"})
    controller, events = await _test_zone(hass, monkeypatch, tmp_path, **{CONF_FLOW_METER_ENTITY: METER, CONF_PUMP_POWER_ENTITY: None})

    def broken(*_args):
        raise RuntimeError("meter exploded")

    monkeypatch.setattr(master_valve, "test_passed", broken)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert hass.states.get(VALVE).state == "off" and hass.states.get(MASTER).state == "off"
    assert controller.store.state.master_test_ts is None  # no verdict recorded
    assert controller.store.state.master_valve_latch is None


@pytest.mark.asyncio
async def test_no_self_test_without_a_meter_or_pump_power(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, events = await _test_zone(hass, monkeypatch, tmp_path, **{CONF_PUMP_POWER_ENTITY: None})
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert not any(e.startswith("Master Valve Test") for e in events)
    assert controller.store.state.master_test_ts is None


@pytest.mark.asyncio
async def test_the_checked_button_forgets_a_failed_test_so_it_runs_again(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, events = await _test_zone(hass, monkeypatch, tmp_path)  # pump power reads 999 W throughout
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert controller.store.state.master_test_ok is False
    assert not controller._master().test_due(controller.store.state.master_test_ts + 86400)  # not for 30 days
    await controller.master_valve_checked()
    assert controller.store.state.master_test_ts is None and controller.store.state.master_test_ok is None
    assert controller._master().test_due(0.0)
    assert "Master Valve Checked" in events
    hass.states.async_set(PUMP, "0")
    events.clear()
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert controller.store.state.master_test_ok is True


@pytest.mark.asyncio
async def test_the_checked_button_does_nothing_without_a_master(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    await controller.master_valve_checked()
    assert "Master Valve Checked" not in events


@pytest.mark.asyncio
async def test_a_master_that_fails_to_open_does_not_leave_a_stale_holder(hass, monkeypatch):
    from types import SimpleNamespace

    from custom_components.zoneflow import master_valve as mv

    monkeypatch.setattr(mv, "OPEN_CONFIRM_SECONDS", 0.0)
    master = mv.get(hass, MASTER)
    hass.states.async_set(MASTER, "off")

    async def boom():
        raise RuntimeError("device timeout")

    monkeypatch.setattr(master, "_send_open", boom)
    zone = SimpleNamespace(entry=SimpleNamespace(entry_id="zone-1"))
    await master.async_acquire(zone)  # the run goes on (the pump audit catches a dead-headed pump)
    assert master.holders == {"zone-1"}
    await master.async_release(zone, valve_closed=True)
    assert master.holders == set()


@pytest.mark.asyncio
async def test_a_restart_in_the_middle_of_a_run_closes_the_master_too(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _clock, _events = await _master_zone(hass, monkeypatch, tmp_path)
    await controller._set_lock(True)
    controller.store.state.lock_set_ts = controller._setup_ts - 600  # taken before this start: stale
    for entity in (VALVE, MASTER):
        hass.states.async_set(entity, "on")
    await hass.async_block_till_done()
    await controller._on_startup(None)
    await hass.async_block_till_done()
    assert hass.states.get(VALVE).state == "off" and hass.states.get(MASTER).state == "off"


@pytest.mark.asyncio
async def test_a_run_cancelled_while_the_master_opens_holds_nothing(hass, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from custom_components.zoneflow import master_valve as mv

    master = mv.get(hass, MASTER)
    hass.states.async_set(MASTER, "off")

    async def never():
        await asyncio.sleep(3600)

    monkeypatch.setattr(master, "_confirmed", lambda **kw: never())
    task = asyncio.ensure_future(master.async_acquire(SimpleNamespace(entry=SimpleNamespace(entry_id="zone-1"))))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert master.holders == set()


@pytest.mark.asyncio
async def test_a_rate_that_a_meter_holds_after_the_water_stops_is_not_a_leak(hass, fake_valve_services, monkeypatch, tmp_path):
    from types import SimpleNamespace

    hass.states.async_set(METER, "0", {"unit_of_measurement": "L/min"})
    controller, clock, events = await _master_zone(
        hass, monkeypatch, tmp_path, **{CONF_FLOW_METER_ENTITY: METER, CONF_PUMP_POWER_ENTITY: None}
    )
    now = [1000.0]
    monkeypatch.setattr(master_valve, "dt_util", SimpleNamespace(utcnow=lambda: SimpleNamespace(timestamp=lambda: now[0])))
    hass.states.async_set(METER, "12", {"unit_of_measurement": "L/min"})  # the last rate, held
    baseline: dict = {}
    assert master_valve.flow_while_closed(controller, baseline, True) is None
    now[0] += 120
    assert master_valve.flow_while_closed(controller, baseline, False) is None
    hass.states.async_set(METER, "0", {"unit_of_measurement": "L/min"})  # the meter's timeout: it lets go
    now[0] += 120
    assert master_valve.flow_while_closed(controller, baseline, False) is None
    hass.states.async_set(METER, "5", {"unit_of_measurement": "L/min"})  # now water really runs
    assert master_valve.flow_while_closed(controller, baseline, False) is None
    now[0] += master_valve.RATE_LEAK_SUSTAIN_SECONDS + 1
    assert master_valve.flow_while_closed(controller, baseline, False) == master_valve.REASON_FLOW


@pytest.mark.asyncio
async def test_litres_that_a_slow_total_meter_delivers_late_are_not_a_leak(hass, fake_valve_services, monkeypatch, tmp_path):
    hass.states.async_set(METER, "100", {"unit_of_measurement": "L"})
    controller, clock, events = await _master_zone(
        hass, monkeypatch, tmp_path, **{CONF_FLOW_METER_ENTITY: METER, CONF_PUMP_POWER_ENTITY: None}
    )
    baseline: dict = {}
    assert master_valve.flow_while_closed(controller, baseline, True) is None
    hass.states.async_set(METER, "108", {"unit_of_measurement": "L"})  # the last of the water, reported late
    assert master_valve.flow_while_closed(controller, baseline, False) is None
    assert master_valve.flow_while_closed(controller, baseline, False) is None  # and nothing more
    hass.states.async_set(METER, "112", {"unit_of_measurement": "L"})
    assert master_valve.flow_while_closed(controller, baseline, False) is None
    hass.states.async_set(METER, "116", {"unit_of_measurement": "L"})  # still counting: a leak
    assert master_valve.flow_while_closed(controller, baseline, False) == master_valve.REASON_FLOW
