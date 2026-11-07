"""FAO-56 Penman-Monteith (1.8): the worked example from the paper, every fallback combination,
and the crop coefficient curve."""
from __future__ import annotations

import itertools
import math

import pytest

from custom_components.zoneflow import calculations as calc
from custom_components.zoneflow import fao56
from custom_components.zoneflow.fao56 import DayInputs, KcStages


def _brussels_rs() -> tuple[float, float]:
    """Example 18's solar radiation from 9.25 hours of sunshine (eqs. 34-35), and Ra."""
    lat, doy = 50.8, 187
    ra = fao56.extraterrestrial_radiation_mj(lat, doy)
    phi = math.radians(lat)
    delta = 0.409 * math.sin(2 * math.pi * doy / 365 - 1.39)
    ws = math.acos(-math.tan(phi) * math.tan(delta))
    daylight = 24 / math.pi * ws
    return (0.25 + 0.50 * 9.25 / daylight) * ra, ra


def test_example_18_brussels_6_july():
    """FAO-56 Example 18: Uccle (Brussels), 6 July, 50°48'N, 100 m. Published: ET0 3.9 mm/day,
    with u2 2.078 m/s, ea 1.409 kPa, Ra 41.09, Rs 22.07, Rn 13.28 MJ m-2 day-1."""
    rs, ra = _brussels_rs()
    u2 = fao56.wind_to_2m(10 / 3.6, 10.0)  # 10 km/h measured at 10 m
    d = DayInputs(t_min=12.3, t_max=21.5, rh_min=63, rh_max=84, wind_2m=u2, rs_mj=rs)
    r = fao56.et0_daily(d, latitude_deg=50.8, day_of_year=187, elevation_m=100)
    assert u2 == pytest.approx(2.078, abs=0.005)
    assert ra == pytest.approx(41.09, abs=0.05)
    assert rs == pytest.approx(22.07, abs=0.05)
    assert r.ea_kpa == pytest.approx(1.409, abs=0.003)
    assert r.rn_mj == pytest.approx(13.28, abs=0.05)
    assert fao56.pressure_kpa(100) == pytest.approx(100.1, abs=0.05)
    assert fao56.slope_vapour_pressure(16.9) == pytest.approx(0.122, abs=0.001)
    assert r.et0_mm == pytest.approx(3.9, abs=0.05)
    assert r.sources == {"humidity": "rh_min_max", "wind": "measured", "solar": "measured"}


def test_the_ra_here_matches_the_ra_the_zone_already_uses():
    for lat, doy in ((50.8, 187), (13.7, 100), (-33.9, 15), (60.0, 355)):
        assert fao56.extraterrestrial_radiation_mj(lat, doy) * 0.408 == pytest.approx(
            calc.extraterrestrial_radiation_mm(lat, doy), rel=0.01
        )


@pytest.mark.parametrize("has_rh,has_wind,has_solar", list(itertools.product([False, True], repeat=3)))
def test_every_combination_of_missing_inputs_gives_an_answer_and_says_where_it_came_from(has_rh, has_wind, has_solar):
    rs, _ = _brussels_rs()
    d = DayInputs(
        t_min=12.3, t_max=21.5,
        rh_min=63 if has_rh else None, rh_max=84 if has_rh else None,
        wind_2m=2.078 if has_wind else None,
        rs_mj=rs if has_solar else None,
    )
    r = fao56.et0_daily(d, latitude_deg=50.8, day_of_year=187, elevation_m=100)
    assert 1.5 < r.et0_mm < 6.0
    assert r.sources["humidity"] == ("rh_min_max" if has_rh else "estimated")
    assert r.sources["wind"] == ("measured" if has_wind else "default")
    assert r.sources["solar"] == ("measured" if has_solar else "estimated")


def test_humidity_falls_back_through_rhmax_then_mean_then_tmin():
    base = dict(t_min=12.3, t_max=21.5)
    assert fao56.actual_vapour_pressure(DayInputs(**base, rh_max=84), 0.0)[1] == "rh_max"
    assert fao56.actual_vapour_pressure(DayInputs(**base, rh_mean=73.5), 0.0)[1] == "rh_mean"
    ea_humid, src = fao56.actual_vapour_pressure(DayInputs(**base), fao56.K0_HUMID)
    ea_dry, _ = fao56.actual_vapour_pressure(DayInputs(**base), fao56.K0_DRY)
    assert src == "estimated" and ea_dry < ea_humid  # a dry climate: lower dew point, drier air


