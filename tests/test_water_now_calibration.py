"""Water now (a counted manual watering with a duration) and the guided
calibration from a measured run (1.7.0)."""
from __future__ import annotations

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.zoneflow import calibration
from custom_components.zoneflow.const import DOMAIN

from .test_scenarios_cycles import _history, _set, _zone
from .test_smoke_setup import VALVE


async def _ready(hass, monkeypatch, tmp_path):
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=1, last_deep_days_ago=3, peaks=(30.5, 30.5, 30.5))
    await _set(controller, zone_flow_l_min=12.0)
    return controller, clock, events


@pytest.mark.asyncio
async def test_water_now_waters_for_the_minutes_and_counts_in_the_water_record(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _ready(hass, monkeypatch, tmp_path)
    state = controller.store.state
    last_routine, last_deep = state.last_routine_ts, state.last_deep_soak_ts
    await hass.services.async_call(DOMAIN, "water_now", {"minutes": 7}, blocking=True)
    await hass.async_block_till_done()
    assert clock.pulses_for(VALVE) == [7]
    assert hass.states.get(VALVE).state == "off" and state.lock_on is False
    # In the record: the last watering amount and the litres (7 min x 12 L/min).
    assert state.last_cycle_kind == "manual" and state.last_cycle_runtime_min == pytest.approx(7)
    assert state.last_cycle_liters == pytest.approx(84.0)
    assert controller.water_used()["liters_30d"] == pytest.approx(84.0)
    # The schedule did not move.
    assert (state.last_routine_ts, state.last_deep_soak_ts) == (last_routine, last_deep)
    assert events[-1] == "Manual Watering"
    assert state.today_runtime_minutes == pytest.approx(7)


@pytest.mark.asyncio
async def test_water_now_defaults_to_ten_minutes_and_keeps_to_the_safety_limits(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _ready(hass, monkeypatch, tmp_path)
    await hass.services.async_call(DOMAIN, "water_now", {}, blocking=True)
    await hass.async_block_till_done()
    assert clock.pulses_for(VALVE) == [10]
    cap = controller.number("max_runtime_minutes")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "water_now", {"minutes": cap + 1}, blocking=True)
    # Not while paused, not while the zone is busy.
    await controller.set_paused(True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "water_now", {"minutes": 5}, blocking=True)
    await controller.set_paused(False)
    await controller._set_lock(True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "water_now", {"minutes": 5}, blocking=True)


@pytest.mark.asyncio
async def test_a_service_run_is_still_not_counted(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _ready(hass, monkeypatch, tmp_path)
    await controller.start_service_run(5)
    await hass.async_block_till_done()
    assert events[-1] == "Service Run" and controller.store.state.last_cycle_kind != "manual"


@pytest.mark.asyncio
async def test_calibration_sets_the_flow_rate_and_zone_flow_from_the_measured_water(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _, _ = await _ready(hass, monkeypatch, tmp_path)
    # 30 litres on 10 m2 in 15 minutes: 3 mm in 15 minutes = 0.2 mm/min; 2 L/min.
    await hass.services.async_call(DOMAIN, "calibrate_flow", {"volume": 30, "area": 10, "minutes": 15}, blocking=True)
    assert controller.number("flow_rate_mm_per_min") == pytest.approx(0.2, abs=0.001)
    assert controller.number("zone_flow_l_min") == pytest.approx(2.0, abs=0.01)
    # Nonsense is refused and changes nothing.
    for bad in ({"volume": 3000, "area": 1, "minutes": 1}, {"volume": 5, "area": 100000, "minutes": 240}):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(DOMAIN, "calibrate_flow", bad, blocking=True)
    assert controller.number("flow_rate_mm_per_min") == pytest.approx(0.2, abs=0.001)


@pytest.mark.asyncio
async def test_calibration_on_an_imperial_zone_takes_gallons_and_square_feet(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _, _ = await _ready(hass, monkeypatch, tmp_path)
    controller.entry.options  # imperial: gallons and ft2
    from custom_components.zoneflow.const import CONF_UNIT_SYSTEM

    hass.config_entries.async_update_entry(controller.entry, options={CONF_UNIT_SYSTEM: "imperial"})
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][controller.entry.entry_id]
    assert controller.imperial
    # 10 gallons on 100 ft2 in 10 minutes.
    rate = await calibration.calibrate_from_volume(controller, 10.0, 100.0, 10.0)
    assert rate == pytest.approx(10 * 3.785411784 / (100 * 0.09290304) / 10, rel=1e-3)
