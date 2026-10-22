"""Watering suggestions from the Plant Variety Database (CC BY 4.0): the numbers read
from its text, the search, and the websocket command the card asks."""
import importlib.util
import json
from pathlib import Path

import pytest

from custom_components.zoneflow import plant_water

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("build_plant_water_data", ROOT / "scripts" / "build_plant_water_data.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


# --- reading a weekly amount out of the dataset's own words ----------------------
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1 inch per week, deep watering", (25.4, 25.4)),
        ("1-1.5 inches per week, consistent moisture", (25.4, 38.1)),
        ("0.5-1 inch per week, drought tolerant", (12.7, 25.4)),
        ("3/4 inch per week", (19.05, 19.05)),
        ("1/2 to 3/4 inch per week", (12.7, 19.05)),
        ("½-1 inch per week", (12.7, 25.4)),
        ("Moderate — about 1 inch per week", (25.4, 25.4)),
        ("regular; consistent moisture of 1-1.5 inches weekly", (25.4, 38.1)),
        ("2-1 inches per week", (25.4, 50.8)),  # a reversed range is read the right way round
    ],
)
def test_a_weekly_amount_is_read_in_millimetres(text, expected):
    assert builder.weekly_range_mm(text) == pytest.approx(expected, abs=0.06)


@pytest.mark.parametrize(
    "text",
    [
        "Moderate — regular watering",
        "High — consistent moisture needed",
        "Water when top 1-2 inches of soil dry out",  # how dry the soil is, not a weekly amount
        "Deep watering 1-2 times per week",
        "20 inches per week",  # a typo, not a weekly depth
        "",
    ],
)
def test_text_without_a_weekly_amount_gives_none(text):
    assert builder.weekly_range_mm(text) is None


# --- the shipped data -------------------------------------------------------------
@pytest.fixture(scope="module")
def data():
    return plant_water._load()


def test_the_data_carries_its_license_and_source(data):
    assert data["source"]["license"] == "CC BY 4.0"
    assert data["source"]["url"].startswith("https://github.com/bripatch/plant-variety-database")
    assert len(data["plants"]) > 1500


def test_every_amount_is_a_sensible_weekly_depth(data):
    amounts = [p for p in data["plants"] if p["low_mm"] is not None]
    assert len(amounts) > 500
    for plant in amounts:
        assert 5 <= plant["low_mm"] <= plant["high_mm"] <= 200, plant["name"]


# --- the search -------------------------------------------------------------------
def test_a_kind_of_plant_starts_with_the_middle_of_all_of_it(data):
    results = plant_water.search(data, "cucumber")
    assert results[0]["kind"] == "category" and results[0]["count"] >= 3
    assert results[0]["low_mm"] is not None and len(results) <= plant_water.MAX_RESULTS
    assert results[0]["kc"] == 1.0  # the FAO crop factor of cucumbers
    assert results[1]["kind"] == "crop" and results[1]["kc"] == 1.0  # then the FAO crop itself
    assert all(r["kind"] == "plant" for r in results[2:])


def test_a_whole_word_comes_before_a_word_that_only_starts_like_it(data):
    plants = [r for r in plant_water.search(data, "pepper") if r["kind"] == "plant"]
    names = [r["name"] for r in plants]
    # "Pepper" the vegetable is the kind; "Peppermint" is a herb that only starts with it
    assert "pepper" in plants[0]["name"].lower().split()
    if "Peppermint" in names:
        assert names.index("Peppermint") > 0
        assert all("pepper" in n.lower().split() for n in names[: names.index("Peppermint")])


def test_accents_quotes_and_capitals_do_not_matter(data):
    names = [r["name"] for r in plant_water.search(data, "JALAPENO")]
    assert any("Jalape" in name for name in names)


def test_several_words_all_have_to_match(data):
    results = plant_water.search(data, "genovese basil")
    assert results and all("basil" in r["name"].lower() for r in results)
    assert plant_water.search(data, "genovese zzzz") == []


