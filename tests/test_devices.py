"""The device lookup works on old and new Home Assistant (the plain lookup is going away)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from homeassistant.helpers import device_registry as dr

from custom_components.zoneflow.const import DOMAIN
from custom_components.zoneflow.devices import zone_device


def test_new_home_assistant_is_asked_with_the_entry_that_made_the_device():
    asked = []
    registry = SimpleNamespace(
        async_get_device_by_identifier=lambda identifier, entry_id: asked.append((identifier, entry_id)) or "device",
        async_get_device=lambda **_: (_ for _ in ()).throw(AssertionError("the deprecated lookup was used")),
    )
    assert zone_device(registry, "abc") == "device"
    assert asked == [((DOMAIN, "abc"), "abc")]


def test_old_home_assistant_gets_the_plain_lookup():
    registry = SimpleNamespace(async_get_device=lambda identifiers: ("plain", identifiers))
    assert zone_device(registry, "abc") == ("plain", {(DOMAIN, "abc")})


@pytest.mark.asyncio
async def test_a_real_registry_finds_the_zone_device_and_nothing_for_a_stranger(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, entry.entry_id)})
    assert zone_device(registry, entry.entry_id).id == device.id
    assert zone_device(registry, "someone-else") is None
