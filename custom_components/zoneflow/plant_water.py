"""What a plant usually wants, as suggestions the person applies themself:

- its weekly amount of water, from the Plant Variety Database (Wind River Greens, CC BY 4.0:
  data/plant_water.json, built by scripts/build_plant_water_data.py), and
- its crop factor (Kc): from FAO Irrigation and drainage paper 56, Table 12 (Allen, Pereira, Raes and
  Smith, 1998) where it has the crop, from extension and published studies for a few more (mango, guava,
  papaya, basil), and for a plant with nothing of its own an estimate from its water-use class, as
  landscape plant factors do (data/crop_kc.json, built by scripts/build_crop_kc.py). Every value says
  which source it comes from, and an estimate says so.

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

# Which of the setup's plant types (PLANT_PRESETS) fits a plant that was picked in the lookup, so that
# What's planted does not have to be answered a second time. Anything not here has no fitting type.
PRESET_BY_CROP = {
    "tomato": "tomatoes", "eggplant": "tomatoes", "pepper": "chilis", "basil": "herbs",
    "mango": "fruit_tree", "guava": "fruit_tree", "papaya": "fruit_tree",
    "lettuce": "leafy_vegetables", "spinach": "leafy_vegetables", "brassica": "leafy_vegetables",
    "celery": "leafy_vegetables", "mint": "herbs", "strawberry": "strawberries",
    "avocado": "fruit_tree", "citrus": "fruit_tree", "olive": "fruit_tree", "apple": "fruit_tree",
    "stone_fruit": "fruit_tree", "almond": "fruit_tree", "walnut": "fruit_tree", "pistachio": "fruit_tree",
    "kiwi": "fruit_tree", "banana": "fruit_tree", "turf_cool": "lawn", "turf_warm": "lawn",
}
PRESET_BY_CATEGORY = {
    "tomato": "tomatoes", "pepper": "chilis", "eggplant": "tomatoes", "lettuce": "leafy_vegetables",
    "brassica": "leafy_vegetables", "herb": "herbs", "berry": "strawberries", "flower": "flowers",
    "rose": "flowers", "native-wildflower": "flowers", "shrub": "shrubs", "grass": "lawn",
    "fruit-tree": "fruit_tree",
}


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
    data["kc_sources"] = kc["sources"]
    data["classes"] = kc["classes"]
    data["derived"] = kc["derived"]
    data["crops"] = crops = kc["crops"]
    for crop in crops:
        crop["_short"] = kc["sources"][crop["source"]]["short"]
        crop["_words"] = [_fold(word) for word in crop["words"]]
        crop["_name_words"] = _fold(crop["name"]).split()
        crop["_aliases"] = {token for word in crop["words"] for token in _fold(word).split()}
    for plant in data["plants"]:
        plant["_name"] = _fold(plant["name"])
        plant["_words"] = _fold(f"{plant['name']} {plant['latin']} {plant['category']}").split()
        crop = _match_crop(crops, plant["category"], plant["_name"])
        plant["kc"] = crop["kc_mid"] if crop else None
        plant["crop"] = crop["name"] if crop else None
        plant["crop_id"] = crop["id"] if crop else None
        plant["kc_source"] = crop["source"] if crop else None
        plant["kc_estimate"] = False
        if crop is None and plant["low_mm"] is None:
            # nothing of its own: an estimate from the water-use class its water text starts with
            estimate = _estimate_kc(data["classes"], plant["category"], plant["note"])
            if estimate is not None:
                plant["kc"], plant["kc_source"], plant["kc_estimate"] = estimate, data["classes"]["source"], True
        plant["mm_estimate"] = False
        if plant["low_mm"] is None and plant["kc"] is not None:
            # no weekly amount in the database: one worked out from the crop factor
            plant["low_mm"] = plant["high_mm"] = round(plant["kc"] * data["derived"]["mm_per_kc"], 1)
            plant["mm_estimate"] = True
    return data


def _estimate_kc(classes: dict[str, Any], category: str, note: str) -> float | None:
    """A crop factor from the water-use class (low, moderate, high) the plant's water text starts with
    ("High, consistent moisture needed", "Drought tolerant"); None for plants kept in pots or trays and
    for texts that start with none of the class words."""
    if category in classes["skip"]:
        return None
    first = re.match(r"^[^a-z]*([a-z]+)", (note or "").lower())
    if not first:
        return None
    for name, words in classes["words"].items():
        if first.group(1) in words:
            return classes["values"][name]
    return None


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
    amounts = [p for p in plants if p["category"] == category and p["low_mm"] is not None and not p["mm_estimate"]]
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
        "kc_source": crop["source"] if crop else None,
        "kc_estimate": False,
        "mm_estimate": False,
        "preset": PRESET_BY_CATEGORY.get(category),
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
        "kc_source": plant["kc_source"],
        "kc_estimate": plant["kc_estimate"],
        "mm_estimate": plant["mm_estimate"],
        "preset": PRESET_BY_CROP.get(plant["crop_id"]) or PRESET_BY_CATEGORY.get(plant["category"]),
        "note": plant["note"],
    }


def _crop_item(crop: dict[str, Any], mm_per_kc: float = 25.4) -> dict[str, Any]:
    return {
        "kind": "crop",
        "name": crop["name"],
        "id": crop["id"],
        "category": "",
        "latin": "",
        "low_mm": round(crop["kc_mid"] * mm_per_kc, 1),
        "high_mm": round(crop["kc_mid"] * mm_per_kc, 1),
        "mm_estimate": True,
        "kc": crop["kc_mid"],
        "kc_source": crop["source"],
        "kc_estimate": False,
        "preset": PRESET_BY_CROP.get(crop["id"]),
        "note": "Kc " + " / ".join("-" if v is None else str(v) for v in (crop["kc_ini"], crop["kc_mid"], crop["kc_end"])),
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
        measured = plant["low_mm"] is not None and not plant["mm_estimate"]
        hits.append(((rank, 0 if measured else 1 if plant["low_mm"] is not None else 2, plant["_name"]), plant))
    hits.sort(key=lambda hit: hit[0])
    plant_results = [_public(plant) for _, plant in hits]
    crop_results = [
        _crop_item(crop, data["derived"]["mm_per_kc"]) for crop in data["crops"]
        # words that start like the crop's name, or are exactly one of the names it goes by ("lemon" is
        # citrus; "pepper" does not find mint because of "peppermint")
        if all(any(word.startswith(w) for word in crop["_name_words"]) or w in crop["_aliases"] for w in words)
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


def amount_text(item: dict[str, Any], imperial: bool, kc_text, about_text=lambda text: text) -> str:
    parts = []
    if item["low_mm"] is not None:

        def show(mm: float) -> str:
            return str(round(mm / 25.4, 2) if imperial else round(mm, 1))

        low, high = show(item["low_mm"]), show(item["high_mm"])
        text = f"{low if low == high else f'{low}-{high}'} {'in' if imperial else 'mm'}"
        parts.append(about_text(text) if item.get("mm_estimate") else text)
    if item.get("kc") is not None:
        parts.append(kc_text(item["kc"], bool(item.get("kc_estimate"))))
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
            options.append((f"kind:{category}", f"{texts.kind(summary)}: {amount_text(summary, imperial, texts.kc, texts.about)}"))
    for crop in sorted(data["crops"], key=lambda c: c["name"]):
        item = _crop_item(crop, data["derived"]["mm_per_kc"])
        options.append((f"crop:{crop['id']}", f"{texts.crop(crop)}: {amount_text(item, imperial, texts.kc, texts.about)}"))
    for index, plant in enumerate(plants):
        if plant["low_mm"] is not None and not plant["mm_estimate"]:  # the list holds measured amounts; the rest is searched
            options.append((f"plant:{index}", f"{plant['name']}: {amount_text(plant, imperial, texts.kc, texts.about)}"))
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
        return _crop_item(crop, data["derived"]["mm_per_kc"]) if crop else None
    if kind == "plant" and key.isdigit() and int(key) < len(plants) and plants[int(key)]["low_mm"] is not None:
        return _public(plants[int(key)])
    return None


def sources_for(data: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The crop factor sources behind a list of results (id -> source), for the credit under them."""
    used = {item["kc_source"] for item in results if item.get("kc") is not None and item.get("kc_source")}
    if any(item.get("mm_estimate") for item in results):
        used.add(data["derived"]["source"])
    return {key: source for key, source in data["kc_sources"].items() if key in used}
