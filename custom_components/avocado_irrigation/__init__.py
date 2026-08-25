"""Avocado Irrigation Home Assistant integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN
from .controller import IrrigationController
from .rain_manager import RainManager

PLATFORMS = ["sensor", "number", "binary_sensor", "button"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration."""
    hass.data.setdefault(DOMAIN, {})

    async def run_routine(call: ServiceCall) -> None:
        entry_id = call.data.get("entry_id") or next(iter(hass.data[DOMAIN]), None)
        if entry_id:
            await hass.data[DOMAIN][entry_id]["controller"].run_routine(force=True)

    async def run_deep_soak(call: ServiceCall) -> None:
        entry_id = call.data.get("entry_id") or next(iter(hass.data[DOMAIN]), None)
        if entry_id:
            await hass.data[DOMAIN][entry_id]["controller"].run_deep_soak(force=True)

    async def clear_fault(call: ServiceCall) -> None:
        entry_id = call.data.get("entry_id") or next(iter(hass.data[DOMAIN]), None)
        if entry_id:
            await hass.data[DOMAIN][entry_id]["controller"].clear_fault()

    hass.services.async_register(DOMAIN, "run_routine", run_routine)
    hass.services.async_register(DOMAIN, "run_deep_soak", run_deep_soak)
    hass.services.async_register(DOMAIN, "clear_fault", clear_fault)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a configured irrigation system."""
    config = dict(entry.data)
    config.update(entry.options)
    data = {
        "config": config,
        "rain_tips": 0,
        "last_significant_rain": None,
        "last_irrigation": None,
        "last_deep_soak": None,
        "fault_lockout": False,
        "irrigation_in_progress": False,
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = data
    rain = RainManager(hass, entry.entry_id, config["rain_gauge"], float(config.get("rain_mm_per_tip", 0.3)))
    controller = IrrigationController(hass, entry.entry_id, rain)
    data["rain"] = rain
    data["controller"] = controller
    await rain.async_start()
    await controller.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an irrigation system."""
    data = hass.data[DOMAIN].get(entry.entry_id)
    if data:
        await data["controller"].async_stop()
        await data["rain"].async_stop()
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
