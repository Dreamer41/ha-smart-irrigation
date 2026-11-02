"""1.8: the frost wait became a general weather hold with a reason (frost, rain, wind). Frost works exactly
as before; rain and wind use the same hourly re-checks, never hold a press of Run Now, send one phone
message per cycle and reason, and pick up again after a restart."""
from __future__ import annotations

from datetime import timedelta

import homeassistant.util.dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.zoneflow.const import HOLD_RETRY_COUNT, HOLD_RETRY_SECONDS, WAITING_HOLD_CODES

from .test_pause_and_frost import _zone
from .test_scenarios_cycles import _history
from .test_smoke_setup import OUTDOOR_TEMP, VALVE

WET = {"sensor": "Garden rain sensor"}


def _rain(monkeypatch, controller, holds):
    """The rain hold, switched by `holds["on"]` (Part R reads a real sensor)."""
    monkeypatch.setattr(controller, "_rain_sensor_hold", lambda: dict(WET) if holds["on"] else None)


@pytest.mark.asyncio
async def test_rain_holds_a_due_run_and_rechecks_hourly(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _zone(hass, monkeypatch, tmp_path)
    holds = {"on": True}
    _rain(monkeypatch, c, holds)
    _history(c, last_routine_days_ago=5, last_deep_days_ago=1)
    await c.run_routine_irrigation()
    await hass.async_block_till_done()
    assert c.clock.pulses_for(VALVE) == []
    status = c.status()
    assert status["code"] == "waiting_rain" and "Garden rain sensor reads wet" in status["text"]
    assert len(c.notes) == 1 and "rain" in c.notes[0]
    # Dry an hour later: it waters.
    holds["on"] = False
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=HOLD_RETRY_SECONDS + 1))
    await hass.async_block_till_done()
    assert c.clock.pulses_for(VALVE) != []
    assert not any("rain" in note for note in c.notes[1:])  # no second rain message


@pytest.mark.asyncio
async def test_frost_then_rain_the_same_morning_sends_two_messages_not_one_per_check(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _zone(hass, monkeypatch, tmp_path, temp="0.5")
    holds = {"on": False}
    _rain(monkeypatch, c, holds)
    _history(c, last_routine_days_ago=5, last_deep_days_ago=1)
    await c.run_routine_irrigation()
    await hass.async_block_till_done()
    assert c.status()["code"] == "waiting_frost" and len(c.notes) == 1
    # Warmer, but now it rains.
    hass.states.async_set(OUTDOOR_TEMP, "8.0")
    holds["on"] = True
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=HOLD_RETRY_SECONDS + 1))
    await hass.async_block_till_done()
    assert c.status()["code"] == "waiting_rain" and len(c.notes) == 2
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2 * HOLD_RETRY_SECONDS + 2))
    await hass.async_block_till_done()
    assert len(c.notes) == 2  # still raining: checked again, no third message
    assert c.clock.pulses_for(VALVE) == []


@pytest.mark.asyncio
async def test_rain_still_wet_after_every_check_skips_until_next_time(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _zone(hass, monkeypatch, tmp_path)
    _rain(monkeypatch, c, {"on": True})
    _history(c, last_routine_days_ago=5, last_deep_days_ago=1)
    await c.run_routine_irrigation()
    await hass.async_block_till_done()
    for hour in range(1, HOLD_RETRY_COUNT + 2):
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=hour * (HOLD_RETRY_SECONDS + 1)))
        await hass.async_block_till_done()
    assert c._hold_retry_cancel is None and not c._hold_held
    status = c.status()
    assert status["code"] == "skipped_rain" and "after 6 hourly checks" in status["text"]
    assert len(c.notes) == 1


@pytest.mark.asyncio
async def test_a_press_of_run_now_is_not_held_by_rain_but_is_by_frost(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _zone(hass, monkeypatch, tmp_path)
    _rain(monkeypatch, c, {"on": True})
    _history(c, last_routine_days_ago=5, last_deep_days_ago=1)
    await c.run_routine_now()
    await hass.async_block_till_done()
    assert c.clock.pulses_for(VALVE) != []
    c.clock.reset()
    hass.states.async_set(OUTDOOR_TEMP, "0.5")
    _history(c, last_routine_days_ago=5, last_deep_days_ago=1)
    await c.run_routine_now()
    await hass.async_block_till_done()
    assert c.clock.pulses_for(VALVE) == []  # frost: freezing lines hurt whoever pressed


@pytest.mark.asyncio
async def test_a_restart_mid_hold_picks_up_the_reason_and_the_count(hass, fake_valve_services, monkeypatch, tmp_path):
    c = await _zone(hass, monkeypatch, tmp_path)
    c.store.state.decisions = {
        "routine": {"code": "waiting_wind", "ts": dt_util.utcnow().timestamp(),
                    "params": {"wind_kmh": 32.0, "limit_kmh": 20.0, "hours": 6, "rechecks": 2}},
    }
    c._resume_hold_wait()
    assert c._hold_held == {"routine"} and c._hold_rechecks == 2
    assert c._hold_notified == {("routine", "wind")}  # told before the restart: not again
    status = c.status()
    assert status["code"] == "waiting_wind" and "wind 32 km/h, above the limit (20 km/h)" in status["text"]
    c._cancel_hold_wait()
    assert c.status()["code"] == "skipped_wind"
    assert set(WAITING_HOLD_CODES) == {"waiting_frost", "waiting_rain", "waiting_wind", "waiting_deep_soak"}
