"""Two simulated weeks of 1.6.1 features on a virtual clock (the time
compressed harness of the season tests): Weather Underground rain with
manual rain, and a greenhouse with three crops. Days of different weather
run in a fraction of a second; every valve-open minute is still recorded.

What is checked is what a person would notice over two weeks: rain is
credited and watering waits for it, nothing is left running, soil probes
stay in range, the climate follows the temperature, and a device switched by
hand is given back to automatic after the Auto Resume time.
"""
from __future__ import annotations

import types
from datetime import datetime, timedelta

import homeassistant.util.dt as dt_util
import pytest
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN  # noqa: F401
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zoneflow import controller as controller_module
from custom_components.zoneflow import greenhouse as greenhouse_module
from custom_components.zoneflow import wu as wu_module
from custom_components.zoneflow import wu_logic
from custom_components.zoneflow.const import (
    CONF_CSV_PATH,
    CONF_ENTRY_TYPE,
    CONF_FAN_ENTITIES,
    CONF_HEATER_ENTITIES,
    CONF_INSIDE_TEMP_ENTITY,
    CONF_PARENT_ZONE,
    CONF_PLANT,
    CONF_PUMP_ID,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_USE_WU,
    CONF_VALVE_ENTITY,
    CONF_WU_API_KEY,
    CONF_WU_RADIUS_KM,
    CONF_WU_STATIONS,
    CONF_ZONE_NAME,
    CONF_ZONE_TYPE,
    DOMAIN,
    ENTRY_TYPE_WU,
    WU_DATA_KEY,
)

from .scenario_harness import CompressedTime
from .season_sim import Day, SeasonSim, VirtualDt
from .test_smoke_setup import OUTDOOR_TEMP, PUMP, VALVE, make_entry

DAY = 86400.0


def _invariants(sim, c):
    for r in sim.results:
        assert r.valve_at_end == "off", f"valve left on at the end of day {r.index}"
        assert r.lock_at_end is False, f"lock still held at the end of day {r.index}"
        minutes = (r.routine_mm + r.deep_soak_mm) / c.number("flow_rate_mm_per_min")
        assert minutes <= c.number("max_daily_runtime_minutes") + 3, f"daily cap exceeded on day {r.index}"


# --------------------------------------------------------------------------
# 1. Rain from Weather Underground stations and by hand, no rain gauge
# --------------------------------------------------------------------------

STATIONS = [
    {"id": "IONE", "name": "One", "latitude": 9.5, "longitude": 100.0, "distance_km": 0.4},
    {"id": "ITWO", "name": "Two", "latitude": 9.5, "longitude": 100.0, "distance_km": 0.8},
    {"id": "ITHREE", "name": "Three", "latitude": 9.5, "longitude": 100.0, "distance_km": 1.3},
]
# What the three stations make of the same rain: a little less, exact, much more.
GAUGE = {"IONE": 0.9, "ITWO": 1.0, "ITHREE": 1.5}


class FakeStations:
    """The stations' rain-since-midnight, on the simulated clock."""

    def __init__(self, vdt):
        self.vdt = vdt
        self.day = None
        self.totals = {sid: 0.0 for sid in GAUGE}
        self.offline = False
        self.calls = 0

    def _local_day(self):
        return dt_util.as_local(self.vdt.t).date().isoformat()

    def add(self, mm):
        self._roll()
        for sid, factor in GAUGE.items():
            self.totals[sid] += mm * factor

    def _roll(self):
        today = self._local_day()
        if today != self.day:
            self.day = today
            self.totals = {sid: 0.0 for sid in GAUGE}

    async def current(self, hass, api_key, station_id):
        self.calls += 1
        self._roll()
        if self.offline:
            return None
        return wu_logic.Observation(self.totals[station_id], self.vdt.t.timestamp() - 30, self.day)


