"""1.6 batch 1: zone types (outdoor / greenhouse / indoor), a zone with no
valve, the greenhouse setup and Configure steps, and what a zone type hides.

An outdoor zone, and any zone made before 1.6, must behave exactly as it did.
"""
from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zoneflow.const import (
    CONF_CLIMATE,
    CONF_CSV_PATH,
    CONF_DEEP_SOAK_TIME,
    CONF_FAN_ENTITIES,
    CONF_HEATER_ENTITIES,
    CONF_INSIDE_HUMIDITY_ENTITY,
    CONF_INSIDE_TEMP_ENTITY,
    CONF_MISTER_ENTITIES,
    CONF_NOTIFY_ENTITY,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_PLANT,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_ROUTINE_TIME,
    CONF_VALVE_ENTITY,
    CONF_VENT_ENTITIES,
    CONF_WEATHER_ENTITY,
    CONF_ZONE_NAME,
    CONF_ZONE_TYPE,
    DOMAIN,
)

from .test_config_flow import _minimal_entities_input
from .test_smoke_setup import OUTDOOR_TEMP, RAIN_COUNTER, VALVE, make_entry

INSIDE_TEMP = "sensor.gh_temperature"
INSIDE_HUM = "sensor.gh_humidity"
FAN = "switch.gh_fan"
VENT = "cover.gh_vent"
MISTER = "switch.gh_mister"
HEATER = "switch.gh_heater"


async def _seed(hass):
    for entity, state in (
        (INSIDE_TEMP, "24"), (INSIDE_HUM, "60"), (OUTDOOR_TEMP, "30"), (RAIN_COUNTER, "0"),
        (VALVE, "off"), (FAN, "off"), (VENT, "closed"), (MISTER, "off"), (HEATER, "off"),
    ):
        hass.states.async_set(entity, state)
    await hass.async_block_till_done()


def _climate_only_entry(hass, **overrides):
    data = {
        CONF_ZONE_NAME: "Tunnel",
        CONF_ZONE_TYPE: "greenhouse",
        CONF_INSIDE_TEMP_ENTITY: INSIDE_TEMP,
        CONF_FAN_ENTITIES: [FAN],
        CONF_CSV_PATH: "/tmp/test_zoneflow_tunnel.csv",
        CONF_DEEP_SOAK_TIME: "05:00:00",
        CONF_ROUTINE_TIME: "05:30:00",
    }
    data.update(overrides)
    entry = MockConfigEntry(domain=DOMAIN, data=data, title=data[CONF_ZONE_NAME])
    entry.add_to_hass(hass)
    return entry


async def _setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


def _reg(hass, entry):
    return er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)


# ---------------------------------------------------------------- unchanged

@pytest.mark.asyncio
async def test_existing_zone_is_outdoor_and_unchanged(hass, fake_valve_services):
    await _seed(hass)
    entry = make_entry(hass)
    controller = await _setup(hass, entry)
    assert controller.zone_type == "outdoor" and controller.is_outdoor
    assert controller.has_valve and controller.valve_entity == VALVE
    assert controller.rain_counter_entity == RAIN_COUNTER
    assert controller.outdoor_temp_entity == OUTDOOR_TEMP
    assert controller.outside_temp_entity == OUTDOOR_TEMP
    assert not controller.has_climate_devices


