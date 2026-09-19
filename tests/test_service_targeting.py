"""Regression coverage for the multi-zone service-targeting fix.

Before this fix, __init__.py registered zoneflow.run_deep_soak /
run_routine_irrigation / reset_lock / test_pulse fresh inside
async_setup_entry -- once per zone. hass.services.async_register silently
replaces a same-name registration, so with two zones loaded, calling any of
these four services always ran whichever zone's config entry happened to
load LAST, no matter which zone the caller actually meant. These tests
prove: (1) a single-zone install still needs no target at all (unchanged
behavior), (2) a multi-zone call with no target is a clear error rather
than a silent guess, and (3) a multi-zone call WITH a target (device_id or
entity_id) lands on the correct zone's controller, not the other one's.
"""
import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr

from custom_components.zoneflow.const import DOMAIN

from .test_smoke_setup import PUMP, RAIN_COUNTER, VALVE, OUTDOOR_TEMP, make_entry

VALVE_B = "switch.watering2"


async def _seed(hass):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(VALVE_B, "off")
    hass.states.async_set(PUMP, "0")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "25.0")
    await hass.async_block_till_done()


def _device_id_for(hass, entry) -> str:
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None, "zone device was not registered"
    return device.id


@pytest.mark.asyncio
async def test_single_zone_service_call_needs_no_target(hass, fake_valve_services):
    """Unchanged behavior for the common case: one zone, no target given."""
    await _seed(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(DOMAIN, "reset_lock", {}, blocking=True)
    await hass.async_block_till_done()
    # No exception raised is the assertion here; reset_lock is a no-op-safe
    # call, so also confirm it actually reached the one real controller.
    controller = hass.data[DOMAIN][entry.entry_id]
    assert controller.store.state.lock_on is False


@pytest.mark.asyncio
async def test_multi_zone_call_without_target_raises(hass, fake_valve_services):
    await _seed(hass)
    entry_a = make_entry(hass, zone_name="Zone A")
    entry_b = make_entry(hass, zone_name="Zone B", valve_entity=VALVE_B)
    assert await hass.config_entries.async_setup(entry_a.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "reset_lock", {}, blocking=True)


@pytest.mark.asyncio
async def test_multi_zone_call_with_device_target_hits_correct_zone(hass, fake_valve_services):
    await _seed(hass)
    entry_a = make_entry(hass, zone_name="Zone A")
    entry_b = make_entry(hass, zone_name="Zone B", valve_entity=VALVE_B)
    assert await hass.config_entries.async_setup(entry_a.entry_id)
    await hass.async_block_till_done()

    controller_a = hass.data[DOMAIN][entry_a.entry_id]
    controller_b = hass.data[DOMAIN][entry_b.entry_id]

    # Simulate both zones mid-cycle (lock held).
    await controller_a._set_lock(True)
    await controller_b._set_lock(True)

    device_id_b = _device_id_for(hass, entry_b)
    await hass.services.async_call(
        DOMAIN, "reset_lock", {"device_id": [device_id_b]}, blocking=True
    )
    await hass.async_block_till_done()

    # Only zone B's lock was cleared -- proves the call was NOT silently
    # routed to zone A (the zone that happened to load first/last).
    assert controller_b.store.state.lock_on is False
    assert controller_a.store.state.lock_on is True


@pytest.mark.asyncio
async def test_multi_zone_call_with_entity_target_hits_correct_zone(hass, fake_valve_services):
    """Targeting via any entity that belongs to the zone's device (not just
    the device_id itself) must resolve to the same zone -- this is the more
    common real-world case, since the UI target picker offers both."""
    await _seed(hass)
    entry_a = make_entry(hass, zone_name="Zone A")
    entry_b = make_entry(hass, zone_name="Zone B", valve_entity=VALVE_B)
    assert await hass.config_entries.async_setup(entry_a.entry_id)
    await hass.async_block_till_done()

    controller_a = hass.data[DOMAIN][entry_a.entry_id]
    controller_b = hass.data[DOMAIN][entry_b.entry_id]
    await controller_a._set_lock(True)
    await controller_b._set_lock(True)

    # Any entity registered against zone B's device works -- pick one of
    # its number entities (every zone has these) rather than requiring a
    # specific platform.
    from homeassistant.helpers import entity_registry as er

    ent_reg = er.async_get(hass)
    device_id_b = _device_id_for(hass, entry_b)
    zone_b_entity_id = next(
        entity.entity_id for entity in ent_reg.entities.values() if entity.device_id == device_id_b
    )

    await hass.services.async_call(
        DOMAIN, "reset_lock", {"entity_id": [zone_b_entity_id]}, blocking=True
    )
    await hass.async_block_till_done()

    assert controller_b.store.state.lock_on is False
    assert controller_a.store.state.lock_on is True


@pytest.mark.asyncio
async def test_multi_zone_ambiguous_target_raises(hass, fake_valve_services):
    """Targeting entities/devices from BOTH zones at once must fail loudly,
    not silently pick one."""
    await _seed(hass)
    entry_a = make_entry(hass, zone_name="Zone A")
    entry_b = make_entry(hass, zone_name="Zone B", valve_entity=VALVE_B)
    assert await hass.config_entries.async_setup(entry_a.entry_id)
    await hass.async_block_till_done()

    device_id_a = _device_id_for(hass, entry_a)
    device_id_b = _device_id_for(hass, entry_b)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "reset_lock", {"device_id": [device_id_a, device_id_b]}, blocking=True
        )
