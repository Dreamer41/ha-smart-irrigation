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
    max_lookback_days: int = 10,
) -> float:
    """Port of the `eff_rain` variable in avocado_routine_irrigation.

    day_history_mm[0] is "yesterday" (rain_day_1) ... [9] is 10 days ago.
    Only the first `min(days_elapsed, max_lookback_days)` history days are
    summed. `max_lookback_days` used to be a hardcoded 10 (matching the
    original YAML's `days_to_sum = [days_elapsed, 10] | min`), which meant a
    storm from over a week ago -- already handled by the separate
    significant-rain drydown holdoff -- could keep suppressing routine
    watering for up to 10 days after it fell, long after the holdoff itself
    had cleared. `plan_routine_irrigation` now passes the zone's own
    `interval_days` (3 hot / 4 normal-or-cool) here instead, so each cycle
    only ever credits rain that actually fell within that cycle's own
    window. The 10-day default is kept only for direct callers that don't
    pass their own interval.
    """
    days_to_sum = min(days_elapsed, max_lookback_days)
    total = today_mm * rain_efficiency(today_mm, low_eff, mid_eff, high_eff)
    for i in range(days_to_sum):
        mm = day_history_mm[i] if i < len(day_history_mm) else 0.0
        total += mm * rain_efficiency(mm, low_eff, mid_eff, high_eff)
    return jinja_round(total, 2)


RAIN_COUNTER_GLITCH_WINDOW_SECONDS = 7 * 86400
# A glitch brings the count back to where it was, plus at most a few tips
# of rain that fell meanwhile.
RAIN_COUNTER_GLITCH_RETURN_TOLERANCE_TIPS = 5
# Below this many tips, any drop is treated as a real reset: getting a tiny
# counter wrong costs a few mm at most, while treating a small daily-reset
# counter's next reading as a "glitch" would drop real rain every day.
RAIN_COUNTER_GLITCH_MIN_TIPS = 20


def track_tip_total(
    total: float | None,
    last: float | None,
    drop_from: float | None,
    drop_ts: float | None,
    since_drop: float,
    tips: float,
    now_ts: float,
) -> tuple[float, float, float | None, float | None, float]:
    """Turn a raw rain-gauge tip count into an ever-growing total, surviving
    both real resets and glitches. Returns the new
    (total, last, drop_from, drop_ts, since_drop).

    - Counting up: the increase is added to the total.
    - The count going DOWN is either a real reset (a counter helper reset,
      a gauge that forgets its count on reboot, a daily-reset counter) or a
      glitch (a template reporting 0 while its source is unavailable,
      perhaps for hours). Nothing is added or removed at the drop; later
      tips count normally from the new, lower number.
    - A glitch ends with the count jumping back (more than one tip in a
      single reading) to where it was before the drop -- give or take a
      few tips of rain that fell meanwhile -- within a week. When that
      happens, whatever was counted since the drop is taken back and only
      the tips beyond the old level are added. Real rain landing a reset
      counter back on exactly its old total in one jump is not a realistic
      event, so a genuine reset isn't mistaken for this; counters below
      RAIN_COUNTER_GLITCH_MIN_TIPS are always treated as real resets.
    """
    if total is None or last is None:
        return tips, tips, None, None, 0.0
    if drop_from is not None and drop_ts is not None and now_ts - drop_ts > RAIN_COUNTER_GLITCH_WINDOW_SECONDS:
        drop_from, drop_ts, since_drop = None, None, 0.0
    if (
        drop_from is not None
        and drop_from <= tips <= drop_from + RAIN_COUNTER_GLITCH_RETURN_TOLERANCE_TIPS
        and tips - last > 1
    ):
        return total - since_drop + (tips - drop_from), tips, None, None, 0.0
    if tips >= last:
        increase = tips - last
        return total + increase, tips, drop_from, drop_ts, (since_drop + increase if drop_from is not None else 0.0)
    if drop_from is None and last >= RAIN_COUNTER_GLITCH_MIN_TIPS:
        return total, tips, last, now_ts, 0.0
    return total, tips, drop_from, drop_ts, since_drop


