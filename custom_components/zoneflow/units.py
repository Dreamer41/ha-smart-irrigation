"""Metric / imperial display for the tunable sliders.

ZoneFlow always stores and calculates in metric (mm, mm/min, °C). This
module only converts what a person sees and types on the number entities,
so the watering math -- and every test of it -- is identical whichever
units a zone shows. Which units a zone shows is the zone's "Units" option:
follow Home Assistant's own unit system (the default), or force metric or
imperial.
"""
from __future__ import annotations

MM_PER_INCH = 25.4

# Depths and rain amounts: mm <-> in.
DEPTH_KEYS = {
    "target_weekly_mm",
    "target_weekly_hot_mm",
    "target_weekly_cool_mm",
    "deep_soak_target_mm",
    "deep_soak_rain_threshold",
    "rain_mm_per_tip",
    "preirrigation_rain_threshold_mm",
    "forecast_rain_threshold_mm",
}
# Emitter application rate: mm/min <-> in/h (the usual drip rating in the US).
FLOW_KEYS = {"flow_rate_mm_per_min"}
# Temperature thresholds: °C <-> °F.
TEMP_KEYS = {"hot_temp_threshold", "cool_temp_threshold"}

IMPERIAL_UNIT = {"depth": "in", "flow": "in/h", "temp": "°F"}
IMPERIAL_STEP = {"depth": 0.01, "flow": 0.01, "temp": 0.5}
# rain_mm_per_tip is tiny (0.2-0.5 mm = 0.008-0.02 in), so finer steps.
IMPERIAL_STEP_OVERRIDE = {"rain_mm_per_tip": 0.001}

UNIT_SYSTEM_AUTO = "auto"
UNIT_SYSTEM_METRIC = "metric"
UNIT_SYSTEM_IMPERIAL = "imperial"
UNIT_SYSTEM_OPTIONS = [UNIT_SYSTEM_AUTO, UNIT_SYSTEM_METRIC, UNIT_SYSTEM_IMPERIAL]


def kind(key: str) -> str | None:
    if key in DEPTH_KEYS:
        return "depth"
    if key in FLOW_KEYS:
        return "flow"
    if key in TEMP_KEYS:
        return "temp"
    return None


def to_display(key: str, metric_value: float, imperial: bool) -> float:
    k = kind(key)
    if not imperial or k is None:
        return metric_value
    if k == "depth":
        return metric_value / MM_PER_INCH
    if k == "flow":
        return metric_value * 60 / MM_PER_INCH
    return metric_value * 9 / 5 + 32


def to_metric(key: str, display_value: float, imperial: bool) -> float:
    k = kind(key)
    if not imperial or k is None:
        return display_value
    if k == "depth":
        return display_value * MM_PER_INCH
    if k == "flow":
        return display_value * MM_PER_INCH / 60
    return (display_value - 32) * 5 / 9


def unit(key: str, metric_unit: str | None, imperial: bool) -> str | None:
    k = kind(key)
    if not imperial or k is None:
        return metric_unit
    return IMPERIAL_UNIT[k]


def step(key: str, metric_step: float, imperial: bool) -> float:
    k = kind(key)
    if not imperial or k is None:
        return metric_step
    return IMPERIAL_STEP_OVERRIDE.get(key, IMPERIAL_STEP[k])


def _decimals(step_value: float) -> int:
    text = f"{step_value:.6f}".rstrip("0")
    return len(text.split(".")[1]) if "." in text else 0


def display_range(key: str, metric_min: float, metric_max: float, metric_step: float, imperial: bool) -> tuple[float, float]:
    """Slider min/max in display units, rounded outward to the display step
    so the whole metric range stays reachable."""
    if not imperial or kind(key) is None:
        return metric_min, metric_max
    s = step(key, metric_step, True)
    lo = to_display(key, metric_min, True)
    hi = to_display(key, metric_max, True)
    lo = (lo // s) * s
    hi = -((-hi) // s) * s
    d = _decimals(s)
    return round(lo, d), round(hi, d)


def display_value(key: str, metric_value: float, metric_step: float, imperial: bool) -> float:
    """Value shown on the slider: converted, rounded one digit finer than
    the step so it reads cleanly without hiding the stored precision."""
    value = to_display(key, metric_value, imperial)
    if not imperial or kind(key) is None:
        return value
    return round(value, _decimals(step(key, metric_step, True)) + 1)


def metric_from_saved(key: str, value: float, saved_unit: str | None) -> float:
    """A restored slider value, saved in whatever unit it was showing then,
    turned back into metric -- so switching units never changes a setting."""
    k = kind(key)
    if k is not None and saved_unit == IMPERIAL_UNIT[k]:
        return to_metric(key, value, True)
    return value


# --- sensors ---------------------------------------------------------------
LITERS_PER_GALLON = 3.785411784

# kind -> (metric unit, imperial unit, imperial display precision)
SENSOR_UNITS = {
    "depth": ("mm", "in", 2),
    "rate": ("mm/d", "in/d", 2),
    "temp": ("°C", "°F", 1),
    "volume": ("L", "gal", 1),
}


def sensor_value(sensor_kind: str, metric_value: float | None, imperial: bool) -> float | None:
    if metric_value is None or not imperial:
        return metric_value
    if sensor_kind in ("depth", "rate"):
        return metric_value / MM_PER_INCH
    if sensor_kind == "temp":
        return metric_value * 9 / 5 + 32
    return metric_value / LITERS_PER_GALLON


def sensor_unit(sensor_kind: str, imperial: bool) -> str:
    metric_unit, imperial_unit, _ = SENSOR_UNITS[sensor_kind]
    return imperial_unit if imperial else metric_unit


def depth_text(mm: float, imperial: bool) -> str:
    """An amount of water for log/phone text, in the zone's units."""
    return f"{mm / MM_PER_INCH:.2f} in" if imperial else f"{mm:.1f} mm"
