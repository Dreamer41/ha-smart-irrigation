"""More intent-level scenarios: rain gauge end to end, estimates vs what
actually happens, restarts, manual vs scheduled runs, snooze/forecast/soil
moisture interplay. Same CompressedTime harness as test_scenarios_cycles.
"""
from __future__ import annotations

import pytest
import homeassistant.util.dt as dt_util

from custom_components.zoneflow.const import DOMAIN

from .scenario_harness import CompressedTime
from .test_scenarios_cycles import DAY, VALVE, _delivered_mm, _history, _set, _tolerance_mm, _zone
from .test_smoke_setup import OUTDOOR_TEMP, RAIN_COUNTER, make_entry

SOIL = "sensor.soil_moisture_zone1"
WEATHER = "weather.home"


def _sensor(hass, fragment):
    return next(s.entity_id for s in hass.states.async_all("sensor") if fragment in s.entity_id)


def _sensor_value(hass, fragment):
    entity_id = _sensor(hass, fragment)
    ent = next(e for e in hass.data["sensor"].entities if e.entity_id == entity_id)
    return ent.native_value


# ---------------------------------------------------------------------------
# Rain gauge: tips -> mm -> windows -> daily history -> credit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rain_tips_flow_through_windows_daily_history_and_credit(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    await _set(controller, rain_mm_per_tip=0.5)
    for tips in ("4", "10", "16"):  # 16 tips x 0.5 = 8 mm today
        hass.states.async_set(RAIN_COUNTER, tips)
        await hass.async_block_till_done()

    assert controller.rain_windows()["24h"] == pytest.approx(8.0)
    assert controller.today_rain_mm() == pytest.approx(8.0)

    controller._on_daily_shift(None)  # 23:59:50
    controller._on_midnight(None)     # 00:00:00
    await hass.async_block_till_done()
    assert controller.store.state.rain_day_history_mm[0] == pytest.approx(8.0)
    assert controller.today_rain_mm() == pytest.approx(0.0)

    # That 8 mm is credited against the next due cycle (see the cycle tests
    # for the efficiency curve: 8 mm -> 0.44 -> 3.52 mm).
    state = controller.store.state
    state.rain_samples = [[ts - 3 * 3600, mm] for ts, mm in state.rain_samples]  # not "right now"
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    state.rain_day_history_mm = [8.0] + [0.0] * 9
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert _delivered_mm(clock, controller) == pytest.approx(20.0 - 3.52, abs=_tolerance_mm(controller, 3))


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=(
    "FINDING: the rain tracker assumes the tip counter never goes down. If it "
    "resets to 0 (counter helper reset, or a gauge that forgets its count on "
    "reboot), rain from before the reset vanishes from every window and "
    "later windows under-count by that amount for up to 14 days -- less rain "
    "credit and possibly a missed heavy-rain holdoff."
))
async def test_rain_counter_reset_to_zero_is_not_negative_rain_or_a_storm(hass, fake_valve_services, monkeypatch, tmp_path):
    """A counter helper being reset (or the gauge's battery swapped) drops
    the raw count back to 0. That must read as "no new rain", not a
    negative amount -- and the next real tips must count normally."""
    controller, _, events = await _zone(hass, monkeypatch, tmp_path)
    for tips in ("20", "0", "4"):
        hass.states.async_set(RAIN_COUNTER, tips)
        await hass.async_block_till_done()

    windows = controller.rain_windows()
    assert all(v >= 0 for v in windows.values())
    assert windows["24h"] == pytest.approx((20 + 4) * 0.3)
    assert "Significant Rain" not in events


@pytest.mark.asyncio
async def test_significant_rain_fires_once_per_threshold_crossed_not_per_tip(hass, fake_valve_services, monkeypatch, tmp_path):
    """One storm logs once per threshold it crosses (24h 35 mm, 4-day 50 mm,
    7-day 100 mm) -- faithful to the original automation's three triggers --
    and never again on every further tip. Each crossing restarts the
    drydown holdoff from that moment."""
    controller, _, events = await _zone(hass, monkeypatch, tmp_path)
    stamps = []
    for tips in range(100, 200, 10):  # 30 mm -> 57 mm: crosses 35 (24h) then 50 (4d)
        hass.states.async_set(RAIN_COUNTER, str(tips))
        await hass.async_block_till_done()
        stamps.append(controller.store.state.last_significant_rain_ts)
    assert events.count("Significant Rain") == 2
    assert len({t for t in stamps if t is not None}) == 2  # holdoff anchor moved once per crossing


# ---------------------------------------------------------------------------
# Estimates vs what the controller actually does
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("peaks,interval", [((30.5, 30.5, 30.5), 4), ((33.0, 33.0, 33.0), 3)])
async def test_next_run_estimate_matches_when_the_cycle_really_becomes_due(
    hass, fake_valve_services, monkeypatch, tmp_path, peaks, interval
):
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=0, peaks=peaks)
    estimate = _sensor_value(hass, "next_irrigation_estimate").timestamp()
    last = controller.store.state.last_routine_ts
    assert estimate - last == pytest.approx(interval * DAY, abs=60)

    # One day before the estimate: not due. At the estimate: due.
    controller.store.state.last_routine_ts = last - (interval - 1) * DAY
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert clock.pulses == []
    controller.store.state.last_routine_ts = last - interval * DAY
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert clock.valve_minutes(VALVE) > 0


