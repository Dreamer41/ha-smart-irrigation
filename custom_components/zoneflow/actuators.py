"""Switching a climate device, whatever kind of Home Assistant entity it is.

A role (fans, vents, misters, heater) takes any number of entities of the
domains in const.DEVICE_ROLE_DOMAINS. This module is the only place that
knows how to turn each domain on or off and how to tell whether it is on:

  switch / input_boolean / fan   turn_on / turn_off
  valve                          open_valve / close_valve
  cover                          open_cover / close_cover, or set_cover_position
                                 when asked for a part-open position it supports
  climate (heater)               set_hvac_mode heat / off

Every call has a time limit: a device that never answers must not stall the
climate engine (or a mister's off command) for ever.
"""
from __future__ import annotations

import asyncio
import logging

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import GREENHOUSE_SERVICE_TIMEOUT_SECONDS

_LOGGER = logging.getLogger(__name__)

OFFLINE = ("unavailable", "unknown")
COVER_SET_POSITION = 4  # CoverEntityFeature.SET_POSITION
# A climate entity counts as a heater that is on only in these modes ("cool"
# or "fan_only", set by a person, is not ZoneFlow's heater running).
CLIMATE_HEAT_MODES = ("heat", "heat_cool", "auto")


def entity_is_on(hass: HomeAssistant, entity_id: str) -> bool | None:
    """True if on / open / heating, False if off / closed, None when the
    entity is missing or offline (then nothing is known about it)."""
    return state_is_on(entity_id, hass.states.get(entity_id))


def state_is_on(entity_id: str, state) -> bool | None:
    """entity_is_on() for a given State (e.g. an event's new_state)."""
    if state is None or state.state in OFFLINE:
        return None
    domain = entity_id.split(".", 1)[0]
    if domain == "cover":
        if state.state in ("open", "opening"):
            return True
        if state.state in ("closed", "closing"):
            return False
        return None
    if domain == "valve":
        return state.state in ("open", "opening")
    if domain == "climate":
        return state.state in CLIMATE_HEAT_MODES
    return state.state == "on"


async def async_set(
    hass: HomeAssistant,
    entity_id: str,
    on: bool,
    *,
    position: float | None = None,
    context: Context | None = None,
) -> None:
    """Turn the entity on/off (open/close). `position` (1-100) is only used
    to open a cover that can be set to a position. Raises HomeAssistantError
    when the device can't do it."""
    domain = entity_id.split(".", 1)[0]
    if domain == "cover":
        state = hass.states.get(entity_id)
        features = int(state.attributes.get("supported_features", 0)) if state else 0
        if on and position is not None and position < 100 and features & COVER_SET_POSITION:
            await _call(hass, "cover", "set_cover_position", entity_id, context, position=int(position))
        else:
            await _call(hass, "cover", "open_cover" if on else "close_cover", entity_id, context)
    elif domain == "valve":
        await _call(hass, "valve", "open_valve" if on else "close_valve", entity_id, context)
    elif domain == "climate":
        await _call(hass, "climate", "set_hvac_mode", entity_id, context, hvac_mode=_hvac_mode(hass, entity_id, on))
    elif domain in ("switch", "input_boolean", "fan"):
        await _call(hass, domain, "turn_on" if on else "turn_off", entity_id, context)
    else:
        raise HomeAssistantError(f"ZoneFlow can't switch a {domain} entity ({entity_id})")


def _hvac_mode(hass: HomeAssistant, entity_id: str, on: bool) -> str:
    if not on:
        return "off"
    state = hass.states.get(entity_id)
    modes = list(state.attributes.get("hvac_modes", [])) if state else []
    for wanted in CLIMATE_HEAT_MODES:
        if wanted in modes:
            return wanted
    return "heat"


async def _call(hass, domain, service, entity_id, context, **data) -> None:
    try:
        async with asyncio.timeout(GREENHOUSE_SERVICE_TIMEOUT_SECONDS):
            await hass.services.async_call(
                domain, service, {"entity_id": entity_id, **data}, blocking=True, context=context
            )
    except TimeoutError as err:
        raise HomeAssistantError(
            f"{entity_id} did not answer {domain}.{service} within {GREENHOUSE_SERVICE_TIMEOUT_SECONDS} s"
        ) from err
