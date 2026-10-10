"""Guided calibration (1.7.0): the zone card runs the valve for a while, asks
how much water came out and over what area, and sets the flow rate (and Zone
Flow, for litres) from the answers. The same sum as Configure -> Flow rate:
litres / area / minutes."""
from __future__ import annotations

from typing import Any

from homeassistant.exceptions import ServiceValidationError

from . import units
from .errors import service_error
from .const import DOMAIN, NUMBER_DEFS


_error = service_error


async def calibrate_from_volume(controller: Any, volume: float, area: float, minutes: float) -> float:
    """Set the zone's flow rate from `volume` (litres, or gallons on an
    imperial zone) that came out over `area` (m2, or ft2) in `minutes`.
    Returns the new rate in mm/min."""
    if volume <= 0 or area <= 0 or minutes <= 0:
        raise _error("calibration_out_of_range")
    imperial = controller.imperial
    liters = volume * (units.LITERS_PER_GALLON if imperial else 1.0)
    area_m2 = area * (units.M2_PER_FT2 if imperial else 1.0)
    mm_per_min = liters / area_m2 / minutes
    _name, lo, hi, _step, _unit = NUMBER_DEFS["flow_rate_mm_per_min"]
    number = controller.numbers.get("flow_rate_mm_per_min")
    if number is None:
        raise _error("calibration_unavailable")
    if not lo <= mm_per_min <= hi:
        raise _error("calibration_out_of_range")
    await number.async_set_metric_value(round(mm_per_min, 3))
    # Zone Flow turns valve time into litres for the water-use numbers.
    l_per_min = liters / minutes
    _n, zlo, zhi, _s, _u = NUMBER_DEFS["zone_flow_l_min"]
    zone_flow = controller.numbers.get("zone_flow_l_min")
    if zone_flow is not None and zlo < l_per_min <= zhi:
        await zone_flow.async_set_metric_value(round(l_per_min, 2))
    controller._check_issues()  # the "flow rate not set" repair clears at once
    controller._notify_status()
    return mm_per_min
