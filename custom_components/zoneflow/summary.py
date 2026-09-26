"""Weekly summary: one phone message per notify target on the chosen
weekday (each zone's "Weekly Summary" select), covering every zone that
sends to that target -- water given, rain, how often a due run was held
back, and what happens next.

One timer for the whole integration (at SUMMARY_HOUR local time); each zone
keeps its own counters since its last summary (IrrigationState.summary_*),
added up by the controller as cycles complete.
"""
from __future__ import annotations

from collections import defaultdict
import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
import homeassistant.util.dt as dt_util

from . import messages, units
from .const import DOMAIN, SUMMARY_DAYS, SUMMARY_HOUR, SUMMARY_OFF

if TYPE_CHECKING:
    from .controller import ZoneFlowController

_LOGGER = logging.getLogger(__name__)
_UNSUB_KEY = "zoneflow_summary_unsub"


def async_setup(hass: HomeAssistant) -> None:
    """Start the weekly timer (once, however many zones there are)."""
    if _UNSUB_KEY in hass.data:
        return

    @callback
    def _tick(now) -> None:
        today = SUMMARY_DAYS[dt_util.as_local(now).weekday()]
        hass.async_create_task(async_send(hass, day=today))

    hass.data[_UNSUB_KEY] = async_track_time_change(hass, _tick, hour=SUMMARY_HOUR, minute=0, second=0)


def async_teardown(hass: HomeAssistant) -> None:
    """Stop the timer (when the last zone unloads)."""
    if (unsub := hass.data.pop(_UNSUB_KEY, None)) is not None:
        unsub()


def zone_line(controller: ZoneFlowController) -> str:
    """One zone's part of the summary."""
    hass = controller.hass
    state = controller.store.state
    imperial = controller.imperial
    if state.summary_runs:
        text = messages.text(
            hass,
            "summary.zone",
            zone=controller.entry.title,
            runs=state.summary_runs,
            water=units.depth_text(state.summary_mm, imperial),
            minutes=f"{state.summary_minutes:.0f}",
        )
    else:
        text = messages.text(hass, "summary.zone_none", zone=controller.entry.title)
    if controller.flow_meter_entity and state.summary_liters > 0:
        text += messages.text(hass, "summary.measured", volume=units.volume_text(state.summary_liters, imperial))
    if controller.rain_counter_entity:
        text += messages.text(hass, "summary.rain", rain=units.depth_text(controller.rain_windows()["7d"], imperial))
    if state.summary_skip_days:
        text += messages.text(hass, "summary.held_back", days=len(state.summary_skip_days))
    status = controller.status()
    if state.paused:
        text += messages.text(hass, "summary.paused")
    elif status["next_watering"] is not None:
        next_ts = dt_util.parse_datetime(status["next_watering"]).timestamp()
        text += messages.text(hass, "summary.next", when=controller._when(next_ts))
    return text


async def async_send(hass: HomeAssistant, *, day: str | None = None, reset: bool = True) -> int:
    """Send the summary for the zones set to `day` (every zone with a
    notify target when None, e.g. from the send_weekly_summary service).
    Returns how many messages were sent."""
    controllers: dict[str, ZoneFlowController] = hass.data.get(DOMAIN, {})
    by_target: dict[str, list[ZoneFlowController]] = defaultdict(list)
    for controller in controllers.values():
        state = controller.store.state
        # Its own opt-in: sent whatever the zone's Notifications setting.
        if not controller.notify_entity:
            continue
        if day is not None and state.summary_day != day:
            continue
        if day is None and state.summary_day == SUMMARY_OFF:
            continue
        by_target[controller.notify_entity].append(controller)

    sent = 0
    for target, zones in by_target.items():
        zones.sort(key=lambda c: c.entry.title.lower())
        message = "\n".join(zone_line(c) for c in zones)
        reported = {c.entry.entry_id: c.summary_snapshot() for c in zones}
        try:
            await hass.services.async_call(
                "notify",
                "send_message",
                {"entity_id": target, "title": messages.text(hass, "summary.title"), "message": message},
                blocking=True,
            )
        except Exception:  # noqa: BLE001 - a notify failure must never break anything else
            _LOGGER.exception("ZoneFlow: weekly summary to %s failed", target)
            continue
        sent += 1
        if reset:
            for entry_id, counts in reported.items():
                # The zone as it is now (it may have reloaded while sending).
                if (current := controllers.get(entry_id)) is not None:
                    await current.reset_summary(counts)
    return sent
