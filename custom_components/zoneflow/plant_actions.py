"""What a person can do with plants (1.7.0): add one, move it to another
zone, make an extra the main plant, remove one, add a note -- and read a
plant's history in words.

The plant in a zone keeps its live settings in the zone's own entities
(plants.py). Moving a plant takes a snapshot of those settings from the zone
it leaves and puts them on the zone it arrives in, so its watering follows it.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import async_update_entity
import homeassistant.util.dt as dt_util

from . import messages
from .const import DOMAIN, NUMBER_DEFAULTS, NUMBER_DEFS, PLANT_CUSTOM, PLANT_PRESETS
from .plants import PLANT_NUMBER_KEYS, PLANT_STATE_KEYS, async_get_book
from .state_store import IrrigationState

NAME_MAX_LENGTH = 40
NOTE_MAX_LENGTH = 255
# What happens to the main plant of a zone when another plant takes its place.
OLD_MAIN_CHOICES = ("extra", "archive", "swap", "keep")


def _error(key: str, **placeholders: Any) -> ServiceValidationError:
    return ServiceValidationError(translation_domain=DOMAIN, translation_key=key, translation_placeholders=placeholders or None)


def _zone(hass: HomeAssistant, zone_id: str | None):
    controller = hass.data.get(DOMAIN, {}).get(zone_id or "")
    if controller is None:
        raise _error("plant_zone_not_available")
    return controller


def _zone_name(hass: HomeAssistant, zone_id: str | None) -> str:
    controller = hass.data.get(DOMAIN, {}).get(zone_id or "")
    return controller.entry.title if controller is not None else ""


def starting_snapshot(kind: str) -> dict[str, Any]:
    """The settings a new plant of this type starts with: the zone defaults,
    with the type's targets, crop factor, growth ramp and deep soak on top."""
    state = IrrigationState()
    snapshot: dict[str, Any] = {key: NUMBER_DEFAULTS[key] for key in PLANT_NUMBER_KEYS if key in NUMBER_DEFAULTS}
    snapshot.update({key: getattr(state, key) for key in PLANT_STATE_KEYS})
    snapshot["growth_ramp_profile"] = "off"
    snapshot["deep_soak_enabled"] = True
    preset = PLANT_PRESETS.get(kind)
    if preset is not None:
        snapshot.update(preset["numbers"])
        snapshot["growth_ramp_profile"] = preset["ramp"]
        snapshot["deep_soak_enabled"] = preset["deep_soak"]
    return snapshot


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


async def _refresh_zone_entities(hass: HomeAssistant, zone) -> None:
    """After settings were put on a zone from outside, its selects, dates and
    switches show them straight away."""
    registry = er.async_get(hass)
    for entry in er.async_entries_for_config_entry(registry, zone.entry.entry_id):
        try:
            await async_update_entity(hass, entry.entity_id)
        except Exception:  # noqa: BLE001 - an entity that is not loaded just shows its value later
            continue


async def _apply(hass: HomeAssistant, zone, snapshot: dict[str, Any]) -> None:
    """Put a plant's settings on the zone, without logging them as edits."""
    await zone.plants.async_apply(snapshot)
    await _refresh_zone_entities(hass, zone)


def _live(zone) -> dict[str, Any]:
    zone.plants.check()
    return zone.plants.values()


# --- the actions -------------------------------------------------------------


async def add_plant(hass: HomeAssistant, zone_id: str, name: str, kind: str | None, old_main: str | None) -> dict[str, Any]:
    """A new plant in the zone. In a zone with no main plant it becomes the
    main one (its type's settings go onto the zone); otherwise it is a record
    only, unless `old_main` says it takes over (see move_plant)."""
    book = await async_get_book(hass)
    zone = _zone(hass, zone_id)
    name = _clean(name, NAME_MAX_LENGTH)
    if not name:
        raise _error("plant_name_required")
    kind = kind if kind in PLANT_PRESETS else PLANT_CUSTOM
    current = book.main(zone_id)
    takes_over = zone.has_valve and (current is None or old_main in ("extra", "archive"))
    if current is not None and old_main in ("extra", "archive"):
        await _retire_main(hass, book, zone, current, old_main, None)
    plant = book.create(name, kind, zone_id, takes_over, "user")
    plant["snapshot"] = starting_snapshot(kind)
    if takes_over:
        await _apply(hass, zone, plant["snapshot"])
    zone._notify_status()
    return plant


