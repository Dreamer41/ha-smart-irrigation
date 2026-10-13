"""Watered by the rain (1.7.2): once an hour the zone works out what its next
routine watering would give; when the rain since the last watering is more
than that, the zone counts as watered -- its interval starts again, the
Status says so, nothing runs and no litres are counted."""
from __future__ import annotations

from unittest.mock import AsyncMock

import homeassistant.util.dt as dt_util
import pytest

from custom_components.zoneflow.const import DOMAIN

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

DAY = 86400.0


async def _zone(hass, rain_today=0.0, **overrides):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "28.0")
    await hass.async_block_till_done()
    entry = make_entry(hass, **overrides)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = hass.data[DOMAIN][entry.entry_id]
    c._run_pulses = AsyncMock(return_value=True)
    c.today_rain_mm = lambda: rain_today
    c.store.state.last_routine_ts = dt_util.utcnow().timestamp() - 1 * DAY
    c.store.state.rain_day_history_mm = [0.0] * 10
    return c


@pytest.mark.asyncio
async def test_rain_more_than_the_next_dose_counts_as_the_watering(hass, fake_valve_services):
    c = await _zone(hass, rain_today=60.0)
    before = c.store.state.last_routine_ts
    liters_before = dict(c.store.state.water_ledger)
    dose = c._routine_plan().interval_target_mm

    await c._on_rain_credit_check()

    assert c.store.state.last_routine_ts > before  # watered now: the interval starts again
    c._run_pulses.assert_not_called()  # nothing ran
    assert c.store.state.water_ledger == liters_before  # and no litres counted
    status = c.status()
    assert status["code"] == "watered_by_rain" and "counted as done" in status["text"]
    assert c.store.state.rain_credit_spent_mm == pytest.approx(dose, abs=0.01)


@pytest.mark.asyncio
async def test_less_rain_than_the_dose_changes_nothing(hass, fake_valve_services):
    c = await _zone(hass, rain_today=2.0)
    before = c.store.state.last_routine_ts

    await c._on_rain_credit_check()

    assert c.store.state.last_routine_ts == before
    assert c.status()["code"] != "watered_by_rain"


@pytest.mark.asyncio
async def test_the_same_rain_is_not_counted_twice(hass, fake_valve_services):
    c = await _zone(hass, rain_today=60.0)
    await c._on_rain_credit_check()
    first = c.store.state.last_routine_ts

    await c._on_rain_credit_check()  # an hour later, the same rain, even though it would cover more than one dose

    assert c.store.state.last_routine_ts == first


@pytest.mark.asyncio
async def test_what_the_rain_gave_beyond_the_dose_is_credited_to_the_next_watering(hass, fake_valve_services):
    c = await _zone(hass, rain_today=60.0)
    gross = c._routine_plan().eff_rain_mm
    dose = c._routine_plan().interval_target_mm
    await c._on_rain_credit_check()
    # Tomorrow: yesterday's rain is history; the routine counts it less the dose already used.
    c.today_rain_mm = lambda: 0.0
    c.store.state.rain_day_history_mm = [60.0] + [0.0] * 9
    c.store.state.last_routine_ts -= DAY
    c.store.state.rain_credit_spent_ts -= DAY
    left = c._routine_plan().eff_rain_mm
    assert left == pytest.approx(max(gross - dose, 0.0), abs=0.05)


@pytest.mark.asyncio
async def test_a_later_watering_ends_the_offset(hass, fake_valve_services):
    c = await _zone(hass, rain_today=60.0)
    await c._on_rain_credit_check()
    assert c.rain_offset_mm() > 0
    c.store.state.last_routine_ts += 3600  # a watering after the mark
    assert c.rain_offset_mm() == 0.0


@pytest.mark.asyncio
async def test_the_offset_ends_when_the_window_has_passed(hass, fake_valve_services):
    c = await _zone(hass, rain_today=60.0)
    await c._on_rain_credit_check()
    c.store.state.rain_credit_spent_ts -= 9 * DAY
    c.store.state.last_routine_ts = c.store.state.rain_credit_spent_ts
    assert c.rain_offset_mm() == 0.0


@pytest.mark.asyncio
async def test_a_paused_zone_is_left_alone(hass, fake_valve_services):
    c = await _zone(hass, rain_today=60.0)
    before = c.store.state.last_routine_ts
    await c.set_paused(True)

    await c._on_rain_credit_check()

    assert c.store.state.last_routine_ts == before


