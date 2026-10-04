"""Sensors of the Weather Underground rain entry (wu.py): today's rain as
ZoneFlow counts it, and each station's own reading, so a person can check
the numbers look right before trusting them."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

from .const import DOMAIN, WU_DATA_KEY


def _ts(value: float | None) -> str | None:
    return dt_util.as_local(dt_util.utc_from_timestamp(value)).isoformat(timespec="minutes") if value else None


@callback
def async_setup_wu_sensors(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    source = hass.data[WU_DATA_KEY]
    # Stations no longer chosen: their sensors go.
    wanted = {f"{entry.entry_id}_wu_station_{info['id']}" for info in source.station_info}
    registry = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.unique_id.startswith(f"{entry.entry_id}_wu_station_") and reg_entry.unique_id not in wanted:
            registry.async_remove(reg_entry.entity_id)
    entities: list[SensorEntity] = [WURainTodaySensor(entry, source)]
    entities += [WUStationSensor(entry, source, info) for info in source.station_info]
    async_add_entities(entities)


class _WUBase(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_native_unit_of_measurement = "mm"
    _attr_device_class = SensorDeviceClass.PRECIPITATION
    _attr_suggested_display_precision = 1

    def __init__(self, entry: ConfigEntry, source) -> None:
        self._source = source
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name=entry.title, manufacturer="ZoneFlow"
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._source.add_listener(self.async_write_ha_state))


class WURainTodaySensor(_WUBase):
    """Today's rain as ZoneFlow counts it from the chosen stations."""

    _attr_icon = "mdi:weather-pouring"

    def __init__(self, entry: ConfigEntry, source) -> None:
        super().__init__(entry, source)
        self._attr_unique_id = f"{entry.entry_id}_wu_rain_today"
        self._attr_translation_key = "wu_rain_today"

    @property
    def native_value(self) -> float | None:
        if self._source.last_good_ts is None:
            return None
        return round(self._source.today_mm(), 2)

    @property
    def extra_state_attributes(self) -> dict:
        source = self._source
        return {
            "stations_used": source.used_station_ids,
            "confidence": source.confidence,
            "last_poll": _ts(source.last_poll_ts),
            "next_poll": _ts(source.next_poll_ts),
        }


class WUStationSensor(_WUBase):
    """One station's own rain since its midnight, and whether it is used."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:home-thermometer-outline"

    def __init__(self, entry: ConfigEntry, source, info: dict) -> None:
        super().__init__(entry, source)
        self._id = info["id"]
        self._info = info
        self._attr_unique_id = f"{entry.entry_id}_wu_station_{self._id}"
        self._attr_translation_key = "wu_station"
        self._attr_translation_placeholders = {"station": self._id}

    @property
    def native_value(self) -> float | None:
        state = self._source.stations.get(self._id)
        if state is None or state.total is None or state.day != dt_util.now().date().isoformat():
            return None
        return round(state.total, 2)

    @property
    def extra_state_attributes(self) -> dict:
        state = self._source.stations.get(self._id)
        return {
            "station_name": self._info.get("name"),
            "distance_km": self._info.get("distance_km"),
            "status": state.status if state else "waiting",
            "used": self._id in self._source.used_station_ids,
            "last_report": _ts(state.obs_ts) if state else None,
        }
