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

from .const import DEFAULT_DEMAND_MODEL, DEFAULT_FERTILIZING_INTERVAL, DEFAULT_HEALTH_STATUS, DOMAIN, RAIN_HISTORY_DEPTH_DAYS, STORAGE_VERSION
from .rain_tracker import RainWindowTracker


@dataclass
class IrrigationState:
    # Timestamps (epoch seconds), None until first occurrence
    last_deep_soak_ts: float | None = None
    last_routine_ts: float | None = None
    last_significant_rain_ts: float | None = None
    # When the last heavy-rain alert was actually sent (one per storm).
    last_significant_rain_alert_ts: float | None = None

    # rain_day_1 (yesterday) .. rain_day_10, shifted at 23:59:50
    rain_day_history_mm: list[float] = field(default_factory=lambda: [0.0] * RAIN_HISTORY_DEPTH_DAYS)
    # outdoor_peak_day_1 (yesterday) .. outdoor_peak_day_3
    peak_temp_day_history_c: list[float | None] = field(default_factory=lambda: [None, None, None])
    # Matching daily-minimum register (same shift timing, same depth), added
    # for the Hargreaves ET0 estimate. Unlike the peak register it never
    # carries a fallback value forward -- a day with no readings stays None
    # and is simply left out of the ET0 average.
    min_temp_day_history_c: list[float | None] = field(default_factory=lambda: [None, None, None])

    # Today's in-progress bookkeeping (reset at local midnight)
    today_date_iso: str | None = None
    today_peak_temp_c: float | None = None
    today_min_temp_c: float | None = None
    rain_midnight_baseline_mm: float = 0.0

    # Rain counter reset/glitch handling (calculations.track_tip_total):
    # an ever-growing tip total built from the raw counter, the last raw
    # count seen, and -- after the count went down -- where it was before
    # and when, so a quick jump back can be recognised as a glitch.
    rain_counter_total_tips: float | None = None
    rain_counter_last_tips: float | None = None
    rain_counter_drop_from: float | None = None
    rain_counter_drop_ts: float | None = None
    rain_counter_since_drop_tips: float = 0.0

    # Mutex / safety
    lock_on: bool = False
    lock_set_ts: float | None = None
    # The valve the lock was taken for. If a cycle's valve can't be confirmed
    # closed the lock is kept, and the restart safety check closes THIS valve
    # -- even if the zone's valve setting has changed since.
    lock_valve: str | None = None
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

    # Growth-stage auto-ramp (optional, off by default) -- set via the
    # "Planting / Transplant Date" datetime entity. None means "not set",
    # in which case the ramp is never applied regardless of the configured
    # profile, same as leaving the other three "last event" fields unset.
    planting_date_ts: float | None = None

    # Rolling same-day total across BOTH cycles, backing the max-daily-
    # runtime safety cap. Reset at local midnight alongside the other
    # "today" bookkeeping (see ZoneFlowController._start_new_day).
    today_runtime_minutes: float = 0.0

    # Most recent completed cycle's measured water use, from the optional
    # flow-meter entity (None if no flow meter is configured, or if the
    # meter's reading couldn't be read at both ends of the cycle).
    last_cycle_water_liters: float | None = None

    # Live dashboard overrides (select.py) -- both are pure convenience
    # layers on top of the config-flow/planting-date-driven values, not a
    # replacement for them. None/"auto" always means "behave exactly as
    # before this feature existed."
    soil_type_override: str | None = None
    growth_stage_mode: str = "auto"

    # Live override of the growth-ramp profile itself (which curve this
    # zone follows), same "checked first, no reload" pattern as
    # soil_type_override -- lets a person switch to "custom" (or back) from
    # the dashboard instead of Settings -> Configure. None means "use the
    # config-flow/options value," exactly as before this existed.
    growth_ramp_profile_override: str | None = None

    # Pure human journal fields (select.py / text.py) -- see const.py's
    # HEALTH_STATUS_OPTIONS comment. Nothing in the controller reads either
    # one; they exist purely for a person to record how the zone's actually
    # doing, with no effect on scheduling or watering amounts.
    health_status: str = DEFAULT_HEALTH_STATUS
    health_notes: str = ""

    # Fertilizing journal -- same pure-journal rule as the health fields
    # directly above (see const.py's FERTILIZING_INTERVAL_OPTIONS comment).
    # last_fertilizing_ts is None until someone records a feed.
    last_fertilizing_ts: float | None = None
    fertilizing_interval_months: str = DEFAULT_FERTILIZING_INTERVAL

    # Which routine weekly-target model this zone uses -- see const.py's
    # DEMAND_MODEL_* comment. Defaults to the original temperature tiers.
    demand_model: str = DEFAULT_DEMAND_MODEL

    # Snooze Today (button.py's ZoneFlowSnoozeTodayButton): the local
    # calendar date (ISO "YYYY-MM-DD") this snooze applies to, or None
    # when not snoozed. Compared against the local date at each cycle's
    # run-gate, not a timestamp/countdown, so it always means "skip
    # whichever of today's scheduled runs hasn't happened yet" regardless
    # of what time of day the button was pressed, and it can never leak
    # into skipping tomorrow's run by drifting past a fixed duration.
    snooze_date_iso: str | None = None

    # Self-tuning intervals (controller.py's _register_self_tune_signal) --
    # see const.py's SELF_TUNE_* comment. Two independent rolling counts,
    # each reset by the other, so a mixed pattern of presses never quietly
    # accumulates toward a threshold on either side.
    self_tune_early_streak: int = 0
    self_tune_skip_streak: int = 0

    def rain_tracker(self) -> RainWindowTracker:
        return RainWindowTracker.from_persisted(self.rain_samples)

    def save_rain_tracker(self, tracker: RainWindowTracker) -> None:
        self.rain_samples = tracker.as_persisted()


class IrrigationStateStore:
    """Thin async wrapper around HA's Store for IrrigationState."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}")
        self.state = IrrigationState()
        # Set when the zone unloads: a reloaded zone has its own store, and a
        # leftover task of the old one must never overwrite what it loaded.
        self.closed = False

    async def async_load(self) -> IrrigationState:
        raw = await self._store.async_load()
        if raw:
            # Merge to tolerate future fields being added without migration.
            # Merge onto the defaults so fields added later need no
            # migration, and drop keys this version doesn't know (e.g. after
            # a downgrade) instead of failing to load the zone.
            merged = asdict(IrrigationState())
            merged.update({k: v for k, v in raw.items() if k in merged})
            self.state = IrrigationState(**merged)
        return self.state

    async def async_save(self) -> None:
        if self.closed:
            return
        await self._store.async_save(asdict(self.state))
