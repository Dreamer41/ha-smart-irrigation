"""Unit tests for the pure calculation port (no Home Assistant dependency).

Values below are hand-computed against the same Jinja expressions in the
confirmed-final automations.yaml, not just against the Python re-implementation,
so these catch a drifted port, not just a self-consistent one.
"""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "zoneflow"))

import calculations as calc  # noqa: E402


def test_jinja_round_half_up():
    assert calc.jinja_round(2.5, 0) == 3
    assert calc.jinja_round(-2.5, 0) == -3
    assert calc.jinja_round(0.125, 2) == 0.13


def test_rain_efficiency_bands():
    low, mid, high = 0.2, 0.6, 1.0
    assert calc.rain_efficiency(2, low, mid, high) == 0.0
    assert calc.rain_efficiency(3, low, mid, high) == 0.0
    # 4mm: midpoint of the 3-5 ramp -> half of low_eff
    assert math.isclose(calc.rain_efficiency(4, low, mid, high), (4 - 3) / 2 * low)
    assert calc.rain_efficiency(5, low, mid, high) == low
    assert math.isclose(calc.rain_efficiency(10, low, mid, high), mid)
    assert calc.rain_efficiency(20, low, mid, high) == high
    assert calc.rain_efficiency(50, low, mid, high) == high


def test_rain_deduction_uses_only_days_to_sum():
    # days_elapsed=2 -> only rain_day_1 and rain_day_2 count, not the rest
    history = [10.0, 10.0, 999.0, 999.0]
    total = calc.rain_deduction_mm(0.0, history, days_elapsed=2, low_eff=0.2, mid_eff=0.6, high_eff=1.0)
    expected = 10.0 * calc.rain_efficiency(10.0, 0.2, 0.6, 1.0) * 2
    assert math.isclose(total, expected, rel_tol=1e-6)


def test_rain_deduction_caps_history_depth_at_10():
    history = [5.0] * 20
    total_capped = calc.rain_deduction_mm(0.0, history, days_elapsed=15, low_eff=0.2, mid_eff=0.6, high_eff=1.0)
    total_at_10 = calc.rain_deduction_mm(0.0, history, days_elapsed=10, low_eff=0.2, mid_eff=0.6, high_eff=1.0)
    assert total_capped == total_at_10


def test_rain_deduction_max_lookback_days_is_overridable():
    # A storm sitting just past a 4-day window must not count once the
    # caller passes max_lookback_days=4 -- this is what plan_routine_irrigation
    # now does with its own interval_days instead of relying on the 10 default.
    history = [0.0, 0.0, 0.0, 0.0, 77.0, 31.5, 12.7]  # big rain at days 5-7
    total = calc.rain_deduction_mm(
        0.0, history, days_elapsed=11, low_eff=0.2, mid_eff=0.6, high_eff=1.0, max_lookback_days=4
    )
    assert total == 0.0
    # Same history with the old default (10) would have picked up the storm.
    total_default = calc.rain_deduction_mm(
        0.0, history, days_elapsed=11, low_eff=0.2, mid_eff=0.6, high_eff=1.0
    )
    assert total_default > 0.0


def test_three_day_average_drops_impossible_days():
    # An impossible reading (-99, 85) is a broken sensor and is dropped, not
    # averaged in.
    assert calc.three_day_average_peak_temp([30.0, 32.0, -99.0]) == calc.jinja_round((30.0 + 32.0) / 2, 2)
    assert calc.three_day_average_peak_temp([30.0, None, 85.0]) == 30.0


def test_three_day_average_counts_cold_days():
    # A Nordic spring: 8-14C afternoons are real weather, not corrupt data
    # (the original YAML dropped anything below 15C).
    assert calc.three_day_average_peak_temp([12.0, 8.0, 14.0]) == calc.jinja_round(34.0 / 3, 2)
    assert calc.three_day_average_peak_temp([-5.0, 0.0, 2.0]) == calc.jinja_round(-3.0 / 3, 2)


