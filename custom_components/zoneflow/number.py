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

import math

from homeassistant.components.number import RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import async_get as async_get_restore_data
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import units
from . import greenhouse_logic
from .const import CONF_INITIAL_NUMBERS, DOMAIN, GREENHOUSE_NUMBERS, MOISTURE_ONLY_NUMBERS, NUMBER_DEFAULTS, NUMBER_DEFS
from .entity_cleanup import remove_entities


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    controller = hass.data[DOMAIN][entry.entry_id]
    has_probe = bool(controller.soil_moisture_entity)
    if not has_probe:
        # The moisture thresholds do nothing without a probe: don't create
        # them, and drop them if the probe was removed from this zone.
        remove_entities(hass, entry, "number", list(MOISTURE_ONLY_NUMBERS))
    # 1.6.1: Manual Hold Time (minutes) became Auto Resume After (hours).
    controller.migrated_hold_hours = _old_hold_hours(hass, entry)
    remove_entities(hass, entry, "number", ["manual_hold_minutes"])
    if controller.is_outdoor:
        # The greenhouse sliders belong to greenhouse / indoor zones only.
        remove_entities(hass, entry, "number", list(GREENHOUSE_NUMBERS))
    entities = [
        ZoneFlowNumber(entry, controller, key)
        for key in NUMBER_DEFS
        if (has_probe or key not in MOISTURE_ONLY_NUMBERS)
        and (key not in GREENHOUSE_NUMBERS or not controller.is_outdoor)
    ]
    async_add_entities(entities)


def _old_hold_hours(hass: HomeAssistant, entry: ConfigEntry) -> float | None:
    """The old Manual Hold Time as Auto Resume After: minutes rounded up to
    the next half hour, at least 0.5 h (0 -- "no hold" -- is gone)."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("number", DOMAIN, f"{entry.entry_id}_manual_hold_minutes")
    if entity_id is None:
        return None
    stored = async_get_restore_data(hass).last_states.get(entity_id)
    if stored is None:
        return None
    try:
        minutes = float((stored.extra_data.as_dict() if stored.extra_data else {}).get("native_value"))
    except (TypeError, ValueError):
        try:
            minutes = float(stored.state.state)
        except (TypeError, ValueError):
            return None
    return max(0.5, math.ceil(minutes / 30.0) / 2.0)


class ZoneFlowNumber(RestoreNumber):
    """Always holds its value in metric (`metric_value`, what the controller
    reads); shows and accepts it in the zone's display units (units.py)."""

    _attr_entity_category = EntityCategory.CONFIG

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, controller, key: str) -> None:
        name, min_v, max_v, step, unit = NUMBER_DEFS[key]
        self._key = key
        self._controller = controller
        self._entry = entry
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
            # Only the fallback temperature, on a zone with no normal band
            # to seed it from (see ZoneFlowController._seed_fallback_temp).
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
            # First time: the value chosen at setup (the climate step), else
            # the default. The fallback temperature of a zone set up before
            # it existed is seeded by ZoneFlowController._seed_fallback_temp.
            # Setup's values, then any added later (an outdoor zone changed to
            # a greenhouse is seeded from its climate, config_flow zone_type).
            initial = {
                **(self._entry.data.get(CONF_INITIAL_NUMBERS) or {}),
                **(self._entry.options.get(CONF_INITIAL_NUMBERS) or {}),
            }.get(self._key)
            migrated = getattr(self._controller, "migrated_hold_hours", None)
            if initial is not None:
                self.metric_value = float(initial)
            elif self._key == "auto_resume_hours" and migrated is not None:
                self.metric_value = migrated
            elif self._key == "fallback_temp":
                self.metric_value = None
            else:
                self.metric_value = NUMBER_DEFAULTS[self._key]
        self._controller.register_number(self._key, self)

    async def async_set_native_value(self, value: float) -> None:
        metric = units.to_metric(self._key, value, self._imperial)
        # Cool must stay below hot, or the normal band disappears (and the
        # hot check, which runs first, would swallow the cool tier).
        if self._key == "cool_temp_threshold" and metric >= self._controller.number("hot_temp_threshold") - 0.01:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="cool_not_below_hot")
        if self._key == "hot_temp_threshold" and metric <= self._controller.number("cool_temp_threshold") + 0.01:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="cool_not_below_hot")
        if self._key in GREENHOUSE_NUMBERS:
            self._check_climate_order(metric)
        self.metric_value = metric
        self.async_write_ha_state()
        self._controller.number_changed(self._key)

    def _check_climate_order(self, metric: float) -> None:
        """Heating must stop well before venting starts, fans at or after
        vents, misting's humidity band inside its stop (greenhouse_logic)."""
        controller = self._controller
        values = {
            "heat_temp": controller.number("heat_temp"), "vent_temp": controller.number("vent_temp"),
            "fan_temp": controller.number("fan_temp"), "hysteresis": controller.number("climate_hysteresis"),
            "mist_min_humidity": controller.number("mist_min_humidity"),
            "mist_stop_humidity": controller.number("mist_stop_humidity"),
            "max_humidity": controller.number("max_humidity"),
        }
        field = "hysteresis" if self._key == "climate_hysteresis" else self._key
        if field in values:
            values[field] = metric
        error = greenhouse_logic.check_setpoints(greenhouse_logic.Settings(**values))
        if error is not None:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key=error)

    async def async_set_metric_value(self, value: float) -> None:
        """Set in metric regardless of display units (self-tuning, presets)."""
        self.metric_value = value
        self.async_write_ha_state()
        self._controller.number_changed(self._key)
