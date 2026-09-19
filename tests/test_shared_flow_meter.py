"""A single physical flow meter can sit in one of two different places
relative to a multi-zone setup, and they behave very differently:

1. Downstream of ONE shared pump, upstream of that pump's own zones'
   valves -- the normal "shared pump" case (see
   test_multi_zone_pump_sharing.py). _get_pump_lock already guarantees
   only one of those zones' valves is ever open at a time, so the meter's
   before/after reading around a zone's own pulse is automatically
   trustworthy with no extra work.

2. Upstream of MULTIPLE independent pumps (e.g. one main-line meter for
   the whole property, feeding several separate pump branches) -- pumps
   are deliberately allowed to run at the same time (different pump_id
   means no shared lock), so without something extra, two zones on
   different pumps could both draw through that one meter simultaneously,
   and its single running total would have no way to say which zone's
   water was which -- because the water genuinely is mixed on that line,
   not just ambiguously attributed. There's no way to fix that after the
   fact by "looking at which valve is open" once both are already open.

_get_flow_meter_lock (controller.py) is the fix for case 2: a second
lock, keyed on the flow meter's own entity_id, that zones sharing a flow
meter also serialize against -- regardless of whether they share a pump.
These tests cover: it doesn't kick in unless a flow meter is actually
shared: it does force correct serialization when one is shared across
different pumps; and, once serialized, the delta reading is correctly
attributed to only the zone that was actually running.
"""
import asyncio

import pytest

from custom_components.zoneflow.const import DOMAIN

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry
from .test_multi_zone_pump_sharing import _setup_both

VALVE_B = "switch.watering2"
FLOW_METER = "sensor.shared_main_line_flow_liters"
FLOW_METER_B = "sensor.zone_b_own_flow_liters"


async def _seed(hass):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(VALVE_B, "off")
    hass.states.async_set(PUMP, 999)
    hass.states.async_set(RAIN_COUNTER, 0)
    hass.states.async_set(OUTDOOR_TEMP, 25.0)
    hass.states.async_set(FLOW_METER, 0.0)
    hass.states.async_set(FLOW_METER_B, 0.0)
    await hass.async_block_till_done()


def _bump_shared_meter_on_valve_on(hass, valve_entity, flow_meter_entity, increment):
    """Simulates "this zone delivers `increment` liters" by bumping the
    shared cumulative meter the instant this zone's own valve opens --
    idealized (real flow ramps up over the pulse), but sufficient to prove
    which zone's window a given chunk of the running total lands in."""

    def _cb(event):
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        if entity_id == valve_entity and new_state is not None and new_state.state == "on":
            current = float(hass.states.get(flow_meter_entity).state)
            hass.states.async_set(flow_meter_entity, current + increment)

    return hass.bus.async_listen("state_changed", _cb)


@pytest.mark.asyncio
async def test_no_flow_meter_configured_gets_no_lock(hass, fake_valve_services):
    await _seed(hass)
    entry = make_entry(hass, flow_meter_entity=None)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    assert controller._get_flow_meter_lock() is None


@pytest.mark.asyncio
async def test_two_zones_sharing_a_flow_meter_get_the_same_lock_even_on_different_pumps(hass, fake_valve_services):
    await _seed(hass)
    entry_a = make_entry(hass, zone_name="Zone A", pump_id="Pump A", flow_meter_entity=FLOW_METER)
    entry_b = make_entry(
        hass, zone_name="Zone B", valve_entity=VALVE_B, pump_id="Pump B", flow_meter_entity=FLOW_METER
    )
    await _setup_both(hass, entry_a, entry_b)

    controller_a = hass.data[DOMAIN][entry_a.entry_id]
    controller_b = hass.data[DOMAIN][entry_b.entry_id]

    # Genuinely different pumps -- the pump lock does NOT tie them together.
    assert controller_a._get_pump_lock() is not controller_b._get_pump_lock()
    # But the shared flow meter does.
    assert controller_a._get_flow_meter_lock() is controller_b._get_flow_meter_lock()


