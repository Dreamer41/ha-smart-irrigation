"""Core scheduler + safety state machine.

This is a line-by-line behavioral port of the confirmed-final
automations.yaml (avocado_deep_soak, avocado_routine_irrigation, and all
five watchdogs). Manual buttons/services call the exact same
`run_deep_soak` / `run_routine_irrigation` coroutines as the daily time
triggers, so there is no separate "manual" code path to drift out of sync
— that drift (manual vs. scheduled diverging) was part of what went wrong
with the earlier ChatGPT-drafted branch.

One deliberate, disclosed simplification vs. the YAML: the original had
two near-duplicate "clear a stuck lock on HA restart" automations
(`avocado_stale_lock_on_startup`, which also force-offs the valve, and
`avocado_startup_lock_reset`, a strict subset of the same behavior). This
port merges them into one `_on_startup` handler that does everything the
richer of the two did. Flagging this explicitly per your rule about never
silently merging/changing behavior beyond what was asked.
"""
from __future__ import annotations

import asyncio
import contextlib
import csv
import logging
from datetime import time as dt_time, timedelta
from typing import Any

from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_state_change_event,
    async_track_sunrise,
    async_track_sunset,
    async_track_time_change,
)
import homeassistant.util.dt as dt_util

from . import calculations as calc
from .const import (
    CONF_CSV_PATH,
    CONF_DEEP_SOAK_ENABLED,
    CONF_DEEP_SOAK_SUN_MODE,
    CONF_DEEP_SOAK_SUN_OFFSET_MINUTES,
    CONF_DEEP_SOAK_TIME,
    CONF_DRAINAGE,
    CONF_FLOW_METER_ENTITY,
    CONF_GROWTH_RAMP_PROFILE,
    CONF_IRRIGATION_METHOD,
    CONF_NOTIFY_ENTITY,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_PUMP_ID,
    CONF_PUMP_POWER_ENTITY,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_ROUTINE_SUN_MODE,
    CONF_ROUTINE_SUN_OFFSET_MINUTES,
    CONF_ROUTINE_TIME,
    CONF_SLOPE,
    CONF_SOIL_MOISTURE_ENTITY,
    CONF_SOIL_TYPE,
    CONF_VALVE_ENTITY,
    CONF_WEATHER_ENTITY,
    DAILY_SHIFT_TIME,
    DEEP_SOAK_INTERVAL_BUFFER_SECONDS,
    DEEP_SOAK_MIN_PULSE_MINUTES,
    DEFAULT_DEEP_SOAK_ENABLED,
    DEFAULT_DRAINAGE,
    DEFAULT_GROWTH_RAMP_PROFILE,
    DEFAULT_IRRIGATION_METHOD,
    DEFAULT_SLOPE,
    DEFAULT_SOIL_TYPE,
    DOMAIN,
    EVENT_LOG,
    GROWTH_RAMP_CURVES,
    GROWTH_RAMP_CUSTOM,
    GROWTH_RAMP_OFF,
    GROWTH_STAGE_MODE_AUTO,
    NUMBER_DEFAULTS,
    NUMBER_DEFS,
    POWER_LOSS_GRACE_MINUTES,
    PUMP_POWER_WAIT_TIMEOUT_SECONDS,
    ROUTINE_INTERVAL_BUFFER_SECONDS,
    ROUTINE_MIN_PULSE_MINUTES,
    SELF_TUNE_ADJUST_STEP_DAYS,
    SELF_TUNE_STREAK_THRESHOLD,
    SIGNIFICANT_RAIN_24H_MM,
    SIGNIFICANT_RAIN_4D_MM,
    SIGNIFICANT_RAIN_7D_MM,
    STALE_LOCK_MINUTES,
    STARTUP_GRACE_SECONDS,
    SUN_MODE_AFTER_SUNRISE,
    SUN_MODE_AFTER_SUNSET,
    SUN_MODE_BEFORE_SUNRISE,
    SUN_MODE_BEFORE_SUNSET,
    SUN_MODE_FIXED,
    DEFAULT_SUN_MODE,
    DEFAULT_SUN_OFFSET_MINUTES,
    VALVE_STUCK_ON_MINUTES,
)
from .state_store import IrrigationStateStore

_LOGGER = logging.getLogger(__name__)


def _parse_hms(value: str) -> dt_time:
    h, m, s = (int(p) for p in value.split(":"))
    return dt_time(hour=h, minute=m, second=s)


