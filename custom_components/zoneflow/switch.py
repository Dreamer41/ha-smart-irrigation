"""Runtime toggle(s) that live on the dashboard, for settings a person
would reasonably want to flip themselves without reopening the
integration's Options flow every time.

Currently just the deep-soak on/off switch (const.py's CONF_DEEP_SOAK_ENABLED)
-- see run_deep_soak()'s gate in controller.py for what flipping it does.
Everything else that's "set once and rarely touched again" (soil type,
growth-ramp profile, entity selections) stays in the config/options flow;
this platform is specifically for the handful of things worth a direct
switch.
"""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

from .const import CONF_DEEP_SOAK_ENABLED, DOMAIN
from .controller import ZoneFlowController


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    controller: ZoneFlowController = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ZoneFlowDeepSoakEnabledSwitch(entry, controller), ZoneFlowDeficitModeSwitch(entry, controller)])


class ZoneFlowDeficitModeSwitch(SwitchEntity):
    """Deficit mode (regulated deficit irrigation): trims each routine dose
    to the Deficit Mode Water % -- see calculations.deficit_factor for the
    guardrails. Kept in the zone's saved state rather than its options, so
    flipping it doesn't reload the zone."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:water-minus"

    def __init__(self, entry: ConfigEntry, controller: ZoneFlowController) -> None:
        self._controller = controller
        self._attr_unique_id = f"{entry.entry_id}_deficit_mode"
        self._attr_translation_key = "deficit_mode"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=entry.title)

    @property
    def is_on(self) -> bool:
        return self._controller.store.state.deficit_enabled

    async def async_turn_on(self, **kwargs) -> None:
        state = self._controller.store.state
        state.deficit_enabled = True
        # An end date already in the past would switch it straight off again.
        if state.deficit_until_ts is not None and state.deficit_until_ts <= dt_util.utcnow().timestamp():
            state.deficit_until_ts = None
        await self._controller.store.async_save()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._controller.store.state.deficit_enabled = False
        await self._controller.store.async_save()
        self.async_write_ha_state()


class ZoneFlowDeepSoakEnabledSwitch(SwitchEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:waves"

    def __init__(self, entry: ConfigEntry, controller: ZoneFlowController) -> None:
        self._entry = entry
        self._controller = controller
        self._attr_unique_id = f"{entry.entry_id}_deep_soak_enabled"
        self._attr_translation_key = "deep_soak_enabled"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=entry.title)

    @property
    def is_on(self) -> bool:
        return self._controller.deep_soak_enabled

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)

    async def _set(self, value: bool) -> None:
        # Writing into entry.options (not just flipping a local attribute)
        # is what makes this the same source of truth as the config flow's
        # "Enable the deep soak cycle" field -- either one changing it is
        # immediately reflected in the other, and both go through the
        # entry's existing update-listener reload (see __init__.py's
        # _async_update_listener), so nothing about the reload/reconfigure
        # path needs a special case just because a switch triggered it
        # instead of the Options form.
        self.hass.config_entries.async_update_entry(
            self._entry, options={**self._entry.options, CONF_DEEP_SOAK_ENABLED: value}
        )
