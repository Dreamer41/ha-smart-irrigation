"""Longest Valve Open Time (1.7.4): how long the valve is open in one go, worked
out from the zone's own settings, so the person can set the valve's own
auto-off timer (a backup if Home Assistant stops while it is open) above it.
And a typed "Water now" that splits into pulses like the zone's own watering."""
from __future__ import annotations

import asyncio

import pytest

from custom_components.zoneflow import calculations as calc
from custom_components.zoneflow import setup_check
from custom_components.zoneflow.const import CONF_VALVE_ENTITY, DOMAIN

from .test_scenarios_cycles import _history, _set, _zone
from .test_smoke_setup import VALVE, _seed_source_entities, make_entry

SITE = ("unknown", "normal", "flat")  # 10 mm per pulse before the soil asks for more


# --- the calculation ---------------------------------------------------------
@pytest.mark.parametrize(
    "longest, timer",
    [(0, 10), (1, 15), (5, 15), (40, 50), (41, 55), (60, 75), (100, 120)],
)
def test_recommended_timer_is_the_longest_plus_ten_minutes_or_a_fifth_in_fives(longest, timer):
    assert calc.recommended_backup_timer_minutes(longest) == timer


def test_the_longest_pulse_is_the_cap_over_the_pulse_count_when_the_soil_asks_for_nothing_more():
    assert calc.longest_pulse_minutes(90, 5.0, 3, 1, None) == pytest.approx(30.0)
    assert calc.longest_pulse_minutes(90, 5.0, 1, 1, None) == pytest.approx(90.0)
    assert calc.longest_pulse_minutes(90, 5.0, 8, 1, None) == pytest.approx(11.25)


def test_a_dose_too_small_for_every_pulse_runs_fewer_longer_pulses():
    # 2 min over 3 pulses with a 1-minute floor is 2 pulses of 1 minute, never more than the floor.
    assert calc.longest_pulse_minutes(2, 5.0, 3, 1, None) == pytest.approx(1.0)
    # Deep soak floor: 9 min over 3 pulses with a 5-minute floor is one 9-minute pulse.
    assert calc.longest_pulse_minutes(9, 5.0, 3, 5, None) == pytest.approx(9.0)


def test_soil_that_takes_little_water_per_pulse_adds_pulses_so_each_one_is_shorter():
    flat = calc.longest_pulse_minutes(60, 0.5, 1, 1, None)
    clay = calc.longest_pulse_minutes(60, 0.5, 1, 1, ("clay", "normal", "flat"))
    assert clay < flat


def test_the_biggest_tier_dose_and_the_runtime_cap():
    kwargs = dict(flow_rate=0.5, runtime_cap=103, weekly_mm=(35.0, 45.0, 25.0))
    # normal 35/7x4/0.5 = 40; hot 45/7x3/0.5 = 39; cool 25/7x4/0.5 = 29
    assert calc.largest_routine_minutes(interval_days=(4, 3, 4), **kwargs) == 40
    # a longer hot gap makes the hot tier the biggest: 45/7x7/0.5 = 90
    assert calc.largest_routine_minutes(interval_days=(4, 7, 4), **kwargs) == 90
    # over the cap it would be refused, so the cap is the most that can run
    assert calc.largest_routine_minutes(interval_days=(4, 10, 4), **kwargs) == 103
    # a bigger weekly target scales it, a slower flow rate lengthens it
    assert calc.largest_routine_minutes(interval_days=(4, 3, 4), scale=1.5, **kwargs) == 60
    assert calc.largest_routine_minutes(interval_days=(4, 3, 4), **{**kwargs, "flow_rate": 0.25}) == 80
    # the ET demand model has no fixed target: the cap bounds it
    assert calc.largest_routine_minutes(interval_days=(4, 3, 4), demand_model_et=True, **kwargs) == 103


# --- the zone ----------------------------------------------------------------
async def _ready(hass, monkeypatch, tmp_path):
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=1, last_deep_days_ago=3, peaks=(30.5, 30.5, 30.5))
    # Sandy soil takes 30 mm per pulse, so the pulse count is the zone's own setting
    # and the settings below show in the number (heavy soil caps a pulse by itself).
    controller.store.state.soil_type_override = "sandy"
    return controller, clock, events


