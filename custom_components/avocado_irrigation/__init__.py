"""Avocado Irrigation — native port of the confirmed-final HA automation."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN, PLATFORMS
from .controller import AvocadoIrrigationController

SERVICE_RUN_DEEP_SOAK = "run_deep_soak"
SERVICE_RUN_ROUTINE = "run_routine_irrigation"
SERVICE_RESET_LOCK = "reset_lock"
SERVICE_TEST_PULSE = "test_pulse"

TEST_PULSE_SCHEMA = vol.Schema({vol.Optional("seconds", default=10): vol.All(int, vol.Range(min=1, max=120))})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    controller = AvocadoIrrigationController(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = controller
    await controller.async_setup()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _handle_run_deep_soak(call: ServiceCall) -> None:
        await controller.run_deep_soak()

    async def _handle_run_routine(call: ServiceCall) -> None:
        await controller.run_routine_irrigation()

    async def _handle_reset_lock(call: ServiceCall) -> None:
        await controller.reset_lock()

    async def _handle_test_pulse(call: ServiceCall) -> None:
        # Deliberately bypasses every schedule/dry-down/rain gate — this
        # exists ONLY so you can bench-test the valve/pump wiring and the
        # low-pump-power audit path before trusting the 05:00/05:30 schedule
        # unattended. It still respects the abort watchdogs (power loss etc).
        await controller.test_pulse(call.data["seconds"])

    hass.services.async_register(DOMAIN, SERVICE_RUN_DEEP_SOAK, _handle_run_deep_soak)
    hass.services.async_register(DOMAIN, SERVICE_RUN_ROUTINE, _handle_run_routine)
    hass.services.async_register(DOMAIN, SERVICE_RESET_LOCK, _handle_reset_lock)
    hass.services.async_register(DOMAIN, SERVICE_TEST_PULSE, _handle_test_pulse, schema=TEST_PULSE_SCHEMA)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        controller: AvocadoIrrigationController = hass.data[DOMAIN].pop(entry.entry_id)
        await controller.async_unload()
        if not hass.data[DOMAIN]:
            for service in (SERVICE_RUN_DEEP_SOAK, SERVICE_RUN_ROUTINE, SERVICE_RESET_LOCK, SERVICE_TEST_PULSE):
                hass.services.async_remove(DOMAIN, service)
    return unloaded
