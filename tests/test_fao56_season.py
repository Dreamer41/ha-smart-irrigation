"""1.8: FAO-56 over a simulated month (season_sim drives every hour of every day through the
real zone): each routine watering gives the evaporation of the days since the last watering,
rain is still credited, and the site options move the amount the way they should."""
from __future__ import annotations

import pytest

from custom_components.zoneflow.const import CONF_CLIMATE_DRYNESS, CONF_WIND_EXPOSURE, DEMAND_MODEL_FAO56

from .test_season_scenarios import HOT, NORMAL, _check_invariants, _days, _season


async def _fao56_season(hass, monkeypatch, tmp_path, seed=NORMAL, **entry):
    c, sim = await _season(hass, monkeypatch, tmp_path, seed=seed, **entry)
    c.store.state.demand_model = DEMAND_MODEL_FAO56
    c.store.state.et0_day_history = []
    return c, sim


def _daily_need(c) -> float:
    """What one day of this steady weather needs, as the zone waters it."""
    et0 = [e["et0"] for e in c.store.state.et0_day_history if e.get("et0") is not None]
    assert et0, "no FAO-56 day was closed"
    mean = sum(et0) / len(et0)
    assert max(et0) - min(et0) < 0.05 * mean  # the same weather every day: ET0 moves only with the season's sun
    return mean * c.number("crop_coefficient") * c.routine_target_scale()


@pytest.mark.asyncio
async def test_a_dry_month_waters_the_evaporation_of_each_interval(hass, fake_valve_services, monkeypatch, tmp_path):
    c, sim = await _fao56_season(hass, monkeypatch, tmp_path)
    await sim.run(_days(28))
    _check_invariants(sim, c)
    daily = _daily_need(c)
    runs = [r for r in sim.results if r.routine_mm > 0]
    assert len(runs) >= 4
    for run in runs:
        # FAO-56 gives each routine run the days since the last watering (here 4, the
        # interval) of that day's evaporation; the first run still had no FAO-56 day before
        # day 0 closed, so it is not checked against it.
        if run.index >= 4:
            assert run.routine_mm == pytest.approx(daily * 4, rel=0.05), run.index
    assert len(c.store.state.et0_day_history) == 14  # two weeks kept


@pytest.mark.asyncio
async def test_a_hot_month_needs_more_than_a_normal_one(hass, fake_valve_services, monkeypatch, tmp_path):
    c, sim = await _fao56_season(hass, monkeypatch, tmp_path)
    await sim.run(_days(10))
    normal = _daily_need(c)
    c2, sim2 = await _fao56_season(hass, monkeypatch, tmp_path, seed=HOT)
    await sim2.run(_days(10, HOT))
    assert _daily_need(c2) > normal


@pytest.mark.asyncio
async def test_rain_is_credited_against_the_evaporation(hass, fake_valve_services, monkeypatch, tmp_path):
    c, sim = await _fao56_season(hass, monkeypatch, tmp_path)
    await sim.run(_days(16, d9=[(15.0, 8.0)]))  # 8 mm in the afternoon of day 9
    _check_invariants(sim, c)
    daily = _daily_need(c)
    after_rain = [r for r in sim.results if r.routine_mm > 0 and 9 < r.index <= 13]
    assert after_rain and after_rain[0].routine_mm < daily * 4 - 1.0  # less than a dry interval


@pytest.mark.asyncio
async def test_a_dry_exposed_site_needs_more_than_a_humid_sheltered_one(hass, fake_valve_services, monkeypatch, tmp_path):
    c, sim = await _fao56_season(hass, monkeypatch, tmp_path, **{CONF_CLIMATE_DRYNESS: "humid", CONF_WIND_EXPOSURE: "sheltered"})
    await sim.run(_days(6))
    calm = _daily_need(c)
    c2, sim2 = await _fao56_season(hass, monkeypatch, tmp_path, **{CONF_CLIMATE_DRYNESS: "dry", CONF_WIND_EXPOSURE: "exposed"})
    await sim2.run(_days(6))
    assert _daily_need(c2) > calm * 1.2
