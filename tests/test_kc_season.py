"""1.8: the seasonal crop factor. A picked crop curve (data/crop_kc.json, FAO-56 Tables 11 and 12) replaces
the fixed Crop Factor slider; a zone with no curve picked waters exactly as before. The climate
adjustment (eq. 62) and the Sun Exposure factor sit on top of it, in controller.kc_info."""
from __future__ import annotations

from datetime import timedelta

import homeassistant.util.dt as dt_util
import pytest

from custom_components.zoneflow import crop_season, fao56, visibility
from custom_components.zoneflow import messages as zf_messages
from custom_components.zoneflow import setup_check, why
from custom_components.zoneflow.const import (
    CROP_CURVE_FIXED,
    KC_CROP_FOR_PLANT,
    KC_CROP_FOR_PLANT_CLIMATE,
    PLANT_PRESETS,
    SUN_EXPOSURE_FACTORS,
)

from .test_et0_days import _zone


def _entity(hass, domain, fragment):
    return next(s.entity_id for s in hass.states.async_all(domain) if fragment in s.entity_id)


def _plant(c, days_ago: float) -> None:
    c.store.state.planting_date_ts = dt_util.utcnow().timestamp() - days_ago * 86400


def _climate_history(c, u2: float, rh_min: float, days: int = 7) -> None:
    today = dt_util.now().date()
    c.store.state.et0_day_history = [
        {"date": (today - timedelta(days=i + 1)).isoformat(), "et0": 4.0, "u2": u2, "rh_min": rh_min, "sources": {"wind": "measured"}}
        for i in range(days)
    ]


# --- the crop table -------------------------------------------------------------------------


def test_every_crop_of_the_table_is_usable():
    crops = crop_season.read()
    assert len(crops) >= 50
    for crop in crops.values():
        assert crop.kc_flat > 0
        if crop.season != fao56.SEASON_FLAT:
            assert crop.stages is not None and fao56.season_length(crop.stages) > 0
        assert crop.height_m is None or crop.height_m > 0


def test_a_broken_row_is_skipped_not_fatal(tmp_path):
    path = tmp_path / "kc.json"
    path.write_text('{"crops": [{"id": "x", "kc_mid": 1.0, "season": "annual"}, {"id": "ok", "kc_mid": 0.9, "season": "flat"}]}')
    assert list(crop_season.read(path)) == ["ok"]
    assert crop_season.read(tmp_path / "missing.json") == {}


def test_the_plant_types_start_on_crops_that_exist():
    crops = crop_season.read()
    for crop in [*KC_CROP_FOR_PLANT.values(), *KC_CROP_FOR_PLANT_CLIMATE.values()]:
        assert crop in crops
    for plant in [*KC_CROP_FOR_PLANT, *(p for p, _c in KC_CROP_FOR_PLANT_CLIMATE)]:
        assert plant in PLANT_PRESETS


# --- the curve ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_zone_with_no_curve_waters_by_the_slider(hass):
    c = await _zone(hass)
    c.numbers["crop_coefficient"]  # the slider exists
    info = c.kc_info(dt_util.now().date())
    assert info["source"] == "fixed" and info["crop"] is None
    assert info["kc"] == c.number("crop_coefficient")
    assert info["exposure_factor"] == 1.0


@pytest.mark.asyncio
async def test_an_annual_crop_follows_its_season_from_the_planting_date(hass):
    c = await _zone(hass)
    c.store.state.kc_crop = "tomato"
    today = dt_util.now().date()
    assert c.kc_info(today)["source"] == "fixed"  # no planting date yet: the slider decides
    stages = c.crop_seasons["tomato"].stages
    _plant(c, 5)
    young = c.kc_info(today, None)
    assert young["source"] == "curve" and young["stage"] == fao56.STAGE_INITIAL
    assert young["kc"] == pytest.approx(stages.kc_ini * c.number("kc_curve_pct") / 100.0)
    _plant(c, stages.l_ini + stages.l_dev + 5)
    mid = c.kc_info(today, None)
    assert mid["stage"] == fao56.STAGE_MID and mid["kc"] == pytest.approx(stages.kc_mid)
    _plant(c, fao56.season_length(stages) + 30)
    assert c.kc_info(today, None)["stage"] == fao56.STAGE_AFTER
    # Planted in the future: not started, the slider decides.
    c.store.state.planting_date_ts = dt_util.utcnow().timestamp() + 10 * 86400
    assert c.kc_info(today, None)["source"] == "fixed"


