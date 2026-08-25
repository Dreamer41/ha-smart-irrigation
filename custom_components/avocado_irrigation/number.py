"""Tunable number entities for Avocado Irrigation."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

SETTINGS = (
    ("weekly_target_mm", "Weekly Target", 1.0, 50.0, 0.5, "mm", 12.0),
    ("rain_efficiency", "Rain Efficiency", 0.0, 1.0, 0.05, None, 0.75),
    ("flow_rate_mm_per_min", "Flow Rate", 0.05, 2.0, 0.01, "mm/min", 0.30),
    ("deep_soak_target_mm", "Deep Soak Target", 15.0, 40.0, 1.0, "mm", 25.0),
    ("pump_min_watts", "Pump Warning Threshold", 20.0, 500.0, 10.0, "W", 100.0),
    ("max_runtime_minutes", "Routine Max Runtime", 10.0, 120.0, 5.0, "min", 60.0),
    ("deep_soak_max_runtime_minutes", "Deep Soak Max Runtime", 30.0, 180.0, 10.0, "min", 120.0),
    ("routine_drydown_days", "Routine Dry-Down", 1.0, 10.0, 0.5, "d", 4.0),
    ("deep_soak_drydown_days", "Deep Soak Dry-Down", 4.0, 14.0, 0.5, "d", 8.0),
    ("deep_soak_rain_threshold_mm", "Deep Soak Rain Ceiling", 0.0, 100.0, 5.0, "mm", 40.0),
    ("hot_temperature_c", "Hot Temperature Threshold", 25.0, 40.0, 0.1, "°C", 31.5),
    ("rain_mm_per_tip", "Rain mm per Tip", 0.05, 1.0, 0.001, "mm", 0.30),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([AvocadoNumber(entry, *setting) for setting in SETTINGS])


class AvocadoNumber(NumberEntity):
    """Persistent tuning parameter backed by config-entry options."""

    def __init__(self, entry: ConfigEntry, key: str, name: str, minimum: float, maximum: float, step: float, unit: str | None, default: float) -> None:
        self._entry = entry
        self._key = key
        self._default = default
        self._attr_name = f"Avocado {name}"
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> float:
        return float(self._entry.options.get(self._key, self._entry.data.get(self._key, self._default)))

    async def async_set_native_value(self, value: float) -> None:
        self.hass.config_entries.async_update_entry(self._entry, options={**self._entry.options, self._key: value})
        if self._key == "rain_mm_per_tip":
            data = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id)
            if data and data.get("rain"):
                data["rain"].mm_per_tip = value
        self.async_write_ha_state()
