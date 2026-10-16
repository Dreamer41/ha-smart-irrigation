"""Valve overlap (1.7.3): on a shared pump, the zone that is finishing hands the
pump to the next zone and keeps its own valve open for the Valve Overlap
seconds, so the next valve opens before this one closes."""
from __future__ import annotations

import asyncio

import pytest
from homeassistant.core import callback

from custom_components.zoneflow.const import DOMAIN, NUMBER_DEFAULTS, NUMBER_DEFS

from .scenario_harness import CompressedTime
from .test_multi_zone_pump_sharing import VALVE_B, _seed, _setup_both
from .test_smoke_setup import VALVE, make_entry


async def _two_zones(hass, monkeypatch, tmp_path, overlap):
    await _seed(hass)
    entry_a = make_entry(hass, zone_name="Zone A", pump_id="P", csv_path=str(tmp_path / "a.csv"))
    entry_b = make_entry(hass, zone_name="Zone B", valve_entity=VALVE_B, pump_id="P", csv_path=str(tmp_path / "b.csv"))
    await _setup_both(hass, entry_a, entry_b)
    a = hass.data[DOMAIN][entry_a.entry_id]
    b = hass.data[DOMAIN][entry_b.entry_id]
    for zone in (a, b):
        zone.numbers["routine_pulse_count"].metric_value = 1
        zone.numbers["valve_overlap_seconds"].metric_value = overlap
    CompressedTime(hass, [VALVE, VALVE_B]).install(monkeypatch)
    return a, b


async def _run_both(hass, a, b):
    events: list[tuple[str, str]] = []

    @callback
    def _record(event):
        entity_id = event.data.get("entity_id")
        if entity_id in (VALVE, VALVE_B) and event.data.get("new_state"):
            events.append((entity_id, event.data["new_state"].state))

    unsub = hass.bus.async_listen("state_changed", _record)
    try:
        await asyncio.gather(a.run_routine_now(), b.run_routine_now())
        await hass.async_block_till_done()
    finally:
        unsub()
    return events


def _index(events, entity, state):
    return next(i for i, (e, s) in enumerate(events) if e == entity and s == state)


def _first_second(events):
    first = VALVE if _index(events, VALVE, "on") < _index(events, VALVE_B, "on") else VALVE_B
    return first, (VALVE_B if first == VALVE else VALVE)


def _overlapped(events):
    """The first zone's valve is still open when the second zone's opens: it
    closes after the second's first "on" and before the second's first "off"."""
    first, second = _first_second(events)
    on, off = _index(events, second, "on"), _index(events, second, "off")
    return any(e == first and s == "off" and on < i < off for i, (e, s) in enumerate(events))


def test_the_setting_is_zero_to_ten_seconds_and_starts_off():
    name, low, high, step, unit = NUMBER_DEFS["valve_overlap_seconds"]
    assert (low, high, step, unit) == (0.0, 10.0, 1.0, "s")
    assert NUMBER_DEFAULTS["valve_overlap_seconds"] == 0.0


@pytest.mark.asyncio
async def test_with_overlap_the_next_valve_opens_before_the_running_one_closes(hass, fake_valve_services, monkeypatch, tmp_path):
    a, b = await _two_zones(hass, monkeypatch, tmp_path, overlap=5)
    events = await _run_both(hass, a, b)

    assert _overlapped(events), events
    # both ended closed, and the pump is free for the next zone
    assert hass.states.get(VALVE).state == "off" and hass.states.get(VALVE_B).state == "off"
    assert not a._get_pump_lock().locked()
    assert not a._pump_handed_over or a._cycle_kind == ""


@pytest.mark.asyncio
async def test_without_overlap_nothing_changes(hass, fake_valve_services, monkeypatch, tmp_path):
    a, b = await _two_zones(hass, monkeypatch, tmp_path, overlap=0)
    events = await _run_both(hass, a, b)

    assert not _overlapped(events), events
    first, second = _first_second(events)
    assert max(i for i, (e, st) in enumerate(events) if e == first and st == "off") < _index(events, second, "on")
    assert not a._get_pump_lock().locked()


@pytest.mark.asyncio
async def test_a_zone_alone_on_its_pump_just_closes(hass, fake_valve_services, monkeypatch, tmp_path):
    a, b = await _two_zones(hass, monkeypatch, tmp_path, overlap=5)
    await a.run_routine_now()
    await hass.async_block_till_done()
    assert hass.states.get(VALVE).state == "off"
    assert not a._get_pump_lock().locked()
    assert a._pump_handed_over is False  # nobody was waiting: the lock was not given away


