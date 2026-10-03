"""The 1.6 translation round: export the new English texts for a translator
(Gemini or anyone), then merge the translated result back in.

    python scripts/translations_1_6.py export  batch.json [--languages=hu,it,nb] [--missing]
    python scripts/translations_1_6.py merge   reply1.txt [reply2.txt ...]
    python scripts/translations_1_6.py status

The export holds every text 1.6 added (Home Assistant's translations/, the
phone-message catalog in messages/, and the dashboard card), keyed by
"<section>:<path>". The reply is {"<language>": {"<section>:<path>": "text"}} -- strict JSON or, if
that is broken (raw quotes, cut off), one text per line.
Merge checks that every {placeholder} of the English text is kept exactly,
leaves anything else untouched, and copies es -> es-419 and de -> de-CH (those
files are kept identical, see tests/test_messages_and_notify_levels.py).
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "custom_components" / "zoneflow"
CARD = PKG / "frontend" / "zoneflow-card.js"
REGIONAL = {"es-419": "es", "de-CH": "de"}
SECTIONS = ("translations", "messages", "card")

PROMPT = (
    "Translate the English texts of a Home Assistant irrigation / greenhouse integration (ZoneFlow) into "
    "each language listed. Keep every {placeholder} exactly as written (same names, same braces); keep "
    "emoji; keep it short and natural for a smart-home UI; use the formal/neutral register the language "
    "normally uses for software; do not translate entity ids, units like mm or L, or the product name "
    "ZoneFlow. Reply with ONE JSON object: {\"<language code>\": {\"<key>\": \"<translated text>\", ...}, ...}, "
    "one key per line, exactly the keys of the input, none added or dropped. Never put a straight double "
    "quote inside a text: use the language's own typographic quotes instead (for example \u201e \u201c or \u00ab \u00bb). Context: 'Heater Failsafe' is what a heater "
    "does when its temperature sensor fails; 'Misting' is short water pulses in a greenhouse; 'vents' are "
    "roof/side openings; 'Manual hold' means the system leaves a device alone after a person switched it."
)


def _flat(tree, prefix=""):
    for key, value in tree.items():
        if isinstance(value, dict):
            yield from _flat(value, f"{prefix}{key}.")
        else:
            yield f"{prefix}{key}", value


def _card_i18n(text: str) -> dict:
    start = text.index("const I18N = ") + len("const I18N = ")
    return json.loads(text[start: text.index("\n};\n") + 2])


def _git(path: str) -> str:
    return subprocess.check_output(["git", "show", f"HEAD:{path}"], cwd=ROOT).decode("utf-8")


def _current(section: str, language: str) -> dict:
    if section == "card":
        return dict(_flat(_card_i18n(CARD.read_text(encoding="utf-8"))[language]))
    return dict(_flat(json.loads((PKG / section / f"{language}.json").read_text(encoding="utf-8"))))


_LANGUAGE_LINE = re.compile(r'^\s*"([A-Za-z]{2,3}(?:-[A-Za-z0-9]+)?)"\s*:\s*\{\s*$')
_TEXT_LINE = re.compile(r'^\s*"((?:translations|messages|card):[^"]+)"\s*:\s*"(.*)"\s*,?\s*$')


def parse_reply(text: str) -> dict[str, dict[str, str]]:
    """A translator's reply as {language: {key: text}}.

    Strict JSON when it is valid. Otherwise line by line (one text per line,
    as the export asks for), which also survives the two usual faults: a raw
    "quote" inside a text, and a reply cut off half way through.
    """
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return {lang: dict(texts) for lang, texts in data.items() if isinstance(texts, dict)}
    except ValueError:
        pass
    result: dict[str, dict[str, str]] = {}
    language = None
    for line in text.splitlines():
        line = line.strip().removeprefix("```json").removeprefix("```").strip()
        found = _LANGUAGE_LINE.match(line)
        if found:
            language = found.group(1)
            result.setdefault(language, {})
            continue
        found = _TEXT_LINE.match(line)
        if found and language:
            raw = found.group(2)
            # Inner quotes that are not escaped yet, escape them; \" stays.
            raw = re.sub(r'(?<!\\)"', '\\"', raw)
            try:
                result[language][found.group(1)] = json.loads(f'"{raw}"')
            except ValueError:
                print(f"{language}: could not read the line for {found.group(1)}")
    return result


def _clean(text: str) -> str:
    return re.sub("\ufe0f+", "\ufe0f", text).strip()


_SCRIPT_CHECKS = {  # languages written in Latin script must not contain these
    "cyrillic": re.compile("[\u0400-\u04ff]"),
    "cjk": re.compile("[\u4e00-\u9fff]"),
}


def _suspicious(language: str, text: str) -> str | None:
    cyrillic, cjk = bool(_SCRIPT_CHECKS["cyrillic"].search(text)), bool(_SCRIPT_CHECKS["cjk"].search(text))
    if language in ("ru", "uk") and cjk or language == "zh-Hans" and cyrillic:
        return "wrong script"
    if language not in ("ru", "uk", "zh-Hans") and (cyrillic or cjk):
        return "wrong script"
    return None


def _untranslated(language: str, english: dict[str, str]) -> list[str]:
    """New 1.6 keys whose text in the language is still the English one."""
    new = _new_keys()
    out = []
    for section in SECTIONS:
        local = _current(section, language) if section != "card" or language in _card_i18n(CARD.read_text(encoding="utf-8")) else {}
        for path, text in _current(section, "en").items():
            key = f"{section}:{path}"
            if key in new and local.get(path) == text and re.search("[A-Za-z]{4}", text):
                out.append(key)
    return out


def _new_keys() -> set[str]:
    keys = set()
    for section in SECTIONS:
        new = _current(section, "en")
        if section == "card":
            old = dict(_flat(_card_i18n(_git("custom_components/zoneflow/frontend/zoneflow-card.js"))["en"]))
        else:
            old = dict(_flat(json.loads(_git(f"custom_components/zoneflow/{section}/en.json"))))
        keys |= {f"{section}:{p}" for p, t in new.items() if old.get(p) != t}
    return keys


def _languages() -> list[str]:
    return sorted({p.stem for p in (PKG / "translations").glob("*.json")} - {"en"} - set(REGIONAL))


def export(out: Path, languages: list[str] | None = None, missing_only: bool = False) -> None:
    new = _new_keys()
    english = {f"{s}:{p}": t for s in SECTIONS for p, t in _current(s, "en").items()}
    languages = languages or _languages()
    keys = {k for k in english if k in new}
    if missing_only:
        keys = {k for lang in languages for k in _untranslated(lang, english)}
    strings = {k: english[k] for k in english if k in keys}
    out.write_text(
        json.dumps({"prompt": PROMPT, "languages": languages, "strings": strings}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"{len(strings)} texts x {len(languages)} languages -> {out}")


def status() -> None:
    english = {f"{s}:{p}": t for s in SECTIONS for p, t in _current(s, "en").items()}
    total = len(_new_keys())
    for language in _languages():
        left = _untranslated(language, english)
        print(f"{language:8} {total - len(left):3}/{total} translated" + ("" if not left else f"  ({len(left)} still English)"))


def _placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


def _set(tree: dict, path: str, value: str) -> bool:
    node = tree
    parts = path.split(".")
    for part in parts[:-1]:
        node = node.get(part)
        if not isinstance(node, dict):
            return False
    if parts[-1] not in node:
        return False
    node[parts[-1]] = value
    return True


def merge(result_files: list[Path]) -> int:
    result: dict[str, dict[str, str]] = {}
    for file in result_files:
        for language, texts in parse_reply(file.read_text(encoding="utf-8")).items():
            result.setdefault(language, {}).update(texts)
    english = {f"{s}:{p}": t for s in SECTIONS for p, t in _current(s, "en").items()}
    new = _new_keys()
    problems = 0
    for language, texts in result.items():
        if language == "en":
            continue
        applied = {}
        for key, text in texts.items():
            text = _clean(text)
            if key not in english:
                print(f"{language}: unknown key {key}")
                problems += 1
            elif key not in new:
                continue  # an old text the translator sent again: left as it was
            elif _placeholders(text) != _placeholders(english[key]):
                print(f"{language}: placeholders differ in {key}: {text!r}")
                problems += 1
            elif (why := _suspicious(language, text)):
                print(f"{language}: {why} in {key}: {text!r}")
                problems += 1
            else:
                applied[key] = text
        missing = sorted(new - set(applied) - set(_current_translated(language, new, english)))
        targets = [language] + [r for r, base in REGIONAL.items() if base == language]
        for target in targets:
            for section in ("translations", "messages"):
                file = PKG / section / f"{target}.json"
                if not file.exists():  # e.g. messages/ has no regional copies
                    continue
                tree = json.loads(file.read_text(encoding="utf-8"))
                for key, text in applied.items():
                    if key.startswith(f"{section}:"):
                        _set(tree, key.split(":", 1)[1], text)
                file.write_text(json.dumps(tree, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        card_text = CARD.read_text(encoding="utf-8")
        start = card_text.index("const I18N = ") + len("const I18N = ")
        end = card_text.index("\n};\n") + 2
        i18n = json.loads(card_text[start:end])
        if language in i18n:
            for key, text in applied.items():
                if key.startswith("card:"):
                    _set(i18n[language], key.split(":", 1)[1], text)
            CARD.write_text(card_text[:start] + json.dumps(i18n, indent=2, ensure_ascii=False) + card_text[end:], encoding="utf-8")
        print(f"{language}: {len(applied)} merged, {len(missing)} still missing")
    return 1 if problems else 0


def _current_translated(language: str, new: set[str], english: dict[str, str]) -> list[str]:
    still_english = set(_untranslated(language, english))
    return [k for k in new if k not in still_english]


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["export"] and len(args) >= 2:
        langs = next((a.split("=", 1)[1].split(",") for a in args if a.startswith("--languages=")), None)
        export(Path(args[1]), langs, "--missing" in args)
    elif args[:1] == ["merge"] and len(args) >= 2:
        sys.exit(merge([Path(a) for a in args[1:]]))
    elif args[:1] == ["status"]:
        status()
    else:
        print(__doc__)
        sys.exit(2)
