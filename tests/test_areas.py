"""Areas (1.7.0): a part of the garden that holds the sensors its zones share,
plus its own Pause and Snooze Today."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zoneflow import location
from custom_components.zoneflow.const import (
    AREA_DATA_KEY,
    CONF_AREA_ID,
    CONF_AREA_MM_PER_TIP,
    CONF_AREA_NAME,
    CONF_CSV_PATH,
    CONF_ENTRY_TYPE,
    CONF_NOTIFY_ENTITY,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_PARENT_ZONE,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_RAIN_SOURCE,
    CONF_VALVE_ENTITY,
    CONF_WEATHER_ENTITY,
    CONF_ZONE_NAME,
    CONF_ZONE_TYPE,
    DOMAIN,
    ENTRY_TYPE_AREA,
)

from .test_greenhouse_crops import VALVE_A, VALVE_B, _crop, _seed_all
from .test_smoke_setup import make_entry
from .test_zone_types import _climate_only_entry

AREA_RAIN = "sensor.backyard_rain_tips"
AREA_TEMP = "sensor.backyard_temperature"
AREA_WEATHER = "weather.backyard"
OWN_RAIN = "sensor.tomato_rain_tips"
OWN_TEMP = "sensor.tomato_temperature"


def _area(hass, name="Backyard", **extra):
    data = {
        CONF_ENTRY_TYPE: ENTRY_TYPE_AREA,
        CONF_RAIN_COUNTER_ENTITY: AREA_RAIN,
        CONF_RAIN_SOURCE: "tips",
        CONF_AREA_MM_PER_TIP: 0.3,
        CONF_OUTDOOR_TEMP_ENTITY: AREA_TEMP,
        CONF_WEATHER_ENTITY: AREA_WEATHER,
        CONF_NOTIFY_ENTITY: None,
        **extra,
    }
    entry = MockConfigEntry(domain=DOMAIN, data=data, title=name)
    entry.add_to_hass(hass)
    return entry


def _zone(hass, name="Tomatoes", valve=VALVE_A, **extra):
    data = {
        CONF_ZONE_NAME: name,
        CONF_VALVE_ENTITY: valve,
        CONF_RAIN_COUNTER_ENTITY: None,
        CONF_OUTDOOR_TEMP_ENTITY: None,
        CONF_CSV_PATH: f"/tmp/test_zoneflow_{name}.csv",
        **extra,
    }
    return make_entry(hass, **data)


async def _boot(hass, *entries):
    for entity, state in ((AREA_RAIN, "0"), (AREA_TEMP, "28"), (AREA_WEATHER, "sunny"), (OWN_RAIN, "0"), (OWN_TEMP, "30")):
        hass.states.async_set(entity, state)
    await _seed_all(hass)
    assert await hass.config_entries.async_setup(entries[0].entry_id)
    await hass.async_block_till_done()


def _ctl(hass, entry):
    return hass.data[DOMAIN][entry.entry_id]


def _area_ctl(hass, entry):
    return hass.data[AREA_DATA_KEY][entry.entry_id]


@pytest.mark.asyncio
async def test_a_zone_uses_its_areas_sensors(hass, fake_valve_services):
    area = _area(hass)
    zone = _zone(hass, **{CONF_AREA_ID: area.entry_id})
    await _boot(hass, area, zone)
    c = _ctl(hass, zone)
    assert c.garden_area == "Backyard"
    assert c.rain_counter_entity == AREA_RAIN and c.outdoor_temp_entity == AREA_TEMP
    assert c.weather_entity == AREA_WEATHER and c.rain_from_area
    assert c.rain_mm_per_tip == pytest.approx(0.3)  # the gauge's tip size is the area's
    assert c.area_overrides() == []


@pytest.mark.asyncio
async def test_a_zones_own_sensor_wins_and_is_reported(hass, fake_valve_services):
    area = _area(hass)
    zone = _zone(hass, **{CONF_AREA_ID: area.entry_id, CONF_RAIN_COUNTER_ENTITY: OWN_RAIN, CONF_OUTDOOR_TEMP_ENTITY: AREA_TEMP})
    await _boot(hass, area, zone)
    c = _ctl(hass, zone)
    assert c.rain_counter_entity == OWN_RAIN and not c.rain_from_area
    assert c.rain_mm_per_tip == c.number("rain_mm_per_tip")  # its own slider
    assert c.outdoor_temp_entity == AREA_TEMP  # the same as the area's: no override
    assert c.area_overrides() == ["rain_counter_entity"]
    status = hass.states.get("sensor.tomatoes_status")
    assert status.attributes["garden_area"] == "Backyard"


@pytest.mark.asyncio
async def test_a_zone_outside_any_area_is_unchanged(hass, fake_valve_services):
    zone = _zone(hass, **{CONF_RAIN_COUNTER_ENTITY: OWN_RAIN})
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    assert c.area is None and c.garden_area is None and c.rain_counter_entity == OWN_RAIN


@pytest.mark.asyncio
async def test_the_area_pause_is_a_second_layer(hass, fake_valve_services):
    area = _area(hass)
    zone = _zone(hass, **{CONF_AREA_ID: area.entry_id})
    other = _zone(hass, "Chilis", VALVE_B, **{CONF_AREA_ID: area.entry_id})
    await _boot(hass, area, zone, other)
    c, o, a = _ctl(hass, zone), _ctl(hass, other), _area_ctl(hass, area)
    spy = AsyncMock(wraps=c._run_pulses)
    c._run_pulses = spy

    await a.set_paused(True)
    assert c.paused and o.paused
    assert not c.own_paused and hass.states.get("switch.tomatoes_pause").state == "off"
    assert hass.states.get("switch.backyard_pause").state == "on"
    await c.run_deep_soak()
    await c.run_routine_irrigation()
    spy.assert_not_called()
    assert c.status()["code"] == "paused"

    # The zone's own pause stays when the area resumes.
    await c.set_paused(True)
    await a.set_paused(False)
    assert c.paused and not o.paused
    await c.set_paused(False)
    assert not c.paused


@pytest.mark.asyncio
async def test_snooze_today_for_the_whole_area(hass, fake_valve_services):
    area = _area(hass)
    zone = _zone(hass, **{CONF_AREA_ID: area.entry_id})
    await _boot(hass, area, zone)
    c, a = _ctl(hass, zone), _area_ctl(hass, area)
    assert not c._is_snoozed_today()
    await hass.services.async_call("button", "press", {"entity_id": "button.backyard_snooze_today"}, blocking=True)
    assert a.snoozed_today and c._is_snoozed_today()
    assert c.status()["code"] == "snoozed"


@pytest.mark.asyncio
async def test_the_areas_water_total_adds_up_its_zones(hass, fake_valve_services):
    area = _area(hass)
    one = _zone(hass, **{CONF_AREA_ID: area.entry_id})
    two = _zone(hass, "Chilis", VALVE_B, **{CONF_AREA_ID: area.entry_id})
    await _boot(hass, area, one, two)
    assert hass.states.get("sensor.backyard_water_used_past_30_days").state in ("unknown", "unavailable")
    _ctl(hass, one)._add_to_water_ledger(5.0, 100.0)
    _ctl(hass, two)._add_to_water_ledger(5.0, 50.0)
    from homeassistant.helpers.entity_component import async_update_entity

    await async_update_entity(hass, "sensor.backyard_water_used_past_30_days")
    assert float(hass.states.get("sensor.backyard_water_used_past_30_days").state) == pytest.approx(150.0)


@pytest.mark.asyncio
async def test_a_crop_is_in_its_greenhouses_area(hass, fake_valve_services):
    area = _area(hass)
    house = _climate_only_entry(hass, **{CONF_AREA_ID: area.entry_id})
    crop = _crop(hass, "Tomatoes", VALVE_A, house)
    await _boot(hass, area, house, crop)
    assert _ctl(hass, house).garden_area == "Backyard"
    assert _ctl(hass, crop).garden_area == "Backyard"
    assert {z.entry.entry_id for z in _area_ctl(hass, area).zones} == {house.entry_id, crop.entry_id}
    # A paused area pauses its greenhouse's crops too.
    await _area_ctl(hass, area).set_paused(True)
    assert _ctl(hass, crop).paused


@pytest.mark.asyncio
async def test_moving_a_zone_into_an_area_keeps_a_different_sensor(hass, fake_valve_services):
    area = _area(hass)
    zone = _zone(hass, **{CONF_RAIN_COUNTER_ENTITY: AREA_RAIN, CONF_OUTDOOR_TEMP_ENTITY: OWN_TEMP})
    await _boot(hass, area, zone)
    token = location.AREA_PREFIX + area.entry_id
    # The same gauge is dropped (the area's is used); the different thermometer stays an override.
    assert location.differing_keys(hass, zone, area.entry_id) == [CONF_OUTDOOR_TEMP_ENTITY]
    await location.async_set(hass, zone, token)
    await hass.async_block_till_done()
    c = _ctl(hass, zone)
    assert c.area_entry_id == area.entry_id and c.rain_from_area
    assert zone.options[CONF_RAIN_COUNTER_ENTITY] is None
    assert c.outdoor_temp_entity == OWN_TEMP and c.area_overrides() == [CONF_OUTDOOR_TEMP_ENTITY]

    # Asked to use the area's thermometer instead.
    await location.async_set(hass, zone, location.NONE_TOKEN)
    await hass.async_block_till_done()
    await location.async_set(hass, zone, token, {CONF_OUTDOOR_TEMP_ENTITY})
    await hass.async_block_till_done()
    assert _ctl(hass, zone).outdoor_temp_entity == AREA_TEMP


@pytest.mark.asyncio
async def test_leaving_an_area_keeps_what_the_zone_was_getting(hass, fake_valve_services):
    area = _area(hass)
    zone = _zone(hass, **{CONF_AREA_ID: area.entry_id})
    await _boot(hass, area, zone)
    await location.async_set(hass, zone, location.NONE_TOKEN)
    await hass.async_block_till_done()
    c = _ctl(hass, zone)
    assert c.area is None and c.rain_counter_entity == AREA_RAIN and c.weather_entity == AREA_WEATHER


@pytest.mark.asyncio
async def test_a_zone_can_become_a_crop_and_back(hass, fake_valve_services):
    area = _area(hass)
    house = _climate_only_entry(hass, **{CONF_AREA_ID: area.entry_id})
    zone = _zone(hass, **{CONF_AREA_ID: area.entry_id})
    await _boot(hass, area, house, zone)
    choices = dict(location.choices(hass, zone))
    gh_token = next(t for t in choices if t.startswith(location.GREENHOUSE_PREFIX))
    await location.async_set(hass, zone, gh_token)
    await hass.async_block_till_done()
    c = _ctl(hass, zone)
    assert c.is_crop and c.zone_type == house.data[CONF_ZONE_TYPE] and c.garden_area == "Backyard"
    assert location.current_token(zone) == gh_token

    await location.async_set(hass, zone, location.NONE_TOKEN)
    await hass.async_block_till_done()
    assert not _ctl(hass, zone).is_crop


@pytest.mark.asyncio
async def test_the_location_dropdown_lists_the_places_and_moves_the_zone(hass, fake_valve_services):
    area = _area(hass)
    zone = _zone(hass)
    await _boot(hass, area, zone)
    state = hass.states.get("select.tomatoes_where_is_this")
    assert state.state == "None" and "Backyard" in state.attributes["options"]
    await hass.services.async_call(
        "select", "select_option", {"entity_id": "select.tomatoes_where_is_this", "option": "Backyard"}, blocking=True
    )
    await hass.async_block_till_done()
    assert _ctl(hass, zone).area_entry_id == area.entry_id
    assert hass.states.get("select.tomatoes_where_is_this").state == "Backyard"


@pytest.mark.asyncio
async def test_a_deleted_area_leaves_its_zones_with_a_copy(hass, fake_valve_services):
    area = _area(hass)
    zone = _zone(hass, **{CONF_AREA_ID: area.entry_id})
    await _boot(hass, area, zone)
    assert await hass.config_entries.async_remove(area.entry_id)
    await hass.async_block_till_done()
    c = _ctl(hass, zone)
    assert c.area is None and c.rain_counter_entity == AREA_RAIN and c.outdoor_temp_entity == AREA_TEMP
    assert c.number("rain_mm_per_tip") == pytest.approx(0.3)  # the gauge's tip size goes with it
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"{zone.entry_id}_area_removed") is not None


@pytest.mark.asyncio
async def test_changing_the_area_sensors_reloads_its_zones(hass, fake_valve_services):
    area = _area(hass)
    zone = _zone(hass, **{CONF_AREA_ID: area.entry_id})
    await _boot(hass, area, zone)
    hass.states.async_set("sensor.new_temp", "20")
    hass.config_entries.async_update_entry(area, options={CONF_OUTDOOR_TEMP_ENTITY: "sensor.new_temp"})
    await hass.async_block_till_done()
    assert _ctl(hass, zone).outdoor_temp_entity == "sensor.new_temp"


@pytest.mark.asyncio
async def test_a_zone_loaded_before_its_area_picks_it_up(hass, fake_valve_services):
    zone = _zone(hass)
    await _boot(hass, zone)
    first = _ctl(hass, zone)
    area = _area(hass)
    hass.config_entries.async_update_entry(zone, options={CONF_AREA_ID: area.entry_id})
    await hass.async_block_till_done()
    assert await hass.config_entries.async_setup(area.entry_id)
    await hass.async_block_till_done()
    c = _ctl(hass, zone)
    assert c.rain_counter_entity == AREA_RAIN and c.had_area_at_setup
    assert c is not first or first.had_area_at_setup


# --- the screens -------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_area_is_added_from_the_start_menu(hass, fake_valve_services):
    zone = _zone(hass)
    await _boot(hass, zone)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.MENU and "area" in result["menu_options"]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "area"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_AREA_NAME: "  Front   yard ", CONF_RAIN_COUNTER_ENTITY: AREA_RAIN, CONF_AREA_MM_PER_TIP: 0.25},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY and result["title"] == "Front yard"
    assert result["data"][CONF_ENTRY_TYPE] == ENTRY_TYPE_AREA and result["data"][CONF_AREA_MM_PER_TIP] == 0.25
    await hass.async_block_till_done()
    assert len(hass.data[AREA_DATA_KEY]) == 1

    # The same name again is refused.
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "area"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_AREA_NAME: "front YARD"})
    assert result["errors"] == {"base": "area_name_exists"}


@pytest.mark.asyncio
async def test_configure_moves_a_zone_into_an_area(hass, fake_valve_services):
    area = _area(hass)
    zone = _zone(hass, **{CONF_OUTDOOR_TEMP_ENTITY: OWN_TEMP})
    await _boot(hass, area, zone)
    result = await hass.config_entries.options.async_init(zone.entry_id)
    assert "location" in result["menu_options"] and "greenhouse_link" not in result["menu_options"]
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "location"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"location": location.AREA_PREFIX + area.entry_id}
    )
    # The thermometer differs: asked which to use.
    assert result["step_id"] == "location_sensors"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_OUTDOOR_TEMP_ENTITY: False})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    c = _ctl(hass, zone)
    assert c.area_entry_id == area.entry_id and c.outdoor_temp_entity == OWN_TEMP and c.rain_from_area


@pytest.mark.asyncio
async def test_configure_makes_a_new_area_from_the_zones_sensors(hass, fake_valve_services):
    zone = _zone(hass, **{CONF_RAIN_COUNTER_ENTITY: OWN_RAIN, CONF_OUTDOOR_TEMP_ENTITY: OWN_TEMP})
    await _boot(hass, zone)
    result = await hass.config_entries.options.async_init(zone.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "location"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"location": "__new_area__"})
    assert result["step_id"] == "new_area"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_AREA_NAME: "Vegetable beds", CONF_RAIN_COUNTER_ENTITY: OWN_RAIN, CONF_OUTDOOR_TEMP_ENTITY: OWN_TEMP,
         CONF_AREA_MM_PER_TIP: 0.254},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    areas = list(hass.data[AREA_DATA_KEY].values())
    assert [a.name for a in areas] == ["Vegetable beds"]
    c = _ctl(hass, zone)
    assert c.area is areas[0] and c.rain_from_area and c.rain_counter_entity == OWN_RAIN
    assert c.rain_mm_per_tip == pytest.approx(0.254)


@pytest.mark.asyncio
async def test_an_area_is_renamed_and_its_sensors_changed_in_configure(hass, fake_valve_services):
    area = _area(hass)
    zone = _zone(hass, **{CONF_AREA_ID: area.entry_id})
    await _boot(hass, area, zone)
    result = await hass.config_entries.options.async_init(area.entry_id)
    assert result["step_id"] == "area_settings"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_AREA_NAME: "Back garden", CONF_RAIN_COUNTER_ENTITY: AREA_RAIN, CONF_AREA_MM_PER_TIP: 0.5}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert area.title == "Back garden"
    assert _ctl(hass, zone).garden_area == "Back garden" and _ctl(hass, zone).rain_mm_per_tip == pytest.approx(0.5)
    assert _ctl(hass, zone).outdoor_temp_entity is None  # cleared in the form


@pytest.mark.asyncio
async def test_the_status_names_the_areas_pause_and_snooze_for_the_cards(hass, fake_valve_services):
    area = _area(hass)
    zone = _zone(hass, **{CONF_AREA_ID: area.entry_id})
    alone = _zone(hass, "Chilis", VALVE_B)
    await _boot(hass, area, zone, alone)
    attrs = hass.states.get("sensor.tomatoes_status").attributes
    assert attrs["area_pause"] == "switch.backyard_pause" and attrs["area_snooze"] == "button.backyard_snooze_today"
    assert hass.states.get("sensor.chilis_status").attributes["area_pause"] is None
