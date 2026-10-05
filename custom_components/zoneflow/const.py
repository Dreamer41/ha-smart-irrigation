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
# Weather Underground rain (1.6.1, experimental): one shared config entry
# (entry_type below) holds the API key and the chosen stations (wu.py);
# an outdoor zone without a rain gauge opts in with CONF_USE_WU.
CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_WU = "weather_underground"
CONF_WU_API_KEY = "api_key"
CONF_WU_RADIUS_KM = "radius_km"
CONF_WU_STATIONS = "stations"
CONF_USE_WU = "use_weather_underground"
WU_DATA_KEY = "zoneflow_weather_underground"
REPAIR_WU_NO_DATA_SECONDS = 6 * 3600
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

# Fertilizing (datetime.py's "Last Fertilizing" + select.py's "Fertilizing
# Interval"): the Next Fertilizing sensor is the last date plus the
# interval, the "Fertilized Today" button records a feed, and a phone
# reminder goes out on the due date at FERTILIZE_REMINDER_HOUR. None of it
# changes what/when ZoneFlow waters. Options: "1w".."3w" weeks, "1".."12"
# months (the month keys are the original ones, so saved choices stay).
FERTILIZING_INTERVAL_OPTIONS = ["1w", "2w", "3w", *(str(m) for m in range(1, 13))]
DEFAULT_FERTILIZING_INTERVAL = "3"
FERTILIZE_REMINDER_HOUR = 9

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

