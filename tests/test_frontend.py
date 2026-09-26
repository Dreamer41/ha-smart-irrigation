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
async def test_card_is_served_and_loaded_once(hass, monkeypatch):
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