@pytest.mark.asyncio
async def test_the_next_zone_skips_its_warm_up_when_the_pump_is_handed_over(hass, fake_valve_services, monkeypatch, tmp_path):
    await _seed(hass)
    entry_a = make_entry(hass, zone_name="Zone A", pump_id="P", csv_path=str(tmp_path / "a.csv"))
    entry_b = make_entry(hass, zone_name="Zone B", valve_entity=VALVE_B, pump_id="P", csv_path=str(tmp_path / "b.csv"))
    await _setup_both(hass, entry_a, entry_b)
    a, b = hass.data[DOMAIN][entry_a.entry_id], hass.data[DOMAIN][entry_b.entry_id]
    for zone in (a, b):
        zone.numbers["routine_pulse_count"].metric_value = 1
        zone.numbers["pump_preamble_seconds"].metric_value = 7
        zone.numbers["valve_overlap_seconds"].metric_value = 4
    clock = CompressedTime(hass, [VALVE, VALVE_B]).install(monkeypatch)
    await _run_both(hass, a, b)
    # the first zone started cold (7 s warm-up); the second found the pump running
    assert clock.sleeps_seconds.count(7) == 1, clock.sleeps_seconds
    assert 4 in clock.sleeps_seconds  # the overlap itself


@pytest.mark.asyncio
async def test_no_overlap_when_both_zones_share_one_flow_meter(hass, fake_valve_services, monkeypatch, tmp_path):
    await _seed(hass)
    hass.states.async_set("sensor.meter", "0")
    entry_a = make_entry(hass, zone_name="Zone A", pump_id="P", flow_meter_entity="sensor.meter", csv_path=str(tmp_path / "a.csv"))
    entry_b = make_entry(
        hass, zone_name="Zone B", valve_entity=VALVE_B, pump_id="P", flow_meter_entity="sensor.meter", csv_path=str(tmp_path / "b.csv")
    )
    await _setup_both(hass, entry_a, entry_b)
    a, b = hass.data[DOMAIN][entry_a.entry_id], hass.data[DOMAIN][entry_b.entry_id]
    for zone in (a, b):
        zone.numbers["routine_pulse_count"].metric_value = 1
        zone.numbers["valve_overlap_seconds"].metric_value = 5
    CompressedTime(hass, [VALVE, VALVE_B]).install(monkeypatch)
    events = await _run_both(hass, a, b)
    assert not _overlapped(events), events


@pytest.mark.asyncio
async def test_a_zone_that_shares_no_pump_does_not_offer_the_setting(hass, fake_valve_services, monkeypatch, tmp_path):
    from custom_components.zoneflow import visibility

    await _seed(hass)
    entry = make_entry(hass, zone_name="Solo", pump_power_entity=None, csv_path=str(tmp_path / "s.csv"))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    solo = hass.data[DOMAIN][entry.entry_id]
    assert ("number", "valve_overlap_seconds") in visibility.hidden_for(solo)


_real_sleep = asyncio.sleep
_real_wait_for = asyncio.wait_for


def _scaled_clock(monkeypatch):
    """Real-ish time, sped up 50x, so another task can act during the overlap."""
    from custom_components.zoneflow import controller as controller_module

    proxy = controller_module.asyncio

    async def sleep(seconds, *args, **kwargs):
        await _real_sleep(min(seconds, 60) * 0.02)

    async def wait_for(aw, timeout=None):
        if timeout is not None and timeout > 50:
            timeout = 0.6  # a pulse
        elif timeout is not None:
            timeout = timeout * 0.02
        return await _real_wait_for(aw, timeout)

    monkeypatch.setattr(proxy, "sleep", sleep)
    monkeypatch.setattr(proxy, "wait_for", wait_for)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["reload", "abort"])
async def test_a_reload_or_abort_during_the_overlap_leaves_both_valves_closed_and_the_pump_free(
    hass, fake_valve_services, monkeypatch, tmp_path, action
):
    a, b = await _two_zones(hass, monkeypatch, tmp_path, overlap=10)
    _scaled_clock(monkeypatch)
    errors = []
    asyncio.get_running_loop().set_exception_handler(lambda _loop, context: errors.append(context))
    run = asyncio.gather(a.run_routine_now(), b.run_routine_now(), return_exceptions=True)
    first = None
    for _ in range(2000):
        first = next((z for z in (a, b) if z._pump_handed_over), None)
        if first is not None:
            break
        await _real_sleep(0.005)
    assert first is not None, "no hand-over happened"
    await _real_sleep(0.05)  # inside the overlap: the first zone's valve is still open
    if action == "reload":
        await hass.config_entries.async_reload(first.entry.entry_id)
    else:
        await first._set_abort(True)
    results = await run
    await hass.async_block_till_done()
    assert hass.states.get(VALVE).state == "off" and hass.states.get(VALVE_B).state == "off"
    assert not a._get_pump_lock().locked()
    assert not any(isinstance(r, BaseException) for r in results), results
    assert not errors, errors


