"""One sensor's day, time-weighted (1.8): mean, minimum, maximum and integral of a reading
over a local day, and how much of the day the readings actually cover.

A reading holds until the next one (sensors that only report on change are covered all
day), and stops holding when the sensor goes offline or Home Assistant stops: a sensor that
came back at 22:00 does not make a "daily mean" out of two hours. FAO-56 inputs are only
taken from a day whose coverage reaches MIN_COVERAGE_SECONDS.

Pure: no Home Assistant. Saved in the zone's state as a plain dict.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

MIN_COVERAGE_SECONDS = 18 * 3600


@dataclass
class DayAggregate:
    start_ts: float = 0.0
    last_ts: float | None = None  # when the held reading began to count
    last_value: float | None = None  # the reading that holds now, None while offline
    weighted_sum: float = 0.0  # value x seconds
    covered_seconds: float = 0.0
    positive_seconds: float = 0.0  # of those, the time the reading was above 0 (a solar sensor's daylight)
    minimum: float | None = None
    maximum: float | None = None

    def _hold_until(self, ts: float) -> None:
        if self.last_value is not None and self.last_ts is not None and ts > self.last_ts:
            seconds = ts - max(self.last_ts, self.start_ts)
            if seconds > 0:
                self.weighted_sum += self.last_value * seconds
                self.covered_seconds += seconds
                if self.last_value > 0:
                    self.positive_seconds += seconds
        self.last_ts = ts

    def add(self, ts: float, value: float | None) -> None:
        """A new reading at `ts`, or None when the sensor went offline."""
        if self.last_ts is not None and ts < self.last_ts:
            return  # out of order (clock stepped back): ignored
        self._hold_until(ts)
        self.last_value = value
        if value is not None and ts >= self.start_ts:
            self.minimum = value if self.minimum is None else min(self.minimum, value)
            self.maximum = value if self.maximum is None else max(self.maximum, value)

    def pause(self, ts: float) -> None:
        """Home Assistant stopped (or is starting): the time until the next reading is not covered."""
        self._hold_until(ts)
        self.last_value = None

    def close(self, end_ts: float) -> "DaySummary":
        """The day so far, with the held reading counted up to `end_ts`."""
        self._hold_until(end_ts)
        mean = self.weighted_sum / self.covered_seconds if self.covered_seconds > 0 else None
        return DaySummary(mean, self.minimum, self.maximum, self.weighted_sum, self.covered_seconds, self.positive_seconds)

    def reset(self, start_ts: float) -> None:
        """A new day starts at `start_ts`. The reading that holds carries on into it (it is
        still the sensor's value), and counts again as the new day's minimum and maximum."""
        value = self.last_value
        self.start_ts = start_ts
        self.last_ts = start_ts
        self.weighted_sum = 0.0
        self.covered_seconds = 0.0
        self.positive_seconds = 0.0
        self.minimum = self.maximum = value

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "DayAggregate":
        if not isinstance(data, dict):
            return cls()
        try:
            known = {k: (None if data[k] is None else float(data[k])) for k in cls.__dataclass_fields__ if k in data}
            for k in ("start_ts", "weighted_sum", "covered_seconds", "positive_seconds"):
                if known.get(k, 0.0) is None:
                    known[k] = 0.0
            return cls(**known)
        except (TypeError, ValueError):
            return cls()  # unreadable saved data: start the day again


@dataclass(frozen=True)
class DaySummary:
    mean: float | None
    minimum: float | None
    maximum: float | None
    integral: float  # value x seconds (W/m2 x s = J/m2)
    covered_seconds: float
    positive_seconds: float = 0.0

    @property
    def usable(self) -> bool:
        return self.covered_seconds >= MIN_COVERAGE_SECONDS and self.mean is not None
