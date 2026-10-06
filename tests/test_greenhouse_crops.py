"""One greenhouse, several crops (1.6.1): a crop is a zone that belongs to a
greenhouse (the zone with the climate devices), has its own valve, probe and
watering, and uses the greenhouse's inside sensors."""
from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, issue_registry as ir

from custom_components.zoneflow.const import (
    CONF_CSV_PATH,
    CONF_FAN_ENTITIES,
    CONF_INSIDE_TEMP_ENTITY,
    CONF_PARENT_ZONE,
    CONF_PLANT,
    CONF_PUMP_ID,
    CONF_VALVE_ENTITY,
    CONF_ZONE_NAME,
    CONF_ZONE_TYPE,
    DOMAIN,
)

from .test_smoke_setup import make_entry
from .test_zone_types import FAN, INSIDE_TEMP, _climate_only_entry, _seed

OTHER_TEMP = "sensor.gh_temperature_2"
VALVE_A = "switch.valve_tomatoes"
VALVE_B = "switch.valve_peppers"


def _crop(hass, name, valve, parent, **extra):
    return make_entry(
        hass,
        **{
            CONF_ZONE_NAME: name,
            CONF_ZONE_TYPE: "greenhouse",
            CONF_VALVE_ENTITY: valve,
            CONF_PARENT_ZONE: parent.entry_id,
            CONF_CSV_PATH: f"/tmp/test_zoneflow_{name}.csv",
            **extra,
        },
    )


async def _seed_all(hass):
    for entity, state in ((VALVE_A, "off"), (VALVE_B, "off"), (OTHER_TEMP, "20")):
        hass.states.async_set(entity, state)
    await _seed(hass)


async def _load(hass, first):
    assert await hass.config_entries.async_setup(first.entry_id)
    await hass.async_block_till_done()


def _ctl(hass, entry):
    return hass.data[DOMAIN][entry.entry_id]


@pytest.mark.asyncio
async def test_a_crop_uses_its_greenhouses_sensors_live(hass, fake_valve_services):
    await _seed_all(hass)
    house = _climate_only_entry(hass, **{CONF_PUMP_ID: "gh supply"})
    crop = _crop(hass, "Tomatoes", VALVE_A, house)
    await _load(hass, house)
    c = _ctl(hass, crop)
    assert c.is_crop and c.zone_type == "greenhouse"
    assert c.inside_temp_entity == INSIDE_TEMP
    assert c.outdoor_temp_entity == INSIDE_TEMP  # what its watering goes by
    assert not c.has_climate_devices
    assert [z.entry.entry_id for z in _ctl(hass, house).crops] == [crop.entry_id]

    # The greenhouse gets a new inside sensor: the crop follows (reloaded).
    hass.config_entries.async_update_entry(house, options={**house.options, CONF_INSIDE_TEMP_ENTITY: OTHER_TEMP})
    await hass.async_block_till_done()
    assert _ctl(hass, crop).inside_temp_entity == OTHER_TEMP


@pytest.mark.asyncio
async def test_crop_device_is_connected_via_the_greenhouse_and_cards_know_both(hass, fake_valve_services):
    await _seed_all(hass)
    house = _climate_only_entry(hass)
    crop = _crop(hass, "Tomatoes", VALVE_A, house)
    await _load(hass, house)
    registry = dr.async_get(hass)
    house_dev = registry.async_get_device(identifiers={(DOMAIN, house.entry_id)})
    crop_dev = registry.async_get_device(identifiers={(DOMAIN, crop.entry_id)})
    assert crop_dev.via_device_id == house_dev.id

    status = next(s for s in hass.states.async_all("sensor") if s.entity_id == "sensor.tomatoes_status")
    assert status.attributes["greenhouse"] == {"name": "Tunnel", "device_id": house_dev.id}
    _ctl(hass, house)._notify_status()
    await hass.async_block_till_done()
    house_status = next(s for s in hass.states.async_all("sensor") if s.entity_id == "sensor.tunnel_status")
    assert house_status.attributes["crops"] == [{"name": "Tomatoes", "device_id": crop_dev.id}]


@pytest.mark.asyncio
async def test_add_a_crop_through_the_setup_flow(hass, fake_valve_services):
    await _seed_all(hass)
    house = _climate_only_entry(hass, **{CONF_PUMP_ID: "gh supply"})
    await _load(hass, house)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] == FlowResultType.MENU and "crop" in result["menu_options"]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "crop"})
    assert result["step_id"] == "crop"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PARENT_ZONE: house.entry_id, CONF_ZONE_NAME: "Peppers", CONF_PLANT: "chilis"}
    )
    assert result["step_id"] == "crop_valve"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_VALVE_ENTITY: VALVE_B})
    assert result["step_id"] == "watering"
    # The pump ID is the greenhouse's, so the crops don't open together.
    pump_key = next(k for k in result["data_schema"].schema if str(k) == CONF_PUMP_ID)
    assert pump_key.default() == "gh supply"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PUMP_ID: "gh supply"},  # everything else: the defaults
    )
    assert result["step_id"] == "temperatures"  # no climate question: the greenhouse's
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_PARENT_ZONE] == house.entry_id and data[CONF_ZONE_TYPE] == "greenhouse"
    assert data[CONF_VALVE_ENTITY] == VALVE_B and CONF_FAN_ENTITIES not in data
    assert CONF_INSIDE_TEMP_ENTITY not in data  # read live from the greenhouse


@pytest.mark.asyncio
async def test_no_crop_choice_without_a_greenhouse(hass, fake_valve_services):
    await _seed_all(hass)
    first = make_entry(hass)
    await _load(hass, first)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert "crop" not in result.get("menu_options", [])


