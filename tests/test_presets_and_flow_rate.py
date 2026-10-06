"""Plant presets at setup, and the flow-rate helper (Configure -> Flow
rate: work it out from the emitters, or measure it with the flow meter).
"""
import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from custom_components.zoneflow.const import (
    CONF_DEEP_SOAK_ENABLED,
    CONF_GROWTH_RAMP_PROFILE,
    CONF_PLANT,
    CONF_ZONE_NAME,
    DOMAIN,
    FLOW_MEASURE_MINUTES,
    GROWTH_RAMP_PROFILE_OPTIONS,
    NUMBER_DEFAULTS,
    NUMBER_DEFS,
    PLANT_PRESETS,
)

from .scenario_harness import CompressedTime
from .test_config_flow import _minimal_entities_input, _through_climate
from .test_smoke_setup import PUMP, VALVE, make_entry

FLOW_METER = "sensor.flow_meter_liters"


def test_every_preset_fits_the_settings():
    for name, preset in PLANT_PRESETS.items():
        assert preset["ramp"] in GROWTH_RAMP_PROFILE_OPTIONS, name
        assert isinstance(preset["deep_soak"], bool), name
        for key, value in preset["numbers"].items():
            _label, lo, hi, _step, _unit = NUMBER_DEFS[key]
            assert lo <= value <= hi, (name, key)
        n = preset["numbers"]
        assert n["target_weekly_cool_mm"] < n["target_weekly_mm"] < n["target_weekly_hot_mm"], name


async def _setup(hass, plant):
    hass.states.async_set(VALVE, "off")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ZONE_NAME: "Beds", CONF_PLANT: plant}
    )
    assert result["step_id"] == "entities"
    defaults = {k.schema: k.default() for k in result["data_schema"].schema if callable(getattr(k, "default", None))}
    preset = PLANT_PRESETS.get(plant)
    entities = _minimal_entities_input()
    if preset:
        entities[CONF_DEEP_SOAK_ENABLED] = defaults[CONF_DEEP_SOAK_ENABLED]
        entities[CONF_GROWTH_RAMP_PROFILE] = defaults[CONF_GROWTH_RAMP_PROFILE]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], entities)
    result = await _through_climate(hass, result)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    return result["result"], defaults


@pytest.mark.asyncio
async def test_a_plant_preset_prefills_the_zone(hass):
    entry, defaults = await _setup(hass, "tomatoes")
    assert defaults[CONF_DEEP_SOAK_ENABLED] is False
    assert defaults[CONF_GROWTH_RAMP_PROFILE] == "fast_annual"
    assert entry.data[CONF_PLANT] == "tomatoes"
    controller = hass.data[DOMAIN][entry.entry_id]
    for key, value in PLANT_PRESETS["tomatoes"]["numbers"].items():
        assert controller.number(key) == pytest.approx(value), key
    assert controller.deep_soak_enabled is False
    # The climate step's temperatures still apply.
    assert controller.number("hot_temp_threshold") == pytest.approx(28.0)


@pytest.mark.asyncio
async def test_no_preset_keeps_the_defaults(hass):
    entry, _ = await _setup(hass, "custom")
    controller = hass.data[DOMAIN][entry.entry_id]
    assert controller.number("target_weekly_mm") == NUMBER_DEFAULTS["target_weekly_mm"]
    assert controller.deep_soak_enabled is True


async def _options(hass, entry, step):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    assert ("flow_measure" in result["menu_options"]) == bool(hass.data[DOMAIN][entry.entry_id].flow_meter_entity)
    return await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": step})


async def _zone(hass, tmp_path, **overrides):
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    entry = make_entry(hass, csv_path=str(tmp_path / "f.csv"), **overrides)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, hass.data[DOMAIN][entry.entry_id]


@pytest.mark.asyncio
async def test_flow_rate_from_the_emitters(hass, fake_valve_services, tmp_path):
    entry, controller = await _zone(hass, tmp_path)
    result = await _options(hass, entry, "flow_rate")
    assert result["step_id"] == "flow_rate"
    # 4 drippers x 2 L/h on 1 m2 = 8 mm/h = 0.133 mm/min
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"emitters": 4, "emitter_flow": 2.0, "area": 1.0}
    )
    assert result["type"] == FlowResultType.ABORT and result["reason"] == "flow_rate_set"
    assert controller.number("flow_rate_mm_per_min") == pytest.approx(0.133, abs=0.001)
    assert entry.options == {}  # nothing else changed, no reload

    result = await _options(hass, entry, "flow_rate")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"emitters": 100, "emitter_flow": 10.0, "area": 0.1}
    )
    assert result["reason"] == "flow_rate_out_of_range"
    assert controller.number("flow_rate_mm_per_min") == pytest.approx(0.133, abs=0.001)