class ZoneFlowController:
    """Owns all scheduling, safety watchdogs, and irrigation state."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        self.store = IrrigationStateStore(hass, entry.entry_id)
        self.numbers: dict[str, Any] = {}  # key -> NumberEntity, registered at platform setup
        self._unsubs: list[Any] = []
        self._valve_stuck_cancel = None
        self._power_loss_cancel = None
        self._lock_stale_cancel = None
        self._abort_event = asyncio.Event()

    # ------------------------------------------------------------------
    # Config accessors
    # ------------------------------------------------------------------
    # NOTE on the options-first pattern below: the options flow (§ config
    # flow "Configure") writes into entry.options, not entry.data -- every
    # property here must check entry.options first (falling back to
    # entry.data, which is what the entry has at initial creation) or a
    # change made through Options silently never takes effect. This used to
    # be inconsistent (several of these read entry.data only), which meant
    # reconfiguring e.g. the pump-power entity or soil type via Options
    # looked like it saved (entry.options really did update) but the
    # running controller kept using the original value forever. Fixed here
    # across the board rather than just for the new pump_id field below.
    @property
    def valve_entity(self) -> str:
        """The only entity that is truly mandatory -- ZoneFlow cannot
        irrigate without something to open."""
        return self.entry.options.get(CONF_VALVE_ENTITY, self.entry.data[CONF_VALVE_ENTITY])

    @property
    def pump_power_entity(self) -> str | None:
        """Optional. Without it, the pump-audit watchdog is skipped
        entirely (see _execute_pulses) rather than warning on every pulse
        about a "low" reading that was never real to begin with."""
        return self.entry.options.get(CONF_PUMP_POWER_ENTITY, self.entry.data.get(CONF_PUMP_POWER_ENTITY))

    @property
    def pump_id(self) -> str | None:
        """Optional, arbitrary string naming which physical pump this
        zone's valve draws from -- see const.py's CONF_PUMP_ID comment and
        _pump_lock_key below for why this is separate from
        pump_power_entity. Empty string (the config-flow field's default)
        and unset both mean "no explicit id given," normalized to None."""
        return self.entry.options.get(CONF_PUMP_ID, self.entry.data.get(CONF_PUMP_ID)) or None

    @property
    def rain_counter_entity(self) -> str | None:
        """Optional. Without it, every rain-aware gate simply never fires
        -- rain_windows()/today_rain_mm() naturally return 0.0 for an
        empty tracker, which is the correct "assume no rain" fallback."""
        return self.entry.options.get(CONF_RAIN_COUNTER_ENTITY, self.entry.data.get(CONF_RAIN_COUNTER_ENTITY))

    @property
    def outdoor_temp_entity(self) -> str | None:
        """Optional. Without it (or if it's currently unavailable/unknown
        -- see effective_avg_peak_temp), the hot/cool tier logic falls back
        to the "normal" tier rather than freezing on stale history."""
        return self.entry.options.get(CONF_OUTDOOR_TEMP_ENTITY, self.entry.data.get(CONF_OUTDOOR_TEMP_ENTITY))

    @property
    def flow_meter_entity(self) -> str | None:
        """Optional cumulative-volume sensor (e.g. a pulse flow meter).
        When set, backs the "Last Cycle Water Delivered" diagnostic and a
        no-flow-detected check that can substitute for the pump-power audit
        when no pump-power sensor is configured."""
        return self.entry.options.get(CONF_FLOW_METER_ENTITY, self.entry.data.get(CONF_FLOW_METER_ENTITY))

    @property
    def soil_moisture_entity(self) -> str | None:
        """Optional % soil-moisture sensor -- see const.py's
        CONF_SOIL_MOISTURE_ENTITY comment and run_routine_irrigation's
        dry/wet threshold gate."""
        return self.entry.options.get(CONF_SOIL_MOISTURE_ENTITY, self.entry.data.get(CONF_SOIL_MOISTURE_ENTITY))

    @property
    def soil_type(self) -> str:
        """The live dashboard select (select.py) can override this without
        touching the config entry at all -- checked first so it always wins
        once set, with no reload required. None (never touched, the default)
        falls through to the config-flow/options value exactly as before."""
        override = self.store.state.soil_type_override
        if override is not None:
            return override
        return self.entry.options.get(CONF_SOIL_TYPE, self.entry.data.get(CONF_SOIL_TYPE, DEFAULT_SOIL_TYPE))

    @property
    def drainage(self) -> str:
        return self.entry.options.get(CONF_DRAINAGE, self.entry.data.get(CONF_DRAINAGE, DEFAULT_DRAINAGE))

    @property
    def slope(self) -> str:
        return self.entry.options.get(CONF_SLOPE, self.entry.data.get(CONF_SLOPE, DEFAULT_SLOPE))

    @property
    def irrigation_method(self) -> str:
        return self.entry.options.get(
            CONF_IRRIGATION_METHOD, self.entry.data.get(CONF_IRRIGATION_METHOD, DEFAULT_IRRIGATION_METHOD)
        )

    @property
    def growth_ramp_profile(self) -> str:
        """Same live-override pattern as soil_type: select.py's growth-ramp-
        profile select can override this without a config-entry reload."""
        override = self.store.state.growth_ramp_profile_override
        if override is not None:
            return override
        return self.entry.options.get(
            CONF_GROWTH_RAMP_PROFILE, self.entry.data.get(CONF_GROWTH_RAMP_PROFILE, DEFAULT_GROWTH_RAMP_PROFILE)
        )

    @property
    def notify_entity(self) -> str | None:
        return self.entry.options.get(CONF_NOTIFY_ENTITY, self.entry.data.get(CONF_NOTIFY_ENTITY))

    @property
    def weather_entity(self) -> str | None:
        return self.entry.options.get(CONF_WEATHER_ENTITY, self.entry.data.get(CONF_WEATHER_ENTITY))

    @property
    def csv_path(self) -> str:
        return self.entry.options.get(CONF_CSV_PATH, self.entry.data.get(CONF_CSV_PATH))

    @property
    def deep_soak_enabled(self) -> bool:
        """False means this zone's deep-soak cycle is turned off entirely --
        see run_deep_soak()'s gate. Default True (not False) so an existing
        zone from before this field existed keeps running deep soak exactly
        as before; see const.py's CONF_DEEP_SOAK_ENABLED comment."""
        return self.entry.options.get(
            CONF_DEEP_SOAK_ENABLED, self.entry.data.get(CONF_DEEP_SOAK_ENABLED, DEFAULT_DEEP_SOAK_ENABLED)
        )

    @property
    def deep_soak_time(self) -> dt_time:
        return _parse_hms(self.entry.options.get(CONF_DEEP_SOAK_TIME, self.entry.data.get(CONF_DEEP_SOAK_TIME)))

    @property
    def routine_time(self) -> dt_time:
        return _parse_hms(self.entry.options.get(CONF_ROUTINE_TIME, self.entry.data.get(CONF_ROUTINE_TIME)))

    @property
    def deep_soak_sun_mode(self) -> str:
        return self.entry.options.get(
            CONF_DEEP_SOAK_SUN_MODE, self.entry.data.get(CONF_DEEP_SOAK_SUN_MODE, DEFAULT_SUN_MODE)
        )

    @property
    def deep_soak_sun_offset_minutes(self) -> float:
        return float(
            self.entry.options.get(
                CONF_DEEP_SOAK_SUN_OFFSET_MINUTES,
                self.entry.data.get(CONF_DEEP_SOAK_SUN_OFFSET_MINUTES, DEFAULT_SUN_OFFSET_MINUTES),
            )
        )

    @property
    def routine_sun_mode(self) -> str:
        return self.entry.options.get(
            CONF_ROUTINE_SUN_MODE, self.entry.data.get(CONF_ROUTINE_SUN_MODE, DEFAULT_SUN_MODE)
        )

    @property
    def routine_sun_offset_minutes(self) -> float:
        return float(
            self.entry.options.get(
                CONF_ROUTINE_SUN_OFFSET_MINUTES,
                self.entry.data.get(CONF_ROUTINE_SUN_OFFSET_MINUTES, DEFAULT_SUN_OFFSET_MINUTES),
            )
        )

    def number(self, key: str) -> float:
        entity = self.numbers.get(key)
        if entity is not None and entity.native_value is not None:
            return float(entity.native_value)
        return NUMBER_DEFAULTS[key]

    def register_number(self, key: str, entity: Any) -> None:
        self.numbers[key] = entity

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def async_setup(self) -> None:
        await self.store.async_load()
        state = self.store.state

        # Seed the rain window baseline from the counter's current value
        # *before* anything else touches the tracker, so a fresh install (or
        # a restart with no persisted samples yet) has a sane baseline from
        # the first moment rather than momentarily reading 0.0. Skipped
        # entirely when no rain gauge is configured -- the tracker simply
        # stays empty, and rain_windows()/today_rain_mm() already return
        # 0.0 for an empty tracker (the correct "assume no rain" fallback).
        if self.rain_counter_entity:
            counter_state = self.hass.states.get(self.rain_counter_entity)
            if counter_state is not None:
                self._sync_rain_from_counter_state(counter_state, seed_only=True)

        if state.today_date_iso != dt_util.now().date().isoformat():
            self._start_new_day()
            await self.store.async_save()

        if state.lock_on and state.lock_set_ts:
            self._schedule_stale_lock_watchdog(state.lock_set_ts)
        if state.abort_on:
            self._abort_event.set()

        self._unsubs.append(
            self._track_schedule(self.deep_soak_sun_mode, self.deep_soak_sun_offset_minutes, self.deep_soak_time, self._on_deep_soak_time)
        )
        self._unsubs.append(
            self._track_schedule(self.routine_sun_mode, self.routine_sun_offset_minutes, self.routine_time, self._on_routine_time)
        )
        shift_time = _parse_hms(DAILY_SHIFT_TIME)
        self._unsubs.append(
            async_track_time_change(
                self.hass,
                self._on_daily_shift,
                hour=shift_time.hour,
                minute=shift_time.minute,
                second=shift_time.second,
            )
        )
        self._unsubs.append(
            async_track_state_change_event(self.hass, [self.valve_entity], self._on_valve_state_change)
        )
        if self.rain_counter_entity:
            self._unsubs.append(
                async_track_state_change_event(
                    self.hass, [self.rain_counter_entity], self._on_rain_counter_change
                )
            )
        if self.outdoor_temp_entity:
            self._unsubs.append(
                async_track_state_change_event(
                    self.hass, [self.outdoor_temp_entity], self._on_outdoor_temp_change
                )
            )
        self._unsubs.append(
            async_track_time_change(self.hass, self._on_midnight, hour=0, minute=0, second=0)
        )

        # _on_startup deliberately sleeps for STARTUP_GRACE_SECONDS (2 minutes)
        # before doing anything, so Home Assistant's config entries are almost
        # always still set up while hass.is_running is already True (it flips
        # true at the start of the STARTING phase, not the end). Scheduling
        # that sleep as a normal tracked task -- via hass.async_create_task,
        # or by handing an async callback straight to
        # bus.async_listen_once -- makes HA's own end-of-startup
        # async_block_till_done() wait on it too, which produces a scary
        # "something is blocking the start up phase" warning (and the
        # equivalent on every config-entry reload) even though nothing is
        # actually wrong. entry.async_create_background_task keeps the delay
        # working exactly as before but explicitly outside that wait, and
        # also auto-cancels it if the entry is unloaded before the grace
        # period elapses.
        def _schedule_on_startup(event=None) -> None:
            self.entry.async_create_background_task(
                self.hass, self._on_startup(event), name=f"{DOMAIN}_on_startup_{self.entry.entry_id}"
            )

        if self.hass.is_running:
            _schedule_on_startup()
        else:
            self._unsubs.append(self.hass.bus.async_listen_once("homeassistant_start", _schedule_on_startup))

    async def async_unload(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._valve_stuck_cancel:
            self._valve_stuck_cancel()
        if self._power_loss_cancel:
            self._power_loss_cancel()
        if self._lock_stale_cancel:
            self._lock_stale_cancel()

    # ------------------------------------------------------------------
    # Rain / temperature tracking
    # ------------------------------------------------------------------
    def _sync_rain_from_counter_state(self, new_state: State, seed_only: bool = False) -> None:
        state = self.store.state
        try:
            tips = float(new_state.state)
        except (TypeError, ValueError):
            return
        cumulative_mm = tips * self.number("rain_mm_per_tip")
        tracker = state.rain_tracker()
        if not seed_only:
            tracker.record(dt_util.utcnow().timestamp(), cumulative_mm)
            state.save_rain_tracker(tracker)
            self.hass.async_create_task(self.store.async_save())
            self._check_significant_rain(tracker)
        elif not tracker.samples:
            tracker.record(dt_util.utcnow().timestamp(), cumulative_mm)
            state.save_rain_tracker(tracker)

    @callback
    def _on_rain_counter_change(self, event: Event) -> None:
        new_state: State | None = event.data.get("new_state")
        if new_state is None:
            return
        self._sync_rain_from_counter_state(new_state)

    def _check_significant_rain(self, tracker) -> None:
        """Port of avocado_significant_rain_logger (edge-triggered)."""
        now_ts = dt_util.utcnow().timestamp()
        checks = {
            "24h": (tracker.window_sum_mm(24 * 60, now_ts), SIGNIFICANT_RAIN_24H_MM),
            "4d": (tracker.window_sum_mm(4 * 24 * 60, now_ts), SIGNIFICANT_RAIN_4D_MM),
            "7d": (tracker.window_sum_mm(7 * 24 * 60, now_ts), SIGNIFICANT_RAIN_7D_MM),
        }
        state = self.store.state
        fired = False
        for key, (value, threshold) in checks.items():
            was_above = state.rain_threshold_flags.get(key, False)
            is_above = value > threshold
            state.rain_threshold_flags[key] = is_above
            if is_above and not was_above:
                fired = True
        if fired:
            state.last_significant_rain_ts = now_ts
            self.hass.async_create_task(self.store.async_save())
            r24 = checks["24h"][0]
            r4d = checks["4d"][0]
            r7d = checks["7d"][0]
            self.hass.async_create_task(
                self._log_event(
                    event_type="Significant Rain",
                    status="Triggered",
                    target_mm=0.0,
                    deducted_mm=0.0,
                    runtime=0,
                    notify_phone=True,
                    phone_title="🌧️ Heavy Rain Event",
                    phone_msg=f"Heavy rain recorded (24h: {r24:.1f}mm). Dry-down timers updated.",
                    extra_log=f"Heavy rain recorded (24h: {r24:.1f}mm, 4d: {r4d:.1f}mm, 7d: {r7d:.1f}mm). Dry-down timer updated.",
                )
            )

    def _start_new_day(self, seed_temp: float | None = None) -> None:
        """Roll today's bookkeeping over: fresh peak-temp tracking and a new
        midnight rain baseline. Normally driven by `_on_midnight` (mirrors
        the trigger-based template sensor's `id: reset` branch at 00:00:00);
        also called defensively from `_on_outdoor_temp_change` and
        `async_setup` in case a midnight tick was missed (HA was restarting,
        etc.)."""
        state = self.store.state
        state.today_date_iso = dt_util.now().date().isoformat()
        state.today_peak_temp_c = seed_temp
        state.today_min_temp_c = seed_temp
        state.rain_midnight_baseline_mm = state.rain_tracker().latest_cumulative()
        state.today_runtime_minutes = 0.0

    @callback
    def _on_midnight(self, now) -> None:
        seed = None
        if self.outdoor_temp_entity:
            temp_state = self.hass.states.get(self.outdoor_temp_entity)
            if temp_state is not None:
                try:
                    seed = float(temp_state.state)
                except (TypeError, ValueError):
                    seed = None
        self._start_new_day(seed_temp=seed)
        self.hass.async_create_task(self.store.async_save())

    @callback
    def _on_outdoor_temp_change(self, event: Event) -> None:
        new_state: State | None = event.data.get("new_state")
        if new_state is None:
            return
        try:
            temp = float(new_state.state)
        except (TypeError, ValueError):
            return
        state = self.store.state
        today_iso = dt_util.now().date().isoformat()
        if state.today_date_iso != today_iso:
            # Defensive fallback: the 00:00:00 tick was missed (e.g. HA was
            # down at midnight). Roll the day over now, seeded with this
            # reading, instead of waiting for the next midnight.
            self._start_new_day(seed_temp=temp)
        else:
            # Minimum first, while today_peak_temp_c still shows whether the
            # day had readings before this one: a peak with no minimum only
            # happens on the day this version is first installed (the peak
            # has been tracked since midnight, the minimum hasn't), so that
            # partial day is left as None -- skipped for ET0 -- rather than
            # recorded with a too-narrow temperature range.
            if state.today_min_temp_c is not None:
                state.today_min_temp_c = min(temp, state.today_min_temp_c)
            elif state.today_peak_temp_c is None:
                state.today_min_temp_c = temp
            state.today_peak_temp_c = max(temp, state.today_peak_temp_c) if state.today_peak_temp_c is not None else temp
        self.hass.async_create_task(self.store.async_save())

    @callback
    def _on_daily_shift(self, now) -> None:
        """Port of shift_avocado_daily_peak_temps + shift_avocado_daily_rain
        (both fire at 23:59:50)."""
        state = self.store.state
        # Peak temp shift register
        today_max = state.today_peak_temp_c
        fallback = state.peak_temp_day_history_c[0] if state.peak_temp_day_history_c[0] is not None else 30.0
        state.peak_temp_day_history_c = [
            today_max if today_max is not None else fallback,
            state.peak_temp_day_history_c[0],
            state.peak_temp_day_history_c[1],
        ]
        # Daily-minimum shift register, for ET0 -- no fallback on purpose
        # (see state_store.py's min_temp_day_history_c comment).
        state.min_temp_day_history_c = [
            state.today_min_temp_c,
            state.min_temp_day_history_c[0],
            state.min_temp_day_history_c[1],
        ]
        # Rain day shift register (10-deep)
        today_rain = self.today_rain_mm()
        state.rain_day_history_mm = [today_rain, *state.rain_day_history_mm[:9]]
        self.hass.async_create_task(self.store.async_save())

    def today_rain_mm(self) -> float:
        state = self.store.state
        return max(state.rain_tracker().latest_cumulative() - state.rain_midnight_baseline_mm, 0.0)

    def avg_peak_temp(self) -> float:
        state = self.store.state
        return calc.three_day_average_peak_temp(state.peak_temp_day_history_c)

    def et0_daily_history(self) -> list[float | None]:
        """Hargreaves ET0 (mm/day) for each of the last three completed
        days, newest first, using Home Assistant's own configured home
        latitude. A day is None when it has no real min+max pair on record
        -- including the peak register's carried-forward fallback days,
        since those always have a None minimum alongside them."""
        state = self.store.state
        latitude = self.hass.config.latitude
        today = dt_util.now().date()
        values: list[float | None] = []
        for i, (t_min, t_max) in enumerate(zip(state.min_temp_day_history_c, state.peak_temp_day_history_c)):
            day = today - timedelta(days=i + 1)
            values.append(calc.hargreaves_et0(t_min, t_max, latitude, day.timetuple().tm_yday))
        return values

    def avg_et0(self) -> float | None:
        """3-day average reference ET0 (mm/day), or None until at least
        one full day of min/max tracking has been recorded. Display-only
        for now -- see calculations.py's ET0 section comment."""
        return calc.average_et0(self.et0_daily_history())

    def today_et0_so_far(self) -> float | None:
        """Today's ET0 from the min/max seen SO FAR -- informational only
        (it grows through the day as the temperature range widens)."""
        state = self.store.state
        return calc.hargreaves_et0(
            state.today_min_temp_c,
            state.today_peak_temp_c,
            self.hass.config.latitude,
            dt_util.now().date().timetuple().tm_yday,
        )

    def effective_avg_peak_temp(self) -> float | None:
        """The rolling 3-day average to use for the routine hot/cool/normal
        tier DECISION, as opposed to avg_peak_temp() above (which stays a
        plain historical value, used for display on the diagnostic sensor).

        Returns None -- meaning "use the normal tier", an explicit branch
        in calculations.routine_interval_days/routine_target_weekly_mm, not
        a numeric coincidence -- whenever there is no temperature sensor
        configured at all, OR the configured one is *currently*
        unavailable/unknown. Without this check, a sensor that goes dead
        mid-season would silently keep whatever tier its last real reading
        implied, indefinitely (peak_temp_day_history_c keeps carrying that
        stale value forward at each daily shift) -- this makes the fallback
        immediate instead, and it recovers automatically the moment the
        sensor reports a real value again."""
        entity_id = self.outdoor_temp_entity
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            return None
        return self.avg_peak_temp()

    def growth_ramp_fraction(self) -> float:
        """See const.py's GROWTH_RAMP_CURVES comment. Returns 1.0 (no
        adjustment) whenever the feature is off, or on but no planting date
        has been set yet -- an enabled-but-unconfigured ramp must never
        silently reduce watering.

        A manual override (select.py's growth-stage select, paired with the
        "growth_stage_override_pct" slider) takes precedence over the
        planting-date curve whenever it's active -- but, like the curve
        itself, ONLY while the zone's growth-ramp profile isn't "off": off
        must always mean "no adjustment, ever," regardless of what the
        override happens to be set to, or a person could accidentally scale
        down a mature-tree zone's watering just by touching the wrong
        dashboard slider."""
        profile = self.growth_ramp_profile
        if profile == GROWTH_RAMP_OFF:
            return 1.0
        if self.store.state.growth_stage_mode != GROWTH_STAGE_MODE_AUTO:
            return max(0.0, min(1.0, self.number("growth_stage_override_pct") / 100.0))
        planting_ts = self.store.state.planting_date_ts
        if planting_ts is None:
            return 1.0
        curve = self._custom_growth_ramp_curve() if profile == GROWTH_RAMP_CUSTOM else GROWTH_RAMP_CURVES.get(profile)
        if not curve:
            return 1.0
        days_since_planting = max((dt_util.utcnow().timestamp() - planting_ts) / 86400.0, 0.0)
        return calc.growth_ramp_fraction(days_since_planting, curve)

    def _custom_growth_ramp_curve(self) -> list[tuple[float, float]]:
        """Builds a curve from the "growth_ramp_custom_*" sliders (const.py),
        for a person's own plant-specific ramp instead of the three fixed
        presets -- e.g. a chili pepper and a young avocado tree can each get
        their own real numbers instead of both settling for whichever preset
        curve happens to fit best. Percent sliders are clamped to [0, 100]
        and the points are sorted by day before use, so entering the two
        midpoints (or the "day reaching 100%" point) out of order reorders
        the curve rather than producing a broken/backwards ramp -- and two
        points landing on the same day is handled the same way the fixed
        curves already handle it (calculations.growth_ramp_fraction treats
        equal-day points as a vertical step, not a divide-by-zero)."""
        def pct(key: str) -> float:
            return max(0.0, min(100.0, self.number(key))) / 100.0

        points = [
            (0.0, pct("growth_ramp_custom_start_pct")),
            (max(self.number("growth_ramp_custom_point1_day"), 0.0), pct("growth_ramp_custom_point1_pct")),
            (max(self.number("growth_ramp_custom_point2_day"), 0.0), pct("growth_ramp_custom_point2_pct")),
            (max(self.number("growth_ramp_custom_full_day"), 0.0), 1.0),
        ]
        return sorted(points, key=lambda p: p[0])

    def rain_windows(self) -> dict[str, float]:
        now_ts = dt_util.utcnow().timestamp()
        return self.store.state.rain_tracker().all_windows_mm(now_ts)

    def rain_since(self, since_ts: float) -> float:
        """Actual measured rain (mm) between `since_ts` and now -- used by
        the forecast dry-override to check "has it actually rained", as
        opposed to the fixed rolling windows in rain_windows()."""
        now_ts = dt_util.utcnow().timestamp()
        window_minutes = max(now_ts - since_ts, 0.0) / 60.0
        return self.store.state.rain_tracker().window_sum_mm(window_minutes, now_ts)

    # ------------------------------------------------------------------
    # Lock / abort helpers
    # ------------------------------------------------------------------
    async def _set_lock(self, on: bool) -> None:
        state = self.store.state
        state.lock_on = on
        state.lock_set_ts = dt_util.utcnow().timestamp() if on else None
        await self.store.async_save()
        if self._lock_stale_cancel:
            self._lock_stale_cancel()
            self._lock_stale_cancel = None
        if on:
            self._schedule_stale_lock_watchdog(state.lock_set_ts)

    async def _set_abort(self, on: bool) -> None:
        self.store.state.abort_on = on
        await self.store.async_save()
        if on:
            self._abort_event.set()
        else:
            self._abort_event.clear()

    def _schedule_stale_lock_watchdog(self, lock_set_ts: float) -> None:
        fire_at = dt_util.utc_from_timestamp(lock_set_ts + STALE_LOCK_MINUTES * 60)
        self._lock_stale_cancel = async_track_point_in_time(self.hass, self._on_stale_lock, fire_at)

    @callback
    def _on_stale_lock(self, now) -> None:
        """Port of avocado_mutex_safety_watchdog (lock stuck ON 180min)."""
        if not self.store.state.lock_on:
            return
        self.hass.async_create_task(self._fire_stale_lock())

    async def _fire_stale_lock(self) -> None:
        await self._set_lock(False)
        await self._log_event(
            event_type="Stale Lock Watchdog Fired",
            status="CRITICAL",
            target_mm=0.0,
            deducted_mm=0.0,
            runtime=0,
            notify_phone=True,
            phone_title="⚠️ IRRIGATION LOCK RESET",
            phone_msg="The irrigation lock was stuck ON for >3 hours. Auto-reset performed so future runs aren't blocked.",
        )

    # ------------------------------------------------------------------
    # Valve watchdogs: stuck-on (150min), power-loss mid-cycle (10min),
    # power-restore anomaly
    # ------------------------------------------------------------------
    @callback
    def _on_valve_state_change(self, event: Event) -> None:
        old_state: State | None = event.data.get("old_state")
        new_state: State | None = event.data.get("new_state")
        if new_state is None:
            return

        if self._valve_stuck_cancel:
            self._valve_stuck_cancel()
            self._valve_stuck_cancel = None
        if self._power_loss_cancel:
            self._power_loss_cancel()
            self._power_loss_cancel = None

        # Anchor to the state's own last_changed timestamp rather than
        # dt_util.utcnow() taken here -- this callback can run a moment
        # after the state actually changed (event-loop scheduling, or a
        # slow test/CI run), and anchoring to "now" at execution time lets
        # that gap silently steal minutes from the watchdog window.
        if new_state.state == "on":
            fire_at = new_state.last_changed + timedelta(minutes=VALVE_STUCK_ON_MINUTES)
            self._valve_stuck_cancel = async_track_point_in_time(self.hass, self._on_valve_stuck, fire_at)
        elif new_state.state == "unavailable":
            fire_at = new_state.last_changed + timedelta(minutes=POWER_LOSS_GRACE_MINUTES)
            self._power_loss_cancel = async_track_point_in_time(self.hass, self._on_power_loss, fire_at)

        if old_state is not None and old_state.state == "unavailable" and new_state.state != "unavailable":
            self.hass.async_create_task(self._on_power_restore(new_state))

    @callback
    def _on_valve_stuck(self, now) -> None:
        """Port of avocado_valve_safety_watchdog (150min stuck ON)."""
        self.hass.async_create_task(self._fire_valve_stuck())

    async def _fire_valve_stuck(self) -> None:
        await self.hass.services.async_call(
            "switch", "turn_off", {"entity_id": self.valve_entity}, blocking=True
        )
        await self._set_abort(True)
        await self._set_lock(False)
        await self._log_event(
            event_type="Valve Stuck Watchdog Fired",
            status="CRITICAL",
            target_mm=0.0,
            deducted_mm=0.0,
            runtime=150,
            notify_phone=True,
            phone_title="🚨 EMERGENCY: Valve Watchdog Fired",
            phone_msg="Valve stayed ON for 150 minutes continuously! Emergency shutdown executed to protect trees.",
        )

    @callback
    def _on_power_loss(self, now) -> None:
        """Port of avocado_power_loss_abort (unavailable 10min mid-cycle)."""
        if not self.store.state.lock_on:
            return
        self.hass.async_create_task(self._fire_power_loss())

    async def _fire_power_loss(self) -> None:
        await self._set_abort(True)
        await self._set_lock(False)
        await self._log_event(
            event_type="Power Loss Mid-Cycle",
            status="ABORTED",
            target_mm=0.0,
            deducted_mm=0.0,
            runtime=0,
            notify_phone=True,
            phone_title="🚨 Irrigation Power Loss",
            phone_msg="Valve/pump lost power for 10+ min mid-cycle. Irrigation aborted, lock cleared, will retry next scheduled cycle.",
        )

    async def _on_power_restore(self, new_state: State) -> None:
        """Port of avocado_power_restore_check."""
        if new_state.state == "on":
            await self.hass.services.async_call(
                "switch", "turn_off", {"entity_id": self.valve_entity}, blocking=True
            )
            await self._log_event(
                event_type="Power Restore Anomaly",
                status="CRITICAL",
                target_mm=0.0,
                deducted_mm=0.0,
                runtime=0,
                notify_phone=True,
                phone_title="🚨 Valve Anomaly After Power Restore",
                phone_msg="Valve reported ON after power restore — forced off. Check relay/wiring.",
            )
        else:
            _LOGGER.info("ZoneFlow: valve back online, confirmed %s (safe)", new_state.state)

    async def _on_startup(self, event) -> None:
        """Merged port of avocado_stale_lock_on_startup + avocado_startup_lock_reset."""
        await asyncio.sleep(STARTUP_GRACE_SECONDS)
        if not self.store.state.lock_on:
            return
        await self._set_lock(False)
        await self._set_abort(False)
        valve_state = self.hass.states.get(self.valve_entity)
        if valve_state is not None and valve_state.state not in ("unavailable", "off"):
            await self.hass.services.async_call(
                "switch", "turn_off", {"entity_id": self.valve_entity}, blocking=True
            )
        await self._log_event(
            event_type="Stale Lock Cleared On Startup",
            status="ABORTED",
            target_mm=0.0,
            deducted_mm=0.0,
            runtime=0,
            notify_phone=True,
            phone_title="🚨 Irrigation Lock Cleared (HA Restart)",
            phone_msg="HA restarted mid-cycle. Lock cleared, valve forced off if reachable. Will retry next scheduled cycle.",
        )

    # ------------------------------------------------------------------
    # Irrigation cycles
    # ------------------------------------------------------------------
    async def _pump_watts(self) -> float:
        entity_id = self.pump_power_entity
        if not entity_id:
            return 0.0
        state = self.hass.states.get(entity_id)
        try:
            return float(state.state) if state else 0.0
        except (TypeError, ValueError):
            return 0.0

    async def _flow_meter_reading(self) -> float | None:
        """Current cumulative reading of the optional flow-meter entity, or
        None if no flow meter is configured or its reading can't be parsed
        right now. None (not 0.0) so a caller can tell "no data" apart from
        "reads zero" -- delta math must never mix the two."""
        entity_id = self.flow_meter_entity
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        try:
            return float(state.state) if state else None
        except (TypeError, ValueError):
            return None

    async def _soil_moisture_pct(self) -> float | None:
        """Current soil-moisture reading (%), or None if no soil-moisture
        sensor is configured for this zone or its reading isn't currently
        parseable (missing entity, or state "unavailable"/"unknown" --
        float() raising ValueError on either of those strings is exactly
        what makes this fail open the same way _flow_meter_reading does).
        None here always means "no override -- defer to the modeled
        schedule", never "treat as 0% (bone dry)" or "100% (saturated)" --
        either numeric guess could force a wrong decision in either
        direction, where deferring to the existing time-interval schedule
        is always a safe, previously-correct fallback."""
        entity_id = self.soil_moisture_entity
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        try:
            return float(state.state) if state else None
        except (TypeError, ValueError):
            return None

    @property
    def _pump_lock_key(self) -> str:
        """Which physical pump this zone's valve draws from, for
        _get_pump_lock below. Explicit pump_id (const.py's CONF_PUMP_ID)
        always wins when set -- it's the only way to correctly group zones
        that share a pump but don't have a wattage sensor on it (or only
        one of them does), and the only way to tell two zones with the
        *same* pump_power_entity apart if that ever turns out not to mean
        "same pump" for some setup. Falling back to pump_power_entity next
        preserves the original behavior for zones that already relied on
        "same sensor = same pump" before pump_id existed. Falling back to
        this zone's own entry_id last (never a bare None) matters just as
        much as the pump_id case: without it, every zone that simply has no
        pump-power sensor configured would collide on the same key and be
        wrongly serialized with every other sensorless zone, even on
        completely independent pumps."""
        return self.pump_id or self.pump_power_entity or f"__zone_{self.entry.entry_id}"

    def _get_pump_lock(self) -> asyncio.Lock:
        """A lock keyed by _pump_lock_key, shared across every zone (config
        entry) that resolves to the same key. Two zones on independent
        pumps never touch each other's lock (different keys) and so never
        wait on each other; two zones that share a physical pump get
        automatically serialized here instead of opening two valves on the
        same pump at once, which would skew both zones' flow-rate
        calibration. Deliberately stored under its own hass.data key, not
        nested inside hass.data[DOMAIN] (which holds the entry_id -> controller
        map) -- async_unload_entry checks `if not hass.data[DOMAIN]` to decide
        whether to deregister services, and a stray lock left in that same
        dict would make it permanently non-falsy."""
        locks: dict[str, asyncio.Lock] = self.hass.data.setdefault(f"{DOMAIN}_pump_locks", {})
        return locks.setdefault(self._pump_lock_key, asyncio.Lock())

    async def _run_pulses(
        self,
        *,
        count: int,
        pulse_minutes: float,
        rest_minutes: int,
        min_pump_watts: float,
        kind: str,
        target_mm_for_log: float,
        deducted_mm_for_log: float,
        runtime_for_log: int,
    ) -> bool:
        """Acquires this zone's pump lock (queuing behind another zone
        mid-cycle on a shared pump, running immediately if the pump is
        independent or free), applies the pump preamble/postamble delays,
        and runs the actual pulses. See `_execute_pulses` for the pulse
        loop itself."""
        pump_lock = self._get_pump_lock()
        async with pump_lock:
            preamble = self.number("pump_preamble_seconds")
            if preamble > 0:
                await asyncio.sleep(preamble)

            flow_start = await self._flow_meter_reading()

            completed = await self._execute_pulses(
                count=count,
                pulse_minutes=pulse_minutes,
                rest_minutes=rest_minutes,
                min_pump_watts=min_pump_watts,
                kind=kind,
                target_mm_for_log=target_mm_for_log,
                deducted_mm_for_log=deducted_mm_for_log,
                runtime_for_log=runtime_for_log,
            )

            flow_end = await self._flow_meter_reading()
            if flow_start is not None and flow_end is not None:
                delta_liters = max(flow_end - flow_start, 0.0)
                self.store.state.last_cycle_water_liters = delta_liters
                await self.store.async_save()
                # Only meaningful for a cycle that actually ran to
                # completion -- an aborted cycle legitimately may not have
                # moved any water, and that's not a flow-meter problem.
                if completed and delta_liters <= 0.0:
                    await self._log_event(
                        event_type="No Flow Detected",
                        status="WARNING",
                        target_mm=target_mm_for_log,
                        deducted_mm=deducted_mm_for_log,
                        runtime=runtime_for_log,
                        notify_phone=True,
                        phone_title=f"⚠️ {kind.upper()}: No Water Flow Detected",
                        phone_msg=(
                            "Cycle completed but the flow meter shows no water delivered. "
                            "Check the valve/pump/flow-meter wiring."
                        ),
                    )

            postamble = self.number("pump_postamble_seconds")
            if postamble > 0:
                # Runs whether or not the cycle completed cleanly -- the
                # valve is already closed either way, and the point is
                # letting pressure settle before the next zone queued on
                # this same pump opens its own valve.
                await asyncio.sleep(postamble)
            return completed

    async def _execute_pulses(
        self,
        *,
        count: int,
        pulse_minutes: float,
        rest_minutes: int,
        min_pump_watts: float,
        kind: str,
        target_mm_for_log: float,
        deducted_mm_for_log: float,
        runtime_for_log: int,
    ) -> bool:
        """Runs `count` on/wait/off pulses. Returns True if completed without
        an abort, False if aborted partway (mirrors the repeat: block in both
        avocado_deep_soak and avocado_routine_irrigation)."""
        for index in range(1, count + 1):
            if self.store.state.abort_on:
                _LOGGER.warning("%s: aborted by power-loss watchdog before pulse %d", kind, index)
                return False

            await self.hass.services.async_call(
                "switch", "turn_on", {"entity_id": self.valve_entity}, blocking=True
            )

            # The pump-power audit only makes sense when a pump-power
            # sensor is actually configured -- without one, _pump_watts()
            # would always read 0.0, which would otherwise warn on every
            # single pulse about a "low" reading that was never real to
            # begin with. Skipping cleanly here (not by making the
            # threshold trivially pass) means no wasted 45s wait either.
            if self.pump_power_entity:
                # wait_template pump-power check, timeout 45s, continue_on_timeout
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        self._wait_for_pump_watts(min_pump_watts), timeout=PUMP_POWER_WAIT_TIMEOUT_SECONDS
                    )
                if await self._pump_watts() < min_pump_watts:
                    await self._log_event(
                        event_type="Low Pump Power Audit",
                        status="WARNING",
                        target_mm=target_mm_for_log,
                        deducted_mm=deducted_mm_for_log,
                        runtime=runtime_for_log,
                        notify_phone=True,
                        phone_title=f"⚠️ {kind.upper()}: Low Pump Power",
                        phone_msg=f"Pulse {index} running, pump reads {await self._pump_watts()}W.",
                    )

            # wait_template: abort flag on, timeout pulse_minutes, continue_on_timeout
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._abort_event.wait(), timeout=pulse_minutes * 60)

            if self.store.state.abort_on:
                valve_state = self.hass.states.get(self.valve_entity)
                if valve_state is not None and valve_state.state != "unavailable":
                    await self.hass.services.async_call(
                        "switch", "turn_off", {"entity_id": self.valve_entity}, blocking=True
                    )
                _LOGGER.warning("%s: aborted by power-loss watchdog during pulse %d", kind, index)
                return False

            await self.hass.services.async_call(
                "switch", "turn_off", {"entity_id": self.valve_entity}, blocking=True
            )

            if index < count:
                await asyncio.sleep(rest_minutes * 60)
        return True

    async def _wait_for_pump_watts(self, min_pump_watts: float) -> None:
        """Waits until the pump-power reading reaches min_pump_watts.

        Event-driven rather than a fixed 1s poll: a 1s poll can only ever
        notice a new reading once the sensor has actually reported one, so
        polling faster than the sensor updates bought nothing but wasted
        wakeups -- waiting on the entity's own state-changed event is
        exactly as responsive (reacts the instant a new reading arrives)
        without the busy-loop. The caller wraps this whole call in
        asyncio.wait_for(..., timeout=PUMP_POWER_WAIT_TIMEOUT_SECONDS), so
        cancellation on timeout still unwinds through the `finally` below
        and removes the listener -- the external 45s-cap-then-warn
        behavior is unchanged.
        """
        if await self._pump_watts() >= min_pump_watts:
            return

        watts_updated = asyncio.Event()

        @callback
        def _on_pump_power_change(event: Event) -> None:
            watts_updated.set()

        unsub = async_track_state_change_event(self.hass, [self.pump_power_entity], _on_pump_power_change)
        try:
            while await self._pump_watts() < min_pump_watts:
                watts_updated.clear()
                await watts_updated.wait()
        finally:
            unsub()

    def _track_schedule(self, sun_mode: str, offset_minutes: float, fixed_time: dt_time, action) -> Any:
        """Wire up one schedule trigger (deep soak or routine). Fixed clock
        time is the default and unchanged behavior; the four sun-relative
        modes fire once per day, offset from the local sunrise/sunset, and
        HA's sun helpers handle re-scheduling for the next day automatically
        -- same as async_track_time_change does for a fixed clock time."""
        if sun_mode == SUN_MODE_FIXED:
            return async_track_time_change(
                self.hass, action, hour=fixed_time.hour, minute=fixed_time.minute, second=fixed_time.second
            )
        offset = timedelta(minutes=offset_minutes)
        # async_track_sunrise/sunset call their action with no arguments,
        # unlike async_track_time_change (which passes `now`) -- adapt so
        # the same _on_deep_soak_time/_on_routine_time callbacks work either
        # way.
        def sun_action() -> None:
            action(None)

        if sun_mode == SUN_MODE_BEFORE_SUNRISE:
            return async_track_sunrise(self.hass, sun_action, offset=-offset)
        if sun_mode == SUN_MODE_AFTER_SUNRISE:
            return async_track_sunrise(self.hass, sun_action, offset=offset)
        if sun_mode == SUN_MODE_BEFORE_SUNSET:
            return async_track_sunset(self.hass, sun_action, offset=-offset)
        if sun_mode == SUN_MODE_AFTER_SUNSET:
            return async_track_sunset(self.hass, sun_action, offset=offset)
        # Unknown/corrupt value written by something else -- fail open to the
        # safe, always-correct fixed-time behavior rather than not scheduling
        # the zone at all.
        return async_track_time_change(
            self.hass, action, hour=fixed_time.hour, minute=fixed_time.minute, second=fixed_time.second
        )

    @callback
    def _on_deep_soak_time(self, now) -> None:
        self.hass.async_create_task(self.run_deep_soak())

    @callback
    def _on_routine_time(self, now) -> None:
        self.hass.async_create_task(self.run_routine_irrigation())

    # ------------------------------------------------------------------
    # Forecast gate: pre-emptively hold off a scheduled run when rain is
    # forecast, with a per-zone configurable dry-spell override so a wrong
    # or stuck forecast can never starve a plant indefinitely.
    # ------------------------------------------------------------------
    async def _get_forecast_precip_mm(self) -> tuple[float, float | None] | None:
        """Returns (precipitation_mm, probability_pct_or_None) for the next
        forecast period, or None if no usable forecast is available right
        now (entity missing/unavailable, service call failed, or the
        integration behind it returned nothing) -- callers must treat None
        as "can't tell, don't block on it"."""
        entity_id = self.weather_entity
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            return None
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": entity_id, "type": "daily"},
                blocking=True,
                return_response=True,
            )
        except Exception:  # noqa: BLE001 - a broken forecast must never block irrigation
            _LOGGER.exception("Forecast lookup failed for %s; failing open", entity_id)
            return None
        if not response:
            return None
        forecasts = (response.get(entity_id) or {}).get("forecast")
        if not forecasts:
            return None
        today = forecasts[0]
        precip = today.get("precipitation")
        if precip is None:
            return None
        prob = today.get("precipitation_probability")
        return float(precip), (float(prob) if prob is not None else None)

    async def _forecast_gate_allows_run(self, cycle: str) -> bool:
        """`cycle` is "deep_soak" or "routine" -- they run on independent
        schedules so each gets its own skip streak. Returns True whenever
        the run should proceed (no weather entity configured, no rain
        forecast, forecast unreadable, or the dry-spell override just
        fired) and False only when a forecast-based skip should happen now."""
        count_attr = f"forecast_{cycle}_skip_count"
        start_attr = f"forecast_{cycle}_skip_start_ts"
        state = self.store.state

        if not self.weather_entity:
            return True

        forecast = await self._get_forecast_precip_mm()
        if forecast is None:
            # Fail open: an unreadable forecast is never grounds to skip,
            # and it doesn't count towards (or against) the dry streak.
            setattr(state, count_attr, 0)
            setattr(state, start_attr, None)
            return True

        precip_mm, prob_pct = forecast
        rain_forecast = precip_mm >= self.number("forecast_rain_threshold_mm") or (
            prob_pct is not None and prob_pct >= self.number("forecast_probability_threshold_pct") and precip_mm > 0
        )
        if not rain_forecast:
            setattr(state, count_attr, 0)
            setattr(state, start_attr, None)
            return True

        now_ts = dt_util.utcnow().timestamp()
        skip_start = getattr(state, start_attr)
        if skip_start is None:
            skip_start = now_ts
            setattr(state, start_attr, skip_start)

        override_days = self.number("forecast_dry_override_days")
        days_dry = (now_ts - skip_start) / 86400.0
        rain_since_skip_start = self.rain_since(skip_start)

        if days_dry >= override_days and rain_since_skip_start <= 0.0:
            setattr(state, count_attr, 0)
            setattr(state, start_attr, None)
            await self.store.async_save()
            await self._log_event(
                event_type="Forecast Override",
                status="Override",
                target_mm=0.0,
                deducted_mm=0.0,
                runtime=0,
                notify_phone=True,
                phone_title="⏱️ Forecast Override",
                phone_msg=(
                    f"Rain kept being forecast but none has actually fallen in "
                    f"{days_dry:.1f} days (this zone's limit is {override_days:.0f}d) -- watering anyway."
                ),
            )
            return True

        setattr(state, count_attr, getattr(state, count_attr) + 1)
        await self.store.async_save()
        await self._log_event(
            event_type="Forecast Skip",
            status="Skipped",
            target_mm=0.0,
            deducted_mm=0.0,
            runtime=0,
            notify_phone=False,
            phone_title="",
            phone_msg="",
            extra_log=(
                f"Skipping {cycle} run: {precip_mm:.1f}mm rain forecast"
                + (f" ({prob_pct:.0f}% probability)" if prob_pct is not None else "")
                + f". Will override after {override_days:.0f} dry day(s) with no measured rain."
            ),
        )
        return False

    async def run_deep_soak(self) -> None:
        """Port of avocado_deep_soak. Called by the 05:00 trigger and by the
        manual 'Run Deep Soak Now' button/service — same code, same gates."""
        if not self.deep_soak_enabled:
            # Silent, like every other routine gate below -- a zone that has
            # deliberately turned this cycle off shouldn't get a log entry
            # every single day just for staying off. The manual "Run Deep
            # Soak Now" button/service hits this exact same gate, so it
            # no-ops too rather than bypassing the zone's own setting.
            return
        state = self.store.state
        now_ts = dt_util.utcnow().timestamp()

        if state.lock_on:
            return
        if self._is_snoozed_today():
            return
        if not calc.deep_soak_due(
            now_ts - (state.last_deep_soak_ts or 0.0),
            self.number("deep_soak_interval_days"),
            DEEP_SOAK_INTERVAL_BUFFER_SECONDS,
        ):
            return
        if not calc.drydown_satisfied(
            now_ts - (state.last_significant_rain_ts or 0.0), self.number("deep_soak_drydown_days")
        ):
            return
        if self.rain_windows()["14d"] >= self.number("deep_soak_rain_threshold"):
            return
        if not await self._forecast_gate_allows_run("deep_soak"):
            return

        deep_soak_pulse_count = max(int(round(self.number("deep_soak_pulse_count"))), 1)
        plan = calc.plan_deep_soak(
            self.number("deep_soak_target_mm"),
            self.number("flow_rate_mm_per_min"),
            pulse_count=deep_soak_pulse_count,
            min_pulse_minutes=int(DEEP_SOAK_MIN_PULSE_MINUTES),
        )

        if plan.total_runtime_minutes > self.number("deep_soak_max_runtime_minutes"):
            await self._log_event(
                event_type="Deep Soak Cap Exceeded",
                status="ABORTED",
                target_mm=plan.target_mm,
                deducted_mm=0.0,
                runtime=plan.total_runtime_minutes,
                notify_phone=True,
                phone_title="⚠️ DEEP SOAK ABORTED",
                phone_msg=f"Calculated runtime ({plan.total_runtime_minutes} min) exceeded safety cap. Watering cancelled.",
            )
            return

        max_daily = self.number("max_daily_runtime_minutes")
        if state.today_runtime_minutes + plan.total_runtime_minutes > max_daily:
            await self._log_event(
                event_type="Max Daily Runtime Cap Reached",
                status="ABORTED",
                target_mm=plan.target_mm,
                deducted_mm=0.0,
                runtime=plan.total_runtime_minutes,
                notify_phone=True,
                phone_title="⚠️ DEEP SOAK SKIPPED: Daily Runtime Cap",
                phone_msg=(
                    f"Already applied {state.today_runtime_minutes:.0f} min today; this deep soak "
                    f"({plan.total_runtime_minutes} min) would exceed the {max_daily:.0f} min daily cap. "
                    "Skipped -- will retry when due again."
                ),
            )
            return

        rain_30min = self.rain_windows()["30min"]
        if rain_30min > self.number("preirrigation_rain_threshold_mm"):
            await self._log_event(
                event_type="Pre-Irrigation Rain Cancellation",
                status="Cancelled",
                target_mm=plan.target_mm,
                deducted_mm=0.0,
                runtime=0,
                notify_phone=True,
                phone_title="🌧️ Deep Soak Cancelled",
                phone_msg=f"Cancelled: {rain_30min:.1f}mm fell in the last 30 minutes.",
            )
            return

        await self._set_lock(True)
        await self._set_abort(False)

        completed = await self._run_pulses(
            count=deep_soak_pulse_count,
            pulse_minutes=plan.pulse_runtime_minutes,
            rest_minutes=int(round(self.number("deep_soak_pulse_rest_minutes"))),
            min_pump_watts=self.number("pump_min_watts"),
            kind="Deep Soak",
            target_mm_for_log=plan.target_mm,
            deducted_mm_for_log=0.0,
            runtime_for_log=plan.total_runtime_minutes,
        )

        if not completed or state.abort_on:
            return

        state.last_deep_soak_ts = dt_util.utcnow().timestamp()
        state.today_runtime_minutes += plan.total_runtime_minutes
        await self.store.async_save()
        await self._set_lock(False)
        await self._log_event(
            event_type="Deep Soak Completed",
            status="Completed",
            target_mm=plan.target_mm,
            deducted_mm=0.0,
            runtime=plan.total_runtime_minutes,
            notify_phone=True,
            phone_title="🚿 Deep Soak Completed",
            phone_msg=f"DEEP SOAK COMPLETED: {plan.target_mm}mm applied over 3 pulses ({plan.total_runtime_minutes} min).",
        )

    async def run_routine_irrigation(self, manual: bool = False) -> None:
        """Port of avocado_routine_irrigation. Called by the 05:30 trigger and
        by the manual 'Run Routine Irrigation Now' button/service.

        `manual=True` marks this call as a human-triggered press (button or
        service, not the scheduled time trigger). It never bypasses any
        gate -- a manual press is evaluated by exactly the same logic as
        the scheduled trigger, so it can still be a no-op, same as before
        this feature existed. Its only effect is feeding the self-tuning
        "early" signal (see _register_self_tune_signal / const.py's
        SELF_TUNE_* comment) at the one point where the plain time-based
        model explicitly says "not yet due": the person pressing the
        button there is itself the signal, whether or not soil moisture
        (if configured) goes on to force the cycle to run anyway. A manual
        press that was already due, or blocked earlier by the lock/snooze
        gate, never touches the streak."""
        state = self.store.state
        now_ts = dt_util.utcnow().timestamp()
        last_run_ts = state.last_routine_ts or 0.0
        elapsed_seconds = now_ts - last_run_ts

        if state.lock_on:
            return
        if self._is_snoozed_today():
            return

        # effective_avg_peak_temp() (not avg_peak_temp()) is what must drive
        # this decision -- it returns None, an explicit "use normal tier"
        # branch, whenever the temp sensor is unconfigured OR currently
        # unavailable/unknown, rather than silently running whatever tier a
        # dead sensor's last real reading happened to imply.
        avg_peak_temp = self.effective_avg_peak_temp()
        hot_threshold = self.number("hot_temp_threshold")
        interval_days = calc.routine_interval_days(avg_peak_temp, hot_threshold)
        interval_due = calc.routine_due(elapsed_seconds, interval_days, ROUTINE_INTERVAL_BUFFER_SECONDS)

        # Soil moisture (if configured and currently readable) becomes the
        # direct decider at the extremes, ahead of the plain time-interval
        # estimate -- see calc.routine_due_with_soil_moisture's docstring.
        # Deliberately routine-only, not deep soak (see const.py's
        # CONF_SOIL_MOISTURE_ENTITY comment).
        moisture_pct = await self._soil_moisture_pct()
        if not calc.routine_due_with_soil_moisture(
            interval_due,
            moisture_pct,
            self.number("soil_moisture_dry_pct"),
            self.number("soil_moisture_wet_pct"),
        ):
            # This is the plain time-based model's own "not yet due" verdict
            # (soil moisture, if configured, didn't override it to True) --
            # a manual press landing here, itself, is the self-tune "early"
            # signal, independent of whether anything actually gets watered.
            if manual and not interval_due:
                await self._register_self_tune_signal("early")
            return
        if not calc.drydown_satisfied(
            now_ts - (state.last_significant_rain_ts or 0.0), self.number("routine_drydown_days")
        ):
            return
        if not await self._forecast_gate_allows_run("routine"):
            return

        # Growth-stage auto-ramp (optional, off by default -- see
        # growth_ramp_fraction) scales only the routine weekly targets, not
        # the deep-soak depth target: it models "a young plant needs less
        # water overall right now", which is the routine cycle's job, while
        # deep soak's job (root-zone penetration depth) doesn't scale the
        # same way with plant age.
        ramp = self.growth_ramp_fraction()
        routine_pulse_count = max(int(round(self.number("routine_pulse_count"))), 1)
        days_elapsed = int(elapsed_seconds / 86400)
        plan = calc.plan_routine_irrigation(
            avg_peak_temp=avg_peak_temp,
            hot_threshold=hot_threshold,
            cool_threshold=self.number("cool_temp_threshold"),
            normal_weekly_mm=self.number("target_weekly_mm") * ramp,
            hot_weekly_mm=self.number("target_weekly_hot_mm") * ramp,
            cool_weekly_mm=self.number("target_weekly_cool_mm") * ramp,
            flow_rate=self.number("flow_rate_mm_per_min"),
            days_elapsed=days_elapsed,
            today_rain_mm=self.today_rain_mm(),
            rain_day_history_mm=state.rain_day_history_mm,
            rain_eff_low=self.number("rain_eff_low"),
            rain_eff_mid=self.number("rain_eff_mid"),
            rain_eff_high=self.number("rain_eff_high"),
            pulse_count=routine_pulse_count,
            min_pulse_minutes=int(ROUTINE_MIN_PULSE_MINUTES),
        )

        if days_elapsed > 10:
            await self._log_event(
                event_type="Irrigation Overdue",
                status="WARNING",
                target_mm=0.0,
                deducted_mm=0.0,
                runtime=0,
                notify_phone=True,
                phone_title="⚠️ Irrigation Overdue",
                phone_msg=f"{days_elapsed} days since last watering — unusually long gap, worth checking the system.",
            )

        max_runtime = self.number("max_runtime_minutes")
        if plan.calc_runtime_minutes > max_runtime:
            await self._log_event(
                event_type="Runtime Cap Exceeded",
                status="ABORTED",
                target_mm=round(plan.interval_target_mm, 1),
                deducted_mm=round(plan.eff_rain_mm, 1),
                runtime=plan.calc_runtime_minutes,
                notify_phone=True,
                phone_title="⚠️ ROUTINE IRRIGATION ABORTED",
                phone_msg=f"Calculated runtime ({plan.calc_runtime_minutes} min) exceeded max safety limit ({max_runtime} min).",
            )
            return

        max_daily = self.number("max_daily_runtime_minutes")
        if state.today_runtime_minutes + plan.calc_runtime_minutes > max_daily:
            await self._log_event(
                event_type="Max Daily Runtime Cap Reached",
                status="ABORTED",
                target_mm=round(plan.interval_target_mm, 1),
                deducted_mm=round(plan.eff_rain_mm, 1),
                runtime=plan.calc_runtime_minutes,
                notify_phone=True,
                phone_title="⚠️ ROUTINE IRRIGATION SKIPPED: Daily Runtime Cap",
                phone_msg=(
                    f"Already applied {state.today_runtime_minutes:.0f} min today; this cycle "
                    f"({plan.calc_runtime_minutes} min) would exceed the {max_daily:.0f} min daily cap. "
                    "Skipped -- will retry when due again."
                ),
            )
            return

        if plan.calc_runtime_minutes <= 0:
            await self._log_event(
                event_type="Rain Credit Sufficient",
                status="Skipped",
                target_mm=round(plan.interval_target_mm, 1),
                deducted_mm=round(plan.eff_rain_mm, 1),
                runtime=0,
                notify_phone=False,
                phone_title="🌧️ Routine Irrigation Skipped",
                phone_msg=f"Rain credit ({round(plan.eff_rain_mm, 1)}mm) already covers target ({round(plan.interval_target_mm, 1)}mm) — no watering needed.",
            )
            return

        rain_30min = self.rain_windows()["30min"]
        if rain_30min > self.number("preirrigation_rain_threshold_mm"):
            await self._log_event(
                event_type="Pre-Irrigation Rain Cancellation",
                status="Cancelled",
                target_mm=round(plan.interval_target_mm, 1),
                deducted_mm=round(plan.eff_rain_mm, 1),
                runtime=0,
                notify_phone=True,
                phone_title="🌧️ Routine Irrigation Cancelled",
                phone_msg=f"Cancelled: {rain_30min:.1f}mm fell in the last 30 minutes.",
            )
            return

        await self._set_lock(True)
        await self._set_abort(False)

        completed = await self._run_pulses(
            count=routine_pulse_count,
            pulse_minutes=plan.pulse_runtime_minutes,
            rest_minutes=int(round(self.number("routine_pulse_rest_minutes"))),
            min_pump_watts=self.number("pump_min_watts"),
            kind="Routine Irrigation",
            target_mm_for_log=round(plan.interval_target_mm, 1),
            deducted_mm_for_log=round(plan.eff_rain_mm, 1),
            runtime_for_log=plan.calc_runtime_minutes,
        )

        if not completed or state.abort_on:
            return

        state.last_routine_ts = dt_util.utcnow().timestamp()
        state.today_runtime_minutes += plan.calc_runtime_minutes
        await self.store.async_save()
        await self._set_lock(False)
        # Reaching completion with interval_due False only happens when a
        # configured soil-moisture sensor forced the run through despite the
        # plain time model saying "not yet" -- if this was also a manual
        # press, it's a second, rarer flavor of the same "early" signal as
        # the no-op case above (that one already returned before here).
        if manual and not interval_due:
            await self._register_self_tune_signal("early")
        await self._log_event(
            event_type="Routine Irrigation Completed",
            status="Completed",
            target_mm=round(plan.interval_target_mm, 1),
            deducted_mm=round(plan.eff_rain_mm, 1),
            runtime=plan.calc_runtime_minutes,
            notify_phone=True,
            phone_title="🚿 Routine Irrigation Completed",
            phone_msg=f"Applied {plan.calc_runtime_minutes} min (Target: {round(plan.interval_target_mm, 1)}mm, Rain Deducted: {round(plan.eff_rain_mm, 1)}mm).",
        )

    async def test_pulse(self, seconds: int) -> None:
        """Bench-test helper: one short valve pulse bypassing every schedule/
        dry-down/rain gate, so the physical valve + pump-power audit path can
        be verified before the real schedule runs unattended. Still goes
        through the mutex lock and the same watchdogs as a real cycle."""
        if self.store.state.lock_on:
            _LOGGER.warning("ZoneFlow: test pulse skipped, lock already held")
            return
        await self._set_lock(True)
        await self._set_abort(False)
        await self._run_pulses(
            count=1,
            pulse_minutes=max(seconds / 60, 1 / 60),
            rest_minutes=0,
            min_pump_watts=self.number("pump_min_watts"),
            kind="Test Pulse",
            target_mm_for_log=0.0,
            deducted_mm_for_log=0.0,
            runtime_for_log=0,
        )
        await self._set_lock(False)
        await self._log_event(
            event_type="Manual Test Pulse",
            status="Completed",
            target_mm=0.0,
            deducted_mm=0.0,
            runtime=0,
            notify_phone=False,
            phone_title="",
            phone_msg="",
        )

    async def reset_lock(self) -> None:
        """Manual emergency reset (button/service), not time-gated."""
        await self._set_lock(False)
        await self._set_abort(False)
        await self._log_event(
            event_type="Manual Lock Reset",
            status="WARNING",
            target_mm=0.0,
            deducted_mm=0.0,
            runtime=0,
            notify_phone=False,
            phone_title="",
            phone_msg="",
        )

    def _is_snoozed_today(self) -> bool:
        """See run_deep_soak()/run_routine_irrigation()'s snooze gate and
        state_store.py's snooze_date_iso comment. A plain local-date string
        comparison rather than a timestamp/duration -- it self-expires the
        moment the calendar date changes, with no separate cleanup needed,
        and it means "skip today" always means today's local calendar day
        regardless of what time the button was pressed."""
        return self.store.state.snooze_date_iso == dt_util.now().date().isoformat()

    async def snooze_today(self) -> None:
        """Manual 'Snooze Today' button/service. Skips whichever of this
        zone's scheduled cycles (deep soak, routine, or both) hasn't
        already run today, without touching any other setting -- the
        zone's schedule, targets, and every other gate go right back to
        normal starting tomorrow with no further action needed. Does
        nothing to an already-running cycle (the mutex lock, not this
        flag, governs that) -- it only prevents a NEW cycle from starting
        for the rest of today."""
        self.store.state.snooze_date_iso = dt_util.now().date().isoformat()
        await self.store.async_save()
        await self._register_self_tune_signal("skip")
        await self._log_event(
            event_type="Manual Snooze Today",
            status="INFO",
            target_mm=0.0,
            deducted_mm=0.0,
            runtime=0,
            notify_phone=False,
            phone_title="",
            phone_msg="",
        )

    async def _register_self_tune_signal(self, direction: str) -> None:
        """Record one "early" (a manual routine run that completed before
        the modeled interval said it was due) or "skip" (a Snooze Today
        press) signal, and nudge routine_drydown_days once the relevant
        streak hits SELF_TUNE_STREAK_THRESHOLD -- see const.py's SELF_TUNE_*
        comment for the full rationale. Either direction resets the other
        streak, so an early-then-skip (or vice versa) pattern never quietly
        carries partial progress toward the opposite nudge."""
        state = self.store.state
        if direction == "early":
            state.self_tune_early_streak += 1
            state.self_tune_skip_streak = 0
            step_days = -SELF_TUNE_ADJUST_STEP_DAYS
            streak = state.self_tune_early_streak
        else:
            state.self_tune_skip_streak += 1
            state.self_tune_early_streak = 0
            step_days = SELF_TUNE_ADJUST_STEP_DAYS
            streak = state.self_tune_skip_streak

        if streak < SELF_TUNE_STREAK_THRESHOLD:
            await self.store.async_save()
            return

        if direction == "early":
            state.self_tune_early_streak = 0
        else:
            state.self_tune_skip_streak = 0

        _, min_days, max_days, _, _ = NUMBER_DEFS["routine_drydown_days"]
        current_days = self.number("routine_drydown_days")
        new_days = calc.adjust_drydown_days(current_days, step_days, min_days, max_days)
        await self.store.async_save()

        if new_days == current_days:
            # Already sitting at the clamp boundary -- nothing to move and
            # nothing worth logging (the streak still reset above, so a new
            # streak has to build up again before this is re-evaluated).
            return

        number_entity = self.numbers.get("routine_drydown_days")
        if number_entity is not None:
            await number_entity.async_set_native_value(new_days)

        await self._log_event(
            event_type="Self-Tuning Adjustment",
            status="INFO",
            target_mm=0.0,
            deducted_mm=0.0,
            runtime=0,
            notify_phone=True,
            phone_title="🌱 Self-Tuning Adjustment",
            phone_msg=(
                f"Routine Dry-Down Holdoff {'shortened' if step_days < 0 else 'extended'} to "
                f"{new_days:g}d, based on your recent {'early runs' if direction == 'early' else 'snoozes'}."
            ),
        )

    # ------------------------------------------------------------------
    # Logging: CSV row + phone notification (port of avocado_csv_logger)
    # ------------------------------------------------------------------
    async def _log_event(
        self,
        *,
        event_type: str,
        status: str,
        target_mm: float,
        deducted_mm: float,
        runtime: int,
        notify_phone: bool,
        phone_title: str,
        phone_msg: str,
        extra_log: str | None = None,
    ) -> None:
        windows = self.rain_windows()
        row = [
            dt_util.now().strftime("%Y-%m-%d %H:%M:%S"),
            event_type,
            status,
            f"{target_mm}",
            f"{deducted_mm}",
            f"{runtime}",
            f"3d: {windows['3d']:.1f}mm / 7d: {windows['7d']:.1f}mm",
        ]
        await self.hass.async_add_executor_job(self._write_csv_row, row)
        _LOGGER.info("ZoneFlow event: %s (%s)", event_type, status)
        if extra_log:
            _LOGGER.info(extra_log)

        if notify_phone and self.notify_entity:
            try:
                await self.hass.services.async_call(
                    "notify",
                    "send_message",
                    {"entity_id": self.notify_entity, "title": phone_title, "message": phone_msg},
                    blocking=True,
                )
            except Exception:  # noqa: BLE001 - never let a notify failure break irrigation logic
                _LOGGER.exception("Failed to send phone notification for %s", event_type)

        self.hass.bus.async_fire(EVENT_LOG, {"event_type": event_type, "status": status})

    def _write_csv_row(self, row: list[str]) -> None:
        try:
            with open(self.csv_path, "a", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerow(row)
        except OSError:
            _LOGGER.exception("Could not write ZoneFlow CSV log to %s", self.csv_path)
