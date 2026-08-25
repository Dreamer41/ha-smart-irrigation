"""Diagnostic sensors for Avocado Irrigation."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import calculate_deep_soak, calculate_routine


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up calculation/diagnostic sensors."""
    async_add_entities(
        [
            AvocadoCalculationSensor(entry, "interval_target", "Interval Target", "mm"),
            AvocadoCalculationSensor(entry, "effective_rain", "Effective Rain", "mm"),
            AvocadoCalculationSensor(entry, "irrigation_deficit", "Irrigation Deficit", "mm"),
            AvocadoCalculationSensor(entry, "routine_runtime", "Calculated Routine Runtime", "min"),
            AvocadoCalculationSensor(entry, "deep_soak_runtime", "Calculated Deep Soak Runtime", "min"),
            AvocadoCalculationSensor(entry, "deep_soak_pulse", "Deep Soak Pulse Runtime", "min"),
        ]
    )


class AvocadoCalculationSensor(SensorEntity):
    """Expose calculation results for tuning and diagnostics."""

    _attr_should_poll = True

    def __init__(self, entry: ConfigEntry, key: str, name: str, unit: str) -> None:
        self._entry = entry
        self._key = key
        self._attr_name = f"Avocado {name}"
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self):
        """Calculate current value from configured settings.

        Rain/temperature source values are deliberately read live from HA. If the
        source is unavailable, the calculation falls back to zero/30 C rather than
        producing an invalid state.
        """
        config = self._entry.data
        rain_entity = config.get("rain_gauge")
        temp_entity = config.get("outdoor_temperature")
        rain_4d = 0.0
        temperature = 30.0
        if rain_entity:
            rain_4d = _state_float(self.hass, rain_entity)
        if temp_entity:
            temperature = _state_float(self.hass, temp_entity, 30.0)

        routine = calculate_routine(
            average_peak_temperature_c=temperature,
            rain_past_4d_mm=rain_4d,
            weekly_target_mm=config.get("weekly_target_mm", 12.0),
            rain_efficiency=config.get("rain_efficiency", 0.75),
            flow_rate_mm_per_min=config.get("flow_rate_mm_per_min", 0.30),
            max_runtime_minutes=config.get("max_runtime_minutes", 60),
            hot_temperature_c=config.get("hot_temperature_c", 31.5),
        )
        deep = calculate_deep_soak(
            target_mm=config.get("deep_soak_target_mm", 25.0),
            flow_rate_mm_per_min=config.get("flow_rate_mm_per_min", 0.30),
            max_runtime_minutes=config.get("deep_soak_max_runtime_minutes", 120),
        )

        return {
            "interval_target": routine.interval_target_mm,
            "effective_rain": routine.effective_rain_mm,
            "irrigation_deficit": routine.needed_mm,
            "routine_runtime": routine.runtime_minutes,
            "deep_soak_runtime": deep.total_runtime_minutes,
            "deep_soak_pulse": deep.pulse_runtime_minutes,
        }[self._key]


def _state_float(hass: HomeAssistant, entity_id: str, default: float = 0.0) -> float:
    """Return an entity state as float."""
    try:
        value = hass.states.get(entity_id)
        if value is None:
            return default
        return float(value.state)
    except (TypeError, ValueError):
        return default
