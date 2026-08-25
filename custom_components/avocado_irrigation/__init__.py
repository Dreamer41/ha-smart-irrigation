"""Avocado Irrigation Home Assistant integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN

PLATFORMS = ["sensor", "number", "binary_sensor", "button"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a configured irrigation system."""
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "config": dict(entry.data),
        "rain_tips": 0,
        "last_significant_rain": None,
        "last_irrigation": None,
        "last_deep_soak": None,
        "fault_lockout": False,
        "irrigation_in_progress": False,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an irrigation system."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
