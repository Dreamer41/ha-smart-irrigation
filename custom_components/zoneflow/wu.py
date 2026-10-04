"""Weather Underground rain (1.6.1, experimental): the shared poller.

One config entry per Home Assistant (CONF_ENTRY_TYPE = ENTRY_TYPE_WU) holds
the API key and 1-3 chosen stations. This polls them, combines their rain
(wu_logic.py) into one record, and hands it to the outdoor zones that have
no rain gauge and use it (controller.uses_wu).

Only for rain deduction -- not forecasting, and not for zones with a gauge.
The API key is stored only in the config entry: never logged, and redacted
in diagnostics.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, time as dt_time, timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
import homeassistant.util.dt as dt_util

from . import wu_logic as wl
from .const import CONF_WU_API_KEY, CONF_WU_STATIONS, DOMAIN, REPAIR_WU_NO_DATA_SECONDS

_LOGGER = logging.getLogger(__name__)

NEAR_URL = "https://api.weather.com/v3/location/near"
CURRENT_URL = "https://api.weather.com/v2/pws/observations/current"
REQUEST_TIMEOUT_SECONDS = 20
STORE_KEY = f"{DOMAIN}_weather_underground"
ISSUE_NO_DATA = "weather_underground_no_data"


class InvalidKey(Exception):
    """The API key was refused."""


class CannotConnect(Exception):
    """Weather Underground could not be reached or answered with an error."""


async def _get_json(hass: HomeAssistant, url: str, params: dict[str, str]) -> dict | None:
    """GET a WU URL. None for "no content" (a station with nothing recent)."""
    session = async_get_clientsession(hass)
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
            response = await session.get(url, params=params)
            if response.status in (401, 403):
                raise InvalidKey
            if response.status in (204, 404):
                return None
            if response.status != 200:
                raise CannotConnect(f"HTTP {response.status}")
            return await response.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise CannotConnect(type(err).__name__) from err


async def async_nearby_stations(hass: HomeAssistant, api_key: str) -> list[dict[str, Any]]:
    """Up to 10 stations nearest Home Assistant's home, with the distance
    worked out by ZoneFlow, nearest first."""
    lat, lon = hass.config.latitude, hass.config.longitude
    data = await _get_json(
        hass, NEAR_URL, {"geocode": f"{lat},{lon}", "product": "pws", "format": "json", "apiKey": api_key}
    )
    location = (data or {}).get("location") or {}
    stations = []
    for sid, name, s_lat, s_lon in zip(
        location.get("stationId") or [],
        location.get("stationName") or [],
        location.get("latitude") or [],
        location.get("longitude") or [],
    ):
        if sid is None or s_lat is None or s_lon is None:
            continue
        stations.append(
            {
                "id": sid,
                "name": name or sid,
                "latitude": s_lat,
                "longitude": s_lon,
                "distance_km": round(wl.distance_km(lat, lon, s_lat, s_lon), 2),
            }
        )
    return sorted(stations, key=lambda s: s["distance_km"])


async def async_current(hass: HomeAssistant, api_key: str, station_id: str) -> wl.Observation | None:
    """A station's current report, or None when it has nothing recent."""
    data = await _get_json(
        hass,
        CURRENT_URL,
        {"stationId": station_id, "format": "json", "units": "m", "numericPrecision": "decimal", "apiKey": api_key},
    )
    try:
        obs = (data or {}).get("observations") or []
        if not obs:
            return None
        report = obs[0]
        total = report.get("metric", {}).get("precipTotal")
        if total is None:
            return None
        return wl.Observation(
            total_mm=float(total),
            obs_ts=float(report["epoch"]),
            obs_day=str(report["obsTimeLocal"])[:10],
        )
    except (KeyError, TypeError, ValueError):
        return None


