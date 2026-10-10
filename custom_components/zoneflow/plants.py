"""Plants (1.7.0): the living thing in a zone, with a history of its own.

A zone is a place (valve, soil, flow, location). The plant in it has a name,
a type, a planting date, its watering targets and care settings, and a
timeline: planted, fertilized, a setting changed, moved, removed.

The plant that is *in* a zone keeps its live settings where they have always
been -- the zone's own sliders and selects, with the same entity ids, so
dashboards and automations are untouched. This module keeps the records
around them: who the plant is, which zone it is in, and what happened to it.
Each zone with a valve has one main plant (it drives the watering); other
plants in the same zone are records only.

Records live in one store shared by every zone, so a plant can move between
zones and keep its history. A removed zone's plants are archived, not lost.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
import homeassistant.util.dt as dt_util
from datetime import timedelta

from .const import CONF_DEEP_SOAK_ENABLED, CONF_PLANT, DOMAIN, PLANT_CUSTOM

BOOK_KEY = "zoneflow_plant_book"
STORE_VERSION = 1
CHECK_INTERVAL = timedelta(minutes=2)
# A setting changed again within this long is the same edit (a slider being
# dragged): the history keeps the first old value and the last new one.
COALESCE_SECONDS = 600
HISTORY_LIMIT = 500

# Sliders that belong to the plant (not to the place).
PLANT_NUMBER_KEYS = (
    "target_weekly_mm",
    "target_weekly_hot_mm",
    "target_weekly_cool_mm",
    "crop_coefficient",
    "deep_soak_target_mm",
    "deep_soak_interval_days",
    "deep_soak_drydown_days",
    "deep_soak_rain_threshold",
    "deficit_water_pct",
    "growth_ramp_custom_start_pct",
    "growth_ramp_custom_point1_day",
    "growth_ramp_custom_point1_pct",
    "growth_ramp_custom_point2_day",
    "growth_ramp_custom_point2_pct",
    "growth_ramp_custom_full_day",
)
# What is about the watering rather than the plant itself: a plant that moves
# into a bed leaves these as the bed has them unless asked to bring them.
WATERING_STATE_KEYS = ("demand_model", "deficit_enabled", "deficit_until_ts")
# Plant settings kept in the zone's saved state (state_store.IrrigationState).
PLANT_STATE_KEYS = (
    "growth_stage_mode",
    "demand_model",
    "deficit_enabled",
    "deficit_until_ts",
    "planting_date_ts",
    "health_status",
    "health_notes",
    "fertilizing_interval_months",
    "last_fertilizing_ts",
)


class PlantBook:
    """Every plant, in one store."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store = Store(hass, STORE_VERSION, f"{DOMAIN}_plants")
        self.plants: dict[str, dict[str, Any]] = {}
        # Zones that have been given their first main plant. A zone whose plants
        # were all removed on purpose stays empty (it is not given a new one at
        # every restart).
        self.seeded: set[str] = set()
        self.loaded = asyncio.Event()  # set once the store has been read

    async def async_load(self) -> None:
        raw = await self._store.async_load()
        if isinstance(raw, dict) and isinstance(raw.get("plants"), dict):
            self.plants = raw["plants"]
            self.seeded = set(raw.get("seeded") or ())

    def _data(self) -> dict[str, Any]:
        return {"plants": self.plants, "seeded": sorted(self.seeded)}

    def _save(self) -> None:
        self._store.async_delay_save(self._data, 5)

    async def async_flush(self) -> None:
        await self._store.async_save(self._data())

    # --- reading --------------------------------------------------------------
    def in_zone(self, zone_id: str) -> list[dict[str, Any]]:
        """The plants in a zone, the main one first."""
        found = [p for p in self.plants.values() if p.get("zone_id") == zone_id]
        return sorted(found, key=lambda p: (not p.get("main"), p.get("created_ts", 0)))

    def main(self, zone_id: str) -> dict[str, Any] | None:
        return next((p for p in self.in_zone(zone_id) if p.get("main")), None)

    # --- writing --------------------------------------------------------------
    def create(self, name: str, kind: str, zone_id: str | None, main: bool, source: str) -> dict[str, Any]:
        now = dt_util.utcnow().timestamp()
        plant = {
            "id": uuid.uuid4().hex,
            "name": name,
            "type": kind,
            "zone_id": zone_id,
            "main": bool(main and zone_id),
            "created_ts": now,
            "snapshot": {},
            "history": [],
        }
        self.plants[plant["id"]] = plant
        self.add_history(plant["id"], "created", source=source)
        return plant

    def add_history(self, plant_id: str, kind: str, **data: Any) -> None:
        plant = self.plants.get(plant_id)
        if plant is None:
            return
        history = plant.setdefault("history", [])
        history.append({"ts": dt_util.utcnow().timestamp(), "kind": kind, "data": data})
        del history[:-HISTORY_LIMIT]
        self._save()

    def log_setting(self, plant_id: str, key: str, old: Any, new: Any) -> None:
        """A setting changed. Changes to the same setting close together are
        one edit."""
        plant = self.plants.get(plant_id)
        if plant is None:
            return
        history = plant.setdefault("history", [])
        now = dt_util.utcnow().timestamp()
        for entry in reversed(history):
            if now - entry["ts"] > COALESCE_SECONDS:
                break
            if entry["kind"] == "setting" and entry["data"].get("key") == key:
                entry["ts"] = now
                entry["data"]["new"] = new
                if entry["data"].get("old") == new:
                    history.remove(entry)  # back where it started
                self._save()
                return
        self.add_history(plant_id, "setting", key=key, old=old, new=new)

    def archive_zone(self, zone_id: str) -> None:
        """A zone was deleted: its plants stay on record, in no zone."""
        for plant in self.in_zone(zone_id):
            plant["zone_id"] = None
            plant["main"] = False
            plant["archived_ts"] = dt_util.utcnow().timestamp()
            self.add_history(plant["id"], "removed", reason="zone_deleted")
        self._save()


