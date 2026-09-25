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
PLATFORMS = [
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DATETIME,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.TEXT,
]

STORAGE_VERSION = 1
STORAGE_KEY_SUFFIX = "state"

# ---------------------------------------------------------------------------
# Config entry keys (set once via the config flow, changeable via options)
# ---------------------------------------------------------------------------
CONF_ZONE_NAME = "zone_name"
CONF_VALVE_ENTITY = "valve_entity"  # the only entity that is truly mandatory -- everything else below degrades gracefully when unset
CONF_PUMP_POWER_ENTITY = "pump_power_entity"  # optional -- backs the pump-audit watchdog
# Optional, arbitrary string the person picks (e.g. "Pump A") to explicitly
# say which *physical* pump this zone's valve draws from -- decoupled from
# CONF_PUMP_POWER_ENTITY on purpose. The shared-pump lock (controller.py's
# _get_pump_lock) used to be keyed off pump_power_entity alone, which meant
# two zones that genuinely share a pump but don't have a wattage sensor on
# it (or only one of them does) could never be detected as sharing one --
# and, worse, any two zones that both simply have no pump-power sensor
# configured would collide onto the same lock key (None) and be wrongly
# serialized even on completely independent pumps. Setting the same pump_id
# string on every zone that shares a physical pump fixes both: it works
# with or without a wattage sensor, and leaving it blank never accidentally
# groups unrelated zones together (see the lock-key fallback order in
# ZoneFlowController._pump_lock_key).
CONF_PUMP_ID = "pump_id"
CONF_RAIN_COUNTER_ENTITY = "rain_counter_entity"  # optional -- rain-aware gates simply never fire without it
CONF_OUTDOOR_TEMP_ENTITY = "outdoor_temp_entity"  # optional -- hot/cool tiers fall back to "normal" without it
CONF_FLOW_METER_ENTITY = "flow_meter_entity"  # optional -- cumulative-volume sensor, e.g. a pulse flow meter
# Optional -- a % soil-moisture sensor. When configured AND currently
# readable, it becomes the direct decider of whether routine irrigation is
# due (see ZoneFlowController._soil_moisture_pct and run_routine_irrigation's
# dry/wet threshold gate below), instead of only the time-interval-since-
# last-watering estimate. Deliberately routine-only, not deep soak -- a
# shallow surface probe measures near-surface moisture, not the deeper
# root-zone dryness deep soak targets, which is already handled by the
# separate "Deep Soak Subsoil Dry-Down Holdoff" number. Unconfigured or
# currently unavailable/unknown both mean the same thing: fall back to the
# existing modeled schedule exactly as if this feature didn't exist.
CONF_SOIL_MOISTURE_ENTITY = "soil_moisture_entity"
CONF_NOTIFY_ENTITY = "notify_entity"  # phone notify.* entity, optional
CONF_WEATHER_ENTITY = "weather_entity"  # weather.* entity, optional -- enables the forecast gate
CONF_CSV_PATH = "csv_path"
CONF_UNIT_SYSTEM = "unit_system"  # "auto" (follow Home Assistant) / "metric" / "imperial" -- display only, see units.py
# Off-switch for the whole deep-soak cycle -- some plants/setups (shallow-
# rooted crops, containers, frequent-drip greenhouse zones) genuinely don't
# benefit from an infrequent deep soak on top of routine irrigation. Default
# is True (not False like growth-ramp) because, unlike growth-ramp, deep
# soak is not a new capability -- every zone created before this field
# existed already ran it, so True is the only default that doesn't silently
# change an existing installation's behavior. The AI setup guide is what
# actually decides per zone/crop whether to recommend turning this off, not
# this default.
CONF_DEEP_SOAK_ENABLED = "deep_soak_enabled"
DEFAULT_DEEP_SOAK_ENABLED = True
CONF_DEEP_SOAK_TIME = "deep_soak_time"  # "HH:MM:SS", default matches live YAML -- irrelevant while deep_soak_enabled is False
CONF_ROUTINE_TIME = "routine_time"

