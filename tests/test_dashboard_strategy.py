"""The dashboard strategy (`strategy: {type: custom:zoneflow}`) in the card
file: an overview tab and one tab per zone, built from the zones that exist.
Run in Node with a tiny stand-in for the browser, so it needs `node` (the
GitHub runners have it; the test is skipped without)."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

CARD = Path(__file__).parent.parent / "custom_components" / "zoneflow" / "frontend" / "zoneflow-card.js"

HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const registry = {};
const sandbox = {
  window: { customElements: { get: (t) => registry[t], define: (t, c) => { registry[t] = c; } }, customCards: [], addEventListener() {} },
  HTMLElement: class {},
  document: { createElement: () => ({}) },
  console: { info() {} },
  setTimeout: () => 0,
  Intl, Object, Set, Map, WeakMap, Promise, Math, JSON, Date, String, Number, Array,
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), sandbox);
const strategy = registry["ll-strategy-dashboard-zoneflow"];
const hass = JSON.parse(process.argv[3]);
strategy.generate({ type: "custom:zoneflow" }, hass).then((out) => console.log(JSON.stringify(out)));
"""


def _zone(entities, states, device, name, plant, climate=False, hidden_climate=False):
    status = f"sensor.{name.lower().replace(' ', '_')}_status"
    entities[status] = {
        "entity_id": status, "device_id": device, "platform": "zoneflow", "translation_key": "status",
    }
    states[status] = {"entity_id": status, "state": "idle", "attributes": {"plant": plant}}
    if climate:
        gh = f"sensor.{name.lower().replace(' ', '_')}_climate"
        entities[gh] = {"entity_id": gh, "device_id": device, "platform": "zoneflow", "translation_key": "greenhouse_status",
                        "hidden": hidden_climate}


def _run(tmp_path, hass):
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    harness = tmp_path / "harness.js"
    harness.write_text(HARNESS, encoding="utf-8")
    done = subprocess.run(
        ["node", str(harness), str(CARD), json.dumps(hass)], capture_output=True, text=True, timeout=60, check=True
    )
    return json.loads(done.stdout)


def test_overview_first_then_one_tab_per_zone_sorted_by_name(tmp_path):
    entities, states, devices = {}, {}, {}
    _zone(entities, states, "d1", "Tomatoes", "tomatoes")
    _zone(entities, states, "d2", "Cherry Trees", "fruit_tree")
    _zone(entities, states, "d3", "Tunnel", "tomatoes", climate=True)
    for device, name in (("d1", "Tomatoes"), ("d2", "Cherry Trees"), ("d3", "Tunnel")):
        devices[device] = {"name": name}
    out = _run(tmp_path, {"entities": entities, "states": states, "devices": devices, "locale": {"language": "en"}})

    views = out["views"]
    assert [v["path"] for v in views] == ["overview", "cherry-trees", "tomatoes", "tunnel"]
    assert views[0]["cards"] == [{"type": "custom:zoneflow-overview-card"}]
    assert views[0]["type"] == "panel" and views[1]["type"] == "panel"  # the whole width
    assert views[0]["title"] == "Garden"
    assert views[1]["cards"] == [{"type": "custom:zoneflow-card", "device_id": "d2"}]
    assert views[1]["icon"] == "mdi:tree"
    assert views[2]["icon"] == "mdi:food-apple"
    assert views[3]["icon"] == "mdi:greenhouse"  # a climate zone


def test_zone_names_that_clash_or_are_not_plain_ascii_get_unique_paths(tmp_path):
    entities, states, devices = {}, {}, {}
    _zone(entities, states, "d1", "Kasvihuone", "herbs")
    _zone(entities, states, "d2", "Kasvihuöne", "herbs")
    _zone(entities, states, "d3", "Overview", "lawn")
    devices.update({"d1": {"name": "Kasvihuone"}, "d2": {"name": "Kasvihuöne"}, "d3": {"name": "Overview"}})
    out = _run(tmp_path, {"entities": entities, "states": states, "devices": devices, "locale": {"language": "fi"}})
    paths = [v["path"] for v in out["views"]]
    assert len(paths) == len(set(paths)) == 4
    assert paths[0] == "overview"


def test_no_zones_shows_a_friendly_page(tmp_path):
    out = _run(tmp_path, {"entities": {}, "states": {}, "devices": {}, "locale": {"language": "en"}})
    assert len(out["views"]) == 1
    assert out["views"][0]["cards"][0]["type"] == "markdown"


STUB_HARNESS = r"""
const vm = require("vm");
const registry = {};
let timers = 0;
const sandbox = {
  window: { customElements: { get: (t) => registry[t], define: (t, c) => { registry[t] = c; } } },
  HTMLElement: class {},
  setTimeout: (fn, ms) => globalThis.setTimeout(fn, Math.min(ms, 5)),
  Promise, Error, console,
};
sandbox.window.setTimeout = sandbox.setTimeout;
vm.createContext(sandbox);
vm.runInContext(process.argv[2], sandbox);
const stub = registry["ll-strategy-dashboard-zoneflow"];
(async () => {
  if (!stub) { console.log("NO ELEMENT"); return; }
  // The real strategy arrives later than the page asked for it.
  const pending = stub.generate({ type: "custom:zoneflow" }, { who: "hass" });
  setTimeout(() => {
    sandbox.window.__zoneflowDashboardStrategy = {
      generate: async (config, hass) => ({ views: ["from the real strategy"], config, hass }),
    };
  }, 30);
  const out = await pending;
  console.log(JSON.stringify(out));
})();
"""


def test_the_loader_registers_the_strategy_at_once_and_waits_for_the_card(tmp_path):
    """Home Assistant waits only 5 s for a strategy element; the loader
    defines it immediately and hands over once the card file has loaded."""
    from custom_components.zoneflow import frontend

    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    harness = tmp_path / "stub.js"
    harness.write_text(STUB_HARNESS, encoding="utf-8")
    done = subprocess.run(
        ["node", str(harness), frontend.STRATEGY_JS], capture_output=True, text=True, timeout=60, check=True
    )
    out = json.loads(done.stdout.strip().splitlines()[-1])
    assert out["views"] == ["from the real strategy"]
    assert out["config"] == {"type": "custom:zoneflow"} and out["hass"] == {"who": "hass"}


