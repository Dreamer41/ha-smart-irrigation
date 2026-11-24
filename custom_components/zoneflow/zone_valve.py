"""Opening, closing and reading a zone's valve, whatever kind of entity it is (1.8).

A zone's valve can be a `switch` (on / off) or a `valve` entity (open / closed, and
opening / closing while it moves). This module is the only place in the zone code that
knows the difference; everything else asks "is it open?" and "is it confirmed closed?".

Calls keep the zone's own semantics: blocking service calls with no time limit of their
own, and errors are raised to the caller, exactly as the switch-only code did.
"""
from __future__ import annotations

import asyncio
import math

from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

OFFLINE = ("unavailable", "unknown")
# A valve entity that is moving (opening or closing) may let water through: it counts as open.
OPEN_STATES = ("on", "open", "opening", "closing")
CLOSED_STATES = ("off", "closed")


def domain_of(entity_id: str) -> str:
    return entity_id.split(".", 1)[0]


OPENSPRINKLER = "opensprinkler"
_OS_SWITCH_PART = "_switch_station_enabled_"
_OS_RUNNING_PART = "_binary_sensor_station_running_"
OS_MAX_RUN_SECONDS = 64800
OS_START_CONFIRM_SECONDS = 15  # how long a station may take to report that it is running


def is_opensprinkler_station(hass: HomeAssistant, entity_id: str) -> bool:
    """A station of an OpenSprinkler controller (1.8.2). Its switch only enables or disables the
    station: to water, the station is run for a time with the integration's own service."""
    if domain_of(entity_id) != "switch":
        return False
    entry = er.async_get(hass).async_get(entity_id)
    return entry is not None and entry.platform == OPENSPRINKLER and _OS_SWITCH_PART in (entry.unique_id or "")


def state_entity(hass: HomeAssistant, entity_id: str) -> str:
    """The entity that tells whether the valve is open. Normally the valve itself; for an
    OpenSprinkler station its "Station Running" sensor (the switch stays on while idle)."""
    if is_opensprinkler_station(hass, entity_id):
        registry = er.async_get(hass)
        unique_id = registry.async_get(entity_id).unique_id.replace(_OS_SWITCH_PART, _OS_RUNNING_PART)
        running = registry.async_get_entity_id("binary_sensor", OPENSPRINKLER, unique_id)
        if running:
            return running
    return entity_id


def get_state(hass: HomeAssistant, entity_id: str) -> State | None:
    return hass.states.get(state_entity(hass, entity_id))


def is_open(state: State | None) -> bool:
    """On, open, or moving: water may be running."""
    return state is not None and state.state in OPEN_STATES


def is_closed(state: State | None) -> bool:
    """Reports off / closed. Offline, unknown and moving are not closed."""
    return state is not None and state.state in CLOSED_STATES


def is_offline(state: State | None) -> bool:
    return state is not None and state.state in OFFLINE


async def async_open(hass: HomeAssistant, entity_id: str, run_seconds: float | None = None) -> None:
    """Open the valve. `run_seconds` is how long an OpenSprinkler station is run for (it needs a
    time; ZoneFlow closes it sooner when the pulse ends); other valves ignore it."""
    if is_opensprinkler_station(hass, entity_id):
        running = state_entity(hass, entity_id)
        if running == entity_id:
            raise HomeAssistantError(
                f"{entity_id}: its OpenSprinkler 'Station Running' sensor was not found (is it disabled?), "
                "so ZoneFlow could not tell that the station is watering"
            )
        enabled = hass.states.get(entity_id)
        if enabled is not None and enabled.state == "off":
            raise HomeAssistantError(f"{entity_id} is a disabled OpenSprinkler station: turn it on first")
        seconds = int(min(OS_MAX_RUN_SECONDS, max(1, math.ceil(run_seconds or OS_MAX_RUN_SECONDS))))
        await hass.services.async_call(
            OPENSPRINKLER, "run", {"entity_id": entity_id, "run_seconds": seconds}, blocking=True
        )
        # A station that is disabled, or queued behind another one, does not start: say so, rather
        # than time a watering that is not happening.
        for _ in range(int(OS_START_CONFIRM_SECONDS / 0.5)):
            if is_open(hass.states.get(running)):
                return
            await asyncio.sleep(0.5)
        raise HomeAssistantError(f"{entity_id} did not start (another station running, or the controller busy?)")
    elif domain_of(entity_id) == "valve":
        await hass.services.async_call("valve", "open_valve", {"entity_id": entity_id}, blocking=True)
    else:
        await hass.services.async_call("switch", "turn_on", {"entity_id": entity_id}, blocking=True)


async def async_close(hass: HomeAssistant, entity_id: str) -> None:
    if is_opensprinkler_station(hass, entity_id):
        await hass.services.async_call(OPENSPRINKLER, "stop", {"entity_id": entity_id}, blocking=True)
    elif domain_of(entity_id) == "valve":
        await hass.services.async_call("valve", "close_valve", {"entity_id": entity_id}, blocking=True)
    else:
        await hass.services.async_call("switch", "turn_off", {"entity_id": entity_id}, blocking=True)