# Mulch: whether this zone's bare soil is covered (mulch, or a full canopy/
# turf that already does the same job) or exposed. Bare soil loses more of
# what you apply to evaporation before the roots get it, so "not_mulched"
# scales the routine weekly target by the paired "Mulch ET Adjustment"
# number entity (see NUMBER_DEFS): positive values UP (exposed, fast-drying
# soil), negative values DOWN (heavy clay or shade that holds water well),
# range -50% to +70% -- the person's own dial for how much that
# matters for their specific plant/site, since it depends on canopy cover
# and exposure that ZoneFlow has no sensor for. Applied in controller.py's
# `scale` alongside growth ramp and deficit mode, so it affects BOTH demand
# models the same way (temperature tiers and the ET curve alike) -- unlike
# crop_coefficient, which the ET curve alone reads. Default is "mulched"
# (no adjustment) so an existing zone's watering doesn't silently change
# when this ships; see AI_SETUP.md for guidance on how much to dial in for
# different plants/situations.
CONF_MULCH_STATUS = "mulch_status"
MULCH_STATUS_MULCHED = "mulched"
MULCH_STATUS_NOT_MULCHED = "not_mulched"
MULCH_STATUS_OPTIONS = [MULCH_STATUS_MULCHED, MULCH_STATUS_NOT_MULCHED]
DEFAULT_MULCH_STATUS = MULCH_STATUS_MULCHED

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
    # Wide enough for any climate (a Nordic summer to a desert one); a
    # zone's starting values come from its climate choice at setup
    # (CLIMATE_PRESETS below).
    "hot_temp_threshold": ("Hot Weather Temp Threshold", 15.0, 45.0, 0.5, "°C"),
    "cool_temp_threshold": ("Cool Weather Temp Threshold", 5.0, 40.0, 0.5, "°C"),
    # Used for the watering decision when there is no real temperature to
    # go on: no sensor on this zone (then it is the manual "it's a hot /
    # cool spell" control), or the sensor has recorded no real day in the
    # last 3 (see ZoneFlowController.watering_temp).
    "fallback_temp": ("Fallback / Manual Temperature", 0.0, 45.0, 0.5, "°C"),
    "target_weekly_cool_mm": ("Routine Cool Weekly Target", 5.0, 40.0, 0.5, "mm"),
    "rain_eff_low": ("Rain Efficiency - Light (3-5mm)", 0.0, 1.0, 0.05, None),
    "rain_eff_mid": ("Rain Efficiency - Moderate (5-10mm)", 0.0, 1.0, 0.05, None),
    "rain_eff_high": ("Rain Efficiency - Heavy (10-20mm+)", 0.0, 1.0, 0.05, None),
    "flow_rate_mm_per_min": ("Emitter Flow Rate Calibration", 0.05, 2.0, 0.01, "mm/min"),
    # 1.6.5: what the zone's valve delivers in total, for the water-use
    # estimate only (litres = valve minutes x this). 0 = not set: the zone
    # then counts mm only. Never used for a watering decision.
    "zone_flow_l_min": ("Zone Flow", 0.0, 2000.0, 0.01, "L/min"),
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
    # Manual rain (1.6.1): the amount the "Add Manual Rain" button adds,
    # back to 0 after each press (controller.add_manual_rain_from_number).
    "manual_rain_mm": ("Manual Rain", 0.0, 200.0, 0.5, "mm"),
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
    # How much to scale the routine weekly target up while this zone's
    # "Mulch" select is "Not Mulched" -- see CONF_MULCH_STATUS above. Has no
    # effect while the select is "Mulched". Default 20% is a starting point
    # for a mature tree with a fair amount of its own canopy cover; a young
    # or sparse plant with a lot of exposed bare soil around it usually
    # needs more -- AI_SETUP.md has scenario guidance, and the 70% ceiling
    # is there for the person to dial in from their own observation, not a
    # number to reach for by default.
    "mulch_et_adjustment_pct": ("Mulch ET Adjustment", -50.0, 70.0, 5.0, "%"),
    # How long the Service Mode switch keeps the valve open before switching
    # itself off (with a phone alert) -- so a forgotten switch can't water
    # for hours. See controller.start_service_run.
    "service_mode_auto_off_minutes": ("Service Mode Auto-Off", 5.0, 120.0, 5.0, "min"),
    # Frost guard: a due cycle is skipped while the outdoor temperature is
    # below this (needs a temperature sensor). At its lowest it's off. See
    # controller._frost_blocks.
    "frost_guard_temp": ("Frost Guard Temperature", -10.0, 10.0, 0.5, "°C"),
    # --- 1.6 greenhouse / indoor climate (only created for those zones) ---
    "heat_temp": ("Heater On Below", 0.0, 30.0, 0.5, "°C"),
    "vent_temp": ("Vents Open At", 10.0, 40.0, 0.5, "°C"),
    "fan_temp": ("Fans On At", 10.0, 45.0, 0.5, "°C"),
    "climate_hysteresis": ("Climate Hysteresis", 0.5, 5.0, 0.5, "°C"),
    "outside_margin": ("Outside Air Margin", 0.0, 10.0, 0.5, "°C"),
    "max_humidity": ("Ventilate Above Humidity", 50.0, 100.0, 1.0, "%"),
    "mist_temp": ("Mist On Above Temperature", 15.0, 45.0, 0.5, "°C"),
    "mist_min_humidity": ("Mist On Below Humidity", 20.0, 90.0, 1.0, "%"),
    "mist_stop_humidity": ("Mist Stop Humidity", 50.0, 100.0, 1.0, "%"),
    "mist_min_temp": ("Mist Minimum Temperature", 5.0, 30.0, 0.5, "°C"),
    "mist_light_level": ("Mist Light Level", 1000.0, 150000.0, 1000.0, "lx"),
    "mist_on_seconds": ("Mist On Time", 3.0, 300.0, 1.0, "s"),
    "mist_off_seconds": ("Mist Off Time", 10.0, 3600.0, 10.0, "s"),
    "max_mist_minutes_per_hour": ("Max Misting Per Hour", 1.0, 60.0, 1.0, "min"),
    "vent_open_pct": ("Vent Open Position", 10.0, 100.0, 5.0, "%"),
    # 1.6.1: replaces Manual Hold Time (minutes). Used while Auto Resume is
    # on; with it off a hold lasts until Resume Automatic is pressed.
    "auto_resume_hours": ("Auto Resume After", 0.5, 24.0, 0.5, "h"),
    "sensor_offline_hours": ("Sensor Offline After", 1.0, 24.0, 1.0, "h"),
}

