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

    python scripts/build_crop_kc.py
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "custom_components" / "zoneflow" / "data" / "crop_kc.json"
SOURCE = {
    "name": "FAO Irrigation and drainage paper 56, Table 12",
    "author": "Allen, Pereira, Raes and Smith (1998)",
    "url": "https://www.fao.org/3/x0490E/x0490e00.htm",
    "note": "Crop coefficients (Kc), typed in from the table. The mid-season value is the full-grown crop.",
}

# id, name, Kc ini, Kc mid, Kc end, kinds of the Plant Variety Database, words of a plant's name
CROPS = [
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
    ("onion", "Onion", 0.7, 1.05, 0.75, ["allium"], ["onion"]),
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
    ("turf_warm", "Lawn, warm-season grass", 0.8, 0.85, 0.85, ["grass", "ground-cover"], ["bermuda", "zoysia", "buffalo", "st augustine", "centipede"]),
]


def build() -> dict:
    return {
        "source": SOURCE,
        "crops": [
            {"id": i, "name": n, "kc_ini": a, "kc_mid": b, "kc_end": c, "categories": cats, "words": words}
            for i, n, a, b, c, cats, words in CROPS
        ],
    }


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(CROPS)} crops -> {OUT}")


if __name__ == "__main__":
    main()
