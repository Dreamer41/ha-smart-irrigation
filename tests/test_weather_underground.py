"""Weather Underground rain (1.6.1, experimental): the shared entry, its
setup flow, the poller, and the outdoor zones without a rain gauge that use
it. The network is never touched: the WU calls are faked."""
from __future__ import annotations

import pytest
import homeassistant.util.dt as dt_util
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zoneflow import wu, wu_logic
from custom_components.zoneflow.const import (
    CONF_ENTRY_TYPE,
    CONF_RAIN_COUNTER_ENTITY,
    CONF_USE_WU,
    CONF_WU_API_KEY,
    CONF_WU_RADIUS_KM,
    CONF_WU_STATIONS,
    DOMAIN,
    ENTRY_TYPE_WU,
    WU_DATA_KEY,
)

from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

HOME = (9.50, 100.00)
STATIONS = [
    {"id": "ISAMUI1", "name": "Near", "latitude": 9.505, "longitude": 100.0, "distance_km": 0.56},
    {"id": "ISAMUI2", "name": "Close", "latitude": 9.51, "longitude": 100.0, "distance_km": 1.11},
]


class FakeWU:
    """Stands in for the network: each station's current total."""

    def __init__(self):
        self.totals: dict[str, float | None] = {}
        self.calls = 0

    async def current(self, hass, api_key, station_id):
        self.calls += 1
        total = self.totals.get(station_id)
        if total is None:
            return None
        now = dt_util.utcnow().timestamp()
        return wu_logic.Observation(total, now - 30, dt_util.now().date().isoformat())


@pytest.fixture
def fake_wu(monkeypatch):
    fake = FakeWU()
    monkeypatch.setattr(wu, "async_current", fake.current)
    return fake


async def _seed(hass):
    await hass.config.async_update(latitude=HOME[0], longitude=HOME[1])
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "25.0")
    await hass.async_block_till_done()


def _wu_entry(hass, stations=STATIONS):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Weather Underground rain",
        unique_id=ENTRY_TYPE_WU,
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_WU, CONF_WU_API_KEY: "secret-key", CONF_WU_RADIUS_KM: 3.0, CONF_WU_STATIONS: stations},
    )
    entry.add_to_hass(hass)
    return entry


async def _setup_all(hass, *, use_wu=True, gauge=False):
    await _seed(hass)
    zone_entry = make_entry(hass, **({} if gauge else {CONF_RAIN_COUNTER_ENTITY: None}))
    hass.config_entries.async_update_entry(zone_entry, options={CONF_USE_WU: use_wu})
    wu_entry = _wu_entry(hass)
    # Setting up one entry loads the integration, and with it every entry.
    assert await hass.config_entries.async_setup(zone_entry.entry_id)
    await hass.async_block_till_done()
    assert wu_entry.state is config_entries.ConfigEntryState.LOADED
    return hass.data[DOMAIN][zone_entry.entry_id], hass.data[WU_DATA_KEY], wu_entry


# ------------------------------------------------------------------ setup flow


@pytest.mark.asyncio
async def test_setup_flow_offers_wu_once_a_zone_exists_and_creates_the_entry(hass, aioclient_mock):
    await _seed(hass)
    make_entry(hass)
    aioclient_mock.get(
        wu.NEAR_URL,
        json={
            "location": {
                "stationId": ["ISAMUI1", "ISAMUI2", "IFAR1"],
                "stationName": ["Near", "Close", "Far"],
                "latitude": [9.505, 9.51, 9.60],
                "longitude": [100.0, 100.0, 100.0],
            }
        },
    )
    aioclient_mock.get(
        wu.CURRENT_URL,
        json={"observations": [{"epoch": 1, "obsTimeLocal": "2026-10-04 10:00:00", "metric": {"precipTotal": 1.5}}]},
    )

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] == FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "weather_underground"})
    assert result["step_id"] == "weather_underground"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_WU_API_KEY: " secret-key ", CONF_WU_RADIUS_KM: 3.0}
    )
    assert result["step_id"] == "wu_stations"
    # The station 11 km away is not offered.
    offered = [o["value"] for o in result["data_schema"].schema[CONF_WU_STATIONS].config["options"]]
    assert offered == ["ISAMUI1", "ISAMUI2"]

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_WU_STATIONS: []})
    assert result["errors"] == {"base": "wu_pick_1_to_3"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_WU_STATIONS: ["ISAMUI2", "ISAMUI1"]})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_ENTRY_TYPE] == ENTRY_TYPE_WU and data[CONF_WU_API_KEY] == "secret-key"
    assert [s["id"] for s in data[CONF_WU_STATIONS]] == ["ISAMUI2", "ISAMUI1"]
    assert "secret" not in result["title"]

    # One per Home Assistant: no menu any more.
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] == FlowResultType.FORM and result["step_id"] == "user"