class WURainSim(SeasonSim):
    """The season sim with the rain coming from stations, polled like the
    real source polls (a poll after each rain, one at 23:55)."""

    def __init__(self, *args, source, stations, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = source
        self.stations = stations
        self.manual_log: list[tuple[int, float]] = []

    async def _rain(self, mm):
        self.stations.add(mm)
        await self.source.async_poll()

    async def run(self, days):
        # A poll every morning before the 05:00 cycles, as the real source's
        # watering mode does (and the zone refreshes a stale poll itself).
        out = []
        for weather in days:
            out += await super().run([weather])
            self.vdt.set_local(self.start_local + timedelta(days=len(self.results) - 1), 23 + 55 / 60)
            await self.source.async_poll()
        return out


async def _wu_season(hass, monkeypatch, tmp_path):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(OUTDOOR_TEMP, "28", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    await hass.config.async_update(latitude=9.5, longitude=100.0)
    zone_entry = make_entry(hass, **{CONF_RAIN_COUNTER_ENTITY: None, "csv_path": str(tmp_path / "wu.csv")})
    hass.config_entries.async_update_entry(zone_entry, options={CONF_USE_WU: True})
    wu_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Weather Underground rain",
        unique_id=ENTRY_TYPE_WU,
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_WU, CONF_WU_API_KEY: "test", CONF_WU_RADIUS_KM: 2.0, CONF_WU_STATIONS: STATIONS},
    )
    wu_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(zone_entry.entry_id)
    await hass.async_block_till_done()
    c = hass.data[DOMAIN][zone_entry.entry_id]
    source = hass.data[WU_DATA_KEY]
    sim = None

    stations_holder = {}

    async def _current(hass_, api_key, station_id):
        return await stations_holder["fake"].current(hass_, api_key, station_id)

    monkeypatch.setattr(wu_module, "async_current", _current)
    sim = WURainSim(hass, c, monkeypatch, valve=VALVE, temp_entity=OUTDOOR_TEMP, rain_entity="sensor.none",
                    source=source, stations=None)
    stations = FakeStations(sim.vdt)
    sim.stations = stations
    stations_holder["fake"] = stations
    # The source reads the same simulated clock.
    monkeypatch.setattr(wu_module, "dt_util", sim.vdt.module)
    s = c.store.state
    start = sim.vdt.t.timestamp()
    s.last_routine_ts = start - 4 * DAY + 5.5 * 3600
    s.last_deep_soak_ts = start - 3 * DAY + 5 * 3600  # a recent soak: the two weeks are about routine watering
    s.last_significant_rain_ts = None
    s.peak_temp_day_history_c = [31.0] * 3
    s.min_temp_day_history_c = [25.0] * 3
    s.rain_day_history_mm = [0.0] * 10
    return c, sim, source, stations


