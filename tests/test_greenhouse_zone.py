"""1.6 batch 3: the greenhouse engine driving real device entities.

The pure decisions are in test_greenhouse_logic.py; these check the glue:
nothing switches before the startup grace, devices of several domains are
switched, the outside-air gate, the inside-sensor failsafe, manual hold, the
stuck-mister halt, and that the zone's entities appear and hide correctly.
"""
from __future__ import annotations

import asyncio
import time

import pytest
from homeassistant.core import Context
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.setup import async_setup_component

from custom_components.zoneflow import greenhouse
from custom_components.zoneflow.const import (
    CONF_FAN_ENTITIES,
    CONF_HEATER_ENTITIES,
    CONF_INSIDE_HUMIDITY_ENTITY,
    CONF_INSIDE_TEMP_ENTITY,
    CONF_MISTER_ENTITIES,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_VENT_ENTITIES,
    DOMAIN,
)

from .test_zone_types import (
    FAN, HEATER, INSIDE_HUM, INSIDE_TEMP, MISTER, VENT,
    _climate_only_entry, _reg, _seed, _setup,
)

OUTSIDE = "sensor.gh_outside"


@pytest.fixture
async def devices(hass):
    """Working fake devices: switch on/off and cover open/close flip state."""
    await async_setup_component(hass, "switch", {})
    await async_setup_component(hass, "cover", {})
    calls: list[tuple[str, str, str]] = []

    def _flip(domain, service, state):
        async def _handler(call):
            ids = call.data["entity_id"]
            for entity_id in [ids] if isinstance(ids, str) else ids:
                calls.append((domain, service, entity_id))
                hass.states.async_set(entity_id, state, context=call.context)
                await asyncio.sleep(0)  # like a real device: its state event is handled before the call returns

        hass.services.async_register(domain, service, _handler)

    _flip("switch", "turn_on", "on")
    _flip("switch", "turn_off", "off")
    _flip("cover", "open_cover", "open")
    _flip("cover", "close_cover", "closed")
    return calls


def _entry(hass, **extra):
    data = {
        CONF_INSIDE_TEMP_ENTITY: INSIDE_TEMP,
        CONF_INSIDE_HUMIDITY_ENTITY: INSIDE_HUM,
        CONF_OUTDOOR_TEMP_ENTITY: OUTSIDE,
        CONF_FAN_ENTITIES: [FAN],
        CONF_VENT_ENTITIES: [VENT],
        CONF_MISTER_ENTITIES: [MISTER],
        CONF_HEATER_ENTITIES: [HEATER],
    }
    data.update(extra)
    return _climate_only_entry(hass, **data)


async def _ready(hass, entry):
    hass.states.async_set(OUTSIDE, "15")
    await _seed(hass)
    c = await _setup(hass, entry)
    return c


async def _go(c):
    """Pretend the startup grace has passed, then evaluate."""
    c.greenhouse._started = True
    await c.greenhouse.async_evaluate("test")


@pytest.mark.asyncio
async def test_nothing_switches_before_startup_grace(hass, devices, monkeypatch):
    from custom_components.zoneflow import controller as controller_module

    monkeypatch.setattr(controller_module, "STARTUP_GRACE_SECONDS", 120)  # the real value
    entry = _entry(hass)
    hass.states.async_set(INSIDE_TEMP, "35")
    c = await _ready(hass, entry)
    hass.states.async_set(INSIDE_TEMP, "36")
    await hass.async_block_till_done()
    await c.greenhouse.async_evaluate("test")
    assert not [call for call in devices if call[2] in (FAN, VENT, HEATER, MISTER)]
    assert c.greenhouse._started is False
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_hot_opens_vents_and_runs_fans_when_outside_is_cooler(hass, devices):
    entry = _entry(hass)
    c = await _ready(hass, entry)
    hass.states.async_set(INSIDE_TEMP, "30")
    hass.states.async_set(OUTSIDE, "20")
    await _go(c)
    assert hass.states.get(VENT).state == "open"
    assert hass.states.get(FAN).state == "on"
    assert hass.states.get(HEATER).state == "off"


