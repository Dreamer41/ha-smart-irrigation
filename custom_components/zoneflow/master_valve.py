"""Master (backup) shut-off valve (1.8): one valve upstream of several zones, e.g. on the pipe after a
shared pump. It opens when a watering on one of its zones starts and closes when the last one ends, so a
zone valve that sticks open has no water behind it once the run is over.

It also closes, and stays closed until Reset Lock is pressed on one of its zones, when:
- a zone valve doesn't confirm it closed at the end of a run, or the stuck-valve watchdog fires;
- water still flows (the zone's flow meter keeps counting) or the pump still draws power while every
  zone valve behind it is closed, e.g. in the soak between pulses.

Shared by every zone that names the same entity (hass.data[MASTER_VALVES_KEY]). The latch is kept in
each of its zones' saved state, so it survives a restart.

Normally closed (the default and the recommendation: a power cut shuts it) or normally open. A
normally-open valve on a relay (switch) is closed by switching the relay ON, so the commands and the
reading are turned round; a `valve` entity already reports open and closed and is never turned round.

Monthly self-test (zones with a flow meter or a pump power sensor): at the end of a routine watering
that is the last run on the master, ZoneFlow closes the master, opens the zone valve for half a minute
and checks that no water flows and the pump stops. The zone valve is closed again whatever happens.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from . import flow_meter, zone_valve
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

MASTER_VALVES_KEY = "zoneflow_master_valves"
# After the last zone valve closes: a valve takes a moment to shut and a meter reports late.
SETTLE_SECONDS = 60.0
CHECK_SECONDS = 30.0
# More than this counted while every zone valve is closed is water going somewhere.
LEAK_LITRES = 2.0
# A meter reporting a rate: above this many L/min is flowing.
LEAK_RATE = 0.5
# Some rate meters hold their last rate for minutes after the water stops (a pulse meter's timeout): a rate
# only counts as a leak when it has held for longer than that.
RATE_LEAK_SUSTAIN_SECONDS = 400.0
OPEN_CONFIRM_SECONDS = 30.0
# The self-test: how often, how long the pipe after the master may drain (and a pump take to build
# pressure and stop), how long no water may then be counted, and how much counts as water.
TEST_INTERVAL_DAYS = 30
TEST_SETTLE_SECONDS = 10.0
TEST_MEASURE_SECONDS = 20.0
TEST_LEAK_LITRES = 0.5

REASON_VALVE_NOT_CLOSED = "valve_not_closed"
REASON_VALVE_STUCK = "valve_stuck"
REASON_FLOW = "flow"
REASON_PUMP_POWER = "pump_power"
REASON_HIGH_FLOW = "high_flow"


class MasterValveClosed(Exception):
    """The master valve is latched closed: nothing can water behind it until Reset Lock."""


def get(hass: HomeAssistant, entity_id: str) -> MasterValve:
    valves: dict[str, MasterValve] = hass.data.setdefault(MASTER_VALVES_KEY, {})
    if entity_id not in valves:
        valves[entity_id] = MasterValve(hass, entity_id)
    return valves[entity_id]


class MasterValve:
    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self.hass = hass
        self.entity_id = entity_id
        self.holders: set[str] = set()  # entry ids of the zones whose run has it open
        self.open_valves: set[str] = set()  # entry ids of the zones whose own valve is open now
        self._idle_baseline: dict[str, float | None] | None = None
        self._unsub_check: Callable[[], None] | None = None

    # -- the zones -----------------------------------------------------------
    def zones(self) -> list[Any]:
        return [
            c for c in self.hass.data.get(DOMAIN, {}).values()
            if getattr(c, "master_valve_entity", None) == self.entity_id
        ]

    def _zone(self, entry_id: str) -> Any | None:
        return self.hass.data.get(DOMAIN, {}).get(entry_id)

    @property
    def normally_open(self) -> bool:
        """A relay-driven valve that is open without power (only a switch can be turned round)."""
        if zone_valve.domain_of(self.entity_id) == "valve":
            return False
        return any(zone.master_valve_normally_open for zone in self.zones())

    def is_open(self, state) -> bool:
        if state is None or zone_valve.is_offline(state):
            return False
        if self.normally_open and state.state in ("on", "off"):
            return state.state == "off"
        return zone_valve.is_open(state)

    def is_closed(self, state) -> bool:
        if state is None or zone_valve.is_offline(state):
            return False
        if self.normally_open and state.state in ("on", "off"):
            return state.state == "on"
        return zone_valve.is_closed(state)

    async def _send_open(self) -> None:
        if self.normally_open:
            await zone_valve.async_close(self.hass, self.entity_id)  # relay off: the valve opens
        else:
            await zone_valve.async_open(self.hass, self.entity_id)

    async def _send_close(self) -> None:
        if self.normally_open:
            await zone_valve.async_open(self.hass, self.entity_id)  # relay on: the valve closes
        else:
            await zone_valve.async_close(self.hass, self.entity_id)

    @property
    def last_test(self) -> tuple[float | None, bool | None]:
        """(when, passed) of the latest self-test on any of its zones."""
        best: tuple[float | None, bool | None] = (None, None)
        for zone in self.zones():
            ts = zone.store.state.master_test_ts
            if ts is not None and (best[0] is None or ts > best[0]):
                best = (ts, zone.store.state.master_test_ok)
        return best

    async def async_clear_test(self) -> None:
        """Forget the last self-test on every zone of this master: it is tested again at the next
        routine watering (the person says the valve was fixed or checked)."""
        for zone in self.zones():
            zone.store.state.master_test_ts = None
            zone.store.state.master_test_ok = None
            await zone.store.async_save()

    def test_due(self, now_ts: float) -> bool:
        ts, _passed = self.last_test
        return ts is None or now_ts - ts >= TEST_INTERVAL_DAYS * 86400

    async def async_record_test(self, passed: bool, ts: float) -> None:
        for zone in self.zones():
            zone.store.state.master_test_ts = ts
            zone.store.state.master_test_ok = passed
            await zone.store.async_save()

    @property
    def latched(self) -> str | None:
        """Why it was closed for safety, or None."""
        for zone in self.zones():
            reason = zone.store.state.master_valve_latch
            if reason:
                return reason
        return None

    # -- a run -----------------------------------------------------------------
    async def async_acquire(self, controller: Any) -> None:
        """A run starts on `controller`: open the master (if it is not open already)."""
        if self.latched:
            raise MasterValveClosed(self.latched)
        first = not self.holders
        self.holders.add(controller.entry.entry_id)
        try:
            state = self.hass.states.get(self.entity_id)
            if first or not self.is_open(state):
                try:
                    await self._send_open()
                except Exception:  # noqa: BLE001 - a device may raise anything; the run still releases the master
                    _LOGGER.exception("ZoneFlow: could not open master valve %s", self.entity_id)
                if not await self._confirmed(open_=True, seconds=OPEN_CONFIRM_SECONDS):
                    _LOGGER.warning("ZoneFlow: master valve %s did not report open", self.entity_id)
        except BaseException:
            # Cancelled while waiting (the release only starts once this returns): the zone holds nothing.
            self.holders.discard(controller.entry.entry_id)
            raise

    async def async_release(self, controller: Any, *, valve_closed: bool) -> None:
        """A run ended on `controller`. Its valve not confirmed closed: close the master for safety.
        Otherwise the master closes once no other run holds it."""
        self.holders.discard(controller.entry.entry_id)
        if not valve_closed:
            await self.async_emergency_close(controller, REASON_VALVE_NOT_CLOSED, stop_caller=False)
            return
        self.open_valves.discard(controller.entry.entry_id)
        if not self.holders:
            self._stop_check()
            await self._close()

    @callback
    def forget(self, controller: Any) -> None:
        """The zone unloads (a reload, removal or shutdown)."""
        self.holders.discard(controller.entry.entry_id)
        self.open_valves.discard(controller.entry.entry_id)
        if not self.holders:
            self._stop_check()

    @callback
    def valve_changed(self, controller: Any, is_open: bool) -> None:
        """A zone valve behind this master opened or closed."""
        entry_id = controller.entry.entry_id
        if is_open:
            self.open_valves.add(entry_id)
            self._stop_check()
        else:
            self.open_valves.discard(entry_id)
            if self.holders and not self.open_valves:
                self._start_check()

    # -- safety --------------------------------------------------------------
    async def async_emergency_close(self, controller: Any, reason: str, *, stop_caller: bool = True) -> None:
        """Close the master and keep it closed until Reset Lock; stop every run behind it and alert.
        `stop_caller` False: `controller`'s run is already ending (or its watchdog stops it)."""
        self._stop_check()
        already = self.latched
        for zone in self.zones():
            zone.store.state.master_valve_latch = reason
        await self._close()
        holders = [z for z in (self._zone(e) for e in list(self.holders)) if z is not None]
        self.holders.clear()
        for zone in holders:
            if stop_caller or zone is not controller:
                await zone.master_valve_stopped_run()
        for zone in self.zones():
            await zone.store.async_save()
        if not already:
            await controller.log_master_valve_closed(reason, self.entity_id)

    async def async_reset(self) -> None:
        """Reset Lock: the latch is cleared (the valve opens again with the next run)."""
        for zone in self.zones():
            if zone.store.state.master_valve_latch:
                zone.store.state.master_valve_latch = None
                await zone.store.async_save()

    async def async_close_if_idle(self) -> None:
        """At startup: nothing holds it, so it must not be open (a run cut off by a restart)."""
        if self.holders:
            return
        state = self.hass.states.get(self.entity_id)
        if state is not None and not self.is_closed(state) and not zone_valve.is_offline(state):
            await self._close()

    # -- the check while every zone valve is closed ------------------------------
    def _start_check(self) -> None:
        self._stop_check()
        self._schedule_check(SETTLE_SECONDS)

    def _schedule_check(self, seconds: float) -> None:
        if self._unsub_check is not None:
            self._unsub_check()  # one pending check at a time
        self._unsub_check = async_call_later(self.hass, seconds, self._on_check)

    def _stop_check(self) -> None:
        if self._unsub_check is not None:
            self._unsub_check()
            self._unsub_check = None
        self._idle_baseline = None

    @callback
    def _on_check(self, _now) -> None:
        self._unsub_check = None
        if not self.holders or self.open_valves:
            return
        self.hass.async_create_task(self._async_check())

    async def _async_check(self) -> None:
        if not self.holders or self.open_valves:
            return
        zones = [z for z in (self._zone(e) for e in list(self.holders)) if z is not None]
        first = self._idle_baseline is None
        if first:
            self._idle_baseline = {}
        for zone in zones:
            reason = flow_while_closed(zone, self._idle_baseline, first)
            if reason is not None:
                await self.async_emergency_close(zone, reason)  # its run is in a soak: stop it too
                return
        if self.holders and not self.open_valves:
            self._schedule_check(CHECK_SECONDS)

    # -- the valve itself ----------------------------------------------------------
    async def async_close_for_test(self) -> bool:
        """The self-test: close it now and wait for it to report closed."""
        await self._close()
        return await self._confirmed(open_=False, seconds=OPEN_CONFIRM_SECONDS)

    async def _close(self) -> None:
        try:
            await self._send_close()
        except Exception:  # noqa: BLE001 - a device may raise anything; the alert still goes out
            _LOGGER.exception("ZoneFlow: could not close master valve %s", self.entity_id)

    async def _confirmed(self, *, open_: bool, seconds: float) -> bool:
        waited = 0.0
        while True:
            state = self.hass.states.get(self.entity_id)
            if self.is_open(state) if open_ else self.is_closed(state):
                return True
            if waited >= seconds:
                return False
            await asyncio.sleep(0.5)
            waited += 0.5


