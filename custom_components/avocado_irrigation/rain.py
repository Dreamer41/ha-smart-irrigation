"""Rainfall accumulation and rolling-window helpers."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class RainWindow:
    """Rain accumulated inside a rolling window."""
    hours: int
    millimeters: float


class RainAccumulator:
    """Tip-driven lifetime rain accumulator with rolling windows.

    The integration keeps the lifetime total monotonic and derives rolling
    rainfall from tip timestamps. This mirrors the reference architecture:
    lifetime counter -> rolling rainfall, avoiding snapshot double counting.
    """

    def __init__(self, mm_per_tip: float = 0.3) -> None:
        self.mm_per_tip = max(mm_per_tip, 0.0)
        self.total_tips = 0
        self._tips: deque[datetime] = deque()

    def add_tip(self, when: datetime) -> float:
        """Record one bucket tip and return the new lifetime rainfall."""
        self.total_tips += 1
        self._tips.append(when)
        return self.total_mm

    @property
    def total_mm(self) -> float:
        """Return lifetime accumulated rainfall."""
        return self.total_tips * self.mm_per_tip

    def rainfall_since(self, now: datetime, hours: int) -> float:
        """Return rainfall from tips in the requested rolling window."""
        cutoff = now - timedelta(hours=hours)
        while self._tips and self._tips[0] < cutoff:
            self._tips.popleft()
        return len(self._tips) * self.mm_per_tip

    def windows(self, now: datetime) -> tuple[RainWindow, ...]:
        """Return the standard irrigation rainfall windows."""
        return tuple(
            RainWindow(hours=h, millimeters=self.rainfall_since(now, h))
            for h in (24, 96, 168, 336)
        )
