"""Where a zone is (1.7.0): in an area, in a greenhouse (as a crop), or
nowhere in particular. One choice for all three, used by Configure and by the
zone card's "Where is this?" dropdown.

Moving a zone changes where its sensors come from. A zone's own sensor is
never thrown away unless it is the very same as the new place's; a different
one stays as an override, and the card says so.
"""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from . import messages
from .area import AREA_SHARED_KEYS, areas, get_area
from .const import (
    CONF_AREA_ID,
    CONF_AREA_MM_PER_TIP,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_RAIN_SOURCE,
    CONF_PARENT_ZONE,
    CONF_ZONE_TYPE,
    CROP_INHERITED_KEYS,
    DEFAULT_ZONE_TYPE,
    DEVICE_ROLE_KEYS,
    DOMAIN,
    ZONE_TYPE_OUTDOOR,
)

NONE_TOKEN = ""
AREA_PREFIX = "area:"
GREENHOUSE_PREFIX = "gh:"


def _merged(entry: ConfigEntry) -> dict[str, Any]:
    return {**entry.data, **entry.options}


def _is_zone(entry: ConfigEntry) -> bool:
    from . import is_area_entry, is_wu_entry

    return not is_wu_entry(entry) and not is_area_entry(entry)


def greenhouse_entries(hass: HomeAssistant, exclude_entry_id: str | None = None) -> list[ConfigEntry]:
    """Zones a crop can belong to: greenhouse / indoor zones with climate
    devices that aren't crops themselves."""
    found = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        data = _merged(entry)
        if entry.entry_id == exclude_entry_id or not _is_zone(entry) or data.get(CONF_PARENT_ZONE):
            continue
        if data.get(CONF_ZONE_TYPE, DEFAULT_ZONE_TYPE) == ZONE_TYPE_OUTDOOR:
            continue
        if any(data.get(role) for role in DEVICE_ROLE_KEYS):
            found.append(entry)
    return sorted(found, key=lambda e: e.title.casefold())


def area_defaults(controller: Any) -> dict[str, Any]:
    """A new area made from a zone starts with the sensors the zone uses now:
    its own, or the ones it gets from its present area (and, for a rain gauge,
    its tip size). Otherwise moving a zone out of an area would strip it."""
    merged = _merged(controller.entry)
    defaults: dict[str, Any] = {key: controller._area_value(key) for key in AREA_SHARED_KEYS}
    area = controller.area
    from_area = controller.rain_from_area and area is not None
    defaults[CONF_RAIN_SOURCE] = (area.option(CONF_RAIN_SOURCE) if from_area else merged.get(CONF_RAIN_SOURCE))
    if defaults.get(CONF_RAIN_COUNTER_ENTITY):
        defaults[CONF_AREA_MM_PER_TIP] = controller.rain_mm_per_tip
    return defaults


def is_greenhouse_with_devices(entry: ConfigEntry) -> bool:
    data = _merged(entry)
    return data.get(CONF_ZONE_TYPE, DEFAULT_ZONE_TYPE) != ZONE_TYPE_OUTDOOR and any(
        data.get(role) for role in DEVICE_ROLE_KEYS
    )


def has_crops(hass: HomeAssistant, entry_id: str) -> bool:
    return any(
        _merged(e).get(CONF_PARENT_ZONE) == entry_id for e in hass.config_entries.async_entries(DOMAIN)
    )


def choices(hass: HomeAssistant, entry: ConfigEntry) -> list[tuple[str, str]]:
    """(token, label) for each place the zone can be: none, the areas, the
    greenhouses. A greenhouse can only be in an area."""
    out: list[tuple[str, str]] = [(NONE_TOKEN, messages.text(hass, "location.none"))]
    labels = {out[0][1]}

    def unique(label: str) -> str:
        candidate, n = label, 2
        while candidate in labels:
            candidate, n = f"{label} {n}", n + 1
        labels.add(candidate)
        return candidate

    for area in areas(hass):
        out.append((AREA_PREFIX + area.entry.entry_id, unique(area.name)))
    if not is_greenhouse_with_devices(entry):
        suffix = messages.text(hass, "location.greenhouse")
        for gh in greenhouse_entries(hass, exclude_entry_id=entry.entry_id):
            out.append((GREENHOUSE_PREFIX + gh.entry_id, unique(f"{gh.title} ({suffix})")))
    return out


