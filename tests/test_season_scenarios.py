"""Multi-week season scenarios (see season_sim.py for how a day is driven).

These check behavior over time against the model's intent: how often each
cycle runs, how much water goes on per week compared with the weekly
target, how storms push cycles back and for how long, and that the ET curve
actually tracks the weather -- plus invariants every day must satisfy
(valve closed and lock released at the end of the day, daily cap never
exceeded).
"""
from __future__ import annotations

from datetime import date

import pytest

from custom_components.zoneflow import calculations as calc
from custom_components.zoneflow.const import DEMAND_MODEL_ET, DOMAIN

from .season_sim import Day, SeasonSim
from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

DAY = 86400.0
NORMAL = (24.0, 31.0)   # peak 31 -> normal tier (cool < 30 <= normal < 31.5 hot)
HOT = (26.0, 34.0)
COOL = (22.0, 27.0)


async def _season(hass, monkeypatch, tmp_path, *, temp_unit="°C", seed=NORMAL, **entry):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, str(seed[1]), {"unit_of_measurement": temp_unit})
    await hass.async_block_till_done()
    await hass.config.async_update(latitude=9.5)
    entry.setdefault("csv_path", str(tmp_path / "season.csv"))
    e = make_entry(hass, **entry)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    c = hass.data[DOMAIN][e.entry_id]
    sim = SeasonSim(hass, c, monkeypatch, valve=VALVE, temp_entity=OUTDOOR_TEMP, rain_entity=RAIN_COUNTER, temp_unit=temp_unit)
    start = sim.vdt.t.timestamp()
    s = c.store.state
    # An established zone: watered 4 days ago, deep-soaked 14 days ago,
    # three days of this weather already on record.
    s.last_routine_ts = start - 4 * DAY + 5.5 * 3600
    s.last_deep_soak_ts = start - 14 * DAY + 5 * 3600
    s.last_significant_rain_ts = None
    s.peak_temp_day_history_c = [seed[1]] * 3
    s.min_temp_day_history_c = [seed[0]] * 3
    s.rain_day_history_mm = [0.0] * 10
    s.rain_samples = [[start - 3600, 0.0]]  # the counter's reading at setup (what async_setup seeds)
    s.rain_midnight_baseline_mm = 0.0
    return c, sim


def _f(celsius):
    return round(celsius * 9 / 5 + 32, 1)


def _days(n, t=NORMAL, unit="°C", **rain_by_day):
    lo, hi = (t if unit == "°C" else (_f(t[0]), _f(t[1])))
    days = [Day(lo, hi) for _ in range(n)]
    for key, rain in rain_by_day.items():
        days[int(key[1:])].rain = rain
    return days


def _check_invariants(sim, c):
    for r in sim.results:
        assert r.valve_at_end == "off", f"valve left on at end of day {r.index}"
        assert r.lock_at_end is False, f"lock still held at end of day {r.index}"
        minutes = (r.routine_mm + r.deep_soak_mm) / c.number("flow_rate_mm_per_min")
        assert minutes <= c.number("max_daily_runtime_minutes") + 3, f"daily cap exceeded on day {r.index}"


# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_dry_normal_month_waters_the_weekly_target_on_a_4_day_rhythm(hass, fake_valve_services, monkeypatch, tmp_path):
    c, sim = await _season(hass, monkeypatch, tmp_path)
    await sim.run(_days(28))
    _check_invariants(sim, c)

    # Day 0: deep soak is due and runs, and it counts as the routine watering
    # too, so the routine interval restarts from it: routine on day 4, 8, 12,
    # then the day-14 soak restarts it again -> 18, 22, 26. (Before this rule
    # the routine ran on day 1, right after the soak.)
    assert sim.deep_soak_days() == [0, 14]
    assert sim.results[0].routine_attempted_during_soak and sim.results[0].routine_mm == 0
    assert sim.routine_days() == [4, 8, 12, 18, 22, 26]
    # 6 routine runs x (35 mm/week x 4/7) = 120 mm of routine water (the two
    # 25 mm deep soaks come on top).
    assert sim.routine_total() == pytest.approx(120.0, rel=0.03)
    assert all(r.deep_soak_mm == pytest.approx(25.0, abs=0.5) for r in sim.results if r.deep_soak_mm)
    # A routine run always comes a full interval after the previous watering
    # of either kind. (A deep soak keeps its own 14-day clock, so it can
    # follow a routine sooner -- only the soak -> routine direction counts.)
    watered = sorted(set(sim.routine_days()) | set(sim.deep_soak_days()))
    assert all(b - a >= 4 for a, b in zip(watered, watered[1:]) if b in sim.routine_days())