NUMBER_DEFAULTS: dict[str, float] = {
    "target_weekly_mm": 35.0,
    "target_weekly_hot_mm": 45.0,
    "hot_temp_threshold": 31.5,
    "cool_temp_threshold": 30.0,
    # Placeholder only: never used as a value. A zone gets its fallback from
    # the climate step at setup, or (older zones) the middle of its own
    # cool/hot band -- ZoneFlowController._seed_fallback_temp.
    "fallback_temp": 30.75,
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
    "manual_rain_mm": 0.0,
    "zone_flow_l_min": 0.0,
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
    "mulch_et_adjustment_pct": 20.0,
    "service_mode_auto_off_minutes": 30.0,
    "frost_guard_temp": 2.0,
    "heat_temp": 10.0,
    "vent_temp": 25.0,
    "fan_temp": 28.0,
    "climate_hysteresis": 1.5,
    "outside_margin": 1.0,
    "max_humidity": 85.0,
    "mist_temp": 30.0,
    "mist_min_humidity": 50.0,
    "mist_stop_humidity": 85.0,
    "mist_min_temp": 18.0,
    "mist_light_level": 40000.0,
    "mist_on_seconds": 10.0,
    "mist_off_seconds": 120.0,
    "max_mist_minutes_per_hour": 10.0,
    "vent_open_pct": 100.0,
    "auto_resume_hours": 1.0,
    "sensor_offline_hours": 4.0,
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

# Starting temperature thresholds per climate, picked once at setup (the
# sliders stay the source of truth afterwards). Daily PEAK temperatures in
# the growing season, in °C: at or above "hot" is a hot spell, below
# "cool" a cool one, anything between is normal. "fallback" sits in the
# normal band. Tropical is the original Koh Samui avocado calibration.
CONF_CLIMATE = "climate"
CONF_INITIAL_NUMBERS = "initial_numbers"
CLIMATE_PRESETS: dict[str, dict[str, float]] = {
    "tropical": {"hot_temp_threshold": 31.5, "cool_temp_threshold": 30.0, "fallback_temp": 30.5},
    "hot_dry": {"hot_temp_threshold": 34.0, "cool_temp_threshold": 26.0, "fallback_temp": 30.0},
    "temperate": {"hot_temp_threshold": 28.0, "cool_temp_threshold": 20.0, "fallback_temp": 24.0},
    "cool": {"hot_temp_threshold": 24.0, "cool_temp_threshold": 16.0, "fallback_temp": 20.0},
}
CLIMATE_OPTIONS = list(CLIMATE_PRESETS)
DEFAULT_CLIMATE = "temperate"
CLIMATE_NUMBER_KEYS = ("hot_temp_threshold", "cool_temp_threshold", "fallback_temp")

# A soil-moisture reading not reported for this long counts as offline: many
# Zigbee/BLE/cloud sensors keep showing their last value for hours or days
# after a battery dies. Uses Home Assistant's last_reported, which moves on
# every report even when the value is unchanged, so a steady real reading is
# fine. 24 h leaves room for sensors that report rarely overnight.
SOIL_MOISTURE_STALE_SECONDS = 24 * 3600
# Wet readings holding back a due routine run for longer than this many of
# the zone's routine intervals send one "check the probe" alert.
SOIL_WET_HOLD_ALERT_INTERVALS = 2

# The quick service/check run buttons on every zone, in minutes.
SERVICE_RUN_BUTTON_MINUTES = (1, 5, 10, 15)

# Phone notifications: every notification is either informational (a run
# finished, rain skipped a cycle) or a warning (something needs a look).
# Each zone's Notifications select picks which ones reach the phone; the
# CSV log always gets everything.
LEVEL_INFO = "info"
LEVEL_WARNING = "warning"
NOTIFY_ALL = "all"
NOTIFY_WARNINGS = "warnings"
NOTIFY_NONE = "none"
NOTIFY_LEVEL_OPTIONS = [NOTIFY_ALL, NOTIFY_WARNINGS, NOTIFY_NONE]

# Frost guard (controller._frost_blocks): a cycle skipped for frost checks
# again this often, this many times that day.
FROST_RETRY_SECONDS = 3600
FROST_RETRY_COUNT = 6
# A temperature reading older than this, or below this, is not trusted to
# hold watering back (a sensor stuck on a cold reading, an error value).
FROST_TEMP_MAX_AGE_SECONDS = 6 * 3600
FROST_TEMP_MIN_PLAUSIBLE_C = -60.0

# Weekly summary (summary.py): sent at this local hour on each zone's
# chosen weekday ("off" = never).
SUMMARY_HOUR = 18
SUMMARY_OFF = "off"
SUMMARY_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
SUMMARY_OPTIONS = [SUMMARY_OFF, *SUMMARY_DAYS]

# Repairs (issues.py): how long something must be offline before it's
# raised in Settings -> Repairs, and how often zones are checked.
REPAIR_VALVE_OFFLINE_SECONDS = 3600
REPAIR_SENSOR_OFFLINE_SECONDS = 3 * 86400
REPAIR_NOTIFY_MISSING_SECONDS = 86400
REPAIR_CHECK_INTERVAL_SECONDS = 3600
REPAIR_FIRST_CHECK_SECONDS = 300

# Plant presets at setup (config flow's first step): starting values for a
# kind of planting -- weekly targets (normal / hot / cool), crop factor,
# pulses, deep soak on/off and the growth ramp. All of them stay ordinary
# settings afterwards. Rough, widely used horticultural figures meant to be
# tuned; AI_SETUP.md has per-crop guidance.
CONF_PLANT = "plant"
PLANT_CUSTOM = "custom"
PLANT_PRESETS: dict[str, dict] = {
    "tomatoes": {
        "numbers": {"target_weekly_mm": 30.0, "target_weekly_hot_mm": 40.0, "target_weekly_cool_mm": 20.0,
                    "crop_coefficient": 1.05},
        "deep_soak": False, "ramp": "fast_annual",
    },
    "chilis": {
        "numbers": {"target_weekly_mm": 25.0, "target_weekly_hot_mm": 35.0, "target_weekly_cool_mm": 15.0,
                    "crop_coefficient": 0.95},
        "deep_soak": False, "ramp": "slow_fruiting",
    },
    "leafy_vegetables": {
        "numbers": {"target_weekly_mm": 25.0, "target_weekly_hot_mm": 35.0, "target_weekly_cool_mm": 18.0,
                    "crop_coefficient": 1.0},
        "deep_soak": False, "ramp": "fast_annual",
    },
    "herbs": {
        "numbers": {"target_weekly_mm": 15.0, "target_weekly_hot_mm": 22.0, "target_weekly_cool_mm": 10.0,
                    "crop_coefficient": 0.7},
        "deep_soak": False, "ramp": "off",
    },
    "strawberries": {
        "numbers": {"target_weekly_mm": 25.0, "target_weekly_hot_mm": 35.0, "target_weekly_cool_mm": 18.0,
                    "crop_coefficient": 0.85},
        "deep_soak": False, "ramp": "off",
    },
    "flowers": {
        "numbers": {"target_weekly_mm": 22.0, "target_weekly_hot_mm": 30.0, "target_weekly_cool_mm": 15.0,
                    "crop_coefficient": 0.9},
        "deep_soak": False, "ramp": "fast_annual",
    },
    "lawn": {
        "numbers": {"target_weekly_mm": 25.0, "target_weekly_hot_mm": 35.0, "target_weekly_cool_mm": 15.0,
                    "crop_coefficient": 0.8},
        "deep_soak": False, "ramp": "off",
    },
    "shrubs": {
        "numbers": {"target_weekly_mm": 15.0, "target_weekly_hot_mm": 25.0, "target_weekly_cool_mm": 10.0,
                    "crop_coefficient": 0.6},
        "deep_soak": True, "ramp": "off",
    },
    "young_tree": {
        "numbers": {"target_weekly_mm": 20.0, "target_weekly_hot_mm": 30.0, "target_weekly_cool_mm": 12.0,
                    "crop_coefficient": 0.6},
        "deep_soak": True, "ramp": "established_perennial",
    },
    "fruit_tree": {
        "numbers": {"target_weekly_mm": 30.0, "target_weekly_hot_mm": 45.0, "target_weekly_cool_mm": 20.0,
                    "crop_coefficient": 0.8},
        "deep_soak": True, "ramp": "off",
    },
}
PLANT_OPTIONS = [PLANT_CUSTOM, *PLANT_PRESETS]

# Flow-rate measurement with a flow meter (options -> Flow rate): a service
# run this long, then litres / area / minutes.
FLOW_MEASURE_MINUTES = 10
# ...and at least this long (or 80% of it, if the daily cap shortened it),
# and the meter's last report waited for up to this long.
FLOW_MEASURE_MIN_MINUTES = 5
FLOW_METER_SETTLE_SECONDS = 60

# --- 1.6: zone type and greenhouse / indoor climate hardware ----------------
# A zone with no zone type stored is an outdoor zone and behaves exactly as in
# 1.5.1 (nothing is migrated). Greenhouse and indoor zones may have no valve
# (climate control only), have no rain gauge or forecast (a roof), and read
# their temperature for watering from the inside sensor.
CONF_ZONE_TYPE = "zone_type"
ZONE_TYPE_OUTDOOR = "outdoor"
ZONE_TYPE_GREENHOUSE = "greenhouse"
ZONE_TYPE_INDOOR = "indoor"
ZONE_TYPE_OPTIONS = [ZONE_TYPE_OUTDOOR, ZONE_TYPE_GREENHOUSE, ZONE_TYPE_INDOOR]
DEFAULT_ZONE_TYPE = ZONE_TYPE_OUTDOOR

CONF_INSIDE_TEMP_ENTITY = "inside_temp_entity"  # required for any climate device
CONF_INSIDE_HUMIDITY_ENTITY = "inside_humidity_entity"
CONF_LIGHT_ENTITY = "light_entity"
# Extra inside temperature sensors: used, in order, when the main one fails.
CONF_BACKUP_TEMP_ENTITIES = "backup_temp_entities"
# Climate device roles: any number of entities each (a list of entity ids).
CONF_FAN_ENTITIES = "fan_entities"
CONF_VENT_ENTITIES = "vent_entities"
CONF_MISTER_ENTITIES = "mister_entities"
CONF_HEATER_ENTITIES = "heater_entities"
# 1.6.1: a crop is a greenhouse / indoor zone that belongs to a greenhouse
# (the zone with the climate): it stores that zone's entry id here and uses
# its inside sensors (controller.parent_entry).
CONF_PARENT_ZONE = "greenhouse_entry_id"
# What a crop takes from its greenhouse, read live.
CROP_INHERITED_KEYS = (CONF_INSIDE_TEMP_ENTITY, CONF_BACKUP_TEMP_ENTITIES)
DEVICE_ROLE_KEYS = (CONF_FAN_ENTITIES, CONF_VENT_ENTITIES, CONF_MISTER_ENTITIES, CONF_HEATER_ENTITIES)
# What each role accepts (entity domains).
DEVICE_ROLE_DOMAINS: dict[str, list[str]] = {
    CONF_FAN_ENTITIES: ["switch", "input_boolean", "fan"],
    CONF_VENT_ENTITIES: ["cover", "switch", "input_boolean"],
    CONF_MISTER_ENTITIES: ["switch", "input_boolean", "valve"],
    CONF_HEATER_ENTITIES: ["switch", "input_boolean", "climate"],
}

# The greenhouse sliders: created only for greenhouse / indoor zones, and
# shown only when the hardware they act on is configured (visibility.py).
GREENHOUSE_NUMBERS = (
    "heat_temp", "vent_temp", "fan_temp", "climate_hysteresis", "outside_margin", "max_humidity",
    "mist_temp", "mist_min_humidity", "mist_stop_humidity", "mist_min_temp", "mist_light_level",
    "mist_on_seconds", "mist_off_seconds", "max_mist_minutes_per_hour", "vent_open_pct", "auto_resume_hours",
    "sensor_offline_hours",
)
# Seeded from the climate preset at setup (greenhouse_logic.PRESET_SETPOINTS).
GREENHOUSE_PRESET_NUMBER_KEYS = ("heat_temp", "vent_temp", "fan_temp", "mist_temp")

# How the climate engine behaves (greenhouse.py).
GREENHOUSE_EVAL_SECONDS = 30  # re-evaluate this often, and on any sensor change
GREENHOUSE_SENSOR_GRACE_SECONDS = 120  # a sensor dropout shorter than this changes nothing
# A sensor with no report for "Sensor Offline After" hours counts as failed.
GREENHOUSE_SERVICE_TIMEOUT_SECONDS = 15  # a device call that hangs longer has failed
GREENHOUSE_INSIDE_TEMP_RANGE = (-30.0, 70.0)  # outside this a reading is a glitch, not a temperature
GREENHOUSE_OUTSIDE_TEMP_RANGE = (-50.0, 70.0)
GREENHOUSE_ISSUE_SENSOR_SECONDS = 600  # Repairs issue after this long on failsafe
GREENHOUSE_ISSUE_OUTSIDE_SECONDS = 1800
GREENHOUSE_SENSOR_MISMATCH_C = 5.0  # main and backup further apart than this ...
GREENHOUSE_SENSOR_MISMATCH_SECONDS = 1800  # ... for this long: Repairs issue
GREENHOUSE_MANUAL_GRACE_SECONDS = 60  # a device's own slow report after our command isn't a person
GREENHOUSE_CONFIRM_SECONDS = 30  # a device told to move has this long to report it
GREENHOUSE_MIST_STUCK_MARGIN_SECONDS = 60  # a mister on this much past its pulse is forced off
# Minimum time a device stays on / off (seconds), per role.
GREENHOUSE_MIN_TIMES: dict[str, tuple[float, float]] = {
    "fans": (120.0, 120.0),
    "vents": (180.0, 180.0),
    "heater": (300.0, 300.0),
    "misters": (0.0, 0.0),  # pulses are paced by the on/off time sliders
}
