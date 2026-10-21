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
    assert all(r["kind"] == "plant" for r in results[1:])


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


def test_a_plant_with_only_words_is_found_but_has_nothing_to_apply(data):
    avocado = plant_water.search(data, "hass avocado")[0]
    assert avocado["name"] == "Hass Avocado" and avocado["low_mm"] is None and avocado["note"]


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


def test_a_query_that_is_too_long_is_refused_by_the_schema():
    import voluptuous as vol

    from custom_components.zoneflow import plant_api

    with pytest.raises(vol.Invalid):
        plant_api.ws_plant_water._ws_schema({"id": 1, "type": "zoneflow/plant_water", "query": "x" * 200})
