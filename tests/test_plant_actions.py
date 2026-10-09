"""What a person can do with plants (1.7.0): add, move (asking what becomes of
the old main plant), make main, remove, note -- and read the history."""
from __future__ import annotations

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr

from custom_components.zoneflow import plant_actions, plant_api
from custom_components.zoneflow.const import CONF_PLANT, DOMAIN

from .test_greenhouse_crops import VALVE_B
from .test_plants import _book, _boot, _ctl, _zone


async def _call(hass, service, **data):
    await hass.services.async_call(DOMAIN, service, data, blocking=True)
    await hass.async_block_till_done()


def _device(hass, entry):
    return dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)}).id


@pytest.mark.asyncio
async def test_a_new_plant_in_a_zone_with_a_plant_is_a_record_only(hass, fake_valve_services):
    zone = _zone(hass)
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    before = c.number("target_weekly_mm")
    await _call(hass, "add_plant", name="  Basil ", plant_type="herbs", device_id=_device(hass, zone))
    plants = _book(hass).in_zone(zone.entry_id)
    assert [(p["name"], p["main"]) for p in plants] == [("Tomatoes", True), ("Basil", False)]
    assert c.number("target_weekly_mm") == before  # nothing about the watering changed
    assert plants[1]["snapshot"]["crop_coefficient"] == 0.7  # the herb starting settings, kept for later


@pytest.mark.asyncio
async def test_a_new_plant_can_take_over_the_zone(hass, fake_valve_services):
    zone = _zone(hass)
    await _boot(hass, zone)
    old = _book(hass).main(zone.entry_id)
    await _call(hass, "add_plant", name="Chilis", plant_type="chilis", old_main="extra", device_id=_device(hass, zone))
    main = _book(hass).main(zone.entry_id)
    c = _ctl(hass, zone)
    assert main["name"] == "Chilis" and old["id"] != main["id"] and not old["main"] and old["zone_id"] == zone.entry_id
    assert c.number("target_weekly_mm") == 25.0 and c.number("crop_coefficient") == 0.95  # the chili settings are on the zone
    await _call(hass, "add_plant", name="Lettuce", plant_type="leafy_vegetables", old_main="archive", device_id=_device(hass, zone))
    assert main["zone_id"] is None and "archived_ts" in main
    assert [p["name"] for p in _book(hass).in_zone(zone.entry_id)] == ["Lettuce", "Tomatoes"]


@pytest.mark.asyncio
async def test_moving_a_plant_needs_a_choice_when_the_zone_has_a_main_plant(hass, fake_valve_services):
    a, b = _zone(hass), _zone(hass, "Chilis", VALVE_B)
    await _boot(hass, a, b)
    tomato = _book(hass).main(a.entry_id)
    with pytest.raises(ServiceValidationError):
        await _call(hass, "move_plant", plant_id=tomato["id"], device_id=_device(hass, b))
    with pytest.raises(ServiceValidationError):
        await _call(hass, "move_plant", plant_id=tomato["id"], device_id=_device(hass, a), old_main="extra")  # same zone
    assert tomato["zone_id"] == a.entry_id  # nothing moved


@pytest.mark.asyncio
async def test_move_swap_exchanges_the_two_main_plants_and_their_settings(hass, fake_valve_services):
    a, b = _zone(hass, **{CONF_PLANT: "tomatoes"}), _zone(hass, "Chilis", VALVE_B, **{CONF_PLANT: "chilis"})
    await _boot(hass, a, b)
    await _ctl(hass, a).numbers["target_weekly_mm"].async_set_metric_value(33.0)  # tuned by hand
    tomato, chili = _book(hass).main(a.entry_id), _book(hass).main(b.entry_id)
    # The chili zone's own settings differ from the tomato zone's.
    await _ctl(hass, b).numbers["target_weekly_mm"].async_set_metric_value(22.0)
    await _ctl(hass, b).numbers["crop_coefficient"].async_set_metric_value(0.95)

    await _call(hass, "move_plant", plant_id=tomato["id"], device_id=_device(hass, b), old_main="swap")
    assert _book(hass).main(b.entry_id)["id"] == tomato["id"] and _book(hass).main(a.entry_id)["id"] == chili["id"]
    ca, cb = _ctl(hass, a), _ctl(hass, b)  # a zone may restart for its deep soak switch
    assert cb.number("target_weekly_mm") == 33.0  # the tuned tomato settings followed the plant
    assert ca.number("target_weekly_mm") == 22.0 and ca.number("crop_coefficient") == 0.95  # the chili settings went back
    moved = [h for h in tomato["history"] if h["kind"] == "moved"]
    assert moved[0]["data"] == {"from": "Tomatoes", "to": "Chilis"}


