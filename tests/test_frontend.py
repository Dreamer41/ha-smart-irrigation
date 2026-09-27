"""The dashboard card is served by the integration and loaded on every
dashboard (frontend.py); the card itself is checked in a browser by
scripts/check_card.py."""
import json
from pathlib import Path
import re
from unittest.mock import MagicMock

import pytest

from custom_components.zoneflow import frontend

ROOT = Path(__file__).parent.parent / "custom_components" / "zoneflow"


def test_card_version_matches_the_integration():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    card = (ROOT / "frontend" / "zoneflow-card.js").read_text(encoding="utf-8")
    assert re.search(r'const CARD_VERSION = "([^"]+)"', card).group(1) == manifest["version"]


@pytest.mark.asyncio
async def test_card_is_served_and_loaded_once(hass, monkeypatch, tmp_path):
    hass.config.config_dir = str(tmp_path)
    added = []
    monkeypatch.setattr(
        "homeassistant.components.frontend.add_extra_js_url", lambda _hass, url, es5=False: added.append(url)
    )
    class Http:
        registered = None
        register_static_path = MagicMock()

        async def async_register_static_paths(self, configs):
            self.registered = configs

    http = Http()
    hass.http = http
    hass.config.components.add("frontend")
    await frontend.async_register(hass)
    await frontend.async_register(hass)  # a second zone: nothing more
    assert len(added) == 1 and re.fullmatch(r"/zoneflow_static/zoneflow-card.js\?v=[0-9.]+-[0-9]+", added[0])
    served = http.registered
    if served is not None:  # Home Assistant 2024.7+
        assert served[0].url_path == "/zoneflow_static/zoneflow-card.js"
        assert Path(served[0].path).is_file()
    else:
        url, path, _cache = http.register_static_path.call_args.args
        assert url == "/zoneflow_static/zoneflow-card.js" and Path(path).is_file()


@pytest.mark.asyncio
async def test_nothing_to_do_without_the_frontend(hass):
    hass.http = MagicMock()
    await frontend.async_register(hass)
    assert not hass.data.get("zoneflow_frontend_registered")


@pytest.mark.asyncio
async def test_a_card_problem_never_stops_setup(hass, monkeypatch):
    class Http:
        def register_static_path(self, *args):
            raise RuntimeError("route already taken")

        async def async_register_static_paths(self, configs):
            raise RuntimeError("route already taken")

    hass.http = Http()
    hass.config.components.add("frontend")
    await frontend.async_register(hass)  # logged, not raised
    assert not hass.data.get("zoneflow_frontend_registered")  # tried again next time


@pytest.mark.asyncio
async def test_zones_starting_together_register_once(hass, monkeypatch, tmp_path):
    import asyncio

    hass.config.config_dir = str(tmp_path)
    added = []
    monkeypatch.setattr(
        "homeassistant.components.frontend.add_extra_js_url", lambda _hass, url, es5=False: added.append(url)
    )
    registered = []

    class Http:
        def register_static_path(self, url, *args):
            if url in registered:
                raise RuntimeError("method GET is already registered")
            registered.append(url)

        async def async_register_static_paths(self, configs):
            await asyncio.sleep(0)
            for config in configs:
                self.register_static_path(config.url_path)

    hass.http = Http()
    hass.config.components.add("frontend")
    await asyncio.gather(*(frontend.async_register(hass) for _ in range(6)))
    assert registered == ["/zoneflow_static/zoneflow-card.js"] and len(added) == 1


class Resources:
    """Home Assistant's own list of dashboard resources (storage mode)."""

    def __init__(self, items=()):
        self.items = [dict(item) for item in items]
        self.loaded = False
        self.next_id = 100

    async def async_load(self):
        pass

    def async_items(self):
        return list(self.items)

    async def async_create_item(self, data):
        self.next_id += 1
        item = {"id": str(self.next_id), "type": data["res_type"], "url": data["url"]}
        self.items.append(item)
        return item

    async def async_update_item(self, item_id, updates):
        item = next(i for i in self.items if i["id"] == item_id)
        item.update(type=updates["res_type"], url=updates["url"])
        return item

    async def async_delete_item(self, item_id):
        self.items = [i for i in self.items if i["id"] != item_id]


class YamlResources:
    """Resources kept in YAML: nothing may be added."""

    loaded = True

    def async_items(self):
        return []


class LovelaceData:  # Home Assistant 2025+ keeps an object, older ones a dict
    def __init__(self, resources):
        self.resources = resources


async def _served(hass, monkeypatch, tmp_path, lovelace):
    hass.config.config_dir = str(tmp_path)
    added = []
    monkeypatch.setattr(
        "homeassistant.components.frontend.add_extra_js_url", lambda _hass, url, es5=False: added.append(url)
    )

    class Http:
        def register_static_path(self, *args):
            pass

        async def async_register_static_paths(self, configs):
            pass

    hass.http = Http()
    hass.config.components.add("frontend")
    if lovelace is not None:
        hass.data["lovelace"] = lovelace
    await frontend.async_register(hass)
    assert len(added) == 1
    return added[0].split("?")[1]


