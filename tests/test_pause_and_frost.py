"""Pause switch (no watering until it's switched off) and the frost guard
(a due cycle waits while the outdoor temperature is below a threshold,
re-checking hourly a few times).
"""
import asyncio
from datetime import timedelta

import pytest
from homeassistant.exceptions import ServiceValidationError
import homeassistant.util.dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.zoneflow import visibility
from custom_components.zoneflow.const import DOMAIN, FROST_RETRY_COUNT, FROST_RETRY_SECONDS

from .scenario_harness import CompressedTime
from .test_service_runs import _switch
from .test_scenarios_cycles import _history
from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry, schedule_clear_of_now

DAY = 86400


async def _zone(hass, monkeypatch, tmp_path, *, temp="28.0", temp_unit=None, **overrides):
    notes = []

    async def _notify(call):
        notes.append(call.data["title"])

    hass.services.async_register("notify", "send_message", _notify)
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, temp, {"unit_of_measurement": temp_unit} if temp_unit else {})
    await hass.async_block_till_done()
    # The frost tests move the clock hours ahead: keep the zone's own
    # watering times out of the way, or a scheduled run joins in depending
    # on the hour the suite runs.
    overrides = {**schedule_clear_of_now(), **overrides}
    entry = make_entry(hass, csv_path=str(tmp_path / "p.csv"), notify_entity="notify.phone", **overrides)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    controller.clock = CompressedTime(hass, [VALVE]).install(monkeypatch)
    controller.notes = notes
    return controller


def _entity(hass, domain, suffix):
    return next(s.entity_id for s in hass.states.async_all(domain) if s.entity_id.endswith(suffix))


# --- Pause -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_paused_zone_does_not_water_and_says_so(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path)
    switch_id = _entity(hass, "switch", "_pause")
    await _switch(hass, switch_id).async_turn_on()
    assert hass.states.get(switch_id).state == "on"
    assert hass.states.get(switch_id).attributes["paused_since"] is not None

    _history(controller, last_routine_days_ago=5, last_deep_days_ago=20)
    await controller.run_deep_soak()
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert controller.clock.pulses_for(VALVE) == []
    assert controller.status()["code"] == "paused"
    assert controller.status()["next_watering"] is None

    # "Run now" says why instead of silently doing nothing.
    for suffix in ("_run_routine_irrigation_now", "_run_deep_soak_now"):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call("button", "press", {"entity_id": _entity(hass, "button", suffix)}, blocking=True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "run_routine_irrigation", {"entity_id": switch_id}, blocking=True)

    # Service runs still work (checking a line while paused for winter).
    await controller.start_service_run(1)
    await hass.async_block_till_done()
    assert controller.clock.pulses_for(VALVE) == [1.0]

    await _switch(hass, switch_id).async_turn_off()
    assert hass.states.get(switch_id).state == "off"
    _history(controller, last_routine_days_ago=5, last_deep_days_ago=1)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert len(controller.clock.pulses_for(VALVE)) > 1
    assert "Paused" in (tmp_path / "p.csv").read_text() and "Resumed" in (tmp_path / "p.csv").read_text()


@pytest.mark.asyncio
async def test_no_overdue_warning_for_the_paused_weeks(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path)
    await controller.set_paused(True)
    controller.store.state.paused_since_ts = dt_util.utcnow().timestamp() - 40 * DAY
    await controller.set_paused(False)
    _history(controller, last_routine_days_ago=45, last_deep_days_ago=1)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert "Irrigation Overdue" not in (tmp_path / "p.csv").read_text()

    # Without a pause the same gap is overdue.
    controller.store.state.pause_ended_ts = None
    _history(controller, last_routine_days_ago=45, last_deep_days_ago=1)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert "Irrigation Overdue" in (tmp_path / "p.csv").read_text()


@pytest.mark.asyncio
async def test_pause_survives_a_restart(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path)
    await controller.set_paused(True)
    assert await hass.config_entries.async_reload(controller.entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(_entity(hass, "switch", "_pause")).state == "on"


# --- Frost guard -----------------------------------------------------------


@pytest.mark.asyncio
async def test_frost_holds_a_due_run_and_rechecks_hourly(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path, temp="0.5")
    _history(controller, last_routine_days_ago=5, last_deep_days_ago=1)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert controller.clock.pulses_for(VALVE) == []
    status = controller.status()
    assert status["code"] == "waiting_frost"
    assert "0.5 °C, below the frost guard (2.0 °C)" in status["text"]
    assert len(controller.notes) == 1 and "frost" in controller.notes[0]

    # Still cold an hour later: another check, no second phone message.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=FROST_RETRY_SECONDS + 1))
    await hass.async_block_till_done()
    assert controller.clock.pulses_for(VALVE) == []
    assert len(controller.notes) == 1

    # Warmer: the next check waters.
    hass.states.async_set(OUTDOOR_TEMP, "6.0")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2 * FROST_RETRY_SECONDS + 2))
    await hass.async_block_till_done()
    assert controller.clock.pulses_for(VALVE)
    assert controller.status()["code"] == "done"


