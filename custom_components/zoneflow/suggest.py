"""Likely entities for the setup form (1.7.0): the valve, rain gauge, outdoor
temperature and so on, found by device class and name, ranked, and listed
with their friendly names and current values -- so a person recognises
"Garden rain (3.2 mm)" instead of hunting for an entity id.

Only a clear match is filled in for the person; everything is listed so they
can check it, and nothing is saved before they submit the form.
"""
from __future__ import annotations

import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import messages
from .const import (
    CONF_NOTIFY_ENTITY,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_PUMP_POWER_ENTITY,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_SOIL_MOISTURE_ENTITY,
    CONF_VALVE_ENTITY,
    CONF_WEATHER_ENTITY,
    CONF_FLOW_METER_ENTITY,
    DOMAIN,
)

MAX_PER_ROLE = 4
FILL_SCORE = 3  # a device class and a name that both fit
OFFLINE = ("unavailable", "unknown")

# role -> (config key, domains, device classes that fit, name words that fit, name words that rule out)
ROLES: dict[str, tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {
    "valve": (CONF_VALVE_ENTITY, ("switch", "valve"), (), ("valve", "sprinkler", "irrigation", "garden", "zone", "water", "tap"),
              ("light", "lamp", "fan", "heater", "plug", "tv", "update", "restart", "do not disturb", "auto update")),
    "rain": (CONF_RAIN_COUNTER_ENTITY, ("sensor", "counter"), ("precipitation", "precipitation_intensity"),
             ("rain", "precip", "tipping", "bucket", "sade"), ()),
    "temperature": (CONF_OUTDOOR_TEMP_ENTITY, ("sensor",), ("temperature",),
                    ("outdoor", "outside", "garden", "yard", "exterior", "ulko", "weather station"),
                    ("indoor", "inside", "room", "bedroom", "living", "kitchen", "bath", "fridge", "freezer", "cpu",
                     "battery", "water", "pool", "soil", "boiler", "floor", "sisä")),
    "weather": (CONF_WEATHER_ENTITY, ("weather",), (), (), ()),
    "soil": (CONF_SOIL_MOISTURE_ENTITY, ("sensor",), ("moisture",), ("soil", "moisture", "kosteus", "plant"), ("humidity",)),
    "flow": (CONF_FLOW_METER_ENTITY, ("sensor",), ("water", "volume", "volume_flow_rate"), ("flow", "water meter", "virtaus"), ()),
    "pump": (CONF_PUMP_POWER_ENTITY, ("sensor",), ("power",), ("pump", "pumppu"), ()),
    "notify": (CONF_NOTIFY_ENTITY, ("notify",), (), ("mobile app",), ()),
}


def _words(text: str) -> str:
    return re.sub(r"[_\-.]+", " ", text.lower())


def find(hass: HomeAssistant) -> dict[str, list[dict[str, Any]]]:
    """{role: [{entity_id, name, value, score}]}, best first."""
    registry = er.async_get(hass)
    found: dict[str, list[dict[str, Any]]] = {role: [] for role in ROLES}
    for state in hass.states.async_all():
        domain = state.entity_id.split(".", 1)[0]
        reg = registry.async_get(state.entity_id)
        if reg is not None and (reg.platform == DOMAIN or reg.disabled_by):
            continue  # ZoneFlow's own entities are not inputs to ZoneFlow
        name = state.attributes.get("friendly_name") or state.entity_id
        text = _words(f"{state.entity_id} {name}")
        device_class = state.attributes.get("device_class")
        for role, (_key, domains, classes, good, bad) in ROLES.items():
            if domain not in domains:
                continue
            if any(word in text for word in bad):
                continue
            if classes and device_class and device_class not in classes:
                continue  # a sensor of another kind, whatever its name says
            score = 0
            if device_class and device_class in classes:
                score += 2
            if any(word in text for word in good):
                score += 1
            if role == "weather" or (role == "notify" and "mobile app" in text):
                score = FILL_SCORE  # one weather entity / one phone is nearly always the one
            if role == "valve" and domain == "valve":
                score += 2
            if score == 0:
                continue
            found[role].append(
                {
                    "entity_id": state.entity_id,
                    "name": name,
                    "value": "" if state.state in OFFLINE else f"{state.state} {state.attributes.get('unit_of_measurement', '')}".strip(),
                    "score": score,
                }
            )
    for role in found:
        found[role].sort(key=lambda c: (-c["score"], c["name"].lower()))
        del found[role][MAX_PER_ROLE:]
    return found


def defaults_from(found: dict[str, list[dict[str, Any]]], taken: set[str] | None = None) -> dict[str, str]:
    """Config key -> entity id for each role with exactly one clear match
    (and one that no other zone already uses for that role)."""
    taken = taken or set()
    out: dict[str, str] = {}
    for role, (key, *_rest) in ROLES.items():
        clear = [c for c in found.get(role, []) if c["score"] >= FILL_SCORE and c["entity_id"] not in taken]
        if len(clear) == 1:
            out[key] = clear[0]["entity_id"]
    return out


def describe(hass: HomeAssistant, found: dict[str, list[dict[str, Any]]]) -> str:
    """The list shown under the form: 'Rain gauge: Garden rain (3.2 mm)'..."""
    lines = []
    for role in ROLES:
        names = [f"{c['name']} ({c['value']})" if c["value"] else c["name"] for c in found.get(role, [])]
        if names:
            lines.append(messages.text(hass, "suggest.line", role=messages.text(hass, f"suggest.role.{role}"), names=", ".join(names)))
    if not lines:
        return ""
    return messages.text(hass, "suggest.heading") + "\n" + "\n".join(lines)
