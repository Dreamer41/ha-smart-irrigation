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
  out.buttons = [...root.querySelectorAll('.more button')].map(b => b.textContent);
  return out;
}"""

JS_POPUPS = """async () => {
  // Opens each popup (journal, settings, diagnostics) and reads its rows.
  const card = window._card;
  const out = {};
  for (const button of [...card.shadowRoot.querySelectorAll('.more button')]) {
    button.click();
    await new Promise(r => setTimeout(r, 100));
    const dialog = card.shadowRoot.querySelector('dialog');
    out[button.textContent] = {
      modal: dialog.open && dialog.matches(':modal'),
      rows: [...dialog.querySelectorAll('.row')].map(r => r.textContent),
      groups: [...dialog.querySelectorAll('.group-title')].map(g => g.textContent),
    };
    dialog.close();
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
        popups = page.evaluate(JS_POPUPS)
        print(json.dumps(popups, indent=1))
        check(shown["buttons"] == ["Plant journal", "Settings", "Diagnostics"], "journal, settings and diagnostics as buttons")
        check(all(p["modal"] for p in popups.values()), "they open as popups")
        settings = popups["Settings"]["rows"]
        check(popups["Settings"]["groups"][0] == "How much water", "settings popup grouped")
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
        check(popups["Plant journal"]["rows"] == ["health_status", "health_notes"], "plant journal")
        check("rain_past_24h" in popups["Diagnostics"]["rows"], "diagnostics when asked for")
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
        page.evaluate("() => window._card.shadowRoot.querySelectorAll('.more button')[1].click()")
        page.wait_for_timeout(50)
        hass["states"]["sensor.chilis_deficit_status"]["state"] = "off"
        page.evaluate("(hass) => { window._card.hass = hass; }", hass)
        page.wait_for_timeout(200)
        is_open = page.evaluate(
            "() => { const d = window._card.shadowRoot.querySelector('dialog'); return !!d && d.open && d.querySelectorAll('.row').length > 3; }"
        )
        check(is_open, "an open popup stays open when the card rebuilds")
        page.evaluate("() => window._card.shadowRoot.querySelector('dialog').close()")

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
        check_overview(pw, check, args)

    print(f"\n{len(failures)} failed" if failures else "\nall card checks passed")
    return 1 if failures else 0


def overview_hass() -> dict:
    """Three zones: Tomatoes (preset, watered), Chilis (custom icon, rain
    skip, measured litres), Mango (no preset, paused)."""
    entities, states, devices = {}, {}, {}
    zones = [
        ("tom", "Tomatoes", "tomatoes", "done", "2026-09-28T22:30:00+00:00", "12.0 mm", None),
        ("chi", "Chilis", None, "cancelled_rain", "2026-09-27T22:30:00+00:00", "8.0 mm", "18"),
        ("man", "Mango", None, "paused", None, "20.0 mm", None),
    ]
    for dev, name, plant, code, next_iso, estimate, liters in zones:
        devices[dev] = {"id": dev, "name": name, "name_by_user": None}
        keys = [("sensor", "status", None), ("sensor", "last_water_delivered", "diagnostic"),
                ("sensor", "last_cycle_water_liters", None), ("button", "run_routine", None)]
        for domain, key, category in keys:
            entity_id = f"{domain}.{dev}_{key}"
            entities[entity_id] = {"entity_id": entity_id, "device_id": dev, "platform": "zoneflow",
                                   "translation_key": key, "entity_category": category,
                                   "hidden": key == "last_cycle_water_liters" and liters is None}
            states[entity_id] = {"entity_id": entity_id, "state": "unknown", "attributes": {"friendly_name": f"{name} {key}"}}
        states[f"sensor.{dev}_status"] = {"entity_id": f"sensor.{dev}_status", "state": f"{name} status sentence",
                                          "attributes": {"code": code, "next_watering": next_iso, "plant": plant,
                                                         "valve": None, "friendly_name": f"{name} Status"}}
        states[f"sensor.{dev}_last_water_delivered"]["state"] = estimate.split()[0]
        states[f"sensor.{dev}_last_water_delivered"]["attributes"]["unit_of_measurement"] = "mm"
        if liters:
            states[f"sensor.{dev}_last_cycle_water_liters"]["state"] = liters
            states[f"sensor.{dev}_last_cycle_water_liters"]["attributes"]["unit_of_measurement"] = "L"
    return {"entities": entities, "states": states, "devices": devices, "locale": {"language": "en"},
            "config": {"time_zone": "UTC"}}


JS_OVERVIEW = """() => {
  const root = document.querySelector('#ov').shadowRoot;
  return [...root.querySelectorAll('.zone')].map((z) => {
    const r = z.querySelector('.row');
    return {
      name: r.querySelector('.name span').textContent,
      icon: r.querySelector('.name ha-icon').getAttribute('icon'),
      status: r.querySelector('.status span').textContent,
      warn: r.querySelector('.status').classList.contains('warn'),
      next: r.querySelector('.next').textContent,
      last: r.querySelector('.last').textContent,
      water_disabled: !!r.querySelector('ha-icon-button').disabled,
      open: !z.querySelector('.details').hidden,
      inner: !!z.querySelector('.details zoneflow-card'),
    };
  });
}"""


def check_overview(pw, check, args) -> None:
    browser = pw.chromium.launch()
    page = browser.new_page()
    page.route("http://card.test/", lambda route: route.fulfill(body=HARNESS, content_type="text/html"))
    page.route("http://card.test/card.js", lambda route: route.fulfill(path=str(CARD), content_type="text/javascript"))
    page.goto("http://card.test/")
    page.evaluate("customElements.define('ha-icon-button', class extends HTMLElement {})")
    hass = overview_hass()
    page.evaluate(
        """(hass) => {
            window._calls = [];
            hass.callService = async (domain, service, data) => { window._calls.push([domain, service, data]); };
            const card = document.createElement('zoneflow-overview-card');
            card.id = 'ov';
            card.setConfig({icons: {chi: 'mdi:chili-hot'}});
            card.hass = hass;
            document.body.appendChild(card);
            window._ov = card; window._ovHass = hass;
        }""",
        hass,
    )
    page.wait_for_timeout(200)
    rows = page.evaluate(JS_OVERVIEW)
    print(json.dumps(rows, indent=1))
    check([r["name"] for r in rows] == ["Chilis", "Mango", "Tomatoes"], "overview: every zone, by name")
    check(rows[2]["icon"] == "mdi:food-apple", "overview: preset gives the icon")
    check(rows[0]["icon"] == "mdi:chili-hot", "overview: an icon picked in the editor wins")
    check(rows[1]["icon"] == "mdi:sprinkler-variant", "overview: default icon")
    check(rows[0]["status"] == "Rain skip" and rows[2]["status"] == "Watered today", "overview: short status labels")
    check(rows[1]["status"] == "Paused" and rows[1]["next"] == "—" and rows[1]["water_disabled"], "overview: paused zone")
    check(rows[0]["last"] == "18 L" and rows[2]["last"] == "12.0 mm", "overview: measured litres, else the estimate")
    check("Mon" in rows[2]["next"] or "Tue" in rows[2]["next"], "overview: next as weekday and time")

    page.evaluate("() => { window._ov.setConfig({sort: 'next', icons: {chi: 'mdi:chili-hot'}}); window._ov.hass = window._ovHass; }")
    page.wait_for_timeout(100)
    rows = page.evaluate(JS_OVERVIEW)
    check([r["name"] for r in rows] == ["Chilis", "Tomatoes", "Mango"], "overview: by next watering, paused last")

    page.evaluate("() => window._ov.shadowRoot.querySelector('.zone .action ha-icon-button').click()")
    page.wait_for_timeout(50)
    calls = page.evaluate("() => window._calls")
    check(calls == [["button", "press", {"entity_id": "button.chi_run_routine"}]], "overview: water now presses the zone's button")
    check(not page.evaluate(JS_OVERVIEW)[0]["open"], "overview: the water button doesn't open the row")

    page.evaluate("() => window._ov.shadowRoot.querySelector('.zone .row').click()")
    page.wait_for_timeout(200)
    rows = page.evaluate(JS_OVERVIEW)
    check(rows[0]["open"] and rows[0]["inner"], "overview: a click opens the zone's full card")
    page.evaluate("() => { window._ovHass.states['sensor.chi_status'].attributes.code = 'watering'; window._ov.hass = JSON.parse(JSON.stringify(window._ovHass)); }")
    page.wait_for_timeout(100)
    rows = page.evaluate(JS_OVERVIEW)
    check(rows[0]["open"] and rows[0]["status"] == "Watering now", "overview: stays open and follows changes")
    has_add = page.evaluate("() => !!window._ov.shadowRoot.querySelector('.add')")
    check(not has_add, "overview: no Add zone button for non-admin users")
    page.evaluate("() => { const h = JSON.parse(JSON.stringify(window._ovHass)); h.user = {is_admin: true}; h.callService = window._ovHass.callService; window._ov.hass = h; }")
    page.wait_for_timeout(100)
    add = page.evaluate("() => window._ov.shadowRoot.querySelector('.add')?.textContent")
    check(add == "Add zone", "overview: Add zone button for admins")
    page.evaluate("() => { const h = window._ov._hass; window._ov.setConfig({show_add: false}); window._ov.hass = h; }")
    page.wait_for_timeout(100)
    hidden = page.evaluate("() => !window._ov.shadowRoot.querySelector('.add') && !!window._ov.shadowRoot.querySelector('.zone')")
    check(hidden, "overview: show_add: false hides the Add zone button")
    page.evaluate("() => { const h = window._ov._hass; window._ov.setConfig({}); window._ov.hass = h; }")
    page.wait_for_timeout(100)
    tiles = page.evaluate(
        "() => [...window._ov.shadowRoot.querySelectorAll('.zone')].map(z => getComputedStyle(z).marginBottom)"
    )
    check(all(m == "8px" for m in tiles), "overview: zones as separate tiles with a gap")
    if args.screenshot:
        shot = args.screenshot.with_name(args.screenshot.stem + "-overview" + args.screenshot.suffix)
        page.locator("#ov").screenshot(path=str(shot))
        print(f"screenshot: {shot}")
    check_loader(browser, check)
    browser.close()


def check_loader(browser, check) -> None:
    """The loader in /config/www/zoneflow (frontend.py): on a normal page the
    card loads once; on a page opened while Home Assistant was starting (no
    card on it, the card not served yet) the loader keeps trying."""
    sys.path.insert(0, str(ROOT))
    from custom_components.zoneflow.frontend import CARD_URL, LOADER_JS, LOADER_URL

    for startup in (False, True):
        page = browser.new_page()
        fetched = []

        # (Playwright hands a handler the request as a second argument, so
        # the loop's values go in through a closure, not default arguments.)
        def handlers(startup, fetched):
            def card(route):
                fetched.append(route.request.url)
                if startup and len(fetched) < 3:  # ZoneFlow not up yet
                    route.fulfill(status=404, body="404: Not Found")
                else:
                    route.fulfill(path=str(CARD), content_type="text/javascript")

            tag = "" if startup else f'<script type="module" src="{CARD_URL}?v=9"></script>'

            def index(route):
                route.fulfill(body=f"<html><head>{tag}</head></html>", content_type="text/html")

            return card, index

        card, index = handlers(startup, fetched)
        page.route("http://ha.test/", index)
        page.route("http://ha.test/zoneflow_static/**", card)
        page.route("http://ha.test/local/**", lambda route: route.fulfill(body=LOADER_JS, content_type="text/javascript"))
        page.goto("http://ha.test/")
        page.wait_for_timeout(300)
        page.evaluate(f"() => import('{LOADER_URL}?v=9')")  # the dashboard resource
        page.wait_for_timeout(4500 if startup else 500)
        state = page.evaluate(
            "() => [!!customElements.get('zoneflow-card'), !!customElements.get('zoneflow-overview-card'),"
            " (window.customCards || []).filter(c => c.type.startsWith('zoneflow')).length]"
        )
        if startup:
            check(state == [True, True, 2] and len(fetched) == 3, "loader: keeps trying while Home Assistant starts")
        else:
            check(state == [True, True, 2] and fetched == [f"http://ha.test{CARD_URL}?v=9"], "loader: a normal page loads the card once")
        page.close()


if __name__ == "__main__":
    sys.exit(main())