@pytest.mark.asyncio
async def test_a_hot_month_waters_more_often_and_more(hass, fake_valve_services, monkeypatch, tmp_path):
    c, sim = await _season(hass, monkeypatch, tmp_path, seed=HOT)
    await sim.run(_days(28, HOT))
    _check_invariants(sim, c)

    # Every 3 days, counting a deep soak as a watering: each routine run is
    # exactly 3 days after the previous watering of either kind.
    watered = sorted(set(sim.routine_days()) | set(sim.deep_soak_days()))
    assert all(b - a == 3 for a, b in zip(watered, watered[1:]) if b in sim.routine_days())
    # Each routine dose is the hot weekly target spread over a 3-day interval.
    assert all(
        r.routine_mm == pytest.approx(45.0 * 3 / 7, abs=0.6) for r in sim.results if r.routine_mm > 0
    )


@pytest.mark.asyncio
async def test_a_cool_month_waters_less(hass, fake_valve_services, monkeypatch, tmp_path):
    c, sim = await _season(hass, monkeypatch, tmp_path, seed=COOL)
    await sim.run(_days(28, COOL))
    _check_invariants(sim, c)
    # Cool tier: 25 mm/week over a 4-day interval per routine run (a deep
    # soak restarts the interval, as in the normal month).
    doses = [r.routine_mm for r in sim.results if r.routine_mm > 0]
    assert doses and all(d == pytest.approx(25.0 * 4 / 7, abs=0.6) for d in doses)
    assert sim.routine_days() == [4, 8, 12, 18, 22, 26]


@pytest.mark.asyncio
async def test_a_storm_pushes_back_routine_and_deep_soak_for_as_long_as_intended(hass, fake_valve_services, monkeypatch, tmp_path):
    c, sim = await _season(hass, monkeypatch, tmp_path)
    await sim.run(_days(28, d6=[(15, 45.0)]))
    _check_invariants(sim, c)

    assert "Significant Rain" in sim.results[6].events
    # Routine was due day 9; the 4-day holdoff from day 6 15:00 blocks the
    # 05:30 runs on days 9 and 10, so it resumes day 11 with a full dose
    # (the storm is older than this cycle's own rain window).
    days = sim.routine_days()
    assert 9 not in days and 10 not in days and 11 in days
    assert sim.results[11].routine_mm == pytest.approx(20.0, abs=0.5)
    # Deep soak: due day 14, but the 8-day subsoil holdoff runs to day 14
    # 15:00, and then the storm is still inside the 14-day rain window
    # (45 mm >= the 40 mm ceiling) until it ages out on day 20 15:00 -> first run day 21.
    assert sim.deep_soak_days() == [0, 21]


@pytest.mark.asyncio
async def test_regular_moderate_rain_is_credited_and_never_over_credited(hass, fake_valve_services, monkeypatch, tmp_path):
    c, sim = await _season(hass, monkeypatch, tmp_path)
    rain = {f"d{d}": [(16, 8.0)] for d in range(0, 28, 2)}
    await sim.run(_days(28, **rain))
    _check_invariants(sim, c)

    doses = [r.routine_mm for r in sim.results if r.routine_mm > 0]
    # The day-0 deep soak counts as a routine watering, so the first routine
    # is day 4 and -- like every 4-day window after it -- holds two 8 mm
    # days: 2 x 3.52 = 7.04 mm credit, never more.
    for dose in doses:
        assert dose == pytest.approx(20.0 - 7.04, abs=0.6)
    assert sim.routine_total() < 0.75 * 140.0


