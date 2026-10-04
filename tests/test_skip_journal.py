"""Skip journal (1.6.1): every watering skipped for forecast rain is judged
48 hours later against the rain that really fell, and the Forecast Skip Hit
Rate sensor shows how often the skips paid off."""
from __future__ import annotations

import pytest
import homeassistant.util.dt as dt_util
from homeassistant.helpers import entity_registry as er

from custom_components.zoneflow import calculations as calc
from custom_components.zoneflow.const import CONF_RAIN_COUNTER_ENTITY, DOMAIN

from .test_forecast_gate import _make_zone, _register_forecast_service, _seed

HOUR = 3600.0


def test_paid_off_needs_the_forecast_amount_or_the_threshold():
    assert calc.skip_paid_off(5.0, 4.0, 3.0)  # rain at least the threshold
    assert calc.skip_paid_off(3.0, 10.0, 3.0)  # big forecast: the threshold is enough
    assert calc.skip_paid_off(0.8, 1.0, 3.0) is False  # light forecast, a bit less fell
    assert calc.skip_paid_off(1.0, 1.0, 3.0)
    assert calc.skip_paid_off(0.0, 0.0, 3.0) is False  # no rain never pays off


def test_hit_rate_counts_only_judged_entries_of_the_last_30_days():
    now = 100 * 86400.0
    entries = [
        {"ts": now - 5 * 86400, "paid_off": True},
        {"ts": now - 6 * 86400, "paid_off": False},
        {"ts": now - 7 * 86400, "paid_off": None},  # no rain data
        {"ts": now - 40 * 86400, "paid_off": True},  # too old
    ]
    assert calc.skip_hit_rate(entries, now) == (1, 2)
    assert calc.skip_hit_rate([], now) == (0, 0)


@pytest.mark.asyncio
async def test_a_forecast_skip_is_journaled_and_judged_after_48_hours(hass, fake_valve_services):
    await _seed(hass)
    _register_forecast_service(hass, precipitation=10.0)
    controller = await _make_zone(hass)

    assert await controller._forecast_gate_allows_run("routine") is False
    journal = controller.store.state.forecast_skip_journal
    assert len(journal) == 1
    assert journal[0]["cycle"] == "routine" and journal[0]["forecast_mm"] == 10.0
    assert journal[0]["paid_off"] is None

    # Rain on the gauge (10 tips x 0.3 mm = 3 mm) 10 hours after the skip,
    # then two days pass.
    skipped = journal[0]["ts"]
    tracker = controller.store.state.rain_tracker()
    tracker.record(skipped - HOUR, 0.0)
    tracker.record(skipped + 10 * HOUR, 3.0)
    controller.store.state.save_rain_tracker(tracker)
    assert controller.judge_skip_journal() is False  # not 48 h yet

    journal[0]["ts"] = skipped - 49 * HOUR
    tracker = controller.store.state.rain_tracker()
    controller.store.state.rain_samples = [[t - 49 * HOUR, c] for t, c in tracker.samples]
    assert controller.judge_skip_journal() is True
    assert journal[0]["actual_mm"] == pytest.approx(3.0)
    assert journal[0]["paid_off"] is True
    assert controller.skip_hit_rate() == (1, 1)


@pytest.mark.asyncio
async def test_a_dry_two_days_after_the_skip_did_not_pay_off(hass, fake_valve_services):
    await _seed(hass)
    _register_forecast_service(hass, precipitation=10.0)
    controller = await _make_zone(hass)
    await controller._forecast_gate_allows_run("routine")
    journal = controller.store.state.forecast_skip_journal
    journal[0]["ts"] -= 49 * HOUR

    controller.judge_skip_journal()

    assert journal[0]["actual_mm"] == 0.0 and journal[0]["paid_off"] is False
    assert controller.skip_hit_rate() == (0, 1)


@pytest.mark.asyncio
async def test_a_zone_with_no_rain_data_is_not_counted(hass, fake_valve_services):
    await _seed(hass)
    _register_forecast_service(hass, precipitation=10.0)
    controller = await _make_zone(hass, **{CONF_RAIN_COUNTER_ENTITY: None})
    await controller._forecast_gate_allows_run("routine")
    journal = controller.store.state.forecast_skip_journal
    journal[0]["ts"] -= 49 * HOUR

    controller.judge_skip_journal()

    assert journal[0]["paid_off"] is None and journal[0]["actual_mm"] is None
    assert controller.skip_hit_rate() == (0, 0)


@pytest.mark.asyncio
async def test_the_journal_keeps_the_last_30_entries(hass, fake_valve_services):
    await _seed(hass)
    _register_forecast_service(hass, precipitation=10.0)
    controller = await _make_zone(hass)
    for _ in range(35):
        controller._journal_skip("routine", 10.0, dt_util.utcnow().timestamp())
    assert len(controller.store.state.forecast_skip_journal) == 30


@pytest.mark.asyncio
async def test_the_sensor_shows_the_rate_and_the_entries(hass, fake_valve_services):
    await _seed(hass)
    _register_forecast_service(hass, precipitation=10.0)
    controller = await _make_zone(hass)
    registry = er.async_get(hass)
    entity_id = next(
        e.entity_id
        for e in er.async_entries_for_config_entry(registry, controller.entry.entry_id)
        if e.translation_key == "forecast_skip_hit_rate"
    )
    assert hass.states.get(entity_id).state in ("unknown", "unavailable")

    await controller._forecast_gate_allows_run("routine")
    journal = controller.store.state.forecast_skip_journal
    journal[0]["ts"] -= 49 * HOUR
    from homeassistant.helpers.entity_component import async_update_entity

    await async_update_entity(hass, entity_id)
    state = hass.states.get(entity_id)
    assert state.state == "0"
    assert state.attributes["judged"] == 1 and state.attributes["paid_off"] == 0
    assert state.attributes["entries"][0]["paid_off"] is False
