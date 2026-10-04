"""Config + options flow.

Setup is four steps: a short zone name (so multiple zones show up as
distinct, distinguishable devices and don't collide on the default CSV
filename), the real entities (valve switch, pump power sensor, rain tip
counter, outdoor temp sensor) -- it never creates new physical entities of
its own -- then the climate, which fills in the last step: the hot/cool
temperature thresholds and the fallback temperature, as sliders in the
zone's units. Those only seed the zone's number entities; the sliders on
the device page are the source of truth afterwards. Adding a second zone is just adding this integration again with
a different name/entities; each zone is its own independent config entry.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import UnitOfTemperature
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.util import slugify

from . import calculations as calc, greenhouse_logic, units

from .const import (
    CLIMATE_NUMBER_KEYS,
    CLIMATE_OPTIONS,
    CLIMATE_PRESETS,
    CONF_CLIMATE,
    CONF_CSV_PATH,
    CONF_BACKUP_TEMP_ENTITIES,
    CONF_INITIAL_NUMBERS,
    GREENHOUSE_PRESET_NUMBER_KEYS,
    CONF_PLANT,
    FLOW_MEASURE_MINUTES,
    PLANT_CUSTOM,
    PLANT_OPTIONS,
    PLANT_PRESETS,
    CONF_DEEP_SOAK_ENABLED,
    CONF_DEEP_SOAK_SUN_MODE,
    CONF_DEEP_SOAK_SUN_OFFSET_MINUTES,
    CONF_DEEP_SOAK_TIME,
    CONF_DRAINAGE,
    CONF_FLOW_METER_ENTITY,
    CONF_GROWTH_RAMP_PROFILE,
    CONF_IRRIGATION_METHOD,
    CONF_UNIT_SYSTEM,
    CONF_NOTIFY_ENTITY,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_PUMP_ID,
    CONF_PUMP_POWER_ENTITY,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_ROUTINE_SUN_MODE,
    CONF_ROUTINE_SUN_OFFSET_MINUTES,
    CONF_ROUTINE_TIME,
    CONF_SLOPE,
    CONF_SOIL_MOISTURE_ENTITY,
    CONF_SOIL_TYPE,
    CONF_VALVE_ENTITY,
    CONF_WEATHER_ENTITY,
    CONF_INSIDE_HUMIDITY_ENTITY,
    CONF_INSIDE_TEMP_ENTITY,
    CONF_LIGHT_ENTITY,
    CONF_ZONE_NAME,
    CONF_ZONE_TYPE,
    DEFAULT_ZONE_TYPE,
    DEVICE_ROLE_DOMAINS,
    DEVICE_ROLE_KEYS,
    ZONE_TYPE_OPTIONS,
    ZONE_TYPE_OUTDOOR,
    DEFAULT_CLIMATE,
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
    NUMBER_DEFS,
    SLOPE_OPTIONS,
    SOIL_TYPE_OPTIONS,
    SUN_MODE_OPTIONS,
)


# Every genuinely optional entity field -- all but the valve.
OPTIONAL_ENTITY_KEYS = (
    CONF_PUMP_POWER_ENTITY,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_FLOW_METER_ENTITY,
    CONF_SOIL_MOISTURE_ENTITY,
    CONF_NOTIFY_ENTITY,
    CONF_WEATHER_ENTITY,
)


def _optional_entity_key(defaults: dict[str, Any], conf_key: str):
    """Shared pattern for every genuinely-optional entity field. The current
    entity is a *suggested* value, not a default: with default=, clearing
    the field in the form just brought the old entity back, so a sensor,
    once set, could never be removed. (default=None isn't an option either
    -- the frontend then validates the literal "None" as an entity ID.)"""
    value = defaults.get(conf_key)
    if value:
        return vol.Optional(conf_key, description={"suggested_value": value})
    return vol.Optional(conf_key)


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
    soil_moisture_key = _optional_entity_key(defaults, CONF_SOIL_MOISTURE_ENTITY)

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
            soil_moisture_key: selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            notify_key: selector.EntitySelector(selector.EntitySelectorConfig(domain="notify")),
            weather_key: selector.EntitySelector(selector.EntitySelectorConfig(domain="weather")),
            # Descriptive soil/site metadata -- see const.py's comment on
            # CONF_SOIL_TYPE for why these never drive scheduler logic
            # directly. "unknown"/"flat"/"drip" are always valid answers,
            # so these are vol.Required only in the sense that the field
            # always has SOME value, never in the sense of blocking setup.
            vol.Required(
                CONF_UNIT_SYSTEM, default=defaults.get(CONF_UNIT_SYSTEM, units.UNIT_SYSTEM_AUTO)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=units.UNIT_SYSTEM_OPTIONS, translation_key="unit_system")
            ),
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


def _duplicate_errors(hass, data: dict[str, Any], *, exclude_entry_id: str | None = None) -> dict[str, str]:
    """Catch two zones pointed at the same valve, or logging to the same
    CSV file. Nothing else validates this: two zones sharing a valve get
    two independent pump locks unless they also happen to share a pump_id
    or pump_power_entity (controller.py's _pump_lock_key), so the second
    zone's watering call can race the first zone's on the very same
    switch; two zones sharing a csv_path have their controllers' unlocked
    executor-thread writes (_write_csv_row) interleave into one file."""
    errors: dict[str, str] = {}
    valve = data.get(CONF_VALVE_ENTITY)
    csv_path = data.get(CONF_CSV_PATH)
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id == exclude_entry_id:
            continue
        other = {**entry.data, **entry.options}
        if valve and CONF_VALVE_ENTITY not in errors and other.get(CONF_VALVE_ENTITY) == valve:
            errors[CONF_VALVE_ENTITY] = "valve_already_used"
        if csv_path and CONF_CSV_PATH not in errors and other.get(CONF_CSV_PATH) == csv_path:
            errors[CONF_CSV_PATH] = "csv_path_already_used"
    return errors


# What the watering step of a greenhouse or indoor zone leaves out: the
# valve has its own step, a roof has no rain gauge or forecast, watering goes
# by the inside temperature sensor, and the notify target, units and log file
# are settled with the climate hardware.
_WATERING_LEAVES_OUT = {
    CONF_VALVE_ENTITY,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_WEATHER_ENTITY,
    CONF_NOTIFY_ENTITY,
    CONF_UNIT_SYSTEM,
    CONF_CSV_PATH,
}


def _watering_schema(defaults: dict[str, Any]) -> vol.Schema:
    """The watering settings of a greenhouse or indoor zone that has a valve."""
    base = _schema(defaults)
    return vol.Schema({key: value for key, value in base.schema.items() if str(key.schema) not in _WATERING_LEAVES_OUT})


def _optional_list_key(defaults: dict[str, Any], conf_key: str):
    value = defaults.get(conf_key)
    if value:
        return vol.Optional(conf_key, description={"suggested_value": list(value)})
    return vol.Optional(conf_key)


def _devices_schema(defaults: dict[str, Any], *, with_valve: bool) -> vol.Schema:
    """Sensors and climate devices of a greenhouse or indoor zone. Setup asks
    for the valve in its own step (with_valve False); Configure shows it here."""
    fields: dict[Any, Any] = {}
    if with_valve:
        fields[_optional_entity_key(defaults, CONF_VALVE_ENTITY)] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="switch")
        )
    fields[_optional_entity_key(defaults, CONF_INSIDE_TEMP_ENTITY)] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
    )
    fields[_optional_list_key(defaults, CONF_BACKUP_TEMP_ENTITIES)] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor", device_class="temperature", multiple=True)
    )
    fields[_optional_entity_key(defaults, CONF_INSIDE_HUMIDITY_ENTITY)] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor", device_class="humidity")
    )
    fields[_optional_entity_key(defaults, CONF_LIGHT_ENTITY)] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor", device_class=["illuminance", "irradiance"])
    )
    fields[_optional_entity_key(defaults, CONF_OUTDOOR_TEMP_ENTITY)] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
    )
    for role in DEVICE_ROLE_KEYS:
        fields[_optional_list_key(defaults, role)] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=DEVICE_ROLE_DOMAINS[role], multiple=True)
        )
    fields[_optional_entity_key(defaults, CONF_NOTIFY_ENTITY)] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="notify")
    )
    fields[vol.Required(CONF_UNIT_SYSTEM, default=defaults.get(CONF_UNIT_SYSTEM, units.UNIT_SYSTEM_AUTO))] = (
        selector.SelectSelector(
            selector.SelectSelectorConfig(options=units.UNIT_SYSTEM_OPTIONS, translation_key="unit_system")
        )
    )
    return vol.Schema(fields)


def _climate_errors(hass, data: dict[str, Any], *, exclude_entry_id: str | None = None) -> dict[str, str]:
    """Climate devices need the inside temperature sensor; one entity can't
    play two roles or belong to two zones."""
    errors: dict[str, str] = {}
    devices = [entity for role in DEVICE_ROLE_KEYS for entity in (data.get(role) or [])]
    backups = list(data.get(CONF_BACKUP_TEMP_ENTITIES) or [])
    if (devices or backups) and not data.get(CONF_INSIDE_TEMP_ENTITY):
        errors[CONF_INSIDE_TEMP_ENTITY] = "inside_temp_required"
    elif data.get(CONF_INSIDE_TEMP_ENTITY) in backups:
        errors[CONF_BACKUP_TEMP_ENTITIES] = "backup_same_as_inside"
    elif len(devices) != len(set(devices)):
        errors["base"] = "device_in_two_roles"
    else:
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.entry_id == exclude_entry_id:
                continue
            other = {**entry.data, **entry.options}
            if set(devices) & {entity for role in DEVICE_ROLE_KEYS for entity in (other.get(role) or [])}:
                errors["base"] = "device_already_used"
                break
    return errors


def _site_numbers(data: dict[str, Any]) -> dict[str, float]:
    """A new zone's cycle-and-soak starting values from its soil, drainage
    and irrigation method: the pulse-count settings (the minimum; each
    watering adds what the soil and slope need) and the soak between
    pulses."""
    soil = data.get(CONF_SOIL_TYPE, DEFAULT_SOIL_TYPE)
    drainage = data.get(CONF_DRAINAGE, DEFAULT_DRAINAGE)
    count = float(calc.starting_pulse_count(soil, data.get(CONF_IRRIGATION_METHOD, DEFAULT_IRRIGATION_METHOD)))
    soak = calc.soak_minutes(soil, drainage)
    return {
        "routine_pulse_count": count,
        "deep_soak_pulse_count": count,
        "routine_pulse_rest_minutes": soak,
        "deep_soak_pulse_rest_minutes": soak,
    }


class ZoneFlowConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._zone_name: str | None = None
        self._plant: str = PLANT_CUSTOM
        self._data: dict[str, Any] = {}
        self._climate: str = DEFAULT_CLIMATE
        self._zone_type: str = DEFAULT_ZONE_TYPE

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            zone_name = user_input[CONF_ZONE_NAME].strip()
            if not zone_name:
                errors["base"] = "zone_name_required"
            else:
                self._zone_name = zone_name
                self._plant = user_input.get(CONF_PLANT, PLANT_CUSTOM)
                self._zone_type = user_input.get(CONF_ZONE_TYPE, DEFAULT_ZONE_TYPE)
                if self._zone_type != ZONE_TYPE_OUTDOOR:
                    return await self.async_step_greenhouse_devices()
                return await self.async_step_entities()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ZONE_NAME, default=self._zone_name or ""): str,
                    # What's planted: pre-fills targets, crop factor,
                    # pulses, deep soak and growth ramp (PLANT_PRESETS).
                    vol.Required(CONF_PLANT, default=self._plant): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=PLANT_OPTIONS, translation_key="plant")
                    ),
                    # Where it grows: outdoor is how ZoneFlow has always
                    # worked; greenhouse and indoor zones add climate control.
                    vol.Required(CONF_ZONE_TYPE, default=self._zone_type): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=ZONE_TYPE_OPTIONS, translation_key="zone_type")
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_entities(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _duplicate_errors(self.hass, user_input)
            if not errors:
                for key in (CONF_DEEP_SOAK_TIME, CONF_ROUTINE_TIME):
                    if len(user_input[key].split(":")) == 2:
                        user_input[key] = f"{user_input[key]}:00"
                user_input[CONF_ZONE_NAME] = self._zone_name
                self._data = user_input
                return await self.async_step_climate()
        # Default CSV path is zone-specific so two zones never silently
        # write into the same log file if the user just accepts defaults.
        default_csv = f"/config/zoneflow_{slugify(self._zone_name)}.csv"
        defaults: dict[str, Any] = {CONF_CSV_PATH: default_csv}
        if (preset := PLANT_PRESETS.get(self._plant)) is not None:
            defaults[CONF_DEEP_SOAK_ENABLED] = preset["deep_soak"]
            defaults[CONF_GROWTH_RAMP_PROFILE] = preset["ramp"]
        return self.async_show_form(
            step_id="entities",
            data_schema=_schema(defaults),
            errors=errors,
        )

    async def async_step_greenhouse_devices(self, user_input: dict[str, Any] | None = None):
        """Greenhouse / indoor zones: the inside sensors and the climate
        devices (fans, vents, misting, heater). All optional, except that a
        device needs the inside temperature."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _climate_errors(self.hass, user_input)
            if not errors:
                self._data = {**self._data, **user_input}
                return await self.async_step_water_valve()
        defaults = {**self._data, **(user_input or {})}
        return self.async_show_form(
            step_id="greenhouse_devices",
            data_schema=_devices_schema(defaults, with_valve=False),
            errors=errors,
        )

    async def async_step_water_valve(self, user_input: dict[str, Any] | None = None):
        """Does this zone water too? A valve means yes; leave it empty for a
        climate-only zone (then it needs at least one climate device)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            valve = user_input.get(CONF_VALVE_ENTITY)
            has_devices = any(self._data.get(role) for role in DEVICE_ROLE_KEYS)
            if valve:
                errors = _duplicate_errors(self.hass, {CONF_VALVE_ENTITY: valve})
            elif not has_devices:
                errors["base"] = "valve_or_device_required"
            if not errors:
                if valve:
                    self._data = {**self._data, CONF_VALVE_ENTITY: valve}
                    return await self.async_step_watering()
                return await self.async_step_climate()
        return self.async_show_form(
            step_id="water_valve",
            data_schema=vol.Schema(
                {
                    _optional_entity_key({}, CONF_VALVE_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="switch")
                    )
                }
            ),
            errors=errors,
        )

    def _create_climate_only(self):
        """A zone with no valve: it never waters, so none of the watering
        settings are asked for; they get their ordinary defaults."""
        data = {
            **self._data,
            CONF_ZONE_NAME: self._zone_name,
            CONF_PLANT: self._plant,
            CONF_ZONE_TYPE: self._zone_type,
            CONF_CLIMATE: self._climate,
            CONF_CSV_PATH: f"/config/zoneflow_{slugify(self._zone_name)}.csv",
            CONF_DEEP_SOAK_ENABLED: False,
            CONF_DEEP_SOAK_TIME: DEFAULT_DEEP_SOAK_TIME,
            CONF_ROUTINE_TIME: DEFAULT_ROUTINE_TIME,
            CONF_INITIAL_NUMBERS: self._greenhouse_numbers(),
        }
        return self.async_create_entry(title=self._zone_name, data=data)

    def _greenhouse_numbers(self) -> dict[str, float]:
        """Starting heat / vent / fan / mist setpoints for the chosen climate."""
        preset = greenhouse_logic.preset_settings(self._climate)
        return {key: preset[key] for key in GREENHOUSE_PRESET_NUMBER_KEYS}

    async def async_step_watering(self, user_input: dict[str, Any] | None = None):
        """Greenhouse / indoor zone with a valve: the watering settings."""
        errors: dict[str, str] = {}
        if user_input is not None:
            for key in (CONF_DEEP_SOAK_TIME, CONF_ROUTINE_TIME):
                if len(user_input[key].split(":")) == 2:
                    user_input[key] = f"{user_input[key]}:00"
            self._data = {
                **self._data,
                **user_input,
                CONF_ZONE_NAME: self._zone_name,
                CONF_CSV_PATH: f"/config/zoneflow_{slugify(self._zone_name)}.csv",
            }
            return await self.async_step_climate()
        defaults: dict[str, Any] = {}
        if (preset := PLANT_PRESETS.get(self._plant)) is not None:
            defaults[CONF_DEEP_SOAK_ENABLED] = preset["deep_soak"]
            defaults[CONF_GROWTH_RAMP_PROFILE] = preset["ramp"]
        return self.async_show_form(step_id="watering", data_schema=_watering_schema(defaults), errors=errors)

    def _imperial(self) -> bool:
        """The zone's display units, decided the same way the controller
        does (units option, else Home Assistant's own unit system)."""
        choice = self._data.get(CONF_UNIT_SYSTEM, units.UNIT_SYSTEM_AUTO)
        if choice == units.UNIT_SYSTEM_IMPERIAL:
            return True
        if choice == units.UNIT_SYSTEM_METRIC:
            return False
        return self.hass.config.units.temperature_unit == UnitOfTemperature.FAHRENHEIT

    async def async_step_climate(self, user_input: dict[str, Any] | None = None):
        """Pick the climate; it pre-fills the temperature sliders next."""
        if user_input is not None:
            self._climate = user_input[CONF_CLIMATE]
            if self._zone_type != ZONE_TYPE_OUTDOOR and not self._data.get(CONF_VALVE_ENTITY):
                return self._create_climate_only()  # nothing to water: no watering temperatures
            return await self.async_step_temperatures()
        return self.async_show_form(
            step_id="climate",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CLIMATE, default=self._climate): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=CLIMATE_OPTIONS, translation_key="climate")
                    )
                }
            ),
        )

    async def async_step_temperatures(self, user_input: dict[str, Any] | None = None):
        """Hot / cool thresholds and the fallback temperature, shown and
        entered in the zone's units, stored in °C."""
        imperial = self._imperial()
        errors: dict[str, str] = {}
        if user_input is not None:
            metric = {key: units.to_metric(key, float(user_input[key]), imperial) for key in CLIMATE_NUMBER_KEYS}
            if metric["cool_temp_threshold"] >= metric["hot_temp_threshold"] - 0.01:
                errors["base"] = "cool_not_below_hot"
            else:
                plant_numbers = PLANT_PRESETS.get(self._plant, {}).get("numbers", {})
                data = {
                    **self._data,
                    CONF_PLANT: self._plant,
                    CONF_CLIMATE: self._climate,
                    CONF_INITIAL_NUMBERS: {**plant_numbers, **_site_numbers(self._data), **metric},
                }
                if self._zone_type != ZONE_TYPE_OUTDOOR:
                    data[CONF_ZONE_TYPE] = self._zone_type
                    data[CONF_INITIAL_NUMBERS] = {**self._greenhouse_numbers(), **data[CONF_INITIAL_NUMBERS]}
                return self.async_create_entry(title=self._zone_name, data=data)
        preset = CLIMATE_PRESETS[self._climate]
        schema = {}
        for key in CLIMATE_NUMBER_KEYS:
            _name, lo, hi, metric_step, metric_unit = NUMBER_DEFS[key]
            shown_lo, shown_hi = units.display_range(key, lo, hi, metric_step, imperial)
            shown_step = units.step(key, metric_step, imperial)
            # On the slider's own step (31.5C is 88.7F; offer 88.5F).
            default = (
                user_input[key]
                if user_input is not None
                else round(round(units.to_display(key, preset[key], imperial) / shown_step) * shown_step, 2)
            )
            schema[vol.Required(key, default=default)] = selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=shown_lo,
                    max=shown_hi,
                    step=shown_step,
                    unit_of_measurement=units.unit(key, metric_unit, imperial),
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            )
        return self.async_show_form(step_id="temperatures", data_schema=vol.Schema(schema), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ZoneFlowOptionsFlow(config_entry)


class ZoneFlowOptionsFlow(config_entries.OptionsFlow):
    """Configure: the zone's settings, or the flow-rate helper."""

    def __init__(self, config_entry) -> None:
        self._config_entry = config_entry

    def _controller(self):
        return self.hass.data.get(DOMAIN, {}).get(self._config_entry.entry_id)

    def _merged(self) -> dict[str, Any]:
        return {**self._config_entry.data, **self._config_entry.options}

    def _zone_type(self) -> str:
        return self._merged().get(CONF_ZONE_TYPE, DEFAULT_ZONE_TYPE)

    def _has_valve(self) -> bool:
        return bool(self._merged().get(CONF_VALVE_ENTITY))

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        outdoor = self._zone_type() == ZONE_TYPE_OUTDOOR
        has_valve = self._has_valve()
        options = ["settings"] if outdoor else ["greenhouse_devices"]
        if not outdoor and has_valve:
            options.append("watering")
        if has_valve:
            options.append("flow_rate")
        controller = self._controller()
        if has_valve and controller is not None and controller.flow_meter_entity:
            options.append("flow_measure")
        options.append("zone_type")
        return self.async_show_menu(step_id="init", menu_options=options)

    async def async_step_zone_type(self, user_input: dict[str, Any] | None = None):
        """Change where the zone grows. Nothing is deleted: what the new
        type doesn't use is hidden, and comes back if the type is changed
        back."""
        errors: dict[str, str] = {}
        if user_input is not None:
            new_type = user_input[CONF_ZONE_TYPE]
            if new_type == ZONE_TYPE_OUTDOOR and not self._has_valve():
                errors["base"] = "valve_required_outdoor"
            else:
                options = {**self._config_entry.options, CONF_ZONE_TYPE: new_type}
                if new_type != ZONE_TYPE_OUTDOOR:
                    # The heat / vent / fan / mist temperatures start from the
                    # zone's climate, as at setup (only used by sliders that
                    # have no value yet).
                    preset = greenhouse_logic.preset_settings(self._merged().get(CONF_CLIMATE))
                    options[CONF_INITIAL_NUMBERS] = {
                        **{key: preset[key] for key in GREENHOUSE_PRESET_NUMBER_KEYS},
                        **(options.get(CONF_INITIAL_NUMBERS) or {}),
                    }
                return self.async_create_entry(title="", data=options)
        return self.async_show_form(
            step_id="zone_type",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ZONE_TYPE, default=self._zone_type()): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=ZONE_TYPE_OPTIONS, translation_key="zone_type")
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_greenhouse_devices(self, user_input: dict[str, Any] | None = None):
        """Greenhouse / indoor zones: the valve (optional), inside sensors
        and climate devices, changeable any time without re-creating the zone."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _climate_errors(self.hass, user_input, exclude_entry_id=self._config_entry.entry_id)
            if not errors:
                if user_input.get(CONF_VALVE_ENTITY):
                    errors = _duplicate_errors(
                        self.hass, {CONF_VALVE_ENTITY: user_input[CONF_VALVE_ENTITY]},
                        exclude_entry_id=self._config_entry.entry_id,
                    )
                elif not any(user_input.get(role) for role in DEVICE_ROLE_KEYS):
                    errors["base"] = "valve_or_device_required"
            if not errors:
                # A cleared entry is left out of the form's answer: store it
                # as empty, or the zone would fall back to the setup value.
                for key in (
                    CONF_VALVE_ENTITY, CONF_INSIDE_TEMP_ENTITY, CONF_INSIDE_HUMIDITY_ENTITY, CONF_LIGHT_ENTITY,
                    CONF_OUTDOOR_TEMP_ENTITY, CONF_NOTIFY_ENTITY,
                ):
                    user_input.setdefault(key, None)
                for role in (*DEVICE_ROLE_KEYS, CONF_BACKUP_TEMP_ENTITIES):
                    user_input.setdefault(role, [])
                return self.async_create_entry(title="", data={**self._config_entry.options, **user_input})
        defaults = {**self._merged(), **(user_input or {})}
        return self.async_show_form(
            step_id="greenhouse_devices",
            data_schema=_devices_schema(defaults, with_valve=True),
            errors=errors,
        )

    async def async_step_watering(self, user_input: dict[str, Any] | None = None):
        """Greenhouse / indoor zone with a valve: the watering settings
        (the same as an outdoor zone's, without rain gauge and forecast)."""
        if user_input is not None:
            for key in (CONF_DEEP_SOAK_TIME, CONF_ROUTINE_TIME):
                if len(user_input[key].split(":")) == 2:
                    user_input[key] = f"{user_input[key]}:00"
            await self._apply_site(user_input)
            return self.async_create_entry(title="", data={**self._config_entry.options, **user_input})
        defaults = self._merged()
        controller = self._controller()
        if controller is not None:
            defaults.update({CONF_SOIL_TYPE: controller.soil_type, CONF_DRAINAGE: controller.drainage, CONF_SLOPE: controller.slope})
        return self.async_show_form(step_id="watering", data_schema=_watering_schema(defaults))

    async def async_step_flow_rate(self, user_input: dict[str, Any] | None = None):
        """Work the emitter flow rate out from the emitters: how many, how
        much each gives, over how big an area. 1 litre on 1 m² is 1 mm."""
        controller = self._controller()
        if controller is None:
            return self.async_abort(reason="zone_not_loaded")
        imperial = controller.imperial
        if user_input is not None:
            per_emitter_l_h = float(user_input["emitter_flow"]) * (units.LITERS_PER_GALLON if imperial else 1.0)
            area_m2 = float(user_input["area"]) * (units.M2_PER_FT2 if imperial else 1.0)
            mm_per_min = round(float(user_input["emitters"])) * per_emitter_l_h / area_m2 / 60
            return await self._apply_flow_rate(controller, mm_per_min)
        return self.async_show_form(
            step_id="flow_rate",
            data_schema=vol.Schema(
                {
                    vol.Required("emitters", default=4): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=1, max=2000, step=1, mode=selector.NumberSelectorMode.BOX)
                    ),
                    vol.Required("emitter_flow", default=0.5 if imperial else 2.0): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.05, max=200, step=0.05, mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="gal/h" if imperial else "L/h",
                        )
                    ),
                    vol.Required("area", default=10.0 if imperial else 1.0): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.1, max=100000, step=0.1, mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="ft²" if imperial else "m²",
                        )
                    ),
                }
            ),
        )

    async def _apply_flow_rate(self, controller, mm_per_min: float):
        _name, lo, hi, _step, _unit = NUMBER_DEFS["flow_rate_mm_per_min"]

        def shown(value: float) -> str:
            if controller.imperial:
                return f"{units.to_display('flow_rate_mm_per_min', value, True):.3f} in/h"
            return f"{value:.3f} mm/min"

        if not lo <= mm_per_min <= hi:
            return self.async_abort(
                reason="flow_rate_out_of_range",
                description_placeholders={"rate": shown(mm_per_min), "low": shown(lo), "high": shown(hi)},
            )
        number = controller.numbers.get("flow_rate_mm_per_min")
        if number is None:  # the setting's entity is disabled
            return self.async_abort(reason="flow_rate_disabled")
        await number.async_set_metric_value(round(mm_per_min, 3))
        return self.async_abort(reason="flow_rate_set", description_placeholders={"rate": shown(mm_per_min)})

    async def async_step_flow_measure(self, user_input: dict[str, Any] | None = None):
        """With a flow meter: a service run measures the litres, and the
        flow rate is worked out when it ends (with a phone message)."""
        controller = self._controller()
        if controller is None or not controller.flow_meter_entity:
            return self.async_abort(reason="zone_not_loaded")
        if "flow_rate_mm_per_min" not in controller.numbers:
            return self.async_abort(reason="flow_rate_disabled")
        imperial = controller.imperial
        if user_input is not None:
            area_m2 = float(user_input["area"]) * (units.M2_PER_FT2 if imperial else 1.0)
            try:
                await controller.start_flow_measurement(area_m2)
            except HomeAssistantError:
                return self.async_abort(reason="zone_busy")
            return self.async_abort(reason="measuring", description_placeholders={"minutes": str(FLOW_MEASURE_MINUTES)})
        return self.async_show_form(
            step_id="flow_measure",
            data_schema=vol.Schema(
                {
                    vol.Required("area", default=10.0 if imperial else 1.0): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.1, max=100000, step=0.1, mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="ft²" if imperial else "m²",
                        )
                    ),
                }
            ),
            description_placeholders={"minutes": str(FLOW_MEASURE_MINUTES)},
        )

    async def async_step_settings(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _duplicate_errors(self.hass, user_input, exclude_entry_id=self._config_entry.entry_id)
            if not errors:
                for key in (CONF_DEEP_SOAK_TIME, CONF_ROUTINE_TIME):
                    if len(user_input[key].split(":")) == 2:
                        user_input[key] = f"{user_input[key]}:00"
                # A cleared optional sensor is left out of the form's answer;
                # store it as None, or the zone would fall back to the one
                # chosen at first setup (options override the setup data).
                for key in OPTIONAL_ENTITY_KEYS:
                    user_input.setdefault(key, None)
                await self._apply_site(user_input)
                # Keep what other Configure steps stored (the zone type).
                return self.async_create_entry(title="", data={**self._config_entry.options, **user_input})
        defaults = {**self._config_entry.data, **self._config_entry.options, **(user_input or {})}
        controller = self.hass.data.get(DOMAIN, {}).get(self._config_entry.entry_id)
        if controller is not None and not user_input:
            # What the zone uses now -- the device page's dropdowns included.
            defaults.update({CONF_SOIL_TYPE: controller.soil_type, CONF_DRAINAGE: controller.drainage, CONF_SLOPE: controller.slope})
        return self.async_show_form(step_id="settings", data_schema=_schema(defaults), errors=errors)

    async def _apply_site(self, user_input: dict[str, Any]) -> None:
        """The form's soil, drainage and slope are now the zone's: they
        replace what the device page's dropdowns had set, and a changed soil
        or drainage sets the soak between pulses to match (as the dropdowns
        do)."""
        controller = self.hass.data.get(DOMAIN, {}).get(self._config_entry.entry_id)
        if controller is None:
            return
        before = (controller.soil_type, controller.drainage)
        state = controller.store.state
        state.soil_type_override = state.drainage_override = state.slope_override = None
        await controller.store.async_save()
        after = (user_input.get(CONF_SOIL_TYPE, before[0]), user_input.get(CONF_DRAINAGE, before[1]))
        if after != before:
            minutes = calc.soak_minutes(*after)
            for key in ("routine_pulse_rest_minutes", "deep_soak_pulse_rest_minutes"):
                entity = controller.numbers.get(key)
                if entity is not None:
                    await entity.async_set_metric_value(minutes)
