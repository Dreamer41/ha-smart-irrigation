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
import functools
import logging
from datetime import time as dt_time, timedelta
from typing import Any

from homeassistant.core import Event, HassJob, HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_state_change_event,
    async_track_sunrise,
    async_track_sunset,
    async_track_time_change,
)
import homeassistant.util.dt as dt_util
from homeassistant.const import UnitOfTemperature, UnitOfVolume
from homeassistant.util.unit_conversion import TemperatureConverter, VolumeConverter

from . import calculations as calc, units
from .const import (
    CYCLE_STOP_TIMEOUT_SECONDS,
    SHUTDOWN_CONFIRM_SECONDS,
    SHUTDOWN_STOP_TIMEOUT_SECONDS,
    VALVE_CLOSE_CONFIRM_SECONDS,
    CONF_UNIT_SYSTEM,
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
    DEMAND_MODEL_ET,
    DOMAIN,
    EVENT_LOG,
    GROWTH_RAMP_CURVES,
    GROWTH_RAMP_CUSTOM,
    GROWTH_RAMP_OFF,
    GROWTH_STAGE_MODE_AUTO,
    NUMBER_DEFAULTS,
    NUMBER_DEFS,
    SOIL_MOISTURE_STALE_SECONDS,
    SOIL_WET_HOLD_ALERT_INTERVALS,
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
    VALVE_STUCK_MARGIN_MINUTES,
    VALVE_STUCK_ON_MINUTES,
)
from .state_store import IrrigationStateStore

SIGNIFICANT_RAIN_ALERT_QUIET_SECONDS = 24 * 3600

# Weather forecasts report precipitation in the weather entity's own unit.
PRECIP_UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "in": 25.4}


def _state_temp_c(state: State | None) -> float | None:
    """A temperature entity's current reading in degC, or None if it isn't
    a number. Everything inside ZoneFlow (thresholds, the peak/min
    registers, ET0) is in degC, but Home Assistant reports a temperature
    sensor in the instance's own unit system -- so an HA set to Fahrenheit
    hands over 89.6 for a 32C afternoon. The sensor's unit_of_measurement
    decides the conversion; no unit at all is treated as degC, which is
    what ZoneFlow always assumed before this existed."""
    if state is None:
        return None
    try:
        value = float(state.state)
    except (TypeError, ValueError):
        return None
    unit = state.attributes.get("unit_of_measurement")
    if unit in (UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.KELVIN):
        # Rounded so 78.8F shows as 26.0, not 25.999999999999996.
        return round(TemperatureConverter.convert(value, unit, UnitOfTemperature.CELSIUS), 2)
    return value

_LOGGER = logging.getLogger(__name__)


def _parse_hms(value: str) -> dt_time:
    h, m, s = (int(p) for p in value.split(":"))
    return dt_time(hour=h, minute=m, second=s)


# How a pulse loop ended (see _execute_pulses).
_DONE = "done"
_ABORTED = "aborted"
_RAIN = "rain"
_STOPPED = "stopped"
# A service run ended by the person (Service Mode switched off).
_USER_STOPPED = "user_stopped"

# Service / check runs: never counted as watering (see start_service_run).
SERVICE_RUN_KIND = "Service Run"


