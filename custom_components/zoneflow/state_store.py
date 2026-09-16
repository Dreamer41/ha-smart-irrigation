"""Persisted state for the ZoneFlow integration.

Replaces the input_datetime / input_boolean helpers and the rain_day_1-10 /
outdoor_peak_day_1-3 input_number "shift registers" that the YAML automation
used as its memory. All of it lives in one Store file so it survives HA
restarts, same as those helpers did (they're `restore: true` / persisted by
HA's own state machine).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, RAIN_HISTORY_DEPTH_DAYS, STORAGE_VERSION
from .rain_tracker import RainWindowTracker


@dataclass
class IrrigationState:
    # Timestamps (epoch seconds), None until first occurrence
    last_deep_soak_ts: float | None = None
    last_routine_ts: float | None = None
    last_significant_rain_ts: float | None = None

    # rain_day_1 (yesterday) .. rain_day_10, shifted at 23:59:50
    rain_day_history_mm: list[float] = field(default_factory=lambda: [0.0] * RAIN_HISTORY_DEPTH_DAYS)
    # outdoor_peak_day_1 (yesterday) .. outdoor_peak_day_3
    peak_temp_day_history_c: list[float | None] = field(default_factory=lambda: [None, None, None])

    # Today's in-progress bookkeeping (reset at local midnight)
    today_date_iso: str | None = None
    today_peak_temp_c: float | None = None
    rain_midnight_baseline_mm: float = 0.0

    # Mutex / safety
    lock_on: bool = False
    lock_set_ts: float | None = None
    abort_on: bool = False

    # Rolling rain window tracker (own dataclass, serialized separately)
    rain_samples: list[list[float]] = field(default_factory=list)

    # Edge-detection memory for the significant-rain thresholds, so restarts
    # don't spuriously re-fire "just crossed the threshold" logic; not in the
    # original YAML (numeric_state triggers keep this implicitly) but needed
    # here since we evaluate the thresholds on a timer instead.
    rain_threshold_flags: dict[str, bool] = field(
        default_factory=lambda: {"24h": False, "4d": False, "7d": False}
    )

    # Forecast gate: how many consecutive scheduled runs in a row have been
    # held off because rain was forecast, and when the streak started (used
    # to measure "no rain actually fell since then" against the per-zone
    # forecast_dry_override_days number). Deep soak and routine are tracked
    # independently since they run on different schedules.
    forecast_deep_soak_skip_count: int = 0
    forecast_deep_soak_skip_start_ts: float | None = None
    forecast_routine_skip_count: int = 0
    forecast_routine_skip_start_ts: float | None = None

    def rain_tracker(self) -> RainWindowTracker:
        return RainWindowTracker.from_persisted(self.rain_samples)

    def save_rain_tracker(self, tracker: RainWindowTracker) -> None:
        self.rain_samples = tracker.as_persisted()


class IrrigationStateStore:
    """Thin async wrapper around HA's Store for IrrigationState."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}")
        self.state = IrrigationState()

    async def async_load(self) -> IrrigationState:
        raw = await self._store.async_load()
        if raw:
            # Merge to tolerate future fields being added without migration.
            defaults = asdict(IrrigationState())
            defaults.update(raw)
            self.state = IrrigationState(**{k: v for k, v in defaults.items() if k in defaults})
        return self.state

    async def async_save(self) -> None:
        await self._store.async_save(asdict(self.state))