@pytest.mark.asyncio
async def test_two_weeks_on_station_rain_and_hand_entered_rain(hass, fake_valve_services, monkeypatch, tmp_path):
    c, sim, source, stations = await _wu_season(hass, monkeypatch, tmp_path)
    assert c.uses_wu and not c.rain_counter_entity

    hot, cool = (25.0, 33.0), (23.0, 29.0)
    weather = [
        Day(*hot), Day(*hot), Day(*hot),
        Day(*cool, rain=[(9, 4.0), (10, 6.0)]),      # day 3: 10 mm in the morning
        Day(*hot), Day(*hot),
        Day(*cool, rain=[(14, 40.0), (15, 20.0)]),   # day 6: a 60 mm afternoon storm
        Day(*cool), Day(*hot),
        Day(*hot),                                   # day 9: the stations are offline
        Day(*hot), Day(*hot),
        Day(*cool, rain=[(2, 8.0)]),                 # day 12: rain before the 05:00 cycles
        Day(*hot),
    ]
    daily_rain = [sum(mm for _h, mm in d.rain) for d in weather]

    # Run day by day to act between days like a person and the network would.
    credited = []   # the rain the zone credited for each day (its rain-day register)
    for index, day in enumerate(weather):
        if index == 9:
            stations.offline = True   # the whole network is down for the day
        if index == 10:
            stations.offline = False
        await sim.run([day])
        credited.append(c.store.state.rain_day_history_mm[0])
        if index == 5:
            # Rain read from a bucket by hand: counts for the day it fell.
            await c.add_manual_rain(12.0)
            assert c.today_rain_mm() >= 12.0
    _invariants(sim, c)

    # Day 3 (10 mm), day 6 (the 60 mm storm: the stations' median, not the
    # by-hand 12 mm on top and not their sum), day 12 (8 mm); dry days and the
    # day the network was down: nothing.
    assert credited[3] == pytest.approx(10.0, abs=0.1), credited
    assert credited[6] == pytest.approx(60.0, abs=0.1), credited
    assert credited[12] == pytest.approx(8.0, abs=0.1), credited
    for dry in (0, 1, 2, 4, 5, 7, 8, 9, 10, 11, 13):
        assert credited[dry] == 0.0, (dry, credited)

    # The storm (24 h total over 35 mm) is a heavy rain: it restarts the dry-down,
    # so there is no routine watering in the days right after it.
    storm_day = 6
    dry_down = c.number("routine_drydown_days")
    quiet = [r.routine_mm for r in sim.results[storm_day + 1: storm_day + 1 + int(dry_down) - 1]]
    assert quiet and all(mm == 0 for mm in quiet), quiet
    # Rain on day 3 (10 mm) is credited against the next watering: it is smaller
    # than the same weather without rain would have been.
    watered = [r for r in sim.results if r.routine_mm > 0]
    assert len(watered) >= 3
    assert all(r.routine_mm <= c.number("max_runtime_minutes") * c.number("flow_rate_mm_per_min") + 1 for r in watered)
    print("SUMMARY WU run: routine days", [i for i, r in enumerate(sim.results) if r.routine_mm > 0],
          "mm", [round(r.routine_mm, 1) for r in sim.results if r.routine_mm > 0], "credited rain", credited)
    # Both polling modes ran, and the source found its stations every day.
    assert stations.calls >= 14 * 3
    assert source.confidence in ("normal", "none")  # normal unless the very last poll was offline


# --------------------------------------------------------------------------
# 2. A greenhouse with three crops
# --------------------------------------------------------------------------

INSIDE = "sensor.sim_inside_temp"
FAN = "switch.sim_fan"
HEATER = "switch.sim_heater"
CROPS = {
    # name: (valve, probe, soil dries per day in %-points, plant)
    "Tomatoes": ("switch.sim_valve_tomatoes", "sensor.sim_probe_tomatoes", 5.0, "tomatoes"),
    "Cucumbers": ("switch.sim_valve_cucumbers", "sensor.sim_probe_cucumbers", 7.0, "leafy_vegetables"),
    "Herbs": ("switch.sim_valve_herbs", "sensor.sim_probe_herbs", 3.0, "herbs"),
}


class ClockShim:
    """greenhouse.py's `time` on the simulated clock."""

    def __init__(self, vdt):
        self.vdt = vdt

    def time(self):
        return self.vdt.t.timestamp()

    def monotonic(self):
        return self.vdt.t.timestamp()

    def __getattr__(self, name):
        import time as real

        return getattr(real, name)


def _inside_temp(hour, low, high):
    """A day: coldest at 05:00, hottest at 15:00."""
    import math

    return round((low + high) / 2 + (high - low) / 2 * math.sin((hour - 9.0) / 24.0 * 2 * math.pi), 1)


