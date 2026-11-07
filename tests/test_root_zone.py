"""1.8: the root-zone limit (FAO-56 chapter 8). With Root Depth set, a routine dose or a deep soak is never
more than the roots hold (TAW), and the days between waterings shorten when one interval's use would dry
the soil past Allowed Soil Drying (RAW). It can only make waterings sooner and smaller; Root Depth 0
(every existing zone) changes nothing."""
from __future__ import annotations

import random

import pytest

from custom_components.zoneflow import calculations as calc
from custom_components.zoneflow import messages as zf_messages
from custom_components.zoneflow import setup_check, units, visibility, why
from custom_components.zoneflow.const import DEMAND_MODEL_TIERS

from .test_et0_days import _zone


# --- the pure functions ---------------------------------------------------------------------


def test_capacity_scales_with_depth_holding_and_wetted_share():
    assert calc.root_zone_capacity_mm(130, 700, 40) == pytest.approx(36.4)
    assert calc.root_zone_capacity_mm(155, 300, 100) == pytest.approx(46.5)
    assert calc.root_zone_capacity_mm(130, 0, 40) is None  # off
    assert calc.root_zone_capacity_mm(100, 1000, 1) == calc.root_zone_capacity_mm(100, 1000, 5)  # at least 5 %
    assert calc.root_zone_capacity_mm(100, 1000, 300) == pytest.approx(100.0)  # at most the whole area


def test_allowed_depletion_follows_the_days_demand_within_limits():
    assert calc.allowed_depletion(0.40, 6.0) == pytest.approx(0.36)
    assert calc.allowed_depletion(0.40, 5.0) == pytest.approx(0.40)
    assert calc.allowed_depletion(0.75, 0.0) == 0.8
    assert calc.allowed_depletion(0.30, 15.0) == 0.1


def test_capacity_interval():
    assert calc.capacity_interval_days(13.1, 6.0) == 2
    assert calc.capacity_interval_days(1.5, 4.0) == 1  # never below a day
    assert calc.capacity_interval_days(10.0, 0.0) is None


def test_the_limit_never_lengthens_the_interval_or_raises_the_dose():
    rng = random.Random(7)
    for _ in range(500):
        normal, hot = rng.randint(1, 10), rng.randint(1, 10)
        temp = rng.uniform(10, 40)
        cap = rng.choice([None, rng.randint(1, 12)])
        taw = rng.choice([None, rng.uniform(1, 80)])
        kwargs = dict(
            avg_peak_temp=temp, hot_threshold=30.0, cool_threshold=20.0, normal_weekly_mm=rng.uniform(5, 60),
            hot_weekly_mm=rng.uniform(5, 80), cool_weekly_mm=rng.uniform(1, 40), flow_rate=0.5, days_elapsed=3,
            today_rain_mm=0.0, rain_day_history_mm=[0.0] * 10, rain_eff_low=0.5, rain_eff_mid=0.75, rain_eff_high=0.9,
            normal_interval_days=normal, hot_interval_days=hot,
        )
        plain = calc.plan_routine_irrigation(**kwargs)
        limited = calc.plan_routine_irrigation(**kwargs, max_interval_days=cap, root_zone_mm=taw)
        assert limited.interval_days <= plain.interval_days
        assert limited.interval_target_mm <= plain.interval_target_mm + 1e-9
        assert limited.needed_mm <= plain.needed_mm + 1e-9
        if taw is not None:
            assert limited.interval_target_mm <= taw + 1e-9


# --- the zone -------------------------------------------------------------------------------


async def _set(c, **numbers):
    for key, value in numbers.items():
        await c.numbers[key].async_set_metric_value(float(value))


async def _tiers_zone(hass, weekly_mm: float, interval: int):
    c = await _zone(hass)
    c.store.state.demand_model = DEMAND_MODEL_TIERS
    await _set(
        c, target_weekly_mm=weekly_mm, target_weekly_hot_mm=weekly_mm, target_weekly_cool_mm=weekly_mm,
        routine_interval_days=interval, routine_interval_hot_days=interval,
    )
    assert c.routine_target_scale() == pytest.approx(1.0)
    return c


@pytest.mark.asyncio
async def test_an_upgraded_zone_with_no_root_depth_plans_exactly_as_before(hass):
    c = await _tiers_zone(hass, 42.0, 3)
    assert c.number("root_depth_mm") == 0 and c.root_zone() is None
    plan = c._routine_plan()
    assert plan.interval_days == 3 and plan.interval_target_mm == pytest.approx(18.0) and plan.root_zone_capped_mm == 0
    assert c.deep_soak_target_mm() == c.number("deep_soak_target_mm")