def _tracked_run(func):
    """Marks a public run (deep soak, routine, test pulse) as in progress,
    so a reload or shutdown can wait for it to wind down; refuses to start
    one once the zone is stopping."""

    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        if self._stopping:
            return None
        task = asyncio.current_task()
        self._runs.add(task)
        self._idle.clear()
        try:
            return await func(self, *args, **kwargs)
        except asyncio.CancelledError:
            # Cancelled anywhere in the run (queued on the pump, preamble,
            # mid-pulse...): the pulse loop has already closed its valve;
            # free the lock this run took, once the valve is confirmed
            # closed, rather than blocking the zone for 3 hours.
            if (
                self.store.state.lock_on
                and self._lock_owner is task
                and await self._valve_confirmed_closed(self.store.state.lock_valve or self.valve_entity)
            ):
                await self._set_lock(False)
            raise
        finally:
            self._runs.discard(task)
            if not self._runs:
                self._idle.set()

    return wrapper


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
        # Length (minutes) of the pulse ZoneFlow itself is running right now,
        # or None -- lets the stuck-valve watchdog tell a planned long pulse
        # from a valve that failed to close (see VALVE_STUCK_MARGIN_MINUTES).
        self._expected_pulse_minutes: float | None = None
        self._startup_unsub = None
        self._setup_ts = 0.0
        # Runs in progress (run_deep_soak / run_routine_irrigation /
        # test_pulse, tracked by @_tracked_run) -- a reload or shutdown
        # waits for them to wind down before this zone lets go. _stopping
        # is set once, when the zone is unloaded or Home Assistant shuts
        # down; nothing new starts after that.
        self._stopping = False
        self._runs: set[asyncio.Task] = set()
        self._idle = asyncio.Event()
        self._idle.set()
        # The cycle currently running: its kind, the valve it opened (a
        # reload can change the zone's valve setting mid-cycle), the
        # minutes it has given so far, and when the open pulse started.
        self._cycle_kind = ""
        self._cycle_valve: str | None = None
        self._delivered_minutes = 0.0
        self._pulse_started_ts: float | None = None
        self._lock_owner: asyncio.Task | None = None
        self._last_outcome: str | None = None
        # Service / check runs (buttons and the Service Mode switch): whether
        # one is running, the person's "stop" for it, and entities to tell.
        self._service_active = False
        self._service_stop = asyncio.Event()
        self._service_listeners: list[Any] = []

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
        """Optional. Without it, the "Fallback / Manual Temperature" slider
        picks the hot/cool/normal tier -- see watering_temp."""
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

    @property
    def imperial(self) -> bool:
        """Whether this zone shows imperial units (see units.py) -- its own
        Units option, or Home Assistant's unit system when set to follow it."""
        choice = self.entry.options.get(CONF_UNIT_SYSTEM, self.entry.data.get(CONF_UNIT_SYSTEM, units.UNIT_SYSTEM_AUTO))
        if choice == units.UNIT_SYSTEM_IMPERIAL:
            return True
        if choice == units.UNIT_SYSTEM_METRIC:
            return False
        return self.hass.config.units.temperature_unit == UnitOfTemperature.FAHRENHEIT

    def number(self, key: str) -> float:
        entity = self.numbers.get(key)
        value = getattr(entity, "metric_value", None) if entity is not None else None
        if value is not None:
            return float(value)
        return NUMBER_DEFAULTS[key]

    def fallback_temp(self) -> float | None:
        """The Fallback / Manual Temperature, or None while it has no value
        (only on a zone whose cool threshold isn't below its hot one -- see
        _seed_fallback_temp); None means the normal tier."""
        entity = self.numbers.get("fallback_temp")
        value = getattr(entity, "metric_value", None) if entity is not None else None
        return float(value) if value is not None else None

    def register_number(self, key: str, entity: Any) -> None:
        self.numbers[key] = entity
        # The fallback's own registration happens inside its
        # async_added_to_hass, whose state is written right after.
        self._seed_fallback_temp(write_state=key != "fallback_temp")

    def _seed_fallback_temp(self, write_state: bool = True) -> None:
        """A zone from before the fallback slider existed gets it set once,
        to the middle of its own cool/hot band -- the normal tier it always
        fell back to. From then on it is a normal slider value (restored
        across restarts, not moved by later threshold changes). A zone
        whose cool threshold isn't below hot has no normal band to aim for:
        it stays unset, which means the normal tier."""
        fallback = self.numbers.get("fallback_temp")
        hot = self.numbers.get("hot_temp_threshold")
        cool = self.numbers.get("cool_temp_threshold")
        if fallback is None or hot is None or cool is None or fallback.metric_value is not None:
            return
        hot_c = self.number("hot_temp_threshold")
        cool_c = self.number("cool_temp_threshold")
        if cool_c >= hot_c:
            return
        fallback.metric_value = (hot_c + cool_c) / 2
        if write_state and getattr(fallback, "hass", None) is not None:
            fallback.async_write_ha_state()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def async_setup(self) -> None:
        # When this zone started up -- the restart safety check must only
        # ever clear a lock that was set BEFORE this, i.e. left over from
        # before the restart (see _on_startup).
        self._setup_ts = dt_util.utcnow().timestamp()
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

        if not self.outdoor_temp_entity and any(v is not None for v in state.peak_temp_day_history_c):
            # No sensor, so nothing on record is a real reading (before
            # 1.4.2 missing days were filled with a made-up 30C); clear it so
            # a sensor added later starts from real data only.
            state.peak_temp_day_history_c = [None, None, None]
            state.min_temp_day_history_c = [None, None, None]
            await self.store.async_save()

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
        # A valve that is already open when ZoneFlow starts (restored "on"
        # after a restart mid-cycle) never produces an "on" state change for
        # the listener above to see, so arm the stuck-valve watchdog for it
        # here, from when it actually turned on.
        valve_now = self.hass.states.get(self.valve_entity)
        if valve_now is not None and valve_now.state == "on":
            self._arm_valve_stuck_watchdog(valve_now.last_changed)
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
        # Stop a running cycle when Home Assistant shuts down. A shutdown job
        # runs first thing, while the valve's own integration (Zigbee, MQTT,
        # ESPHome...) is still connected and can still close it.
        self._unsubs.append(self.hass.async_add_shutdown_job(HassJob(self._on_shutdown, "zoneflow shutdown")))

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
        #
        # It must be a @callback: HA runs a plain (non-callback) sync
        # listener in a worker thread, where creating the task fails with
        # "loop is not the running loop" -- on a normal boot (ZoneFlow set up
        # before HA has started) that silently dropped this whole check.
        @callback
        def _schedule_on_startup(event=None) -> None:
            # A one-time listener removes itself when it fires; forget our
            # handle so unload doesn't try to remove it a second time (HA
            # logs "Unable to remove unknown job listener" if it does).
            self._startup_unsub = None
            self.entry.async_create_background_task(
                self.hass, self._on_startup(event), name=f"{DOMAIN}_on_startup_{self.entry.entry_id}"
            )

        if self.hass.is_running:
            _schedule_on_startup()
        else:
            self._startup_unsub = self.hass.bus.async_listen_once("homeassistant_start", _schedule_on_startup)

    async def async_unload(self) -> None:
        # A reload (saving the zone's settings, flipping its Deep Soak
        # switch, an update) or removal mid-cycle: stop the cycle here, with
        # the valve closed and the lock released, so the reloaded zone
        # starts clean instead of racing an unsupervised old cycle.
        await self._interrupt_cycle("the zone was reloaded")
        if self._startup_unsub is not None:
            self._startup_unsub()
            self._startup_unsub = None
        for unsub in self._unsubs:
            with contextlib.suppress(ValueError):  # a shutdown job that already ran
                unsub()
        self._unsubs.clear()
        if self._valve_stuck_cancel:
            self._valve_stuck_cancel()
        if self._power_loss_cancel:
            self._power_loss_cancel()
        if self._lock_stale_cancel:
            self._lock_stale_cancel()
        # Anything the old cycle does from here on must not overwrite the
        # state the reloaded zone has just loaded.
        self.store.closed = True

    async def _on_shutdown(self) -> None:
        # Home Assistant gives shutdown jobs 20 s in all, so a tighter budget.
        await self._interrupt_cycle(
            "Home Assistant is shutting down",
            wait_seconds=SHUTDOWN_STOP_TIMEOUT_SECONDS,
            confirm_seconds=SHUTDOWN_CONFIRM_SECONDS,
        )

    async def _interrupt_cycle(
        self,
        reason: str,
        *,
        wait_seconds: float = CYCLE_STOP_TIMEOUT_SECONDS,
        confirm_seconds: float = VALVE_CLOSE_CONFIRM_SECONDS,
    ) -> None:
        """Stops this zone for good (unload/reload or Home Assistant
        shutdown). A running cycle notices at once (the abort event wakes
        every wait inside it), closes its own valve while it still holds the
        pump, logs "<kind> Interrupted", and is not counted as a run -- the
        next scheduled run decides again. This waits for that, and for any
        other run still evaluating its gates, before the zone lets go, so
        nothing is left running unsupervised beside a reloaded zone.

        The lock is released only once the valve is confirmed closed. If it
        isn't, the lock stays, so the restart safety check (or, after a
        reload, the reloaded zone's) forces the valve off."""
        self._stopping = True
        self._abort_event.set()
        if self._runs:
            _LOGGER.warning("%s: stopping a running cycle because %s", self.entry.title, reason)
            if not await self._wait_idle(wait_seconds):
                # Stuck somewhere that doesn't wake (e.g. a valve service
                # call that never returns): cancel -- the cycle still closes
                # its valve on the way out.
                for task in list(self._runs):
                    task.cancel()
                await self._wait_idle(confirm_seconds)
        if self.store.state.lock_on and await self._valve_confirmed_closed(
            self.store.state.lock_valve or self.valve_entity, confirm_seconds
        ):
            await self._set_lock(False)

    async def _wait_idle(self, seconds: float) -> bool:
        try:
            async with asyncio.timeout(seconds):
                await self._idle.wait()
        except TimeoutError:
            return False
        return True

    # ------------------------------------------------------------------
    # Rain / temperature tracking
    # ------------------------------------------------------------------
    def _sync_rain_from_counter_state(self, new_state: State, seed_only: bool = False) -> None:
        state = self.store.state
        try:
            tips = float(new_state.state)
        except (TypeError, ValueError):
            return
        # The rain windows assume an ever-growing total; see
        # calc.track_tip_total for how resets and glitches are told apart.
        (
            state.rain_counter_total_tips,
            state.rain_counter_last_tips,
            state.rain_counter_drop_from,
            state.rain_counter_drop_ts,
            state.rain_counter_since_drop_tips,
        ) = calc.track_tip_total(
            state.rain_counter_total_tips,
            state.rain_counter_last_tips,
            state.rain_counter_drop_from,
            state.rain_counter_drop_ts,
            state.rain_counter_since_drop_tips,
            tips,
            dt_util.utcnow().timestamp(),
        )
        cumulative_mm = state.rain_counter_total_tips * self.number("rain_mm_per_tip")
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
            # Every threshold crossing restarts the drydown holdoff from now,
            # but one storm crossing several thresholds (24h, then 4-day,
            # then 7-day) only alerts once: no second log/phone message
            # within 24 hours of the last ALERT (timed from the alert itself,
            # so suppressed crossings can't keep extending the quiet period,
            # and editing the Last Significant Rain date can't hide one).
            state.last_significant_rain_ts = now_ts
            last_alert = state.last_significant_rain_alert_ts
            if last_alert is not None and now_ts - last_alert < SIGNIFICANT_RAIN_ALERT_QUIET_SECONDS:
                self.hass.async_create_task(self.store.async_save())
                _LOGGER.info("ZoneFlow: another heavy-rain threshold crossed in the same storm; holdoff restarted, no second alert")
                return
            state.last_significant_rain_alert_ts = now_ts
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
                    phone_msg=f"Heavy rain recorded (24h: {units.depth_text(r24, self.imperial)}). Dry-down timers updated.",
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
            seed = _state_temp_c(self.hass.states.get(self.outdoor_temp_entity))
        self._start_new_day(seed_temp=seed)
        self.hass.async_create_task(self.store.async_save())
        self.hass.async_create_task(self._check_deficit_end())

    @callback
    def _on_outdoor_temp_change(self, event: Event) -> None:
        new_state: State | None = event.data.get("new_state")
        if new_state is None:
            return
        temp = _state_temp_c(new_state)
        if temp is None:
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
        # A day without a single reading is recorded as "no reading", not
        # as a copy of the day before: a dead sensor's last value then ages
        # out of the 3-day window instead of being carried forward forever.
        # A sensor that is working but hasn't CHANGED today (some templates
        # and slow sensors only report on change; also a day that began
        # while HA was restarting) still has a real reading: its current
        # value. Peak only -- one reading says nothing about the day's range,
        # so the minimum stays None and ET0 skips that day.
        today_peak = state.today_peak_temp_c
        if today_peak is None and self.outdoor_temp_entity:
            current = _state_temp_c(self.hass.states.get(self.outdoor_temp_entity))
            if calc.plausible_temp(current):
                today_peak = current
        state.peak_temp_day_history_c = [
            today_peak,
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

    def avg_peak_temp(self) -> float | None:
        """Average of the real daily peaks recorded in the last 3 days, or
        None when there are none (new zone, or no readings for 3 days)."""
        state = self.store.state
        return calc.three_day_average_peak_temp(state.peak_temp_day_history_c)

    def et0_daily_history(self) -> list[float | None]:
        """Hargreaves ET0 (mm/day) for each of the last three completed
        days, newest first, using Home Assistant's own configured home
        latitude. A day is None when it has no real min+max pair on record
        (a day without readings is recorded as None in both registers)."""
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

    def effective_avg_et0(self) -> float | None:
        """ET0 for the demand model: the real days in the last 3, the same
        way watering_temp treats the temperature. A sensor that drops out
        keeps its last real days until they age out of the window (days
        without readings are recorded as None, never copied forward); with
        none left, None -- the zone then uses its tier target."""
        if not self.outdoor_temp_entity:
            return None
        return self.avg_et0()

    @property
    def demand_model(self) -> str:
        return self.store.state.demand_model

    def et_weekly_target_mm(self) -> float | None:
        """The ET demand model's full-strength weekly target (before the
        growth ramp), or None when this zone uses temperature tiers, or
        uses the ET curve but ET0 isn't available right now -- None always
        means "use the tier target", see const.py's DEMAND_MODEL_*."""
        if self.demand_model != DEMAND_MODEL_ET:
            return None
        et0 = self.effective_avg_et0()
        if et0 is None:
            return None
        return calc.et_weekly_target_mm(et0, self.number("crop_coefficient"))

    def tier_weekly_target_mm(self) -> float:
        """The original temperature-tier weekly target (before the growth
        ramp), from the same inputs the routine cycle uses."""
        return calc.routine_target_weekly_mm(
            self.effective_avg_peak_temp(),
            self.number("hot_temp_threshold"),
            self.number("cool_temp_threshold"),
            self.number("target_weekly_mm"),
            self.number("target_weekly_hot_mm"),
            self.number("target_weekly_cool_mm"),
        )

    def watering_temp(self) -> tuple[float | None, str]:
        """The temperature that picks the hot/cool/normal tier, and where it
        came from:

        - "sensor": the average of the real daily peaks of the last 3 days.
        - "last_known": the same, while the sensor is currently offline --
          its last real days still count until they age out of the window
          (a day with no reading at all is recorded as none, never copied
          forward, so a dead sensor can't hold a tier for more than 3 days).
        - "fallback": a sensor is configured but no real day is on record
          (a new zone before its first full day, or offline 3+ days): the
          Fallback / Manual Temperature slider.
        - "manual": no sensor on this zone: the same slider, which is then
          how you tell the zone about a hot or cool spell by hand.

        The temperature is None only while the slider has no value (see
        _seed_fallback_temp) -- the tier functions read that as normal."""
        fallback = self.fallback_temp()
        entity_id = self.outdoor_temp_entity
        if not entity_id:
            return fallback, "manual"
        avg = self.avg_peak_temp()
        if avg is None:
            return fallback, "fallback"
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            return avg, "last_known"
        return avg, "sensor"

    def effective_avg_peak_temp(self) -> float | None:
        """The temperature every watering decision uses -- see
        watering_temp. avg_peak_temp() above is the plain recorded average
        (None without real data), shown on the diagnostic sensor."""
        return self.watering_temp()[0]

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
        if on and self._stopping:
            return  # nothing new starts once this zone is stopping
        state = self.store.state
        state.lock_on = on
        state.lock_set_ts = dt_util.utcnow().timestamp() if on else None
        state.lock_valve = self.valve_entity if on else None
        # Which run took the lock, so a cancelled run frees only its own.
        self._lock_owner = asyncio.current_task() if on else None
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
            self._arm_valve_stuck_watchdog(new_state.last_changed)
        elif new_state.state == "unavailable":
            fire_at = new_state.last_changed + timedelta(minutes=POWER_LOSS_GRACE_MINUTES)
            self._power_loss_cancel = async_track_point_in_time(self.hass, self._on_power_loss, fire_at)

        if old_state is not None and old_state.state == "unavailable" and new_state.state != "unavailable":
            self.hass.async_create_task(self._on_power_restore(new_state))

    def _valve_stuck_limit_minutes(self) -> float:
        expected = self._expected_pulse_minutes
        if expected is None:
            return VALVE_STUCK_ON_MINUTES
        return max(VALVE_STUCK_ON_MINUTES, expected + VALVE_STUCK_MARGIN_MINUTES)

    @callback
    def _arm_valve_stuck_watchdog(self, turned_on_at) -> None:
        if self._valve_stuck_cancel:
            self._valve_stuck_cancel()
        self._valve_stuck_limit_armed = self._valve_stuck_limit_minutes()
        fire_at = turned_on_at + timedelta(minutes=self._valve_stuck_limit_armed)
        self._valve_stuck_cancel = async_track_point_in_time(self.hass, self._on_valve_stuck, fire_at)

    @callback
    def _on_valve_stuck(self, now) -> None:
        """Port of avocado_valve_safety_watchdog (150min stuck ON)."""
        self.hass.async_create_task(self._fire_valve_stuck())

    async def _fire_valve_stuck(self) -> None:
        limit = getattr(self, "_valve_stuck_limit_armed", VALVE_STUCK_ON_MINUTES)
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
            runtime=int(limit),
            notify_phone=True,
            phone_title="🚨 EMERGENCY: Valve Watchdog Fired",
            phone_msg=f"Valve stayed ON for {limit:.0f} minutes continuously! Emergency shutdown executed to protect the plants.",
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
        state = self.store.state
        if not state.lock_on:
            return
        # A lock taken after startup belongs to a cycle running right now
        # (e.g. a scheduled run that began during the grace period) -- not
        # stale. Clearing it would close that valve mid-pulse and let a
        # second cycle start while the first is still running.
        if state.lock_set_ts is not None and state.lock_set_ts >= self._setup_ts:
            return
        lock_valve = state.lock_valve
        await self._set_lock(False)
        await self._set_abort(False)
        # The valve the lock was taken for, which a changed valve setting
        # may no longer name, and the zone's current valve.
        for valve in dict.fromkeys(v for v in (lock_valve, self.valve_entity) if v):
            valve_state = self.hass.states.get(valve)
            if valve_state is not None and valve_state.state not in ("unavailable", "off"):
                await self.hass.services.async_call(
                    "switch", "turn_off", {"entity_id": valve}, blocking=True
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
            value = float(state.state) if state else None
        except (TypeError, ValueError):
            return None
        if value is None:
            return None
        # Internally litres; a meter reporting gallons, m³, ft³ etc. is
        # converted from its own unit (no unit is taken as litres).
        unit = state.attributes.get("unit_of_measurement")
        if unit and unit != UnitOfVolume.LITERS:
            try:
                return VolumeConverter.convert(value, unit, UnitOfVolume.LITERS)
            except Exception:  # noqa: BLE001 - an unknown unit: use the number as-is
                return value
        return value

    async def _soil_moisture_pct(self) -> float | None:
        """The soil-moisture reading (%) the watering decision may use, or
        None -- "no override, defer to the modeled schedule", never a guess
        of 0% (bone dry) or 100% (saturated), either of which could force a
        wrong decision. See soil_moisture_check for what counts as usable."""
        return self.soil_moisture_reading()

    def soil_moisture_raw(self) -> float | None:
        """Whatever number the probe shows right now, usable or not (for the
        Soil Moisture sensor, which mirrors the probe)."""
        entity_id = self.soil_moisture_entity
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        try:
            return float(state.state) if state else None
        except (TypeError, ValueError):
            return None

    def soil_moisture_check(self) -> tuple[float | None, str | None]:
        """(usable reading, problem). Problem is None for a good reading,
        else "offline" (missing / unavailable / not a number), "implausible"
        (outside 0-100%) or "stale"; with a problem the reading is None.

        "Stale" = no new report for SOIL_MOISTURE_STALE_SECONDS. That can be
        a device that died without going unavailable -- but MQTT
        (Zigbee2MQTT) and template sensors also never re-report an unchanged
        value, and a probe in soaked soil often sits pinned at one wet value
        for days. So a stale reading is handled by what it says:
        - dry or in range: ignored (a frozen "dry" would force watering at
          every scheduled time);
        - wet: still respected, until wet readings have held a due run back
          for SOIL_WET_HOLD_ALERT_INTERVALS routine intervals -- then the
          schedule takes over (see run_routine_irrigation), and the hold
          starts again from scratch."""
        entity_id = self.soil_moisture_entity
        if not entity_id:
            return None, None
        state = self.hass.states.get(entity_id)
        value = self.soil_moisture_raw()
        if state is None or value is None:
            return None, "offline"
        if not 0.0 <= value <= 100.0:
            return None, "implausible"
        reported = getattr(state, "last_reported", None) or state.last_updated
        if (dt_util.utcnow() - reported).total_seconds() > SOIL_MOISTURE_STALE_SECONDS:
            if value >= self.number("soil_moisture_wet_pct") and not self._wet_hold_at_limit():
                return value, None
            return None, "stale"
        return value, None

    def soil_moisture_report_age_hours(self) -> float | None:
        entity_id = self.soil_moisture_entity
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None:
            return None
        reported = getattr(state, "last_reported", None) or state.last_updated
        return round((dt_util.utcnow() - reported).total_seconds() / 3600, 1)

    def _routine_interval_days(self) -> int:
        return calc.routine_interval_days(self.effective_avg_peak_temp(), self.number("hot_temp_threshold"))

    def _wet_hold_days(self) -> float | None:
        since = self.store.state.wet_hold_since_ts
        if since is None:
            return None
        return (dt_util.utcnow().timestamp() - since) / 86400

    def _wet_hold_at_limit(self) -> bool:
        """Wet readings have held a due run back for the alert limit."""
        held = self._wet_hold_days()
        return held is not None and held >= SOIL_WET_HOLD_ALERT_INTERVALS * self._routine_interval_days()

    def soil_moisture_reading(self) -> float | None:
        """The usable reading only -- see soil_moisture_check."""
        return self.soil_moisture_check()[0]

    def soil_moisture_status(self) -> str | None:
        """What the soil-moisture sensor means for the next routine run
        (see calc.soil_moisture_status) -- or why it's being ignored
        (offline / stale / implausible, the schedule then decides). None
        when the zone has no probe."""
        if not self.soil_moisture_entity:
            return None
        value, problem = self.soil_moisture_check()
        if problem is not None:
            return problem
        return calc.soil_moisture_status(
            value,
            self.number("soil_moisture_dry_pct"),
            self.number("soil_moisture_wet_pct"),
        )

    def deficit(self) -> tuple[float, str]:
        """Deficit mode's share of the routine dose right now, and why --
        see calc.deficit_factor."""
        state = self.store.state
        return calc.deficit_factor(
            enabled=state.deficit_enabled,
            water_pct=self.number("deficit_water_pct"),
            until_ts=state.deficit_until_ts,
            now_ts=dt_util.utcnow().timestamp(),
            avg_peak_temp=self.effective_avg_peak_temp(),
            hot_threshold=self.number("hot_temp_threshold"),
            moisture_pct=self.soil_moisture_reading(),
            dry_pct=self.number("soil_moisture_dry_pct"),
            growth_ramp=self.growth_ramp_fraction(),
            # A sensor with no real reading on record: the fallback is only
            # a guess, so the heat guard can't be trusted -- full dose. (A
            # zone without a sensor uses its manual value as given.)
            temp_unavailable=self.watering_temp()[1] == "fallback",
        )

    def routine_target_scale(self) -> float:
        """Everything that scales the routine weekly target: the growth
        ramp and deficit mode."""
        return self.growth_ramp_fraction() * self.deficit()[0]

    def routine_next_estimate(self) -> tuple[float | None, str]:
        """When the next routine run is expected, and what decides it:
        "schedule" (interval and rain dry-down), "soil_dry" (a dry reading
        waters at the next scheduled time, once any rain dry-down is over),
        "soil_wet" (held until the soil dries -- can't be dated), or
        "never_run" (no history to project from)."""
        state = self.store.state
        if state.last_routine_ts is None:
            return None, "never_run"
        status = self.soil_moisture_status()
        if status == "wet":
            return None, "soil_wet"
        est = calc.estimate_next_irrigation(
            last_routine_ts=state.last_routine_ts,
            last_significant_rain_ts=state.last_significant_rain_ts or 0.0,
            avg_peak_temp=self.effective_avg_peak_temp(),
            hot_threshold=self.number("hot_temp_threshold"),
            routine_drydown_days=self.number("routine_drydown_days"),
        ).next_ts
        if status == "dry":
            now_ts = dt_util.utcnow().timestamp()
            drydown_end = (state.last_significant_rain_ts or 0.0) + self.number("routine_drydown_days") * 86400
            return max(now_ts, drydown_end), "soil_dry"
        return est, "schedule"

    async def _check_deficit_end(self) -> None:
        """Deficit mode switches itself off once its end date has passed."""
        state = self.store.state
        if not state.deficit_enabled or state.deficit_until_ts is None:
            return
        if dt_util.utcnow().timestamp() < state.deficit_until_ts:
            return
        state.deficit_enabled = False
        state.deficit_until_ts = None
        await self.store.async_save()
        await self._log_event(
            event_type="Deficit Mode Ended",
            status="Info",
            target_mm=0.0,
            deducted_mm=0.0,
            runtime=0,
            notify_phone=True,
            phone_title="🌶️ Deficit Mode Ended",
            phone_msg="Its end date passed -- routine watering is back to the full dose.",
        )

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
        loop itself. Returns True only for a cycle that ran to the end."""
        if self._stopping:
            return False
        pump_lock = self._get_pump_lock()
        if not await self._acquire_pump(pump_lock):
            return False
        try:
            if self._stopping:
                return False
            return await self._run_pulses_holding_pump(
                count=count,
                pulse_minutes=pulse_minutes,
                rest_minutes=rest_minutes,
                min_pump_watts=min_pump_watts,
                kind=kind,
                target_mm_for_log=target_mm_for_log,
                deducted_mm_for_log=deducted_mm_for_log,
                runtime_for_log=runtime_for_log,
            )
        finally:
            pump_lock.release()

    async def _acquire_pump(self, pump_lock: asyncio.Lock) -> bool:
        """Takes the (possibly shared) pump lock. While queued behind another
        zone, an abort, reload or shutdown of THIS zone gives up the place
        in the queue instead of waiting out the other zone's whole cycle.
        Always queued this way -- even an apparently free lock may already
        be promised to a woken waiter."""
        acquire = asyncio.ensure_future(pump_lock.acquire())
        waker = asyncio.ensure_future(self._abort_event.wait())
        try:
            await asyncio.wait({acquire, waker}, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:
            # Cancelled right as the pump came free: hand it back, or it
            # would stay locked for every zone on this pump for good.
            if acquire.done() and not acquire.cancelled() and acquire.exception() is None:
                pump_lock.release()
            else:
                acquire.cancel()
            raise
        finally:
            waker.cancel()
        if not acquire.done():
            acquire.cancel()
            return False
        if acquire.cancelled() or acquire.exception() is not None:
            return False
        if self._stopping or self.store.state.abort_on:
            pump_lock.release()
            return False
        return True

    async def _run_pulses_holding_pump(
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
        preamble = self.number("pump_preamble_seconds")
        if preamble > 0:
            await self._pause(preamble)

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
        if postamble > 0 and not self._stopping:
            # Runs whether or not the cycle completed cleanly -- the
            # valve is already closed either way, and the point is
            # letting pressure settle before the next zone queued on
            # this same pump opens its own valve. A reload or shutdown cuts
            # it short, so a finished cycle is still recorded as finished.
            await self._pause(postamble)
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
        """Runs `count` on/wait/off pulses. Returns True if completed, False
        if it ended early -- and however it ends early (power-loss abort,
        rain, a reload or shutdown, an error, a cancel) the valve that was
        opened is closed here, while this zone still holds the pump, and
        the minutes already given count toward today's safety cap."""
        # The valve this cycle opens. A reload can change the zone's valve
        # setting mid-cycle; it's still THIS valve that must be closed.
        self._cycle_valve = self.store.state.lock_valve or self.valve_entity
        self._cycle_kind = kind
        self._delivered_minutes = 0.0
        self._pulse_started_ts = None
        self._last_outcome = None
        outcome = None
        try:
            outcome = await self._execute_pulse_loop(
                count=count,
                pulse_minutes=pulse_minutes,
                rest_minutes=rest_minutes,
                min_pump_watts=min_pump_watts,
                kind=kind,
                target_mm_for_log=target_mm_for_log,
                deducted_mm_for_log=deducted_mm_for_log,
                runtime_for_log=runtime_for_log,
            )
        except asyncio.CancelledError:
            # Torn down from outside mid-cycle (e.g. an automation in
            # restart mode, a stopped script): never leave the valve open.
            # The lock is dealt with in _tracked_run.
            await self._close_cycle_valve()
            self._count_partial_run()
            await self.store.async_save()
            raise
        except Exception as err:  # noqa: BLE001 - e.g. the valve switch is offline
            _LOGGER.exception("%s: %s stopped by an error", self.entry.title, kind)
            closed = await self._close_cycle_valve()
            self._count_partial_run()
            if closed:
                # Free the lock now rather than blocking every run for 3
                # hours; not counted as a run, so the next one tries again.
                await self._set_lock(False)
            else:
                # The valve may still be open: keep the lock, so the
                # stuck-valve and stale-lock watchdogs stay in charge.
                await self.store.async_save()
            await self._log_event(
                event_type=f"{kind} Error",
                status="ERROR",
                target_mm=target_mm_for_log,
                deducted_mm=deducted_mm_for_log,
                runtime=int(round(self._delivered_minutes)),
                notify_phone=True,
                phone_title=f"⚠️ {kind.upper()}: Stopped By An Error",
                phone_msg=(
                    f"Stopped: {err}. "
                    + (
                        "The valve is closed; the next scheduled run will try again."
                        if closed
                        else f"{self._cycle_valve} may still be OPEN -- check it now."
                    )
                ),
            )
            return False
        finally:
            # However a pulse ends, a stale pulse length must never stretch
            # the stuck-valve limit for a later, unrelated valve-on.
            self._expected_pulse_minutes = None

        self._last_outcome = outcome
        if outcome == _DONE:
            return True
        self._count_partial_run()
        await self.store.async_save()
        if outcome == _STOPPED:
            await self._log_event(
                event_type=f"{kind} Interrupted",
                status="Interrupted",
                target_mm=target_mm_for_log,
                deducted_mm=deducted_mm_for_log,
                runtime=int(round(self._delivered_minutes)),
                notify_phone=False,
                phone_title="",
                phone_msg="",
            )
        return False

    async def _execute_pulse_loop(
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
    ) -> str:
        valve = self._cycle_valve
        for index in range(1, count + 1):
            if self._stopping:
                return _STOPPED
            if self.store.state.abort_on:
                _LOGGER.warning("%s: aborted by power-loss watchdog before pulse %d", kind, index)
                return _ABORTED
            if index > 1 and await self._stopped_by_rain(
                kind=kind,
                target_mm_for_log=target_mm_for_log,
                deducted_mm_for_log=deducted_mm_for_log,
                runtime_for_log=runtime_for_log,
            ):
                return _RAIN

            if kind == SERVICE_RUN_KIND and self._service_stop.is_set():
                return _USER_STOPPED
            self._expected_pulse_minutes = pulse_minutes
            self._pulse_started_ts = dt_util.utcnow().timestamp()
            await self.hass.services.async_call("switch", "turn_on", {"entity_id": valve}, blocking=True)

            # The pump-power audit only makes sense when a pump-power
            # sensor is actually configured -- without one, _pump_watts()
            # would always read 0.0, which would otherwise warn on every
            # single pulse about a "low" reading that was never real to
            # begin with. Skipping cleanly here (not by making the
            # threshold trivially pass) means no wasted 45s wait either.
            if self.pump_power_entity and not self._stopping and not self.store.state.abort_on:
                # wait_template pump-power check, timeout 45s, continue_on_timeout
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        self._wait_for_pump_watts_or_abort(min_pump_watts, service=kind == SERVICE_RUN_KIND),
                        timeout=PUMP_POWER_WAIT_TIMEOUT_SECONDS,
                    )
                if (
                    not self._stopping
                    and not self.store.state.abort_on
                    and not (kind == SERVICE_RUN_KIND and self._service_stop.is_set())
                    and await self._pump_watts() < min_pump_watts
                ):
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
            if not self._stopping and not self.store.state.abort_on:
                await self._wait_pulse(pulse_minutes * 60, service=kind == SERVICE_RUN_KIND)

            if kind == SERVICE_RUN_KIND and self._service_stop.is_set() and not (
                self._stopping or self.store.state.abort_on
            ):
                # Switched off by the person: a normal end for a service run --
                # once the valve confirms it's closed. If it doesn't, this is
                # an error (keeps the lock, alerts), not a clean stop.
                self._expected_pulse_minutes = None
                if not await self._close_cycle_valve():
                    raise HomeAssistantError(f"{valve} did not confirm it closed")
                self._end_pulse(pulse_minutes, full=False)
                return _USER_STOPPED

            if self._stopping or self.store.state.abort_on:
                self._expected_pulse_minutes = None
                await self._close_cycle_valve()
                self._end_pulse(pulse_minutes, full=False)
                if self._stopping:
                    return _STOPPED
                _LOGGER.warning("%s: aborted by power-loss watchdog during pulse %d", kind, index)
                return _ABORTED

            self._expected_pulse_minutes = None
            await self.hass.services.async_call("switch", "turn_off", {"entity_id": valve}, blocking=True)
            self._end_pulse(pulse_minutes, full=True)

            if index < count:
                await self._pause(rest_minutes * 60)
        return _DONE

    async def _wait_pulse(self, seconds: float, *, service: bool) -> None:
        """The open-valve wait of a pulse: ends early on an abort, a reload
        or shutdown, or -- for a service run -- the person switching it off.
        (Kept as one wait_for with the pulse length as its timeout, like
        every pulse wait.)"""
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._abort_or_service_stop(service), timeout=seconds)

    async def _abort_or_service_stop(self, service: bool) -> None:
        if not service:
            await self._abort_event.wait()
            return
        waiters = {
            asyncio.ensure_future(self._abort_event.wait()),
            asyncio.ensure_future(self._service_stop.wait()),
        }
        try:
            await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for waiter in waiters:
                waiter.cancel()

    def _end_pulse(self, pulse_minutes: float, *, full: bool) -> None:
        """Adds the pulse just ended to the minutes this cycle has given."""
        if self._pulse_started_ts is None:
            return
        if full:
            given = pulse_minutes
        else:
            elapsed = (dt_util.utcnow().timestamp() - self._pulse_started_ts) / 60.0
            given = min(max(elapsed, 0.0), pulse_minutes)
        self._delivered_minutes += given
        self._pulse_started_ts = None

    def _count_partial_run(self) -> None:
        """A cycle that ended early isn't counted as a run (the next one
        decides again), but the water it did give counts toward today's
        daily safety cap -- otherwise an early stop plus a re-run could go
        past it. Counted once; the caller saves."""
        if self._pulse_started_ts is not None:
            # Ended mid-pulse by an exception or cancel.
            elapsed = (dt_util.utcnow().timestamp() - self._pulse_started_ts) / 60.0
            self._delivered_minutes += max(elapsed, 0.0)
            self._pulse_started_ts = None
        self.store.state.today_runtime_minutes += self._delivered_minutes

    async def _close_cycle_valve(self) -> bool:
        """Best-effort close of the valve this cycle opened, for every early
        exit. Sends turn_off even if the valve already reports "off" -- a
        real device can report its state a moment after the command, so
        "off" right after a turn_on may simply not have caught up yet.
        Returns True once the valve is confirmed not open; if even this
        fails, the stuck-valve watchdog is still armed for it."""
        valve = self._cycle_valve or self.valve_entity
        state = self.hass.states.get(valve)
        if state is None or state.state == "unavailable":
            return state is None
        try:
            await self.hass.services.async_call("switch", "turn_off", {"entity_id": valve}, blocking=True)
        except Exception:  # noqa: BLE001 - last line of defence, must not raise
            _LOGGER.exception("%s: could not close valve %s", self.entry.title, valve)
            return False
        return await self._valve_confirmed_closed(valve)

    async def _valve_confirmed_closed(self, valve: str, seconds: float = VALVE_CLOSE_CONFIRM_SECONDS) -> bool:
        """Waits briefly for a valve that was just told to close to report
        it -- some devices take a few seconds to confirm."""
        for _ in range(int(seconds * 2)):
            state = self.hass.states.get(valve)
            if state is None or state.state != "on":
                return True
            await asyncio.sleep(0.5)
        state = self.hass.states.get(valve)
        return state is None or state.state != "on"

    async def _pause(self, seconds: float) -> None:
        """A wait inside a cycle (soak gap between pulses, pump preamble),
        cut short by an abort, reload or shutdown -- a stopped cycle mustn't
        sit on a shared pump for the rest of a long gap."""
        sleeper = asyncio.ensure_future(asyncio.sleep(seconds))
        waker = asyncio.ensure_future(self._abort_event.wait())
        try:
            await asyncio.wait({sleeper, waker}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            sleeper.cancel()
            waker.cancel()

    async def _stopped_by_rain(
        self,
        *,
        kind: str,
        target_mm_for_log: float,
        deducted_mm_for_log: float,
        runtime_for_log: int,
    ) -> bool:
        """Before each later pulse: the same 30-minute rain check that can
        cancel a cycle before it starts. Rain that arrives mid-cycle stops
        the rest of it. Not counted as a run -- the next scheduled run
        decides again with this rain taken into account."""
        rain_30min = self.rain_windows()["30min"]
        if rain_30min <= self.number("preirrigation_rain_threshold_mm"):
            return False
        given = int(round(self._delivered_minutes))
        await self._set_lock(False)
        await self._log_event(
            event_type=f"{kind} Stopped By Rain",
            status="Stopped",
            target_mm=target_mm_for_log,
            deducted_mm=deducted_mm_for_log,
            runtime=given,
            notify_phone=True,
            phone_title=f"🌧️ {kind} Stopped By Rain",
            phone_msg=(
                f"Stopped after {given} of {runtime_for_log} min: "
                f"{units.depth_text(rain_30min, self.imperial)} fell in the last 30 minutes. "
                "The next scheduled run decides again, taking this rain into account."
            ),
        )
        return True

    async def _wait_for_pump_watts_or_abort(self, min_pump_watts: float, service: bool = False) -> None:
        """The pump-power wait, cut short by an abort, reload or shutdown --
        or, for a service run, the person switching it off."""
        pump = asyncio.ensure_future(self._wait_for_pump_watts(min_pump_watts))
        wakers = {asyncio.ensure_future(self._abort_event.wait())}
        if service:
            wakers.add(asyncio.ensure_future(self._service_stop.wait()))
        try:
            await asyncio.wait({pump, *wakers}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            pump.cancel()
            for waker in wakers:
                waker.cancel()

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
        # Forecasts come in the weather entity's own unit -- inches on an HA
        # set to imperial. The thresholds are mm, so convert first.
        unit = state.attributes.get("precipitation_unit")
        precip_mm = float(precip) * PRECIP_UNIT_TO_MM.get(unit, 1.0)
        return precip_mm, (float(prob) if prob is not None else None)

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
                f"Skipping {cycle} run: {units.depth_text(precip_mm, self.imperial)} rain forecast"
                + (f" ({prob_pct:.0f}% probability)" if prob_pct is not None else "")
                + f". Will override after {override_days:.0f} dry day(s) with no measured rain."
            ),
        )
        return False

    @_tracked_run
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
            if self._service_active and calc.deep_soak_due(
                now_ts - (state.last_deep_soak_ts or 0.0),
                self.number("deep_soak_interval_days"),
                DEEP_SOAK_INTERVAL_BUFFER_SECONDS,
            ):
                await self._log_skipped_for_service("Deep Soak")
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
                phone_msg=f"Cancelled: {units.depth_text(rain_30min, self.imperial)} fell in the last 30 minutes.",
            )
            return

        if state.lock_on or self._service_active:
            # Something took the zone while this cycle was checking its gates.
            return
        await self._set_lock(True)
        await self._set_abort(False)

        completed = await self._run_pulses(
            count=plan.pulse_count,
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

        done_ts = dt_util.utcnow().timestamp()
        state.last_deep_soak_ts = done_ts
        # A deep soak also satisfies the routine watering: without this the
        # routine ran on its own clock and could add a full dose the very
        # next morning. Everything keyed on the last routine follows from
        # here -- the routine interval, the rain-credit window, the
        # next-run estimate and Days Until Next Run. Only a completed soak
        # counts (an aborted or interrupted one returned above).
        state.last_routine_ts = done_ts
        state.today_runtime_minutes += plan.total_runtime_minutes
        await self.store.async_save()
        await self._end_wet_hold()  # the zone has just been watered
        await self._set_lock(False)
        next_ts, _ = self.routine_next_estimate()
        next_text = (
            f" Next routine: {dt_util.as_local(dt_util.utc_from_timestamp(next_ts)).strftime('%a %d %b %H:%M')}."
            if next_ts is not None
            else ""
        )
        await self._log_event(
            event_type="Deep Soak Completed",
            status="Completed",
            target_mm=plan.target_mm,
            deducted_mm=0.0,
            runtime=plan.total_runtime_minutes,
            notify_phone=True,
            phone_title="🚿 Deep Soak Completed",
            phone_msg=(
                f"DEEP SOAK COMPLETED: {units.depth_text(plan.target_mm, self.imperial)} applied over "
                f"{plan.pulse_count} pulse(s) ({plan.total_runtime_minutes} min). Counts as routine "
                f"watering too.{next_text}"
            ),
            extra_log="Counts as routine watering: routine interval restarts from now.",
        )

    @_tracked_run
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
            if self._service_active and calc.routine_due(
                elapsed_seconds,
                calc.routine_interval_days(self.effective_avg_peak_temp(), self.number("hot_temp_threshold")),
                ROUTINE_INTERVAL_BUFFER_SECONDS,
            ):
                await self._log_skipped_for_service("Routine Irrigation")
            return
        if self._is_snoozed_today():
            return
        await self._check_deficit_end()

        # effective_avg_peak_temp() (not avg_peak_temp()) drives this: real
        # recorded days when there are any, otherwise the Fallback / Manual
        # Temperature slider -- see watering_temp.
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
            if interval_due:
                # Due by the schedule, but the soil is wet: say so, instead
                # of skipping silently.
                await self._note_wet_hold(now_ts, interval_days, moisture_pct)
                await self._log_event(
                    event_type="Routine Skipped (Soil Wet)",
                    status="Skipped",
                    target_mm=0.0,
                    deducted_mm=0.0,
                    runtime=0,
                    notify_phone=False,
                    phone_title="",
                    phone_msg="",
                    extra_log=f"Soil moisture {moisture_pct:.0f}% is at or above the wet threshold.",
                )
            else:
                await self._end_wet_hold_if_not_wet(moisture_pct)
            return
        await self._end_wet_hold_if_not_wet(moisture_pct)
        await self._note_frozen_wet_probe()
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
        deficit_share, deficit_reason = self.deficit()
        # The routine dose scales with the growth ramp and deficit mode alike.
        scale = ramp * deficit_share
        et_weekly = self.et_weekly_target_mm()
        routine_pulse_count = max(int(round(self.number("routine_pulse_count"))), 1)
        days_elapsed = int(elapsed_seconds / 86400)
        plan = calc.plan_routine_irrigation(
            avg_peak_temp=avg_peak_temp,
            hot_threshold=hot_threshold,
            cool_threshold=self.number("cool_temp_threshold"),
            normal_weekly_mm=self.number("target_weekly_mm") * scale,
            hot_weekly_mm=self.number("target_weekly_hot_mm") * scale,
            cool_weekly_mm=self.number("target_weekly_cool_mm") * scale,
            flow_rate=self.number("flow_rate_mm_per_min"),
            days_elapsed=days_elapsed,
            today_rain_mm=self.today_rain_mm(),
            rain_day_history_mm=state.rain_day_history_mm,
            rain_eff_low=self.number("rain_eff_low"),
            rain_eff_mid=self.number("rain_eff_mid"),
            rain_eff_high=self.number("rain_eff_high"),
            pulse_count=routine_pulse_count,
            min_pulse_minutes=int(ROUTINE_MIN_PULSE_MINUTES),
            weekly_target_override_mm=(et_weekly * scale) if et_weekly is not None else None,
        )

        # Only a zone that HAS watered before can be overdue -- a brand-new
        # one would otherwise measure its gap from 1970 (~20,000 days).
        if state.last_routine_ts is not None and days_elapsed > 10:
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
                phone_msg=f"Rain credit ({units.depth_text(plan.eff_rain_mm, self.imperial)}) already covers target ({units.depth_text(plan.interval_target_mm, self.imperial)}) — no watering needed.",
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
                phone_msg=f"Cancelled: {units.depth_text(rain_30min, self.imperial)} fell in the last 30 minutes.",
            )
            return

        if state.lock_on or self._service_active:
            # Something took the zone while this cycle was checking its gates.
            return
        await self._end_wet_hold()  # watering is actually starting
        await self._set_lock(True)
        await self._set_abort(False)

        completed = await self._run_pulses(
            count=plan.pulse_count,
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
            phone_msg=(
                f"Applied {plan.calc_runtime_minutes} min (Target: {units.depth_text(plan.interval_target_mm, self.imperial)}, "
                f"Rain Deducted: {units.depth_text(plan.eff_rain_mm, self.imperial)})."
                + self._routine_notes(interval_due, moisture_pct, deficit_share, deficit_reason)
            ),
        )

    async def _note_wet_hold(self, now_ts: float, interval_days: int, moisture_pct: float) -> None:
        """A due run skipped for wet soil. Soil can stay wet for days after
        heavy rain, so this never overrides the probe -- but once wet
        readings have held watering back for SOIL_WET_HOLD_ALERT_INTERVALS
        routine intervals, send one alert to check it (a probe sitting in a
        puddle, or reading wrong)."""
        state = self.store.state
        if state.wet_hold_since_ts is None:
            state.wet_hold_since_ts = now_ts
            state.wet_hold_alerted = False
            await self.store.async_save()
            return
        held_days = (now_ts - state.wet_hold_since_ts) / 86400
        if state.wet_hold_alerted or held_days < SOIL_WET_HOLD_ALERT_INTERVALS * interval_days:
            return
        state.wet_hold_alerted = True
        await self.store.async_save()
        await self._log_event(
            event_type="Soil Probe Check",
            status="Warning",
            target_mm=0.0,
            deducted_mm=0.0,
            runtime=0,
            notify_phone=True,
            phone_title="🌱 Check the soil probe",
            phone_msg=(
                f"Wet soil readings ({moisture_pct:.0f}%) have held routine watering back for "
                f"{held_days:.0f} days. If it hasn't rained much, check the probe (placement, "
                f"battery, reading) -- it's still being followed."
            ),
            extra_log=f"Wet-soil hold for {held_days:.1f} days (routine interval {interval_days} days).",
        )

    async def _end_wet_hold_if_not_wet(self, moisture_pct: float | None) -> None:
        """A fresh reading that isn't wet ends a wet hold. (An unusable
        reading doesn't: the hold also ends when a routine run starts.)"""
        state = self.store.state
        if state.wet_hold_since_ts is None or moisture_pct is None:
            return
        if moisture_pct >= self.number("soil_moisture_wet_pct"):
            return
        await self._end_wet_hold()

    async def _end_wet_hold(self) -> None:
        state = self.store.state
        if state.wet_hold_since_ts is None:
            return
        state.wet_hold_since_ts = None
        state.wet_hold_alerted = False
        state.wet_hold_frozen_alerted = False
        await self.store.async_save()

    async def _note_frozen_wet_probe(self) -> None:
        """The wet hold reached its limit on a probe that hasn't reported for
        24 h: its (wet) reading is now ignored and the schedule decides.
        Say so once per hold."""
        state = self.store.state
        if state.wet_hold_frozen_alerted or not self._wet_hold_at_limit():
            return
        raw = self.soil_moisture_raw()
        if self.soil_moisture_check()[1] != "stale" or raw is None or raw < self.number("soil_moisture_wet_pct"):
            return
        held_days = self._wet_hold_days() or 0.0
        state.wet_hold_frozen_alerted = True
        await self.store.async_save()
        await self._log_event(
            event_type="Soil Probe Check",
            status="Warning",
            target_mm=0.0,
            deducted_mm=0.0,
            runtime=0,
            notify_phone=True,
            phone_title="🌱 Soil probe looks frozen",
            phone_msg=(
                f"The soil probe has read wet ({raw:.0f}%) for {held_days:.0f} days without a new report "
                f"in 24 h, so watering follows the schedule again. Check the probe (battery, connection)."
            ),
            extra_log=f"Wet-soil hold at {held_days:.1f} days, probe not reporting: schedule decides.",
        )

    def _routine_notes(
        self, interval_due: bool, moisture_pct: float | None, deficit_share: float, deficit_reason: str
    ) -> str:
        """What moisture and deficit mode did to this run, for the message."""
        notes = []
        if not interval_due and moisture_pct is not None:
            notes.append(f"Soil moisture {moisture_pct:.0f}% (dry) -- watered before the schedule was due.")
        if deficit_reason == "active":
            notes.append(f"Deficit mode: {deficit_share * 100:.0f}% dose.")
        elif deficit_reason == "full_dose_hot":
            notes.append("Deficit mode: full dose today (hot weather).")
        elif deficit_reason == "full_dose_soil_dry":
            notes.append("Deficit mode: full dose today (soil at the dry threshold).")
        elif deficit_reason == "full_dose_no_temp":
            notes.append("Deficit mode: full dose (no temperature reading on record).")
        elif deficit_reason == "full_dose_young_plant":
            notes.append("Deficit mode: full dose (plant still on its growth ramp).")
        return "".join(" " + n for n in notes)

    @_tracked_run
    async def test_pulse(self, seconds: int) -> None:
        """Bench-test helper: one short valve pulse bypassing every schedule/
        dry-down/rain gate, so the physical valve + pump-power audit path can
        be verified before the real schedule runs unattended. Still goes
        through the mutex lock and the same watchdogs as a real cycle."""
        if self.store.state.lock_on or self._service_active:
            _LOGGER.warning("ZoneFlow: test pulse skipped, lock already held")
            return
        await self._set_lock(True)
        await self._set_abort(False)
        completed = await self._run_pulses(
            count=1,
            pulse_minutes=max(seconds / 60, 1 / 60),
            rest_minutes=0,
            min_pump_watts=self.number("pump_min_watts"),
            kind="Test Pulse",
            target_mm_for_log=0.0,
            deducted_mm_for_log=0.0,
            runtime_for_log=0,
        )
        if not completed:
            return  # aborted, stopped or failed -- already handled and logged
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

    # ------------------------------------------------------------------
    # Service / check runs
    # ------------------------------------------------------------------
    @property
    def service_active(self) -> bool:
        return self._service_active

    def add_service_listener(self, listener) -> Any:
        """Called when a service run starts or ends (the Service Mode
        switch shows it). Returns the remover."""
        self._service_listeners.append(listener)
        return lambda: self._service_listeners.remove(listener)

    def _notify_service_listeners(self) -> None:
        for listener in list(self._service_listeners):
            listener()

    async def start_service_run(self, minutes: float, *, from_switch: bool = False) -> None:
        """Run the valve for `minutes` to check emitters, flush a line or
        find a leak -- the 1/5/10 min buttons and the Service Mode switch.

        Never counted as watering: it doesn't set Last Routine / Last Deep
        Soak, move the schedule or feed self-tuning. It does take the zone
        lock and the shared pump and run the same pump audit, watchdogs and
        confirmed valve close as a real cycle, and its minutes count toward
        the daily runtime safety cap. Refused (with a message) while the
        zone or its shared pump is busy, or when the daily cap has no room
        left; a run longer than the room left is shortened to fit.

        Returns once the run has started; the run itself carries on in the
        background so a button press or switch doesn't hang."""
        state = self.store.state
        if self._stopping:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="zone_busy")
        # _runs: a cycle may still be checking its gates before it takes the
        # lock -- it must not end up running alongside a service run.
        if self._service_active or state.lock_on or self._runs:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="zone_busy")
        pump_lock = self._get_pump_lock()
        if pump_lock.locked() or getattr(pump_lock, "_waiters", None):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="pump_busy")
        room = self.number("max_daily_runtime_minutes") - state.today_runtime_minutes
        if room < 1:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="daily_cap_reached")
        shortened = float(minutes) > room
        minutes = min(float(minutes), room)
        self._service_active = True
        self._service_stop.clear()
        self._notify_service_listeners()
        self.hass.async_create_task(self._service_task(minutes, from_switch, shortened))

    async def _service_task(self, minutes: float, from_switch: bool, shortened: bool) -> None:
        """Owns the service-run flags, so they're cleared however the run
        ends -- including a zone that started stopping before it began."""
        try:
            await self._service_run(minutes, from_switch, shortened)
        finally:
            self._service_active = False
            self._service_stop.clear()
            self._notify_service_listeners()

    async def stop_service_run(self) -> None:
        """The Service Mode switch turned off: end the service run now."""
        if self._service_active:
            self._service_stop.set()

    @_tracked_run
    async def _service_run(self, minutes: float, from_switch: bool, shortened: bool) -> None:
        state = self.store.state
        if state.lock_on:
            return
        await self._set_lock(True)
        await self._set_abort(False)
        self._last_outcome = None
        completed = await self._run_pulses(
            count=1,
            pulse_minutes=minutes,
            rest_minutes=0,
            min_pump_watts=self.number("pump_min_watts"),
            kind=SERVICE_RUN_KIND,
            target_mm_for_log=0.0,
            deducted_mm_for_log=0.0,
            runtime_for_log=int(round(minutes)),
        )
        stopped_by_person = self._last_outcome == _USER_STOPPED
        if not completed and not stopped_by_person:
            return  # aborted, interrupted or failed -- already handled and logged
        if completed:
            # A finished pulse isn't counted by the pulse loop (a watering
            # cycle adds its planned minutes itself); a stopped one was.
            state.today_runtime_minutes += minutes
        await self.store.async_save()
        await self._set_lock(False)
        ran = self._delivered_minutes
        auto_off = completed and from_switch
        cap_note = " (shortened to fit today's runtime safety cap)" if shortened else ""
        await self._log_event(
            event_type=SERVICE_RUN_KIND,
            status="Auto-Off" if auto_off else ("Completed" if completed else "Stopped"),
            target_mm=0.0,
            deducted_mm=0.0,
            runtime=int(round(ran)),
            notify_phone=auto_off,
            phone_title="🔧 Service Mode switched off",
            phone_msg=(
                f"Service Mode ran for {ran:.0f} min and switched itself off"
                + (cap_note + "." if shortened else " (the auto-off time).")
            ),
            extra_log=f"Service run: {ran:.1f} min, not counted as watering{cap_note}.",
        )

    async def _log_skipped_for_service(self, kind: str) -> None:
        """A scheduled cycle found a service run holding the zone: say so
        (it runs at its next scheduled time instead)."""
        await self._log_event(
            event_type=f"{kind} Skipped (Service Run)",
            status="Skipped",
            target_mm=0.0,
            deducted_mm=0.0,
            runtime=0,
            notify_phone=False,
            phone_title="",
            phone_msg="",
        )

    async def reset_lock(self) -> None:
        """Manual emergency reset (button/service), not time-gated. Also
        ends a service run, so the valve doesn't keep running unlocked."""
        if self._service_active:
            self._service_stop.set()
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
