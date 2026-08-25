"""Tests for the Avocado Irrigation calculation engine."""

from custom_components.avocado_irrigation.coordinator import (
    calculate_deep_soak,
    calculate_routine,
    significant_rain,
)


def test_routine_normal_4_day_interval() -> None:
    result = calculate_routine(
        average_peak_temperature_c=30.0,
        rain_past_4d_mm=0.0,
    )

    assert result.target_interval_days == 4
    assert result.interval_target_mm == 12.0 / 7.0 * 4
    assert result.needed_mm == result.interval_target_mm
    assert result.runtime_minutes == round(result.needed_mm / 0.30)


def test_routine_hot_3_day_interval() -> None:
    result = calculate_routine(
        average_peak_temperature_c=31.5,
        rain_past_4d_mm=0.0,
    )

    assert result.target_interval_days == 3
    assert result.interval_target_mm == 12.0 / 7.0 * 3


def test_rain_reduces_irrigation_need() -> None:
    result = calculate_routine(
        average_peak_temperature_c=30.0,
        rain_past_4d_mm=4.0,
        rain_efficiency=0.75,
    )

    expected = max((12.0 / 7.0 * 4) - 3.0, 0.0)
    assert result.effective_rain_mm == 3.0
    assert result.needed_mm == expected


def test_runtime_cap_is_reported() -> None:
    result = calculate_routine(
        average_peak_temperature_c=30.0,
        rain_past_4d_mm=0.0,
        flow_rate_mm_per_min=0.05,
        max_runtime_minutes=10,
    )

    assert result.capped is True


def test_deep_soak_three_pulses() -> None:
    result = calculate_deep_soak(
        target_mm=25.0,
        flow_rate_mm_per_min=0.30,
    )

    assert result.total_runtime_minutes == round(25.0 / 0.30)
    assert result.pulse_runtime_minutes == max(round(result.total_runtime_minutes / 3), 5)
    assert result.capped is False


def test_significant_rain_thresholds() -> None:
    assert significant_rain(rain_24h_mm=35.0, rain_4d_mm=0, rain_7d_mm=0)
    assert significant_rain(rain_24h_mm=0, rain_4d_mm=50.0, rain_7d_mm=0)
    assert significant_rain(rain_24h_mm=0, rain_4d_mm=0, rain_7d_mm=100.0)
    assert not significant_rain(rain_24h_mm=34.9, rain_4d_mm=49.9, rain_7d_mm=99.9)