# Descriptive soil/site metadata -- informational context an AI or person
# uses to pick sensible split-cycle NUMBER_DEFS values below (pulse count,
# soak interval, rain-efficiency, dry-down holdoffs). None of it is read by
# the scheduler's own decision logic directly -- the physical parameters
# it should inform are always the real adjustable number entities, never a
# hidden lookup keyed off these strings, so a person who disagrees with the
# category can always just move the numbers themselves.
CONF_SOIL_TYPE = "soil_type"
CONF_DRAINAGE = "drainage"
CONF_SLOPE = "slope"
CONF_IRRIGATION_METHOD = "irrigation_method"

SOIL_TYPE_OPTIONS = ["unknown", "sandy", "sandy_loam", "loam", "clay_loam", "clay"]
DRAINAGE_OPTIONS = ["unknown", "fast", "medium", "slow"]
SLOPE_OPTIONS = ["flat", "slight", "moderate", "steep"]
IRRIGATION_METHOD_OPTIONS = ["drip", "micro_sprinkler", "sprinkler", "soaker_hose", "other"]
DEFAULT_SOIL_TYPE = "unknown"
DEFAULT_DRAINAGE = "unknown"
DEFAULT_SLOPE = "flat"
DEFAULT_IRRIGATION_METHOD = "drip"

# A pure human journal entity (select.py's ZoneFlowHealthSelect + text.py's
# ZoneFlowHealthNotesText) -- nothing in the controller reads either value,
# they exist purely so a person (or anyone else who tends the zone) has
# somewhere to record how the plant is actually doing over time, without
# that ever silently changing what/when ZoneFlow waters.
HEALTH_STATUS_OPTIONS = ["excellent", "good", "poor", "sick"]
DEFAULT_HEALTH_STATUS = "good"

# Fertilizing journal (datetime.py's "Last Fertilizing" + select.py's
# ZoneFlowFertilizingIntervalSelect) -- same pure-journal rule as the health
# fields above: nothing in the controller reads either value, so recording
# a feed never changes what/when ZoneFlow waters. Options are whole months,
# stored as strings because a select entity's options are strings.
FERTILIZING_INTERVAL_OPTIONS = [str(m) for m in range(1, 13)]
DEFAULT_FERTILIZING_INTERVAL = "3"

# Routine weekly-target model (select.py's ZoneFlowDemandModelSelect).
# "temperature_tiers" is the original hot/normal/cool slider system and the
# default, so upgrading never changes how an existing zone waters.
# "et_curve" replaces the tier target with a continuous one:
#     weekly target = 3-day avg Hargreaves ET0 x 7 x crop factor (Kc)
# Only the weekly TARGET changes -- the 3/4-day interval still follows the
# hot threshold, and rain credit, growth ramp, runtime caps etc. all apply
# exactly as before. Whenever ET0 can't be computed (no full day of
# min/max recorded yet, or the temperature sensor is currently
# unavailable) the zone falls back to the tier target for that cycle.
DEMAND_MODEL_TIERS = "temperature_tiers"
DEMAND_MODEL_ET = "et_curve"
DEMAND_MODEL_OPTIONS = [DEMAND_MODEL_TIERS, DEMAND_MODEL_ET]
DEFAULT_DEMAND_MODEL = DEMAND_MODEL_TIERS

