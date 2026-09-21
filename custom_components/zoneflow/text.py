"""ZoneFlowHealthNotesText: a free-text notes field paired with
select.py's ZoneFlowHealthSelect -- together they're a pure human journal
for the zone (e.g. "yellowing on the lower leaves, watching it"), with
zero effect on watering logic. Persists through IrrigationState
(state_store.py) exactly like the health-status select, so a note
survives an HA restart the same way everything else that store holds
does.
"""
from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

# Generous but bounded -- a running journal entry, not an essay; HA's own
# state-length ceiling (255) is the hard upper limit regardless of what's
# set here.
NOTES_MAX_LENGTH = 255


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    controller = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ZoneFlowHealthNotesText(entry, controller)])


class ZoneFlowHealthNotesText(TextEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:notebook-edit-outline"
    _attr_translation_key = "health_notes"
    _attr_mode = TextMode.TEXT
    _attr_native_max = NOTES_MAX_LENGTH

    def __init__(self, entry: ConfigEntry, controller) -> None:
        self._controller = controller
        self._attr_unique_id = f"{entry.entry_id}_health_notes_text"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="ZoneFlow",
        )

    @property
    def native_value(self) -> str:
        return self._controller.store.state.health_notes

    async def async_set_value(self, value: str) -> None:
        self._controller.store.state.health_notes = value[:NOTES_MAX_LENGTH]
        await self._controller.store.async_save()
        self.async_write_ha_state()
