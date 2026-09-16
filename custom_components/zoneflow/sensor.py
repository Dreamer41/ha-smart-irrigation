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
from .const import DOMAIN

RAIN_WINDOW_SENSORS = ["30min", "24h", "3d", "7d", "14d"]


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
        self._attr_name = f"Rain Past {window}"

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
        self._attr_name = "3-Day Average Peak Temperature"

    @property
    def native_value(self) -> float:
        return self._controller.avg_peak_temp()


class ZoneFlowNextIrrigationSensor(_Base):
    _attr_icon = "mdi:calendar-clock"
    _attr_device_class = "timestamp"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_next_irrigation_estimate"
        self._attr_name = "Next Irrigation Estimate"

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
        self._attr_name = "Last Water Delivered (Estimate)"

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
        self._attr_name = "Rain Today"

    @property
    def native_value(self) -> float:
        return round(self._controller.today_rain_mm(), 2)