@pytest.mark.asyncio
async def test_outside_air_gate_blocks_ventilation_when_outside_is_hotter(hass, devices):
    entry = _entry(hass)
    c = await _ready(hass, entry)
    hass.states.async_set(INSIDE_TEMP, "30")
    hass.states.async_set(OUTSIDE, "33")
    await _go(c)
    assert hass.states.get(VENT).state == "closed"
    assert hass.states.get(FAN).state == "off"
    reg = er.async_get(hass)
    allowed = reg.async_get_entity_id("binary_sensor", DOMAIN, f"{entry.entry_id}_ventilation_allowed")
    assert hass.states.get(allowed).state == "off"


@pytest.mark.asyncio
async def test_cold_runs_the_heater(hass, devices):
    entry = _entry(hass)
    c = await _ready(hass, entry)
    hass.states.async_set(INSIDE_TEMP, "5")
    await _go(c)
    assert hass.states.get(HEATER).state == "on"
    assert hass.states.get(FAN).state == "off"


@pytest.mark.asyncio
async def test_control_switch_off_leaves_devices_alone(hass, devices):
    entry = _entry(hass)
    c = await _ready(hass, entry)
    c.store.state.greenhouse_enabled = False
    hass.states.async_set(INSIDE_TEMP, "30")
    await _go(c)
    assert hass.states.get(VENT).state == "closed"
    assert hass.states.get(FAN).state == "off"


@pytest.mark.asyncio
async def test_failsafe_after_grace_follows_the_failsafe_settings(hass, devices):
    entry = _entry(hass)
    c = await _ready(hass, entry)
    hass.states.async_set(HEATER, "on")
    c.store.state.ventilation_failsafe = "open"
    hass.states.async_set(INSIDE_TEMP, "unavailable")
    await _go(c)
    # A brief dropout: heater, vents and fans untouched.
    assert hass.states.get(HEATER).state == "on"
    assert hass.states.get(VENT).state == "closed"
    c.greenhouse._inside_bad_since = time.time() - 300
    await c.greenhouse.async_evaluate("test")
    # Default heater failsafe with an outside sensor: follow outside (15 C, not cold).
    assert hass.states.get(HEATER).state == "off"
    assert hass.states.get(VENT).state == "open"
    assert hass.states.get(FAN).state == "on"
    assert hass.states.get(MISTER).state == "off"


@pytest.mark.asyncio
async def test_failsafe_closed_mode_closes_vents(hass, devices):
    entry = _entry(hass)
    c = await _ready(hass, entry)
    hass.states.async_set(VENT, "open")
    hass.states.async_set(FAN, "on")
    c.store.state.ventilation_failsafe = "closed"
    hass.states.async_set(INSIDE_TEMP, "unavailable")
    c.greenhouse._started = True
    c.greenhouse._inside_bad_since = time.time() - 300
    await c.greenhouse.async_evaluate("test")
    assert hass.states.get(VENT).state == "closed"
    assert hass.states.get(FAN).state == "off"


@pytest.mark.asyncio
async def test_implausible_inside_reading_counts_as_a_failed_sensor(hass, devices):
    entry = _entry(hass)
    c = await _ready(hass, entry)
    hass.states.async_set(INSIDE_TEMP, "-127")  # a typical dead-probe value
    c.greenhouse._started = True
    c.greenhouse._inside_bad_since = time.time() - 300
    await c.greenhouse.async_evaluate("test")
    assert c.greenhouse._decision.failsafe is True
    assert hass.states.get(HEATER).state == "off"


@pytest.mark.asyncio
async def test_manual_switching_is_respected_for_the_hold_time(hass, devices):
    entry = _entry(hass)
    c = await _ready(hass, entry)
    hass.states.async_set(INSIDE_TEMP, "30")
    hass.states.async_set(OUTSIDE, "20")
    await _go(c)
    assert hass.states.get(FAN).state == "on"
    # A person turns the fan off from the dashboard (context carries a user).
    hass.states.async_set(FAN, "off", context=Context(user_id="abc123"))
    await hass.async_block_till_done()
    assert c.greenhouse._held("fans", time.time()) > 0
    await c.greenhouse.async_evaluate("test")
    assert hass.states.get(FAN).state == "off"  # not switched back on
    # Hold over: it takes charge again.
    c.store.state.gh_hold_until["fans"] = 0.0
    c.store.state.gh_changed_ts.pop("fans", None)
    await c.greenhouse.async_evaluate("test")
    assert hass.states.get(FAN).state == "on"


