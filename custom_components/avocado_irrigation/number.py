"""Tunable number entities for Avocado Irrigation."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

SETTINGS = (
    ("weekly_target_mm", "Weekly Target", 1.0, 50.0, 0.5, "mm"),
    ("rain_efficiency", "Rain Efficiency", 0.0, 1.0, 0.05, None),
    ("flow_rate_mm_per_min", "Flow Rate", 0.05, 2.0, 0.01, "mm/min"),
    ("deep_soak_target_mm", "Deep Soak Target", 15.0, 40.0, 1.0, "mm"),
    ("pump_min_watts", "Pump Warning Threshold", 20.0, 500.0, 10.0, "W"),
    ("max_runtime_minutes", "Routine Max Runtime", 10.0, 120.0, 5.0, "min"),
    ("deep_soak_max_runtime_minutes", "Deep Soak Max Runtime", 30.0, 180.0, 10.0, "min"),
    ("routine_drydown_days", "Routine Dry-Down", 1.0, 10.0, 0.5, "d"),
    ("deep_soak_drydown_days", "Deep Soak Dry-Down", 4.0, 14.0, 0.5, "d"),
    ("deep_soak_rain_threshold_mm", "Deep Soak Rain Ceiling", 0.0, 100.0, 5.0, "mm"),
    ("hot_temperature_c", "Hot Temperature Threshold", 25.0, 40.0, 0.1, "°C"),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([AvocadoNumber(entry, *setting) for setting in SETTINGS])


class AvocadoNumber(NumberEntity):
    """Expose a tuning parameter as a native HA number entity."""

    def __init__(self, entry: ConfigEntry, key: str, name: str, minimum: float, maximum: float, step: float, unit: str | None) -> None:
        self._entry = entry
        self._key = key
        self._attr_name = f"Avocado {name}"
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._value = float(entry.data.get(key, minimum))

    @property
    def native_value(self) -> float:
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        self._value = value
        self.async_write_ha_state()
