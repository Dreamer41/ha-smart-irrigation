"""Serves the ZoneFlow dashboard card (frontend/zoneflow-card.js) and loads
it on every dashboard, so it's there without adding a resource by hand and
updates with the integration. The version in the URL makes browsers fetch
the new card after an update instead of a cached old one.
"""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
URL_BASE = "/zoneflow_static"
CARD_FILE = "zoneflow-card.js"
_DONE_KEY = "zoneflow_frontend_registered"


async def async_register(hass: HomeAssistant) -> None:
    """Once per Home Assistant run (not per zone). The card is a nicety: a
    failure here is logged and never stops a zone from setting up."""
    if hass.data.get(_DONE_KEY) or getattr(hass, "http", None) is None:
        return
    if "frontend" not in hass.config.components:
        return  # e.g. a setup without the frontend: nothing to show it in
    try:
        await _register(hass)
    except Exception:  # noqa: BLE001
        _LOGGER.warning("ZoneFlow: could not load the dashboard card", exc_info=True)
        return
    hass.data[_DONE_KEY] = True


async def _register(hass: HomeAssistant) -> None:
    card = Path(__file__).parent / "frontend" / CARD_FILE
    url = f"{URL_BASE}/{CARD_FILE}"
    try:
        from homeassistant.components.http import StaticPathConfig  # 2024.7+
    except ImportError:  # older Home Assistant
        hass.http.register_static_path(url, str(card), True)
    else:
        await hass.http.async_register_static_paths([StaticPathConfig(url, str(card), True)])
    from homeassistant.components.frontend import add_extra_js_url

    # Browsers keep the card for a month: the version (and the file's own
    # time, for a change without a new version) makes them fetch a new one.
    version = (await async_get_integration(hass, DOMAIN)).version
    mtime = int((await hass.async_add_executor_job(card.stat)).st_mtime)
    add_extra_js_url(hass, f"{url}?v={version}-{mtime}")
    _LOGGER.debug("ZoneFlow card served at %s", url)
