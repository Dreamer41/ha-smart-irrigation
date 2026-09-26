/*
 * ZoneFlow zone card -- shipped with the integration and loaded on every
 * dashboard automatically (no resource to add, nothing to update by hand).
 *
 *   type: custom:zoneflow-card
 *   device_id: <the zone's device>
 *
 * It finds the zone's entities through its device, so new entities from a
 * ZoneFlow update show up by themselves, and anything the zone doesn't use
 * (hidden entities) stays out. Rows are Home Assistant's own entity rows,
 * so units, sliders, toggles and more-info work as everywhere else.
 */
const CARD_VERSION = "1.5.0";

// Card texts per language (English is the fallback for anything missing).
const I18N = {
  "en": {
    "now": "Now",
    "controls": "Controls",
    "service": "Service & checks (not counted as watering)",
    "journal": "Plant journal",
    "settings": "Settings",
    "diagnostics": "Diagnostics",
    "valve": "Valve",
    "water_now": "Water now",
    "deep_soak_now": "Deep soak now",
    "snooze": "Snooze today",
    "reset_lock": "Reset lock",
    "min": "min",
    "pick_zone": "Pick a ZoneFlow zone for this card.",
    "not_found": "This ZoneFlow zone wasn't found (removed, or not loaded yet).",
    "zone": "Zone",
    "show_journal": "Show the plant journal",
    "show_settings": "Show the settings",
    "show_diagnostics": "Show the diagnostics",
    "groups": {
      "amounts": "How much water",
      "rain": "Rain, forecast and frost",
      "deep_soak": "Deep soak",
      "soil": "Soil",
      "growth": "Growth",
      "deficit": "Deficit mode",
      "history": "History",
      "safety": "Safety limits and pump",
      "notifications": "Notifications",
      "more": "More"
    }
  },
  "de": {
    "now": "Jetzt",
    "controls": "Steuerung",
    "service": "Wartung & Tests (zählt nicht als Bewässerung)",
    "journal": "Pflanzentagebuch",
    "settings": "Einstellungen",
    "diagnostics": "Diagnose",
    "valve": "Ventil",
    "water_now": "Jetzt gießen",
    "deep_soak_now": "Jetzt tief wässern",
    "snooze": "Heute aussetzen",
    "reset_lock": "Sperre zurücksetzen",
    "min": "min",
    "pick_zone": "Wähle eine ZoneFlow-Zone für diese Karte.",
    "not_found": "Diese ZoneFlow-Zone wurde nicht gefunden (entfernt oder noch nicht geladen).",
    "zone": "Zone",
    "show_journal": "Pflanzentagebuch anzeigen",
    "show_settings": "Einstellungen anzeigen",
    "show_diagnostics": "Diagnose anzeigen",
    "groups": {
      "amounts": "Wassermenge",
      "rain": "Regen, Vorhersage und Frost",
      "deep_soak": "Tiefenbewässerung",
      "soil": "Boden",
      "growth": "Wachstum",
      "deficit": "Defizitmodus",
      "history": "Verlauf",
      "safety": "Sicherheitslimits und Pumpe",
      "notifications": "Benachrichtigungen",
      "more": "Mehr"
    }
  },
  "es": {
    "now": "Ahora",
    "controls": "Controles",
    "service": "Mantenimiento y pruebas (no cuentan como riego)",
    "journal": "Diario de la planta",
    "settings": "Ajustes",
    "diagnostics": "Diagnóstico",
    "valve": "Válvula",
    "water_now": "Regar ahora",
    "deep_soak_now": "Riego profundo ahora",
    "snooze": "Omitir hoy",
    "reset_lock": "Restablecer bloqueo",
    "min": "min",
    "pick_zone": "Elige una zona de ZoneFlow para esta tarjeta.",
    "not_found": "No se encontró esta zona de ZoneFlow (eliminada o aún no cargada).",
    "zone": "Zona",
    "show_journal": "Mostrar el diario de la planta",
    "show_settings": "Mostrar los ajustes",
    "show_diagnostics": "Mostrar el diagnóstico",
    "groups": {
      "amounts": "Cuánta agua",
      "rain": "Lluvia, previsión y heladas",
      "deep_soak": "Riego profundo",
      "soil": "Suelo",
      "growth": "Crecimiento",
      "deficit": "Modo déficit",
      "history": "Historial",
      "safety": "Límites de seguridad y bomba",
      "notifications": "Notificaciones",
      "more": "Más"
    }
  },
  "fi": {
    "now": "Nyt",
    "controls": "Ohjaus",
    "service": "Huolto ja tarkistukset (ei lasketa kasteluksi)",
    "journal": "Kasvipäiväkirja",
    "settings": "Asetukset",
    "diagnostics": "Diagnostiikka",
    "valve": "Venttiili",
    "water_now": "Kastele nyt",
    "deep_soak_now": "Syväkastele nyt",
    "snooze": "Ohita tänään",
    "reset_lock": "Nollaa lukko",
    "min": "min",
    "pick_zone": "Valitse tälle kortille ZoneFlow-vyöhyke.",
    "not_found": "Tätä ZoneFlow-vyöhykettä ei löytynyt (poistettu tai ei vielä ladattu).",
    "zone": "Vyöhyke",
    "show_journal": "Näytä kasvipäiväkirja",
    "show_settings": "Näytä asetukset",
    "show_diagnostics": "Näytä diagnostiikka",
    "groups": {
      "amounts": "Vesimäärä",
      "rain": "Sade, ennuste ja halla",
      "deep_soak": "Syväkastelu",
      "soil": "Maa",
      "growth": "Kasvu",
      "deficit": "Vajaakastelu",
      "history": "Historia",
      "safety": "Turvarajat ja pumppu",
      "notifications": "Ilmoitukset",
      "more": "Lisää"
    }
  },
  "fr": {
    "now": "Maintenant",
    "controls": "Commandes",
    "service": "Maintenance et contrôles (non comptés comme arrosage)",
    "journal": "Carnet de culture",
    "settings": "Paramètres",
    "diagnostics": "Diagnostics",
    "valve": "Vanne",
    "water_now": "Arroser maintenant",
    "deep_soak_now": "Arrosage profond",
    "snooze": "Sauter aujourd'hui",
    "reset_lock": "Réinitialiser le verrou",
    "min": "min",
    "pick_zone": "Choisissez une zone ZoneFlow pour cette carte.",
    "not_found": "Zone ZoneFlow introuvable (supprimée ou pas encore chargée).",
    "zone": "Zone",
    "show_journal": "Afficher le carnet de culture",
    "show_settings": "Afficher les paramètres",
    "show_diagnostics": "Afficher les diagnostics",
    "groups": {
      "amounts": "Quantité d'eau",
      "rain": "Pluie, prévisions et gel",
      "deep_soak": "Arrosage profond",
      "soil": "Sol",
      "growth": "Croissance",
      "deficit": "Arrosage réduit",
      "history": "Historique",
      "safety": "Limites de sécurité et pompe",
      "notifications": "Notifications",
      "more": "Plus"
    }
  },
  "it": {
    "now": "Adesso",
    "controls": "Comandi",
    "service": "Manutenzione e verifiche (non conta come irrigazione)",
    "journal": "Diario delle piante",
    "settings": "Impostazioni",
    "diagnostics": "Diagnostica",
    "valve": "Valvola",
    "water_now": "Irriga ora",
    "deep_soak_now": "Irrigazione profonda ora",
    "snooze": "Salta oggi",
    "reset_lock": "Reimposta blocco",
    "min": "min",
    "pick_zone": "Scegli una zona ZoneFlow per questa scheda.",
    "not_found": "Questa zona ZoneFlow non è stata trovata (rimossa o non ancora caricata).",
    "zone": "Zona",
    "show_journal": "Mostra il diario delle piante",
    "show_settings": "Mostra le impostazioni",
    "show_diagnostics": "Mostra la diagnostica",
    "groups": {
      "amounts": "Quanta acqua",
      "rain": "Pioggia, previsioni e gelo",
      "deep_soak": "Irrigazione profonda",
      "soil": "Terreno",
      "growth": "Crescita",
      "deficit": "Modalità deficit",
      "history": "Cronologia",
      "safety": "Limiti di sicurezza e pompa",
      "notifications": "Notifiche",
      "more": "Altro"
    }
  },
  "nl": {
    "now": "Nu",
    "controls": "Bediening",
    "service": "Onderhoud en controles (telt niet als water geven)",
    "journal": "Plantendagboek",
    "settings": "Instellingen",
    "diagnostics": "Diagnose",
    "valve": "Klep",
    "water_now": "Nu water geven",
    "deep_soak_now": "Nu diepe watergift",
    "snooze": "Vandaag overslaan",
    "reset_lock": "Slot resetten",
    "min": "min",
    "pick_zone": "Kies een ZoneFlow-zone voor deze kaart.",
    "not_found": "Deze ZoneFlow-zone is niet gevonden (verwijderd of nog niet geladen).",
    "zone": "Zone",
    "show_journal": "Plantendagboek tonen",
    "show_settings": "Instellingen tonen",
    "show_diagnostics": "Diagnose tonen",
    "groups": {
      "amounts": "Hoeveel water",
      "rain": "Regen, voorspelling en vorst",
      "deep_soak": "Diepe watergift",
      "soil": "Bodem",
      "growth": "Groei",
      "deficit": "Spaarmodus",
      "history": "Geschiedenis",
      "safety": "Veiligheidslimieten en pomp",
      "notifications": "Meldingen",
      "more": "Meer"
    }
  },
  "pl": {
    "now": "Teraz",
    "controls": "Sterowanie",
    "service": "Serwis i testy (nie liczą się jako podlewanie)",
    "journal": "Dziennik rośliny",
    "settings": "Ustawienia",
    "diagnostics": "Diagnostyka",
    "valve": "Zawór",
    "water_now": "Podlej teraz",
    "deep_soak_now": "Podlej głęboko teraz",
    "snooze": "Pomiń dzisiaj",
    "reset_lock": "Zresetuj blokadę",
    "min": "min",
    "pick_zone": "Wybierz strefę ZoneFlow dla tej karty.",
    "not_found": "Nie znaleziono tej strefy ZoneFlow (usunięta albo jeszcze niezaładowana).",
    "zone": "Strefa",
    "show_journal": "Pokaż dziennik rośliny",
    "show_settings": "Pokaż ustawienia",
    "show_diagnostics": "Pokaż diagnostykę",
    "groups": {
      "amounts": "Ile wody",
      "rain": "Deszcz, prognoza i przymrozki",
      "deep_soak": "Głębokie podlewanie",
      "soil": "Gleba",
      "growth": "Wzrost",
      "deficit": "Tryb deficytowy",
      "history": "Historia",
      "safety": "Limity bezpieczeństwa i pompa",
      "notifications": "Powiadomienia",
      "more": "Więcej"
    }
  },
  "pt": {
    "now": "Agora",
    "controls": "Comandos",
    "service": "Manutenção e testes (não conta como rega)",
    "journal": "Diário da planta",
    "settings": "Definições",
    "diagnostics": "Diagnóstico",
    "valve": "Válvula",
    "water_now": "Regar agora",
    "deep_soak_now": "Rega profunda agora",
    "snooze": "Não regar hoje",
    "reset_lock": "Desbloquear",
    "min": "min",
    "pick_zone": "Escolha uma zona ZoneFlow para este cartão.",
    "not_found": "Esta zona ZoneFlow não foi encontrada (removida ou ainda não carregada).",
    "zone": "Zona",
    "show_journal": "Mostrar o diário da planta",
    "show_settings": "Mostrar as definições",
    "show_diagnostics": "Mostrar o diagnóstico",
    "groups": {
      "amounts": "Quantidade de água",
      "rain": "Chuva, previsão e geada",
      "deep_soak": "Rega profunda",
      "soil": "Solo",
      "growth": "Crescimento",
      "deficit": "Rega deficitária",
      "history": "Histórico",
      "safety": "Limites de segurança e bomba",
      "notifications": "Notificações",
      "more": "Mais"
    }
  },
  "sv": {
    "now": "Nu",
    "controls": "Styrning",
    "service": "Service och kontroller (räknas inte som vattning)",
    "journal": "Växtdagbok",
    "settings": "Inställningar",
    "diagnostics": "Diagnostik",
    "valve": "Ventil",
    "water_now": "Vattna nu",
    "deep_soak_now": "Djupvattna nu",
    "snooze": "Hoppa över idag",
    "reset_lock": "Återställ lås",
    "min": "min",
    "pick_zone": "Välj en ZoneFlow-zon för det här kortet.",
    "not_found": "ZoneFlow-zonen hittades inte (borttagen eller inte laddad än).",
    "zone": "Zon",
    "show_journal": "Visa växtdagboken",
    "show_settings": "Visa inställningarna",
    "show_diagnostics": "Visa diagnostiken",
    "groups": {
      "amounts": "Hur mycket vatten",
      "rain": "Regn, prognos och frost",
      "deep_soak": "Djupvattning",
      "soil": "Jord",
      "growth": "Tillväxt",
      "deficit": "Sparläge",
      "history": "Historik",
      "safety": "Säkerhetsgränser och pump",
      "notifications": "Aviseringar",
      "more": "Mer"
    }
  }
};

