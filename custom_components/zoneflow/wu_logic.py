"""Weather Underground rain (1.6.1, experimental): the pure part.

For outdoor zones WITHOUT a rain gauge, rain is borrowed from 1-3 private
weather stations near the garden. Nothing here talks to Home Assistant or
the network (that is wu.py), so it can be tested on its own.

Each station reports `precipTotal`: rain since its local midnight. Every
poll the usable stations' totals are combined into one figure for the day:

- 3 stations: the median, so one broken gauge can't fool it;
- 2 stations: the LOWER one -- too much rain makes ZoneFlow water too
  little, which hurts plants; too little only waters a bit more;
- 1 station: used as is (lower confidence);
- 0 stations: nothing (the zone acts as if it had no gauge).

What the day's combined figure grew by since the last poll is the rain
added to the record. Totals rather than per-poll differences, because
stations report a few minutes apart: taking the lower of two stations'
10-minute differences would lose rain whenever one lags the other. When a
station drops out or comes back, the combined figure would jump, so the
figure is re-anchored then and only the stations present both times count
for that one poll.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# A station whose latest report is older than this is silent.
SILENT_SECONDS = 2 * 3600
# More than this since the last report is not rain, it's a broken gauge.
SPIKE_MM = 150.0
# A station that hasn't risen for this long while another one did is stuck.
STUCK_SECONDS = 24 * 3600
# Rain counts for the 15/30/60-minute "raining now" checks only when the
# previous poll was at most this much earlier (watering mode polls every 10
# minutes; a 2-hour lump never counts as "now").
FRESH_GAP_SECONDS = 15 * 60
# Rain record kept this long (covers the 14-day window).
RECORD_RETENTION_SECONDS = 15 * 86400

# Polling: every 2 hours, every 10 minutes from an hour before a WU zone's
# watering until it has finished, and at 23:55 local time for the day's last
# rain (a station's total resets at midnight).
QUIET_POLL_SECONDS = 2 * 3600
WATERING_POLL_SECONDS = 10 * 60
WATERING_LEAD_SECONDS = 60 * 60
DAY_END_POLL_TIME = (23, 55)

MAX_STATIONS = 3
# Nearer is better: rain can differ a lot over a couple of km. Beyond 1 km
# the person should compare with what really falls in the garden.
RADIUS_DEFAULT_KM = 1.0
RADIUS_MIN_KM = 0.5
RADIUS_MAX_KM = 2.0
CHECK_DISTANCE_KM = 1.0


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance (haversine), worked out by ZoneFlow rather than
    trusted from the station list."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass
class Observation:
    """One station's current report: rain since its local midnight."""

    total_mm: float
    obs_ts: float
    obs_day: str  # the report's local date


@dataclass
class StationState:
    """What ZoneFlow remembers about one station between polls."""

    day: str | None = None
    total: float | None = None  # today's total at its last good report
    obs_ts: float | None = None
    last_rise_ts: float | None = None  # when its total last went up
    first_seen_ts: float | None = None
    status: str = "waiting"  # ok / silent / stuck / spike / no_data / waiting

    def as_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, data: dict | None) -> StationState:
        state = cls()
        for key, value in (data or {}).items():
            if hasattr(state, key):
                setattr(state, key, value)
        return state


def check_station(state: StationState, obs: Observation | None, now_ts: float, today: str) -> float | None:
    """The station's usable total for `today`, or None. Updates `state`."""
    if state.first_seen_ts is None:
        state.first_seen_ts = now_ts
    if obs is None:
        state.status = "no_data"
        return None
    if now_ts - obs.obs_ts > SILENT_SECONDS or obs.obs_day != today:
        state.status = "silent"  # nothing recent, or still yesterday's total
        return None
    if obs.total_mm < 0:
        state.status = "spike"
        return None
    previous = (state.total or 0.0) if state.day == today else 0.0
    if obs.total_mm - previous > SPIKE_MM:
        state.status = "spike"
        return None
    if obs.total_mm > previous:
        state.last_rise_ts = now_ts
    state.day, state.obs_ts = today, obs.obs_ts
    # A total that went down the same day is a glitch: keep the higher one.
    state.total = max(obs.total_mm, previous)
    state.status = "ok"
    return state.total


def drop_stuck(states: dict[str, StationState], totals: dict[str, float], now_ts: float) -> dict[str, float]:
    """Drop stations that haven't risen for 24 h while another one did: a
    gauge stuck at 0 would otherwise pull the figure down."""

    def rose_recently(state: StationState) -> bool:
        return state.last_rise_ts is not None and now_ts - state.last_rise_ts < STUCK_SECONDS

    if not any(rose_recently(states[sid]) for sid in totals):
        return totals
    kept = {}
    for sid, total in totals.items():
        state = states[sid]
        quiet_since = state.last_rise_ts if state.last_rise_ts is not None else state.first_seen_ts
        if quiet_since is not None and now_ts - quiet_since >= STUCK_SECONDS:
            state.status = "stuck"
            continue
        kept[sid] = total
    return kept