@pytest.mark.asyncio
async def test_frost_gives_up_after_the_last_recheck(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path, temp="-3")
    _history(controller, last_routine_days_ago=5, last_deep_days_ago=1)
    await controller.run_routine_irrigation()
    for hour in range(1, FROST_RETRY_COUNT + 2):
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=hour * (FROST_RETRY_SECONDS + 1)))
        await hass.async_block_till_done()
    assert controller.clock.pulses_for(VALVE) == []
    assert controller._frost_retry_cancel is None and not controller._frost_held
    assert len(controller.notes) == 1  # one phone message for the whole wait
    status = controller.status()
    assert status["code"] == "skipped_frost"
    assert " · next " in status["text"]
    log = (tmp_path / "p.csv").read_text()
    assert log.count("Skipped (Frost)") == FROST_RETRY_COUNT + 1


@pytest.mark.asyncio
async def test_frost_guard_off_unreadable_sensor_and_fahrenheit(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path, temp="-3")
    await controller.numbers["frost_guard_temp"].async_set_metric_value(-10.0)  # lowest = off
    _history(controller, last_routine_days_ago=5, last_deep_days_ago=1)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert controller.clock.pulses_for(VALVE)

    await controller.numbers["frost_guard_temp"].async_set_metric_value(2.0)
    hass.states.async_set(OUTDOOR_TEMP, "unavailable")
    assert await controller._frost_blocks("routine") is False  # never blocks on a missing reading

    hass.states.async_set(OUTDOOR_TEMP, "30", {"unit_of_measurement": "°F"})  # -1.1 °C
    assert await controller._frost_blocks("routine") is True
    hass.states.async_set(OUTDOOR_TEMP, "40", {"unit_of_measurement": "°F"})  # 4.4 °C
    assert await controller._frost_blocks("deep_soak") is False


@pytest.mark.asyncio
async def test_frost_guard_holds_the_deep_soak_too(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path, temp="1.0")
    _history(controller, last_routine_days_ago=1, last_deep_days_ago=20)
    await controller.run_deep_soak()
    await hass.async_block_till_done()
    assert controller.clock.pulses_for(VALVE) == []
    assert controller.status()["cycle"] == "deep_soak"
    assert controller._frost_held == {"deep_soak"} and controller._frost_retry_cancel is not None

    # Unloading the zone cancels the pending re-check.
    assert await hass.config_entries.async_unload(controller.entry.entry_id)
    await hass.async_block_till_done()
    assert controller._frost_retry_cancel is None
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=FROST_RETRY_SECONDS + 1))
    await hass.async_block_till_done()
    assert controller.clock.pulses_for(VALVE) == []


@pytest.mark.asyncio
async def test_frost_guard_hidden_without_a_temperature_sensor(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path, outdoor_temp_entity=None)
    assert ("number", "frost_guard_temp") in visibility.hidden_for(controller)
    assert controller.frost_guard_c() is None


@pytest.mark.asyncio
async def test_pause_stops_a_running_cycle_at_once(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path)

    async def on_pulse(index):
        if index == 1:  # during the second pulse
            await controller.set_paused(True)

    controller.clock.on_pulse = on_pulse
    _history(controller, last_routine_days_ago=4, last_deep_days_ago=1, peaks=(30.5, 30.5, 30.5))
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert len(controller.clock.pulses_for(VALVE)) == 2
    assert hass.states.get(VALVE).state == "off"
    assert controller.store.state.lock_on is False
    assert controller.store.state.last_routine_ts < dt_util.utcnow().timestamp() - DAY  # not counted as watered
    assert "Routine Irrigation Stopped (Paused)" in (tmp_path / "p.csv").read_text()
    assert controller.status()["code"] == "paused"


@pytest.mark.asyncio
async def test_pause_gives_up_a_place_in_the_pump_queue(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path)
    pump_lock = controller._get_pump_lock()
    await pump_lock.acquire()  # another zone on the pump
    _history(controller, last_routine_days_ago=4, last_deep_days_ago=1)
    task = hass.async_create_task(controller.run_routine_irrigation())
    for _ in range(20):
        await asyncio.sleep(0)
        if controller._waiting_pump_kind:
            break
    assert controller.status()["code"] == "waiting_pump"
    await controller.set_paused(True)
    await task
    pump_lock.release()
    await hass.async_block_till_done()
    assert controller.clock.pulses_for(VALVE) == []
    assert controller.store.state.lock_on is False


