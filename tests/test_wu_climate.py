"""1.8: Borrow Wind, Humidity and Sunshine. With the option on, the Weather Underground poller also takes
the nearby stations' wind, humidity and sunshine (the median of the stations), polls every 30 minutes,
and every outdoor zone uses them for FAO-56 where it has no sensor and no weather entity of its own.
Off (the default), nothing changes. The network is never touched."""
from __future__ import annotations

from datetime import timedelta

import homeassistant.util.dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zoneflow import wu, wu_logic
from custom_components.zoneflow.const import (
    CONF_ENTRY_TYPE,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_USE_WU,
    CONF_WEATHER_ENTITY,
    CONF_WIND_SENSOR_HEIGHT_M,
    CONF_WU_API_KEY,
    CONF_WU_CLIMATE,
    CONF_WU_RADIUS_KM,
    CONF_WU_STATIONS,
    DOMAIN,
    ENTRY_TYPE_WU,
    WU_DATA_KEY,
)
from custom_components.zoneflow import fao56

from .test_smoke_setup import make_entry
from .test_weather_underground import STATIONS, _seed

H = 3600.0
NOW = 1_800_000_000.0


def _obs(total=0.0, age=60.0, wind=None, hum=None, sol=None, now=NOW):
    return wu_logic.Observation(total, now - age, "2027-01-15", wind_ms=wind, humidity_pct=hum, solar_wm2=sol)


# --- the pure part --------------------------------------------------------------------------


def test_the_stations_are_combined_by_their_median():
    got = wu_logic.combine_climate([_obs(wind=1.0, hum=40), _obs(wind=3.0, hum=60), _obs(wind=8.0, hum=70)], NOW)
    assert got == {"wind": 3.0, "humidity": 60.0, "solar": None}
    two = wu_logic.combine_climate([_obs(wind=2.0), _obs(wind=4.0)], NOW)
    assert two["wind"] == 3.0


def test_a_silent_or_implausible_station_is_left_out():
    got = wu_logic.combine_climate(
        [_obs(wind=2.0, hum=50, sol=400), _obs(age=3 * H, wind=9.0, hum=99, sol=900),
         _obs(wind=-1.0, hum=140, sol=3000), _obs(wind=float("nan"), hum=None, sol=None)],
        NOW,
    )
    assert got == {"wind": 2.0, "humidity": 50.0, "solar": 400.0}
    assert wu_logic.combine_climate([], NOW) == {"wind": None, "humidity": None, "solar": None}


def test_a_station_without_a_rain_gauge_gives_no_rain_but_can_give_wind():
    state = wu_logic.StationState()
    assert wu_logic.check_station(state, _obs(total=None, wind=2.0), NOW, "2027-01-15") is None
    assert state.status == "no_data"
    assert wu_logic.combine_climate([_obs(total=None, wind=2.0)], NOW)["wind"] == 2.0


def test_borrowing_polls_every_30_minutes_when_nothing_is_due():
    day_end = NOW + 10 * H
    assert wu_logic.next_poll_ts(NOW, [], False, day_end) == NOW + wu_logic.QUIET_POLL_SECONDS
    assert wu_logic.next_poll_ts(NOW, [], False, day_end, wu_logic.CLIMATE_POLL_SECONDS) == NOW + 30 * 60
    assert wu_logic.next_poll_ts(NOW, [], True, day_end, wu_logic.CLIMATE_POLL_SECONDS) == NOW + wu_logic.WATERING_POLL_SECONDS


@pytest.mark.asyncio
async def test_the_report_fields_are_read_in_metric_units(hass, monkeypatch):
    report = {"epoch": NOW, "obsTimeLocal": "2027-01-15 10:00:00", "humidity": 55, "solarRadiation": 612.3,
              "metric": {"precipTotal": 1.5, "windSpeed": 7.2}}

    async def fake_get(_hass, _url, _params):
        return {"observations": [report]}

    monkeypatch.setattr(wu, "_get_json", fake_get)
    obs = await wu.async_current(hass, "k", "S1")
    assert obs.total_mm == 1.5 and obs.wind_ms == pytest.approx(2.0) and obs.humidity_pct == 55 and obs.solar_wm2 == 612.3
    report["metric"] = {"windSpeed": "n/a"}
    report["humidity"] = [1]
    obs = await wu.async_current(hass, "k", "S1")
    assert obs.total_mm is None and obs.wind_ms is None and obs.humidity_pct is None and obs.solar_wm2 == 612.3


