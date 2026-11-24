"""1.8.2: an OpenSprinkler station's switch only enables or disables the station. ZoneFlow
waters it with opensprinkler.run (for a time) and stops it with opensprinkler.stop, and reads
whether it is open from the station's "Station Running" sensor."""
from __future__ import annotations

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.zoneflow import zone_valve
from custom_components.zoneflow.const import CONF_VALVE_ENTITY, DOMAIN, NUMBER_DEFAULTS

from .test_smoke_setup import PUMP, _seed_source_entities, make_entry

SWITCH = "switch.camellia_station_enabled"
RUNNING = "binary_sensor.camellia_station_running"


@pytest.fixture
async def fake_opensprinkler(hass):
    """A station switch (always on) with its running sensor, and the run / stop services."""
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "switch", "opensprinkler", "ctl_switch_station_enabled_3", suggested_object_id="camellia_station_enabled"
    )
    registry.async_get_or_create(
        "binary_sensor", "opensprinkler", "ctl_binary_sensor_station_running_3",
        suggested_object_id="camellia_station_running",
    )
    hass.states.async_set(SWITCH, "on")
    hass.states.async_set(RUNNING, "off")
    calls: list[tuple[str, dict]] = []

    async def _run(call):
        calls.append(("run", dict(call.data)))
        hass.states.async_set(RUNNING, "on")

    async def _stop(call):
        calls.append(("stop", dict(call.data)))
        hass.states.async_set(RUNNING, "off")

    hass.services.async_register("opensprinkler", "run", _run)
    hass.services.async_register("opensprinkler", "stop", _stop)

    async def _switch_off(call):  # must never be used to water
        calls.append(("switch", dict(call.data)))

    hass.services.async_register("switch", "turn_on", _switch_off)
    hass.services.async_register("switch", "turn_off", _switch_off)
    yield calls


async def _zone(hass):
    await _seed_source_entities(hass)
    hass.states.async_set(PUMP, NUMBER_DEFAULTS["pump_min_watts"] + 50)
    await hass.async_block_till_done()
    entry = make_entry(hass, **{CONF_VALVE_ENTITY: SWITCH})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


@pytest.mark.asyncio
async def test_a_station_is_told_apart_and_read_from_its_running_sensor(hass, fake_opensprinkler):
    assert zone_valve.is_opensprinkler_station(hass, SWITCH)
    assert zone_valve.state_entity(hass, SWITCH) == RUNNING
    hass.states.async_set(RUNNING, "on")
    assert zone_valve.is_open(zone_valve.get_state(hass, SWITCH))  # the switch itself still says "on" when idle


@pytest.mark.asyncio
async def test_other_switches_and_valves_are_left_alone(hass, fake_opensprinkler):
    registry = er.async_get(hass)
    registry.async_get_or_create("switch", "shelly", "abc", suggested_object_id="plain")
    hass.states.async_set("switch.plain", "off")
    assert not zone_valve.is_opensprinkler_station(hass, "switch.plain")
    assert not zone_valve.is_opensprinkler_station(hass, "switch.unregistered")
    assert not zone_valve.is_opensprinkler_station(hass, "valve.garden")
    assert zone_valve.state_entity(hass, "switch.plain") == "switch.plain"
    # The master-valve style switch of the same integration is not a station.
    registry.async_get_or_create("switch", "opensprinkler", "ctl_switch_controller_enabled", suggested_object_id="ctl")
    assert not zone_valve.is_opensprinkler_station(hass, "switch.ctl")


@pytest.mark.asyncio
async def test_a_station_whose_running_sensor_is_missing_falls_back_to_the_switch(hass):
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "switch", "opensprinkler", "ctl_switch_station_enabled_5", suggested_object_id="lonely_station_enabled"
    )
    assert zone_valve.state_entity(hass, "switch.lonely_station_enabled") == "switch.lonely_station_enabled"


