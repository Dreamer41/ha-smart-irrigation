"""Intent-level scenarios for single routine / deep-soak cycles.

Each test runs a real cycle through the controller (with CompressedTime, so
pulses and soak gaps take simulated rather than real minutes) and checks
what the valve ACTUALLY did -- total open minutes, pulse split, soak gaps,
and therefore mm delivered -- against the water the model is meant to
apply. Expected values are worked out by hand in each test from the
model's own rules (weekly target x interval / 7, minus credited rain,
divided by flow rate), not by calling calculations.py, so a drift in the
real math shows up as a failure here.
"""
from __future__ import annotations

import pytest
import homeassistant.util.dt as dt_util

from custom_components.zoneflow.const import DEMAND_MODEL_ET, DOMAIN, EVENT_LOG

from .scenario_harness import CompressedTime
from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

DAY = 86400.0


async def _zone(hass, monkeypatch, tmp_path, temp="28.0", **entry_overrides):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, temp)
    await hass.async_block_till_done()
    entry_overrides.setdefault("csv_path", str(tmp_path / "zone.csv"))
    entry = make_entry(hass, **entry_overrides)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    clock = CompressedTime(hass, [VALVE]).install(monkeypatch)
    events: list[str] = []
    hass.bus.async_listen(EVENT_LOG, lambda e: events.append(e.data["event_type"]))
    return controller, clock, events


def _history(controller, *, last_routine_days_ago=None, last_deep_days_ago=None, peaks=(28.0, 28.0, 28.0)):
    now = dt_util.utcnow().timestamp()
    s = controller.store.state
    s.last_routine_ts = None if last_routine_days_ago is None else now - last_routine_days_ago * DAY
    s.last_deep_soak_ts = None if last_deep_days_ago is None else now - last_deep_days_ago * DAY
    s.last_significant_rain_ts = None
    s.peak_temp_day_history_c = list(peaks)
    s.today_runtime_minutes = 0.0


async def _set(controller, **numbers):
    for key, value in numbers.items():
        await controller.numbers[key].async_set_native_value(value)


def _delivered_mm(clock, controller):
    return clock.valve_minutes(VALVE) * controller.number("flow_rate_mm_per_min")


def _tolerance_mm(controller, pulses):
    # Runtime is rounded to whole minutes, then split into whole-minute
    # pulses: at most half a minute per pulse plus half a minute overall.
    return (pulses * 0.5 + 0.5) * controller.number("flow_rate_mm_per_min")


# ---------------------------------------------------------------------------
# Routine cycle: how much water goes on
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "peaks,expected_interval,weekly_key",
    [
        ((28.0, 28.0, 28.0), 4, "target_weekly_cool_mm"),   # 28 < cool threshold 30 -> cool tier
        ((30.5, 31.0, 30.5), 4, "target_weekly_mm"),        # between thresholds -> normal tier
        ((33.0, 34.0, 32.0), 3, "target_weekly_hot_mm"),    # >= 31.5 -> hot tier, 3-day interval
    ],
)
async def test_routine_delivers_the_tier_share_of_the_weekly_target(
    hass, fake_valve_services, monkeypatch, tmp_path, peaks, expected_interval, weekly_key
):
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=expected_interval, peaks=peaks)

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    expected_mm = controller.number(weekly_key) / 7 * expected_interval
    assert _delivered_mm(clock, controller) == pytest.approx(expected_mm, abs=_tolerance_mm(controller, 3))
    # Split into 3 equal pulses, valve open during each, 20-minute soak gaps between.
    pulses = clock.pulses_for(VALVE)
    assert len(pulses) == 3 and len(set(pulses)) == 1
    assert all(p.valve_state_during == "on" for p in clock.pulses)
    assert [s for s in clock.sleeps_seconds if s > 0] == [20 * 60, 20 * 60]
    # Bookkeeping afterwards: valve closed, lock released, run recorded.
    assert hass.states.get(VALVE).state == "off"
    assert controller.store.state.lock_on is False
    assert controller.store.state.last_routine_ts == pytest.approx(dt_util.utcnow().timestamp(), abs=5)
    assert events[-1] == "Routine Irrigation Completed"