# --- the zone -------------------------------------------------------------------------------


class FakeStations:
    def __init__(self):
        self.reading = {"wind": 3.6, "humidity": 50.0, "solar": 0.0}
        self.present = True

    async def current(self, hass, api_key, station_id):
        if not self.present:
            return None
        now = dt_util.utcnow().timestamp()
        return wu_logic.Observation(
            0.0, now - 30, dt_util.now().date().isoformat(),
            wind_ms=self.reading["wind"], humidity_pct=self.reading["humidity"], solar_wm2=self.reading["solar"],
        )


@pytest.fixture
def stations(monkeypatch):
    fake = FakeStations()
    monkeypatch.setattr(wu, "async_current", fake.current)
    return fake


async def _setup(hass, *, climate=True, **zone):
    await _seed(hass)
    zone_entry = make_entry(hass, **zone)
    wu_entry = MockConfigEntry(
        domain=DOMAIN, title="Weather Underground rain", unique_id=ENTRY_TYPE_WU,
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_WU, CONF_WU_API_KEY: "secret-key", CONF_WU_RADIUS_KM: 2.0,
              CONF_WU_STATIONS: STATIONS, CONF_WU_CLIMATE: climate},
    )
    wu_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(zone_entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][zone_entry.entry_id], hass.data[WU_DATA_KEY]


def _full_day(c, source, stations, day, readings):
    """Feed the zone a whole local `day` of polls every 30 minutes: readings(hour) -> (wind, hum, solar)."""
    start = dt_util.start_of_local_day(day).timestamp()
    c.store.state.day_aggregates = {}
    for key in ("wu_humidity", "wu_wind", "wu_solar"):
        agg = c._aggregate(key)
        agg.reset(start)
        c._put_aggregate(key, agg)
    for i in range(48):
        hour = i / 2
        wind, hum, sol = readings(hour)
        c.on_wu_climate({"wind": wind, "humidity": hum, "solar": sol}, start + hour * H)
    return start + 24 * H


@pytest.mark.asyncio
async def test_a_poll_hands_the_readings_to_every_outdoor_zone_even_one_with_a_gauge(hass, stations):
    c, source = await _setup(hass)
    assert c.uses_wu_climate and not c.uses_wu  # it has a rain gauge: rain stays its own
    await source.async_poll()
    assert source.climate == {"wind": pytest.approx(3.6), "humidity": 50.0, "solar": 0.0}
    agg = c._aggregate("wu_wind")
    assert agg.last_value == pytest.approx(3.6)
    assert source.next_poll_ts - dt_util.utcnow().timestamp() <= wu_logic.CLIMATE_POLL_SECONDS + 5


@pytest.mark.asyncio
async def test_off_nothing_is_borrowed_and_polling_stays_every_two_hours(hass, stations):
    c, source = await _setup(hass, climate=False, **{CONF_RAIN_COUNTER_ENTITY: None})
    hass.config_entries.async_update_entry(c.entry, options={CONF_USE_WU: True})
    await source.async_poll()
    assert not c.uses_wu_climate and source.climate == {} and source.fresh_climate() is None
    assert not any(k.startswith("wu_") for k in c.store.state.day_aggregates)