def three_day_average_peak_temp(day_values: list[float | None]) -> float:
    """Port of the `sensor.3_day_average_peak_temperature` template.

    Days with no reading, or outside 15-50C, are dropped as corrupt.
    Falls back to 30.0 only if all three are corrupt/missing.
    """
    valid = [v for v in day_values if v is not None and 15.0 <= v <= 50.0]
    if not valid:
        return 30.0
    return jinja_round(sum(valid) / len(valid), 2)


# ----------------------------------------------------------------------
# Reference evapotranspiration (ET0) -- Hargreaves-Samani
# ----------------------------------------------------------------------
# Not a port of anything in the original YAML: this is the temperature-only
# ET0 method from FAO Irrigation & Drainage Paper 56 (eq. 52), chosen
# because it needs nothing beyond the outdoor temperature sensor every zone
# already has, plus latitude and the date. Penman-Monteith (the FAO
# reference method) would need humidity, wind and solar-radiation sensors.
# For now this is display-only -- nothing in the watering math reads it
# yet.

SOLAR_CONSTANT_MJ_M2_MIN = 0.0820
MJ_M2_TO_MM_WATER = 0.408  # latent heat conversion, FAO-56 eq. 20


def extraterrestrial_radiation_mm(latitude_deg: float, day_of_year: int) -> float:
    """Ra, top-of-atmosphere solar radiation for one day, expressed as mm/day
    of evaporation-equivalent (FAO-56 eqs. 21-25, then x0.408).

    Clamps the sunset-hour-angle argument to [-1, 1] so polar day/night
    latitudes give 24h/0h of sun instead of a math domain error."""
    phi = math.radians(latitude_deg)
    angle = 2 * math.pi * day_of_year / 365
    dr = 1 + 0.033 * math.cos(angle)
    decl = 0.409 * math.sin(angle - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(decl))))
    ra_mj = (
        (24 * 60 / math.pi)
        * SOLAR_CONSTANT_MJ_M2_MIN
        * dr
        * (ws * math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.sin(ws))
    )
    return max(ra_mj, 0.0) * MJ_M2_TO_MM_WATER


def hargreaves_et0(
    t_min_c: float | None, t_max_c: float | None, latitude_deg: float, day_of_year: int
) -> float | None:
    """Daily reference ET0 in mm/day (FAO-56 eq. 52):

        ET0 = 0.0023 * (Tmean + 17.8) * sqrt(Tmax - Tmin) * Ra

    Returns None -- "no usable reading for that day", never a guessed
    number -- when either temperature is missing, outside a physically
    plausible range (-40..60C), or Tmin > Tmax (a corrupt pair)."""
    if t_min_c is None or t_max_c is None:
        return None
    if not (-40.0 <= t_min_c <= 60.0 and -40.0 <= t_max_c <= 60.0) or t_min_c > t_max_c:
        return None
    t_mean = (t_max_c + t_min_c) / 2
    ra = extraterrestrial_radiation_mm(latitude_deg, day_of_year)
    return max(0.0023 * (t_mean + 17.8) * math.sqrt(t_max_c - t_min_c) * ra, 0.0)


def average_et0(daily_values: list[float | None]) -> float | None:
    """Mean of the days that produced a usable ET0, or None if none did --
    same drop-the-bad-days approach as three_day_average_peak_temp, but
    with no invented fallback number, since a made-up ET0 would look like
    a real measurement on the dashboard."""
    valid = [v for v in daily_values if v is not None]
    if not valid:
        return None
    return jinja_round(sum(valid) / len(valid), 2)


def et_weekly_target_mm(avg_et0_mm_per_day: float, crop_coefficient: float) -> float:
    """ET demand model's weekly target: ET0 (mm/day) x 7 days x crop factor.
    See const.py's DEMAND_MODEL_* comment."""
    return jinja_round(max(avg_et0_mm_per_day, 0.0) * 7.0 * max(crop_coefficient, 0.0), 2)


@dataclass
class DeepSoakPlan:
    target_mm: float
    flow_rate: float
    total_runtime_minutes: int
    pulse_runtime_minutes: float
    pulse_count: int = 3


