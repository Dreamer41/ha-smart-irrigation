"""Constants for the ZoneFlow integration.

Every default value in this file is copied verbatim from the Jinja
fallback (the `| float(x)` / `| int(x)`) baked into the confirmed-final
automations.yaml on 2026-09-14, and every min/max/step/unit is copied
from the matching input_number definition in configuration.yaml. If you
ever need to re-verify one of these against the live YAML, that is where
to look — do not "improve" a default without checking the source first.
"""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "zoneflow"
PLATFORMS = [Platform.NUMBER, Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]

STORAGE_VERSION = 1
STORAGE_KEY_SUFFIX = "state"

# ---------------------------------------------------------------------------
# Config entry keys (set once via the config flow, changeable via options)
# ---------------------------------------------------------------------------
CONF_ZONE_NAME = "zone_name"
CONF_VALVE_ENTITY = "valve_entity"
CONF_PUMP_POWER_ENTITY = "pump_power_entity"
CONF_RAIN_COUNTER_ENTITY = "rain_counter_entity"
CONF_OUTDOOR_TEMP_ENTITY = "outdoor_temp_entity"
CONF_NOTIFY_ENTITY = "notify_entity"  # phone notify.* entity, optional
CONF_WEATHER_ENTITY = "weather_entity"  # weather.* entity, optional -- enables the forecast gate
CONF_CSV_PATH = "csv_path"
CONF_DEEP_SOAK_TIME = "deep_soak_time"  # "HH:MM:SS", default matches live YAML
CONF_ROUTINE_TIME = "routine_time"

# Optional alternative to the fixed clock time above: fire relative to
# sunrise/sunset instead. Mode "fixed" (the default) means "ignore this and
# use the *_TIME field" -- so a zone that never touches these fields behaves
# exactly as before. See SUN_MODE_* below for the other values.
CONF_DEEP_SOAK_SUN_MODE = "deep_soak_sun_mode"
CONF_DEEP_SOAK_SUN_OFFSET_MINUTES = "deep_soak_sun_offset_minutes"
CONF_ROUTINE_SUN_MODE = "routine_sun_mode"
CONF_ROUTINE_SUN_OFFSET_MINUTES = "routine_sun_offset_minutes"

SUN_MODE_FIXED = "fixed"
SUN_MODE_BEFORE_SUNRISE = "before_sunrise"
SUN_MODE_AFTER_SUNRISE = "after_sunrise"
SUN_MODE_BEFORE_SUNSET = "before_sunset"
SUN_MODE_AFTER_SUNSET = "after_sunset"
SUN_MODE_OPTIONS = [
    SUN_MODE_FIXED,
    SUN_MODE_BEFORE_SUNRISE,
    SUN_MODE_AFTER_SUNRISE,
    SUN_MODE_BEFORE_SUNSET,
    SUN_MODE_AFTER_SUNSET,
]

DEFAULT_CSV_PATH = "/config/zoneflow_v2.csv"
DEFAULT_DEEP_SOAK_TIME = "05:00:00"
DEFAULT_ROUTINE_TIME = "05:30:00"
DEFAULT_SUN_MODE = SUN_MODE_FIXED
DEFAULT_SUN_OFFSET_MINUTES = 0
DAILY_SHIFT_TIME = "23:59:50"  # matches shift_avocado_daily_peak_temps / shift_avocado_daily_rain

# ---------------------------------------------------------------------------
# Fixed structural constants taken directly from the automation (not sliders)
# ---------------------------------------------------------------------------
DEEP_SOAK_INTERVAL_DAYS = 14
DEEP_SOAK_INTERVAL_BUFFER_SECONDS = 6 * 3600  # "14-day check with a 6-hour buffer"
DEEP_SOAK_PULSE_COUNT = 3
DEEP_SOAK_PULSE_REST_MINUTES = 20
DEEP_SOAK_MIN_PULSE_MINUTES = 5

ROUTINE_PULSE_COUNT = 3
ROUTINE_PULSE_REST_MINUTES = 20
ROUTINE_MIN_PULSE_MINUTES = 1
ROUTINE_INTERVAL_BUFFER_SECONDS = 6 * 3600  # (interval_days*86400) - 21600, same buffer
ROUTINE_HOT_INTERVAL_DAYS = 3
ROUTINE_NORMAL_INTERVAL_DAYS = 4
RAIN_HISTORY_DEPTH_DAYS = 10  # rain_day_1..10

PUMP_POWER_WAIT_TIMEOUT_SECONDS = 45  # wait_template timeout before "low pump power" audit

VALVE_STUCK_ON_MINUTES = 150
STALE_LOCK_MINUTES = 180
POWER_LOSS_GRACE_MINUTES = 10
STARTUP_GRACE_SECONDS = 120  # "delay: 00:02:00" before checking stale lock on startup

# Significant-rain thresholds (avocado_significant_rain_logger)
SIGNIFICANT_RAIN_24H_MM = 35.0
SIGNIFICANT_RAIN_4D_MM = 50.0
SIGNIFICANT_RAIN_7D_MM = 100.0

PEAK_TEMP_VALID_MIN_C = 15.0
PEAK_TEMP_VALID_MAX_C = 50.0
PEAK_TEMP_FALLBACK_C = 30.0  # used when all 3 days are corrupt/missing