def test_drier_windier_sunnier_days_need_more_water():
    rs, _ = _brussels_rs()
    calm = fao56.et0_daily(DayInputs(12.3, 21.5, rh_min=63, rh_max=84, wind_2m=1.0, rs_mj=rs), latitude_deg=50.8, day_of_year=187)
    windy = fao56.et0_daily(DayInputs(12.3, 21.5, rh_min=63, rh_max=84, wind_2m=5.0, rs_mj=rs), latitude_deg=50.8, day_of_year=187)
    dry = fao56.et0_daily(DayInputs(12.3, 21.5, rh_min=25, rh_max=50, wind_2m=1.0, rs_mj=rs), latitude_deg=50.8, day_of_year=187)
    cloudy = fao56.et0_daily(DayInputs(12.3, 21.5, rh_min=63, rh_max=84, wind_2m=1.0, rs_mj=rs / 3), latitude_deg=50.8, day_of_year=187)
    assert windy.et0_mm > calm.et0_mm and dry.et0_mm > calm.et0_mm and cloudy.et0_mm < calm.et0_mm


@pytest.mark.parametrize("t_min,t_max,lat,doy", [(12.3, 21.5, 50.8, 187), (25.6, 34.8, 13.7, 105), (5.0, 18.0, 40.0, 100), (18.0, 32.0, -30.0, 15)])
def test_with_temperature_only_it_stays_close_to_hargreaves(t_min, t_max, lat, doy):
    """FAO-56 chapter 3: Penman-Monteith with estimated inputs is about what Hargreaves gives."""
    pm = fao56.et0_daily(DayInputs(t_min, t_max), latitude_deg=lat, day_of_year=doy).et0_mm
    hg = calc.hargreaves_et0(t_min, t_max, lat, doy)
    assert pm == pytest.approx(hg, rel=0.25)


def test_odd_inputs_do_not_break_it():
    swapped = fao56.et0_daily(DayInputs(21.5, 12.3), latitude_deg=50.8, day_of_year=187)
    normal = fao56.et0_daily(DayInputs(12.3, 21.5), latitude_deg=50.8, day_of_year=187)
    assert swapped.et0_mm == pytest.approx(normal.et0_mm)
    flat = fao56.et0_daily(DayInputs(15.0, 15.0), latitude_deg=50.8, day_of_year=187)
    assert flat.et0_mm >= 0.0
    polar = fao56.et0_daily(DayInputs(-20.0, -12.0), latitude_deg=78.0, day_of_year=355)
    assert polar.et0_mm >= 0.0 and polar.sources["solar"] == "estimated"
    soaked = fao56.et0_daily(DayInputs(12.3, 21.5, rh_min=120, rh_max=150), latitude_deg=50.8, day_of_year=187)
    assert soaked.et0_mm >= 0.0
    assert fao56.wind_to_2m(3.0, 0.1) == pytest.approx(fao56.wind_to_2m(3.0, 0.5))
    assert fao56.wind_to_2m(3.0, 2.0) == pytest.approx(3.0, rel=0.01)


def test_kc_follows_the_stage_curve():
    tomato = KcStages(kc_ini=0.6, kc_mid=1.15, kc_end=0.8, l_ini=30, l_dev=40, l_mid=40, l_late=25)
    assert fao56.kc_on_day(tomato, -5) == 0.6
    assert fao56.kc_on_day(tomato, 10) == 0.6
    assert fao56.kc_on_day(tomato, 50) == pytest.approx(0.6 + 0.55 * 0.5)
    assert fao56.kc_on_day(tomato, 90) == 1.15
    assert fao56.kc_on_day(tomato, 110 + 12.5) == pytest.approx(1.15 - 0.35 * 0.5)
    assert fao56.kc_on_day(tomato, 400) == 0.8
    instant = KcStages(0.5, 1.0, 0.7, 0, 0, 10, 0)
    assert fao56.kc_on_day(instant, 5) == 1.0 and fao56.kc_on_day(instant, 11) == 0.7


def test_estimated_sunshine_under_glass_is_less():
    d = DayInputs(14.0, 30.0)
    open_air = fao56.et0_daily(d, latitude_deg=13.7, day_of_year=100)
    glass = fao56.et0_daily(d, latitude_deg=13.7, day_of_year=100, solar_factor=fao56.GLAZING_TRANSMISSION)
    assert glass.rs_mj == pytest.approx(open_air.rs_mj * 0.7) and glass.et0_mm < open_air.et0_mm
    measured = DayInputs(14.0, 30.0, rs_mj=15.0)
    a = fao56.et0_daily(measured, latitude_deg=13.7, day_of_year=100)
    b = fao56.et0_daily(measured, latitude_deg=13.7, day_of_year=100, solar_factor=0.7)
    assert a.et0_mm == b.et0_mm  # a reading under the roof is what gets through already
