"""The greenhouse / indoor climate engine (1.6): reads the zone's inside
sensors, asks greenhouse_logic.decide() what each device role should be doing,
and switches the devices -- with minimum on/off times, respect for a person's
own switching (manual hold), confirmation that devices really moved, and
supervised misting pulses.

Safety rules this module keeps:
  * A mister is never left on by ZoneFlow: every pulse ends with a confirmed
    off; a stop, reload, shutdown, "control off", failsafe or lost sensor
    switches it off first. A mister that will not switch off halts misting
    (and tells the person) until Reset Irrigation Lock is pressed.
  * A mister found on at startup is switched off.
  * An inside sensor that is unavailable, silent for "Sensor Offline After"
    or implausible puts the zone in failsafe (after a short grace): misters
    off, the heater as "Heater Failsafe" says, vents and fans as "Sensor
    Failsafe" says (shut while the failsafe heater may run).
  * A heater ZoneFlow switched on is switched off at unload, shutdown and
    "Greenhouse Control" off; fans and vents are left as they are.
  * Only greenhouse and indoor zones run any of this.
  * Every device call has a time limit (actuators.py).
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
import logging
import time
from typing import TYPE_CHECKING, Any, Callable

from homeassistant.exceptions import ServiceValidationError
from homeassistant.core import Context, Event, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later, async_track_state_change_event, async_track_time_interval
from datetime import timedelta
import homeassistant.util.dt as dt_util

from . import actuators, greenhouse_logic as gl, issues, messages, units
from .const import (
    CONF_CLIMATE,
    DEVICE_ROLE_KEYS,
    DOMAIN,
    GREENHOUSE_CONFIRM_SECONDS,
    GREENHOUSE_EVAL_SECONDS,
    GREENHOUSE_INSIDE_TEMP_RANGE,
    GREENHOUSE_ISSUE_OUTSIDE_SECONDS,
    GREENHOUSE_ISSUE_SENSOR_SECONDS,
    GREENHOUSE_SENSOR_MISMATCH_C,
    GREENHOUSE_SENSOR_MISMATCH_SECONDS,
    GREENHOUSE_MANUAL_GRACE_SECONDS,
    GREENHOUSE_MIN_TIMES,
    GREENHOUSE_MIST_STUCK_MARGIN_SECONDS,
    GREENHOUSE_OUTSIDE_TEMP_RANGE,
    GREENHOUSE_SENSOR_GRACE_SECONDS,
    LEVEL_INFO,
    LEVEL_WARNING,
    VALVE_CLOSE_CONFIRM_SECONDS,
)

if TYPE_CHECKING:
    from .controller import ZoneFlowController

_LOGGER = logging.getLogger(__name__)

ROLE_ENTITIES = {
    "fans": "fan_entities",
    "vents": "vent_entities",
    "misters": "mister_entities",
    "heater": "heater_entities",
}
# Auto Resume off: a hold that only Resume Automatic ends (10 years; a
# number, so the saved state stays plain JSON).
NO_AUTO_RESUME_SECONDS = 10 * 365 * 86400.0
ROLE_LABEL = {"fans": "Fans", "vents": "Vents", "misters": "Misting", "heater": "Heater"}
ISSUE_SENSOR = "greenhouse_sensor"
ISSUE_OUTSIDE = "greenhouse_outside_sensor"
ISSUE_DEVICE = "greenhouse_device"
ISSUE_MIST_HALTED = "greenhouse_mist_halted"
ISSUE_ON_BACKUP = "greenhouse_on_backup_sensor"
ISSUE_MISMATCH = "greenhouse_sensor_mismatch"


async def async_release_devices(hass: HomeAssistant, entry) -> None:
    """A greenhouse zone was deleted: nothing controls its devices any more,
    so they are switched off (vents closed) rather than left running. Only on
    deletion -- a reload or a restart leaves the devices alone. A device that
    won't answer is skipped (and logged)."""
    data = {**entry.data, **entry.options}
    for role_key in DEVICE_ROLE_KEYS:
        for entity_id in data.get(role_key) or []:
            try:
                await actuators.async_set(hass, entity_id, False)
            except Exception as err:  # noqa: BLE001 -- one stubborn device must not stop the rest
                _LOGGER.warning("ZoneFlow: could not switch off %s after its zone was deleted: %s", entity_id, err)


