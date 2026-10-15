"""The rain that starts the dry-down holdoffs is a setting (1.7.3): the Dry-Down
Rain Threshold for 24 hours, 4 days and 7 days, starting at 35, 50 and 100 mm
as before."""
from __future__ import annotations

import pytest

from custom_components.zoneflow import presets, units, visibility
from custom_components.zoneflow.const import (
    DOMAIN,
    NUMBER_DEFAULTS,
    SIGNIFICANT_RAIN_4D_MM,
    SIGNIFICANT_RAIN_7D_MM,
    SIGNIFICANT_RAIN_24H_MM,
)

from .test_smoke_setup import RAIN_COUNTER, _seed_source_entities, make_entry

KEYS = ("drydown_rain_24h_mm", "drydown_rain_4d_mm", "drydown_rain_7d_mm")


async def _zone(hass):
    await _seed_source_entities(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


def test_they_start_where_the_fixed_values_were():
    assert [NUMBER_DEFAULTS[k] for k in KEYS] == [SIGNIFICANT_RAIN_24H_MM, SIGNIFICANT_RAIN_4D_MM, SIGNIFICANT_RAIN_7D_MM]
    assert (SIGNIFICANT_RAIN_24H_MM, SIGNIFICANT_RAIN_4D_MM, SIGNIFICANT_RAIN_7D_MM) == (35.0, 50.0, 100.0)


@pytest.mark.asyncio
async def test_a_higher_24h_threshold_leaves_the_same_rain_out(hass):
    c = await _zone(hass)
    await c.numbers["drydown_rain_24h_mm"].async_set_metric_value(60.0)
    hass.states.async_set(RAIN_COUNTER, "150")  # 45 mm in 24 h: heavy at 35 mm, not at 60 mm
    await hass.async_block_till_done()
    assert c.store.state.last_significant_rain_ts is None


@pytest.mark.asyncio
async def test_a_lower_24h_threshold_starts_the_dry_down_sooner(hass):
    c = await _zone(hass)
    await c.numbers["drydown_rain_24h_mm"].async_set_metric_value(20.0)
    hass.states.async_set(RAIN_COUNTER, "80")  # 24 mm: under the old 35 mm, over the new 20 mm
    await hass.async_block_till_done()
    assert c.store.state.last_significant_rain_ts is not None


@pytest.mark.asyncio
async def test_the_4_day_and_7_day_thresholds_are_read_too(hass):
    c = await _zone(hass)
    for key in KEYS:
        await c.numbers[key].async_set_metric_value(500.0 if key != "drydown_rain_4d_mm" else 20.0)
    await c.numbers["drydown_rain_24h_mm"].async_set_metric_value(200.0)
    hass.states.async_set(RAIN_COUNTER, "80")  # 24 mm: only the lowered 4-day line is crossed
    await hass.async_block_till_done()
    assert c.store.state.last_significant_rain_ts is not None


def test_they_show_in_inches_and_are_copied_with_a_zones_settings():
    for key in KEYS:
        assert key in units.DEPTH_KEYS
        assert key in presets.COPY_NUMBER_KEYS


@pytest.mark.asyncio
async def test_they_are_shown_where_rain_is_measured(hass):
    c = await _zone(hass)  # has a rain gauge
    hidden = visibility.hidden_for(c)
    assert not any(("number", key) in hidden for key in KEYS)


@pytest.mark.asyncio
async def test_the_three_thresholds_are_all_sliders_on_the_card(hass):
    from homeassistant.components.number import NumberMode

    controller = await _zone(hass)
    for key in ("drydown_rain_24h_mm", "drydown_rain_4d_mm", "drydown_rain_7d_mm"):
        assert controller.numbers[key].mode is NumberMode.SLIDER
    assert controller.numbers["target_weekly_mm"].mode is NumberMode.AUTO
