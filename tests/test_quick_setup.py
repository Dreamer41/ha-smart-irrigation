"""Quick setup (1.7.1): a new outdoor zone asks for its name, the valve and how
it is watered; the rest comes from the plant type, the sensors that were
clearly found and the climate defaults."""
from __future__ import annotations

import pytest
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType, InvalidData

from custom_components.zoneflow.const import (
    CLIMATE_PRESETS,
    CONF_AREA_ID,
    CONF_CLIMATE,
    CONF_DEEP_SOAK_ENABLED,
    CONF_DEEP_SOAK_TIME,
    CONF_INITIAL_NUMBERS,
    CONF_IRRIGATION_METHOD,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_QUICK_SETUP,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_ROUTINE_TIME,
    CONF_VALVE_ENTITY,
    CONF_ZONE_NAME,
    CONF_ZONE_TYPE,
    DEFAULT_CLIMATE,
    DOMAIN,
    PLANT_PRESETS,
)

from .test_suggest import _house

VALVE = "switch.sprinkler_valve"
# 10 drippers of 2 L/h on 2 m2: 20 L/h -> 10 mm/h on the wet area.
FLOW = {"emitters": 10, "emitter_flow": 2.0, "area": 2.0}


async def _first_form(hass, **extra):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ZONE_NAME: "Tomato bed", "plant": "tomatoes", CONF_ZONE_TYPE: "outdoor", **extra}
    )


@pytest.mark.asyncio
async def test_the_quick_box_is_ticked_in_the_form_but_off_when_left_out(hass, fake_valve_services):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    keys = {getattr(k, "schema", k): k for k in result["data_schema"].schema}
    assert keys[CONF_QUICK_SETUP].description == {"suggested_value": True}
    # A call that leaves it out gets the full setup, as before.
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ZONE_NAME: "Bed"})
    assert result["step_id"] == "entities"


@pytest.mark.asyncio
async def test_quick_setup_asks_for_the_valve_and_the_method_only(hass, fake_valve_services):
    _house(hass)
    result = await _first_form(hass, **{CONF_QUICK_SETUP: True})
    assert result["step_id"] == "quick"
    assert set(getattr(k, "schema", k) for k in result["data_schema"].schema) == {CONF_VALVE_ENTITY, CONF_IRRIGATION_METHOD, "emitters", "emitter_flow", "area"}
    assert "Garden rain (3.2 mm)" in result["description_placeholders"]["suggestions"]


@pytest.mark.asyncio
async def test_quick_setup_makes_a_working_zone_with_the_found_sensors(hass, fake_valve_services):
    _house(hass)
    result = await _first_form(hass, **{CONF_QUICK_SETUP: True})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VALVE_ENTITY: VALVE, CONF_IRRIGATION_METHOD: "drip", **FLOW}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    data = result["result"].data
    assert result["title"] == "Tomato bed"
    assert data[CONF_VALVE_ENTITY] == VALVE and data[CONF_IRRIGATION_METHOD] == "drip"
    assert data[CONF_RAIN_COUNTER_ENTITY] == "sensor.garden_rain_gauge"  # the clearly found sensors
    assert data[CONF_OUTDOOR_TEMP_ENTITY] == "sensor.outdoor_temperature"
    assert data[CONF_CLIMATE] == DEFAULT_CLIMATE
    assert data[CONF_DEEP_SOAK_ENABLED] is PLANT_PRESETS["tomatoes"]["deep_soak"]  # the plant type's settings
    assert data[CONF_ROUTINE_TIME] == "05:30:00" and data[CONF_DEEP_SOAK_TIME].count(":") == 2
    numbers = data[CONF_INITIAL_NUMBERS]
    assert numbers["target_weekly_mm"] == PLANT_PRESETS["tomatoes"]["numbers"]["target_weekly_mm"]
    assert numbers["hot_temp_threshold"] == CLIMATE_PRESETS[DEFAULT_CLIMATE]["hot_temp_threshold"]
    assert numbers["flow_rate_mm_per_min"] == pytest.approx(10 * 2.0 / 2.0 / 60, abs=0.001)  # from what was entered
    assert numbers["zone_flow_l_min"] == pytest.approx(20 / 60, abs=0.01)


