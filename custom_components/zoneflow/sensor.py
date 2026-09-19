"""Diagnostic sensors: rain windows, 3-day avg peak temp, next irrigation
estimate, last water delivered estimate, days since last run. Ports of the
matching template sensors in configuration.yaml."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

from . import calculations as calc
from .const import DOMAIN, GROWTH_RAMP_CUSTOM, GROWTH_RAMP_OFF

RAIN_WINDOW_SENSORS = ["30min", "24h", "3d", "7d", "14d"]


def _label(raw: str) -> str:
    """Turn a stored option key like "clay_loam" / "off" into a display
    string ("Clay Loam" / "Off") without needing a separate lookup table --
    these are informational-only categories (see const.py), never parsed
    back out of the label."""
    return raw.replace("_", " ").title()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    controller = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        ZoneFlowRainWindowSensor(entry, controller, window) for window in RAIN_WINDOW_SENSORS
    ]
    entities += [
        ZoneFlowAvgPeakTempSensor(entry, controller),
        ZoneFlowNextIrrigationSensor(entry, controller),
        ZoneFlowLastWaterDeliveredSensor(entry, controller),
        ZoneFlowTodayRainSensor(entry, controller),
        ZoneFlowSoilProfileSensor(entry, controller),
        ZoneFlowGrowthRampSensor(entry, controller),
        ZoneFlowLastCycleWaterSensor(entry, controller),
    ]
    async_add_entities(entities, update_before_add=False)


class _Base(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = True

    def __init__(self, entry: ConfigEntry, controller) -> None:
        self._controller = controller
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=entry.title)


class ZoneFlowRainWindowSensor(_Base):
    _attr_native_unit_of_measurement = "mm"
    _attr_icon = "mdi:weather-pouring"

    def __init__(self, entry: ConfigEntry, controller, window: str) -> None:
        super().__init__(entry, controller)
        self._window = window
        self._attr_unique_id = f"{entry.entry_id}_rain_past_{window}"
        self._attr_translation_key = f"rain_past_{window}"

    @property
    def native_value(self) -> float:
        return round(self._controller.rain_windows()[self._window], 2)


class ZoneFlowAvgPeakTempSensor(_Base):
    _attr_native_unit_of_measurement = "°C"
    _attr_icon = "mdi:thermometer"
    _attr_device_class = "temperature"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_avg_peak_temp_3d"
        self._attr_translation_key = "avg_peak_temp_3d"

    @property
    def native_value(self) -> float:
        return self._controller.avg_peak_temp()


class ZoneFlowNextIrrigationSensor(_Base):
    _attr_icon = "mdi:calendar-clock"
    _attr_device_class = "timestamp"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_next_irrigation_estimate"
        self._attr_translation_key = "next_irrigation_estimate"

    @property
    def native_value(self):
        state = self._controller.store.state
        if state.last_routine_ts is None:
            # Never watered yet (a brand-new zone) -- there's no real last-run
            # time to project a next-run estimate from. Falling back to epoch
            # (0.0) here used to compute a "next irrigation" date decades in
            # the past ("56 years ago" in the UI) instead of an honest
            # "unknown". Once the first routine cycle actually runs, this
            # starts producing a real estimate.
            return None
        est = calc.estimate_next_irrigation(
            last_routine_ts=state.last_routine_ts,
            last_significant_rain_ts=state.last_significant_rain_ts or 0.0,
            avg_peak_temp=self._controller.avg_peak_temp(),
            hot_threshold=self._controller.number("hot_temp_threshold"),
            routine_drydown_days=self._controller.number("routine_drydown_days"),
        )
        return dt_util.utc_from_timestamp(est.next_ts)


class ZoneFlowLastWaterDeliveredSensor(_Base):
    _attr_native_unit_of_measurement = "mm"
    _attr_icon = "mdi:water-gauge"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_last_water_delivered"
        self._attr_translation_key = "last_water_delivered"

    @property
    def native_value(self) -> float:
        return calc.estimate_last_water_delivered_mm(
            avg_peak_temp=self._controller.avg_peak_temp(),
            hot_threshold=self._controller.number("hot_temp_threshold"),
            cool_threshold=self._controller.number("cool_temp_threshold"),
            normal_weekly_mm=self._controller.number("target_weekly_mm"),
            hot_weekly_mm=self._controller.number("target_weekly_hot_mm"),
            cool_weekly_mm=self._controller.number("target_weekly_cool_mm"),
        )


class ZoneFlowTodayRainSensor(_Base):
    _attr_native_unit_of_measurement = "mm"
    _attr_icon = "mdi:weather-rainy"
    _attr_device_class = "precipitation"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_rain_today"
        self._attr_translation_key = "rain_today"

    @property
    def native_value(self) -> float:
        return round(self._controller.today_rain_mm(), 2)


class ZoneFlowSoilProfileSensor(_Base):
    """Read-only summary of the descriptive soil/site fields set at setup
    (see const.py's CONF_SOIL_TYPE block) -- purely informational, so this
    sensor never feeds back into any scheduling decision. Its state is the
    soil type; drainage/slope/irrigation method ride along as attributes so
    the whole profile is visible at a glance on one entity."""

    _attr_icon = "mdi:layers-outline"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_soil_profile"
        self._attr_translation_key = "soil_profile"

    @property
    def native_value(self) -> str:
        return _label(self._controller.soil_type)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "drainage": _label(self._controller.drainage),
            "slope": _label(self._controller.slope),
            "irrigation_method": _label(self._controller.irrigation_method),
        }


class ZoneFlowGrowthRampSensor(_Base):
    """Current growth-stage auto-ramp fraction (see controller.py's
    growth_ramp_fraction()) as a percentage of the full weekly target.
    Always 100% when the feature is off, or on but no planting date has
    been recorded yet -- an enabled-but-unconfigured ramp never silently
    reduces watering, and this sensor reflects that honestly rather than
    showing a misleading partial value."""

    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:sprout"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_growth_ramp_pct"
        self._attr_translation_key = "growth_ramp_pct"

    @property
    def native_value(self) -> float:
        return round(self._controller.growth_ramp_fraction() * 100, 0)

    @property
    def extra_state_attributes(self) -> dict:
        profile = self._controller.growth_ramp_profile
        attrs = {"profile": _label(profile)}
        if profile == GROWTH_RAMP_OFF:
            return attrs
        # "manual" here means the dashboard growth-stage select (select.py)
        # is currently overriding the planting-date curve -- see
        # ZoneFlowController.growth_ramp_fraction. days_since_planting keeps
        # being reported either way since the planting date itself is
        # unaffected by the override.
        attrs["mode"] = self._controller.store.state.growth_stage_mode
        planting_ts = self._controller.store.state.planting_date_ts
        if planting_ts is not None:
            days = max((dt_util.utcnow().timestamp() - planting_ts) / 86400.0, 0.0)
            attrs["days_since_planting"] = round(days, 1)
        if profile == GROWTH_RAMP_CUSTOM:
            # Surfaces exactly what the "Custom Ramp: ..." sliders currently
            # produce, sorted the same way _custom_growth_ramp_curve
            # (controller.py) applies them -- so it's easy to tell at a
            # glance whether the sliders are set the way you think they are.
            curve = self._controller._custom_growth_ramp_curve()
            attrs["custom_curve"] = [
                {"day": round(day, 1), "pct": round(pct * 100, 0)} for day, pct in curve
            ]
        return attrs


class ZoneFlowLastCycleWaterSensor(_Base):
    """Measured (not estimated) water delivered by the most recently
    completed cycle, from the optional flow-meter entity -- distinct from
    ZoneFlowLastWaterDeliveredSensor above, which is always a target-based
    estimate. Stays "unknown" until a cycle has actually run with a flow
    meter configured and readable at both ends (see
    ZoneFlowController._run_pulses)."""

    _attr_native_unit_of_measurement = "L"
    _attr_icon = "mdi:water"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_last_cycle_water_liters"
        self._attr_translation_key = "last_cycle_water_liters"

    @property
    def native_value(self) -> float | None:
        return self._controller.store.state.last_cycle_water_liters
