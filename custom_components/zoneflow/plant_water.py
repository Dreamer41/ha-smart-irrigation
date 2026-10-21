"""What a plant usually wants, as suggestions the person applies themself:

- its weekly amount of water, from the Plant Variety Database (Wind River Greens, CC BY 4.0:
  data/plant_water.json, built by scripts/build_plant_water_data.py), and
- its crop factor (Kc), from FAO Irrigation and drainage paper 56, Table 12 (Allen, Pereira, Raes and
  Smith, 1998: data/crop_kc.json, built by scripts/build_crop_kc.py).

The card shows them with their sources. The files are read the first time someone looks up a plant,
not at start.
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
KC_FILE = Path(__file__).parent / "data" / "crop_kc.json"
_DATA_KEY = "zoneflow_plant_water"
MAX_RESULTS = 8
MAX_QUERY_LENGTH = 60
TARGET_KEYS = ("target_weekly_mm", "target_weekly_hot_mm", "target_weekly_cool_mm")


def _fold(text: str) -> str:
    """Lower case without accents, quotes or punctuation: 'Jalapeño' matches 'jalapeno'."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", plain.lower()).strip()


def _match_crop(crops: list[dict[str, Any]], category: str, name: str) -> dict[str, Any] | None:
    """The FAO crop a plant of this kind and name stands for: the first crop (the specific ones come
    first) whose kinds include the plant's and one of whose words is a whole word of its name."""
    padded = f" {name} "
    for crop in crops:
        if crop["categories"] and category not in crop["categories"]:
            continue
        if crop["_words"] and not any(f" {word} " in padded for word in crop["_words"]):
            continue
        return crop
    return None


def _load() -> dict[str, Any]:
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    kc = json.loads(KC_FILE.read_text(encoding="utf-8"))
    data["kc_source"] = kc["source"]
    data["crops"] = crops = kc["crops"]
    for crop in crops:
        crop["_words"] = [_fold(word) for word in crop["words"]]
        crop["_search"] = _fold(" ".join([crop["name"], *crop["words"]])).split()
    for plant in data["plants"]:
        plant["_name"] = _fold(plant["name"])
        plant["_words"] = _fold(f"{plant['name']} {plant['latin']} {plant['category']}").split()
        crop = _match_crop(crops, plant["category"], plant["_name"])
        plant["kc"] = crop["kc_mid"] if crop else None
        plant["crop"] = crop["name"] if crop else None
    return data


async def async_get_data(hass: HomeAssistant) -> dict[str, Any]:
    if _DATA_KEY not in hass.data:
        hass.data[_DATA_KEY] = await hass.async_add_executor_job(_load)
    return hass.data[_DATA_KEY]


def usable(item: dict[str, Any]) -> bool:
    """Whether there is anything to apply: a weekly amount or a crop factor."""
    return item["low_mm"] is not None or item.get("kc") is not None


def _category_summary(data: dict[str, Any], category: str) -> dict[str, Any] | None:
    """The middle of what a whole kind of plant (all peppers, all roses) wants, from the varieties
    that give a weekly amount (None when fewer than three do), with the crop factor of the FAO crop
    that stands for the whole kind, if there is one."""
    plants = data["plants"]
    amounts = [p for p in plants if p["category"] == category and p["low_mm"] is not None]
    crop = next((c for c in data["crops"] if category in c["categories"] and not c["_words"]), None)
    if len(amounts) < 3:
        return None
    return {
        "kind": "category",
        "name": category.replace("-", " ").capitalize(),
        "category": category,
        "latin": "",
        "low_mm": round(median(p["low_mm"] for p in amounts), 1),
        "high_mm": round(median(p["high_mm"] for p in amounts), 1),
        "kc": crop["kc_mid"] if crop else None,
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
        "kc": plant["kc"],
        "note": plant["note"],
    }


def _crop_item(crop: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "crop",
        "name": crop["name"],
        "id": crop["id"],
        "category": "",
        "latin": "",
        "low_mm": None,
        "high_mm": None,
        "kc": crop["kc_mid"],
        "note": f"Kc {crop['kc_ini']} / {crop['kc_mid']} / {crop['kc_end']}",
    }


