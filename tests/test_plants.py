"""Plants (1.7.0): each zone with a valve has a main plant with a history of
its own; the zone's entities stay the live settings."""
from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta

import homeassistant.util.dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.zoneflow import plants as plants_module
from custom_components.zoneflow.const import (
    CONF_PLANT,
    CONF_VALVE_ENTITY,
    CONF_ZONE_NAME,
    DOMAIN,
    STORAGE_VERSION,
)
from custom_components.zoneflow.state_store import IrrigationState

from .test_greenhouse_crops import VALVE_A, VALVE_B, _seed_all
from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry
from .test_zone_types import _climate_only_entry


def _zone(hass, name="Tomatoes", valve=VALVE_A, **extra):
    return make_entry(hass, **{CONF_ZONE_NAME: name, CONF_VALVE_ENTITY: valve,
                               "csv_path": f"/tmp/test_zoneflow_{name}.csv", **extra})


async def _boot(hass, *first):
    await _seed_all(hass)
    assert await hass.config_entries.async_setup(first[0].entry_id)
    await hass.async_block_till_done()


def _book(hass):
    return hass.data[plants_module.BOOK_KEY]


def _ctl(hass, entry):
    return hass.data[DOMAIN][entry.entry_id]


@pytest.mark.asyncio
async def test_each_zone_with_a_valve_gets_one_main_plant(hass, fake_valve_services):
    custom = _zone(hass, "Back bed")
    typed = _zone(hass, "Row 1", VALVE_B, **{CONF_PLANT: "fruit_tree"})
    house = _climate_only_entry(hass)
    await _boot(hass, custom, typed, house)
    book = _book(hass)
    main = book.main(custom.entry_id)
    assert main["name"] == "Back bed" and main["type"] == "custom" and main["main"]
    assert book.main(typed.entry_id)["name"] == "Fruit tree"
    assert book.in_zone(house.entry_id) == []  # a climate-only zone has no plant
    assert [h["kind"] for h in main["history"]] == ["created"]
    assert main["history"][0]["data"] == {"source": "update"}


@pytest.mark.asyncio
async def test_a_reload_keeps_the_same_plant(hass, fake_valve_services):
    zone = _zone(hass)
    await _boot(hass, zone)
    first = _book(hass).main(zone.entry_id)["id"]
    assert await hass.config_entries.async_reload(zone.entry_id)
    await hass.async_block_till_done()
    assert [p["id"] for p in _book(hass).in_zone(zone.entry_id)] == [first]


@pytest.mark.asyncio
async def test_changed_settings_go_into_the_history_once_per_edit(hass, fake_valve_services):
    zone = _zone(hass)
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    plant = _book(hass).main(zone.entry_id)
    start = c.number("target_weekly_mm")

    # A slider dragged through several values is one edit.
    for value in (31.0, 33.0, 38.0):
        await c.numbers["target_weekly_mm"].async_set_metric_value(value)
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=3))
        await hass.async_block_till_done()
        c.plants.check()
    changes = [h for h in plant["history"] if h["kind"] == "setting"]
    assert len(changes) == 1
    assert changes[0]["data"] == {"key": "target_weekly_mm", "old": start, "new": 38.0}

    # Back to where it was: no edit at all.
    await c.numbers["target_weekly_mm"].async_set_metric_value(start)
    c.plants.check()
    assert not [h for h in plant["history"] if h["kind"] == "setting"]

    # A journal field and a date.
    c.store.state.health_status = "stressed"
    c.store.state.last_fertilizing_ts = 1_790_000_000.0
    c.plants.check()
    logged = {h["data"]["key"]: h["data"] for h in plant["history"] if h["kind"] == "setting"}
    assert logged["health_status"]["new"] == "stressed"
    assert logged["last_fertilizing_ts"]["old"] is None and logged["last_fertilizing_ts"]["new"] == 1_790_000_000.0
    # The record's snapshot follows the live settings.
    assert plant["snapshot"]["health_status"] == "stressed"
    assert plant["snapshot"]["target_weekly_mm"] == start


@pytest.mark.asyncio
async def test_the_deep_soak_switch_is_a_plant_setting(hass, fake_valve_services):
    zone = _zone(hass)
    await _boot(hass, zone)
    plant = _book(hass).main(zone.entry_id)
    on = _ctl(hass, zone).deep_soak_enabled
    hass.config_entries.async_update_entry(zone, options={**zone.options, "deep_soak_enabled": not on})
    await hass.async_block_till_done()
    changes = [h["data"] for h in plant["history"] if h["kind"] == "setting"]
    assert {"key": "deep_soak_enabled", "old": on, "new": not on} in changes


