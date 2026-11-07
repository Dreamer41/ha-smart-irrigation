"""Litres through a zone's flow meter while its valve is open (1.8): from a running total, or by adding
up a flow rate over time. Pure: the controller feeds it readings, already converted to litres (a total)
or litres per minute (a rate).

What a meter reports is told by its unit: a volume (L, gal, m³, ...; no unit counts as litres, as
before) is a running total; a volume per time (L/min, m³/h, gal/min, ...) is a rate. Anything else
("pulses", "kWh") can't be read as water.
"""
from __future__ import annotations

from collections import deque

from homeassistant.util.unit_conversion import VolumeConverter

METER_TOTAL = "total"
METER_RATE = "rate"

# A rate not reported for this long is not trusted past its last report (it stops counting).
RATE_STALE_SECONDS = 180.0
# A running total that drops by more than this the same run was reset (or rolled over).
TOTAL_RESET_TOLERANCE_L = 0.5
# A running total that rises by more than this in one reading is a broken meter, not water (a zone
# takes litres a minute): the reading is ignored unless the next one stays there (the meter moved).
TOTAL_MAX_JUMP_L = 10000.0
# A total meter's "flow right now": what it counted over the last minute.
RATE_WINDOW_SECONDS = 60.0

_GALLON_L = 3.785411784
_FT3_L = 28.316846592
# Litres per minute in one unit of each rate. Home Assistant knows some of these (and more each year):
# the table is ZoneFlow's own, so a unit means the same on every version.
RATE_UNITS_L_MIN = {
    "L/min": 1.0,
    "L/h": 1 / 60,
    "L/s": 60.0,
    "mL/s": 0.06,
    "mL/min": 0.001,
    "m³/h": 1000 / 60,
    "m³/min": 1000.0,
    "m³/s": 60000.0,
    "gal/min": _GALLON_L,
    "gal/h": _GALLON_L / 60,
    "gal/d": _GALLON_L / 1440,
    "ft³/min": _FT3_L,
}


def meter_kind(unit: str | None) -> str | None:
    """What a meter with this unit reports; None for a unit that is neither a volume nor a rate."""
    if not unit or unit in VolumeConverter.VALID_UNITS:
        return METER_TOTAL
    if unit in RATE_UNITS_L_MIN:
        return METER_RATE
    return None


def to_litres(value: float, unit: str | None) -> float:
    """A total in litres."""
    if not unit or unit == "L":
        return value
    return VolumeConverter.convert(value, unit, "L")


def to_l_min(value: float, unit: str) -> float:
    """A rate in litres per minute."""
    return value * RATE_UNITS_L_MIN[unit]


class FlowTracker:
    """Litres since the tracker started, and the flow right now."""

    def __init__(self, kind: str, value: float | None, ts: float) -> None:
        self.kind = kind
        self._base = 0.0  # total: litres counted before a meter reset
        self._start = value if kind == METER_TOTAL else None
        self._last_value = value
        self._last_ts = ts
        self._spike: float | None = None  # total: an implausible reading waiting for its confirmation
        self._rate_litres = 0.0  # rate: litres added up so far
        self.last_change_ts = ts  # when the count last went up (the no-flow check)
        self.started_ts = ts
        self._recent: deque[tuple[float, float]] = deque()  # total: (ts, litres) of the last minute
        if kind == METER_TOTAL:
            self._recent.append((ts, 0.0))

    def update(self, value: float, ts: float) -> None:
        """A reading: litres (total) or L/min (rate). Called on every state change and every state
        report, so a steady rate keeps counting."""
        if ts < self._last_ts:
            return  # out of order
        if self.kind == METER_TOTAL:
            if self._last_value is not None and self._start is not None and value - self._last_value > TOTAL_MAX_JUMP_L:
                if self._spike is None or abs(value - self._spike) > TOTAL_MAX_JUMP_L:
                    self._spike = value
                    return  # first reading up there: wait to see whether the meter stays
                self._start += value - self._last_value  # it stayed: a new baseline, no litres for the jump
            self._spike = None
            if self._start is None:
                self._start = value
            elif self._last_value is not None and value < self._last_value - TOTAL_RESET_TOLERANCE_L:
                self._base += self._last_value - self._start  # the meter reset or rolled over
                self._start = 0.0
            elif self._last_value is not None and value < self._last_value:
                return  # a small step back is noise: keep the higher reading
            if self._last_value is None or value > self._last_value:
                self.last_change_ts = ts
            self._last_value, self._last_ts = value, ts
            self._recent.append((ts, self.litres(ts)))
            while len(self._recent) > 1 and self._recent[1][0] <= ts - RATE_WINDOW_SECONDS:
                self._recent.popleft()
            return
        self._rate_litres += self._segment(ts)
        if value > 0:
            self.last_change_ts = ts
        self._last_value, self._last_ts = value, ts

    def _segment(self, now: float) -> float:
        if self._last_value is None or self._last_value <= 0:
            return 0.0
        end = min(now, self._last_ts + RATE_STALE_SECONDS)
        return max(end - self._last_ts, 0.0) / 60.0 * self._last_value

    def litres(self, now: float) -> float:
        if self.kind == METER_TOTAL:
            if self._start is None or self._last_value is None:
                return self._base
            return self._base + max(self._last_value - self._start, 0.0)
        return self._rate_litres + self._segment(now)

    def flowing_since(self, now: float) -> float:
        """Seconds since the meter last showed water moving (a rate above 0 counts while it holds)."""
        if self.kind == METER_RATE and self._last_value and self._last_value > 0 and now - self._last_ts <= RATE_STALE_SECONDS:
            return 0.0
        return max(now - self.last_change_ts, 0.0)

    def rate_l_min(self, now: float) -> float | None:
        """The flow right now: the reported rate (while it holds), or what a total counted over the
        last minute. None when there is not yet a minute of totals to tell."""
        if self.kind == METER_RATE:
            if self._last_value is None or now - self._last_ts > RATE_STALE_SECONDS:
                return None
            return max(self._last_value, 0.0)
        if not self._recent:
            return None
        oldest_ts, oldest_l = self._recent[0]
        span = now - oldest_ts
        if span < RATE_WINDOW_SECONDS * 0.5:
            return None
        return max(self.litres(now) - oldest_l, 0.0) / span * 60.0
