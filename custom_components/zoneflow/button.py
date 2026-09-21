"""Manual controls. Each button calls the exact same controller coroutine
the scheduled time triggers use, so a manual run can never drift from a
scheduled one — the two are the same code path."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    controller = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            ZoneFlowButton(entry, controller, "run_deep_soak", "Run Deep Soak Now", controller.run_deep_soak),
            ZoneFlowButton(
                entry,
                controller,
                "run_routine",
                "Run Routine Irrigation Now",
                # manual=True feeds the self-tuning "early" signal -- see
                # controller.py's run_routine_irrigation/_register_self_tune_signal.
                lambda: controller.run_routine_irrigation(manual=True),
            ),
            ZoneFlowButton(entry, controller, "reset_lock", "Reset Irrigation Lock", controller.reset_lock),
            ZoneFlowButton(entry, controller, "snooze_today", "Snooze Today", controller.snooze_today),
        ]
    )


class ZoneFlowButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, controller, key: str, name: str, action) -> None:
        self._action = action
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key  # see translations/<lang>.json's entity.button.<key>.name
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=entry.title)

    async def async_press(self) -> None:
        await self._action()