def test_the_card_file_hands_its_strategy_to_the_loader_stub():
    card = CARD.read_text(encoding="utf-8")
    assert "window.__zoneflowDashboardStrategy = ZoneFlowDashboardStrategy" in card


def test_a_greenhouse_tab_holds_its_crops(tmp_path):
    entities, states, devices = {}, {}, {}
    _zone(entities, states, "gh", "Tunnel", "custom", climate=True)
    _zone(entities, states, "c1", "Tomatoes", "tomatoes", climate=True, hidden_climate=True)  # crops: hidden climate
    _zone(entities, states, "c2", "Peppers", "chilis")
    _zone(entities, states, "o1", "Lawn", "lawn")
    _zone(entities, states, "s1", "Shed", "herbs", climate=True, hidden_climate=True)  # waters only, on its own
    for crop in ("sensor.tomatoes_status", "sensor.peppers_status"):
        states[crop]["attributes"]["greenhouse"] = {"name": "Tunnel", "device_id": "gh"}
    devices.update({"gh": {"name": "Tunnel"}, "c1": {"name": "Tomatoes"}, "c2": {"name": "Peppers"}, "o1": {"name": "Lawn"}, "s1": {"name": "Shed"}})
    out = _run(tmp_path, {"entities": entities, "states": states, "devices": devices, "locale": {"language": "en"}})
    views = {v["path"]: v for v in out["views"]}
    assert set(views) == {"overview", "lawn", "shed", "tunnel"}  # crops have no tab of their own
    assert views["shed"]["icon"] == "mdi:sprout"  # a hidden climate status is no greenhouse
    assert views["tunnel"]["icon"] == "mdi:greenhouse"
    assert "type" not in views["tunnel"]  # several cards: side by side
    assert views["tunnel"]["cards"] == [
        {"type": "custom:zoneflow-card", "device_id": "gh", "show_crops": False},
        {"type": "custom:zoneflow-card", "device_id": "c2"},  # Peppers, then Tomatoes: by name
        {"type": "custom:zoneflow-card", "device_id": "c1"},
    ]


def _with_area(states, name, area):
    states[f"sensor.{name.lower().replace(' ', '_')}_status"]["attributes"]["garden_area"] = area


def test_garden_areas_get_one_tab_each_and_the_rest_keep_their_own(tmp_path):
    entities, states, devices = {}, {}, {}
    for device, name, plant, area in (
        ("d1", "Tomatoes", "tomatoes", "Backyard"),
        ("d2", "Chilis", "chilis", "Backyard"),
        ("d3", "Lawn", "lawn", "Front yard"),
        ("d4", "Shed", "herbs", None),
    ):
        _zone(entities, states, device, name, plant)
        _with_area(states, name, area)
        devices[device] = {"name": name}
    out = _run(tmp_path, {"entities": entities, "states": states, "devices": devices, "locale": {"language": "en"}})
    views = out["views"]
    assert [v["path"] for v in views] == ["overview", "backyard", "front-yard", "shed"]
    assert views[1]["title"] == "Backyard" and views[1]["icon"] == "mdi:flower-outline"
    assert views[1]["cards"] == [  # its zones side by side, by name
        {"type": "custom:zoneflow-card", "device_id": "d2"},
        {"type": "custom:zoneflow-card", "device_id": "d1"},
    ]
    assert "type" not in views[1]
    assert views[2]["type"] == "panel"  # one zone: the whole width
    assert views[3]["title"] == "Shed" and views[3]["cards"] == [{"type": "custom:zoneflow-card", "device_id": "d4"}]


def test_a_greenhouse_and_its_crops_have_a_tab_of_their_own_apart_from_the_area(tmp_path):
    entities, states, devices = {}, {}, {}
    _zone(entities, states, "gh", "Tunnel", "custom", climate=True)
    _zone(entities, states, "c1", "Tomatoes", "tomatoes", climate=True, hidden_climate=True)
    _zone(entities, states, "o1", "Lawn", "lawn")
    states["sensor.tomatoes_status"]["attributes"]["greenhouse"] = {"name": "Tunnel", "device_id": "gh"}
    states["sensor.tunnel_status"]["attributes"]["zone_type"] = "greenhouse"
    states["sensor.tomatoes_status"]["attributes"]["zone_type"] = "greenhouse"
    states["sensor.lawn_status"]["attributes"]["zone_type"] = "outdoor"
    states["sensor.tunnel_status"]["attributes"].update(pause_entity="switch.tunnel_pause", snooze_entity="button.tunnel_snooze_today")
    for name in ("Tunnel", "Tomatoes", "Lawn"):
        _with_area(states, name, "Backyard")  # even in the area, the greenhouse stands apart
    devices.update({"gh": {"name": "Tunnel"}, "c1": {"name": "Tomatoes"}, "o1": {"name": "Lawn"}})
    out = _run(tmp_path, {"entities": entities, "states": states, "devices": devices, "locale": {"language": "en"}})
    assert [v["path"] for v in out["views"]] == ["overview", "backyard", "tunnel"]
    assert out["views"][1]["cards"] == [{"type": "custom:zoneflow-card", "device_id": "o1"}]  # the outdoor zones only
    assert out["views"][2]["icon"] == "mdi:greenhouse"
    assert out["views"][2]["cards"] == [
        # the greenhouse's own Pause and Snooze Today lead its tab (they pause its crops too)
        {"type": "entities", "entities": ["switch.tunnel_pause", "button.tunnel_snooze_today"], "show_header_toggle": False},
        {"type": "custom:zoneflow-card", "device_id": "gh", "show_crops": False},
        {"type": "custom:zoneflow-card", "device_id": "c1"},
    ]


