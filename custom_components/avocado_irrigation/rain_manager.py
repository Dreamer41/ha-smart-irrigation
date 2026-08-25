"""Persistent tip-driven rainfall manager."""
from __future__ import annotations

from datetime import datetime, timedelta
from homeassistant.core import HomeAssistant, Event
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .coordinator import significant_rain

STORAGE_VERSION = 1
STORAGE_KEY = "avocado_irrigation_rain"


class RainManager:
    """Persist rain tips and expose rolling rainfall without snapshot summing."""

    def __init__(self, hass: HomeAssistant, entry_id: str, entity_id: str, mm_per_tip: float = 0.3) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.entity_id = entity_id
        self.mm_per_tip = mm_per_tip
        self.store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry_id}")
        self.tips: list[str] = []
        self.total_tips = 0
        self.last_counter_value: int | None = None
        self.last_significant_rain: datetime | None = None
        self._unsub = None

    async def async_load(self) -> None:
        data = await self.store.async_load() or {}
        self.tips = list(data.get("tips", []))
        self.total_tips = int(data.get("total_tips", 0))
        self.last_counter_value = data.get("last_counter_value")
        raw = data.get("last_significant_rain")
        self.last_significant_rain = datetime.fromisoformat(raw) if raw else None
        self._prune(datetime.now().astimezone())

    async def async_start(self) -> None:
        await self.async_load()
        self._unsub = async_track_state_change_event(self.hass, [self.entity_id], self._state_changed)

    async def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        await self._save()

    async def _state_changed(self, event: Event) -> None:
        new = event.data.get("new_state")
        old = event.data.get("old_state")
        if new is None or new.state in ("unknown", "unavailable"):
            return
        entity = self.hass.states.get(self.entity_id)
        domain = self.entity_id.split(".", 1)[0]
        tips = 0
        if domain == "counter":
            try:
                current = int(float(new.state))
                previous = self.last_counter_value
                if previous is not None and current > previous:
                    tips = current - previous
                self.last_counter_value = current
            except ValueError:
                return
        else:
            if new.state == "on" and (old is None or old.state != "on"):
                tips = 1
        if tips:
            now = datetime.now().astimezone()
            for _ in range(tips):
                self.tips.append(now.isoformat())
                self.total_tips += 1
            self._prune(now)
            if self.is_significant(now):
                self.last_significant_rain = now
            await self._save()

    def _prune(self, now: datetime) -> None:
        cutoff = now - timedelta(days=14)
        self.tips = [t for t in self.tips if datetime.fromisoformat(t) >= cutoff]

    def rainfall(self, hours: int, now: datetime | None = None) -> float:
        now = now or datetime.now().astimezone()
        cutoff = now - timedelta(hours=hours)
        count = sum(datetime.fromisoformat(t) >= cutoff for t in self.tips)
        return count * self.mm_per_tip

    def is_significant(self, now: datetime | None = None) -> bool:
        now = now or datetime.now().astimezone()
        return significant_rain(
            rain_24h_mm=self.rainfall(24, now),
            rain_4d_mm=self.rainfall(96, now),
            rain_7d_mm=self.rainfall(168, now),
        )

    @property
    def lifetime_mm(self) -> float:
        return self.total_tips * self.mm_per_tip

    async def _save(self) -> None:
        await self.store.async_save({
            "tips": self.tips,
            "total_tips": self.total_tips,
            "last_counter_value": self.last_counter_value,
            "last_significant_rain": self.last_significant_rain.isoformat() if self.last_significant_rain else None,
        })