def test_a_plant_with_only_words_is_found_and_still_gets_its_crop_factor(data):
    avocado = next(r for r in plant_water.search(data, "hass avocado") if r["kind"] == "plant")
    assert avocado["name"] == "Hass Avocado" and avocado["note"]
    assert avocado["kc"] == 0.85  # no weekly amount in the database, but the FAO crop factor
    assert avocado["low_mm"] == 21.6 and avocado["mm_estimate"] is True  # so its weekly amount is worked out from it
    assert plant_water.usable(avocado)


def test_a_plant_with_neither_is_not_usable(data):
    nothing = next(p for p in data["plants"] if p["low_mm"] is None and p["kc"] is None)
    assert not plant_water.usable(plant_water._public(nothing))


def test_empty_and_odd_queries_are_safe(data):
    assert plant_water.search(data, "") == []
    assert plant_water.search(data, "   ") == []
    assert plant_water.search(data, "%%%") == []
    assert isinstance(plant_water.search(data, "x" * 500), list)


def test_the_shipped_file_matches_what_the_builder_makes_from_it(data):
    """The file is plain JSON a person can read; nothing in it needs the code."""
    raw = json.loads(plant_water.DATA_FILE.read_text(encoding="utf-8"))
    assert set(raw) == {"source", "plants"}
    assert {"name", "category", "latin", "low_mm", "high_mm", "note"} <= set(raw["plants"][0])


# --- the websocket command --------------------------------------------------------
class _Connection:
    def __init__(self):
        self.sent = []

    def send_result(self, msg_id, result):
        self.sent.append((msg_id, result))

    def send_error(self, msg_id, code, message):
        self.sent.append((msg_id, code))


@pytest.mark.asyncio
async def test_the_websocket_command_answers_with_results_and_the_source(hass):
    from custom_components.zoneflow import plant_api

    connection = _Connection()
    # Through the command's real schema, as Home Assistant checks it.
    message = plant_api.ws_plant_water._ws_schema({"id": 3, "type": "zoneflow/plant_water", "query": "cucumber"})
    plant_api.ws_plant_water(hass, connection, message)
    await hass.async_block_till_done()
    msg_id, result = connection.sent[0]
    assert msg_id == 3 and result["results"][0]["kind"] == "category"
    assert result["source"]["license"] == "CC BY 4.0"
    assert "Allen" in result["kc_sources"]["fao56"]["author"]  # the crop factors' source is named too
    assert set(result["kc_sources"]) == {"fao56", "derived"}  # only the sources behind these results


def test_a_query_that_is_too_long_is_refused_by_the_schema():
    import voluptuous as vol

    from custom_components.zoneflow import plant_api

    with pytest.raises(vol.Invalid):
        plant_api.ws_plant_water._ws_schema({"id": 1, "type": "zoneflow/plant_water", "query": "x" * 200})


# --- crop factors (FAO-56) ---------------------------------------------------------
def _kc(data, name):
    plant = next(p for p in data["plants"] if p["name"] == name)
    return plant["kc"], plant["crop"]


@pytest.mark.parametrize(
    ("name", "kc"),
    [
        ("Hass Avocado", 0.85),
        ("Banana Pepper 'Sweet Banana'", 1.05),  # a pepper, not a banana
        ("Common Mint", 1.15),  # mint
        ("Apple Mint", 1.15),  # a mint, not an apple tree
        ("Genovese Basil", 0.86),  # not FAO-56: a greenhouse study of basil
    ],
)
def test_plants_map_to_the_right_fao_crop(data, name, kc):
    found = [p for p in data["plants"] if p["name"] == name]
    assert found, name
    assert found[0]["kc"] == kc


def test_look_alikes_do_not_get_the_wrong_crop(data):
    by_name = {p["name"]: p for p in data["plants"]}
    for name, plant in by_name.items():
        lowered = name.lower()
        if plant["category"] == "herb" and "lemon" in lowered:
            assert plant["crop"] != "Citrus", name  # lemon balm is not a lemon tree
        if plant["category"] == "flower" and "grape" in lowered:
            assert plant["crop"] != "Grapes (table)", name  # grape hyacinth is not a grape
        if plant["category"] == "tomato" and "grape" in lowered:
            assert plant["crop"] == "Tomato", name  # grape tomato is a tomato


