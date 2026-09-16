"""Config + options flow.

Setup is two steps: first a short zone name (so multiple zones show up as
distinct, distinguishable devices and don't collide on the default CSV
filename), then the real entities (valve switch, pump power sensor, rain
tip counter, outdoor temp sensor) -- it never creates new physical entities
of its own. Adding a second zone is just adding this integration again with
a different name/entities; each zone is its own independent config entry.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import (
    CONF_CSV_PATH,
    CONF_DEEP_SOAK_SUN_MODE,
    CONF_DEEP_SOAK_SUN_OFFSET_MINUTES,
    CONF_DEEP_SOAK_TIME,
    CONF_NOTIFY_ENTITY,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_PUMP_POWER_ENTITY,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_ROUTINE_SUN_MODE,
    CONF_ROUTINE_SUN_OFFSET_MINUTES,
    CONF_ROUTINE_TIME,
    CONF_VALVE_ENTITY,
    CONF_WEATHER_ENTITY,
    CONF_ZONE_NAME,
    DEFAULT_CSV_PATH,
    DEFAULT_DEEP_SOAK_TIME,
    DEFAULT_ROUTINE_TIME,
    DEFAULT_SUN_MODE,
    DEFAULT_SUN_OFFSET_MINUTES,
    DOMAIN,
    SUN_MODE_OPTIONS,
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
    # Same optional-with-no-fake-default pattern as notify_entity above --
    # this zone works exactly as before if you never touch this field. When
    # set, it enables the forecast gate (skip a scheduled run pre-emptively
    # when rain is forecast) and the dry-spell override numbers below become
    # relevant; when unset, those numbers are simply unused.
    weather_default = defaults.get(CONF_WEATHER_ENTITY)
    weather_key = (
        vol.Optional(CONF_WEATHER_ENTITY, default=weather_default)
        if weather_default
        else vol.Optional(CONF_WEATHER_ENTITY)
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
            weather_key: selector.EntitySelector(selector.EntitySelectorConfig(domain="weather")),
            vol.Required(CONF_CSV_PATH, default=defaults.get(CONF_CSV_PATH, DEFAULT_CSV_PATH)): str,
            vol.Required(
                CONF_DEEP_SOAK_TIME, default=defaults.get(CONF_DEEP_SOAK_TIME, DEFAULT_DEEP_SOAK_TIME)
            ): selector.TimeSelector(),
            vol.Required(
                CONF_ROUTINE_TIME, default=defaults.get(CONF_ROUTINE_TIME, DEFAULT_ROUTINE_TIME)
            ): selector.TimeSelector(),
            # Sun-relative scheduling is optional and additive: mode "fixed"
            # (the default) means the *_TIME fields above are what fires, so
            # a zone that never touches these two pairs behaves exactly as
            # it always has.
            vol.Required(
                CONF_DEEP_SOAK_SUN_MODE, default=defaults.get(CONF_DEEP_SOAK_SUN_MODE, DEFAULT_SUN_MODE)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=SUN_MODE_OPTIONS, translation_key="sun_mode")
            ),
            vol.Required(
                CONF_DEEP_SOAK_SUN_OFFSET_MINUTES,
                default=defaults.get(CONF_DEEP_SOAK_SUN_OFFSET_MINUTES, DEFAULT_SUN_OFFSET_MINUTES),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=180, step=5, unit_of_measurement="min")
            ),
            vol.Required(
                CONF_ROUTINE_SUN_MODE, default=defaults.get(CONF_ROUTINE_SUN_MODE, DEFAULT_SUN_MODE)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=SUN_MODE_OPTIONS, translation_key="sun_mode")
            ),
            vol.Required(
                CONF_ROUTINE_SUN_OFFSET_MINUTES,
                default=defaults.get(CONF_ROUTINE_SUN_OFFSET_MINUTES, DEFAULT_SUN_OFFSET_MINUTES),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=180, step=5, unit_of_measurement="min")
            ),
        }
    )


class ZoneFlowConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._zone_name: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            zone_name = user_input[CONF_ZONE_NAME].strip()
            if not zone_name:
                errors["base"] = "zone_name_required"
            else:
                self._zone_name = zone_name
                return await self.async_step_entities()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ZONE_NAME, default=self._zone_name or ""): str}),
            errors=errors,
        )

    async def async_step_entities(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            for key in (CONF_DEEP_SOAK_TIME, CONF_ROUTINE_TIME):
                if len(user_input[key].split(":")) == 2:
                    user_input[key] = f"{user_input[key]}:00"
            user_input[CONF_ZONE_NAME] = self._zone_name
            return self.async_create_entry(title=self._zone_name, data=user_input)
        # Default CSV path is zone-specific so two zones never silently
        # write into the same log file if the user just accepts defaults.
        default_csv = f"/config/zoneflow_{slugify(self._zone_name)}.csv"
        return self.async_show_form(
            step_id="entities",
            data_schema=_schema({CONF_CSV_PATH: default_csv}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ZoneFlowOptionsFlow(config_entry)


class ZoneFlowOptionsFlow(config_entries.OptionsFlow):
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