@pytest.mark.asyncio
async def test_each_day_of_a_week_gets_its_own_crop_factor(hass):
    c = await _zone(hass)
    c.store.state.kc_crop = "tomato"
    _plant(c, 10)
    today = dt_util.now().date()
    values = [c.kc_for(today + timedelta(days=i), None) for i in range(40)]
    assert values == sorted(values) and values[-1] > values[0]  # a young crop only rises


@pytest.mark.asyncio
async def test_a_perennial_has_a_dormant_season_and_a_flat_crop_has_one_value(hass):
    c = await _zone(hass)
    c.store.state.kc_crop = "apple"
    apple = c.crop_seasons["apple"]
    assert apple.season == fao56.SEASON_PERENNIAL
    kcs = {c.kc_info(dt_util.now().date() + timedelta(days=i), None)["stage"] for i in range(0, 365, 15)}
    assert fao56.STAGE_DORMANT in kcs and fao56.STAGE_MID in kcs
    c.store.state.kc_crop = "turf_cool"
    flat = {round(c.kc_for(dt_util.now().date() + timedelta(days=i), None), 3) for i in range(0, 365, 30)}
    assert len(flat) == 1


@pytest.mark.asyncio
async def test_an_unknown_crop_falls_back_to_the_slider(hass):
    c = await _zone(hass)
    c.store.state.kc_crop = "no_such_crop"
    assert c.kc_info(dt_util.now().date())["source"] == "fixed"
    assert not c.kc_curve_covers_growth()


@pytest.mark.asyncio
async def test_the_strength_scales_the_curve_and_the_exposure_scales_it_again(hass):
    c = await _zone(hass)
    c.store.state.kc_crop = "turf_cool"
    day = dt_util.now().date()
    base = c.kc_for(day, None)
    await c.numbers["kc_curve_pct"].async_set_metric_value(150.0)
    assert c.kc_for(day, None) == pytest.approx(base * 1.5)
    await c.numbers["kc_curve_pct"].async_set_metric_value(100.0)
    c.store.state.sun_exposure = "deep_shade"
    info = c.kc_info(day, None)
    assert info["kc"] == pytest.approx(base * SUN_EXPOSURE_FACTORS["deep_shade"])
    assert info["kc_before_exposure"] == pytest.approx(base)


@pytest.mark.asyncio
async def test_a_curve_that_counts_from_planting_covers_the_growth_ramp(hass):
    c = await _zone(hass)
    c.store.state.kc_crop = "tomato"
    assert not c.kc_curve_covers_growth()  # no planting date
    _plant(c, 20)
    assert c.kc_curve_covers_growth()
    c.store.state.kc_crop = "turf_cool"
    assert not c.kc_curve_covers_growth()  # a flat crop is not a young plant


# --- entities and visibility ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_crop_curve_select_picks_and_clears_a_curve(hass):
    c = await _zone(hass)
    entity = _entity(hass, "select", "crop_curve")
    state = hass.states.get(entity)
    assert state.state == CROP_CURVE_FIXED
    assert CROP_CURVE_FIXED in state.attributes["options"] and "tomato" in state.attributes["options"]
    await hass.services.async_call("select", "select_option", {"entity_id": entity, "option": "tomato"}, blocking=True)
    assert c.store.state.kc_crop == "tomato" and hass.states.get(entity).state == "tomato"
    await hass.services.async_call("select", "select_option", {"entity_id": entity, "option": CROP_CURVE_FIXED}, blocking=True)
    assert c.store.state.kc_crop == "" and hass.states.get(entity).state == CROP_CURVE_FIXED