@pytest.mark.asyncio
async def test_the_routine_waits_for_a_frost_held_deep_soak(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path, temp="0.0")
    _history(controller, last_routine_days_ago=5, last_deep_days_ago=20)
    await controller.run_deep_soak()  # 05:00: frost
    hass.states.async_set(OUTDOOR_TEMP, "5.0")
    await controller.run_routine_irrigation()  # 05:30: warm enough, so the due routine hands over to the deep soak
    await hass.async_block_till_done()
    # Only the deep soak ran (it counts as the routine watering too).
    assert "Deep Soak Completed" in (tmp_path / "p.csv").read_text()
    assert "Routine Irrigation Completed" not in (tmp_path / "p.csv").read_text()
    assert not controller._frost_held and controller._frost_retry_cancel is None


@pytest.mark.asyncio
async def test_a_stale_or_impossible_reading_never_holds_watering(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path)
    hass.states.async_set(OUTDOOR_TEMP, "-127")
    assert await controller._frost_blocks("routine") is False
    hass.states.async_set(OUTDOOR_TEMP, "-1")
    later = dt_util.utcnow() + timedelta(hours=7)
    monkeypatch.setattr(dt_util, "utcnow", lambda: later)
    assert await controller._frost_blocks("routine") is False


@pytest.mark.asyncio
async def test_a_frost_wait_carries_on_after_a_restart(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path, temp="0.0")
    _history(controller, last_routine_days_ago=5, last_deep_days_ago=1)
    await controller.run_routine_irrigation()
    assert len(controller.notes) == 1
    notes = controller.notes
    assert await hass.config_entries.async_reload(controller.entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][controller.entry.entry_id]
    controller.clock = CompressedTime(hass, [VALVE]).install(monkeypatch)
    assert controller.status()["code"] == "waiting_frost"
    hass.states.async_set(OUTDOOR_TEMP, "6.0")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=FROST_RETRY_SECONDS + 1))
    await hass.async_block_till_done()
    assert controller.clock.pulses_for(VALVE)
    assert len(notes) == 2  # no second frost message; the second is "watering done"


@pytest.mark.asyncio
async def test_a_test_pulse_is_not_stopped_by_pause(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path)
    await controller.set_paused(True)
    await controller.test_pulse(10)
    await hass.async_block_till_done()
    assert len(controller.clock.pulses_for(VALVE)) == 1
    assert controller.store.state.lock_on is False


@pytest.mark.asyncio
async def test_pause_cuts_a_soak_gap_short(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path)
    controller.clock.sleep_real_seconds = 5.0  # a long soak gap in real time

    async def on_pulse(index):
        if index == 0:
            hass.loop.call_later(0.05, lambda: hass.async_create_task(controller.set_paused(True)))

    controller.clock.on_pulse = on_pulse
    _history(controller, last_routine_days_ago=4, last_deep_days_ago=1, peaks=(30.5, 30.5, 30.5))
    started = asyncio.get_running_loop().time()
    await controller.run_routine_irrigation()
    assert asyncio.get_running_loop().time() - started < 2.0
    assert len(controller.clock.pulses_for(VALVE)) == 1
    assert controller.store.state.lock_on is False


@pytest.mark.asyncio
async def test_restarts_dont_restart_the_recheck_count(hass, fake_valve_services, monkeypatch, tmp_path):
    controller = await _zone(hass, monkeypatch, tmp_path, temp="-2")
    _history(controller, last_routine_days_ago=5, last_deep_days_ago=1)
    await controller.run_routine_irrigation()
    for hour in range(1, FROST_RETRY_COUNT):
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=hour * (FROST_RETRY_SECONDS + 1)))
        await hass.async_block_till_done()
    assert controller._frost_rechecks == FROST_RETRY_COUNT - 1
    assert await hass.config_entries.async_reload(controller.entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][controller.entry.entry_id]
    assert controller._frost_rechecks == FROST_RETRY_COUNT - 1
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=(FROST_RETRY_COUNT + 1) * (FROST_RETRY_SECONDS + 1)))
    await hass.async_block_till_done()
    assert controller._frost_retry_cancel is None
    assert (tmp_path / "p.csv").read_text().count("Skipped (Frost)") == FROST_RETRY_COUNT + 1