def test_three_day_average_without_real_days_is_none_not_30():
    assert calc.three_day_average_peak_temp([None, None, None]) is None
    assert calc.three_day_average_peak_temp([-99.0, 61.0, None]) is None


@pytest.mark.parametrize(
    "temp,tier", [(None, "normal"), (35.0, "hot"), (28.0, "hot"), (27.9, "normal"), (20.0, "normal"), (19.9, "cool"), (5.0, "cool")]
)
def test_temperature_tier_temperate_thresholds(temp, tier):
    assert calc.temperature_tier(temp, 28.0, 20.0) == tier
    expected_mm = {"hot": 45.0, "cool": 25.0, "normal": 35.0}[tier]
    assert calc.routine_target_weekly_mm(temp, 28.0, 20.0, 35.0, 45.0, 25.0) == expected_mm


def test_plan_deep_soak_matches_yaml_formula():
    # target 25mm / flow 0.24 mm/min = 104.166 -> round -> 104
    plan = calc.plan_deep_soak(target_mm=25.0, flow_rate=0.24)
    assert plan.total_runtime_minutes == round(25.0 / 0.24)
    # Split exactly: 3 pulses that add up to the logged 104 minutes.
    assert plan.pulse_count == 3
    assert plan.pulse_runtime_minutes * plan.pulse_count == pytest.approx(plan.total_runtime_minutes)


def test_plan_deep_soak_pulse_floor_is_5_minutes():
    plan = calc.plan_deep_soak(target_mm=1.0, flow_rate=2.0)  # total_runtime = 1min -> pulse would be 0
    assert plan.pulse_runtime_minutes == 5


def test_routine_interval_and_tier_selection():
    assert calc.routine_interval_days(32.0, hot_threshold=31.5) == 3
    assert calc.routine_interval_days(31.4, hot_threshold=31.5) == 4
    # hot wins even if also below the (nonsensical) cool threshold
    assert calc.routine_target_weekly_mm(35.0, 31.5, 30.0, 35.0, 45.0, 25.0) == 45.0
    assert calc.routine_target_weekly_mm(29.0, 31.5, 30.0, 35.0, 45.0, 25.0) == 25.0
    assert calc.routine_target_weekly_mm(30.5, 31.5, 30.0, 35.0, 45.0, 25.0) == 35.0


def test_plan_routine_irrigation_needed_mm_never_negative():
    plan = calc.plan_routine_irrigation(
        avg_peak_temp=30.5,
        hot_threshold=31.5,
        cool_threshold=30.0,
        normal_weekly_mm=35.0,
        hot_weekly_mm=45.0,
        cool_weekly_mm=25.0,
        flow_rate=0.24,
        days_elapsed=4,
        today_rain_mm=200.0,  # huge rain should floor needed_mm at 0, not go negative
        rain_day_history_mm=[0.0] * 10,
        rain_eff_low=0.2,
        rain_eff_mid=0.6,
        rain_eff_high=1.0,
    )
    assert plan.needed_mm == 0.0
    assert plan.calc_runtime_minutes == 0


def test_plan_routine_irrigation_old_storm_no_longer_blocks_new_cycle():
    """Regression test for the real 2026-09-21 incident: a storm 5-7 days
    ago (already handled by the separate significant-rain drydown holdoff)
    used to keep crediting the routine cycle's rain deduction for up to 10
    days afterwards, even though the interval is only 3-4 days. Once the
    drydown holdoff has cleared (checked separately by the caller, not by
    this function), the rain-credit window must match the current interval,
    not a fixed 10 days, so old already-handled rain can't silently zero out
    every cycle until it ages out of a much longer window.
    """
    # Cool tier -> interval_days=4, target 25mm/7*4 = ~14.3mm. Big rain sits
    # at days 5-7 (indices 4-6), outside a 4-day window but inside the old
    # fixed 10-day one.
    history = [0.0, 0.0, 0.0, 0.0, 77.0, 31.5, 12.7, 0.0, 0.0, 0.0]
    plan = calc.plan_routine_irrigation(
        avg_peak_temp=29.7,
        hot_threshold=31.5,
        cool_threshold=30.0,
        normal_weekly_mm=35.0,
        hot_weekly_mm=45.0,
        cool_weekly_mm=25.0,
        flow_rate=0.24,
        days_elapsed=11,
        today_rain_mm=0.0,
        rain_day_history_mm=history,
        rain_eff_low=0.2,
        rain_eff_mid=0.6,
        rain_eff_high=1.0,
    )
    assert plan.interval_days == 4
    assert plan.eff_rain_mm == 0.0  # the days-5-7 storm is outside the 4-day window
    assert plan.needed_mm > 0.0
    assert plan.calc_runtime_minutes > 0