def test_the_crop_table_is_the_fao_one():
    kc = json.loads(plant_water.KC_FILE.read_text(encoding="utf-8"))
    assert "Allen" in kc["sources"]["fao56"]["author"] and "FAO" in kc["sources"]["fao56"]["name"]
    crops = {c["id"]: c for c in kc["crops"]}
    # a few values of Table 12 (initial, mid-season, end)
    assert (crops["tomato"]["kc_ini"], crops["tomato"]["kc_mid"], crops["tomato"]["kc_end"]) == (0.6, 1.15, 0.8)
    assert crops["avocado"]["kc_mid"] == 0.85 and crops["potato"]["kc_mid"] == 1.15 and crops["lettuce"]["kc_mid"] == 1.0
    assert all(0.1 <= c["kc_mid"] <= 1.5 for c in kc["crops"])  # inside the crop factor slider
    assert len({c["id"] for c in kc["crops"]}) == len(kc["crops"])


def test_a_crop_with_no_weekly_amount_gives_only_the_crop_factor():
    got = plant_water.suggested_numbers(None, None, None, 0.85)
    assert got == {"crop_coefficient": 0.85}


def test_amount_and_crop_factor_together():
    got = plant_water.suggested_numbers(25.4, 38.1, {"target_weekly_mm": 30, "target_weekly_hot_mm": 40, "target_weekly_cool_mm": 20}, 1.15)
    assert got["target_weekly_mm"] == 32.0 and got["crop_coefficient"] == 1.15


def test_a_crop_is_found_by_its_name_or_a_name_it_goes_by_but_not_by_a_lookalike(data):
    def crops(query):
        return [r["name"] for r in plant_water.search(data, query) if r["kind"] == "crop"]

    assert "Citrus" in crops("lemon")  # a name it goes by
    assert "Pepper (sweet and chili)" in crops("pepper") and "Mint" not in crops("pepper")  # not through "peppermint"
    assert "Mint" in crops("peppermint")
    assert crops("zzzz") == []


# --- gaps filled from other sources, and estimates ---------------------------------------
def test_every_crop_names_a_source_that_exists():
    kc = json.loads(plant_water.KC_FILE.read_text(encoding="utf-8"))
    assert {c["source"] for c in kc["crops"]} <= set(kc["sources"])
    assert kc["classes"]["source"] in kc["sources"]
    by_id = {c["id"]: c for c in kc["crops"]}
    assert (by_id["mango"]["kc_mid"], by_id["mango"]["source"]) == (0.8, "ifas")
    assert (by_id["guava"]["kc_mid"], by_id["guava"]["source"]) == (1.0, "ifas")
    assert (by_id["papaya"]["kc_mid"], by_id["papaya"]["source"]) == (1.05, "papaya")
    assert (by_id["basil"]["kc_mid"], by_id["basil"]["source"]) == (0.86, "basil")
    assert by_id["tomato"]["source"] == "fao56"
    for source in kc["sources"].values():  # every source can be credited and found
        assert source["name"] and source["author"] and source["url"].startswith("https://") and source["short"]


@pytest.mark.parametrize(
    ("category", "note", "expected"),
    [
        ("flower", "Low — drought tolerant once established", 0.2),
        ("shrub", "Drought tolerant", 0.2),
        ("shrub", "Moderate, regular watering", 0.5),
        ("flower", "Regular", 0.5),
        ("flower", "High — consistent moisture needed", 0.8),
        ("ground-cover", "Consistent moisture", 0.8),
        ("succulent", "Low", None),  # kept in pots: no estimate
        ("houseplant", "Water when the top inch is dry", None),
        ("microgreen", "High", None),
        ("flower", "Water when the top inch of soil is dry", None),  # starts with none of the class words
        ("flower", "", None),
    ],
)
def test_the_water_use_class_gives_an_estimate(data, category, note, expected):
    assert plant_water._estimate_kc(data["classes"], category, note) == expected


