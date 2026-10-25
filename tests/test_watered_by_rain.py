"""Watered by the rain (1.7.2): once an hour the zone works out what its next
routine watering would give; when the rain since the last watering is more
than that, the zone counts as watered -- its interval starts again, the
Status says so, nothing runs and no litres are counted."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import homeassistant.util.dt as dt_util
import pytest

from custom_components.zoneflow import calculations as calc
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
    c.store.state.rain_credit_marks = [[t - 9 * DAY, m] for t, m in c.store.state.rain_credit_marks]
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
async def test_the_deep_soak_is_counted_by_rain_once_a_day(hass, fake_valve_services):
    c = await _zone(hass, rain_today=5.0)
    c.store.state.last_deep_soak_ts = dt_util.utcnow().timestamp() - 3 * DAY
    target = c.number("deep_soak_target_mm")
    _rain_after(c, target + 5)
    await c._on_rain_credit_check()
    first = c.store.state.last_deep_soak_ts

    # An hour later another deep soak's worth of rain has fallen, the same day: no second count.
    start = dt_util.utcnow().timestamp() - 60
    c.rain_since = lambda since_ts: target + 10 if since_ts < start else 0.0
    await c._on_rain_credit_check()
    assert c.store.state.last_deep_soak_ts == first

    # Next day the same rain counts again.
    c.store.state.last_deep_soak_ts = dt_util.utcnow().timestamp() - 1.2 * DAY
    c.rain_since = lambda since_ts: target + 10
    await c._on_rain_credit_check()
    assert c.store.state.last_deep_soak_ts > dt_util.utcnow().timestamp() - 60


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


def _rain_events(c, events):
    """rain_since from (hours ago, mm) events: the rain that fell after `since`."""
    now = dt_util.utcnow().timestamp()
    c.rain_since = lambda since_ts: sum(mm for hours, mm in events if now - hours * 3600 > since_ts)


@pytest.mark.asyncio
async def test_rain_over_the_target_plus_5_mm_in_72_hours_counts_too(hass, fake_valve_services):
    c = await _zone(hass, rain_today=5.0)
    c.store.state.last_deep_soak_ts = dt_util.utcnow().timestamp() - 5 * DAY
    target = c.number("deep_soak_target_mm")
    # Spread over three days: not enough in any one 24 h, but target + 5 mm over 72 h.
    _rain_events(c, [(2, target * 0.4), (30, target * 0.4), (60, target * 0.4 + 6)])
    before = c.store.state.last_deep_soak_ts

    await c._on_rain_credit_check()

    assert c.store.state.last_deep_soak_ts > before
    assert c.status()["code"] == "watered_by_rain" and c.status()["cycle"] == "deep_soak"


@pytest.mark.asyncio
async def test_the_target_alone_is_not_enough_over_72_hours(hass, fake_valve_services):
    c = await _zone(hass, rain_today=5.0)
    c.store.state.last_deep_soak_ts = dt_util.utcnow().timestamp() - 5 * DAY
    target = c.number("deep_soak_target_mm")
    _rain_events(c, [(2, target * 0.3), (30, target * 0.3), (60, target * 0.4 + 4)])  # the target + 4 mm: not yet
    before = c.store.state.last_deep_soak_ts

    await c._on_rain_credit_check()

    assert c.store.state.last_deep_soak_ts == before


@pytest.mark.asyncio
async def test_rain_before_the_last_deep_soak_is_not_counted_again(hass, fake_valve_services):
    c = await _zone(hass, rain_today=5.0)
    c.store.state.last_deep_soak_ts = dt_util.utcnow().timestamp() - 20 * 3600  # soaked 20 h ago
    target = c.number("deep_soak_target_mm")
    _rain_events(c, [(30, target + 20), (60, target + 20)])  # all of it before that deep soak
    before = c.store.state.last_deep_soak_ts

    await c._on_rain_credit_check()

    assert c.store.state.last_deep_soak_ts == before


@pytest.mark.asyncio
async def test_the_hourly_check_refreshes_weather_underground_rain_first(hass, fake_valve_services):
    c = await _zone(hass, rain_today=0.0)
    c._refresh_wu_rain = AsyncMock()
    await c._on_rain_credit_check()
    c._refresh_wu_rain.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_cycle_checking_its_gates_is_left_alone(hass, fake_valve_services):
    c = await _zone(hass, rain_today=60.0)
    before = c.store.state.last_routine_ts
    c._runs.add("routine") if hasattr(c._runs, "add") else c._runs.append("routine")

    await c._on_rain_credit_check()

    assert c.store.state.last_routine_ts == before


@pytest.mark.asyncio
async def test_a_failing_estimate_never_breaks_the_status(hass, fake_valve_services, monkeypatch):
    c = await _zone(hass)
    monkeypatch.setattr(type(c), "_routine_plan", lambda self: (_ for _ in ()).throw(ValueError("odd data")))
    assert c.next_amount_mm("routine") is None
    assert c.status()["code"] in ("next", "first_run", "next_deep_soak", "done", "idle")


@pytest.mark.asyncio
async def test_rain_after_the_mark_is_not_taken_off_by_the_old_offset(hass, fake_valve_services):
    """A zone marked watered by heavy rain four days ago: the rain that fell
    since is new, and the credit for the old rain must not wipe it."""
    c = await _zone(hass, rain_today=0.0)
    now_ts = dt_util.utcnow().timestamp()
    mark = now_ts - 4.4 * DAY
    c.store.state.last_routine_ts = mark
    c.store.state.rain_credit_spent_ts = mark
    c.store.state.rain_credit_spent_mm = 14.29
    # yesterday 12 mm, the day before 12 mm, then two dry days (the mark day and before)
    c.store.state.rain_day_history_mm = [12.0, 12.0, 0.0, 0.0] + [30.0] * 6
    plan = c._routine_plan()
    assert plan.eff_rain_mm > 10.0  # both new days count in full


@pytest.mark.asyncio
async def test_rain_of_the_mark_day_is_still_taken_off(hass, fake_valve_services):
    c = await _zone(hass, rain_today=0.0)
    local_today = dt_util.now().replace(hour=12, minute=0, second=0, microsecond=0)
    marked = (local_today - timedelta(days=1)).timestamp()  # noon yesterday, when that 60 mm had fallen
    c.store.state.rain_day_history_mm = [60.0] + [0.0] * 9
    c.store.state.last_routine_ts = marked
    c.store.state.rain_credit_spent_ts = marked
    c.store.state.rain_credit_spent_mm = 14.29  # one dose of it is used already
    gross = 60.0 * c.number("rain_eff_high")
    plan = c._routine_plan(elapsed_seconds=36 * 3600.0)  # a day and a half after the mark
    assert plan.eff_rain_mm == pytest.approx(gross - 14.29, abs=0.05)


@pytest.mark.asyncio
async def test_the_ignore_level_is_a_setting_that_starts_at_three_mm(hass, fake_valve_services):
    c = await _zone(hass, rain_today=0.0)
    assert c.number("rain_ignore_below_mm") == 3.0
    c.store.state.last_routine_ts = dt_util.utcnow().timestamp() - 4.5 * DAY
    c.store.state.rain_day_history_mm = [2.0, 2.0, 2.0, 2.0] + [0.0] * 6
    assert c._routine_plan().eff_rain_mm == 0.0  # drizzle counts as nothing, as it always did
    await c.numbers["rain_ignore_below_mm"].async_set_native_value(0.0)
    assert c._routine_plan().eff_rain_mm > 0.0



@pytest.mark.asyncio
async def test_a_rain_decision_does_not_hide_the_dry_down(hass, fake_valve_services):
    """Counted by rain while the dry-down holds: the sentence says both, and the decision stays first."""
    c = await _zone(hass, rain_today=5.0)
    now = dt_util.utcnow().timestamp()
    c.store.state.last_deep_soak_ts = now - 3 * DAY
    c.store.state.last_significant_rain_ts = now - 3600
    _rain_after(c, c.number("deep_soak_target_mm") + 5)
    await c._on_rain_credit_check()

    status = c.status()
    assert status["code"] == "watered_by_rain" and status["decided_at"] is not None
    assert status["text"].startswith("Deep soak counted as done")
    assert " · Drying out after rain until " in status["text"] and " · next " in status["text"]
    assert status["text"].index("Drying out") < status["text"].index(" · next ")


# --- the rain credit rolls (1.7.7) ---------------------------------------------


def _age(c, seconds):
    """Everything a rain mark wrote happened `seconds` earlier."""
    state = c.store.state
    state.rain_credit_marks = [[t - seconds, m] for t, m in state.rain_credit_marks]
    state.rain_credit_spent_ts -= seconds
    state.last_routine_ts -= seconds


@pytest.mark.asyncio
async def test_a_rain_mark_keeps_the_days_of_rain_before_it_in_the_credit(hass, fake_valve_services):
    """Oct 22: 21 mm, Oct 23: 45 mm. The mark takes one dose off; the credit still counts both days."""
    c = await _zone(hass, rain_today=45.0)
    real_watering = dt_util.utcnow().timestamp() - 3.5 * DAY
    c.store.state.last_routine_ts = real_watering
    c.store.state.rain_day_history_mm = [21.3] + [0.0] * 9
    dose = c._routine_plan().interval_target_mm
    high = c.number("rain_eff_high")

    await c._on_rain_credit_check()

    assert c.store.state.rain_window_base_ts == real_watering  # the window still starts at the real watering
    assert c.store.state.last_routine_ts > real_watering  # the interval starts again all the same
    plan = c._routine_plan()
    assert plan.eff_rain_mm == pytest.approx(45.0 * high + 21.3 * high - dose, abs=0.1)  # both days, less one dose
    assert plan.needed_mm == 0.0  # the next routine has nothing to add


@pytest.mark.asyncio
async def test_a_mark_written_before_1_7_7_is_adopted_into_the_rolling_credit(hass, fake_valve_services):
    """A mark with no window start (saved by 1.7.6) rolls too: the rain before it counts again at once,
    less the one dose it took."""
    c = await _zone(hass, rain_today=0.0)
    now_ts = dt_util.utcnow().timestamp()
    c.store.state.last_routine_ts = now_ts - 3600
    c.store.state.rain_credit_spent_ts = now_ts - 3600
    c.store.state.rain_credit_spent_mm = 12.57
    c.store.state.rain_day_history_mm = [21.3] + [0.0] * 9
    assert c._chain_marks() == [(now_ts - 3600, 12.57)]
    eff = calc.rain_efficiency(
        21.3, c.number("rain_eff_low"), c.number("rain_eff_mid"), c.number("rain_eff_high"), c.number("rain_ignore_below_mm")
    )
    assert c._routine_plan().eff_rain_mm == pytest.approx(21.3 * eff - 12.57, abs=0.1)  # yesterday counts again


@pytest.mark.asyncio
async def test_a_second_mark_in_the_same_spell_takes_a_second_dose(hass, fake_valve_services):
    c = await _zone(hass, rain_today=70.0)
    c.store.state.last_routine_ts = dt_util.utcnow().timestamp() - 3.5 * DAY
    dose = c._routine_plan().interval_target_mm
    await c._on_rain_credit_check()
    base = c.store.state.rain_window_base_ts
    _age(c, 4 * DAY + 1)  # a whole interval later, still raining
    c.store.state.rain_window_base_ts = base - (4 * DAY + 1)  # (the real watering moves back with it)
    c.today_rain_mm = lambda: 40.0
    c.store.state.rain_day_history_mm = [70.0] + [0.0] * 9
    await c._on_rain_credit_check()

    assert len(c.store.state.rain_credit_marks) == 2
    assert c.rain_offset_mm() == pytest.approx(2 * dose, abs=0.05)


@pytest.mark.asyncio
async def test_a_dose_leaves_with_the_day_it_was_taken_on(hass, fake_valve_services):
    """Five days on, the rain of the mark day is out of the window and so is the dose taken for it."""
    c = await _zone(hass, rain_today=60.0)
    c.store.state.last_routine_ts = dt_util.utcnow().timestamp() - 3.5 * DAY
    await c._on_rain_credit_check()
    assert c.rain_offset_mm() > 0
    _age(c, 5.2 * DAY)
    c.store.state.rain_window_base_ts -= 5.2 * DAY
    c.today_rain_mm = lambda: 6.0
    c.store.state.rain_day_history_mm = [0.0, 0.0, 0.0, 0.0, 60.0] + [0.0] * 5
    assert c.rain_offset_mm() == 0.0
    eff = calc.rain_efficiency(
        6.0, c.number("rain_eff_low"), c.number("rain_eff_mid"), c.number("rain_eff_high"), c.number("rain_ignore_below_mm")
    )
    assert c._routine_plan().eff_rain_mm == pytest.approx(6.0 * eff, abs=0.05)  # only today's rain: the 60 mm is out


@pytest.mark.asyncio
async def test_a_real_watering_after_a_mark_starts_the_credit_again(hass, fake_valve_services):
    c = await _zone(hass, rain_today=60.0)
    c.store.state.last_routine_ts = dt_util.utcnow().timestamp() - 3.5 * DAY
    c.store.state.rain_day_history_mm = [30.0] + [0.0] * 9
    await c._on_rain_credit_check()
    assert c._chain_marks()
    c.store.state.last_routine_ts += 3600  # the valve ran after the mark
    assert c._chain_marks() == [] and c.rain_offset_mm() == 0.0
    assert c._rain_pool_elapsed() == pytest.approx(
        dt_util.utcnow().timestamp() - c.store.state.last_routine_ts, abs=5
    )  # the window starts at that watering again


@pytest.mark.asyncio
async def test_a_dose_does_not_eat_new_rain_once_the_rain_that_paid_for_it_has_left(hass, fake_valve_services):
    """The mark was paid for by a big day that has since left the window: the rain of the days
    after the mark is credited in full, not reduced by that dose."""
    c = await _zone(hass, rain_today=6.0)
    now_ts = dt_util.utcnow().timestamp()
    mark = now_ts - 3 * DAY
    c.store.state.last_routine_ts = mark
    c.store.state.rain_window_base_ts = now_ts - 8 * DAY
    c.store.state.rain_credit_marks = [[mark, 17.0]]
    c.store.state.rain_credit_spent_mm = 17.0
    c.store.state.rain_credit_spent_ts = mark
    # the big day (60 mm) was 5 days ago: out of the 4-day window; the mark day and after were dry
    c.store.state.rain_day_history_mm = [0.0, 0.0, 0.0, 0.0, 60.0] + [0.0] * 5
    eff = calc.rain_efficiency(
        6.0, c.number("rain_eff_low"), c.number("rain_eff_mid"), c.number("rain_eff_high"), c.number("rain_ignore_below_mm")
    )
    assert c.rain_offset_mm() == 0.0
    assert c._routine_plan().eff_rain_mm == pytest.approx(6.0 * eff, abs=0.05)


@pytest.mark.asyncio
async def test_a_last_routine_time_set_back_before_the_mark_ends_the_chain(hass, fake_valve_services):
    c = await _zone(hass, rain_today=60.0)
    c.store.state.last_routine_ts = dt_util.utcnow().timestamp() - 3.5 * DAY
    c.store.state.rain_day_history_mm = [30.0] + [0.0] * 9
    await c._on_rain_credit_check()
    assert c._chain_marks()
    c.store.state.last_routine_ts = dt_util.utcnow().timestamp() - 10 * DAY  # edited back in time
    assert c._chain_marks() == []


@pytest.mark.asyncio
async def test_a_second_rain_mark_waits_a_full_interval_even_with_no_credit_left(hass, fake_valve_services):
    c = await _zone(hass, rain_today=60.0)
    await c._on_rain_credit_check()
    first = c.store.state.last_routine_ts
    c.store.state.rain_day_history_mm = [0.0] * 10
    c.number = lambda key, _n=c.number: 0.0 if key.startswith("rain_eff_") else _n(key)
    await c._on_rain_credit_check()
    assert c.store.state.last_routine_ts == first


@pytest.mark.asyncio
async def test_a_paused_zone_advertises_no_next_dates(hass, fake_valve_services):
    c = await _zone(hass)
    await c.set_paused(True)
    status = c.status()
    assert status["code"] == "paused"
    assert status["next_routine"] is None and status["next_deep_soak"] is None


@pytest.mark.asyncio
async def test_the_routine_after_a_deep_soak_is_dated_a_full_interval_later(hass, fake_valve_services):
    c = await _zone(hass)
    now_ts = dt_util.utcnow().timestamp()
    c.store.state.last_routine_ts = now_ts - 2 * DAY
    c.store.state.last_deep_soak_ts = now_ts - 14 * DAY
    c._scheduled_next = lambda not_before: (now_ts + 3600 * 1.5, now_ts + 3600)  # deep soak first, routine just after
    status = c.status()
    assert status["next_cycle"] == "deep_soak"
    deep = dt_util.parse_datetime(status["next_deep_soak"])
    routine = dt_util.parse_datetime(status["next_routine"])
    assert routine - deep >= timedelta(days=c._routine_interval_days()) - timedelta(hours=7)


@pytest.mark.asyncio
async def test_the_rolling_credit_in_imperial_units(hass, fake_valve_services):
    from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

    hass.config.units = US_CUSTOMARY_SYSTEM
    c = await _zone(hass, rain_today=60.0)
    c.store.state.last_routine_ts = dt_util.utcnow().timestamp() - 3.5 * DAY
    c.store.state.rain_day_history_mm = [30.0] + [0.0] * 9
    await c._on_rain_credit_check()
    assert c._chain_marks()
    from custom_components.zoneflow import why

    plan = c._routine_plan()
    gross, used, used_ts = c.rain_credit_breakdown(plan)
    assert used_ts is not None and used > 0 and gross >= used  # mm inside; shown with units.depth_text
    assert " in" in c.status()["text"] or "mm" not in c.status()["text"]


@pytest.mark.asyncio
async def test_a_mark_across_the_clock_change_still_ages_by_local_days(hass, fake_valve_services):
    """Autumn clock change (EU, 25 Oct 2026): a mark made the evening before is one local day old
    the next morning, 24 or 25 hours later."""
    from freezegun import freeze_time

    if hasattr(hass.config, "async_set_time_zone"):  # newer Home Assistant forbids the sync call
        await hass.config.async_set_time_zone("Europe/Helsinki")
    else:
        hass.config.set_time_zone("Europe/Helsinki")
    c = await _zone(hass)
    with freeze_time("2026-10-24 19:30:00+00:00"):  # 22:30 local on the 24th (summer time)
        mark = dt_util.utcnow().timestamp()
    with freeze_time("2026-10-25 03:30:00+00:00"):  # 05:30 local on the 25th, after the clock went back
        c.store.state.last_routine_ts = mark
        c.store.state.rain_window_base_ts = mark - 2 * DAY
        c.store.state.rain_credit_marks = [[mark, 10.0]]
        assert dt_util.now().date().isoformat() == "2026-10-25"
        assert c._chain_offset(2 * DAY + 3600) <= 10.0  # counted, never negative or doubled
        assert c._chain_offset(2 * DAY + 3600) >= 0.0


@pytest.mark.asyncio
async def test_a_mark_dated_in_the_future_never_breaks_the_plan(hass, fake_valve_services):
    """The clock was stepped back after a mark was written: the chain is dropped, nothing raises."""
    c = await _zone(hass, rain_today=6.0)
    future = dt_util.utcnow().timestamp() + 12 * DAY
    c.store.state.last_routine_ts = future
    c.store.state.rain_window_base_ts = future - 3 * DAY
    c.store.state.rain_credit_marks = [[future, 17.0]]
    assert c._chain_marks() == []
    c._routine_plan()
    c.rain_offset_mm()
