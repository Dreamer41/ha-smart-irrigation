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

from . import units
from .const import DOMAIN, MOISTURE_ONLY_NUMBERS, NUMBER_DEFAULTS, NUMBER_DEFS
from .entity_cleanup import remove_entities


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    controller = hass.data[DOMAIN][entry.entry_id]
    has_probe = bool(controller.soil_moisture_entity)
    if not has_probe:
        # The moisture thresholds do nothing without a probe: don't create
        # them, and drop them if the probe was removed from this zone.
        remove_entities(hass, entry, "number", list(MOISTURE_ONLY_NUMBERS))
    entities = [
        ZoneFlowNumber(entry, controller, key)
        for key in NUMBER_DEFS
        if has_probe or key not in MOISTURE_ONLY_NUMBERS
    ]
    async_add_entities(entities)


class ZoneFlowNumber(RestoreNumber):
    """Always holds its value in metric (`metric_value`, what the controller
    reads); shows and accepts it in the zone's display units (units.py)."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, controller, key: str) -> None:
        name, min_v, max_v, step, unit = NUMBER_DEFS[key]
        self._key = key
        self._controller = controller
        self._metric_min, self._metric_max, self._metric_step, self._metric_unit = min_v, max_v, step, unit
        self.metric_value: float | None = None
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key  # see translations/<lang>.json's entity.number.<key>.name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="ZoneFlow",
        )

    @property
    def _imperial(self) -> bool:
        return self._controller.imperial

    @property
    def native_value(self) -> float | None:
        if self.metric_value is None:
            return None
        return units.display_value(self._key, self.metric_value, self._metric_step, self._imperial)

    @property
    def native_min_value(self) -> float:
        return units.display_range(self._key, self._metric_min, self._metric_max, self._metric_step, self._imperial)[0]

    @property
    def native_max_value(self) -> float:
        return units.display_range(self._key, self._metric_min, self._metric_max, self._metric_step, self._imperial)[1]

    @property
    def native_step(self) -> float:
        return units.step(self._key, self._metric_step, self._imperial)

    @property
    def native_unit_of_measurement(self) -> str | None:
        return units.unit(self._key, self._metric_unit, self._imperial)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            # Saved in whatever unit it showed then -- convert back to metric.
            self.metric_value = units.metric_from_saved(self._key, last.native_value, last.native_unit_of_measurement)
        else:
            self.metric_value = NUMBER_DEFAULTS[self._key]
        self._controller.register_number(self._key, self)

    async def async_set_native_value(self, value: float) -> None:
        self.metric_value = units.to_metric(self._key, value, self._imperial)
        self.async_write_ha_state()

    async def async_set_metric_value(self, value: float) -> None:
        """Set in metric regardless of display units (self-tuning, presets)."""
        self.metric_value = value
        self.async_write_ha_state()