@pytest.mark.asyncio
async def test_drip_tomatoes_on_sandy_loam_in_a_hot_week_water_every_two_days(hass):
    c = await _tiers_zone(hass, 42.0, 3)  # 6 mm a day
    await _set(c, root_depth_mm=700, soil_holding_mm_per_m=130, wetted_area_pct=40, allowed_depletion_pct=40)
    rz = c.root_zone()
    assert rz.taw_mm == pytest.approx(36.4) and rz.p == pytest.approx(0.36) and rz.raw_mm == pytest.approx(13.1, abs=0.01)
    assert rz.max_interval_days == 2
    plan = c._routine_plan()
    assert plan.interval_days == 2 and plan.interval_target_mm == pytest.approx(12.0)
    # One source: the due check and the Status estimate use the same shortened gap.
    assert c._routine_interval_days() == 2 and c._tier_interval_days() == 3
    c.store.state.last_routine_ts = 1_000_000.0
    c.store.state.last_significant_rain_ts = 0.0
    est, _source = c.routine_next_estimate()
    assert est == pytest.approx(1_000_000.0 + 2 * 86400)


@pytest.mark.asyncio
async def test_a_lawn_on_loam_is_not_changed_when_the_soil_holds_enough(hass):
    c = await _tiers_zone(hass, 28.0, 4)  # 4 mm a day
    await _set(c, root_depth_mm=300, soil_holding_mm_per_m=155, wetted_area_pct=100, allowed_depletion_pct=40)
    rz = c.root_zone()
    assert rz.taw_mm == pytest.approx(46.5) and rz.max_interval_days == 5
    plan = c._routine_plan()
    assert plan.interval_days == 4 and plan.interval_target_mm == pytest.approx(16.0) and plan.root_zone_capped_mm == 0


@pytest.mark.asyncio
async def test_shallow_strawberries_on_sand_water_daily_and_the_deep_soak_is_capped(hass):
    await zf_messages.async_setup(hass)
    c = await _tiers_zone(hass, 28.0, 4)
    await _set(c, root_depth_mm=200, soil_holding_mm_per_m=80, wetted_area_pct=40, allowed_depletion_pct=20,
               deep_soak_target_mm=25)
    rz = c.root_zone()
    assert rz.taw_mm == pytest.approx(6.4) and rz.raw_mm == pytest.approx(1.54, abs=0.01)
    plan = c._routine_plan()
    assert plan.interval_days == 1 and plan.interval_target_mm == pytest.approx(4.0)
    assert c.deep_soak_target_mm() == pytest.approx(6.4)
    ids = {i["id"] for i in setup_check.run_checks(c)}
    assert "root_zone_shallow" in ids
    assert c.next_amount_mm("deep_soak") == pytest.approx(6.4)


@pytest.mark.asyncio
async def test_a_dose_bigger_than_the_root_zone_is_capped_and_why_says_so(hass):
    await zf_messages.async_setup(hass)
    c = await _tiers_zone(hass, 70.0, 7)  # 10 mm a day, 70 mm a week in one go
    await _set(c, root_depth_mm=300, soil_holding_mm_per_m=100, wetted_area_pct=100, allowed_depletion_pct=80)
    rz = c.root_zone()
    assert rz.taw_mm == pytest.approx(30.0)
    plan = c._routine_plan()
    # p = 0.8 - 0.2 = 0.6, RAW 18 mm: every day -> 10 mm. Under the cap.
    assert plan.interval_days == 1 and plan.root_zone_capped_mm == 0
    texts = {i["id"]: i["text"] for i in why.explain(c)}
    assert "root_zone" in texts and "root_zone_interval" in texts and "every 1 days instead of 7" in texts["root_zone_interval"]


def test_the_dose_cap_applies_on_its_own():
    plan = calc.plan_routine_irrigation(
        avg_peak_temp=25.0, hot_threshold=30.0, cool_threshold=20.0, normal_weekly_mm=70.0, hot_weekly_mm=70.0,
        cool_weekly_mm=70.0, flow_rate=0.5, days_elapsed=7, today_rain_mm=0.0, rain_day_history_mm=[0.0] * 10,
        rain_eff_low=0.5, rain_eff_mid=0.75, rain_eff_high=0.9, normal_interval_days=7, hot_interval_days=7,
        root_zone_mm=30.0,
    )
    assert plan.interval_target_mm == 30.0 and plan.root_zone_capped_mm == pytest.approx(40.0)
    assert plan.calc_runtime_minutes == 60


@pytest.mark.asyncio
async def test_root_depth_shows_and_hides_the_rest(hass):
    c = await _zone(hass)
    hidden = visibility.hidden_for(c)
    assert ("number", "soil_holding_mm_per_m") in hidden and ("sensor", "root_zone") in hidden
    assert ("number", "root_depth_mm") not in hidden
    await _set(c, root_depth_mm=500)
    hidden = visibility.hidden_for(c)
    assert ("number", "soil_holding_mm_per_m") not in hidden and ("sensor", "root_zone") not in hidden


