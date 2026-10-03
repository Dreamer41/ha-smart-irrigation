"""Diagnostics download (Settings → Devices & Services → ZoneFlow → ⋮ →
Download diagnostics): everything needed to understand a bug report --
the zone's settings, its saved state and what it is deciding right now.

The phone notify target and the plant-journal notes are redacted (they
usually carry names or personal text); the rain history is summarised
rather than dumped sample by sample. Works for a zone that isn't loaded
too (settings and entities only).
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration
import homeassistant.util.dt as dt_util

from .const import CONF_NOTIFY_ENTITY, DOMAIN

TO_REDACT = {CONF_NOTIFY_ENTITY}


def _ts(value: float | None) -> str | None:
    return dt_util.utc_from_timestamp(value).isoformat() if value is not None else None


def _entities(hass: HomeAssistant, entry: ConfigEntry) -> list[dict[str, Any]]:
    registry = er.async_get(hass)
    result = []
    for e in er.async_entries_for_config_entry(registry, entry.entry_id):
        current = hass.states.get(e.entity_id)
        value = current.state if current else None
        if e.domain == "text" and value not in (None, "", "unknown", "unavailable"):
            value = "**REDACTED**"  # the plant journal's free-text notes
        result.append(
            {
                "entity_id": e.entity_id,
                "key": e.translation_key,
                "category": e.entity_category.value if e.entity_category else None,
                "disabled": e.disabled_by is not None,
                "hidden": e.hidden_by.value if e.hidden_by else None,
                "state": value,
            }
        )
    return result


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    integration = await async_get_integration(hass, DOMAIN)
    base: dict[str, Any] = {
        "version": str(integration.version),
        "home_assistant": {
            "temperature_unit": hass.config.units.temperature_unit,
            "time_zone": str(hass.config.time_zone),
        },
        "entry": {
            "title": entry.title,
            "state": str(entry.state),
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "entities": _entities(hass, entry),
    }
    controller = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if controller is None:
        return base  # the zone isn't loaded right now
    state = asdict(controller.store.state)
    if state.get("health_notes"):
        state["health_notes"] = "**REDACTED**"
    notify = controller.notify_entity
    if notify and notify in state.get("offline_since", {}):
        state["offline_since"]["**REDACTED**"] = state["offline_since"].pop(notify)
    samples = state.pop("rain_samples", [])
    state["rain_samples_summary"] = {
        "count": len(samples),
        "oldest": _ts(samples[0][0]) if samples else None,
        "newest": _ts(samples[-1][0]) if samples else None,
    }
    for key in [k for k in state if k.endswith("_ts")]:
        if isinstance(state[key], dict):  # per-role times (greenhouse)
            state[key] = {role: _ts(value) for role, value in state[key].items()}
        else:
            state[key] = _ts(state[key])

    temp, temp_source = controller.watering_temp()
    moisture, moisture_problem = controller.soil_moisture_check()
    next_ts, next_source = controller.routine_next_estimate()
    deficit_share, deficit_reason = controller.deficit()
    return {
        **base,
        # What each slider really holds (None = never set, e.g. a fallback
        # temperature with no normal band to seed it from).
        "numbers": {key: getattr(ent, "metric_value", None) for key, ent in sorted(controller.numbers.items())},
        "state": state,
        "decisions_now": {
            "watering_temperature_c": temp,
            "temperature_source": temp_source,
            "soil_moisture_pct": moisture,
            "soil_moisture_problem": moisture_problem,
            "next_routine": _ts(next_ts),
            "next_routine_decided_by": next_source,
            "deficit_share": deficit_share,
            "deficit_reason": deficit_reason,
            "service_run_active": controller.service_active,
            "status": controller.status(),
            "imperial_display": controller.imperial,
        },
    }
