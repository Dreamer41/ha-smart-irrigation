"""Buttons on phone notifications (1.7.0): "Water 10 min", "Snooze today",
"Fertilized" on the messages where they make sense. They work with the Home
Assistant companion app (the notify.mobile_app_<phone> service takes action
buttons; a phone that is not one gets the plain message as before).

The button a person taps comes back as a `mobile_app_notification_action`
event; its action id says which zone and what to do.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from . import messages
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
PREFIX = "ZONEFLOW"
WATER_MINUTES = 10
LISTENER_KEY = "zoneflow_notification_actions"

# Which message offers which buttons.
ACTIONS_FOR_MESSAGE: dict[str, tuple[str, ...]] = {
    "rain_cancel": ("water", "snooze"),
    "overdue": ("water",),
    "fertilize_due": ("fertilized",),
}


def action_id(entry_id: str, verb: str) -> str:
    return f"{PREFIX}|{entry_id}|{verb}"


def build(hass: HomeAssistant, entry_id: str, verbs: tuple[str, ...]) -> list[dict[str, str]]:
    return [
        {"action": action_id(entry_id, verb), "title": messages.text(hass, f"notify.action.{verb}", minutes=WATER_MINUTES)}
        for verb in verbs
    ]


def legacy_service(hass: HomeAssistant, notify_entity: str | None) -> str | None:
    """The notify.mobile_app_<phone> service that goes with a phone's notify
    entity, or None (any other notify target: no buttons)."""
    if not notify_entity or "." not in notify_entity:
        return None
    name = notify_entity.split(".", 1)[1]
    if name.startswith("mobile_app_") and hass.services.has_service("notify", name):
        return name
    return None


async def _handle(hass: HomeAssistant, event: Event) -> None:
    action = str(event.data.get("action") or "")
    parts = action.split("|")
    if len(parts) != 3 or parts[0] != PREFIX:
        return
    _, entry_id, verb = parts
    controller = hass.data.get(DOMAIN, {}).get(entry_id)
    if controller is None:
        return
    try:
        if verb == "water":
            await controller.water_now(WATER_MINUTES)
        elif verb == "snooze":
            await controller.snooze_today()
        elif verb == "fertilized":
            await controller.fertilized_today()
    except HomeAssistantError as err:
        _LOGGER.warning("%s: the %s button on a phone message did nothing: %s", controller.entry.title, verb, err)


@callback
def async_register(hass: HomeAssistant) -> None:
    """Listen for the buttons, once for all zones."""
    if hass.data.get(LISTENER_KEY) is not None:
        return

    async def listener(event: Event) -> None:
        await _handle(hass, event)

    hass.data[LISTENER_KEY] = hass.bus.async_listen("mobile_app_notification_action", listener)


@callback
def async_unregister(hass: HomeAssistant) -> None:
    unsub: Any = hass.data.pop(LISTENER_KEY, None)
    if unsub is not None:
        unsub()