@pytest.mark.asyncio
async def test_zones_with_different_flow_meters_on_different_pumps_still_run_concurrently(hass, fake_valve_services):
    """Regression/control: adding the flow-meter lock must not accidentally
    serialize zones that don't actually share anything. Two independent
    pumps, two separate flow meters (one zone has none at all) -- both
    pulses should start at essentially the same moment, exactly like the
    no-flow-meter case already covered in test_multi_zone_pump_sharing.py.
    """
    await _seed(hass)
    entry_a = make_entry(hass, zone_name="Zone A", pump_id="Pump A", flow_meter_entity=FLOW_METER)
    entry_b = make_entry(hass, zone_name="Zone B", valve_entity=VALVE_B, pump_id="Pump B", flow_meter_entity=None)
    await _setup_both(hass, entry_a, entry_b)

    controller_a = hass.data[DOMAIN][entry_a.entry_id]
    controller_b = hass.data[DOMAIN][entry_b.entry_id]

    loop = asyncio.get_event_loop()
    on_ts: dict[str, float] = {}

    def _record(event):
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        if entity_id in (VALVE, VALVE_B) and new_state is not None and new_state.state == "on":
            on_ts.setdefault(entity_id, loop.time())

    unsub = hass.bus.async_listen("state_changed", _record)
    try:
        await asyncio.gather(controller_a.test_pulse(1), controller_b.test_pulse(1))
        await hass.async_block_till_done()
    finally:
        unsub()

    assert abs(on_ts[VALVE] - on_ts[VALVE_B]) < 0.5, (
        "zones with unrelated flow meters on different pumps should start at the same time, "
        "not wait on each other"
    )


@pytest.mark.asyncio
async def test_shared_flow_meter_across_different_pumps_forces_serialization(hass, fake_valve_services):
    """The actual fix: two zones on genuinely DIFFERENT pumps (so the pump
    lock alone would let them run at once) but pointed at the SAME single
    upstream flow meter must still never have both valves open together --
    otherwise the shared meter's reading would mix both zones' water with
    no way to separate it back out afterwards."""
    await _seed(hass)
    entry_a = make_entry(hass, zone_name="Zone A", pump_id="Pump A", flow_meter_entity=FLOW_METER)
    entry_b = make_entry(
        hass, zone_name="Zone B", valve_entity=VALVE_B, pump_id="Pump B", flow_meter_entity=FLOW_METER
    )
    await _setup_both(hass, entry_a, entry_b)

    controller_a = hass.data[DOMAIN][entry_a.entry_id]
    controller_b = hass.data[DOMAIN][entry_b.entry_id]

    events: list[tuple[str, str]] = []

    def _record(event):
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        if entity_id in (VALVE, VALVE_B) and new_state is not None:
            events.append((entity_id, new_state.state))

    unsub = hass.bus.async_listen("state_changed", _record)
    try:
        # Confirm up front these really are independent pumps -- if this
        # assertion ever fails, the test below would pass for the wrong
        # reason (pump-lock serialization instead of flow-meter-lock
        # serialization).
        assert controller_a._get_pump_lock() is not controller_b._get_pump_lock()

        await asyncio.gather(controller_a.test_pulse(1), controller_b.test_pulse(1))
        await hass.async_block_till_done()
    finally:
        unsub()

    assert (VALVE, "on") in events and (VALVE, "off") in events
    assert (VALVE_B, "on") in events and (VALVE_B, "off") in events

    first_on_index = min(i for i, (e, s) in enumerate(events) if s == "on")
    first_entity = events[first_on_index][0]
    other_entity = VALVE_B if first_entity == VALVE else VALVE
    first_off_index = next(i for i, (e, s) in enumerate(events) if e == first_entity and s == "off")
    other_on_index = next(i for i, (e, s) in enumerate(events) if e == other_entity and s == "on")
    assert first_off_index < other_on_index, (
        "the second zone's valve opened before the first zone's had closed -- both zones "
        "were drawing through the same shared flow meter at once"
    )