LOADER = "/local/zoneflow/zoneflow-loader.js"


@pytest.mark.asyncio
@pytest.mark.parametrize("as_dict", [True, False])
async def test_the_loader_is_added_to_the_dashboard_resources(hass, monkeypatch, tmp_path, as_dict):
    resources = Resources([{"id": "1", "type": "module", "url": "/hacsfiles/other-card.js"}])
    lovelace = {"resources": resources} if as_dict else LovelaceData(resources)
    query = await _served(hass, monkeypatch, tmp_path, lovelace)
    loader = tmp_path / "www" / "zoneflow" / "zoneflow-loader.js"
    assert loader.read_text(encoding="utf-8") == frontend.LOADER_JS
    assert "/zoneflow_static/zoneflow-card.js" in frontend.LOADER_JS
    assert [i["url"] for i in resources.items] == ["/hacsfiles/other-card.js", f"{LOADER}?{query}"]
    assert resources.items[1]["type"] == "module"


@pytest.mark.asyncio
async def test_an_update_moves_the_resource_to_the_new_version(hass, monkeypatch, tmp_path):
    resources = Resources(
        [
            {"id": "1", "type": "module", "url": f"{LOADER}?v=1.5.0-1"},
            {"id": "2", "type": "module", "url": "/hacsfiles/other-card.js"},
            {"id": "3", "type": "module", "url": f"{LOADER}?v=1.5.0-2"},  # a stray copy
        ]
    )
    (tmp_path / "www" / "zoneflow").mkdir(parents=True)
    (tmp_path / "www" / "zoneflow" / "zoneflow-loader.js").write_text("old", encoding="utf-8")
    query = await _served(hass, monkeypatch, tmp_path, LovelaceData(resources))
    assert [(i["id"], i["url"]) for i in resources.items] == [
        ("1", f"{LOADER}?{query}"),
        ("2", "/hacsfiles/other-card.js"),
    ]
    assert (tmp_path / "www" / "zoneflow" / "zoneflow-loader.js").read_text(encoding="utf-8") == frontend.LOADER_JS


@pytest.mark.asyncio
async def test_nothing_changes_when_the_resource_is_current(hass, monkeypatch, tmp_path):
    resources = Resources()
    query = await _served(hass, monkeypatch, tmp_path, LovelaceData(resources))
    before = [dict(i) for i in resources.items]
    hass.data.pop("zoneflow_frontend_registered")  # the next Home Assistant start
    assert await _served(hass, monkeypatch, tmp_path, LovelaceData(resources)) == query
    assert resources.items == before


@pytest.mark.asyncio
async def test_yaml_dashboards_get_the_file_but_no_resource(hass, monkeypatch, tmp_path):
    # For adding it by hand (README); the resource list itself is theirs.
    await _served(hass, monkeypatch, tmp_path, LovelaceData(YamlResources()))
    assert (tmp_path / "www" / "zoneflow" / "zoneflow-loader.js").is_file()


@pytest.mark.asyncio
async def test_a_loader_problem_leaves_the_card_working(hass, monkeypatch, tmp_path):
    class Broken(Resources):
        async def async_create_item(self, data):
            raise RuntimeError("storage is read-only")

    await _served(hass, monkeypatch, tmp_path, LovelaceData(Broken()))
    assert hass.data.get("zoneflow_frontend_registered")  # the card itself is served


@pytest.mark.asyncio
async def test_removing_the_last_zone_takes_the_loader_away(hass, monkeypatch, tmp_path):
    resources = Resources([{"id": "1", "type": "module", "url": "/hacsfiles/other-card.js"}])
    await _served(hass, monkeypatch, tmp_path, LovelaceData(resources))
    (tmp_path / "www" / "mine.png").write_bytes(b"x")  # the person's own file stays
    await frontend.async_remove_loader(hass)
    assert [i["url"] for i in resources.items] == ["/hacsfiles/other-card.js"]
    assert not (tmp_path / "www" / "zoneflow").exists()
    assert (tmp_path / "www" / "mine.png").is_file()
    await frontend.async_remove_loader(hass)  # twice: nothing to do, no error


@pytest.mark.asyncio
async def test_only_the_last_zone_removed_takes_the_loader_away(hass, monkeypatch, tmp_path):
    from .test_smoke_setup import PUMP, VALVE, make_entry

    removed = []

    async def remove(_hass):
        removed.append(True)

    monkeypatch.setattr(frontend, "async_remove_loader", remove)
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "0")
    first = make_entry(hass, zone_name="One", csv_path=str(tmp_path / "1.csv"))
    second = make_entry(hass, zone_name="Two", csv_path=str(tmp_path / "2.csv"))
    assert await hass.config_entries.async_setup(first.entry_id)
    await hass.async_block_till_done()
    await hass.config_entries.async_remove(first.entry_id)
    assert removed == []
    await hass.config_entries.async_remove(second.entry_id)
    assert removed == [True]
