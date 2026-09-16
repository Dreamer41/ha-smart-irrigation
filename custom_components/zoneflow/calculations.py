"""Pure, HA-free port of the Jinja math in the confirmed-final automations.yaml.

Every function here has a docstring pointing at the automation section it
mirrors. Keeping this pure (no hass, no entities) is what makes it possible
to unit-test the actual irrigation math in isolation, the same way
`tests/test_calculations.py` exercises it.

IMPORTANT: Jinja's `round()` filter defaults to method="common", which is
round-half-up (0.5 always rounds away from zero), NOT Python's native
round() (which is round-half-to-even / banker's rounding). `jinja_round`
below reproduces the Jinja behavior so runtime-minute calculations match
the live automation exactly.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


def jinja_round(value: float, ndigits: int = 0) -> float:
    """Round the way Jinja's default `| round(ndigits)` does (half-up)."""
    factor = 10**ndigits
    result = math.floor(abs(value) * factor + 0.5) / factor
    result = math.copysign(result, value) if value != 0 else 0.0
    return result if ndigits > 0 else int(result) if result == int(result) else result


def rain_efficiency(mm: float, low_eff: float, mid_eff: float, high_eff: float) -> float:
    """Port of the `eff()` macro used by both rain-deduction blocks.

    mm <= 3          -> 0.0
    3  < mm <= 5      -> ramps 0 -> low_eff
    5  < mm <= 10      -> ramps low_eff -> mid_eff
    10 < mm <= 20      -> ramps mid_eff -> high_eff
    mm > 20            -> high_eff
    """
    if mm <= 3:
        return 0.0
    if mm <= 5:
        return (mm - 3) / 2 * low_eff
    if mm <= 10:
        return low_eff + (mm - 5) / 5 * (mid_eff - low_eff)
    if mm <= 20:
        return mid_eff + (mm - 10) / 10 * (high_eff - mid_eff)
    return high_eff


def rain_deduction_mm(
    today_mm: float,
    day_history_mm: list[float],
    days_elapsed: int,
    low_eff: float,
    mid_eff: float,
    high_eff: float,
) -> float:
    """Port of the `eff_rain` variable in avocado_routine_irrigation.

    day_history_mm[0] is "yesterday" (rain_day_1) ... [9] is 10 days ago.
    Only the first `min(days_elapsed, 10)` history days are summed, exactly
    like the YAML's `days_to_sum = [days_elapsed, 10] | min`.
    """
    days_to_sum = min(days_elapsed, 10)
    total = today_mm * rain_efficiency(today_mm, low_eff, mid_eff, high_eff)
    for i in range(days_to_sum):
        mm = day_history_mm[i] if i < len(day_history_mm) else 0.0
        total += mm * rain_efficiency(mm, low_eff, mid_eff, high_eff)
    return jinja_round(total, 2)


def three_day_average_peak_temp(day_values: list[float | None]) -> float:
    """Port of the `sensor.3_day_average_peak_temperature` template.

    Days with no reading, or outside 15-50C, are dropped as corrupt.
    Falls back to 30.0 only if all three are corrupt/missing.
    """
    valid = [v for v in day_values if v is not None and 15.0 <= v <= 50.0]
    if not valid:
        return 30.0
    return jinja_round(sum(valid) / len(valid), 2)


@dataclass
class DeepSoakPlan:
    target_mm: float
    flow_rate: float
    total_runtime_minutes: int
    pulse_runtime_minutes: int


def plan_deep_soak(target_mm: float, flow_rate: float) -> DeepSoakPlan:
    """Port of the variables block in avocado_deep_soak.

    total_runtime = round(target_mm / flow_rate)
    pulse_runtime = max(round(total_runtime / 3), 5)   # 3 pulses, 5-min floor
    """
    total_runtime = int(jinja_round(target_mm / flow_rate, 0))
    pulse_runtime = max(int(jinja_round(total_runtime / 3, 0)), 5)
    return DeepSoakPlan(target_mm, flow_rate, total_runtime, pulse_runtime)


@dataclass
class RoutinePlan:
    interval_days: int
    target_weekly_mm: float
    interval_target_mm: float
    eff_rain_mm: float
    needed_mm: float
    calc_runtime_minutes: int
    pulse_runtime_minutes: int


def routine_interval_days(avg_peak_temp: float, hot_threshold: float) -> int:
    """Port of `target_interval_days`: 3 if hot, else 4."""
    return 3 if avg_peak_temp >= hot_threshold else 4


