"""Binary sensors for Avocado Irrigation."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([
        AvocadoBinary(entry, "irrigation_active", "Irrigation Active", "irrigation_in_progress"),
        AvocadoBinary(entry, "fault_lockout", "Fault Lockout", "fault_lockout"),
    ])


class AvocadoBinary(BinarySensorEntity):
    """Expose central safety state."""

    def __init__(self, entry: ConfigEntry, key: str, name: str, state_key: str) -> None:
        self._entry = entry
        self._state_key = state_key
        self._attr_name = f"Avocado {name}"
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_class = "problem" if key == "fault_lockout" else None

    @property
    def is_on(self) -> bool:
        return bool(self.hass.data[DOMAIN][self._entry.entry_id][self._state_key])