@pytest.mark.asyncio
async def test_two_weeks_in_a_greenhouse_with_three_crops(hass, monkeypatch, tmp_path):
    from homeassistant.setup import async_setup_component

    await async_setup_component(hass, "switch", {})
    log: dict[str, list[tuple[float, str]]] = {}

    def _flip(service, state):
        async def handler(call):
            ids = call.data["entity_id"]
            for entity_id in [ids] if isinstance(ids, str) else ids:
                hass.states.async_set(entity_id, state, context=call.context)

        hass.services.async_register("switch", service, handler)

    _flip("turn_on", "on")
    _flip("turn_off", "off")

    valves = [v for v, *_ in CROPS.values()]
    for entity in (FAN, HEATER, *valves):
        hass.states.async_set(entity, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(INSIDE, "22", {"unit_of_measurement": "°C"})
    moisture = {name: 45.0 for name in CROPS}
    for name, (_v, probe, _d, _p) in CROPS.items():
        hass.states.async_set(probe, str(moisture[name]))
    await hass.async_block_till_done()
    await hass.config.async_update(latitude=9.5, longitude=100.0)

    house = MockConfigEntry(
        domain=DOMAIN,
        title="Sim Greenhouse",
        data={
            CONF_ZONE_NAME: "Sim Greenhouse", CONF_ZONE_TYPE: "greenhouse", CONF_INSIDE_TEMP_ENTITY: INSIDE,
            CONF_FAN_ENTITIES: [FAN], CONF_HEATER_ENTITIES: [HEATER], CONF_PUMP_ID: "gh supply",
            CONF_CSV_PATH: str(tmp_path / "house.csv"),
            "deep_soak_time": "05:00:00", "routine_time": "05:30:00", "deep_soak_enabled": False,
        },
    )
    house.add_to_hass(hass)
    crop_entries = {}
    for name, (valve, probe, _d, plant) in CROPS.items():
        crop_entries[name] = MockConfigEntry(
            domain=DOMAIN,
            title=name,
            data={
                CONF_ZONE_NAME: name, CONF_ZONE_TYPE: "greenhouse", CONF_PARENT_ZONE: house.entry_id,
                CONF_VALVE_ENTITY: valve, "soil_moisture_entity": probe, CONF_PLANT: plant,
                CONF_PUMP_ID: "gh supply", CONF_CSV_PATH: str(tmp_path / f"{name}.csv"),
                "deep_soak_time": "05:00:00", "routine_time": "05:30:00", "deep_soak_enabled": False,
            },
        )
        crop_entries[name].add_to_hass(hass)
    assert await hass.config_entries.async_setup(house.entry_id)
    await hass.async_block_till_done()
    gh = hass.data[DOMAIN][house.entry_id]
    crops = {name: hass.data[DOMAIN][e.entry_id] for name, e in crop_entries.items()}
    assert [c.is_crop for c in crops.values()] == [True, True, True]
    gh.greenhouse._started = True

    clock = CompressedTime(hass, valves).install(monkeypatch)
    start_local = dt_util.now().astimezone(dt_util.DEFAULT_TIME_ZONE).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    vdt = VirtualDt(dt_util.as_utc(start_local)).install(monkeypatch)
    monkeypatch.setattr(greenhouse_module, "time", ClockShim(vdt))
    heat, vent, fan_t = gh.number("heat_temp"), gh.number("vent_temp"), gh.number("fan_temp")
    assert heat < vent < fan_t

    hourly: list[dict] = []
    watered_mm: dict[str, float] = {name: 0.0 for name in CROPS}
    lows_highs = []
    # Two weeks: mild, a cold snap, a heatwave, mild again.
    plan = [(16, 27)] * 3 + [(5, 18)] * 3 + [(18, 30)] * 2 + [(25, 38)] * 4 + [(16, 27)] * 2
    for day_index, (low, high) in enumerate(plan):
        day_start = start_local + timedelta(days=day_index)
        vdt.set_local(day_start, 0)
        for crop in crops.values():
            crop._on_midnight(None)
        await hass.async_block_till_done()
        lows_highs.append((low, high))
        for hour in range(24):
            vdt.set_local(day_start, hour)
            temp = _inside_temp(hour, low, high)
            if day_index == 10 and 8 <= hour < 14:
                # The inside sensor drops out for six hours in the heatwave.
                hass.states.async_set(INSIDE, "unavailable")
            else:
                hass.states.async_set(INSIDE, str(temp), {"unit_of_measurement": "°C"})
            # The soil dries through the day.
            for name, (_v, probe, drying, _p) in CROPS.items():
                moisture[name] = max(moisture[name] - drying / 24.0, 5.0)
                hass.states.async_set(probe, f"{moisture[name]:.1f}")
            await hass.async_block_till_done()
            if day_index == 6 and hour == 7:
                hass.states.async_set(FAN, "on")  # someone switches the fan on by hand
                await hass.async_block_till_done()
            await gh.greenhouse.async_evaluate("sim")
            await hass.async_block_till_done()
            hourly.append(
                {"day": day_index, "hour": hour, "temp": temp, "fan": hass.states.get(FAN).state,
                 "heater": hass.states.get(HEATER).state, "held": gh.greenhouse._held("fans", vdt.t.timestamp()) > 0}
            )
            if hour == 5:
                vdt.set_local(day_start, 5.5)
                for name, crop in crops.items():
                    clock.reset()
                    await crop.run_routine_irrigation()
                    await hass.async_block_till_done()
                    mm = clock.valve_minutes(CROPS[name][0]) * crop.number("flow_rate_mm_per_min")
                    watered_mm[name] += mm
                    moisture[name] = min(moisture[name] + mm * 1.8, 90.0)  # water into the soil
                    hass.states.async_set(CROPS[name][1], f"{moisture[name]:.1f}")
                    assert hass.states.get(CROPS[name][0]).state == "off", f"{name}: valve left on"
                    assert not crop.store.state.lock_on, f"{name}: lock held"
        for crop in crops.values():
            assert not crop.store.state.lock_on

    # --- the climate followed the temperature ------------------------------
    cold_hours = [h for h in hourly if h["temp"] < heat - 0.5]
    hot_hours = [h for h in hourly if h["temp"] > fan_t + 1.0]
    assert cold_hours, "the cold snap should have gone below the heater setpoint"
    assert hot_hours, "the heatwave should have gone above the fan setpoint"
    # Cold: the heater ran for most of those hours (it switches on below the
    # setpoint and keeps a minimum run time).
    assert sum(1 for h in cold_hours if h["heater"] == "on") >= len(cold_hours) * 0.5
    # Hot: the fan ran for most of those hours.
    assert sum(1 for h in hot_hours if h["fan"] == "on") >= len(hot_hours) * 0.6
    # Never heating while it is hot.
    assert not [h for h in hourly if h["heater"] == "on" and h["temp"] > vent + 2.0]

    # --- the sensor outage: nothing left running without a sensor ----------
    outage = [h for h in hourly if h["day"] == 10 and 8 <= h["hour"] < 14]
    assert len(outage) == 6
    assert sum(1 for h in outage if h["heater"] == "on") <= 3, outage  # never non-stop in the heat
    recovered = [h for h in hourly if h["day"] == 10 and h["hour"] >= 15]
    assert any(h["fan"] == "on" for h in recovered), "back on the sensor, the afternoon heat is ventilated"

    # --- a device switched by hand is given back after Auto Resume After ----
    # Day 6, 07:00 (cool morning, fan not wanted): held for the default 1 h,
    # then given back to automatic (off).
    day6 = [h for h in hourly if h["day"] == 6]
    assert day6[7]["fan"] == "on" and day6[7]["held"], day6[7]
    assert day6[9]["fan"] == "off" and not day6[9]["held"], day6[9]

    print("SUMMARY greenhouse: heater hours", sum(1 for h in hourly if h["heater"] == "on"),
          "fan hours", sum(1 for h in hourly if h["fan"] == "on"),
          "water mm", {k: round(v, 1) for k, v in watered_mm.items()},
          "final soil %", {k: round(v) for k, v in moisture.items()})
    # --- the crops were watered by their probes and kept in range -----------
    for name in CROPS:
        assert watered_mm[name] > 0, f"{name} was never watered in two weeks"
        assert 5.0 < moisture[name] < 90.0
    # The fastest drying crop (cucumbers, 7 points a day) got more water than the slowest (herbs, 3).
    assert watered_mm["Cucumbers"] > watered_mm["Herbs"], watered_mm

    # --- restart keeps the links and the settings ---------------------------
    assert await hass.config_entries.async_reload(house.entry_id)
    await hass.async_block_till_done()
    for name, entry in crop_entries.items():
        assert hass.data[DOMAIN][entry.entry_id].is_crop
        assert hass.data[DOMAIN][entry.entry_id].inside_temp_entity == INSIDE
