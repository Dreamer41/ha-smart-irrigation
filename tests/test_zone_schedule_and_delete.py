"""The zone card's Watering time popup (zoneflow.set_schedule) and its Delete
zone button (zoneflow.delete_zone): the same settings and the same removal as
Configure > Settings and the device page's Delete, one tap away."""
from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError

from custom_components.zoneflow.const import (
    CONF_ROUTINE_SUN_MODE,
    CONF_ROUTINE_SUN_OFFSET_MINUTES,
    CONF_ROUTINE_TIME,
    DOMAIN,
    SUN_MODE_AFTER_SUNRISE,
)

from .test_smoke_setup import _seed_source_entities, make_entry


async def _loaded(hass, **overrides):
    await _seed_source_entities(hass)
    entry = make_entry(hass, **overrides)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.asyncio
async def test_schedule_summary_is_what_the_zone_is_set_to(hass):
    entry = await _loaded(hass)
    summary = hass.data[DOMAIN][entry.entry_id].schedule_summary()
    assert summary["routine_time"] == "05:30"
    assert summary["deep_soak_time"] == "05:00"
    assert summary["routine_sun_mode"] == "fixed"
    assert summary["deep_soak_enabled"] is True


@pytest.mark.asyncio
async def test_set_schedule_changes_the_time_and_the_zone_runs_on_it(hass):
    entry = await _loaded(hass)
    await hass.services.async_call(
        DOMAIN, "set_schedule", {"routine_time": "06:45:00", "deep_soak_time": "04:15:00"}, blocking=True
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_ROUTINE_TIME] == "06:45:00"
    controller = hass.data[DOMAIN][entry.entry_id]  # the zone reloaded
    assert controller.routine_time.strftime("%H:%M") == "06:45"
    assert controller.deep_soak_time.strftime("%H:%M") == "04:15"


@pytest.mark.asyncio
async def test_set_schedule_to_sunrise_with_an_offset(hass):
    entry = await _loaded(hass)
    await hass.services.async_call(
        DOMAIN,
        "set_schedule",
        {"routine_sun_mode": SUN_MODE_AFTER_SUNRISE, "routine_sun_offset_minutes": 30},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_ROUTINE_SUN_MODE] == SUN_MODE_AFTER_SUNRISE
    assert entry.options[CONF_ROUTINE_SUN_OFFSET_MINUTES] == 30
    controller = hass.data[DOMAIN][entry.entry_id]
    assert controller.schedule_summary()["routine_sun_mode"] == SUN_MODE_AFTER_SUNRISE
    # the time that was there is kept for when the mode goes back to fixed
    assert controller.routine_time.strftime("%H:%M") == "05:30"


@pytest.mark.asyncio
async def test_set_schedule_with_the_same_values_does_not_reload(hass):
    entry = await _loaded(hass)
    controller = hass.data[DOMAIN][entry.entry_id]
    await hass.services.async_call(
        DOMAIN, "set_schedule", {"routine_time": "05:30:00", "routine_sun_mode": "fixed"}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][entry.entry_id] is controller


@pytest.mark.asyncio
async def test_set_schedule_refuses_a_bad_mode_and_offset(hass):
    await _loaded(hass)
    import voluptuous as vol

    for bad in ({"routine_sun_mode": "noon"}, {"routine_sun_offset_minutes": 500}):
        with pytest.raises(vol.Invalid):
            await hass.services.async_call(DOMAIN, "set_schedule", bad, blocking=True)


@pytest.mark.asyncio
async def test_delete_zone_removes_the_zone(hass):
    entry = await _loaded(hass)
    device_id = next(iter(hass.data["device_registry"].devices.values())).id
    await hass.services.async_call(DOMAIN, "delete_zone", {"device_id": [device_id]}, blocking=True)
    await hass.async_block_till_done()
    assert hass.config_entries.async_get_entry(entry.entry_id) is None
    assert entry.entry_id not in hass.data.get(DOMAIN, {})


@pytest.mark.asyncio
async def test_delete_zone_never_picks_the_only_zone_for_you(hass):
    entry = await _loaded(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "delete_zone", {}, blocking=True)
    assert entry.state is ConfigEntryState.LOADED
