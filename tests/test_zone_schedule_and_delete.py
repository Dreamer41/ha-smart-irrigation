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


async def _two_loaded(hass):
    await _seed_source_entities(hass)
    from .test_multi_zone_pump_sharing import VALVE_B

    hass.states.async_set(VALVE_B, "off")
    a = make_entry(hass, zone_name="Zone A")
    b = make_entry(hass, zone_name="Zone B", valve_entity=VALVE_B, csv_path="/tmp/test_zoneflow_b.csv")
    assert await hass.config_entries.async_setup(a.entry_id)
    await hass.async_block_till_done()
    return a, b


def _device_of(hass, entry):
    from homeassistant.helpers import device_registry as dr

    return next(d.id for d in dr.async_get(hass).devices.values() if entry.entry_id in d.config_entries)


@pytest.mark.asyncio
async def test_delete_zone_deletes_the_zone_it_names_not_the_only_loaded_one(hass):
    a, b = await _two_loaded(hass)
    # B is not loaded (a setup error, say): naming B must not delete A
    await hass.config_entries.async_unload(b.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "delete_zone", {"device_id": [_device_of(hass, b)]}, blocking=True)
    await hass.async_block_till_done()
    assert hass.config_entries.async_get_entry(a.entry_id) is not None
    assert hass.config_entries.async_get_entry(b.entry_id) is None


@pytest.mark.asyncio
async def test_delete_zone_with_an_unrelated_target_deletes_nothing(hass):
    entry = await _loaded(hass)
    hass.states.async_set("light.kitchen", "off")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "delete_zone", {"entity_id": ["light.kitchen"]}, blocking=True)
    assert hass.config_entries.async_get_entry(entry.entry_id) is not None


@pytest.mark.asyncio
async def test_a_second_delete_call_does_not_delete_the_next_zone(hass):
    a, b = await _two_loaded(hass)
    device_a = _device_of(hass, a)
    await hass.services.async_call(DOMAIN, "delete_zone", {"device_id": [device_a]}, blocking=True)
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "delete_zone", {"device_id": [device_a]}, blocking=True)
    assert hass.config_entries.async_get_entry(b.entry_id) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("service,data", [("delete_zone", {}), ("set_schedule", {"routine_time": "06:00:00"})])
async def test_zone_services_that_change_configuration_need_an_administrator(hass, hass_read_only_user, hass_admin_user, service, data):
    from homeassistant.core import Context
    from homeassistant.exceptions import Unauthorized

    entry = await _loaded(hass)
    data = {**data, "device_id": [_device_of(hass, entry)]}
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN, service, data, blocking=True, context=Context(user_id=hass_read_only_user.id)
        )
    assert hass.config_entries.async_get_entry(entry.entry_id) is not None
    assert not entry.options.get(CONF_ROUTINE_TIME)
    # an administrator (and an automation, which has no user) may
    await hass.services.async_call(DOMAIN, service, data, blocking=True, context=Context(user_id=hass_admin_user.id))


@pytest.mark.asyncio
async def test_set_schedule_refuses_while_the_zone_is_watering(hass):
    entry = await _loaded(hass)
    controller = hass.data[DOMAIN][entry.entry_id]
    controller.store.state.lock_on = True
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "set_schedule", {"routine_time": "06:00:00"}, blocking=True)
    assert not entry.options.get(CONF_ROUTINE_TIME)


@pytest.mark.asyncio
async def test_schedule_summary_survives_an_entry_with_no_times(hass):
    from custom_components.zoneflow.const import CONF_DEEP_SOAK_TIME

    entry = await _loaded(hass)
    hass.config_entries.async_update_entry(entry, data={k: v for k, v in entry.data.items() if k not in (CONF_ROUTINE_TIME, CONF_DEEP_SOAK_TIME)})
    controller = hass.data[DOMAIN][entry.entry_id]
    assert controller.schedule_summary()["routine_time"] == "05:30"


@pytest.mark.asyncio
async def test_set_schedule_changes_the_zone_it_names_not_the_only_loaded_one(hass):
    a, b = await _two_loaded(hass)
    await hass.config_entries.async_unload(b.entry_id)  # B is not loaded: A is the only controller
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "set_schedule", {"device_id": [_device_of(hass, b)], "routine_time": "21:15:00"}, blocking=True
        )
    assert not a.options.get(CONF_ROUTINE_TIME)


@pytest.mark.asyncio
async def test_set_schedule_with_an_unrelated_target_changes_nothing(hass):
    entry = await _loaded(hass)
    hass.states.async_set("light.kitchen", "off")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "set_schedule", {"entity_id": ["light.kitchen"], "routine_time": "21:15:00"}, blocking=True
        )
    assert not entry.options.get(CONF_ROUTINE_TIME)
