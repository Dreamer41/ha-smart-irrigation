"""Why? (1.7.0): the numbers behind a zone's next watering, in plain words --
which method and temperature, the weekly target, the rain credit, what it
would water if it ran now, the forecast and the soil.

Nothing here decides anything: it re-reads what the zone's own planning uses.
"""
from __future__ import annotations

from typing import Any

import homeassistant.util.dt as dt_util

from . import calculations as calc
from . import messages, units
from .const import DEMAND_MODEL_ET, ROUTINE_MIN_PULSE_MINUTES


def _preview(controller: Any):
    """The plan the next routine would make if it ran now."""
    state = controller.store.state
    now_ts = dt_util.utcnow().timestamp()
    days_elapsed = int((now_ts - state.last_routine_ts) / 86400) if state.last_routine_ts else 0
    et_weekly = controller.et_weekly_target_mm()
    scale = controller.routine_target_scale()
    return scale, calc.plan_routine_irrigation(
        avg_peak_temp=controller.effective_avg_peak_temp(),
        hot_threshold=controller.number("hot_temp_threshold"),
        cool_threshold=controller.number("cool_temp_threshold"),
        normal_weekly_mm=controller.number("target_weekly_mm") * scale,
        hot_weekly_mm=controller.number("target_weekly_hot_mm") * scale,
        cool_weekly_mm=controller.number("target_weekly_cool_mm") * scale,
        flow_rate=controller.number("flow_rate_mm_per_min"),
        days_elapsed=days_elapsed,
        today_rain_mm=controller.today_rain_mm(),
        rain_day_history_mm=state.rain_day_history_mm,
        rain_eff_low=controller.number("rain_eff_low"),
        rain_eff_mid=controller.number("rain_eff_mid"),
        rain_eff_high=controller.number("rain_eff_high"),
        pulse_count=max(int(round(controller.number("routine_pulse_count"))), 1),
        min_pulse_minutes=int(ROUTINE_MIN_PULSE_MINUTES),
        weekly_target_override_mm=(et_weekly * scale) if et_weekly is not None else None,
        site=controller.site,
        interval_fraction=1.0,
    )


def explain(controller: Any) -> list[dict[str, str]]:
    """[{id, label, text}] for the card's Why? panel."""
    hass = controller.hass
    imperial = controller.imperial
    items: list[dict[str, str]] = []

    def add(item_id: str, path: str, **params: Any) -> None:
        items.append({"id": item_id, "text": messages.text(hass, f"why.{path}", **params)})

    if not controller.has_valve:
        return items

    model = controller.store.state.demand_model
    add("method", "method", method=messages.text(hass, f"why.method_{'et' if model == DEMAND_MODEL_ET else 'temperature'}"))

    temp, source = controller.watering_temp()
    tier = calc.temperature_tier(temp, controller.number("hot_temp_threshold"), controller.number("cool_temp_threshold"))
    if temp is not None:
        add(
            "temperature", "temperature",
            value=units.temp_text(temp, imperial), source=messages.text(hass, f"why.source.{source}"),
            tier=messages.text(hass, f"why.tier.{tier}"),
        )

    try:
        scale, plan = _preview(controller)
    except Exception:  # noqa: BLE001 - an explanation must never raise
        plan = None
        scale = 1.0
    if plan is not None:
        add("target", "target", target=units.depth_text(plan.target_weekly_mm, imperial))
        if abs(scale - 1.0) > 0.005:
            add("scale", "scale", pct=f"{scale * 100:.0f}")
        add(
            "rain", "rain",
            credit=units.depth_text(plan.eff_rain_mm, imperial),
            rain=units.depth_text(controller.rain_windows().get("7d", 0.0), imperial),
        )
        add("needed", "needed", needed=units.depth_text(max(plan.needed_mm, 0.0), imperial), minutes=plan.calc_runtime_minutes)

    skips = controller.store.state.forecast_routine_skip_count
    if controller.weather_entity and skips:
        add("forecast", "forecast", n=skips)

    moisture = controller.soil_moisture_reading()
    if moisture is not None:
        add("soil", "soil", pct=f"{moisture:.0f}", status=messages.text(hass, f"why.soil_{controller.soil_moisture_status() or 'ok'}"))

    items.append({"id": "last", "text": controller.status()["text"]})
    return items