async def _retire_main(hass, book, zone, main: dict[str, Any], how: str, elsewhere: dict[str, Any] | None) -> None:
    """The zone's main plant steps aside: kept as a record, or archived."""
    main["snapshot"] = _live(zone)
    main["main"] = False
    if how == "archive":
        main["zone_id"] = None
        main["archived_ts"] = dt_util.utcnow().timestamp()
        book.add_history(main["id"], "archived", zone=zone.entry.title)
    else:
        book.add_history(main["id"], "demoted", zone=zone.entry.title)


async def _promote_next(hass, book, zone) -> None:
    """The zone lost its main plant: the first record left in it takes over."""
    left = book.in_zone(zone.entry.entry_id)
    if not left:
        return
    nxt = left[0]
    nxt["main"] = True
    book.add_history(nxt["id"], "promoted", zone=zone.entry.title)
    await _apply(hass, zone, nxt["snapshot"] or starting_snapshot(nxt.get("type") or PLANT_CUSTOM))


async def set_main(hass: HomeAssistant, plant_id: str) -> None:
    """Make a record in a zone the zone's main plant: its settings go onto the
    zone, the old main plant stays as a record."""
    book = await async_get_book(hass)
    plant = _plant(book, plant_id)
    zone = _zone(hass, plant.get("zone_id"))
    if plant.get("main"):
        return
    if not zone.has_valve:
        raise _error("plant_zone_has_no_valve")
    current = book.main(zone.entry.entry_id)
    if current is not None:
        await _retire_main(hass, book, zone, current, "extra", None)
    plant["main"] = True
    book.add_history(plant["id"], "promoted", zone=zone.entry.title)
    await _apply(hass, zone, plant["snapshot"] or starting_snapshot(plant.get("type") or PLANT_CUSTOM))
    zone._notify_status()


async def move_plant(hass: HomeAssistant, plant_id: str, target_id: str, old_main: str | None) -> None:
    """Move a plant to another zone, with its history. If the zone it arrives
    in already has a main plant, `old_main` says what becomes of that one:
    "extra" (stays as a record), "archive", "swap" (goes to the zone this
    plant leaves), or "keep" (this plant joins as a record only)."""
    book = await async_get_book(hass)
    plant = _plant(book, plant_id)
    source_id = plant.get("zone_id")
    if source_id == target_id:
        raise _error("plant_same_zone")
    target = _zone(hass, target_id)
    source = hass.data.get(DOMAIN, {}).get(source_id or "")
    occupant = book.main(target_id)
    if occupant is not None and old_main not in OLD_MAIN_CHOICES:
        raise _error("plant_old_main_choice", zone=target.entry.title)
    if old_main == "swap" and source is None:
        raise _error("plant_old_main_choice", zone=target.entry.title)

    was_main = bool(plant.get("main"))
    if source is not None and was_main:
        plant["snapshot"] = _live(source)
    source_name = source.entry.title if source is not None else ""
    # Does the arriving plant run the target zone's watering?
    becomes_main = target.has_valve and (occupant is None or old_main != "keep")

    plant["zone_id"] = target_id
    plant["main"] = False
    book.add_history(plant["id"], "moved", **{"from": source_name, "to": target.entry.title})

    swapped_in: dict[str, Any] | None = None
    if occupant is not None and becomes_main:
        if old_main == "swap" and source is not None:
            occupant["snapshot"] = _live(target)
            occupant["zone_id"] = source_id
            occupant["main"] = False
            book.add_history(occupant["id"], "moved", **{"from": target.entry.title, "to": source_name})
            swapped_in = occupant
        else:
            await _retire_main(hass, book, target, occupant, "archive" if old_main == "archive" else "extra", None)

    if becomes_main:
        plant["main"] = True
        book.add_history(plant["id"], "promoted", zone=target.entry.title)
        await _apply(hass, target, plant["snapshot"] or starting_snapshot(plant.get("type") or PLANT_CUSTOM))

    # The zone the plant left: a swapped-in plant takes over if it was the main one, else the next record.
    if source is not None and was_main:
        if swapped_in is not None:
            swapped_in["main"] = True
            book.add_history(swapped_in["id"], "promoted", zone=source.entry.title)
            await _apply(hass, source, swapped_in["snapshot"] or starting_snapshot(swapped_in.get("type") or PLANT_CUSTOM))
        else:
            await _promote_next(hass, book, source)
    for zone in (source, target):
        if zone is not None:
            zone._notify_status()


