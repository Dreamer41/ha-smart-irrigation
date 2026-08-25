"""Control buttons for Avocado Irrigation."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([
        AvocadoButton(entry, "clear_fault", "Clear Fault Lockout"),
    ])


class AvocadoButton(ButtonEntity):
    """Manual safety reset."""

    def __init__(self, entry: ConfigEntry, key: str, name: str) -> None:
        self._entry = entry
        self._attr_name = f"Avocado {name}"
        self._attr_unique_id = f"{entry.entry_id}_{key}"

    async def async_press(self) -> None:
        self.hass.data[DOMAIN][self._entry.entry_id]["fault_lockout"] = False
        self.async_write_ha_state()