@pytest.mark.asyncio
async def test_the_zone_made_by_quick_setup_starts(hass, fake_valve_services):
    hass.states.async_set(VALVE, "off")
    result = await _first_form(hass, **{CONF_QUICK_SETUP: True})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_VALVE_ENTITY: VALVE, **FLOW})
    await hass.async_block_till_done()
    entry = result["result"]
    assert hass.data[DOMAIN][entry.entry_id].has_valve


@pytest.mark.asyncio
async def test_quick_setup_refuses_a_valve_another_zone_uses(hass, fake_valve_services):
    hass.states.async_set(VALVE, "off")
    first = await _first_form(hass, **{CONF_QUICK_SETUP: True})
    await hass.config_entries.flow.async_configure(first["flow_id"], {CONF_VALVE_ENTITY: VALVE, **FLOW})
    await hass.async_block_till_done()
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "zone"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ZONE_NAME: "Other", "plant": "chilis", CONF_ZONE_TYPE: "outdoor", CONF_QUICK_SETUP: True}
    )
    assert result["step_id"] == "quick"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_VALVE_ENTITY: VALVE, **FLOW})
    assert result["type"] == FlowResultType.FORM and result["errors"]


@pytest.mark.asyncio
async def test_quick_setup_in_an_area_leaves_the_areas_sensors_to_the_area(hass, fake_valve_services):
    from .test_areas import _area, _boot

    area = _area(hass)
    await _boot(hass, area)
    _house(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "zone"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ZONE_NAME: "Bed", "plant": "tomatoes", CONF_ZONE_TYPE: "outdoor", "location": area.entry_id, CONF_QUICK_SETUP: True},
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_VALVE_ENTITY: VALVE, **FLOW})
    data = result["result"].data
    assert data[CONF_AREA_ID] == area.entry_id
    assert CONF_RAIN_COUNTER_ENTITY not in data and CONF_OUTDOOR_TEMP_ENTITY not in data  # the area provides them


@pytest.mark.asyncio
async def test_unticking_quick_setup_gives_the_full_steps(hass, fake_valve_services):
    result = await _first_form(hass, **{CONF_QUICK_SETUP: False})
    assert result["step_id"] == "entities"


@pytest.mark.asyncio
async def test_the_flow_is_asked_for_and_has_no_default(hass, fake_valve_services):
    result = await _first_form(hass, **{CONF_QUICK_SETUP: True})
    schema = {getattr(k, "schema", k): k for k in result["data_schema"].schema}
    for key in ("emitters", "emitter_flow", "area"):
        assert isinstance(schema[key], vol.Required) and schema[key].default is vol.UNDEFINED
    with pytest.raises(InvalidData):  # not accepted without it
        await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_VALVE_ENTITY: VALVE})


@pytest.mark.asyncio
async def test_a_sprinkler_gives_a_much_higher_flow_than_drip(hass, fake_valve_services):
    result = await _first_form(hass, **{CONF_QUICK_SETUP: True})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_VALVE_ENTITY: VALVE, CONF_IRRIGATION_METHOD: "sprinkler", "emitters": 2, "emitter_flow": 600.0, "area": 30.0},
    )
    # 1200 L/h on 30 m2 = 40 mm/h
    assert result["result"].data[CONF_INITIAL_NUMBERS]["flow_rate_mm_per_min"] == pytest.approx(40 / 60, abs=0.001)


@pytest.mark.asyncio
async def test_an_impossible_flow_is_refused_with_a_message(hass, fake_valve_services):
    result = await _first_form(hass, **{CONF_QUICK_SETUP: True})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VALVE_ENTITY: VALVE, "emitters": 1, "emitter_flow": 0.05, "area": 500.0}
    )
    assert result["type"] == FlowResultType.FORM and result["errors"] == {"base": "flow_rate_out_of_range"}
