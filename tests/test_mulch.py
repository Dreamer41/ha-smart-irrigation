"""Mulch: an opt-in "Not Mulched" adjustment that scales the routine weekly
target up, the same way under either demand model. Default is "Mulched"
(no adjustment), so upgrading never changes how an existing zone waters.
"""
from unittest.mock import AsyncMock

import pytest

from custom_components.zoneflow import calculations as calc
from custom_components.zoneflow import controller as controller_module
from custom_components.zoneflow.const import DEMAND_MODEL_ET, DOMAIN

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry


async def _setup(hass):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "28.0")
    await hass.async_block_till_done()
    await hass.config.async_update(latitude=9.5)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    controller.store.state.min_temp_day_history_c = [25.0, 24.0, None]
    controller.store.state.peak_temp_day_history_c = [31.0, 31.0, 30.0]
    controller.store.state.last_routine_ts = 0.0
    controller.store.state.last_significant_rain_ts = 0.0
    controller._run_pulses = AsyncMock(return_value=True)
    return controller


def _capture_plans(monkeypatch):
    plans = []
    real = calc.plan_routine_irrigation

    def spy(**kwargs):
        plan = real(**kwargs)
        plans.append(plan)
        return plan

    monkeypatch.setattr(controller_module.calc, "plan_routine_irrigation", spy)
    return plans


def _entity(hass, domain, fragment):
    return next(s.entity_id for s in hass.states.async_all(domain) if fragment in s.entity_id)


@pytest.mark.asyncio
async def test_default_is_mulched_and_makes_no_difference(hass, fake_valve_services, monkeypatch):
    controller = await _setup(hass)
    assert hass.states.get(_entity(hass, "select", "mulch")).state == "mulched"
    assert controller.mulch_factor() == 1.0
    plans = _capture_plans(monkeypatch)

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    assert plans[-1].target_weekly_mm == controller.number("target_weekly_mm")


@pytest.mark.asyncio
async def test_not_mulched_scales_the_tier_target_up_by_the_slider(hass, fake_valve_services, monkeypatch):
    controller = await _setup(hass)
    plans = _capture_plans(monkeypatch)
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": _entity(hass, "select", "mulch"), "option": "not_mulched"},
        blocking=True,
    )
    assert controller.mulch_factor() == pytest.approx(1.2)  # default 20%

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    assert plans[-1].target_weekly_mm == pytest.approx(controller.number("target_weekly_mm") * 1.2)


@pytest.mark.asyncio
async def test_slider_changes_how_much_not_mulched_adjusts(hass, fake_valve_services):
    controller = await _setup(hass)
    controller.store.state.mulch_status = "not_mulched"
    await controller.numbers["mulch_et_adjustment_pct"].async_set_native_value(70)
    assert controller.mulch_factor() == pytest.approx(1.7)

    await controller.numbers["mulch_et_adjustment_pct"].async_set_native_value(0)
    assert controller.mulch_factor() == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_applies_under_the_et_curve_too(hass, fake_valve_services, monkeypatch):
    controller = await _setup(hass)
    controller.store.state.demand_model = DEMAND_MODEL_ET
    controller.store.state.mulch_status = "not_mulched"
    plans = _capture_plans(monkeypatch)

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    expected = controller.et_weekly_target_mm() * controller.routine_target_scale()
    assert plans[-1].target_weekly_mm == pytest.approx(expected)


@pytest.mark.asyncio
async def test_does_not_affect_deep_soak(hass, fake_valve_services):
    """Mulch is about evaporation loss from the routine cycle's shallow,
    frequent doses -- deep soak's job (root-zone penetration depth) doesn't
    scale with it, same as growth ramp and deficit mode already don't (see
    controller.py's run_deep_soak, which reads deep_soak_target_mm
    directly with no routine_target_scale()/mulch_factor() involved)."""
    controller = await _setup(hass)
    controller.store.state.mulch_status = "not_mulched"
    plan = calc.plan_deep_soak(
        controller.number("deep_soak_target_mm"),
        controller.number("flow_rate_mm_per_min"),
    )
    assert plan.target_mm == controller.number("deep_soak_target_mm")


@pytest.mark.asyncio
async def test_mulch_status_survives_a_reload(hass, fake_valve_services):
    controller = await _setup(hass)
    controller.store.state.mulch_status = "not_mulched"
    await controller.store.async_save()
    reloaded = await controller.store.async_load()
    assert reloaded.mulch_status == "not_mulched"


@pytest.mark.asyncio
async def test_weekly_target_sensor_reports_mulch_attributes(hass, fake_valve_services):
    controller = await _setup(hass)
    entity_id = _entity(hass, "sensor", "routine_weekly_target")
    ent = next(e for e in hass.data["sensor"].entities if e.entity_id == entity_id)

    controller.store.state.mulch_status = "not_mulched"
    ent.async_write_ha_state()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.attributes["mulch_status"] == "not_mulched"
    assert state.attributes["mulch_factor"] == pytest.approx(1.2)


@pytest.mark.asyncio
async def test_negative_slider_scales_the_target_down_and_is_floored(hass, fake_valve_services, monkeypatch):
    controller = await _setup(hass)
    plans = _capture_plans(monkeypatch)
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": _entity(hass, "select", "mulch"), "option": "not_mulched"},
        blocking=True,
    )
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": _entity(hass, "number", "mulch_et_adjustment"), "value": -25},
        blocking=True,
    )
    assert controller.mulch_factor() == pytest.approx(0.75)

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert plans[-1].target_weekly_mm == pytest.approx(controller.number("target_weekly_mm") * 0.75)

    # The slider stops at -50%, and the factor never goes below that either.
    monkeypatch.setattr(controller, "number", lambda key: -90.0 if key == "mulch_et_adjustment_pct" else 0.0)
    assert controller.mulch_factor() == pytest.approx(0.5)
