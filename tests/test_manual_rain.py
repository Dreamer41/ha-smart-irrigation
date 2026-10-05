"""Manual rain (1.6.1): rain read by hand from a simple gauge, entered with
the Manual Rain number + Add Manual Rain button or the zoneflow.add_rain
service. For outdoor zones without a rain gauge; with a gauge, the higher
of the two counts, never the sum.
"""
from __future__ import annotations

from datetime import timedelta

import homeassistant.util.dt as dt_util
import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.zoneflow.const import CONF_RAIN_COUNTER_ENTITY, DOMAIN, SIGNIFICANT_RAIN_24H_MM

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

HIDDEN_BY_ZONEFLOW = er.RegistryEntryHider.INTEGRATION


async def _setup(hass, **overrides):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "25.0")
    await hass.async_block_till_done()
    entry = make_entry(hass, **overrides)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, hass.data[DOMAIN][entry.entry_id]


def _reg(hass, entry, domain, key):
    registry = er.async_get(hass)
    return next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == domain and e.translation_key == key
    )


async def _set_number(hass, entry, key, value):
    await hass.services.async_call(
        "number", "set_value", {"entity_id": _reg(hass, entry, "number", key).entity_id, "value": value}, blocking=True
    )


async def _press(hass, entry, key):
    await hass.services.async_call(
        "button", "press", {"entity_id": _reg(hass, entry, "button", key).entity_id}, blocking=True
    )


@pytest.mark.asyncio
async def test_button_adds_the_number_and_resets_it(hass, fake_valve_services):
    entry, controller = await _setup(hass, **{CONF_RAIN_COUNTER_ENTITY: None})
    assert _reg(hass, entry, "number", "manual_rain_mm").hidden_by is None
    assert _reg(hass, entry, "button", "add_manual_rain").hidden_by is None
    # No rain entered yet: the rain sensors stay hidden as before.
    assert _reg(hass, entry, "sensor", "rain_today").hidden_by == HIDDEN_BY_ZONEFLOW

    await _set_number(hass, entry, "manual_rain_mm", 6.5)
    await _press(hass, entry, "add_manual_rain")
    await hass.async_block_till_done()

    assert controller.today_rain_mm() == pytest.approx(6.5)
    windows = controller.rain_windows()
    assert windows["24h"] == pytest.approx(6.5)
    assert windows["7d"] == pytest.approx(6.5)
    # Entered after the fact: never a "raining now" reading.
    assert windows["30min"] == 0.0
    assert controller.number("manual_rain_mm") == 0.0
    # Now the rain sensors are worth showing -- not the gauge's own ones.
    assert _reg(hass, entry, "sensor", "rain_today").hidden_by is None
    assert _reg(hass, entry, "sensor", "rain_past_7d").hidden_by is None
    assert _reg(hass, entry, "number", "rain_mm_per_tip").hidden_by == HIDDEN_BY_ZONEFLOW
    assert _reg(hass, entry, "sensor", "rain_past_30min").hidden_by == HIDDEN_BY_ZONEFLOW


@pytest.mark.asyncio
async def test_button_with_zero_is_refused(hass, fake_valve_services):
    entry, controller = await _setup(hass, **{CONF_RAIN_COUNTER_ENTITY: None})
    with pytest.raises(ServiceValidationError):
        await _press(hass, entry, "add_manual_rain")
    assert controller.today_rain_mm() == 0.0


@pytest.mark.asyncio
async def test_hidden_on_a_zone_with_a_gauge_and_never_counted_twice(hass, fake_valve_services):
    entry, controller = await _setup(hass)
    assert _reg(hass, entry, "number", "manual_rain_mm").hidden_by == HIDDEN_BY_ZONEFLOW
    assert _reg(hass, entry, "button", "add_manual_rain").hidden_by == HIDDEN_BY_ZONEFLOW

    hass.states.async_set(RAIN_COUNTER, "10")  # 10 tips x 0.3 mm = 3 mm
    await hass.async_block_till_done()
    assert controller.today_rain_mm() == pytest.approx(3.0)

    await hass.services.async_call(DOMAIN, "add_rain", {"amount": 8.0}, blocking=True)
    assert controller.today_rain_mm() == pytest.approx(8.0)  # the higher, not 11
    assert controller.rain_windows()["24h"] == pytest.approx(8.0)

    await hass.services.async_call(DOMAIN, "add_rain", {"amount": 1.0}, blocking=True)
    hass.states.async_set(RAIN_COUNTER, "40")  # the gauge now says 12 mm
    await hass.async_block_till_done()
    assert controller.today_rain_mm() == pytest.approx(12.0)


@pytest.mark.asyncio
async def test_service_for_an_earlier_day_updates_that_days_rain_credit(hass, fake_valve_services):
    _entry, controller = await _setup(hass, **{CONF_RAIN_COUNTER_ENTITY: None})
    three_days_ago = dt_util.now() - timedelta(days=3)
    await hass.services.async_call(
        DOMAIN, "add_rain", {"amount": 12.0, "when": three_days_ago.isoformat()}, blocking=True
    )
    history = controller.store.state.rain_day_history_mm
    assert history[2] == pytest.approx(12.0)  # [0] is yesterday
    assert history[0] == 0.0 and history[1] == 0.0
    assert controller.today_rain_mm() == 0.0
    assert controller.rain_windows()["4d"] == pytest.approx(12.0)
    assert controller.rain_windows()["24h"] == 0.0


@pytest.mark.asyncio
async def test_service_refuses_future_and_too_old(hass, fake_valve_services):
    _entry, controller = await _setup(hass, **{CONF_RAIN_COUNTER_ENTITY: None})
    for when in (dt_util.now() + timedelta(hours=2), dt_util.now() - timedelta(days=15)):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN, "add_rain", {"amount": 5.0, "when": when.isoformat()}, blocking=True
            )
    assert controller.store.state.manual_rain_samples == []


@pytest.mark.asyncio
async def test_heavy_manual_rain_restarts_the_dry_down(hass, fake_valve_services):
    _entry, controller = await _setup(hass, **{CONF_RAIN_COUNTER_ENTITY: None})
    controller.store.state.last_significant_rain_ts = 0.0
    await hass.services.async_call(DOMAIN, "add_rain", {"amount": SIGNIFICANT_RAIN_24H_MM + 5}, blocking=True)
    assert controller.store.state.last_significant_rain_ts > 0.0


@pytest.mark.asyncio
async def test_manual_rain_survives_a_restart(hass, fake_valve_services):
    entry, controller = await _setup(hass, **{CONF_RAIN_COUNTER_ENTITY: None})
    await hass.services.async_call(DOMAIN, "add_rain", {"amount": 4.0}, blocking=True)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    assert controller.today_rain_mm() == pytest.approx(4.0)


@pytest.mark.asyncio
async def test_a_non_finite_amount_is_refused(hass, fake_valve_services):
    from homeassistant.exceptions import ServiceValidationError

    _entry, controller = await _setup(hass, **{CONF_RAIN_COUNTER_ENTITY: None})
    for bad in (float("nan"), float("inf")):
        with pytest.raises(ServiceValidationError):
            await controller.add_manual_rain(bad)
    assert controller.store.state.manual_rain_samples == []
