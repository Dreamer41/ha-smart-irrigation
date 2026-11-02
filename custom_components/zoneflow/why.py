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
from .const import DEMAND_MODEL_ET, DEMAND_MODEL_FAO56


def _preview(controller: Any):
    """The plan the next routine would make if it ran now."""
    # The zone's own plan (controller._routine_plan): the one place the dose is
    # worked out, so this panel can never show a different amount than the run.
    return controller.routine_target_scale(), controller._routine_plan()


def _crop_factor(controller: Any, add) -> None:
    """The crop factor the zone waters by today and what it comes from (1.8)."""
    hass = controller.hass
    info = controller.kc_info(dt_util.now().date())
    crop = controller.crop_seasons.get(info["crop"]) if info["crop"] else None
    if info["source"] == "fixed":
        if crop is not None:
            add("kc_planting", "kc_needs_planting_date", crop=crop.name)
        add("crop_factor", "crop_factor", kc=f"{info['kc']:.2f}", detail=messages.text(hass, "why.kc_fixed"))
        return
    stage = messages.text(hass, f"why.kc_stage.{info['stage']}")
    detail = messages.text(hass, "why.kc_curve", crop=crop.name if crop else "", stage=stage)
    adjustment = info["climate_adjustment"]
    if abs(adjustment) >= 0.005:
        detail += "; " + messages.text(hass, "why.kc_adjust_up" if adjustment > 0 else "why.kc_adjust_down", adj=f"{abs(adjustment):.2f}")
    if abs(info["exposure_factor"] - 1.0) >= 0.005:
        exposure = messages.text(hass, f"why.kc_exposure_name.{info['exposure']}")
        detail += "; " + messages.text(hass, "why.kc_exposure", pct=f"{info['exposure_factor'] * 100:.0f}", exposure=exposure)
    add("crop_factor", "crop_factor", kc=f"{info['kc']:.2f}", detail=detail)


def _root_zone(controller: Any, add) -> None:
    """What the root zone holds and what that does to the watering (1.8). Nothing while it is off."""
    root_zone = controller.root_zone()
    if root_zone is None:
        return
    imperial = controller.imperial
    use = root_zone.etc_mm_day or 0.0
    add(
        "root_zone", "root_zone", taw=units.depth_text(root_zone.taw_mm, imperial),
        raw=units.depth_text(root_zone.raw_mm, imperial), use=units.depth_text(use, imperial),
    )
    days, tier = controller._routine_interval_days(), controller._tier_interval_days()
    if days < tier:
        add("root_zone_interval", "root_zone_interval", days=days, tier=tier)
    try:
        capped = controller._routine_plan().root_zone_capped_mm
    except Exception:  # noqa: BLE001 - an explanation must never raise
        capped = 0.0
    if capped >= 0.5:
        add(
            "root_zone_capped", "root_zone_capped",
            taw=units.depth_text(root_zone.taw_mm, imperial), capped=units.depth_text(capped, imperial),
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
    method = {DEMAND_MODEL_ET: "et", DEMAND_MODEL_FAO56: "fao56"}.get(model, "temperature")
    add("method", "method", method=messages.text(hass, f"why.method_{method}"))
    if model == DEMAND_MODEL_FAO56 and (latest := controller.fao56_latest_day()) is not None:
        sources = latest.get("sources") or {}
        add(
            "fao56_inputs", "fao56_inputs",
            et0=units.depth_text(float(latest["et0"]), imperial),
            humidity=messages.text(hass, f"why.fao56_source.{sources.get('humidity', 'estimated')}"),
            wind=messages.text(hass, f"why.fao56_source.{sources.get('wind', 'default')}"),
            solar=messages.text(hass, f"why.fao56_source.{sources.get('solar', 'estimated')}"),
        )

    _crop_factor(controller, add)
    _root_zone(controller, add)

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
        rain_7d = units.depth_text(controller.rain_windows().get("7d", 0.0), imperial)
        try:
            gross, used, used_ts = controller.rain_credit_breakdown(plan)
        except Exception:  # noqa: BLE001 - an explanation must never raise
            gross = used = 0.0
            used_ts = None
        if used_ts is not None:
            # Rain counted as a watering already used up part of what fell: say so, so the
            # credit is not read as all the rain of the last days.
            add(
                "rain", "rain_used",
                credit=units.depth_text(plan.eff_rain_mm, imperial), gross=units.depth_text(gross, imperial),
                used=units.depth_text(used, imperial), when=controller._when(used_ts), rain=rain_7d,
            )
        else:
            add("rain", "rain", credit=units.depth_text(plan.eff_rain_mm, imperial), rain=rain_7d)
        add("needed", "needed", needed=units.depth_text(max(plan.needed_mm, 0.0), imperial), minutes=plan.calc_runtime_minutes)

        # What would run now: the pulses, the soak and the longest the valve is open at once.
        try:
            if plan.calc_runtime_minutes <= 0:
                add("preview", "preview_none")
            else:
                times = controller.valve_open_times() or {}
                longest = f"{times.get('longest_minutes', 0):g}"
                if plan.pulse_count <= 1:
                    add("preview", "preview_one", minutes=plan.calc_runtime_minutes, longest=longest)
                else:
                    add(
                        "preview", "preview",
                        minutes=plan.calc_runtime_minutes, pulses=plan.pulse_count,
                        each=f"{plan.pulse_runtime_minutes:.1f}".rstrip("0").rstrip("."),
                        soak=f"{controller.number('routine_pulse_rest_minutes'):g}", longest=longest,
                    )
        except Exception:  # noqa: BLE001 - an explanation must never raise
            pass

    skips = controller.store.state.forecast_routine_skip_count
    if controller.weather_entity and skips:
        add("forecast", "forecast", n=skips)

    moisture = controller.soil_moisture_reading()
    soil = {"dry": "soil_dry", "wet": "soil_wet", "in_range": "soil_ok"}.get(controller.soil_moisture_status() or "")
    if moisture is not None and soil is not None:  # a probe that is offline, stale or implausible is ignored: Check my setup says so
        add("soil", "soil", pct=f"{moisture:.0f}", status=messages.text(hass, f"why.{soil}"))

    items.append({"id": "last", "text": controller.status()["text"]})
    return items
