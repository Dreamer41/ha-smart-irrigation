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


class _Texts:
    kind = staticmethod(lambda summary: summary["name"])
    crop = staticmethod(lambda crop: crop["name"])
    kc = staticmethod(lambda value: f"kc {value:g}")
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
    expected = plant_water.suggested_numbers(kind["low_mm"], kind["high_mm"], PLANT_PRESETS["tomatoes"]["numbers"], kind["kc"])
    numbers = result["result"].data[CONF_INITIAL_NUMBERS]
    assert all(numbers[key] == value for key, value in expected.items())
    assert numbers["crop_coefficient"] == 1.0  # the FAO crop factor of cucumbers, not the tomato preset's


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
async def test_a_plant_with_only_a_crop_factor_is_offered_for_that(hass, fake_valve_services):
    _house(hass)
    result = await _first(hass, "hass avocado")  # no weekly amount in the database, but FAO-56 has avocado
    options = _options(result)
    assert any("crop factor 0.85" in label and "mm" not in label for label in options.values())
    index = next(v for v, label in options.items() if "Hass Avocado" in label)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"pick": index})
    assert result["step_id"] == "quick"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VALVE_ENTITY: VALVE, CONF_IRRIGATION_METHOD: "drip", **FLOW}
    )
    numbers = result["result"].data[CONF_INITIAL_NUMBERS]
    assert numbers["crop_coefficient"] == 0.85
    for key in plant_water.TARGET_KEYS:  # no weekly amount: the preset's weekly water stays
        assert numbers[key] == PLANT_PRESETS["tomatoes"]["numbers"][key]


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
    expected = plant_water.suggested_numbers(kind["low_mm"], kind["high_mm"], None, kind["kc"])  # "something else": the ordinary starting values
    numbers = result["result"].data[CONF_INITIAL_NUMBERS]
    assert all(numbers[key] == value for key, value in expected.items())


# --- the picker on the first screen ---------------------------------------------------
def _field(result):
    return next(v for k, v in result["data_schema"].schema.items() if getattr(k, "schema", k) == "plant_search")


async def _first_form(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


@pytest.mark.asyncio
async def test_the_first_screen_has_a_searchable_list_of_plants_with_their_amounts(hass, fake_valve_services):
    result = await _first_form(hass)
    config = _field(result).config
    assert config["custom_value"] is True  # the picker that filters as you type; other text is searched for
    options = config["options"]
    assert len(options) > 600
    assert options[0]["value"].startswith("kind:") and "varieties" in options[0]["label"] and " mm" in options[0]["label"]
    assert any(o["value"].startswith("plant:") and ": 25.4-38.1 mm" in o["label"] for o in options)
    assert any(o["value"] == "crop:avocado" and "crop factor 0.85" in o["label"] for o in options)  # FAO-only crops too
    assert all(o["value"].split(":")[0] in ("kind", "crop", "plant") for o in options)


@pytest.mark.asyncio
async def test_a_plant_picked_on_the_first_screen_goes_straight_on(hass, fake_valve_services):
    _house(hass)
    result = await _first_form(hass)
    options = {o["label"]: o["value"] for o in _field(result).config["options"]}
    picked = next(value for label, value in options.items() if label.startswith("Jalape") and "Craig" in label)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ZONE_NAME: "Chilis", "plant": "chilis", CONF_ZONE_TYPE: "outdoor", CONF_QUICK_SETUP: True, "plant_search": picked},
    )
    assert result["step_id"] == "quick"  # no extra screen
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VALVE_ENTITY: VALVE, CONF_IRRIGATION_METHOD: "drip", **FLOW}
    )
    numbers = result["result"].data[CONF_INITIAL_NUMBERS]
    expected = plant_water.suggested_numbers(25.4, 25.4, PLANT_PRESETS["chilis"]["numbers"], 1.05)  # a pepper: FAO crop factor 1.05
    assert all(numbers[key] == value for key, value in expected.items())


@pytest.mark.asyncio
async def test_a_kind_picked_on_the_first_screen_works_too(hass, fake_valve_services):
    _house(hass)
    result = await _first_form(hass)
    kind = next(o["value"] for o in _field(result).config["options"] if o["value"] == "kind:cucumber")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ZONE_NAME: "Cucumbers", "plant": "custom", CONF_ZONE_TYPE: "outdoor", CONF_QUICK_SETUP: True, "plant_search": kind},
    )
    assert result["step_id"] == "quick"


@pytest.mark.asyncio
async def test_text_that_is_not_in_the_list_is_searched_for_on_the_next_screen(hass, fake_valve_services):
    _house(hass)
    result = await _first(hass, "cucumb")
    assert result["step_id"] == "plant_pick"