@pytest.mark.asyncio
@pytest.mark.parametrize("unit", ["°C", "°F"])
async def test_fahrenheit_home_assistant_waters_exactly_like_celsius(hass, fake_valve_services, monkeypatch, tmp_path, unit):
    c, sim = await _season(hass, monkeypatch, tmp_path, temp_unit=unit, seed=HOT)
    await sim.run(_days(21, HOT, unit=unit))
    _check_invariants(sim, c)
    # Identical expectations for both units: hot tier, every 3 days, counted
    # from the latest watering (the day-0 and day-14 deep soaks included).
    assert sim.routine_days() == [3, 6, 9, 12, 17, 20]
    assert c.store.state.peak_temp_day_history_c[0] == pytest.approx(34.0, abs=0.05)
    assert c.store.state.min_temp_day_history_c[0] == pytest.approx(26.0, abs=0.05)


@pytest.mark.asyncio
async def test_et_curve_replaces_roughly_the_water_the_plant_used(hass, fake_valve_services, monkeypatch, tmp_path):
    c, sim = await _season(hass, monkeypatch, tmp_path)
    c.store.state.demand_model = DEMAND_MODEL_ET
    await c.numbers["crop_coefficient"].async_set_native_value(0.8)
    weather = _days(14, COOL) + _days(14, HOT)
    await sim.run(weather)
    _check_invariants(sim, c)

    # Independent reference: each day's own Hargreaves ET0 x Kc, summed.
    used = 0.0
    for i, d in enumerate(weather):
        doy = date.fromisoformat(sim.results[i].date).timetuple().tm_yday
        used += calc.hargreaves_et0(d.t_min, d.t_max, 9.5, doy) * 0.8
    # Water applied over days 1..27 should be in line with what was used
    # (routine replaces demand in arrears; allow for the 3-day averaging lag
    # and the first/last partial intervals).
    assert sim.routine_total() == pytest.approx(used, rel=0.2)

    # The weekly target the model chose follows the weather: in the cool
    # fortnight ~ET0(22-27C) x 7 x 0.8, in the hot one ~ET0(26-34C) x 7 x 0.8.
    def expected_weekly(t):
        return calc.hargreaves_et0(t[0], t[1], 9.5, 280) * 7 * 0.8

    cool = [r.target_weekly_used for r in sim.results[4:14] if r.routine_mm > 0]
    hot = [r.target_weekly_used for r in sim.results[18:] if r.routine_mm > 0]
    assert cool and hot
    assert all(t == pytest.approx(expected_weekly(COOL), rel=0.05) for t in cool)
    assert all(t == pytest.approx(expected_weekly(HOT), rel=0.05) for t in hot)
    assert expected_weekly(HOT) > expected_weekly(COOL) * 1.3


@pytest.mark.asyncio
async def test_temp_sensor_outage_mid_season_falls_back_and_recovers(hass, fake_valve_services, monkeypatch, tmp_path):
    c, sim = await _season(hass, monkeypatch, tmp_path, seed=HOT)
    c.store.state.demand_model = DEMAND_MODEL_ET
    weather = _days(8, HOT) + [Day("unavailable", "unavailable") for _ in range(8)] + _days(12, HOT)
    await sim.run(weather)
    _check_invariants(sim, c)

    # The first 3 outage days are recorded as "no reading" one by one; from
    # day 11 no real day is left and the fallback (unset -> normal tier)
    # takes over.
    during = [r for r in sim.results[11:16] if r.routine_mm > 0]
    after = [r for r in sim.results[19:] if r.routine_mm > 0]
    assert during, "zone must keep watering during a sensor outage"
    # Normal tier target (35 mm/week), 4-day interval: a dead sensor must
    # not keep the hot 3-day rhythm past its last real day.
    assert all(r.target_weekly_used == pytest.approx(35.0) for r in during)
    during_days = [r.index for r in sim.results[8:16] if r.routine_mm > 0]
    late = [d for d in during_days if d >= 11]
    assert all(b - a >= 4 for a, b in zip(late, late[1:]))
    # After it recovers (and has a fresh full day on record) it's back on the ET curve.
    assert after and all(r.target_weekly_used != pytest.approx(35.0) for r in after)


