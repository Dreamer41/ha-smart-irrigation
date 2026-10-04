"""1.6 batch 2: the greenhouse / indoor climate decisions (greenhouse_logic.py),
tested directly as tables -- no devices, no Home Assistant state."""
from __future__ import annotations

import pytest

from custom_components.zoneflow import greenhouse_logic as gl
from custom_components.zoneflow.greenhouse_logic import (
    Decision,
    Hardware,
    Latches,
    Readings,
    Settings,
    decide,
    min_time_gate,
)

S = Settings(heat_temp=10, vent_temp=25, fan_temp=28, hysteresis=1.5, outside_margin=1.0)
ALL = Hardware(humidity_sensor=True, outside_sensor=True, light_sensor=True)
NONE = Hardware()


def run(temps, s=S, hw=NONE, **readings) -> list[Decision]:
    """Feed a series of inside temperatures, carrying the latches along."""
    latches = Latches()
    out = []
    for t in temps:
        d = decide(s, hw, Readings(inside_temp=t, **readings), latches)
        latches = d.latches
        out.append(d)
    return out


# ------------------------------------------------------------------ heating

def test_heater_turns_on_below_heat_temp_and_off_after_the_hysteresis():
    d = run([12, 9.9, 10.5, 11.4, 11.5, 11.0, 9.9])
    assert [x.heater for x in d] == [False, True, True, True, False, False, True]


def test_heater_on_means_vents_closed_fans_off_and_no_misting():
    s = Settings(heat_temp=10, vent_temp=25, fan_temp=28, mist_min_temp=0, mist_temp=5)
    d = decide(s, NONE, Readings(inside_temp=5, inside_humidity=60), Latches(humid=True))
    assert d.heater is True and d.vents is False and d.fans is False
    assert d.mist is False and d.mist_block == gl.MIST_BLOCK_HEATING


# ------------------------------------------------------------------ cooling

def test_vents_then_fans_with_separate_hysteresis():
    d = run([24, 25, 27, 28, 27, 26.5, 26, 23.6, 23.5])
    assert [x.vents for x in d] == [False, True, True, True, True, True, True, True, False]
    assert [x.fans for x in d] == [False, False, False, True, True, False, False, False, False]
    assert d[3].ventilating_for == ("temperature",)


def test_values_inside_the_band_keep_the_previous_state():
    rising = run([24, 24.5])
    assert rising[-1].vents is False
    falling = run([25, 24.5])
    assert falling[-1].vents is True


# ----------------------------------------------------- outside-air gate

def test_no_outside_sensor_works_on_inside_readings_only():
    d = run([30], hw=NONE)[0]
    assert d.gate == gl.GATE_NONE and d.vents is True and d.fans is True


def test_outside_hotter_than_inside_never_ventilates():
    d = run([30], hw=ALL, outside_temp=33, inside_humidity=60)[0]
    assert d.gate == gl.GATE_BLOCKED
    assert d.vents is False and d.fans is False and d.ventilating_for == ()


def test_outside_cooler_by_the_margin_ventilates():
    d = run([30], hw=ALL, outside_temp=29, inside_humidity=60)[0]
    assert d.gate == gl.GATE_OPEN and d.vents is True and d.fans is True


def test_gate_hysteresis_between_margin_and_equal():
    s = S
    latches = Latches()
    seq = [(30, 28), (30, 29.5), (30, 30), (30, 29.5), (30, 29)]
    got = []
    for inside, outside in seq:
        d = decide(s, ALL, Readings(inside_temp=inside, outside_temp=outside, inside_humidity=60), latches)
        latches = d.latches
        got.append(d.gate)
    # open, stays open in the band, blocked at equal, stays blocked in the band, open at the margin
    assert got == [gl.GATE_OPEN, gl.GATE_OPEN, gl.GATE_BLOCKED, gl.GATE_BLOCKED, gl.GATE_OPEN]


def test_outside_sensor_failed_falls_back_to_inside_only_and_reports_it():
    d = run([30], hw=ALL, outside_temp=None, inside_humidity=60)[0]
    assert d.gate == gl.GATE_UNKNOWN and d.vents is True and d.fans is True


def test_gate_blocked_keeps_the_temperature_latches_running():
    latches = Latches()
    d = decide(S, ALL, Readings(inside_temp=30, outside_temp=35, inside_humidity=60), latches)
    assert d.vents is False and d.latches.vent is True and d.latches.fan is True
    d = decide(S, ALL, Readings(inside_temp=30, outside_temp=25, inside_humidity=60), d.latches)
    assert d.vents is True and d.fans is True


