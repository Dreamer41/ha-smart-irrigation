"""Control buttons for Avocado Irrigation."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([
        AvocadoButton(entry, "run_routine", "Run Routine Now", "run_routine"),
        AvocadoButton(entry, "run_deep_soak", "Run Deep Soak Now", "run_deep_soak"),
        AvocadoButton(entry, "clear_fault", "Clear Fault Lockout", "clear_fault"),
    ])


class AvocadoButton(ButtonEntity):
    """Manual irrigation controls."""

    def __init__(self, entry: ConfigEntry, key: str, name: str, action: str) -> None:
        self._entry = entry
        self._action = action
        self._attr_name = f"Avocado {name}"
        self._attr_unique_id = f"{entry.entry_id}_{key}"

    async def async_press(self) -> None:
        controller = self.hass.data[DOMAIN][self._entry.entry_id]["controller"]
        if self._action == "run_routine":
            await controller.run_routine(force=True)
        elif self._action == "run_deep_soak":
            await controller.run_deep_soak(force=True)
        else:
            await controller.clear_fault()
