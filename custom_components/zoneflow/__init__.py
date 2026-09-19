"""ZoneFlow — native port of the confirmed-final HA automation."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, PLATFORMS
from .controller import ZoneFlowController

SERVICE_RUN_DEEP_SOAK = "run_deep_soak"
SERVICE_RUN_ROUTINE = "run_routine_irrigation"
SERVICE_RESET_LOCK = "reset_lock"
SERVICE_TEST_PULSE = "test_pulse"

# These four are domain-level services, not entity-platform services, so
# Home Assistant's automatic area/device -> entity expansion (the thing
# that makes e.g. light.turn_on with an area_id "just work") does not apply
# here -- we resolve device_id/entity_id -> zone ourselves in
# _resolve_controller. area_id targeting isn't supported yet; device_id or
# entity_id (any entity belonging to the zone's device) both work from the
# UI's target picker.
_ZONE_TARGET_FIELDS = {
    vol.Optional(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
}
ZONE_TARGET_SCHEMA = vol.Schema(_ZONE_TARGET_FIELDS)
TEST_PULSE_SCHEMA = vol.Schema(
    {
        vol.Optional("seconds", default=10): vol.All(int, vol.Range(min=1, max=120)),
        **_ZONE_TARGET_FIELDS,
    }
)


def _resolve_controller(hass: HomeAssistant, call: ServiceCall) -> ZoneFlowController:
    """Resolve which zone's controller a domain-level service call targets.

    Before this existed, every one of these four services was registered
    fresh inside async_setup_entry -- once per zone -- and
    hass.services.async_register silently replaces a same-name registration,
    so with two or more zones loaded, calling e.g. zoneflow.test_pulse
    always ran whichever zone's config entry loaded LAST, regardless of
    intent. The four services are now registered exactly once (see
    async_setup_entry below); this function is what makes a specific call
    land on the right zone.

    With only one ZoneFlow zone configured, no target is required at all --
    the single zone is used automatically, so a single-zone install's
    existing automations/scripts keep working completely unchanged. With
    two or more zones, a target (a ZoneFlow device, or any entity that
    belongs to one) is required; an ambiguous or missing target is a hard,
    clearly-worded error rather than silently guessing -- silently picking
    a zone is exactly the bug this replaces.
    """
    controllers: dict[str, ZoneFlowController] = hass.data.get(DOMAIN, {})
    if len(controllers) == 1:
        return next(iter(controllers.values()))
    if not controllers:
        raise ServiceValidationError("No ZoneFlow zones are set up.")

    device_ids: set[str] = set(call.data.get(ATTR_DEVICE_ID) or [])
    entity_ids: list[str] = call.data.get(ATTR_ENTITY_ID) or []

    if entity_ids:
        ent_reg = er.async_get(hass)
        for entity_id in entity_ids:
            entity_entry = ent_reg.async_get(entity_id)
            if entity_entry and entity_entry.device_id:
                device_ids.add(entity_entry.device_id)

    if not device_ids:
        raise ServiceValidationError(
            "Multiple ZoneFlow zones are configured. Target one zone's device "
            "(or one of its entities, e.g. a number/sensor/button that "
            "belongs to it) when calling this service."
        )

    dev_reg = dr.async_get(hass)
    matched_entry_ids: set[str] = set()
    for device_id in device_ids:
        device = dev_reg.async_get(device_id)
        if device is None:
            continue
        matched_entry_ids.update(entry_id for entry_id in device.config_entries if entry_id in controllers)

    if not matched_entry_ids:
        raise ServiceValidationError("The given target doesn't match any ZoneFlow zone.")
    if len(matched_entry_ids) > 1:
        raise ServiceValidationError("The given target matches more than one ZoneFlow zone -- target exactly one.")

    return controllers[next(iter(matched_entry_ids))]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    controller = ZoneFlowController(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = controller
    await controller.async_setup()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register the domain services exactly once, the first time any zone
    # sets up -- not once per zone (see _resolve_controller's docstring for
    # why that was a real bug). async_unload_entry only removes them once
    # the LAST zone unloads, so has_service correctly reflects "at least one
    # zone is currently loaded" the whole time.
    if not hass.services.has_service(DOMAIN, SERVICE_RUN_DEEP_SOAK):

        async def _handle_run_deep_soak(call: ServiceCall) -> None:
            await _resolve_controller(hass, call).run_deep_soak()

        async def _handle_run_routine(call: ServiceCall) -> None:
            await _resolve_controller(hass, call).run_routine_irrigation()

        async def _handle_reset_lock(call: ServiceCall) -> None:
            await _resolve_controller(hass, call).reset_lock()

        async def _handle_test_pulse(call: ServiceCall) -> None:
            # Deliberately bypasses every schedule/dry-down/rain gate — this
            # exists ONLY so you can bench-test the valve/pump wiring and the
            # low-pump-power audit path before trusting the 05:00/05:30
            # schedule unattended. It still respects the abort watchdogs
            # (power loss etc).
            await _resolve_controller(hass, call).test_pulse(call.data["seconds"])

        hass.services.async_register(DOMAIN, SERVICE_RUN_DEEP_SOAK, _handle_run_deep_soak, schema=ZONE_TARGET_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_RUN_ROUTINE, _handle_run_routine, schema=ZONE_TARGET_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_RESET_LOCK, _handle_reset_lock, schema=ZONE_TARGET_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_TEST_PULSE, _handle_test_pulse, schema=TEST_PULSE_SCHEMA)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        controller: ZoneFlowController = hass.data[DOMAIN].pop(entry.entry_id)
        await controller.async_unload()
        if not hass.data[DOMAIN]:
            for service in (SERVICE_RUN_DEEP_SOAK, SERVICE_RUN_ROUTINE, SERVICE_RESET_LOCK, SERVICE_TEST_PULSE):
                hass.services.async_remove(DOMAIN, service)
    return unloaded