@pytest.mark.asyncio
async def test_check_my_setup_offers_root_depth_on_an_upgraded_zone(hass):
    await zf_messages.async_setup(hass)
    c = await _zone(hass)
    assert "root_zone" in {i["id"] for i in setup_check.run_checks(c)}
    await _set(c, root_depth_mm=500)
    assert "root_zone" not in {i["id"] for i in setup_check.run_checks(c)}


@pytest.mark.asyncio
async def test_the_root_zone_sensor(hass):
    from homeassistant.helpers.entity_component import async_update_entity

    c = await _tiers_zone(hass, 42.0, 3)
    entity = next(s.entity_id for s in hass.states.async_all("sensor") if s.entity_id.endswith("root_zone_holds"))
    await async_update_entity(hass, entity)
    assert hass.states.get(entity).state == "unavailable"
    await _set(c, root_depth_mm=700, soil_holding_mm_per_m=130, wetted_area_pct=40, allowed_depletion_pct=40)
    await async_update_entity(hass, entity)
    state = hass.states.get(entity)
    assert float(state.state) == pytest.approx(36.4)
    assert state.attributes["waters_every_days"] == 2 and state.attributes["interval_shortened"] is True


@pytest.mark.asyncio
async def test_a_new_soil_type_sets_the_holding_capacity(hass):
    c = await _zone(hass)
    entity = next(s.entity_id for s in hass.states.async_all("select") if s.entity_id.endswith("soil_type"))
    await hass.services.async_call("select", "select_option", {"entity_id": entity, "option": "sandy"}, blocking=True)
    assert c.number("soil_holding_mm_per_m") == 80.0
    await _set(c, soil_holding_mm_per_m=95)
    drainage = next(s.entity_id for s in hass.states.async_all("select") if s.entity_id.endswith("drainage"))
    options = hass.states.get(drainage).attributes["options"]
    await hass.services.async_call("select", "select_option", {"entity_id": drainage, "option": options[-1]}, blocking=True)
    assert c.number("soil_holding_mm_per_m") == 95.0  # drainage leaves it alone


@pytest.mark.asyncio
async def test_a_new_irrigation_method_sets_the_wetted_share_at_the_next_start(hass):
    from custom_components.zoneflow.const import CONF_IRRIGATION_METHOD

    c = await _zone(hass)
    assert c.store.state.wetted_method == c.irrigation_method
    await _set(c, wetted_area_pct=55)
    hass.config_entries.async_update_entry(c.entry, options={**c.entry.options, CONF_IRRIGATION_METHOD: "sprinkler"})
    await hass.async_block_till_done()
    await c.async_method_changed()
    assert c.number("wetted_area_pct") == 100.0 and c.store.state.wetted_method == "sprinkler"
    await _set(c, wetted_area_pct=60)
    await c.async_method_changed()  # no change of method: the person's value stays
    assert c.number("wetted_area_pct") == 60.0


def test_imperial_root_depth_in_inches_and_holding_in_inches_per_foot():
    assert units.unit("root_depth_mm", "mm", True) == "in" and units.step("root_depth_mm", 50.0, True) == 1.0
    assert units.to_display("root_depth_mm", 254.0, True) == pytest.approx(10.0)
    assert units.unit("soil_holding_mm_per_m", "mm/m", True) == "in/ft"
    assert units.to_display("soil_holding_mm_per_m", 150.0, True) == pytest.approx(1.8)
    assert units.to_metric("soil_holding_mm_per_m", 1.8, True) == pytest.approx(150.0)
    lo, hi = units.display_range("soil_holding_mm_per_m", 40.0, 250.0, 5.0, True)
    assert lo <= 0.48 and hi >= 3.0


# --- setup ----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_new_zone_starts_with_its_crops_root_zone(hass, fake_valve_services):
    from .test_kc_season import _create
    from custom_components.zoneflow.const import CONF_INITIAL_NUMBERS

    await _create(hass)  # tomatoes on drip
    entry = hass.config_entries.async_entries("zoneflow")[-1]
    numbers = entry.data[CONF_INITIAL_NUMBERS]
    assert numbers["root_depth_mm"] == 700.0 and numbers["allowed_depletion_pct"] == 40.0
    assert numbers["wetted_area_pct"] == 40.0 and numbers["soil_holding_mm_per_m"] == 140.0


@pytest.mark.asyncio
async def test_a_plant_type_with_no_curve_uses_its_own_root_depth(hass, fake_valve_services):
    from .test_kc_season import _create
    from custom_components.zoneflow.const import CONF_INITIAL_NUMBERS

    await _create(hass, plant="flowers")
    numbers = hass.config_entries.async_entries("zoneflow")[-1].data[CONF_INITIAL_NUMBERS]
    assert numbers["root_depth_mm"] == 300.0 and "allowed_depletion_pct" not in numbers