@pytest.mark.asyncio
async def test_open_runs_the_station_for_a_time_and_close_stops_it(hass, fake_opensprinkler):
    await zone_valve.async_open(hass, SWITCH, 125.2)
    await zone_valve.async_close(hass, SWITCH)
    assert fake_opensprinkler == [
        ("run", {"entity_id": SWITCH, "run_seconds": 126}),
        ("stop", {"entity_id": SWITCH}),
    ]


@pytest.mark.asyncio
async def test_the_run_time_is_kept_within_what_opensprinkler_accepts(hass, fake_opensprinkler):
    await zone_valve.async_open(hass, SWITCH, 10**7)
    await zone_valve.async_open(hass, SWITCH, 0)
    await zone_valve.async_open(hass, SWITCH)
    assert [c[1]["run_seconds"] for c in fake_opensprinkler] == [64800, 1, 64800]


@pytest.mark.asyncio
async def test_a_pulse_waters_the_station_and_ends_closed(hass, fake_opensprinkler):
    c = await _zone(hass)
    await hass.services.async_call(DOMAIN, "test_pulse", {"seconds": 1}, blocking=True)
    await hass.async_block_till_done()
    kinds = [k for k, _ in fake_opensprinkler]
    assert kinds[0] == "run" and kinds[-1] == "stop" and "switch" not in kinds
    assert 1 <= fake_opensprinkler[0][1]["run_seconds"] <= 64800
    assert hass.states.get(RUNNING).state == "off"
    assert c.store.state.lock_on is False and c.store.state.abort_on is False


@pytest.mark.asyncio
async def test_closed_is_confirmed_from_the_running_sensor_not_the_enabled_switch(hass, fake_opensprinkler):
    c = await _zone(hass)
    hass.states.async_set(RUNNING, "on")
    assert await c._valve_confirmed_closed(SWITCH, seconds=0.5) is False  # the switch says "on" both ways
    hass.states.async_set(RUNNING, "off")
    assert await c._valve_confirmed_closed(SWITCH, seconds=0.5) is True


@pytest.mark.asyncio
async def test_the_stuck_valve_watchdog_stops_a_running_station(hass, fake_opensprinkler):
    c = await _zone(hass)
    hass.states.async_set(RUNNING, "on")

    async def log_event(**kw):
        return None

    c._log_event = log_event
    await c._fire_valve_stuck()
    assert ("stop", {"entity_id": SWITCH}) in fake_opensprinkler
    assert hass.states.get(RUNNING).state == "off"


@pytest.mark.asyncio
async def test_a_station_running_after_power_comes_back_is_stopped(hass, fake_opensprinkler):
    c = await _zone(hass)

    async def log_event(**kw):
        return None

    c._log_event = log_event
    hass.states.async_set(RUNNING, "on")
    await c._on_power_restore(hass.states.get(RUNNING))
    assert hass.states.get(RUNNING).state == "off"


@pytest.mark.asyncio
async def test_a_station_cannot_be_the_master_valve(hass, fake_opensprinkler):
    from custom_components.zoneflow.config_flow import _duplicate_errors
    from custom_components.zoneflow.const import CONF_MASTER_VALVE_ENTITY

    assert _duplicate_errors(hass, {CONF_VALVE_ENTITY: "switch.zone_a", CONF_MASTER_VALVE_ENTITY: SWITCH}) == {
        CONF_MASTER_VALVE_ENTITY: "master_is_opensprinkler"
    }
    assert _duplicate_errors(hass, {CONF_VALVE_ENTITY: SWITCH}) == {}


@pytest.mark.asyncio
async def test_a_disabled_station_is_refused_and_nothing_is_sent(hass, fake_opensprinkler):
    from homeassistant.exceptions import HomeAssistantError

    hass.states.async_set(SWITCH, "off")
    with pytest.raises(HomeAssistantError, match="disabled"):
        await zone_valve.async_open(hass, SWITCH, 60)
    assert fake_opensprinkler == []