@pytest.mark.asyncio
async def test_own_off_command_long_after_the_on_is_not_a_manual_hold(hass, devices):
    """The device's state event arrives while the switch call is still
    running: a later command must already be recorded then, or it is read as
    a person's (found in the sandbox: the fan was put on hold by ZoneFlow's
    own off command)."""
    entry = _entry(hass)
    c = await _ready(hass, entry)
    hass.states.async_set(INSIDE_TEMP, "30")
    hass.states.async_set(OUTSIDE, "20")
    await _go(c)
    assert hass.states.get(FAN).state == "on"
    # Minutes later: it has cooled down and ZoneFlow switches the fan off.
    c.greenhouse._commanded[FAN] = (True, time.time() - 300)
    c.store.state.gh_changed_ts["fans"] = time.time() - 300
    hass.states.async_set(INSIDE_TEMP, "22")
    await c.greenhouse.async_evaluate("test")
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == "off"
    assert c.greenhouse._held("fans", time.time()) == 0


@pytest.mark.asyncio
async def test_climate_only_zone_has_no_irrigation_flow_rate_warning(hass, devices):
    """No valve, no watering: the "flow rate is still the default" Repairs
    warning (found in the sandbox) does not apply."""
    entry = _entry(hass)
    c = await _ready(hass, entry)
    from custom_components.zoneflow import issues

    issues.async_check(c)
    await hass.async_block_till_done()
    issue_id = f"{entry.entry_id}_flow_rate_default"
    assert ir.async_get(hass).async_get_issue("zoneflow", issue_id) is None


@pytest.mark.asyncio
async def test_a_misting_pulse_runs_and_ends(hass, devices, monkeypatch):
    entry = _entry(hass)
    c = await _ready(hass, entry)
    c.greenhouse._started = True
    # Make it hot and dry enough to mist, and the pulse short.
    hass.states.async_set(INSIDE_TEMP, "33")
    hass.states.async_set(INSIDE_HUM, "30")
    hass.states.async_set(OUTSIDE, "40")  # no ventilation helps; misting does
    c.number = lambda key, _orig=c.number: {"mist_on_seconds": 0.2, "mist_off_seconds": 60.0}.get(key, _orig(key))
    c.greenhouse._grace = lambda: 0
    await c.greenhouse.async_evaluate("test")
    for _ in range(40):
        await hass.async_block_till_done()
        if c.store.state.mist_pulses:
            break
        await __import__("asyncio").sleep(0.1)
    assert c.store.state.mist_pulses, "a pulse should have run"
    assert hass.states.get(MISTER).state == "off"
    await c.greenhouse.async_unload()


@pytest.mark.asyncio
async def test_mister_that_will_not_switch_off_halts_misting_until_reset(hass, monkeypatch):
    monkeypatch.setattr(greenhouse, "VALVE_CLOSE_CONFIRM_SECONDS", 1)
    await async_setup_component(hass, "switch", {})

    async def _ignore(call):  # a broken relay: never turns off
        return None

    hass.services.async_register("switch", "turn_off", _ignore)
    entry = _entry(hass)
    hass.states.async_set(OUTSIDE, "15")
    await _seed(hass)
    hass.states.async_set(MISTER, "on")
    hass.services.async_register("switch", "turn_off", _ignore)
    c = await _setup(hass, entry)
    hass.services.async_register("switch", "turn_off", _ignore)
    c.greenhouse._started = True
    await c.greenhouse._misters_off("test")
    assert c.store.state.mist_halted is True
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_greenhouse_mist_halted")
    assert issue is not None
    hass.states.async_set(MISTER, "off")
    await c.reset_lock()
    await hass.async_block_till_done()
    assert c.store.state.mist_halted is False
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_greenhouse_mist_halted") is None


@pytest.mark.asyncio
async def test_greenhouse_entities_exist_and_follow_the_hardware(hass, devices):
    entry = _entry(hass, **{CONF_MISTER_ENTITIES: [], CONF_HEATER_ENTITIES: []})
    await _ready(hass, entry)
    keys = {(r.domain, r.translation_key): r for r in _reg(hass, entry)}
    assert ("switch", "greenhouse_control") in keys
    assert ("sensor", "greenhouse_status") in keys
    assert keys[("number", "vent_temp")].hidden_by is None
    assert keys[("number", "mist_temp")].hidden_by is not None  # no misters
    assert keys[("number", "heat_temp")].hidden_by is not None  # no heater
    assert keys[("number", "outside_margin")].hidden_by is None  # vents + outside sensor
    assert keys[("number", "target_weekly_mm")].hidden_by is not None  # no valve: no watering


