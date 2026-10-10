"""The zone card asks for a zone's plants and their histories here."""
from __future__ import annotations

import homeassistant.util.dt as dt_util
import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from . import plant_actions
from .const import DOMAIN
from . import presets, setup_check, why
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


@websocket_api.websocket_command({vol.Required("type"): "zoneflow/check", vol.Required("device_id"): str})
@websocket_api.async_response
async def ws_check(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """The zone's Check my setup list."""
    controller = controller_for_device(hass, msg["device_id"])
    if controller is None:
        connection.send_error(msg["id"], "not_found", "No such ZoneFlow zone")
        return
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