OVERVIEW_HARNESS = HARNESS.replace(
    'const strategy = registry["ll-strategy-dashboard-zoneflow"];',
    'const card = registry["zoneflow-overview-card"];',
).replace(
    'strategy.generate({ type: "custom:zoneflow" }, hass).then((out) => console.log(JSON.stringify(out)));',
    'const zones = card.prototype._zones.call({ _hass: hass, _config: {} });\n'
    'console.log(JSON.stringify(zones.map((z) => [z.name, z.areaName === undefined ? null : z.areaName, !!z.areaStart, z.areaKind || null])));',
)


def test_the_overview_card_groups_zones_under_their_area(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    entities, states, devices = {}, {}, {}
    for device, name, area in (("d1", "Tomatoes", "Backyard"), ("d2", "Lawn", "Front yard"), ("d3", "Shed", None), ("d4", "Chilis", "Backyard")):
        _zone(entities, states, device, name, "lawn")
        _with_area(states, name, area)
        devices[device] = {"name": name}
    harness = tmp_path / "overview.js"
    harness.write_text(OVERVIEW_HARNESS, encoding="utf-8")
    hass = {"entities": entities, "states": states, "devices": devices, "locale": {"language": "en"}}
    done = subprocess.run(["node", str(harness), str(CARD), json.dumps(hass)], capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(done.stdout) == [
        ["Chilis", "Backyard", True, "area"], ["Tomatoes", "Backyard", False, "area"],
        ["Lawn", "Front yard", True, "area"],
        ["Shed", "", True, "other"],  # no area: last, under "Other"
    ]


def test_without_any_area_the_overview_is_as_before(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    entities, states, devices = {}, {}, {}
    for device, name in (("d1", "Tomatoes"), ("d2", "Lawn")):
        _zone(entities, states, device, name, "lawn")
        devices[device] = {"name": name}
    harness = tmp_path / "overview.js"
    harness.write_text(OVERVIEW_HARNESS, encoding="utf-8")
    hass = {"entities": entities, "states": states, "devices": devices, "locale": {"language": "en"}}
    done = subprocess.run(["node", str(harness), str(CARD), json.dumps(hass)], capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(done.stdout) == [["Lawn", None, False, None], ["Tomatoes", None, False, None]]


GARDEN_AREAS_HARNESS = HARNESS.replace(
    'const strategy = registry["ll-strategy-dashboard-zoneflow"];', ""
).replace(
    'strategy.generate({ type: "custom:zoneflow" }, hass).then((out) => console.log(JSON.stringify(out)));',
    "console.log(JSON.stringify(sandbox.gardenAreas(hass)));",
)


def test_the_area_names_in_use_are_listed_once_each(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    entities, states, devices = {}, {}, {}
    for device, name, area in (
        ("d1", "Tomatoes", "Backyard"), ("d2", "Chilis", "backyard"), ("d3", "Lawn", "Front yard"), ("d4", "Shed", None),
    ):
        _zone(entities, states, device, name, "lawn")
        _with_area(states, name, area)
        devices[device] = {"name": name}
    harness = tmp_path / "areas.js"
    harness.write_text(GARDEN_AREAS_HARNESS, encoding="utf-8")
    hass = {"entities": entities, "states": states, "devices": devices, "locale": {"language": "en"}}
    done = subprocess.run(["node", str(harness), str(CARD), json.dumps(hass)], capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(done.stdout) == ["Backyard", "Front yard"]


def test_an_area_tab_starts_with_the_areas_pause_and_snooze(tmp_path):
    entities, states, devices = {}, {}, {}
    for device, name in (("d1", "Tomatoes"), ("d2", "Chilis")):
        _zone(entities, states, device, name, "tomatoes")
        _with_area(states, name, "Backyard")
        attrs = states[f"sensor.{name.lower()}_status"]["attributes"]
        attrs["area_pause"], attrs["area_snooze"] = "switch.backyard_pause", "button.backyard_snooze_today"
        devices[device] = {"name": name}
    out = _run(tmp_path, {"entities": entities, "states": states, "devices": devices, "locale": {"language": "en"}})
    cards = out["views"][1]["cards"]
    assert cards[0] == {
        "type": "entities", "entities": ["switch.backyard_pause", "button.backyard_snooze_today"], "show_header_toggle": False,
    }
    assert [c["device_id"] for c in cards[1:]] == ["d2", "d1"]
    # No controls known (an older status): the tab is just the zones.
    for name in ("Tomatoes", "Chilis"):
        states[f"sensor.{name.lower()}_status"]["attributes"].pop("area_pause")
        states[f"sensor.{name.lower()}_status"]["attributes"].pop("area_snooze")
    out = _run(tmp_path, {"entities": entities, "states": states, "devices": devices, "locale": {"language": "en"}})
    assert all(c["type"] == "custom:zoneflow-card" for c in out["views"][1]["cards"])


LOCATION_ROW_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const registry = {};
class El {
  constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; this._text = ""; this.value = ""; this.hidden = false; }
  append(...c) { this.children.push(...c); }
  appendChild(c) { this.children.push(c); }
  addEventListener(type, fn) { this.listeners[type] = fn; }
  focus() {}
  set textContent(v) { this._text = v; if (v === "") this.children = []; }
  get textContent() { return this._text; }
}
const pushed = [];
const sandbox = {
  window: { customElements: { get: (t) => registry[t], define: (t, c) => { registry[t] = c; } }, customCards: [], addEventListener() {},
            dispatchEvent() {} },
  HTMLElement: class {},
  document: { createElement: (tag) => new El(tag) },
  history: { pushState: (...a) => pushed.push(a[2]) },
  CustomEvent: class {},
  console: { info() {} },
  setTimeout: () => 0,
  Intl, Object, Set, Map, WeakMap, Promise, Math, JSON, Date, String, Number, Array,
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), sandbox);
const hass = JSON.parse(process.argv[3]);
const calls = [];
hass.callService = (domain, service, data) => calls.push([domain, service, data]);
const ctx = { _hass: hass, _config: { device_id: "d1" } };
const row = registry["zoneflow-card"].prototype._locationRow.call(ctx, { entity: "select.tomatoes_where_is_this", name: "Where is this?" });
row.hass = hass;
const [label, select, input] = row.children;
const result = { label: select.title, labelHidden: label.hidden, options: select.children.map((o) => [o.value, o.textContent]), selected: select.value };
select.value = "Backyard"; select.listeners.change();
select.value = "__new_area__"; select.listeners.change();
result.inputShown = !input.hidden;
input.value = "  Side garden "; input.listeners.keydown({ key: "Enter" });
select.value = "__new_greenhouse__"; select.listeners.change();
result.afterGreenhouse = select.value;
result.pushed = pushed;
result.calls = calls;
console.log(JSON.stringify(result));
"""


def test_the_location_row_offers_the_places_a_new_area_and_a_new_greenhouse(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    harness = tmp_path / "location.js"
    harness.write_text(LOCATION_ROW_HARNESS, encoding="utf-8")
    hass = {
        "states": {"select.tomatoes_where_is_this": {
            "state": "None", "attributes": {"options": ["None", "Backyard", "Tunnel (greenhouse)"]}}},
        "locale": {"language": "en"}, "user": {"is_admin": True},
    }
    done = subprocess.run(["node", str(harness), str(CARD), json.dumps(hass)], capture_output=True, encoding="utf-8", timeout=60, check=True)
    out = json.loads(done.stdout)
    assert out["label"] == "Where is this?" and out["labelHidden"] is True  # hover text only: the heading above says it on screen
    assert out["options"] == [
        ["None", "None"], ["Backyard", "Backyard"], ["Tunnel (greenhouse)", "Tunnel (greenhouse)"],
        ["__new_area__", "New area…"], ["__new_greenhouse__", "New greenhouse…"],
    ]
    assert out["selected"] == "None" and out["inputShown"] is True
    assert out["calls"] == [
        ["select", "select_option", {"entity_id": "select.tomatoes_where_is_this", "option": "Backyard"}],
        ["zoneflow", "create_area", {"name": "Side garden", "device_id": "d1"}],
    ]
    assert out["pushed"] == ["/config/integrations/dashboard/add?domain=zoneflow"] and out["afterGreenhouse"] == "None"


PLANTS_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const registry = {};
class El {
  constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; this._text = ""; this.value = ""; this.hidden = false; this.className = ""; this.checked = false; }
  append(...c) { for (const x of c) this.children.push(typeof x === "string" ? { text: x, children: [] } : x); }
  appendChild(c) { this.children.push(c); }
  setAttribute(k, v) { this.attrs = { ...(this.attrs || {}), [k]: v }; }
  insertBefore(el) { this.children.push(el); }
  remove() {}
  addEventListener(type, fn) { this.listeners[type] = fn; }
  set textContent(v) { this._text = v; if (v === "") this.children = []; }
  get textContent() { return this._text; }
}
const sandbox = {
  window: { customElements: { get: (t) => registry[t], define: (t, c) => { registry[t] = c; } }, customCards: [], addEventListener() {},
            confirm: () => true, alert() {} },
  HTMLElement: class {},
  document: { createElement: (tag) => new El(tag), createTextNode: (text) => ({ text, children: [] }) },
  console: { info() {} },
  setTimeout: () => 0,
  Intl, Object, Set, Map, WeakMap, Promise, Math, JSON, Date, String, Number, Array,
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), sandbox);
const input = JSON.parse(process.argv[3]);
const calls = [];
const hass = input.hass;
hass.callService = async (domain, service, data) => { calls.push([domain, service, data]); };
hass.callWS = async () => input.ws;
const proto = registry["zoneflow-card"].prototype;
const ctx = { _hass: hass, _config: { device_id: "d1" } };
ctx._plantsBody = proto._plantsBody;
const walk = (el, out = []) => { out.push(el); for (const c of el.children || []) walk(c, out); return out; };
const run = async () => {
  const body = new El("div");
  await proto._plantsBody.call(ctx, body);
  const all = () => walk(body);
  const buttons = (label) => all().filter((e) => e.tag === "button" && e._text === label);
  const result = {};
  result.names = all().filter((e) => e.className === "plant-name").map((e) => e._text);
  result.badges = all().filter((e) => (e.className || "").startsWith("plant-badge")).map((e) => e._text);
  result.makeMainButtons = buttons("Make main plant").length;
  // Every click re-draws the popup: take hold of the controls first.
  const copyBtn = buttons("Copy")[0];
  const useBtn = buttons("Use preset")[0];
  const delBtn = buttons("Delete preset")[0];
  const saveBtn = buttons("Save this zone's settings as a preset")[0];
  const presetName = all().filter((e) => e.tag === "input" && e.placeholder === "Preset name")[0];
  const zoneSelects = all().filter((e) => e.tag === "select" && e.children[0]?.value === "d2");
  const sourceSelect = zoneSelects[zoneSelects.length - 1];  // the last one is the copy list
  const presetSelect = all().filter((e) => e.tag === "select" && e.children[0]?.value === "Hot bed")[0];
  buttons("Make main plant")[0].listeners.click();
  await Promise.resolve();
  // Move the main plant: the first panel is the main plant's.
  const selects = all().filter((e) => e.tag === "select" && e.className === "area-select" && e.children.length && e.children[0].value === "d2");
  result.targets = selects[0].children.map((o) => [o.value, o._text]);
  selects[0].value = "d2"; selects[0].listeners.change();
  result.choices = all().filter((e) => e.className === "plant-choice" && e.children[0].type === "radio").map((e) => e.children[0].value);
  result.hasSettingsBox = all().some((e) => e.tag === "input" && e.type === "checkbox");
  result.hasRename = buttons("Rename").length;
  buttons("Move")[0].listeners.click();
  await Promise.resolve();
  // Add a plant.
  const names = all().filter((e) => e.tag === "input" && e.placeholder === "Name");
  names[0].value = "  Basil ";
  const types = all().filter((e) => e.tag === "select" && e.children[0]?.value === "custom");
  types[0].value = "herbs";
  const modes = all().filter((e) => e.tag === "select" && e.children[0]?._text === "Record only (the zone keeps watering as it is)");
  result.modeOptions = modes[0].children.map((o) => o.value);
  modes[0].value = "archive";
  buttons("Add a plant")[0].listeners.click();
  await Promise.resolve();
  // Copy settings from another zone, use / delete a preset, save one.
  sourceSelect.value = "d2"; presetSelect.value = "Hot bed";
  copyBtn.listeners.click();
  useBtn.listeners.click();
  delBtn.listeners.click();
  presetName.value = " Cool bed ";
  saveBtn.listeners.click();
  await Promise.resolve();
  result.calls = calls;
  console.log(JSON.stringify(result));
};
run();
"""


def test_the_plants_popup_lists_the_plants_and_calls_the_services(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    entities, states, devices = {}, {}, {}
    for device, name in (("d1", "Tomatoes"), ("d2", "Chilis")):
        _zone(entities, states, device, name, "tomatoes")
        devices[device] = {"name": name}
    states["sensor.chilis_status"]["attributes"]["valve"] = "switch.chilis"  # a zone that waters can be copied from
    states["sensor.tomatoes_status"]["attributes"]["valve"] = "switch.tomatoes"
    states["sensor.chilis_status"]["attributes"]["plants"] = [{"id": "c", "name": "Chilis", "main": True}]
    states["sensor.tomatoes_status"]["attributes"]["plants"] = [
        {"id": "t", "name": "Tomatoes", "main": True}, {"id": "b", "name": "Basil", "main": False}]
    ws = {"zone": "Tomatoes", "presets": [{"id": "p1", "name": "Hot bed"}], "plants": [
        {"id": "t", "name": "Tomatoes", "type": "tomatoes", "main": True, "history": [{"ts": "2026-10-09T09:00:00+00:00", "kind": "created", "text": "Added to ZoneFlow"}]},
        {"id": "b", "name": "Basil", "type": "herbs", "main": False, "history": []},
    ]}
    harness = tmp_path / "plants.js"
    harness.write_text(PLANTS_HARNESS, encoding="utf-8")
    hass = {"entities": entities, "states": states, "devices": devices, "locale": {"language": "en"}, "user": {"is_admin": True}}
    done = subprocess.run(["node", str(harness), str(CARD), json.dumps({"hass": hass, "ws": ws})], capture_output=True, encoding="utf-8", timeout=60, check=True)
    out = json.loads(done.stdout)
    assert out["names"] == ["Tomatoes", "Basil"] and out["badges"] == ["Main plant", "Record only"]
    assert out["makeMainButtons"] == 1
    assert out["hasSettingsBox"] is True and out["hasRename"] == 2  # a rename button per plant; the move panel asks about watering settings
    assert out["targets"] == [["d2", "Chilis"]]
    assert out["choices"] == ["extra", "archive", "swap", "keep"]  # Chilis already has a main plant
    assert out["modeOptions"] == ["", "extra", "archive"]
    assert out["calls"] == [
        ["zoneflow", "set_main_plant", {"plant_id": "b"}],
        ["zoneflow", "move_plant", {"plant_id": "t", "device_id": "d2", "use_plant_settings": False, "old_main": "extra"}],
        ["zoneflow", "add_plant", {"name": "Basil", "plant_type": "herbs", "device_id": "d1", "old_main": "archive"}],
        ["zoneflow", "copy_settings", {"source_device_id": "d2", "device_id": "d1"}],
        ["zoneflow", "copy_settings", {"preset": "Hot bed", "device_id": "d1"}],
        ["zoneflow", "delete_preset", {"name": "Hot bed"}],
        ["zoneflow", "save_preset", {"name": "Cool bed", "device_id": "d1"}],
    ]


_PREAMBLE = PLANTS_HARNESS[: PLANTS_HARNESS.index("const run = async")]

CHECK_HARNESS = _PREAMBLE + r"""
hass.callWS = async (msg) => { calls.push(["ws", msg.type]); return input.ws; };
const run = async () => {
  const result = {};
  const popups = { calibrate: { runEntity: "button.tomatoes_service_run_15_min" }, check: {} };
  const ctx2 = { _hass: hass, _config: { device_id: "d1" }, _popups: popups, _openPopup: (key) => calls.push(["open", key]) };
  const body = new El("div");
  await proto._checkBody.call(ctx2, body);
  const all = () => walk(body);
  result.headline = all().filter((e) => e.className.startsWith("check-headline")).map((e) => [e.className, e._text]);
  result.items = all().filter((e) => e.className.startsWith("check-item")).map((e) => e.className);
  const calibrate = all().filter((e) => e.tag === "button" && e._text === "Calibrate")[0];
  calibrate.listeners.click();

  const cal = new El("div");
  proto._calibrateBody.call(ctx2, cal, popups.calibrate);
  const inputs = walk(cal).filter((e) => e.tag === "input");
  const labels = walk(cal).filter((e) => e.text && e.text.includes("("));
  result.labels = labels.map((l) => l.text);
  const [water, area, minutes] = inputs;
  water.value = "30"; area.value = "10";
  result.minutesDefault = minutes.value;
  walk(cal).filter((e) => e.tag === "button" && e._text === "Run 15 minutes")[0].listeners.click();
  walk(cal).filter((e) => e.tag === "button" && e._text === "Set the flow rate")[0].listeners.click();
  await Promise.resolve();

  const row = proto._waterNowRow.call({ _hass: hass, _config: { device_id: "d1" } });
  const rowButtons = walk(row).filter((e) => e.tag === "button");
  rowButtons[1].listeners.click();  // +5
  rowButtons[1].listeners.click();  // +5
  rowButtons[0].listeners.click();  // -5
  result.shown = walk(row).filter((e) => e.className === "waternow-minutes")[0]._text;
  rowButtons[2].listeners.click();  // Start
  await Promise.resolve();
  result.calls = calls;
  console.log(JSON.stringify(result));
};
run();
"""


def test_the_check_calibrate_and_water_now_controls(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    entities, states, devices = {}, {}, {}
    _zone(entities, states, "d1", "Tomatoes", "tomatoes")
    devices["d1"] = {"name": "Tomatoes"}
    states["sensor.tomatoes_status"]["attributes"].update(volume_unit="L", area_unit="m²")
    ws = {"zone": "Tomatoes", "level": "warn", "items": [
        {"id": "flow", "level": "warn", "text": "The flow rate is still the example value.", "action": "calibrate"},
        {"id": "valve", "level": "ok", "text": "The valve answers.", "action": None}]}
    harness = tmp_path / "check.js"
    harness.write_text(CHECK_HARNESS, encoding="utf-8")
    hass = {"entities": entities, "states": states, "devices": devices, "locale": {"language": "en"}, "user": {"is_admin": True}}
    done = subprocess.run(["node", str(harness), str(CARD), json.dumps({"hass": hass, "ws": ws})],
                          capture_output=True, encoding="utf-8", timeout=60, check=False)
    assert done.returncode == 0, done.stderr[-800:]
    out = json.loads(done.stdout)
    assert out["headline"] == [["check-headline warn", "A few things to look at."]]
    assert out["items"] == ["check-item warn", "check-item ok"]
    assert out["labels"] == ["Water that came out (L) ", "Watered area (m²) ", "Minutes the valve was open (min) "]
    assert out["minutesDefault"] == "15" and out["shown"] == "15 min"
    assert out["calls"] == [
        ["ws", "zoneflow/check"],
        ["open", "calibrate"],
        ["button", "press", {"entity_id": "button.tomatoes_service_run_15_min"}],
        ["zoneflow", "calibrate_flow", {"volume": 30, "area": 10, "minutes": 15, "device_id": "d1"}],
        ["zoneflow", "water_now", {"minutes": 15, "device_id": "d1"}],
    ]


DASHBOARD_HARNESS = (_PREAMBLE + r"""
const over = registry["zoneflow-overview-card"].prototype;
const make = (list, fail) => ({
  _hass: { user: { is_admin: true }, callWS: async (msg) => { calls.push(msg.type + (msg.url_path ? ":" + msg.url_path : "")); if (fail) throw new Error("no"); return msg.type.endsWith("list") ? list : {}; } },
  _config: {},
  _render() { calls.push("render"); },
});
const run = async () => {
  const result = {};
  const a = make([{ url_path: "lovelace" }]);
  await over._checkDashboard.call(a);
  result.missing = a._dashboardState;
  const b = make([{ url_path: "zoneflow" }]);
  await over._checkDashboard.call(b);
  result.exists = b._dashboardState;
  const c = make([], true);
  await over._checkDashboard.call(c);
  result.unknown = c._dashboardState;
  const d = make([]);
  d._hass.user.is_admin = false;
  await over._checkDashboard.call(d);
  result.nonAdmin = d._dashboardState || null;
  calls.length = 0;
  hass.callWS = a._hass.callWS;
  sandbox.history.pushState = (...x) => calls.push("go:" + x[2]);
  await over._createDashboard.call(a);
  result.created = [...calls];
  console.log(JSON.stringify(result));
};
run();
""").replace("const sandbox = {", "const sandbox = { CustomEvent: class {}, history: { pushState() {} },").replace(
    "window: {", "window: { dispatchEvent() {}, ", 1)


def test_one_click_dashboard_creation(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    harness = tmp_path / "dash.js"
    harness.write_text(DASHBOARD_HARNESS, encoding="utf-8")
    hass = {"entities": {}, "states": {}, "devices": {}, "locale": {"language": "en"}, "user": {"is_admin": True}}
    done = subprocess.run(["node", str(harness), str(CARD), json.dumps({"hass": hass, "ws": {}})],
                          capture_output=True, encoding="utf-8", timeout=60, check=False)
    assert done.returncode == 0, done.stderr[-800:]
    out = json.loads(done.stdout)
    assert out["missing"] == "missing" and out["exists"] == "exists"
    assert out["unknown"] == "exists" and out["nonAdmin"] is None
    # A dashboard's path must contain a hyphen, or Home Assistant refuses it.
    assert out["created"] == ["lovelace/dashboards/create:zoneflow-garden", "lovelace/config/save:zoneflow-garden", "go:/zoneflow-garden"]


SIMPLE_HARNESS = _PREAMBLE.replace(
    "document: { createElement: (tag) => new El(tag), createTextNode: (text) => ({ text, children: [] }) },",
    "document: { createElement: (tag) => new El(tag), createTextNode: (text) => ({ text, children: [] }) },\n"
    "  CustomEvent: class {},",
).replace("window: {", "window: { loadCardHelpers: async () => ({ createRowElement: (conf) => { const e = new El('row'); e.conf = conf; return e; } }), ", 1) + r"""
const proto2 = registry["zoneflow-card"].prototype;
const buildCard = async (simple, advanced) => {
  const root = new El("root");
  root.innerHTML = "";
  const ctx = Object.create(proto2);
  Object.assign(ctx, { _hass: hass, _config: { device_id: "d1", simple, show_journal: true, show_settings: true }, shadowRoot: root,
                       _showAdvanced: advanced, _render() { calls.push("render"); } });
  const visible = {};
  for (const key of input.keys) visible[key] = { entity_id: key.replace(".", "." + "tomatoes_"), entity_category: null };
  proto2._build.call(ctx, visible, "switch.valve", { valve: "switch.valve", plants: [{ id: "t", name: "T", main: true }] });
  for (let i = 0; i < 6; i++) await Promise.resolve();
  const all = walk(root);
  return {
    titles: all.filter((e) => e.className === "section-title").map((e) => e._text),
    more: all.filter((e) => e.className === "more").length,
    toggle: all.filter((e) => e.className === "advanced-toggle").map((e) => e._text),
    ctx, all,
  };
};
const run = async () => {
  const simple = await buildCard(true, false);
  const open = await buildCard(true, true);
  const normal = await buildCard(false, false);
  simple.all.filter((e) => e.className === "advanced-toggle")[0].listeners.click();
  console.log(JSON.stringify({
    simple: [simple.titles, simple.more, simple.toggle],
    open: [open.titles, open.more, open.toggle],
    normal: [normal.titles, normal.more, normal.toggle],
    flipped: simple.ctx._showAdvanced, calls,
  }));
};
run();
"""


def test_the_simple_view_shows_the_few_controls_and_hides_the_rest_behind_advanced(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    entities, states, devices = {}, {}, {}
    _zone(entities, states, "d1", "Tomatoes", "tomatoes")
    devices["d1"] = {"name": "Tomatoes"}
    keys = ["sensor.status", "button.run_routine", "button.snooze_today", "switch.pause", "button.run_deep_soak", "switch.service_mode"]
    harness = tmp_path / "simple.js"
    harness.write_text(SIMPLE_HARNESS, encoding="utf-8")
    hass = {"entities": entities, "states": states, "devices": devices, "locale": {"language": "en"}, "user": {"is_admin": True}}
    done = subprocess.run(["node", str(harness), str(CARD), json.dumps({"hass": hass, "ws": {}, "keys": keys})],
                          capture_output=True, encoding="utf-8", timeout=60, check=False)
    assert done.returncode == 0, done.stderr[-1200:]
    out = json.loads(done.stdout)
    assert out["simple"] == [["Controls"], 0, ["Advanced settings"]]
    assert out["open"][0] == ["Controls", "Service & checks (not counted as watering)"] and out["open"][1] == 1 and out["open"][2] == ["Hide advanced settings"]
    assert out["normal"][0] == ["Controls", "Service & checks (not counted as watering)"] and out["normal"][1] == 1 and out["normal"][2] == []
    assert out["flipped"] is True and "render" in out["calls"]


def test_the_help_links_point_at_guides_that_exist():
    import re

    text = CARD.read_text(encoding="utf-8")
    base = re.search(r'const GUIDE = "https://github.com/Dreamer41/ha-smart-irrigation/blob/main/docs/";', text)
    assert base, "the guide base address changed"
    for name in set(re.findall(r"\$\{GUIDE\}([A-Z-]+\.md)", text)):
        assert (CARD.parents[3] / "docs" / name).is_file(), name


WHY_HARNESS = SIMPLE_HARNESS[: SIMPLE_HARNESS.rindex("const run = async")] + r"""
const run = async () => {
  const card = await buildCard(false, false);
  const toggle = card.all.filter((e) => e.className === "why-toggle")[0];
  const panel = card.all.filter((e) => e.className === "why-panel")[0];
  const result = { before: [toggle._text, panel.hidden] };
  toggle.listeners.click();
  for (let i = 0; i < 5; i++) await Promise.resolve();
  result.open = [toggle._text, panel.hidden, panel.children.map((c) => c._text)];
  toggle.listeners.click();
  result.closed = [toggle._text, panel.hidden];
  result.calls = calls;
  console.log(JSON.stringify(result));
};
run();
"""


def test_the_why_panel_opens_with_the_numbers_and_closes_again(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    entities, states, devices = {}, {}, {}
    _zone(entities, states, "d1", "Tomatoes", "tomatoes")
    devices["d1"] = {"name": "Tomatoes"}
    ws = {"items": [{"id": "target", "text": "Weekly target: 35 mm."}, {"id": "last", "text": "Next watering Mon 05:30"}]}
    keys = ["sensor.status", "button.run_routine", "switch.pause"]
    harness = tmp_path / "why.js"
    harness.write_text(WHY_HARNESS, encoding="utf-8")
    hass = {"entities": entities, "states": states, "devices": devices, "locale": {"language": "en"}, "user": {"is_admin": True}}
    done = subprocess.run(["node", str(harness), str(CARD), json.dumps({"hass": hass, "ws": ws, "keys": keys})],
                          capture_output=True, encoding="utf-8", timeout=60, check=False)
    assert done.returncode == 0, done.stderr[-1000:]
    out = json.loads(done.stdout)
    assert out["before"] == ["Why?", True]
    assert out["open"] == ["Hide", False, ["Weekly target: 35 mm.", "Next watering Mon 05:30"]]
    assert out["closed"] == ["Why?", True]


GARDEN_HARNESS = _PREAMBLE + r"""
const over = registry["zoneflow-overview-card"].prototype;
const zones = input.zones;
const out = over._summary.call({ _hass: hass }, zones);
console.log(JSON.stringify(out));
"""


def test_my_garden_summary_chips(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node is not installed")

    def sensor(device, key, entity, state, unit):
        return (
            {"entity_id": entity, "device_id": device, "platform": "zoneflow", "translation_key": key},
            {"entity_id": entity, "state": state, "attributes": {"unit_of_measurement": unit}},
        )

    entities, states = {}, {}
    for device, rain, water in (("d1", "4.2", "100"), ("d2", "6.0", "50"), ("d3", "unknown", "unavailable")):
        for key, entity, state, unit in (
            ("rain_today", f"sensor.{device}_rain_today", rain, "mm"),
            ("water_used_30d", f"sensor.{device}_water_30d", water, "L"),
        ):
            reg, st = sensor(device, key, entity, state, unit)
            entities[entity], states[entity] = reg, st
    zones = [
        {"device_id": "d1", "name": "Tomatoes", "code": "watering", "next": None},
        {"device_id": "d2", "name": "Chilis", "code": "next", "next": "2099-01-02T05:30:00+00:00"},
        {"device_id": "d3", "name": "Lawn", "code": "lock_held", "next": "2099-01-01T05:30:00+00:00"},
    ]
    harness = tmp_path / "garden.js"
    harness.write_text(GARDEN_HARNESS, encoding="utf-8")
    hass = {"entities": entities, "states": states, "devices": {}, "locale": {"language": "en"}, "user": {"is_admin": True}}
    done = subprocess.run(["node", str(harness), str(CARD), json.dumps({"hass": hass, "ws": {}, "zones": zones})],
                          capture_output=True, encoding="utf-8", timeout=60, check=False)
    assert done.returncode == 0, done.stderr[-1000:]
    chips = json.loads(done.stdout)
    texts = [c[1] for c in chips]
    assert texts[0] == "Watering now: Tomatoes"
    assert texts[1].startswith("Next: Lawn")  # the soonest of the zones that have a next watering
    assert "Rain today: 6.0 mm" in texts and "Needs a look: Lawn" in texts and "Water used, 30 days: 150 L" in texts


def test_the_overview_keeps_each_greenhouse_and_its_crops_in_a_group_of_its_own(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    entities, states, devices = {}, {}, {}
    _zone(entities, states, "gh", "Tunnel", "custom", climate=True)
    _zone(entities, states, "c1", "Peppers", "chilis", climate=True, hidden_climate=True)
    _zone(entities, states, "c2", "Basil", "herbs", climate=True, hidden_climate=True)
    _zone(entities, states, "o1", "Lawn", "lawn")
    _zone(entities, states, "o2", "Beds", "tomatoes")
    for name in ("Peppers", "Basil"):
        states[f"sensor.{name.lower()}_status"]["attributes"]["greenhouse"] = {"name": "Tunnel", "device_id": "gh"}
        states[f"sensor.{name.lower()}_status"]["attributes"]["zone_type"] = "greenhouse"
    states["sensor.tunnel_status"]["attributes"]["zone_type"] = "greenhouse"
    for name, area in (("Tunnel", "Backyard"), ("Peppers", "Backyard"), ("Basil", "Backyard"), ("Lawn", "Backyard"), ("Beds", None)):
        _with_area(states, name, area)
    devices.update({"gh": {"name": "Tunnel"}, "c1": {"name": "Peppers"}, "c2": {"name": "Basil"}, "o1": {"name": "Lawn"}, "o2": {"name": "Beds"}})
    harness = tmp_path / "overview.js"
    harness.write_text(OVERVIEW_HARNESS, encoding="utf-8")
    hass = {"entities": entities, "states": states, "devices": devices, "locale": {"language": "en"}}
    done = subprocess.run(["node", str(harness), str(CARD), json.dumps(hass)], capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(done.stdout) == [
        ["Lawn", "Backyard", True, "area"],           # the outdoor area first
        ["Tunnel", "Tunnel", True, "house"],          # then the greenhouse, with its crops, under its own heading
        ["Basil", "Tunnel", False, "house"], ["Peppers", "Tunnel", False, "house"],
        ["Beds", "", True, "other"],                  # no area: last
    ]


def test_the_watering_method_help_link_points_at_the_blog_post():
    text = CARD.read_text(encoding="utf-8")
    assert 'const METHOD_HELP_URL = "https://zoneflowirrigation.com/blog/temperature-tiers-et-or-soil-sensor";' in text
    assert "amounts: [METHOD_HELP_URL]" in text  # one "?" beside How much water (the flow rate has its own in Calibrate)


PLANTS_LINE_HARNESS = SIMPLE_HARNESS[: SIMPLE_HARNESS.rindex("const run = async")] + r"""
const run = async () => {
  const card = await buildCard(false, false);
  card.ctx._statusEl.classList = { toggle() {} };
  card.ctx._plantsEl.classList = { toggle() {} };
  const visible = { "sensor.status": { entity_id: "sensor.tomatoes_status" }, "select.demand_model": { entity_id: "select.tomatoes_demand_model" } };
  hass.states["select.tomatoes_demand_model"] = { state: "et_curve", attributes: { friendly_name: "Tomatoes Water Demand Model" } };
  hass.states["sensor.tomatoes_status"].attributes.valve = "switch.valve";
  const show = (plants) => {
    hass.states["sensor.tomatoes_status"].attributes.plants = plants;
    proto2._update.call(card.ctx, visible);
    return [card.ctx._plantsEl.textContent, card.ctx._plantsEl.hidden, card.ctx._methodEl.textContent, card.ctx._methodEl.hidden];
  };
  console.log(JSON.stringify({
    one: show([{ id: "a", name: "Tomatoes", main: true }]),
    mixed: show([{ id: "a", name: "Eggplant", main: true }, { id: "b", name: "Basil", main: false }, { id: "c", name: "Marigold", main: false }]),
    none: show([]),
    ready: show([{ id: "a", name: "Eggplant", main: true }, { id: "b", name: "Basil", main: false, stage: "ready" }]),
    soon: show([{ id: "a", name: "Eggplant", main: true, stage: "seedling", days_left: 9 }]),
  }));
};
run();
"""


def test_a_mixed_zone_lists_its_plants_under_the_status(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    entities, states, devices = {}, {}, {}
    _zone(entities, states, "d1", "Tomatoes", "tomatoes")
    devices["d1"] = {"name": "Tomatoes"}
    harness = tmp_path / "plants_line.js"
    harness.write_text(PLANTS_LINE_HARNESS, encoding="utf-8")
    hass = {"entities": entities, "states": states, "devices": devices, "locale": {"language": "en"}, "user": {"is_admin": True}}
    done = subprocess.run(["node", str(harness), str(CARD), json.dumps({"hass": hass, "ws": {}, "keys": ["sensor.status"]})],
                          capture_output=True, encoding="utf-8", timeout=60, check=False)
    assert done.returncode == 0, done.stderr[-1000:]
    out = json.loads(done.stdout)
    assert out["one"][1] is True and out["none"][1] is True  # one plant needs no list
    assert out["mixed"][:2] == ["Plants: Eggplant, Basil, Marigold", False]
    assert out["mixed"][2:] == ["Tomatoes Water Demand Model: et_curve", False]  # how the zone is watered, always shown
    assert out["ready"][:2] == ["Plants: Eggplant, Basil · Ready to move: Basil", False]
    assert out["soon"][1] is True  # a seedling that is not ready yet adds nothing here