@pytest.mark.asyncio
async def test_a_station_that_never_starts_is_reported(hass, fake_opensprinkler, monkeypatch):
    from homeassistant.exceptions import HomeAssistantError

    monkeypatch.setattr(zone_valve, "OS_START_CONFIRM_SECONDS", 1)

    async def _queued(call):  # accepted, but the station does not start
        fake_opensprinkler.append(("run", dict(call.data)))

    hass.services.async_register("opensprinkler", "run", _queued)
    with pytest.raises(HomeAssistantError, match="did not start"):
        await zone_valve.async_open(hass, SWITCH, 60)


@pytest.mark.asyncio
async def test_a_station_without_its_running_sensor_is_refused(hass, fake_opensprinkler):
    from homeassistant.exceptions import HomeAssistantError

    registry = er.async_get(hass)
    registry.async_get_or_create(
        "switch", "opensprinkler", "ctl_switch_station_enabled_7", suggested_object_id="no_sensor_station_enabled"
    )
    hass.states.async_set("switch.no_sensor_station_enabled", "on")
    with pytest.raises(HomeAssistantError, match="Station Running"):
        await zone_valve.async_open(hass, "switch.no_sensor_station_enabled", 60)
    assert fake_opensprinkler == []


@pytest.mark.asyncio
async def test_the_enable_switch_changing_is_not_read_as_the_valve_opening(hass, fake_opensprinkler):
    c = await _zone(hass)
    armed = []
    c._arm_valve_stuck_watchdog = lambda when: armed.append(when)
    hass.states.async_set(SWITCH, "off")
    hass.states.async_set(SWITCH, "on")
    await hass.async_block_till_done()
    assert armed == []
    hass.states.async_set(RUNNING, "on")
    await hass.async_block_till_done()
    assert len(armed) == 1


@pytest.mark.asyncio
async def test_a_saved_master_that_is_a_station_is_ignored(hass, fake_opensprinkler):
    from custom_components.zoneflow.const import CONF_MASTER_VALVE_ENTITY

    registry = er.async_get(hass)
    registry.async_get_or_create(
        "switch", "opensprinkler", "ctl_switch_station_enabled_0", suggested_object_id="master_station_enabled"
    )
    hass.states.async_set("switch.master_station_enabled", "on")
    await _seed_source_entities(hass)
    hass.states.async_set(PUMP, NUMBER_DEFAULTS["pump_min_watts"] + 50)
    entry = make_entry(hass, **{CONF_VALVE_ENTITY: SWITCH, CONF_MASTER_VALVE_ENTITY: "switch.master_station_enabled"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][entry.entry_id].master_valve_entity is None


@pytest.mark.asyncio
async def test_a_disabled_running_sensor_counts_as_missing(hass, fake_opensprinkler):
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers.entity_registry import RegistryEntryDisabler

    registry = er.async_get(hass)
    registry.async_update_entity(RUNNING, disabled_by=RegistryEntryDisabler.USER)
    hass.states.async_remove(RUNNING)
    assert zone_valve.state_entity(hass, SWITCH) == SWITCH
    with pytest.raises(HomeAssistantError, match="Station Running"):
        await zone_valve.async_open(hass, SWITCH, 60)
    assert fake_opensprinkler == []  # nothing was sent, so nothing runs untracked


@pytest.mark.asyncio
async def test_a_station_that_never_starts_counts_no_watering_time(hass, fake_opensprinkler, monkeypatch):
    c = await _zone(hass)
    monkeypatch.setattr(zone_valve, "OS_START_CONFIRM_SECONDS", 1)

    async def _queued(call):
        fake_opensprinkler.append(("run", dict(call.data)))

    hass.services.async_register("opensprinkler", "run", _queued)
    await hass.services.async_call(DOMAIN, "test_pulse", {"seconds": 1}, blocking=True)
    await hass.async_block_till_done()
    assert c.store.state.today_runtime_minutes == 0
