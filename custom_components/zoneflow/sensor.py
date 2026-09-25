"""Diagnostic sensors: rain windows, 3-day avg peak temp, next irrigation
estimate, last water delivered estimate, days since last run. Ports of the
matching template sensors in configuration.yaml."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

from . import calculations as calc, units
from .const import DEMAND_MODEL_ET, DOMAIN, GROWTH_RAMP_CUSTOM, GROWTH_RAMP_OFF

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
        ZoneFlowReferenceEt0Sensor(entry, controller),
        ZoneFlowWeeklyTargetSensor(entry, controller),
        ZoneFlowNextIrrigationSensor(entry, controller),
        ZoneFlowDaysUntilNextRunSensor(entry, controller),
        ZoneFlowLastWaterDeliveredSensor(entry, controller),
        ZoneFlowTodayRainSensor(entry, controller),
        ZoneFlowSoilProfileSensor(entry, controller),
        ZoneFlowGrowthRampSensor(entry, controller),
        ZoneFlowLastCycleWaterSensor(entry, controller),
        ZoneFlowDeficitStatusSensor(entry, controller),
    ]
    if controller.soil_moisture_entity:
        entities += [
            ZoneFlowSoilMoistureSensor(entry, controller),
            ZoneFlowSoilMoistureStatusSensor(entry, controller),
        ]
    async_add_entities(entities, update_before_add=False)


class _Base(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = True

    def __init__(self, entry: ConfigEntry, controller) -> None:
        self._controller = controller
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=entry.title)

    # Sensors with a unit set _unit_kind (see units.SENSOR_UNITS) and
    # implement metric_native_value(); display units follow the zone's
    # Units option. Everything is still calculated in metric.
    _unit_kind: str | None = None

    def metric_native_value(self):
        return None

    @property
    def native_value(self):
        value = self.metric_native_value()
        if self._unit_kind is None or not isinstance(value, (int, float)):
            return value
        return units.sensor_value(self._unit_kind, value, self._controller.imperial)

    @property
    def native_unit_of_measurement(self):
        if self._unit_kind is None:
            return getattr(self, "_attr_native_unit_of_measurement", None)
        return units.sensor_unit(self._unit_kind, self._controller.imperial)

    @property
    def suggested_unit_of_measurement(self):
        # So a newly created entity shows the zone's units rather than
        # whatever Home Assistant's own system would pick.
        return self.native_unit_of_measurement if self._unit_kind is not None else None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._follow_zone_units()

    @callback
    def _follow_zone_units(self) -> None:
        """Home Assistant fixes a sensor's display unit when the entity is
        first created, so after the zone's Units option (or HA's own unit
        system) changes, an existing sensor would keep showing the old unit
        next to sliders in the new one. Move that fixed unit along -- unless
        the person picked a unit for this sensor themselves."""
        entry = self.registry_entry
        if self._unit_kind is None or entry is None:
            return
        if (entry.options.get("sensor") or {}).get("unit_of_measurement"):
            return
        private = dict(entry.options.get("sensor.private") or {})
        wanted = self.native_unit_of_measurement
        if private.get("suggested_unit_of_measurement") in (None, wanted):
            return
        private["suggested_unit_of_measurement"] = wanted
        er.async_get(self.hass).async_update_entity_options(entry.entity_id, "sensor.private", private)

    @property
    def suggested_display_precision(self):
        if self._unit_kind is not None and self._controller.imperial:
            return units.SENSOR_UNITS[self._unit_kind][2]
        return getattr(self, "_attr_suggested_display_precision", None)


class ZoneFlowRainWindowSensor(_Base):
    _unit_kind = "depth"
    # Precipitation device class on every rain sensor (not just Rain Today),
    # so an HA set to imperial shows them all in the same unit, with a
    # sensible number of decimals instead of raw conversion noise.
    _attr_native_unit_of_measurement = "mm"
    _attr_icon = "mdi:weather-pouring"
    _attr_device_class = "precipitation"
    _attr_suggested_display_precision = 1

    def __init__(self, entry: ConfigEntry, controller, window: str) -> None:
        super().__init__(entry, controller)
        self._window = window
        self._attr_unique_id = f"{entry.entry_id}_rain_past_{window}"
        self._attr_translation_key = f"rain_past_{window}"

    def metric_native_value(self) -> float:
        return round(self._controller.rain_windows()[self._window], 2)


class ZoneFlowAvgPeakTempSensor(_Base):
    _unit_kind = "temp"
    _attr_native_unit_of_measurement = "°C"
    _attr_icon = "mdi:thermometer"
    _attr_device_class = "temperature"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_avg_peak_temp_3d"
        self._attr_translation_key = "avg_peak_temp_3d"

    def metric_native_value(self) -> float:
        return self._controller.avg_peak_temp()


class ZoneFlowReferenceEt0Sensor(_Base):
    _unit_kind = "rate"
    _attr_device_class = "precipitation_intensity"
    """3-day average reference evapotranspiration (Hargreaves-Samani, see
    calculations.py). Display-only for now: nothing in the watering math
    reads it yet. Shows "unknown" until at least one full day of daily
    min/max temperature has been recorded."""

    _attr_native_unit_of_measurement = "mm/d"
    _attr_icon = "mdi:water-thermometer-outline"
    _attr_suggested_display_precision = 2

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_reference_et0_3d"
        self._attr_translation_key = "reference_et0_3d"

    def metric_native_value(self) -> float | None:
        return self._controller.avg_et0()

    @property
    def extra_state_attributes(self) -> dict:
        state = self._controller.store.state
        daily = self._controller.et0_daily_history()
        today = self._controller.today_et0_so_far()
        return {
            "method": "Hargreaves-Samani (FAO-56)",
            "latitude": self._controller.hass.config.latitude,
            "daily_et0_mm": [round(v, 2) if v is not None else None for v in daily],
            "daily_min_temp_c": list(state.min_temp_day_history_c),
            "daily_max_temp_c": list(state.peak_temp_day_history_c),
            "today_min_temp_c": state.today_min_temp_c,
            "today_max_temp_c": state.today_peak_temp_c,
            "today_et0_so_far_mm": round(today, 2) if today is not None else None,
        }


class ZoneFlowWeeklyTargetSensor(_Base):
    _unit_kind = "depth"
    _attr_device_class = "precipitation"
    """The routine weekly target a cycle would use right now, including the
    growth ramp, and which model produced it -- so switching a zone to the
    ET curve (or it falling back to the tiers) is visible on the dashboard
    rather than only in the CSV log."""

    _attr_native_unit_of_measurement = "mm"
    _attr_icon = "mdi:target"
    _attr_suggested_display_precision = 1

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_routine_weekly_target"
        self._attr_translation_key = "routine_weekly_target"

    def _source(self) -> tuple[float, str]:
        et_weekly = self._controller.et_weekly_target_mm()
        if et_weekly is not None:
            return et_weekly, "et_curve"
        tier = self._controller.tier_weekly_target_mm()
        if self._controller.demand_model == DEMAND_MODEL_ET:
            return tier, "temperature_tiers_fallback"
        return tier, "temperature_tiers"

    def metric_native_value(self) -> float:
        target, _ = self._source()
        return round(target * self._controller.routine_target_scale(), 2)

    @property
    def extra_state_attributes(self) -> dict:
        target, source = self._source()
        et0 = self._controller.effective_avg_et0()
        return {
            "demand_model": self._controller.demand_model,
            "source": source,
            "full_strength_target_mm": round(target, 2),
            "growth_ramp_pct": round(self._controller.growth_ramp_fraction() * 100, 0),
            "deficit_pct": round(self._controller.deficit()[0] * 100, 0),
            "avg_et0_mm_per_day": round(et0, 2) if et0 is not None else None,
            "crop_coefficient": self._controller.number("crop_coefficient"),
        }


class ZoneFlowNextIrrigationSensor(_Base):
    _attr_icon = "mdi:calendar-clock"
    _attr_device_class = "timestamp"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_next_irrigation_estimate"
        self._attr_translation_key = "next_irrigation_estimate"

    @property
    def native_value(self):
        # Unknown for a zone that has never watered (nothing to project from
        # -- epoch would read "56 years ago") and while wet soil holds the
        # routine back (can't be dated); a dry reading brings it forward.
        next_ts, _ = self._controller.routine_next_estimate()
        return dt_util.utc_from_timestamp(next_ts) if next_ts is not None else None

    @property
    def extra_state_attributes(self) -> dict:
        return {"decided_by": self._controller.routine_next_estimate()[1]}


class ZoneFlowDaysUntilNextRunSensor(_Base):
    """A friendly "how many days until this zone next waters" countdown:
    whichever comes first, the next routine cycle (same estimate as
    ZoneFlowNextIrrigationSensor above) or the next deep soak (skipped when
    deep soak is turned off for this zone). Models the time gates only --
    interval, drydown after heavy rain, and soil moisture (a dry reading
    brings the routine forward; wet soil holds it back undated) -- not rain
    credit or the forecast, so the real run can come later. A deep soak that is due
    but held back by a wet fortnight (its 14-day rain ceiling) is left out
    until it can run, instead of pinning the countdown at 0. Clamped
    to 0 rather than going negative once a cycle is due: "0 days" reads
    as "due any time now"."""

    _attr_native_unit_of_measurement = "d"
    _attr_icon = "mdi:calendar-arrow-right"
    _attr_suggested_display_precision = 1

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_days_until_next_run"
        self._attr_translation_key = "days_until_next_run"

    def _next_times(self) -> tuple[float | None, float | None]:
        c = self._controller
        state = c.store.state
        now_ts = dt_util.utcnow().timestamp()
        routine_next, _ = c.routine_next_estimate()
        deep_next = None
        if c.deep_soak_enabled and (state.last_deep_soak_ts is not None or state.last_routine_ts is not None):
            deep_next = calc.estimate_next_deep_soak(
                state.last_deep_soak_ts,
                c.number("deep_soak_interval_days"),
                state.last_significant_rain_ts,
                c.number("deep_soak_drydown_days"),
                now_ts,
            )
            # Due, but held back because the last 14 days were already wet:
            # it runs once the subsoil has dried, which can't be dated --
            # leave it out rather than pinning the countdown at 0 all
            # through a wet spell.
            if deep_next <= now_ts and c.rain_windows()["14d"] >= c.number("deep_soak_rain_threshold"):
                deep_next = None
        return routine_next, deep_next

    @staticmethod
    def _days(ts: float | None) -> float | None:
        if ts is None:
            return None
        return round(max(ts - dt_util.utcnow().timestamp(), 0.0) / 86400, 1)

    @property
    def native_value(self) -> float | None:
        known = [t for t in self._next_times() if t is not None]
        return self._days(min(known)) if known else None

    @property
    def extra_state_attributes(self) -> dict:
        routine_next, deep_next = self._next_times()
        next_cycle = None
        if routine_next is not None or deep_next is not None:
            next_cycle = "deep_soak" if (deep_next is not None and (routine_next is None or deep_next < routine_next)) else "routine"
        return {
            "routine_days": self._days(routine_next),
            "deep_soak_days": self._days(deep_next),
            "next_cycle": next_cycle,
        }


class ZoneFlowLastWaterDeliveredSensor(_Base):
    _unit_kind = "depth"
    _attr_device_class = "precipitation"
    _attr_native_unit_of_measurement = "mm"
    _attr_icon = "mdi:water-gauge"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_last_water_delivered"
        self._attr_translation_key = "last_water_delivered"

    def metric_native_value(self) -> float:
        return calc.estimate_last_water_delivered_mm(
            avg_peak_temp=self._controller.effective_avg_peak_temp(),
            hot_threshold=self._controller.number("hot_temp_threshold"),
            cool_threshold=self._controller.number("cool_temp_threshold"),
            normal_weekly_mm=self._controller.number("target_weekly_mm"),
            hot_weekly_mm=self._controller.number("target_weekly_hot_mm"),
            cool_weekly_mm=self._controller.number("target_weekly_cool_mm"),
            weekly_target_override_mm=self._controller.et_weekly_target_mm(),
        )


class ZoneFlowTodayRainSensor(_Base):
    _unit_kind = "depth"
    _attr_native_unit_of_measurement = "mm"
    _attr_icon = "mdi:weather-rainy"
    _attr_device_class = "precipitation"
    _attr_suggested_display_precision = 1

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_rain_today"
        self._attr_translation_key = "rain_today"

    def metric_native_value(self) -> float:
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
    _unit_kind = "volume"
    _attr_device_class = "water"
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

    def metric_native_value(self) -> float | None:
        return self._controller.store.state.last_cycle_water_liters


class ZoneFlowSoilMoistureSensor(_Base):
    """The zone's soil-moisture reading, on the zone itself -- next to the
    thresholds and status it's judged against. Only created when the zone
    has a soil-moisture sensor."""

    _attr_native_unit_of_measurement = "%"
    _attr_device_class = "moisture"
    _attr_state_class = "measurement"
    _attr_suggested_display_precision = 0

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_soil_moisture"
        self._attr_translation_key = "soil_moisture"

    @property
    def native_value(self) -> float | None:
        return self._controller.soil_moisture_reading()


class ZoneFlowSoilMoistureStatusSensor(_Base):
    """What the soil moisture means for the next routine run: dry (waters
    at the next scheduled time even if not due), wet (skips even if due),
    in range or offline (the schedule decides)."""

    _attr_device_class = "enum"
    _attr_options = ["dry", "wet", "in_range", "offline"]
    _attr_icon = "mdi:water-percent"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_soil_moisture_status"
        self._attr_translation_key = "soil_moisture_status"

    @property
    def native_value(self) -> str | None:
        return self._controller.soil_moisture_status()

    @property
    def extra_state_attributes(self) -> dict:
        c = self._controller
        return {
            "moisture_pct": c.soil_moisture_reading(),
            "dry_threshold_pct": c.number("soil_moisture_dry_pct"),
            "wet_threshold_pct": c.number("soil_moisture_wet_pct"),
        }


class ZoneFlowDeficitStatusSensor(_Base):
    """Deficit mode at a glance: off, active (reduced dose), a full dose
    today because of a guardrail, or ended."""

    _attr_device_class = "enum"
    _attr_options = [
        "off", "active", "full_dose_young_plant", "full_dose_no_temp", "full_dose_hot", "full_dose_soil_dry", "ended",
    ]
    _attr_icon = "mdi:water-minus"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_deficit_status"
        self._attr_translation_key = "deficit_status"

    @property
    def native_value(self) -> str:
        return self._controller.deficit()[1]

    @property
    def extra_state_attributes(self) -> dict:
        c = self._controller
        share, _ = c.deficit()
        until = c.store.state.deficit_until_ts
        return {
            "dose_pct": round(share * 100, 0),
            "water_pct_setting": c.number("deficit_water_pct"),
            "ends": dt_util.utc_from_timestamp(until).isoformat() if until is not None else None,
            # Without a temperature sensor there's no hot-day guard.
            "heat_guard": bool(c.outdoor_temp_entity),
        }
