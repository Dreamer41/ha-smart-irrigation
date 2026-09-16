"""Config + options flow. Setup just points the integration at your real
entities (valve switch, pump power sensor, rain tip counter, outdoor temp
sensor) — it never creates new physical entities of its own."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CSV_PATH,
    CONF_DEEP_SOAK_TIME,
    CONF_NOTIFY_ENTITY,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_PUMP_POWER_ENTITY,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_ROUTINE_TIME,
    CONF_VALVE_ENTITY,
    DEFAULT_CSV_PATH,
    DEFAULT_DEEP_SOAK_TIME,
    DEFAULT_ROUTINE_TIME,
    DOMAIN,
)


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    # CONF_NOTIFY_ENTITY is genuinely optional (there may be no phone to
    # notify). Passing default=None into vol.Optional() for an
    # EntitySelector makes the frontend try to validate the literal string
    # "None" as an entity ID/UUID ("Entity None is neither a valid entity ID
    # nor a valid UUID") -- so only attach a default when one actually
    # exists; otherwise leave the key truly unset and let the marker default
    # to nothing selected.
    notify_default = defaults.get(CONF_NOTIFY_ENTITY)
    notify_key = (
        vol.Optional(CONF_NOTIFY_ENTITY, default=notify_default)
        if notify_default
        else vol.Optional(CONF_NOTIFY_ENTITY)
    )

    return vol.Schema(
        {
            vol.Required(CONF_VALVE_ENTITY, default=defaults.get(CONF_VALVE_ENTITY)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="switch")
            ),
            vol.Required(
                CONF_PUMP_POWER_ENTITY, default=defaults.get(CONF_PUMP_POWER_ENTITY)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Required(
                CONF_RAIN_COUNTER_ENTITY, default=defaults.get(CONF_RAIN_COUNTER_ENTITY)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain=["counter", "sensor"])),
            vol.Required(
                CONF_OUTDOOR_TEMP_ENTITY, default=defaults.get(CONF_OUTDOOR_TEMP_ENTITY)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="temperature")),
            notify_key: selector.EntitySelector(selector.EntitySelectorConfig(domain="notify")),
            vol.Required(CONF_CSV_PATH, default=defaults.get(CONF_CSV_PATH, DEFAULT_CSV_PATH)): str,
            vol.Required(
                CONF_DEEP_SOAK_TIME, default=defaults.get(CONF_DEEP_SOAK_TIME, DEFAULT_DEEP_SOAK_TIME)
            ): selector.TimeSelector(),
            vol.Required(
                CONF_ROUTINE_TIME, default=defaults.get(CONF_ROUTINE_TIME, DEFAULT_ROUTINE_TIME)
            ): selector.TimeSelector(),
        }
    )


class AvocadoIrrigationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            for key in (CONF_DEEP_SOAK_TIME, CONF_ROUTINE_TIME):
                if len(user_input[key].split(":")) == 2:
                    user_input[key] = f"{user_input[key]}:00"
            return self.async_create_entry(title="Avocado Irrigation", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema({}), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return AvocadoIrrigationOptionsFlow(config_entry)


class AvocadoIrrigationOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            for key in (CONF_DEEP_SOAK_TIME, CONF_ROUTINE_TIME):
                if len(user_input[key].split(":")) == 2:
                    user_input[key] = f"{user_input[key]}:00"
            return self.async_create_entry(title="", data=user_input)
        defaults = {**self._config_entry.data, **self._config_entry.options}
        return self.async_show_form(step_id="init", data_schema=_schema(defaults))
