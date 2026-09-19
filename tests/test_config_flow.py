"""Exercises the real config flow / options flow (not just MockConfigEntry)
so the schema in config_flow.py -- especially the new optional-entity
fields (pump power / rain counter / outdoor temp / flow meter) and the
descriptive soil/site + growth-ramp selectors -- is actually verified end
to end, the way a person clicking through the UI would hit it.
"""
import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.zoneflow.const import (
    CONF_CSV_PATH,
    CONF_DEEP_SOAK_ENABLED,
    CONF_DEEP_SOAK_SUN_MODE,
    CONF_DEEP_SOAK_SUN_OFFSET_MINUTES,
    CONF_DEEP_SOAK_TIME,
    CONF_DRAINAGE,
    CONF_FLOW_METER_ENTITY,
    CONF_GROWTH_RAMP_PROFILE,
    CONF_IRRIGATION_METHOD,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_PUMP_POWER_ENTITY,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_ROUTINE_SUN_MODE,
    CONF_ROUTINE_SUN_OFFSET_MINUTES,
    CONF_ROUTINE_TIME,
    CONF_SLOPE,
    CONF_SOIL_TYPE,
    CONF_VALVE_ENTITY,
    CONF_ZONE_NAME,
    DEFAULT_DEEP_SOAK_ENABLED,
    DEFAULT_DRAINAGE,
    DEFAULT_GROWTH_RAMP_PROFILE,
    DEFAULT_IRRIGATION_METHOD,
    DEFAULT_SLOPE,
    DEFAULT_SOIL_TYPE,
    DEFAULT_SUN_MODE,
    DOMAIN,
    GROWTH_RAMP_FAST_ANNUAL,
)

VALVE = "switch.watering1"


def _minimal_entities_input(**overrides):
    """Only the one truly-required field (valve) plus the required-with-a-
    sensible-default descriptive/select fields -- every optional entity
    field (pump power, rain counter, outdoor temp, flow meter, notify,
    weather) is left out entirely, exactly as a person skipping every
    optional sensor during setup would submit the form."""
    data = {
        CONF_VALVE_ENTITY: VALVE,
        CONF_SOIL_TYPE: DEFAULT_SOIL_TYPE,
        CONF_DRAINAGE: DEFAULT_DRAINAGE,
        CONF_SLOPE: DEFAULT_SLOPE,
        CONF_IRRIGATION_METHOD: DEFAULT_IRRIGATION_METHOD,
        CONF_GROWTH_RAMP_PROFILE: DEFAULT_GROWTH_RAMP_PROFILE,
        CONF_CSV_PATH: "/tmp/test_zoneflow_flow.csv",
        CONF_DEEP_SOAK_ENABLED: DEFAULT_DEEP_SOAK_ENABLED,
        CONF_DEEP_SOAK_TIME: "05:00:00",
        CONF_ROUTINE_TIME: "05:30:00",
        CONF_DEEP_SOAK_SUN_MODE: DEFAULT_SUN_MODE,
        CONF_DEEP_SOAK_SUN_OFFSET_MINUTES: 0,
        CONF_ROUTINE_SUN_MODE: DEFAULT_SUN_MODE,
        CONF_ROUTINE_SUN_OFFSET_MINUTES: 0,
    }
    data.update(overrides)
    return data


@pytest.mark.asyncio
async def test_zone_name_required_shows_error(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ZONE_NAME: "   "})
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "zone_name_required"}