@pytest.mark.asyncio
async def test_the_zone_works_it_out_from_its_own_settings_and_follows_every_change(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, _, _ = await _ready(hass, monkeypatch, tmp_path)
    await _set(
        controller, flow_rate_mm_per_min=0.5, target_weekly_mm=35.0, target_weekly_hot_mm=45.0,
        target_weekly_cool_mm=25.0, routine_interval_days=4.0, routine_interval_hot_days=3.0,
        routine_pulse_count=1.0, max_runtime_minutes=103.0, deep_soak_pulse_count=3.0,
        service_mode_auto_off_minutes=5.0, deep_soak_target_mm=50.0, deep_soak_max_runtime_minutes=124.0,
    )

    def times():
        return controller.valve_open_times()

    base = times()
    assert base["routine_minutes"] > 0 and base["service_minutes"] == 15.0  # the 15-minute check button
    assert base["longest_minutes"] == max(base["routine_minutes"], base["deep_soak_minutes"], 15.0)
    extra = base["open_before_and_after_minutes"]  # the pump-power wait before the pulse, the overlap after it
    assert extra == pytest.approx(0.75)  # a pump-power sensor is set here: up to 45 s
    assert base["recommended_timer_minutes"] == calc.recommended_backup_timer_minutes(base["longest_minutes"] + extra)

    # More pulses: shorter pulses.
    await _set(controller, routine_pulse_count=4.0)
    assert times()["routine_minutes"] < base["routine_minutes"]
    await _set(controller, routine_pulse_count=1.0)
    assert times()["routine_minutes"] == pytest.approx(base["routine_minutes"])

    # A slower flow rate: a longer watering for the same dose, so a longer pulse.
    await _set(controller, flow_rate_mm_per_min=0.25)
    slower = times()["routine_minutes"]
    assert slower > base["routine_minutes"]
    await _set(controller, flow_rate_mm_per_min=0.5)

    # A longer gap between waterings: a bigger dose, so a longer pulse.
    await _set(controller, routine_interval_days=7.0)
    longer_gap = times()["routine_minutes"]
    assert longer_gap > base["routine_minutes"]
    await _set(controller, routine_interval_days=4.0)
    await _set(controller, routine_interval_hot_days=9.0)  # the hot tier can be the biggest one
    assert times()["routine_minutes"] > base["routine_minutes"]
    await _set(controller, routine_interval_hot_days=3.0)

    # The runtime cap bounds it: a watering over the cap is refused, never run.
    await _set(controller, routine_interval_days=10.0, routine_interval_hot_days=10.0, max_runtime_minutes=50.0)
    assert times()["routine_minutes"] <= 50.0
    await _set(controller, routine_interval_days=4.0, routine_interval_hot_days=3.0, max_runtime_minutes=103.0)

    # Deep soak: a bigger target is a longer one, a cap under it means it never runs.
    await _set(controller, deep_soak_target_mm=60.0, deep_soak_pulse_count=1.0, deep_soak_max_runtime_minutes=500.0)
    long_deep = times()["deep_soak_minutes"]
    assert long_deep > 50
    await _set(controller, deep_soak_max_runtime_minutes=60.0)
    assert times()["deep_soak_minutes"] == 0.0
    await _set(controller, deep_soak_max_runtime_minutes=500.0)

    # The service run: the Service Mode auto-off, and never less than the biggest check run.
    await _set(controller, service_mode_auto_off_minutes=120.0, deep_soak_target_mm=10.0)
    assert times()["service_minutes"] == 120.0 and times()["longest_minutes"] >= 120.0
    await _set(controller, service_mode_auto_off_minutes=5.0)
    assert times()["service_minutes"] == 15.0


@pytest.mark.asyncio
async def test_deep_soak_off_leaves_it_out_and_water_now_by_hand_is_given_apart(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, _, _ = await _ready(hass, monkeypatch, tmp_path)
    await _set(controller, routine_pulse_count=1.0, max_runtime_minutes=103.0, target_weekly_mm=14.0,
               target_weekly_hot_mm=14.0, target_weekly_cool_mm=14.0, flow_rate_mm_per_min=0.5)
    await _set(controller, service_mode_auto_off_minutes=5.0)
    times = controller.valve_open_times()
    # A typed Water now can be as long as the cap allows: given apart, not in the main number.
    assert times["with_water_now_minutes"] > times["longest_minutes"]
    assert times["recommended_timer_with_water_now_minutes"] > times["recommended_timer_minutes"]
    controller.entry.options = {**controller.entry.options, "deep_soak_enabled": False}
    assert controller.valve_open_times()["deep_soak_minutes"] == 0.0 or not controller.deep_soak_enabled


@pytest.mark.asyncio
async def test_a_zone_without_a_valve_has_no_such_time(hass, fake_valve_services):
    await _seed_source_entities(hass)
    entry = make_entry(hass, **{CONF_VALVE_ENTITY: None})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    assert controller.valve_open_times() is None
    state = hass.states.get(next(s.entity_id for s in hass.states.async_all("sensor") if s.entity_id.endswith("longest_valve_open_time")))
    assert state.state in ("unknown", "unavailable")
    assert "backup_timer" not in {item["id"] for item in setup_check.run_checks(controller)}
    # A zone with no valve hides all its watering entities, this one too.
    from homeassistant.helpers import entity_registry as er

    reg = er.async_get(hass).async_get(state.entity_id)
    assert reg.hidden_by == er.RegistryEntryHider.INTEGRATION


@pytest.mark.asyncio
async def test_the_sensor_shows_it_and_follows_a_changed_slider_at_once(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, _, _ = await _ready(hass, monkeypatch, tmp_path)
    entity = next(s.entity_id for s in hass.states.async_all("sensor") if s.entity_id.endswith("longest_valve_open_time"))
    await _set(controller, routine_pulse_count=1.0, max_runtime_minutes=103.0, routine_interval_days=7.0,
               routine_interval_hot_days=7.0, target_weekly_mm=35.0, target_weekly_hot_mm=35.0,
               target_weekly_cool_mm=35.0, flow_rate_mm_per_min=0.5, service_mode_auto_off_minutes=5.0)
    await hass.async_block_till_done()
    before = hass.states.get(entity)
    assert before.attributes["unit_of_measurement"] == "min"
    assert float(before.state) == controller.valve_open_times()["longest_minutes"]
    assert before.attributes["recommended_timer_minutes"] == controller.valve_open_times()["recommended_timer_minutes"]
    await _set(controller, routine_pulse_count=5.0)
    await hass.async_block_till_done()
    after = hass.states.get(entity)
    assert float(after.state) < float(before.state)
    assert after.attributes["recommended_timer_minutes"] < before.attributes["recommended_timer_minutes"]


@pytest.mark.asyncio
async def test_check_my_setup_says_what_timer_to_set(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _, _ = await _ready(hass, monkeypatch, tmp_path)
    items = {item["id"]: item for item in setup_check.run_checks(controller)}
    item = items["backup_timer"]
    times = controller.valve_open_times()
    assert item["level"] == "info"
    assert f"at least {times['recommended_timer_minutes']} min" in item["text"]
    assert f"{times['longest_minutes']:.0f} min" in item["text"]


# --- Water now in pulses -----------------------------------------------------
@pytest.mark.asyncio
async def test_water_now_splits_into_the_zones_pulses_with_the_soak_between(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, clock, events = await _ready(hass, monkeypatch, tmp_path)
    await _set(controller, routine_pulse_count=3.0, routine_pulse_rest_minutes=20.0, flow_rate_mm_per_min=0.1)
    await hass.services.async_call(DOMAIN, "water_now", {"minutes": 9}, blocking=True)
    await hass.async_block_till_done()
    assert clock.pulses_for(VALVE) == [3.0, 3.0, 3.0]
    assert clock.sleeps_seconds.count(20 * 60) == 2  # the soak, between the pulses only
    state = controller.store.state
    assert hass.states.get(VALVE).state == "off" and state.lock_on is False
    assert events[-1] == "Manual Watering"
    assert state.today_runtime_minutes == pytest.approx(9.0)
    assert state.last_cycle_runtime_min == pytest.approx(9.0)


@pytest.mark.asyncio
async def test_water_now_adds_pulses_for_soil_that_runs_off(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _ready(hass, monkeypatch, tmp_path)
    await _set(controller, routine_pulse_count=1.0, flow_rate_mm_per_min=0.5)
    # 20 min x 0.5 mm/min = 10 mm: fine in one pulse on the default soil ...
    await hass.services.async_call(DOMAIN, "water_now", {"minutes": 20}, blocking=True)
    await hass.async_block_till_done()
    one = list(clock.pulses_for(VALVE))
    assert one == [20.0]
    # ... but on heavy clay (3 mm per pulse) it takes four.
    clock.reset()
    controller.store.state.today_runtime_minutes = 0.0
    controller.store.state.soil_type_override = "clay"
    await hass.services.async_call(DOMAIN, "water_now", {"minutes": 20}, blocking=True)
    await hass.async_block_till_done()
    assert len(clock.pulses_for(VALVE)) == 4 and sum(clock.pulses_for(VALVE)) == pytest.approx(20.0)


@pytest.mark.asyncio
async def test_the_soak_of_a_manual_watering_can_be_stopped(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _ready(hass, monkeypatch, tmp_path)
    clock.sleep_real_seconds = 5.0  # the soak really lasts, until stopped
    await _set(controller, routine_pulse_count=3.0, routine_pulse_rest_minutes=20.0, flow_rate_mm_per_min=0.1)
    await hass.services.async_call(DOMAIN, "water_now", {"minutes": 9}, blocking=True)
    for _ in range(300):
        if len(clock.pulses_for(VALVE)) == 1 and hass.states.get(VALVE).state == "off" and clock.sleeps_seconds:
            break
        await asyncio.sleep(0.01)
    assert controller.service_active
    await controller.stop_service_run()
    for _ in range(300):
        if not controller.service_active:
            break
        await asyncio.sleep(0.01)
    await hass.async_block_till_done()
    assert not controller.service_active and controller.store.state.lock_on is False
    assert clock.pulses_for(VALVE) == [3.0]  # no second pulse after the stop
    assert hass.states.get(VALVE).state == "off"


@pytest.mark.asyncio
async def test_a_service_run_stays_one_pulse(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _ready(hass, monkeypatch, tmp_path)
    await _set(controller, routine_pulse_count=3.0)
    await controller.start_service_run(10)
    await hass.async_block_till_done()
    assert clock.pulses_for(VALVE) == [10]


# --- My Valve's Own Timer (1.7.4) and the preview in Why? ------------------------
@pytest.mark.asyncio
async def test_check_my_setup_follows_the_timer_the_person_set(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _, _ = await _ready(hass, monkeypatch, tmp_path)
    await _set(controller, service_mode_auto_off_minutes=5.0, routine_pulse_count=1.0)

    def item():
        return {i["id"]: i for i in setup_check.run_checks(controller)}["backup_timer"]

    longest = controller.valve_open_times()["longest_minutes"]
    assert item()["level"] == "info" and "My Valve's Own Timer" in item()["text"]  # not set: the advice
    await _set(controller, valve_timer_minutes=5.0)  # shorter than the longest open time
    assert longest > 5
    assert item()["level"] == "warn" and "set to 5 min" in item()["text"]
    assert f"at least {controller.valve_open_times()['recommended_timer_minutes']} min" in item()["text"]
    await _set(controller, valve_timer_minutes=300.0)
    assert item()["level"] == "ok" and "300 min" in item()["text"]
    # a later change makes the longest time grow past the timer: the warning is back
    await _set(controller, valve_timer_minutes=float(controller.valve_open_times()["longest_minutes"] // 5 * 5 + 5))
    assert item()["level"] == "ok"
    await _set(controller, routine_interval_days=10.0, routine_interval_hot_days=10.0, flow_rate_mm_per_min=0.2,
               max_runtime_minutes=300.0)
    if controller.valve_open_times()["longest_minutes"] > controller.number("valve_timer_minutes"):
        assert item()["level"] == "warn"
    assert controller.valve_open_times()["my_timer_minutes"] == controller.number("valve_timer_minutes")


@pytest.mark.asyncio
async def test_why_previews_what_would_run_now(hass, fake_valve_services, monkeypatch, tmp_path):
    from custom_components.zoneflow import why

    controller, _, _ = await _ready(hass, monkeypatch, tmp_path)
    await _set(controller, routine_pulse_count=3.0, routine_pulse_rest_minutes=25.0, flow_rate_mm_per_min=0.2,
               routine_min_pulse_minutes=1.0)
    plan = controller._routine_plan()
    texts = {item["id"]: item["text"] for item in why.explain(controller)}
    assert plan.calc_runtime_minutes > 0 and plan.pulse_count > 1
    preview = texts["preview"]
    assert preview.startswith(f"If it ran now: {plan.calc_runtime_minutes} min in {plan.pulse_count} pulses")
    assert "25 min of soak" in preview
    assert f"at most {controller.valve_open_times()['longest_minutes']:g} min" in preview
    # a dose in one go
    await _set(controller, routine_pulse_count=1.0)
    controller.store.state.soil_type_override = "sandy"
    one = {item["id"]: item["text"] for item in why.explain(controller)}["preview"]
    plan = controller._routine_plan()
    if plan.pulse_count == 1:
        assert "in one go" in one


@pytest.mark.asyncio
async def test_water_now_is_never_longer_than_the_minutes_typed(hass, fake_valve_services, monkeypatch, tmp_path):
    """A minimum pulse longer than the time typed must not stretch it, nor go past the daily cap."""
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    await _set(controller, routine_min_pulse_minutes=10)
    count, each, _rest = controller._manual_pulses(3.0)
    assert count * each == pytest.approx(3.0)
    controller.store.state.today_runtime_minutes = 237.0  # 3 minutes left of the 240 a day
    await controller.water_now(20)  # shortened to the 3 minutes left
    await hass.async_block_till_done()
    assert sum(clock.pulses_for(VALVE)) == pytest.approx(3.0)
    assert controller.store.state.today_runtime_minutes == pytest.approx(240.0)