def test_estimates_are_marked_and_never_replace_a_value_of_the_plants_own(data):
    estimated = [p for p in data["plants"] if p["kc_estimate"]]
    assert len(estimated) > 500
    for plant in estimated:
        assert plant["kc"] in (0.2, 0.5, 0.8) and plant["kc_source"] == "landscape"
        assert plant["mm_estimate"] and plant["crop_id"] is None  # nothing else was known: its weekly amount follows the crop factor too
        assert plant["category"] not in ("succulent", "houseplant", "microgreen")
    for plant in data["plants"]:
        if plant["crop_id"] is not None or (plant["low_mm"] is not None and not plant["mm_estimate"]):
            assert not plant["kc_estimate"]


def test_the_onion_family_stands_for_an_allium_with_no_name_of_its_own(data):
    bandit = next(p for p in data["plants"] if p["name"] == "Bandit" and p["category"] == "allium")
    assert bandit["crop"] == "Onion family" and bandit["kc"] == 1.05 and not bandit["kc_estimate"]


def test_the_sources_behind_results_include_the_estimate_when_there_is_one(data):
    flower = next(p for p in data["plants"] if p["kc_estimate"] and p["category"] == "flower" and " " not in p["name"])
    results = [r for r in plant_water.search(data, flower["name"]) if r["name"] == flower["name"]]
    assert results and results[0]["kc_estimate"] and results[0]["kc_source"] == "landscape"
    sources = plant_water.sources_for(data, results)
    assert set(sources) == {"landscape", "derived"}  # the class estimate and the weekly amount worked out from it
    assert plant_water.sources_for(data, []) == {}


def test_a_result_names_its_source_and_whether_it_is_an_estimate(data):
    mango = next(r for r in plant_water.search(data, "mango") if r["kind"] == "crop")
    assert mango["kc"] == 0.8 and mango["kc_source"] == "ifas" and mango["kc_estimate"] is False
    assert mango["note"] == "Kc - / 0.8 / -"  # only the value the source gives


def test_every_plant_with_a_water_text_has_a_weekly_amount_except_those_kept_in_pots(data):
    without = [p for p in data["plants"] if p["low_mm"] is None]
    assert len(without) < 160
    assert all(p["category"] in ("microgreen", "succulent", "houseplant", "fruit-tree", "ground-cover", "rose") for p in without)
    assert sum(1 for p in without if p["category"] in ("microgreen", "succulent", "houseplant")) > 130
    for plant in data["plants"]:
        if plant["low_mm"] is not None:
            assert 4 <= plant["low_mm"] <= plant["high_mm"] <= 80, plant["name"]  # a worked-out amount stays sensible too


def test_a_worked_out_weekly_amount_follows_the_crop_factor_and_is_marked(data):
    per_kc = data["derived"]["mm_per_kc"]
    worked = [p for p in data["plants"] if p["mm_estimate"]]
    assert len(worked) > 1000
    for plant in worked:
        assert plant["low_mm"] == plant["high_mm"] == round(plant["kc"] * per_kc, 1), plant["name"]
    assert all(not p["mm_estimate"] for p in data["plants"] if p["kc"] is None)


def test_a_kind_is_the_middle_of_the_measured_amounts_only(data):
    kinds = {}
    for plant in data["plants"]:
        if plant["low_mm"] is not None and not plant["mm_estimate"]:
            kinds.setdefault(plant["category"], []).append(plant["low_mm"])
    summary = plant_water._category_summary(data, "pepper")
    assert summary["count"] == len(kinds["pepper"])  # the estimated ones are not in it
    assert summary["mm_estimate"] is False


def test_the_worked_out_amount_lines_up_with_the_setup_plant_types(data):
    from custom_components.zoneflow.const import PLANT_PRESETS

    per_kc = data["derived"]["mm_per_kc"]
    kc = {c["id"]: c["kc_mid"] for c in data["crops"]}
    # ZoneFlow's own plant types, which were set by hand, are within about 20 % of what the crop factor says
    for crop, preset in (("tomato", "tomatoes"), ("pepper", "chilis"), ("lettuce", "leafy_vegetables")):
        worked = kc[crop] * per_kc
        assert abs(worked - PLANT_PRESETS[preset]["numbers"]["target_weekly_mm"]) / worked < 0.2, crop


def test_the_derived_source_can_be_credited(data):
    source = data["kc_sources"][data["derived"]["source"]]
    assert source["short"] == "estimate" and source["url"].startswith("https://")

