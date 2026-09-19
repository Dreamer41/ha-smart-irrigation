"""The deep-soak on/off dashboard switch (switch.py) -- lets a person flip
whether this zone runs the deep-soak cycle at all, straight from the
dashboard, without reopening the integration's Options flow. Verifies its
actual behavior (reads/writes the same CONF_DEEP_SOAK_ENABLED as the config
flow), not just that the entity exists -- see test_smoke_setup.py for the
"does it get created at all" check.
"""
import pytest

from custom_components.zoneflow.const import CONF_DEEP_SOAK_ENABLED, DOMAIN
from custom_components.zoneflow.switch import ZoneFlowDeepSoakEnabledSwitch

from .test_smoke_setup import _seed_source_entities, make_entry


@pytest.mark.asyncio
async def test_switch_reflects_controller_state_and_toggling_updates_options(hass, fake_valve_services):
    await _seed_source_entities(hass)
    entry = make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]

    # Defaults on, same as the config-flow field (const.py's
    # DEFAULT_DEEP_SOAK_ENABLED) -- see test_config_flow.py for that side.
    assert controller.deep_soak_enabled is True

    switch = ZoneFlowDeepSoakEnabledSwitch(entry, controller)
    switch.hass = hass
    assert switch.is_on is True

    await switch.async_turn_off()
    await hass.async_block_till_done()

    # Turning the switch off writes into entry.options -- the exact same
    # place the config flow's "Enable the deep soak cycle" field writes --
    # so the two are genuinely the same setting, not two competing copies.
    assert entry.options[CONF_DEEP_SOAK_ENABLED] is False
    # The entry reload triggered by the options change (see
    # __init__.py's _async_update_listener) rebuilds the controller; fetch
    # it again rather than assuming the old reference is still valid.
    await hass.async_block_till_done()
    reloaded_controller = hass.data[DOMAIN][entry.entry_id]
    assert reloaded_controller.deep_soak_enabled is False

    switch_after_reload = ZoneFlowDeepSoakEnabledSwitch(entry, reloaded_controller)
    switch_after_reload.hass = hass
    assert switch_after_reload.is_on is False

    await switch_after_reload.async_turn_on()
    await hass.async_block_till_done()
    assert entry.options[CONF_DEEP_SOAK_ENABLED] is True
