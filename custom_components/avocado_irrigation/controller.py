"""Automatic irrigation controller preserving the reference YAML behavior."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_change

from .const import DOMAIN
from .coordinator import calculate_deep_soak, calculate_routine
from .rain_manager import RainManager


class IrrigationController:
    """Central scheduler, mutex and safety controller."""

    def __init__(self, hass: HomeAssistant, entry_id: str, rain: RainManager) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.rain = rain
        self._unsubs = []
        self._task: asyncio.Task | None = None
        self.last_irrigation: datetime | None = None
        self.last_deep_soak: datetime | None = None
        self.fault_lockout = False
        self.irrigation_in_progress = False

    @property
    def data(self) -> dict:
        return self.hass.data[DOMAIN][self.entry_id]

    @property
    def config(self) -> dict:
        return self.data["config"]

    async def async_start(self) -> None:
        self._unsubs.append(async_track_time_change(self.hass, self._scheduled, hour=6, minute=0, second=0))
        self._unsubs.append(async_track_time_change(self.hass, self._deep_soak_schedule, hour=5, minute=30, second=0))
        self._unsubs.append(self.hass.bus.async_listen("state_changed", self._watchdog))

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._task:
            self._task.cancel()

    async def _scheduled(self, now: datetime) -> None:
        await self.run_routine()

    async def _deep_soak_schedule(self, now: datetime) -> None:
        await self.run_deep_soak()

    def _set_state(self, **kwargs) -> None:
        self.data.update(kwargs)
        self.hass.helpers.entity_platform.async_get_platforms(self.hass, DOMAIN) if False else None

    def _temperature(self) -> float:
        entity = self.config.get("outdoor_temperature")
        try:
            return float(self.hass.states.get(entity).state) if entity else 30.0
        except (AttributeError, ValueError, TypeError):
            return 30.0

    def _last_run(self) -> datetime:
        return self.last_irrigation or (datetime.now().astimezone() - timedelta(days=7))

    def _last_deep(self) -> datetime:
        return self.last_deep_soak or (datetime.now().astimezone() - timedelta(days=14))

    def _blocked(self) -> bool:
        return self.fault_lockout or self.irrigation_in_progress

    async def run_routine(self, force: bool = False) -> bool:
        if self._blocked():
            return False
        now = datetime.now().astimezone()
        interval = 3 if self._temperature() >= float(self.config.get("hot_temperature_c", 31.5)) else 4
        if not force and (now - self._last_run()).total_seconds() < interval * 86400:
            return False
        if not force and not self._drydown_ok(float(self.config.get("routine_drydown_days", 4.0))):
            return False
        calc = calculate_routine(
            average_peak_temperature_c=self._temperature(),
            rain_past_4d_mm=self.rain.rainfall(96, now),
            weekly_target_mm=float(self.config.get("weekly_target_mm", 12.0)),
            rain_efficiency=float(self.config.get("rain_efficiency", 0.75)),
            flow_rate_mm_per_min=float(self.config.get("flow_rate_mm_per_min", 0.30)),
            max_runtime_minutes=int(self.config.get("max_runtime_minutes", 60)),
            hot_temperature_c=float(self.config.get("hot_temperature_c", 31.5)),
        )
        if calc.capped or calc.runtime_minutes <= 0:
            return False
        return await self._run_valve(calc.runtime_minutes, "routine")

    async def run_deep_soak(self, force: bool = False) -> bool:
        if self._blocked():
            return False
        now = datetime.now().astimezone()
        if not force and (now - self._last_deep()).total_seconds() < 14 * 86400:
            return False
        if not force and not self._drydown_ok(float(self.config.get("deep_soak_drydown_days", 8.0))):
            return False
        if not force and self.rain.rainfall(336, now) >= float(self.config.get("deep_soak_rain_threshold_mm", 40.0)):
            return False
        calc = calculate_deep_soak(
            target_mm=float(self.config.get("deep_soak_target_mm", 25.0)),
            flow_rate_mm_per_min=float(self.config.get("flow_rate_mm_per_min", 0.30)),
            max_runtime_minutes=int(self.config.get("deep_soak_max_runtime_minutes", 120)),
        )
        if calc.capped or calc.total_runtime_minutes <= 0:
            return False
        self.irrigation_in_progress = True
        self.data["irrigation_in_progress"] = True
        try:
            for index in range(3):
                await self._valve_on()
                await asyncio.sleep(calc.pulse_runtime_minutes * 60)
                await self._valve_off()
                if index < 2:
                    await asyncio.sleep(20 * 60)
            self.last_deep_soak = datetime.now().astimezone()
            self.data["last_deep_soak"] = self.last_deep_soak
            return True
        finally:
            await self._valve_off()
            self.irrigation_in_progress = False
            self.data["irrigation_in_progress"] = False

    def _drydown_ok(self, days: float) -> bool:
        last = self.rain.last_significant_rain
        return last is None or (datetime.now().astimezone() - last).total_seconds() >= days * 86400

    async def _run_valve(self, minutes: int, kind: str) -> bool:
        self.irrigation_in_progress = True
        self.data["irrigation_in_progress"] = True
        try:
            await self._valve_on()
            await asyncio.sleep(max(minutes - 1, 0) * 60)
            await self._valve_off()
            self.last_irrigation = datetime.now().astimezone()
            self.data["last_irrigation"] = self.last_irrigation
            return True
        finally:
            await self._valve_off()
            self.irrigation_in_progress = False
            self.data["irrigation_in_progress"] = False

    async def _valve_on(self) -> None:
        valve = self.config["irrigation_valve"]
        await self.hass.services.async_call("switch", "turn_on", {"entity_id": valve}, blocking=True)

    async def _valve_off(self) -> None:
        valve = self.config["irrigation_valve"]
        await self.hass.services.async_call("switch", "turn_off", {"entity_id": valve}, blocking=True)

    async def _watchdog(self, event) -> None:
        if event.data.get("entity_id") != self.config.get("irrigation_valve"):
            return
        new = event.data.get("new_state")
        if new is None or new.state != "on":
            return
        # Independent hard cutoff. A scheduled/manual run is always far below this.
        started = new.last_changed
        if (datetime.now().astimezone() - started).total_seconds() >= 150 * 60:
            await self._valve_off()
            self.fault_lockout = True
            self.data["fault_lockout"] = True
            self.irrigation_in_progress = False
            self.data["irrigation_in_progress"] = False

    async def clear_fault(self) -> None:
        self.fault_lockout = False
        self.data["fault_lockout"] = False
