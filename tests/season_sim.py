"""Multi-week season simulator for intent tests.

Drives a real, set-up ZoneFlow zone through N simulated days on a virtual
clock, calling the controller's own daily handlers in the order Home
Assistant would fire them:

    00:00     _on_midnight           (new day, today's min/max/rain reset)
    03:00     temperature low        (outdoor sensor reading)
    05:00     run_deep_soak          (scheduled trigger)
    05:30     run_routine_irrigation (scheduled trigger -- while a deep soak
                                      that started at 05:00 is still going,
                                      exactly as in real life, so it meets
                                      the lock)
    hh:00     rain tips              (whatever the weather script says)
    14:00     temperature high
    23:59:50  _on_daily_shift        (peak/min/rain history registers)

Pulses and soak gaps run through CompressedTime, so a 30-day season takes
well under a second while every valve-open minute is still recorded.
"""
from __future__ import annotations

import types
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import homeassistant.util.dt as dt_util

from custom_components.zoneflow import controller as controller_module

from .scenario_harness import CompressedTime


class VirtualDt:
    """Stand-in for the controller module's `dt_util`: utcnow()/now() return
    the simulated time, everything else is the real dt_util."""

    def __init__(self, start_utc: datetime) -> None:
        self.t = start_utc
        self.module = types.SimpleNamespace(
            **{k: getattr(dt_util, k) for k in dir(dt_util) if not k.startswith("__")}
        )
        self.module.utcnow = lambda: self.t
        self.module.now = lambda time_zone=None: self.t.astimezone(time_zone or dt_util.DEFAULT_TIME_ZONE)

    def install(self, monkeypatch) -> "VirtualDt":
        monkeypatch.setattr(controller_module, "dt_util", self.module)
        return self

    def set_local(self, day_start_local: datetime, hour: float) -> None:
        self.t = dt_util.as_utc(day_start_local + timedelta(hours=hour))


@dataclass
class Day:
    """One day of weather. rain = list of (hour, mm)."""
    t_min: float | str
    t_max: float | str
    rain: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class DayResult:
    index: int
    date: str
    deep_soak_mm: float = 0.0
    routine_mm: float = 0.0
    routine_attempted_during_soak: bool = False
    events: list[str] = field(default_factory=list)
    target_weekly_used: float | None = None
    lock_at_end: bool = False
    valve_at_end: str = "off"


class SeasonSim:
    def __init__(self, hass, controller, monkeypatch, *, valve, temp_entity, rain_entity, temp_unit="°C"):
        self.hass = hass
        self.c = controller
        self.valve = valve
        self.temp_entity = temp_entity
        self.rain_entity = rain_entity
        self.temp_unit = temp_unit
        self.clock = CompressedTime(hass, [valve]).install(monkeypatch)
        tz = dt_util.DEFAULT_TIME_ZONE
        # Start tomorrow at local midnight, so every virtual time is in the
        # real future (no point-in-time callback ever fires "in the past").
        today = dt_util.now().astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        self.start_local = today + timedelta(days=1)
        self.vdt = VirtualDt(dt_util.as_utc(self.start_local)).install(monkeypatch)
        self.tips = 0.0
        self.results: list[DayResult] = []
        self._events: list[str] = []
        hass.bus.async_listen(controller_module.EVENT_LOG, lambda e: self._events.append(e.data["event_type"]))
        self._plans: list = []
        real_plan = controller_module.calc.plan_routine_irrigation

        def spy(**kw):
            plan = real_plan(**kw)
            self._plans.append(plan)
            return plan

        monkeypatch.setattr(controller_module.calc, "plan_routine_irrigation", spy)

    async def _temp(self, value):
        attrs = {"unit_of_measurement": self.temp_unit} if value not in ("unavailable", "unknown") else {}
        self.hass.states.async_set(self.temp_entity, str(value), attrs)
        await self.hass.async_block_till_done()

    async def _rain(self, mm):
        self.tips += mm / self.c.number("rain_mm_per_tip")
        self.hass.states.async_set(self.rain_entity, str(round(self.tips, 3)))
        await self.hass.async_block_till_done()

    def _mm(self) -> float:
        return self.clock.valve_minutes(self.valve) * self.c.number("flow_rate_mm_per_min")

    async def run(self, days: list[Day]) -> list[DayResult]:
        for i, weather in enumerate(days):
            day_start = self.start_local + timedelta(days=len(self.results))
            res = DayResult(i, day_start.date().isoformat())
            self._events.clear()
            self._plans.clear()

            self.vdt.set_local(day_start, 0)
            self.c._on_midnight(None)
            await self.hass.async_block_till_done()

            self.vdt.set_local(day_start, 3)
            await self._temp(weather.t_min)

            # Rain before the 05:00 cycles.
            for hour, mm in sorted(weather.rain):
                if hour < 5:
                    self.vdt.set_local(day_start, hour)
                    await self._rain(mm)

            # 05:00 deep soak; routine fires at 05:30 -- during the soak's
            # first pulse if the soak is running.
            self.vdt.set_local(day_start, 5)
            routine_done = False

            async def routine_mid_soak(index):
                nonlocal routine_done
                if index == 0 and not routine_done:
                    routine_done = True
                    res.routine_attempted_during_soak = True
                    before = len(self.clock.pulses)
                    await self.c.run_routine_irrigation()
                    res.routine_mm = (
                        sum(p.minutes for p in self.clock.pulses[before:] if p.valve == self.valve)
                        * self.c.number("flow_rate_mm_per_min")
                    )

            self.clock.reset()
            self.clock.on_pulse = routine_mid_soak
            await self.c.run_deep_soak()
            await self.hass.async_block_till_done()
            self.clock.on_pulse = None
            res.deep_soak_mm = self._mm() - res.routine_mm

            if not routine_done:
                self.vdt.set_local(day_start, 5.5)
                self.clock.reset()
                await self.c.run_routine_irrigation()
                await self.hass.async_block_till_done()
                res.routine_mm = self._mm()
            if self._plans:
                res.target_weekly_used = self._plans[-1].target_weekly_mm

            for hour, mm in sorted(weather.rain):
                if hour >= 5:
                    self.vdt.set_local(day_start, hour)
                    await self._rain(mm)

            self.vdt.set_local(day_start, 14)
            await self._temp(weather.t_max)
            self.vdt.set_local(day_start, 20)
            if isinstance(weather.t_min, (int, float)) and isinstance(weather.t_max, (int, float)):
                await self._temp(round((weather.t_min + weather.t_max) / 2, 1))

            self.vdt.set_local(day_start, 23 + 59 / 60 + 50 / 3600)
            self.c._on_daily_shift(None)
            await self.hass.async_block_till_done()

            res.events = list(self._events)
            res.lock_at_end = self.c.store.state.lock_on
            res.valve_at_end = self.hass.states.get(self.valve).state
            self.results.append(res)
        return self.results

    # --- summaries ---------------------------------------------------------
    def routine_days(self) -> list[int]:
        return [r.index for r in self.results if r.routine_mm > 0]

    def deep_soak_days(self) -> list[int]:
        return [r.index for r in self.results if r.deep_soak_mm > 0]

    def routine_total(self, first=0, last=None) -> float:
        return sum(r.routine_mm for r in self.results[first:last])
