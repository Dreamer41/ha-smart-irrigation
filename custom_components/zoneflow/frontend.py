"""Serves the ZoneFlow dashboard cards (frontend/zoneflow-card.js) and loads
them on every dashboard, so they're there without adding a resource by hand
and update with the integration. The version in the URL makes browsers
fetch the new card after an update instead of a cached old one.

Two ways in, because Home Assistant shows dashboards while it is still
starting: a page opened before ZoneFlow has loaded doesn't get the card
the first way, and showed "Configuration error" until it was reloaded.

1. The card's URL is added to every page Home Assistant serves (as early as
   possible: when the integration loads, before any zone sets up).
2. A small loader in /config/www/zoneflow/, listed under Settings ->
   Dashboards -> Resources. Home Assistant loads that list from the first
   second, and the loader keeps trying until ZoneFlow is up. On a normal
   page it asks for the same URL as 1, so the card still loads once.
   Dashboards in YAML mode can't have a resource added for them; docs/GUIDE.md
   says how to add it by hand. Removing the last zone removes both.
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
LOADER_DIR = "zoneflow"  # under /config/www, served as /local/zoneflow
LOADER_FILE = "zoneflow-loader.js"
LOADER_URL = f"/local/{LOADER_DIR}/{LOADER_FILE}"
_DONE_KEY = "zoneflow_frontend_registered"

# The dashboard strategy (`strategy: {type: custom:zoneflow}`). Home Assistant
# waits only 5 seconds for a strategy's element to exist, and the card file
# can be later than that on the first page after a restart or an update, which
# showed "Timeout waiting for strategy element". So the loader (listed in the
# Resources, loaded from the first second) defines the element at once; it
# hands the work to the real strategy in the card file when that is there.
STRATEGY_JS = """\
const defineStrategy = () => {
  const tag = "ll-strategy-dashboard-zoneflow";
  if (window.customElements.get(tag)) return;
  try {
    window.customElements.define(tag, class extends HTMLElement {
      static async generate(config, hass) {
        for (let waited = 0; !window.__zoneflowDashboardStrategy; waited += 250) {
          if (waited >= 60000) throw new Error("The ZoneFlow card did not load.");
          await new Promise((resolve) => setTimeout(resolve, 250));
        }
        return window.__zoneflowDashboardStrategy.generate(config, hass);
      }
    });
  } catch (err) {
    // Known to the registry already: nothing to do.
  }
};
defineStrategy();
for (const delay of [250, 1000, 3000, 10000]) setTimeout(defineStrategy, delay);
"""

LOADER_JS = f"""\
// ZoneFlow Irrigation: loads the ZoneFlow dashboard cards.
// Written by the ZoneFlow integration and listed under Settings ->
// Dashboards -> Resources; removing ZoneFlow removes both.
//
// Home Assistant can show a dashboard while it is still starting, before
// ZoneFlow has loaded. This keeps trying until the cards are there.
{STRATEGY_JS}const base = "{CARD_URL}";
const query = new URL(import.meta.url).search;
let tries = 0;
const load = () => {{
  if (window.customElements.get("zoneflow-overview-card")) return;
  // The same URL as the one on the page: the browser loads it only once.
  const url = query && !tries ? base + query : `${{base}}?t=${{Date.now()}}`;
  import(url).catch(() => {{
    tries += 1;
    if (tries < 120) setTimeout(load, Math.min(1000 * tries, 5000));
  }});
}};
load();
"""


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
    card = Path(__file__).parent / "frontend" / CARD_FILE
    try:
        from homeassistant.components.http import StaticPathConfig  # 2024.7+
    except ImportError:  # older Home Assistant: register_static_path is a
        # blocking call, so it must not run directly on the event loop.
        await hass.async_add_executor_job(hass.http.register_static_path, CARD_URL, str(card), True)
    else:
        await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(card), True)])
    from homeassistant.components.frontend import add_extra_js_url

    # Browsers keep the card for a month: the version (and the file's own
    # time, for a change without a new version) makes them fetch a new one.
    version = (await async_get_integration(hass, DOMAIN)).version
    mtime = int((await hass.async_add_executor_job(card.stat)).st_mtime)
    query = f"?v={version}-{mtime}"
    add_extra_js_url(hass, CARD_URL + query)
    _LOGGER.debug("ZoneFlow card served at %s", CARD_URL)
    return query


def _loader_path(hass: HomeAssistant) -> Path:
    return Path(hass.config.path("www", LOADER_DIR, LOADER_FILE))


def _write_loader(path: Path) -> None:
    if path.is_file() and path.read_text(encoding="utf-8") == LOADER_JS:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(LOADER_JS, encoding="utf-8")


def _storage_resources(hass: HomeAssistant):
    """The dashboard resources Home Assistant keeps itself, or None (no
    dashboards, or resources kept in YAML: nothing we may change)."""
    data = hass.data.get("lovelace")
    if data is None:
        return None
    resources = data.get("resources") if isinstance(data, dict) else getattr(data, "resources", None)
    if resources is None or not hasattr(resources, "async_create_item"):
        return None
    return resources


async def _ours(resources) -> list[dict]:
    if not getattr(resources, "loaded", True):
        await resources.async_load()
        resources.loaded = True
    return [item for item in resources.async_items() if str(item.get("url", "")).split("?")[0] == LOADER_URL]


async def _async_install_loader(hass: HomeAssistant, query: str) -> None:
    await hass.async_add_executor_job(_write_loader, _loader_path(hass))
    resources = _storage_resources(hass)
    if resources is None:
        return
    url = LOADER_URL + query
    ours = await _ours(resources)
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
    """The last zone was deleted: take the loader and its resource away."""
    try:
        resources = _storage_resources(hass)
        if resources is not None:
            for item in await _ours(resources):
                await resources.async_delete_item(item["id"])

        def _delete(path: Path) -> None:
            path.unlink(missing_ok=True)
            try:
                path.parent.rmdir()  # only when nothing else is in it
            except OSError:
                pass

        await hass.async_add_executor_job(_delete, _loader_path(hass))
    except Exception:  # noqa: BLE001
        _LOGGER.warning("ZoneFlow: could not remove the card loader", exc_info=True)
