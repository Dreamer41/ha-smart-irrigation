"""What a plant usually wants per week, from the Plant Variety Database
(Wind River Greens, CC BY 4.0: data/plant_water.json, built by
scripts/build_plant_water_data.py). It only suggests: the card shows it
with its source and the person decides whether to apply it.

The file is read the first time someone looks up a plant, not at start.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from statistics import median
from typing import Any

from homeassistant.core import HomeAssistant

from .const import NUMBER_DEFAULTS, NUMBER_DEFS

DATA_FILE = Path(__file__).parent / "data" / "plant_water.json"
_DATA_KEY = "zoneflow_plant_water"
MAX_RESULTS = 8
MAX_QUERY_LENGTH = 60
TARGET_KEYS = ("target_weekly_mm", "target_weekly_hot_mm", "target_weekly_cool_mm")


def _fold(text: str) -> str:
    """Lower case without accents, quotes or punctuation: 'Jalapeño' matches 'jalapeno'."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", plain.lower()).strip()


def _load() -> dict[str, Any]:
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    for plant in data["plants"]:
        plant["_name"] = _fold(plant["name"])
        plant["_words"] = _fold(f"{plant['name']} {plant['latin']} {plant['category']}").split()
    return data


async def async_get_data(hass: HomeAssistant) -> dict[str, Any]:
    if _DATA_KEY not in hass.data:
        hass.data[_DATA_KEY] = await hass.async_add_executor_job(_load)
    return hass.data[_DATA_KEY]


def _category_summary(plants: list[dict[str, Any]], category: str) -> dict[str, Any] | None:
    """The middle of what a whole kind of plant (all tomatoes, all peppers) wants, from the
    varieties that give a weekly amount; None when fewer than three do."""
    amounts = [p for p in plants if p["category"] == category and p["low_mm"] is not None]
    if len(amounts) < 3:
        return None
    return {
        "kind": "category",
        "name": category.replace("-", " ").capitalize(),
        "category": category,
        "latin": "",
        "low_mm": round(median(p["low_mm"] for p in amounts), 1),
        "high_mm": round(median(p["high_mm"] for p in amounts), 1),
        "note": "",
        "count": len(amounts),
    }


def _public(plant: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "plant",
        "name": plant["name"],
        "category": plant["category"],
        "latin": plant["latin"],
        "low_mm": plant["low_mm"],
        "high_mm": plant["high_mm"],
        "note": plant["note"],
    }


def search(data: dict[str, Any], query: str, limit: int = MAX_RESULTS) -> list[dict[str, Any]]:
    """Plants whose name, Latin name or kind start with each word of the query, best first.
    A query that is a kind of plant ("tomato") starts with the middle of that whole kind."""
    words = _fold(query[:MAX_QUERY_LENGTH]).split()
    if not words:
        return []
    plants = data["plants"]
    hits: list[tuple[tuple[int, int, str], dict[str, Any]]] = []
    for plant in plants:
        if not all(any(word.startswith(w) for word in plant["_words"]) for w in words):
            continue
        name_words = plant["_name"].split()
        # whole words of the name first ("pepper" before "peppermint"), then words that only start
        # like it, then plants that match only through their Latin name or kind
        rank = (
            0 if all(w in name_words for w in words)
            else 1 if all(any(nw.startswith(w) for nw in name_words) for w in words)
            else 2
        )
        name = plant["_name"]
        # a plant that gives an amount comes before one that only has words
        hits.append(((rank, 0 if plant["low_mm"] is not None else 1, name), plant))
    hits.sort(key=lambda hit: hit[0])
    results = [_public(plant) for _, plant in hits[:limit]]
    kind = " ".join(words)
    for category in {p["category"] for p in plants}:
        if kind in (category.replace("-", " "), category.replace("-", " ") + "s"):
            summary = _category_summary(plants, category)
            if summary:
                results.insert(0, summary)
                results = results[:limit]
            break
    return results


def suggested_numbers(low_mm: float, high_mm: float, base: dict[str, float] | None = None) -> dict[str, float]:
    """The three weekly targets (millimetres) for a plant that wants `low_mm`-`high_mm` a week:
    the normal week gets the middle of the range, and the hot and cool weeks keep the proportion
    they have to the normal week in `base` (a plant preset, else the ordinary starting values).
    Each is rounded to its slider's step and kept inside its range."""
    base = base or {}
    start = {key: float(base.get(key, NUMBER_DEFAULTS[key])) for key in TARGET_KEYS}
    middle = (low_mm + high_mm) / 2
    factor = middle / start["target_weekly_mm"] if start["target_weekly_mm"] > 0 else 1.0
    result: dict[str, float] = {}
    for key in TARGET_KEYS:
        _name, low, high, step, _unit = NUMBER_DEFS[key]
        value = middle if key == "target_weekly_mm" else start[key] * factor
        value = round(round(value / step) * step, 2)
        result[key] = min(max(value, low), high)
    return result


def _amount_text(item: dict[str, Any], imperial: bool) -> str:
    def show(mm: float) -> str:
        return str(round(mm / 25.4, 2) if imperial else round(mm, 1))

    low, high = show(item["low_mm"]), show(item["high_mm"])
    return f"{low if low == high else f'{low}-{high}'} {'in' if imperial else 'mm'}"


def picker_options(data: dict[str, Any], imperial: bool, kind_label) -> list[tuple[str, str]]:
    """(value, label) for a searchable picker: first each kind of plant (the middle of all its
    varieties), then every variety that gives a weekly amount, each with that amount in the
    person's units. `kind_label(summary)` words a kind ("Pepper, the middle of all 69 varieties")."""
    plants = data["plants"]
    options: list[tuple[str, str]] = []
    for category in sorted({p["category"] for p in plants if p["low_mm"] is not None}):
        summary = _category_summary(plants, category)
        if summary:
            options.append((f"kind:{category}", f"{kind_label(summary)}: {_amount_text(summary, imperial)}"))
    for index, plant in enumerate(plants):
        if plant["low_mm"] is not None:
            options.append((f"plant:{index}", f"{plant['name']}: {_amount_text(plant, imperial)}"))
    return options


def resolve(data: dict[str, Any], value: str) -> dict[str, Any] | None:
    """The kind or plant a value from picker_options() stands for; None for anything else
    (text typed by hand), which is then searched for."""
    plants = data["plants"]
    kind, _, key = value.partition(":")
    if kind == "kind":
        return _category_summary(plants, key)
    if kind == "plant" and key.isdigit() and int(key) < len(plants) and plants[int(key)]["low_mm"] is not None:
        return _public(plants[int(key)])
    return None