@pytest.mark.asyncio
async def test_the_list_is_in_inches_for_imperial(hass, fake_valve_services):
    from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

    hass.config.units = US_CUSTOMARY_SYSTEM
    options = _field(await _first_form(hass)).config["options"]
    weekly = [o for o in options if ": " in o["label"] and not o["label"].split(": ")[1].startswith("crop factor")]
    assert weekly and all(" in" in o["label"] and " mm" not in o["label"] for o in weekly)


@pytest.mark.parametrize("value", ["", "cucumber", "plant:", "plant:abc", "plant:999999", "plant:-1", "kind:nothing", "kind:", "x:1"])
def test_odd_values_are_not_a_pick(value):
    data = plant_water._load()
    assert plant_water.resolve(data, value) is None


def test_a_plant_with_only_words_is_never_in_the_list():
    data = plant_water._load()
    words_only = next(i for i, p in enumerate(data["plants"]) if p["low_mm"] is None)
    assert plant_water.resolve(data, f"plant:{words_only}") is None
    assert all(not value.endswith(f":{words_only}") for value, _ in plant_water.picker_options(data, False, _Texts))


@pytest.mark.asyncio
async def test_the_lookup_comes_before_whats_planted_which_is_the_fallback(hass, fake_valve_services):
    result = await _first_form(hass)
    names = [getattr(k, "schema", k) for k in result["data_schema"].schema]
    assert names.index("plant_search") < names.index("plant")
    assert names.index(CONF_ZONE_NAME) < names.index("plant_search")
    # What's planted is still required: it is what a plant that is not found falls back on.
    plant_key = next(k for k in result["data_schema"].schema if getattr(k, "schema", k) == "plant")
    assert plant_key.default() == "custom" or plant_key.default is not None


# --- What's planted follows the pick when it was left on "Something else" ----------------
async def _pick_and_finish(hass, label_part, plant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    options = {o["label"]: o["value"] for o in _field(result).config["options"]}
    picked = next(value for label, value in options.items() if label_part in label)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ZONE_NAME: "Bed", "plant": plant, CONF_ZONE_TYPE: "outdoor", CONF_QUICK_SETUP: True, "plant_search": picked},
    )
    assert result["step_id"] == "quick"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VALVE_ENTITY: VALVE, CONF_IRRIGATION_METHOD: "drip", **FLOW}
    )
    return result["result"].data


@pytest.mark.asyncio
async def test_a_pick_chooses_the_plant_type_when_whats_planted_was_left_open(hass, fake_valve_services):
    from custom_components.zoneflow.const import CONF_DEEP_SOAK_ENABLED, CONF_PLANT

    _house(hass)
    data = await _pick_and_finish(hass, "Avocado (FAO-56)", "custom")
    assert data[CONF_PLANT] == "fruit_tree"  # the zone's plant type, and the type's own starting values
    assert data[CONF_DEEP_SOAK_ENABLED] is PLANT_PRESETS["fruit_tree"]["deep_soak"]
    assert data[CONF_INITIAL_NUMBERS]["crop_coefficient"] == 0.85  # the pick's value, not the type's


@pytest.mark.asyncio
async def test_a_plant_type_the_person_chose_is_kept(hass, fake_valve_services):
    from custom_components.zoneflow.const import CONF_PLANT

    _house(hass)
    data = await _pick_and_finish(hass, "Avocado (FAO-56)", "young_tree")
    assert data[CONF_PLANT] == "young_tree"


@pytest.mark.asyncio
async def test_a_kind_picked_gets_its_types_proportions(hass, fake_valve_services):
    from custom_components.zoneflow.const import CONF_PLANT

    _house(hass)
    data = await _pick_and_finish(hass, "Pepper, the middle of all", "custom")
    assert data[CONF_PLANT] == "chilis"
    plants = await hass.async_add_executor_job(plant_water._load)
    kind = next(r for r in plant_water.search(plants, "pepper") if r["kind"] == "category")
    expected = plant_water.suggested_numbers(kind["low_mm"], kind["high_mm"], PLANT_PRESETS["chilis"]["numbers"], kind["kc"])
    assert all(data[CONF_INITIAL_NUMBERS][key] == value for key, value in expected.items())


@pytest.mark.asyncio
async def test_a_pick_with_no_fitting_type_stays_on_something_else(hass, fake_valve_services):
    from custom_components.zoneflow.const import CONF_PLANT

    _house(hass)
    data = await _pick_and_finish(hass, "Potato (FAO-56)", "custom")
    assert data[CONF_PLANT] == "custom"
    assert data[CONF_INITIAL_NUMBERS]["crop_coefficient"] == 1.15


def test_every_plant_type_the_lookup_names_exists():
    kc = __import__("json").loads(plant_water.KC_FILE.read_text(encoding="utf-8"))
    crops = {c["id"] for c in kc["crops"]}
    assert set(plant_water.PRESET_BY_CROP) <= crops
    for table in (plant_water.PRESET_BY_CROP, plant_water.PRESET_BY_CATEGORY):
        assert set(table.values()) <= set(PLANT_PRESETS)