@pytest.mark.asyncio
async def test_minimal_setup_with_every_optional_entity_skipped(hass):
    """The real point of this test: a person who has only a valve (no pump
    power sensor, no rain gauge, no temp sensor, no flow meter) can still
    complete setup and get a working config entry -- this is what
    controller.py's graceful-degradation properties (pump_power_entity etc.
    returning None) actually get exercised against."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ZONE_NAME: "Bare Zone"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "entities"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], _minimal_entities_input())
    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.title == "Bare Zone"
    assert entry.data[CONF_VALVE_ENTITY] == VALVE
    # Left out of the submitted form entirely -- vol.Optional() with no
    # default means the key is simply absent, not None or "".
    for key in (CONF_PUMP_POWER_ENTITY, CONF_RAIN_COUNTER_ENTITY, CONF_OUTDOOR_TEMP_ENTITY, CONF_FLOW_METER_ENTITY):
        assert key not in entry.data
    assert entry.data[CONF_SOIL_TYPE] == DEFAULT_SOIL_TYPE
    assert entry.data[CONF_GROWTH_RAMP_PROFILE] == DEFAULT_GROWTH_RAMP_PROFILE
    # Deep soak defaults ON (unlike growth-ramp) -- see const.py's
    # CONF_DEEP_SOAK_ENABLED comment for why the two features default
    # differently.
    assert entry.data[CONF_DEEP_SOAK_ENABLED] is DEFAULT_DEEP_SOAK_ENABLED is True


@pytest.mark.asyncio
async def test_deep_soak_can_be_turned_off_for_crops_that_dont_need_it(hass):
    """Some plants/setups (shallow-rooted crops, containers, frequent-drip
    greenhouse zones) genuinely don't benefit from an infrequent deep soak
    on top of routine irrigation -- this is what actually gates
    controller.run_deep_soak() (see test_irrigation_gates.py)."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ZONE_NAME: "Lettuce"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _minimal_entities_input(**{CONF_DEEP_SOAK_ENABLED: False})
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["result"].data[CONF_DEEP_SOAK_ENABLED] is False


@pytest.mark.asyncio
async def test_full_setup_with_soil_profile_and_growth_ramp(hass):
    pump = "sensor.waterpump_power_power"
    rain = "sensor.rain_gauge_tips"
    temp = "sensor.outdoor_temp_temperature"
    flow = "sensor.flow_meter_liters"

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ZONE_NAME: "Strawberries"})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        _minimal_entities_input(
            **{
                CONF_PUMP_POWER_ENTITY: pump,
                CONF_RAIN_COUNTER_ENTITY: rain,
                CONF_OUTDOOR_TEMP_ENTITY: temp,
                CONF_FLOW_METER_ENTITY: flow,
                CONF_SOIL_TYPE: "clay_loam",
                CONF_DRAINAGE: "slow",
                CONF_SLOPE: "slight",
                CONF_IRRIGATION_METHOD: "drip",
                CONF_GROWTH_RAMP_PROFILE: GROWTH_RAMP_FAST_ANNUAL,
            }
        ),
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.data[CONF_PUMP_POWER_ENTITY] == pump
    assert entry.data[CONF_FLOW_METER_ENTITY] == flow
    assert entry.data[CONF_SOIL_TYPE] == "clay_loam"
    assert entry.data[CONF_DRAINAGE] == "slow"
    assert entry.data[CONF_GROWTH_RAMP_PROFILE] == GROWTH_RAMP_FAST_ANNUAL


@pytest.mark.asyncio
async def test_options_flow_prefills_current_soil_profile_and_can_change_it(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ZONE_NAME: "Pumpkins"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _minimal_entities_input(**{CONF_SOIL_TYPE: "sandy"})
    )
    entry = result["result"]

    options_result = await hass.config_entries.options.async_init(entry.entry_id)
    assert options_result["type"] == FlowResultType.FORM
    schema = options_result["data_schema"].schema
    # The current value round-trips back as the field's default.
    soil_field = next(k for k in schema if k == CONF_SOIL_TYPE)
    assert soil_field.default() == "sandy"

    updated = await hass.config_entries.options.async_configure(
        options_result["flow_id"], _minimal_entities_input(**{CONF_SOIL_TYPE: "loam"})
    )
    assert updated["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SOIL_TYPE] == "loam"
    # Saving options triggers zoneflow's update listener, which reloads the
    # entry (see __init__._async_update_listener) -- let that finish so the
    # reload's freshly (re)scheduled daily-trigger timers are the ones still
    # live when the test ends, not a half-finished reload racing teardown's
    # own automatic entry unload.
    await hass.async_block_till_done()
