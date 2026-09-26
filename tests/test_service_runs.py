"""Service / check runs: the 1/5/10 min buttons and the Service Mode switch.

For checking emitters, flushing a line or finding a leak. They take the zone
lock and the shared pump and go through the same pulse, watchdog and
confirmed-valve-close path as a real cycle, but are never counted as
watering: Last Routine / Last Deep Soak and the schedule don't move. Their
minutes do count toward the daily runtime safety cap.
"""
from __future__ import annotations

import asyncio

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.zoneflow.const import DOMAIN

from .test_scenarios_cycles import _history, _set, _zone
from .test_smoke_setup import VALVE


def _entity(hass, domain, suffix):
    return next(s.entity_id for s in hass.states.async_all(domain) if s.entity_id.endswith(suffix))


def _switch(hass, entity_id):
    """The switch entity itself -- the suite's fake valve services own
    switch.turn_on/turn_off, so the service can't reach it."""
    from homeassistant.helpers.entity_component import DATA_INSTANCES

    return hass.data[DATA_INSTANCES]["switch"].get_entity(entity_id)


async def _service_zone(hass, monkeypatch, tmp_path):
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=1, last_deep_days_ago=3, peaks=(30.5, 30.5, 30.5))
    return controller, clock, events


async def _wait_until(predicate, seconds=3.0):
    for _ in range(int(seconds * 100)):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not reached")


@pytest.mark.asyncio
@pytest.mark.parametrize("minutes", [1, 5, 10])
async def test_service_run_button_runs_the_valve_and_is_not_counted_as_watering(
    hass, fake_valve_services, monkeypatch, tmp_path, minutes
):
    controller, clock, events = await _service_zone(hass, monkeypatch, tmp_path)
    state = controller.store.state
    last_routine, last_deep = state.last_routine_ts, state.last_deep_soak_ts
    next_before = controller.routine_next_estimate()

    await hass.services.async_call(
        "button", "press", {"entity_id": _entity(hass, "button", f"service_run_{minutes}_min")}, blocking=True
    )
    await hass.async_block_till_done()

    assert clock.pulses_for(VALVE) == [minutes]
    assert hass.states.get(VALVE).state == "off"
    assert state.lock_on is False and controller.service_active is False
    # Not watering: nothing that decides watering moved.
    assert (state.last_routine_ts, state.last_deep_soak_ts) == (last_routine, last_deep)
    assert controller.routine_next_estimate() == next_before
    # But it's water through the pump: it counts toward the daily safety cap.
    assert state.today_runtime_minutes == pytest.approx(minutes)
    assert events[-1] == "Service Run"


