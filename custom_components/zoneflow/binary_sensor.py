"""Lock/fault indicators — ports of input_boolean.irrigation_in_progress
and input_boolean.avocado_irrigation_abort, now internal controller state
instead of generic helpers."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity_cleanup import remove_entities


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    controller = hass.data[DOMAIN][entry.entry_id]
    entities = [
        ZoneFlowLockBinarySensor(entry, controller),
        ZoneFlowAbortBinarySensor(entry, controller),
    ]
    if controller.is_outdoor:
        remove_entities(hass, entry, "binary_sensor", ["ventilation_allowed"])
    else:
        entities.append(ZoneFlowVentilationAllowedBinarySensor(entry, controller))
    async_add_entities(entities)


class _Base(BinarySensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_should_poll = True

    def __init__(self, entry: ConfigEntry, controller) -> None:
        self._controller = controller
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=entry.title)


class ZoneFlowLockBinarySensor(_Base):
    _attr_icon = "mdi:lock"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_irrigation_in_progress"
        self._attr_translation_key = "irrigation_in_progress"

    @property
    def is_on(self) -> bool:
        return self._controller.store.state.lock_on


class ZoneFlowAbortBinarySensor(_Base):
    _attr_icon = "mdi:alert-octagon"
    _attr_device_class = "problem"

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_irrigation_abort"
        self._attr_translation_key = "irrigation_abort"

    @property
    def is_on(self) -> bool:
        return self._controller.store.state.abort_on


class ZoneFlowVentilationAllowedBinarySensor(_Base):
    """On while outside air may be used to cool or dry (it is cooler than
    inside by the margin, or there is no outside sensor); off when it would
    only bring in hotter air."""

    _attr_icon = "mdi:window-open-variant"
    _attr_should_poll = False
    _attr_entity_category = None

    def __init__(self, entry: ConfigEntry, controller) -> None:
        super().__init__(entry, controller)
        self._attr_unique_id = f"{entry.entry_id}_ventilation_allowed"
        self._attr_translation_key = "ventilation_allowed"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._controller.add_status_listener(self._changed))

    def _changed(self) -> None:
        if self.hass is not None:
            self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._controller.greenhouse.ventilation_allowed()

    @property
    def extra_state_attributes(self) -> dict:
        decision = self._controller.greenhouse._decision
        return {"gate": decision.gate if decision else None}