class GreenhouseManager:
    def __init__(self, controller: ZoneFlowController, grace: Callable[[], float]) -> None:
        self.c = controller
        self.hass: HomeAssistant = controller.hass
        self._grace = grace  # startup grace in seconds, read when it is needed
        self._unsubs: list[Callable[[], None]] = []
        self._timers: set[Callable[[], None]] = set()
        self._lock = asyncio.Lock()
        self._stopping = False
        # Nothing is switched until the startup grace has passed: before
        # that the sliders hold defaults, not what the person set.
        self._started = False
        self._latches = gl.Latches()
        self._decision: gl.Decision | None = None
        self._readings: gl.Readings | None = None
        self._commanded: dict[str, tuple[bool, float]] = {}
        self._unresponsive: set[str] = set()
        self._position_sent: dict[str, tuple[float, float]] = {}
        self._inside_bad_since: float | None = None
        self._outside_bad_since: float | None = None
        self._failsafe_active = False
        self._last_block: str | None = None
        # Backup inside sensors
        self._primary_temp: float | None = None
        self._backup_temp: float | None = None
        self._inside_source: str | None = None
        self._on_backup_since: float | None = None
        self._mismatch_since: float | None = None
        # Misting
        self._mist_task: asyncio.Task | None = None
        self._mist_stop = asyncio.Event()
        self._mist_started: float | None = None  # when the pulse now running began
        self._mist_stuck_cancel: Callable[[], None] | None = None

    # ------------------------------------------------------------------
    # Setup / unload
    # ------------------------------------------------------------------
    @property
    def active(self) -> bool:
        # An outdoor zone never runs the climate engine, even with devices
        # left in its settings from when it was a greenhouse.
        return self.c.has_climate_devices and not self.c.is_outdoor

    def _role_entities(self, role: str) -> list[str]:
        return list(getattr(self.c, ROLE_ENTITIES[role]))

    def _all_devices(self) -> list[str]:
        return [e for role in ROLE_ENTITIES for e in self._role_entities(role)]

    def _role_of(self, entity_id: str) -> str | None:
        for role in ROLE_ENTITIES:
            if entity_id in self._role_entities(role):
                return role
        return None

    async def async_setup(self) -> None:
        if not self.active:
            return
        c = self.c
        sensors = [
            e for e in (c.inside_temp_entity, c.inside_humidity_entity, c.light_entity, c.outside_temp_entity, *c.backup_temp_entities)
            if e
        ]
        if sensors:
            self._unsubs.append(async_track_state_change_event(self.hass, sensors, self._on_sensor_change))
        devices = self._all_devices()
        if devices:
            self._unsubs.append(async_track_state_change_event(self.hass, devices, self._on_device_change))
        self._unsubs.append(
            async_track_time_interval(self.hass, self._on_tick, timedelta(seconds=GREENHOUSE_EVAL_SECONDS))
        )
        # A mister left on by a restart is switched off at once; and again
        # after the startup grace, when devices that weren't up yet can be.
        c.entry.async_create_background_task(self.hass, self._startup(), name=f"zoneflow_greenhouse_{c.entry.entry_id}")

    async def _startup(self) -> None:
        await self._misters_off("startup")
        await asyncio.sleep(self._grace())
        if self._stopping:
            return
        self._started = True
        await self._misters_off("startup")
        await self.async_evaluate("startup")

    async def async_unload(self) -> None:
        self._stopping = True
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        for cancel in list(self._timers):
            cancel()
        self._timers.clear()
        await self._stop_misting(wait=15.0)
        self._cancel_mist_watchdog()
        await self._heater_off_if_ours()

    async def async_shutdown(self) -> None:
        """Home Assistant is stopping: misters off, within its short budget."""
        self._stopping = True
        await self._stop_misting(wait=5.0)
        await self._heater_off_if_ours()

    # ------------------------------------------------------------------
    # Triggers
    # ------------------------------------------------------------------
    @callback
    def _on_sensor_change(self, event: Event) -> None:
        self.hass.async_create_task(self.async_evaluate("sensor"))

    @callback
    def _on_tick(self, now) -> None:
        self.hass.async_create_task(self.async_evaluate("tick"))

    @callback
    def _on_device_change(self, event: Event) -> None:
        """A device changed. If it isn't what ZoneFlow asked for (and isn't
        just a slow report of what it asked), a person did it: leave that
        role alone for the Manual Hold time."""
        new = event.data.get("new_state")
        old = event.data.get("old_state")
        entity = event.data["entity_id"]
        if new is None or (old is not None and old.state == new.state):
            return
        if (old is None or old.state in actuators.OFFLINE) and not event.context.user_id:
            # Back from offline (a reboot, a Wi-Fi drop): not a person's
            # choice. The next evaluation puts it right.
            return
        on = actuators.state_is_on(entity, new)  # this event's state, not a later one
        role = self._role_of(entity)
        if on is None or role is None:
            return
        if role == "misters" and not on and not event.context.user_id:
            # A mister going off by itself (its own auto-off timer, a cut-out)
            # is the safe direction and no hold: the pulse loop sees it.
            return
        now = time.time()
        commanded = self._commanded.get(entity)
        # Not ZoneFlow's command: a person (the HA app, a wall button, the
        # device's own app) or another automation.
        manual = bool(event.context.user_id) or commanded is None
        if commanded is not None:
            was_on, when = commanded
            if on == was_on or now - when < GREENHOUSE_MANUAL_GRACE_SECONDS:
                if not manual:
                    return
            else:
                manual = True
        if not manual:
            return
        # The person's state now, not ZoneFlow's: forget the command (so it
        # is not confirmed, nor switched off at unload as if ZoneFlow's).
        self._commanded.pop(entity, None)
        hold = self.hold_seconds()
        if role == "misters" and on:
            # A mister switched on by hand is water running unsupervised:
            # it is left on at most Max Misting Per Hour, then switched off.
            hold = min(hold, self.c.number("max_mist_minutes_per_hour") * 60)
        self.c.store.state.gh_hold_until[role] = now + hold
        if role == "misters":
            self._mist_stop.set()  # the pulses stop; the person's choice is left as it is
        self.hass.async_create_task(self._log(f"Manual Hold: {ROLE_LABEL[role]}", "HOLD"))
        self.hass.async_create_task(self.c.store.async_save())
        self.hass.async_create_task(self.async_evaluate("manual"))

    def hold_seconds(self) -> float:
        """How long a device switched by hand is left alone: Auto Resume
        After, or (Auto Resume off) until Resume Automatic is pressed."""
        if self.c.store.state.gh_auto_resume:
            return self.c.number("auto_resume_hours") * 3600
        return NO_AUTO_RESUME_SECONDS

    async def async_resume_automatic(self) -> None:
        """The Resume Automatic button: every manual hold ends now."""
        state = self.c.store.state
        if not state.gh_hold_until:
            # Nothing was switched by hand: say so (Home Assistant shows
            # this as a message), and look at the climate again anyway.
            await self.async_evaluate("resume")
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="nothing_on_hold")
        state.gh_hold_until.clear()
        await self.c.store.async_save()
        await self._log("Automatic Resumed", "INFO")
        await self.async_evaluate("resume")

    async def async_auto_resume_changed(self) -> None:
        """Auto Resume switched on: holds that were waiting for the button
        now end after Auto Resume After (from now) instead."""
        state = self.c.store.state
        if state.gh_auto_resume:
            limit = time.time() + self.hold_seconds()
            state.gh_hold_until = {role: min(until, limit) for role, until in state.gh_hold_until.items()}
        await self.c.store.async_save()
        await self.async_evaluate("setting")

    def _release_hot_heater(self, readings, now: float) -> bool:
        """A heater switched on by hand is taken back once the inside
        temperature passes the vent temperature, whatever the hold: a
        forgotten heater must never overheat the greenhouse."""
        if self._held("heater", now) <= 0 or readings.inside_temp is None:
            return False
        if readings.inside_temp <= self.c.number("vent_temp"):
            return False
        if not any(actuators.state_is_on(e, self.hass.states.get(e)) for e in self.c.heater_entities):
            return False
        self.c.store.state.gh_hold_until.pop("heater", None)
        return True

    def _held(self, role: str, now: float) -> float:
        """Seconds of manual hold left for the role (0 = none)."""
        until = self.c.store.state.gh_hold_until.get(role, 0.0)
        return max(0.0, until - now)

    # ------------------------------------------------------------------
    # Settings and readings
    # ------------------------------------------------------------------
    def failsafe_mode(self) -> str:
        chosen = self.c.store.state.ventilation_failsafe
        if chosen in gl.FAILSAFE_OPTIONS:
            return chosen
        climate = self.c.entry.options.get(CONF_CLIMATE, self.c.entry.data.get(CONF_CLIMATE))
        return gl.PRESET_FAILSAFE.get(climate, gl.FAILSAFE_CLOSED)

    def failsafe_vent_mode(self) -> str:
        """What vents and fans really do in the failsafe right now: the
        Sensor Failsafe setting, except that they are shut while the failsafe
        heater is in force in the cold (greenhouse_logic.decide)."""
        decision = self._decision
        if decision is not None and decision.failsafe:
            if decision.vents is True:
                return gl.FAILSAFE_OPEN
            if decision.vents is False:
                return gl.FAILSAFE_CLOSED
            return gl.FAILSAFE_LEAVE
        return self.failsafe_mode()

    def heater_failsafe_mode(self) -> str:
        """Chosen on the Heater Failsafe select; by default follow the
        outside temperature when there is an outside sensor, else off."""
        chosen = self.c.store.state.heater_failsafe
        if chosen in gl.HEATER_FAILSAFE_OPTIONS:
            return chosen
        return gl.HEATER_FAILSAFE_OUTSIDE if self.c.outside_temp_entity else gl.HEATER_FAILSAFE_OFF

    def settings(self) -> gl.Settings:
        n = self.c.number
        state = self.c.store.state
        return gl.Settings(
            heat_temp=n("heat_temp"),
            vent_temp=n("vent_temp"),
            fan_temp=n("fan_temp"),
            hysteresis=n("climate_hysteresis"),
            outside_margin=n("outside_margin"),
            max_humidity=n("max_humidity"),
            mist_temp=n("mist_temp"),
            mist_min_humidity=n("mist_min_humidity"),
            mist_stop_humidity=n("mist_stop_humidity"),
            mist_min_temp=n("mist_min_temp"),
            mist_light_level=n("mist_light_level"),
            mist_trigger=state.mist_trigger if state.mist_trigger in gl.MIST_TRIGGER_OPTIONS else gl.MIST_TRIGGER_ANY,
            mist_at_night=state.mist_at_night,
            max_mist_minutes_per_hour=n("max_mist_minutes_per_hour"),
            ventilation_failsafe=self.failsafe_mode(),
            heater_failsafe=self.heater_failsafe_mode(),
        )

    def _number_from(self, entity_id: str | None, lo: float, hi: float, stale: float | None, *, temperature: bool) -> float | None:
        """A sensor's number, or None when it can't be trusted: missing,
        unavailable, not a number, impossible, or silent for too long."""
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in actuators.OFFLINE:
            return None
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return None
        if temperature:
            unit = state.attributes.get("unit_of_measurement")
            if unit == "°F":
                value = (value - 32) * 5 / 9
            elif unit == "K":
                value -= 273.15
        if not lo <= value <= hi:
            return None
        if stale is not None:
            seen = getattr(state, "last_reported", None) or state.last_updated
            if (dt_util.utcnow() - seen).total_seconds() > stale:
                return None
        return value

    def mist_minutes_last_hour(self, now: float) -> float:
        state = self.c.store.state
        seconds = sum(sec for end, sec in state.mist_pulses if end > now - 3600)
        if self._mist_started is not None:
            seconds += now - self._mist_started
        return seconds / 60.0

    def _read(self, now: float) -> gl.Readings:
        c = self.c
        # Silent this long = offline ("Sensor Offline After", hours).
        stale = c.number("sensor_offline_hours") * 3600
        primary = self._number_from(c.inside_temp_entity, *GREENHOUSE_INSIDE_TEMP_RANGE, stale, temperature=True)
        backups = [
            self._number_from(e, *GREENHOUSE_INSIDE_TEMP_RANGE, stale, temperature=True)
            for e in c.backup_temp_entities
        ]
        backup = next((value for value in backups if value is not None), None)
        self._primary_temp, self._backup_temp = primary, backup
        # The main sensor while it works; else the first backup that does.
        inside = primary if primary is not None else backup
        self._inside_source = "primary" if primary is not None else ("backup" if backup is not None else None)
        outside = self._number_from(c.outside_temp_entity, *GREENHOUSE_OUTSIDE_TEMP_RANGE, stale, temperature=True)
        humidity = self._number_from(c.inside_humidity_entity, 0.0, 100.0, stale, temperature=False)
        light = self._number_from(c.light_entity, 0.0, 1e9, stale, temperature=False)
        sun = self.hass.states.get("sun.sun")
        guard = c.frost_guard_c()
        return gl.Readings(
            inside_temp=inside,
            inside_humidity=humidity,
            outside_temp=outside,
            light=light,
            is_day=sun is None or sun.state != "below_horizon",
            frost=guard is not None and inside is not None and inside <= guard,
            mist_minutes_last_hour=self.mist_minutes_last_hour(now),
        )

    def _hardware(self) -> gl.Hardware:
        c = self.c
        return gl.Hardware(
            humidity_sensor=bool(c.inside_humidity_entity),
            outside_sensor=bool(c.outside_temp_entity),
            light_sensor=bool(c.light_entity),
        )

    # ------------------------------------------------------------------
    # The evaluation
    # ------------------------------------------------------------------
    async def async_evaluate(self, reason: str = "") -> None:
        if self._stopping or not self.active or not self._started:
            return
        async with self._lock:
            if self._stopping:
                return
            try:
                await self._evaluate()
            except Exception:  # noqa: BLE001 - one bad evaluation must never stop the next
                _LOGGER.exception("ZoneFlow greenhouse evaluation failed (%s)", reason)

    async def _evaluate(self) -> None:
        c = self.c
        state = c.store.state
        now = time.time()
        self._new_day_if_needed()
        readings = self._read(now)
        self._readings = readings

        in_grace = False
        if readings.inside_temp is None:
            if self._inside_bad_since is None:
                self._inside_bad_since = now
            in_grace = now - self._inside_bad_since < GREENHOUSE_SENSOR_GRACE_SECONDS
        else:
            self._inside_bad_since = None
        if c.outside_temp_entity and readings.outside_temp is None:
            if self._outside_bad_since is None:
                self._outside_bad_since = now
        else:
            self._outside_bad_since = None

        if self._inside_bad_since is not None:
            readings = replace(readings, failsafe_seconds=now - self._inside_bad_since)
            self._readings = readings
        await self._backup_checks(now)
        if self._release_hot_heater(readings, now):
            await self._log("Manual Hold Ended: too hot", "WARNING")
            await c.store.async_save()

        decision = gl.decide(
            self.settings(), self._hardware(), readings, self._latches, enabled=state.greenhouse_enabled
        )
        if decision.failsafe and in_grace:
            # A short dropout: misters off now (the safe side); heater, vents
            # and fans left as they are; control state kept.
            decision = replace(decision, heater=None, vents=None, fans=None, failsafe=False, latches=self._latches)
        self._latches = decision.latches
        self._decision = decision

        await self._failsafe_notices(decision, now)
        await self._issues(now)
        if decision.control_off:
            # Paused: nothing watches the temperature, so a heater ZoneFlow
            # switched on doesn't stay on (one a person switched is theirs).
            await self._heater_off_if_ours()

        # Cooling off before heating on, so they never fight.
        force = decision.failsafe or decision.control_off
        await self._apply_role("fans", decision.fans, now, force=force)
        await self._apply_role("vents", decision.vents, now, force=force)
        # Inside sensor lost: the heater goes off even if a person switched it.
        await self._apply_role(
            "heater", decision.heater, now, force=force, override_hold=decision.failsafe and decision.heater is False
        )
        await self._apply_mist(decision, now)

        if decision.mist_block != self._last_block:
            self._last_block = decision.mist_block
        self._publish_status()

    def _new_day_if_needed(self) -> None:
        state = self.c.store.state
        today = dt_util.now().date().isoformat()
        if state.mist_today_date_iso != today:
            state.mist_today_date_iso = today
            state.mist_today_seconds = 0.0

    # ------------------------------------------------------------------
    # Devices
    # ------------------------------------------------------------------
    async def _apply_role(
        self, role: str, desired: bool | None, now: float, *, force: bool = False, override_hold: bool = False
    ) -> None:
        entities = self._role_entities(role)
        if role == "misters" or not entities or desired is None:
            return
        if self._held(role, now) > 0 and not override_hold:
            return
        known = [(e, actuators.entity_is_on(self.hass, e)) for e in entities]
        known = [(e, on) for e, on in known if on is not None]
        if not known:
            return
        mismatch = [e for e, on in known if on != desired]
        if not mismatch:
            self._unresponsive.discard(role)
            self._set_device_issue()
            if role == "vents" and desired:
                await self._adjust_vent_positions(known, now)
            return
        role_on = any(on for _e, on in known)
        if desired != role_on:
            min_on, min_off = GREENHOUSE_MIN_TIMES[role]
            changed = self.c.store.state.gh_changed_ts.get(role)
            if gl.min_time_gate(desired, role_on, changed, now, min_on, min_off, force=force) is None:
                return
            self.c.store.state.gh_changed_ts[role] = now
        await self._command(role, mismatch, desired, now)
        await self._log(f"{ROLE_LABEL[role]} {'On' if desired else 'Off'}", "OK")

    async def _adjust_vent_positions(self, known: list[tuple[str, bool]], now: float) -> None:
        """Vents already open but not at Vent Open Position (the slider was
        changed): move the ones that can be set to a position. Each target
        is sent once per 10 minutes, so a vent that stops short of it is not
        pestered every evaluation."""
        target = self.c.number("vent_open_pct")
        for entity, on in known:
            if not on or entity.split(".", 1)[0] != "cover":
                continue
            state = self.hass.states.get(entity)
            if state is None or state.state != "open":  # not while it is moving
                continue
            if not int(state.attributes.get("supported_features", 0)) & actuators.COVER_SET_POSITION:
                continue
            position = state.attributes.get("current_position")
            if not isinstance(position, (int, float)) or abs(position - target) <= 5:
                continue
            sent = self._position_sent.get(entity)
            if sent is not None and sent[0] == target and now - sent[1] < 600:
                continue
            self._position_sent[entity] = (target, now)
            await self._command("vents", [entity], True, now)

    async def _command(self, role: str, entities: list[str], on: bool, now: float) -> None:
        context = Context()
        position = self.c.number("vent_open_pct") if role == "vents" else None
        for entity in entities:
            # Recorded before the call: the device's state event arrives while
            # the call is still running and must be seen as ZoneFlow's own.
            self._commanded[entity] = (on, now)
            try:
                await actuators.async_set(self.hass, entity, on, position=position, context=context)
            except Exception as err:  # noqa: BLE001 - a device that fails must not stop the others
                _LOGGER.warning("ZoneFlow: could not switch %s: %s", entity, err)
        await self.c.store.async_save()
        self._timer(GREENHOUSE_CONFIRM_SECONDS, lambda _now: self.hass.async_create_task(self._confirm(role, on, 0)))

    def _timer(self, seconds: float, action) -> None:
        holder: dict[str, Callable[[], None]] = {}

        @callback
        def _fire(now) -> None:
            self._timers.discard(holder["cancel"])
            action(now)

        holder["cancel"] = async_call_later(self.hass, seconds, _fire)
        self._timers.add(holder["cancel"])

    async def _confirm(self, role: str, on: bool, attempt: int) -> None:
        """A device told to move must report it. One retry, then a Repairs
        issue and a phone message."""
        async with self._lock:  # not in the middle of an evaluation
            if self._stopping or self._held(role, time.time()) > 0:
                return
            decision = self._decision
            wanted = getattr(decision, role, None) if decision is not None else None
            if wanted is not on:
                return  # the situation changed since the command: the evaluation decides now
            entities = self._role_entities(role)
            wrong = [e for e in entities if actuators.entity_is_on(self.hass, e) is not on and e in self._commanded]
            wrong = [e for e in wrong if self._commanded[e][0] == on]
            if not wrong:
                self._unresponsive.discard(role)
                self._set_device_issue()
                return
            if attempt == 0:
                await self._command(role, wrong, on, time.time())
                self._timer(
                    GREENHOUSE_CONFIRM_SECONDS, lambda _now: self.hass.async_create_task(self._confirm(role, on, 1))
                )
                return
            if role not in self._unresponsive:
                self._unresponsive.add(role)
                self._set_device_issue()
                await self._notice("greenhouse_device", LEVEL_WARNING, device=ROLE_LABEL[role], entity=", ".join(wrong))

    def _set_device_issue(self) -> None:
        names = ", ".join(ROLE_LABEL[r] for r in sorted(self._unresponsive))
        issues._set(
            self.hass, self.c, ISSUE_DEVICE, bool(self._unresponsive),
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_DEVICE,
            translation_placeholders={"zone": self.c.entry.title, "devices": names},
        )

    # ------------------------------------------------------------------
    # Misting
    # ------------------------------------------------------------------
    async def _apply_mist(self, decision: gl.Decision, now: float) -> None:
        state = self.c.store.state
        want = decision.mist and not state.mist_halted and self._held("misters", now) <= 0
        if not want:
            self._mist_stop.set()
            if self._mist_task is not None and not self._mist_task.done():
                return  # the loop switches the mister off and ends
            # Not misting: no mister stays on -- one left on by a restart, a
            # stopped loop or an ended manual hold. Only a running manual
            # hold is respected, and not on failsafe.
            await self._misters_off("failsafe" if decision.failsafe else "idle", ignore_hold=decision.failsafe)
            return
        if self._mist_task is None or self._mist_task.done():
            if not any(actuators.entity_is_on(self.hass, e) is not None for e in self._role_entities("misters")):
                return  # every mister offline: nothing to start (and nothing to log each time)
            self._mist_stop.clear()
            self._mist_task = self.c.entry.async_create_background_task(
                self.hass, self._mist_loop(), name=f"zoneflow_mist_{self.c.entry.entry_id}"
            )
            await self._log("Misting Started", "OK")

    async def _wait_stop(self, seconds: float) -> bool:
        """Sleep, but wake at once if misting must stop. True = stopped."""
        try:
            await asyncio.wait_for(self._mist_stop.wait(), timeout=seconds)
            return True
        except asyncio.TimeoutError:
            return False

    async def _mist_loop(self) -> None:
        try:
            while not self._mist_stop.is_set() and not self._stopping:
                decision = self._decision
                if decision is None or not decision.mist:
                    break
                on_seconds = self.c.number("mist_on_seconds")
                off_seconds = self.c.number("mist_off_seconds")
                if not await self._mist_pulse(on_seconds):
                    break
                if await self._wait_stop(off_seconds):
                    break
        finally:
            self._mist_started = None
            confirmed = await self._misters_off_confirmed()
            self._cancel_mist_watchdog()
            if not confirmed:
                await self._halt_misting()
            self._publish_status()

    async def _mist_pulse(self, seconds: float) -> bool:
        """One pulse: on, wait, off. False = nothing started."""
        misters = self._role_entities("misters")
        usable = [e for e in misters if actuators.entity_is_on(self.hass, e) is not None]
        if not usable:
            return False
        start = time.time()
        context = Context()
        for entity in usable:
            self._commanded[entity] = (True, start)  # before the call, see _command
            try:
                await actuators.async_set(self.hass, entity, True, context=context)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("ZoneFlow: could not start mister %s: %s", entity, err)
        self._mist_started = start
        self._arm_mist_watchdog(seconds)
        await self._wait_stop(seconds)
        elapsed = time.time() - start
        self._mist_started = None
        confirmed = await self._misters_off_confirmed()
        self._cancel_mist_watchdog()
        state = self.c.store.state
        end = time.time()
        state.mist_pulses = [p for p in state.mist_pulses if p[0] > end - 3600] + [[end, elapsed]]
        self._new_day_if_needed()
        state.mist_today_seconds += elapsed
        await self.c.store.async_save()
        if not confirmed:
            await self._halt_misting()
            return False
        return True

    async def _misters_off_confirmed(self, *, ignore_hold: bool = False) -> bool:
        """Switch every mister off and wait for each to say so; one retry.
        A mister a person is holding on (manual hold) is theirs: left alone,
        unless `ignore_hold` (failsafe, unload, shutdown)."""
        if self._held("misters", time.time()) > 0 and not ignore_hold:
            return True
        misters = self._role_entities("misters")
        for _attempt in range(2):
            on = [e for e in misters if actuators.entity_is_on(self.hass, e) is True]
            if not on:
                return True
            context = Context()
            for entity in on:
                self._commanded[entity] = (False, time.time())  # before the call, see _command
                try:
                    await actuators.async_set(self.hass, entity, False, context=context)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning("ZoneFlow: could not stop mister %s: %s", entity, err)
            waited = 0.0
            while waited < VALVE_CLOSE_CONFIRM_SECONDS:
                if not any(actuators.entity_is_on(self.hass, e) is True for e in misters):
                    return True
                await asyncio.sleep(0.5)
                waited += 0.5
        return not any(actuators.entity_is_on(self.hass, e) is True for e in misters)

    async def _misters_off(self, why: str, *, ignore_hold: bool = False) -> None:
        """Outside the pulse loop: a mister that is on while ZoneFlow isn't
        pulsing (a restart, a stopped loop, an ended hold) is switched off --
        unless a person is holding it on (and `ignore_hold` is False)."""
        if self._held("misters", time.time()) > 0 and not ignore_hold:
            return
        if self._mist_task is not None and not self._mist_task.done():
            return
        if any(actuators.entity_is_on(self.hass, e) is True for e in self._role_entities("misters")):
            confirmed = await self._misters_off_confirmed(ignore_hold=ignore_hold)
            if not confirmed:
                await self._halt_misting()

    async def _stop_misting(self, wait: float) -> None:
        self._mist_stop.set()
        task = self._mist_task
        if task is not None and not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=wait)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()
        if self._role_entities("misters"):
            # Nobody watches a mister after this: off, whatever the hold.
            await self._misters_off_confirmed(ignore_hold=True)

    async def _heater_off_if_ours(self) -> None:
        """Unload / shutdown: a heater ZoneFlow switched on is switched off,
        so it never runs with nothing watching the temperature. One a person
        switched on themselves is left alone."""
        ours = [
            e for e in self._role_entities("heater")
            if self._commanded.get(e, (False, 0.0))[0] and actuators.entity_is_on(self.hass, e) is True
        ]
        if ours:
            self.c.store.state.gh_changed_ts["heater"] = time.time()
            if not self._stopping:
                await self._log("Heater Off", "OK")
        for entity in ours:
            self._commanded[entity] = (False, time.time())  # ours, not a person's (see _command)
            try:
                await actuators.async_set(self.hass, entity, False, context=Context())
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("ZoneFlow: could not switch heater %s off: %s", entity, err)

    def _arm_mist_watchdog(self, pulse_seconds: float) -> None:
        self._cancel_mist_watchdog()
        self._mist_stuck_cancel = async_call_later(
            self.hass, pulse_seconds + GREENHOUSE_MIST_STUCK_MARGIN_SECONDS, self._on_mist_stuck
        )

    def _cancel_mist_watchdog(self) -> None:
        if self._mist_stuck_cancel is not None:
            self._mist_stuck_cancel()
            self._mist_stuck_cancel = None

    @callback
    def _on_mist_stuck(self, now) -> None:
        self._mist_stuck_cancel = None
        self.hass.async_create_task(self._fire_mist_stuck())

    async def _fire_mist_stuck(self) -> None:
        """A mister has been on well past its pulse: force it off."""
        self._mist_stop.set()
        confirmed = await self._misters_off_confirmed()
        if not confirmed:
            await self._halt_misting()
        else:
            await self._notice("greenhouse_mist_stuck", LEVEL_WARNING)

    async def _halt_misting(self) -> None:
        state = self.c.store.state
        if state.mist_halted:
            return
        state.mist_halted = True
        await self.c.store.async_save()
        issues._set(
            self.hass, self.c, ISSUE_MIST_HALTED, True,
            severity=ir.IssueSeverity.ERROR,
            translation_key=ISSUE_MIST_HALTED,
            translation_placeholders={"zone": self.c.entry.title},
        )
        await self._notice("greenhouse_mist_halted", LEVEL_WARNING, always=True)
        self._publish_status()

    async def async_reset_mist_halt(self) -> None:
        state = self.c.store.state
        if not state.mist_halted:
            return
        state.mist_halted = False
        await self.c.store.async_save()
        issues._set(self.hass, self.c, ISSUE_MIST_HALTED, False)
        await self._log("Misting Halt Reset", "OK")
        await self.async_evaluate("reset")

    # ------------------------------------------------------------------
    # Failsafe, issues, messages
    # ------------------------------------------------------------------
    async def _failsafe_notices(self, decision: gl.Decision, now: float) -> None:
        if decision.failsafe and not self._failsafe_active:
            self._failsafe_active = True
            mode = self.failsafe_vent_mode()
            await self._log("Greenhouse Failsafe", "WARNING")
            await self._notice(
                "greenhouse_failsafe", LEVEL_WARNING,
                mode=messages.text(self.hass, f"greenhouse.failsafe_mode.{mode}"),
                heater=messages.text(self.hass, f"greenhouse.heater_mode.{self.heater_failsafe_mode()}"),
            )
        elif not decision.failsafe and self._failsafe_active and self._inside_bad_since is None:
            self._failsafe_active = False
            await self._log("Greenhouse Failsafe Ended", "OK")
            await self._notice("greenhouse_recovered", LEVEL_INFO)

    async def _issues(self, now: float) -> None:
        zone = self.c.entry.title
        inside_bad = self._inside_bad_since is not None and now - self._inside_bad_since >= GREENHOUSE_ISSUE_SENSOR_SECONDS
        issues._set(
            self.hass, self.c, ISSUE_SENSOR, inside_bad,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_SENSOR,
            translation_placeholders={"zone": zone, "entity": self.c.inside_temp_entity or ""},
        )
        outside_bad = (
            self._outside_bad_since is not None and now - self._outside_bad_since >= GREENHOUSE_ISSUE_OUTSIDE_SECONDS
        )
        issues._set(
            self.hass, self.c, ISSUE_OUTSIDE, outside_bad,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_OUTSIDE,
            translation_placeholders={"zone": zone, "entity": self.c.outside_temp_entity or ""},
        )

    async def _backup_checks(self, now: float) -> None:
        """Running on a backup sensor: say so once, and raise a Repairs issue
        if it lasts. Main and backup far apart for long: one is wrong."""
        c = self.c
        if not c.backup_temp_entities:
            return
        zone = c.entry.title
        if self._inside_source == "backup":
            if self._on_backup_since is None:
                self._on_backup_since = now
                await self._log("Backup Temperature Sensor In Use", "WARNING")
                await self._notice("greenhouse_backup_sensor", LEVEL_WARNING, entity=c.inside_temp_entity or "")
        elif self._on_backup_since is not None:
            # Back on the main sensor, or no sensor at all (failsafe has
            # taken over): either way no longer "running on a backup".
            self._on_backup_since = None
            if self._inside_source == "primary":
                await self._log("Main Temperature Sensor Back", "OK")
        issues._set(
            self.hass, c, ISSUE_ON_BACKUP,
            self._on_backup_since is not None and now - self._on_backup_since >= GREENHOUSE_ISSUE_SENSOR_SECONDS,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_ON_BACKUP,
            translation_placeholders={"zone": zone, "entity": c.inside_temp_entity or ""},
        )
        apart = (
            self._primary_temp is not None
            and self._backup_temp is not None
            and abs(self._primary_temp - self._backup_temp) > GREENHOUSE_SENSOR_MISMATCH_C
        )
        if not apart:
            self._mismatch_since = None
        elif self._mismatch_since is None:
            self._mismatch_since = now
        mismatch = self._mismatch_since is not None and now - self._mismatch_since >= GREENHOUSE_SENSOR_MISMATCH_SECONDS
        issues._set(
            self.hass, c, ISSUE_MISMATCH, mismatch,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_MISMATCH,
            translation_placeholders={
                "zone": zone,
                "entity": c.inside_temp_entity or "",
                "main": self._t(self._primary_temp),
                "backup": self._t(self._backup_temp),
            },
        )

    async def _log(self, event_type: str, status: str) -> None:
        await self.c._log_event(event_type=f"Greenhouse: {event_type}", status=status, target_mm=0.0, deducted_mm=0.0, runtime=0)

    async def _notice(self, key: str, level: str, *, always: bool = False, **params: Any) -> None:
        await self.c._log_event(
            event_type=f"Greenhouse: {key}",
            status="NOTICE",
            target_mm=0.0,
            deducted_mm=0.0,
            runtime=0,
            notify_phone=True,
            message=key,
            params={"zone": self.c.entry.title, **params},
            level=level,
            always_notify=always,
        )

    # ------------------------------------------------------------------
    # Status (the Greenhouse status sensor)
    # ------------------------------------------------------------------
    def _t(self, celsius: float | None) -> str:
        return units.temp_text(celsius, self.c.imperial) if celsius is not None else "?"

    def status(self) -> dict[str, Any]:
        decision, r = self._decision, self._readings
        state = self.c.store.state
        now = time.time()
        attrs: dict[str, Any] = {
            "inside_temp": r.inside_temp if r else None,
            "inside_humidity": r.inside_humidity if r else None,
            "outside_temp": r.outside_temp if r else None,
            "gate": decision.gate if decision else None,
            "mist_block": decision.mist_block if decision else None,
            "failsafe": bool(decision and decision.failsafe),
            "inside_source": self._inside_source,
            "heating": bool(decision and decision.heater),
            "ventilating": bool(decision and decision.vents),
            "fans": bool(decision and decision.fans),
            "misting": bool(self._mist_task is not None and not self._mist_task.done() and decision and decision.mist),
            "mist_halted": state.mist_halted,
        }
        params: dict[str, Any] = {
            "temp": self._t(r.inside_temp if r else None),
            "outside": self._t(r.outside_temp if r else None),
            "humidity": f"{r.inside_humidity:.0f}%" if r and r.inside_humidity is not None else "?",
        }
        held = next((role for role in ROLE_ENTITIES if self._held(role, now) > 0), None)
        if decision is None:
            code = "starting"
        elif decision.control_off:
            code = "control_off"
        elif decision.failsafe:
            code = "failsafe"
            params["mode"] = messages.text(self.hass, f"greenhouse.failsafe_mode.{self.failsafe_vent_mode()}")
            params["heater"] = messages.text(self.hass, f"greenhouse.heater_mode.{self.heater_failsafe_mode()}")
        elif state.mist_halted:
            code = "mist_halted"
        elif held is not None:
            params["device"] = ROLE_LABEL[held]
            until = state.gh_hold_until.get(held, now)
            if until - now >= NO_AUTO_RESUME_SECONDS / 2:
                code = "held_until_resume"
            else:
                code = "held_until"
                params["time"] = messages.when(
                    self.hass, dt_util.as_local(dt_util.utc_from_timestamp(until)), "weekday_time"
                )
        elif decision.heater:
            code = "heating"
        elif decision.vents or decision.fans:
            code = "ventilating_" + ("humidity" if decision.ventilating_for == ("humidity",) else "temperature")
        elif attrs["misting"]:
            code = "misting"
        elif decision.gate == gl.GATE_BLOCKED and (self._latches.vent or self._latches.fan or self._latches.humid):
            code = "gate_blocked"
        else:
            code = "idle"
        attrs["code"] = code
        text = messages.text(self.hass, f"greenhouse.status.{code}", **params)
        return {"text": text, **attrs}

    @callback
    def _publish_status(self) -> None:
        """Tell the status entities (the attributes carry live readings, so
        every evaluation writes)."""
        self.c._notify_status()

    def ventilation_allowed(self) -> bool:
        return self._decision is None or self._decision.gate != gl.GATE_BLOCKED
