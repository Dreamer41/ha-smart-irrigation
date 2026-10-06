"""ZoneFlow — native port of the confirmed-final HA automation."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

import homeassistant.util.dt as dt_util

from . import frontend, issues, summary, units, visibility
from . import greenhouse as greenhouse_module
from .const import CONF_ENTRY_TYPE, CONF_PARENT_ZONE, CONF_USE_WU, CONF_ZONE_TYPE, CROP_INHERITED_KEYS, DOMAIN, ENTRY_TYPE_WU, PLATFORMS, WU_DATA_KEY
from .controller import ZoneFlowController

SERVICE_RUN_DEEP_SOAK = "run_deep_soak"
SERVICE_RUN_ROUTINE = "run_routine_irrigation"
SERVICE_RESET_LOCK = "reset_lock"
SERVICE_TEST_PULSE = "test_pulse"
SERVICE_SNOOZE_TODAY = "snooze_today"
SERVICE_SEND_WEEKLY_SUMMARY = "send_weekly_summary"
SERVICE_ADD_RAIN = "add_rain"

# These five are domain-level services, not entity-platform services, so
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
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Serve the dashboard cards as soon as the integration loads, before any
    zone sets up: Home Assistant shows dashboards while it is still starting,
    and the sooner the cards are there, the fewer pages open without them
    (frontend.py has the rest)."""
    await frontend.async_register(hass)
    return True


TEST_PULSE_SCHEMA = vol.Schema(
    {
        vol.Optional("seconds", default=10): vol.All(int, vol.Range(min=1, max=120)),
        **_ZONE_TARGET_FIELDS,
    }
)


