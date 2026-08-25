"""Rainfall and irrigation diagnostic sensors."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import calculate_deep_soak, calculate_routine


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entities = []
    for key, name, unit in (
        ("rain_lifetime", "Rain Lifetime", "mm"),
        ("rain_24h", "Rain Past 24h", "mm"),
        ("rain_4d", "Rain Past 4d", "mm"),
        ("rain_7d", "Rain Past 7d", "mm"),
        ("rain_14d", "Rain Past 14d", "mm"),
        ("interval_target", "Interval Target", "mm"),
        ("effective_rain", "Effective Rain", "mm"),
        ("irrigation_deficit", "Irrigation Deficit", "mm"),
        ("routine_runtime", "Calculated Routine Runtime", "min"),
        ("deep_soak_runtime", "Calculated Deep Soak Runtime", "min"),
        ("deep_soak_pulse", "Deep Soak Pulse Runtime", "min"),
    ):
        entities.append(AvocadoSensor(entry, key, name, unit))
    async_add_entities(entities)


class AvocadoSensor(SensorEntity):
    """Expose live rainfall and reference calculation diagnostics."""

    _attr_should_poll = True

    def __init__(self, entry: ConfigEntry, key: str, name: str, unit: str) -> None:
        self._entry = entry
        self._key = key
        self._attr_name = f"Avocado {name}"
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = "measurement"
        if key == "rain_lifetime":
            self._attr_state_class = "total_increasing"
            self._attr_device_class = "precipitation"

    @property
    def native_value(self):
        data = self.hass.data[DOMAIN][self._entry.entry_id]
        rain = data["rain"]
        if self._key == "rain_lifetime":
            return rain.lifetime_mm
        if self._key.startswith("rain_"):
            hours = {"rain_24h": 24, "rain_4d": 96, "rain_7d": 168, "rain_14d": 336}[self._key]
            return rain.rainfall(hours)

        config = data["config"]
        temperature = _state_float(self.hass, config.get("outdoor_temperature"), 30.0)
        routine = calculate_routine(
            average_peak_temperature_c=temperature,
            rain_past_4d_mm=rain.rainfall(96),
            weekly_target_mm=float(config.get("weekly_target_mm", 12.0)),
            rain_efficiency=float(config.get("rain_efficiency", 0.75)),
            flow_rate_mm_per_min=float(config.get("flow_rate_mm_per_min", 0.30)),
            max_runtime_minutes=int(config.get("max_runtime_minutes", 60)),
            hot_temperature_c=float(config.get("hot_temperature_c", 31.5)),
        )
        deep = calculate_deep_soak(
            target_mm=float(config.get("deep_soak_target_mm", 25.0)),
            flow_rate_mm_per_min=float(config.get("flow_rate_mm_per_min", 0.30)),
            max_runtime_minutes=int(config.get("deep_soak_max_runtime_minutes", 120)),
        )
        return {
            "interval_target": routine.interval_target_mm,
            "effective_rain": routine.effective_rain_mm,
            "irrigation_deficit": routine.needed_mm,
            "routine_runtime": routine.runtime_minutes,
            "deep_soak_runtime": deep.total_runtime_minutes,
            "deep_soak_pulse": deep.pulse_runtime_minutes,
        }[self._key]


def _state_float(hass: HomeAssistant, entity_id: str | None, default: float) -> float:
    if not entity_id:
        return default
    try:
        state = hass.states.get(entity_id)
        return float(state.state) if state else default
    except (TypeError, ValueError):
        return default
