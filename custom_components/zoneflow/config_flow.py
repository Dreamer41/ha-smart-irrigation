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

from . import calculations as calc, greenhouse_logic, location, messages, presets, suggest, units, wu_logic
from .area import AREA_SHARED_KEYS, DEFAULT_AREA_MM_PER_TIP

from .const import (
    CONF_PARENT_ZONE,
    CROP_INHERITED_KEYS,
    CONF_ENTRY_TYPE,
    CONF_USE_WU,
    CONF_WU_API_KEY,
    CONF_WU_RADIUS_KM,
    CONF_WU_STATIONS,
    ENTRY_TYPE_WU,
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
    CONF_AREA_ID,
    CONF_START_FROM,
    CONF_START_STATE,
    CONF_AREA_MM_PER_TIP,
    CONF_AREA_NAME,
    ENTRY_TYPE_AREA,
    AREA_NAME_MAX_LENGTH,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_RAIN_SOURCE,
    RAIN_SOURCE_OPTIONS,
    RAIN_SOURCE_TIPS,
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
            vol.Optional(CONF_RAIN_SOURCE, default=defaults.get(CONF_RAIN_SOURCE) or RAIN_SOURCE_TIPS): selector.SelectSelector(
                selector.SelectSelectorConfig(options=RAIN_SOURCE_OPTIONS, translation_key="rain_source")
            ),
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
    CONF_RAIN_SOURCE,
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


# --- Greenhouse crops (1.6.1) -----------------------------------------------
# A crop is a greenhouse / indoor zone that belongs to a greenhouse (the zone
# with the climate devices) and uses its inside sensors (controller.is_crop).


def _merged_entry(entry) -> dict[str, Any]:
    return {**entry.data, **entry.options}


def _greenhouses(hass, exclude_entry_id: str | None = None) -> list:
    """Zones a crop can belong to: greenhouse / indoor zones with climate
    devices that aren't crops themselves."""
    found = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        data = _merged_entry(entry)
        if entry.entry_id == exclude_entry_id or _is_wu_entry(entry) or data.get(CONF_PARENT_ZONE):
            continue
        if data.get(CONF_ZONE_TYPE, DEFAULT_ZONE_TYPE) == ZONE_TYPE_OUTDOOR:
            continue
        if any(data.get(role) for role in DEVICE_ROLE_KEYS):
            found.append(entry)
    return sorted(found, key=lambda e: e.title.lower())


def _has_crops(hass, entry_id: str) -> bool:
    return any(_merged_entry(e).get(CONF_PARENT_ZONE) == entry_id for e in hass.config_entries.async_entries(DOMAIN))


def _greenhouse_selector(entries: list, *, with_none: bool) -> selector.SelectSelector:
    options = [selector.SelectOptionDict(value=e.entry_id, label=e.title) for e in entries]
    if with_none:
        options.insert(0, selector.SelectOptionDict(value="", label="-"))
    return selector.SelectSelector(selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.LIST))


# --- Weather Underground rain (1.6.1, experimental) -----------------------
# One shared entry (wu.py) for outdoor zones without a rain gauge. Offered
# once a zone exists; the first screen says to check the WU map for nearby
# stations first, and that the free API key needs a station of your own
# uploading at least temperature and humidity.


def _is_wu_entry(entry) -> bool:
    return entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_WU


def _is_area_entry(entry) -> bool:
    return entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_AREA


def _clean_name(value: Any) -> str:
    return " ".join(str(value or "").split())[:AREA_NAME_MAX_LENGTH]


def _area_name_taken(hass, name: str, exclude_entry_id: str | None = None) -> bool:
    return any(
        _is_area_entry(e) and e.entry_id != exclude_entry_id and e.title.casefold() == name.casefold()
        for e in hass.config_entries.async_entries(DOMAIN)
    )