def test_drydown_and_due_thresholds_use_correct_buffer():
    # exactly at the 6h-buffered boundary should be due
    assert calc.deep_soak_due(14 * 86400 - 21600, 14, 21600) is True
    assert calc.deep_soak_due(14 * 86400 - 21601, 14, 21600) is False
    assert calc.drydown_satisfied(4 * 86400, 4.0) is True
    assert calc.drydown_satisfied(4 * 86400 - 1, 4.0) is False


def test_estimate_next_irrigation_takes_the_later_date():
    est = calc.estimate_next_irrigation(
        last_routine_ts=1000.0,
        last_significant_rain_ts=2000.0,
        avg_peak_temp=35.0,
        hot_threshold=31.5,
        routine_drydown_days=4.0,
    )
    assert est.next_ts == max(est.routine_next_ts, est.rain_next_ts)


def test_soil_moisture_none_is_a_pure_passthrough_of_interval_due():
    """No sensor configured (or currently unreadable) must behave exactly
    as if the feature didn't exist -- a pure passthrough either way."""
    assert calc.routine_due_with_soil_moisture(True, None, 20.0, 60.0) is True
    assert calc.routine_due_with_soil_moisture(False, None, 20.0, 60.0) is False


def test_soil_moisture_wet_skips_even_when_interval_says_overdue():
    assert calc.routine_due_with_soil_moisture(True, 65.0, 20.0, 60.0) is False


def test_soil_moisture_dry_waters_even_when_interval_says_not_due_yet():
    assert calc.routine_due_with_soil_moisture(False, 15.0, 20.0, 60.0) is True


def test_soil_moisture_ambiguous_middle_band_defers_to_interval():
    assert calc.routine_due_with_soil_moisture(True, 40.0, 20.0, 60.0) is True
    assert calc.routine_due_with_soil_moisture(False, 40.0, 20.0, 60.0) is False


def test_soil_moisture_exactly_at_thresholds():
    # >= wet_pct skips; <= dry_pct waters -- boundary values are inclusive
    # on both sides, matching the docstring's ">=" / "<=" wording exactly.
    assert calc.routine_due_with_soil_moisture(True, 60.0, 20.0, 60.0) is False
    assert calc.routine_due_with_soil_moisture(False, 20.0, 20.0, 60.0) is True


def test_soil_moisture_inverted_thresholds_never_raises():
    """dry_pct >= wet_pct isn't cross-validated (same as the growth-ramp
    custom curve's points) -- every reading must still resolve to a real
    True/False at one of the two extremes rather than erroring."""
    assert calc.routine_due_with_soil_moisture(True, 50.0, 70.0, 30.0) is False
    assert calc.routine_due_with_soil_moisture(True, 10.0, 70.0, 30.0) is True


def test_adjust_drydown_days_shrinks_and_extends():
    assert calc.adjust_drydown_days(4.0, -0.5, 1.0, 10.0) == 3.5
    assert calc.adjust_drydown_days(4.0, 0.5, 1.0, 10.0) == 4.5


def test_adjust_drydown_days_clamps_at_minimum():
    assert calc.adjust_drydown_days(1.2, -0.5, 1.0, 10.0) == 1.0
    assert calc.adjust_drydown_days(1.0, -0.5, 1.0, 10.0) == 1.0


def test_adjust_drydown_days_clamps_at_maximum():
    assert calc.adjust_drydown_days(9.8, 0.5, 1.0, 10.0) == 10.0
    assert calc.adjust_drydown_days(10.0, 0.5, 1.0, 10.0) == 10.0


