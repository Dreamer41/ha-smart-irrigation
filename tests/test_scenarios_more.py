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
async def test_rain_counter_reset_to_zero_is_not_negative_rain_or_a_storm(hass, fake_valve_services, monkeypatch, tmp_path):
    """Regression (seen live in the sandbox): a counter helper being reset,
    or a gauge that forgets its count on reboot, drops the raw count back to
    0. Rain already recorded must stay in every window, and the next real
    tips must add on top."""
    controller, _, events = await _zone(hass, monkeypatch, tmp_path)
    for tips in ("20", "0", "4"):
        hass.states.async_set(RAIN_COUNTER, tips)
        await hass.async_block_till_done()

    windows = controller.rain_windows()
    assert all(v >= 0 for v in windows.values())
    assert windows["24h"] == pytest.approx((20 + 4) * 0.3)
    assert "Significant Rain" not in events


@pytest.mark.asyncio
async def test_one_storm_sends_one_heavy_rain_alert_but_every_crossing_restarts_the_holdoff(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    """A storm that crosses both the 24h (35 mm) and 4-day (50 mm) lines used
    to log and phone-alert twice. Now: one alert, while each crossing still
    moves the drydown holdoff to that moment."""
    controller, _, events = await _zone(hass, monkeypatch, tmp_path)
    stamps = []
    for tips in range(100, 200, 10):  # 30 mm -> 57 mm
        hass.states.async_set(RAIN_COUNTER, str(tips))
        await hass.async_block_till_done()
        stamps.append(controller.store.state.last_significant_rain_ts)
    assert events.count("Significant Rain") == 1
    assert len({t for t in stamps if t is not None}) == 2


@pytest.mark.asyncio
async def test_a_new_storm_a_day_later_alerts_again(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _, events = await _zone(hass, monkeypatch, tmp_path)
    hass.states.async_set(RAIN_COUNTER, "120")  # 36 mm -> alert
    await hass.async_block_till_done()
    assert events.count("Significant Rain") == 1

    # A day and a half later the first storm has left the 24h window...
    s = controller.store.state
    s.rain_samples = [[ts - 36 * 3600, mm] for ts, mm in s.rain_samples]
    s.last_significant_rain_ts -= 36 * 3600
    s.last_significant_rain_alert_ts -= 36 * 3600
    hass.states.async_set(RAIN_COUNTER, "121")  # 24h window drops below 35 -> flag resets
    await hass.async_block_till_done()
    hass.states.async_set(RAIN_COUNTER, "250")  # a fresh 38.7 mm storm
    await hass.async_block_till_done()
    assert events.count("Significant Rain") == 2


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
async def test_next_run_estimate_agrees_with_the_cycle_when_the_temp_sensor_is_dead(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    """Regression: the estimate used the plain peak average while the real
    cycle uses the dropout-aware one (dashboard said 3 days, zone waited 4)."""
    controller, _, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=0, peaks=(34.0, 34.0, 34.0))
    hass.states.async_set(OUTDOOR_TEMP, "unavailable")
    await hass.async_block_till_done()
    estimate = _sensor_value(hass, "next_irrigation_estimate").timestamp()
    assert estimate - controller.store.state.last_routine_ts == pytest.approx(4 * DAY, abs=60)


@pytest.mark.asyncio
async def test_days_until_next_run_counts_a_sooner_deep_soak(hass, fake_valve_services, monkeypatch, tmp_path):
    """Regression: README promises whichever comes first, routine or deep
    soak -- the sensor used to look at routine only."""
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
async def test_restart_safety_check_runs_when_zoneflow_loads_before_ha_has_started(hass, fake_valve_services):
    """Regression (found live in the sandbox): on a normal HA boot ZoneFlow
    is set up before HA has started, so the restart safety check is
    scheduled from the homeassistant_start event. That listener used to be
    a plain function, which HA runs in a worker thread, where creating the
    task failed -- the check never ran, and a lock plus an open valve from
    a mid-cycle restart were left in place."""
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
async def test_a_brand_new_zones_first_run_is_not_reported_as_overdue(hass, fake_valve_services, monkeypatch, tmp_path):
    """Regression (seen live in the sandbox): a never-watered zone measured
    its gap from 1970 and phone-alerted "~20,000 days overdue"."""
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    controller.store.state.last_routine_ts = None  # never watered
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert clock.valve_minutes(VALVE) > 0
    assert "Irrigation Overdue" not in events


@pytest.mark.asyncio
async def test_rain_counter_that_reset_while_ha_was_down_keeps_its_rain(hass, fake_valve_services, monkeypatch, tmp_path):
    """The gauge rebooted (count back to 0) while HA itself was restarting:
    ZoneFlow first sees the lower count at setup. The rain recorded before
    must survive the reload, and new tips must add on top."""
    controller, _, _ = await _zone(hass, monkeypatch, tmp_path)
    for tips in ("10", "20"):
        hass.states.async_set(RAIN_COUNTER, tips)
        await hass.async_block_till_done()
    assert controller.rain_windows()["24h"] == pytest.approx(6.0)
    await controller.store.async_save()

    hass.states.async_set(RAIN_COUNTER, "0")  # reset happens "while HA is down"...
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    reloaded = hass.data[DOMAIN][entry.entry_id]
    assert reloaded.rain_windows()["24h"] == pytest.approx(6.0)

    hass.states.async_set(RAIN_COUNTER, "3")
    await hass.async_block_till_done()
    assert reloaded.rain_windows()["24h"] == pytest.approx(6.0 + 0.9)


@pytest.mark.asyncio
async def test_all_rain_sensors_are_precipitation_with_sensible_rounding(hass, fake_valve_services, monkeypatch, tmp_path):
    """On an HA set to imperial, Rain Today used to show raw conversion
    noise (0.12992125984252 in) while the other rain sensors stayed in mm.
    Now every rain sensor is a precipitation sensor in the same unit, with
    a display precision so the dashboard rounds it."""
    from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

    hass.config.units = US_CUSTOMARY_SYSTEM
    controller, _, _ = await _zone(hass, monkeypatch, tmp_path)
    hass.states.async_set(RAIN_COUNTER, "11")  # 3.3 mm
    await hass.async_block_till_done()

    rain_sensors = [s for s in hass.states.async_all("sensor") if s.entity_id.startswith("sensor.test_zone_rain_")]
    assert len(rain_sensors) == 6  # 5 windows + today
    for st in rain_sensors:
        ent = next(e for e in hass.data["sensor"].entities if e.entity_id == st.entity_id)
        ent.async_write_ha_state()
    await hass.async_block_till_done()
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    for st in (hass.states.get(s.entity_id) for s in rain_sensors):
        assert st.attributes["device_class"] == "precipitation", st.entity_id
        assert st.attributes["unit_of_measurement"] == "in", st.entity_id
        # The dashboard rounds to the registry's display precision (HA adds
        # decimals itself for the mm -> in conversion); without one it
        # showed every digit.
        options = registry.async_get(st.entity_id).options.get("sensor", {})
        assert options.get("suggested_display_precision") is not None, st.entity_id
    assert float(hass.states.get(_sensor(hass, "rain_today")).state) == pytest.approx(3.3 / 25.4, abs=0.001)


@pytest.mark.asyncio
async def test_a_rain_counter_glitch_to_zero_and_back_adds_no_fake_rain(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _, events = await _zone(hass, monkeypatch, tmp_path)
    hass.states.async_set(RAIN_COUNTER, "1500")
    await hass.async_block_till_done()
    controller.store.state.rain_samples = [[ts - 3 * DAY, mm] for ts, mm in controller.store.state.rain_samples]
    events.clear()  # the setup jump 0 -> 1500 was (correctly) a big "storm" three days ago
    for tips in ("0", "1500"):
        hass.states.async_set(RAIN_COUNTER, tips)
        await hass.async_block_till_done()
    assert controller.rain_windows()["24h"] == pytest.approx(0.0)
    assert "Significant Rain" not in events


@pytest.mark.asyncio
async def test_suppressed_crossings_do_not_stretch_the_alert_quiet_period(hass, fake_valve_services, monkeypatch, tmp_path):
    """Alert at t0, a crossing at t0+20h stays quiet, but a new storm at
    t0+40h alerts: the 24h quiet period runs from the last ALERT."""
    controller, _, events = await _zone(hass, monkeypatch, tmp_path)
    s = controller.store.state
    now = dt_util.utcnow().timestamp()
    s.last_significant_rain_alert_ts = now - 40 * 3600  # alert at t0
    s.last_significant_rain_ts = now - 20 * 3600        # quiet crossing at t0+20h
    hass.states.async_set(RAIN_COUNTER, "130")  # a new 39 mm storm now
    await hass.async_block_till_done()
    assert events.count("Significant Rain") == 1


@pytest.mark.asyncio
async def test_pulse_length_is_cleared_even_if_a_pulse_errors(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))

    async def boom(index):
        assert controller._expected_pulse_minutes is not None
        raise RuntimeError("switch integration fell over")

    clock.on_pulse = boom
    with pytest.raises(RuntimeError):
        await controller.run_routine_irrigation()
    assert controller._expected_pulse_minutes is None
    assert controller._valve_stuck_limit_minutes() == 150


@pytest.mark.asyncio
async def test_countdown_skips_a_deep_soak_held_back_by_a_wet_fortnight(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=1, last_deep_days_ago=20, peaks=(30.5, 30.5, 30.5))
    now = dt_util.utcnow().timestamp()
    controller.store.state.rain_samples = [[now - 10 * DAY, 0.0], [now - 5 * DAY, 45.0]]  # 45 mm >= 40 mm ceiling
    assert _sensor_value(hass, "days_until_next_run") == pytest.approx(3.0, abs=0.1)  # routine, not a stuck 0
