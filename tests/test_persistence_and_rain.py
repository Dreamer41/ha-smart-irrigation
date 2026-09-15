"""Two more things that can't be checked by pure-Python unit tests:

1. Do dashboard-set numbers survive an integration reload (simulating an HA
   restart), via RestoreNumber?
2. Does the "significant rain" event really only fire on the rising edge
   (crossing the threshold), not on every rain sample above it?
"""
import pytest

from custom_components.avocado_irrigation.const import DOMAIN, NUMBER_DEFAULTS

from .test_smoke_setup import RAIN_COUNTER, _seed_source_entities, make_entry


@pytest.mark.asyncio
async def test_number_value_persists_across_a_simulated_restart(hass):
    await _seed_source_entities(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    target_entity_id = None
    for state in hass.states.async_all("number"):
        if state.attributes.get("friendly_name", "").endswith("Routine Normal Weekly Target"):
            target_entity_id = state.entity_id
            break
    assert target_entity_id, "could not find the target_weekly_mm number entity"

    default_value = NUMBER_DEFAULTS["target_weekly_mm"]
    assert float(hass.states.get(target_entity_id).state) == default_value

    new_value = default_value + 5.0
    await hass.services.async_call(
        "number", "set_value", {"entity_id": target_entity_id, "value": new_value}, blocking=True
    )
    await hass.async_block_till_done()
    assert float(hass.states.get(target_entity_id).state) == new_value

    # Simulate an HA restart: unload the entry, then set it up again.
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    restored = hass.states.get(target_entity_id)
    assert restored is not None
    assert float(restored.state) == new_value, "the dashboard-set value did not survive the simulated restart"


@pytest.mark.asyncio
async def test_significant_rain_fires_once_on_threshold_crossing(hass):
    await _seed_source_entities(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    assert controller.store.state.last_significant_rain_ts is None

    # 150 tips * default 0.3mm/tip = 45mm -- crosses the 35mm/24h
    # significant-rain threshold.
    hass.states.async_set(RAIN_COUNTER, "150")
    await hass.async_block_till_done()
    first_ts = controller.store.state.last_significant_rain_ts
    assert first_ts is not None, "significant rain was not detected after crossing the 24h threshold"

    # More rain, but still short of the next threshold up (50mm/4d) -- no
    # new rising edge, so this must not re-fire. (Note: going all the way to
    # 200 tips/60mm would *correctly* re-fire, since that crosses the
    # separate 50mm/4-day threshold for the first time -- that's not a bug,
    # so this test deliberately stays under it.)
    hass.states.async_set(RAIN_COUNTER, "160")
    await hass.async_block_till_done()
    assert controller.store.state.last_significant_rain_ts == first_ts, (
        "the significant-rain event re-fired while already above threshold instead of only on the rising edge"
    )
