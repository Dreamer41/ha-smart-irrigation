"""Unit tests for the rolling rain-window tracker (no HA dependency)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "zoneflow"))

from rain_tracker import RainWindowTracker  # noqa: E402


def test_window_sum_only_counts_tips_after_window_start():
    tracker = RainWindowTracker()
    now = 1_000_000.0
    tracker.record(now - 3600, 5.0)  # 1h ago: outside a 30-min window
    tracker.record(now - 600, 8.0)  # 10 min ago: inside a 30-min window
    assert tracker.window_sum_mm(30, now) == 3.0  # 8.0 - 5.0
    # A 120-min window doesn't reach far enough back to see anything before
    # the first known sample, so it can only account for the delta since
    # then (this matches the real integration, which always seeds an
    # anchor sample from the live counter on startup before anything else
    # is recorded — see test_seeded_anchor_makes_first_real_tip_count_in_full).
    assert tracker.window_sum_mm(120, now) == 3.0


def test_seeded_anchor_makes_first_real_tip_count_in_full():
    tracker = RainWindowTracker()
    now = 1_000_000.0
    tracker.record(now - 3600 * 24, 0.0)  # seeded anchor, as done on integration startup
    tracker.record(now - 600, 8.0)  # first real tip since then
    assert tracker.window_sum_mm(120, now) == 8.0


def test_no_samples_returns_zero():
    tracker = RainWindowTracker()
    assert tracker.window_sum_mm(60, 1_000_000.0) == 0.0


def test_monotonic_source_never_goes_negative():
    tracker = RainWindowTracker()
    now = 1_000_000.0
    tracker.record(now - 100, 10.0)
    tracker.record(now - 50, 10.0)  # flat (no new tips) must not go negative
    assert tracker.window_sum_mm(10, now) == 0.0


def test_prune_keeps_one_anchor_before_cutoff_and_drops_the_rest():
    tracker = RainWindowTracker()
    now = 2_000_000.0
    retention_cutoff = now - 15 * 24 * 60 * 60
    very_old_ts = retention_cutoff - 10 * 24 * 60 * 60  # long before the anchor
    anchor_ts = retention_cutoff - 60  # just before the retention cutoff
    tracker.record(very_old_ts, 1.0)
    tracker.record(anchor_ts, 2.0)
    tracker.record(now - 60, 4.0)
    tracker.prune(now)
    # The very old sample is gone, but the one anchor at-or-before the
    # cutoff is deliberately kept so window baselines stay correct.
    assert (very_old_ts, 1.0) not in tracker.samples
    assert (anchor_ts, 2.0) in tracker.samples
    # 14d window reaches back to the retention cutoff, which is right after
    # the anchor -> full delta since the anchor counts.
    assert tracker.window_sum_mm(14 * 24 * 60, now) == 2.0


def test_round_trip_persistence():
    tracker = RainWindowTracker()
    tracker.record(100.0, 1.0)
    tracker.record(200.0, 2.5)
    restored = RainWindowTracker.from_persisted(tracker.as_persisted())
    assert restored.samples == tracker.samples


def test_insert_into_an_empty_tracker_counts_in_full():
    tracker = RainWindowTracker()
    now = 1_000_000.0
    tracker.insert(now - 600, 5.0)
    assert tracker.window_sum_mm(30, now) == 5.0
    assert tracker.window_sum_mm(24 * 60, now) == 5.0


def test_insert_in_the_past_moves_later_samples_up():
    tracker = RainWindowTracker()
    now = 1_000_000.0
    tracker.insert(now - 600, 5.0)
    tracker.insert(now - 3 * 3600, 2.0)  # entered later, fell earlier
    assert tracker.latest_cumulative() == 7.0
    assert tracker.window_sum_mm(60, now) == 5.0  # only the recent one
    assert tracker.window_sum_mm(24 * 60, now) == 7.0
    assert [c for _t, c in tracker.samples] == sorted(c for _t, c in tracker.samples)


def test_sum_between_one_day():
    tracker = RainWindowTracker()
    day = 86400.0
    tracker.insert(10 * day + 100, 3.0)
    tracker.insert(11 * day + 100, 4.0)
    assert tracker.sum_between_mm(10 * day, 11 * day) == 3.0
    assert tracker.sum_between_mm(11 * day, 12 * day) == 4.0
    assert tracker.sum_between_mm(12 * day, 13 * day) == 0.0
