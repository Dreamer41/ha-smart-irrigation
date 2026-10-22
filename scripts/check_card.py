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
    ("sensor", "next_fertilizing", None), ("button", "fertilized_today", None),
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
        check(shown["buttons"] == ["Plant journal", "Settings", "Check my setup", "Calibrate the flow rate", "Recent activity", "Diagnostics"], "journal, settings and diagnostics as buttons")
        check(all(p["modal"] for p in popups.values()), "they open as popups")
        settings = popups["Settings"]["rows"]
        # (each group's name is followed by its "?" help link)
        check(popups["Settings"]["groups"][0].rstrip("?") == "How much water", "settings popup grouped")
        check(shown["status"] == "Next watering Tue 05:30", "status sentence at the top")
        check(now[:2] == ["Valve", "soil_moisture"], "valve first, names without the zone prefix")
        check("deficit_status" not in now, "deficit status left out while deficit mode is off")
        check(controls and controls[0] == "Water now | Snooze today | Fertilized", "run-now buttons; a hidden one left out")
        check("pause" in controls and "paused_until" in controls, "pause and paused-until in the controls")
        check(service[0] == "service_mode" and service[1] == "1 min | 5 min | 10 min | Reset lock", "service runs")
        check(settings[:2] == ["flow_rate_mm_per_min", "target_weekly_mm"], "settings grouped, flow rate first")
        check("rain_eff_low" not in settings, "hidden settings left out")
        check("brand_new_setting" in settings, "a setting added later appears by itself")
        check("notifications" in settings, "notifications among the settings")
        check(popups["Plant journal"]["rows"] == ["health_status", "health_notes"], "plant journal")
        check("next_fertilizing" in now, "next fertilizing date in Now")
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
        check(shown["sections"]["Controls"][0] == "Water now | Deep soak now | Snooze today | Fertilized", "an unhidden entity appears")

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

        # Quick reconfiguring never leaves extra rows behind (the Water now line is tracked too, but is not a ".row").
        page.evaluate(
            """(hass) => { const c = window._card; for (let i = 0; i < 3; i++) { c.setConfig({device_id: 'dev1', show_diagnostics: true}); c.hass = hass; } }""",
            hass,
        )
        page.wait_for_timeout(300)
        counts = page.evaluate(
            "() => [window._card._rows.filter(r => r.classList.contains('row')).length, window._card.shadowRoot.querySelectorAll('.row').length]"
        )
        check(counts[0] == counts[1], f"no stray rows after quick reconfiguring ({counts[0]} tracked, {counts[1]} shown)")
        browser.close()
        check_overview(pw, check, args)
        check_greenhouse(pw, check)

    print(f"\n{len(failures)} failed" if failures else "\nall card checks passed")
    return 1 if failures else 0


def greenhouse_hass() -> dict:
    """A climate-only zone (no valve): the irrigation status is hidden."""
    keys = [
        ("sensor", "status", None, True), ("button", "run_routine", None, True),
        ("sensor", "greenhouse_status", None, False), ("sensor", "inside_vpd", None, False),
        ("binary_sensor", "ventilation_allowed", None, False), ("switch", "greenhouse_control", None, False),
        ("number", "heat_temp", "config", False), ("number", "vent_temp", "config", False),
        ("select", "heater_failsafe", "config", False), ("select", "ventilation_failsafe", "config", False),
        ("select", "misting_trigger", "config", False), ("number", "mist_temp", "config", False),
        ("switch", "mist_at_night", "config", False), ("select", "notifications", "config", False),
    ]
    entities, states = {}, {}
    for domain, key, category, hidden in keys:
        entity_id = f"{domain}.tunnel_{key}"
        entities[entity_id] = {"entity_id": entity_id, "device_id": "gh", "platform": "zoneflow",
                               "translation_key": key, "entity_category": category, "hidden": hidden}
        states[entity_id] = {"entity_id": entity_id, "state": "on", "attributes": {"friendly_name": f"Tunnel {key}"}}
    states["sensor.tunnel_greenhouse_status"].update(
        state="Heating (8.5 \u00b0C)", attributes={"code": "heating", "friendly_name": "Tunnel greenhouse_status"})
    return {"entities": entities, "states": states, "locale": {"language": "en"},
            "devices": {"gh": {"id": "gh", "name": "Tunnel", "name_by_user": None}}, "config": {"time_zone": "UTC"}}


