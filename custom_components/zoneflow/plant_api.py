"""The zone card asks for a zone's plants and their histories here."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from . import plant_actions
from .const import DOMAIN
from . import presets, setup_check, why
from .plants import async_get_book


@websocket_api.websocket_command({vol.Required("type"): "zoneflow/why", vol.Required("device_id"): str})
@websocket_api.async_response
async def ws_why(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """The numbers behind the zone's next watering."""
    device = dr.async_get(hass).async_get(msg["device_id"])
    controllers = hass.data.get(DOMAIN, {})
    zone_id = next((e for e in (device.config_entries if device else ()) if e in controllers), None)
    if zone_id is None:
        connection.send_error(msg["id"], "not_found", "No such ZoneFlow zone")
        return
    connection.send_result(msg["id"], {"items": why.explain(controllers[zone_id])})


@websocket_api.websocket_command({vol.Required("type"): "zoneflow/check", vol.Required("device_id"): str})
@websocket_api.async_response
async def ws_check(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """The zone's Check my setup list."""
    device = dr.async_get(hass).async_get(msg["device_id"])
    controllers = hass.data.get(DOMAIN, {})
    zone_id = next((e for e in (device.config_entries if device else ()) if e in controllers), None)
    if zone_id is None:
        connection.send_error(msg["id"], "not_found", "No such ZoneFlow zone")
        return
    items = setup_check.run_checks(controllers[zone_id])
    connection.send_result(msg["id"], {"zone": controllers[zone_id].entry.title, "level": setup_check.summary(items), "items": items})


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
    saved = await presets.async_get_book(hass)
    connection.send_result(
        msg["id"],
        {
            "zone": controllers[zone_id].entry.title,
            "presets": [{"id": p["id"], "name": p["name"]} for p in saved.listing()],
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
