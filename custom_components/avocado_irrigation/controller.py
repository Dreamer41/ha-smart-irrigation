"""Automatic irrigation controller preserving the reference YAML behavior."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .coordinator import calculate_deep_soak, calculate_routine
from .rain_manager import RainManager


class IrrigationController:
    """Central scheduler, mutex and hard safety controller."""

    def __init__(self, hass: HomeAssistant, entry_id: str, rain: RainManager) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.rain = rain
        self.store = Store(hass, 1, f"avocado_irrigation_controller_{entry_id}")
        self._unsubs = []
        self.last_irrigation: datetime | None = None
        self.last_deep_soak: datetime | None = None
        self.fault_lockout = False
        self.irrigation_in_progress = False

    @property
    def data(self) -> dict:
        return self.hass.data[DOMAIN][self.entry_id]

    @property
    def config(self) -> dict:
        entry = self.hass.config_entries.async_get_entry(self.entry_id)
        return {**self.data["config"], **(entry.options if entry else {})}

    async def async_start(self) -> None:
        saved = await self.store.async_load() or {}
        self.last_irrigation = self._parse(saved.get("last_irrigation"))
        self.last_deep_soak = self._parse(saved.get("last_deep_soak"))
        self.fault_lockout = bool(saved.get("fault_lockout", False))
        self.data["fault_lockout"] = self.fault_lockout
        self._unsubs.append(async_track_time_change(self.hass, self._scheduled, hour=6, minute=0, second=0))
        self._unsubs.append(async_track_time_change(self.hass, self._deep_soak_schedule, hour=5, minute=30, second=0))
        self._unsubs.append(async_track_time_change(self.hass, self._watchdog_tick, second=0))

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        await self._save()

    @staticmethod
    def _parse(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value else None

    async def _save(self) -> None:
        await self.store.async_save({
            "last_irrigation": self.last_irrigation.isoformat() if self.last_irrigation else None,
            "last_deep_soak": self.last_deep_soak.isoformat() if self.last_deep_soak else None,
            "fault_lockout": self.fault_lockout,
        })

    async def _scheduled(self, now: datetime) -> None:
        await self.run_routine()

    async def _deep_soak_schedule(self, now: datetime) -> None:
        await self.run_deep_soak()

    def _temperature(self) -> float:
        entity = self.config.get("outdoor_temperature")
        try:
            state = self.hass.states.get(entity) if entity else None
            return float(state.state) if state else 30.0
        except (AttributeError, ValueError, TypeError):
            return 30.0

    def _last_run(self) -> datetime:
        return self.last_irrigation or (datetime.now().astimezone() - timedelta(days=7))

    def _last_deep(self) -> datetime:
        return self.last_deep_soak or (datetime.now().astimezone() - timedelta(days=14))

    def _blocked(self) -> bool:
        return self.fault_lockout or self.irrigation_in_progress

    def _start_mutex(self) -> None:
        self.irrigation_in_progress = True
        self.data["irrigation_in_progress"] = True
        self.data["irrigation_started"] = datetime.now().astimezone()

    def _stop_mutex(self) -> None:
        self.irrigation_in_progress = False
        self.data["irrigation_in_progress"] = False
        self.data.pop("irrigation_started", None)

    async def run_routine(self, force: bool = False) -> bool:
        if self._blocked():
            return False
        now = datetime.now().astimezone()
        interval = 3 if self._temperature() >= float(self.config.get("hot_temperature_c", 31.5)) else 4
        if not force and (now - self._last_run()).total_seconds() < interval * 86400:
            return False
        # Manual run may bypass the schedule interval, but never bypasses the
        # reference rain/dry-down safety check.
        if not self._drydown_ok(float(self.config.get("routine_drydown_days", 4.0))):
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
        return await self._run_valve(calc.runtime_minutes)

    async def run_deep_soak(self, force: bool = False) -> bool:
        if self._blocked():
            return False
        now = datetime.now().astimezone()
        if not force and (now - self._last_deep()).total_seconds() < 14 * 86400:
            return False
        # Manual run may bypass the 14-day schedule gate, but retains both
        # significant-rain dry-down and 14-day rain-ceiling protection.
        if not self._drydown_ok(float(self.config.get("deep_soak_drydown_days", 8.0))):
            return False
        if self.rain.rainfall(336, now) >= float(self.config.get("deep_soak_rain_threshold_mm", 40.0)):
            return False
        calc = calculate_deep_soak(
            target_mm=float(self.config.get("deep_soak_target_mm", 25.0)),
            flow_rate_mm_per_min=float(self.config.get("flow_rate_mm_per_min", 0.30)),
            max_runtime_minutes=int(self.config.get("deep_soak_max_runtime_minutes", 120)),
        )
        if calc.capped or calc.total_runtime_minutes <= 0:
            return False
        self._start_mutex()
        try:
            for index in range(3):
                await self._valve_on()
                await self._pump_audit()
                await asyncio.sleep(calc.pulse_runtime_minutes * 60)
                await self._valve_off()
                if index < 2:
                    await asyncio.sleep(20 * 60)
            self.last_deep_soak = datetime.now().astimezone()
            self.data["last_deep_soak"] = self.last_deep_soak
            await self._save()
            return True
        finally:
            await self._valve_off()
            self._stop_mutex()

    def _drydown_ok(self, days: float) -> bool:
        last = self.rain.last_significant_rain
        return last is None or (datetime.now().astimezone() - last).total_seconds() >= days * 86400

    async def _run_valve(self, minutes: int) -> bool:
        self._start_mutex()
        try:
            await self._valve_on()
            await self._pump_audit()
            # Preserve the reference YAML's runtime behavior: runtime - 1 minute.
            await asyncio.sleep(max(minutes - 1, 0) * 60)
            await self._valve_off()
            self.last_irrigation = datetime.now().astimezone()
            self.data["last_irrigation"] = self.last_irrigation
            await self._save()
            return True
        finally:
            await self._valve_off()
            self._stop_mutex()

    async def _pump_audit(self) -> None:
        await asyncio.sleep(30)
        entity = self.config.get("pump_power")
        if not entity:
            return
        try:
            state = self.hass.states.get(entity)
            power = float(state.state) if state else 0.0
        except (AttributeError, ValueError, TypeError):
            return
        if power < float(self.config.get("pump_min_watts", 100.0)):
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {"title": "Avocado Irrigation: Low Pump Power Audit", "message": f"Pump reads {power:.0f} W while irrigation is active. Continuing because this is an audit warning, not a hard failure."},
            )

    async def _valve_on(self) -> None:
        await self.hass.services.async_call("switch", "turn_on", {"entity_id": self.config["irrigation_valve"]}, blocking=True)

    async def _valve_off(self) -> None:
        await self.hass.services.async_call("switch", "turn_off", {"entity_id": self.config["irrigation_valve"]}, blocking=True)

    async def _watchdog_tick(self, now: datetime) -> None:
        valve = self.config["irrigation_valve"]
        state = self.hass.states.get(valve)
        if state and state.state == "on" and (now - state.last_changed).total_seconds() >= 150 * 60:
            await self._trip_fault("Valve remained ON for 150 minutes. Emergency shutdown executed.")
            return
        started = self.data.get("irrigation_started")
        if self.irrigation_in_progress and started and (now - started).total_seconds() >= 180 * 60:
            await self._trip_fault("Irrigation mutex remained active for 180 minutes.")

    async def _trip_fault(self, message: str) -> None:
        await self._valve_off()
        self.fault_lockout = True
        self.data["fault_lockout"] = True
        self._stop_mutex()
        await self._save()
        await self.hass.services.async_call(
            "persistent_notification", "create",
            {"title": "CRITICAL: Avocado Irrigation Fault Lockout", "message": f"{message} System is locked until manually reset."},
        )

    async def clear_fault(self) -> None:
        self.fault_lockout = False
        self.data["fault_lockout"] = False
        await self._save()
