"""1.8: a zone's valve can be a `valve` entity (open / closed, opening / closing while it moves),
opened with valve.open_valve and closed with valve.close_valve, next to the `switch` valves it
always took. The safety paths treat a moving valve as open and only "closed" as closed."""
from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.core import State

from custom_components.zoneflow import zone_valve
from custom_components.zoneflow.const import CONF_VALVE_ENTITY, DOMAIN, NUMBER_DEFAULTS, VALVE_DOMAINS

from .test_smoke_setup import PUMP, _seed_source_entities, make_entry

VALVE_ENTITY = "valve.garden_zone"


@pytest.fixture
async def fake_valve_entity_services(hass):
    """valve.open_valve / close_valve that move the fake valve through opening/closing."""
    calls: list[tuple[str, str]] = []

    async def _open(call):
        for entity_id in _ids(call):
            calls.append(("open", entity_id))
            hass.states.async_set(entity_id, "opening")
            hass.states.async_set(entity_id, "open")

    async def _close(call):
        for entity_id in _ids(call):
            calls.append(("close", entity_id))
            hass.states.async_set(entity_id, "closing")
            hass.states.async_set(entity_id, "closed")

    def _ids(call):
        ids = call.data.get("entity_id")
        return [ids] if isinstance(ids, str) else list(ids or [])

    hass.services.async_register("valve", "open_valve", _open)
    hass.services.async_register("valve", "close_valve", _close)
    yield calls


async def _zone(hass, valve=VALVE_ENTITY):
    await _seed_source_entities(hass)
    hass.states.async_set(PUMP, NUMBER_DEFAULTS["pump_min_watts"] + 50)
    hass.states.async_set(valve, "closed")
    await hass.async_block_till_done()
    entry = make_entry(hass, **{CONF_VALVE_ENTITY: valve})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


def _s(value: str) -> State:
    return State(VALVE_ENTITY, value)


def test_states_are_read_the_same_for_switches_and_valve_entities():
    for value in ("on", "open", "opening", "closing"):
        assert zone_valve.is_open(_s(value)) and not zone_valve.is_closed(_s(value)), value
    for value in ("off", "closed"):
        assert zone_valve.is_closed(_s(value)) and not zone_valve.is_open(_s(value)), value
    for value in ("unavailable", "unknown"):
        assert zone_valve.is_offline(_s(value))
        assert not zone_valve.is_open(_s(value)) and not zone_valve.is_closed(_s(value)), value
    assert not zone_valve.is_open(None) and not zone_valve.is_closed(None)
    assert VALVE_DOMAINS == ["switch", "valve"]


@pytest.mark.asyncio
async def test_a_pulse_opens_and_closes_a_valve_entity(hass, fake_valve_entity_services):
    c = await _zone(hass)
    seen: list[str] = []
    unsub = hass.bus.async_listen(
        "state_changed",
        lambda e: seen.append(e.data["new_state"].state) if e.data.get("entity_id") == VALVE_ENTITY else None,
    )
    try:
        await hass.services.async_call(DOMAIN, "test_pulse", {"seconds": 1}, blocking=True)
        await hass.async_block_till_done()
    finally:
        unsub()
    assert [k for k, _ in fake_valve_entity_services][:1] == ["open"] and fake_valve_entity_services[-1][0] == "close"
    assert "open" in seen and hass.states.get(VALVE_ENTITY).state == "closed"
    assert c.store.state.lock_on is False and c.store.state.abort_on is False


@pytest.mark.asyncio
async def test_a_moving_or_offline_valve_entity_is_not_confirmed_closed(hass, fake_valve_entity_services):
    c = await _zone(hass)
    for value, expected in (("closed", True), ("closing", False), ("opening", False), ("open", False), ("unavailable", False)):
        hass.states.async_set(VALVE_ENTITY, value)
        assert await c._valve_confirmed_closed(VALVE_ENTITY, seconds=0.5) is expected, value


@pytest.mark.asyncio
async def test_the_stuck_valve_watchdog_arms_from_when_the_valve_began_to_open(hass, fake_valve_entity_services):
    c = await _zone(hass)
    armed = []
    c._arm_valve_stuck_watchdog = lambda when: armed.append(when)
    hass.states.async_set(VALVE_ENTITY, "opening")
    await hass.async_block_till_done()
    began = hass.states.get(VALVE_ENTITY).last_changed
    hass.states.async_set(VALVE_ENTITY, "open")
    await hass.async_block_till_done()
    assert len(armed) == 2 and armed[0] == began and armed[1] == began  # not moved on to "open"


@pytest.mark.asyncio
async def test_the_stuck_valve_watchdog_closes_a_valve_entity(hass, fake_valve_entity_services):
    c = await _zone(hass)
    hass.states.async_set(VALVE_ENTITY, "open")
    events = []

    async def log_event(**kw):
        events.append(kw["event_type"])

    c._log_event = log_event
    await c._fire_valve_stuck()
    assert ("close", VALVE_ENTITY) in fake_valve_entity_services
    assert hass.states.get(VALVE_ENTITY).state == "closed"
    assert "Valve Stuck Watchdog Fired" in events


@pytest.mark.asyncio
async def test_a_valve_entity_found_open_after_power_comes_back_is_closed(hass, fake_valve_entity_services):
    c = await _zone(hass)
    events = []

    async def log_event(**kw):
        events.append(kw["event_type"])

    c._log_event = log_event
    hass.states.async_set(VALVE_ENTITY, "open")
    await c._on_power_restore(hass.states.get(VALVE_ENTITY))
    assert hass.states.get(VALVE_ENTITY).state == "closed" and "Power Restore Anomaly" in events
    events.clear()
    await c._on_power_restore(State(VALVE_ENTITY, "closed"))
    assert events == []  # back online and closed: safe, nothing to do


@pytest.mark.asyncio
async def test_a_stale_lock_at_startup_closes_an_open_valve_entity(hass, fake_valve_entity_services, monkeypatch):
    from custom_components.zoneflow import controller as controller_module

    c = await _zone(hass)
    monkeypatch.setattr(controller_module, "STARTUP_GRACE_SECONDS", 0)
    c.store.state.lock_on = True
    c.store.state.lock_set_ts = c._setup_ts - 3600  # taken before this start: stale
    c.store.state.lock_valve = VALVE_ENTITY
    hass.states.async_set(VALVE_ENTITY, "open")

    async def log_event(**kw):
        pass

    c._log_event = log_event
    await c._on_startup(None)
    assert hass.states.get(VALVE_ENTITY).state == "closed" and c.store.state.lock_on is False


@pytest.mark.asyncio
async def test_the_setup_valve_test_works_with_a_valve_entity(hass, fake_valve_entity_services, monkeypatch):
    from custom_components.zoneflow import config_flow

    monkeypatch.setattr(config_flow, "VALVE_TEST_HOLD_SECONDS", 0)
    hass.states.async_set(VALVE_ENTITY, "closed")
    text = await config_flow._test_valve(hass, VALVE_ENTITY)
    assert hass.states.get(VALVE_ENTITY).state == "closed"
    assert [k for k, _ in fake_valve_entity_services] == ["open", "close"]
    hass.states.async_set(VALVE_ENTITY, "open")
    fake_valve_entity_services.clear()
    await config_flow._test_valve(hass, VALVE_ENTITY)  # someone is watering by hand: left alone
    assert fake_valve_entity_services == [] and hass.states.get(VALVE_ENTITY).state == "open"
    assert text