# ----------------------------------------------------- humidity ventilation

def test_humidity_vents_and_runs_fans_until_five_percent_lower():
    hw = Hardware(humidity_sensor=True)
    latches = Latches()
    got = []
    for rh in (80, 85, 82, 80, 79):
        d = decide(S, hw, Readings(inside_temp=22, inside_humidity=rh), latches)
        latches = d.latches
        got.append((d.vents, d.fans))
    assert got == [(False, False), (True, True), (True, True), (False, False), (False, False)]


def test_no_humidity_venting_when_it_is_cold():
    hw = Hardware(humidity_sensor=True)
    # vent 25 - H 1.5 - 2 = 21.5: at or below, humidity is not vented out
    d = decide(S, hw, Readings(inside_temp=21.5, inside_humidity=95), Latches())
    assert d.vents is False and d.fans is False and d.latches.humid is True
    d = decide(S, hw, Readings(inside_temp=21.6, inside_humidity=95), Latches())
    assert d.vents is True and d.ventilating_for == ("humidity",)


def test_humidity_venting_respects_the_outside_gate():
    d = decide(S, ALL, Readings(inside_temp=23, inside_humidity=95, outside_temp=26), Latches())
    assert d.vents is False and d.gate == gl.GATE_BLOCKED


# ------------------------------------------------------------------ failsafe

@pytest.mark.parametrize(
    ("mode", "expected"),
    [(gl.FAILSAFE_OPEN, True), (gl.FAILSAFE_CLOSED, False), (gl.FAILSAFE_LEAVE, None)],
)
def test_inside_sensor_lost(mode, expected):
    s = Settings(ventilation_failsafe=mode)
    d = decide(s, ALL, Readings(inside_temp=None, inside_humidity=40), Latches(heat=True, vent=True))
    assert d.failsafe is True
    assert d.heater is False and d.mist is False
    assert d.vents is expected and d.fans is expected
    assert d.latches == Latches()  # starts fresh when readings return


def test_control_off_leaves_everything_alone_but_misting():
    d = decide(S, ALL, Readings(inside_temp=40), Latches(vent=True), enabled=False)
    assert d.control_off and d.heater is None and d.vents is None and d.fans is None and d.mist is False


# ------------------------------------------------------------------ misting

MIST = Settings(
    heat_temp=10, vent_temp=25, fan_temp=28, mist_temp=30, mist_min_humidity=50,
    mist_stop_humidity=85, mist_min_temp=18, mist_light_level=40000,
)


def mist(r: Readings, s=MIST, hw=ALL, latches=Latches()):
    return decide(s, hw, r, latches)


def test_mist_temperature_trigger_with_hysteresis():
    d = mist(Readings(inside_temp=30, inside_humidity=60))
    assert d.mist is True
    d = mist(Readings(inside_temp=29, inside_humidity=60), latches=d.latches)
    assert d.mist is True  # still above 30 - 1.5
    d = mist(Readings(inside_temp=28.5, inside_humidity=60), latches=d.latches)
    assert d.mist is False and d.mist_block == gl.MIST_BLOCK_NO_TRIGGER


def test_mist_humidity_trigger():
    d = mist(Readings(inside_temp=24, inside_humidity=50))
    assert d.mist is True
    d = mist(Readings(inside_temp=24, inside_humidity=54), latches=d.latches)
    assert d.mist is True
    d = mist(Readings(inside_temp=24, inside_humidity=55), latches=d.latches)
    assert d.mist is False


def test_mist_light_trigger():
    d = mist(Readings(inside_temp=24, inside_humidity=70, light=40000))
    assert d.mist is True
    d = mist(Readings(inside_temp=24, inside_humidity=70, light=33000), latches=d.latches)
    assert d.mist is True
    d = mist(Readings(inside_temp=24, inside_humidity=70, light=32000), latches=d.latches)
    assert d.mist is False