// Where each entity goes, by "<domain>.<translation key>". Anything not
// listed lands by its category: settings -> "More", diagnostics ->
// Diagnostics, everyday -> Now. So entities added later appear by themselves.
const NOW = [
  "sensor.soil_moisture",
  "sensor.soil_moisture_status",
  "sensor.next_irrigation_estimate",
  "sensor.days_until_next_run",
  "sensor.last_cycle_water_liters",
  "sensor.rain_today",
  "sensor.routine_weekly_target",
  "sensor.avg_peak_temp_3d",
  "sensor.growth_ramp_pct",
  "sensor.deficit_status",
];
// Shown only while they say something (deficit mode on).
const ONLY_WHEN = {
  "sensor.deficit_status": (state) => state && state.state !== "off",
};
const CONTROLS = ["switch.pause", "datetime.paused_until", "switch.deficit_mode"];
const JOURNAL = ["select.health_status", "text.health_notes", "datetime.last_fertilizing", "select.fertilizing_interval"];
const SETTINGS_GROUPS = [
  ["amounts", [
    "number.flow_rate_mm_per_min", "number.target_weekly_mm", "number.target_weekly_hot_mm",
    "number.target_weekly_cool_mm", "select.demand_model", "number.crop_coefficient",
    "number.hot_temp_threshold", "number.cool_temp_threshold", "number.fallback_temp",
    "number.routine_pulse_count", "number.routine_pulse_rest_minutes",
  ]],
  ["rain", [
    "number.routine_drydown_days", "number.rain_mm_per_tip", "number.preirrigation_rain_threshold_mm",
    "number.forecast_rain_threshold_mm", "number.forecast_probability_threshold_pct",
    "number.forecast_dry_override_days", "number.frost_guard_temp",
    "number.rain_eff_low", "number.rain_eff_mid", "number.rain_eff_high",
  ]],
  ["deep_soak", [
    "switch.deep_soak_enabled", "number.deep_soak_target_mm", "number.deep_soak_interval_days",
    "number.deep_soak_drydown_days", "number.deep_soak_rain_threshold", "number.deep_soak_pulse_count",
    "number.deep_soak_pulse_rest_minutes", "number.deep_soak_max_runtime_minutes",
  ]],
  ["soil", ["number.soil_moisture_dry_pct", "number.soil_moisture_wet_pct", "select.soil_type"]],
  ["growth", [
    "select.growth_ramp_profile", "datetime.planting_date", "select.growth_stage_mode",
    "number.growth_stage_override_pct", "number.growth_ramp_custom_start_pct",
    "number.growth_ramp_custom_point1_day", "number.growth_ramp_custom_point1_pct",
    "number.growth_ramp_custom_point2_day", "number.growth_ramp_custom_point2_pct",
    "number.growth_ramp_custom_full_day",
  ]],
  ["deficit", ["number.deficit_water_pct", "datetime.deficit_until"]],
  ["history", ["datetime.last_routine", "datetime.last_deep_soak", "datetime.last_significant_rain"]],
  ["safety", [
    "number.max_runtime_minutes", "number.max_daily_runtime_minutes", "number.service_mode_auto_off_minutes",
    "number.pump_min_watts", "number.pump_preamble_seconds", "number.pump_postamble_seconds",
  ]],
  ["notifications", ["select.notifications", "select.weekly_summary"]],
];
const HANDLED = new Set([
  "sensor.status", "button.run_routine", "button.run_deep_soak", "button.snooze_today",
  "button.reset_lock", "switch.service_mode", "button.service_run_1_min", "button.service_run_5_min",
  "button.service_run_10_min",
]);