ADD_RAIN_SCHEMA = vol.Schema(
    {
        # In the zone's units: mm, or inches on an imperial zone.
        vol.Required("amount"): vol.All(vol.Coerce(float), vol.Range(min=0.01, max=500)),
        vol.Optional("when"): cv.datetime,
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


def is_wu_entry(entry: ConfigEntry) -> bool:
    """The shared Weather Underground rain entry (wu.py), not a zone."""
    return entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_WU


WU_PLATFORMS = [Platform.SENSOR]


async def _async_setup_wu(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from .wu import WURainSource

    source = WURainSource(hass, entry)
    hass.data[WU_DATA_KEY] = source
    await source.async_setup()
    await hass.config_entries.async_forward_entry_setups(entry, WU_PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    # The zones that use it start reading its rain now (their rain sensors
    # and status).
    for controller in hass.data.get(DOMAIN, {}).values():
        if controller.uses_wu:
            controller.on_wu_rain()
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if is_wu_entry(entry):
        return await _async_setup_wu(hass, entry)
    hass.data.setdefault(DOMAIN, {})
    controller = ZoneFlowController(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = controller
    await controller.async_setup()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Hide what this zone doesn't use (see visibility.py).
    await visibility.async_apply(hass, entry, controller)
    _link_crop_devices(hass)
    # A greenhouse's card lists its crops: tell it about this one.
    if (parent := hass.data[DOMAIN].get(controller.parent_entry_id or "")) is not None:
        parent._notify_status()
    summary.async_setup(hass)
    await frontend.async_register(hass)

    # Register the domain services exactly once, the first time any zone
    # sets up -- not once per zone (see _resolve_controller's docstring for
    # why that was a real bug). async_unload_entry only removes them once
    # the LAST zone unloads, so has_service correctly reflects "at least one
    # zone is currently loaded" the whole time.
    if not hass.services.has_service(DOMAIN, SERVICE_RUN_DEEP_SOAK):

        async def _handle_run_deep_soak(call: ServiceCall) -> None:
            await _resolve_controller(hass, call).run_deep_soak_now()

        async def _handle_run_routine(call: ServiceCall) -> None:
            # manual=True feeds the self-tuning "early" signal, same as the
            # button -- a service call is just as much a deliberate human
            # decision as pressing the button.
            await _resolve_controller(hass, call).run_routine_now()

        async def _handle_reset_lock(call: ServiceCall) -> None:
            await _resolve_controller(hass, call).reset_lock()

        async def _handle_snooze_today(call: ServiceCall) -> None:
            await _resolve_controller(hass, call).snooze_today()

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
        hass.services.async_register(DOMAIN, SERVICE_SNOOZE_TODAY, _handle_snooze_today, schema=ZONE_TARGET_SCHEMA)

        async def _handle_add_rain(call: ServiceCall) -> None:
            controller = _resolve_controller(hass, call)
            amount_mm = units.to_metric("manual_rain_mm", call.data["amount"], controller.imperial)
            when = call.data.get("when")
            when_ts = None
            if when is not None:
                when_ts = dt_util.as_utc(when).timestamp()
            await controller.add_manual_rain(amount_mm, when_ts)

        hass.services.async_register(DOMAIN, SERVICE_ADD_RAIN, _handle_add_rain, schema=ADD_RAIN_SCHEMA)

        async def _handle_send_weekly_summary(call: ServiceCall) -> None:
            # Now, to every phone with a zone that has a weekly summary set --
            # a preview; the weekly counts carry on until the real one.
            if not summary.has_recipients(hass):
                raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_weekly_summary")
            if not await summary.async_send(hass, day=None, reset=False):
                raise HomeAssistantError(translation_domain=DOMAIN, translation_key="summary_send_failed")

        hass.services.async_register(DOMAIN, SERVICE_SEND_WEEKLY_SUMMARY, _handle_send_weekly_summary)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
    # A greenhouse's crops read its sensors: they follow its changes.
    for crop in _crop_entries(hass, entry.entry_id):
        if crop.state is ConfigEntryState.LOADED:
            await hass.config_entries.async_reload(crop.entry_id)


def _crop_entries(hass: HomeAssistant, parent_id: str) -> list[ConfigEntry]:
    return [
        e for e in hass.config_entries.async_entries(DOMAIN)
        if {**e.data, **e.options}.get(CONF_PARENT_ZONE) == parent_id
    ]


@callback
def _link_crop_devices(hass: HomeAssistant) -> None:
    """Settings -> Devices shows each crop "connected via" its greenhouse."""
    registry = dr.async_get(hass)
    for entry in hass.config_entries.async_entries(DOMAIN):
        parent_id = {**entry.data, **entry.options}.get(CONF_PARENT_ZONE)
        device = registry.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
        if device is None:
            continue
        parent = registry.async_get_device(identifiers={(DOMAIN, parent_id)}) if parent_id else None
        wanted = parent.id if parent is not None else None
        if device.via_device_id != wanted:
            registry.async_update_device(device.id, via_device_id=wanted)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if is_wu_entry(entry):
        unloaded = await hass.config_entries.async_unload_platforms(entry, WU_PLATFORMS)
        if unloaded:
            source = hass.data.pop(WU_DATA_KEY, None)
            if source is not None:
                await source.async_unload()
        return unloaded
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and entry.disabled_by is not None:
        issues.async_remove(hass, entry.entry_id)  # a disabled zone has nothing to fix
    if unloaded:
        controller: ZoneFlowController = hass.data[DOMAIN].pop(entry.entry_id)
        await controller.async_unload()
        if not hass.data[DOMAIN]:
            for service in (
                SERVICE_RUN_DEEP_SOAK,
                SERVICE_RUN_ROUTINE,
                SERVICE_RESET_LOCK,
                SERVICE_TEST_PULSE,
                SERVICE_SNOOZE_TODAY,
                SERVICE_SEND_WEEKLY_SUMMARY,
                SERVICE_ADD_RAIN,
            ):
                hass.services.async_remove(DOMAIN, service)
            summary.async_teardown(hass)
    return unloaded


def _release_crops(hass: HomeAssistant, greenhouse: ConfigEntry) -> None:
    """A greenhouse was deleted: its crops keep working on their own, with a
    copy of its inside sensors, and a note in Repairs (until the next
    restart)."""
    source = {**greenhouse.data, **greenhouse.options}
    for crop in _crop_entries(hass, greenhouse.entry_id):
        options = {key: value for key, value in crop.options.items() if key != CONF_PARENT_ZONE}
        for key in CROP_INHERITED_KEYS:
            if source.get(key):
                options[key] = source[key]
        data = {key: value for key, value in crop.data.items() if key != CONF_PARENT_ZONE}
        hass.config_entries.async_update_entry(crop, data=data, options=options)
        ir.async_create_issue(
            hass,
            DOMAIN,
            f"{crop.entry_id}_greenhouse_removed",
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="greenhouse_removed",
            translation_placeholders={"zone": crop.title, "greenhouse": greenhouse.title},
        )


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """A zone was deleted: clear its Repairs issues. The last one also takes
    the dashboard card's loader away (frontend.py)."""
    if is_wu_entry(entry):
        from .wu import ISSUE_NO_DATA

        ir.async_delete_issue(hass, DOMAIN, ISSUE_NO_DATA)
        # The zones that borrowed its rain go back to a plain zone: manual
        # rain is offered again (it stays hidden while "use Weather
        # Underground" is on).
        for zone in hass.config_entries.async_entries(DOMAIN):
            if not is_wu_entry(zone) and zone.options.get(CONF_USE_WU, zone.data.get(CONF_USE_WU)):
                hass.config_entries.async_update_entry(zone, options={**zone.options, CONF_USE_WU: False})
        return
    issues.async_remove(hass, entry.entry_id)
    _release_crops(hass, entry)
    if entry.data.get(CONF_ZONE_TYPE, "outdoor") != "outdoor":
        await greenhouse_module.async_release_devices(hass, entry)
    others = [
        e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id and not is_wu_entry(e)
    ]
    if not others:
        await frontend.async_remove_loader(hass)
