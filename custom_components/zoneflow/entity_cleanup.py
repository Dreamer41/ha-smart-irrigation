"""Removing entities a zone no longer has.

Some entities only exist for a zone with a particular sensor (the soil-
moisture reading, status and thresholds only with a probe). When that
sensor is removed from the zone's options, the entities it brought along
would otherwise linger in the registry as "unavailable"; this removes them.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN


def remove_entities(hass: HomeAssistant, entry: ConfigEntry, platform: str, keys: list[str]) -> None:
    """Remove this zone's `platform` entities whose unique_id is
    "<entry_id>_<key>" for each key, if they are registered."""
    registry = er.async_get(hass)
    for key in keys:
        entity_id = registry.async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
        if entity_id is not None:
            registry.async_remove(entity_id)
