"""The entities of an area's device (area.py): Pause, Snooze Today, and the
litres its zones used."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import AREA_DATA_KEY, DOMAIN


def _device(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=entry.title, manufacturer="ZoneFlow")


class _AreaEntity:
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, area, key: str) -> None:
        self._area = area
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = _device(entry)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._area.add_listener(self.async_write_ha_state))


@callback
def async_setup_area_switches(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([AreaPauseSwitch(entry, hass.data[AREA_DATA_KEY][entry.entry_id])])


@callback
def async_setup_area_buttons(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([AreaSnoozeButton(entry, hass.data[AREA_DATA_KEY][entry.entry_id])])


@callback
def async_setup_area_sensors(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    area = hass.data[AREA_DATA_KEY][entry.entry_id]
    async_add_entities([AreaWaterUsedSensor(entry, area, "30d"), AreaWaterUsedSensor(entry, area, "year")])


class AreaPauseSwitch(_AreaEntity, SwitchEntity):
    """No watering in any zone of the area while on. A zone's own Pause is
    separate: this one never switches it, and switching this off leaves a
    zone that is paused itself paused."""

    _attr_icon = "mdi:pause-circle-outline"
    _attr_translation_key = "pause"

    def __init__(self, entry: ConfigEntry, area) -> None:
        super().__init__(entry, area, "pause")

    @property
    def is_on(self) -> bool:
        return self._area.paused

    async def async_turn_on(self, **kwargs) -> None:
        await self._area.set_paused(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._area.set_paused(False)


class AreaSnoozeButton(_AreaEntity, ButtonEntity):
    """Skips today's watering in every zone of the area."""

    _attr_translation_key = "snooze_today"

    def __init__(self, entry: ConfigEntry, area) -> None:
        super().__init__(entry, area, "snooze_today")

    async def async_press(self) -> None:
        await self._area.snooze_today()


class AreaWaterUsedSensor(_AreaEntity, SensorEntity):
    """Litres the area's zones applied: the last 30 days and this year."""

    _attr_native_unit_of_measurement = "L"
    _attr_device_class = "water"
    _attr_icon = "mdi:water-sync"
    _attr_suggested_display_precision = 0
    _attr_should_poll = True

    def __init__(self, entry: ConfigEntry, area, window: str) -> None:
        super().__init__(entry, area, f"water_used_{window}")
        self._window = window
        self._attr_translation_key = f"water_used_{window}"
        if window == "year":
            self._attr_state_class = "total_increasing"

    @property
    def native_value(self) -> float | None:
        zones = [z for z in self._area.zones if z.has_water_volume]
        if not zones:
            return None
        return round(self._area.water_used_liters()[f"liters_{self._window}"], 1)
