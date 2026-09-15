"""Lock/fault indicators — ports of input_boolean.irrigation_in_progress
and input_boolean.avocado_irrigation_abort, now internal controller state
instead of generic helpers."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    controller = hass.data[DOMAIN][entry.entry_id]
    entities = [
        AvocadoLockBinarySensor(entry, controller),
        AvocadoAbortBinarySensor(entry, controller),
    ]
    async_add_entities(entities)


class _Base(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = True

    def __init__(self, entry: ConfigEntry, controller) -> None:
        self._controller = controller
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name="Avocado Irrigation")


class AvocadoLockBinarySensor(_Base):
    _attr_icon = "mdi:lock"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_irrigation_in_progress"
        self._attr_name = "Irrigation In Progress"

    @property
    def is_on(self) -> bool:
        return self._controller.store.state.lock_on


class AvocadoAbortBinarySensor(_Base):
    _attr_icon = "mdi:alert-octagon"
    _attr_device_class = "problem"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_irrigation_abort"
        self._attr_name = "Irrigation Abort Flag"

    @property
    def is_on(self) -> bool:
        return self._controller.store.state.abort_on
