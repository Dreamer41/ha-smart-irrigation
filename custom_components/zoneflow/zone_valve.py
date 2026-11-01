"""Opening, closing and reading a zone's valve, whatever kind of entity it is (1.8).

A zone's valve can be a `switch` (on / off) or a `valve` entity (open / closed, and
opening / closing while it moves). This module is the only place in the zone code that
knows the difference; everything else asks "is it open?" and "is it confirmed closed?".

Calls keep the zone's own semantics: blocking service calls with no time limit of their
own, and errors are raised to the caller, exactly as the switch-only code did.
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant, State

OFFLINE = ("unavailable", "unknown")
# A valve entity that is moving (opening or closing) may let water through: it counts as open.
OPEN_STATES = ("on", "open", "opening", "closing")
CLOSED_STATES = ("off", "closed")


def domain_of(entity_id: str) -> str:
    return entity_id.split(".", 1)[0]


def is_open(state: State | None) -> bool:
    """On, open, or moving: water may be running."""
    return state is not None and state.state in OPEN_STATES


def is_closed(state: State | None) -> bool:
    """Reports off / closed. Offline, unknown and moving are not closed."""
    return state is not None and state.state in CLOSED_STATES


def is_offline(state: State | None) -> bool:
    return state is not None and state.state in OFFLINE


async def async_open(hass: HomeAssistant, entity_id: str) -> None:
    if domain_of(entity_id) == "valve":
        await hass.services.async_call("valve", "open_valve", {"entity_id": entity_id}, blocking=True)
    else:
        await hass.services.async_call("switch", "turn_on", {"entity_id": entity_id}, blocking=True)


async def async_close(hass: HomeAssistant, entity_id: str) -> None:
    if domain_of(entity_id) == "valve":
        await hass.services.async_call("valve", "close_valve", {"entity_id": entity_id}, blocking=True)
    else:
        await hass.services.async_call("switch", "turn_off", {"entity_id": entity_id}, blocking=True)
