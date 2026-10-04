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


def _zone(entities, states, device, name, plant, climate=False):
    status = f"sensor.{name.lower().replace(' ', '_')}_status"
    entities[status] = {
        "entity_id": status, "device_id": device, "platform": "zoneflow", "translation_key": "status",
    }
    states[status] = {"entity_id": status, "state": "idle", "attributes": {"plant": plant}}
    if climate:
        gh = f"sensor.{name.lower().replace(' ', '_')}_climate"
        entities[gh] = {"entity_id": gh, "device_id": device, "platform": "zoneflow", "translation_key": "greenhouse_status"}


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
    _zone(entities, states, "c1", "Tomatoes", "tomatoes")
    _zone(entities, states, "c2", "Peppers", "chilis")
    _zone(entities, states, "o1", "Lawn", "lawn")
    for crop in ("sensor.tomatoes_status", "sensor.peppers_status"):
        states[crop]["attributes"]["greenhouse"] = {"name": "Tunnel", "device_id": "gh"}
    devices.update({"gh": {"name": "Tunnel"}, "c1": {"name": "Tomatoes"}, "c2": {"name": "Peppers"}, "o1": {"name": "Lawn"}})
    out = _run(tmp_path, {"entities": entities, "states": states, "devices": devices, "locale": {"language": "en"}})
    views = {v["path"]: v for v in out["views"]}
    assert set(views) == {"overview", "lawn", "tunnel"}  # crops have no tab of their own
    assert views["tunnel"]["icon"] == "mdi:greenhouse"
    assert views["tunnel"]["cards"] == [
        {"type": "custom:zoneflow-card", "device_id": "gh", "show_crops": False},
        {"type": "custom:zoneflow-card", "device_id": "c2"},  # Peppers, then Tomatoes: by name
        {"type": "custom:zoneflow-card", "device_id": "c1"},
    ]
