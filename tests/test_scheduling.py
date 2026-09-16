"""Sunrise/sunset-relative scheduling is an alternative to the fixed clock
time, not a replacement -- the default mode ("fixed") must produce exactly
the same async_track_time_change call as before this feature existed, and
each sun-relative mode must translate to the right helper + signed offset.
These are unit tests against ZoneFlowController._track_schedule directly
(no config entry / hass bootstrap needed) so they stay fast and don't
depend on real sunrise/sunset timing.
"""
from datetime import time as dt_time, timedelta

import pytest

from custom_components.zoneflow import controller as controller_module
from custom_components.zoneflow.const import (
    SUN_MODE_AFTER_SUNRISE,
    SUN_MODE_AFTER_SUNSET,
    SUN_MODE_BEFORE_SUNRISE,
    SUN_MODE_BEFORE_SUNSET,
    SUN_MODE_FIXED,
)

FIXED_TIME = dt_time(5, 30, 0)


def _bare_controller():
    """A ZoneFlowController with none of __init__'s side effects -- only
    self.hass is needed for _track_schedule, and every call in this test is
    monkeypatched so hass is never actually touched."""
    ctrl = controller_module.ZoneFlowController.__new__(controller_module.ZoneFlowController)
    ctrl.hass = object()
    return ctrl


def test_fixed_mode_uses_the_clock_time_trigger(monkeypatch):
    calls = []
    monkeypatch.setattr(
        controller_module,
        "async_track_time_change",
        lambda hass, action, hour, minute, second: calls.append(("fixed", hour, minute, second)) or (lambda: None),
    )
    ctrl = _bare_controller()

    ctrl._track_schedule(SUN_MODE_FIXED, 0, FIXED_TIME, lambda now: None)

    assert calls == [("fixed", 5, 30, 0)]


@pytest.mark.parametrize(
    "mode,offset_minutes,expected_helper,expected_offset",
    [
        (SUN_MODE_BEFORE_SUNRISE, 30, "sunrise", -timedelta(minutes=30)),
        (SUN_MODE_AFTER_SUNRISE, 15, "sunrise", timedelta(minutes=15)),
        (SUN_MODE_BEFORE_SUNSET, 45, "sunset", -timedelta(minutes=45)),
        (SUN_MODE_AFTER_SUNSET, 10, "sunset", timedelta(minutes=10)),
    ],
)
def test_sun_relative_modes_use_the_right_helper_and_signed_offset(
    monkeypatch, mode, offset_minutes, expected_helper, expected_offset
):
    calls = []
    monkeypatch.setattr(
        controller_module,
        "async_track_sunrise",
        lambda hass, action, offset=None: calls.append(("sunrise", offset)) or (lambda: None),
    )
    monkeypatch.setattr(
        controller_module,
        "async_track_sunset",
        lambda hass, action, offset=None: calls.append(("sunset", offset)) or (lambda: None),
    )
    ctrl = _bare_controller()

    ctrl._track_schedule(mode, offset_minutes, FIXED_TIME, lambda now: None)

    assert calls == [(expected_helper, expected_offset)]


def test_sun_relative_action_is_called_with_no_arguments(monkeypatch):
    """async_track_sunrise/sunset invoke their action with zero arguments,
    unlike async_track_time_change which passes `now` -- the wrapper must
    adapt so the existing _on_deep_soak_time/_on_routine_time callbacks
    (which take `now`) still work under sun-relative scheduling."""
    captured_action = {}

    def fake_track_sunrise(hass, action, offset=None):
        captured_action["action"] = action
        return lambda: None

    monkeypatch.setattr(controller_module, "async_track_sunrise", fake_track_sunrise)
    ctrl = _bare_controller()

    received = []
    ctrl._track_schedule(SUN_MODE_BEFORE_SUNRISE, 30, FIXED_TIME, lambda now: received.append(now))

    captured_action["action"]()  # simulate HA firing the sunrise trigger
    assert received == [None]
