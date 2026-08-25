"""Config flow for Avocado Irrigation."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    CONF_IRRIGATION_VALVE,
    CONF_NAME,
    CONF_OUTDOOR_TEMPERATURE,
    CONF_PUMP_POWER,
    CONF_RAIN_GAUGE,
    DEFAULT_DEEP_SOAK_DRYDOWN_DAYS,
    DEFAULT_DEEP_SOAK_MAX_RUNTIME_MIN,
    DEFAULT_DEEP_SOAK_RAIN_THRESHOLD_MM,
    DEFAULT_DEEP_SOAK_TARGET_MM,
    DEFAULT_FLOW_RATE_MM_PER_MIN,
    DEFAULT_HOT_TEMPERATURE_C,
    DEFAULT_MAX_RUNTIME_MIN,
    DEFAULT_PUMP_MIN_WATTS,
    DEFAULT_RAIN_EFFICIENCY,
    DEFAULT_ROUTINE_DRYDOWN_DAYS,
    DEFAULT_WEEKLY_TARGET_MM,
    DOMAIN,
)


class AvocadoIrrigationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Avocado Irrigation config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME, default="Avocado Irrigation"): str,
                vol.Required(CONF_IRRIGATION_VALVE): selector.EntitySelector(selector.EntitySelectorConfig(domain="switch")),
                vol.Required(CONF_RAIN_GAUGE): selector.EntitySelector(selector.EntitySelectorConfig(domain=["binary_sensor", "counter"])),
                vol.Optional(CONF_PUMP_POWER): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(CONF_OUTDOOR_TEMPERATURE): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
                ),
                vol.Required("weekly_target_mm", default=DEFAULT_WEEKLY_TARGET_MM): vol.All(vol.Coerce(float), vol.Range(min=1, max=50)),
                vol.Required("rain_efficiency", default=DEFAULT_RAIN_EFFICIENCY): vol.All(vol.Coerce(float), vol.Range(min=0, max=1)),
                vol.Required("flow_rate_mm_per_min", default=DEFAULT_FLOW_RATE_MM_PER_MIN): vol.All(vol.Coerce(float), vol.Range(min=0.05, max=2)),
                vol.Required("deep_soak_target_mm", default=DEFAULT_DEEP_SOAK_TARGET_MM): vol.All(vol.Coerce(float), vol.Range(min=15, max=40)),
                vol.Required("pump_min_watts", default=DEFAULT_PUMP_MIN_WATTS): vol.All(vol.Coerce(float), vol.Range(min=20, max=500)),
                vol.Required("max_runtime_minutes", default=DEFAULT_MAX_RUNTIME_MIN): vol.All(vol.Coerce(int), vol.Range(min=10, max=120)),
                vol.Required("deep_soak_max_runtime_minutes", default=DEFAULT_DEEP_SOAK_MAX_RUNTIME_MIN): vol.All(vol.Coerce(int), vol.Range(min=30, max=180)),
                vol.Required("routine_drydown_days", default=DEFAULT_ROUTINE_DRYDOWN_DAYS): vol.All(vol.Coerce(float), vol.Range(min=1, max=10)),
                vol.Required("deep_soak_drydown_days", default=DEFAULT_DEEP_SOAK_DRYDOWN_DAYS): vol.All(vol.Coerce(float), vol.Range(min=4, max=14)),
                vol.Required("deep_soak_rain_threshold_mm", default=DEFAULT_DEEP_SOAK_RAIN_THRESHOLD_MM): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
                vol.Required("hot_temperature_c", default=DEFAULT_HOT_TEMPERATURE_C): vol.All(vol.Coerce(float), vol.Range(min=25, max=40)),
                vol.Required("rain_mm_per_tip", default=0.30): vol.All(vol.Coerce(float), vol.Range(min=0.05, max=1)),
            }),
        )
