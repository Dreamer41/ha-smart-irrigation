"""Builds custom_components/zoneflow/data/crop_kc.json: crop coefficients (Kc) from

    Allen, R. G., Pereira, L. S., Raes, D., Smith, M. (1998). Crop evapotranspiration -
    Guidelines for computing crop water requirements. FAO Irrigation and drainage
    paper 56, Table 12. https://www.fao.org/3/x0490E/x0490e00.htm

The values below were typed in from that table (Kc for the initial, mid-season and late-season stage). A
crop the table gives in several variants (with or without ground cover, a range at the end of the season)
is one row here: the variant for a garden, and the middle of a range. `categories` and `words` say which
plants of the Plant Variety Database the crop stands for: a plant matches when its kind is in `categories`
(any kind when empty) and one of `words` is a whole word (or words) of its name (any name when empty); the
first crop that matches wins, so the more specific crops come first.

Where FAO-56 has no crop, the gaps are filled from other published sources, in this order:

    1. extension and peer-reviewed measurements for the crop itself (SOURCES "ifas", "basil", "papaya"), and
    2. for plants that have nothing of their own, an ESTIMATE from the plant's water-use class (low,
       moderate, high), as landscape plant factors do (SOURCES "landscape": WUCOLS and California's MWELO
       define the classes as ranges of ETo; CLASSES takes the middle of each range).

Every row says which source it comes from, and the card says when a value is an estimate.

    python scripts/build_crop_kc.py
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "custom_components" / "zoneflow" / "data" / "crop_kc.json"
SOURCES = {
    "fao56": {
        "short": "FAO-56",
        "name": "FAO Irrigation and drainage paper 56, Table 12",
        "author": "Allen, Pereira, Raes and Smith (1998)",
        "url": "https://www.fao.org/3/x0490E/x0490e00.htm",
        "note": "Crop coefficients (Kc), typed in from the table. The mid-season value is the full-grown crop.",
    },
    "ifas": {
        "short": "UF/IFAS",
        "name": "UF/IFAS Extension EDIS AE456, Crop coefficients of some commercial crops in Florida",
        "author": "University of Florida / IFAS",
        "url": "https://edis.ifas.ufl.edu/publication/AE456",
        "note": "Monthly Kc of subtropical tree crops, which the publication takes from De Azevedo et al. (2003) for mango and Fares (2008) for guava. The highest monthly value is used as the full-grown one.",
    },
    "basil": {
        "short": "study",
        "name": "Determination of water requirement and crop coefficient for basil under controlled greenhouse conditions",
        "author": "Rahimikhoob, Sohrabi and Delshad (2019), Iranian Journal of Soil and Water Research 50(10)",
        "url": "https://doi.org/10.22059/ijswr.2019.280405.668191",
        "note": "A greenhouse micro-lysimeter study: Kc 0.30 initial, 0.86 mid and 0.76 end stage.",
    },
    "papaya": {
        "short": "study",
        "name": "Papaya crop coefficient from a weighing lysimeter",
        "author": "Posse et al. (2008), Engenharia Agricola",
        "url": "https://doaj.org/article/193f95d62f5e45ea8a6379edc4f2ece3",
        "note": "Kc rose from 0.63 to 1.05 from transplanting to 206 days. Taken from the abstract.",
    },
    "derived": {
        "short": "estimate",
        "name": "Weekly amount worked out from the crop factor (1 inch a week at a crop factor of 1.0)",
        "author": "ZoneFlow, from the Plant Variety Database's own figure for most vegetables",
        "url": "https://github.com/Dreamer41/ha-smart-irrigation/blob/main/docs/AREAS-AND-PLANTS.md",
        "note": "An estimate, not a measurement: it follows the crop factor, so it is only as good as that is.",
    },
    "landscape": {
        "short": "estimate",
        "name": "Landscape plant factors: WUCOLS water-use classes (UC Davis) as used in California's MWELO, and the UC ANR plant factor table",
        "author": "University of California; State of California",
        "url": "https://ucanr.edu/site/center-landscape-urban-horticulture/plant-factor-or-crop-coefficient-whats-difference",
        "note": "An estimate, not a measurement: the middle of the range of the plant's water-use class (low 0.1-0.3, moderate 0.4-0.6, high 0.7-1.0 of reference evapotranspiration).",
    },
}

# A plant with a crop factor but no weekly amount of its own gets one worked out from the crop factor: a
# crop factor of 1.0 is taken as 1 inch (25.4 mm) a week, which is what the Plant Variety Database itself
# gives for most vegetables. It lines up with ZoneFlow's own plant types (tomatoes: 1.15 -> 29 mm, the type
# says 30; leafy vegetables 1.0 -> 25 mm, the type says 25).
MM_PER_KC = 25.4

# Estimated crop factor of a plant that has nothing else, by the water-use class its water text starts with
CLASSES = {"low": 0.2, "moderate": 0.5, "high": 0.8}
# The first word of the database's water text that means each class
CLASS_WORDS = {
    "low": ["low", "drought", "dry", "xeric", "minimal"],
    "moderate": ["moderate", "regular", "medium", "average"],
    "high": ["high", "consistent", "moist", "keep", "wet", "bog"],
}
# Plants that are not given an estimate: they live in pots or trays, or are eaten as seedlings
NO_ESTIMATE = ["succulent", "houseplant", "microgreen"]

# id, name, Kc ini, Kc mid, Kc end, kinds of the Plant Variety Database, words of a plant's name, source (FAO-56 when left out)
CROPS: list[tuple] = [
    # vegetables: Solanum and cucumber families
    ("tomato", "Tomato", 0.6, 1.15, 0.8, ["tomato"], []),
    ("pepper", "Pepper (sweet and chili)", 0.6, 1.05, 0.9, ["pepper"], []),
    ("eggplant", "Eggplant", 0.6, 1.05, 0.9, ["eggplant"], []),
    ("cucumber", "Cucumber", 0.6, 1.0, 0.75, ["cucumber"], []),
    ("watermelon", "Watermelon", 0.4, 1.0, 0.75, ["melon"], ["watermelon"]),
    ("cantaloupe", "Cantaloupe", 0.5, 0.85, 0.6, ["melon"], ["cantaloupe", "muskmelon"]),
    ("melon", "Melon (sweet)", 0.5, 1.05, 0.75, ["melon"], []),
    ("pumpkin", "Pumpkin and winter squash", 0.5, 1.0, 0.8, ["squash"], ["pumpkin", "winter", "butternut", "acorn", "kabocha", "hubbard"]),
    ("squash", "Squash and zucchini", 0.5, 0.95, 0.75, ["squash"], []),
    # small vegetables
    ("lettuce", "Lettuce", 0.7, 1.0, 0.95, ["lettuce"], []),
    ("spinach", "Spinach", 0.7, 1.0, 0.95, ["lettuce", "brassica", "herb"], ["spinach"]),
    ("brassica", "Cabbage family (cabbage, broccoli, cauliflower, kale)", 0.7, 1.05, 0.95, ["brassica"], []),
    ("carrot", "Carrot", 0.7, 1.05, 0.95, ["root-vegetable"], ["carrot"]),
    ("radish", "Radish", 0.7, 0.9, 0.85, ["root-vegetable", "brassica"], ["radish", "daikon"]),
    ("celery", "Celery", 0.7, 1.05, 1.0, ["root-vegetable", "herb"], ["celery", "celeriac"]),
    ("garlic", "Garlic", 0.7, 1.0, 0.7, ["allium"], ["garlic"]),
    ("onion_green", "Green onion", 0.7, 1.0, 1.0, ["allium"], ["green onion", "scallion", "bunching"]),
    ("onion", "Onion family", 0.7, 1.05, 0.75, ["allium"], []),
    # roots and tubers
    ("sweet_potato", "Sweet potato", 0.5, 1.15, 0.65, ["root-vegetable"], ["sweet potato"]),
    ("potato", "Potato", 0.5, 1.15, 0.75, ["root-vegetable"], ["potato"]),
    ("beet", "Beet", 0.5, 1.05, 0.95, ["root-vegetable"], ["beet", "beets"]),
    ("turnip", "Turnip and rutabaga", 0.5, 1.1, 0.95, ["root-vegetable", "brassica"], ["turnip", "rutabaga"]),
    ("parsnip", "Parsnip", 0.5, 1.05, 0.95, ["root-vegetable"], ["parsnip"]),
    # legumes
    ("pea", "Pea (fresh)", 0.5, 1.15, 1.1, ["pea"], []),
    ("bean", "Bean (green)", 0.5, 1.05, 0.9, ["bean"], []),
    # corn
    ("sweet_corn", "Sweet corn", 0.3, 1.15, 1.05, ["corn"], []),
    # perennial vegetables, berries, grapes
    ("strawberry", "Strawberry", 0.4, 0.85, 0.75, ["berry"], ["strawberry", "strawberries"]),
    ("mint", "Mint", 0.6, 1.15, 1.1, ["herb"], ["mint", "peppermint", "spearmint"]),
    ("artichoke", "Artichoke", 0.5, 1.0, 0.95, ["flower", "herb", "root-vegetable"], ["artichoke"]),
    ("asparagus", "Asparagus", 0.5, 0.95, 0.3, ["root-vegetable", "allium", "flower"], ["asparagus"]),
    ("berries", "Berry bushes", 0.3, 1.05, 0.5, ["berry"], []),
    ("grapes", "Grapes (table)", 0.3, 0.85, 0.45, ["vine", "fruit-tree", "berry"], ["grape", "grapes"]),
    # fruit and nut trees
    ("avocado", "Avocado", 0.6, 0.85, 0.75, ["tropical", "fruit-tree"], ["avocado"]),
    ("citrus", "Citrus", 0.7, 0.65, 0.7, ["fruit-tree", "tropical"], ["citrus", "orange", "lemon", "lime", "mandarin", "tangerine", "grapefruit", "kumquat"]),
    ("olive", "Olive", 0.65, 0.7, 0.7, ["fruit-tree", "nut-tree", "shade-tree", "ornamental-tree"], ["olive"]),
    ("apple", "Apple, pear and cherry", 0.6, 0.95, 0.75, ["fruit-tree"], ["apple", "pear", "cherry", "quince"]),
    ("stone_fruit", "Peach, apricot and plum", 0.55, 0.9, 0.65, ["fruit-tree"], ["peach", "apricot", "plum", "nectarine"]),
    ("almond", "Almond", 0.4, 0.9, 0.65, ["nut-tree", "fruit-tree"], ["almond"]),
    ("walnut", "Walnut", 0.5, 1.1, 0.65, ["nut-tree"], ["walnut", "pecan"]),
    ("pistachio", "Pistachio", 0.4, 1.1, 0.45, ["nut-tree"], ["pistachio"]),
    ("kiwi", "Kiwi", 0.4, 1.05, 1.05, ["fruit-tree", "vine", "berry"], ["kiwi", "kiwifruit"]),
    ("banana", "Banana (second year)", 1.0, 1.2, 1.1, ["tropical", "fruit-tree"], ["banana", "plantain"]),
    ("palm", "Palm", 0.95, 1.0, 1.0, ["tropical", "ornamental-tree", "shade-tree"], ["palm"]),
    ("coffee", "Coffee", 0.9, 0.95, 0.95, ["tropical", "shrub"], ["coffee"]),
    ("cacao", "Cacao", 1.0, 1.05, 1.05, ["tropical"], ["cacao", "cocoa"]),
    ("conifer", "Conifer trees", 1.0, 1.0, 1.0, ["shade-tree", "ornamental-tree"], ["conifer", "pine", "spruce", "fir"]),
    # turf
    ("turf_cool", "Lawn, cool-season grass", 0.9, 0.95, 0.95, ["grass", "ground-cover"], ["ryegrass", "fescue", "bluegrass", "lawn", "turf"]),
    # tropical fruit: UF/IFAS (Florida) for mango and guava, a lysimeter study for papaya
    ("mango", "Mango", None, 0.8, None, ["tropical", "fruit-tree"], ["mango"], "ifas"),
    ("guava", "Guava", None, 1.0, None, ["tropical", "fruit-tree"], ["guava"], "ifas"),
    ("papaya", "Papaya", 0.63, 1.05, None, ["tropical", "fruit-tree"], ["papaya"], "papaya"),
    # herbs: the one measured value found
    ("basil", "Basil", 0.3, 0.86, 0.76, ["herb"], ["basil"], "basil"),
    ("turf_warm", "Lawn, warm-season grass", 0.8, 0.85, 0.85, ["grass", "ground-cover"], ["bermuda", "zoysia", "buffalo", "st augustine", "centipede"]),
]


# 1.8: the crop's season and root zone, for the seasonal crop factor and the root-zone limit.
#   Lengths of the stages in days: FAO-56 Table 11. Several regions are listed for most crops; the row nearest
#   Mediterranean or temperate gardens is used and named in the note. A crop with no Table 11 row (or an
#   evergreen without a real cycle) is "flat": always Kc mid. "annual" counts from the planting date;
#   "perennial" counts from green-up each year (see const.py KC_GREEN_UP_DOY).
#   Maximum effective rooting depth Zr (m) and the depletion fraction for no stress p (at ETc 5 mm/day): Table 22.
#   Maximum crop height h (m): Table 12 (mid-season; for a range, the middle; for a tree, the garden size).
#   Crops outside the tables (basil, mango, guava, papaya) have estimated values, and the note says so.
# id: (season, l_ini, l_dev, l_mid, l_late, zr_min, zr_max, p, h, note)
SEASONS: dict[str, tuple] = {
    "tomato": ("annual", 30, 40, 45, 30, 0.7, 1.5, 0.40, 0.6, "Table 11, Mediterranean"),
    "pepper": ("annual", 25, 35, 40, 20, 0.5, 1.0, 0.30, 0.7, "Table 11, Europe and Mediterranean"),
    "eggplant": ("annual", 30, 45, 40, 25, 0.7, 1.2, 0.45, 0.8, "Table 11, Mediterranean"),
    "cucumber": ("annual", 20, 30, 40, 15, 0.7, 1.2, 0.50, 0.3, "Table 11, arid region (the only rows given)"),
    "watermelon": ("annual", 20, 30, 30, 30, 0.8, 1.5, 0.40, 0.4, "Table 11, Italy"),
    "cantaloupe": ("annual", 30, 45, 35, 10, 0.9, 1.5, 0.45, 0.3, "Table 11, California"),
    "melon": ("annual", 25, 35, 40, 20, 0.8, 1.5, 0.40, 0.4, "Table 11, Mediterranean"),
    "pumpkin": ("annual", 20, 30, 30, 20, 1.0, 1.5, 0.35, 0.4, "Table 11, Mediterranean"),
    "squash": ("annual", 25, 35, 25, 15, 0.6, 1.0, 0.50, 0.3, "Table 11, Mediterranean and arid"),
    "lettuce": ("annual", 20, 30, 15, 10, 0.3, 0.5, 0.30, 0.3, "Table 11, Mediterranean (the shortest row)"),
    "spinach": ("annual", 20, 20, 15, 5, 0.3, 0.5, 0.20, 0.3, "Table 11, Mediterranean"),
    "brassica": ("annual", 20, 30, 20, 10, 0.5, 0.8, 0.45, 0.4, "Table 11, crucifers (cabbage, cauliflower, broccoli)"),
    "carrot": ("annual", 30, 40, 60, 20, 0.5, 1.0, 0.35, 0.3, "Table 11, Mediterranean"),
    "radish": ("annual", 5, 10, 15, 5, 0.3, 0.5, 0.30, 0.3, "Table 11, Mediterranean and Europe"),
    "celery": ("annual", 25, 40, 45, 15, 0.3, 0.5, 0.20, 0.6, "Table 11, Mediterranean"),
    "garlic": ("flat", None, None, None, None, 0.3, 0.5, 0.30, 0.3, "no stage lengths in Table 11"),
    "onion_green": ("annual", 25, 30, 10, 5, 0.3, 0.6, 0.30, 0.3, "Table 11, Mediterranean"),
    "onion": ("annual", 15, 25, 70, 40, 0.3, 0.6, 0.30, 0.4, "Table 11, Mediterranean"),
    "sweet_potato": ("annual", 20, 30, 60, 40, 1.0, 1.5, 0.65, 0.4, "Table 11, Mediterranean"),
    "potato": ("annual", 30, 35, 50, 30, 0.4, 0.6, 0.35, 0.6, "Table 11, Europe"),
    "beet": ("annual", 15, 25, 20, 10, 0.6, 1.0, 0.50, 0.4, "Table 11, Mediterranean"),
    "turnip": ("flat", None, None, None, None, 0.5, 1.0, 0.50, 0.6, "no stage lengths in Table 11"),
    "parsnip": ("flat", None, None, None, None, 0.5, 1.0, 0.40, 0.4, "no stage lengths in Table 11"),
    "pea": ("annual", 20, 30, 35, 15, 0.6, 1.0, 0.35, 0.5, "Table 11, Mediterranean"),
    "bean": ("annual", 20, 30, 30, 10, 0.5, 0.7, 0.45, 0.4, "Table 11, California and Mediterranean"),
    "sweet_corn": ("annual", 20, 25, 25, 10, 0.8, 1.2, 0.50, 1.5, "Table 11, Mediterranean"),
    "strawberry": ("flat", None, None, None, None, 0.2, 0.3, 0.20, 0.2, "no stage lengths in Table 11"),
    "mint": ("flat", None, None, None, None, 0.4, 0.8, 0.40, 0.7, "no stage lengths in Table 11"),
    "artichoke": ("perennial", 20, 25, 250, 30, 0.6, 0.9, 0.45, 0.7, "Table 11, California, second year"),
    "asparagus": ("perennial", 90, 30, 200, 45, 1.2, 1.8, 0.45, 0.8, "Table 11, Mediterranean"),
    "berries": ("flat", None, None, None, None, 0.6, 1.2, 0.50, 1.5, "no stage lengths in Table 11"),
    "grapes": ("perennial", 20, 50, 75, 60, 1.0, 2.0, 0.35, 2.0, "Table 11, California"),
    "avocado": ("flat", None, None, None, None, 0.5, 1.0, 0.70, 3.0, "evergreen: no stage lengths in Table 11"),
    "citrus": ("perennial", 60, 90, 120, 95, 1.2, 1.5, 0.50, 3.0, "Table 11, Mediterranean; Table 12 height at a 50% canopy"),
    "olive": ("perennial", 30, 90, 60, 90, 1.2, 1.7, 0.65, 4.0, "Table 11, Mediterranean"),
    "apple": ("perennial", 20, 70, 90, 30, 1.0, 2.0, 0.50, 4.0, "Table 11, deciduous orchard, high latitudes"),
    "stone_fruit": ("perennial", 20, 70, 90, 30, 1.0, 2.0, 0.50, 3.0, "Table 11, deciduous orchard, high latitudes"),
    "almond": ("flat", None, None, None, None, 1.0, 2.0, 0.40, 5.0, "no stage lengths in Table 11"),
    "walnut": ("perennial", 20, 10, 130, 30, 1.7, 2.4, 0.50, 4.5, "Table 11, Utah"),
    "pistachio": ("perennial", 20, 60, 30, 40, 1.0, 1.5, 0.40, 4.0, "Table 11, Mediterranean"),
    "kiwi": ("flat", None, None, None, None, 0.7, 1.3, 0.35, 3.0, "no stage lengths in Table 11"),
    "banana": ("flat", None, None, None, None, 0.5, 0.9, 0.35, 4.0, "second year; no yearly cycle"),
    "palm": ("flat", None, None, None, None, 0.7, 1.1, 0.65, 8.0, "evergreen: no stage lengths in Table 11"),
    "coffee": ("flat", None, None, None, None, 0.9, 1.5, 0.40, 2.5, "evergreen: no stage lengths in Table 11"),
    "cacao": ("flat", None, None, None, None, 0.7, 1.0, 0.30, 3.0, "evergreen: no stage lengths in Table 11"),
    "conifer": ("flat", None, None, None, None, 1.0, 1.5, 0.70, 10.0, "evergreen: no stage lengths in Table 11"),
    "turf_cool": ("flat", None, None, None, None, 0.5, 1.0, 0.40, 0.1, "turf grass, Table 12"),
    "mango": ("flat", None, None, None, None, 1.0, 2.0, 0.50, 4.0, "estimate: not in Tables 11, 12 or 22"),
    "guava": ("flat", None, None, None, None, 1.0, 2.0, 0.50, 4.0, "estimate: not in Tables 11, 12 or 22"),
    "papaya": ("flat", None, None, None, None, 0.5, 1.0, 0.50, 3.0, "estimate: not in Tables 11, 12 or 22"),
    "basil": ("flat", None, None, None, None, 0.3, 0.5, 0.40, 0.4, "estimate: not in Tables 11, 12 or 22"),
    "turf_warm": ("flat", None, None, None, None, 0.5, 1.0, 0.50, 0.1, "turf grass, Table 12"),
}


def _season(crop_id: str) -> dict:
    season, l_ini, l_dev, l_mid, l_late, zr_min, zr_max, p, height, note = SEASONS[crop_id]
    return {
        "season": season, "l_ini": l_ini, "l_dev": l_dev, "l_mid": l_mid, "l_late": l_late,
        "root_min_m": zr_min, "root_max_m": zr_max, "p": p, "height_m": height, "season_source": note,
    }


def build() -> dict:
    return {
        "sources": SOURCES,
        "classes": {"values": CLASSES, "words": CLASS_WORDS, "skip": NO_ESTIMATE, "source": "landscape"},
        "derived": {"mm_per_kc": MM_PER_KC, "source": "derived"},
        "crops": [
            {
                "id": row[0], "name": row[1], "kc_ini": row[2], "kc_mid": row[3], "kc_end": row[4],
                "categories": row[5], "words": row[6], "source": row[7] if len(row) > 7 else "fao56",
                **_season(row[0]),
            }
            for row in CROPS
        ],
    }


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(CROPS)} crops -> {OUT}")


if __name__ == "__main__":
    main()
