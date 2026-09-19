"""The tunable sliders (see `const.py` NUMBER_DEFS), 1:1 with the
input_number helpers in the original live configuration.yaml this was
ported from (same name/min/max/step/unit).

Uses RestoreNumber so a value you set on the dashboard survives an HA
restart. Deliberately does NOT set a value at construction time beyond the
restored/default one — that `initial:` bug (helpers snapping back to
calibrated defaults on every reboot) is exactly what you had to fix in the
YAML helpers in Sept 2026, so this is built to not repeat it.
"""
from __future__ import annotations

from homeassistant.components.number import RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, NUMBER_DEFAULTS, NUMBER_DEFS


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    controller = hass.data[DOMAIN][entry.entry_id]
    entities = [ZoneFlowNumber(entry, controller, key) for key in NUMBER_DEFS]
    async_add_entities(entities)


class ZoneFlowNumber(RestoreNumber):
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, controller, key: str) -> None:
        name, min_v, max_v, step, unit = NUMBER_DEFS[key]
        self._key = key
        self._controller = controller
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key  # see translations/<lang>.json's entity.number.<key>.name
        self._attr_native_min_value = min_v
        self._attr_native_max_value = max_v
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="ZoneFlow",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = last.native_value
        else:
            self._attr_native_value = NUMBER_DEFAULTS[self._key]
        self._controller.register_number(self._key, self)

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
