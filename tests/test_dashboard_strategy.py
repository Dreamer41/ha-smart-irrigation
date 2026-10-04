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