def test_reading(zone: Any) -> float | None:
    """The zone's flow meter in litres (a total meter) at the start of the self-test, or None."""
    reading = _meter(zone)
    if reading is None or reading[1]:
        return None
    return reading[0]


def test_passed(zone: Any, start_litres: float | None) -> bool | None:
    """The self-test's verdict with the master closed and the zone valve open: no water counted since
    `start_litres` and the pump stopped. None when nothing can tell (no reading at all)."""
    verdicts: list[bool] = []
    pump = zone.pump_power_entity
    minimum = zone.number("pump_min_watts")
    if pump and minimum > 0:
        state = zone.hass.states.get(pump)
        try:
            verdicts.append(float(state.state) < minimum)
        except (TypeError, ValueError, AttributeError):
            pass
    reading = _meter(zone)
    if reading is not None:
        value, is_rate = reading
        # A rate meter may still show the rate from before the valves closed (see RATE_LEAK_SUSTAIN_SECONDS),
        # so only a total, or the pump, can tell in half a minute.
        if is_rate:
            pass
        elif start_litres is not None:
            verdicts.append(value - start_litres <= TEST_LEAK_LITRES)
    return all(verdicts) if verdicts else None


def _meter(zone: Any) -> tuple[float, bool] | None:
    """(the flow meter's value in litres or its rate, whether it is a rate meter), or None."""
    reading = zone.flow_meter_now()
    if reading is None:
        return None
    kind, value = reading
    return value, kind == flow_meter.METER_RATE


