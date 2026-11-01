"""1.8: the FAO-56 climate sensors and site options in the zone and area forms, and what an
input without a sensor falls back on."""
from __future__ import annotations

import json
import os
from datetime import timedelta

import homeassistant.util.dt as dt_util
import pytest

from custom_components.zoneflow import config_flow
from custom_components.zoneflow.const import (
    CONF_CLIMATE_DRYNESS,
    CONF_COASTAL,
    CONF_HUMIDITY_ENTITY,
    CONF_SOLAR_ENTITY,
    CONF_WIND_ENTITY,
    CONF_WIND_EXPOSURE,
    CONF_WIND_SENSOR_HEIGHT_M,
    DOMAIN,
)

from .test_smoke_setup import _seed_source_entities, make_entry

SENSORS = (CONF_HUMIDITY_ENTITY, CONF_WIND_ENTITY, CONF_SOLAR_ENTITY)
SITE = (CONF_WIND_EXPOSURE, CONF_CLIMATE_DRYNESS, CONF_COASTAL, CONF_WIND_SENSOR_HEIGHT_M)
TRANSLATIONS = os.path.join(os.path.dirname(__file__), "..", "custom_components", "zoneflow", "translations")


def _keys(schema) -> set[str]:
    return {str(k) for k in schema.schema}


def test_the_zone_form_asks_for_the_sensors_and_the_site_and_the_area_form_for_the_sensors():
    zone = _keys(config_flow._schema({}))
    area = _keys(config_flow._area_schema({}))
    assert set(SENSORS) <= zone and set(SITE) <= zone
    assert set(SENSORS) <= area and not set(SITE) & area


def test_the_site_options_have_safe_defaults():
    schema = config_flow._schema({})
    defaults = {str(k): k.default() for k in schema.schema if hasattr(k, "default") and callable(k.default)}
    assert defaults[CONF_WIND_EXPOSURE] == "open" and defaults[CONF_CLIMATE_DRYNESS] == "humid"
    assert defaults[CONF_COASTAL] is False and defaults[CONF_WIND_SENSOR_HEIGHT_M] == 2.0


async def _zone(hass, **options):
    await _seed_source_entities(hass)
    entry = make_entry(hass, **options)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


@pytest.mark.asyncio
async def test_an_old_zone_without_the_options_uses_the_fao56_defaults(hass):
    c = await _zone(hass)
    assert c._fao56_settings() == {"default_wind": 2.0, "k0": 0.0, "krs": 0.16, "wind_height_m": 2.0, "solar_factor": 1.0}


@pytest.mark.asyncio
async def test_the_site_options_change_the_fallbacks_and_the_estimate(hass):
    c = await _zone(hass, **{CONF_WIND_EXPOSURE: "exposed", CONF_CLIMATE_DRYNESS: "dry", CONF_COASTAL: True, CONF_WIND_SENSOR_HEIGHT_M: 10})
    assert c._fao56_settings() == {"default_wind": 3.5, "k0": 2.0, "krs": 0.19, "wind_height_m": 10.0, "solar_factor": 1.0}
    s = c.store.state
    s.today_min_temp_c, s.today_peak_temp_c = 14.0, 27.0
    day = dt_util.now().date() - timedelta(days=1)
    c._close_et0_day(day, dt_util.utcnow().timestamp())
    exposed = s.et0_day_history[0]
    assert exposed["u2"] == 3.5 and exposed["sources"]["wind"] == "default"

    plain = await _zone(hass)
    ps = plain.store.state
    ps.today_min_temp_c, ps.today_peak_temp_c = 14.0, 27.0
    plain._close_et0_day(day, dt_util.utcnow().timestamp())
    assert exposed["et0"] > ps.et0_day_history[0]["et0"]  # windier, drier, sunnier: more water


@pytest.mark.asyncio
async def test_a_bad_saved_height_falls_back_to_two_metres(hass):
    c = await _zone(hass, **{CONF_WIND_SENSOR_HEIGHT_M: "high"})
    assert c._fao56_settings()["wind_height_m"] == 2.0


@pytest.mark.parametrize("name", sorted(f for f in os.listdir(TRANSLATIONS) if f.endswith(".json")))
def test_every_language_labels_the_new_fields(name):
    data = json.load(open(os.path.join(TRANSLATIONS, name), encoding="utf-8"))
    for section, step in (("config", "entities"), ("options", "settings")):
        st = data[section]["step"][step]
        for key in (*SENSORS, *SITE):
            assert st["data"][key] and st["data_description"][key], (name, step, key)
    for section, step in (("config", "area"), ("options", "new_area"), ("options", "area_settings")):
        for key in SENSORS:
            assert data[section]["step"][step]["data"][key], (name, step, key)
    for key in SENSORS:
        assert data["options"]["step"]["location_sensors"]["data"][key]
    assert set(data["selector"]["wind_exposure"]["options"]) == {"sheltered", "open", "exposed"}
    assert set(data["selector"]["climate_dryness"]["options"]) == {"humid", "dry"}