@pytest.mark.asyncio
async def test_routine_does_not_run_a_day_early_for_the_hot_interval_when_it_is_normal(
    hass, fake_valve_services, monkeypatch, tmp_path
):
    """Normal weather: 3 days after the last run must still be a no-op
    (the 3-day interval is only for the hot tier)."""
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=3, peaks=(30.5, 30.5, 30.5))

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    assert clock.pulses == []
    assert events == []


@pytest.mark.asyncio
async def test_partial_rain_credit_reduces_water_by_the_credited_amount(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    # 8 mm yesterday: efficiency 0.2 + (8-5)/5 x (0.6-0.2) = 0.44 -> 3.52 mm credited.
    controller.store.state.rain_day_history_mm = [8.0] + [0.0] * 9

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    expected = 35.0 / 7 * 4 - 8.0 * 0.44
    assert _delivered_mm(clock, controller) == pytest.approx(expected, abs=_tolerance_mm(controller, 3))


@pytest.mark.asyncio
async def test_light_showers_under_3mm_earn_no_credit(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    controller.store.state.rain_day_history_mm = [2.9, 2.5, 3.0, 1.0] + [0.0] * 6

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    assert _delivered_mm(clock, controller) == pytest.approx(20.0, abs=_tolerance_mm(controller, 3))


@pytest.mark.asyncio
async def test_rain_older_than_the_interval_is_not_credited(hass, fake_valve_services, monkeypatch, tmp_path):
    """A storm 6 days ago was already handled by the drydown holdoff; it must
    not also shrink this 4-day cycle."""
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=6, peaks=(30.5, 30.5, 30.5))
    controller.store.state.rain_day_history_mm = [0.0] * 5 + [30.0] + [0.0] * 4

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    assert _delivered_mm(clock, controller) == pytest.approx(20.0, abs=_tolerance_mm(controller, 3))


@pytest.mark.asyncio
async def test_enough_rain_credit_means_no_water_and_no_recorded_run(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    controller.store.state.rain_day_history_mm = [25.0] + [0.0] * 9  # 25 mm x 1.0 > 20 mm target
    before = controller.store.state.last_routine_ts

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    assert clock.pulses == []
    assert events == ["Rain Credit Sufficient"]
    assert controller.store.state.last_routine_ts == before
    assert controller.store.state.lock_on is False


@pytest.mark.asyncio
async def test_growth_ramp_scales_the_delivered_water(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    monkeypatch.setattr(controller, "growth_ramp_fraction", lambda: 0.5)

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    assert _delivered_mm(clock, controller) == pytest.approx(10.0, abs=_tolerance_mm(controller, 3))


@pytest.mark.asyncio
async def test_et_curve_delivers_et0_x_kc_share(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    await hass.config.async_update(latitude=9.5)
    _history(controller, last_routine_days_ago=4, peaks=(31.0, 31.0, 31.0))
    controller.store.state.min_temp_day_history_c = [24.0, 24.0, 24.0]
    controller.store.state.demand_model = DEMAND_MODEL_ET
    await _set(controller, crop_coefficient=0.8)

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    et0 = controller.avg_et0()
    assert 3.5 < et0 < 5.5  # sanity: typical tropical day
    expected = et0 * 7 * 0.8 / 7 * 4  # 4-day interval (31 < 31.5 hot threshold)
    assert _delivered_mm(clock, controller) == pytest.approx(expected, abs=_tolerance_mm(controller, 3))


@pytest.mark.asyncio
async def test_doubling_the_flow_rate_halves_runtime_but_not_the_water(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    await _set(controller, flow_rate_mm_per_min=0.48)

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    assert clock.valve_minutes(VALVE) == pytest.approx(20.0 / 0.48, abs=2)
    assert _delivered_mm(clock, controller) == pytest.approx(20.0, abs=_tolerance_mm(controller, 3))


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 2, 5, 8])
async def test_pulse_count_splits_the_same_water_evenly(hass, fake_valve_services, monkeypatch, tmp_path, count):
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    await _set(controller, routine_pulse_count=count, routine_pulse_rest_minutes=10)

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    pulses = clock.pulses_for(VALVE)
    assert len(pulses) == count and len(set(pulses)) == 1
    assert [s for s in clock.sleeps_seconds if s > 0] == [600] * (count - 1)
    assert _delivered_mm(clock, controller) == pytest.approx(20.0, abs=_tolerance_mm(controller, count))


@pytest.mark.asyncio
async def test_a_small_need_uses_fewer_pulses_and_delivers_exactly_the_logged_minutes(hass, fake_valve_services, monkeypatch, tmp_path):
    """Regression: a tiny need used to run every pulse at its 1-minute
    minimum (up to 3x the water asked for), and pulses were rounded to whole
    minutes each, so the valve could be open longer than the log said."""
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    # 19.5 mm of credit against a 20 mm target -> 0.5 mm -> 2 minutes needed.
    controller.store.state.rain_day_history_mm = [19.5] + [0.0] * 9
    await _set(controller, rain_eff_mid=1.0, rain_eff_high=1.0)
    runtimes = []
    real_log = controller._log_event

    async def capture(**kw):
        runtimes.append(kw["runtime"])
        await real_log(**kw)

    monkeypatch.setattr(controller, "_log_event", capture)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    assert clock.pulses_for(VALVE) == [1.0, 1.0]  # 2 one-minute pulses, not 3
    assert clock.valve_minutes(VALVE) == runtimes[-1] == 2


@pytest.mark.asyncio
async def test_open_valve_minutes_always_equal_the_logged_runtime(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    runtimes = []
    real_log = controller._log_event

    async def capture(**kw):
        runtimes.append((kw["event_type"], kw["runtime"]))
        await real_log(**kw)

    monkeypatch.setattr(controller, "_log_event", capture)
    for count in (1, 2, 3, 4, 7):
        clock.reset()
        _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
        await _set(controller, routine_pulse_count=count)
        await controller.run_routine_irrigation()
        await hass.async_block_till_done()
        assert runtimes[-1][0] == "Routine Irrigation Completed"
        assert clock.valve_minutes(VALVE) == pytest.approx(runtimes[-1][1])


# ---------------------------------------------------------------------------
# Routine cycle: things that must stop it, and must not leave damage behind
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runtime_cap_blocks_without_opening_the_valve(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    await _set(controller, max_runtime_minutes=30)  # needs ~83 min

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    assert clock.pulses == [] and events == ["Runtime Cap Exceeded"]
    assert controller.store.state.lock_on is False
    assert hass.states.get(VALVE).state == "off"


@pytest.mark.asyncio
async def test_daily_cap_counts_the_deep_soak_that_already_ran_today(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, last_deep_days_ago=14, peaks=(30.5, 30.5, 30.5))
    await _set(controller, max_daily_runtime_minutes=150, deep_soak_max_runtime_minutes=120)

    await controller.run_deep_soak()
    await hass.async_block_till_done()
    deep_minutes = clock.valve_minutes(VALVE)
    assert deep_minutes > 0
    clock.reset()

    # A completed deep soak also counts as the routine watering, so put the
    # routine back to "due" to reach the cap check at all.
    controller.store.state.last_routine_ts = dt_util.utcnow().timestamp() - 4 * DAY
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    # ~104 min deep soak + ~83 min routine > 150 -> routine must not open the valve.
    assert clock.pulses == []
    assert events[-1] == "Max Daily Runtime Cap Reached"


@pytest.mark.asyncio
async def test_rain_right_now_cancels_before_the_valve_opens(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    # 12 tips x 0.3 mm = 3.6 mm in the last few minutes (> 3 mm threshold).
    hass.states.async_set(RAIN_COUNTER, "12")
    await hass.async_block_till_done()

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    assert clock.pulses == []
    assert "Pre-Irrigation Rain Cancellation" in events
    assert controller.store.state.lock_on is False


def _age_rain_samples(controller, seconds):
    """Pretend all recorded rain fell `seconds` earlier than it did."""
    state = controller.store.state
    state.rain_samples = [[ts - seconds, mm] for ts, mm in state.rain_samples]


def _rain_at(controller, points):
    """Replace the rain record with (days_ago, cumulative_mm) points."""
    now = dt_util.utcnow().timestamp()
    controller.store.state.rain_samples = [[now - d * DAY, mm] for d, mm in points]


@pytest.mark.asyncio
async def test_heavy_rain_starts_the_drydown_holdoff_and_it_expires(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    # 120 tips x 0.3 = 36 mm within 24 h -> crosses the 35 mm significant-rain line.
    hass.states.async_set(RAIN_COUNTER, "120")
    await hass.async_block_till_done()
    assert "Significant Rain" in events
    rain_ts = controller.store.state.last_significant_rain_ts
    assert rain_ts == pytest.approx(dt_util.utcnow().timestamp(), abs=5)
    events.clear()
    _age_rain_samples(controller, 3600)  # an hour ago, so the 30-min cancel isn't what blocks it

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert clock.pulses == []  # held off by the 4-day drydown
    assert events == []  # a silent holdoff, not an error

    # Four days later: holdoff over. The storm is now older than this
    # cycle's own rain window, so it earns no credit either -> full dose.
    controller.store.state.last_significant_rain_ts = rain_ts - 4 * DAY
    _age_rain_samples(controller, 4 * DAY)
    controller.store.state.rain_day_history_mm = [0.0, 0.0, 0.0, 0.0, 36.0] + [0.0] * 5
    controller.store.state.rain_midnight_baseline_mm = 36.0  # midnights have passed since
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert _delivered_mm(clock, controller) == pytest.approx(20.0, abs=_tolerance_mm(controller, 3))


@pytest.mark.asyncio
async def test_abort_during_a_pulse_closes_the_valve_and_records_nothing(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    before = controller.store.state.last_routine_ts

    async def abort_on_third_pulse(index):
        if index == 2:
            await controller._fire_power_loss()  # what the 10-min power-loss watchdog does

    clock.on_pulse = abort_on_third_pulse

    await controller.run_routine_irrigation()
    await hass.async_block_till_done()

    # The third pulse opened the valve, then the abort closed it at once.
    assert hass.states.get(VALVE).state == "off"
    assert hass.states.get(VALVE).state == "off"
    assert controller.store.state.last_routine_ts == before  # not counted as watered
    assert controller.store.state.lock_on is False
    assert "Routine Irrigation Completed" not in events

    # And the next attempt works normally (abort flag doesn't wedge it).
    clock.reset()
    clock.on_pulse = None
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert len(clock.pulses_for(VALVE)) == 3


# ---------------------------------------------------------------------------
# Deep soak
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deep_soak_delivers_its_target_depth(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=1, last_deep_days_ago=14)
    await _set(controller, deep_soak_max_runtime_minutes=150)

    await controller.run_deep_soak()
    await hass.async_block_till_done()

    assert _delivered_mm(clock, controller) == pytest.approx(25.0, abs=_tolerance_mm(controller, 3))
    assert len(clock.pulses_for(VALVE)) == 3
    assert events[-1] == "Deep Soak Completed"
    assert controller.store.state.last_deep_soak_ts == pytest.approx(dt_util.utcnow().timestamp(), abs=5)


@pytest.mark.asyncio
async def test_deep_soak_follows_its_interval_slider(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    await _set(controller, deep_soak_interval_days=7, deep_soak_max_runtime_minutes=150)

    _history(controller, last_deep_days_ago=6)
    await controller.run_deep_soak()
    await hass.async_block_till_done()
    assert clock.pulses == []

    _history(controller, last_deep_days_ago=7)
    await controller.run_deep_soak()
    await hass.async_block_till_done()
    assert clock.valve_minutes(VALVE) > 0


@pytest.mark.asyncio
async def test_deep_soak_skips_when_the_last_two_weeks_were_already_wet(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    await _set(controller, deep_soak_max_runtime_minutes=150)
    _history(controller, last_deep_days_ago=20)
    # 45 mm spread over the last week (never 35 mm in one day, so no
    # significant-rain holdoff) -- only the 14-day ceiling should stop it.
    _rain_at(controller, [(7, 0.0), (6, 15.0), (4, 30.0), (2, 45.0)])

    await controller.run_deep_soak()
    await hass.async_block_till_done()
    assert controller.rain_windows()["14d"] == pytest.approx(45.0)
    assert clock.pulses == []

    # Same zone, only 30 mm in two weeks -> below the 40 mm ceiling -> runs.
    _rain_at(controller, [(13, 0.0), (10, 15.0), (5, 30.0)])
    await controller.run_deep_soak()
    await hass.async_block_till_done()
    assert _delivered_mm(clock, controller) == pytest.approx(25.0, abs=_tolerance_mm(controller, 3))


@pytest.mark.asyncio
async def test_deep_soak_and_routine_never_run_their_valve_at_the_same_time(hass, fake_valve_services, monkeypatch, tmp_path):
    """The shared lock: if routine fires while a deep soak holds the lock, it
    must be a no-op (not a second concurrent cycle on the same valve)."""
    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, last_deep_days_ago=14, peaks=(30.5, 30.5, 30.5))
    await _set(controller, deep_soak_max_runtime_minutes=150)
    routine_during_soak = []

    async def routine_mid_soak(index):
        if index == 0:
            before = len(clock.pulses)
            await controller.run_routine_irrigation()
            routine_during_soak.append(len(clock.pulses) == before)

    clock.on_pulse = routine_mid_soak

    await controller.run_deep_soak()
    await hass.async_block_till_done()

    assert routine_during_soak == [True]  # routine was attempted mid-soak and added no pulse
    assert len(clock.pulses_for(VALVE)) == 3
    # The mid-soak routine attempt recorded nothing; the only update is the
    # completed soak itself counting as the routine watering.
    assert controller.store.state.last_routine_ts == controller.store.state.last_deep_soak_ts


# ---------------------------------------------------------------------------
# Regressions for issues these scenarios found
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_long_slow_drip_pulse_runs_whole_and_its_watchdog_limit_covers_it(hass, fake_valve_services, monkeypatch, tmp_path):
    """Regression: a legitimate single pulse longer than 150 min (slow drip,
    pulse count 1, allowed by the 900-min caps) used to be killed by the
    stuck-valve watchdog every time. The limit now stretches to the planned
    pulse + 30 min while ZoneFlow runs it."""
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_deep_days_ago=14)
    await _set(
        controller,
        flow_rate_mm_per_min=0.1,
        deep_soak_pulse_count=1,
        deep_soak_max_runtime_minutes=300,
        max_daily_runtime_minutes=300,  # the 240-min default daily cap would (correctly) refuse 250 min
    )
    limits = []

    async def note_limit(index):
        limits.append(controller._valve_stuck_limit_minutes())

    clock.on_pulse = note_limit
    await controller.run_deep_soak()
    await hass.async_block_till_done()

    assert clock.pulses_for(VALVE) == [250.0]  # 25 mm / 0.1 mm/min in one pulse
    assert limits == [280.0]
    assert events[-1] == "Deep Soak Completed"
    assert controller._expected_pulse_minutes is None  # cleared once the valve closed


# ---------------------------------------------------------------------------
# A completed deep soak also counts as the routine watering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_completed_deep_soak_counts_as_routine_watering(hass, fake_valve_services, monkeypatch, tmp_path):
    """Regression (production, 26 Sep): deep soak at 05:00 with the last
    routine 4 days earlier, and the routine ran again the next morning --
    ~48 mm in two days. A completed deep soak restarts the routine clock."""
    controller, clock, events = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, last_deep_days_ago=14, peaks=(30.5, 30.5, 30.5))
    await controller.run_deep_soak()
    await hass.async_block_till_done()
    assert events[-1] == "Deep Soak Completed"
    state = controller.store.state
    assert state.last_routine_ts == state.last_deep_soak_ts
    assert state.last_routine_ts == pytest.approx(dt_util.utcnow().timestamp(), abs=60)

    # The routine due by the old clock no longer runs...
    clock.reset()
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert clock.pulses == []

    # ...and the estimate counts one routine interval (4 days) from the soak.
    next_ts, source = controller.routine_next_estimate()
    assert source == "schedule"
    assert next_ts == pytest.approx(state.last_deep_soak_ts + 4 * DAY, abs=60)


@pytest.mark.asyncio
async def test_unfinished_deep_soak_does_not_count_as_routine(hass, fake_valve_services, monkeypatch, tmp_path):
    """Only a completed soak counts: an aborted or interrupted one leaves the
    routine clock alone, so the routine still runs when due."""
    from unittest.mock import AsyncMock

    controller, clock, _ = await _zone(hass, monkeypatch, tmp_path)
    _history(controller, last_routine_days_ago=4, last_deep_days_ago=14, peaks=(30.5, 30.5, 30.5))
    before = controller.store.state.last_routine_ts
    real = controller._run_pulses
    controller._run_pulses = AsyncMock(return_value=False)
    await controller.run_deep_soak()
    await hass.async_block_till_done()
    assert controller.store.state.last_routine_ts == before
    controller._run_pulses = real
    await controller._set_lock(False)
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert clock.valve_minutes(VALVE) > 0