@pytest.mark.asyncio
async def test_move_with_the_old_plant_kept_as_a_record_or_archived(hass, fake_valve_services):
    a, b, c3 = _zone(hass), _zone(hass, "Chilis", VALVE_B), _zone(hass, "Beans", "switch.valve_beans")
    hass.states.async_set("switch.valve_beans", "off")
    await _boot(hass, a, b, c3)
    t, ch, bn = (_book(hass).main(x.entry_id) for x in (a, b, c3))
    await _call(hass, "move_plant", plant_id=t["id"], device_id=_device(hass, b), old_main="extra")
    assert _book(hass).main(b.entry_id)["id"] == t["id"] and ch["zone_id"] == b.entry_id and not ch["main"]
    assert _book(hass).main(a.entry_id) is None  # Tomatoes' old zone is empty now
    await _call(hass, "move_plant", plant_id=bn["id"], device_id=_device(hass, b), old_main="archive")
    assert _book(hass).main(b.entry_id)["id"] == bn["id"] and t["zone_id"] is None and "archived_ts" in t
    assert ch["zone_id"] == b.entry_id and not ch["main"]  # the first one stays on record
    # An empty zone just takes the plant, no choice needed.
    await _call(hass, "move_plant", plant_id=ch["id"], device_id=_device(hass, a))
    assert _book(hass).main(a.entry_id)["id"] == ch["id"]


@pytest.mark.asyncio
async def test_move_keep_joins_as_a_record_and_changes_nothing_on_the_zone(hass, fake_valve_services):
    a, b = _zone(hass), _zone(hass, "Chilis", VALVE_B)
    await _boot(hass, a, b)
    tomato, chili = _book(hass).main(a.entry_id), _book(hass).main(b.entry_id)
    before = _ctl(hass, b).number("target_weekly_mm")
    await _call(hass, "move_plant", plant_id=tomato["id"], device_id=_device(hass, b), old_main="keep")
    assert tomato["zone_id"] == b.entry_id and not tomato["main"]
    assert _book(hass).main(b.entry_id)["id"] == chili["id"] and _ctl(hass, b).number("target_weekly_mm") == before
    assert _book(hass).main(a.entry_id) is None


@pytest.mark.asyncio
async def test_set_main_remove_and_note(hass, fake_valve_services):
    zone = _zone(hass)
    await _boot(hass, zone)
    book = _book(hass)
    tomato = book.main(zone.entry_id)
    await _call(hass, "add_plant", name="Chilis", plant_type="chilis", device_id=_device(hass, zone))
    chili = next(p for p in book.in_zone(zone.entry_id) if p["name"] == "Chilis")
    await _call(hass, "set_main_plant", plant_id=chili["id"])
    assert book.main(zone.entry_id)["id"] == chili["id"] and not tomato["main"]
    assert _ctl(hass, zone).number("crop_coefficient") == 0.95

    await _call(hass, "add_plant_note", plant_id=chili["id"], text="  first flowers ")
    assert chili["history"][-1]["kind"] == "note" and chili["history"][-1]["data"] == {"text": "first flowers"}
    with pytest.raises(ServiceValidationError):
        await _call(hass, "add_plant_note", plant_id=chili["id"], text="   ")

    await _call(hass, "remove_plant", plant_id=chili["id"])
    assert chili["zone_id"] is None and "archived_ts" in chili and book.main(zone.entry_id)["id"] == tomato["id"]
    await _call(hass, "remove_plant", plant_id=tomato["id"])
    assert book.main(zone.entry_id) is None and book.in_zone(zone.entry_id) == []
    # A plant added to the empty zone becomes its main plant.
    await _call(hass, "add_plant", name="Basil", plant_type="herbs", device_id=_device(hass, zone))
    assert book.main(zone.entry_id)["name"] == "Basil"
    with pytest.raises(ServiceValidationError):
        await _call(hass, "remove_plant", plant_id="nope")


@pytest.mark.asyncio
async def test_the_history_reads_in_words(hass, fake_valve_services):
    zone = _zone(hass)
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    plant = _book(hass).main(zone.entry_id)
    start = c.number("target_weekly_mm")
    await c.numbers["target_weekly_mm"].async_set_metric_value(40.0)
    c.store.state.planting_date_ts = 1_790_000_000.0
    c.plants.check()
    await _call(hass, "add_plant_note", plant_id=plant["id"], text="Looks healthy")
    texts = [e["text"] for e in plant_actions.history(hass, plant)]
    assert texts[0] == "Looks healthy"
    assert any(t.startswith("Planting date: - -> 20") for t in texts), texts
    assert any(t.endswith(f"{start:g} -> 40") for t in texts), texts
    assert texts[-1] == "Added to ZoneFlow"


@pytest.mark.asyncio
async def test_the_card_can_ask_for_a_zones_plants(hass, fake_valve_services):
    zone = _zone(hass)
    await _boot(hass, zone)

    class Connection:
        def __init__(self):
            self.result = self.error = None

        def send_result(self, msg_id, result):
            self.result = result

        def send_error(self, msg_id, code, message):
            self.error = code

    connection = Connection()
    plant_api.ws_plants(hass, connection, {"id": 1, "type": "zoneflow/plants", "device_id": _device(hass, zone)})
    await hass.async_block_till_done()
    assert connection.result["zone"] == "Tomatoes"
    assert [(p["name"], p["main"]) for p in connection.result["plants"]] == [("Tomatoes", True)]
    assert connection.result["plants"][0]["history"][0]["text"] == "Added to ZoneFlow"
    missing = Connection()
    plant_api.ws_plants(hass, missing, {"id": 2, "type": "zoneflow/plants", "device_id": "nope"})
    await hass.async_block_till_done()
    assert missing.error == "not_found"
