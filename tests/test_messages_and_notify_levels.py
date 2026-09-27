"""The message catalog (messages.py, messages/<language>.json) and the
per-zone Notifications setting (all / warnings only / none).

- Every notification the controller sends names a catalog text that
  exists, and passes exactly the placeholders that text uses -- checked
  statically over controller.py, so a new notification can't ship with a
  missing key or a typo'd placeholder.
- Lookup falls back per text: exact language, then its base, then English;
  a translation whose placeholders don't match falls back to English
  rather than showing a broken message.
- The Notifications select filters what reaches the phone; the CSV log
  always records everything.
"""
import ast
import json
from pathlib import Path
import string

import pytest

from custom_components.zoneflow import messages
from custom_components.zoneflow.const import DOMAIN

from .scenario_harness import CompressedTime
from .test_scenarios_cycles import _history
from .test_smoke_setup import OUTDOOR_TEMP, PUMP, RAIN_COUNTER, VALVE, make_entry

ROOT = Path(__file__).parent.parent / "custom_components" / "zoneflow"
CATALOG = json.loads((ROOT / "messages" / "en.json").read_text(encoding="utf-8"))


def _placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def _lookup(path: str):
    node = CATALOG
    for part in path.split("."):
        node = node[part]
    return node


def _const_strings(node) -> list[str]:
    """message="x" or message="a" if cond else "b"."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.IfExp):
        return _const_strings(node.body) + _const_strings(node.orelse)
    return []


def _notification_calls():
    tree = ast.parse((ROOT / "controller.py").read_text(encoding="utf-8"))
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call) or getattr(call.func, "attr", None) != "_log_event":
            continue
        kwargs = {kw.arg: kw.value for kw in call.keywords}
        if "message" not in kwargs:
            continue
        params = kwargs.get("params")
        keys = None
        if isinstance(params, ast.Dict) and all(isinstance(k, ast.Constant) for k in params.keys):
            keys = {k.value for k in params.keys}
        elif params is None:
            keys = set()
        yield call.lineno, _const_strings(kwargs["message"]), keys


def test_every_notification_names_a_catalog_text_with_matching_placeholders():
    calls = list(_notification_calls())
    assert len(calls) >= 25
    for lineno, names, keys in calls:
        assert names, f"controller.py:{lineno}: message= must be a literal key"
        used_by_any = set()
        for name in names:
            entry = CATALOG["notify"].get(name)
            assert entry and entry.get("title") and entry.get("message"), f"controller.py:{lineno}: notify.{name} missing"
            used = _placeholders(entry["title"]) | _placeholders(entry["message"])
            used_by_any |= used
            if keys is not None:
                assert used <= keys, f"controller.py:{lineno}: notify.{name} needs {used - keys}"
        if keys is not None:
            # (a message="a" if x else "b" call shares one params dict)
            assert keys <= used_by_any, f"controller.py:{lineno}: {names} never show {keys - used_by_any}"


def test_every_msg_path_in_the_code_exists():
    source = (ROOT / "controller.py").read_text(encoding="utf-8") + (ROOT / "sensor.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    paths = set()
    for call in ast.walk(tree):
        if isinstance(call, ast.Call) and getattr(call.func, "attr", None) in ("_msg", "text"):
            args = [a for a in call.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            paths |= {a.value for a in args if "." in a.value}
    assert paths
    for path in paths:
        assert isinstance(_lookup(path), str), path


def test_every_translation_file_is_valid_and_uses_the_same_placeholders():
    def walk(node, prefix=""):
        for key, value in node.items():
            path = f"{prefix}{key}"
            if isinstance(value, dict):
                yield from walk(value, path + ".")
            else:
                yield path, value

    english = dict(walk(CATALOG))
    for file in (ROOT / "messages").glob("*.json"):
        local = dict(walk(json.loads(file.read_text(encoding="utf-8"))))
        for path, text in local.items():
            assert path in english, f"{file.name}: {path} isn't an English text"
            if not path.startswith("formats."):
                assert _placeholders(text) == _placeholders(english[path]), f"{file.name}: {path}"


@pytest.mark.asyncio
async def test_lookup_falls_back_per_text_and_on_broken_placeholders(hass, monkeypatch):
    local = {"notify": {"heavy_rain": {"title": "Starkregen", "message": "Kaputt {nope}"}}}
    monkeypatch.setattr(messages, "_read", lambda language: local if language == "de" else None)
    hass.config.language = "de-CH"
    await messages.async_setup(hass)

    assert messages.text(hass, "notify.heavy_rain.title") == "Starkregen"  # base language "de"
    # The German template asks for a placeholder nobody passes: English instead.
    english = CATALOG["notify"]["heavy_rain"]["message"]
    params = {name: "X" for name in _placeholders(english)}
    assert messages.text(hass, "notify.heavy_rain.message", **params) == english.format(**params)
    # Not translated at all: English.
    assert messages.text(hass, "cycle.routine") == CATALOG["cycle"]["routine"]
    # Unknown path: the path itself, never an exception.
    assert messages.text(hass, "notify.nothing.title") == "notify.nothing.title"


@pytest.mark.asyncio
async def test_language_change_reloads(hass, monkeypatch):
    monkeypatch.setattr(messages, "_read", lambda language: {"cycle": {"routine": "Routine-FR"}} if language == "fr" else None)
    hass.config.language = "en"
    await messages.async_setup(hass)
    assert messages.text(hass, "cycle.routine") == CATALOG["cycle"]["routine"]
    hass.config.language = "fr"
    messages.text(hass, "cycle.routine")  # notices the change, reloads in the background
    await hass.async_block_till_done()
    assert messages.text(hass, "cycle.routine") == "Routine-FR"


async def _zone(hass, monkeypatch, tmp_path, level):
    sent = []

    async def _notify(call):
        sent.append(call.data["title"])

    hass.services.async_register("notify", "send_message", _notify)
    hass.states.async_set(VALVE, "off")
    hass.states.async_set(PUMP, "999")
    hass.states.async_set(RAIN_COUNTER, "0")
    hass.states.async_set(OUTDOOR_TEMP, "28.0")
    await hass.async_block_till_done()
    entry = make_entry(hass, csv_path=str(tmp_path / "n.csv"), notify_entity="notify.phone")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = hass.data[DOMAIN][entry.entry_id]
    select_id = next(s.entity_id for s in hass.states.async_all("select") if s.entity_id.endswith("_notifications"))
    await hass.services.async_call("select", "select_option", {"entity_id": select_id, "option": level}, blocking=True)
    CompressedTime(hass, [VALVE]).install(monkeypatch)
    return controller, sent


async def _info_then_warning(hass, controller):
    """A completed routine (info), then a daily-cap refusal (warning)."""
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()
    _history(controller, last_routine_days_ago=4, peaks=(30.5, 30.5, 30.5))
    controller.store.state.today_runtime_minutes = controller.number("max_daily_runtime_minutes")
    await controller.run_routine_irrigation()
    await hass.async_block_till_done()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("level", "expected"),
    [
        ("all", ["routine_done", "daily_cap"]),
        ("warnings", ["daily_cap"]),
        ("none", []),
    ],
)
async def test_notifications_setting_filters_the_phone_but_not_the_log(
    hass, fake_valve_services, monkeypatch, tmp_path, level, expected
):
    controller, sent = await _zone(hass, monkeypatch, tmp_path, level)
    assert controller.store.state.notify_level == level
    await _info_then_warning(hass, controller)

    cycle = CATALOG["cycle"]["routine"]
    titles = {key: CATALOG["notify"][key]["title"].format(cycle=cycle) for key in ("routine_done", "daily_cap")}
    assert sent == [titles[key] for key in expected]
    log = (tmp_path / "n.csv").read_text()
    assert "Routine Irrigation Completed" in log and "Max Daily Runtime Cap Reached" in log


@pytest.mark.asyncio
async def test_notifications_setting_survives_a_restart(hass, fake_valve_services, monkeypatch, tmp_path):
    controller, _ = await _zone(hass, monkeypatch, tmp_path, "warnings")
    entry = controller.entry
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    select = next(s for s in hass.states.async_all("select") if s.entity_id.endswith("_notifications"))
    assert select.state == "warnings"


@pytest.mark.asyncio
async def test_a_broken_translation_never_raises(hass, monkeypatch):
    local = {"status": {"next": "Nächste {when.foo}", "snoozed": "{0[1]}"}}
    monkeypatch.setattr(messages, "_read", lambda language: local if language == "de" else None)
    hass.config.language = "de"
    await messages.async_setup(hass)
    assert messages.text(hass, "status.next", when="Mo 05:30") == CATALOG["status"]["next"].format(when="Mo 05:30")
    assert messages.text(hass, "status.snoozed") == CATALOG["status"]["snoozed"]
    assert messages.has(hass, "status.next") and not messages.has(hass, "status.nothing")


@pytest.mark.asyncio
async def test_a_language_change_reloads_once(hass, monkeypatch):
    reads = []

    def _read(language):
        reads.append(language)
        return None

    monkeypatch.setattr(messages, "_read", _read)
    hass.config.language = "nl"
    for _ in range(5):
        messages.text(hass, "cycle.routine")
    await hass.async_block_till_done()
    assert reads.count("nl") == 1


def _walk(node, prefix=""):
    for key, value in node.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            yield from _walk(value, path + ".")
        else:
            yield path, value


LANGUAGES = ("de", "nl", "fr", "es", "it", "fi", "sv", "pl", "pt")


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_language_is_complete(language):
    """Home Assistant's translation file, the message catalog and the card's
    texts: nothing missing, nothing extra, the same placeholders."""
    for folder in ("translations", "messages"):
        english = dict(_walk(json.loads((ROOT / folder / "en.json").read_text(encoding="utf-8"))))
        local = dict(_walk(json.loads((ROOT / folder / f"{language}.json").read_text(encoding="utf-8"))))
        assert local.keys() == english.keys(), (folder, sorted(local.keys() ^ english.keys())[:5])
        for path, text in english.items():
            if not path.startswith("formats."):
                assert _placeholders(local[path]) == _placeholders(text), (folder, path)
    card = (ROOT / "frontend" / "zoneflow-card.js").read_text(encoding="utf-8")
    i18n = json.loads(card[card.index("const I18N = ") + len("const I18N = "): card.index("\n};\n") + 2])
    assert dict(_walk(i18n[language])).keys() == dict(_walk(i18n["en"])).keys()


@pytest.mark.asyncio
@pytest.mark.parametrize("language", LANGUAGES)
async def test_dates_in_every_language(hass, language):
    from datetime import datetime

    hass.config.language = language
    await messages.async_setup(hass)
    catalog = json.loads((ROOT / "messages" / f"{language}.json").read_text(encoding="utf-8"))
    monday = datetime(2026, 9, 28, 5, 30)
    text = messages.when(hass, monday, "weekday_time")
    assert catalog["formats"]["days"].split(",")[0] in text and ("05" in text or "5" in text)
    assert "Mon" not in text or language == "en"


@pytest.mark.parametrize(("regional", "base"), [("pt-BR", "pt"), ("es-419", "es"), ("de-CH", "de")])
def test_regional_copies_match(regional, base):
    """Home Assistant doesn't fall back from a regional language to its base
    for integration texts: those files are copies, kept identical."""
    folder = ROOT / "translations"
    assert (folder / f"{regional}.json").read_text(encoding="utf-8") == (folder / f"{base}.json").read_text(encoding="utf-8")


def test_every_setup_field_has_a_label_and_an_explanation():
    """The grey help line under each field is what people who set ZoneFlow up
    by hand go on: every field of every setup and settings form has one."""
    from custom_components.zoneflow.config_flow import _schema

    english = json.loads((ROOT / "translations" / "en.json").read_text(encoding="utf-8"))
    fields = {str(key.schema) for key in _schema({}).schema}
    for flow, step in (("config", "entities"), ("options", "settings")):
        assert set(english[flow]["step"][step]["data"]) == fields, (flow, step)
    for flow in ("config", "options"):
        for name, step in english[flow]["step"].items():
            labels = step.get("data", {})
            assert set(step.get("data_description", {})) == set(labels), (flow, name)
            assert all(text.strip() for text in step.get("data_description", {}).values()), (flow, name)