# --- Safety review (Opus) -------------------------------------------------


@pytest.mark.asyncio
async def test_device_back_from_offline_is_not_a_manual_hold(hass, devices):
    entry = _entry(hass)
    c = await _ready(hass, entry)
    hass.states.async_set(INSIDE_TEMP, "30")
    hass.states.async_set(OUTSIDE, "20")
    await _go(c)
    assert hass.states.get(FAN).state == "on"
    c.greenhouse._commanded[FAN] = (True, time.time() - 600)  # long ago
    hass.states.async_set(FAN, "unavailable")
    hass.states.async_set(FAN, "off")  # rebooted, comes back off
    await hass.async_block_till_done()
    assert c.greenhouse._held("fans", time.time()) == 0
    c.store.state.gh_changed_ts.pop("fans", None)
    await c.greenhouse.async_evaluate("test")
    assert hass.states.get(FAN).state == "on"


@pytest.mark.asyncio
async def test_mister_left_on_while_not_misting_is_switched_off(hass, devices):
    entry = _entry(hass)
    c = await _ready(hass, entry)
    hass.states.async_set(INSIDE_TEMP, "22")  # nothing to mist for
    hass.states.async_set(MISTER, "on")  # e.g. an ended manual hold
    await _go(c)
    assert hass.states.get(MISTER).state == "off"


@pytest.mark.asyncio
async def test_hand_switched_mister_hold_is_capped_at_max_misting_per_hour(hass, devices):
    entry = _entry(hass)
    c = await _ready(hass, entry)
    hass.states.async_set(INSIDE_TEMP, "22")
    await _go(c)
    hass.states.async_set(MISTER, "on", context=Context(user_id="abc123"))
    await hass.async_block_till_done()
    left = c.greenhouse._held("misters", time.time())
    assert 0 < left <= c.number("max_mist_minutes_per_hour") * 60
    await c.greenhouse.async_evaluate("test")
    assert hass.states.get(MISTER).state == "on"  # the person's choice, for now
    c.store.state.gh_hold_until["misters"] = 0.0  # hold over
    await c.greenhouse.async_evaluate("test")
    assert hass.states.get(MISTER).state == "off"


@pytest.mark.asyncio
async def test_failsafe_overrides_a_manual_hold_on_heater_and_misters(hass, devices):
    entry = _entry(hass)
    c = await _ready(hass, entry)
    await _go(c)
    hass.states.async_set(HEATER, "on", context=Context(user_id="abc123"))
    hass.states.async_set(MISTER, "on", context=Context(user_id="abc123"))
    await hass.async_block_till_done()
    assert c.greenhouse._held("heater", time.time()) > 0
    hass.states.async_set(INSIDE_TEMP, "unavailable")
    c.greenhouse._inside_bad_since = time.time() - 300
    await c.greenhouse.async_evaluate("test")
    assert hass.states.get(HEATER).state == "off"
    assert hass.states.get(MISTER).state == "off"


@pytest.mark.asyncio
async def test_unload_switches_off_a_heater_zoneflow_turned_on(hass, devices):
    entry = _entry(hass)
    c = await _ready(hass, entry)
    hass.states.async_set(INSIDE_TEMP, "5")
    await _go(c)
    assert hass.states.get(HEATER).state == "on"
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(HEATER).state == "off"


@pytest.mark.asyncio
async def test_unload_leaves_a_heater_a_person_switched_on(hass, devices):
    entry = _entry(hass)
    c = await _ready(hass, entry)
    hass.states.async_set(INSIDE_TEMP, "22")
    await _go(c)
    hass.states.async_set(HEATER, "on", context=Context(user_id="abc123"))
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(HEATER).state == "on"


# --- Heater failsafe and backup sensor ------------------------------------

BACKUP = "sensor.gh_backup_temperature"


