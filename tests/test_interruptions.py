"""Cycles that get interrupted part-way: a reload (saving the zone's
settings, flipping its Deep Soak switch), Home Assistant shutting down, the
run being cancelled, the valve switch failing, and rain arriving mid-cycle.

Whatever happens, the valve that was opened must end up closed -- while the
zone still holds the pump, so a zone sharing it can't open alongside -- the
lock must be free (unless the valve could not be confirmed closed), an
interrupted cycle must not count as a finished run, the water it did give
must count toward today's safety cap, and no old cycle may keep running
unsupervised next to the reloaded zone.

Reloads and shutdowns are started from a separate task, as they are in real
life, while the cycle genuinely sits in a pulse or soak gap
(CompressedTime.pulse_real_seconds / sleep_real_seconds); the interruption
wakes it at once.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
import homeassistant.util.dt as dt_util
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.zoneflow import controller as controller_module
from custom_components.zoneflow.const import CONF_VALVE_ENTITY, DOMAIN

from .test_scenarios_cycles import _history, _set, _zone
from .test_smoke_setup import PUMP, RAIN_COUNTER, VALVE, schedule_clear_of_now


async def _due_routine_zone(hass, monkeypatch, tmp_path):
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    return controller, clock, events


def _reload_soon(hass, controller):
    hass.async_create_task(hass.config_entries.async_reload(controller.entry.entry_id))


async def _timed(coro):
    """Runs a cycle; returns how many real seconds it took."""
    loop = asyncio.get_running_loop()
    start = loop.time()
    await coro
    return loop.time() - start


# ---------------------------------------------------------------------------
# Reload mid-cycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_reload_mid_pulse_closes_the_valve_and_the_old_cycle_never_reopens_it(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, clock, events = await _due_routine_zone(hass, monkeypatch, tmp_path)
    entry = controller.entry
    before = controller.store.state.last_routine_ts

    async def reload_during_second_pulse(index):
        if index == 1:
            clock.pulse_real_seconds = 5  # this pulse really waits, until woken
            _reload_soon(hass, controller)

    clock.on_pulse = reload_during_second_pulse
    took = await _timed(controller.run_routine_irrigation())
    await hass.async_block_till_done()

    assert took < 3  # woken at once, not after the pulse
    new = hass.data[DOMAIN][entry.entry_id]
    assert new is not controller
    assert hass.states.get(VALVE).state == "off"
    pulses = clock.pulses_for(VALVE)
    assert len(pulses) == 2  # the first pulse, and the one cut short
    assert "Routine Irrigation Interrupted" in events
    assert "Routine Irrigation Completed" not in events
    assert "Stale Lock Cleared On Startup" not in events
    # The reloaded zone starts clean: not counted as a run, no stuck lock,
    # pump free -- and the minutes given count toward today's cap.
    assert new.store.state.lock_on is False
    assert new.store.state.last_routine_ts == before
    assert new.store.state.today_runtime_minutes == pytest.approx(pulses[0], abs=0.1)
    on_disk = await new.store._store.async_load()
    assert on_disk["lock_on"] is False
    assert on_disk["last_routine_ts"] == before
    assert not new._get_pump_lock().locked()

    # And the reloaded zone waters normally on its next run.
    clock.reset()
    clock.on_pulse = None
    clock.pulse_real_seconds = 0.001
    await new.run_routine_irrigation()
    await hass.async_block_till_done()
    assert len(clock.pulses_for(VALVE)) == 3
    assert new.store.state.last_routine_ts != before


@pytest.mark.asyncio
async def test_a_reload_during_a_soak_gap_ends_the_cycle_at_once_without_another_pulse(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, clock, events = await _due_routine_zone(hass, monkeypatch, tmp_path)
    await _set(controller, routine_pulse_rest_minutes=20)
    clock.sleep_real_seconds = 5
    real_pause = controller._pause
    reloaded = []

    async def pause_then_reload(seconds):
        if not reloaded:
            reloaded.append(True)
            _reload_soon(hass, controller)
        await real_pause(seconds)

    monkeypatch.setattr(controller, "_pause", pause_then_reload)
    took = await _timed(controller.run_routine_irrigation())
    await hass.async_block_till_done()

    assert took < 3  # didn't sit out the soak gap on the pump
    assert len(clock.pulses_for(VALVE)) == 1
    assert hass.states.get(VALVE).state == "off"
    assert hass.data[DOMAIN][controller.entry.entry_id].store.state.lock_on is False
    assert "Routine Irrigation Completed" not in events


@pytest.mark.asyncio
async def test_a_reload_that_changes_the_valve_setting_closes_the_valve_that_was_open(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, clock, events = await _due_routine_zone(hass, monkeypatch, tmp_path)
    entry = controller.entry
    hass.states.async_set("switch.new_valve", "off")

    async def change_valve_during_second_pulse(index):
        if index == 1:
            clock.pulse_real_seconds = 5
            # Saving options reloads the zone (from its own task).
            hass.config_entries.async_update_entry(
                entry, options={**entry.options, CONF_VALVE_ENTITY: "switch.new_valve"}
            )

    clock.on_pulse = change_valve_during_second_pulse
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][entry.entry_id] is not controller
    assert hass.states.get(VALVE).state == "off"
    assert hass.states.get("switch.new_valve").state == "off"
    assert "Routine Irrigation Interrupted" in events


@pytest.mark.asyncio
async def test_a_reload_while_the_valve_has_not_yet_reported_on_still_closes_it(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    """Real devices (Zigbee, MQTT, ESPHome) report "on" a moment after the
    command -- a valve that still reads "off" may be opening."""
    controller, clock, events = await _due_routine_zone(hass, monkeypatch, tmp_path)
    clock.pulse_real_seconds = 5
    calls = {"n": 0}

    async def slow_reporting_turn_on(call):
        calls["n"] += 1
        if calls["n"] == 1:
            _reload_soon(hass, controller)
            await asyncio.sleep(0.2)
        hass.states.async_set(VALVE, "on")

    hass.services.async_register("switch", "turn_on", slow_reporting_turn_on)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert hass.states.get(VALVE).state == "off"
    assert hass.data[DOMAIN][controller.entry.entry_id].store.state.lock_on is False


@pytest.mark.asyncio
async def test_a_valve_that_reports_on_only_after_the_command_returns_is_still_closed(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    """MQTT-style: the command is accepted and the state arrives later, so
    the valve still reads "off" when the reload closes it -- turn_off must
    be sent anyway."""
    controller, clock, events = await _due_routine_zone(hass, monkeypatch, tmp_path)
    clock.pulse_real_seconds = 5
    log = []

    async def turn_on(call):
        hass.loop.call_later(0.05, lambda: (log.append("on"), hass.states.async_set(VALVE, "on")))
        _reload_soon(hass, controller)

    async def turn_off(call):
        log.append("off-cmd")
        hass.loop.call_later(0.1, lambda: (log.append("off"), hass.states.async_set(VALVE, "off")))

    hass.services.async_register("switch", "turn_on", turn_on)
    hass.services.async_register("switch", "turn_off", turn_off)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    await asyncio.sleep(0.3)
    assert "off-cmd" in log
    assert hass.states.get(VALVE).state == "off"


@pytest.mark.asyncio
async def test_a_reload_during_a_long_pump_postamble_keeps_the_finished_run(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    """Everything was delivered: the postamble is cut short, the run is
    recorded as finished (not cancelled), and the reloaded zone knows it
    watered -- or it would water again."""
    controller, clock, events = await _due_routine_zone(hass, monkeypatch, tmp_path)
    await _set(controller, pump_postamble_seconds=45, routine_pulse_rest_minutes=0)
    entry = controller.entry
    before = controller.store.state.last_routine_ts
    clock.sleep_real_seconds = 5  # the postamble really waits, until woken
    real_pause = controller._pause

    async def pause(seconds):
        if seconds == 45:
            _reload_soon(hass, controller)
        await real_pause(seconds)

    monkeypatch.setattr(controller, "_pause", pause)
    took = await _timed(controller.run_routine_irrigation())
    await hass.async_block_till_done()

    assert took < 3
    assert len(clock.pulses_for(VALVE)) == 3
    assert "Routine Irrigation Completed" in events
    assert "Routine Irrigation Interrupted" not in events
    new = hass.data[DOMAIN][entry.entry_id]
    assert new is not controller
    assert new.store.state.last_routine_ts != before
    assert new.store.state.today_runtime_minutes > 0
    clock.reset()
    clock.sleep_real_seconds = 0
    await new.run_routine_irrigation()
    await hass.async_block_till_done()
    assert clock.pulses_for(VALVE) == []  # not due again


@pytest.mark.asyncio
async def test_a_run_still_checking_its_gates_during_a_reload_starts_nothing_and_raises_no_false_alarm(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path, **schedule_clear_of_now())
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))

    async def slow_forecast(cycle):
        # e.g. weather.get_forecasts takes a moment while the zone is saved
        _reload_soon(hass, controller)
        await asyncio.sleep(0.1)
        return True

    monkeypatch.setattr(controller, "_forecast_gate_allows_run", slow_forecast)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert clock.pulses_for(VALVE) == []
    assert controller.store.state.lock_on is False
    assert controller._lock_stale_cancel is None
    events.clear()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=181))
    await hass.async_block_till_done()
    assert "Stale Lock Watchdog Fired" not in events


@pytest.mark.asyncio
async def test_a_reload_during_the_pump_power_wait_sends_no_false_low_power_alert(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, clock, events = await _due_routine_zone(hass, monkeypatch, tmp_path)
    hass.states.async_set(PUMP, "0")  # pump still spinning up
    clock.pump_wait_real_seconds = 5

    async def turn_on(call):
        hass.states.async_set(VALVE, "on")
        _reload_soon(hass, controller)

    hass.services.async_register("switch", "turn_on", turn_on)
    took = await _timed(controller.run_routine_irrigation())
    await hass.async_block_till_done()
    assert took < 3
    assert hass.states.get(VALVE).state == "off"
    assert "Routine Irrigation Interrupted" in events
    assert "Low Pump Power Audit" not in events


# ---------------------------------------------------------------------------
# Home Assistant shutting down, or the run being cancelled
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_shutdown_job_is_registered_and_removed_with_the_zone(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _, _ = await _due_routine_zone(hass, monkeypatch, tmp_path)

    def ours():
        return [j for j in hass._shutdown_jobs if getattr(j.job.target, "__self__", None) is controller]

    assert len(ours()) == 1
    await hass.config_entries.async_unload(controller.entry.entry_id)
    await hass.async_block_till_done()
    assert ours() == []


@pytest.mark.asyncio
async def test_home_assistant_shutting_down_mid_pulse_closes_the_valve_and_frees_the_lock(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, clock, events = await _due_routine_zone(hass, monkeypatch, tmp_path)
    before = controller.store.state.last_routine_ts

    async def shutdown_during_second_pulse(index):
        if index == 1:
            clock.pulse_real_seconds = 5
            hass.async_create_task(controller._on_shutdown())

    clock.on_pulse = shutdown_during_second_pulse
    took = await _timed(controller.run_routine_irrigation())
    await hass.async_block_till_done()

    assert took < 3
    assert hass.states.get(VALVE).state == "off"
    assert len(clock.pulses_for(VALVE)) == 2
    assert controller.store.state.lock_on is False
    assert controller.store.state.last_routine_ts == before
    assert "Routine Irrigation Interrupted" in events


@pytest.mark.asyncio
async def test_the_valve_is_closed_before_a_zone_sharing_the_pump_could_open(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, clock, events = await _due_routine_zone(hass, monkeypatch, tmp_path)
    clock.pulse_real_seconds = 5
    pump_lock = controller._get_pump_lock()
    seen = {}

    async def slow_turn_off(call):
        await asyncio.sleep(0.2)  # a relay takes a moment
        seen.setdefault("pump_held", pump_lock.locked())
        hass.states.async_set(VALVE, "off")

    hass.services.async_register("switch", "turn_off", slow_turn_off)

    async def shutdown_during_first_pulse(index):
        if index == 0:
            hass.async_create_task(controller._on_shutdown())

    clock.on_pulse = shutdown_during_first_pulse
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert hass.states.get(VALVE).state == "off"
    assert seen["pump_held"] is True


@pytest.mark.asyncio
async def test_nothing_starts_once_home_assistant_is_shutting_down(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _due_routine_zone(hass, monkeypatch, tmp_path)
    await controller._on_shutdown()  # nothing was running
    await controller.run_routine_irrigation()
    await controller.run_deep_soak()
    await controller.test_pulse(10)
    await hass.async_block_till_done()
    assert clock.pulses_for(VALVE) == []
    assert controller.store.state.lock_on is False


@pytest.mark.asyncio
async def test_a_cancelled_run_closes_the_valve_and_frees_the_zone(hass, fake_valve_services, monkeypatch, tmp_path):
    """e.g. an automation in restart mode, or a stopped script, cancels the
    service call that is running the cycle."""
    controller, clock, _ = await _due_routine_zone(hass, monkeypatch, tmp_path)
    in_second_pulse = asyncio.Event()

    async def hang(index):
        if index == 1:
            in_second_pulse.set()
            await asyncio.sleep(3600)

    clock.on_pulse = hang
    task = hass.async_create_task(controller.run_routine_irrigation())
    await in_second_pulse.wait()
    assert hass.states.get(VALVE).state == "on"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert hass.states.get(VALVE).state == "off"
    assert controller.store.state.lock_on is False  # not blocked for 3 hours
    first_pulse = clock.pulses_for(VALVE)[0]
    assert controller.store.state.today_runtime_minutes == pytest.approx(first_pulse, abs=0.1)

    clock.reset()
    clock.on_pulse = None
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert len(clock.pulses_for(VALVE)) == 3


# ---------------------------------------------------------------------------
# The valve switch failing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_valve_that_fails_to_switch_stops_the_cycle_alerts_and_frees_the_lock(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, clock, events = await _due_routine_zone(hass, monkeypatch, tmp_path)
    before = controller.store.state.last_routine_ts
    calls = {"n": 0}

    async def flaky_turn_on(call):
        calls["n"] += 1
        if calls["n"] == 3:
            raise HomeAssistantError("valve offline")
        hass.states.async_set(VALVE, "on")

    hass.services.async_register("switch", "turn_on", flaky_turn_on)
    await controller.run_routine_irrigation()  # must not raise
    await hass.async_block_till_done()

    given = clock.valve_minutes(VALVE)
    assert len(clock.pulses_for(VALVE)) == 2
    assert hass.states.get(VALVE).state == "off"
    assert controller.store.state.lock_on is False  # not blocked for 3 hours
    assert controller.store.state.last_routine_ts == before  # tries again next time
    assert "Routine Irrigation Error" in events
    assert "Routine Irrigation Completed" not in events
    # The two pulses given count toward today's cap, so a re-run can't go past it.
    assert controller.store.state.today_runtime_minutes == pytest.approx(given)
    await _set(controller, max_daily_runtime_minutes=given * 3 / 2 + 1)
    clock.reset()
    await controller.run_routine_irrigation(manual=True)
    await hass.async_block_till_done()
    assert clock.pulses_for(VALVE) == []


@pytest.mark.asyncio
async def test_a_valve_that_will_not_close_keeps_the_lock_for_the_watchdogs(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, clock, events = await _due_routine_zone(hass, monkeypatch, tmp_path)

    async def turn_on(call):
        hass.states.async_set(VALVE, "on")
        raise HomeAssistantError("lost contact after switching")

    async def turn_off(call):
        raise HomeAssistantError("valve offline")

    hass.services.async_register("switch", "turn_on", turn_on)
    hass.services.async_register("switch", "turn_off", turn_off)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert hass.states.get(VALVE).state == "on"
    assert controller.store.state.lock_on is True  # stale-lock + stuck-valve watchdogs stay in charge
    assert "Routine Irrigation Error" in events


# ---------------------------------------------------------------------------
# Rain arriving mid-cycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_heavy_rain_between_pulses_stops_the_rest_of_the_routine(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, clock, events = await _due_routine_zone(hass, monkeypatch, tmp_path)
    before = controller.store.state.last_routine_ts

    async def downpour_after_first_pulse(index):
        if index == 0:
            hass.states.async_set(RAIN_COUNTER, "100")  # 30 mm, over the 3 mm / 30 min threshold
            await hass.async_block_till_done()

    clock.on_pulse = downpour_after_first_pulse
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    pulses = clock.pulses_for(VALVE)
    assert len(pulses) == 1
    assert hass.states.get(VALVE).state == "off"
    assert controller.store.state.lock_on is False
    assert controller.store.state.last_routine_ts == before  # not counted as a full run
    assert controller.store.state.today_runtime_minutes == pytest.approx(pulses[0])  # but the cap counts it
    assert "Routine Irrigation Stopped By Rain" in events
    assert "Routine Irrigation Completed" not in events


@pytest.mark.asyncio
async def test_a_light_shower_mid_cycle_does_not_stop_it(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _due_routine_zone(hass, monkeypatch, tmp_path)

    async def drizzle(index):
        if index == 0:
            hass.states.async_set(RAIN_COUNTER, "5")  # 1.5 mm, under the threshold
            await hass.async_block_till_done()

    clock.on_pulse = drizzle
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert len(clock.pulses_for(VALVE)) == 3
    assert "Routine Irrigation Completed" in events


@pytest.mark.asyncio
async def test_heavy_rain_mid_deep_soak_stops_it_too(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=1, last_deep_days_ago=14)
    await _set(controller, deep_soak_max_runtime_minutes=150, deep_soak_pulse_count=3)
    before = controller.store.state.last_deep_soak_ts

    async def downpour(index):
        if index == 0:
            hass.states.async_set(RAIN_COUNTER, "100")
            await hass.async_block_till_done()

    clock.on_pulse = downpour
    await controller.run_deep_soak()
    await hass.async_block_till_done()
    assert len(clock.pulses_for(VALVE)) == 1
    assert controller.store.state.last_deep_soak_ts == before
    assert controller.store.state.lock_on is False
    assert "Deep Soak Stopped By Rain" in events


# ---------------------------------------------------------------------------
# Queued on a shared pump
# ---------------------------------------------------------------------------

async def _queued_on(pump_lock, task):
    for _ in range(400):
        await asyncio.sleep(0.005)
        if pump_lock._waiters and any(not w.done() for w in pump_lock._waiters):
            return
        if task.done():
            break
    raise AssertionError("run never queued on the pump")


@pytest.mark.asyncio
async def test_a_zone_queued_on_a_shared_pump_gives_up_its_place_on_reload(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, clock, events = await _due_routine_zone(hass, monkeypatch, tmp_path)
    pump_lock = controller._get_pump_lock()
    await pump_lock.acquire()  # another zone on this pump is mid-cycle
    task = hass.async_create_task(controller.run_routine_irrigation())
    await _queued_on(pump_lock, task)
    took = await _timed(hass.config_entries.async_reload(controller.entry.entry_id))
    await task
    assert took < 3  # didn't wait out the other zone's cycle
    assert clock.pulses_for(VALVE) == []
    assert hass.data[DOMAIN][controller.entry.entry_id].store.state.lock_on is False
    pump_lock.release()
    assert not pump_lock.locked()


@pytest.mark.asyncio
async def test_a_run_cancelled_while_queued_frees_its_lock(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _due_routine_zone(hass, monkeypatch, tmp_path)
    pump_lock = controller._get_pump_lock()
    await pump_lock.acquire()
    task = hass.async_create_task(controller.run_routine_irrigation())
    await _queued_on(pump_lock, task)
    task.cancel()  # e.g. an automation in restart mode re-triggered
    with pytest.raises(asyncio.CancelledError):
        await task
    pump_lock.release()
    assert controller.store.state.lock_on is False
    assert controller._lock_stale_cancel is None


@pytest.mark.asyncio
async def test_a_cancel_right_as_the_pump_frees_up_does_not_leak_the_pump(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, clock, events = await _due_routine_zone(hass, monkeypatch, tmp_path)
    pump_lock = controller._get_pump_lock()
    await pump_lock.acquire()
    task = hass.async_create_task(controller.run_routine_irrigation())
    await _queued_on(pump_lock, task)
    pump_lock.release()  # the other zone finishes...
    task.cancel()  # ...and in the same moment this run is cancelled
    with pytest.raises(asyncio.CancelledError):
        await task
    await hass.async_block_till_done()
    assert not pump_lock.locked()
    await asyncio.wait_for(controller.run_routine_irrigation(), timeout=5)
    assert len(clock.pulses_for(VALVE)) == 3


# ---------------------------------------------------------------------------
# When the valve can't be confirmed closed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_shutdown_that_cannot_close_the_valve_keeps_the_lock_for_the_restart_check(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, clock, events = await _due_routine_zone(hass, monkeypatch, tmp_path)

    async def turn_off(call):
        raise HomeAssistantError("valve integration already stopped")

    hass.services.async_register("switch", "turn_off", turn_off)

    async def shutdown_during_first_pulse(index):
        if index == 0:
            clock.pulse_real_seconds = 5
            hass.async_create_task(controller._on_shutdown())

    clock.on_pulse = shutdown_during_first_pulse
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert hass.states.get(VALVE).state == "on"
    assert controller.store.state.lock_on is True
    assert controller.store.state.lock_valve == VALVE


@pytest.mark.asyncio
async def test_the_restart_check_closes_the_valve_the_lock_was_kept_for(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    """The lock was kept for a valve that may still be open, and the zone's
    valve setting has changed since: the restart check closes that valve."""
    controller, clock, events = await _due_routine_zone(hass, monkeypatch, tmp_path)
    hass.states.async_set("switch.old_valve", "on")
    state = controller.store.state
    state.lock_on = True
    state.lock_set_ts = controller._setup_ts - 60
    state.lock_valve = "switch.old_valve"
    await controller._on_startup(None)
    await hass.async_block_till_done()
    assert hass.states.get("switch.old_valve").state == "off"
    assert controller.store.state.lock_on is False
    assert "Stale Lock Cleared On Startup" in events


@pytest.mark.asyncio
async def test_a_cycle_stuck_where_nothing_wakes_it_is_cancelled_and_still_closes_its_valve(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, clock, events = await _due_routine_zone(hass, monkeypatch, tmp_path)
    stuck = asyncio.Event()

    async def hang(index):
        if index == 1:
            stuck.set()
            await asyncio.sleep(3600)  # e.g. a valve service call that never returns

    clock.on_pulse = hang
    task = hass.async_create_task(controller.run_routine_irrigation())
    await stuck.wait()
    await controller._interrupt_cycle("test", wait_seconds=0.2, confirm_seconds=1)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert hass.states.get(VALVE).state == "off"
    assert controller.store.state.lock_on is False


@pytest.mark.asyncio
async def test_a_valve_that_confirms_closing_a_moment_later_still_frees_the_lock(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    """Some valves report "off" a second or so after the command -- that's
    closed, not stuck, so the lock is freed rather than kept."""
    controller, clock, events = await _due_routine_zone(hass, monkeypatch, tmp_path)

    async def slow_confirm_turn_off(call):
        hass.loop.call_later(0.3, lambda: hass.states.async_set(VALVE, "off"))

    hass.services.async_register("switch", "turn_off", slow_confirm_turn_off)

    async def shutdown_during_first_pulse(index):
        if index == 0:
            clock.pulse_real_seconds = 5
            clock.sleep_real_seconds = 1  # the confirm wait really waits
            hass.async_create_task(controller._on_shutdown())

    clock.on_pulse = shutdown_during_first_pulse
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert hass.states.get(VALVE).state == "off"
    assert controller.store.state.lock_on is False
