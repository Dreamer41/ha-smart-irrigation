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


@pytest.mark.asyncio
async def test_days_until_next_run_follows_a_changed_gap_at_once(hass, fake_valve_services):
    import homeassistant.util.dt as dt_util

    await _seed_source_entities(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    zone = hass.data[DOMAIN][entry.entry_id]
    zone.store.state.last_routine_ts = dt_util.utcnow().timestamp() - 86400
    zone.store.state.last_significant_rain_ts = 0.0
    entity_id = next(s.entity_id for s in hass.states.async_all("sensor") if s.entity_id.endswith("days_until_next_run"))
    for key in ("routine_interval_days", "routine_interval_hot_days"):
        await zone.numbers[key].async_set_metric_value(2.0)
    await hass.async_block_till_done()
    short = float(hass.states.get(entity_id).attributes["routine_days"])
    for key in ("routine_interval_days", "routine_interval_hot_days"):
        await zone.numbers[key].async_set_metric_value(9.0)
    await hass.async_block_till_done()
    assert float(hass.states.get(entity_id).attributes["routine_days"]) - short >= 5.0  # 7 days more, shown without waiting for a poll


GAP_COMBOS = [(1, 1), (4, 3), (3, 4), (6, 2), (2, 6), (10, 1), (1, 10), (10, 10)]
TIERS = {"hot": 35.0, "normal": 25.0, "cool": 10.0}  # a temperature in each tier (hot 31.5, cool 20)


@pytest.mark.parametrize("normal,hot", GAP_COMBOS)
@pytest.mark.parametrize("tier", list(TIERS))
def test_every_gap_combination_picks_the_right_gap_and_dose_in_every_tier(normal, hot, tier):
    temp = TIERS[tier]
    gap = hot if tier == "hot" else normal  # cool weather uses the normal gap
    assert calc.routine_interval_days(temp, 31.5, normal, hot) == gap
    plan = _plan(avg_peak_temp=temp, normal_interval_days=normal, hot_interval_days=hot)
    weekly = {"hot": 45.0, "normal": 35.0, "cool": 25.0}[tier]
    assert plan.interval_target_mm == pytest.approx(weekly * gap / 7, abs=0.1)  # the week's water, in gap-sized doses
    # due exactly one gap after the last watering (less the 6 h buffer), never before
    buffer = 6 * 3600
    assert not calc.routine_due(gap * 86400 - buffer - 60, gap, buffer)
    assert calc.routine_due(gap * 86400 - buffer + 60, gap, buffer)


@pytest.mark.parametrize("normal,hot", GAP_COMBOS)
@pytest.mark.asyncio
async def test_a_zone_follows_every_gap_combination(hass, fake_valve_services, monkeypatch, normal, hot):
    await _seed_source_entities(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    zone = hass.data[DOMAIN][entry.entry_id]
    await zone.numbers["routine_interval_days"].async_set_metric_value(float(normal))
    await zone.numbers["routine_interval_hot_days"].async_set_metric_value(float(hot))
    for temp, expected in ((35.0, hot), (25.0, normal), (10.0, normal)):
        monkeypatch.setattr(zone, "effective_avg_peak_temp", lambda temp=temp: temp)
        assert zone._routine_interval_days() == expected
        assert zone._routine_plan().interval_target_mm > 0


@pytest.mark.parametrize("normal,hot", [(1, 1), (4, 3), (3, 4), (10, 2), (2, 10)])
@pytest.mark.parametrize("temp,name", [(35.0, "hot"), (25.0, "normal")])
@pytest.mark.asyncio
async def test_a_zone_waters_when_its_gap_is_up_and_not_before(hass, fake_valve_services, monkeypatch, tmp_path, normal, hot, temp, name):
    """End to end: the scheduled routine does nothing one hour before the gap
    (less the 6 h buffer) has passed and waters one hour after."""
    import homeassistant.util.dt as dt_util

    from .scenario_harness import CompressedTime
    from .test_smoke_setup import VALVE

    await _seed_source_entities(hass)
    entry = make_entry(hass, csv_path=str(tmp_path / "g.csv"))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    zone = hass.data[DOMAIN][entry.entry_id]
    await zone.numbers["routine_interval_days"].async_set_metric_value(float(normal))
    await zone.numbers["routine_interval_hot_days"].async_set_metric_value(float(hot))
    zone.numbers["max_runtime_minutes"].metric_value = 900
    zone.numbers["max_daily_runtime_minutes"].metric_value = 900
    monkeypatch.setattr(zone, "effective_avg_peak_temp", lambda: temp)
    gap = hot if name == "hot" else normal
    now = dt_util.utcnow().timestamp()
    zone.store.state.last_significant_rain_ts = 0.0
    zone.store.state.last_deep_soak_ts = now - 86400  # a deep soak is not what is due
    clock = CompressedTime(hass, [VALVE]).install(monkeypatch)

    zone.store.state.last_routine_ts = now - (gap * 86400 - 6 * 3600 - 3600)  # one hour short
    await zone.run_routine_irrigation(manual=False)
    await hass.async_block_till_done()
    assert clock.valve_minutes(VALVE) == 0, f"watered a {gap}-day gap too early"

    zone.store.state.last_routine_ts = now - (gap * 86400 - 6 * 3600 + 3600)  # one hour past
    await zone.run_routine_irrigation(manual=False)
    await hass.async_block_till_done()
    assert clock.valve_minutes(VALVE) > 0, f"did not water after a {gap}-day gap"