function t(hass, key) {
  const lang = (hass && (hass.locale?.language || hass.language)) || "en";
  const table = I18N[lang] || I18N[lang.split("-")[0]] || I18N.en;
  const lookup = (tbl) => key.split(".").reduce((node, part) => (node ? node[part] : undefined), tbl);
  return lookup(table) ?? lookup(I18N.en) ?? key;
}

const _entityCache = new WeakMap();

function zoneEntities(hass, deviceId) {
  // hass.entities is replaced (not changed) when the registry changes:
  // worked out once per registry version and zone.
  const registry = hass.entities || {};
  let perDevice = _entityCache.get(registry);
  if (!perDevice) {
    perDevice = {};
    _entityCache.set(registry, perDevice);
  }
  if (!perDevice[deviceId]) perDevice[deviceId] = _zoneEntities(hass, deviceId);
  return perDevice[deviceId];
}

function _zoneEntities(hass, deviceId) {
  const byKey = {};
  for (const entry of Object.values(hass.entities || {})) {
    if (entry.device_id !== deviceId || entry.platform !== "zoneflow" || !entry.translation_key) continue;
    const domain = entry.entity_id.split(".")[0];
    byKey[`${domain}.${entry.translation_key}`] = entry;
  }
  return byKey;
}

function firstZoneDevice(hass) {
  const entry = Object.values(hass.entities || {}).find((e) => e.platform === "zoneflow" && e.device_id);
  return entry ? entry.device_id : undefined;
}

class ZoneFlowCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("zoneflow-card-editor");
  }

  static getStubConfig(hass) {
    return { device_id: firstZoneDevice(hass) || "" };
  }

  setConfig(config) {
    if (!config) throw new Error("Pick a ZoneFlow zone (device_id).");
    this._config = { show_journal: true, show_settings: true, show_diagnostics: false, ...config };
    this._signature = undefined;
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 10;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  _render() {
    if (!this._config || !this._hass) return;
    const entities = zoneEntities(this._hass, this._config.device_id);
    const visible = Object.fromEntries(
      Object.entries(entities).filter(([key, e]) => {
        if (e.hidden) return false;
        const when = ONLY_WHEN[key];
        return !when || when(this._hass.states[e.entity_id]);
      })
    );
    const valve = this._hass.states[visible["sensor.status"]?.entity_id]?.attributes?.valve;
    const device = this._hass.devices?.[this._config.device_id];
    // What the card is built from: rebuilt only when one of these changes.
    const signature = JSON.stringify([
      Object.entries(visible)
        .map(([key, e]) => [key, e.entity_id, this._hass.states[e.entity_id]?.attributes?.friendly_name])
        .sort(),
      valve,
      !!(valve && this._hass.states[valve]),
      this._hass.locale?.language,
      device?.name_by_user || device?.name,
    ]);
    if (signature !== this._signature) {
      this._signature = signature;
      this._build(visible, valve);
    }
    this._update(visible);
  }

  async _helpers() {
    if (!this._helpersPromise) {
      this._helpersPromise = window.loadCardHelpers().catch((err) => {
        this._helpersPromise = undefined; // try again on the next build
        throw err;
      });
    }
    return this._helpersPromise;
  }

  _build(visible, valve) {
    const hass = this._hass;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const root = this.shadowRoot;
    this._buildId = (this._buildId || 0) + 1;
    this._open = this._open || {};
    root.innerHTML = "";
    const style = document.createElement("style");
    style.textContent = `
      ha-card { }
      .header { display: flex; align-items: center; gap: 12px; padding: 16px 16px 4px; }
      .header ha-icon { color: var(--state-icon-color, var(--primary-color)); }
      .title { font-size: 1.25em; font-weight: 500; line-height: 1.2; }
      .status { padding: 4px 16px 12px; font-size: 1.05em; color: var(--primary-text-color); }
      .status.warn { color: var(--warning-color, #db4437); }
      .status .code { display: block; font-size: 0.75em; color: var(--secondary-text-color); margin-top: 2px; }
      .section { padding: 0 16px 8px; }
      .section-title { font-weight: 500; color: var(--secondary-text-color); font-size: 0.85em;
        text-transform: uppercase; letter-spacing: 0.04em; margin: 12px 0 4px; }
      details { border-top: 1px solid var(--divider-color); padding: 0 16px; }
      details > summary { cursor: pointer; padding: 12px 0; font-weight: 500; list-style: none; display: flex;
        align-items: center; justify-content: space-between; }
      details > summary::-webkit-details-marker { display: none; }
      details > summary::after { content: "▸" / ""; color: var(--secondary-text-color); }
      details[open] > summary::after { content: "▾" / ""; }
      .group-title { color: var(--secondary-text-color); font-size: 0.85em; margin: 8px 0 2px; }
      .rows > * { display: block; margin: 4px 0; }
      .missing { padding: 16px; color: var(--secondary-text-color); }
    `;
    root.appendChild(style);
    const card = document.createElement("ha-card");
    root.appendChild(card);
    this._rows = [];

    if (!this._config.device_id || !Object.keys(visible).length) {
      const missing = document.createElement("div");
      missing.className = "missing";
      missing.textContent = t(hass, this._config.device_id ? "not_found" : "pick_zone");
      card.appendChild(missing);
      this._statusEl = undefined;
      return;
    }

    const device = hass.devices?.[this._config.device_id];
    const header = document.createElement("div");
    header.className = "header";
    const icon = document.createElement("ha-icon");
    icon.setAttribute("icon", this._config.icon || "mdi:sprinkler-variant");
    const title = document.createElement("div");
    title.className = "title";
    title.textContent = this._config.title || device?.name_by_user || device?.name || t(hass, "zone");
    header.append(icon, title);
    card.appendChild(header);
    this._statusEl = document.createElement("div");
    this._statusEl.className = "status";
    card.appendChild(this._statusEl);

    const used = new Set();
    const id = (key) => {
      used.add(key);
      return visible[key]?.entity_id;
    };
    const rows = (keys) => keys.map((key) => id(key)).filter(Boolean).map((entity) => ({ entity }));
    const buttons = (items) => {
      const entities = items
        .map(([key, name, icon]) => (id(key) ? { entity: visible[key].entity_id, name, icon } : null))
        .filter(Boolean);
      return entities.length ? [{ type: "buttons", entities }] : [];
    };

    // Now: the valve and what the zone is looking at.
    const now = [];
    if (valve && hass.states[valve]) now.push({ entity: valve, name: t(hass, "valve") });
    now.push(...rows(NOW));
    // Controls: run now, snooze, pause.
    const controls = [
      ...buttons([
        ["button.run_routine", t(hass, "water_now"), "mdi:watering-can"],
        ["button.run_deep_soak", t(hass, "deep_soak_now"), "mdi:waves"],
        ["button.snooze_today", t(hass, "snooze"), "mdi:sleep"],
      ]),
      ...rows(CONTROLS),
    ];
    const minutes = t(hass, "min");
    const service = [
      ...rows(["switch.service_mode"]),
      ...buttons([
        ["button.service_run_1_min", `1 ${minutes}`, "mdi:timer-outline"],
        ["button.service_run_5_min", `5 ${minutes}`, "mdi:timer-outline"],
        ["button.service_run_10_min", `10 ${minutes}`, "mdi:timer-outline"],
        ["button.reset_lock", t(hass, "reset_lock"), "mdi:lock-open-variant"],
      ]),
    ];
    const journal = rows(JOURNAL);
    const groups = SETTINGS_GROUPS.map(([name, keys]) => [name, rows(keys)]);
    for (const key of HANDLED) used.add(key);
    // Everything else, by category -- including entities added later.
    const more = [];
    const diagnostics = [];
    for (const [key, entry] of Object.entries(visible).sort((a, b) => a[0].localeCompare(b[0]))) {
      if (used.has(key)) continue;
      if (entry.entity_category === "config") more.push({ entity: entry.entity_id });
      else if (entry.entity_category === "diagnostic") diagnostics.push({ entity: entry.entity_id });
      else now.push({ entity: entry.entity_id });
    }
    groups.push(["more", more]);

    const section = (titleKey, confs) => {
      if (!confs.length) return;
      const el = document.createElement("div");
      el.className = "section";
      const heading = document.createElement("div");
      heading.className = "section-title";
      heading.textContent = t(hass, titleKey);
      const list = document.createElement("div");
      list.className = "rows";
      el.append(heading, list);
      card.appendChild(el);
      this._addRows(list, confs);
    };
    const folded = (titleKey, parts) => {
      const nonEmpty = parts.filter(([, confs]) => confs.length);
      if (!nonEmpty.length) return;
      const details = document.createElement("details");
      // Stays open (or closed) when the card rebuilds.
      details.open = !!this._open[titleKey];
      details.addEventListener("toggle", () => {
        this._open[titleKey] = details.open;
      });
      const summary = document.createElement("summary");
      summary.textContent = t(hass, titleKey);
      details.appendChild(summary);
      for (const [groupKey, confs] of nonEmpty) {
        if (groupKey) {
          const heading = document.createElement("div");
          heading.className = "group-title";
          heading.textContent = t(hass, `groups.${groupKey}`);
          details.appendChild(heading);
        }
        const list = document.createElement("div");
        list.className = "rows";
        details.appendChild(list);
        this._addRows(list, confs);
      }
      card.appendChild(details);
    };

    section("now", now);
    section("controls", controls);
    section("service", service);
    if (this._config.show_journal) folded("journal", [[null, journal]]);
    if (this._config.show_settings) folded("settings", groups);
    if (this._config.show_diagnostics) folded("diagnostics", [[null, diagnostics]]);
  }

  _shortName(conf) {
    // "Chilis Soil Moisture" -> "Soil Moisture": the card already says which zone.
    if (conf.name || !conf.entity) return conf;
    const device = this._hass.devices?.[this._config.device_id];
    const zone = device?.name_by_user || device?.name;
    const full = this._hass.states[conf.entity]?.attributes?.friendly_name;
    if (zone && full && full.startsWith(`${zone} `)) return { ...conf, name: full.slice(zone.length + 1) };
    return conf;
  }

  _addRows(list, confs) {
    const build = this._buildId;
    this._helpers().then(
      (helpers) => {
        if (build !== this._buildId) return; // rebuilt meanwhile
        for (const raw of confs) {
          const conf = this._shortName(raw);
          const add = (before) => {
            const row = helpers.createRowElement(conf);
            row.hass = this._hass;
            // A row that has to be recreated replaces just itself.
            row.addEventListener("ll-rebuild", (ev) => {
              ev.stopPropagation();
              const replacement = add(row);
              row.remove();
              this._rows = this._rows.filter((r) => r !== row);
              return replacement;
            }, { once: true });
            list.insertBefore(row, before ? before.nextSibling : null);
            this._rows.push(row);
            return row;
          };
          add(null);
        }
      },
      (err) => console.error("ZoneFlow card: Home Assistant's card helpers didn't load", err)
    );
  }

  _update(visible) {
    const hass = this._hass;
    for (const row of this._rows || []) row.hass = hass;
    if (!this._statusEl) return;
    const status = hass.states[visible["sensor.status"]?.entity_id];
    const code = status?.attributes?.code;
    this._statusEl.textContent = status ? status.state : "";
    this._statusEl.classList.toggle("warn", ["lock_held", "refused_daily_cap", "refused_runtime_cap",
      "refused_deep_soak_cap", "interrupted"].includes(code));
  }
}

class ZoneFlowCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (schema) => t(this._hass, schema.name === "device_id" ? "zone" : schema.name);
      this._form.schema = [
        { name: "device_id", required: true, selector: { device: { filter: { integration: "zoneflow" } } } },
        { name: "show_journal", selector: { boolean: {} } },
        { name: "show_settings", selector: { boolean: {} } },
        { name: "show_diagnostics", selector: { boolean: {} } },
      ];
      this._form.addEventListener("value-changed", (ev) => {
        this._config = ev.detail.value;
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: this._config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = { show_journal: true, show_settings: true, show_diagnostics: false, ...this._config };
  }
}

if (!customElements.get("zoneflow-card")) customElements.define("zoneflow-card", ZoneFlowCard);
if (!customElements.get("zoneflow-card-editor")) customElements.define("zoneflow-card-editor", ZoneFlowCardEditor);
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "zoneflow-card")) {
  window.customCards.push({
    type: "zoneflow-card",
    name: "ZoneFlow zone",
    description: "One ZoneFlow irrigation zone: status and why, controls, service runs and settings.",
    preview: true,
    documentationURL: "https://github.com/Dreamer41/ha-smart-irrigation#dashboard",
  });
}
console.info(`%c ZONEFLOW-CARD %c ${CARD_VERSION} `, "color:white;background:#2e7d32", "color:#2e7d32");