# Growth-stage auto-ramp (optional, off by default -- see controller.py's
# growth_ramp_fraction()). "off" means the weekly-target math behaves
# exactly as it always has; any other profile scales the weekly target by
# a days-since-planting curve intended as a reasonable starting
# approximation from typical growth timing, not a precise measurement.
CONF_GROWTH_RAMP_PROFILE = "growth_ramp_profile"
CONF_PLANTING_DATE_ENTITY_ID = "planting_date_entity_id"  # informational only; the real datetime entity is platform-created
GROWTH_RAMP_OFF = "off"
GROWTH_RAMP_FAST_ANNUAL = "fast_annual"
GROWTH_RAMP_SLOW_FRUITING = "slow_fruiting"
GROWTH_RAMP_ESTABLISHED_PERENNIAL = "established_perennial"
# A person's own curve, built from the "growth_ramp_custom_*" NUMBER_DEFS
# sliders below rather than a fixed GROWTH_RAMP_CURVES entry -- see
# ZoneFlowController.growth_ramp_fraction. Lets two zones on genuinely
# different plants (e.g. a chili pepper vs. a young avocado tree) each get
# their own real curve instead of picking whichever of the three fixed
# presets happens to fit best.
GROWTH_RAMP_CUSTOM = "custom"
GROWTH_RAMP_PROFILE_OPTIONS = [
    GROWTH_RAMP_OFF,
    GROWTH_RAMP_FAST_ANNUAL,
    GROWTH_RAMP_SLOW_FRUITING,
    GROWTH_RAMP_ESTABLISHED_PERENNIAL,
    GROWTH_RAMP_CUSTOM,
]
DEFAULT_GROWTH_RAMP_PROFILE = GROWTH_RAMP_OFF

# (days_since_planting_upper_bound, ramp_fraction) control points per
# profile, linearly interpolated between points and clamped to 1.0 beyond
# the last point. These are calendar-day approximations of typical growth
# timing, not growing-degree-day accuracy -- a cool or hot season will
# genuinely run ahead of or behind the real plant. Deliberately
# conservative early (never below 0.4) so a young planting is never
# starved outright while ramping up.
GROWTH_RAMP_CURVES: dict[str, list[tuple[int, float]]] = {
    GROWTH_RAMP_FAST_ANNUAL: [(0, 0.4), (14, 0.6), (30, 0.85), (45, 1.0)],
    GROWTH_RAMP_SLOW_FRUITING: [(0, 0.4), (21, 0.55), (45, 0.75), (70, 0.9), (100, 1.0)],
    GROWTH_RAMP_ESTABLISHED_PERENNIAL: [(0, 0.5), (30, 0.7), (60, 0.85), (90, 1.0)],
}

# ---------------------------------------------------------------------------
# Manual growth-stage override -- lets a person directly say "what stage is
# this plant at" instead of waiting on the planting-date curve above. Purely
# a dashboard convenience layered on top of growth_ramp_fraction(): it never
# takes effect when the zone's growth-ramp profile is "off" (see
# ZoneFlowController.growth_ramp_fraction -- off always means "no
# adjustment, ever," override or not), and it is entirely separate from the
# planting date itself, which keeps recording real elapsed time underneath
# regardless of whether the override is active.
#
# GROWTH_STAGE_MODE_AUTO is the only default -- an existing zone (or a
# freshly created one) always starts on the computed curve; "manual" is
# something a person opts into explicitly via the select entity below.
GROWTH_STAGE_MODE_AUTO = "auto"
GROWTH_STAGE_MODE_MANUAL = "manual"

# Named presets are just a shortcut that jumps the paired
# "growth_stage_override_pct" number (slider) to a representative value and
# switches the mode to manual in one step -- the same generic labels apply
# regardless of which curve (fast_annual/slow_fruiting/established_perennial)
# the zone is otherwise using, since they're a rough "how far along is it"
# stand-in, not a per-curve exact match.
GROWTH_STAGE_PRESETS: dict[str, float] = {
    "seedling": 40.0,
    "establishing": 55.0,
    "vegetative": 75.0,
    "near_fruiting": 90.0,
    "mature": 100.0,
}
GROWTH_STAGE_SELECT_OPTIONS = [
    GROWTH_STAGE_MODE_AUTO,
    *GROWTH_STAGE_PRESETS,
    GROWTH_STAGE_MODE_MANUAL,
]

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
# Deep-soak interval used to be fixed here at 14 -- it's now the
# "deep_soak_interval_days" NUMBER_DEFS entry below, adjustable per zone
# (see calc.deep_soak_due). Only the buffer stays a fixed constant.
DEEP_SOAK_INTERVAL_BUFFER_SECONDS = 6 * 3600  # "14-day check with a 6-hour buffer"
# Pulse COUNT and REST MINUTES used to be fixed here (3 / 20 for both
# cycles) -- they are now the "..._pulse_count" / "..._pulse_rest_minutes"
# NUMBER_DEFS below, adjustable per zone based on soil drainage. Only the
# per-pulse MINIMUM floor stays a fixed constant (matches the original
# automation's floor exactly; there's no agronomic reason to make an
# absolute minimum pulse length itself configurable).
DEEP_SOAK_MIN_PULSE_MINUTES = 5
ROUTINE_MIN_PULSE_MINUTES = 1
ROUTINE_INTERVAL_BUFFER_SECONDS = 6 * 3600  # (interval_days*86400) - 21600, same buffer
ROUTINE_HOT_INTERVAL_DAYS = 3
ROUTINE_NORMAL_INTERVAL_DAYS = 4
RAIN_HISTORY_DEPTH_DAYS = 10  # rain_day_1..10