def _area_schema(defaults: dict[str, Any], *, with_name: bool = True) -> vol.Schema:
    """An area: its name and the sensors its zones share."""
    fields: dict[Any, Any] = {}
    if with_name:
        fields[vol.Required(CONF_AREA_NAME, default=defaults.get(CONF_AREA_NAME, ""))] = str
    fields[_optional_entity_key(defaults, CONF_RAIN_COUNTER_ENTITY)] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain=["counter", "sensor"])
    )
    fields[vol.Optional(CONF_RAIN_SOURCE, default=defaults.get(CONF_RAIN_SOURCE) or RAIN_SOURCE_TIPS)] = (
        selector.SelectSelector(selector.SelectSelectorConfig(options=RAIN_SOURCE_OPTIONS, translation_key="rain_source"))
    )
    fields[
        vol.Optional(CONF_AREA_MM_PER_TIP, default=defaults.get(CONF_AREA_MM_PER_TIP) or DEFAULT_AREA_MM_PER_TIP)
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0.01, max=2.0, step=0.001, unit_of_measurement="mm", mode=selector.NumberSelectorMode.BOX
        )
    )
    fields[_optional_entity_key(defaults, CONF_OUTDOOR_TEMP_ENTITY)] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
    )
    fields[_optional_entity_key(defaults, CONF_WEATHER_ENTITY)] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="weather")
    )
    fields[_optional_entity_key(defaults, CONF_NOTIFY_ENTITY)] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="notify")
    )
    return vol.Schema(fields)


def _area_data(user_input: dict[str, Any]) -> dict[str, Any]:
    """What an area entry stores, from the form's answer (a cleared field is left out)."""
    data: dict[str, Any] = {
        CONF_ENTRY_TYPE: ENTRY_TYPE_AREA,
        CONF_RAIN_SOURCE: user_input.get(CONF_RAIN_SOURCE) or RAIN_SOURCE_TIPS,
        CONF_AREA_MM_PER_TIP: float(user_input.get(CONF_AREA_MM_PER_TIP) or DEFAULT_AREA_MM_PER_TIP),
    }
    for key in AREA_SHARED_KEYS:
        data[key] = user_input.get(key) or None
    return data


def _wu_key_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_WU_API_KEY, default=defaults.get(CONF_WU_API_KEY, "")): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(
                CONF_WU_RADIUS_KM, default=defaults.get(CONF_WU_RADIUS_KM, wu_logic.RADIUS_DEFAULT_KM)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=wu_logic.RADIUS_MIN_KM,
                    max=wu_logic.RADIUS_MAX_KM,
                    step=0.5,
                    unit_of_measurement="km",
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
        }
    )


async def _wu_candidates(hass, api_key: str, radius_km: float) -> tuple[list[dict[str, Any]], str | None]:
    """Stations within the radius with today's rain, or an error key."""
    from . import wu

    try:
        stations = await wu.async_nearby_stations(hass, api_key)
    except wu.InvalidKey:
        return [], "wu_invalid_key"
    except wu.CannotConnect:
        return [], "wu_cannot_connect"
    stations = [s for s in stations if s["distance_km"] <= radius_km]
    if not stations:
        return [], "wu_no_stations"
    for station in stations:
        try:
            obs = await wu.async_current(hass, api_key, station["id"])
        except (wu.InvalidKey, wu.CannotConnect):
            obs = None
        station["rain_today"] = None if obs is None else obs.total_mm
    return stations, None


def _wu_station_schema(candidates: list[dict[str, Any]], chosen: list[str]) -> vol.Schema:
    options = [
        selector.SelectOptionDict(
            value=s["id"],
            label=(
                f"{s['id']} ({s['name']}) - {s['distance_km']:.1f} km - "
                + ("no recent report" if s.get("rain_today") is None else f"{s['rain_today']:.1f} mm today")
                + (" - over 1 km: compare with your own rain" if s["distance_km"] > wu_logic.CHECK_DISTANCE_KM else "")
            ),
        )
        for s in candidates
    ]
    return vol.Schema(
        {
            vol.Required(CONF_WU_STATIONS, default=chosen): selector.SelectSelector(
                selector.SelectSelectorConfig(options=options, multiple=True, mode=selector.SelectSelectorMode.LIST)
            )
        }
    )


def _wu_picked(candidates: list[dict[str, Any]], ids: list[str]) -> tuple[list[dict[str, Any]], str | None]:
    if not 1 <= len(ids) <= wu_logic.MAX_STATIONS:
        return [], "wu_pick_1_to_3"
    by_id = {s["id"]: s for s in candidates}
    return [
        {k: by_id[i][k] for k in ("id", "name", "latitude", "longitude", "distance_km")} for i in ids if i in by_id
    ], None


class ZoneFlowConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._zone_name: str | None = None
        self._plant: str = PLANT_CUSTOM
        self._data: dict[str, Any] = {}
        self._climate: str = DEFAULT_CLIMATE
        self._zone_type: str = DEFAULT_ZONE_TYPE
        self._menu_done = False
        self._crop_pump_id: str | None = None
        self._wu: dict[str, Any] = {}
        self._wu_candidates: list[dict[str, Any]] = []
        self._bundle: dict[str, Any] = {}

    def _offer_wu(self) -> bool:
        """Weather Underground rain is offered once a zone exists, and only
        one per Home Assistant."""
        entries = self.hass.config_entries.async_entries(DOMAIN)
        return any(not _is_wu_entry(e) for e in entries) and not any(_is_wu_entry(e) for e in entries)

    def _menu_options(self) -> list[str]:
        options = ["zone"]
        if _greenhouses(self.hass):
            options.append("crop")
        if any(not _is_wu_entry(e) and not _is_area_entry(e) for e in self.hass.config_entries.async_entries(DOMAIN)):
            options.append("area")
        if self._offer_wu():
            options.append("weather_underground")
        return options

    async def async_step_area(self, user_input: dict[str, Any] | None = None):
        """A part of the garden, with the sensors its zones share."""
        errors: dict[str, str] = {}
        defaults = user_input or {}
        if user_input is not None:
            name = _clean_name(user_input.get(CONF_AREA_NAME))
            if not name:
                errors["base"] = "area_name_required"
            elif _area_name_taken(self.hass, name):
                errors["base"] = "area_name_exists"
            else:
                return self.async_create_entry(title=name, data=_area_data(user_input))
        return self.async_show_form(step_id="area", data_schema=_area_schema(defaults), errors=errors)

    async def async_step_area_create(self, data: dict[str, Any]):
        """An area made from a zone's Configure (the options flow starts this)."""
        return self.async_create_entry(title=data["name"], data=_area_data(data))

    async def async_step_crop(self, user_input: dict[str, Any] | None = None):
        """A crop in a greenhouse: which greenhouse, the crop's name and
        plant. Then its valve and watering settings; the climate (zone type,
        inside sensors, climate preset) comes from the greenhouse."""
        greenhouses = _greenhouses(self.hass)
        errors: dict[str, str] = {}
        if user_input is not None:
            parent = self.hass.config_entries.async_get_entry(user_input[CONF_PARENT_ZONE])
            name = user_input[CONF_ZONE_NAME].strip()
            if not name:
                errors["base"] = "zone_name_required"
            elif parent is not None:
                source = _merged_entry(parent)
                self._zone_name = name
                self._plant = user_input.get(CONF_PLANT, PLANT_CUSTOM)
                self._zone_type = source.get(CONF_ZONE_TYPE, DEFAULT_ZONE_TYPE)
                self._climate = source.get(CONF_CLIMATE, DEFAULT_CLIMATE)
                self._crop_pump_id = source.get(CONF_PUMP_ID) or ""
                self._data = {
                    CONF_PARENT_ZONE: parent.entry_id,
                    CONF_ZONE_TYPE: self._zone_type,
                    # Phone messages and units as the greenhouse has them.
                    CONF_NOTIFY_ENTITY: source.get(CONF_NOTIFY_ENTITY),
                    CONF_UNIT_SYSTEM: source.get(CONF_UNIT_SYSTEM, units.UNIT_SYSTEM_AUTO),
                }
                return await self.async_step_crop_valve()
        return self.async_show_form(
            step_id="crop",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PARENT_ZONE, default=greenhouses[0].entry_id if greenhouses else ""
                    ): _greenhouse_selector(greenhouses, with_none=False),
                    vol.Required(CONF_ZONE_NAME, default=self._zone_name or ""): str,
                    vol.Required(CONF_PLANT, default=self._plant): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=PLANT_OPTIONS, translation_key="plant")
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_crop_valve(self, user_input: dict[str, Any] | None = None):
        """A crop always has a valve: it is what makes it a crop."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _duplicate_errors(self.hass, user_input)
            if not errors:
                self._data = {**self._data, CONF_VALVE_ENTITY: user_input[CONF_VALVE_ENTITY]}
                return await self.async_step_watering()
        return self.async_show_form(
            step_id="crop_valve",
            data_schema=vol.Schema(
                {vol.Required(CONF_VALVE_ENTITY): selector.EntitySelector(selector.EntitySelectorConfig(domain="switch"))}
            ),
            errors=errors,
        )

    async def async_step_start(self, user_input: dict[str, Any] | None = None):
        return self.async_show_menu(step_id="start", menu_options=self._menu_options())

    async def async_step_zone(self, user_input: dict[str, Any] | None = None):
        self._menu_done = True
        return await self.async_step_user()

    async def async_step_weather_underground(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(ENTRY_TYPE_WU)
            self._abort_if_unique_id_configured()
            self._wu = dict(user_input)
            candidates, error = await _wu_candidates(
                self.hass, user_input[CONF_WU_API_KEY].strip(), float(user_input[CONF_WU_RADIUS_KM])
            )
            if error:
                errors["base"] = error
            else:
                self._wu_candidates = candidates
                return await self.async_step_wu_stations()
        return self.async_show_form(
            step_id="weather_underground", data_schema=_wu_key_schema(self._wu), errors=errors
        )

    async def async_step_wu_stations(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            stations, error = _wu_picked(self._wu_candidates, user_input[CONF_WU_STATIONS])
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title="Weather Underground rain",
                    data={
                        CONF_ENTRY_TYPE: ENTRY_TYPE_WU,
                        CONF_WU_API_KEY: self._wu[CONF_WU_API_KEY].strip(),
                        CONF_WU_RADIUS_KM: float(self._wu[CONF_WU_RADIUS_KM]),
                        CONF_WU_STATIONS: stations,
                    },
                )
        nearest = [s["id"] for s in self._wu_candidates[: wu_logic.MAX_STATIONS]]
        return self.async_show_form(
            step_id="wu_stations", data_schema=_wu_station_schema(self._wu_candidates, nearest), errors=errors
        )

    def _progress(self, n: int) -> str:
        """"Step 2 of 4" on the steps every outdoor zone goes through (a
        greenhouse zone's steps differ, so it gets no counter)."""
        if self._zone_type != ZONE_TYPE_OUTDOOR:
            return ""
        return messages.text(self.hass, "setup.progress", n=n, total=4)

    async def _start_choices(self) -> list[tuple[str, str]]:
        """(value, label): start from the plant type, a copy of a zone, or a saved preset."""
        out = [("", messages.text(self.hass, "start_from.none"))]
        for entry in sorted(self.hass.config_entries.async_entries(DOMAIN), key=lambda e: e.title.casefold()):
            if _is_wu_entry(entry) or _is_area_entry(entry) or not _merged_entry(entry).get(CONF_VALVE_ENTITY):
                continue
            out.append((f"zone:{entry.entry_id}", messages.text(self.hass, "start_from.zone", zone=entry.title)))
        for preset in (await presets.async_get_book(self.hass)).listing():
            out.append((f"preset:{preset['id']}", messages.text(self.hass, "start_from.preset", name=preset["name"])))
        return out

    async def _start_bundle(self, choice: str) -> dict[str, Any]:
        """The settings bundle behind a start-from choice (empty for none)."""
        kind, _, ident = (choice or "").partition(":")
        if kind == "zone":
            controller = self.hass.data.get(DOMAIN, {}).get(ident)
            return presets.capture(controller) if controller is not None else {}
        if kind == "preset":
            preset = (await presets.async_get_book(self.hass)).presets.get(ident)
            return preset["bundle"] if preset else {}
        return {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is None and not self._menu_done and len(self._menu_options()) > 1:
            return await self.async_step_start()
        errors: dict[str, str] = {}
        if user_input is not None:
            zone_name = user_input[CONF_ZONE_NAME].strip()
            if not zone_name:
                errors["base"] = "zone_name_required"
            else:
                self._zone_name = zone_name
                self._plant = user_input.get(CONF_PLANT, PLANT_CUSTOM)
                self._zone_type = user_input.get(CONF_ZONE_TYPE, DEFAULT_ZONE_TYPE)
                self._bundle = await self._start_bundle(user_input.get(CONF_START_FROM, ""))
                if self._zone_type != ZONE_TYPE_OUTDOOR:
                    return await self.async_step_greenhouse_devices()
                return await self.async_step_entities()
        choices = await self._start_choices()
        start_field: dict[Any, Any] = {}
        if len(choices) > 1:
            start_field[vol.Optional(CONF_START_FROM, default="")] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[selector.SelectOptionDict(value=v, label=label) for v, label in choices],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
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
                    **start_field,
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
        defaults.update((self._bundle.get("options") or {}))  # a copy of another zone: its way of watering
        # Likely entities, listed under the form; a clear single match is filled in.
        found = suggest.find(self.hass)
        used = {
            value
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            for key in (CONF_VALVE_ENTITY, CONF_SOIL_MOISTURE_ENTITY, CONF_FLOW_METER_ENTITY, CONF_PUMP_POWER_ENTITY)
            if (value := _merged_entry(entry).get(key))
        }
        for key, entity_id in suggest.defaults_from(found, used).items():
            defaults.setdefault(key, entity_id)
        return self.async_show_form(
            step_id="entities",
            data_schema=_schema(defaults),
            errors=errors,
            description_placeholders={
                "progress": self._progress(2),
                "suggestions": suggest.describe(self.hass, found),
            },
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
            if self._data.get(CONF_PARENT_ZONE):
                return await self.async_step_temperatures()  # the greenhouse's climate
            return await self.async_step_climate()
        defaults: dict[str, Any] = {}
        if self._crop_pump_id:
            # Crops on one water supply don't open at the same time.
            defaults[CONF_PUMP_ID] = self._crop_pump_id
        if (preset := PLANT_PRESETS.get(self._plant)) is not None:
            defaults[CONF_DEEP_SOAK_ENABLED] = preset["deep_soak"]
            defaults[CONF_GROWTH_RAMP_PROFILE] = preset["ramp"]
        defaults.update((self._bundle.get("options") or {}))
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
            description_placeholders={"progress": self._progress(3)},
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
                    CONF_INITIAL_NUMBERS: {
                        **plant_numbers, **_site_numbers(self._data), **(self._bundle.get("numbers") or {}), **metric
                    },
                }
                if self._bundle.get("state"):
                    data[CONF_START_STATE] = dict(self._bundle["state"])
                if self._zone_type != ZONE_TYPE_OUTDOOR:
                    data[CONF_ZONE_TYPE] = self._zone_type
                    data[CONF_INITIAL_NUMBERS] = {**self._greenhouse_numbers(), **data[CONF_INITIAL_NUMBERS]}
                return self.async_create_entry(title=self._zone_name, data=data)
        preset = {
            **CLIMATE_PRESETS[self._climate],
            **{k: v for k, v in (self._bundle.get("numbers") or {}).items() if k in CLIMATE_NUMBER_KEYS},
        }
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
        return self.async_show_form(
            step_id="temperatures", data_schema=vol.Schema(schema), errors=errors,
            description_placeholders={"progress": self._progress(4)},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        if _is_wu_entry(config_entry):
            return WeatherUndergroundOptionsFlow(config_entry)
        if _is_area_entry(config_entry):
            return AreaOptionsFlow(config_entry)
        return ZoneFlowOptionsFlow(config_entry)


class AreaOptionsFlow(config_entries.OptionsFlow):
    """Configure an area: its name and the sensors its zones share."""

    def __init__(self, config_entry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        # Its own step id: "init" is the zones' Configure menu.
        return await self.async_step_area_settings()

    async def async_step_area_settings(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        entry = self._config_entry
        current = {**entry.data, **entry.options, CONF_AREA_NAME: entry.title}
        if user_input is not None:
            name = _clean_name(user_input.get(CONF_AREA_NAME))
            if not name:
                errors["base"] = "area_name_required"
            elif _area_name_taken(self.hass, name, exclude_entry_id=entry.entry_id):
                errors["base"] = "area_name_exists"
            else:
                if name != entry.title:
                    self.hass.config_entries.async_update_entry(entry, title=name)
                data = _area_data(user_input)
                data.pop(CONF_ENTRY_TYPE)
                return self.async_create_entry(title="", data=data)
            current = {**current, **user_input}
        return self.async_show_form(step_id="area_settings", data_schema=_area_schema(current), errors=errors)


class WeatherUndergroundOptionsFlow(config_entries.OptionsFlow):
    """Configure the Weather Underground entry: key, radius and stations."""

    def __init__(self, config_entry) -> None:
        self._config_entry = config_entry
        self._wu: dict[str, Any] = {}
        self._candidates: list[dict[str, Any]] = []

    def _merged(self) -> dict[str, Any]:
        return {**self._config_entry.data, **self._config_entry.options}

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        # Its own step id: "init" is the zones' Configure menu.
        return await self.async_step_wu_key()

    async def async_step_wu_key(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            self._wu = dict(user_input)
            candidates, error = await _wu_candidates(
                self.hass, user_input[CONF_WU_API_KEY].strip(), float(user_input[CONF_WU_RADIUS_KM])
            )
            if error:
                errors["base"] = error
            else:
                self._candidates = candidates
                return await self.async_step_wu_stations()
        return self.async_show_form(step_id="wu_key", data_schema=_wu_key_schema(self._wu or self._merged()), errors=errors)

    async def async_step_wu_stations(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            stations, error = _wu_picked(self._candidates, user_input[CONF_WU_STATIONS])
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_WU_API_KEY: self._wu[CONF_WU_API_KEY].strip(),
                        CONF_WU_RADIUS_KM: float(self._wu[CONF_WU_RADIUS_KM]),
                        CONF_WU_STATIONS: stations,
                    },
                )
        current = [s["id"] for s in self._merged().get(CONF_WU_STATIONS) or []]
        chosen = [i for i in current if any(s["id"] == i for s in self._candidates)]
        return self.async_show_form(
            step_id="wu_stations", data_schema=_wu_station_schema(self._candidates, chosen), errors=errors
        )


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

    def _is_crop(self) -> bool:
        parent_id = self._merged().get(CONF_PARENT_ZONE)
        return bool(parent_id and self.hass.config_entries.async_get_entry(parent_id))

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        outdoor = self._zone_type() == ZONE_TYPE_OUTDOOR
        has_valve = self._has_valve()
        crop = self._is_crop()
        # A crop's sensors and climate are its greenhouse's: only its valve here.
        options = ["settings"] if outdoor else (["crop_valve"] if crop else ["greenhouse_devices"])
        if not outdoor and has_valve:
            options.append("watering")
        if has_valve:
            options.append("flow_rate")
            options.append("flow_volume")
            options.append("zone_flow")
        controller = self._controller()
        if has_valve and controller is not None and controller.flow_meter_entity:
            options.append("flow_measure")
        if outdoor and not self._merged().get(CONF_RAIN_COUNTER_ENTITY) and any(
            _is_wu_entry(e) for e in self.hass.config_entries.async_entries(DOMAIN)
        ):
            options.append("weather_underground")
        options.append("location")  # the area or greenhouse it is in
        if not crop:
            options.append("zone_type")  # a crop is whatever its greenhouse is
        return self.async_show_menu(step_id="init", menu_options=options)

    async def async_step_greenhouse_link(self, user_input: dict[str, Any] | None = None):
        """Which greenhouse this zone is a crop of, or none (on its own).
        Leaving a greenhouse keeps a copy of its inside sensors."""
        greenhouses = _greenhouses(self.hass, exclude_entry_id=self._config_entry.entry_id)
        current = self._merged().get(CONF_PARENT_ZONE) or ""
        if user_input is not None:
            chosen = user_input.get(CONF_PARENT_ZONE) or ""
            options = {**self._config_entry.options}
            if chosen:
                parent = self.hass.config_entries.async_get_entry(chosen)
                options[CONF_PARENT_ZONE] = chosen
                options[CONF_ZONE_TYPE] = _merged_entry(parent).get(CONF_ZONE_TYPE, DEFAULT_ZONE_TYPE)
            else:
                old = self.hass.config_entries.async_get_entry(current) if current else None
                options[CONF_PARENT_ZONE] = None
                if old is not None:
                    source = _merged_entry(old)
                    for key in CROP_INHERITED_KEYS:
                        if source.get(key):
                            options[key] = source[key]
            return self.async_create_entry(title="", data=options)
        return self.async_show_form(
            step_id="greenhouse_link",
            data_schema=vol.Schema(
                {vol.Optional(CONF_PARENT_ZONE, default=current): _greenhouse_selector(greenhouses, with_none=True)}
            ),
        )

    async def async_step_crop_valve(self, user_input: dict[str, Any] | None = None):
        """A crop's valve (its sensors and climate are its greenhouse's)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _duplicate_errors(self.hass, user_input, exclude_entry_id=self._config_entry.entry_id)
            if not errors:
                return self.async_create_entry(title="", data={**self._config_entry.options, **user_input})
        return self.async_show_form(
            step_id="crop_valve",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_VALVE_ENTITY, default=self._merged().get(CONF_VALVE_ENTITY)): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="switch")
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_weather_underground(self, user_input: dict[str, Any] | None = None):
        """Use the shared Weather Underground rain (zones without a gauge)."""
        if user_input is not None:
            return self.async_create_entry(
                title="", data={**self._config_entry.options, CONF_USE_WU: bool(user_input[CONF_USE_WU])}
            )
        return self.async_show_form(
            step_id="weather_underground",
            data_schema=vol.Schema(
                {vol.Required(CONF_USE_WU, default=bool(self._merged().get(CONF_USE_WU, False))): bool}
            ),
        )

    _NEW_AREA = "__new_area__"

    async def async_step_location(self, user_input: dict[str, Any] | None = None):
        """Where the zone is: in an area, in a greenhouse (as a crop of it),
        or nowhere in particular. "New area" makes one from this zone's own
        sensors."""
        entry = self._config_entry
        choices = location.choices(self.hass, entry)
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input["location"]
            if token == self._NEW_AREA:
                return await self.async_step_new_area()
            self._token = token
            if token.startswith(location.AREA_PREFIX) and location.differing_keys(
                self.hass, entry, token[len(location.AREA_PREFIX):]
            ):
                return await self.async_step_location_sensors()
            return self._finish_location(token, None, errors)
        options = [selector.SelectOptionDict(value=t, label=label) for t, label in choices]
        options.append(selector.SelectOptionDict(value=self._NEW_AREA, label=messages.text(self.hass, "location.new_area")))
        current = location.current_token(entry)
        if current not in {t for t, _ in choices}:
            current = location.NONE_TOKEN
        return self.async_show_form(
            step_id="location",
            data_schema=vol.Schema(
                {
                    vol.Required("location", default=current): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN)
                    )
                }
            ),
            errors=errors,
        )

    def _finish_location(self, token: str, use_area_keys: set[str] | None, errors: dict[str, str]):
        try:
            options = location.apply(self.hass, self._config_entry, token, use_area_keys)
        except HomeAssistantError:
            return self.async_abort(reason="location_not_available")
        return self.async_create_entry(title="", data=options)

    async def async_step_location_sensors(self, user_input: dict[str, Any] | None = None):
        """The zone has its own sensor where the area has another: use the
        area's, or keep the zone's own (an override the card says so about)."""
        entry = self._config_entry
        keys = location.differing_keys(self.hass, entry, self._token[len(location.AREA_PREFIX):])
        if user_input is not None:
            return self._finish_location(self._token, {k for k in keys if user_input.get(k)}, {})
        return self.async_show_form(
            step_id="location_sensors",
            data_schema=vol.Schema({vol.Required(key, default=True): bool for key in keys}),
        )

    async def async_step_new_area(self, user_input: dict[str, Any] | None = None):
        """Make an area from this zone's own sensors and put the zone in it."""
        errors: dict[str, str] = {}
        controller = self._controller()
        merged = self._merged()
        defaults: dict[str, Any] = (
            location.area_defaults(controller) if controller is not None
            else {key: merged.get(key) for key in (*AREA_SHARED_KEYS, CONF_RAIN_SOURCE)}
        )
        if user_input is not None:
            name = _clean_name(user_input.get(CONF_AREA_NAME))
            if not name:
                errors["base"] = "area_name_required"
            elif _area_name_taken(self.hass, name):
                errors["base"] = "area_name_exists"
            else:
                result = await self.hass.config_entries.flow.async_init(
                    DOMAIN, context={"source": "area_create"}, data={**user_input, "name": name}
                )
                new_id = result["result"].entry_id
                return self._finish_location(location.AREA_PREFIX + new_id, None, errors)
            defaults = {**defaults, **user_input}
        return self.async_show_form(step_id="new_area", data_schema=_area_schema(defaults), errors=errors)

    async def async_step_zone_type(self, user_input: dict[str, Any] | None = None):
        """Change where the zone grows. Nothing is deleted: what the new
        type doesn't use is hidden, and comes back if the type is changed
        back."""
        errors: dict[str, str] = {}
        if user_input is not None:
            new_type = user_input[CONF_ZONE_TYPE]
            if new_type == ZONE_TYPE_OUTDOOR and not self._has_valve():
                errors["base"] = "valve_required_outdoor"
            elif new_type == ZONE_TYPE_OUTDOOR and _has_crops(self.hass, self._config_entry.entry_id):
                errors["base"] = "greenhouse_has_crops"
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
            result = await self._apply_flow_rate(controller, mm_per_min)
            if result.get("reason") == "flow_rate_set":  # only when the entry was accepted
                await self._set_zone_flow(controller, round(float(user_input["emitters"])) * per_emitter_l_h / 60)
            return result
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

    async def async_step_flow_volume(self, user_input: dict[str, Any] | None = None):
        """Without a flow meter: the person runs a Service Run, catches or
        reads the litres, and enters them here. The result is the zone's
        AVERAGE depth per minute (litres / area / minutes); different
        emitters on one valve cannot be told apart."""
        controller = self._controller()
        if controller is None:
            return self.async_abort(reason="zone_not_loaded")
        imperial = controller.imperial
        if user_input is not None:
            liters = float(user_input["volume"]) * (units.LITERS_PER_GALLON if imperial else 1.0)
            area_m2 = float(user_input["area"]) * (units.M2_PER_FT2 if imperial else 1.0)
            mm_per_min = liters / area_m2 / float(user_input["minutes"])
            result = await self._apply_flow_rate(controller, mm_per_min)
            if result.get("reason") == "flow_rate_set":
                await self._set_zone_flow(controller, liters / float(user_input["minutes"]))
            return result
        return self.async_show_form(
            step_id="flow_volume",
            data_schema=vol.Schema(
                {
                    vol.Required("minutes", default=15): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1, max=240, step=1, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="min"
                        )
                    ),
                    vol.Required("volume", default=10.0): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.01, max=1000000, step=0.01, mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="gal" if imperial else "L",
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

    async def _set_zone_flow(self, controller, l_per_min: float) -> None:
        """Zone Flow (litres per minute) only converts valve time to litres
        for the water-use estimate. Left alone when it is not a sensible
        number or its entity is disabled."""
        _name, lo, hi, _step, _unit = NUMBER_DEFS["zone_flow_l_min"]
        number = controller.numbers.get("zone_flow_l_min")
        if number is not None and lo < l_per_min <= hi:
            await number.async_set_metric_value(round(l_per_min, 2))

    async def async_step_zone_flow(self, user_input: dict[str, Any] | None = None):
        """Zone Flow from the heads: how many, and what one gives (drippers
        are usually rated per hour, sprinklers per minute). Sets only the
        zone's total flow, for the water-use estimate; the Emitter Flow
        Rate Calibration is not touched."""
        controller = self._controller()
        if controller is None:
            return self.async_abort(reason="zone_not_loaded")
        imperial = controller.imperial
        per_hour, per_minute = ("gal/h", "gal/min") if imperial else ("L/h", "L/min")
        if user_input is not None:
            one = float(user_input["head_flow"]) * (units.LITERS_PER_GALLON if imperial else 1.0)
            if user_input["head_flow_unit"] == per_hour:
                one /= 60
            l_per_min = round(float(user_input["heads"])) * one
            _name, lo, hi, _step, _unit = NUMBER_DEFS["zone_flow_l_min"]
            number = controller.numbers.get("zone_flow_l_min")
            if number is None:
                return self.async_abort(reason="flow_rate_disabled")
            if not lo < l_per_min <= hi:
                return self.async_abort(reason="zone_flow_out_of_range")
            await number.async_set_metric_value(round(l_per_min, 2))
            shown = f"{units.to_display('zone_flow_l_min', l_per_min, imperial):.2f} {per_minute}"
            return self.async_abort(reason="zone_flow_set", description_placeholders={"flow": shown})
        return self.async_show_form(
            step_id="zone_flow",
            data_schema=vol.Schema(
                {
                    vol.Required("heads", default=10): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=1, max=5000, step=1, mode=selector.NumberSelectorMode.BOX)
                    ),
                    vol.Required("head_flow", default=2.0): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0.01, max=10000, step=0.01, mode=selector.NumberSelectorMode.BOX)
                    ),
                    vol.Required("head_flow_unit", default=per_hour): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=[per_hour, per_minute], mode=selector.SelectSelectorMode.DROPDOWN)
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
