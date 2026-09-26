"""Problems a person should fix, shown in Settings -> System -> Repairs
(Home Assistant's issue registry) as well as in the log:

- the zone's valve has been unavailable for an hour (nothing can water);
- a sensor the zone uses has been offline for three days (the zone carries
  on without it -- README "When a sensor misbehaves" -- but it should be
  looked at);
- the phone notify target no longer exists;
- the emitter flow rate is still the untouched default (the one number
  that must be right; a person whose emitters really are 0.24 mm/min can
  ignore the issue).

Each zone is checked hourly and at startup; an issue disappears by itself
once the problem is gone.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
import homeassistant.util.dt as dt_util

from .const import (
    DOMAIN,
    NUMBER_DEFAULTS,
    REPAIR_NOTIFY_MISSING_SECONDS,
    REPAIR_SENSOR_OFFLINE_SECONDS,
    REPAIR_VALVE_OFFLINE_SECONDS,
)

if TYPE_CHECKING:
    from .controller import ZoneFlowController

LEARN_MORE = "https://github.com/Dreamer41/ha-smart-irrigation#what-each-sensor-adds"
OFFLINE = ("unavailable", "unknown")


SENSOR_ROLES = ("temperature", "rain_gauge", "soil_moisture", "pump_power", "flow_meter", "weather")
ALL_KEYS = ("valve_unavailable", "notify_missing", "flow_rate_default", *(f"sensor_offline_{r}" for r in SENSOR_ROLES))
# Flow rates within this of the default count as "never calibrated" (an
# imperial zone saves its display value, which comes back a hair off).
FLOW_DEFAULT_TOLERANCE = 0.0005


def _issue_id(entry_id: str, key: str) -> str:
    return f"{entry_id}_{key}"


def _offline_for(controller: ZoneFlowController, entity_id: str, *, missing_only: bool = False) -> float | None:
    """Seconds `entity_id` has been offline (missing from Home Assistant,
    or -- unless `missing_only` -- unavailable or unknown), or None while
    it's fine. Measured from when ZoneFlow first found it offline, kept in
    the zone's saved state so a restart doesn't start the count over."""
    now = dt_util.utcnow().timestamp()
    since_map = controller.store.state.offline_since
    state = controller.hass.states.get(entity_id)
    fine = state is not None and (missing_only or state.state not in OFFLINE)
    if fine:
        if since_map.pop(entity_id, None) is not None:
            controller.hass.async_create_task(controller.store.async_save())
        return None
    if entity_id not in since_map:
        since = now
        if state is not None:
            since = min(now, state.last_changed.timestamp())
        since_map[entity_id] = since
        controller.hass.async_create_task(controller.store.async_save())
    return now - since_map[entity_id]


def _set(hass: HomeAssistant, controller: ZoneFlowController, key: str, raised: bool, **kwargs) -> None:
    issue_id = _issue_id(controller.entry.entry_id, key)
    if not raised:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    ir.async_create_issue(hass, DOMAIN, issue_id, is_fixable=False, **kwargs)


def _sensors(controller: ZoneFlowController) -> dict[str, str | None]:
    return {
        "temperature": controller.outdoor_temp_entity,
        "rain_gauge": controller.rain_counter_entity,
        "soil_moisture": controller.soil_moisture_entity,
        "pump_power": controller.pump_power_entity,
        "flow_meter": controller.flow_meter_entity,
        "weather": controller.weather_entity,
    }


def async_check(controller: ZoneFlowController) -> None:
    """Raise or clear this zone's issues."""
    hass = controller.hass
    zone = controller.entry.title

    # A paused zone isn't watering: a valve or sensor switched off for the
    # winter isn't a problem to report.
    paused = controller.paused
    offline = _offline_for(controller, controller.valve_entity) if controller.valve_entity and not paused else None
    _set(
        hass,
        controller,
        "valve_unavailable",
        offline is not None and offline >= REPAIR_VALVE_OFFLINE_SECONDS,
        severity=ir.IssueSeverity.ERROR,
        translation_key="valve_unavailable",
        translation_placeholders={"zone": zone, "entity": controller.valve_entity or ""},
    )

    for role, entity_id in _sensors(controller).items():
        offline = _offline_for(controller, entity_id) if entity_id and not paused else None
        _set(
            hass,
            controller,
            f"sensor_offline_{role}",
            offline is not None and offline >= REPAIR_SENSOR_OFFLINE_SECONDS,
            severity=ir.IssueSeverity.WARNING,
            translation_key="sensor_offline",
            translation_placeholders={"zone": zone, "entity": entity_id or "", "days": f"{(offline or 0) / 86400:.0f}"},
            learn_more_url=LEARN_MORE,
        )

    notify = controller.notify_entity
    # A notify entity has no "unavailable" worth reporting -- only gone.
    missing = _offline_for(controller, notify, missing_only=True) if notify else None
    _set(
        hass,
        controller,
        "notify_missing",
        missing is not None and missing >= REPAIR_NOTIFY_MISSING_SECONDS,
        severity=ir.IssueSeverity.WARNING,
        translation_key="notify_missing",
        translation_placeholders={"zone": zone, "entity": notify or ""},
    )

    flow = controller.numbers.get("flow_rate_mm_per_min")
    value = getattr(flow, "metric_value", None)
    untouched = value is not None and abs(value - NUMBER_DEFAULTS["flow_rate_mm_per_min"]) < FLOW_DEFAULT_TOLERANCE
    _set(
        hass,
        controller,
        "flow_rate_default",
        untouched,
        severity=ir.IssueSeverity.WARNING,
        translation_key="flow_rate_default",
        translation_placeholders={"zone": zone},
        learn_more_url="https://github.com/Dreamer41/ha-smart-irrigation#installation",
    )


def async_prune(controller: ZoneFlowController) -> None:
    """At setup: drop issues (and offline records) for entities the zone
    no longer uses, e.g. a sensor just removed under Configure."""
    hass = controller.hass
    entry_id = controller.entry.entry_id
    in_use = {e for e in (controller.valve_entity, controller.notify_entity, *_sensors(controller).values()) if e}
    for role, entity_id in _sensors(controller).items():
        if not entity_id:
            ir.async_delete_issue(hass, DOMAIN, _issue_id(entry_id, f"sensor_offline_{role}"))
    if not controller.notify_entity:
        ir.async_delete_issue(hass, DOMAIN, _issue_id(entry_id, "notify_missing"))
    state = controller.store.state
    state.offline_since = {k: v for k, v in state.offline_since.items() if k in in_use}


def async_remove(hass: HomeAssistant, entry_id: str) -> None:
    """The zone was deleted or disabled: its issues go with it."""
    for key in ALL_KEYS:
        ir.async_delete_issue(hass, DOMAIN, _issue_id(entry_id, key))
