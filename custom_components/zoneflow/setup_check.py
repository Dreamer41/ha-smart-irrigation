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

from . import fao56, messages, units
from .const import NUMBER_DEFAULTS

# Less than this before the plant feels dry: even daily watering may let it dry out (1.8).
ROOT_ZONE_SHALLOW_MM = 3.0
from .issues import FLOW_DEFAULT_TOLERANCE, OFFLINE

LEVEL_ORDER = {"fail": 0, "warn": 1, "info": 2, "ok": 3}
OVERDUE_FACTOR = 3  # routine intervals without a watering


def _state(hass: HomeAssistant, entity_id: str | None):
    return hass.states.get(entity_id) if entity_id else None


def _working(state) -> bool:
    return state is not None and state.state not in OFFLINE


def _root_zone_checks(controller: Any, add) -> None:
    root_zone = controller.root_zone()
    if root_zone is None:
        add("root_zone", "info", "root_zone.off")
        return
    imperial = controller.imperial
    if root_zone.raw_mm < ROOT_ZONE_SHALLOW_MM:
        add("root_zone_shallow", "warn", "root_zone.shallow", raw=units.depth_text(root_zone.raw_mm, imperial))
    flow = controller.number("flow_rate_mm_per_min")
    if root_zone.max_interval_days == 1 and root_zone.etc_mm_day and flow > 0:
        minutes = root_zone.etc_mm_day / flow
        if minutes < controller._routine_min_pulse():
            # A day's dose is stretched to the Minimum Pulse: more than the soil holds, every day.
            add("root_zone_short_dose", "warn", "root_zone.short_dose", minutes=f"{minutes:.1f}",
                minimum=f"{controller._routine_min_pulse()}")
    target = controller.number("deep_soak_target_mm")
    if controller.deep_soak_enabled and target > root_zone.taw_mm:
        add("root_zone_deep_soak", "info", "root_zone.deep_soak",
            taw=units.depth_text(root_zone.taw_mm, imperial), target=units.depth_text(target, imperial))


def run_checks(controller: Any) -> list[dict[str, Any]]:
    hass: HomeAssistant = controller.hass

    def text(path: str, **params: Any) -> str:
        return messages.text(hass, f"check.{path}", **params)

    items: list[dict[str, Any]] = []
    ignored = set(controller.store.state.check_ignored)

    def add(item_id: str, level: str, path: str, action: str | None = None, **params: Any) -> None:
        items.append({
            "id": item_id, "level": level, "text": text(path, **params), "action": action,
            # A warning can be ignored (by an administrator, after a confirmation on the card).
            "ignorable": level == "warn", "ignored": level == "warn" and item_id in ignored,
        })

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
        # A routine watering must fit inside the runtime cap, or it is refused every time
        # (a longer gap between waterings, or a low flow rate, makes each one longer).
        try:
            minutes = controller._routine_plan().calc_runtime_minutes
        except Exception:  # noqa: BLE001 - a check must never raise
            minutes = 0
        cap = controller.number("max_runtime_minutes")
        if minutes > cap:
            add("cap", "warn", "cap.low", minutes=f"{minutes:.0f}", cap=f"{cap:.0f}")
        # The valve's own auto-off timer: a backup in case Home Assistant stops while it is open.
        try:
            times = controller.valve_open_times()
        except Exception:  # noqa: BLE001 - a check must never raise
            times = None
        if times:
            params = dict(
                minutes=f"{times['recommended_timer_minutes']:.0f}", longest=f"{times['longest_minutes']:.0f}",
                timer=f"{times['my_timer_minutes']:.0f}",
            )
            mine = times["my_timer_minutes"]
            if mine <= 0:
                add("backup_timer", "info", "backup_timer", **params)
            elif mine < times["longest_minutes"] + times["open_before_and_after_minutes"]:
                add("backup_timer", "warn", "backup_timer_short", **params)
            else:
                add("backup_timer", "ok", "backup_timer_ok", **params)
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

    # The crop curve (1.8): an annual crop needs a planting date.
    if controller.has_valve and (crop := controller.crop_seasons.get(controller.store.state.kc_crop)) is not None:
        if crop.season == fao56.SEASON_ANNUAL and controller.store.state.planting_date_ts is None:
            add("kc_planting", "info", "kc.planting_date", crop=crop.name)

    # The master valve (1.8): closed for safety, nothing behind it waters until Reset Lock.
    if (master := controller.master_valve_entity) is not None:
        reason = controller.store.state.master_valve_latch
        if reason:
            add("master_valve", "warn", "master_valve.latched", valve=master,
                reason=messages.text(hass, f"notify.master_valve_reason.{reason}", valve=controller.valve_entity or ""))
        elif _state(hass, master) is None or not _working(_state(hass, master)):
            add("master_valve", "warn", "master_valve.fail", valve=master)
        else:
            add("master_valve", "ok", "master_valve.ok", valve=master)
        # The monthly self-test (needs a flow meter or a pump power sensor to tell).
        test_ts, test_ok = controller._master().last_test
        when = dt_util.as_local(dt_util.utc_from_timestamp(test_ts)).strftime("%Y-%m-%d") if test_ts else ""
        if test_ts is not None and test_ok is False:
            add("master_valve_test", "warn", "master_valve.test_failed", valve=master, when=when)
        elif test_ts is not None:
            add("master_valve_test", "ok", "master_valve.test_ok", when=when)
        elif controller.flow_meter_entity or controller.pump_power_entity:
            add("master_valve_test", "info", "master_valve.test_pending")
        else:
            add("master_valve_test", "info", "master_valve.test_none")

    # The root zone (1.8).
    if controller.has_valve:
        _root_zone_checks(controller, add)

    # The last watering.
    if controller.has_valve:
        last = controller.store.state.last_routine_ts
        if last is None:
            add("last", "info", "last.never")
        else:
            days = (dt_util.utcnow().timestamp() - last) / 86400
            interval = controller._routine_interval_days()
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

    items.sort(key=lambda i: (i["ignored"], LEVEL_ORDER[i["level"]]))
    return items


def summary(items: list[dict[str, Any]]) -> str:
    """The worst level among the items that are not ignored."""
    return min(
        (i["level"] for i in items if not i.get("ignored")), key=lambda level: LEVEL_ORDER[level], default="ok"
    )