@pytest.mark.parametrize(
    ("trigger", "readings", "expected"),
    [
        (gl.MIST_TRIGGER_TEMPERATURE, dict(inside_temp=24, inside_humidity=40, light=50000), False),
        (gl.MIST_TRIGGER_TEMPERATURE, dict(inside_temp=31, inside_humidity=70, light=0), True),
        (gl.MIST_TRIGGER_HUMIDITY, dict(inside_temp=31, inside_humidity=70, light=50000), False),
        (gl.MIST_TRIGGER_HUMIDITY, dict(inside_temp=24, inside_humidity=40, light=0), True),
        (gl.MIST_TRIGGER_LIGHT, dict(inside_temp=31, inside_humidity=40, light=0), False),
        (gl.MIST_TRIGGER_LIGHT, dict(inside_temp=24, inside_humidity=70, light=50000), True),
    ],
)
def test_mist_trigger_select(trigger, readings, expected):
    s = Settings(**{**MIST.__dict__, "mist_trigger": trigger})
    assert mist(Readings(**readings), s=s).mist is expected


@pytest.mark.parametrize(
    ("readings", "hw", "block"),
    [
        (dict(inside_temp=31, inside_humidity=None), ALL, gl.MIST_BLOCK_HUMIDITY_UNAVAILABLE),
        (dict(inside_temp=31, inside_humidity=85), ALL, gl.MIST_BLOCK_TOO_HUMID),
        (dict(inside_temp=17.9, inside_humidity=40), ALL, gl.MIST_BLOCK_TOO_COLD),
        (dict(inside_temp=31, inside_humidity=40, frost=True), ALL, gl.MIST_BLOCK_FROST),
        (dict(inside_temp=31, inside_humidity=40, is_day=False), ALL, gl.MIST_BLOCK_NIGHT),
        (dict(inside_temp=31, inside_humidity=40, mist_minutes_last_hour=10), ALL, gl.MIST_BLOCK_HOURLY_LIMIT),
    ],
)
def test_mist_hard_blocks(readings, hw, block):
    d = mist(Readings(**readings), hw=hw)
    assert d.mist is False and d.mist_block == block


def test_mist_at_night_switch():
    s = Settings(**{**MIST.__dict__, "mist_at_night": True})
    assert mist(Readings(inside_temp=31, inside_humidity=40, is_day=False), s=s).mist is True


def test_mist_without_a_humidity_sensor_works_on_temperature_and_the_hourly_cap():
    hw = Hardware(outside_sensor=True)
    assert mist(Readings(inside_temp=31), hw=hw).mist is True
    d = mist(Readings(inside_temp=31, mist_minutes_last_hour=10.0), hw=hw)
    assert d.mist is False and d.mist_block == gl.MIST_BLOCK_HOURLY_LIMIT


def test_misting_still_runs_when_the_gate_blocks_ventilation():
    """Outside hotter: no venting, so misting is the cooling route."""
    d = mist(Readings(inside_temp=33, inside_humidity=55, outside_temp=36))
    assert d.vents is False and d.mist is True


# ---------------------------------------------------------- setpoint checks

@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({}, None),
        ({"hysteresis": 0}, "hysteresis_not_positive"),
        ({"heat_temp": 22.0}, "heat_overlaps_vent"),  # 22 + 1.5 >= 25 - 1.5
        ({"fan_temp": 24.0}, "fan_below_vent"),
        ({"mist_min_humidity": 80.0}, "mist_humidity_overlap"),
        ({"mist_stop_humidity": 90.0}, "mist_stop_above_max_humidity"),
    ],
)
def test_check_setpoints(changes, error):
    assert gl.check_setpoints(Settings(**{**S.__dict__, **changes})) == error


@pytest.mark.parametrize("preset", list(gl.PRESET_SETPOINTS))
def test_every_preset_is_consistent(preset):
    s = Settings(**{**Settings().__dict__, **{k: v for k, v in gl.preset_settings(preset).items()}})
    assert gl.check_setpoints(s) is None


# ------------------------------------------------------- minimum on / off

@pytest.mark.parametrize(
    ("desired", "is_on", "elapsed", "force", "expected"),
    [
        (None, True, 999, False, None),     # leave alone
        (True, True, 999, False, None),     # already so
        (True, False, 60, False, None),     # off only 60 s, min off 120
        (True, False, 120, False, True),
        (False, True, 60, False, None),     # on only 60 s, min on 120
        (False, True, 60, True, False),     # failsafe may cut min on short
        (True, False, 60, True, None),      # ...but never min off
        (False, True, 120, False, False),
    ],
)
def test_min_time_gate(desired, is_on, elapsed, force, expected):
    assert min_time_gate(desired, is_on, 1000.0 - elapsed, 1000.0, 120, 120, force=force) == expected