def check_greenhouse(pw, check) -> None:
    browser = pw.chromium.launch()
    page = browser.new_page()
    page.route("http://card.test/", lambda route: route.fulfill(body=HARNESS, content_type="text/html"))
    page.route("http://card.test/card.js", lambda route: route.fulfill(path=str(CARD), content_type="text/javascript"))
    page.goto("http://card.test/")
    hass = greenhouse_hass()
    page.evaluate(
        """(hass) => {
            const card = document.createElement('zoneflow-card');
            card.setConfig({device_id: 'gh'});
            card.hass = hass;
            window._card = card;
            document.body.appendChild(card);
        }""",
        hass,
    )
    page.wait_for_timeout(300)
    shown = page.evaluate(JS_SECTIONS)
    check(shown["status"] == "Heating (8.5 \u00b0C)", "greenhouse: the status line is the climate status")
    icon = page.evaluate("() => window._card.shadowRoot.querySelector('.header ha-icon').getAttribute('icon')")
    check(icon == "mdi:greenhouse", "greenhouse: greenhouse icon without a valve")
    now = shown["sections"].get("Now", [])
    check(now[:3] == ["greenhouse_status", "inside_vpd", "ventilation_allowed"], "greenhouse: climate rows in Now")
    check("greenhouse_control" in shown["sections"].get("Controls", [""])[0:1], "greenhouse: control switch in Controls")
    check("Water now" not in " ".join(shown["sections"].get("Controls", [])), "greenhouse: no watering buttons")
    check(page.evaluate("() => window._card.shadowRoot.querySelector('.status').classList.contains('warn')") is False,
          "greenhouse: heating is not a warning")
    popups = page.evaluate(JS_POPUPS)
    groups = popups["Settings"]["groups"]
    check([g.rstrip("?") for g in groups[:2]] == ["Climate control", "Misting"], "greenhouse: climate and misting settings groups first")
    check("heater_failsafe" in popups["Settings"]["rows"] and "mist_temp" in popups["Settings"]["rows"],
          "greenhouse: its settings are in the popup")
    hass["states"]["sensor.tunnel_greenhouse_status"]["attributes"]["code"] = "failsafe"
    page.evaluate("(hass) => { window._card.hass = hass; }", hass)
    page.wait_for_timeout(100)
    check(page.evaluate("() => window._card.shadowRoot.querySelector('.status').classList.contains('warn')"),
          "greenhouse: failsafe is shown as a warning")
    # In the overview: the climate status, the greenhouse icon, no water button action.
    ov = overview_hass()
    ov["entities"].update(hass["entities"]); ov["states"].update(hass["states"]); ov["devices"].update(hass["devices"])
    page.evaluate(
        """(hass) => { const c = document.createElement('zoneflow-overview-card'); c.setConfig({}); c.hass = hass;
            c.id = 'ov'; document.body.appendChild(c); }""",
        ov,
    )
    page.wait_for_timeout(300)
    rows = {r["name"]: r for r in page.evaluate(JS_OVERVIEW)}
    tunnel = rows.get("Tunnel", {})
    check(tunnel.get("icon") == "mdi:greenhouse" and tunnel.get("status") == "Heating (8.5 \u00b0C)" or tunnel.get("warn"),
          "overview: a climate-only zone shows its climate status")
    check(tunnel.get("water_disabled") is True and tunnel.get("next") == "\u2014", "overview: nothing to water, no next watering")
    check(tunnel.get("warn") is True, "overview: failsafe is a warning")
    browser.close()


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
                ("sensor", "last_cycle_water_liters", None), ("button", "run_routine", None),
                ("sensor", "next_fertilizing", None)]
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
        feed = {"tom": ("2026-09-20", True), "chi": ("2026-10-12", False)}.get(dev)
        if feed:  # Mango: no feed recorded yet
            states[f"sensor.{dev}_next_fertilizing"]["state"] = feed[0]
            states[f"sensor.{dev}_next_fertilizing"]["attributes"]["due"] = feed[1]
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
      feed: r.querySelector('.feed').hidden ? null : r.querySelector('.feed span').textContent,
      feed_due: r.querySelector('.feed').classList.contains('due'),
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
    check(rows[2]["feed"] == "Fertilize now" and rows[2]["feed_due"], "overview: fertilizing due shows under the name")
    check(rows[0]["feed"] == "Mon, Oct 12" and not rows[0]["feed_due"], "overview: next fertilizing date under the name")
    check(rows[1]["feed"] is None, "overview: nothing before a first feed is recorded")
    check(rows[0]["status"] == "Rain skip" and rows[2]["status"] == "Watered today", "overview: short status labels")
    check(rows[1]["status"] == "Paused" and rows[1]["next"] == "—" and rows[1]["water_disabled"], "overview: paused zone")
    check(rows[0]["last"] == "8.0 mm · 18 L" and rows[2]["last"] == "12.0 mm", "overview: measured litres, else the estimate")
    check("Mon" in rows[2]["next"] or "Tue" in rows[2]["next"], "overview: next as weekday and time")

    def headline():
        return page.evaluate("() => { const h = window._ov.shadowRoot.querySelector('.garden-headline'); return [h.textContent, h.className]; }")

    check(headline() == ["Your garden is doing well.", "garden-headline ok"], "overview: a plain sentence says the garden is fine")

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

    def set_codes(**codes):
        page.evaluate(
            """(codes) => { const h = JSON.parse(JSON.stringify(window._ovHass)); h.callService = window._ovHass.callService;
                for (const [dev, code] of Object.entries(codes)) h.states[`sensor.${dev}_status`].attributes.code = code;
                window._ovHass = h; window._ov.hass = h; }""",
            codes,
        )
        page.wait_for_timeout(100)

    check(headline() == ["Watering now: Chilis", "garden-headline active"], "overview: the sentence says what is watering")
    set_codes(chi="interrupted")
    check(headline() == ["Chilis: needs a look", "garden-headline warn"], "overview: a stopped zone is an amber sentence")
    set_codes(chi="skipped_rain_credit", tom="skipped_soil_wet")
    check(headline() == ["Nothing needs water right now. Rain and soil have it covered.", "garden-headline ok"],
          "overview: rain and wet soil have it covered")
    set_codes(chi="paused", tom="paused")
    check(headline() == ["Watering is paused.", "garden-headline ok"], "overview: everything paused")
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
    check_water_tips(browser, check)
    check_activity(browser, check)
    check_details(browser, check)
    browser.close()


