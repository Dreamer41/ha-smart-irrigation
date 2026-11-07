"""Crop seasons for the seasonal crop factor (1.8): the FAO-56 stages, rooting depth and allowed
depletion per crop, from data/crop_kc.json (scripts/build_crop_kc.py)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from homeassistant.core import HomeAssistant

from .fao56 import SEASON_ANNUAL, SEASON_FLAT, SEASON_PERENNIAL, KcStages

_LOGGER = logging.getLogger(__name__)
_KEY = "zoneflow_crop_seasons"  # not under hass.data[DOMAIN]: unloading tests whether that dict is empty
KC_FILE = Path(__file__).parent / "data" / "crop_kc.json"


@dataclass(frozen=True)
class CropSeason:
    crop_id: str
    name: str
    season: str  # fao56.SEASON_*
    stages: KcStages | None  # None for a flat crop
    kc_flat: float  # kc_mid: used for a flat crop and as the fallback
    root_min_m: float | None
    root_max_m: float | None
    p: float | None
    height_m: float | None
    season_source: str


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _crop(row: dict) -> CropSeason | None:
    kc_mid = _number(row.get("kc_mid"))
    if kc_mid is None or kc_mid <= 0:
        return None
    season = row.get("season")
    stages = None
    if season in (SEASON_ANNUAL, SEASON_PERENNIAL):
        lengths = [_number(row.get(k)) for k in ("l_ini", "l_dev", "l_mid", "l_late")]
        if any(v is None or v < 0 for v in lengths) or sum(lengths) <= 0:
            return None
        kc_ini = _number(row.get("kc_ini"))
        kc_end = _number(row.get("kc_end"))
        stages = KcStages(kc_ini if kc_ini is not None else kc_mid, kc_mid, kc_end if kc_end is not None else kc_mid, *lengths)
    elif season != SEASON_FLAT:
        return None
    return CropSeason(
        crop_id=str(row["id"]), name=str(row.get("name", row["id"])), season=season, stages=stages, kc_flat=kc_mid,
        root_min_m=_number(row.get("root_min_m")), root_max_m=_number(row.get("root_max_m")),
        p=_number(row.get("p")), height_m=_number(row.get("height_m")), season_source=str(row.get("season_source", "")),
    )


def read(path: Path = KC_FILE) -> dict[str, CropSeason]:
    """Every usable crop of the table by id. A row that can't be used is skipped with a warning."""
    try:
        with open(path, encoding="utf-8") as handle:
            rows = json.load(handle).get("crops", [])
    except (OSError, ValueError, AttributeError):
        _LOGGER.warning("The crop table could not be read: zones water with the fixed crop factor")
        return {}
    crops: dict[str, CropSeason] = {}
    for row in rows:
        try:
            crop = _crop(row)
        except (KeyError, TypeError, AttributeError):
            crop = None
        if crop is None:
            _LOGGER.warning("Skipped a crop row that can't be used: %s", row.get("id") if isinstance(row, dict) else row)
            continue
        crops[crop.crop_id] = crop
    return crops


async def async_crop_seasons(hass: HomeAssistant) -> dict[str, CropSeason]:
    cached = hass.data.get(_KEY)
    if cached is None:
        cached = hass.data[_KEY] = await hass.async_add_executor_job(read)
    return cached