def combine(values: list[float]) -> float | None:
    """One figure from the usable stations (see the module doc)."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 2:
        return ordered[0]
    if len(ordered) >= 3:
        mid = len(ordered) // 2
        return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    return ordered[0]


@dataclass
class DayState:
    """Today's combined rain: `credited` is what went into the record,
    `anchor` the combined figure of the current set of stations at the last
    poll, `totals` each of those stations' total then."""

    day: str | None = None
    credited: float = 0.0
    anchor: float = 0.0
    station_ids: list[str] = field(default_factory=list)
    totals: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, data: dict | None) -> DayState:
        state = cls()
        for key, value in (data or {}).items():
            if hasattr(state, key):
                setattr(state, key, value)
        return state


def new_rain(day_state: DayState, totals: dict[str, float], today: str) -> float | None:
    """Rain to add to the record from this poll's usable totals, or None when
    no station was usable. Updates `day_state`."""
    if day_state.day != today:
        day_state.day, day_state.credited, day_state.anchor = today, 0.0, 0.0
        day_state.station_ids, day_state.totals = [], {}
    if not totals:
        return None  # the last usable totals are kept for when they return
    ids = sorted(totals)
    figure = combine(list(totals.values()))
    if ids == day_state.station_ids:
        rise = max(figure - day_state.anchor, 0.0)
    else:
        both = [sid for sid in ids if sid in day_state.totals]
        if both:
            # Stations dropped out or came back: only those present both
            # times count for this poll, then the figure is re-anchored.
            rise = combine([max(totals[sid] - day_state.totals[sid], 0.0) for sid in both])
        else:
            # The first report of the day: what fell since midnight.
            rise = figure if day_state.credited == 0.0 else 0.0
        day_state.anchor = figure
    day_state.anchor = max(day_state.anchor, figure)
    day_state.credited += rise
    day_state.station_ids = ids
    day_state.totals = dict(totals)
    return rise

@dataclass
class RainRecord:
    """The combined WU rain: (time, cumulative mm, fresh) samples, only when
    rain was added. `fresh` says the rise is known to be recent (see
    FRESH_GAP_SECONDS)."""

    samples: list[tuple[float, float, bool]] = field(default_factory=list)

    @property
    def total(self) -> float:
        return self.samples[-1][1] if self.samples else 0.0

    def add(self, ts: float, mm: float, fresh: bool) -> None:
        if mm <= 0:
            return
        if not self.samples:
            self.samples.append((ts - 1.0, 0.0, False))  # a baseline for the windows
        self.samples.append((ts, self.total + mm, fresh))
        cutoff = ts - RECORD_RETENTION_SECONDS
        while len(self.samples) > 1 and self.samples[1][0] <= cutoff:
            self.samples.pop(0)

    def _at(self, when: float) -> float:
        value = self.samples[0][1] if self.samples else 0.0
        for t, c, _fresh in self.samples:
            if t > when:
                break
            value = c
        return value

    def sum_between(self, start_ts: float, end_ts: float) -> float:
        if not self.samples:
            return 0.0
        return max(self._at(end_ts) - self._at(start_ts), 0.0)

    def fresh_sum_since(self, start_ts: float) -> float:
        """Rain after `start_ts` that arrived fresh (for "raining now")."""
        total = 0.0
        previous = None
        for t, c, fresh in self.samples:
            if previous is not None and t > start_ts and fresh:
                total += c - previous
            previous = c
        return total

    def as_persisted(self) -> list[list]:
        return [[t, c, 1 if f else 0] for t, c, f in self.samples]

    @classmethod
    def from_persisted(cls, data: list | None) -> RainRecord:
        return cls(samples=[(row[0], row[1], bool(row[2])) for row in (data or [])])


def next_poll_ts(now_ts: float, waterings: list[float], running: bool, day_end_ts: float) -> float:
    """When to poll next. `waterings` are the next scheduled starts of the
    zones that use WU; `running` is true while one of them waters;
    `day_end_ts` is the next 23:55 local."""
    if running or any(start - WATERING_LEAD_SECONDS <= now_ts <= start + WATERING_POLL_SECONDS for start in waterings):
        return now_ts + WATERING_POLL_SECONDS
    candidates = [now_ts + QUIET_POLL_SECONDS, day_end_ts]
    candidates += [start - WATERING_LEAD_SECONDS for start in waterings if start - WATERING_LEAD_SECONDS > now_ts]
    return max(min(candidates), now_ts + 60)
