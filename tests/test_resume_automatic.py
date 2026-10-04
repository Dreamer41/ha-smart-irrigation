"""Resume Automatic (1.6.1): a button that ends every manual hold, the Auto
Resume switch and its 0.5-24 h slider (replacing Manual Hold Time), and the
heater safety: a heater switched on by hand is taken back once it gets too
hot, whatever the hold setting."""
from __future__ import annotations

import time

import pytest
from homeassistant.components.number import NumberExtraStoredData
from homeassistant.core import State
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import mock_restore_cache_with_extra_data

from custom_components.zoneflow import greenhouse
from custom_components.zoneflow.const import DOMAIN

from .test_greenhouse_zone import _entry, _go, _ready, devices  # noqa: F401 -- fixture
from .test_zone_types import FAN, HEATER, INSIDE_TEMP


def _reg(hass, entry, domain, key):
    registry = er.async_get(hass)
    return next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == domain and e.translation_key == key
    )


async def _press(hass, entry, key):
    await hass.services.async_call(
        "button", "press", {"entity_id": _reg(hass, entry, "button", key).entity_id}, blocking=True
    )


async def _switch(hass, entry, key, on):
    # The devices fixture replaces switch.turn_on/off with fakes: call the
    # ZoneFlow switch entity itself.
    entity_id = _reg(hass, entry, "switch", key).entity_id
    entity = next(
        p.entities[entity_id] for p in hass.data["entity_platform"][DOMAIN] if entity_id in p.entities
    )
    await (entity.async_turn_on() if on else entity.async_turn_off())
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_a_hold_lasts_auto_resume_after(hass, devices):
    entry = _entry(hass)
    c = await _ready(hass, entry)
    hass.states.async_set(INSIDE_TEMP, "20")
    await _go(c)
    hass.states.async_set(FAN, "on")  # switched by hand
    await hass.async_block_till_done()
    assert c.greenhouse._held("fans", time.time()) == pytest.approx(3600, abs=5)  # default 1 h
    assert c.greenhouse.status()["code"] == "held_until"
    assert "automatic again" in c.greenhouse.status()["text"]


@pytest.mark.asyncio
async def test_resume_automatic_takes_the_device_back_at_once(hass, devices):
    entry = _entry(hass)
    c = await _ready(hass, entry)
    hass.states.async_set(INSIDE_TEMP, "20")
    await _go(c)
    hass.states.async_set(FAN, "on")
    await hass.async_block_till_done()
    await c.greenhouse.async_evaluate("test")
    assert hass.states.get(FAN).state == "on"  # held

    await _press(hass, entry, "resume_automatic")
    await hass.async_block_till_done()
    assert c.greenhouse._held("fans", time.time()) == 0
    assert hass.states.get(FAN).state == "off"  # 20 degrees: no fan


@pytest.mark.asyncio
async def test_auto_resume_off_waits_for_the_button(hass, devices):
    entry = _entry(hass)
    c = await _ready(hass, entry)
    await _switch(hass, entry, "auto_resume", False)
    assert _reg(hass, entry, "number", "auto_resume_hours").hidden_by == er.RegistryEntryHider.INTEGRATION
    hass.states.async_set(INSIDE_TEMP, "20")
    await _go(c)
    hass.states.async_set(FAN, "on")
    await hass.async_block_till_done()
    assert c.greenhouse._held("fans", time.time()) > 365 * 86400
    assert c.greenhouse.status()["code"] == "held_until_resume"

    # Switched back on: the waiting hold now ends after Auto Resume After.
    await _switch(hass, entry, "auto_resume", True)
    assert _reg(hass, entry, "number", "auto_resume_hours").hidden_by is None
    assert c.greenhouse._held("fans", time.time()) == pytest.approx(3600, abs=5)


@pytest.mark.asyncio
async def test_a_heater_held_on_by_hand_is_taken_back_when_too_hot(hass, devices):
    entry = _entry(hass)
    c = await _ready(hass, entry)
    await _switch(hass, entry, "auto_resume", False)  # even when waiting for the button
    hass.states.async_set(INSIDE_TEMP, "20")
    await _go(c)
    hass.states.async_set(HEATER, "on")
    await hass.async_block_till_done()
    assert c.greenhouse._held("heater", time.time()) > 0

    hass.states.async_set(INSIDE_TEMP, str(c.number("vent_temp") - 1))  # warm, not too hot
    await c.greenhouse.async_evaluate("test")
    assert hass.states.get(HEATER).state == "on"

    hass.states.async_set(INSIDE_TEMP, str(c.number("vent_temp") + 1))
    await c.greenhouse.async_evaluate("test")
    assert c.greenhouse._held("heater", time.time()) == 0
    assert hass.states.get(HEATER).state == "off"


@pytest.mark.asyncio
async def test_resume_button_is_hidden_on_outdoor_zones(hass, fake_valve_services):
    from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

    for entity, value in ((VALVE, "off"), (PUMP, "999"), (RAIN_COUNTER, "0"), (OUTDOOR_TEMP, "25")):
        hass.states.async_set(entity, value)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert _reg(hass, entry, "button", "resume_automatic").hidden_by == er.RegistryEntryHider.INTEGRATION


@pytest.mark.parametrize(("old_minutes", "hours"), [(60.0, 1.0), (45.0, 1.0), (90.0, 1.5), (0.0, 0.5), (480.0, 8.0)])
@pytest.mark.asyncio
async def test_manual_hold_time_carries_over_to_auto_resume_after(hass, devices, old_minutes, hours):
    entry = _entry(hass)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "number", DOMAIN, f"{entry.entry_id}_manual_hold_minutes", config_entry=entry, suggested_object_id="gh_hold"
    )
    mock_restore_cache_with_extra_data(
        hass,
        [(State(old.entity_id, str(old_minutes)), NumberExtraStoredData(native_max_value=480.0, native_min_value=0.0, native_step=5.0, native_unit_of_measurement="min", native_value=old_minutes).as_dict())],
    )
    c = await _ready(hass, entry)
    assert c.number("auto_resume_hours") == hours
    assert registry.async_get(old.entity_id) is None  # the old slider is gone
    assert greenhouse.NO_AUTO_RESUME_SECONDS > 0


@pytest.mark.asyncio
async def test_pressing_resume_with_nothing_on_hold_says_so(hass, devices):
    from homeassistant.exceptions import ServiceValidationError

    entry = _entry(hass)
    c = await _ready(hass, entry)
    hass.states.async_set(INSIDE_TEMP, "20")
    await _go(c)
    assert not c.store.state.gh_hold_until
    with pytest.raises(ServiceValidationError) as err:
        await _press(hass, entry, "resume_automatic")
    assert err.value.translation_key == "nothing_on_hold"
