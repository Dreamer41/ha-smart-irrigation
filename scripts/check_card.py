"""Renders the ZoneFlow dashboard card (custom_components/zoneflow/frontend/
zoneflow-card.js) in headless Chromium against a fake Home Assistant, checks
what it shows, and saves a screenshot.

    python scripts/check_card.py [--screenshot card.png]

Home Assistant's own elements are stubbed (rows become plain text), so this
checks the card's logic -- which entity goes where, what's left out, how
it follows changes -- not Home Assistant's styling. Exits non-zero on a
failed check.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
CARD = ROOT / "custom_components" / "zoneflow" / "frontend" / "zoneflow-card.js"
DEVICE = "dev1"

KEYS = [
    ("sensor", "status", None), ("sensor", "soil_moisture", None), ("sensor", "next_irrigation_estimate", None),
    ("sensor", "deficit_status", None), ("sensor", "rain_past_24h", "diagnostic"),
    ("button", "run_routine", None), ("button", "run_deep_soak", None), ("button", "snooze_today", None),
    ("button", "reset_lock", None), ("button", "service_run_1_min", None), ("button", "service_run_5_min", None),
    ("button", "service_run_10_min", None), ("switch", "service_mode", None), ("switch", "pause", None),
    ("datetime", "paused_until", None), ("switch", "deficit_mode", None),
    ("number", "flow_rate_mm_per_min", "config"), ("number", "target_weekly_mm", "config"),
    ("number", "rain_eff_low", "config"), ("select", "notifications", "config"),
    ("number", "brand_new_setting", "config"),  # something a later version adds
    ("select", "health_status", None), ("text", "health_notes", None),
    ("binary_sensor", "irrigation_in_progress", "diagnostic"),
]
HIDDEN = {"number.rain_eff_low", "button.run_deep_soak"}


def fake_hass() -> dict:
    entities, states = {}, {}
    for domain, key, category in KEYS:
        entity_id = f"{domain}.chilis_{key}"
        entities[entity_id] = {
            "entity_id": entity_id, "device_id": DEVICE, "platform": "zoneflow", "translation_key": key,
            "entity_category": category, "hidden": f"{domain}.{key}" in HIDDEN,
        }
        states[entity_id] = {"entity_id": entity_id, "state": "on", "attributes": {"friendly_name": f"Chilis {key}"}}
    states["sensor.chilis_status"]["state"] = "Next watering Tue 05:30"
    states["sensor.chilis_status"]["attributes"].update(code="next", valve="switch.valve_chilis")
    states["sensor.chilis_deficit_status"]["state"] = "off"
    states["switch.valve_chilis"] = {"entity_id": "switch.valve_chilis", "state": "off", "attributes": {"friendly_name": "Valve"}}
    entities["sensor.other_zone_status"] = {
        "entity_id": "sensor.other_zone_status", "device_id": "dev2", "platform": "zoneflow",
        "translation_key": "status", "entity_category": None, "hidden": False,
    }
    return {
        "entities": entities, "states": states, "locale": {"language": "en"},
        "devices": {DEVICE: {"id": DEVICE, "name": "Chilis", "name_by_user": None}},
    }


HARNESS = """<!doctype html><html><head><meta charset="utf-8">
<style>body{font-family:sans-serif;background:#fafafa;width:420px}</style></head><body>
<script>
customElements.define('ha-card', class extends HTMLElement {});
customElements.define('ha-icon', class extends HTMLElement {});
window.loadCardHelpers = async () => ({
  createRowElement(conf) {
    const el = document.createElement('div');
    el.className = 'row';
    el.dataset.entity = conf.entity || '';
    el.dataset.type = conf.type || 'entity';
    el.textContent = conf.type === 'buttons'
      ? conf.entities.map((e) => e.name).join(' | ')
      : (conf.name || conf.entity);
    return el;
  },
});
</script>
<script src="card.js"></script>
</body></html>"""

JS_SECTIONS = """() => {
  const root = document.querySelector('zoneflow-card').shadowRoot;
  const out = {status: root.querySelector('.status')?.textContent, sections: {}, folded: {}, missing: root.querySelector('.missing')?.textContent};
  for (const s of root.querySelectorAll('.section')) {
    out.sections[s.querySelector('.section-title').textContent] = [...s.querySelectorAll('.row')].map(r => r.textContent);
  }
  for (const d of root.querySelectorAll('details')) {
    out.folded[d.querySelector('summary').textContent] = [...d.querySelectorAll('.row')].map(r => r.textContent);
  }
  return out;
}"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    failures: list[str] = []

    def check(condition: bool, what: str) -> None:
        print(("ok   " if condition else "FAIL ") + what)
        if not condition:
            failures.append(what)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.route("http://card.test/", lambda route: route.fulfill(body=HARNESS, content_type="text/html"))
        page.route("http://card.test/card.js", lambda route: route.fulfill(path=str(CARD), content_type="text/javascript"))
        page.goto("http://card.test/")
        hass = fake_hass()
        page.evaluate(
            """([hass, device]) => {
                const card = document.createElement('zoneflow-card');
                card.setConfig({device_id: device, show_diagnostics: true});
                card.hass = hass;
                document.body.appendChild(card);
                window._card = card;
            }""",
            [hass, DEVICE],
        )
        page.wait_for_timeout(200)
        shown = page.evaluate(JS_SECTIONS)
        print(json.dumps(shown, indent=1))
        now, controls, service = (shown["sections"].get(k, []) for k in ("Now", "Controls", "Service & checks (not counted as watering)"))
        settings = shown["folded"].get("Settings", [])
        check(shown["status"] == "Next watering Tue 05:30", "status sentence at the top")
        check(now[:2] == ["Valve", "soil_moisture"], "valve first, names without the zone prefix")
        check("deficit_status" not in now, "deficit status left out while deficit mode is off")
        check(controls and controls[0] == "Water now | Snooze today", "run-now buttons; a hidden one left out")
        check("pause" in controls and "paused_until" in controls, "pause and paused-until in the controls")
        check(service[0] == "service_mode" and service[1] == "1 min | 5 min | 10 min | Reset lock", "service runs")
        check(settings[:2] == ["flow_rate_mm_per_min", "target_weekly_mm"], "settings grouped, flow rate first")
        check("rain_eff_low" not in settings, "hidden settings left out")
        check("brand_new_setting" in settings, "a setting added later appears by itself")
        check("notifications" in settings, "notifications among the settings")
        check(shown["folded"].get("Plant journal") == ["health_status", "health_notes"], "plant journal")
        check("rain_past_24h" in shown["folded"].get("Diagnostics", []), "diagnostics when asked for")
        check(not any("other_zone" in row for rows in shown["sections"].values() for row in rows), "only this zone")

        # Changes: deficit mode switched on, the hidden button unhidden, status changes.
        hass["states"]["sensor.chilis_deficit_status"]["state"] = "active"
        hass["entities"]["button.chilis_run_deep_soak"]["hidden"] = False
        hass["states"]["sensor.chilis_status"]["state"] = "Service run in progress"
        page.evaluate("(hass) => { window._card.hass = hass; }", hass)
        page.wait_for_timeout(200)
        shown = page.evaluate(JS_SECTIONS)
        check(shown["status"] == "Service run in progress", "status follows changes")
        check("deficit_status" in shown["sections"]["Now"], "deficit status appears when deficit mode is on")
        check(shown["sections"]["Controls"][0] == "Water now | Deep soak now | Snooze today", "an unhidden entity appears")

        if args.screenshot:
            page.locator("zoneflow-card").screenshot(path=str(args.screenshot))
            print(f"screenshot: {args.screenshot}")

        # A zone that isn't there.
        page.evaluate(
            """(hass) => { const c = document.createElement('zoneflow-card'); c.setConfig({device_id: 'nope'});
                c.hass = hass; c.id = 'missing'; document.body.appendChild(c); }""",
            hass,
        )
        page.wait_for_timeout(100)
        text = page.evaluate("() => document.getElementById('missing').shadowRoot.querySelector('.missing')?.textContent")
        check(bool(text) and "wasn't found" in text, "a missing zone says so")
        page.evaluate(
            """(hass) => { const c = document.createElement('zoneflow-card'); c.setConfig({device_id: ''});
                c.hass = hass; c.id = 'nozone'; document.body.appendChild(c); }""",
            hass,
        )
        page.wait_for_timeout(100)
        text = page.evaluate("() => document.getElementById('nozone').shadowRoot.querySelector('.missing')?.textContent")
        check(bool(text) and "Pick a ZoneFlow zone" in text, "a card without a zone asks for one (card picker preview)")

        # Settings opened, then something makes the card rebuild: stays open.
        page.evaluate("() => { const d = window._card.shadowRoot.querySelectorAll('details')[1]; d.open = true; }")
        page.wait_for_timeout(50)
        hass["states"]["sensor.chilis_deficit_status"]["state"] = "off"
        page.evaluate("(hass) => { window._card.hass = hass; }", hass)
        page.wait_for_timeout(200)
        is_open = page.evaluate("() => window._card.shadowRoot.querySelectorAll('details')[1].open")
        check(is_open, "an opened section stays open when the card rebuilds")

        # A renamed entity: the card follows it.
        hass["entities"]["sensor.chilis_soil_moisture"]["entity_id"] = "sensor.chili_soil"
        hass["entities"]["sensor.chili_soil"] = hass["entities"].pop("sensor.chilis_soil_moisture")
        hass["states"]["sensor.chili_soil"] = {"entity_id": "sensor.chili_soil", "state": "40", "attributes": {"friendly_name": "Chilis soil_moisture"}}
        page.evaluate("(hass) => { window._card.hass = hass; }", hass)
        page.wait_for_timeout(200)
        rows = page.evaluate("() => [...window._card.shadowRoot.querySelectorAll('.row')].map(r => r.dataset.entity)")
        check("sensor.chili_soil" in rows and "sensor.chilis_soil_moisture" not in rows, "a renamed entity is followed")

        # Quick reconfiguring never leaves extra rows behind.
        page.evaluate(
            """(hass) => { const c = window._card; for (let i = 0; i < 3; i++) { c.setConfig({device_id: 'dev1', show_diagnostics: true}); c.hass = hass; } }""",
            hass,
        )
        page.wait_for_timeout(300)
        counts = page.evaluate(
            "() => [window._card._rows.length, window._card.shadowRoot.querySelectorAll('.row').length]"
        )
        check(counts[0] == counts[1], f"no stray rows after quick reconfiguring ({counts[0]} tracked, {counts[1]} shown)")
        browser.close()

    print(f"\n{len(failures)} failed" if failures else "\nall card checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