def flow_while_closed(zone: Any, baseline: dict[str, float | None], first: bool) -> str | None:
    """Whether water runs on `zone` while its valve is closed: its pump draws power, or its flow meter
    counted more than LEAK_LITRES since the first check (or a rate meter shows a rate). `baseline`
    keeps each meter's first reading. None when nothing runs (or nothing can tell)."""
    pump = zone.pump_power_entity
    if pump:
        state = zone.hass.states.get(pump)
        try:
            watts = float(state.state) if state else 0.0
        except (TypeError, ValueError):
            watts = 0.0
        if watts >= zone.number("pump_min_watts") > 0:
            return REASON_PUMP_POWER
    reading = _meter(zone)
    if reading is None:
        return None
    litres, is_rate = reading
    key = zone.entry.entry_id
    if is_rate:  # L/min
        now = dt_util.utcnow().timestamp()
        if litres <= LEAK_RATE:
            baseline.pop(f"{key}:rate_since", None)
            return None
        since = baseline.setdefault(f"{key}:rate_since", now)
        return REASON_FLOW if now - since >= RATE_LEAK_SUSTAIN_SECONDS else None
    if first or baseline.get(key) is None:
        baseline[key] = baseline[f"{key}:prev"] = litres
        baseline[f"{key}:rises"] = 0
        return None
    # A meter that reports every minute or two delivers the last of the water late: more than
    # LEAK_LITRES counts only once it has gone up on two checks in a row.
    rises = baseline[f"{key}:rises"] + 1 if litres > baseline[f"{key}:prev"] else 0
    baseline[f"{key}:prev"], baseline[f"{key}:rises"] = litres, rises
    return REASON_FLOW if litres - baseline[key] > LEAK_LITRES and rises >= 2 else None