@pytest.mark.asyncio
async def test_flow_rate_from_the_litres_a_service_run_gave(hass, fake_valve_services, tmp_path):
    entry, controller = await _zone(hass, tmp_path)
    result = await _options(hass, entry, "flow_volume")
    assert result["step_id"] == "flow_volume"
    # 15 min, 36 L caught, 10 m2: 36 / 10 / 15 = 0.24 mm/min (the zone average)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"minutes": 15, "volume": 36.0, "area": 10.0}
    )
    assert result["type"] == FlowResultType.ABORT and result["reason"] == "flow_rate_set"
    assert controller.number("flow_rate_mm_per_min") == pytest.approx(0.24, abs=0.001)

    result = await _options(hass, entry, "flow_volume")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"minutes": 1, "volume": 5000.0, "area": 0.1}
    )
    assert result["reason"] == "flow_rate_out_of_range"
    assert controller.number("flow_rate_mm_per_min") == pytest.approx(0.24, abs=0.001)


@pytest.mark.asyncio
async def test_flow_rate_from_the_emitters_imperial(hass, fake_valve_services, tmp_path):
    hass.config.units = US_CUSTOMARY_SYSTEM
    entry, controller = await _zone(hass, tmp_path)
    result = await _options(hass, entry, "flow_rate")
    # 4 x 0.5 gal/h on 10 ft2
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"emitters": 4, "emitter_flow": 0.5, "area": 10.0}
    )
    assert result["reason"] == "flow_rate_set" and "in/h" in result["description_placeholders"]["rate"]
    assert controller.number("flow_rate_mm_per_min") == pytest.approx(4 * 0.5 * 3.785411784 / 0.9290304 / 60, abs=0.001)


@pytest.mark.asyncio
async def test_flow_rate_measured_with_the_flow_meter(hass, fake_valve_services, monkeypatch, tmp_path):
    sent = []

    async def _notify(call):
        sent.append(call.data["title"])

    hass.services.async_register("notify", "send_message", _notify)
    hass.states.async_set(FLOW_METER, "100.0")
    entry, controller = await _zone(hass, tmp_path, flow_meter_entity=FLOW_METER, notify_entity="notify.phone")
    clock = CompressedTime(hass, [VALVE]).install(monkeypatch)

    async def on_pulse(index):
        hass.states.async_set(FLOW_METER, "102.5")  # 2.5 L over the run

    clock.on_pulse = on_pulse
    result = await _options(hass, entry, "flow_measure")
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"area": 1.0})
    assert result["reason"] == "measuring"
    await hass.async_block_till_done()
    assert clock.pulses_for(VALVE) == [float(FLOW_MEASURE_MINUTES)]
    # 2.5 L / 1 m2 / 10 min = 0.25 mm/min
    assert controller.number("flow_rate_mm_per_min") == pytest.approx(0.25)
    assert any("Flow rate measured" in title for title in sent)
    assert controller.store.state.today_runtime_minutes == pytest.approx(FLOW_MEASURE_MINUTES)

    # No water counted: a warning, and the setting stays.
    clock.on_pulse = None
    await controller.start_flow_measurement(1.0)
    await hass.async_block_till_done()
    assert controller.number("flow_rate_mm_per_min") == pytest.approx(0.25)
    assert any("not measured" in title for title in sent)


@pytest.mark.asyncio
async def test_a_failed_or_cancelled_measurement_leaves_nothing_behind(hass, fake_valve_services, monkeypatch, tmp_path):
    sent = []

    async def _notify(call):
        sent.append(call.data["title"])

    hass.services.async_register("notify", "send_message", _notify)
    hass.states.async_set(FLOW_METER, "100.0")
    entry, controller = await _zone(hass, tmp_path, flow_meter_entity=FLOW_METER, notify_entity="notify.phone")
    controller.store.state.notify_level = "warnings"  # a requested result still comes through
    clock = CompressedTime(hass, [VALVE]).install(monkeypatch)

    # Stopped by the person: cancelled, nothing set, no warning.
    async def stop(index):
        hass.states.async_set(FLOW_METER, "101.0")
        await controller.stop_service_run()

    clock.on_pulse = stop
    await controller.start_flow_measurement(1.0)
    await hass.async_block_till_done()
    assert controller.number("flow_rate_mm_per_min") == pytest.approx(0.24)
    assert sent == [] and "Cancelled" in (tmp_path / "f.csv").read_text()

    # A second request while one runs is refused and doesn't disturb it.
    async def second(index):
        hass.states.async_set(FLOW_METER, "103.0")
        with pytest.raises(Exception):
            await controller.start_flow_measurement(5.0)

    clock.on_pulse = second
    await controller.start_flow_measurement(1.0)
    await hass.async_block_till_done()
    assert controller.number("flow_rate_mm_per_min") == pytest.approx(0.2)  # 2 L / 1 m2 / 10 min
    assert any("Flow rate measured" in title for title in sent)

    # An ordinary service run afterwards is just a service run.
    clock.on_pulse = None
    hass.states.async_set(FLOW_METER, "150.0")
    await controller.start_service_run(5)
    await hass.async_block_till_done()
    assert controller.number("flow_rate_mm_per_min") == pytest.approx(0.2)