@pytest.mark.asyncio
async def test_the_sun_exposure_select_and_the_climate_switch(hass):
    c = await _zone(hass)
    entity = _entity(hass, "select", "sun_exposure")
    assert hass.states.get(entity).state == "full_sun"
    await hass.services.async_call("select", "select_option", {"entity_id": entity, "option": "afternoon_sun"}, blocking=True)
    assert c.store.state.sun_exposure == "afternoon_sun"
    switch = _entity(hass, "switch", "climate")
    assert hass.states.get(switch).state == "on"
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch}, blocking=True)
    assert c.store.state.kc_climate_adjust is False


@pytest.mark.asyncio
async def test_the_slider_and_the_strength_swap_places_with_the_curve(hass):
    c = await _zone(hass)
    assert ("number", "crop_coefficient") not in visibility.hidden_for(c)
    assert ("number", "kc_curve_pct") in visibility.hidden_for(c)
    assert ("switch", "kc_climate_adjust") in visibility.hidden_for(c)
    c.store.state.kc_crop = "tomato"
    hidden = visibility.hidden_for(c)
    assert ("number", "crop_coefficient") in hidden
    assert ("number", "kc_curve_pct") not in hidden and ("switch", "kc_climate_adjust") not in hidden
    _plant(c, 10)
    assert ("select", "growth_stage_mode") in visibility.hidden_for(c)  # the curve covers the growth


@pytest.mark.asyncio
async def test_the_crop_factor_sensor_says_where_the_number_comes_from(hass):
    c = await _zone(hass)
    entity = _entity(hass, "sensor", "crop_factor")
    c.store.state.kc_crop = "tomato"
    _plant(c, 60)
    c._notify_status()
    await hass.async_block_till_done()
    from homeassistant.helpers.entity_component import async_update_entity

    await async_update_entity(hass, entity)
    state = hass.states.get(entity)
    attrs = state.attributes
    assert attrs["source"] == "curve" and attrs["crop"] == "tomato" and attrs["stage"] in {"development", "mid"}
    assert len(attrs["next_7_days"]) == 7
    assert float(state.state) == pytest.approx(c.kc_for(dt_util.now().date()), abs=0.001)


# --- climate adjustment (FAO-56 eq. 62) ---------------------------------------------------------


def test_the_climate_adjustment_matches_the_worked_example():
    # Tomato (0.6 m) in a week with 3 m/s wind and 25 % minimum humidity: +0.074
    assert fao56.kc_climate_adjustment(3.0, 25.0, 0.6) == pytest.approx(0.074, abs=0.002)
    assert fao56.kc_climate_adjustment(2.0, 45.0, 0.6) == pytest.approx(0.0)  # the reference climate
    assert fao56.kc_climate_adjustment(1.0, 70.0, 0.6) < 0  # calm and humid lowers it
    # Out-of-range inputs are held to the fitted range.
    assert fao56.kc_climate_adjustment(50.0, 0.0, 0.6) == fao56.kc_climate_adjustment(6.0, 20.0, 0.6)


def test_a_low_kc_end_is_not_adjusted():
    stages = fao56.KcStages(0.3, 1.0, 0.25, 10, 10, 10, 10)
    adjusted = fao56.adjusted_stages(stages, 0.1)
    assert adjusted.kc_mid == pytest.approx(1.1) and adjusted.kc_end == 0.25 and adjusted.kc_ini == 0.3


@pytest.mark.asyncio
async def test_a_dry_windy_week_raises_the_crop_factor_and_the_switch_turns_it_off(hass):
    c = await _zone(hass)
    c.store.state.kc_crop = "turf_cool"
    day = dt_util.now().date()
    plain = c.kc_for(day, None)
    _climate_history(c, u2=3.0, rh_min=25.0)
    adjusted = c.kc_info(day)
    assert adjusted["climate_adjustment"] > 0.03 and adjusted["kc"] > plain
    assert adjusted["climate"]["days"] == 7
    c.store.state.kc_climate_adjust = False
    assert c.kc_for(day) == pytest.approx(plain)