@pytest.mark.asyncio
async def test_setup_flow_errors(hass, aioclient_mock):
    await _seed(hass)
    make_entry(hass)
    aioclient_mock.get(wu.NEAR_URL, status=401)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "weather_underground"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_WU_API_KEY: "bad", CONF_WU_RADIUS_KM: 3.0})
    assert result["errors"] == {"base": "wu_invalid_key"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        wu.NEAR_URL,
        json={"location": {"stationId": ["IFAR1"], "stationName": ["Far"], "latitude": [9.6], "longitude": [100.0]}},
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_WU_API_KEY: "k", CONF_WU_RADIUS_KM: 3.0})
    assert result["errors"] == {"base": "wu_no_stations"}


@pytest.mark.asyncio
async def test_first_zone_setup_has_no_menu(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] == FlowResultType.FORM and result["step_id"] == "user"


@pytest.mark.asyncio
async def test_zone_option_only_for_zones_without_a_gauge(hass, fake_wu):
    zone, _source, _ = await _setup_all(hass, use_wu=False)
    result = await hass.config_entries.options.async_init(zone.entry.entry_id)
    assert "weather_underground" in result["menu_options"]
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "weather_underground"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_USE_WU: True})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert zone.entry.options[CONF_USE_WU] is True

    gauge_entry = make_entry(hass, csv_path="/tmp/test_zoneflow_gauge.csv", valve_entity="switch.other_valve")
    assert await hass.config_entries.async_setup(gauge_entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(gauge_entry.entry_id)
    assert "weather_underground" not in result["menu_options"]


# ------------------------------------------------------------------ poller and zones


@pytest.mark.asyncio
async def test_zone_rain_comes_from_the_stations(hass, fake_valve_services, fake_wu):
    zone, source, _ = await _setup_all(hass)
    assert zone.uses_wu and not zone.manual_rain_available

    fake_wu.totals = {"ISAMUI1": 0.0, "ISAMUI2": 0.0}
    await source.async_poll()
    fake_wu.totals = {"ISAMUI1": 6.0, "ISAMUI2": 4.0}
    source.last_poll_ts -= 2 * 3600  # a quiet-mode poll two hours later
    await source.async_poll()

    assert zone.today_rain_mm() == pytest.approx(4.0)  # two stations: the lower
    windows = zone.rain_windows()
    assert windows["24h"] == pytest.approx(4.0)
    assert windows["30min"] == 0.0  # a 2-hour lump is not "raining now"

    fake_wu.totals = {"ISAMUI1": 9.0, "ISAMUI2": 7.0}
    await source.async_poll()  # straight after: fresh
    assert zone.rain_windows()["30min"] == pytest.approx(3.0)
    assert zone.today_rain_mm() == pytest.approx(7.0)


@pytest.mark.asyncio
async def test_a_zone_with_a_gauge_never_uses_wu(hass, fake_valve_services, fake_wu):
    zone, source, _ = await _setup_all(hass, gauge=True)
    assert zone.uses_wu is False
    fake_wu.totals = {"ISAMUI1": 0.0, "ISAMUI2": 0.0}
    await source.async_poll()
    fake_wu.totals = {"ISAMUI1": 20.0, "ISAMUI2": 20.0}
    await source.async_poll()
    assert zone.today_rain_mm() == 0.0


@pytest.mark.asyncio
async def test_heavy_wu_rain_restarts_the_dry_down(hass, fake_valve_services, fake_wu):
    zone, source, _ = await _setup_all(hass)
    zone.store.state.last_significant_rain_ts = 0.0
    fake_wu.totals = {"ISAMUI1": 0.0, "ISAMUI2": 0.0}
    await source.async_poll()
    fake_wu.totals = {"ISAMUI1": 50.0, "ISAMUI2": 50.0}
    await source.async_poll()
    assert zone.store.state.last_significant_rain_ts > 0.0


@pytest.mark.asyncio
async def test_a_watering_refreshes_stale_wu_rain_first(hass, fake_valve_services, fake_wu):
    zone, source, _ = await _setup_all(hass)
    fake_wu.totals = {"ISAMUI1": 0.0, "ISAMUI2": 0.0}
    await source.async_poll()
    calls = fake_wu.calls
    await zone._refresh_wu_rain()
    assert fake_wu.calls == calls  # just polled: nothing to do
    source.last_poll_ts -= 20 * 60
    await zone._refresh_wu_rain()
    assert fake_wu.calls == calls + 2


@pytest.mark.asyncio
async def test_polls_every_10_minutes_around_a_watering(hass, fake_valve_services, fake_wu):
    zone, source, _ = await _setup_all(hass)
    fake_wu.totals = {"ISAMUI1": 0.0, "ISAMUI2": 0.0}
    now = dt_util.utcnow().timestamp()
    zone.wu_watering_slots = lambda _now: [now + 30 * 60]
    await source.async_poll()
    assert source.next_poll_ts - dt_util.utcnow().timestamp() == pytest.approx(wu_logic.WATERING_POLL_SECONDS, abs=5)
    zone.wu_watering_slots = lambda _now: []
    await source.async_poll()
    assert source.next_poll_ts - dt_util.utcnow().timestamp() <= wu_logic.QUIET_POLL_SECONDS + 5


@pytest.mark.asyncio
async def test_no_data_for_6_hours_raises_a_repair_issue(hass, fake_valve_services, fake_wu):
    _zone, source, _ = await _setup_all(hass)
    fake_wu.totals = {}
    await source.async_poll()
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, wu.ISSUE_NO_DATA) is None
    for state in source.stations.values():
        state.first_seen_ts -= 7 * 3600
    await source.async_poll()
    assert registry.async_get_issue(DOMAIN, wu.ISSUE_NO_DATA) is not None
    fake_wu.totals = {"ISAMUI1": 0.0}
    await source.async_poll()
    assert registry.async_get_issue(DOMAIN, wu.ISSUE_NO_DATA) is None


