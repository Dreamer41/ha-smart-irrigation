"""Core calculations for Avocado Irrigation.

This module intentionally contains pure calculation helpers first.  The existing
Home Assistant YAML is the reference implementation; keeping the math isolated
makes it possible to compare the integration against the working automation
before valve control is introduced.
"""

from __future__ import annotations

from dataclasses import dataclass

from .const import (
    DEFAULT_DEEP_SOAK_MAX_RUNTIME_MIN,
    DEFAULT_DEEP_SOAK_TARGET_MM,
    DEFAULT_FLOW_RATE_MM_PER_MIN,
    DEFAULT_MAX_RUNTIME_MIN,
    DEFAULT_RAIN_EFFICIENCY,
    DEFAULT_WEEKLY_TARGET_MM,
    DEFAULT_HOT_TEMPERATURE_C,
    ROUTINE_INTERVAL_COOL_DAYS,
    ROUTINE_INTERVAL_HOT_DAYS,
)


@dataclass(frozen=True, slots=True)
class RoutineCalculation:
    """Result of the routine irrigation calculation."""

    target_interval_days: int
    interval_target_mm: float
    effective_rain_mm: float
    needed_mm: float
    runtime_minutes: int
    capped: bool


@dataclass(frozen=True, slots=True)
class DeepSoakCalculation:
    """Result of the deep-soak runtime calculation."""

    target_mm: float
    flow_rate_mm_per_min: float
    total_runtime_minutes: int
    pulse_runtime_minutes: int
    capped: bool


def routine_interval_days(
    average_peak_temperature_c: float,
    hot_temperature_c: float = DEFAULT_HOT_TEMPERATURE_C,
) -> int:
    """Return the 3-day hot or 4-day normal routine interval."""
    return (
        ROUTINE_INTERVAL_HOT_DAYS
        if average_peak_temperature_c >= hot_temperature_c
        else ROUTINE_INTERVAL_COOL_DAYS
    )


def calculate_routine(
    *,
    average_peak_temperature_c: float,
    rain_past_4d_mm: float,
    weekly_target_mm: float = DEFAULT_WEEKLY_TARGET_MM,
    rain_efficiency: float = DEFAULT_RAIN_EFFICIENCY,
    flow_rate_mm_per_min: float = DEFAULT_FLOW_RATE_MM_PER_MIN,
    max_runtime_minutes: int = DEFAULT_MAX_RUNTIME_MIN,
    hot_temperature_c: float = DEFAULT_HOT_TEMPERATURE_C,
) -> RoutineCalculation:
    """Calculate routine irrigation using the reference YAML formula.

    Weekly target is scaled to the actual 3- or 4-day application interval:
        interval target = (weekly target / 7) * interval days

    Effective rain is the matching four-day rainfall multiplied by the configured
    absorption efficiency.  The result is never allowed to go below zero.
    """
    interval_days = routine_interval_days(
        average_peak_temperature_c, hot_temperature_c
    )
    interval_target = (weekly_target_mm / 7.0) * interval_days
    effective_rain = max(rain_past_4d_mm, 0.0) * max(rain_efficiency, 0.0)
    needed = max(interval_target - effective_rain, 0.0)

    if flow_rate_mm_per_min <= 0:
        runtime = 0
    else:
        runtime = int(round(needed / flow_rate_mm_per_min))

    capped = runtime > max_runtime_minutes

    return RoutineCalculation(
        target_interval_days=interval_days,
        interval_target_mm=interval_target,
        effective_rain_mm=effective_rain,
        needed_mm=needed,
        runtime_minutes=runtime,
        capped=capped,
    )


def calculate_deep_soak(
    *,
    target_mm: float = DEFAULT_DEEP_SOAK_TARGET_MM,
    flow_rate_mm_per_min: float = DEFAULT_FLOW_RATE_MM_PER_MIN,
    max_runtime_minutes: int = DEFAULT_DEEP_SOAK_MAX_RUNTIME_MIN,
) -> DeepSoakCalculation:
    """Calculate total and three-pulse deep-soak runtime."""
    if flow_rate_mm_per_min <= 0:
        total_runtime = 0
    else:
        total_runtime = int(round(max(target_mm, 0.0) / flow_rate_mm_per_min))

    pulse_runtime = max(int(round(total_runtime / 3)), 5)

    return DeepSoakCalculation(
        target_mm=max(target_mm, 0.0),
        flow_rate_mm_per_min=max(flow_rate_mm_per_min, 0.0),
        total_runtime_minutes=total_runtime,
        pulse_runtime_minutes=pulse_runtime,
        capped=total_runtime > max_runtime_minutes,
    )


def significant_rain(
    *,
    rain_24h_mm: float,
    rain_4d_mm: float,
    rain_7d_mm: float,
) -> bool:
    """Return whether any reference significant-rain threshold is met."""
    return (
        rain_24h_mm >= 35.0
        or rain_4d_mm >= 50.0
        or rain_7d_mm >= 100.0
    )
