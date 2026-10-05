"""Weather Underground rain, the pure part (wu_logic.py): station checks,
combining 1-3 stations, the rain record and when to poll."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "zoneflow"))

import wu_logic as wl  # noqa: E402
from wu_logic import DayState, Observation, RainRecord, StationState  # noqa: E402

NOW = 1_000_000.0
TODAY = "2026-10-04"


def _poll(states, day, reports, now=NOW, today=TODAY):
    """One poll: {station: total or None} -> rain added (or None)."""
    totals = {}
    for sid, total in reports.items():
        obs = None if total is None else Observation(total, now - 60, today)
        value = wl.check_station(states.setdefault(sid, StationState()), obs, now, today)
        if value is not None:
            totals[sid] = value
    totals = wl.drop_stuck(states, totals, now)
    return wl.new_rain(day, totals, today)


def test_distance_is_worked_out_from_coordinates():
    assert wl.distance_km(9.5, 100.0, 9.5, 100.0) == 0.0
    assert wl.distance_km(9.5, 100.0, 9.509, 100.0) == pytest.approx(1.0, abs=0.01)


def test_combine_rules():
    assert wl.combine([]) is None
    assert wl.combine([4.0]) == 4.0
    assert wl.combine([4.0, 9.0]) == 4.0  # two stations: the lower one
    assert wl.combine([1.0, 9.0, 4.0]) == 4.0  # three: the median


def test_rain_follows_the_combined_daily_total():
    states, day = {}, DayState()
    assert _poll(states, day, {"A": 0.0, "B": 0.0, "C": 0.0}) == 0.0
    assert _poll(states, day, {"A": 2.0, "B": 3.0, "C": 50.0}, NOW + 600) == pytest.approx(3.0)
    assert _poll(states, day, {"A": 5.0, "B": 4.0, "C": 50.0}, NOW + 1200) == pytest.approx(2.0)
    assert day.credited == pytest.approx(5.0)


def test_two_stations_reporting_out_of_step_lose_no_rain():
    states, day = {}, DayState()
    _poll(states, day, {"A": 0.0, "B": 0.0})
    _poll(states, day, {"A": 4.0, "B": 0.0}, NOW + 600)  # B hasn't uploaded yet
    _poll(states, day, {"A": 4.0, "B": 4.0}, NOW + 1200)
    _poll(states, day, {"A": 8.0, "B": 4.0}, NOW + 1800)
    _poll(states, day, {"A": 8.0, "B": 8.0}, NOW + 2400)
    assert day.credited == pytest.approx(8.0)


def test_a_station_dropping_out_and_coming_back_makes_no_fake_rain():
    states, day = {}, DayState()
    _poll(states, day, {"A": 0.0, "B": 0.0, "C": 0.0})
    _poll(states, day, {"A": 1.0, "B": 1.0, "C": 20.0}, NOW + 600)
    assert day.credited == pytest.approx(1.0)
    # B goes silent: A and C left, the lower of the two is A.
    _poll(states, day, {"A": 1.0, "B": None, "C": 20.0}, NOW + 1200)
    assert day.credited == pytest.approx(1.0)
    _poll(states, day, {"A": 1.0, "B": 1.0, "C": 20.0}, NOW + 1800)
    assert day.credited == pytest.approx(1.0)


def test_rain_during_an_outage_still_counts_when_stations_return():
    states, day = {}, DayState()
    _poll(states, day, {"A": 0.0, "B": 0.0})
    _poll(states, day, {"A": None, "B": None}, NOW + 600)
    _poll(states, day, {"A": 6.0, "B": 5.0}, NOW + 1200)
    assert day.credited == pytest.approx(5.0)


def test_a_new_day_starts_from_zero_and_counts_rain_since_midnight():
    states, day = {}, DayState()
    _poll(states, day, {"A": 0.0, "B": 0.0})
    _poll(states, day, {"A": 10.0, "B": 10.0}, NOW + 600)
    assert _poll(states, day, {"A": 2.0, "B": 3.0}, NOW + 7200, "2026-10-05") == pytest.approx(2.0)
    assert day.credited == pytest.approx(2.0)


def test_yesterdays_total_after_midnight_is_not_used():
    states = {"A": StationState()}
    obs = Observation(12.0, NOW - 60, "2026-10-03")
    assert wl.check_station(states["A"], obs, NOW, TODAY) is None
    assert states["A"].status == "silent"


def test_silent_and_spike_are_left_out():
    state = StationState()
    assert wl.check_station(state, Observation(1.0, NOW - 3 * 3600, TODAY), NOW, TODAY) is None
    assert state.status == "silent"
    assert wl.check_station(state, Observation(200.0, NOW - 60, TODAY), NOW, TODAY) is None
    assert state.status == "spike"
    assert wl.check_station(state, None, NOW, TODAY) is None
    assert state.status == "no_data"


def test_a_total_that_goes_down_the_same_day_is_ignored():
    states, day = {}, DayState()
    _poll(states, day, {"A": 5.0})
    _poll(states, day, {"A": 2.0}, NOW + 600)
    assert _poll(states, day, {"A": 6.0}, NOW + 1200) == pytest.approx(1.0)


def test_a_station_stuck_at_zero_is_dropped_when_others_rise():
    states, day = {}, DayState()
    _poll(states, day, {"A": 0.0, "B": 0.0}, NOW - 2 * 86400)
    _poll(states, day, {"A": 3.0, "B": 0.0}, NOW - 600, TODAY)
    _poll(states, day, {"A": 8.0, "B": 0.0}, NOW, TODAY)
    assert states["B"].status == "stuck"
    assert day.credited >= 5.0


def test_record_windows_and_fresh_rain():
    record = RainRecord()
    record.add(NOW - 7200, 4.0, fresh=False)  # a 2-hour lump
    record.add(NOW - 600, 1.5, fresh=True)
    assert record.sum_between(NOW - 86400, NOW) == pytest.approx(5.5)
    assert record.fresh_sum_since(NOW - 1800) == pytest.approx(1.5)
    assert record.fresh_sum_since(NOW - 3 * 3600) == pytest.approx(1.5)  # the lump never counts as "now"
    assert RainRecord.from_persisted(record.as_persisted()).samples == record.samples


def test_polling_interval():
    day_end = NOW + 10 * 3600
    assert wl.next_poll_ts(NOW, [], False, day_end) == NOW + wl.QUIET_POLL_SECONDS
    # An hour before a watering: every 10 minutes.
    assert wl.next_poll_ts(NOW, [NOW + 1800], False, day_end) == NOW + 600
    # Watering in 2.5 h: wake up an hour before it.
    assert wl.next_poll_ts(NOW, [NOW + 9000], False, day_end) == NOW + 9000 - 3600
    # While watering, every 10 minutes.
    assert wl.next_poll_ts(NOW, [], True, day_end) == NOW + 600
    # The 23:55 poll comes first when it is sooner.
    assert wl.next_poll_ts(NOW, [], False, NOW + 1200) == NOW + 1200


def test_nan_infinity_and_negative_totals_are_not_rain():
    for bad in (float("nan"), float("inf"), -float("inf"), -0.5):
        state = StationState()
        assert wl.check_station(state, Observation(bad, NOW - 60, TODAY), NOW, TODAY) is None, bad
        assert state.status == "spike"
