"""1.8: the flow meter, read right. A meter's unit says whether it counts a running total or reports a
rate; a rate meter was read as a total of litres before. FlowTracker counts the litres of a run either way."""
from __future__ import annotations

import pytest

from custom_components.zoneflow import flow_meter as fm


def test_the_unit_tells_a_total_from_a_rate():
    for unit in (None, "", "L", "gal", "m³", "ft³", "CCF", "mL"):
        assert fm.meter_kind(unit) == fm.METER_TOTAL, unit
    for unit in ("L/min", "L/h", "m³/h", "gal/min", "ft³/min", "mL/s"):
        assert fm.meter_kind(unit) == fm.METER_RATE, unit
    for unit in ("pulses", "kWh", "W"):
        assert fm.meter_kind(unit) is None, unit


def test_conversions():
    assert fm.to_litres(1.0, "m³") == pytest.approx(1000.0)
    assert fm.to_litres(1.0, "gal") == pytest.approx(3.785, abs=0.001)
    assert fm.to_l_min(0.6, "m³/h") == pytest.approx(10.0)
    assert fm.to_l_min(120.0, "L/h") == pytest.approx(2.0)


def test_a_total_counts_and_survives_a_reset():
    t = fm.FlowTracker(fm.METER_TOTAL, 100.0, 0.0)
    t.update(102.0, 10.0)
    t.update(105.0, 20.0)
    assert t.litres(20.0) == pytest.approx(5.0)
    t.update(2.0, 30.0)  # the meter reset
    t.update(5.0, 40.0)
    assert t.litres(40.0) == pytest.approx(10.0)
    t.update(4.8, 50.0)  # a small step back is noise
    assert t.litres(50.0) == pytest.approx(10.0)


def test_a_rate_adds_up_over_time_and_stops_when_it_goes_quiet():
    t = fm.FlowTracker(fm.METER_RATE, 10.0, 0.0)  # 10 L/min
    t.update(10.0, 60.0)
    t.update(10.0, 120.0)
    assert t.litres(180.0) == pytest.approx(30.0)  # held between reports
    # No report for longer than RATE_STALE_SECONDS: counting stops at the stale limit.
    assert t.litres(180.0 + 1000.0) == pytest.approx(20.0 + 10.0 * fm.RATE_STALE_SECONDS / 60.0)
    assert t.rate_l_min(1000.0) is None


def test_the_flow_right_now_and_whether_it_moves():
    t = fm.FlowTracker(fm.METER_TOTAL, 0.0, 0.0)
    for second in range(0, 61, 10):
        t.update(second / 6.0, float(second))  # 10 L/min
    assert t.rate_l_min(60.0) == pytest.approx(10.0, rel=0.05)
    assert t.flowing_since(60.0) == 0.0 and t.flowing_since(200.0) == pytest.approx(140.0)
    rate = fm.FlowTracker(fm.METER_RATE, 0.0, 0.0)
    assert rate.flowing_since(100.0) == pytest.approx(100.0)
    rate.update(4.0, 100.0)
    assert rate.flowing_since(150.0) == 0.0 and rate.rate_l_min(150.0) == 4.0


def test_a_broken_reading_is_not_water_but_a_meter_that_really_moved_is_followed():
    t = fm.FlowTracker(fm.METER_TOTAL, 100.0, 0.0)
    t.update(110.0, 10.0)
    t.update(99999.0, 20.0)  # one wild reading
    t.update(115.0, 30.0)  # and back to normal
    assert t.litres(30.0) == pytest.approx(15.0)
    moved = fm.FlowTracker(fm.METER_TOTAL, 100.0, 0.0)
    moved.update(50000.0, 10.0)
    moved.update(50005.0, 20.0)  # it stayed there: a new baseline
    moved.update(50010.0, 30.0)
    assert moved.litres(30.0) == pytest.approx(5.0)