@pytest.mark.asyncio
async def test_service_mode_switch_runs_until_switched_off(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _service_zone(hass, monkeypatch, tmp_path)
    clock.pulse_real_seconds = 10  # the valve really stays open until switched off
    switch_id = _entity(hass, "switch", "service_mode")
    switch = _switch(hass, switch_id)

    await switch.async_turn_on()
    await _wait_until(lambda: hass.states.get(VALVE).state == "on")
    assert hass.states.get(switch_id).state == "on"
    assert controller.store.state.lock_on is True

    await switch.async_turn_off()
    await _wait_until(lambda: not controller.service_active)
    await hass.async_block_till_done()

    assert hass.states.get(VALVE).state == "off"
    assert hass.states.get(switch_id).state == "off"
    assert controller.store.state.lock_on is False
    assert events[-1] == "Service Run"
    assert "Service Run Interrupted" not in events
    # The pulse was planned for the auto-off time (30 min) but ended early.
    assert clock.pulses_for(VALVE) == [30.0]
    assert controller.store.state.today_runtime_minutes < 1.0


@pytest.mark.asyncio
async def test_service_mode_switches_itself_off_after_the_auto_off_time(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _service_zone(hass, monkeypatch, tmp_path)
    await _set(controller, service_mode_auto_off_minutes=15)
    notified = []
    real_log = controller._log_event

    async def spy(**kwargs):
        if kwargs.get("notify_phone"):
            notified.append(kwargs["phone_title"])
        await real_log(**kwargs)

    controller._log_event = spy
    switch_id = _entity(hass, "switch", "service_mode")

    await _switch(hass, switch_id).async_turn_on()
    await hass.async_block_till_done()

    assert clock.pulses_for(VALVE) == [15.0]
    assert hass.states.get(VALVE).state == "off"
    assert hass.states.get(switch_id).state == "off"
    assert controller.store.state.today_runtime_minutes == pytest.approx(15.0)
    assert notified == ["🔧 Service Mode switched off"]


@pytest.mark.asyncio
async def test_service_run_is_refused_while_the_zone_is_busy(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _service_zone(hass, monkeypatch, tmp_path)
    controller.store.state.lock_on = True
    with pytest.raises(ServiceValidationError):
        await controller.start_service_run(5)
    controller.store.state.lock_on = False

    # A zone on the same pump is running: the pump is busy.
    pump_lock = controller._get_pump_lock()
    await pump_lock.acquire()
    try:
        with pytest.raises(ServiceValidationError):
            await controller.start_service_run(5)
    finally:
        pump_lock.release()
    assert clock.pulses == []


@pytest.mark.asyncio
async def test_service_run_respects_the_daily_safety_cap(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _service_zone(hass, monkeypatch, tmp_path)
    state = controller.store.state
    cap = controller.number("max_daily_runtime_minutes")

    state.today_runtime_minutes = cap
    with pytest.raises(ServiceValidationError):
        await controller.start_service_run(1)

    # Only 3 minutes of room left: a 10-minute run is shortened to fit.
    state.today_runtime_minutes = cap - 3
    await controller.start_service_run(10)
    await hass.async_block_till_done()
    assert clock.pulses_for(VALVE) == [3.0]
    assert state.today_runtime_minutes == pytest.approx(cap)


@pytest.mark.asyncio
async def test_a_scheduled_cycle_during_a_service_run_is_skipped_and_logged(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _service_zone(hass, monkeypatch, tmp_path)
    controller.store.state.last_routine_ts -= 5 * 86400  # routine due
    clock.pulse_real_seconds = 10

    await controller.start_service_run(10)
    await _wait_until(lambda: hass.states.get(VALVE).state == "on")
    await controller.run_routine_irrigation()
    await _wait_until(lambda: "Routine Irrigation Skipped (Service Run)" in events)

    await controller.stop_service_run()
    await _wait_until(lambda: not controller.service_active)
    await hass.async_block_till_done()
    assert clock.pulses_for(VALVE) == [10.0]  # only the service run opened it
    assert hass.states.get(VALVE).state == "off"


@pytest.mark.asyncio
async def test_a_reload_during_a_service_run_closes_the_valve(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _service_zone(hass, monkeypatch, tmp_path)
    entry = controller.entry
    clock.pulse_real_seconds = 10

    await controller.start_service_run(10)
    await _wait_until(lambda: hass.states.get(VALVE).state == "on")
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    new = hass.data[DOMAIN][entry.entry_id]
    assert new is not controller
    assert hass.states.get(VALVE).state == "off"
    assert new.store.state.lock_on is False
    assert new.service_active is False
    assert "Service Run Interrupted" in events


@pytest.mark.asyncio
async def test_new_entities_exist(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _, _ = await _service_zone(hass, monkeypatch, tmp_path)
    for minutes in (1, 5, 10):
        assert _entity(hass, "button", f"service_run_{minutes}_min")
    assert hass.states.get(_entity(hass, "switch", "service_mode")).state == "off"
    auto_off = _entity(hass, "number", "service_mode_auto_off")
    assert float(hass.states.get(auto_off).state) == 30.0


@pytest.mark.asyncio
async def test_no_service_run_while_a_cycle_is_still_checking_its_gates(hass, fake_valve_services, monkeypatch, tmp_path):
    """Regression (review): a deep soak waiting on its forecast check hadn't
    taken the lock yet, a service run was accepted, and the soak then ran
    alongside it -- and ended up running with no lock at all."""
    controller, clock, _ = await _service_zone(hass, monkeypatch, tmp_path)
    controller.store.state.last_deep_soak_ts -= 30 * 86400  # deep soak due
    gate_open = asyncio.Event()

    async def slow_forecast_gate(kind):
        await gate_open.wait()
        return True

    controller._forecast_gate_allows_run = slow_forecast_gate
    soak = hass.async_create_task(controller.run_deep_soak())
    await asyncio.sleep(0.05)
    with pytest.raises(ServiceValidationError):
        await controller.start_service_run(5)
    gate_open.set()
    await soak
    await hass.async_block_till_done()
    assert controller.store.state.lock_on is False
    assert clock.pulses_for(VALVE) and controller.service_active is False


@pytest.mark.asyncio
async def test_a_cycle_that_started_its_checks_after_the_service_run_backs_off(hass, fake_valve_services, monkeypatch, tmp_path):
    """The other order: the service run is accepted first, a scheduled cycle
    starts before the service task has taken the lock -- the cycle must not
    run."""
    controller, clock, _ = await _service_zone(hass, monkeypatch, tmp_path)
    controller.store.state.last_deep_soak_ts -= 30 * 86400
    clock.pulse_real_seconds = 10
    await controller.start_service_run(5)  # flag set, task not yet running
    await controller.run_deep_soak()
    await _wait_until(lambda: hass.states.get(VALVE).state == "on")
    await controller.stop_service_run()
    await _wait_until(lambda: not controller.service_active)
    await hass.async_block_till_done()
    assert clock.pulses_for(VALVE) == [5.0]  # only the service run


@pytest.mark.asyncio
async def test_switching_off_with_a_valve_that_wont_close_keeps_the_lock_and_alerts(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    """Regression (review): the stop ignored an unconfirmed close, released
    the lock and logged a clean "Stopped"."""
    from custom_components.zoneflow import controller as controller_module

    controller, clock, events = await _service_zone(hass, monkeypatch, tmp_path)
    monkeypatch.setattr(controller_module, "VALVE_CLOSE_CONFIRM_SECONDS", 0.2)
    clock.pulse_real_seconds = 10
    await controller.start_service_run(10)
    await _wait_until(lambda: hass.states.get(VALVE).state == "on")

    async def ignored_turn_off(call):
        return None  # the valve ignores it and stays on

    hass.services.async_register("switch", "turn_off", ignored_turn_off)
    await controller.stop_service_run()
    await _wait_until(lambda: not controller.service_active)
    await hass.async_block_till_done()

    assert "Service Run Error" in events
    assert controller.store.state.lock_on is True  # the watchdogs stay in charge
    assert "Service Run" not in events


@pytest.mark.asyncio
async def test_a_power_loss_abort_during_a_service_run_ends_it_cleanly(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _service_zone(hass, monkeypatch, tmp_path)
    clock.pulse_real_seconds = 10
    await controller.start_service_run(10)
    await _wait_until(lambda: hass.states.get(VALVE).state == "on")
    await controller._set_abort(True)
    await _wait_until(lambda: not controller.service_active)
    await hass.async_block_till_done()
    assert hass.states.get(VALVE).state == "off"


@pytest.mark.asyncio
async def test_reset_lock_also_ends_a_service_run(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _service_zone(hass, monkeypatch, tmp_path)
    clock.pulse_real_seconds = 10
    await controller.start_service_run(10)
    await _wait_until(lambda: hass.states.get(VALVE).state == "on")
    await controller.reset_lock()
    await _wait_until(lambda: not controller.service_active)
    await hass.async_block_till_done()
    assert hass.states.get(VALVE).state == "off"


@pytest.mark.asyncio
async def test_skip_row_only_when_the_cycle_was_due(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _service_zone(hass, monkeypatch, tmp_path)  # soak 3 days old: not due
    clock.pulse_real_seconds = 10
    await controller.start_service_run(10)
    await _wait_until(lambda: hass.states.get(VALVE).state == "on")
    await controller.run_deep_soak()
    await asyncio.sleep(0.05)
    assert "Deep Soak Skipped (Service Run)" not in events
    await controller.stop_service_run()
    await _wait_until(lambda: not controller.service_active)
    await hass.async_block_till_done()