@pytest.mark.asyncio
async def test_shared_flow_meter_delta_is_correctly_attributed_per_zone(hass, fake_valve_services):
    """Once two different-pump zones are correctly serialized against each
    other by the shared flow meter (previous test), confirm the actual
    payoff: each zone's own `last_cycle_water_liters` reflects only the
    water that moved during ITS OWN window on the shared meter, not a
    blended or double-counted total."""
    await _seed(hass)
    entry_a = make_entry(hass, zone_name="Zone A", pump_id="Pump A", flow_meter_entity=FLOW_METER)
    entry_b = make_entry(
        hass, zone_name="Zone B", valve_entity=VALVE_B, pump_id="Pump B", flow_meter_entity=FLOW_METER
    )
    await _setup_both(hass, entry_a, entry_b)

    controller_a = hass.data[DOMAIN][entry_a.entry_id]
    controller_b = hass.data[DOMAIN][entry_b.entry_id]

    # Zone A "delivers" 5.0L the instant its valve opens; Zone B "delivers"
    # 3.0L the instant its valve opens. Both bump the SAME running total.
    unsub_a = _bump_shared_meter_on_valve_on(hass, VALVE, FLOW_METER, 5.0)
    unsub_b = _bump_shared_meter_on_valve_on(hass, VALVE_B, FLOW_METER, 3.0)
    try:
        await asyncio.gather(controller_a.test_pulse(1), controller_b.test_pulse(1))
        await hass.async_block_till_done()
    finally:
        unsub_a()
        unsub_b()

    # Regardless of which zone happened to go first, each one's own delta
    # must equal exactly what IT added -- never 0 (missed entirely), never
    # 8.0 (both zones' water blended together).
    assert controller_a.store.state.last_cycle_water_liters == pytest.approx(5.0)
    assert controller_b.store.state.last_cycle_water_liters == pytest.approx(3.0)
    # Sanity: the meter really did end up with both contributions.
    assert float(hass.states.get(FLOW_METER).state) == pytest.approx(8.0)


@pytest.mark.asyncio
async def test_zones_sharing_both_pump_and_flow_meter_still_work_as_before(hass, fake_valve_services):
    """The common, originally-intended case (flow meter on the shared
    pump's own line, same as the pump-power sensor) -- adding the new
    flow-meter lock must not change this at all, since the pump lock
    already fully serializes them. Regression check that the two locks
    layer correctly instead of conflicting or deadlocking."""
    await _seed(hass)
    entry_a = make_entry(hass, zone_name="Zone A", pump_id="Pump A", flow_meter_entity=FLOW_METER)
    entry_b = make_entry(
        hass, zone_name="Zone B", valve_entity=VALVE_B, pump_id="Pump A", flow_meter_entity=FLOW_METER
    )
    await _setup_both(hass, entry_a, entry_b)

    controller_a = hass.data[DOMAIN][entry_a.entry_id]
    controller_b = hass.data[DOMAIN][entry_b.entry_id]

    assert controller_a._get_pump_lock() is controller_b._get_pump_lock()
    assert controller_a._get_flow_meter_lock() is controller_b._get_flow_meter_lock()

    unsub_a = _bump_shared_meter_on_valve_on(hass, VALVE, FLOW_METER, 5.0)
    unsub_b = _bump_shared_meter_on_valve_on(hass, VALVE_B, FLOW_METER, 3.0)
    try:
        await asyncio.gather(controller_a.test_pulse(1), controller_b.test_pulse(1))
        await hass.async_block_till_done()
    finally:
        unsub_a()
        unsub_b()

    assert controller_a.store.state.last_cycle_water_liters == pytest.approx(5.0)
    assert controller_b.store.state.last_cycle_water_liters == pytest.approx(3.0)