@pytest.mark.asyncio
async def test_new_outdoor_zone_stores_no_zone_type(hass, fake_valve_services):
    """A zone set up as outdoor is stored exactly like a 1.5 zone."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ZONE_NAME: "Garden", CONF_PLANT: "custom", CONF_ZONE_TYPE: "outdoor"}
    )
    assert result["step_id"] == "entities"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _minimal_entities_input())
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_CLIMATE: "temperate"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {k.schema: k.default() for k in result["data_schema"].schema}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_ZONE_TYPE not in result["data"]


# ------------------------------------------------------------ greenhouse zone

@pytest.mark.asyncio
async def test_greenhouse_zone_has_no_rain_gauge_and_waters_by_inside_temperature(hass, fake_valve_services):
    await _seed(hass)
    entry = make_entry(
        hass,
        **{CONF_ZONE_TYPE: "greenhouse", CONF_INSIDE_TEMP_ENTITY: INSIDE_TEMP, CONF_WEATHER_ENTITY: "weather.home"},
    )
    controller = await _setup(hass, entry)
    assert controller.zone_type == "greenhouse" and not controller.is_outdoor
    assert controller.rain_counter_entity is None
    assert controller.weather_entity is None
    assert controller.outdoor_temp_entity == INSIDE_TEMP  # what watering goes by
    assert controller.outside_temp_entity == OUTDOOR_TEMP  # kept for the ventilation gate
    registry = {(e.domain, e.translation_key): e for e in _reg(hass, entry)}
    assert registry[("sensor", "rain_today")].hidden_by == er.RegistryEntryHider.INTEGRATION
    assert registry[("number", "forecast_rain_threshold_mm")].hidden_by == er.RegistryEntryHider.INTEGRATION


# --------------------------------------------------------- zone without valve

@pytest.mark.asyncio
async def test_zone_without_valve_loads_and_never_waters(hass, fake_valve_services):
    await _seed(hass)
    entry = _climate_only_entry(hass)
    controller = await _setup(hass, entry)
    assert controller.has_valve is False and controller.valve_entity is None
    assert controller.fan_entities == [FAN] and controller.has_climate_devices
    # No irrigation schedule and nothing that opens a valve.
    await controller.run_routine_irrigation()
    await controller.run_deep_soak()
    assert controller.store.state.lock_on is False
    for call in (controller.run_routine_now, controller.run_deep_soak_now):
        with pytest.raises(ServiceValidationError):
            await call()
    with pytest.raises(ServiceValidationError):
        await controller.test_pulse(5)
    with pytest.raises(ServiceValidationError):
        await controller.start_service_run(1)
    assert hass.states.get(VALVE).state == "off"  # nothing ever opened it


@pytest.mark.asyncio
async def test_zone_without_valve_hides_watering_entities_and_unhides_them_with_a_valve(hass, fake_valve_services):
    await _seed(hass)
    entry = _climate_only_entry(hass, **{CONF_NOTIFY_ENTITY: "notify.phone"})
    await _setup(hass, entry)
    registry = {(e.domain, e.translation_key): e for e in _reg(hass, entry)}
    hidden = er.RegistryEntryHider.INTEGRATION
    assert registry[("number", "target_weekly_mm")].hidden_by == hidden
    assert registry[("button", "run_routine")].hidden_by == hidden
    assert registry[("sensor", "status")].hidden_by == hidden
    assert registry[("select", "notifications")].hidden_by is None  # still shown

    # Add a valve later: the zone reloads and the watering entities return.
    hass.config_entries.async_update_entry(entry, options={CONF_VALVE_ENTITY: VALVE})
    await hass.async_block_till_done()
    registry = {(e.domain, e.translation_key): e for e in _reg(hass, entry)}
    assert registry[("number", "target_weekly_mm")].hidden_by is None
    assert registry[("button", "run_routine")].hidden_by is None
    controller = hass.data[DOMAIN][entry.entry_id]
    assert controller.has_valve and controller.valve_entity == VALVE


@pytest.mark.asyncio
async def test_zone_without_valve_survives_restart_of_the_zone(hass, fake_valve_services):
    await _seed(hass)
    entry = _climate_only_entry(hass)
    await _setup(hass, entry)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][entry.entry_id].has_valve is False


# ------------------------------------------------------------------ setup flow

async def _start_non_outdoor(hass, zone_type="greenhouse"):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    if result["type"] == "menu":  # a zone already exists: add a zone
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "zone"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ZONE_NAME: "Tunnel", CONF_PLANT: "tomatoes", CONF_ZONE_TYPE: zone_type}
    )
    assert result["type"] == FlowResultType.FORM and result["step_id"] == "greenhouse_devices"
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize("zone_type", ["greenhouse", "indoor"])
async def test_setup_climate_only_zone(hass, zone_type):
    result = await _start_non_outdoor(hass, zone_type)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_INSIDE_TEMP_ENTITY: INSIDE_TEMP,
            CONF_INSIDE_HUMIDITY_ENTITY: INSIDE_HUM,
            CONF_FAN_ENTITIES: [FAN],
            CONF_VENT_ENTITIES: [VENT],
            CONF_MISTER_ENTITIES: [MISTER],
            CONF_HEATER_ENTITIES: [HEATER],
            "unit_system": "auto",
        },
    )
    assert result["step_id"] == "water_valve"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "climate"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_CLIMATE: "tropical"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_ZONE_TYPE] == zone_type
    assert data["initial_numbers"]["vent_temp"] == 28.0 and data["initial_numbers"]["heat_temp"] == 15.0
    assert CONF_VALVE_ENTITY not in data
    assert data[CONF_FAN_ENTITIES] == [FAN] and data[CONF_MISTER_ENTITIES] == [MISTER]
    assert data[CONF_CSV_PATH].endswith("zoneflow_tunnel.csv")


@pytest.mark.asyncio
async def test_setup_greenhouse_with_valve_goes_through_watering(hass):
    result = await _start_non_outdoor(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_INSIDE_TEMP_ENTITY: INSIDE_TEMP, CONF_FAN_ENTITIES: [FAN], "unit_system": "auto"},
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_VALVE_ENTITY: VALVE})
    assert result["step_id"] == "watering"
    fields = {str(k.schema) for k in result["data_schema"].schema}
    assert not {CONF_VALVE_ENTITY, CONF_RAIN_COUNTER_ENTITY, CONF_WEATHER_ENTITY, CONF_OUTDOOR_TEMP_ENTITY} & fields
    watering = _minimal_entities_input()
    for key in (CONF_VALVE_ENTITY, CONF_CSV_PATH):
        watering.pop(key)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], watering)
    assert result["step_id"] == "climate"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_CLIMATE: "tropical"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {k.schema: k.default() for k in result["data_schema"].schema}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_ZONE_TYPE] == "greenhouse" and data[CONF_VALVE_ENTITY] == VALVE
    assert data[CONF_INSIDE_TEMP_ENTITY] == INSIDE_TEMP and data[CONF_FAN_ENTITIES] == [FAN]


@pytest.mark.asyncio
async def test_setup_errors(hass):
    result = await _start_non_outdoor(hass)
    # A device without the inside temperature sensor.
    bad = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_FAN_ENTITIES: [FAN], "unit_system": "auto"}
    )
    assert bad["errors"] == {CONF_INSIDE_TEMP_ENTITY: "inside_temp_required"}
    # The same entity in two roles.
    bad = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_INSIDE_TEMP_ENTITY: INSIDE_TEMP, CONF_FAN_ENTITIES: [FAN], CONF_HEATER_ENTITIES: [FAN], "unit_system": "auto"},
    )
    assert bad["errors"] == {"base": "device_in_two_roles"}
    # No valve and no device.
    ok = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_INSIDE_TEMP_ENTITY: INSIDE_TEMP, "unit_system": "auto"}
    )
    assert ok["step_id"] == "water_valve"
    bad = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert bad["errors"] == {"base": "valve_or_device_required"}


@pytest.mark.asyncio
async def test_a_device_cannot_belong_to_two_zones(hass, fake_valve_services):
    await _seed(hass)
    _climate_only_entry(hass)
    result = await _start_non_outdoor(hass)
    bad = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_INSIDE_TEMP_ENTITY: INSIDE_TEMP, CONF_FAN_ENTITIES: [FAN], "unit_system": "auto"},
    )
    assert bad["errors"] == {"base": "device_already_used"}


# --------------------------------------------------------------- Configure

async def _menu(hass, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    return result


@pytest.mark.asyncio
async def test_configure_menu_per_zone_type(hass, fake_valve_services):
    await _seed(hass)
    outdoor = make_entry(hass)
    await _setup(hass, outdoor)
    assert (await _menu(hass, outdoor))["menu_options"] == ["settings", "flow_rate", "zone_type"]

    greenhouse = _climate_only_entry(hass)
    await _setup(hass, greenhouse)
    assert (await _menu(hass, greenhouse))["menu_options"] == ["greenhouse_devices", "zone_type"]

    with_valve = _climate_only_entry(
        hass, **{CONF_ZONE_NAME: "Other", CONF_FAN_ENTITIES: [HEATER], CONF_VALVE_ENTITY: "switch.other_valve",
                 CONF_CSV_PATH: "/tmp/other.csv"}
    )
    hass.states.async_set("switch.other_valve", "off")
    await _setup(hass, with_valve)
    assert (await _menu(hass, with_valve))["menu_options"] == [
        "greenhouse_devices", "watering", "flow_rate", "zone_type"
    ]


@pytest.mark.asyncio
async def test_configure_can_add_a_valve_and_devices_later_without_losing_other_options(hass, fake_valve_services):
    await _seed(hass)
    entry = _climate_only_entry(hass, **{CONF_ZONE_TYPE: "indoor"})
    await _setup(hass, entry)
    menu = await _menu(hass, entry)
    form = await hass.config_entries.options.async_configure(menu["flow_id"], {"next_step_id": "greenhouse_devices"})
    assert form["step_id"] == "greenhouse_devices"
    result = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {
            CONF_VALVE_ENTITY: VALVE,
            CONF_INSIDE_TEMP_ENTITY: INSIDE_TEMP,
            CONF_FAN_ENTITIES: [FAN],
            CONF_MISTER_ENTITIES: [MISTER],
            "unit_system": "auto",
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options[CONF_VALVE_ENTITY] == VALVE
    assert entry.options[CONF_MISTER_ENTITIES] == [MISTER]
    assert entry.options[CONF_OUTDOOR_TEMP_ENTITY] is None  # cleared sensors are stored empty
    controller = hass.data[DOMAIN][entry.entry_id]
    assert controller.valve_entity == VALVE and controller.mister_entities == [MISTER]
    assert controller.zone_type == "indoor"


@pytest.mark.asyncio
async def test_configure_needs_a_valve_or_a_device(hass, fake_valve_services):
    await _seed(hass)
    entry = _climate_only_entry(hass)
    await _setup(hass, entry)
    menu = await _menu(hass, entry)
    form = await hass.config_entries.options.async_configure(menu["flow_id"], {"next_step_id": "greenhouse_devices"})
    bad = await hass.config_entries.options.async_configure(
        form["flow_id"], {CONF_INSIDE_TEMP_ENTITY: INSIDE_TEMP, "unit_system": "auto"}
    )
    assert bad["errors"] == {"base": "valve_or_device_required"}


@pytest.mark.asyncio
async def test_zone_type_can_change_and_outdoor_needs_a_valve(hass, fake_valve_services):
    await _seed(hass)
    entry = _climate_only_entry(hass)
    await _setup(hass, entry)
    menu = await _menu(hass, entry)
    form = await hass.config_entries.options.async_configure(menu["flow_id"], {"next_step_id": "zone_type"})
    bad = await hass.config_entries.options.async_configure(form["flow_id"], {CONF_ZONE_TYPE: "outdoor"})
    assert bad["errors"] == {"base": "valve_required_outdoor"}
    done = await hass.config_entries.options.async_configure(form["flow_id"], {CONF_ZONE_TYPE: "indoor"})
    assert done["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][entry.entry_id].zone_type == "indoor"


@pytest.mark.asyncio
async def test_outdoor_settings_save_keeps_the_zone_type_option(hass, fake_valve_services):
    await _seed(hass)
    entry = make_entry(hass)
    await _setup(hass, entry)
    hass.config_entries.async_update_entry(entry, options={CONF_ZONE_TYPE: "outdoor", "marker": 1})
    menu = await _menu(hass, entry)
    form = await hass.config_entries.options.async_configure(menu["flow_id"], {"next_step_id": "settings"})
    result = await hass.config_entries.options.async_configure(form["flow_id"], _minimal_entities_input())
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()  # the update listener reloads the zone
    assert entry.options[CONF_ZONE_TYPE] == "outdoor" and entry.options["marker"] == 1


@pytest.mark.asyncio
async def test_outdoor_zone_changed_to_greenhouse_starts_from_its_climate_preset(hass, fake_valve_services):
    from custom_components.zoneflow.const import CONF_CLIMATE

    await _seed(hass)
    entry = make_entry(hass, **{CONF_CLIMATE: "tropical"})
    await _setup(hass, entry)
    menu = await _menu(hass, entry)
    form = await hass.config_entries.options.async_configure(menu["flow_id"], {"next_step_id": "zone_type"})
    done = await hass.config_entries.options.async_configure(form["flow_id"], {CONF_ZONE_TYPE: "greenhouse"})
    assert done["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    assert controller.number("heat_temp") == 15.0  # tropical, not the temperate default of 10
    assert controller.number("vent_temp") == 28.0


# ------------------------------------------- a greenhouse that waters with a probe

@pytest.mark.asyncio
@pytest.mark.parametrize(("moisture", "runs"), [("10", True), ("80", False)])
async def test_greenhouse_with_valve_and_soil_probe_waters_by_the_moisture(hass, fake_valve_services, moisture, runs):
    """A greenhouse or indoor zone with a valve waters like an outdoor zone,
    including by its soil-moisture probe: dry soil waters early, wet soil
    skips."""
    from unittest.mock import AsyncMock

    probe = "sensor.gh_soil_moisture"
    await _seed(hass)
    hass.states.async_set(probe, moisture)
    entry = make_entry(
        hass, **{CONF_ZONE_TYPE: "greenhouse", CONF_INSIDE_TEMP_ENTITY: INSIDE_TEMP, "soil_moisture_entity": probe}
    )
    controller = await _setup(hass, entry)
    assert controller.has_valve and controller.soil_moisture_entity == probe
    registry = {(e.domain, e.translation_key): e for e in _reg(hass, entry)}
    # The probe's own settings and sensors are shown, not hidden.
    assert registry[("sensor", "soil_moisture")].hidden_by is None
    assert registry[("number", "soil_moisture_dry_pct")].hidden_by is None
    # Last watering just now (the interval is not due): only the probe can start one.
    import homeassistant.util.dt as dt_util

    controller.store.state.last_routine_ts = dt_util.utcnow().timestamp() if runs else 0.0
    controller.store.state.last_significant_rain_ts = 0.0
    spy = AsyncMock(return_value=True)
    controller._run_pulses = spy
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    assert spy.called is runs


@pytest.mark.asyncio
async def test_one_greenhouse_with_a_climate_zone_and_several_watering_zones(hass, fake_valve_services):
    """Different crops in one greenhouse today: one climate zone owns the
    fans, vents, misters and heater; each crop is its own greenhouse zone
    with its own valve and probe, all reading the same inside temperature
    sensor (sensors may be shared; valves and climate devices may not)."""
    from unittest.mock import AsyncMock

    for entity in ("switch.valve_tomatoes", "switch.valve_peppers", "sensor.probe_tomatoes", "sensor.probe_peppers"):
        hass.states.async_set(entity, "off" if entity.startswith("switch") else "50")
    await _seed(hass)
    climate = _climate_only_entry(hass)
    crops = []
    for name, valve, probe in (("Tomatoes", "switch.valve_tomatoes", "sensor.probe_tomatoes"),
                               ("Peppers", "switch.valve_peppers", "sensor.probe_peppers")):
        crops.append(make_entry(
            hass,
            **{CONF_ZONE_NAME: name, CONF_ZONE_TYPE: "greenhouse", CONF_INSIDE_TEMP_ENTITY: INSIDE_TEMP,
               CONF_VALVE_ENTITY: valve, "soil_moisture_entity": probe,
               CONF_CSV_PATH: f"/tmp/test_zoneflow_{name}.csv"},
        ))
    controller_climate = await _setup(hass, climate)  # sets up every entry of the integration
    controllers = [hass.data[DOMAIN][entry.entry_id] for entry in crops]

    assert controller_climate.has_climate_devices and not controller_climate.has_valve
    assert all(c.has_valve and not c.has_climate_devices for c in controllers)
    assert all(c.inside_temp_entity == INSIDE_TEMP for c in controllers)
    # Each crop waters by its own probe: dry tomatoes, wet peppers.
    hass.states.async_set("sensor.probe_tomatoes", "10")
    hass.states.async_set("sensor.probe_peppers", "80")
    import homeassistant.util.dt as dt_util

    spies = []
    for c in controllers:
        c.store.state.last_routine_ts = dt_util.utcnow().timestamp()
        c.store.state.last_significant_rain_ts = 0.0
        spy = AsyncMock(return_value=True)
        c._run_pulses = spy
        spies.append(spy)
    for c in controllers:
        await c.run_routine_irrigation()
    await hass.async_block_till_done()
    assert spies[0].called is True and spies[1].called is False