@pytest.mark.asyncio
async def test_the_status_lists_the_plants(hass, fake_valve_services):
    zone = _zone(hass, **{CONF_PLANT: "tomatoes"})
    await _boot(hass, zone)
    book = _book(hass)
    extra = book.create("Basil", "herbs", zone.entry_id, False, "user")
    await hass.async_block_till_done()
    plants = hass.states.get("sensor.tomatoes_status").attributes["plants"]
    assert [(p["name"], p["main"]) for p in plants] == [("Tomatoes", True)]  # listed as soon as the zone starts
    _ctl(hass, zone)._notify_status()
    await hass.async_block_till_done()
    plants = hass.states.get("sensor.tomatoes_status").attributes["plants"]
    assert [(p["name"], p["main"]) for p in plants] == [("Tomatoes", True), ("Basil", False)]
    assert extra["main"] is False


@pytest.mark.asyncio
async def test_deleting_a_zone_archives_its_plants(hass, fake_valve_services):
    zone = _zone(hass)
    other = _zone(hass, "Chilis", VALVE_B)
    await _boot(hass, zone, other)
    plant_id = _book(hass).main(zone.entry_id)["id"]
    assert await hass.config_entries.async_remove(zone.entry_id)
    await hass.async_block_till_done()
    record = _book(hass).plants[plant_id]
    assert record["zone_id"] is None and not record["main"] and "archived_ts" in record
    assert record["history"][-1]["kind"] == "removed"
    assert _book(hass).main(other.entry_id) is not None


@pytest.mark.asyncio
async def test_the_records_survive_a_restart(hass, fake_valve_services, hass_storage):
    zone = _zone(hass)
    await _boot(hass, zone)
    plant_id = _book(hass).main(zone.entry_id)["id"]
    await hass.config_entries.async_unload(zone.entry_id)
    await hass.async_block_till_done()
    assert plant_id in hass_storage[f"{DOMAIN}_plants"]["data"]["plants"]


# --- upgrading from 1.6.5 ----------------------------------------------------


@pytest.mark.asyncio
async def test_a_1_6_5_zone_upgrades_cleanly(hass, fake_valve_services, hass_storage, tmp_path):
    """A zone saved by 1.6.5 (with the garden-area label, no plant records)
    loads, keeps its settings and history, and gets its main plant."""
    entry = make_entry(hass, csv_path=str(tmp_path / "u.csv"), **{CONF_PLANT: "chilis"})
    old = asdict(IrrigationState())
    now = 1_790_000_000.0
    old.update(
        last_routine_ts=now - 86400,
        planting_date_ts=now - 40 * 86400,
        health_status="healthy",
        health_notes="aphids on the lower leaves",
        last_fertilizing_ts=now - 10 * 86400,
        rain_counter_total_tips=449.0,
        rain_counter_last_tips=449.0,
        garden_area="Backyard",  # the 1.6.5 free-text label: no longer a field
    )
    hass_storage[f"{DOMAIN}_{entry.entry_id}"] = {"version": STORAGE_VERSION, "key": f"{DOMAIN}_{entry.entry_id}", "data": old}
    for entity, value in ((VALVE, "off"), (PUMP, "999"), (RAIN_COUNTER, "449"), (OUTDOOR_TEMP, "25")):
        hass.states.async_set(entity, value)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = _ctl(hass, entry)
    state = c.store.state
    # Everything the zone had is still there.
    assert state.planting_date_ts == now - 40 * 86400 and state.health_notes == "aphids on the lower leaves"
    assert state.last_routine_ts == now - 86400 and not hasattr(state, "garden_area")
    assert c.area is None and c.garden_area is None  # the old label is gone, the zone is in no area
    # And the zone has its plant, started from its settings.
    plant = _book(hass).main(entry.entry_id)
    assert plant["name"] == "Chilis" and plant["snapshot"]["planting_date_ts"] == now - 40 * 86400
    assert plant["snapshot"]["health_notes"] == "aphids on the lower leaves"
    assert [h["kind"] for h in plant["history"]] == ["created"]
