"""Greenhouse / indoor climate decisions (1.6) -- pure Python, no Home
Assistant imports, so every rule here is tested directly with plain tables.

decide() takes the zone's settings, the latest readings and the previous
latches, and says what each device role should be doing now:

  True  = on / open        False = off / closed        None = leave it alone

It never talks to a device. greenhouse.py does that, adding the minimum
on/off times (min_time_gate() below), manual hold and the mister pulse
supervision.

Order of priority, highest first:
  1. control off        -> misters off, everything else left alone
  2. failsafe           -> inside temperature lost: misters off, vents/fans
                           per "Sensor Failsafe", heater per "Heater Failsafe"
                           (off / limited duty / limited duty while cold
                           outside)
  3. heating            -> heater on => vents closed, fans off, no misting
  4. cooling / humidity ventilation, through the outside-air gate
  5. misting            -> triggers, then hard blocks

Every on/off threshold has a separate turn-on and turn-off point
(hysteresis), held in Latches between calls, so nothing chatters around one
temperature.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

# Misting triggers (the "Misting trigger" select).
MIST_TRIGGER_TEMPERATURE = "temperature"
MIST_TRIGGER_HUMIDITY = "humidity"
MIST_TRIGGER_LIGHT = "light"
MIST_TRIGGER_ANY = "any"
MIST_TRIGGER_OPTIONS = [MIST_TRIGGER_ANY, MIST_TRIGGER_TEMPERATURE, MIST_TRIGGER_HUMIDITY, MIST_TRIGGER_LIGHT]

# "Ventilation if sensor fails" select.
FAILSAFE_OPEN = "open"
FAILSAFE_CLOSED = "closed"
FAILSAFE_LEAVE = "leave"
FAILSAFE_OPTIONS = [FAILSAFE_OPEN, FAILSAFE_CLOSED, FAILSAFE_LEAVE]

# "Heater Failsafe" select: what the heater does with no inside temperature.
# Running blind it is never on all the time (it could cook the plants), only
# FAILSAFE_HEAT_ON_SECONDS of every FAILSAFE_HEAT_PERIOD_SECONDS.
HEATER_FAILSAFE_OFF = "off"
HEATER_FAILSAFE_LIMITED = "limited"  # duty cycle, whatever the weather
HEATER_FAILSAFE_OUTSIDE = "outside"  # duty cycle while it is cold outside
HEATER_FAILSAFE_OPTIONS = [HEATER_FAILSAFE_OFF, HEATER_FAILSAFE_LIMITED, HEATER_FAILSAFE_OUTSIDE]
FAILSAFE_HEAT_ON_SECONDS = 600.0
FAILSAFE_HEAT_PERIOD_SECONDS = 1200.0

# Fixed bands (not settings in 1.6.0).
HUMIDITY_BAND = 5.0  # % RH between turn-on and turn-off for humidity rules
LIGHT_OFF_FRACTION = 0.8  # light trigger stops at 80 % of its level
HUMID_VENT_COLD_MARGIN = 2.0  # C: no humidity venting below vent temp - H - this

# Outside-air gate states.
GATE_NONE = "none"  # no outside sensor: works on inside readings only
GATE_OPEN = "open"
GATE_BLOCKED = "blocked"  # outside is not cooler: no ventilation
GATE_UNKNOWN = "unknown"  # outside sensor failed: open, and reported

# Misting block reasons, in the order they are checked.
MIST_BLOCK_NO_TRIGGER = "no_trigger"
MIST_BLOCK_HUMIDITY_UNAVAILABLE = "humidity_unavailable"
MIST_BLOCK_TOO_HUMID = "too_humid"
MIST_BLOCK_TOO_COLD = "too_cold"
MIST_BLOCK_FROST = "frost"
MIST_BLOCK_HEATING = "heating"
MIST_BLOCK_NIGHT = "night"
MIST_BLOCK_HOURLY_LIMIT = "hourly_limit"

# Starting setpoints per climate preset (const.CLIMATE_PRESETS keys), C.
PRESET_SETPOINTS: dict[str, dict[str, float]] = {
    "tropical": {"heat_temp": 15.0, "vent_temp": 28.0, "fan_temp": 31.0, "mist_temp": 32.0},
    "hot_dry": {"heat_temp": 8.0, "vent_temp": 27.0, "fan_temp": 30.0, "mist_temp": 30.0},
    "temperate": {"heat_temp": 10.0, "vent_temp": 25.0, "fan_temp": 28.0, "mist_temp": 30.0},
    "cool": {"heat_temp": 8.0, "vent_temp": 22.0, "fan_temp": 26.0, "mist_temp": 28.0},
}
PRESET_FAILSAFE: dict[str, str] = {
    "tropical": FAILSAFE_OPEN,
    "hot_dry": FAILSAFE_OPEN,
    "temperate": FAILSAFE_CLOSED,
    "cool": FAILSAFE_CLOSED,
}


@dataclass(frozen=True)
class Settings:
    heat_temp: float = 10.0
    vent_temp: float = 25.0
    fan_temp: float = 28.0
    hysteresis: float = 1.5
    outside_margin: float = 1.0
    max_humidity: float = 85.0
    mist_temp: float = 30.0
    mist_min_humidity: float = 50.0
    mist_stop_humidity: float = 85.0
    mist_min_temp: float = 18.0
    mist_light_level: float = 40000.0
    mist_trigger: str = MIST_TRIGGER_ANY
    mist_at_night: bool = False
    max_mist_minutes_per_hour: float = 10.0
    ventilation_failsafe: str = FAILSAFE_CLOSED
    heater_failsafe: str = HEATER_FAILSAFE_OFF


@dataclass(frozen=True)
class Hardware:
    """Which sensors the zone has configured (a configured sensor that has
    failed is a different thing from no sensor at all)."""

    humidity_sensor: bool = False
    outside_sensor: bool = False
    light_sensor: bool = False


@dataclass(frozen=True)
class Readings:
    """None = no usable reading (unavailable, unknown or stale)."""

    inside_temp: float | None = None
    inside_humidity: float | None = None
    outside_temp: float | None = None
    light: float | None = None
    is_day: bool = True
    frost: bool = False
    mist_minutes_last_hour: float = 0.0
    # How long the inside temperature has been missing (failsafe duty cycle).
    failsafe_seconds: float = 0.0


@dataclass(frozen=True)
class Latches:
    heat: bool = False
    vent: bool = False
    fan: bool = False
    humid: bool = False
    gate_open: bool = True
    mist_temp: bool = False
    mist_humidity: bool = False
    mist_light: bool = False
    # Failsafe heating: is it cold outside (Heater Failsafe "outside")?
    failsafe_cold: bool = False


@dataclass(frozen=True)
class Decision:
    heater: bool | None
    vents: bool | None
    fans: bool | None
    mist: bool
    latches: Latches
    gate: str = GATE_NONE
    failsafe: bool = False
    control_off: bool = False
    mist_block: str | None = None
    # Why vents/fans are on: "temperature", "humidity" or both.
    ventilating_for: tuple[str, ...] = field(default_factory=tuple)


def _latch(previous: bool, on: bool, off: bool) -> bool:
    """On when `on`, off when `off`, otherwise as it was."""
    if on:
        return True
    if off:
        return False
    return previous


def _failsafe_heater(s: Settings, hw: Hardware, r: Readings, was_cold: bool) -> tuple[bool, bool]:
    """(heater on?, cold-outside latch) with no inside temperature.

    "limited": on for the first part of every period, whatever the weather.
    "outside": the same, but only while outside is below Heater On Below
    (off again once it is that plus the hysteresis). If the outside sensor
    has failed too it can't tell, so it heats limited -- the cold is the
    danger this mode was chosen for. Without an outside sensor at all: off.
    """
    mode = s.heater_failsafe
    duty_on = (r.failsafe_seconds % FAILSAFE_HEAT_PERIOD_SECONDS) < FAILSAFE_HEAT_ON_SECONDS
    if mode == HEATER_FAILSAFE_LIMITED:
        return duty_on, False
    if mode != HEATER_FAILSAFE_OUTSIDE or not hw.outside_sensor:
        return False, False
    if r.outside_temp is None:
        return duty_on, was_cold
    cold = _latch(was_cold, on=r.outside_temp < s.heat_temp, off=r.outside_temp >= s.heat_temp + s.hysteresis)
    return cold and duty_on, cold


def check_setpoints(s: Settings) -> str | None:
    """The error key when the settings contradict each other, else None.
    Heating must stop well before venting starts, fans come at or after
    vents, and the misting humidity trigger must stop before the humidity
    stop (or misting would flap at the boundary)."""
    if s.hysteresis <= 0:
        return "hysteresis_not_positive"
    if s.heat_temp + s.hysteresis >= s.vent_temp - s.hysteresis:
        return "heat_overlaps_vent"
    if s.fan_temp < s.vent_temp:
        return "fan_below_vent"
    if s.mist_min_humidity + HUMIDITY_BAND >= s.mist_stop_humidity:
        return "mist_humidity_overlap"
    if s.mist_stop_humidity > s.max_humidity:
        # Misting on above the humidity that opens the vents: they'd fight.
        return "mist_stop_above_max_humidity"
    return None


def _gate(s: Settings, hw: Hardware, r: Readings, previous_open: bool, inside: float) -> tuple[str, bool]:
    """May outside air be used to cool or dry? Only when it is cooler than
    inside by the margin; blocked again once it is not cooler at all. In
    between it stays as it was."""
    if not hw.outside_sensor:
        return GATE_NONE, True
    if r.outside_temp is None:
        return GATE_UNKNOWN, True
    is_open = _latch(
        previous_open,
        on=r.outside_temp <= inside - s.outside_margin,
        off=r.outside_temp >= inside,
    )
    return (GATE_OPEN if is_open else GATE_BLOCKED), is_open


def _mist(s: Settings, hw: Hardware, r: Readings, latches: Latches, heater_on: bool) -> tuple[bool, str | None, Latches]:
    t = r.inside_temp
    rh = r.inside_humidity
    h = s.hysteresis
    mist_temp = _latch(latches.mist_temp, on=t >= s.mist_temp, off=t <= s.mist_temp - h)
    mist_humidity = False
    if rh is not None:
        mist_humidity = _latch(
            latches.mist_humidity,
            on=rh <= s.mist_min_humidity,
            off=rh >= s.mist_min_humidity + HUMIDITY_BAND,
        )
    mist_light = False
    if r.light is not None:
        mist_light = _latch(
            latches.mist_light,
            on=r.light >= s.mist_light_level,
            off=r.light <= s.mist_light_level * LIGHT_OFF_FRACTION,
        )
    latches = replace(latches, mist_temp=mist_temp, mist_humidity=mist_humidity, mist_light=mist_light)

    trigger = s.mist_trigger
    triggered = (
        (trigger in (MIST_TRIGGER_ANY, MIST_TRIGGER_TEMPERATURE) and mist_temp)
        or (trigger in (MIST_TRIGGER_ANY, MIST_TRIGGER_HUMIDITY) and mist_humidity)
        or (trigger in (MIST_TRIGGER_ANY, MIST_TRIGGER_LIGHT) and mist_light)
    )
    # Hard blocks: checked whether or not a trigger is on, so the status can
    # say what would stop misting.
    if hw.humidity_sensor and rh is None:
        block = MIST_BLOCK_HUMIDITY_UNAVAILABLE  # can't tell when it is damp enough
    elif rh is not None and rh >= s.mist_stop_humidity:
        block = MIST_BLOCK_TOO_HUMID
    elif t < s.mist_min_temp:
        block = MIST_BLOCK_TOO_COLD
    elif r.frost:
        block = MIST_BLOCK_FROST
    elif heater_on:
        block = MIST_BLOCK_HEATING
    elif not r.is_day and not s.mist_at_night:
        block = MIST_BLOCK_NIGHT
    elif r.mist_minutes_last_hour >= s.max_mist_minutes_per_hour:
        block = MIST_BLOCK_HOURLY_LIMIT
    elif not triggered:
        block = MIST_BLOCK_NO_TRIGGER
    else:
        block = None
    return block is None, block, latches


def decide(
    s: Settings,
    hw: Hardware,
    r: Readings,
    previous: Latches,
    *,
    enabled: bool = True,
) -> Decision:
    if not enabled:
        return Decision(heater=None, vents=None, fans=None, mist=False, latches=previous, control_off=True)

    t = r.inside_temp
    if t is None:
        vent = {FAILSAFE_OPEN: True, FAILSAFE_CLOSED: False}.get(s.ventilation_failsafe)
        heater, cold = _failsafe_heater(s, hw, r, previous.failsafe_cold)
        # Latches are reset so control restarts from the readings, not from
        # what it was doing before the sensor failed.
        return Decision(
            heater=heater, vents=vent, fans=vent, mist=False, latches=Latches(failsafe_cold=cold), failsafe=True
        )

    h = s.hysteresis
    heat = _latch(previous.heat, on=t < s.heat_temp, off=t >= s.heat_temp + h)
    vent = _latch(previous.vent, on=t >= s.vent_temp, off=t <= s.vent_temp - h)
    fan = _latch(previous.fan, on=t >= s.fan_temp, off=t <= s.fan_temp - h)
    humid = False
    if r.inside_humidity is not None:
        humid = _latch(
            previous.humid,
            on=r.inside_humidity >= s.max_humidity,
            off=r.inside_humidity <= s.max_humidity - HUMIDITY_BAND,
        )
    gate, gate_open = _gate(s, hw, r, previous.gate_open, t)
    # replace(), not a new Latches: the misting latches carry over to _mist.
    latches = replace(previous, heat=heat, vent=vent, fan=fan, humid=humid, gate_open=gate_open)

    # Humidity is vented out only when it isn't cold: never while heating,
    # and not below vent temp - H - 2 C (don't chill the house to dry it).
    humid_vent = humid and not heat and t > s.vent_temp - h - HUMID_VENT_COLD_MARGIN

    if heat:
        vents_on = fans_on = False
        reasons: tuple[str, ...] = ()
    else:
        reasons = tuple(
            reason for reason, active in (("temperature", vent or fan), ("humidity", humid_vent)) if active
        )
        vents_on = gate_open and (vent or humid_vent)
        fans_on = gate_open and (fan or humid_vent)
        if not gate_open:
            reasons = ()

    mist, block, latches = _mist(s, hw, r, latches, heat)
    return Decision(
        heater=heat,
        vents=vents_on,
        fans=fans_on,
        mist=mist,
        latches=latches,
        gate=gate,
        mist_block=block,
        ventilating_for=reasons,
    )


def min_time_gate(
    desired: bool | None,
    is_on: bool,
    changed_ts: float | None,
    now_ts: float,
    min_on_seconds: float,
    min_off_seconds: float,
    *,
    force: bool = False,
) -> bool | None:
    """What to actually command now: None = no change. A device stays on at
    least min_on and off at least min_off, so it doesn't short-cycle. `force`
    (failsafe, control off) may cut a minimum ON time short -- turning off is
    the safe direction -- but never a minimum off time."""
    if desired is None or desired == is_on:
        return None
    elapsed = float("inf") if changed_ts is None else now_ts - changed_ts
    if desired and elapsed < min_off_seconds:
        return None
    if not desired and elapsed < min_on_seconds and not force:
        return None
    return desired


def preset_settings(preset: str) -> dict[str, float | str]:
    """Starting greenhouse setpoints for a climate preset."""
    values: dict[str, float | str] = dict(PRESET_SETPOINTS.get(preset, PRESET_SETPOINTS["temperate"]))
    values["ventilation_failsafe"] = PRESET_FAILSAFE.get(preset, FAILSAFE_CLOSED)
    return values


def vpd_kpa(temp_c: float, humidity_pct: float) -> float:
    """Vapour pressure deficit of the air (Tetens), kPa -- display only."""
    import math

    saturation = 0.6108 * math.exp(17.27 * temp_c / (temp_c + 237.3))
    return round(saturation * (1 - humidity_pct / 100.0), 2)
