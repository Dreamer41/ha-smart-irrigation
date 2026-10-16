"""The days between routine waterings are settings (1.7.3): one for the normal
and cool tiers, one for the hot tier, starting at the old fixed 4 and 3."""
from __future__ import annotations

import pytest

from custom_components.zoneflow import calculations as calc
from custom_components.zoneflow import presets, visibility
from custom_components.zoneflow.const import DOMAIN, NUMBER_DEFAULTS

from .test_smoke_setup import _seed_source_entities, make_entry


def test_they_start_at_the_old_fixed_gaps():
    assert (NUMBER_DEFAULTS["routine_interval_days"], NUMBER_DEFAULTS["routine_interval_hot_days"]) == (4.0, 3.0)
    assert calc.routine_interval_days(32.0, 31.5) == 3 and calc.routine_interval_days(20.0, 31.5) == 4


def test_the_calculation_defaults_match_the_constants():
    from custom_components.zoneflow import const

    assert (calc.ROUTINE_NORMAL_INTERVAL_DAYS, calc.ROUTINE_HOT_INTERVAL_DAYS) == (
        const.ROUTINE_NORMAL_INTERVAL_DAYS, const.ROUTINE_HOT_INTERVAL_DAYS)


def test_the_gaps_follow_the_settings():
    assert calc.routine_interval_days(32.0, 31.5, normal_days=6, hot_days=2) == 2
    assert calc.routine_interval_days(25.0, 31.5, normal_days=6, hot_days=2) == 6
    assert calc.routine_interval_days(None, 31.5, normal_days=6, hot_days=2) == 6


def _plan(**kwargs):
    base = dict(
        avg_peak_temp=25.0, hot_threshold=31.5, cool_threshold=20.0,
        normal_weekly_mm=35.0, hot_weekly_mm=45.0, cool_weekly_mm=25.0, flow_rate=0.5,
        days_elapsed=10, today_rain_mm=0.0, rain_day_history_mm=[0.0] * 10,
        rain_eff_low=0.2, rain_eff_mid=0.6, rain_eff_high=1.0,
    )
    base.update(kwargs)
    return calc.plan_routine_irrigation(**base)


def test_a_longer_gap_gives_a_bigger_dose_so_the_week_still_gets_its_water():
    four = _plan(normal_interval_days=4).interval_target_mm
    seven = _plan(normal_interval_days=7).interval_target_mm
    assert seven == pytest.approx(four * 7 / 4)


@pytest.mark.asyncio
async def test_the_zone_uses_its_own_gaps_and_the_normal_tier_in_cool_weather(hass, fake_valve_services, monkeypatch):
    await _seed_source_entities(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    zone = hass.data[DOMAIN][entry.entry_id]
    assert zone._routine_interval_days() in (3, 4)  # untouched: as before
    await zone.numbers["routine_interval_days"].async_set_metric_value(6.0)
    await zone.numbers["routine_interval_hot_days"].async_set_metric_value(2.0)
    monkeypatch.setattr(zone, "effective_avg_peak_temp", lambda: 35.0)
    assert zone._routine_interval_days() == 2
    monkeypatch.setattr(zone, "effective_avg_peak_temp", lambda: 22.0)
    assert zone._routine_interval_days() == 6
    monkeypatch.setattr(zone, "effective_avg_peak_temp", lambda: 10.0)  # cool shares the normal gap
    assert zone._routine_interval_days() == 6
    assert ("number", "routine_interval_days") not in visibility.hidden_for(zone)
    assert ("number", "routine_interval_hot_days") not in visibility.hidden_for(zone)
    assert "routine_interval_days" in presets.COPY_NUMBER_KEYS and "routine_interval_hot_days" in presets.COPY_NUMBER_KEYS


@pytest.mark.asyncio
async def test_why_shows_the_same_dose_as_the_run(hass, fake_valve_services):
    from custom_components.zoneflow import why

    await _seed_source_entities(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    zone = hass.data[DOMAIN][entry.entry_id]
    await zone.numbers["routine_interval_days"].async_set_metric_value(7.0)
    await zone.numbers["routine_interval_hot_days"].async_set_metric_value(7.0)
    _scale, plan = why._preview(zone)
    assert plan.interval_target_mm == pytest.approx(zone._routine_plan().interval_target_mm)
    assert plan.interval_target_mm == pytest.approx(35.0, abs=0.5)  # 7 of 7 days of the 35 mm week


@pytest.mark.asyncio
async def test_check_my_setup_warns_when_one_watering_no_longer_fits_the_runtime_cap(hass, fake_valve_services):
    from custom_components.zoneflow import setup_check

    await _seed_source_entities(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    zone = hass.data[DOMAIN][entry.entry_id]
    assert not any(i["id"] == "cap" for i in setup_check.run_checks(zone))
    await zone.numbers["routine_interval_days"].async_set_metric_value(10.0)
    await zone.numbers["routine_interval_hot_days"].async_set_metric_value(10.0)
    items = [i for i in setup_check.run_checks(zone) if i["id"] == "cap"]
    assert items and items[0]["level"] == "warn"


@pytest.mark.asyncio
async def test_a_long_gap_that_is_on_time_is_not_reported_overdue(hass, fake_valve_services, monkeypatch, tmp_path):
    import homeassistant.util.dt as dt_util

    from .scenario_harness import CompressedTime

    await _seed_source_entities(hass)
    entry = make_entry(hass, csv_path=str(tmp_path / "a.csv"))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    zone = hass.data[DOMAIN][entry.entry_id]
    for key in ("routine_interval_days", "routine_interval_hot_days"):
        await zone.numbers[key].async_set_metric_value(10.0)
    zone.numbers["max_runtime_minutes"].metric_value = 900
    zone.numbers["max_daily_runtime_minutes"].metric_value = 900
    zone.store.state.last_routine_ts = dt_util.utcnow().timestamp() - 9.8 * 86400  # just due: 10 days minus the buffer
    zone.store.state.last_significant_rain_ts = 0.0
    CompressedTime(hass, ["switch.watering1"]).install(monkeypatch)
    logged = []
    real = zone._log_event

    async def spy(**kwargs):
        logged.append(kwargs.get("event_type"))
        return await real(**kwargs)

    monkeypatch.setattr(zone, "_log_event", spy)
    await zone.run_routine_irrigation(manual=False)
    await hass.async_block_till_done()
    assert "Irrigation Overdue" not in logged, logged