@pytest.mark.asyncio
async def test_a_young_plant_on_a_growth_ramp_gets_more_water_week_by_week(hass, fake_valve_services, monkeypatch, tmp_path):
    c, sim = await _season(hass, monkeypatch, tmp_path, growth_ramp_profile="fast_annual")
    c.store.state.planting_date_ts = sim.vdt.t.timestamp() - 2 * DAY  # planted 2 days before the season
    await sim.run(_days(52))  # fast-annual curve reaches 100% at day 45 after planting
    _check_invariants(sim, c)

    doses = [r.routine_mm for r in sim.results if r.routine_mm > 0]
    assert doses == sorted(doses), "doses should only ever grow as the plant ramps up"
    assert doses[0] < 0.7 * 20.0  # starts well below the full 20 mm dose
    assert doses[-1] == pytest.approx(20.0, abs=0.5)  # full dose once grown


@pytest.mark.asyncio
@pytest.mark.parametrize("seed", range(6))
async def test_sixty_days_of_random_weather_never_breaks_the_rules(hass, fake_valve_services, monkeypatch, tmp_path, seed):
    """Chaos run: random temperatures, showers, downpours and sensor
    dropouts. Doesn't check exact amounts -- checks the rules the model
    must never break, every single day."""
    import random

    rng = random.Random(seed)
    weather = []
    for _ in range(60):
        if rng.random() < 0.05:
            weather.append(Day("unavailable", "unavailable"))
            continue
        lo = rng.uniform(20, 27)
        d = Day(round(lo, 1), round(lo + rng.uniform(3, 10), 1))
        roll = rng.random()
        if roll < 0.08:
            d.rain = [(rng.choice([2, 10, 16, 22]), rng.uniform(36, 80))]  # downpour
        elif roll < 0.35:
            d.rain = [(rng.choice([1, 7, 15, 19]), rng.uniform(1, 15))]
        weather.append(d)

    c, sim = await _season(hass, monkeypatch, tmp_path)
    if seed % 2:
        c.store.state.demand_model = DEMAND_MODEL_ET
    await sim.run(weather)
    _check_invariants(sim, c)

    routine = sim.routine_days()
    deep = sim.deep_soak_days()
    assert all(b - a >= 3 for a, b in zip(routine, routine[1:])), "routine closer than the 3-day hot interval"
    assert all(b - a >= 14 for a, b in zip(deep, deep[1:])), "deep soak closer than its 14-day interval"

    # Never water inside the 4-day routine holdoff after a significant storm.
    storm_days = [r.index for r in sim.results if "Significant Rain" in r.events]
    for storm in storm_days:
        storm_hour = max(h for h, _ in weather[storm].rain)
        for day in routine:
            if day > storm or (day == storm and storm_hour < 5.5):
                hours_after = (day - storm) * 24 + (5.5 - storm_hour)
                assert hours_after >= 4 * 24 or hours_after < 0, f"watered {hours_after:.0f}h after a storm"

    # No dose is ever larger than the biggest the model can ask for
    # (hot tier 45 mm/week over 3 days, or ET at the hottest day in the run).
    et_cap = max(
        (calc.hargreaves_et0(d.t_min, d.t_max, 9.5, 280) or 0) for d in weather if isinstance(d.t_min, float)
    ) * 7 * 0.8 / 7 * 4
    biggest = max(45 / 7 * 3, 35 / 7 * 4, et_cap)
    assert all(0 <= r.routine_mm <= biggest + 1 for r in sim.results)
