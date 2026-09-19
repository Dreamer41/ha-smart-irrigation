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


async def _setup_all(hass, first_entry, *rest_entries):
    """Same idea as _setup_both, generalized to 3+ zones registered at
    once -- the first async_setup() call still bootstraps every
    already-registered entry for the domain in one go."""
    assert await hass.config_entries.async_setup(first_entry.entry_id)
    await hass.async_block_till_done()
    for entry in rest_entries:
        assert entry.state == ConfigEntryState.LOADED


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
async def test_zones_with_no_pump_power_sensor_still_get_independent_locks(hass, fake_valve_services):
    """Regression: the lock used to be keyed on pump_power_entity alone, so
    any two zones that simply had no pump-power sensor configured (a
    perfectly normal, fully-supported setup -- see the const.py comment on
    CONF_PUMP_ID) would both key to None and collide onto the SAME lock,
    wrongly serializing two zones that may be on completely independent
    pumps. Neither zone below has a pump-power sensor or a pump_id -- they
    must still get different locks."""
    await _seed(hass)
    entry_a = make_entry(hass, zone_name="Zone A", pump_power_entity=None)
    entry_b = make_entry(hass, zone_name="Zone B", valve_entity=VALVE_B, pump_power_entity=None)
    await _setup_both(hass, entry_a, entry_b)

    controller_a = hass.data[DOMAIN][entry_a.entry_id]
    controller_b = hass.data[DOMAIN][entry_b.entry_id]

    assert controller_a.pump_power_entity is None
    assert controller_b.pump_power_entity is None
    assert controller_a._get_pump_lock() is not controller_b._get_pump_lock()


@pytest.mark.asyncio
async def test_pump_id_groups_zones_that_share_a_pump_without_a_wattage_sensor(hass, fake_valve_services):
    """The whole reason pump_id exists: two zones can genuinely share one
    physical pump even when neither (or only one) has a pump-power sensor
    on it. Setting the same pump_id string must group them onto the same
    lock regardless of what pump_power_entity says."""
    await _seed(hass)
    entry_a = make_entry(hass, zone_name="Zone A", pump_power_entity=None, pump_id="Pump A")
    entry_b = make_entry(hass, zone_name="Zone B", valve_entity=VALVE_B, pump_power_entity=None, pump_id="Pump A")
    await _setup_both(hass, entry_a, entry_b)

    controller_a = hass.data[DOMAIN][entry_a.entry_id]
    controller_b = hass.data[DOMAIN][entry_b.entry_id]

    assert controller_a._get_pump_lock() is controller_b._get_pump_lock()


@pytest.mark.asyncio
async def test_three_zone_mixed_pump_grouping(hass, fake_valve_services):
    """The exact scenario from real multi-zone setups: 3 zones, 2 of them
    (A and B) share one physical pump via pump_id, the third (C) is on a
    completely independent pump. A and B must share a lock; C must never
    share a lock with either of them, so C is free to run at the same time
    as A or B without waiting its turn."""
    await _seed(hass)
    valve_c = "switch.watering3"
    hass.states.async_set(valve_c, "off")
    entry_a = make_entry(hass, zone_name="Zone A", pump_power_entity=None, pump_id="Pump A")
    entry_b = make_entry(hass, zone_name="Zone B", valve_entity=VALVE_B, pump_power_entity=None, pump_id="Pump A")
    entry_c = make_entry(hass, zone_name="Zone C", valve_entity=valve_c, pump_power_entity=None, pump_id="Pump B")
    await _setup_all(hass, entry_a, entry_b, entry_c)

    controller_a = hass.data[DOMAIN][entry_a.entry_id]
    controller_b = hass.data[DOMAIN][entry_b.entry_id]
    controller_c = hass.data[DOMAIN][entry_c.entry_id]

    assert controller_a._get_pump_lock() is controller_b._get_pump_lock()
    assert controller_c._get_pump_lock() is not controller_a._get_pump_lock()
    assert controller_c._get_pump_lock() is not controller_b._get_pump_lock()


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


# Real, deliberately-mismatched split-cycle durations (see calculations.py's
# plan_deep_soak): strawberries in clay-loam infiltrate slowly, so they run
# as 3 short pulses separated by long soak gaps (a total on/off span of
# 3*9 + 2*31 = 89 minutes); pumpkin in sandy soil infiltrates fast enough to
# just take one continuous pulse (111 minutes, no soak needed at all). The
# two durations don't neatly divide into each other on purpose, so a naive
# "wait until roughly the same time" implementation would show its seams.
# Real minutes are divided by 6000 (i.e. 1 scenario-minute -> 10ms of real
# test time) purely so the test runs in about a second instead of two hours
# -- the pulse/rest *structure* (3-pulse split cycle vs. 1 continuous pulse,
# same shared pump) is exactly what production code runs.
_SCENARIO_MINUTES_TO_TEST_SECONDS = 1 / 100  # pulse_minutes * 60 == real_minutes / 100


