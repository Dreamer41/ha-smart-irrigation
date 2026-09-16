"""Weather forecast gate: pre-emptively hold off a scheduled run when rain
is forecast, but never let a wrong/stuck forecast starve a plant -- the
`forecast_dry_override_days` number (adjustable per zone, per crop, in the
UI) caps how long the gate is allowed to keep skipping before it overrides
itself, provided no rain has actually been measured in the meantime.
"""
from datetime import timedelta

import pytest
from homeassistant.core import SupportsResponse
import homeassistant.util.dt as dt_util

from custom_components.zoneflow.const import DOMAIN

from .test_smoke_setup import PUMP, RAIN_COUNTER, VALVE, OUTDOOR_TEMP, make_entry

WEATHER = "weather.home"


async def _seed(hass):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "0")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "25.0")
    hass.states.async_set(WEATHER, "sunny")
    await hass.async_block_till_done()


def _register_forecast_service(hass, *, precipitation, probability=None):
    """Fake `weather.get_forecasts`, mirroring the real service's response
    shape: {entity_id: {"forecast": [...]}}."""

    async def _get_forecasts(call):
        day = {"precipitation": precipitation}
        if probability is not None:
            day["precipitation_probability"] = probability
        entity_ids = call.data["entity_id"]
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        return {entity_id: {"forecast": [day]} for entity_id in entity_ids}

    hass.services.async_register(
        "weather", "get_forecasts", _get_forecasts, supports_response=SupportsResponse.ONLY
    )


async def _make_zone(hass, **overrides):
    entry = make_entry(hass, weather_entity=WEATHER, **overrides)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


@pytest.mark.asyncio
async def test_no_weather_entity_never_blocks(hass, fake_valve_services):
    await _seed(hass)
    entry = make_entry(hass)  # no weather_entity at all
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    assert await controller._forecast_gate_allows_run("routine") is True


@pytest.mark.asyncio
async def test_unavailable_forecast_fails_open(hass, fake_valve_services):
    await _seed(hass)
    hass.states.async_set(WEATHER, "unavailable")
    controller = await _make_zone(hass)

    assert await controller._forecast_gate_allows_run("routine") is True


@pytest.mark.asyncio
async def test_rain_above_threshold_blocks_the_run(hass, fake_valve_services):
    await _seed(hass)
    _register_forecast_service(hass, precipitation=10.0)
    controller = await _make_zone(hass)

    assert await controller._forecast_gate_allows_run("routine") is False
    state = controller.store.state
    assert state.forecast_routine_skip_count == 1
    assert state.forecast_routine_skip_start_ts is not None


@pytest.mark.asyncio
async def test_rain_below_threshold_and_probability_lets_it_run(hass, fake_valve_services):
    await _seed(hass)
    _register_forecast_service(hass, precipitation=0.1, probability=10)
    controller = await _make_zone(hass)

    assert await controller._forecast_gate_allows_run("routine") is True
    assert controller.store.state.forecast_routine_skip_count == 0


@pytest.mark.asyncio
async def test_high_probability_light_rain_also_blocks(hass, fake_valve_services):
    """Not just the mm threshold -- a high-confidence forecast should also
    count, even with rainfall just under the mm threshold."""
    await _seed(hass)
    _register_forecast_service(hass, precipitation=1.0, probability=90)
    controller = await _make_zone(hass)

    assert await controller._forecast_gate_allows_run("routine") is False


@pytest.mark.asyncio
async def test_dry_spell_override_fires_after_the_configured_days_with_no_rain(hass, fake_valve_services):
    await _seed(hass)
    _register_forecast_service(hass, precipitation=10.0)
    controller = await _make_zone(hass)
    # Make this zone's crop override quickly (e.g. a thirsty vegetable bed).
    controller.numbers["forecast_dry_override_days"]._attr_native_value = 1.0

    # First check: forecast blocks, streak starts now.
    assert await controller._forecast_gate_allows_run("routine") is False
    start_ts = controller.store.state.forecast_routine_skip_start_ts
    assert start_ts is not None

    # Simulate the streak start being 2 days ago with zero rain since, by
    # backdating the stored timestamp (equivalent to two scheduled runs
    # having already been skipped with nothing measured in between).
    controller.store.state.forecast_routine_skip_start_ts = start_ts - 2 * 86400

    assert await controller._forecast_gate_allows_run("routine") is True
    # Override resets the streak.
    assert controller.store.state.forecast_routine_skip_count == 0
    assert controller.store.state.forecast_routine_skip_start_ts is None


@pytest.mark.asyncio
async def test_dry_spell_override_does_not_fire_if_rain_actually_fell(hass, fake_valve_services):
    await _seed(hass)
    _register_forecast_service(hass, precipitation=10.0)
    controller = await _make_zone(hass)
    controller.numbers["forecast_dry_override_days"]._attr_native_value = 1.0

    assert await controller._forecast_gate_allows_run("routine") is False
    start_ts = controller.store.state.forecast_routine_skip_start_ts
    controller.store.state.forecast_routine_skip_start_ts = start_ts - 2 * 86400

    # Real rain landed during the "dry" streak -- override must not fire.
    # (Samples must be chronologically non-decreasing, so this has to land
    # at-or-after the tracker's existing baseline sample from zone setup,
    # not literally 2 days ago -- what matters for the check is that it's
    # after the *simulated* skip_start, which the backdate above already put
    # in the past relative to "now".)
    tracker = controller.store.state.rain_tracker()
    tracker.record(dt_util.utcnow().timestamp(), tracker.latest_cumulative() + 5.0)
    controller.store.state.save_rain_tracker(tracker)

    assert await controller._forecast_gate_allows_run("routine") is False


@pytest.mark.asyncio
async def test_a_less_drought_tolerant_crop_can_be_configured_to_override_sooner(hass, fake_valve_services):
    """The whole point of making forecast_dry_override_days a UI-adjustable
    number: two zones with identical forecasts can behave differently."""
    await _seed(hass)
    _register_forecast_service(hass, precipitation=10.0)
    thirsty = await _make_zone(hass, zone_name="Thirsty Veggies", valve_entity="switch.watering2")
    hardy = await _make_zone(hass, zone_name="Hardy Succulents", pump_power_entity="sensor.other_pump")
    thirsty.numbers["forecast_dry_override_days"]._attr_native_value = 1.0
    hardy.numbers["forecast_dry_override_days"]._attr_native_value = 5.0

    for controller in (thirsty, hardy):
        assert await controller._forecast_gate_allows_run("routine") is False
        start_ts = controller.store.state.forecast_routine_skip_start_ts
        controller.store.state.forecast_routine_skip_start_ts = start_ts - 2 * 86400

    # 2 dry days is enough for the thirsty zone's 1-day limit, but not for
    # the hardy zone's 5-day limit.
    assert await thirsty._forecast_gate_allows_run("routine") is True
    assert await hardy._forecast_gate_allows_run("routine") is False