@pytest.mark.asyncio
async def test_with_no_climate_record_the_curve_is_unadjusted(hass):
    c = await _zone(hass)
    c.store.state.kc_crop = "turf_cool"
    c.store.state.et0_day_history = []
    assert c.kc_climate() is None
    assert c.kc_info(dt_util.now().date())["climate_adjustment"] == 0.0


# --- words ----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_why_names_the_crop_factor_and_says_when_a_planting_date_is_missing(hass):
    c = await _zone(hass)
    await zf_messages.async_setup(hass)
    c.store.state.kc_crop = "tomato"
    texts = {i["id"]: i["text"] for i in why.explain(c)}
    assert "planting date" in texts["kc_planting"] and "Tomato" in texts["kc_planting"]
    assert "Crop Factor setting" in texts["crop_factor"]
    _plant(c, 60)
    c.store.state.sun_exposure = "morning_sun"
    texts = {i["id"]: i["text"] for i in why.explain(c)}
    assert "kc_planting" not in texts
    assert "Tomato" in texts["crop_factor"] and "75 %" in texts["crop_factor"]


@pytest.mark.asyncio
async def test_check_my_setup_mentions_a_missing_planting_date(hass):
    c = await _zone(hass)
    await zf_messages.async_setup(hass)
    c.store.state.kc_crop = "tomato"
    assert "kc_planting" in {i["id"] for i in setup_check.run_checks(c)}
    _plant(c, 3)
    assert "kc_planting" not in {i["id"] for i in setup_check.run_checks(c)}
    c.store.state.kc_crop = "turf_cool"
    assert "kc_planting" not in {i["id"] for i in setup_check.run_checks(c)}


# --- setup ----------------------------------------------------------------------------------


async def _create(hass, search=None, pick=None, plant="tomatoes", climate=None):
    from homeassistant import config_entries

    from custom_components.zoneflow.const import (
        CONF_IRRIGATION_METHOD, CONF_QUICK_SETUP, CONF_START_STATE, CONF_VALVE_ENTITY, CONF_ZONE_NAME, CONF_ZONE_TYPE, DOMAIN,
    )

    from .test_suggest import _house

    _house(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ZONE_NAME: "Bed", "plant": plant, CONF_ZONE_TYPE: "outdoor", CONF_QUICK_SETUP: True,
         **({"plant_search": search} if search else {})},
    )
    if search:
        schema = next(v for k, v in result["data_schema"].schema.items() if getattr(k, "schema", k) == "pick")
        options = {o["label"]: o["value"] for o in schema.config["options"]}
        value = next((v for label, v in options.items() if pick and pick in label), "")
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"pick": value})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_VALVE_ENTITY: "switch.sprinkler_valve", CONF_IRRIGATION_METHOD: "drip", "emitters": 10, "emitter_flow": 2.0, "area": 2.0},
    )
    return result["result"].data.get(CONF_START_STATE, {})


@pytest.mark.asyncio
async def test_a_new_zone_starts_on_the_curve_of_its_plant_type(hass, fake_valve_services):
    assert (await _create(hass)).get("kc_crop") == "tomato"


@pytest.mark.asyncio
async def test_a_plant_picked_in_the_lookup_brings_its_own_curve(hass, fake_valve_services):
    assert (await _create(hass, "hass avocado", "Hass Avocado")).get("kc_crop") == "avocado"


@pytest.mark.asyncio
async def test_keeping_the_starting_values_keeps_the_plant_types_curve(hass, fake_valve_services):
    assert (await _create(hass, "cucumber", None)).get("kc_crop") == "tomato"


@pytest.mark.asyncio
async def test_a_kind_of_plant_with_no_crop_of_its_own_does_not_borrow_the_plant_types_curve(hass, fake_valve_services):
    assert "kc_crop" not in await _create(hass, "cucumber", "varieties")


@pytest.mark.asyncio
async def test_a_plant_type_with_no_curve_starts_on_the_slider(hass, fake_valve_services):
    assert "kc_crop" not in await _create(hass, plant="flowers")
