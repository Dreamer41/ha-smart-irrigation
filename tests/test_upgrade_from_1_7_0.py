"""Upgrading from 1.7.0: a plant book saved before nursery plants (no
`ready_days`, `transplanted_ts` or `ready_notified`) loads as it was, plants
are not followed until asked, and nothing is messaged or reset."""
import pytest

from custom_components.zoneflow.const import DOMAIN
from custom_components.zoneflow.plants import BOOK_KEY, STORE_VERSION

from .test_plants import _boot, _book, _ctl, _zone


@pytest.mark.asyncio
async def test_a_1_7_0_plant_book_upgrades_cleanly(hass, fake_valve_services, hass_storage):
    zone = _zone(hass)
    old = {
        "p1": {
            "id": "p1", "name": "Tomatoes", "type": "tomatoes", "zone_id": zone.entry_id, "main": True,
            "created_ts": 1.0, "snapshot": {"planting_date_ts": 1_700_000_000.0},
            "history": [{"ts": 1.0, "kind": "created", "data": {"source": "update"}}],
        },
        "p2": {
            "id": "p2", "name": "Basil", "type": "herbs", "zone_id": zone.entry_id, "main": False,
            "created_ts": 2.0, "snapshot": {}, "history": [],
        },
    }
    hass_storage[f"{DOMAIN}_plants"] = {
        "version": STORE_VERSION, "key": f"{DOMAIN}_plants", "data": {"plants": old, "seeded": [zone.entry_id]},
    }
    await _boot(hass, zone)
    c = _ctl(hass, zone)
    assert [p["name"] for p in _book(hass).in_zone(zone.entry_id)] == ["Tomatoes", "Basil"]  # nothing lost
    assert all("stage" not in row for row in c.plants.summary())  # not followed until asked
    sent = []
    c.notify_plant_ready = lambda name: sent.append(name)
    await c.plants.async_check_ready()
    assert sent == []
    assert _book(hass).plants["p1"]["history"] == old["p1"]["history"]