# --- Hargreaves-Samani ET0 ------------------------------------------------

def test_extraterrestrial_radiation_matches_fao56_example_8():
    """FAO-56 Example 8: 20 deg S on 3 September (day 246) -> Ra = 32.2
    MJ/m2/day. The function returns mm/day, i.e. x0.408."""
    ra_mm = calc.extraterrestrial_radiation_mm(-20.0, 246)
    assert ra_mm / calc.MJ_M2_TO_MM_WATER == pytest.approx(32.2, abs=0.1)


def test_extraterrestrial_radiation_survives_polar_day_and_night():
    assert calc.extraterrestrial_radiation_mm(80.0, 172) > 0  # midsummer sun
    assert calc.extraterrestrial_radiation_mm(80.0, 355) == 0.0  # polar night


def test_hargreaves_et0_matches_hand_calculation():
    ra = calc.extraterrestrial_radiation_mm(9.5, 268)
    expected = 0.0023 * (28.5 + 17.8) * (32.0 - 25.0) ** 0.5 * ra
    assert calc.hargreaves_et0(25.0, 32.0, 9.5, 268) == pytest.approx(expected)
    # A tropical day like that lands in the usual 4-5 mm/day band.
    assert 4.0 < calc.hargreaves_et0(25.0, 32.0, 9.5, 268) < 5.5


def test_hargreaves_et0_rises_with_heat_and_temperature_range():
    base = calc.hargreaves_et0(25.0, 32.0, 9.5, 268)
    assert calc.hargreaves_et0(25.0, 35.0, 9.5, 268) > base
    assert calc.hargreaves_et0(28.0, 32.0, 9.5, 268) < base


@pytest.mark.parametrize(
    "t_min,t_max",
    [(None, 30.0), (20.0, None), (31.0, 30.0), (-60.0, 10.0), (10.0, 75.0)],
)
def test_hargreaves_et0_returns_none_for_unusable_pairs(t_min, t_max):
    assert calc.hargreaves_et0(t_min, t_max, 9.5, 268) is None


def test_average_et0_drops_missing_days_and_never_invents_a_value():
    assert calc.average_et0([4.0, None, 5.0]) == 4.5
    assert calc.average_et0([None, None, None]) is None


def test_et_weekly_target_is_et0_times_seven_times_kc():
    assert calc.et_weekly_target_mm(4.0, 0.8) == 22.4
    assert calc.et_weekly_target_mm(5.0, 1.0) == 35.0
    assert calc.et_weekly_target_mm(-1.0, 0.8) == 0.0


def test_plan_routine_irrigation_uses_the_override_target_when_given():
    common = dict(
        avg_peak_temp=35.0,  # hot tier on its own
        hot_threshold=31.5,
        cool_threshold=30.0,
        normal_weekly_mm=35.0,
        hot_weekly_mm=45.0,
        cool_weekly_mm=25.0,
        flow_rate=0.24,
        days_elapsed=3,
        today_rain_mm=0.0,
        rain_day_history_mm=[0.0] * 10,
        rain_eff_low=0.2,
        rain_eff_mid=0.6,
        rain_eff_high=1.0,
    )
    tiers = calc.plan_routine_irrigation(**common)
    et = calc.plan_routine_irrigation(**common, weekly_target_override_mm=21.0)
    assert tiers.target_weekly_mm == 45.0
    assert et.target_weekly_mm == 21.0
    # The interval still follows the hot threshold under the ET model.
    assert et.interval_days == tiers.interval_days == 3
    assert et.interval_target_mm == pytest.approx(21.0 / 7 * 3)


def test_last_water_delivered_follows_the_override_target():
    args = (30.5, 31.5, 30.0, 35.0, 45.0, 25.0)
    assert calc.estimate_last_water_delivered_mm(*args) == 17.5
    assert calc.estimate_last_water_delivered_mm(*args, weekly_target_override_mm=28.0) == 14.0


# --- exact pulse split -------------------------------------------------------