async def async_get_book(hass: HomeAssistant) -> PlantBook:
    book = hass.data.get(BOOK_KEY)
    if book is None:
        book = PlantBook(hass)
        hass.data[BOOK_KEY] = book  # set first so a second caller finds this one...
        try:
            await book.async_load()
        finally:
            book.loaded.set()
    else:
        await book.loaded.wait()  # ...and waits for the load: an empty book would give every zone a new main plant
    return book


def _round(value: Any) -> Any:
    return round(value, 4) if isinstance(value, float) else value


class ZonePlants:
    """A zone's view of its plants: makes sure it has a main plant, and keeps
    that plant's history up to date as its settings change."""

    def __init__(self, controller: Any, book: PlantBook) -> None:
        self.controller = controller
        self.book = book
        self._last: dict[str, Any] = {}
        self._unsub = None

    @property
    def zone_id(self) -> str:
        return self.controller.entry.entry_id

    def main(self) -> dict[str, Any] | None:
        return self.book.main(self.zone_id)

    def values(self) -> dict[str, Any]:
        """The plant's live settings as the zone has them now."""
        c = self.controller
        out: dict[str, Any] = {key: _round(c.number(key)) for key in PLANT_NUMBER_KEYS if key in c.numbers}
        state = c.store.state
        for key in PLANT_STATE_KEYS:
            out[key] = _round(getattr(state, key, None))
        out["growth_ramp_profile"] = c.growth_ramp_profile
        out["deep_soak_enabled"] = bool(c.deep_soak_enabled)
        return out

    def _default_name(self) -> str:
        c = self.controller
        kind = c.entry.options.get(CONF_PLANT, c.entry.data.get(CONF_PLANT)) or PLANT_CUSTOM
        if kind == PLANT_CUSTOM:
            return c.entry.title
        return kind.replace("_", " ").capitalize()

    async def async_start(self) -> None:
        """After the zone's entities exist: give a zone with a valve its main
        plant (an updated install gets one for each existing zone), take the
        baseline for the history, and keep watching."""
        c = self.controller
        if c.has_valve and self.zone_id not in self.book.seeded:
            if self.main() is None:
                kind = c.entry.options.get(CONF_PLANT, c.entry.data.get(CONF_PLANT)) or PLANT_CUSTOM
                plant = self.book.create(self._default_name(), kind, self.zone_id, True, "update")
                plant["snapshot"] = self.values()
            self.book.seeded.add(self.zone_id)
            self.book._save()
        self._last = self.values()
        self._unsub = async_track_time_interval(c.hass, self._tick, CHECK_INTERVAL)
        c._notify_status()  # the Status sensor lists the plants

    @callback
    def _tick(self, _now=None) -> None:
        self.check()

    def check(self) -> None:
        """Log what changed in the plant's settings since last time."""
        plant = self.main()
        now = self.values()
        if plant is not None:
            for key, value in now.items():
                old = self._last.get(key)
                if key in self._last and old != value:
                    self.book.log_setting(plant["id"], key, old, value)
            plant["snapshot"] = now
        self._last = now

    async def async_apply(self, snapshot: dict[str, Any], watering: bool = True) -> None:
        """Put a plant's settings on the zone (a plant arriving, or becoming
        the main one). Not logged as edits of the plant. With `watering` False
        only what is about the plant itself (planting date, health, fertilizing)
        goes on; the zone keeps its way of watering."""
        c = self.controller
        if watering:
            for key in PLANT_NUMBER_KEYS:
                if snapshot.get(key) is not None and key in c.numbers:
                    await c.numbers[key].async_set_metric_value(float(snapshot[key]))
        state = c.store.state
        for key in PLANT_STATE_KEYS:
            if key in snapshot and (watering or key not in WATERING_STATE_KEYS):
                setattr(state, key, snapshot[key])
        if watering and snapshot.get("growth_ramp_profile") is not None:
            state.growth_ramp_profile_override = snapshot["growth_ramp_profile"]
        await c.store.async_save()
        self._last = self.values()
        wanted = snapshot.get("deep_soak_enabled") if watering else None
        if wanted is not None and bool(wanted) != c.deep_soak_enabled:
            # Deep soak on/off is kept in the zone's settings: changing it restarts the zone.
            c.hass.config_entries.async_update_entry(
                c.entry, options={**c.entry.options, CONF_DEEP_SOAK_ENABLED: bool(wanted)}
            )
        c._notify_status()

    async def async_unload(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        if self.controller.numbers:
            self.check()  # a change made just before a reload or shutdown
        await self.book.async_flush()

    # --- for the cards --------------------------------------------------------
    def summary(self) -> list[dict[str, Any]]:
        return [
            {"id": p["id"], "name": p["name"], "type": p.get("type"), "main": bool(p.get("main"))}
            for p in self.book.in_zone(self.zone_id)
        ]