def routine_target_weekly_mm(
    avg_peak_temp: float,
    hot_threshold: float,
    cool_threshold: float,
    normal_mm: float,
    hot_mm: float,
    cool_mm: float,
) -> float:
    """Port of `target_weekly_mm`. Hot is tested before cool so the two
    thresholds can never invert, exactly as the YAML comment states."""
    if avg_peak_temp >= hot_threshold:
        return hot_mm
    if avg_peak_temp < cool_threshold:
        return cool_mm
    return normal_mm


def plan_routine_irrigation(
    *,
    avg_peak_temp: float,
    hot_threshold: float,
    cool_threshold: float,
    normal_weekly_mm: float,
    hot_weekly_mm: float,
    cool_weekly_mm: float,
    flow_rate: float,
    days_elapsed: int,
    today_rain_mm: float,
    rain_day_history_mm: list[float],
    rain_eff_low: float,
    rain_eff_mid: float,
    rain_eff_high: float,
) -> RoutinePlan:
    """Port of the full variables block in avocado_routine_irrigation
    (interval_target_mm through pulse_runtime)."""
    interval_days = routine_interval_days(avg_peak_temp, hot_threshold)
    target_weekly_mm = routine_target_weekly_mm(
        avg_peak_temp, hot_threshold, cool_threshold, normal_weekly_mm, hot_weekly_mm, cool_weekly_mm
    )
    interval_target_mm = (target_weekly_mm / 7.0) * interval_days
    eff_rain = rain_deduction_mm(
        today_rain_mm, rain_day_history_mm, days_elapsed, rain_eff_low, rain_eff_mid, rain_eff_high
    )
    needed_mm = max(interval_target_mm - eff_rain, 0.0)
    calc_runtime = int(jinja_round(needed_mm / flow_rate, 0))
    pulse_runtime = max(int(jinja_round(calc_runtime / 3, 0)), 1)
    return RoutinePlan(
        interval_days=interval_days,
        target_weekly_mm=target_weekly_mm,
        interval_target_mm=interval_target_mm,
        eff_rain_mm=eff_rain,
        needed_mm=needed_mm,
        calc_runtime_minutes=calc_runtime,
        pulse_runtime_minutes=pulse_runtime,
    )


def routine_due(elapsed_seconds: float, interval_days: int, buffer_seconds: int) -> bool:
    """Port of `elapsed_seconds >= target_interval_seconds`
    where target_interval_seconds = interval_days*86400 - buffer_seconds."""
    return elapsed_seconds >= (interval_days * 86400 - buffer_seconds)


def deep_soak_due(elapsed_seconds: float, interval_days: int, buffer_seconds: int) -> bool:
    """Port of the deep-soak 14-day-with-6h-buffer check."""
    return elapsed_seconds >= (interval_days * 86400 - buffer_seconds)


def drydown_satisfied(elapsed_seconds_since_rain: float, drydown_days: float) -> bool:
    """Port of the dry-down check shared by both deep soak and routine."""
    return elapsed_seconds_since_rain >= (drydown_days * 86400)


@dataclass
class NextIrrigationEstimate:
    routine_next_ts: float
    rain_next_ts: float
    next_ts: float


def estimate_next_irrigation(
    last_routine_ts: float,
    last_significant_rain_ts: float,
    avg_peak_temp: float,
    hot_threshold: float,
    routine_drydown_days: float,
) -> NextIrrigationEstimate:
    """Port of `sensor.avocado_next_irrigation_estimate`."""
    interval_days = routine_interval_days(avg_peak_temp, hot_threshold)
    routine_next = last_routine_ts + interval_days * 86400
    rain_next = last_significant_rain_ts + routine_drydown_days * 86400
    return NextIrrigationEstimate(routine_next, rain_next, max(routine_next, rain_next))


def estimate_last_water_delivered_mm(
    avg_peak_temp: float,
    hot_threshold: float,
    cool_threshold: float,
    normal_weekly_mm: float,
    hot_weekly_mm: float,
    cool_weekly_mm: float,
) -> float:
    """Port of `sensor.last_avocado_water_delivered` (per-session estimate,
    i.e. half the applicable weekly target)."""
    target = routine_target_weekly_mm(
        avg_peak_temp, hot_threshold, cool_threshold, normal_weekly_mm, hot_weekly_mm, cool_weekly_mm
    )
    return jinja_round(target / 2, 1)