@pytest.mark.asyncio
async def test_the_overlap_seconds_count_toward_the_daily_runtime(hass, fake_valve_services, monkeypatch, tmp_path):
    a, b = await _two_zones(hass, monkeypatch, tmp_path, overlap=10)
    await _run_both(hass, a, b)
    planned = a._routine_plan().calc_runtime_minutes + b._routine_plan().calc_runtime_minutes
    # CompressedTime shrinks the waits to nothing, so the extra here is only the (compressed)
    # overlap wait: it is added on top of the plans (>= planned), never dropped.
    assert a.store.state.today_runtime_minutes + b.store.state.today_runtime_minutes >= planned - 0.01


@pytest.mark.asyncio
async def test_the_next_zone_holds_its_pump_audit_until_the_first_has_closed(hass, fake_valve_services, monkeypatch, tmp_path):
    from custom_components.zoneflow.controller import ZoneFlowController

    a, b = await _two_zones(hass, monkeypatch, tmp_path, overlap=8)
    waits = []
    real_pause = ZoneFlowController._pause

    async def spy(self, seconds):
        waits.append((self.entry.title, seconds))
        return await real_pause(self, seconds)

    monkeypatch.setattr(ZoneFlowController, "_pause", spy)
    await _run_both(hass, a, b)
    overlapping = [title for title, seconds in waits if seconds == 8]
    assert len(overlapping) == 1, waits  # one zone kept its valve open the 8 s
    holders = [title for title, seconds in waits if title != overlapping[0] and 0 < seconds < 8]
    assert holders, waits  # the other held its pump-power audit until then


VALVE_C = "switch.watering3"


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["ACB", "ABC"])
async def test_three_zones_one_pump_never_have_two_valves_open_when_a_meter_is_shared(
    hass, fake_valve_services, monkeypatch, tmp_path, order
):
    await _seed(hass)
    hass.states.async_set(VALVE_C, "off")
    for meter in ("sensor.meter_m", "sensor.meter_n"):
        hass.states.async_set(meter, "0")
    specs = {
        "A": dict(zone_name="Zone A", pump_id="P", flow_meter_entity="sensor.meter_m", csv_path=str(tmp_path / "a.csv")),
        "B": dict(zone_name="Zone B", valve_entity=VALVE_B, pump_id="P", flow_meter_entity="sensor.meter_m", csv_path=str(tmp_path / "b.csv")),
        "C": dict(zone_name="Zone C", valve_entity=VALVE_C, pump_id="P", flow_meter_entity="sensor.meter_n", csv_path=str(tmp_path / "c.csv")),
    }
    entries = {k: make_entry(hass, **specs[k]) for k in order}
    assert await hass.config_entries.async_setup(entries[order[0]].entry_id)
    await hass.async_block_till_done()
    zones = {k: hass.data[DOMAIN][entries[k].entry_id] for k in "ABC"}
    for zone in zones.values():
        zone.numbers["routine_pulse_count"].metric_value = 1
        zone.numbers["valve_overlap_seconds"].metric_value = 5
    CompressedTime(hass, [VALVE, VALVE_B, VALVE_C]).install(monkeypatch)
    events = []

    @callback
    def _record(event):
        if event.data.get("entity_id") in (VALVE, VALVE_B, VALVE_C) and event.data.get("new_state"):
            events.append((event.data["entity_id"], event.data["new_state"].state))

    unsub = hass.bus.async_listen("state_changed", _record)
    try:
        await asyncio.gather(*(z.run_routine_now() for z in zones.values()))
        await hass.async_block_till_done()
    finally:
        unsub()
    open_now, both_a_and_b = set(), False
    for entity, state in events:
        (open_now.add if state == "on" else open_now.discard)(entity)
        if {VALVE, VALVE_B} <= open_now:
            both_a_and_b = True  # A and B share a meter: they must never overlap
    assert not both_a_and_b, events