def _scaled(real_minutes: float) -> float:
    return real_minutes * _SCENARIO_MINUTES_TO_TEST_SECONDS / 60


@pytest.mark.asyncio
async def test_shared_pump_second_zone_waits_out_first_zones_full_split_cycle(hass, fake_valve_services):
    """Decision: a zone holds the shared-pump lock for its ENTIRE multi-pulse
    cycle, including the soak gaps between pulses (see controller.py's
    _run_pulses -- the lock is acquired once and held across the whole
    _execute_pulses call). This test is what that decision is actually for:
    zone A's soak gap after its first pulse might look, from the outside,
    like "the pump is free again" -- but zone B (sharing the same pump)
    must NOT sneak a pulse in during that gap. It has to wait for zone A's
    entire cycle -- all 3 pulses AND both soak gaps -- to fully finish,
    even though zone B's own pulse (a single continuous run) would
    technically fit inside just one of those gaps."""
    await _seed(hass)
    entry_a = make_entry(hass, zone_name="Strawberries")  # clay-loam, split-cycle
    entry_b = make_entry(hass, zone_name="Pumpkin", valve_entity=VALVE_B)  # sandy, single pulse, same pump
    await _setup_both(hass, entry_a, entry_b)

    controller_a = hass.data[DOMAIN][entry_a.entry_id]
    controller_b = hass.data[DOMAIN][entry_b.entry_id]

    loop = asyncio.get_event_loop()
    events: list[tuple[str, str, float]] = []  # (entity_id, new_state, timestamp)

    def _record(event):
        entity_id = event.data.get("entity_id")
        if entity_id in (VALVE, VALVE_B):
            events.append((entity_id, event.data["new_state"].state, loop.time()))

    unsub = hass.bus.async_listen("state_changed", _record)
    try:
        await asyncio.gather(
            controller_a._run_pulses(
                count=3,
                pulse_minutes=_scaled(9),
                rest_minutes=_scaled(31),
                min_pump_watts=100,
                kind="test_strawberries_deep_soak",
                target_mm_for_log=0.0,
                deducted_mm_for_log=0.0,
                runtime_for_log=89,
            ),
            controller_b._run_pulses(
                count=1,
                pulse_minutes=_scaled(111),
                rest_minutes=0,
                min_pump_watts=100,
                kind="test_pumpkin_deep_soak",
                target_mm_for_log=0.0,
                deducted_mm_for_log=0.0,
                runtime_for_log=111,
            ),
        )
        await hass.async_block_till_done()
    finally:
        unsub()

    zone_a_events = [(s, t) for e, s, t in events if e == VALVE]
    zone_b_events = [(s, t) for e, s, t in events if e == VALVE_B]

    # Zone A really did split into 3 separate on/off pulses (not collapsed
    # into one continuous run) -- 3 "on" and 3 "off" transitions.
    assert [s for s, _ in zone_a_events].count("on") == 3
    assert [s for s, _ in zone_a_events].count("off") == 3
    # Zone B ran its one continuous pulse.
    assert [s for s, _ in zone_b_events] == ["on", "off"]

    zone_a_last_off_ts = max(t for s, t in zone_a_events if s == "off")
    zone_a_first_on_ts = min(t for s, t in zone_a_events if s == "on")
    zone_b_on_ts = next(t for s, t in zone_b_events if s == "on")

    # The actual regression this guards: zone B's valve must open only
    # after zone A's LAST "off" (the true end of its whole cycle) -- not
    # merely after zone A's first pulse ends, which is when a soak-gap-
    # release implementation would have let it sneak in.
    assert zone_b_on_ts > zone_a_last_off_ts, (
        "zone B opened its valve before zone A's full split cycle (all 3 pulses "
        "+ both soak gaps) had finished -- the shared pump lock must be held "
        "across the whole cycle, not released during a soak gap"
    )
    # Sanity: that really was a wait, not a coincidence of ordering -- zone A's
    # cycle genuinely spanned from its first pulse to well after it.
    assert zone_a_last_off_ts > zone_a_first_on_ts