@pytest.mark.asyncio
async def test_a_day_of_borrowed_readings_feeds_fao56_with_the_zones_wind_height(hass, stations):
    c, source = await _setup(hass, **{CONF_WIND_SENSOR_HEIGHT_M: 10.0})
    day = dt_util.now().date() - timedelta(days=1)

    def readings(hour):
        sun = 600.0 if 7 <= hour < 18 else 0.0
        return 4.0, 40.0 + hour, sun

    end = _full_day(c, source, stations, day, readings)
    c.store.state.today_min_temp_c, c.store.state.today_peak_temp_c = 18.0, 30.0
    c._close_et0_day(day, end)
    e = c.store.state.et0_day_history[0]
    assert e["sources"] == {"humidity": "wu", "wind": "wu", "solar": "wu"}
    assert e["rh_min"] == 40.0 and e["rh_max"] == pytest.approx(63.5)
    assert e["u2"] == pytest.approx(fao56.wind_to_2m(4.0, 10.0), abs=0.01)
    assert e["rs"] == pytest.approx(600 * 11 * H / 1e6, abs=0.1)


@pytest.mark.asyncio
async def test_the_weather_entity_still_comes_before_the_stations(hass, stations):
    hass.states.async_set("weather.home", "sunny", {"humidity": 70, "wind_speed": 9.0, "wind_speed_unit": "km/h"})
    c, source = await _setup(hass, **{CONF_WEATHER_ENTITY: "weather.home"})
    day = dt_util.now().date() - timedelta(days=1)
    end = _full_day(c, source, stations, day, lambda hour: (4.0, 40.0, 500.0 if 6.5 <= hour < 18.5 else 0.0))
    start = dt_util.start_of_local_day(day).timestamp()
    for key, value in (("weather_humidity", 70.0), ("weather_wind", 2.5)):
        agg = c._aggregate(key)
        agg.reset(start)
        agg.add(start, value)
        c._put_aggregate(key, agg)
    c.store.state.today_min_temp_c, c.store.state.today_peak_temp_c = 18.0, 30.0
    c._close_et0_day(day, end)
    e = c.store.state.et0_day_history[0]
    assert e["sources"]["humidity"] == "weather" and e["sources"]["wind"] == "weather"
    assert e["sources"]["solar"] == "wu"  # a weather entity has no sunshine reading


@pytest.mark.asyncio
async def test_too_few_borrowed_hours_are_not_used(hass, stations):
    c, source = await _setup(hass)
    day = dt_util.now().date() - timedelta(days=1)
    start = dt_util.start_of_local_day(day).timestamp()
    c.store.state.day_aggregates = {}
    for key in ("wu_humidity", "wu_wind", "wu_solar"):
        agg = c._aggregate(key)
        agg.reset(start)
        c._put_aggregate(key, agg)
    c.on_wu_climate({"wind": 4.0, "humidity": 40.0, "solar": 500.0}, start + 20 * H)  # from 20:00 only
    c.store.state.today_min_temp_c, c.store.state.today_peak_temp_c = 18.0, 30.0
    c._close_et0_day(day, start + 24 * H)
    sources = c.store.state.et0_day_history[0]["sources"]
    assert "wu" not in sources.values()


@pytest.mark.asyncio
async def test_a_reading_stops_holding_an_hour_after_the_last_poll(hass, stations):
    c, source = await _setup(hass)
    now = dt_util.utcnow().timestamp()
    c.on_wu_climate({"wind": 3.0, "humidity": 50.0, "solar": 0.0}, now - 3 * H)
    c._end_stale_wu_climate(now)
    agg = c._aggregate("wu_wind")
    assert agg.last_value is None and agg.last_ts == pytest.approx(now - 3 * H + wu_logic.CLIMATE_HOLD_SECONDS)
    # A recent reading is left alone.
    c.on_wu_climate({"wind": 3.0, "humidity": 50.0, "solar": 0.0}, now - 600)
    c._end_stale_wu_climate(now)
    assert c._aggregate("wu_wind").last_value == 3.0


@pytest.mark.asyncio
async def test_stations_with_nothing_leave_a_gap(hass, stations):
    c, source = await _setup(hass)
    await source.async_poll()
    stations.present = False
    await source.async_poll()
    assert source.climate == {"wind": None, "humidity": None, "solar": None}
    assert c._aggregate("wu_wind").last_value is None
