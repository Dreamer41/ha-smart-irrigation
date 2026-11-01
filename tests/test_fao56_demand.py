"""1.8: the FAO-56 demand model. The weekly target is the average daily ET0 x Kc over the
completed days since the last real watering, x 7, so a routine watering after a normal
interval gives the sum of those days' water use, less the rain credit as before."""
from __future__ import annotations

from datetime import timedelta

import homeassistant.util.dt as dt_util
import pytest

from custom_components.zoneflow import why
from custom_components.zoneflow.const import DEMAND_MODEL_ET, DEMAND_MODEL_FAO56, DEMAND_MODEL_OPTIONS, DEMAND_MODEL_TIERS, DOMAIN

from .test_smoke_setup import _seed_source_entities, make_entry


async def _zone(hass, model=DEMAND_MODEL_FAO56):
    await _seed_source_entities(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = hass.data[DOMAIN][entry.entry_id]
    c.store.state.demand_model = model
    return c


def _history(values_newest_first):
    today = dt_util.now().date()
    return [{"date": (today - timedelta(days=i + 1)).isoformat(), "et0": v, "sources": {}} for i, v in enumerate(values_newest_first)]


def _watered_days_ago(c, days: float):
    """Watered at noon, `days` calendar days back (the fraction is ignored)."""
    day = dt_util.now().date() - timedelta(days=int(days))
    c.store.state.last_routine_ts = (dt_util.start_of_local_day(day) + timedelta(hours=12)).timestamp()
    c.store.state.rain_window_base_ts = None
    c.store.state.rain_credit_marks = []


def test_fao56_is_a_choice():
    assert DEMAND_MODEL_OPTIONS == [DEMAND_MODEL_TIERS, DEMAND_MODEL_ET, DEMAND_MODEL_FAO56]


@pytest.mark.asyncio
async def test_the_weekly_target_is_the_average_since_the_last_watering_times_kc_times_seven(hass):
    c = await _zone(hass)
    c.store.state.et0_day_history = _history([6.0, 6.0, 6.0, 2.0, 2.0, 2.0, 2.0])
    _watered_days_ago(c, 3.2)  # the watering day and two full days since: 3 completed days
    kc = c.number("crop_coefficient")
    assert c.fao56_daily_demand_mm() == pytest.approx(6.0 * kc)
    assert c.et_weekly_target_mm() == pytest.approx(42.0 * kc)
    plan = c._routine_plan()
    scale = c.routine_target_scale()
    assert plan.target_weekly_mm == pytest.approx(42.0 * kc * scale)
    assert plan.interval_target_mm == pytest.approx(6.0 * kc * scale * plan.interval_days)


@pytest.mark.asyncio
async def test_missing_days_are_left_out_and_an_empty_window_uses_the_last_week(hass):
    c = await _zone(hass)
    kc = c.number("crop_coefficient")
    c.store.state.et0_day_history = _history([None, 4.0, None, 2.0])
    _watered_days_ago(c, 3.5)
    assert c.fao56_daily_demand_mm() == pytest.approx(4.0 * kc)  # only the day that has one
    c.store.state.et0_day_history = _history([None, None, 3.0, 5.0])
    _watered_days_ago(c, 1.5)  # window: yesterday only, which has none
    assert c.fao56_daily_demand_mm() == pytest.approx(4.0 * kc)  # the last seven days instead


@pytest.mark.asyncio
async def test_without_any_fao56_day_the_zone_uses_its_tier_target(hass):
    c = await _zone(hass)
    c.store.state.et0_day_history = []
    assert c.fao56_daily_demand_mm() is None and c.et_weekly_target_mm() is None
    assert c._routine_plan().target_weekly_mm == pytest.approx(c.tier_weekly_target_mm() * c.routine_target_scale())


@pytest.mark.asyncio
async def test_tier_and_et_curve_zones_are_not_changed(hass):
    c = await _zone(hass, model=DEMAND_MODEL_TIERS)
    c.store.state.et0_day_history = _history([6.0] * 7)
    assert c.et_weekly_target_mm() is None
    c.store.state.demand_model = DEMAND_MODEL_ET
    hargreaves = c.et_weekly_target_mm()
    assert hargreaves is None or hargreaves != pytest.approx(42.0 * c.number("crop_coefficient"))


@pytest.mark.asyncio
async def test_a_long_gap_counts_at_most_two_weeks(hass):
    c = await _zone(hass)
    c.store.state.et0_day_history = _history([3.0] * 14)
    _watered_days_ago(c, 40)
    assert c.fao56_daily_demand_mm() == pytest.approx(3.0 * c.number("crop_coefficient"))


@pytest.mark.asyncio
async def test_why_names_the_fao56_method(hass):
    c = await _zone(hass)
    c.store.state.et0_day_history = _history([5.0] * 7)
    items = {i["id"]: i["text"] for i in why.explain(c)}
    assert "FAO-56" in items["method"]
