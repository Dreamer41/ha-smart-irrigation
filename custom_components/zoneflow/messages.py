"""The zone's own words -- phone notifications and the plain-language status
-- in Home Assistant's language.

Home Assistant's translation files cover entity names, setup screens and
errors; texts ZoneFlow builds at run time (notifications, the "why" status)
live in messages/<language>.json instead. Lookup order: the exact language
("pt-BR"), then its base ("pt"), then English -- per text, so a partly
translated file still works. The CSV log stays in English on purpose.
"""
from __future__ import annotations

from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
DATA_KEY = "zoneflow_messages"
_PENDING_KEY = "zoneflow_messages_reloading"
_DIR = Path(__file__).parent / "messages"


def _read(language: str) -> dict[str, Any] | None:
    path = _DIR / f"{language}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _LOGGER.exception("ZoneFlow: could not read %s", path)
        return None


# English is read once, when Home Assistant imports the integration (off the
# event loop), so there's always something to fall back to.
_ENGLISH: dict[str, Any] = _read("en") or {}


def _load(language: str) -> dict[str, Any]:
    english = _ENGLISH
    local: dict[str, Any] = {}
    for candidate in dict.fromkeys((language, language.split("-")[0])):
        if candidate and candidate != "en":
            found = _read(candidate)
            if found:
                local = found
                break
    return {"language": language, "en": english, "local": local}


async def async_setup(hass: HomeAssistant) -> None:
    """Load the catalogs for Home Assistant's current language (once)."""
    language = hass.config.language or "en"
    loaded = hass.data.get(DATA_KEY)
    if loaded and loaded["language"] == language:
        return
    hass.data[DATA_KEY] = await hass.async_add_executor_job(_load, language)


def _lookup(tree: Any, path: str) -> str | None:
    for part in path.split("."):
        if not isinstance(tree, dict):
            return None
        tree = tree.get(part)
    return tree if isinstance(tree, str) else None


def text(hass: HomeAssistant, path: str, **params: Any) -> str:
    """The text at `path` (e.g. "notify.heavy_rain.title") with `params`
    filled in. Falls back to English per text, and to the English template
    if a translation's placeholders don't match."""
    loaded = hass.data.get(DATA_KEY)
    if loaded is None or loaded["language"] != (hass.config.language or "en"):
        # Not loaded yet, or the language changed: reload in the background
        # (once), and use what we have -- or English -- meanwhile.
        if not hass.data.get(_PENDING_KEY):
            hass.data[_PENDING_KEY] = True
            hass.async_create_task(_reload(hass))
        loaded = loaded or {"language": "", "en": _ENGLISH, "local": {}}
    english = _lookup(loaded["en"], path)
    template = _lookup(loaded["local"], path) or english
    if template is None:
        return path
    # A text is shown on a sensor and in notifications: a broken template
    # (wrong placeholder, bad format spec) must never raise.
    try:
        return template.format(**params)
    except Exception:  # noqa: BLE001
        if english is not None and template is not english:
            try:
                return english.format(**params)
            except Exception:  # noqa: BLE001
                pass
        return template


def has(hass: HomeAssistant, path: str) -> bool:
    """Whether `path` names a text (in English, which every text has)."""
    loaded = hass.data.get(DATA_KEY)
    return _lookup(loaded["en"] if loaded else _ENGLISH, path) is not None


async def _reload(hass: HomeAssistant) -> None:
    try:
        await async_setup(hass)
    finally:
        hass.data.pop(_PENDING_KEY, None)


def when(hass: HomeAssistant, moment: datetime, style: str = "datetime") -> str:
    """A local date/time in the language's own format (formats.<style>).
    Day and month names come from the catalog too (formats.days /
    formats.months), not from the system locale, which is usually English."""
    fmt = text(hass, f"formats.{style}")
    if "%" not in fmt:
        fmt = "%Y-%m-%d %H:%M"
    days = text(hass, "formats.days").split(",")
    months = text(hass, "formats.months").split(",")
    if len(days) == 7:
        fmt = fmt.replace("%a", days[moment.weekday()].replace("%", "%%"))
    if len(months) == 12:
        fmt = fmt.replace("%b", months[moment.month - 1].replace("%", "%%"))
    return moment.strftime(fmt)
