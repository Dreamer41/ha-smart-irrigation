"""The zone card asks for a zone's plants and their histories here."""
from __future__ import annotations

import homeassistant.util.dt as dt_util
import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from . import plant_actions
from .const import DOMAIN
from . import plant_water, presets, setup_check, why
from .plants import async_get_book, default_ready_days, planting_ts, stage_of


def controller_for_device(hass: HomeAssistant, device_id: str):
    """The loaded zone that owns a device, or None."""
    device = dr.async_get(hass).async_get(device_id)
    controllers = hass.data.get(DOMAIN, {})
    return next((controllers[e] for e in (device.config_entries if device else ()) if e in controllers), None)


@websocket_api.websocket_command({vol.Required("type"): "zoneflow/why", vol.Required("device_id"): str})
@websocket_api.async_response
async def ws_why(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """The numbers behind the zone's next watering."""
    controller = controller_for_device(hass, msg["device_id"])
    if controller is None:
        connection.send_error(msg["id"], "not_found", "No such ZoneFlow zone")
        return
    connection.send_result(msg["id"], {"items": why.explain(controller)})


@websocket_api.websocket_command({
    vol.Required("type"): "zoneflow/plant_water",
    vol.Required("query"): vol.All(str, vol.Length(max=plant_water.MAX_QUERY_LENGTH)),
})
@websocket_api.async_response
async def ws_plant_water(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """What a plant usually wants per week (a suggestion from the Plant Variety Database)."""
    data = await plant_water.async_get_data(hass)
    results = plant_water.search(data, msg["query"])
    connection.send_result(
        msg["id"],
        {"results": results, "source": data["source"], "kc_sources": plant_water.sources_for(data, results)},
    )


@websocket_api.websocket_command({vol.Required("type"): "zoneflow/check", vol.Required("device_id"): str})
@websocket_api.async_response
async def ws_check(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """The zone's Check my setup list."""
    controller = controller_for_device(hass, msg["device_id"])
    if controller is None:
        connection.send_error(msg["id"], "not_found", "No such ZoneFlow zone")
        return
    items = await _tidy_ignored(controller, setup_check.run_checks(controller))
    connection.send_result(msg["id"], {"zone": controller.entry.title, "level": setup_check.summary(items), "items": items})


async def _tidy_ignored(controller, items: list[dict]) -> list[dict]:
    """A warning that is gone (fixed, or the setting changed) is no longer ignored: if it
    comes back, it is a new warning."""
    state = controller.store.state
    live = {item["id"] for item in items if item["level"] == "warn"}
    kept = [item_id for item_id in state.check_ignored if item_id in live]
    if kept != state.check_ignored:
        state.check_ignored = kept
        await controller.store.async_save()
        controller._check_issues()
    return items


@websocket_api.websocket_command({
    vol.Required("type"): "zoneflow/check_ignore",
    vol.Required("device_id"): str,
    vol.Required("item_id"): str,  # not "id": that is the websocket message id
    vol.Required("ignore"): bool,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_check_ignore(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Ignore a Check my setup warning (or show it again). Administrators only."""
    controller = controller_for_device(hass, msg["device_id"])
    if controller is None:
        connection.send_error(msg["id"], "not_found", "No such ZoneFlow zone")
        return
    items = setup_check.run_checks(controller)
    item = next((i for i in items if i["id"] == msg["item_id"]), None)
    state = controller.store.state
    if msg["ignore"]:
        if item is None or not item["ignorable"]:
            connection.send_error(msg["id"], "not_ignorable", "Only a warning can be ignored")
            return
        if msg["item_id"] not in state.check_ignored:
            state.check_ignored = [*state.check_ignored, msg["item_id"]]
    else:
        state.check_ignored = [i for i in state.check_ignored if i != msg["item_id"]]
    await controller.store.async_save()
    controller._check_issues()
    items = setup_check.run_checks(controller)
    connection.send_result(msg["id"], {"zone": controller.entry.title, "level": setup_check.summary(items), "items": items})


def _ready_fields(plant: dict, controller) -> dict:
    """What the card shows about a nursery plant: its stage and the days the
    type usually takes (the suggestion for a plant that is not followed yet)."""
    planted = planting_ts(plant, controller)
    stage = stage_of(plant, planted)
    out = {
        "ready_days_default": default_ready_days(plant.get("type")),
        "planted": dt_util.as_local(dt_util.utc_from_timestamp(planted)).date().isoformat() if planted else None,
    }
    if stage is not None:
        out.update(ready_days=stage["ready_days"], stage=stage["stage"], days_left=stage["days_left"])
    return out


@websocket_api.websocket_command({vol.Required("type"): "zoneflow/plants", vol.Required("device_id"): str})
@websocket_api.async_response
async def ws_plants(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    controller = controller_for_device(hass, msg["device_id"])
    if controller is None:
        connection.send_error(msg["id"], "not_found", "No such ZoneFlow zone")
        return
    zone_id = controller.entry.entry_id
    book = await async_get_book(hass)
    saved = await presets.async_get_book(hass)
    connection.send_result(
        msg["id"],
        {
            "zone": controller.entry.title,
            "presets": [{"id": p["id"], "name": p["name"]} for p in saved.listing()],
            "plants": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "type": p.get("type"),
                    "main": bool(p.get("main")),
                    "history": plant_actions.history(hass, p),
                    **_ready_fields(p, controller),
                }
                for p in book.in_zone(zone_id)
            ],
        },
    )
