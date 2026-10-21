"""Plant lookup when a zone is set up: an optional field on the first screen; when it is filled in, a
screen shows what the plant database says, and the pick becomes the zone's starting weekly targets.
Left empty, nothing changes and no screen is added."""
from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.zoneflow import plant_water
from custom_components.zoneflow.const import (
    CONF_INITIAL_NUMBERS,
    CONF_IRRIGATION_METHOD,
    CONF_QUICK_SETUP,
    CONF_VALVE_ENTITY,
    CONF_ZONE_NAME,
    CONF_ZONE_TYPE,
    DOMAIN,
    NUMBER_DEFS,
    PLANT_PRESETS,
)

from .test_suggest import _house

VALVE = "switch.sprinkler_valve"
FLOW = {"emitters": 10, "emitter_flow": 2.0, "area": 2.0}


async def _first(hass, search, plant="tomatoes", **extra):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ZONE_NAME: "Cucumber bed", "plant": plant, CONF_ZONE_TYPE: "outdoor", CONF_QUICK_SETUP: True,
         **({"plant_search": search} if search is not None else {}), **extra},
    )


def _options(result):
    schema = next(v for k, v in result["data_schema"].schema.items() if getattr(k, "schema", k) == "pick")
    return {o["value"]: o["label"] for o in schema.config["options"]}


# --- the numbers ------------------------------------------------------------------
def test_the_normal_week_gets_the_middle_and_the_others_keep_their_proportion():
    base = PLANT_PRESETS["tomatoes"]["numbers"]  # 30 / 40 / 20
    got = plant_water.suggested_numbers(25.4, 38.1, base)  # middle 31.75
    assert got["target_weekly_mm"] == 32.0
    assert got["target_weekly_hot_mm"] == 42.5 and got["target_weekly_cool_mm"] == 21.0
    assert got["target_weekly_cool_mm"] <= got["target_weekly_mm"] <= got["target_weekly_hot_mm"]


def test_a_plant_with_no_preset_starts_from_the_ordinary_values_and_stays_in_the_slider_ranges():
    for low, high in ((12.7, 12.7), (50.8, 76.2), (200.0, 200.0), (1.0, 1.0)):
        got = plant_water.suggested_numbers(low, high)
        for key, value in got.items():
            _name, lo, hi, step, _unit = NUMBER_DEFS[key]
            assert lo <= value <= hi, (key, value)
            assert abs(value / step - round(value / step)) < 1e-6, (key, value)


# --- the flow ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_left_empty_there_is_no_extra_screen(hass, fake_valve_services):
    _house(hass)
    for search in (None, "", "   "):
        result = await _first(hass, search)
        assert result["step_id"] == "quick", search


@pytest.mark.asyncio
async def test_a_plant_that_is_found_is_picked_and_becomes_the_starting_weekly_targets(hass, fake_valve_services):
    _house(hass)
    result = await _first(hass, "cucumber")
    assert result["step_id"] == "plant_pick"
    options = _options(result)
    assert list(options)[0] == "" and "cucumber" in options["0"].lower() and "varieties" in options["0"]  # the kind, first
    assert "mm" in options["0"]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"pick": "0"})
    assert result["step_id"] == "quick"  # on with the setup
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VALVE_ENTITY: VALVE, CONF_IRRIGATION_METHOD: "drip", **FLOW}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    data = await hass.async_add_executor_job(plant_water._load)
    kind = plant_water.search(data, "cucumber")[0]
    expected = plant_water.suggested_numbers(kind["low_mm"], kind["high_mm"], PLANT_PRESETS["tomatoes"]["numbers"])
    numbers = result["result"].data[CONF_INITIAL_NUMBERS]
    assert all(numbers[key] == value for key, value in expected.items())
    assert numbers["crop_coefficient"] == PLANT_PRESETS["tomatoes"]["numbers"]["crop_coefficient"]  # the rest of the preset stays


@pytest.mark.asyncio
async def test_keeping_the_starting_values_changes_nothing(hass, fake_valve_services):
    _house(hass)
    result = await _first(hass, "cucumber")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"pick": ""})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VALVE_ENTITY: VALVE, CONF_IRRIGATION_METHOD: "drip", **FLOW}
    )
    numbers = result["result"].data[CONF_INITIAL_NUMBERS]
    for key in plant_water.TARGET_KEYS:
        assert numbers[key] == PLANT_PRESETS["tomatoes"]["numbers"][key]


@pytest.mark.asyncio
async def test_nothing_found_says_so_and_goes_on(hass, fake_valve_services):
    _house(hass)
    result = await _first(hass, "zzzz")
    assert result["step_id"] == "plant_pick"
    assert list(_options(result)) == [""]
    assert "zzzz" in result["description_placeholders"]["result"]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"pick": ""})
    assert result["step_id"] == "quick"


@pytest.mark.asyncio
async def test_a_plant_with_only_words_is_not_offered(hass, fake_valve_services):
    _house(hass)
    result = await _first(hass, "hass avocado")  # the database has words for it, but no weekly amount
    assert list(_options(result)) == [""]


@pytest.mark.asyncio
async def test_the_full_setup_gets_the_lookup_too(hass, fake_valve_services):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ZONE_NAME: "Basil", "plant": "herbs", CONF_ZONE_TYPE: "outdoor", "plant_search": "genovese basil"}
    )
    assert result["step_id"] == "plant_pick"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"pick": ""})
    assert result["step_id"] == "entities"  # no quick setup ticked: the full form follows


@pytest.mark.asyncio
async def test_imperial_zones_see_inches(hass, fake_valve_services):
    from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

    hass.config.units = US_CUSTOMARY_SYSTEM
    _house(hass)
    result = await _first(hass, "cucumber")
    label = _options(result)["0"]
    assert " in" in label and " mm" not in label


@pytest.mark.asyncio
async def test_a_crop_in_a_greenhouse_gets_the_lookup_too(hass, fake_valve_services):
    from custom_components.zoneflow.const import CONF_PARENT_ZONE

    from .test_greenhouse_crops import VALVE_B, _climate_only_entry, _load, _seed_all

    await _seed_all(hass)
    house = _climate_only_entry(hass)
    await _load(hass, house)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "crop"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_PARENT_ZONE: house.entry_id, CONF_ZONE_NAME: "Cucumbers", "plant": "custom", "plant_search": "cucumber"},
    )
    assert result["step_id"] == "plant_pick"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"pick": "0"})
    assert result["step_id"] == "crop_valve"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_VALVE_ENTITY: VALVE_B})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "temperatures"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    data = await hass.async_add_executor_job(plant_water._load)
    kind = plant_water.search(data, "cucumber")[0]
    expected = plant_water.suggested_numbers(kind["low_mm"], kind["high_mm"])  # "something else": the ordinary starting values
    numbers = result["result"].data[CONF_INITIAL_NUMBERS]
    assert all(numbers[key] == value for key, value in expected.items())

