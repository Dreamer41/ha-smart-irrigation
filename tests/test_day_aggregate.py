"""1.8: a sensor's day, time-weighted, with the 18-hour coverage rule."""
from __future__ import annotations

import pytest

from custom_components.zoneflow.day_aggregate import MIN_COVERAGE_SECONDS, DayAggregate

H = 3600.0


def test_a_steady_reading_covers_the_whole_day():
    a = DayAggregate()
    a.reset(0.0)
    a.add(0.0, 60.0)
    s = a.close(24 * H)
    assert s.mean == 60.0 and s.covered_seconds == 24 * H and s.usable


def test_the_mean_is_weighted_by_time_not_by_number_of_readings():
    a = DayAggregate()
    a.reset(0.0)
    a.add(0.0, 90.0)  # 90 % for 18 hours
    for k in range(60):  # then 60 quick readings of 30 % in the last 6 hours
        a.add(18 * H + k * 360, 30.0)
    s = a.close(24 * H)
    assert s.mean == pytest.approx((90 * 18 + 30 * 6) / 24)
    assert s.minimum == 30.0 and s.maximum == 90.0


def test_offline_time_is_not_covered_and_a_late_start_is_not_a_day():
    a = DayAggregate()
    a.reset(0.0)
    a.add(22 * H, 50.0)  # came back at 22:00
    s = a.close(24 * H)
    assert s.covered_seconds == 2 * H and not s.usable
    b = DayAggregate()
    b.reset(0.0)
    b.add(0.0, 50.0)
    b.add(4 * H, None)  # offline 04:00-10:00
    b.add(10 * H, 70.0)
    s = b.close(24 * H)
    assert s.covered_seconds == 18 * H and s.usable == (18 * H >= MIN_COVERAGE_SECONDS)
    assert s.mean == pytest.approx((50 * 4 + 70 * 14) / 18)


def test_a_restart_is_not_covered():
    a = DayAggregate()
    a.reset(0.0)
    a.add(0.0, 40.0)
    a.pause(8 * H)  # Home Assistant stopped at 08:00
    restored = DayAggregate.from_dict(a.as_dict())
    restored.add(9 * H, 45.0)  # back at 09:00
    s = restored.close(24 * H)
    assert s.covered_seconds == 23 * H


def test_the_integral_is_value_times_seconds():
    a = DayAggregate()
    a.reset(0.0)
    a.add(0.0, 0.0)
    a.add(6 * H, 500.0)  # 500 W/m2 from 06:00 to 18:00
    a.add(18 * H, 0.0)
    s = a.close(24 * H)
    assert s.integral / 1e6 == pytest.approx(500 * 12 * H / 1e6)  # 21.6 MJ/m2


def test_a_new_day_keeps_the_reading_that_holds():
    a = DayAggregate()
    a.reset(0.0)
    a.add(10 * H, 55.0)
    a.close(24 * H)
    a.reset(24 * H)
    s = a.close(48 * H)
    assert s.mean == 55.0 and s.covered_seconds == 24 * H and s.minimum == 55.0


def test_out_of_order_and_bad_saved_data_are_harmless():
    a = DayAggregate()
    a.reset(0.0)
    a.add(10 * H, 50.0)
    a.add(5 * H, 99.0)  # clock stepped back: ignored
    assert a.maximum == 50.0
    assert DayAggregate.from_dict(None).covered_seconds == 0.0
    assert DayAggregate.from_dict({"start_ts": "x", "covered_seconds": 3}).covered_seconds == 0.0
    assert DayAggregate.from_dict({"unknown": 1}).last_value is None
