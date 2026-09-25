"""ET curve part 2: the opt-in "Water Demand Model" select. Temperature
tiers stay the default (upgrading never changes how a zone waters); the ET
curve replaces only the routine WEEKLY TARGET with ET0 x 7 x crop factor,
and falls back to the tier target whenever ET0 isn't available.
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
    # Two full days of min/max on record, normal-tier peaks.
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
async def test_default_model_is_temperature_tiers_and_ignores_et0(hass, fake_valve_services, monkeypatch):
    controller = await _setup(hass)
    plans = _capture_plans(monkeypatch)
    assert hass.states.get(_entity(hass, "select", "water_demand_model")).state == "temperature_tiers"
    assert controller.avg_et0() is not None  # ET0 is available, but must be ignored

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    assert plans[-1].target_weekly_mm == controller.number("target_weekly_mm")  # normal tier, 35


@pytest.mark.asyncio
async def test_et_curve_sets_the_weekly_target_from_et0_and_crop_factor(hass, fake_valve_services, monkeypatch):
    controller = await _setup(hass)
    plans = _capture_plans(monkeypatch)
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": _entity(hass, "select", "water_demand_model"), "option": "et_curve"},
        blocking=True,
    )
    assert controller.store.state.demand_model == DEMAND_MODEL_ET

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    expected = calc.et_weekly_target_mm(controller.avg_et0(), 0.8)
    assert plans[-1].target_weekly_mm == pytest.approx(expected)
    assert plans[-1].target_weekly_mm != controller.number("target_weekly_mm")


@pytest.mark.asyncio
async def test_crop_factor_scales_the_et_target(hass, fake_valve_services, monkeypatch):
    controller = await _setup(hass)
    controller.store.state.demand_model = DEMAND_MODEL_ET
    at_08 = controller.et_weekly_target_mm()
    await controller.numbers["crop_coefficient"].async_set_native_value(0.4)
    assert controller.et_weekly_target_mm() == pytest.approx(at_08 / 2, abs=0.02)


@pytest.mark.asyncio
async def test_growth_ramp_still_scales_the_et_target(hass, fake_valve_services, monkeypatch):
    controller = await _setup(hass)
    controller.store.state.demand_model = DEMAND_MODEL_ET
    monkeypatch.setattr(controller, "growth_ramp_fraction", lambda: 0.5)
    plans = _capture_plans(monkeypatch)

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    assert plans[-1].target_weekly_mm == pytest.approx(controller.et_weekly_target_mm() * 0.5)


@pytest.mark.asyncio
async def test_no_et_history_falls_back_to_the_tier_target(hass, fake_valve_services, monkeypatch):
    controller = await _setup(hass)
    controller.store.state.demand_model = DEMAND_MODEL_ET
    controller.store.state.min_temp_day_history_c = [None, None, None]
    plans = _capture_plans(monkeypatch)

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    assert controller.et_weekly_target_mm() is None
    assert plans[-1].target_weekly_mm == controller.number("target_weekly_mm")


@pytest.mark.asyncio
async def test_dead_temp_sensor_falls_back_immediately_and_recovers(hass, fake_valve_services):
    controller = await _setup(hass)
    controller.store.state.demand_model = DEMAND_MODEL_ET
    assert controller.et_weekly_target_mm() is not None

    hass.states.async_set(OUTDOOR_TEMP, "unavailable")
    await hass.async_block_till_done()
    assert controller.et_weekly_target_mm() is None
    assert controller.tier_weekly_target_mm() == controller.number("target_weekly_mm")

    hass.states.async_set(OUTDOOR_TEMP, "29.0")
    await hass.async_block_till_done()
    assert controller.et_weekly_target_mm() is not None


@pytest.mark.asyncio
async def test_weekly_target_sensor_reports_value_and_source(hass, fake_valve_services):
    controller = await _setup(hass)
    entity_id = _entity(hass, "sensor", "routine_weekly_target")
    ent = next(e for e in hass.data["sensor"].entities if e.entity_id == entity_id)

    ent.async_write_ha_state()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert float(state.state) == controller.number("target_weekly_mm")
    assert state.attributes["source"] == "temperature_tiers"

    controller.store.state.demand_model = DEMAND_MODEL_ET
    ent.async_write_ha_state()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert float(state.state) == pytest.approx(controller.et_weekly_target_mm(), abs=0.01)
    assert state.attributes["source"] == "et_curve"

    controller.store.state.min_temp_day_history_c = [None, None, None]
    ent.async_write_ha_state()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).attributes["source"] == "temperature_tiers_fallback"


@pytest.mark.asyncio
async def test_demand_model_survives_a_reload(hass, fake_valve_services):
    controller = await _setup(hass)
    controller.store.state.demand_model = DEMAND_MODEL_ET
    await controller.store.async_save()
    reloaded = await controller.store.async_load()
    assert reloaded.demand_model == DEMAND_MODEL_ET