@pytest.mark.asyncio
async def test_sensors_and_diagnostics_keep_the_key_secret(hass, fake_valve_services, fake_wu):
    _zone, source, wu_entry = await _setup_all(hass)
    fake_wu.totals = {"ISAMUI1": 0.0, "ISAMUI2": 1.0}
    await source.async_poll()
    await hass.async_block_till_done()
    states = [s for s in hass.states.async_all("sensor") if "weather_underground" in s.entity_id]
    assert len(states) == 3  # rain today + two stations
    from custom_components.zoneflow.diagnostics import async_get_config_entry_diagnostics

    diag = await async_get_config_entry_diagnostics(hass, wu_entry)
    assert "secret-key" not in str(diag)
    assert diag["weather_underground"]["used_stations"] == ["ISAMUI1", "ISAMUI2"]


@pytest.mark.asyncio
async def test_unloading_the_wu_entry_leaves_the_zone_without_wu_rain(hass, fake_valve_services, fake_wu):
    zone, source, wu_entry = await _setup_all(hass)
    fake_wu.totals = {"ISAMUI1": 0.0, "ISAMUI2": 0.0}
    await source.async_poll()
    fake_wu.totals = {"ISAMUI1": 5.0, "ISAMUI2": 5.0}
    await source.async_poll()
    assert await hass.config_entries.async_unload(wu_entry.entry_id)
    assert WU_DATA_KEY not in hass.data
    assert zone.today_rain_mm() == 0.0
