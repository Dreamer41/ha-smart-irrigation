"""FAO-56 Penman-Monteith reference evapotranspiration (ET0), one day at a time (1.8).

Pure functions, no Home Assistant: the same style as calculations.py. Equation numbers refer
to Allen, Pereira, Raes and Smith (1998), "Crop evapotranspiration", FAO Irrigation and
Drainage Paper 56, chapters 3 and 4.

One equation is always used (eq. 6). An input that is not measured is estimated the way
chapter 3 prescribes for missing data, so a sensor that drops out changes only that input,
never the method:

  humidity  RHmax and RHmin (eq. 17), else RHmax only (eq. 18), else mean RH (eq. 19),
            else the dew point taken as Tmin - K0 (eq. 48)
  wind      measured, converted to 2 m (eq. 47), else a typical wind (2 m/s, chapter 3)
  solar     measured, else from the temperature range (Hargreaves, eq. 50)

Every result says where each input came from, so a person can see what to add for a better
estimate.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

SIGMA_MJ = 4.903e-9  # Stefan-Boltzmann constant, MJ K-4 m-2 day-1
ALBEDO = 0.23  # the hypothetical grass reference crop
DEFAULT_WIND_2M = 2.0  # m/s: FAO-56's global default when no wind data exist
MIN_WIND_2M = 0.5  # m/s: FAO-56 advises not to go below this (wind is never quite still at 2 m)
INDOOR_WIND_2M = MIN_WIND_2M  # under a roof: near still air
GLAZING_TRANSMISSION = 0.7  # typical share of sunshine through greenhouse glass or plastic
LUX_PER_W_M2 = 120.0  # daylight: about 120 lx per W/m2 of solar irradiance
KRS_INLAND = 0.16  # eq. 50 adjustment coefficient, interior locations
KRS_COASTAL = 0.19  # coastal locations
K0_HUMID = 0.0  # eq. 48: Tdew ~ Tmin in humid climates and where it is irrigated
K0_DRY = 2.0  # arid and semi-arid climates

SOURCE_MEASURED = "measured"
SOURCE_ESTIMATED = "estimated"
SOURCE_DEFAULT = "default"


@dataclass(frozen=True)
class DayInputs:
    """One completed day. Only the temperatures are required."""

    t_min: float  # deg C
    t_max: float  # deg C
    rh_min: float | None = None  # %
    rh_max: float | None = None  # %
    rh_mean: float | None = None  # %
    wind_2m: float | None = None  # m/s, already at 2 m (see wind_to_2m)
    rs_mj: float | None = None  # incoming solar radiation, MJ m-2 day-1


@dataclass(frozen=True)
class Et0Result:
    et0_mm: float
    sources: dict[str, str] = field(default_factory=dict)  # {"humidity": ..., "wind": ..., "solar": ...}
    rn_mj: float = 0.0
    ea_kpa: float = 0.0
    u2: float = 0.0
    rs_mj: float = 0.0


def sat_vapour_pressure(t: float) -> float:
    """e°(T), kPa (eq. 11)."""
    return 0.6108 * math.exp(17.27 * t / (t + 237.3))


def slope_vapour_pressure(t: float) -> float:
    """Δ, kPa / deg C (eq. 13)."""
    return 4098.0 * sat_vapour_pressure(t) / (t + 237.3) ** 2


def pressure_kpa(elevation_m: float) -> float:
    """Atmospheric pressure from elevation, kPa (eq. 7)."""
    return 101.3 * ((293.0 - 0.0065 * elevation_m) / 293.0) ** 5.26


def psychrometric_constant(pressure: float) -> float:
    """γ, kPa / deg C (eq. 8)."""
    return 0.000665 * pressure


def extraterrestrial_radiation_mj(latitude_deg: float, day_of_year: int) -> float:
    """Ra, MJ m-2 day-1 (eqs. 21-25)."""
    phi = math.radians(latitude_deg)
    angle = 2.0 * math.pi * day_of_year / 365.0
    dr = 1.0 + 0.033 * math.cos(angle)
    delta = 0.409 * math.sin(angle - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(delta))))
    ra = (24.0 * 60.0 / math.pi) * 0.0820 * dr * (
        ws * math.sin(phi) * math.sin(delta) + math.cos(phi) * math.cos(delta) * math.sin(ws)
    )
    return max(ra, 0.0)


def clear_sky_radiation_mj(ra_mj: float, elevation_m: float) -> float:
    """Rso, MJ m-2 day-1 (eq. 37)."""
    return (0.75 + 2e-5 * elevation_m) * ra_mj


def wind_to_2m(speed: float, height_m: float) -> float:
    """Wind measured at `height_m` brought to the 2 m standard (eq. 47). Heights below 0.5 m
    are taken as 0.5 m (the log profile is meaningless lower down)."""
    height = max(height_m, 0.5)
    return speed * 4.87 / math.log(67.8 * height - 5.42)


def actual_vapour_pressure(d: DayInputs, k0: float) -> tuple[float, str]:
    """ea, kPa, and where it came from."""
    es_min = sat_vapour_pressure(d.t_min)
    es_max = sat_vapour_pressure(d.t_max)
    if d.rh_min is not None and d.rh_max is not None:
        return (es_min * _pct(d.rh_max) + es_max * _pct(d.rh_min)) / 2.0, "rh_min_max"  # eq. 17
    if d.rh_max is not None:
        return es_min * _pct(d.rh_max), "rh_max"  # eq. 18
    if d.rh_mean is not None:
        return _pct(d.rh_mean) * (es_min + es_max) / 2.0, "rh_mean"  # eq. 19
    return sat_vapour_pressure(d.t_min - k0), SOURCE_ESTIMATED  # eq. 48


def _pct(value: float) -> float:
    return max(0.0, min(100.0, value)) / 100.0


def et0_daily(
    d: DayInputs,
    *,
    latitude_deg: float,
    day_of_year: int,
    elevation_m: float = 0.0,
    default_wind: float = DEFAULT_WIND_2M,
    k0: float = K0_HUMID,
    krs: float = KRS_INLAND,
    solar_factor: float = 1.0,
) -> Et0Result:
    """Daily ET0 (mm/day) with FAO-56 Penman-Monteith (eq. 6), soil heat flux G = 0 for a day.
    `solar_factor` scales estimated sunshine only (a measured reading under a roof is already
    what gets through)."""
    t_min, t_max = min(d.t_min, d.t_max), max(d.t_min, d.t_max)
    d = DayInputs(t_min, t_max, d.rh_min, d.rh_max, d.rh_mean, d.wind_2m, d.rs_mj)
    t_mean = (t_min + t_max) / 2.0
    es = (sat_vapour_pressure(t_max) + sat_vapour_pressure(t_min)) / 2.0
    ea, humidity_source = actual_vapour_pressure(d, k0)
    ea = min(ea, es)  # air cannot hold more than saturation

    if d.wind_2m is not None:
        u2, wind_source = max(d.wind_2m, 0.0), SOURCE_MEASURED
    else:
        u2, wind_source = default_wind, SOURCE_DEFAULT

    ra = extraterrestrial_radiation_mj(latitude_deg, day_of_year)
    rso = clear_sky_radiation_mj(ra, elevation_m)
    if d.rs_mj is not None:
        rs, solar_source = max(d.rs_mj, 0.0), SOURCE_MEASURED
    else:
        # eq. 50; `solar_factor` is the share that gets through glass or plastic under a roof
        rs, solar_source = min(krs * math.sqrt(t_max - t_min) * ra, rso) * solar_factor, SOURCE_ESTIMATED
    rns = (1.0 - ALBEDO) * rs  # eq. 38
    ratio = min(rs / rso, 1.0) if rso > 0 else 0.5  # polar night: no sun to compare with
    rnl = (
        SIGMA_MJ
        * ((t_max + 273.16) ** 4 + (t_min + 273.16) ** 4) / 2.0
        * (0.34 - 0.14 * math.sqrt(max(ea, 0.0)))
        * (1.35 * ratio - 0.35)
    )  # eq. 39
    rn = rns - rnl  # eq. 40

    delta = slope_vapour_pressure(t_mean)
    gamma = psychrometric_constant(pressure_kpa(elevation_m))
    numerator = 0.408 * delta * rn + gamma * (900.0 / (t_mean + 273.0)) * u2 * (es - ea)
    et0 = numerator / (delta + gamma * (1.0 + 0.34 * u2))
    return Et0Result(
        et0_mm=max(et0, 0.0),
        sources={"humidity": humidity_source, "wind": wind_source, "solar": solar_source},
        rn_mj=rn,
        ea_kpa=ea,
        u2=u2,
        rs_mj=rs,
    )


@dataclass(frozen=True)
class KcStages:
    """A crop's FAO-56 crop coefficient curve (Table 12 values, Table 11 stage lengths)."""

    kc_ini: float
    kc_mid: float
    kc_end: float
    l_ini: float  # days
    l_dev: float
    l_mid: float
    l_late: float


def kc_on_day(stages: KcStages, days_since_planting: float) -> float:
    """Kc on a day of the season: flat in the initial and mid stages, straight lines between
    (eq. 66). Before planting the initial value, after the season the end value."""
    s = stages
    day = max(days_since_planting, 0.0)
    if day <= s.l_ini:
        return s.kc_ini
    day -= s.l_ini
    if day <= s.l_dev:
        return s.kc_ini + (s.kc_mid - s.kc_ini) * (day / s.l_dev if s.l_dev > 0 else 1.0)
    day -= s.l_dev
    if day <= s.l_mid:
        return s.kc_mid
    day -= s.l_mid
    if day <= s.l_late:
        return s.kc_mid + (s.kc_end - s.kc_mid) * (day / s.l_late if s.l_late > 0 else 1.0)
    return s.kc_end