class WURainSource:
    """The poller and its rain record, shared by every zone that uses it."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store: Store = Store(hass, 1, STORE_KEY)
        self.record = wl.RainRecord()
        self.day = wl.DayState()
        self.stations: dict[str, wl.StationState] = {}
        self.last_poll_ts: float | None = None
        self.last_good_ts: float | None = None
        self.next_poll_ts: float | None = None
        self.used_station_ids: list[str] = []
        self._unsub_timer: Callable[[], None] | None = None
        self._listeners: list[Callable[[], None]] = []
        self._poll_lock = asyncio.Lock()
        self._stopping = False

    # -- configuration ---------------------------------------------------
    @property
    def station_info(self) -> list[dict[str, Any]]:
        return list(self.entry.options.get(CONF_WU_STATIONS, self.entry.data.get(CONF_WU_STATIONS)) or [])

    @property
    def _api_key(self) -> str:
        return self.entry.options.get(CONF_WU_API_KEY, self.entry.data.get(CONF_WU_API_KEY)) or ""

    # -- lifecycle -------------------------------------------------------
    async def async_setup(self) -> None:
        raw = await self._store.async_load() or {}
        self.record = wl.RainRecord.from_persisted(raw.get("record"))
        self.day = wl.DayState.from_dict(raw.get("day"))
        self.stations = {sid: wl.StationState.from_dict(data) for sid, data in (raw.get("stations") or {}).items()}
        self.last_poll_ts = raw.get("last_poll_ts")
        self.last_good_ts = raw.get("last_good_ts")
        self.used_station_ids = list(raw.get("used_station_ids") or [])
        # First poll shortly after start (Home Assistant is busy at startup).
        self._schedule(dt_util.utcnow().timestamp() + 30)

    async def async_unload(self) -> None:
        self._stopping = True
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "record": self.record.as_persisted(),
                "day": self.day.as_dict(),
                "stations": {sid: state.as_dict() for sid, state in self.stations.items()},
                "last_poll_ts": self.last_poll_ts,
                "last_good_ts": self.last_good_ts,
                "used_station_ids": self.used_station_ids,
            }
        )

    @callback
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener) if listener in self._listeners else None

    # -- what the zones read ----------------------------------------------
    def sum_between(self, start_ts: float, end_ts: float) -> float:
        return self.record.sum_between(start_ts, end_ts)

    def fresh_sum_since(self, start_ts: float) -> float:
        return self.record.fresh_sum_since(start_ts)

    def today_mm(self) -> float:
        return self.record.sum_between(dt_util.start_of_local_day().timestamp(), dt_util.utcnow().timestamp())

    @property
    def confidence(self) -> str:
        """"none", "low" (one station) or "normal"."""
        if not self.used_station_ids:
            return "none"
        return "low" if len(self.used_station_ids) == 1 else "normal"

    # -- polling -----------------------------------------------------------
    def _zones(self) -> list[Any]:
        return [c for c in self.hass.data.get(DOMAIN, {}).values() if getattr(c, "uses_wu", False)]

    def _day_end_ts(self, now: datetime) -> float:
        local = dt_util.as_local(now)
        target = datetime.combine(local.date(), dt_time(*wl.DAY_END_POLL_TIME), tzinfo=local.tzinfo)
        if target <= local:
            target = datetime.combine(local.date() + timedelta(days=1), dt_time(*wl.DAY_END_POLL_TIME), tzinfo=local.tzinfo)
        return dt_util.as_utc(target).timestamp()

    def _schedule_next(self) -> None:
        now = dt_util.utcnow()
        now_ts = now.timestamp()
        waterings: list[float] = []
        running = False
        for zone in self._zones():
            try:
                waterings += zone.wu_watering_slots(now_ts)
                running = running or zone.store.state.lock_on
            except Exception:  # noqa: BLE001 -- a zone's schedule must never stop the poller
                _LOGGER.exception("ZoneFlow: could not read a zone's schedule for Weather Underground polling")
        self._schedule(wl.next_poll_ts(now_ts, waterings, running, self._day_end_ts(now)))

    def _schedule(self, when_ts: float) -> None:
        if self._stopping:
            return
        if self._unsub_timer:
            self._unsub_timer()
        self.next_poll_ts = when_ts
        self._unsub_timer = async_track_point_in_utc_time(
            self.hass, self._on_timer, dt_util.utc_from_timestamp(when_ts)
        )

    @callback
    def _on_timer(self, _now: datetime) -> None:
        self._unsub_timer = None
        self.hass.async_create_task(self.async_poll())

    async def async_refresh_if_stale(self, max_age_seconds: float = wl.FRESH_GAP_SECONDS) -> None:
        """Before a watering checks its rain: poll now unless a poll was
        recent. Never raises -- no data just means no WU rain this time."""
        last = self.last_poll_ts
        if last is not None and dt_util.utcnow().timestamp() - last < max_age_seconds:
            return
        try:
            await self.async_poll()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("ZoneFlow: Weather Underground poll failed")

    async def async_poll(self) -> None:
        async with self._poll_lock:
            try:
                await self._poll()
            finally:
                self._schedule_next()
            # After scheduling, so the sensors show the next poll time too.
            for listener in list(self._listeners):
                try:
                    listener()
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("ZoneFlow: could not update after a Weather Underground poll")
            for zone in self._zones():
                zone.on_wu_rain()

    async def _poll(self) -> None:
        stations = [s["id"] for s in self.station_info]
        if not stations:
            return
        api_key = self._api_key
        results = await asyncio.gather(
            *(async_current(self.hass, api_key, sid) for sid in stations), return_exceptions=True
        )
        now_ts = dt_util.utcnow().timestamp()
        today = dt_util.now().date().isoformat()
        totals: dict[str, float] = {}
        for sid, result in zip(stations, results):
            state = self.stations.setdefault(sid, wl.StationState())
            if isinstance(result, InvalidKey):
                _LOGGER.warning("ZoneFlow: Weather Underground refused the API key")
            elif isinstance(result, Exception):
                _LOGGER.debug("ZoneFlow: Weather Underground station %s: %s", sid, result)
            obs = None if isinstance(result, BaseException) else result
            value = wl.check_station(state, obs, now_ts, today)
            if value is not None:
                totals[sid] = value
        totals = wl.drop_stuck(self.stations, totals, now_ts)
        # Stations no longer chosen are forgotten.
        self.stations = {sid: self.stations[sid] for sid in stations if sid in self.stations}
        rain = wl.new_rain(self.day, totals, today)
        fresh = self.last_poll_ts is not None and now_ts - self.last_poll_ts <= wl.FRESH_GAP_SECONDS
        self.last_poll_ts = now_ts
        self.used_station_ids = sorted(totals)
        if rain is not None:
            self.last_good_ts = now_ts
            self.record.add(now_ts, rain, fresh)
        self._update_issue(now_ts)
        await self._async_save()

    def _update_issue(self, now_ts: float) -> None:
        since = self.last_good_ts
        if since is None:
            # Never had data: count from the first poll.
            since = self.stations and min(
                (s.first_seen_ts for s in self.stations.values() if s.first_seen_ts is not None), default=now_ts
            ) or now_ts
        if now_ts - since >= REPAIR_WU_NO_DATA_SECONDS:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                ISSUE_NO_DATA,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_NO_DATA,
                translation_placeholders={"hours": str(int(REPAIR_WU_NO_DATA_SECONDS // 3600))},
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, ISSUE_NO_DATA)