@pytest.mark.asyncio
async def test_failsafe_heats_part_time_when_cold_outside(hass, devices):
    entry = _entry(hass)
    c = await _ready(hass, entry)
    await _go(c)
    assert c.greenhouse.heater_failsafe_mode() == "outside"  # default with an outside sensor
    hass.states.async_set(OUTSIDE, "2")
    hass.states.async_set(INSIDE_TEMP, "unavailable")
    c.greenhouse._inside_bad_since = time.time() - 300  # past the grace, first half of the period
    await c.greenhouse.async_evaluate("test")
    assert hass.states.get(HEATER).state == "on"
    c.greenhouse._inside_bad_since = time.time() - 900  # second half: rest
    await c.greenhouse.async_evaluate("test")
    assert hass.states.get(HEATER).state == "off"


@pytest.mark.asyncio
async def test_heater_failsafe_default_is_off_without_outside_sensor(hass, devices):
    entry = _entry(hass, **{CONF_OUTDOOR_TEMP_ENTITY: None})
    c = await _ready(hass, entry)
    assert c.greenhouse.heater_failsafe_mode() == "off"
    reg = er.async_get(hass)
    select = reg.async_get_entity_id("select", DOMAIN, f"{entry.entry_id}_heater_failsafe")
    assert hass.states.get(select).state == "off"


@pytest.mark.asyncio
async def test_failsafe_heat_does_not_override_a_person_holding_the_heater_off(hass, devices):
    entry = _entry(hass)
    c = await _ready(hass, entry)
    c.store.state.heater_failsafe = "limited"
    await _go(c)
    hass.states.async_set(HEATER, "on")
    hass.states.async_set(HEATER, "off", context=Context(user_id="abc123"))
    await hass.async_block_till_done()
    hass.states.async_set(INSIDE_TEMP, "unavailable")
    c.greenhouse._inside_bad_since = time.time() - 300
    await c.greenhouse.async_evaluate("test")
    assert hass.states.get(HEATER).state == "off"


@pytest.mark.asyncio
async def test_backup_sensor_takes_over_and_then_mismatch_is_reported(hass, devices):
    from custom_components.zoneflow.const import CONF_BACKUP_TEMP_ENTITIES

    hass.states.async_set(BACKUP, "5")
    entry = _entry(hass, **{CONF_BACKUP_TEMP_ENTITIES: [BACKUP]})
    c = await _ready(hass, entry)
    hass.states.async_set(INSIDE_TEMP, "unavailable")
    await _go(c)
    # The backup reads cold: normal control, heater on -- no failsafe.
    assert c.greenhouse._decision.failsafe is False
    assert c.greenhouse._inside_source == "backup"
    assert hass.states.get(HEATER).state == "on"
    c.greenhouse._on_backup_since = time.time() - 3600
    await c.greenhouse.async_evaluate("test")
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_greenhouse_on_backup_sensor") is not None
    # Main back, but 15 C apart from the backup for long: one is wrong.
    hass.states.async_set(INSIDE_TEMP, "20")
    await c.greenhouse.async_evaluate("test")
    assert c.greenhouse._inside_source == "primary"
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_greenhouse_on_backup_sensor") is None
    c.greenhouse._mismatch_since = time.time() - 3600
    await c.greenhouse.async_evaluate("test")
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_greenhouse_sensor_mismatch") is not None


@pytest.mark.asyncio
async def test_backup_sensor_checks_in_the_setup_form(hass):
    from custom_components.zoneflow.config_flow import _climate_errors
    from custom_components.zoneflow.const import CONF_BACKUP_TEMP_ENTITIES

    assert _climate_errors(hass, {CONF_BACKUP_TEMP_ENTITIES: [BACKUP]}) == {CONF_INSIDE_TEMP_ENTITY: "inside_temp_required"}
    assert _climate_errors(
        hass, {CONF_INSIDE_TEMP_ENTITY: INSIDE_TEMP, CONF_BACKUP_TEMP_ENTITIES: [INSIDE_TEMP]}
    ) == {CONF_BACKUP_TEMP_ENTITIES: "backup_same_as_inside"}
    assert _climate_errors(hass, {CONF_INSIDE_TEMP_ENTITY: INSIDE_TEMP, CONF_BACKUP_TEMP_ENTITIES: [BACKUP]}) == {}