# NOTE: the rolling rain-window definitions (RAIN_WINDOWS_MINUTES) and the
# sample-retention window live in rain_tracker.py, not here, so that module
# has zero dependency on Home Assistant and can be unit-tested standalone.

# ---------------------------------------------------------------------------
# Tunable numbers. key -> (name, min, max, step, unit, default)
# Order matches the "AVOCADO IRRIGATION SLIDERS" block in configuration.yaml.
# ---------------------------------------------------------------------------
NUMBER_DEFS: dict[str, tuple[str, float, float, float, str | None]] = {
    "target_weekly_mm": ("Routine Normal Weekly Target", 10.0, 60.0, 0.5, "mm"),
    "target_weekly_hot_mm": ("Routine Hot Weekly Target", 15.0, 75.0, 0.5, "mm"),
    "hot_temp_threshold": ("Hot Weather Temp Threshold", 28.0, 38.0, 0.5, "°C"),
    "cool_temp_threshold": ("Cool Weather Temp Threshold", 20.0, 33.0, 0.5, "°C"),
    "target_weekly_cool_mm": ("Routine Cool Weekly Target", 5.0, 40.0, 0.5, "mm"),
    "rain_eff_low": ("Rain Efficiency - Light (3-5mm)", 0.0, 1.0, 0.05, None),
    "rain_eff_mid": ("Rain Efficiency - Moderate (5-10mm)", 0.0, 1.0, 0.05, None),
    "rain_eff_high": ("Rain Efficiency - Heavy (10-20mm+)", 0.0, 1.0, 0.05, None),
    "flow_rate_mm_per_min": ("Emitter Flow Rate Calibration", 0.05, 2.0, 0.01, "mm/min"),
    "deep_soak_target_mm": ("Deep Soak Target Depth", 15.0, 40.0, 1.0, "mm"),
    "pump_min_watts": ("Pump Low-Power Warning Threshold", 20.0, 500.0, 10.0, "W"),
    "deep_soak_max_runtime_minutes": ("Deep Soak Max Safety Runtime Cap", 30.0, 220.0, 10.0, "min"),
    "max_runtime_minutes": ("Routine Max Safety Runtime Cap", 10.0, 150.0, 5.0, "min"),
    "routine_drydown_days": ("Routine Dry-Down Holdoff", 1.0, 10.0, 0.5, "d"),
    "deep_soak_drydown_days": ("Deep Soak Subsoil Dry-Down Holdoff", 4.0, 14.0, 0.5, "d"),
    "deep_soak_rain_threshold": ("Deep Soak Rain Ceiling (14d)", 0.0, 100.0, 5.0, "mm"),
    "rain_mm_per_tip": ("Rain Gauge mm per Tip (Calibration)", 0.05, 1.0, 0.001, "mm"),
    "preirrigation_rain_threshold_mm": ("Pre-Irrigation Cancel Threshold (30min)", 0.5, 20.0, 0.5, "mm"),
    # Only matter when another zone shares this zone's pump-power entity --
    # see ZoneFlowController._get_pump_lock. Default 0 on both means no
    # behavior change for a single-zone/independent-pump setup.
    "pump_preamble_seconds": ("Pump Preamble (Warm-Up Delay)", 0.0, 60.0, 1.0, "s"),
    "pump_postamble_seconds": ("Pump Postamble (Settle Delay)", 0.0, 60.0, 1.0, "s"),
    # Only apply when a weather entity is configured for this zone -- see
    # ZoneFlowController._forecast_gate_allows_run. Skip is preemptive
    # (rain forecast -> hold off, check again next scheduled run); the dry
    # override days number is per-zone/per-crop precisely because different
    # plants tolerate a missed watering very differently.
    "forecast_rain_threshold_mm": ("Forecast Rain Skip Threshold", 0.5, 20.0, 0.5, "mm"),
    "forecast_probability_threshold_pct": ("Forecast Rain Probability Threshold", 0.0, 100.0, 5.0, "%"),
    "forecast_dry_override_days": ("Forecast Dry-Spell Override", 1.0, 10.0, 1.0, "d"),
}

NUMBER_DEFAULTS: dict[str, float] = {
    "target_weekly_mm": 35.0,
    "target_weekly_hot_mm": 45.0,
    "hot_temp_threshold": 31.5,
    "cool_temp_threshold": 30.0,
    "target_weekly_cool_mm": 25.0,
    "rain_eff_low": 0.2,
    "rain_eff_mid": 0.6,
    "rain_eff_high": 1.0,
    "flow_rate_mm_per_min": 0.24,
    "deep_soak_target_mm": 25.0,
    "pump_min_watts": 100.0,
    "deep_soak_max_runtime_minutes": 124.0,
    "max_runtime_minutes": 103.0,
    "routine_drydown_days": 4.0,
    "deep_soak_drydown_days": 8.0,
    "deep_soak_rain_threshold": 40.0,
    "rain_mm_per_tip": 0.3,
    "preirrigation_rain_threshold_mm": 3.0,
    "pump_preamble_seconds": 0.0,
    "pump_postamble_seconds": 0.0,
    "forecast_rain_threshold_mm": 3.0,
    "forecast_probability_threshold_pct": 60.0,
    "forecast_dry_override_days": 2.0,
}

EVENT_LOG = f"{DOMAIN}_log_event"
