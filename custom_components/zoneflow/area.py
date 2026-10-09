"""Areas (1.7.0): a part of the garden ("Backyard", "Front yard") that holds the
sensors its zones share -- the rain gauge, the outdoor temperature, the
weather entity and the phone to notify -- and its own Pause and Snooze Today.

An area is a config entry of its own (CONF_ENTRY_TYPE = ENTRY_TYPE_AREA), like
the Weather Underground entry. A zone uses the area's sensor unless it has
one of its own (controller._area_value). Pause is a second layer: a zone is
paused when its own Pause is on or its area's is, and switching the area
off leaves a zone's own pause alone.
"""
from __future__ import annotations

from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
import homeassistant.util.dt as dt_util

from .const import (
    AREA_DATA_KEY,
    CONF_AREA_MM_PER_TIP,
    CONF_NOTIFY_ENTITY,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_RAIN_SOURCE,
    CONF_WEATHER_ENTITY,
    DOMAIN,
    RAIN_SOURCE_OPTIONS,
    RAIN_SOURCE_TIPS,
)

# The settings an area gives its zones (the same keys a zone stores its own under).
AREA_SHARED_KEYS = (
    CONF_RAIN_COUNTER_ENTITY,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_WEATHER_ENTITY,
    CONF_NOTIFY_ENTITY,
)
DEFAULT_AREA_MM_PER_TIP = 0.2


class AreaController:
    """Runtime state of one area: its settings (from the entry), its Pause and
    Snooze Today (stored), and the zones that are in it."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store: Store = Store(hass, 1, f"{DOMAIN}_area_{entry.entry_id}")
        self.paused = False
        self.paused_since_ts: float | None = None
        self.snooze_date_iso: str | None = None
        self._listeners: list[Callable[[], None]] = []

    async def async_setup(self) -> None:
        raw = await self._store.async_load() or {}
        self.paused = bool(raw.get("paused", False))
        self.paused_since_ts = raw.get("paused_since_ts")
        self.snooze_date_iso = raw.get("snooze_date_iso")

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "paused": self.paused,
                "paused_since_ts": self.paused_since_ts,
                "snooze_date_iso": self.snooze_date_iso,
            }
        )

    # --- settings -----------------------------------------------------------
    @property
    def name(self) -> str:
        return self.entry.title

    def option(self, key: str) -> Any:
        return self.entry.options.get(key, self.entry.data.get(key))

    @property
    def rain_counter_entity(self) -> str | None:
        return self.option(CONF_RAIN_COUNTER_ENTITY) or None

    @property
    def rain_source_type(self) -> str:
        value = self.option(CONF_RAIN_SOURCE)
        return value if value in RAIN_SOURCE_OPTIONS else RAIN_SOURCE_TIPS

    @property
    def rain_mm_per_tip(self) -> float:
        try:
            value = float(self.option(CONF_AREA_MM_PER_TIP))
        except (TypeError, ValueError):
            return DEFAULT_AREA_MM_PER_TIP
        return value if value > 0 else DEFAULT_AREA_MM_PER_TIP

    # --- zones --------------------------------------------------------------
    @property
    def zones(self) -> list[Any]:
        """The loaded zones in this area (a crop is in its greenhouse's)."""
        return [
            c for c in self.hass.data.get(DOMAIN, {}).values()
            if getattr(c, "area_entry_id", None) == self.entry.entry_id
        ]

    # --- listeners ----------------------------------------------------------
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def notify(self) -> None:
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:  # noqa: BLE001 - a display problem must not stop a pause
                pass
        for zone in self.zones:
            zone._notify_status()

    # --- pause and snooze -----------------------------------------------------
    async def set_paused(self, on: bool) -> None:
        if self.paused == on:
            return
        self.paused = on
        self.paused_since_ts = dt_util.utcnow().timestamp() if on else None
        await self._async_save()
        if on:
            # A cycle that is running or queued stops at once, as for a zone's own pause.
            for zone in self.zones:
                await zone.on_area_paused()
        self.notify()

    @property
    def snoozed_today(self) -> bool:
        return self.snooze_date_iso == dt_util.now().date().isoformat()

    async def snooze_today(self) -> None:
        self.snooze_date_iso = dt_util.now().date().isoformat()
        await self._async_save()
        self.notify()

    # --- water --------------------------------------------------------------
    def water_used_liters(self) -> dict[str, float]:
        """Litres applied by the area's zones over the last 30 days and this
        calendar year (mm do not add up across zones, so only litres)."""
        out = {"liters_30d": 0.0, "liters_year": 0.0}
        for zone in self.zones:
            used = zone.water_used()
            out["liters_30d"] += used["liters_30d"]
            out["liters_year"] += used["liters_year"]
        return out


def get_area(hass: HomeAssistant, entry_id: str | None) -> AreaController | None:
    if not entry_id:
        return None
    return hass.data.get(AREA_DATA_KEY, {}).get(entry_id)


def areas(hass: HomeAssistant) -> list[AreaController]:
    return sorted(hass.data.get(AREA_DATA_KEY, {}).values(), key=lambda a: a.name.casefold())