@pytest.mark.parametrize(
    "total,count,floor,expected",
    [
        (3, 2, 1, (2, 1.5)),      # the live sandbox case: used to become 2 + 2 = 4 min
        (84, 3, 1, (3, 28.0)),
        (83, 3, 1, (3, 83 / 3)),  # no longer rounded per pulse
        (2, 3, 1, (2, 1.0)),      # too small for 3 one-minute pulses -> 2 pulses
        (1, 3, 1, (1, 1.0)),
        (12, 3, 5, (2, 6.0)),     # deep soak: 5-min floor -> 2 pulses of 6
        (3, 3, 5, (1, 5.0)),      # below one minimum pulse: the single floor pulse remains
        (0, 3, 1, (3, 0.0)),
    ],
)
def test_split_pulses_delivers_exactly_the_planned_minutes(total, count, floor, expected):
    got = calc.split_pulses(total, count, floor)
    assert got[0] == expected[0]
    assert got[1] == pytest.approx(expected[1])
    if total >= floor:
        assert got[0] * got[1] == pytest.approx(total)


# --- rain counter: resets vs glitches ---------------------------------------

def _feed(readings, start=0.0, step=60.0):
    """Feed raw counter readings a minute apart; return the tip total after each."""
    total = last = drop_from = drop_ts = None
    since = 0.0
    out = []
    for i, tips in enumerate(readings):
        total, last, drop_from, drop_ts, since = calc.track_tip_total(
            total, last, drop_from, drop_ts, since, tips, start + i * step
        )
        out.append(total)
    return out


def test_tip_total_counts_up_normally():
    assert _feed([100, 101, 102, 110]) == [100, 101, 102, 110]


def test_a_real_reset_keeps_old_rain_and_counts_new_tips():
    assert _feed([20, 0, 1, 2, 3])[-1] == 23


def test_a_brief_drop_to_zero_and_back_adds_no_fake_rain():
    """The reviewer's case: a template briefly reporting 0 while its source
    is unavailable, then the real 1500 again."""
    assert _feed([1500, 0, 1500]) == [1500, 1500, 1500]


def test_a_brief_drop_with_a_tip_counted_in_between_is_taken_back():
    assert _feed([1500, 0, 1, 1500])[-1] == 1500


def test_coming_back_above_the_old_level_counts_only_the_new_tips():
    assert _feed([1500, 0, 1503])[-1] == 1503


def test_a_one_tip_debounce_correction_costs_at_most_one_tip():
    assert _feed([1500, 1499, 1500])[-1] in (1500, 1501)


def test_a_small_counter_reset_that_climbs_back_tip_by_tip_is_real_rain():
    # 5 tips, reset, then 6 real tips one at a time within the hour.
    assert _feed([5, 0, 1, 2, 3, 4, 5, 6])[-1] == 11


def test_a_glitch_lasting_hours_still_adds_no_fake_rain():
    """Reviewer's case: a sleeping device reads 0 for two hours overnight."""
    assert _feed([1500, 0, 1500], step=2 * 3600) == [1500, 1500, 1500]


def test_a_glitch_with_a_little_rain_meanwhile_counts_just_that_rain():
    assert _feed([1500, 0, 1503])[-1] == 1503


def test_a_small_daily_reset_counter_never_loses_its_next_batch():
    # 3 tips yesterday, reset at midnight, gauge polls and reports 5 at once.
    assert _feed([3, 0, 5])[-1] == 8


def test_a_big_daily_reset_counter_keeps_a_bigger_next_day():
    # 200 tips yesterday, reset, next day a batch of 260 -- not "back where it was".
    assert _feed([200, 0, 120, 260])[-1] == 460


def test_a_jump_back_after_a_week_is_real_rain():
    total = last = drop_from = drop_ts = None
    since = 0.0
    for tips, t in ((1500, 0), (0, 60), (1500, 60 + 8 * 86400)):
        total, last, drop_from, drop_ts, since = calc.track_tip_total(total, last, drop_from, drop_ts, since, tips, t)
    assert total == 3000