def split_pulses(total_minutes: int, pulse_count: int, min_pulse_minutes: float) -> tuple[int, float]:
    """Split a cycle's whole-minute runtime into (pulses, minutes per pulse)
    so the valve is open for exactly total_minutes -- the same number the
    log records -- instead of rounding each pulse to whole minutes (3 min
    over 2 pulses used to become 2 + 2 = 4 min). When the need is too small
    for every pulse to reach its minimum length, fewer pulses are used
    rather than running each one at the minimum (which used to deliver up
    to pulse_count times what was asked for). Only a need shorter than one
    minimum-length pulse still runs that one minimum pulse."""
    count = max(int(pulse_count), 1)
    if total_minutes <= 0:
        return count, 0.0
    if total_minutes < count * min_pulse_minutes:
        count = max(int(total_minutes // min_pulse_minutes), 1)
    return count, max(total_minutes / count, min_pulse_minutes)


def plan_deep_soak(
    target_mm: float, flow_rate: float, pulse_count: int = 3, min_pulse_minutes: int = 5
) -> DeepSoakPlan:
    """Port of the variables block in avocado_deep_soak.

    total_runtime = round(target_mm / flow_rate)   (whole minutes, as logged)
    pulses        = split_pulses(total_runtime, ...) (exact split, see above)

    pulse_count and min_pulse_minutes default to the original fixed values
    (3 pulses, 5-min floor) so an existing call site that doesn't pass them
    behaves exactly as before. A zone's actual pulse_count now comes from
    its own "Deep Soak Pulse Count (Split-Cycle)" number entity -- see
    ZoneFlowController.run_deep_soak -- chosen based on drainage (slow-
    draining soil generally wants more, shorter pulses)."""
    total_runtime = int(jinja_round(target_mm / flow_rate, 0))
    count, pulse_runtime = split_pulses(total_runtime, pulse_count, min_pulse_minutes)
    return DeepSoakPlan(target_mm, flow_rate, total_runtime, pulse_runtime, count)


@dataclass
class RoutinePlan:
    interval_days: int
    target_weekly_mm: float
    interval_target_mm: float
    eff_rain_mm: float
    needed_mm: float
    calc_runtime_minutes: int
    pulse_runtime_minutes: float
    pulse_count: int = 3


def routine_interval_days(avg_peak_temp: float | None, hot_threshold: float) -> int:
    """Port of `target_interval_days`: 3 if hot, else 4.

    avg_peak_temp is None when the zone's temperature sensor is either not
    configured or is currently unavailable/unknown -- see
    ZoneFlowController.effective_avg_peak_temp(). That is treated as an
    explicit "use the normal tier" branch, not a numeric coincidence, so a
    dead sensor can never silently freeze a zone on whatever tier its last
    real reading happened to imply."""
    if avg_peak_temp is None:
        return 4
    return 3 if avg_peak_temp >= hot_threshold else 4


def routine_target_weekly_mm(
    avg_peak_temp: float | None,
    hot_threshold: float,
    cool_threshold: float,
    normal_mm: float,
    hot_mm: float,
    cool_mm: float,
) -> float:
    """Port of `target_weekly_mm`. Hot is tested before cool so the two
    thresholds can never invert, exactly as the YAML comment states.

    See routine_interval_days for why avg_peak_temp being None explicitly
    means "normal tier", independent of where cool_threshold happens to sit."""
    if avg_peak_temp is None:
        return normal_mm
    if avg_peak_temp >= hot_threshold:
        return hot_mm
    if avg_peak_temp < cool_threshold:
        return cool_mm
    return normal_mm


def plan_routine_irrigation(
    *,
    avg_peak_temp: float | None,
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
    pulse_count: int = 3,
    min_pulse_minutes: int = 1,
    weekly_target_override_mm: float | None = None,
) -> RoutinePlan:
    """Port of the full variables block in avocado_routine_irrigation
    (interval_target_mm through pulse_runtime).

    pulse_count/min_pulse_minutes default to the original fixed values (3
    pulses, 1-min floor) for the same backward-compatibility reason as
    plan_deep_soak above -- a zone's real pulse_count comes from its
    "Routine Pulse Count (Split-Cycle)" number entity."""
    interval_days = routine_interval_days(avg_peak_temp, hot_threshold)
    # weekly_target_override_mm is the ET demand model's target (see
    # et_weekly_target_mm) when a zone uses it and ET0 is available; None
    # means the original temperature-tier target, exactly as before.
    if weekly_target_override_mm is not None:
        target_weekly_mm = weekly_target_override_mm
    else:
        target_weekly_mm = routine_target_weekly_mm(
            avg_peak_temp, hot_threshold, cool_threshold, normal_weekly_mm, hot_weekly_mm, cool_weekly_mm
        )
    interval_target_mm = (target_weekly_mm / 7.0) * interval_days
    eff_rain = rain_deduction_mm(
        today_rain_mm,
        rain_day_history_mm,
        days_elapsed,
        rain_eff_low,
        rain_eff_mid,
        rain_eff_high,
        max_lookback_days=interval_days,
    )
    needed_mm = max(interval_target_mm - eff_rain, 0.0)
    calc_runtime = int(jinja_round(needed_mm / flow_rate, 0))
    count, pulse_runtime = split_pulses(calc_runtime, pulse_count, min_pulse_minutes)
    return RoutinePlan(
        interval_days=interval_days,
        target_weekly_mm=target_weekly_mm,
        interval_target_mm=interval_target_mm,
        eff_rain_mm=eff_rain,
        needed_mm=needed_mm,
        calc_runtime_minutes=calc_runtime,
        pulse_runtime_minutes=pulse_runtime,
        pulse_count=count,
    )


def routine_due(elapsed_seconds: float, interval_days: int, buffer_seconds: int) -> bool:
    """Port of `elapsed_seconds >= target_interval_seconds`
    where target_interval_seconds = interval_days*86400 - buffer_seconds."""
    return elapsed_seconds >= (interval_days * 86400 - buffer_seconds)


def deep_soak_due(elapsed_seconds: float, interval_days: float, buffer_seconds: int) -> bool:
    """Port of the deep-soak interval-with-6h-buffer check. interval_days
    used to be a fixed 14 -- it's now the zone's own tunable
    "deep_soak_interval_days" number entity, hence the float type (a
    number entity always reports a float even when set to a whole number)."""
    return elapsed_seconds >= (interval_days * 86400 - buffer_seconds)


def drydown_satisfied(elapsed_seconds_since_rain: float, drydown_days: float) -> bool:
    """Port of the dry-down check shared by both deep soak and routine."""
    return elapsed_seconds_since_rain >= (drydown_days * 86400)


def routine_due_with_soil_moisture(
    interval_due: bool,
    moisture_pct: float | None,
    dry_pct: float,
    wet_pct: float,
) -> bool:
    """Whether routine irrigation is due, factoring in an optional soil-
    moisture reading on top of the plain time-interval estimate
    (`interval_due`, from routine_due() above) -- see
    ZoneFlowController.run_routine_irrigation and const.py's
    CONF_SOIL_MOISTURE_ENTITY comment.

    moisture_pct is None whenever no soil-moisture sensor is configured, or
    it's currently unavailable/unreadable -- in that case this is a pure
    passthrough of interval_due, i.e. behaves exactly as if the feature
    didn't exist.

    When a reading IS available, it becomes the direct decider at the
    extremes and the interval estimate only breaks the tie in the
    ambiguous middle band:
      - moisture >= wet_pct  -> definitely wet enough: skip, regardless of
        how overdue the time interval says this is.
      - moisture <= dry_pct  -> definitely dry: water now, even if the
        time interval hasn't technically elapsed yet.
      - dry_pct < moisture < wet_pct -> genuinely ambiguous: defer to
        interval_due, exactly as if there were no soil-moisture sensor.
    dry_pct and wet_pct are not required to be ordered relative to each
    other (same as the growth-ramp custom curve's points) -- if dry_pct
    ends up >= wet_pct, the "ambiguous middle band" is simply empty, which
    just means every reading resolves at one of the two extremes; it is
    not treated as a misconfiguration error."""
    if moisture_pct is None:
        return interval_due
    if moisture_pct >= wet_pct:
        return False
    if moisture_pct <= dry_pct:
        return True
    return interval_due


def adjust_drydown_days(current_days: float, step_days: float, min_days: float, max_days: float) -> float:
    """Nudge current_days by step_days (positive to extend, negative to
    shrink), clamped to [min_days, max_days] -- see
    ZoneFlowController._register_self_tune_signal and const.py's
    SELF_TUNE_* comment. The clamp is what keeps repeated self-tune nudges
    from ever pushing the value outside the same safe range a person could
    reach by hand on the number slider."""
    return max(min_days, min(max_days, current_days + step_days))


@dataclass
class NextIrrigationEstimate:
    routine_next_ts: float
    rain_next_ts: float
    next_ts: float


def estimate_next_irrigation(
    last_routine_ts: float,
    last_significant_rain_ts: float,
    avg_peak_temp: float | None,
    hot_threshold: float,
    routine_drydown_days: float,
) -> NextIrrigationEstimate:
    """Port of `sensor.avocado_next_irrigation_estimate`."""
    interval_days = routine_interval_days(avg_peak_temp, hot_threshold)
    routine_next = last_routine_ts + interval_days * 86400
    rain_next = last_significant_rain_ts + routine_drydown_days * 86400
    return NextIrrigationEstimate(routine_next, rain_next, max(routine_next, rain_next))


def estimate_next_deep_soak(
    last_deep_soak_ts: float | None,
    interval_days: float,
    last_significant_rain_ts: float | None,
    drydown_days: float,
    now_ts: float,
) -> float:
    """When the next deep soak is expected: the later of its interval and
    its subsoil drydown after significant rain. A zone that has never
    deep-soaked is due now. (Like the routine estimate, this models the
    time gates only, not the 14-day rain ceiling or the forecast.)"""
    interval_next = (last_deep_soak_ts + interval_days * 86400) if last_deep_soak_ts is not None else now_ts
    rain_next = (last_significant_rain_ts or 0.0) + drydown_days * 86400
    return max(interval_next, rain_next)


def growth_ramp_fraction(days_since_planting: float, curve: list[tuple[int, float]]) -> float:
    """Linear interpolation between a growth-curve profile's control points
    (see GROWTH_RAMP_CURVES in const.py). Clamped to the first point's
    fraction for a negative/zero days-since-planting (e.g. a planting date
    set in the future by mistake) and to the last point's fraction (1.0)
    beyond the curve's final point, rather than extrapolating past it.

    This is a calendar-day approximation of typical growth timing, not a
    growing-degree-day model -- a cooler or hotter season will genuinely
    make real growth lag behind or run ahead of this curve. It is meant as
    a reasonable default to ramp FROM, not a precise measurement, and the
    weekly-target number it scales stays fully overridable at any time
    regardless of what this returns."""
    if not curve:
        return 1.0
    if days_since_planting <= curve[0][0]:
        return curve[0][1]
    for (day_a, frac_a), (day_b, frac_b) in zip(curve, curve[1:], strict=False):
        if days_since_planting <= day_b:
            if day_b == day_a:
                return frac_b
            t = (days_since_planting - day_a) / (day_b - day_a)
            return frac_a + t * (frac_b - frac_a)
    return curve[-1][1]


def estimate_last_water_delivered_mm(
    avg_peak_temp: float,
    hot_threshold: float,
    cool_threshold: float,
    normal_weekly_mm: float,
    hot_weekly_mm: float,
    cool_weekly_mm: float,
    weekly_target_override_mm: float | None = None,
) -> float:
    """Port of `sensor.last_avocado_water_delivered` (per-session estimate,
    i.e. half the applicable weekly target). weekly_target_override_mm:
    same meaning as in plan_routine_irrigation."""
    if weekly_target_override_mm is not None:
        target = weekly_target_override_mm
    else:
        target = routine_target_weekly_mm(
            avg_peak_temp, hot_threshold, cool_threshold, normal_weekly_mm, hot_weekly_mm, cool_weekly_mm
        )
    return jinja_round(target / 2, 1)