def check_loader(browser, check) -> None:
    """The loader frontend/zoneflow-loader.js (frontend.py): on a normal page the
    card loads once; on a page opened while Home Assistant was starting (no
    card on it, the card not served yet) the loader keeps trying."""
    sys.path.insert(0, str(ROOT))
    from custom_components.zoneflow.frontend import CARD_URL, LOADER_URL

    loader_js = (ROOT / "custom_components" / "zoneflow" / "frontend" / "zoneflow-loader.js").read_text(encoding="utf-8")

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
        page.route(f"http://ha.test{LOADER_URL}*", lambda route: route.fulfill(body=loader_js, content_type="text/javascript"))
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


def check_water_tips(browser, check) -> None:
    """The Watering tips popup: a search that asks the integration, results with their amounts in the
    zone's units, and Apply, which sets the three weekly targets in proportion."""
    for unit, now, expected_amounts, expected_calls, expected_crop_calls in (
        # mm: 25.4-38.1 mm -> middle 31.75 -> normal 32 (step 0.5); hot 45 x 1.058 = 47.6 -> 47.5; cool 20 x 1.058 = 21.2 -> 21
        ("mm", {"normal": 30, "hot": 45, "cool": 20},
         ["25.4\u201338.1 mm per week, Crop factor 1.05", "about 21.6 mm per week, Crop factor 0.85",
          "about 12.7 mm per week, Crop factor 0.5 (estimate)"],
         [47.5, 21, 32, 1.05], [32.5, 14.5, 21.5, 0.85]),
        # in: 1-1.5 in -> middle 1.25 -> normal 1.25 (step 0.05); hot 1.8 x 1.0417 = 1.875 -> 1.9; cool 0.8 x 1.0417 = 0.83 -> 0.85
        ("in", {"normal": 1.2, "hot": 1.8, "cool": 0.8},
         ["1\u20131.5 in per week, Crop factor 1.05", "about 0.85 in per week, Crop factor 0.85",
          "about 0.5 in per week, Crop factor 0.5 (estimate)"],
         [1.9, 0.85, 1.25, 1.05], [1.3, 0.55, 0.85, 0.85]),
    ):
        page = browser.new_page()
        page.route("http://card.test/", lambda route: route.fulfill(body=HARNESS, content_type="text/html"))
        page.route("http://card.test/card.js", lambda route: route.fulfill(path=str(CARD), content_type="text/javascript"))
        page.goto("http://card.test/")
        hass = fake_hass()
        step, low, high = (0.5, 5, 80) if unit == "mm" else (0.05, 0.2, 3.2)
        for key, entity_key in (("normal", "target_weekly_mm"), ("hot", "target_weekly_hot_mm"), ("cool", "target_weekly_cool_mm")):
            entity_id = f"number.chilis_{entity_key}"
            hass["entities"][entity_id] = {
                "entity_id": entity_id, "device_id": DEVICE, "platform": "zoneflow", "translation_key": entity_key,
                "entity_category": "config", "hidden": False,
            }
            hass["states"][entity_id] = {
                "entity_id": entity_id, "state": str(now[key]),
                "attributes": {"friendly_name": entity_key, "unit_of_measurement": unit, "min": low, "max": high, "step": step},
            }
        hass["entities"]["number.chilis_crop_coefficient"] = {
            "entity_id": "number.chilis_crop_coefficient", "device_id": DEVICE, "platform": "zoneflow",
            "translation_key": "crop_coefficient", "entity_category": "config", "hidden": False,
        }
        hass["states"]["number.chilis_crop_coefficient"] = {
            "entity_id": "number.chilis_crop_coefficient", "state": "0.8",
            "attributes": {"friendly_name": "crop_coefficient", "min": 0.1, "max": 1.5, "step": 0.05},
        }
        hass["states"]["sensor.chilis_status"]["attributes"]["plants"] = [{"id": "p1", "name": "Peppers 'Jalape\u00f1o'", "type": "chilis", "main": True}]
        hass["user"] = {"is_admin": True}
        page.evaluate(
            """([hass, device]) => {
                window._calls = [];
                window._queries = [];
                hass.callService = async (domain, service, data) => { window._calls.push([domain, service, data]); };
                hass.callWS = async (msg) => {
                    window._queries.push(msg.query);
                    return {
                        results: [
                            {kind: 'category', name: 'Pepper', category: 'pepper', latin: '', low_mm: 25.4, high_mm: 38.1, kc: 1.05, note: '', count: 69},
                            {kind: 'crop', name: 'Avocado', id: 'avocado', category: '', latin: '', low_mm: 21.6, high_mm: 21.6, mm_estimate: true,
                             kc: 0.85, kc_source: 'fao56', note: 'Kc 0.6 / 0.85 / 0.75'},
                            {kind: 'plant', name: 'Pink Moss', category: 'ground-cover', latin: '', low_mm: null, high_mm: null, kc: null,
                             note: 'Moderate, regular watering'},
                            {kind: 'plant', name: 'Yarrow', category: 'flower', latin: '', low_mm: 12.7, high_mm: 12.7, mm_estimate: true,
                             kc: 0.5, kc_estimate: true, kc_source: 'landscape', note: 'Moderate, regular watering'},
                        ],
                        source: {name: 'Plant Variety Database', author: 'Wind River Greens', license: 'CC BY 4.0',
                                 url: 'https://github.com/bripatch/plant-variety-database',
                                 license_url: 'https://creativecommons.org/licenses/by/4.0/'},
                        kc_sources: {
                            fao56: {short: 'FAO-56', name: 'FAO Irrigation and drainage paper 56, Table 12',
                                    author: 'Allen, Pereira, Raes and Smith (1998)', url: 'https://www.fao.org/3/x0490E/x0490e00.htm'},
                            landscape: {short: 'estimate', name: 'Landscape plant factors', author: 'University of California',
                                        url: 'https://ucanr.edu/site/center-landscape-urban-horticulture/plant-factor-or-crop-coefficient-whats-difference'},
                            derived: {short: 'estimate', name: 'Weekly amount worked out from the crop factor', author: 'ZoneFlow',
                                      url: 'https://github.com/Dreamer41/ha-smart-irrigation'},
                        },
                    };
                };
                const card = document.createElement('zoneflow-card');
                card.setConfig({device_id: device});
                card.hass = hass;
                document.body.appendChild(card);
                window._card = card;
            }""",
            [hass, DEVICE],
        )
        page.wait_for_timeout(200)
        opened = page.evaluate(
            """async () => {
                const root = window._card.shadowRoot;
                const button = [...root.querySelectorAll('.more button')].find((b) => b.textContent === 'Watering tips');
                if (!button) return null;
                button.click();
                await new Promise((r) => setTimeout(r, 400));
                const dialog = root.querySelector('dialog');
                return {
                    query: dialog.querySelector('input').value,
                    names: [...dialog.querySelectorAll('.tips-name')].map((n) => n.textContent),
                    amounts: [...dialog.querySelectorAll('.tips-amount')].map((n) => n.textContent),
                    buttons: [...dialog.querySelectorAll('.tips-row .plant-button')].length,
                    notes: [...dialog.querySelectorAll('.tips-row .group-note')].map((n) => n.textContent)
                        .filter((text) => text.startsWith('Crop table') || text.startsWith('An estimate')),
                    credit: [...dialog.querySelectorAll('.group-note')].pop().textContent,
                    links: [...dialog.querySelectorAll('.group-note')].pop().querySelectorAll('a').length,
                    asked: window._queries,
                };
            }"""
        )
        check(opened is not None, f"water tips ({unit}): the button is there for an administrator")
        if opened is None:
            page.close()
            continue
        check(opened["query"] == "Peppers" and opened["asked"] == ["Peppers"], f"water tips ({unit}): starts with the zone's plant, without its variety")
        check(opened["names"] == ["Pepper", "Avocado", "Pink Moss", "Yarrow"], f"water tips ({unit}): the results")
        check(opened["amounts"] == expected_amounts,
              f"water tips ({unit}): the amounts in the zone's units, estimates marked, and the crop factor")
        check(opened["buttons"] == 3, f"water tips ({unit}): only a result with an amount or a crop factor can be used")
        check("CC BY 4.0" in opened["credit"] and "Allen" in opened["credit"] and "University of California" in opened["credit"]
              and opened["links"] == 5, f"water tips ({unit}): every source and the license are shown and linked")
        check(opened["notes"] == ["Crop table: FAO-56.",
                                  "An estimate from the plant's water-use class (landscape plant factor), not a measured value."],
              f"water tips ({unit}): the note says where a crop is from and when a value is an estimate")
        result = page.evaluate(
            """async () => {
                const dialog = window._card.shadowRoot.querySelector('dialog');
                dialog.querySelector('.tips-row .plant-button').click();
                await new Promise((r) => setTimeout(r, 100));
                const proposal = dialog.querySelector('.tips-proposal').textContent;
                const before = window._calls.length;
                [...dialog.querySelectorAll('.tips-proposal .plant-button')].find((b) => b.textContent === 'Apply').click();
                await new Promise((r) => setTimeout(r, 100));
                return {proposal, before, calls: window._calls.map((c) => [c[0], c[1], c[2].entity_id, c[2].value])};
            }"""
        )
        check(result["before"] == 0, f"water tips ({unit}): nothing is changed until Apply")
        check([c[3] for c in result["calls"]] == expected_calls, f"water tips ({unit}): the three targets in proportion, then the crop factor")
        check(all(c[0] == "number" and c[1] == "set_value" for c in result["calls"]), f"water tips ({unit}): through number.set_value")
        check("Suggestion: Pepper" in result["proposal"] and "Crop factor: 0.8" in result["proposal"],
              f"water tips ({unit}): the suggestion names what it is from and shows the crop factor")
        only = page.evaluate(
            """async () => {
                const dialog = window._card.shadowRoot.querySelector('dialog');
                window._calls.length = 0;
                dialog.querySelectorAll('.tips-row .plant-button')[1].click();
                await new Promise((r) => setTimeout(r, 100));
                const proposal = dialog.querySelector('.tips-proposal').textContent;
                [...dialog.querySelectorAll('.tips-proposal .plant-button')].find((b) => b.textContent === 'Apply').click();
                await new Promise((r) => setTimeout(r, 100));
                return {proposal, calls: window._calls.map((c) => c[2].value)};
            }"""
        )
        check(only["calls"] == expected_crop_calls and "Crop factor: 0.8" in only["proposal"],
              f"water tips ({unit}): a crop's weekly amount is worked out from its crop factor, and both are applied")
        page.close()


