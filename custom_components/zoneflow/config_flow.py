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
    CONF_DEEP_SOAK_ENABLED,
    CONF_DEEP_SOAK_SUN_MODE,
    CONF_DEEP_SOAK_SUN_OFFSET_MINUTES,
    CONF_DEEP_SOAK_TIME,
    CONF_DRAINAGE,
    CONF_FLOW_METER_ENTITY,
    CONF_GROWTH_RAMP_PROFILE,
    CONF_IRRIGATION_METHOD,
    CONF_NOTIFY_ENTITY,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_PUMP_ID,
    CONF_PUMP_POWER_ENTITY,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_ROUTINE_SUN_MODE,
    CONF_ROUTINE_SUN_OFFSET_MINUTES,
    CONF_ROUTINE_TIME,
    CONF_SLOPE,
    CONF_SOIL_TYPE,
    CONF_VALVE_ENTITY,
    CONF_WEATHER_ENTITY,
    CONF_ZONE_NAME,
    DEFAULT_CSV_PATH,
    DEFAULT_DEEP_SOAK_ENABLED,
    DEFAULT_DEEP_SOAK_TIME,
    DEFAULT_DRAINAGE,
    DEFAULT_GROWTH_RAMP_PROFILE,
    DEFAULT_IRRIGATION_METHOD,
    DEFAULT_ROUTINE_TIME,
    DEFAULT_SLOPE,
    DEFAULT_SOIL_TYPE,
    DEFAULT_SUN_MODE,
    DEFAULT_SUN_OFFSET_MINUTES,
    DOMAIN,
    DRAINAGE_OPTIONS,
    GROWTH_RAMP_PROFILE_OPTIONS,
    IRRIGATION_METHOD_OPTIONS,
    SLOPE_OPTIONS,
    SOIL_TYPE_OPTIONS,
    SUN_MODE_OPTIONS,
)


def _optional_entity_key(defaults: dict[str, Any], conf_key: str):
    """Shared pattern for every genuinely-optional entity field: passing
    default=None into vol.Optional() for an EntitySelector makes the
    frontend try to validate the literal string "None" as an entity ID/UUID
    ("Entity None is neither a valid entity ID nor a valid UUID") -- so only
    attach a default when one actually exists; otherwise leave the key
    truly unset and let the marker default to nothing selected."""
    value = defaults.get(conf_key)
    return vol.Optional(conf_key, default=value) if value else vol.Optional(conf_key)


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    # The valve is the only entity that is truly mandatory -- ZoneFlow
    # cannot irrigate without something to open. Every other entity below
    # degrades gracefully when left unset (see controller.py): rain-aware
    # gates simply never fire without a rain gauge, hot/cool tiers fall
    # back to "normal" without a temp sensor, the pump-audit watchdog is
    # skipped without a pump-power or flow-meter reading, and the forecast
    # gate is skipped without a weather entity. The AI setup guide explains
    # exactly what capability is lost by skipping each one.
    notify_key = _optional_entity_key(defaults, CONF_NOTIFY_ENTITY)
    weather_key = _optional_entity_key(defaults, CONF_WEATHER_ENTITY)
    pump_power_key = _optional_entity_key(defaults, CONF_PUMP_POWER_ENTITY)
    rain_counter_key = _optional_entity_key(defaults, CONF_RAIN_COUNTER_ENTITY)
    outdoor_temp_key = _optional_entity_key(defaults, CONF_OUTDOOR_TEMP_ENTITY)
    flow_meter_key = _optional_entity_key(defaults, CONF_FLOW_METER_ENTITY)

    return vol.Schema(
        {
            vol.Required(CONF_VALVE_ENTITY, default=defaults.get(CONF_VALVE_ENTITY)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="switch")
            ),
            pump_power_key: selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            # Plain text, not an entity selector -- this identifies the
            # physical pump (e.g. "Pump A"), independent of whether a
            # wattage sensor exists for it. See const.py's CONF_PUMP_ID
            # comment. Blank is a valid, common answer (single-pump/
            # independent-pump setups never need this).
            vol.Optional(CONF_PUMP_ID, default=defaults.get(CONF_PUMP_ID, "")): str,
            rain_counter_key: selector.EntitySelector(selector.EntitySelectorConfig(domain=["counter", "sensor"])),
            outdoor_temp_key: selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
            ),
            flow_meter_key: selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            notify_key: selector.EntitySelector(selector.EntitySelectorConfig(domain="notify")),
            weather_key: selector.EntitySelector(selector.EntitySelectorConfig(domain="weather")),
            # Descriptive soil/site metadata -- see const.py's comment on
            # CONF_SOIL_TYPE for why these never drive scheduler logic
            # directly. "unknown"/"flat"/"drip" are always valid answers,
            # so these are vol.Required only in the sense that the field
            # always has SOME value, never in the sense of blocking setup.
            vol.Required(CONF_SOIL_TYPE, default=defaults.get(CONF_SOIL_TYPE, DEFAULT_SOIL_TYPE)): selector.SelectSelector(
                selector.SelectSelectorConfig(options=SOIL_TYPE_OPTIONS, translation_key="soil_type")
            ),
            vol.Required(CONF_DRAINAGE, default=defaults.get(CONF_DRAINAGE, DEFAULT_DRAINAGE)): selector.SelectSelector(
                selector.SelectSelectorConfig(options=DRAINAGE_OPTIONS, translation_key="drainage")
            ),
            vol.Required(CONF_SLOPE, default=defaults.get(CONF_SLOPE, DEFAULT_SLOPE)): selector.SelectSelector(
                selector.SelectSelectorConfig(options=SLOPE_OPTIONS, translation_key="slope")
            ),
            vol.Required(
                CONF_IRRIGATION_METHOD, default=defaults.get(CONF_IRRIGATION_METHOD, DEFAULT_IRRIGATION_METHOD)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=IRRIGATION_METHOD_OPTIONS, translation_key="irrigation_method")
            ),
            # Off by default. See const.py's GROWTH_RAMP_CURVES comment --
            # this scales the weekly target by a days-since-planting curve
            # as a starting approximation, never as a replacement for the
            # number entity staying manually overridable.
            vol.Required(
                CONF_GROWTH_RAMP_PROFILE, default=defaults.get(CONF_GROWTH_RAMP_PROFILE, DEFAULT_GROWTH_RAMP_PROFILE)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=GROWTH_RAMP_PROFILE_OPTIONS, translation_key="growth_ramp_profile"
                )
            ),
            vol.Required(CONF_CSV_PATH, default=defaults.get(CONF_CSV_PATH, DEFAULT_CSV_PATH)): str,
            # Off-switch for the whole deep-soak cycle -- see const.py's
            # comment on CONF_DEEP_SOAK_ENABLED for why this defaults True
            # rather than following growth-ramp's off-by-default pattern.
            # The two fields below (time/sun-mode) are simply unused while
            # this is False.
            vol.Required(
                CONF_DEEP_SOAK_ENABLED, default=defaults.get(CONF_DEEP_SOAK_ENABLED, DEFAULT_DEEP_SOAK_ENABLED)
            ): selector.BooleanSelector(),
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
