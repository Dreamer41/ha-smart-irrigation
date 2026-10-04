"""Rolling rain-window tracker.

Replaces the 8 separate `platform: statistics` sensors (Rain Past
15/30/60min, 24h, 3d, 4d, 7d, 14d) that fed off `sensor.rain_lifetime_mm`
(a monotonically-increasing counter: tips * mm_per_tip, `restore: true`).

Because the source is monotonic non-decreasing, "sum of nonnegative
differences within the last N minutes" reduces to:

    latest_cumulative_mm - cumulative_mm_at_window_start

which is what `window_sum_mm` below computes from a pruned list of
(timestamp, cumulative_mm) samples recorded on every tip.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Rolling rain windows this integration tracks internally (replaces the 8
# separate `platform: statistics` sensors keyed off sensor.rain_lifetime_mm).
RAIN_WINDOWS_MINUTES = {
    "15min": 15,
    "30min": 30,
    "60min": 60,
    "24h": 24 * 60,
    "3d": 3 * 24 * 60,
    "4d": 4 * 24 * 60,
    "7d": 7 * 24 * 60,
    "14d": 14 * 24 * 60,
}
# The "raining now" windows: only rain known to be recent counts here, so
# manual rain (entered after the fact) is left out of them.
SHORT_RAIN_WINDOWS = {"15min", "30min", "60min"}
# Manual rain can be entered this far back (the longest window above).
MANUAL_RAIN_MAX_AGE_MINUTES = 14 * 24 * 60
# How long raw tip samples are kept before being pruned (must cover the
# longest rolling window above, i.e. 14 days) plus slack.
RAIN_SAMPLE_RETENTION_MINUTES = 15 * 24 * 60


@dataclass
class RainWindowTracker:
    samples: list[tuple[float, float]] = field(default_factory=list)  # (ts, cumulative_mm), ts ascending

    def record(self, ts: float, cumulative_mm: float) -> None:
        """Record a new cumulative rain reading (call on every tip)."""
        if self.samples and ts < self.samples[-1][0]:
            # Defensive: ignore out-of-order samples (e.g. clock skew on restore)
            return
        self.samples.append((ts, cumulative_mm))
        self.prune(ts)

    def prune(self, now_ts: float) -> None:
        cutoff = now_ts - RAIN_SAMPLE_RETENTION_MINUTES * 60
        # Keep one sample at-or-before cutoff so window baselines stay accurate,
        # drop the rest that are older than that.
        keep_from = 0
        for i, (t, _c) in enumerate(self.samples):
            if t <= cutoff:
                keep_from = i
            else:
                break
        if keep_from > 0:
            self.samples = self.samples[keep_from:]

    def latest_cumulative(self) -> float:
        return self.samples[-1][1] if self.samples else 0.0

    def window_sum_mm(self, window_minutes: float, now_ts: float) -> float:
        if not self.samples:
            return 0.0
        window_start = now_ts - window_minutes * 60
        baseline = self.samples[0][1]
        latest = self.samples[-1][1]
        for t, c in self.samples:
            if t <= window_start:
                baseline = c
            else:
                break
        return max(latest - baseline, 0.0)

    def insert(self, ts: float, mm: float) -> None:
        """Add `mm` of rain at `ts`, which may be in the past (manual rain
        entered later): every later sample moves up by `mm`, so the total
        stays monotonic and every window that covers `ts` gains `mm`."""
        index = 0
        while index < len(self.samples) and self.samples[index][0] <= ts:
            index += 1
        before = self.samples[index - 1][1] if index else (self.samples[0][1] if self.samples else 0.0)
        new = [(ts, before + mm)]
        if not index:
            new.insert(0, (ts - 1.0, before))  # a baseline, so windows see the step
        self.samples = self.samples[:index] + new + [(t, c + mm) for t, c in self.samples[index:]]
        self.prune(max(ts, self.samples[-1][0]))

    def sum_between_mm(self, start_ts: float, end_ts: float) -> float:
        """Rain between two times (e.g. one past local day)."""
        if not self.samples:
            return 0.0

        def at(when: float) -> float:
            value = self.samples[0][1]
            for t, c in self.samples:
                if t > when:
                    break
                value = c
            return value

        return max(at(end_ts) - at(start_ts), 0.0)

    def all_windows_mm(self, now_ts: float) -> dict[str, float]:
        return {name: self.window_sum_mm(minutes, now_ts) for name, minutes in RAIN_WINDOWS_MINUTES.items()}

    def as_persisted(self) -> list[list[float]]:
        return [[t, c] for t, c in self.samples]

    @classmethod
    def from_persisted(cls, data: list[list[float]] | None) -> RainWindowTracker:
        if not data:
            return cls()
        return cls(samples=[(row[0], row[1]) for row in data])
