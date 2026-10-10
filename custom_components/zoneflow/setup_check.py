"""Check my setup (1.7.0): a plain checklist for one zone -- is the valve
answering, do the sensors report, is the flow rate set, when did it last
water -- with what to fix when something is wrong.

Each item is {id, level, text, action}: level is ok / info / warn / fail, text
is written in the user's language, action names the card's help for it
("calibrate" opens the flow-rate calibration).
"""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
import homeassistant.util.dt as dt_util

from . import messages
from .const import NUMBER_DEFAULTS
from .issues import FLOW_DEFAULT_TOLERANCE, OFFLINE

LEVEL_ORDER = {"fail": 0, "warn": 1, "info": 2, "ok": 3}
OVERDUE_FACTOR = 3  # routine intervals without a watering


def _state(hass: HomeAssistant, entity_id: str | None):
    return hass.states.get(entity_id) if entity_id else None


def _working(state) -> bool:
    return state is not None and state.state not in OFFLINE


def run_checks(controller: Any) -> list[dict[str, Any]]:
    hass: HomeAssistant = controller.hass

    def text(path: str, **params: Any) -> str:
        return messages.text(hass, f"check.{path}", **params)

    items: list[dict[str, Any]] = []

    def add(item_id: str, level: str, path: str, action: str | None = None, **params: Any) -> None:
        items.append({"id": item_id, "level": level, "text": text(path, **params), "action": action})

    # The valve.
    if controller.has_valve:
        valve = controller.valve_entity
        if _working(_state(hass, valve)):
            add("valve", "ok", "valve.ok", entity=valve)
        else:
            add("valve", "fail", "valve.fail", entity=valve)

    # Rain.
    gauge = controller.rain_counter_entity
    if gauge:
        if _working(_state(hass, gauge)):
            add("rain", "ok", "rain.ok", entity=gauge)
        else:
            add("rain", "fail", "rain.fail", entity=gauge)
    elif controller.uses_wu:
        add("rain", "ok", "rain.wu")
    elif controller.is_outdoor and controller.store.state.manual_rain_used:
        add("rain", "ok", "rain.manual")
    elif controller.is_outdoor:
        add("rain", "info", "rain.none")

    # Temperature.
    if controller.is_outdoor or controller.has_valve:
        sensor = controller.outdoor_temp_entity
        state = _state(hass, sensor)
        if not sensor:
            add("temperature", "warn", "temperature.none")
        elif _working(state):
            add("temperature", "ok", "temperature.ok", value=state.state, unit=state.attributes.get("unit_of_measurement", ""))
        else:
            add("temperature", "warn", "temperature.fail", entity=sensor)

    # The forecast.
    weather = controller.weather_entity
    if controller.is_outdoor:
        if not weather:
            add("weather", "info", "weather.none")
        elif _working(_state(hass, weather)):
            add("weather", "ok", "weather.ok", entity=weather)
        else:
            add("weather", "warn", "weather.fail", entity=weather)

    if controller.has_valve:
        # The flow rate: the one number that must be right.
        flow = controller.number("flow_rate_mm_per_min")
        if abs(flow - NUMBER_DEFAULTS["flow_rate_mm_per_min"]) < FLOW_DEFAULT_TOLERANCE:
            add("flow", "warn", "flow.default", action="calibrate")
        else:
            add("flow", "ok", "flow.ok", value=f"{flow:g}")
        # Litres.
        if controller.has_water_volume:
            add("volume", "ok", "volume.ok")
        else:
            add("volume", "info", "volume.none", action="calibrate")

    # The probe and the pump sensor, if there are any.
    probe = controller.soil_moisture_entity
    if probe:
        state = _state(hass, probe)
        if _working(state):
            add("soil", "ok", "soil.ok", value=state.state)
        else:
            add("soil", "warn", "soil.fail", entity=probe)
    pump = controller.pump_power_entity
    if pump:
        if _working(_state(hass, pump)):
            add("pump", "ok", "pump.ok", entity=pump)
        else:
            add("pump", "warn", "pump.fail", entity=pump)

    # Paused?
    if controller.paused:
        area = controller.area
        by = controller.paused_by()
        if by == "own":
            add("paused", "warn", "paused.zone")
        elif by == "house":
            add("paused", "warn", "paused.house", house=controller.parent_entry.title)
        elif area is not None:
            add("paused", "warn", "paused.area", area=area.name)

    # The last watering.
    if controller.has_valve:
        last = controller.store.state.last_routine_ts
        if last is None:
            add("last", "info", "last.never")
        else:
            days = (dt_util.utcnow().timestamp() - last) / 86400
            from . import calculations as calc

            interval = calc.routine_interval_days(controller.effective_avg_peak_temp(), controller.number("hot_temp_threshold"))
            when = dt_util.as_local(dt_util.utc_from_timestamp(last)).strftime("%Y-%m-%d %H:%M")
            if days > interval * OVERDUE_FACTOR and not controller.paused:
                add("last", "warn", "last.overdue", days=f"{days:.0f}")
            else:
                add("last", "ok", "last.ok", when=when)

    # The phone.
    notify = controller.notify_entity
    if not notify:
        add("notify", "info", "notify.none")
    elif hass.states.get(notify) is None:
        add("notify", "warn", "notify.fail", entity=notify)
    else:
        add("notify", "ok", "notify.ok", entity=notify)

    items.sort(key=lambda i: LEVEL_ORDER[i["level"]])
    return items


def summary(items: list[dict[str, Any]]) -> str:
    """The worst level among the items."""
    return min((i["level"] for i in items), key=lambda level: LEVEL_ORDER[level], default="ok")