def check_activity(browser, check) -> None:
    """The Recent activity popup: one line per decision from the status sensor's history, newest first, with the
    runs and skips and their reasons; the "next watering" and waiting states are left out."""
    for empty in (False, True):
        page = browser.new_page()
        page.route("http://card.test/", lambda route: route.fulfill(body=HARNESS, content_type="text/html"))
        page.route("http://card.test/card.js", lambda route: route.fulfill(path=str(CARD), content_type="text/javascript"))
        page.goto("http://card.test/")
        hass = fake_hass()
        page.evaluate(
            """([hass, device, empty]) => {
                window._asked = [];
                hass.callWS = async (msg) => {
                    window._asked.push(msg);
                    const now = Date.now();
                    const iso = (hoursAgo) => new Date(now - hoursAgo * 3600000).toISOString();
                    const lu = (hoursAgo) => (now - hoursAgo * 3600000) / 1000;
                    const st = (state, code, decided, hoursAgo, cycle) => ({s: state, a: {code, decided_at: decided, cycle}, lu: lu(hoursAgo)});
                    return {'sensor.chilis_status': empty ? [] : [
                        st('Routine done at 05:30: 13 mm in 8 min — next Fri 05:30', 'done', iso(72), 72, 'routine'),
                        st('Routine done at 05:30: 13 mm in 8 min — next Sat 05:30', 'done', iso(72), 71, 'routine'),
                        st('Next watering Fri 05:30, estimated 13 mm', 'next', null, 70, null),
                        st('Waiting for the soil to dry (45%)', 'waiting_soil_wet', iso(60), 60, 'routine'),
                        st('Routine skipped at 05:30: recent rain (4.2 mm) covers the 13 mm needed', 'skipped_rain_credit', iso(48), 48, 'routine'),
                        st('Routine stopped at 05:34 before finishing', 'interrupted', iso(24), 24, 'routine'),
                        st('Watering now: Routine', 'watering', null, 1, null),
                    ]};
                };
                const card = document.createElement('zoneflow-card');
                card.setConfig({device_id: device});
                card.hass = hass;
                document.body.appendChild(card);
                window._card = card;
            }""",
            [hass, DEVICE, empty],
        )
        page.wait_for_timeout(200)
        opened = page.evaluate(
            """async () => {
                const root = window._card.shadowRoot;
                const button = [...root.querySelectorAll('.more button')].find((b) => b.textContent === 'Recent activity');
                if (!button) return null;
                button.click();
                await new Promise((r) => setTimeout(r, 300));
                const dialog = root.querySelector('dialog');
                return {
                    rows: [...dialog.querySelectorAll('.activity-row')].map((r) => [r.children[1].children[0].textContent, r.className]),
                    list: dialog.querySelector('.activity-list').textContent,
                    asked: window._asked.map((m) => [m.type, m.entity_ids]),
                };
            }"""
        )
        check(opened is not None, "activity: the button is on the zone card")
        if opened is None:
            page.close()
            continue
        check(opened["asked"] == [["history/history_during_period", ["sensor.chilis_status"]]], "activity: asks the history of the zone's status")
        if empty:
            check(opened["rows"] == [] and "Nothing yet" in opened["list"], "activity: a friendly line when there is nothing yet")
        else:
            texts = [r[0] for r in opened["rows"]]
            check(texts == ["Watering now: Routine", "Routine stopped at 05:34 before finishing",
                            "Routine skipped at 05:30: recent rain (4.2 mm) covers the 13 mm needed",
                            "Routine done at 05:30: 13 mm in 8 min — next Fri 05:30"],
                  "activity: one line per decision, newest first, without the next watering and waiting lines")
            classes = [r[1] for r in opened["rows"]]
            check("ran" in classes[0] and "warn" in classes[1] and "ran" in classes[3] and "warn" not in classes[2],
                  "activity: runs are marked, a stopped run is amber")
        page.close()

