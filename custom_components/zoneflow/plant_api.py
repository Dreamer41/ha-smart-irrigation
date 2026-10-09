"""The zone card asks for a zone's plants and their histories here."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from . import plant_actions
from .const import DOMAIN
from .plants import async_get_book


@websocket_api.websocket_command({vol.Required("type"): "zoneflow/plants", vol.Required("device_id"): str})
@websocket_api.async_response
async def ws_plants(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    device = dr.async_get(hass).async_get(msg["device_id"])
    controllers = hass.data.get(DOMAIN, {})
    zone_id = next((e for e in (device.config_entries if device else ()) if e in controllers), None)
    if zone_id is None:
        connection.send_error(msg["id"], "not_found", "No such ZoneFlow zone")
        return
    book = await async_get_book(hass)
    connection.send_result(
        msg["id"],
        {
            "zone": controllers[zone_id].entry.title,
            "plants": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "type": p.get("type"),
                    "main": bool(p.get("main")),
                    "history": plant_actions.history(hass, p),
                }
                for p in book.in_zone(zone_id)
            ],
        },
    )