def current_token(entry: ConfigEntry) -> str:
    data = _merged(entry)
    if data.get(CONF_PARENT_ZONE):
        return GREENHOUSE_PREFIX + data[CONF_PARENT_ZONE]
    if data.get(CONF_AREA_ID):
        return AREA_PREFIX + data[CONF_AREA_ID]
    return NONE_TOKEN


def differing_keys(hass: HomeAssistant, entry: ConfigEntry, area_id: str) -> list[str]:
    """The zone's own sensors that are not the area's: kept as overrides
    unless the person says to use the area's."""
    area = get_area(hass, area_id)
    if area is None:
        return []
    merged = _merged(entry)
    return [
        key for key in AREA_SHARED_KEYS
        if merged.get(key) and area.option(key) and merged[key] != area.option(key)
    ]


def apply(
    hass: HomeAssistant,
    entry: ConfigEntry,
    token: str,
    use_area_keys: set[str] | None = None,
) -> dict[str, Any]:
    """The zone's options once it is in `token`'s place (not yet saved).
    `use_area_keys`: differing sensors to replace by the area's."""
    options = {**entry.options}
    merged = _merged(entry)
    old_parent_id = merged.get(CONF_PARENT_ZONE)
    old_area_id = merged.get(CONF_AREA_ID)

    def leave_greenhouse() -> None:
        old = hass.config_entries.async_get_entry(old_parent_id) if old_parent_id else None
        if old is not None:
            source = _merged(old)
            for key in CROP_INHERITED_KEYS:
                if source.get(key):
                    options[key] = source[key]
        options[CONF_PARENT_ZONE] = None

    if token.startswith(GREENHOUSE_PREFIX):
        parent = hass.config_entries.async_get_entry(token[len(GREENHOUSE_PREFIX):])
        if parent is None or parent.entry_id not in {g.entry_id for g in greenhouse_entries(hass, entry.entry_id)}:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="location_not_available")
        if is_greenhouse_with_devices(entry):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="greenhouse_cannot_be_crop")
        options[CONF_PARENT_ZONE] = parent.entry_id
        options[CONF_ZONE_TYPE] = _merged(parent).get(CONF_ZONE_TYPE, DEFAULT_ZONE_TYPE)
        options[CONF_AREA_ID] = None  # a crop is in its greenhouse's area
    elif token.startswith(AREA_PREFIX):
        area = get_area(hass, token[len(AREA_PREFIX):])
        if area is None:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="location_not_available")
        if old_parent_id:
            leave_greenhouse()
        options[CONF_AREA_ID] = area.entry.entry_id
        differing = set(differing_keys(hass, entry, area.entry.entry_id))
        for key in AREA_SHARED_KEYS:
            own, shared = merged.get(key), area.option(key)
            if own and shared and (own == shared or (key in differing and key in (use_area_keys or set()))):
                options[key] = None  # the area's sensor is used from now on
    else:
        if old_parent_id:
            leave_greenhouse()
        old_area = get_area(hass, old_area_id)
        if old_area is not None:
            for key in AREA_SHARED_KEYS:
                if not merged.get(key) and old_area.option(key):
                    options[key] = old_area.option(key)  # keeps what it was getting
        options[CONF_AREA_ID] = None
    return options


async def async_set(hass: HomeAssistant, entry: ConfigEntry, token: str, use_area_keys: set[str] | None = None) -> None:
    options = apply(hass, entry, token, use_area_keys)
    hass.config_entries.async_update_entry(entry, options=options)
