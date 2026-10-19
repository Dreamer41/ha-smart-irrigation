"""Serves the ZoneFlow dashboard cards (frontend/zoneflow-card.js) and loads
them on every dashboard, so they're there without adding a resource by hand
and update with the integration. The version in the URL makes browsers
fetch the new card after an update instead of a cached old one.

Two ways in, because Home Assistant shows dashboards while it is still
starting: a page opened before ZoneFlow has loaded doesn't get the card
the first way, and showed "Configuration error" until it was reloaded.

1. The card's URL is added to every page Home Assistant serves (as early as
   possible: when the integration loads, before any zone sets up).
2. A small loader (frontend/zoneflow-loader.js, served from /zoneflow_static/
   next to the card), listed under Settings -> Dashboards -> Resources. Home
   Assistant loads that list from the first second, and the loader keeps
   trying until ZoneFlow is up. On a normal page it asks for the same URL as
   1, so the card still loads once. Dashboards in YAML mode can't have a
   resource added for them; docs/GUIDE.md says how to add it by hand.
   Removing the last zone removes the resource.

Nothing is written outside the integration's own folder. Versions up to 1.7.4
put the loader in /config/www/zoneflow/ (served as /local/zoneflow/); on
start that file and its resource are removed.
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
CARD_URL = f"{URL_BASE}/{CARD_FILE}"
LOADER_FILE = "zoneflow-loader.js"
LOADER_URL = f"{URL_BASE}/{LOADER_FILE}"
# Up to 1.7.4 the loader was a file written into the person's /config/www.
OLD_LOADER_DIR = "zoneflow"
OLD_LOADER_URL = f"/local/{OLD_LOADER_DIR}/{LOADER_FILE}"
_DONE_KEY = "zoneflow_frontend_registered"
_STATIC_KEY = "zoneflow_frontend_static_paths"  # a path can be registered only once

async def async_register(hass: HomeAssistant) -> None:
    """Once per Home Assistant run (not per zone). The card is a nicety: a
    failure here is logged and never stops a zone from setting up."""
    if hass.data.get(_DONE_KEY) or getattr(hass, "http", None) is None:
        return
    if "frontend" not in hass.config.components:
        return  # e.g. a setup without the frontend: nothing to show it in
    # Zones set up at the same time: the first one does it (the flag is
    # set before the first await, so the others see it straight away).
    hass.data[_DONE_KEY] = True
    try:
        query = await _register(hass)
    except Exception:  # noqa: BLE001
        hass.data.pop(_DONE_KEY, None)  # try again with the next zone
        _LOGGER.warning("ZoneFlow: could not load the dashboard card", exc_info=True)
        return
    try:
        await _async_install_loader(hass, query)
    except Exception:  # noqa: BLE001
        _LOGGER.warning(
            "ZoneFlow: could not add the card loader to the dashboard resources; "
            "the cards may need a page reload right after Home Assistant starts",
            exc_info=True,
        )


async def _register(hass: HomeAssistant) -> str:
    folder = Path(__file__).parent / "frontend"
    card = folder / CARD_FILE
    loader = folder / LOADER_FILE
    if not hass.data.get(_STATIC_KEY):  # a retry (next zone) must not register them again
        # The loader is tiny and its address carries no version in a YAML
        # dashboard, so it is served without long-lived cache headers.
        try:
            from homeassistant.components.http import StaticPathConfig  # 2024.7+
        except ImportError:  # older Home Assistant: register_static_path is a
            # blocking call, so it must not run directly on the event loop.
            await hass.async_add_executor_job(hass.http.register_static_path, CARD_URL, str(card), True)
            await hass.async_add_executor_job(hass.http.register_static_path, LOADER_URL, str(loader), False)
        else:
            await hass.http.async_register_static_paths(
                [StaticPathConfig(CARD_URL, str(card), True), StaticPathConfig(LOADER_URL, str(loader), False)]
            )
        hass.data[_STATIC_KEY] = True
    from homeassistant.components.frontend import add_extra_js_url

    # Browsers keep the card for a month: the version (and the file's own
    # time, for a change without a new version) makes them fetch a new one.
    version = (await async_get_integration(hass, DOMAIN)).version
    mtime = int((await hass.async_add_executor_job(card.stat)).st_mtime)
    query = f"?v={version}-{mtime}"
    add_extra_js_url(hass, CARD_URL + query)
    _LOGGER.debug("ZoneFlow card served at %s", CARD_URL)
    return query


def _remove_old_loader(hass: HomeAssistant) -> None:
    """The file older versions wrote into /config/www (only ours, and the
    folder only when nothing else is in it)."""
    path = Path(hass.config.path("www", OLD_LOADER_DIR, LOADER_FILE))
    if not path.is_file():
        return
    try:
        path.unlink(missing_ok=True)
        path.parent.rmdir()  # only when nothing else is in it
    except OSError:
        _LOGGER.debug("ZoneFlow: could not remove the old loader file %s", path, exc_info=True)


def _resources_any(hass: HomeAssistant):
    data = hass.data.get("lovelace")
    if data is None:
        return None
    return data.get("resources") if isinstance(data, dict) else getattr(data, "resources", None)


def _storage_resources(hass: HomeAssistant):
    """The dashboard resources Home Assistant keeps itself, or None (no
    dashboards, or resources kept in YAML: nothing we may change)."""
    resources = _resources_any(hass)
    if resources is None or not hasattr(resources, "async_create_item"):
        return None
    return resources


async def _ours(resources, *urls: str) -> list[dict]:
    if not getattr(resources, "loaded", True):
        await resources.async_load()
        resources.loaded = True
    return [item for item in resources.async_items() if str(item.get("url", "")).split("?")[0] in urls]


async def _async_install_loader(hass: HomeAssistant, query: str) -> None:
    resources = _storage_resources(hass)
    if resources is None:
        # Resources kept in YAML are theirs. One that still points at the old
        # file keeps the file (and is told to move), or the cards would lose
        # their loader without a word.
        yaml_items = _resources_any(hass)
        if yaml_items is not None and await _ours(yaml_items, OLD_LOADER_URL):
            _LOGGER.warning(
                "ZoneFlow: your YAML dashboard resources still use %s; change it to %s "
                "(the old file is kept until you do)", OLD_LOADER_URL, LOADER_URL,
            )
            return
        await hass.async_add_executor_job(_remove_old_loader, hass)
        return
    await hass.async_add_executor_job(_remove_old_loader, hass)
    url = LOADER_URL + query
    ours = await _ours(resources, LOADER_URL, OLD_LOADER_URL)
    # The resource of an older version is moved to the new address.
    keep = next((item for item in ours if item["url"] == url), None)
    if keep is None and ours:
        keep = ours[0]
        await resources.async_update_item(keep["id"], {"res_type": "module", "url": url})
    elif keep is None:
        await resources.async_create_item({"res_type": "module", "url": url})
    for item in ours:
        if item is not keep:
            await resources.async_delete_item(item["id"])


async def async_remove_loader(hass: HomeAssistant) -> None:
    """The last zone was deleted: take the loader's resource away."""
    try:
        resources = _storage_resources(hass)
        if resources is not None:
            for item in await _ours(resources, LOADER_URL, OLD_LOADER_URL):
                await resources.async_delete_item(item["id"])
        await hass.async_add_executor_job(_remove_old_loader, hass)
    except Exception:  # noqa: BLE001
        _LOGGER.warning("ZoneFlow: could not remove the card loader", exc_info=True)
    hass.data.pop(_DONE_KEY, None)  # a zone added again in this run installs it again