@pytest.mark.asyncio
async def test_next_run_estimate_includes_the_rain_holdoff(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=3, peaks=(30.5, 30.5, 30.5))
    now = dt_util.utcnow().timestamp()
    controller.store.state.last_significant_rain_ts = now - 1 * DAY  # holdoff ends in 3 days
    estimate = _sensor_value(hass, "next_irrigation_estimate").timestamp()
    assert estimate == pytest.approx(now + 3 * DAY, abs=60)
    assert _sensor_value(hass, "days_until_next_run") == pytest.approx(3.0, abs=0.1)


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=(
    "FINDING: the next-run estimate uses the plain 3-day peak average, but "
    "the real cycle uses the dropout-aware one -- with a dead temperature "
    "sensor and hot history on record, the dashboard says 3 days while the "
    "zone actually waits 4."
))
async def test_next_run_estimate_agrees_with_the_cycle_when_the_temp_sensor_is_dead(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, _, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=0, peaks=(34.0, 34.0, 34.0))
    hass.states.async_set(OUTDOOR_TEMP, "unavailable")
    await hass.async_block_till_done()
    estimate = _sensor_value(hass, "next_irrigation_estimate").timestamp()
    assert estimate - controller.store.state.last_routine_ts == pytest.approx(4 * DAY, abs=60)


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=(
    "FINDING: README says Days Until Next Run counts down to whichever comes "
    "first, the next routine cycle or the next deep soak -- the sensor only "
    "looks at the routine cycle."
))
async def test_days_until_next_run_counts_a_sooner_deep_soak(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=1, last_deep_days_ago=13, peaks=(30.5, 30.5, 30.5))
    # Routine next in 3 days, deep soak next in 1 day.
    assert _sensor_value(hass, "days_until_next_run") == pytest.approx(1.0, abs=0.1)


@pytest.mark.asyncio
async def test_last_water_delivered_estimate_matches_a_real_cycle(hass, fake_valve_services, monkeypatch, tmp_path):
    """The "Last Water Delivered (estimate)" sensor shows half the weekly
    target -- right for the original 3.5-day average cadence. Check it's in
    the same ballpark as what a real normal-tier cycle puts on."""
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    estimate = _sensor_value(hass, "last_water_delivered")
    delivered = _delivered_mm(clock, controller)
    assert estimate == pytest.approx(17.5)
    assert abs(estimate - delivered) / delivered < 0.15  # within 15% of the real 20 mm