async def remove_plant(hass: HomeAssistant, plant_id: str) -> None:
    """Take a plant out of its zone. It stays on record (archived) with its
    history. The next record in the zone, if any, becomes the main plant;
    otherwise the zone keeps its current settings with no plant."""
    book = await async_get_book(hass)
    plant = _plant(book, plant_id)
    zone = hass.data.get(DOMAIN, {}).get(plant.get("zone_id") or "")
    was_main = bool(plant.get("main"))
    if zone is not None and was_main:
        plant["snapshot"] = _live(zone)
    plant["zone_id"] = None
    plant["main"] = False
    plant["archived_ts"] = dt_util.utcnow().timestamp()
    book.add_history(plant["id"], "removed", zone=zone.entry.title if zone is not None else "")
    if zone is not None:
        if was_main:
            await _promote_next(hass, book, zone)
        zone._notify_status()


async def add_note(hass: HomeAssistant, plant_id: str, text: str) -> None:
    book = await async_get_book(hass)
    plant = _plant(book, plant_id)
    text = _clean(text, NOTE_MAX_LENGTH)
    if not text:
        raise _error("plant_note_required")
    book.add_history(plant["id"], "note", text=text)


def _plant(book, plant_id: str) -> dict[str, Any]:
    plant = book.plants.get(plant_id)
    if plant is None:
        raise _error("plant_not_found")
    return plant


# --- history in words ----------------------------------------------------------


def _setting_name(hass: HomeAssistant, key: str, zone_id: str | None = None) -> str:
    text = messages.text(hass, f"plants.setting.{key}")
    if text != f"plants.setting.{key}":
        return text
    if key in NUMBER_DEFS:
        # The zone's own slider, named in the user's language.
        zone = hass.data.get(DOMAIN, {}).get(zone_id or "")
        entity_id = er.async_get(hass).async_get_entity_id("number", DOMAIN, f"{zone_id}_{key}") if zone_id else None
        state = hass.states.get(entity_id) if entity_id else None
        name = state.attributes.get("friendly_name") if state is not None else None
        if name and zone is not None and name.startswith(f"{zone.entry.title} "):
            return name[len(zone.entry.title) + 1:]
        return NUMBER_DEFS[key][0]
    return key.replace("_", " ").capitalize()


def _value_text(hass: HomeAssistant, key: str, value: Any) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, bool):
        return messages.text(hass, "plants.on" if value else "plants.off")
    if key.endswith("_ts") and isinstance(value, (int, float)):
        return dt_util.as_local(dt_util.utc_from_timestamp(value)).strftime("%Y-%m-%d")
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def history_text(hass: HomeAssistant, entry: dict[str, Any], zone_id: str | None = None) -> str:
    kind, data = entry.get("kind", ""), entry.get("data") or {}
    if kind == "setting":
        key = data.get("key", "")
        return messages.text(
            hass, "plants.history.setting",
            setting=_setting_name(hass, key, zone_id), old=_value_text(hass, key, data.get("old")), new=_value_text(hass, key, data.get("new")),
        )
    params = {k: v for k, v in data.items() if isinstance(v, (str, int, float))}
    params.setdefault("zone", "")
    params.setdefault("text", "")
    params.setdefault("source", "")
    params["from_zone"] = data.get("from", "")
    params["to_zone"] = data.get("to", "")
    return messages.text(hass, f"plants.history.{kind}", **params)


def history(hass: HomeAssistant, plant: dict[str, Any], limit: int = 100) -> list[dict[str, Any]]:
    """Newest first."""
    events = list(reversed(plant.get("history") or []))[:limit]
    return [
        {
            "ts": datetime.fromtimestamp(e["ts"], tz=dt_util.UTC).isoformat(),
            "kind": e.get("kind"),
            "text": history_text(hass, e, plant.get("zone_id")),
        }
        for e in events
    ]