def check_details(browser, check) -> None:
    """The technical numbers of the Now section start folded behind Show details."""
    page = browser.new_page()
    page.route("http://card.test/", lambda route: route.fulfill(body=HARNESS, content_type="text/html"))
    page.route("http://card.test/card.js", lambda route: route.fulfill(path=str(CARD), content_type="text/javascript"))
    page.goto("http://card.test/")
    hass = fake_hass()
    for key, value in (("routine_weekly_target", "30"), ("avg_peak_temp_3d", "31.5")):
        entity_id = f"sensor.chilis_{key}"
        hass["entities"][entity_id] = {
            "entity_id": entity_id, "device_id": DEVICE, "platform": "zoneflow", "translation_key": key,
            "entity_category": None, "hidden": False,
        }
        hass["states"][entity_id] = {"entity_id": entity_id, "state": value, "attributes": {"friendly_name": key}}
    page.evaluate(
        """([hass, device]) => {
            const card = document.createElement('zoneflow-card');
            card.setConfig({device_id: device});
            card.hass = hass;
            document.body.appendChild(card);
            window._card = card;
        }""",
        [hass, DEVICE],
    )
    page.wait_for_timeout(300)
    probe = """() => {
        const now = [...window._card.shadowRoot.querySelectorAll('.section')].find((s) => s.querySelector('.section-title').textContent === 'Now');
        const toggle = now.querySelector('.details-toggle');
        const lists = now.querySelectorAll('.rows');
        return {toggle: toggle && toggle.textContent, hidden: lists[1] && lists[1].hidden, folded: lists[1] ? lists[1].querySelectorAll('.row').length : -1,
                shown: lists[0].querySelectorAll('.row').length};
    }"""
    first = page.evaluate(probe)
    check(first["toggle"] == "Show details" and first["hidden"] is True and first["folded"] == 2,
          "details: the technical numbers start folded behind Show details")
    check(first["shown"] >= 1, "details: the rest of the Now section stays visible")
    page.evaluate("() => window._card.shadowRoot.querySelector('.details-toggle').click()")
    opened = page.evaluate(probe)
    check(opened["toggle"] == "Hide details" and opened["hidden"] is False, "details: one press shows them")
    page.close()


if __name__ == "__main__":
    sys.exit(main())