# ---------------------------------------------------------------------------
# Manual vs scheduled, snooze, forecast, soil moisture
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manual_button_on_a_due_day_gives_exactly_the_scheduled_dose(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    scheduled = clock.valve_minutes(VALVE)

    clock.reset()
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    button = next(s.entity_id for s in hass.states.async_all("button") if "run_routine" in s.entity_id)
    await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
    await hass.async_block_till_done()
    assert clock.valve_minutes(VALVE) == scheduled


@pytest.mark.asyncio
async def test_snooze_skips_today_then_tomorrow_gets_one_normal_dose_not_two(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    await controller.snooze_today()
    await controller.run_routine_irrigation()
    await controller.run_deep_soak()
    await hass.async_block_till_done()
    assert clock.pulses == []

    # "Tomorrow": the snooze date no longer matches, and the zone is now 5
    # days since its last run -- it still gets one 4-day dose, not a catch-up.
    controller.store.state.snooze_date_iso = "2000-01-01"
    _history(controller, last_routine_days_ago=5, peaks=(30.5, 30.5, 30.5))
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert _delivered_mm(clock, controller) == pytest.approx(20.0, abs=_tolerance_mm(controller, 3))


@pytest.mark.asyncio
async def test_long_gap_warns_and_still_applies_one_interval_dose(hass, fake_valve_services, monkeypatch, tmp_path):
    """Documents a design choice: after 12 days without water (e.g. the
    system was off), the cycle warns and applies one normal interval's
    worth -- it deliberately does not try to pour the whole backlog on at
    once."""
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=12, peaks=(30.5, 30.5, 30.5))
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert events[0] == "Irrigation Overdue"
    assert _delivered_mm(clock, controller) == pytest.approx(20.0, abs=_tolerance_mm(controller, 3))


@pytest.mark.asyncio
async def test_forecast_rain_holds_off_then_dry_spell_override_waters_the_normal_dose(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path, weather_entity=WEATHER)
    hass.states.async_set(WEATHER, "rainy")

    async def forecast_rain(*_args, **_kwargs):
        return (10.0, 90.0)  # 10 mm at 90% -- always "rain coming", never arrives

    monkeypatch.setattr(controller, "_get_forecast_precip_mm", forecast_rain)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert clock.pulses == []  # held off for the forecast

    # Two dry days later the forecast still says rain, none has fallen ->
    # the dry-spell override (2 days) waters anyway, with the normal dose.
    s = controller.store.state
    s.forecast_routine_skip_start_ts = (s.forecast_routine_skip_start_ts or dt_util.utcnow().timestamp()) - 2 * DAY - 60
    _history(controller, last_routine_days_ago=6, peaks=(30.5, 30.5, 30.5))
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert _delivered_mm(clock, controller) == pytest.approx(20.0, abs=_tolerance_mm(controller, 3))


@pytest.mark.asyncio
async def test_dry_soil_waters_early_with_a_full_dose_and_wet_soil_blocks_an_overdue_one(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path, soil_moisture_entity=SOIL)

    hass.states.async_set(SOIL, "12")  # below 20% dry threshold
    _history(controller, last_routine_days_ago=1, peaks=(30.5, 30.5, 30.5))
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    # Documents current behavior: the forced early run applies the full
    # interval dose (weekly/7 x 4), not a 1-day share.
    assert _delivered_mm(clock, controller) == pytest.approx(20.0, abs=_tolerance_mm(controller, 3))

    clock.reset()
    hass.states.async_set(SOIL, "75")  # above 60% wet threshold
    _history(controller, last_routine_days_ago=9, peaks=(30.5, 30.5, 30.5))
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert clock.pulses == []


# ---------------------------------------------------------------------------
# Restarts / reloads mid-season
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reload_keeps_history_settings_and_does_not_rewater(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    await _set(controller, crop_coefficient=0.65, target_weekly_mm=40)
    controller.store.state.demand_model = "et_curve"
    controller.store.state.rain_day_history_mm = [3.3] + [0.0] * 9
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    watered_at = controller.store.state.last_routine_ts
    await controller.store.async_save()

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    reloaded = hass.data[DOMAIN][entry.entry_id]
    clock2 = CompressedTime(hass, [VALVE]).install(monkeypatch)

    s = reloaded.store.state
    assert s.last_routine_ts == watered_at
    assert s.demand_model == "et_curve"
    assert s.rain_day_history_mm[0] == 3.3
    assert reloaded.number("crop_coefficient") == 0.65
    assert reloaded.number("target_weekly_mm") == 40

    await reloaded.run_routine_irrigation()  # just watered -> must not water again
    await hass.async_block_till_done()
    assert clock2.pulses == []


@pytest.mark.asyncio
async def test_test_pulse_waters_briefly_but_does_not_count_as_a_routine_run(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    before = controller.store.state.last_routine_ts
    await controller.test_pulse(10)
    await hass.async_block_till_done()
    assert hass.states.get(VALVE).state == "off"
    assert controller.store.state.last_routine_ts == before
    assert controller.store.state.lock_on is False


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=(
    "FINDING (safety): on a normal HA boot ZoneFlow loads before HA has "
    "started, so the restart safety check is scheduled from the "
    "homeassistant_start event -- but through a plain (non-@callback) "
    "function, which HA runs in a worker thread, where creating the task "
    "fails ('loop is not the running loop'). The check never runs: a lock "
    "and an open valve left by a mid-cycle restart stay until the 150/180-"
    "minute backstop watchdogs. Seen live in the sandbox log on every restart."
))
async def test_restart_safety_check_runs_when_zoneflow_loads_before_ha_has_started(hass, fake_valve_services):
    from homeassistant.const import EVENT_HOMEASSISTANT_START
    from homeassistant.core import CoreState

    from .test_smoke_setup import PUMP

    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "28.0")
    await hass.async_block_till_done()

    if hasattr(hass, "set_state"):
        hass.set_state(CoreState.not_running)
    else:
        hass.state = CoreState.not_running
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    # State persisted from before the restart: mid-cycle, valve open.
    controller.store.state.lock_on = True
    hass.states.async_set(VALVE, "on")
    await hass.async_block_till_done()

    hass.bus.async_fire(EVENT_HOMEASSISTANT_START)
    await hass.async_block_till_done()
    import asyncio

    for _ in range(20):  # the check runs as a background task (not waited on by block_till_done)
        await asyncio.sleep(0)
    await hass.async_block_till_done()

    assert controller.store.state.lock_on is False
    assert hass.states.get(VALVE).state == "off"


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason=(
    "FINDING: a brand-new zone (never watered) measures its gap from 1970, "
    "so its very first routine run logs and phone-notifies 'Irrigation "
    "Overdue: ~20,000 days since last watering'. Seen live in the sandbox."
))
async def test_a_brand_new_zones_first_run_is_not_reported_as_overdue(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    controller.store.state.last_routine_ts = None  # never watered
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert clock.valve_minutes(VALVE) > 0
    assert "Irrigation Overdue" not in events