@pytest.mark.asyncio
async def test_no_rain_on_record_means_no_mark(hass, fake_valve_services):
    c = await _zone(hass, rain_today=0.0)
    before = c.store.state.last_routine_ts

    await c._on_rain_credit_check()

    assert c.store.state.last_routine_ts == before


@pytest.mark.asyncio
async def test_a_zone_that_is_watering_is_left_alone(hass, fake_valve_services):
    c = await _zone(hass, rain_today=60.0)
    before = c.store.state.last_routine_ts
    c.store.state.lock_on = True

    await c._on_rain_credit_check()

    assert c.store.state.last_routine_ts == before


@pytest.mark.asyncio
async def test_a_watered_by_rain_day_is_not_a_held_back_day(hass, fake_valve_services):
    c = await _zone(hass, rain_today=60.0)
    c.store.state.summary_skip_days = [dt_util.now().date().isoformat()]
    await c._on_rain_credit_check()
    assert dt_util.now().date().isoformat() not in c.store.state.summary_skip_days


# --- deep soak ---------------------------------------------------------------


def _rain_after(c, mm):
    """rain_since: `mm` fell in the last 24 hours, nothing before them is counted twice."""
    start = dt_util.utcnow().timestamp() - 3600

    def rain_since(since_ts):
        return mm if since_ts < start else 0.0

    c.rain_since = rain_since


@pytest.mark.asyncio
async def test_rain_over_the_deep_soak_target_counts_as_the_deep_soak(hass, fake_valve_services):
    c = await _zone(hass, rain_today=5.0)
    c.store.state.last_deep_soak_ts = dt_util.utcnow().timestamp() - 3 * DAY
    _rain_after(c, c.number("deep_soak_target_mm") + 5)
    before = c.store.state.last_deep_soak_ts

    await c._on_rain_credit_check()

    assert c.store.state.last_deep_soak_ts > before  # the deep soak interval starts again
    assert c.store.state.last_routine_ts >= c.store.state.last_deep_soak_ts  # and it is the routine watering too
    c._run_pulses.assert_not_called()
    assert c.status()["code"] == "watered_by_rain" and c.status()["cycle"] == "deep_soak"
    first = c.store.state.last_deep_soak_ts

    await c._on_rain_credit_check()  # an hour later: the same rain is not counted again
    assert c.store.state.last_deep_soak_ts == first


@pytest.mark.asyncio
async def test_rain_under_the_deep_soak_target_does_not(hass, fake_valve_services):
    c = await _zone(hass, rain_today=5.0)
    before = c.store.state.last_deep_soak_ts
    _rain_after(c, c.number("deep_soak_target_mm") - 5)

    await c._on_rain_credit_check()

    assert c.store.state.last_deep_soak_ts == before


@pytest.mark.asyncio
async def test_a_zone_with_deep_soak_off_is_not_marked(hass, fake_valve_services):
    from custom_components.zoneflow.const import CONF_DEEP_SOAK_ENABLED

    c = await _zone(hass, rain_today=5.0, **{CONF_DEEP_SOAK_ENABLED: False})
    _rain_after(c, 500.0)
    await c._on_rain_credit_check()
    assert c.store.state.last_deep_soak_ts is None


@pytest.mark.asyncio
async def test_the_mark_deep_soak_done_button_counts_as_a_deep_soak(hass, fake_valve_services):
    c = await _zone(hass)
    c.store.state.last_deep_soak_ts = dt_util.utcnow().timestamp() - 10 * DAY
    before = c.store.state.last_deep_soak_ts

    await c.mark_deep_soak_done()

    assert c.store.state.last_deep_soak_ts > before
    assert c.store.state.last_routine_ts >= c.store.state.last_deep_soak_ts
    c._run_pulses.assert_not_called()


@pytest.mark.asyncio
async def test_the_button_is_shown_only_where_no_rain_is_measured(hass, fake_valve_services):
    from custom_components.zoneflow import visibility
    from custom_components.zoneflow.const import CONF_RAIN_COUNTER_ENTITY

    key = ("button", "mark_deep_soak_done")
    with_gauge = await _zone(hass)
    assert key in visibility.hidden_for(with_gauge)  # rain is measured: it marks itself
    without = await _zone(hass, **{CONF_RAIN_COUNTER_ENTITY: None, "csv_path": "/tmp/test_no_gauge.csv", "valve_entity": "switch.other_valve"})
    assert key not in visibility.hidden_for(without)  # no rain measured: the person marks it
