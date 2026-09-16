"""Multi-zone: each zone is its own config entry (see config_flow.py), so
most independence falls out for free -- separate locks, separate watchdogs,
separate storage. The one thing that needs real coordination is when two
zones happen to share the same physical pump: they must never open their
valves at the same time (it would skew both zones' flow-rate calibration),
but neither should a shared pump silently block a zone that's due -- it
should just queue and run right after, not skip.

Note: in this test harness, the FIRST call to hass.config_entries.async_setup()
for a domain bootstraps the whole zoneflow component, which brings up every
config entry already registered (add_to_hass'd) for that domain in one go --
not just the entry_id passed in. So these tests register both entries first,
then make a single async_setup() call and confirm both come up loaded.
"""
import asyncio

import pytest
from homeassistant.config_entries import ConfigEntryState

from custom_components.zoneflow.const import DOMAIN

from .test_smoke_setup import PUMP, RAIN_COUNTER, VALVE, OUTDOOR_TEMP, make_entry

VALVE_B = "switch.watering2"


async def _seed(hass):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(VALVE_B, "off")
    hass.states.async_set(PUMP, 999)  # comfortably above pump_min_watts default
    hass.states.async_set(RAIN_COUNTER, 0)
    hass.states.async_set(OUTDOOR_TEMP, 25.0)
    await hass.async_block_till_done()


async def _setup_both(hass, entry_a, entry_b):
    """Bring up both entries. The first async_setup() call bootstraps the
    whole domain and loads every already-registered entry, so entry_b comes
    up as a side effect -- don't call async_setup() on it again."""
    assert await hass.config_entries.async_setup(entry_a.entry_id)
    await hass.async_block_till_done()
    assert entry_b.state == ConfigEntryState.LOADED


@pytest.mark.asyncio
async def test_independent_pumps_get_different_locks(hass, fake_valve_services):
    await _seed(hass)
    entry_a = make_entry(hass, zone_name="Zone A")
    entry_b = make_entry(hass, zone_name="Zone B", pump_power_entity="sensor.other_pump")
    await _setup_both(hass, entry_a, entry_b)

    controller_a = hass.data[DOMAIN][entry_a.entry_id]
    controller_b = hass.data[DOMAIN][entry_b.entry_id]

    assert controller_a._get_pump_lock() is not controller_b._get_pump_lock()


@pytest.mark.asyncio
async def test_shared_pump_gets_the_same_lock(hass, fake_valve_services):
    await _seed(hass)
    entry_a = make_entry(hass, zone_name="Zone A")
    entry_b = make_entry(hass, zone_name="Zone B", valve_entity=VALVE_B)  # same pump_power_entity as A
    await _setup_both(hass, entry_a, entry_b)

    controller_a = hass.data[DOMAIN][entry_a.entry_id]
    controller_b = hass.data[DOMAIN][entry_b.entry_id]

    assert controller_a._get_pump_lock() is controller_b._get_pump_lock()


@pytest.mark.asyncio
async def test_shared_pump_serializes_valve_pulses_instead_of_overlapping(hass, fake_valve_services):
    """Both zones share a pump. Firing both at once must never show zone B's
    valve going on before zone A's has gone back off -- if it did, both
    valves were open on the same pump at the same time."""
    await _seed(hass)
    entry_a = make_entry(hass, zone_name="Zone A")
    entry_b = make_entry(hass, zone_name="Zone B", valve_entity=VALVE_B)  # same pump
    await _setup_both(hass, entry_a, entry_b)

    controller_a = hass.data[DOMAIN][entry_a.entry_id]
    controller_b = hass.data[DOMAIN][entry_b.entry_id]

    events: list[tuple[str, str]] = []  # (entity_id, new_state)

    def _record(event):
        entity_id = event.data.get("entity_id")
        if entity_id in (VALVE, VALVE_B):
            events.append((entity_id, event.data["new_state"].state))

    unsub = hass.bus.async_listen("state_changed", _record)
    try:
        await asyncio.gather(controller_a.test_pulse(1), controller_b.test_pulse(1))
        await hass.async_block_till_done()
    finally:
        unsub()

    # Both zones must have actually run (queued, not skipped/overwritten).
    assert (VALVE, "on") in events and (VALVE, "off") in events
    assert (VALVE_B, "on") in events and (VALVE_B, "off") in events

    # Whichever zone went first, it must have fully closed its valve before
    # the other zone's valve opened -- no overlap on the shared pump.
    first_on_index = min(i for i, (e, s) in enumerate(events) if s == "on")
    first_entity = events[first_on_index][0]
    other_entity = VALVE_B if first_entity == VALVE else VALVE
    first_off_index = next(i for i, (e, s) in enumerate(events) if e == first_entity and s == "off")
    other_on_index = next(i for i, (e, s) in enumerate(events) if e == other_entity and s == "on")
    assert first_off_index < other_on_index, "the second zone's valve opened before the first zone's had closed"


@pytest.mark.asyncio
async def test_pump_preamble_and_postamble_delay_the_next_queued_zone(hass, fake_valve_services):
    """A configured preamble/postamble should measurably delay when the
    second zone's valve opens, beyond just the first zone's own pulse time."""
    await _seed(hass)
    entry_a = make_entry(hass, zone_name="Zone A")
    entry_b = make_entry(hass, zone_name="Zone B", valve_entity=VALVE_B)
    await _setup_both(hass, entry_a, entry_b)

    controller_a = hass.data[DOMAIN][entry_a.entry_id]
    controller_b = hass.data[DOMAIN][entry_b.entry_id]
    # Small values to keep the test fast, but big enough to reliably measure.
    controller_a.numbers["pump_postamble_seconds"]._attr_native_value = 0.3
    controller_b.numbers["pump_preamble_seconds"]._attr_native_value = 0.0

    loop = asyncio.get_event_loop()
    timestamps: dict[tuple[str, str], float] = {}

    def _record(event):
        entity_id = event.data.get("entity_id")
        if entity_id in (VALVE, VALVE_B):
            timestamps.setdefault((entity_id, event.data["new_state"].state), loop.time())

    unsub = hass.bus.async_listen("state_changed", _record)
    try:
        await asyncio.gather(controller_a.test_pulse(1), controller_b.test_pulse(1))
        await hass.async_block_till_done()
    finally:
        unsub()

    # Zone A ran first (it was submitted first and the lock is uncontended
    # at t=0), so its postamble should push zone B's valve-on well past
    # zone A's valve-off.
    gap = timestamps[(VALVE_B, "on")] - timestamps[(VALVE, "off")]
    assert gap >= 0.25, f"expected the postamble to delay the next zone by ~0.3s, only saw {gap:.3f}s"