def search(data: dict[str, Any], query: str, limit: int = MAX_RESULTS) -> list[dict[str, Any]]:
    """A kind of plant ("pepper"), FAO crops and plants whose name, Latin name or kind start with each
    word of the query, best first. A query that is a kind of plant starts with the middle of that
    whole kind."""
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
        # a plant that gives something to apply comes before one that only has words
        hits.append(((rank, 0 if plant["low_mm"] is not None else 1 if plant["kc"] is not None else 2, plant["_name"]), plant))
    hits.sort(key=lambda hit: hit[0])
    plant_results = [_public(plant) for _, plant in hits]
    crop_results = [
        _crop_item(crop) for crop in data["crops"]
        if all(any(word.startswith(w) for word in crop["_search"]) for w in words)
    ]
    results = [*crop_results, *plant_results][:limit]
    kind = " ".join(words)
    for category in {p["category"] for p in plants}:
        if kind in (category.replace("-", " "), category.replace("-", " ") + "s"):
            summary = _category_summary(data, category)
            if summary:
                results.insert(0, summary)
                results = results[:limit]
            break
    return results


def suggested_numbers(
    low_mm: float | None, high_mm: float | None, base: dict[str, float] | None = None, kc: float | None = None
) -> dict[str, float]:
    """What to start a zone with for a plant that wants `low_mm`-`high_mm` a week (millimetres) and
    has the crop factor `kc` (either may be None). The normal week gets the middle of the range, and
    the hot and cool weeks keep the proportion they have to the normal week in `base` (a plant preset,
    else the ordinary starting values). Each is rounded to its slider's step and kept inside its range."""
    base = base or {}
    result: dict[str, float] = {}
    if low_mm is not None and high_mm is not None:
        start = {key: float(base.get(key, NUMBER_DEFAULTS[key])) for key in TARGET_KEYS}
        middle = (low_mm + high_mm) / 2
        factor = middle / start["target_weekly_mm"] if start["target_weekly_mm"] > 0 else 1.0
        for key in TARGET_KEYS:
            _name, low, high, step, _unit = NUMBER_DEFS[key]
            value = middle if key == "target_weekly_mm" else start[key] * factor
            value = round(round(value / step) * step, 2)
            result[key] = min(max(value, low), high)
    if kc is not None:
        _name, low, high, step, _unit = NUMBER_DEFS["crop_coefficient"]
        result["crop_coefficient"] = min(max(round(round(kc / step) * step, 2), low), high)
    return result


def amount_text(item: dict[str, Any], imperial: bool, kc_text) -> str:
    parts = []
    if item["low_mm"] is not None:

        def show(mm: float) -> str:
            return str(round(mm / 25.4, 2) if imperial else round(mm, 1))

        low, high = show(item["low_mm"]), show(item["high_mm"])
        parts.append(f"{low if low == high else f'{low}-{high}'} {'in' if imperial else 'mm'}")
    if item.get("kc") is not None:
        parts.append(kc_text(item["kc"]))
    return ", ".join(parts)


def picker_options(data: dict[str, Any], imperial: bool, texts) -> list[tuple[str, str]]:
    """(value, label) for a searchable picker: each kind of plant (the middle of all its varieties),
    each FAO crop, then every variety that gives a weekly amount, each with what it offers in the
    person's units. `texts` words the labels: `texts.kind(summary)`, `texts.crop(crop)`, `texts.kc(kc)`."""
    plants = data["plants"]
    options: list[tuple[str, str]] = []
    for category in sorted({p["category"] for p in plants if p["low_mm"] is not None}):
        summary = _category_summary(data, category)
        if summary:
            options.append((f"kind:{category}", f"{texts.kind(summary)}: {amount_text(summary, imperial, texts.kc)}"))
    for crop in sorted(data["crops"], key=lambda c: c["name"]):
        item = _crop_item(crop)
        options.append((f"crop:{crop['id']}", f"{texts.crop(crop)}: {amount_text(item, imperial, texts.kc)}"))
    for index, plant in enumerate(plants):
        if plant["low_mm"] is not None:
            options.append((f"plant:{index}", f"{plant['name']}: {amount_text(plant, imperial, texts.kc)}"))
    return options


def resolve(data: dict[str, Any], value: str) -> dict[str, Any] | None:
    """The kind, crop or plant a value from picker_options() stands for; None for anything else
    (text typed by hand), which is then searched for."""
    plants = data["plants"]
    kind, _, key = value.partition(":")
    if kind == "kind":
        return _category_summary(data, key)
    if kind == "crop":
        crop = next((c for c in data["crops"] if c["id"] == key), None)
        return _crop_item(crop) if crop else None
    if kind == "plant" and key.isdigit() and int(key) < len(plants) and plants[int(key)]["low_mm"] is not None:
        return _public(plants[int(key)])
    return None