PUMP_POWER_WAIT_TIMEOUT_SECONDS = 45  # wait_template timeout before "low pump power" audit

VALVE_STUCK_ON_MINUTES = 150
# While ZoneFlow itself has the valve open for a planned pulse longer than
# VALVE_STUCK_ON_MINUTES (a slow drip with few pulses can legitimately need
# that), the stuck-valve limit becomes that pulse plus this margin instead,
# so the watchdog still catches a valve that fails to close but never kills
# a cycle that is simply doing what it was asked to.
VALVE_STUCK_MARGIN_MINUTES = 30
STALE_LOCK_MINUTES = 180
POWER_LOSS_GRACE_MINUTES = 10
STARTUP_GRACE_SECONDS = 120  # "delay: 00:02:00" before checking stale lock on startup

# Self-tuning intervals (ZoneFlowController._register_self_tune_signal):
# a rolling streak of manual "Run Routine Now" presses made BEFORE the
# modeled schedule says routine irrigation is due nudges
# "routine_drydown_days" shorter (the person keeps deciding the plant
# needs water sooner than the model thinks); a rolling streak of "Snooze
# Today" presses nudges it longer (the person keeps deciding it doesn't).
# Either streak resets the other -- a mixed pattern never quietly
# accumulates toward a threshold on either side. These are algorithm
# parameters, not a per-crop physical quantity, so they're fixed constants
# rather than a tunable number entity (same category as VALVE_STUCK_ON_MINUTES
# above), while the number they actually adjust (routine_drydown_days)
# stays exactly as adjustable as it always was -- a self-tune nudge is
# indistinguishable from a person moving that slider themselves, and
# either can override the other at any time.
SELF_TUNE_STREAK_THRESHOLD = 3
SELF_TUNE_ADJUST_STEP_DAYS = 0.5  # matches routine_drydown_days' own NUMBER_DEFS step

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
    # Upper bound covers the worst case a slow drip emitter can legitimately
    # need: at the lowest configurable flow_rate_mm_per_min (0.05) and the
    # highest configurable target (deep_soak_target_mm 40 / weekly targets
    # up to 75), the calculated runtime can approach ~800-860 minutes. The
    # cap exists to catch a genuinely wrong calibration/config, not to
    # arbitrarily block a real slow-drip system -- raise it here, not by
    # disabling the cap.
    "deep_soak_max_runtime_minutes": ("Deep Soak Max Safety Runtime Cap", 30.0, 900.0, 10.0, "min"),
    "max_runtime_minutes": ("Routine Max Safety Runtime Cap", 10.0, 900.0, 5.0, "min"),
    "routine_drydown_days": ("Routine Dry-Down Holdoff", 1.0, 10.0, 0.5, "d"),
    "deep_soak_drydown_days": ("Deep Soak Subsoil Dry-Down Holdoff", 4.0, 14.0, 0.5, "d"),
    "deep_soak_interval_days": ("Deep Soak Interval", 3.0, 30.0, 1.0, "d"),
    # NOTE: the rain-ceiling check just below still looks at the fixed
    # rolling "14d" rain_windows() bucket (a standard reporting window
    # shared with the dashboard diagnostics), independent of whatever this
    # zone's deep_soak_interval_days is now set to -- they only happened to
    # share the number 14 back when the interval itself was hardcoded.
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
    # Only apply when a soil-moisture entity is configured for this zone --
    # see const.py's CONF_SOIL_MOISTURE_ENTITY comment and
    # ZoneFlowController.run_routine_irrigation's threshold gate. Not
    # ordering-enforced against each other (same as the growth-ramp custom
    # curve's points) -- a dry_pct set above wet_pct just means the
    # "ambiguous middle band that defers to the modeled schedule" never
    # occurs, which is harmless, not broken.
    "soil_moisture_dry_pct": ("Soil Moisture Dry Threshold", 0.0, 100.0, 1.0, "%"),
    "soil_moisture_wet_pct": ("Soil Moisture Wet Threshold", 0.0, 100.0, 1.0, "%"),
    # Deficit mode (regulated deficit irrigation): share of the normal
    # routine dose while it's on -- see calculations.deficit_factor.
    "deficit_water_pct": ("Deficit Mode Water", 50.0, 100.0, 5.0, "%"),
    # Split-cycle watering: how many on/soak/on pulses a cycle is broken
    # into, and how long the soak gap between pulses is. Slow-draining
    # soil (clay) generally wants MORE pulses and a LONGER soak so water
    # doesn't pool/run off; fast-draining soil (sand) can often use fewer,
    # shorter-soak pulses since infiltration isn't the bottleneck. These
    # replace what used to be fixed constants (3 pulses / 20min rest,
    # identical for every zone regardless of soil) -- see const.py history
    # for the previous DEEP_SOAK_PULSE_COUNT / ROUTINE_PULSE_COUNT etc.
    # Defaults below are exactly those previous fixed values, so an
    # existing installation's behavior does not change on upgrade.
    "routine_pulse_count": ("Routine Pulse Count (Split-Cycle)", 1.0, 8.0, 1.0, None),
    "routine_pulse_rest_minutes": ("Routine Soak Interval Between Pulses", 0.0, 120.0, 5.0, "min"),
    "deep_soak_pulse_count": ("Deep Soak Pulse Count (Split-Cycle)", 1.0, 8.0, 1.0, None),
    "deep_soak_pulse_rest_minutes": ("Deep Soak Soak Interval Between Pulses", 0.0, 120.0, 5.0, "min"),
    # A hard ceiling on total irrigation runtime across BOTH cycles in a
    # rolling day, independent of the per-cycle safety caps above -- those
    # catch one miscalculated cycle, this catches the case where several
    # legitimately-sized cycles would still add up to more water than is
    # reasonable to apply in a single day (e.g. a mis-set schedule firing
    # more often than intended). Generous default so it doesn't interfere
    # with normal use; it exists to catch a real runaway, not to micromanage.
    "max_daily_runtime_minutes": ("Max Daily Irrigation Runtime (Safety Cap)", 10.0, 1440.0, 10.0, "min"),
    # The manual growth-stage override slider (see GROWTH_STAGE_MODE_* above).
    # Only read by growth_ramp_fraction() while the paired select entity is
    # not set to "auto" -- otherwise this value just sits here unused, so
    # leaving it at its default is always harmless.
    "growth_stage_override_pct": ("Growth Stage Manual Override", 0.0, 100.0, 1.0, "%"),
    # A person's own growth-ramp curve -- only read when this zone's
    # growth_ramp_profile is "custom" (see GROWTH_RAMP_CUSTOM above and
    # ZoneFlowController.growth_ramp_fraction). Shape mirrors the built-in
    # curves: a day-0 floor, two adjustable midpoints, and a day at which
    # the ramp reaches 100% (clamped there and beyond, same as the fixed
    # curves). The two "day" sliders aren't ordering-enforced against each
    # other or against the full-ramp day here -- growth_ramp_fraction sorts
    # them before building the curve, so entering them out of order just
    # reorders the points rather than producing a broken/backwards ramp.
    "growth_ramp_custom_start_pct": ("Custom Ramp: Day 0 Starting %", 0.0, 100.0, 1.0, "%"),
    "growth_ramp_custom_point1_day": ("Custom Ramp: Midpoint 1 Day", 0.0, 365.0, 1.0, "d"),
    "growth_ramp_custom_point1_pct": ("Custom Ramp: Midpoint 1 %", 0.0, 100.0, 1.0, "%"),
    "growth_ramp_custom_point2_day": ("Custom Ramp: Midpoint 2 Day", 0.0, 365.0, 1.0, "d"),
    "growth_ramp_custom_point2_pct": ("Custom Ramp: Midpoint 2 %", 0.0, 100.0, 1.0, "%"),
    "growth_ramp_custom_full_day": ("Custom Ramp: Day Reaching 100%", 0.0, 365.0, 1.0, "d"),
    # ET demand model's crop factor (Kc): how much water this zone's plant
    # uses relative to the Hargreaves reference ET0 (a reference grass
    # surface). Only read while the zone's "Water Demand Model" select is
    # set to the ET curve -- see DEMAND_MODEL_* below.
    "crop_coefficient": ("Crop Factor (Kc)", 0.1, 1.5, 0.05, None),
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
    "deep_soak_interval_days": 14.0,
    "deep_soak_rain_threshold": 40.0,
    "rain_mm_per_tip": 0.3,
    "preirrigation_rain_threshold_mm": 3.0,
    "pump_preamble_seconds": 0.0,
    "pump_postamble_seconds": 0.0,
    "forecast_rain_threshold_mm": 3.0,
    "forecast_probability_threshold_pct": 60.0,
    "forecast_dry_override_days": 2.0,
    "soil_moisture_dry_pct": 20.0,
    "soil_moisture_wet_pct": 60.0,
    "deficit_water_pct": 70.0,
    "routine_pulse_count": 3.0,
    "routine_pulse_rest_minutes": 20.0,
    "deep_soak_pulse_count": 3.0,
    "deep_soak_pulse_rest_minutes": 20.0,
    "max_daily_runtime_minutes": 240.0,
    "growth_stage_override_pct": 40.0,
    # Defaults trace out a reasonable generic curve on their own (40% -> 60%
    # by day 15 -> 85% by day 35 -> 100% by day 60) so a zone freshly
    # switched to "custom" doesn't start from a degenerate flat line before
    # anyone has touched these sliders.
    "growth_ramp_custom_start_pct": 40.0,
    "growth_ramp_custom_point1_day": 15.0,
    "growth_ramp_custom_point1_pct": 60.0,
    "growth_ramp_custom_point2_day": 35.0,
    "growth_ramp_custom_point2_pct": 85.0,
    "growth_ramp_custom_full_day": 60.0,
    # Middle of the usual 0.6-1.0 range for established trees and most
    # fruiting crops; set per zone (AI_SETUP.md has per-crop guidance).
    "crop_coefficient": 0.8,
}

EVENT_LOG = f"{DOMAIN}_log_event"

# A reload or shutdown waits this long for a running cycle to close its valve
# and wind down before cancelling it (it closes the valve on the way out).
CYCLE_STOP_TIMEOUT_SECONDS = 30
# How long to wait for a valve told to close to report "off".
VALVE_CLOSE_CONFIRM_SECONDS = 10
# Home Assistant gives shutdown jobs 20 s in all; stay well inside it.
SHUTDOWN_STOP_TIMEOUT_SECONDS = 12
SHUTDOWN_CONFIRM_SECONDS = 3

# Sliders that only mean something for a zone with a soil-moisture probe --
# only created for such a zone (the controller falls back to the defaults).
MOISTURE_ONLY_NUMBERS = ("soil_moisture_dry_pct", "soil_moisture_wet_pct")