@pytest.mark.asyncio
async def test_crop_configure_menu_and_link_unlink(hass, fake_valve_services):
    await _seed_all(hass)
    house = _climate_only_entry(hass)
    # Today's workaround: a separate greenhouse zone with its own valve.
    loose = make_entry(
        hass,
        **{CONF_ZONE_NAME: "Peppers", CONF_ZONE_TYPE: "greenhouse", CONF_VALVE_ENTITY: VALVE_B,
           CONF_INSIDE_TEMP_ENTITY: OTHER_TEMP, CONF_CSV_PATH: "/tmp/test_zoneflow_peppers.csv"},
    )
    await _load(hass, house)
    menu = await hass.config_entries.options.async_init(loose.entry_id)
    assert "greenhouse_link" in menu["menu_options"]
    result = await hass.config_entries.options.async_configure(menu["flow_id"], {"next_step_id": "greenhouse_link"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_PARENT_ZONE: house.entry_id})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    c = _ctl(hass, loose)
    assert c.is_crop and c.inside_temp_entity == INSIDE_TEMP

    menu = await hass.config_entries.options.async_init(loose.entry_id)
    assert "crop_valve" in menu["menu_options"]
    assert "zone_type" not in menu["menu_options"] and "greenhouse_devices" not in menu["menu_options"]

    # Back on its own: it keeps a copy of the greenhouse's sensor.
    result = await hass.config_entries.options.async_configure(menu["flow_id"], {"next_step_id": "greenhouse_link"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_PARENT_ZONE: ""})
    await hass.async_block_till_done()
    c = _ctl(hass, loose)
    assert not c.is_crop and c.inside_temp_entity == INSIDE_TEMP


@pytest.mark.asyncio
async def test_a_greenhouse_with_crops_cannot_become_outdoor(hass, fake_valve_services):
    await _seed_all(hass)
    house = _climate_only_entry(hass, **{CONF_VALVE_ENTITY: "switch.valve_house"})
    hass.states.async_set("switch.valve_house", "off")
    _crop(hass, "Tomatoes", VALVE_A, house)
    await _load(hass, house)
    menu = await hass.config_entries.options.async_init(house.entry_id)
    result = await hass.config_entries.options.async_configure(menu["flow_id"], {"next_step_id": "zone_type"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_ZONE_TYPE: "outdoor"})
    assert result["errors"] == {"base": "greenhouse_has_crops"}


@pytest.mark.asyncio
async def test_deleting_the_greenhouse_leaves_working_crops(hass, fake_valve_services):
    await _seed_all(hass)
    house = _climate_only_entry(hass)
    crop = _crop(hass, "Tomatoes", VALVE_A, house)
    await _load(hass, house)
    assert await hass.config_entries.async_remove(house.entry_id)
    await hass.async_block_till_done()
    c = _ctl(hass, crop)
    assert not c.is_crop
    assert c.inside_temp_entity == INSIDE_TEMP and c.has_valve
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"{crop.entry_id}_greenhouse_removed") is not None


@pytest.mark.asyncio
async def test_an_offline_inside_sensor_is_not_reported_on_every_crop(hass, fake_valve_services):
    from custom_components.zoneflow import issues

    await _seed_all(hass)
    house = _climate_only_entry(hass)
    crop = _crop(hass, "Tomatoes", VALVE_A, house)
    await _load(hass, house)
    assert issues._sensors(_ctl(hass, crop))["temperature"] is None


@pytest.mark.asyncio
async def test_a_crop_shows_no_climate_status_or_control(hass, fake_valve_services):
    from homeassistant.helpers import entity_registry as er

    await _seed_all(hass)
    house = _climate_only_entry(hass)
    crop = _crop(hass, "Tomatoes", VALVE_A, house)
    await _load(hass, house)
    registry = er.async_get(hass)
    entries = {(e.domain, e.translation_key): e for e in er.async_entries_for_config_entry(registry, crop.entry_id)}
    assert entries[("sensor", "greenhouse_status")].hidden_by == er.RegistryEntryHider.INTEGRATION
    assert entries[("switch", "greenhouse_control")].hidden_by == er.RegistryEntryHider.INTEGRATION
    house_entries = {(e.domain, e.translation_key): e for e in er.async_entries_for_config_entry(registry, house.entry_id)}
    assert house_entries[("switch", "greenhouse_control")].hidden_by is None


@pytest.mark.asyncio
async def test_a_zone_that_names_itself_as_its_greenhouse_is_just_a_zone(hass, fake_valve_services):
    await _seed_all(hass)
    house = _climate_only_entry(hass)
    crop = _crop(hass, "Tomatoes", VALVE_A, house)
    hass.config_entries.async_update_entry(crop, options={CONF_PARENT_ZONE: crop.entry_id})
    await _load(hass, house)
    c = _ctl(hass, crop)
    assert not c.is_crop and c.has_valve
    assert c.crops == []  # not a crop of itself


@pytest.mark.asyncio
async def test_a_crop_is_in_its_greenhouses_garden_area(hass, fake_valve_services):
    from custom_components.zoneflow.const import CONF_GARDEN_AREA

    await _seed_all(hass)
    house = _climate_only_entry(hass)
    crop = _crop(hass, "Tomatoes", VALVE_A, house)
    await _load(hass, house)
    assert _ctl(hass, house).garden_area is None and _ctl(hass, crop).garden_area is None
    hass.config_entries.async_update_entry(house, options={**house.options, CONF_GARDEN_AREA: "Backyard"})
    await hass.async_block_till_done()
    assert _ctl(hass, house).garden_area == "Backyard"
    assert _ctl(hass, crop).garden_area == "Backyard"  # follows its greenhouse
