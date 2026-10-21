"""Builds custom_components/zoneflow/data/plant_water.json: what a plant usually
wants per week, taken from the Plant Variety Database (Wind River Greens,
CC BY 4.0, https://github.com/bripatch/plant-variety-database).

    python scripts/build_plant_water_data.py path/to/varieties.csv

Every variety with a water text is kept, in the dataset's own words so the card
can show where a suggestion comes from. Those whose text gives a weekly amount
("1-1.5 inches per week") also get it in millimetres, which is what can be
applied to a zone. The file is small (the full CSV is 2 MB) and is read only when
someone opens the watering suggestions.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from fractions import Fraction
from pathlib import Path

MM_PER_INCH = 25.4
OUT = Path(__file__).resolve().parent.parent / "custom_components" / "zoneflow" / "data" / "plant_water.json"
SOURCE = {
    "name": "Plant Variety Database",
    "author": "Wind River Greens",
    "license": "CC BY 4.0",
    "url": "https://github.com/bripatch/plant-variety-database",
    "license_url": "https://creativecommons.org/licenses/by/4.0/",
    "note": "Only the weekly watering amounts, converted from inches to millimetres.",
}

NUMBER = r"(\d+(?:\.\d+)?(?:\s*/\s*\d+)?|[¼½¾])"
# "1-1.5 inches per week", "1 inch per week", "3/4 inch per week", "1/2 to 3/4 inch per week"
AMOUNT = re.compile(NUMBER + r"(?:\s*(?:-|–|to)\s*" + NUMBER + r")?\s*(?:inch|inches|in\b)", re.IGNORECASE)
WEEKLY = re.compile(r"\bweek(?:ly)?\b", re.IGNORECASE)


FRACTIONS = {"¼": 0.25, "½": 0.5, "¾": 0.75}


def _value(text: str) -> float:
    if text in FRACTIONS:  # a written fraction: the half, quarter and three-quarter signs
        return FRACTIONS[text]
    return float(Fraction(text.replace(" ", "")))


def weekly_range_mm(text: str) -> tuple[float, float] | None:
    """(low, high) millimetres a week from a water text, or None when it gives no weekly amount."""
    if not WEEKLY.search(text):
        return None
    match = AMOUNT.search(text)
    if not match:
        return None
    low = _value(match.group(1))
    high = _value(match.group(2)) if match.group(2) else low
    if low > high:
        low, high = high, low
    if not 0.2 <= low <= 6 or high > 8:  # a typo or a different unit: not a weekly depth in inches
        return None
    return round(low * MM_PER_INCH, 1), round(high * MM_PER_INCH, 1)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def build(rows) -> dict:
    plants = []
    for row in rows:
        text = clean(row.get("water_requirement") or "")
        if not text:
            continue
        found = weekly_range_mm(text)
        plants.append({
            "name": row["name"].strip(),
            "category": (row.get("category") or "").strip(),
            "latin": (row.get("scientific_name") or "").strip(),
            # None for a plant whose text gives no weekly amount ("Moderate, regular
            # watering"): the card shows the words but has nothing to apply.
            "low_mm": found[0] if found else None,
            "high_mm": found[1] if found else None,
            "note": text[:140],
        })
    plants.sort(key=lambda p: (p["category"], p["name"].lower()))
    return {"source": SOURCE, "plants": plants}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    with open(sys.argv[1], encoding="utf-8", newline="") as handle:
        data = build(csv.DictReader(handle))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(data['plants'])} plants, {OUT.stat().st_size / 1024:.0f} KB -> {OUT}")


if __name__ == "__main__":
    main()