def test_min_time_gate_with_no_history_acts_at_once():
    assert min_time_gate(True, False, None, 1000.0, 120, 120) is True


def test_vpd():
    assert gl.vpd_kpa(25, 60) == pytest.approx(1.27, abs=0.01)
    assert gl.vpd_kpa(25, 100) == 0.0


# ------------------------------------------------------- heater failsafe

def _fs(mode, hw=ALL, latches=Latches(), **r):
    return decide(Settings(heat_temp=10, hysteresis=1.5, heater_failsafe=mode), hw, Readings(inside_temp=None, **r), latches)


def test_heater_failsafe_off_keeps_the_heater_off():
    assert _fs("off", outside_temp=-5).heater is False


@pytest.mark.parametrize(
    "seconds, on",
    [(0, True), (599, True), (600, False), (1199, False), (1200, True), (1900, False)],
)
def test_heater_failsafe_limited_runs_a_duty_cycle(seconds, on):
    assert _fs("limited", failsafe_seconds=seconds, outside_temp=30).heater is on


def test_heater_failsafe_outside_heats_only_when_cold_outside_with_hysteresis():
    latches = Latches()
    seen = []
    for outside in (12, 9.9, 10.5, 11.4, 11.5, 9.0):
        d = _fs("outside", latches=latches, outside_temp=outside, failsafe_seconds=0)
        latches = d.latches
        seen.append(d.heater)
    assert seen == [False, True, True, True, False, True]


def test_heater_failsafe_outside_still_follows_the_duty_cycle():
    assert _fs("outside", outside_temp=0, failsafe_seconds=700).heater is False


def test_heater_failsafe_outside_with_outside_sensor_failed_heats_limited():
    assert _fs("outside", outside_temp=None, failsafe_seconds=0).heater is True
    assert _fs("outside", outside_temp=None, failsafe_seconds=700).heater is False


def test_heater_failsafe_outside_without_outside_sensor_is_off():
    assert _fs("outside", hw=NONE, outside_temp=None).heater is False


def test_failsafe_never_mists_whatever_the_heater_does():
    d = _fs("limited", inside_humidity=20, outside_temp=0)
    assert d.mist is False and d.failsafe is True


# ------------------------------------------------------------ review fixes (1.6.0)

def _failsafe(outside, mode, vent=gl.FAILSAFE_OPEN):
    s = Settings(heat_temp=10, vent_temp=25, fan_temp=28, hysteresis=1.5,
                 ventilation_failsafe=vent, heater_failsafe=mode)
    return decide(s, ALL, Readings(inside_temp=None, outside_temp=outside, failsafe_seconds=0), Latches())


@pytest.mark.parametrize("mode", [gl.HEATER_FAILSAFE_LIMITED, gl.HEATER_FAILSAFE_OUTSIDE])
def test_failsafe_heating_in_the_cold_keeps_the_vents_shut(mode):
    d = _failsafe(outside=2, mode=mode)
    assert d.heater is True
    assert d.vents is False and d.fans is False


def test_failsafe_vents_follow_the_setting_when_it_is_not_cold():
    d = _failsafe(outside=30, mode=gl.HEATER_FAILSAFE_LIMITED)
    assert d.heater is True  # "limited" heats whatever the weather ...
    assert d.vents is True and d.fans is True  # ... but a shut hot house is the bigger danger


def test_failsafe_heater_off_leaves_vents_to_the_setting():
    d = _failsafe(outside=2, mode=gl.HEATER_FAILSAFE_OFF)
    assert d.heater is False and d.vents is True


def test_failsafe_vents_stay_shut_through_the_heaters_off_part():
    s = Settings(heat_temp=10, hysteresis=1.5, ventilation_failsafe=gl.FAILSAFE_OPEN,
                 heater_failsafe=gl.HEATER_FAILSAFE_OUTSIDE)
    d = decide(s, ALL, Readings(inside_temp=None, outside_temp=2, failsafe_seconds=900), Latches())
    assert d.heater is False and d.vents is False


def test_climate_heater_in_cool_mode_is_not_a_heater_that_is_on():
    from homeassistant.core import State

    from custom_components.zoneflow import actuators

    assert actuators.state_is_on("climate.h", State("climate.h", "heat")) is True
    assert actuators.state_is_on("climate.h", State("climate.h", "cool")) is False
    assert actuators.state_is_on("climate.h", State("climate.h", "off")) is False
