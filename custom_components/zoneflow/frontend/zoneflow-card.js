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
 *
 * Also here: zoneflow-overview-card, every zone in one table (further down).
 */
const CARD_VERSION = "1.5.1";

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
    },
    "overview": {
      "title": "Garden",
      "zone": "Zone",
      "status": "Status",
      "next": "Next",
      "last": "Last",
      "sort": "Order",
      "sort_name": "By name",
      "sort_next": "By next watering",
      "icons": "Zone icons",
      "no_zones": "No ZoneFlow zones yet.",
      "labels": {
        "watering": "Watering now",
        "service_run": "Service run",
        "waiting_pump": "Waiting for pump",
        "locked": "Locked",
        "snoozed": "Snoozed",
        "paused": "Paused",
        "watered": "Watered today",
        "soil_wet": "Soil wet",
        "drying": "Drying out after rain",
        "rain_forecast": "Rain forecast",
        "rain_covered": "Rain covered it",
        "wet_fortnight": "Wet fortnight",
        "rain_skip": "Rain skip",
        "safety_limit": "Safety limit",
        "stopped": "Stopped",
        "scheduled": "Scheduled",
        "nothing": "Nothing scheduled",
        "frost_wait": "Frost wait",
        "frost_skip": "Frost skip",
        "deep_soak_first": "Deep soak first"
      },
      "add_zone": "Add zone",
      "show_add": "Show the Add zone button",
      "next_feed": "Next fertilizing",
      "feed_due": "Fertilize now"
    },
    "tips": {
      "crop_coefficient": "How thirsty this plant is compared with reference evapotranspiration (ET0). Higher = more water, lower = less.",
      "flow_rate_mm_per_min": "How fast your irrigation delivers water, in mm per minute. It sets how long each run lasts. Measure it with a flow meter, or a container and a stopwatch.",
      "deep_soak_target_mm": "How much water a deep soak applies, so it reaches the deeper roots.",
      "deep_soak_interval_days": "The shortest time between deep soaks. Longer means less frequent deep watering.",
      "growth_ramp_profile": "Waters young plants less and increases the amount as they grow up to full size.",
      "deficit_water_pct": "Share of the normal water to give while deficit mode is on. Lower stresses the plant more (encourages deep roots); higher keeps growth lush.",
      "mulch_status": "Mulched soil (or a full canopy or turf) loses little water to evaporation. Choose Not mulched for exposed soil, then use the adjustment next to it.",
      "mulch_et_adjustment_pct": "Fine-tunes the routine watering amount for your soil cover, -50% to +70%. Positive for exposed soil that dries fast, negative for water-holding soil such as heavy clay or shade. Large negative values cut watering a lot: use them only if your soil stays wet, and watch it for a week or two.",
      "rain_eff_low": "Share of light rain that actually reaches the roots. The rest runs off or evaporates.",
      "rain_eff_mid": "Share of moderate rain that actually reaches the roots. The rest runs off or evaporates.",
      "rain_eff_high": "Share of heavy rain that actually reaches the roots. The rest runs off or evaporates."
    },
    "close": "Close",
    "device_page": "Open the device page",
    "fertilized": "Fertilized",
    "mark_watered": "Mark watered"
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
    "deep_soak_now": "Jetzt Tiefenbewässerung",
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
    },
    "overview": {
      "title": "Garten",
      "zone": "Zone",
      "status": "Status",
      "next": "Nächste",
      "last": "Zuletzt",
      "sort": "Reihenfolge",
      "sort_name": "Nach Name",
      "sort_next": "Nach nächster Bewässerung",
      "icons": "Zonen-Symbole",
      "no_zones": "Noch keine ZoneFlow-Zonen.",
      "labels": {
        "watering": "Bewässert gerade",
        "service_run": "Wartungslauf",
        "waiting_pump": "Wartet auf Pumpe",
        "locked": "Gesperrt",
        "snoozed": "Heute ausgesetzt",
        "paused": "Pausiert",
        "watered": "Heute bewässert",
        "soil_wet": "Boden nass",
        "drying": "Abtrocknen nach Regen",
        "rain_forecast": "Regen vorhergesagt",
        "rain_covered": "Regen hat gereicht",
        "wet_fortnight": "Zwei nasse Wochen",
        "rain_skip": "Regen: übersprungen",
        "safety_limit": "Sicherheitslimit",
        "stopped": "Abgebrochen",
        "scheduled": "Geplant",
        "nothing": "Nichts geplant",
        "frost_wait": "Wartet: Frost",
        "frost_skip": "Frost: übersprungen",
        "deep_soak_first": "Erst Tiefenbewässerung"
      },
      "add_zone": "Zone hinzufügen",
      "show_add": "Schaltfläche „Zone hinzufügen“ anzeigen",
      "next_feed": "Nächste Düngung",
      "feed_due": "Jetzt düngen"
    },
    "close": "Schließen",
    "device_page": "Geräteseite öffnen",
    "fertilized": "Gedüngt",
    "mark_watered": "Als bewässert markieren",
    "tips": {
      "crop_coefficient": "Gibt den Wasserbedarf der Pflanze im Vergleich zur Referenz-Evapotranspiration (ET0) an. Höhere Werte bedeuten mehr Wasser, niedrigere weniger.",
      "flow_rate_mm_per_min": "Gibt an, wie viel Wasser das Bewässerungssystem pro Minute abgibt (in mm/min). Dieser Wert bestimmt die Laufzeit pro Durchgang. Messung per Durchflussmesser oder Behälter und Stoppuhr.",
      "deep_soak_target_mm": "Wassermenge für eine Tiefenbewässerung, damit das Wasser auch tiefere Wurzelzonen erreicht.",
      "deep_soak_interval_days": "Mindestabstand zwischen zwei Tiefenbewässerungen. Ein höherer Wert führt zu seltenerer Tiefenbewässerung.",
      "growth_ramp_profile": "Bewässert Jungpflanzen sparsamer und steigert die Wassermenge schrittweise mit zunehmender Wuchsgröße.",
      "deficit_water_pct": "Prozentualer Anteil der normalen Wassermenge im Defizitmodus. Niedrigere Werte belasten die Pflanze stärker (fördert tiefes Wurzelwachstum), höhere Werte erhalten ein üppiges Wachstum.",
      "mulch_status": "Mulchschichten, dichtes Blätterdach oder Rasen reduzieren die Verdunstung. Wählen Sie „Nicht gemulcht“ bei offenem Boden und passen Sie den Korrekturwert daneben an.",
      "mulch_et_adjustment_pct": "Feinanpassung der täglichen Bewässerungsmenge je nach Bodenbedeckung (-50 % bis +70 %). Positive Werte für schnell trocknende Böden, negative Werte für wasserspeichernde Böden (z. B. lehmig oder schattig). Starke negative Anpassungen reduzieren die Wassermenge erheblich – bitte beobachten Sie die Pflanzen in den ersten zwei Wochen gut.",
      "rain_eff_low": "Anteil leichten Regens, der die Wurzeln erreicht. Der Rest verdunstet oder fließt oberflächlich ab.",
      "rain_eff_mid": "Anteil mäßigen Regens, der die Wurzeln erreicht. Der Rest verdunstet oder fließt oberflächlich ab.",
      "rain_eff_high": "Anteil starken Regens, der die Wurzeln erreicht. Der Rest verdunstet oder fließt oberflächlich ab."
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
    },
    "overview": {
      "title": "Jardín",
      "zone": "Zona",
      "status": "Estado",
      "next": "Próximo",
      "last": "Último",
      "sort": "Orden",
      "sort_name": "Por nombre",
      "sort_next": "Por próximo riego",
      "icons": "Iconos de zonas",
      "no_zones": "Todavía no hay zonas de ZoneFlow.",
      "labels": {
        "watering": "Regando ahora",
        "service_run": "Mantenimiento",
        "waiting_pump": "Esperando la bomba",
        "locked": "Bloqueada",
        "snoozed": "Omitido hoy",
        "paused": "En pausa",
        "watered": "Regada hoy",
        "soil_wet": "Suelo húmedo",
        "drying": "Secándose tras la lluvia",
        "rain_forecast": "Lluvia prevista",
        "rain_covered": "La lluvia bastó",
        "wet_fortnight": "Quincena húmeda",
        "rain_skip": "Omitido por lluvia",
        "safety_limit": "Límite de seguridad",
        "stopped": "Detenido",
        "scheduled": "Programado",
        "nothing": "Nada programado",
        "frost_wait": "En espera por helada",
        "frost_skip": "Omitido por helada",
        "deep_soak_first": "Primero riego profundo"
      },
      "add_zone": "Añadir zona",
      "show_add": "Mostrar el botón Añadir zona",
      "next_feed": "Próximo abonado",
      "feed_due": "Abonar ya"
    },
    "close": "Cerrar",
    "device_page": "Abrir la página del dispositivo",
    "fertilized": "Abonado",
    "mark_watered": "Marcar como regado",
    "tips": {
      "crop_coefficient": "Indica las necesidades de agua de la planta en comparación con la evapotranspiración de referencia (ET0). Un valor más alto requiere más agua; uno más bajo, menos.",
      "flow_rate_mm_per_min": "Caudal que aporta el sistema de riego en mm por minuto. Determina la duración de cada sesión. Puede medirlo con un caudalímetro o usando un recipiente y un cronómetro.",
      "deep_soak_target_mm": "Cantidad de agua aplicada en un riego profundo para garantizar que llegue a las raíces más profundas.",
      "deep_soak_interval_days": "Tiempo mínimo entre riegos profundos. Un intervalo mayor reduce la frecuencia de los riegos profundos.",
      "growth_ramp_profile": "Riega menos las plantas jóvenes e incrementa el aporte de agua gradualmente a medida que crecen.",
      "deficit_water_pct": "Porcentaje de agua respecto al riego normal mientras el modo de déficit está activo. Un valor menor estresa más a la planta (estimula raíces profundas); un valor mayor mantiene un crecimiento frondoso.",
      "mulch_status": "El suelo acolchado (cubierto de mantillo, vegetación tupida o césped) pierde muy poca agua por evaporación. Seleccione 'Sin acolchado' si el suelo está expuesto y ajuste el porcentaje contiguo.",
      "mulch_et_adjustment_pct": "Ajuste fino del riego habitual según la cobertura del suelo (-50% a +70%). Los valores positivos son para suelos expuestos que se secan rápido; los negativos, para suelos que retienen humedad (arcillosos o en sombra). Ajustes negativos altos reducen bastante el riego: úselos solo si el suelo permanece húmedo y observe la evolución durante un par de semanas.",
      "rain_eff_low": "Proporción de lluvia débil que llega realmente a las raíces. El resto se evapora o se pierde por escorrentía.",
      "rain_eff_mid": "Proporción de lluvia moderada que llega realmente a las raíces. El resto se evapora o se pierde por escorrentía.",
      "rain_eff_high": "Proporción de lluvia intensa que llega realmente a las raíces. El resto se evapora o se pierde por escorrentía."
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
    "snooze": "Ei kastelua tänään",
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
    },
    "overview": {
      "title": "Puutarha",
      "zone": "Vyöhyke",
      "status": "Tila",
      "next": "Seuraava",
      "last": "Viimeksi",
      "sort": "Järjestys",
      "sort_name": "Nimen mukaan",
      "sort_next": "Seuraavan kastelun mukaan",
      "icons": "Vyöhykkeiden kuvakkeet",
      "no_zones": "Ei vielä ZoneFlow-vyöhykkeitä.",
      "labels": {
        "watering": "Kastelee nyt",
        "service_run": "Huoltoajo",
        "waiting_pump": "Odottaa pumppua",
        "locked": "Lukittu",
        "snoozed": "Ohitettu tänään",
        "paused": "Tauolla",
        "watered": "Kasteltu tänään",
        "soil_wet": "Maa märkä",
        "drying": "Kuivuu sateen jälkeen",
        "rain_forecast": "Sadetta ennustettu",
        "rain_covered": "Sade riitti",
        "wet_fortnight": "Kaksi sateista viikkoa",
        "rain_skip": "Ohitettu: sade",
        "safety_limit": "Turvaraja",
        "stopped": "Keskeytetty",
        "scheduled": "Ajastettu",
        "nothing": "Ei ajastettu",
        "frost_wait": "Odottaa: halla",
        "frost_skip": "Halla: ohitettu",
        "deep_soak_first": "Ensin syväkastelu"
      },
      "add_zone": "Lisää vyöhyke",
      "show_add": "Näytä Lisää vyöhyke -painike",
      "next_feed": "Seuraava lannoitus",
      "feed_due": "Lannoita nyt"
    },
    "close": "Sulje",
    "device_page": "Avaa laitesivu",
    "fertilized": "Lannoita",
    "mark_watered": "Merkitse kastelluksi",
    "tips": {
      "crop_coefficient": "Kasvin vedenkulutus verrattuna vertailuevapotranspiraatioon (ET0). Suurempi arvo tarkoittaa suurempaa veden tarvetta, pienempi vähempää.",
      "flow_rate_mm_per_min": "Sadetuksen tai kastelun määrä millimetreinä minuutissa. Määrittää kastelukerran keston. Voit mitata arvon virtausmittarilla tai astialla ja sekuntikellolla.",
      "deep_soak_target_mm": "Syväkastelun vesimäärä millimetreinä, jotta kosteus saavuttaa syvemmät juuret.",
      "deep_soak_interval_days": "Syväkastelujen välinen vähimmäisaika vuorokausina. Suurempi arvo harventaa syväkastelukertoja.",
      "growth_ramp_profile": "Kastelee nuoria kasveja vähemmän ja lisää vesimäärää asteittain kasvin varttuessa täyteen kokoonsa.",
      "deficit_water_pct": "Kastelumäärän osuus normaalista, kun vajaakastelu on käytössä. Pienempi arvo aiheuttaa kasville enemmän kuivuusstressiä (edistää syvää juurtumista); suurempi arvo ylläpitää rehevää kasvua.",
      "mulch_status": "Kate, tiheä lehvästö tai nurmikko vähentää veden haihtumista maaperästä. Valitse 'Ei katetta', jos maaperä on paljas, ja säädä vieressä olevaa korjausprosenttia.",
      "mulch_et_adjustment_pct": "Säätää rutiinikastelun määrää maaperän katteen mukaan (-50 % – +70 %). Positiivinen arvo sopii nopeasti kuivuvalle paljaalle maalle, negatiivinen arvo vettä pidättävälle maalle (kuten savimaalle tai varjoisalle paikalle). Suuret negatiiviset arvot leikkaavat kastelua huomattavasti: käytä niitä vain, jos maa pysyy märkänä, ja seuraa tilannetta viikko tai kaksi.",
      "rain_eff_low": "Kevyen sateen osuus, joka todellisuudessa saavuttaa juuret. Loput haihtuu tai valuu pois.",
      "rain_eff_mid": "Kohtalaisen sateen osuus, joka todellisuudessa saavuttaa juuret. Loput haihtuu tai valuu pois.",
      "rain_eff_high": "Runsaan sateen osuus, joka todellisuudessa saavuttaa juuret. Loput haihtuu tai valuu pois."
    }
  },
  "fr": {
    "now": "Maintenant",
    "controls": "Contrôles",
    "service": "Maintenance et contrôles (non comptés comme arrosage)",
    "journal": "Carnet de culture",
    "settings": "Paramètres",
    "diagnostics": "Diagnostic",
    "valve": "Vanne",
    "water_now": "Arroser maintenant",
    "deep_soak_now": "Lancer l'arrosage profond",
    "snooze": "Sauter aujourd'hui",
    "reset_lock": "Réinitialiser le verrou",
    "min": "min",
    "pick_zone": "Choisissez une zone ZoneFlow pour cette carte.",
    "not_found": "Zone ZoneFlow introuvable (supprimée ou pas encore chargée).",
    "zone": "Zone",
    "show_journal": "Afficher le carnet de culture",
    "show_settings": "Afficher les paramètres",
    "show_diagnostics": "Afficher le diagnostic",
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
    },
    "overview": {
      "title": "Jardin",
      "zone": "Zone",
      "status": "État",
      "next": "Prochain",
      "last": "Dernier",
      "sort": "Ordre",
      "sort_name": "Par nom",
      "sort_next": "Par prochain arrosage",
      "icons": "Icônes des zones",
      "no_zones": "Aucune zone ZoneFlow pour l'instant.",
      "labels": {
        "watering": "Arrosage en cours",
        "service_run": "Test de maintenance",
        "waiting_pump": "En attente de la pompe",
        "locked": "Verrouillée",
        "snoozed": "Sautée aujourd'hui",
        "paused": "En pause",
        "watered": "Arrosée aujourd'hui",
        "soil_wet": "Sol humide",
        "drying": "Ressuyage après pluie",
        "rain_forecast": "Pluie prévue",
        "rain_covered": "La pluie a suffi",
        "wet_fortnight": "Quinzaine humide",
        "rain_skip": "Sauté (pluie)",
        "safety_limit": "Limite de sécurité",
        "stopped": "Arrêté",
        "scheduled": "Programmé",
        "nothing": "Rien de prévu",
        "frost_wait": "En attente (gel)",
        "frost_skip": "Sauté (gel)",
        "deep_soak_first": "Arrosage profond d'abord"
      },
      "add_zone": "Ajouter une zone",
      "show_add": "Afficher le bouton Ajouter une zone",
      "next_feed": "Prochain apport d'engrais",
      "feed_due": "Engrais à apporter"
    },
    "close": "Fermer",
    "device_page": "Ouvrir la page de l'appareil",
    "fertilized": "Engrais apporté",
    "mark_watered": "Marquer comme arrosé",
    "tips": {
      "crop_coefficient": "Besoins en eau de la plante par rapport à l'évapotranspiration de référence (ET0). Une valeur plus élevée augmente l'arrosage, une valeur plus basse le réduit.",
      "flow_rate_mm_per_min": "Pluviométrie du système d'arrosage en mm par minute. Détermine la durée de chaque cycle. À mesurer avec un débitmètre ou un récipient et un chronomètre.",
      "deep_soak_target_mm": "Quantité d'eau appliquée lors d'un arrosage en profondeur pour atteindre les racines profondes.",
      "deep_soak_interval_days": "Intervalle minimal en jours entre deux arrosages en profondeur. Une valeur plus élevée espace ces arrosages.",
      "growth_ramp_profile": "Arrose moins les jeunes plants et augmente progressivement le volume d'eau jusqu'à maturité.",
      "deficit_water_pct": "Pourcentage de l'apport d'eau normal en mode déficit. Une valeur faible stresse davantage la plante (incite l'enracinement profond) ; une valeur plus élevée maintient un feuillage dense.",
      "mulch_status": "Un sol paillé (ou un feuillage dense / de la pelouse) limite fortement l'évaporation. Choisissez « Non paillé » pour un sol nu, puis ajustez le pourcentage associé.",
      "mulch_et_adjustment_pct": "Ajustement précis de l'arrosage quotidien selon la couverture du sol (de -50% à +70%). Valeurs positives pour les sols nus séchant vite, négatives pour les sols retenant l'eau (argileux ou à l'ombre). Des valeurs fortement négatives réduisent nettement l'arrosage : à n'utiliser que si le sol reste très humide, en observant le résultat sur une à deux semaines.",
      "rain_eff_low": "Proportion de pluie faible atteignant réellement les racines. Le reste s'évapore ou ruisselle.",
      "rain_eff_mid": "Proportion de pluie modérée atteignant réellement les racines. Le reste s'évapore ou ruisselle.",
      "rain_eff_high": "Proportion de pluie forte atteignant réellement les racines. Le reste s'évapore ou ruisselle."
    }
  },
  "it": {
    "now": "Adesso",
    "controls": "Controlli",
    "service": "Manutenzione e verifiche (non conta come irrigazione)",
    "journal": "Diario delle piante",
    "settings": "Impostazioni",
    "diagnostics": "Diagnostica",
    "valve": "Valvola",
    "water_now": "Irriga ora",
    "deep_soak_now": "Avvia irrigazione profonda",
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
    },
    "overview": {
      "title": "Giardino",
      "zone": "Zona",
      "status": "Stato",
      "next": "Prossima",
      "last": "Ultima",
      "sort": "Ordine",
      "sort_name": "Per nome",
      "sort_next": "Per prossima irrigazione",
      "icons": "Icone delle zone",
      "no_zones": "Ancora nessuna zona ZoneFlow.",
      "labels": {
        "watering": "Irrigazione in corso",
        "service_run": "Manutenzione",
        "waiting_pump": "In attesa della pompa",
        "locked": "Bloccata",
        "snoozed": "Saltata oggi",
        "paused": "In pausa",
        "watered": "Irrigata oggi",
        "soil_wet": "Terreno bagnato",
        "drying": "Asciugatura dopo pioggia",
        "rain_forecast": "Pioggia prevista",
        "rain_covered": "È bastata la pioggia",
        "wet_fortnight": "Due settimane piovose",
        "rain_skip": "Saltata per pioggia",
        "safety_limit": "Limite di sicurezza",
        "stopped": "Interrotta",
        "scheduled": "Programmata",
        "nothing": "Niente in programma",
        "frost_wait": "In attesa (gelo)",
        "frost_skip": "Saltata per gelo",
        "deep_soak_first": "Prima l'irrigazione profonda"
      },
      "add_zone": "Aggiungi zona",
      "show_add": "Mostra il pulsante Aggiungi zona",
      "next_feed": "Prossima concimazione",
      "feed_due": "Concima ora"
    },
    "close": "Chiudi",
    "device_page": "Apri la pagina del dispositivo",
    "fertilized": "Concimato",
    "mark_watered": "Segna come annaffiato",
    "tips": {
      "crop_coefficient": "Fabbisogno idrico della pianta rispetto all'evapotraspirazione di riferimento (ET0). Valori più alti indicano maggiore fabbisogno d'acqua, valori più bassi minore.",
      "flow_rate_mm_per_min": "Tasso di erogazione dell'impianto di irrigazione espresso in mm al minuto. Determina la durata di ciascuna sessione. Può essere misurato con un flussometro oppure con un contenitore e un cronometro.",
      "deep_soak_target_mm": "Quantità d'acqua erogata per un'irrigazione profonda, in modo da raggiungere le radici più profonde.",
      "deep_soak_interval_days": "Intervallo minimo espresso in giorni tra due irrigazioni profonde. Valori più alti diradano la frequenza.",
      "growth_ramp_profile": "Irriga meno le piante giovani e aumenta gradualmente la quantità d'acqua man mano che crescono fino a raggiungere la maturità.",
      "deficit_water_pct": "Percentuale rispetto al normale apporto idrico applicata durante la modalità deficit. Valori più bassi stimolano lo stress idrico (favoriscono radici profonde); valori più alti mantengono una crescita rigogliosa.",
      "mulch_status": "Il terreno pacciamato (o con fitta copertura vegetale / prato) riduce notevolmente l'evaporazione. Selezionare 'Non pacciamato' in caso di terreno esposto e impostare la correzione percentuale affianco.",
      "mulch_et_adjustment_pct": "Regolazione fine dell'irrigazione quotidiana in base alla copertura del suolo (-50% a +70%). Valori positivi per terreni esposti ad asciugatura rapida; valori negativi per terreni a forte ritenzione idrica (come argilla o zone d'ombra). Valori fortemente negativi riducono parecchio l'irrigazione: utilizzare solo se il terreno rimane molto umido e monitorare per una o due settimane.",
      "rain_eff_low": "Quota di pioggia debole che raggiunge effettivamente le radici. La parte restante evapora o scivola via per ruscellamento.",
      "rain_eff_mid": "Quota di pioggia moderata che raggiunge effettivamente le radici. La parte restante evapora o scivola via per ruscellamento.",
      "rain_eff_high": "Quota di pioggia intensa che raggiunge effettivamente le radici. La parte restante evapora o scivola via per ruscellamento."
    }
  },
  "nl": {
    "now": "Nu",
    "controls": "Bediening",
    "service": "Onderhoud en controles (telt niet als watergift)",
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
      "rain": "Regen, verwachting en vorst",
      "deep_soak": "Diepe watergift",
      "soil": "Bodem",
      "growth": "Groei",
      "deficit": "Spaarmodus",
      "history": "Geschiedenis",
      "safety": "Veiligheidslimieten en pomp",
      "notifications": "Meldingen",
      "more": "Meer"
    },
    "overview": {
      "title": "Tuin",
      "zone": "Zone",
      "status": "Status",
      "next": "Volgende",
      "last": "Laatste",
      "sort": "Volgorde",
      "sort_name": "Op naam",
      "sort_next": "Op volgende watergift",
      "icons": "Zonepictogrammen",
      "no_zones": "Nog geen ZoneFlow-zones.",
      "labels": {
        "watering": "Geeft nu water",
        "service_run": "Proefdraaien",
        "waiting_pump": "Wacht op pomp",
        "locked": "Vergrendeld",
        "snoozed": "Vandaag overgeslagen",
        "paused": "Gepauzeerd",
        "watered": "Vandaag water gehad",
        "soil_wet": "Bodem nat",
        "drying": "Opdrogen na regen",
        "rain_forecast": "Regen verwacht",
        "rain_covered": "Regen was genoeg",
        "wet_fortnight": "Twee natte weken",
        "rain_skip": "Overgeslagen: regen",
        "safety_limit": "Veiligheidslimiet",
        "stopped": "Gestopt",
        "scheduled": "Gepland",
        "nothing": "Niets gepland",
        "frost_wait": "Wacht: vorst",
        "frost_skip": "Vorst: overgeslagen",
        "deep_soak_first": "Eerst diepe watergift"
      },
      "add_zone": "Zone toevoegen",
      "show_add": "Knop Zone toevoegen tonen",
      "next_feed": "Volgende bemesting",
      "feed_due": "Nu bemesten"
    },
    "close": "Sluiten",
    "device_page": "Apparaatpagina openen",
    "fertilized": "Bemest",
    "mark_watered": "Markeer als bewaterd",
    "tips": {
      "crop_coefficient": "Bepaalt de waterbehoefte van het gewas ten opzichte van de referentie-evapotranspiratie (ET0). Hoger = meer water, lager = minder water.",
      "flow_rate_mm_per_min": "De neerslagsnelheid van je irrigatiesysteem in mm per minuut. Dit bepaalt de duur van elke sproeibeurt. Te meten met een stroommeter of met een opvangbakje en een stopwatch.",
      "deep_soak_target_mm": "Hoeveelheid water die bij een diepe bewatering wordt toegediend om de diepere wortels te bereiken.",
      "deep_soak_interval_days": "Minimale periode tussen twee diepe bewateringsbeurten. Een hogere waarde betekent minder frequente diepe bewatering.",
      "growth_ramp_profile": "Geeft jonge planten minder water en verhoogt de hoeveelheid geleidelijk naarmate ze uitgroeien tot volwaardige planten.",
      "deficit_water_pct": "Percentage van de normale hoeveelheid water dat wordt gegeven als de deficit-modus actief is. Een lagere waarde geeft meer stress (stimuleert diepe wortelgroei); een hogere waarde behoudt een volle, weelderige groei.",
      "mulch_status": "Gemulchte grond (of een dicht bladerdek of gazon) verliest weinig vocht door verdamping. Kies 'Niet gemulcht' bij onbedekte grond en stel de aanpassing ernaast in.",
      "mulch_et_adjustment_pct": "Fijnafstemming van de dagelijkse bewatering op basis van de bodembedekking (-50% tot +70%). Positief voor onbedekte grond die snel uitdroogt, negatief voor watervasthoudende grond (zoals zware klei of schaduwrijke zones). Grote negatieve waarden verminderen de bewatering sterk: gebruik dit alleen als de grond erg nat blijft en houd het een à twee weken in de gaten.",
      "rain_eff_low": "Het deel van lichte regen dat daadwerkelijk de wortels bereikt. De rest verdampt of stroomt weg.",
      "rain_eff_mid": "Het deel van matige regen dat daadwerkelijk de wortels bereikt. De rest verdampt of stroomt weg.",
      "rain_eff_high": "Het deel van zware regen dat daadwerkelijk de wortels bereikt. De rest verdampt of stroomt weg."
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
    },
    "overview": {
      "title": "Ogród",
      "zone": "Strefa",
      "status": "Stan",
      "next": "Następne",
      "last": "Ostatnio",
      "sort": "Kolejność",
      "sort_name": "Według nazwy",
      "sort_next": "Według następnego podlewania",
      "icons": "Ikony stref",
      "no_zones": "Brak jeszcze stref ZoneFlow.",
      "labels": {
        "watering": "Podlewa teraz",
        "service_run": "Uruchomienie serwisowe",
        "waiting_pump": "Czeka na pompę",
        "locked": "Zablokowana",
        "snoozed": "Pominięte dziś",
        "paused": "Wstrzymana",
        "watered": "Podlana dziś",
        "soil_wet": "Mokra gleba",
        "drying": "Przesychanie po deszczu",
        "rain_forecast": "Prognozowany deszcz",
        "rain_covered": "Deszcz wystarczył",
        "wet_fortnight": "Mokre dwa tygodnie",
        "rain_skip": "Pominięte: deszcz",
        "safety_limit": "Limit bezpieczeństwa",
        "stopped": "Przerwane",
        "scheduled": "Zaplanowane",
        "nothing": "Nic nie zaplanowano",
        "frost_wait": "Czeka: przymrozek",
        "frost_skip": "Przymrozek: pominięte",
        "deep_soak_first": "Najpierw głębokie podlewanie"
      },
      "add_zone": "Dodaj strefę",
      "show_add": "Pokaż przycisk Dodaj strefę",
      "next_feed": "Następne nawożenie",
      "feed_due": "Nawieź teraz"
    },
    "close": "Zamknij",
    "device_page": "Otwórz stronę urządzenia",
    "fertilized": "Nawożono",
    "mark_watered": "Oznacz jako podlane",
    "tips": {
      "crop_coefficient": "Określa zapotrzebowanie rośliny na wodę w stosunku do ewapotranspiracji wskaźnikowej (ET0). Wyższa wartość = więcej wody, niższa = mniej.",
      "flow_rate_mm_per_min": "Wydajność systemu nawadniania wyrażona w mm na minutę. Wyznacza czas trwania pojedynczego cyklu. Można ją zmierzyć przepływomierzem lub pojemnikiem i stoperem.",
      "deep_soak_target_mm": "Ilość wody dostarczana podczas głębokiego podlewania, dostosowana do zasięgu głębszych korzeni.",
      "deep_soak_interval_days": "Minimalny odstęp w dniach między kolejnymi cyklami głębokiego podlewania. Wyższa wartość oznacza rzadsze nawadnianie głębokie.",
      "growth_ramp_profile": "Podaje mniej wody młodym roślinom i stopniowo zwiększa dawkę w miarę ich wzrostu do dojrzałości.",
      "deficit_water_pct": "Procentowa część standardowej dawki wody podawana w trybie deficytowym. Niższa wartość zwiększa stres wodny (stymuluje głębszy rozwój korzeni); wyższa utrzymuje bujny wzrost.",
      "mulch_status": "Gleba pokryta ściółką (lub gęstą koroną roślin czy trawnikiem) traci niewiele wody przez parowanie. Wybierz 'Bez ściółki' dla odkrytej gleby i dostosuj współczynnik obok.",
      "mulch_et_adjustment_pct": "Precyzyjna korekta dawki nawadniania w zależności od przykrycia gleby (od -50% do +70%). Wartości dodatnie stosuj dla odsłoniętej, szybko schnącej gleby; ujemne dla gleb zatrzymujących wilgoć (np. gliniastych lub zacienionych). Znaczne wartości ujemne mocno ograniczają podlewanie – stosuj je tylko, gdy gleba długo pozostaje wilgotna i obserwuj rośliny przez 1-2 tygodnie.",
      "rain_eff_low": "Część opadów lekkiego deszczu, która rzeczywiście dociera do strefy korzeniowej. Reszta paruje lub spływa.",
      "rain_eff_mid": "Część opadów umiarkowanego deszczu, która rzeczywiście dociera do strefy korzeniowej. Reszta paruje lub spływa.",
      "rain_eff_high": "Część opadów ulewnego deszczu, która rzeczywiście dociera do strefy korzeniowej. Reszta paruje lub spływa."
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
    },
    "overview": {
      "title": "Jardim",
      "zone": "Zona",
      "status": "Estado",
      "next": "Próxima",
      "last": "Última",
      "sort": "Ordem",
      "sort_name": "Por nome",
      "sort_next": "Pela próxima rega",
      "icons": "Ícones das zonas",
      "no_zones": "Ainda não há zonas ZoneFlow.",
      "labels": {
        "watering": "A regar agora",
        "service_run": "Ciclo de manutenção",
        "waiting_pump": "À espera da bomba",
        "locked": "Bloqueada",
        "snoozed": "Não regar hoje",
        "paused": "Em pausa",
        "watered": "Regada hoje",
        "soil_wet": "Solo molhado",
        "drying": "A secar após chuva",
        "rain_forecast": "Chuva prevista",
        "rain_covered": "A chuva bastou",
        "wet_fortnight": "Quinzena húmida",
        "rain_skip": "Dispensada: chuva",
        "safety_limit": "Limite de segurança",
        "stopped": "Interrompida",
        "scheduled": "Agendada",
        "nothing": "Nada agendado",
        "frost_wait": "Espera: geada",
        "frost_skip": "Geada: dispensada",
        "deep_soak_first": "Primeiro a rega profunda"
      },
      "add_zone": "Adicionar zona",
      "show_add": "Mostrar o botão Adicionar zona",
      "next_feed": "Próxima adubação",
      "feed_due": "Adubar agora"
    },
    "close": "Fechar",
    "device_page": "Abrir a página do dispositivo",
    "fertilized": "Adubado",
    "mark_watered": "Marcar como regado",
    "tips": {
      "crop_coefficient": "Indica a necessidade de água da planta em comparação com a evapotranspiração de referência (ET0). Valores mais altos significam mais água; valores mais baixos, menos.",
      "flow_rate_mm_per_min": "Taxa de precipitação da rega em mm por minuto. Define a duração de cada ciclo. Pode medir com um caudalímetro ou com um recipiente e um cronómetro.",
      "deep_soak_target_mm": "Quantidade de água aplicada numa rega profunda para alcançar as raízes mais profundas.",
      "deep_soak_interval_days": "Intervalo mínimo em dias entre regas profundas. Valores maiores tornam as regas profundas menos frequentes.",
      "growth_ramp_profile": "Aplica menos água a plantas jovens e aumenta gradualmente a quantidade à medida que crescem até ao tamanho adulto.",
      "deficit_water_pct": "Percentagem da quantidade normal de água a aplicar com o modo de défice ativo. Valores mais baixos causam mais stress à planta (estimulando raízes profundas); valores mais altos mantêm um crescimento exuberante.",
      "mulch_status": "Solo com cobertura (ou copa densa / relvado) perde pouca água por evaporação. Escolha 'Sem cobertura' para solo exposto e ajuste a percentagem ao lado.",
      "mulch_et_adjustment_pct": "Ajuste fino da rega diária com base na cobertura do solo (-50% a +70%). Valores positivos destinam-se a solos expostos que secam rápido; valores negativos para solos que retêm humidade (como argilosos ou à sombra). Ajustes negativos elevados reduzem bastante a rega: utilize-os apenas se o solo se mantiver húmido e monitorize durante uma ou duas semanas.",
      "rain_eff_low": "Percentagem de chuva fraca que chega efetivamente às raízes. O restante evapora ou escorre.",
      "rain_eff_mid": "Percentagem de chuva moderada que chega efetivamente às raízes. O restante evapora ou escorre.",
      "rain_eff_high": "Percentagem de chuva forte que chega efetivamente às raízes. O restante evapora ou escorre."
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
    },
    "overview": {
      "title": "Trädgård",
      "zone": "Zon",
      "status": "Status",
      "next": "Nästa",
      "last": "Senast",
      "sort": "Ordning",
      "sort_name": "Efter namn",
      "sort_next": "Efter nästa vattning",
      "icons": "Zonikoner",
      "no_zones": "Inga ZoneFlow-zoner ännu.",
      "labels": {
        "watering": "Vattnar nu",
        "service_run": "Servicekörning",
        "waiting_pump": "Väntar på pumpen",
        "locked": "Låst",
        "snoozed": "Överhoppad idag",
        "paused": "Pausad",
        "watered": "Vattnad idag",
        "soil_wet": "Jorden blöt",
        "drying": "Torkar upp efter regn",
        "rain_forecast": "Regn väntas",
        "rain_covered": "Regnet räckte",
        "wet_fortnight": "Två blöta veckor",
        "rain_skip": "Överhoppad: regn",
        "safety_limit": "Säkerhetsgräns",
        "stopped": "Stoppad",
        "scheduled": "Schemalagd",
        "nothing": "Inget schemalagt",
        "frost_wait": "Väntar: frost",
        "frost_skip": "Frost: överhoppad",
        "deep_soak_first": "Djupvattning först"
      },
      "add_zone": "Lägg till zon",
      "show_add": "Visa knappen Lägg till zon",
      "next_feed": "Nästa gödsling",
      "feed_due": "Gödsla nu"
    },
    "close": "Stäng",
    "device_page": "Öppna enhetssidan",
    "fertilized": "Gödslat",
    "mark_watered": "Markera som vattnad",
    "tips": {
      "crop_coefficient": "Växtens vattenbehov i jämförelse med referensevapotranspiration (ET0). Högre värde innebär mer vatten, lägre värde mindre.",
      "flow_rate_mm_per_min": "Bevattningssystemets flöde i mm per minut. Detta bestämmer bevattningstiden för varje pass. Mät med flödesmätare eller behållare och tidtagarur.",
      "deep_soak_target_mm": "Vattenmängd vid en djupvattning för att nå ner till de djupare rötterna.",
      "deep_soak_interval_days": "Minsta antal dagar mellan djupvattningar. Ett högre värde ger glesare djupvattningar.",
      "growth_ramp_profile": "Vattnar unga plantor mindre och ökar vattenmängden efter hand som de växer till full storlek.",
      "deficit_water_pct": "Andel av normal vattenmängd som ges när sparläget är aktivt. Lägre värde stressar växten mer (stimulerar djupa rötter); högre värde bibehåller en tät och frodig tillväxt.",
      "mulch_status": "Täckt jord (med täckmaterial, tätt bladverk eller gräsmatta) förlorar lite vatten genom avdunstning. Välj 'Ej marktäckt' för bar jord och justera procentsatsen bredvid.",
      "mulch_et_adjustment_pct": "Finjustering av den dagliga bevattningen baserat på marktäckning (-50 % till +70 %). Positiva värden för bar jord som torkar snabbt, negativa för vattenhållande jord (t.ex. styv lera eller skuggiga lägen). Stora negativa värden minskar bevattningen avsevärt: använd dem endast om jorden förblir fuktig och följ upp under en till två veckor.",
      "rain_eff_low": "Andel av lätt regn som faktiskt når rötterna. Resten dunstar eller rinner av.",
      "rain_eff_mid": "Andel av måttligt regn som faktiskt når rötterna. Resten dunstar eller rinner av.",
      "rain_eff_high": "Andel av kraftigt regn som faktiskt når rötterna. Resten dunstar eller rinner av."
    }
  },
  "cs": {
    "now": "Teď",
    "controls": "Ovládání",
    "service": "Servis a kontroly (nepočítá se jako zálivka)",
    "journal": "Deník rostliny",
    "settings": "Nastavení",
    "diagnostics": "Diagnostika",
    "valve": "Ventil",
    "water_now": "Zalít teď",
    "deep_soak_now": "Hloubková zálivka teď",
    "snooze": "Dnes vynechat",
    "reset_lock": "Resetovat zámek",
    "min": "min",
    "pick_zone": "Vyberte pro tuto kartu zónu ZoneFlow.",
    "not_found": "Tato zóna ZoneFlow nebyla nalezena (odebrána, nebo ještě nenačtena).",
    "zone": "Zóna",
    "show_journal": "Zobrazit deník rostliny",
    "show_settings": "Zobrazit nastavení",
    "show_diagnostics": "Zobrazit diagnostiku",
    "groups": {
      "amounts": "Kolik vody",
      "rain": "Déšť, předpověď a mráz",
      "deep_soak": "Hloubková zálivka",
      "soil": "Půda",
      "growth": "Růst",
      "deficit": "Deficitní režim",
      "history": "Historie",
      "safety": "Bezpečnostní limity a čerpadlo",
      "notifications": "Oznámení",
      "more": "Další"
    },
    "overview": {
      "title": "Zahrada",
      "zone": "Zóna",
      "status": "Stav",
      "next": "Další",
      "last": "Poslední",
      "sort": "Řazení",
      "sort_name": "Podle názvu",
      "sort_next": "Podle další zálivky",
      "icons": "Ikony zón",
      "no_zones": "Zatím žádné zóny ZoneFlow.",
      "labels": {
        "watering": "Právě zalévá",
        "service_run": "Servisní běh",
        "waiting_pump": "Čeká na čerpadlo",
        "locked": "Zamčeno",
        "snoozed": "Dnes vynecháno",
        "paused": "Pozastaveno",
        "watered": "Dnes zalito",
        "soil_wet": "Mokrá půda",
        "drying": "Vysychá po dešti",
        "rain_forecast": "Předpověď deště",
        "rain_covered": "Stačil déšť",
        "wet_fortnight": "Mokré dva týdny",
        "rain_skip": "Vynecháno kvůli dešti",
        "safety_limit": "Bezpečnostní limit",
        "stopped": "Zastaveno",
        "scheduled": "Naplánováno",
        "nothing": "Nic naplánováno",
        "frost_wait": "Čeká kvůli mrazu",
        "frost_skip": "Vynecháno kvůli mrazu",
        "deep_soak_first": "Nejdřív hloubková zálivka"
      },
      "add_zone": "Přidat zónu",
      "show_add": "Zobrazit tlačítko Přidat zónu",
      "next_feed": "Další hnojení",
      "feed_due": "Pohnojit teď"
    },
    "close": "Zavřít",
    "device_page": "Otevřít stránku zařízení",
    "fertilized": "Pohnojeno",
    "mark_watered": "Označit jako zalité",
    "tips": {
      "crop_coefficient": "Vyjadřuje nároky rostliny na vodu v porovnání s referenční evapotranspirací (ET0). Vyšší hodnota znamená více vody, nižší méně.",
      "flow_rate_mm_per_min": "Intenzita závlahy v mm za minutu. Určuje délku jednoho zavlažovacího cyklu. Změřte průtokoměrem nebo pomocí nádoby a stopek.",
      "deep_soak_target_mm": "Množství vody dodané při hlubokém prolití, aby se vlhkost dostala až ke hlubším kořenům.",
      "deep_soak_interval_days": "Nejkratší interval ve dnech mezi hlubokými prolitími. Vyšší hodnota znamená méně časté hluboké zalévání.",
      "growth_ramp_profile": "Mladé rostliny zalévá méně a dávku postupně zvyšuje, jak rostou do plné velikosti.",
      "deficit_water_pct": "Podíl běžné dávky vody aplikovaný v deficitním režimu. Nižší hodnota rostlinu více vystavuje stresu (podporuje hlubší kořenění), vyšší hodnota udržuje bujný růst.",
      "mulch_status": "Mulčovaná půda (případně hustý zápoj rostlin nebo trávník) ztrácí odparem jen málo vody. Pro odhalenou půdu zvolte 'Bez mulče' a nastavte vedlejší korekci.",
      "mulch_et_adjustment_pct": "Jemné doladění denní závlahy podle pokryvu půdy (-50 % až +70 %). Kladné hodnoty pro odhalenou půdu, která rychle vysychá; záporné hodnoty pro půdu zadržující vodu (např. těžká jílovitá nebo ve stínu). Výrazně záporné hodnoty značně omezí zálivku: používejte je pouze v případě, že půda zůstává mokrá, a stav týden až dva sledujte.",
      "rain_eff_low": "Podíl mírného deště, který se skutečně dostane ke kořenům. Zbytek odteče nebo se odpaří.",
      "rain_eff_mid": "Podíl středně silného deště, který se skutečně dostane ke kořenům. Zbytek odteče nebo se odpaří.",
      "rain_eff_high": "Podíl silného deště, který se skutečně dostane ke kořenům. Zbytek odteče nebo se odpaří."
    }
  },
  "da": {
    "now": "Nu",
    "controls": "Betjening",
    "service": "Service og tjek (tæller ikke som vanding)",
    "journal": "Plantedagbog",
    "settings": "Indstillinger",
    "diagnostics": "Diagnosticering",
    "valve": "Ventil",
    "water_now": "Vand nu",
    "deep_soak_now": "Dybdevand nu",
    "snooze": "Spring over i dag",
    "reset_lock": "Nulstil lås",
    "min": "min",
    "pick_zone": "Vælg en ZoneFlow-zone til kortet.",
    "not_found": "ZoneFlow-zonen blev ikke fundet (fjernet eller ikke indlæst endnu).",
    "zone": "Zone",
    "show_journal": "Vis plantedagbogen",
    "show_settings": "Vis indstillingerne",
    "show_diagnostics": "Vis diagnosticeringen",
    "groups": {
      "amounts": "Vandmængde",
      "rain": "Regn, vejrudsigt og frost",
      "deep_soak": "Dybdevanding",
      "soil": "Jord",
      "growth": "Vækst",
      "deficit": "Sparetilstand",
      "history": "Historik",
      "safety": "Sikkerhedsgrænser og pumpe",
      "notifications": "Notifikationer",
      "more": "Mere"
    },
    "overview": {
      "title": "Have",
      "zone": "Zone",
      "status": "Status",
      "next": "Næste",
      "last": "Seneste",
      "sort": "Rækkefølge",
      "sort_name": "Efter navn",
      "sort_next": "Efter næste vanding",
      "icons": "Zoneikoner",
      "no_zones": "Ingen ZoneFlow-zoner endnu.",
      "labels": {
        "watering": "Vander nu",
        "service_run": "Servicekørsel",
        "waiting_pump": "Venter på pumpe",
        "locked": "Låst",
        "snoozed": "Sprunget over",
        "paused": "På pause",
        "watered": "Vandet i dag",
        "soil_wet": "Våd jord",
        "drying": "Tørrer ud efter regn",
        "rain_forecast": "Regn i udsigt",
        "rain_covered": "Regnen dækkede det",
        "wet_fortnight": "Våde 14 dage",
        "rain_skip": "Sprunget over pga. regn",
        "safety_limit": "Sikkerhedsgrænse",
        "stopped": "Stoppet",
        "scheduled": "Planlagt",
        "nothing": "Intet planlagt",
        "frost_wait": "Venter pga. frost",
        "frost_skip": "Sprunget over pga. frost",
        "deep_soak_first": "Dybdevanding først"
      },
      "add_zone": "Tilføj zone",
      "show_add": "Vis knappen Tilføj zone",
      "next_feed": "Næste gødskning",
      "feed_due": "Gød nu"
    },
    "close": "Luk",
    "device_page": "Åbn enhedssiden",
    "fertilized": "Gødsket",
    "mark_watered": "Markér som vandet",
    "tips": {
      "crop_coefficient": "Viser plantens vandbehov sammenlignet med reference-evapotranspiration (ET0). Højere værdi betyder mere vand, lavere betyder mindre.",
      "flow_rate_mm_per_min": "Vandtilførsel fra vandingssystemet i mm pr. minut. Det bestemmer varigheden af hver vanding. Måles med en flowmåler eller en beholder og et stopur.",
      "deep_soak_target_mm": "Vandmængde ved en dybdevanding, så fugten når helt ned til de dybe rødder.",
      "deep_soak_interval_days": "Minimumsantal af dage mellem dybdevandinger. En højere værdi giver sjældnere dybdevanding.",
      "growth_ramp_profile": "Vander unge planter mindre og øger vandmængden gradvist, efterhånden som de vokser til fuld størrelse.",
      "deficit_water_pct": "Andel af den normale vandmængde, der tilføres i sparetilstand. En lavere værdi stresser planten mere (fremmer dybe rødder); en højere værdi bevarer en frodig vækst.",
      "mulch_status": "Jord med mulch (eller et tæt løvhang eller græsplæne) mister meget lidt vand ved fordampning. Vælg 'Ikke mulchet' ved bar jord, og juster efterfølgende procenten ved siden af.",
      "mulch_et_adjustment_pct": "Finjustering af den daglige vanding baseret på jorddække (-50% til +70%). Positive værdier er til bar jord, der tørrer hurtigt ud; negative værdier er til vandholdende jord (f.eks. tung lerjord eller skyggefulde områder). Store negative værdier reducerer vandingen markant: brug dem kun, hvis jorden forbliver våd, og hold øje med det i 1-2 uger.",
      "rain_eff_low": "Andel af let regn, der reelt når rødderne. Resten fordamper eller løber af.",
      "rain_eff_mid": "Andel af moderat regn, der reelt når rødderne. Resten fordamper eller løber af.",
      "rain_eff_high": "Andel af kraftig regn, der reelt når rødderne. Resten fordamper eller løber af."
    }
  },
  "hu": {
    "now": "Most",
    "controls": "Vezérlés",
    "service": "Szerviz és ellenőrzés (nem számít öntözésnek)",
    "journal": "Növénynapló",
    "settings": "Beállítások",
    "diagnostics": "Diagnosztika",
    "valve": "Szelep",
    "water_now": "Öntözés most",
    "deep_soak_now": "Mélyöntözés most",
    "snooze": "Kihagyás ma",
    "reset_lock": "Zárolás feloldása",
    "min": "min",
    "pick_zone": "Válassz ZoneFlow zónát ehhez a kártyához.",
    "not_found": "Ez a ZoneFlow zóna nem található (törölték, vagy még nem töltődött be).",
    "zone": "Zóna",
    "show_journal": "Növénynapló megjelenítése",
    "show_settings": "Beállítások megjelenítése",
    "show_diagnostics": "Diagnosztika megjelenítése",
    "groups": {
      "amounts": "Vízmennyiség",
      "rain": "Eső, előrejelzés és fagy",
      "deep_soak": "Mélyöntözés",
      "soil": "Talaj",
      "growth": "Növekedés",
      "deficit": "Takarékos mód",
      "history": "Előzmények",
      "safety": "Biztonsági korlátok és szivattyú",
      "notifications": "Értesítések",
      "more": "Egyéb"
    },
    "overview": {
      "title": "Kert",
      "zone": "Zóna",
      "status": "Állapot",
      "next": "Következő",
      "last": "Utolsó",
      "sort": "Sorrend",
      "sort_name": "Név szerint",
      "sort_next": "Következő öntözés szerint",
      "icons": "Zónaikonok",
      "no_zones": "Még nincs ZoneFlow zóna.",
      "labels": {
        "watering": "Öntöz",
        "service_run": "Szervizfuttatás",
        "waiting_pump": "Szivattyúra vár",
        "locked": "Zárolva",
        "snoozed": "Mára kihagyva",
        "paused": "Szüneteltetve",
        "watered": "Ma öntözve",
        "soil_wet": "Nedves talaj",
        "drying": "Száradás eső után",
        "rain_forecast": "Eső várható",
        "rain_covered": "Az eső pótolta",
        "wet_fortnight": "Esős két hét",
        "rain_skip": "Eső miatt kihagyva",
        "safety_limit": "Biztonsági korlát",
        "stopped": "Leállt",
        "scheduled": "Ütemezve",
        "nothing": "Nincs ütemezve",
        "frost_wait": "Fagy miatt vár",
        "frost_skip": "Fagy miatt kihagyva",
        "deep_soak_first": "Előbb mélyöntözés"
      },
      "add_zone": "Zóna hozzáadása",
      "show_add": "A Zóna hozzáadása gomb megjelenítése",
      "next_feed": "Következő tápanyag-utánpótlás",
      "feed_due": "Tápanyag most"
    },
    "close": "Bezárás",
    "device_page": "Eszközoldal megnyitása",
    "fertilized": "Tápanyag pótolva",
    "mark_watered": "Megjelölés öntözöttként",
    "tips": {
      "crop_coefficient": "A növény vízigénye a referencia-párolgáshoz (ET0) képest. A magasabb érték több, az alacsonyabb kevesebb vizet jelent.",
      "flow_rate_mm_per_min": "A öntözőrendszer csapadékintenzitása mm/percben. Ez határozza meg az egyes öntözések időtartamát. Áramlásmérővel, vagy edénnyel és stopperórával mérhető.",
      "deep_soak_target_mm": "A mélyöntözés során kijuttatott vízmennyiség, amely eléri a mélyebben fekvő gyökereket is.",
      "deep_soak_interval_days": "A mélyöntözések közötti minimális időtartam napokban. A nagyobb érték ritkább mélyöntözést jelent.",
      "growth_ramp_profile": "A fiatal növényeket kevesebb vízzel öntözi, majd a növekedéssel párhuzamosan fokozatosan emeli a mennyiséget a teljes méret eléréséig.",
      "deficit_water_pct": "A normál vízmennyiség százalékos aránya hiányöntözési (csökkentett) módban. Az alacsonyabb érték jobban terheli a növényt (mélyebb gyökérzet növesztésére ösztönzi); a magasabb érték dús növekedést biztosít.",
      "mulch_status": "A mulcsozott talaj (vagy a sűrű növényzet, illetve gyep) párolgási vesztesége alacsony. Csupasz talaj esetén válassza a 'Nem takart' lehetőséget, majd állítsa be a mellette lévő korrekciót.",
      "mulch_et_adjustment_pct": "A napi öntözési mennyiség finomhangolása a talajtakarástól függően (-50% és +70% között). Pozitív érték a gyorsan kiszáradó, csupasz talajhoz; negatív érték a jó víztartó talajhoz (pl. kötött agyag vagy árnyékos terület). A nagy negatív értékek jelentősen csökkentik az öntözést: csak akkor használja, ha a talaj tartósan nedves marad, és figyelje a növényeket 1-2 hétig.",
      "rain_eff_low": "A gyenge eső azon hányada, amely valóban eléri a gyökereket. A többi elpárolog vagy elfolyik.",
      "rain_eff_mid": "A mérsékelt eső azon hányada, amely valóban eléri a gyökereket. A többi elpárolog vagy elfolyik.",
      "rain_eff_high": "A heves eső azon hányada, amely valóban eléri a gyökereket. A többi elpárolog vagy elfolyik."
    }
  },
  "nb": {
    "now": "Nå",
    "controls": "Styring",
    "service": "Service og kontroll (teller ikke som vanning)",
    "journal": "Plantedagbok",
    "settings": "Innstillinger",
    "diagnostics": "Diagnostikk",
    "valve": "Ventil",
    "water_now": "Vann nå",
    "deep_soak_now": "Dypvann nå",
    "snooze": "Hopp over i dag",
    "reset_lock": "Nullstill lås",
    "min": "min",
    "pick_zone": "Velg en ZoneFlow-sone for dette kortet.",
    "not_found": "Fant ikke denne ZoneFlow-sonen (fjernet, eller ikke lastet ennå).",
    "zone": "Sone",
    "show_journal": "Vis plantedagboken",
    "show_settings": "Vis innstillingene",
    "show_diagnostics": "Vis diagnostikken",
    "groups": {
      "amounts": "Vannmengde",
      "rain": "Regn, værmelding og frost",
      "deep_soak": "Dypvanning",
      "soil": "Jord",
      "growth": "Vekst",
      "deficit": "Underskuddsvanning",
      "history": "Historikk",
      "safety": "Sikkerhetsgrenser og pumpe",
      "notifications": "Varsler",
      "more": "Mer"
    },
    "overview": {
      "title": "Hage",
      "zone": "Sone",
      "status": "Status",
      "next": "Neste",
      "last": "Sist",
      "sort": "Rekkefølge",
      "sort_name": "Etter navn",
      "sort_next": "Etter neste vanning",
      "icons": "Soneikoner",
      "no_zones": "Ingen ZoneFlow-soner ennå.",
      "labels": {
        "watering": "Vanner nå",
        "service_run": "Servicekjøring",
        "waiting_pump": "Venter på pumpe",
        "locked": "Låst",
        "snoozed": "Hoppet over i dag",
        "paused": "På pause",
        "watered": "Vannet i dag",
        "soil_wet": "Våt jord",
        "drying": "Tørker opp etter regn",
        "rain_forecast": "Regn meldt",
        "rain_covered": "Regnet dekket behovet",
        "wet_fortnight": "Våte to uker",
        "rain_skip": "Hoppet over pga. regn",
        "safety_limit": "Sikkerhetsgrense",
        "stopped": "Stoppet",
        "scheduled": "Planlagt",
        "nothing": "Ingenting planlagt",
        "frost_wait": "Venter på grunn av frost",
        "frost_skip": "Hoppet over pga. frost",
        "deep_soak_first": "Dypvanning først"
      },
      "add_zone": "Legg til sone",
      "show_add": "Vis knappen Legg til sone",
      "next_feed": "Neste gjødsling",
      "feed_due": "Gjødsle nå"
    },
    "close": "Lukk",
    "device_page": "Åpne enhetssiden",
    "fertilized": "Gjødslet",
    "mark_watered": "Merk som vannet",
    "tips": {
      "crop_coefficient": "Plantens vannbehov sammenlignet med referanse-evapotranspirasjon (ET0). Høyere verdi gir mer vann, lavere gir mindre.",
      "flow_rate_mm_per_min": "Vanningssystemets vanntilførsel i mm per minutt. Dette bestemmer varigheten på hver vanning. Kan måles med mengdemåler eller med en beholder og stoppeklokke.",
      "deep_soak_target_mm": "Vannmengde tilført ved dypvanning slik at fuktigheten når de dypere røttene.",
      "deep_soak_interval_days": "Minstetid i dager mellom hver dypvanning. Høyere verdi gir sjeldnere dypvanning.",
      "growth_ramp_profile": "Vanner unge planter mindre og øker vannmengden gradvis etter hvert som de vokser til full størrelse.",
      "deficit_water_pct": "Andel av normal vannmengde som tilføres når underskuddsvanning er aktiv. Lavere verdi stresser planten mer (fremmer dypere rotvekst); høyere verdi opprettholder frodig vekst.",
      "mulch_status": "Jord dekket med mulch (eller tett bladverk/plen) mister lite vann til fordamping. Velg 'Ikke mulchet' for bar jord, og juster deretter korreksjonsprosenten ved siden av.",
      "mulch_et_adjustment_pct": "Finjustering av den daglige vanningen basert på dekke (-50 % til +70 %). Positive verdier brukes for bar jord som tørker raskt; negative verdier for jord som holder på fuktigheten (som tung leirjord eller i skygge). Store negative verdier reduserer vanningen betraktelig: bruk dette kun dersom jorden forblir våt, og følg med i en uke eller to.",
      "rain_eff_low": "Andel av lett regn som faktisk når røttene. Resten fordamper eller renner vekk.",
      "rain_eff_mid": "Andel av moderat regn som faktisk når røttene. Resten fordamper eller renner vekk.",
      "rain_eff_high": "Andel av kraftig regn som faktisk når røttene. Resten fordamper eller renner vekk."
    }
  },
  "pt-BR": {
    "now": "Agora",
    "controls": "Controles",
    "service": "Manutenção e testes (não conta como irrigação)",
    "journal": "Diário da planta",
    "settings": "Configurações",
    "diagnostics": "Diagnóstico",
    "valve": "Válvula",
    "water_now": "Irrigar agora",
    "deep_soak_now": "Irrigação profunda agora",
    "snooze": "Não irrigar hoje",
    "reset_lock": "Desbloquear",
    "min": "min",
    "pick_zone": "Escolha uma zona ZoneFlow para este cartão.",
    "not_found": "Esta zona ZoneFlow não foi encontrada (removida ou ainda não carregada).",
    "zone": "Zona",
    "show_journal": "Mostrar o diário da planta",
    "show_settings": "Mostrar as configurações",
    "show_diagnostics": "Mostrar o diagnóstico",
    "groups": {
      "amounts": "Quantidade de água",
      "rain": "Chuva, previsão e geada",
      "deep_soak": "Irrigação profunda",
      "soil": "Solo",
      "growth": "Crescimento",
      "deficit": "Irrigação deficitária",
      "history": "Histórico",
      "safety": "Limites de segurança e bomba",
      "notifications": "Notificações",
      "more": "Mais"
    },
    "overview": {
      "title": "Jardim",
      "zone": "Zona",
      "status": "Status",
      "next": "Próxima",
      "last": "Última",
      "sort": "Ordem",
      "sort_name": "Por nome",
      "sort_next": "Pela próxima irrigação",
      "icons": "Ícones das zonas",
      "no_zones": "Ainda não há zonas ZoneFlow.",
      "labels": {
        "watering": "Irrigando agora",
        "service_run": "Ciclo de manutenção",
        "waiting_pump": "Aguardando a bomba",
        "locked": "Bloqueada",
        "snoozed": "Sem irrigação hoje",
        "paused": "Em pausa",
        "watered": "Irrigada hoje",
        "soil_wet": "Solo úmido",
        "drying": "Secando após a chuva",
        "rain_forecast": "Previsão de chuva",
        "rain_covered": "A chuva bastou",
        "wet_fortnight": "Quinzena úmida",
        "rain_skip": "Pulada: chuva",
        "safety_limit": "Limite de segurança",
        "stopped": "Interrompida",
        "scheduled": "Agendada",
        "nothing": "Nada agendado",
        "frost_wait": "Aguardando: geada",
        "frost_skip": "Pulada: geada",
        "deep_soak_first": "Irrigação profunda primeiro"
      },
      "add_zone": "Adicionar zona",
      "show_add": "Mostrar o botão Adicionar zona",
      "next_feed": "Próxima adubação",
      "feed_due": "Adubar agora"
    },
    "close": "Fechar",
    "device_page": "Abrir a página do dispositivo",
    "fertilized": "Adubado",
    "mark_watered": "Marcar como regado",
    "tips": {
      "crop_coefficient": "Necessidade de água da planta em comparação com a evapotranspiração de referência (ET0). Valores mais altos significam mais água; valores mais baixos, menos.",
      "flow_rate_mm_per_min": "Taxa de precipitação da irrigação em mm por minuto. Determina a duração de cada ciclo. Pode ser medida com um medidor de vazão ou usando um recipiente e um cronômetro.",
      "deep_soak_target_mm": "Quantidade de água aplicada em uma irrigação profunda para atingir as raízes mais profundas.",
      "deep_soak_interval_days": "Intervalo mínimo em dias entre irrigações profundas. Valores maiores tornam as irrigações profundas menos frequentes.",
      "growth_ramp_profile": "Aplica menos água em plantas jovens e aumenta a quantidade gradualmente à medida que crescem até o tamanho adulto.",
      "deficit_water_pct": "Porcentagem da quantidade normal de água aplicada enquanto o modo de déficit estiver ativo. Valores menores estressam mais a planta (estimulam raízes profundas); valores maiores mantêm um crescimento exuberante.",
      "mulch_status": "Solo com cobertura (ou copa densa / gramado) perde pouca água por evaporação. Selecione 'Sem cobertura' para solo exposto e ajuste a porcentagem ao lado.",
      "mulch_et_adjustment_pct": "Ajuste fino da irrigação diária com base na cobertura do solo (-50% a +70%). Valores positivos são para solos expostos que secam rápido; valores negativos para solos que retêm umidade (como argilosos ou na sombra). Ajustes negativos altos reduzem bastante a irrigação: use-os apenas se o solo permanecer úmido e observe o resultado por uma ou duas semanas.",
      "rain_eff_low": "Proporção de chuva fraca que realmente atinge as raízes. O restante evapora ou escorre.",
      "rain_eff_mid": "Proporção de chuva moderada que realmente atinge as raízes. O restante evapora ou escorre.",
      "rain_eff_high": "Proporção de chuva forte que realmente atinge as raízes. O restante evapora ou escorre."
    }
  },
  "ru": {
    "now": "Сейчас",
    "controls": "Управление",
    "service": "Сервис и проверки (не считаются поливом)",
    "journal": "Дневник растения",
    "settings": "Настройки",
    "diagnostics": "Диагностика",
    "valve": "Клапан",
    "water_now": "Полить сейчас",
    "deep_soak_now": "Глубокий полив сейчас",
    "snooze": "Пропустить сегодня",
    "reset_lock": "Сбросить блокировку",
    "min": "мин",
    "pick_zone": "Выберите зону ZoneFlow для этой карточки.",
    "not_found": "Зона ZoneFlow не найдена (удалена или ещё не загружена).",
    "zone": "Зона",
    "show_journal": "Показывать дневник растения",
    "show_settings": "Показывать настройки",
    "show_diagnostics": "Показывать диагностику",
    "groups": {
      "amounts": "Сколько воды",
      "rain": "Дождь, прогноз и заморозки",
      "deep_soak": "Глубокий полив",
      "soil": "Почва",
      "growth": "Рост",
      "deficit": "Режим дефицита",
      "history": "История",
      "safety": "Защитные лимиты и насос",
      "notifications": "Уведомления",
      "more": "Ещё"
    },
    "overview": {
      "title": "Сад",
      "zone": "Зона",
      "status": "Состояние",
      "next": "Далее",
      "last": "Последний",
      "sort": "Порядок",
      "sort_name": "По имени",
      "sort_next": "По следующему поливу",
      "icons": "Значки зон",
      "no_zones": "Зон ZoneFlow пока нет.",
      "labels": {
        "watering": "Идёт полив",
        "service_run": "Сервисный запуск",
        "waiting_pump": "Ждёт насос",
        "locked": "Заблокировано",
        "snoozed": "Пропуск сегодня",
        "paused": "Пауза",
        "watered": "Полито сегодня",
        "soil_wet": "Почва мокрая",
        "drying": "Просыхание после дождя",
        "rain_forecast": "Прогноз дождя",
        "rain_covered": "Хватило дождя",
        "wet_fortnight": "Дождливые 2 недели",
        "rain_skip": "Пропуск из-за дождя",
        "safety_limit": "Защитный лимит",
        "stopped": "Остановлено",
        "scheduled": "Запланировано",
        "nothing": "Ничего не запланировано",
        "frost_wait": "Ждёт из-за заморозков",
        "frost_skip": "Пропуск из-за заморозков",
        "deep_soak_first": "Сначала глубокий полив"
      },
      "add_zone": "Добавить зону",
      "show_add": "Показывать кнопку «Добавить зону»",
      "next_feed": "Следующая подкормка",
      "feed_due": "Подкормить сейчас"
    },
    "close": "Закрыть",
    "device_page": "Открыть страницу устройства",
    "fertilized": "Подкормлено",
    "mark_watered": "Отметить полив",
    "tips": {
      "crop_coefficient": "Потребность растения в воде по сравнению с эталонной эвапотранспирацией (ET0). Чем выше значение, тем больше воды требуется.",
      "flow_rate_mm_per_min": "Интенсивность полива в мм/мин. Определяет продолжительность одного сеанса. Можно измерить расходомером или с помощью емкости и секундомера.",
      "deep_soak_target_mm": "Количество воды, подаваемое при глубоком промачивании, чтобы влага доходила до глубоких корней.",
      "deep_soak_interval_days": "Минимальный интервал в днях между глубокими поливами. Чем выше значение, тем реже проводится глубокий полив.",
      "growth_ramp_profile": "Подает меньше воды молодым растениям и постепенно увеличивает объем по мере их роста до взрослого состояния.",
      "deficit_water_pct": "Доля от нормы полива, подаваемая в режиме дефицита. Низкое значение сильнее подвергает растение стрессу (стимулирует рост корней вглубь); высокое — поддерживает пышный рост.",
      "mulch_status": "Замульчированная почва (или плотный покров / газон) теряет мало влаги на испарение. Выберите «Без мульчи» для открытого грунта и задайте процент коррекции рядом.",
      "mulch_et_adjustment_pct": "Точная настройка ежедневного полива в зависимости от покрытия почвы (от -50% до +70%). Положительные значения — для открытой, быстро сохнущей почвы; отрицательные — для влагоемких почв (глинистых или в тени). Сильно отрицательные значения существенно снижают полив: используйте их только если почва остается сырой, и наблюдайте за состоянием в течение 1-2 недель.",
      "rain_eff_low": "Доля слабого дождя, которая реально доходит до корней. Остальное испаряется или стекает.",
      "rain_eff_mid": "Доля умеренного дождя, которая реально доходит до корней. Остальное испаряется или стекает.",
      "rain_eff_high": "Доля сильного дождя, которая реально доходит до корней. Остальное испаряется или стекает."
    }
  },
  "sk": {
    "now": "Teraz",
    "controls": "Ovládanie",
    "service": "Servis a kontroly (nepočíta sa ako zálievka)",
    "journal": "Denník rastliny",
    "settings": "Nastavenia",
    "diagnostics": "Diagnostika",
    "valve": "Ventil",
    "water_now": "Zaliať teraz",
    "deep_soak_now": "Hĺbková zálievka teraz",
    "snooze": "Dnes vynechať",
    "reset_lock": "Resetovať zámok",
    "min": "min",
    "pick_zone": "Vyberte pre túto kartu zónu ZoneFlow.",
    "not_found": "Táto zóna ZoneFlow sa nenašla (odstránená alebo ešte nenačítaná).",
    "zone": "Zóna",
    "show_journal": "Zobraziť denník rastliny",
    "show_settings": "Zobraziť nastavenia",
    "show_diagnostics": "Zobraziť diagnostiku",
    "groups": {
      "amounts": "Koľko vody",
      "rain": "Dážď, predpoveď a mráz",
      "deep_soak": "Hĺbková zálievka",
      "soil": "Pôda",
      "growth": "Rast",
      "deficit": "Deficitný režim",
      "history": "História",
      "safety": "Bezpečnostné limity a čerpadlo",
      "notifications": "Oznámenia",
      "more": "Viac"
    },
    "overview": {
      "title": "Záhrada",
      "zone": "Zóna",
      "status": "Stav",
      "next": "Ďalšia",
      "last": "Posledná",
      "sort": "Poradie",
      "sort_name": "Podľa názvu",
      "sort_next": "Podľa ďalšej zálievky",
      "icons": "Ikony zón",
      "no_zones": "Zatiaľ žiadne zóny ZoneFlow.",
      "labels": {
        "watering": "Práve polieva",
        "service_run": "Servisný chod",
        "waiting_pump": "Čaká na čerpadlo",
        "locked": "Zamknuté",
        "snoozed": "Dnes vynechané",
        "paused": "Pozastavené",
        "watered": "Dnes zaliate",
        "soil_wet": "Mokrá pôda",
        "drying": "Vysychá po daždi",
        "rain_forecast": "Predpoveď dažďa",
        "rain_covered": "Stačil dážď",
        "wet_fortnight": "Mokré dva týždne",
        "rain_skip": "Vynechané pre dážď",
        "safety_limit": "Bezpečnostný limit",
        "stopped": "Zastavené",
        "scheduled": "Naplánované",
        "nothing": "Nič nie je naplánované",
        "frost_wait": "Čaká pre mráz",
        "frost_skip": "Vynechané pre mráz",
        "deep_soak_first": "Najprv hĺbková zálievka"
      },
      "add_zone": "Pridať zónu",
      "show_add": "Zobraziť tlačidlo Pridať zónu",
      "next_feed": "Ďalšie hnojenie",
      "feed_due": "Pohnojiť teraz"
    },
    "close": "Zavrieť",
    "device_page": "Otvoriť stránku zariadenia",
    "fertilized": "Pohnojené",
    "mark_watered": "Označiť ako zaliate",
    "tips": {
      "crop_coefficient": "Vyjadruje potrebu vody pre rastlinu v porovnaní s referenčnou evapotranspiráciou (ET0). Vyššia hodnota znamená viac vody, nižšia menej.",
      "flow_rate_mm_per_min": "Intenzita zavlažovania v mm za minútu. Určuje dĺžku jedného cyklu. Zmerajte ju prietokomerom alebo pomocou nádoby a stopiek.",
      "deep_soak_target_mm": "Množstvo vody dodané pri hlbokom preliatí, aby sa vlhkosť dostala až k hlbším koreňom.",
      "deep_soak_interval_days": "Najkratší interval v dňoch medzi hlbokými preliatiami. Vyššia hodnota znamená menej časté hlboké zalievanie.",
      "growth_ramp_profile": "Mladé rastliny zalieva menej a dávku postupne zvyšuje, ako rastú do plnej veľkosti.",
      "deficit_water_pct": "Podiel bežnej dávky vody aplikovaný v deficitnom režime. Nižšia hodnota vystavuje rastlinu väčšiemu stresu (podporuje hlbšie zakorenenie); vyššia udržiava bujný rast.",
      "mulch_status": "Mulčovaná pôda (prípadne hustý porast alebo trávnik) stráca odparovaním len málo vody. Pre odhalenú pôdu zvoľte 'Bez mulča' a nastavte vedľajšiu korekciu.",
      "mulch_et_adjustment_pct": "Jemné doladenie dennej závlahy podľa pokrytia pôdy (-50 % až +70 %). Kladné hodnoty pre odhalenú pôdu, ktorá rýchlo schne; záporné hodnoty pre pôdu zadržiavajúcu vodu (napr. ťažká ílovitá alebo v tieni). Výrazne záporné hodnoty značne obmedzia zálievku: používajte ich len vtedy, ak pôda zostáva mokrá, a stav týždeň až dva sledujte.",
      "rain_eff_low": "Podiel mierneho dažďa, ktorý sa skutočne dostane ku koreňom. Zvyšok odtečie alebo sa odparí.",
      "rain_eff_mid": "Podiel stredne silného dažďa, ktorý sa skutočne dostane ku koreňom. Zvyšok odtečie alebo sa odparí.",
      "rain_eff_high": "Podiel silného dažďa, ktorý sa skutočne dostane ku koreňom. Zvyšok odtečie alebo sa odparí."
    }
  },
  "uk": {
    "now": "Зараз",
    "controls": "Керування",
    "service": "Сервіс і перевірки (не зараховуються як полив)",
    "journal": "Щоденник рослини",
    "settings": "Налаштування",
    "diagnostics": "Діагностика",
    "valve": "Клапан",
    "water_now": "Полити зараз",
    "deep_soak_now": "Глибокий полив зараз",
    "snooze": "Пропустити сьогодні",
    "reset_lock": "Скинути блокування",
    "min": "min",
    "pick_zone": "Виберіть зону ZoneFlow для цієї картки.",
    "not_found": "Цю зону ZoneFlow не знайдено (видалена або ще не завантажена).",
    "zone": "Зона",
    "show_journal": "Показувати щоденник рослини",
    "show_settings": "Показувати налаштування",
    "show_diagnostics": "Показувати діагностику",
    "groups": {
      "amounts": "Скільки води",
      "rain": "Дощ, прогноз і заморозки",
      "deep_soak": "Глибокий полив",
      "soil": "Ґрунт",
      "growth": "Ріст",
      "deficit": "Дефіцитний полив",
      "history": "Історія",
      "safety": "Запобіжні ліміти й насос",
      "notifications": "Сповіщення",
      "more": "Більше"
    },
    "overview": {
      "title": "Сад",
      "zone": "Зона",
      "status": "Стан",
      "next": "Далі",
      "last": "Останній",
      "sort": "Порядок",
      "sort_name": "За назвою",
      "sort_next": "За наступним поливом",
      "icons": "Значки зон",
      "no_zones": "Ще немає зон ZoneFlow.",
      "labels": {
        "watering": "Поливає",
        "service_run": "Сервісний запуск",
        "waiting_pump": "Чекає на насос",
        "locked": "Заблоковано",
        "snoozed": "Пропущено сьогодні",
        "paused": "Пауза",
        "watered": "Полито сьогодні",
        "soil_wet": "Ґрунт мокрий",
        "drying": "Підсихає після дощу",
        "rain_forecast": "Прогноз дощу",
        "rain_covered": "Дощу досить",
        "wet_fortnight": "Дощові 2 тижні",
        "rain_skip": "Пропуск: дощ",
        "safety_limit": "Запобіжний ліміт",
        "stopped": "Зупинено",
        "scheduled": "Заплановано",
        "nothing": "Нічого не заплановано",
        "frost_wait": "Чекає: заморозки",
        "frost_skip": "Пропуск: заморозки",
        "deep_soak_first": "Спершу глибокий полив"
      },
      "add_zone": "Додати зону",
      "show_add": "Показувати кнопку «Додати зону»",
      "next_feed": "Наступне підживлення",
      "feed_due": "Підживити зараз"
    },
    "close": "Закрити",
    "device_page": "Відкрити сторінку пристрою",
    "fertilized": "Підживлено",
    "mark_watered": "Позначити полив",
    "tips": {
      "crop_coefficient": "Потреба рослини у воді порівняно з еталонною евапотранспірацією (ET0). Вище значення означає більше води, нижче — менше.",
      "flow_rate_mm_per_min": "Інтенсивність поливу в мм за хвилину. Визначає тривалість кожного сеансу. Можна виміряти витратоміром або за допомогою ємності та секундоміра.",
      "deep_soak_target_mm": "Кількість води, що подається під час глибокого просочування, щоб волога досягала глибокого коріння.",
      "deep_soak_interval_days": "Мінімальний інтервал у днях між глибокими поливами. Більше значення означає рідший глибокий полив.",
      "growth_ramp_profile": "Поливає молоді рослини менше і поступово збільшує об'єм води в міру їхнього росту до дорослого стану.",
      "deficit_water_pct": "Частка від норми води під час увімкненого дефіцитного режиму. Нижчий відсоток сильніше піддає рослину стресу (стимулює розвиток глибокого коріння); вищий — підтримує пишний ріст.",
      "mulch_status": "Замульчований ґрунт (або щільний насадження / газон) втрачає мало води через випаровування. Виберіть «Без мульчі» для відкритого ґрунту та налаштуйте відсоток коригування поруч.",
      "mulch_et_adjustment_pct": "Точне налаштування щоденного поливу залежно від покриття ґрунту (від -50% до +70%). Додатні значення — для відкритого ґрунту, що швидко висихає; від'ємні — для ґрунту, що добре утримує вологу (наприклад, глинистого або в тіні). Значні від'ємні значення суттєво зменшують полив: використовуйте їх лише якщо ґрунт залишається вологим, і спостерігайте протягом 1-2 тижнів.",
      "rain_eff_low": "Частка слабкого дощу, яка дійсно досягає коріння. Решта випаровується або стікає.",
      "rain_eff_mid": "Частка помірного дощу, яка дійсно досягає коріння. Решта випаровується або стікає.",
      "rain_eff_high": "Частка сильного дощу, яка дійсно досягає коріння. Решта випаровується або стікає."
    }
  },
  "zh-Hans": {
    "now": "当前",
    "controls": "控制",
    "service": "维护与检查（不计为浇水）",
    "journal": "植物日志",
    "settings": "设置",
    "diagnostics": "诊断",
    "valve": "阀门",
    "water_now": "立即浇水",
    "deep_soak_now": "立即深层浇灌",
    "snooze": "今天跳过",
    "reset_lock": "重置锁",
    "min": "min",
    "pick_zone": "请为此卡片选择一个 ZoneFlow 区域。",
    "not_found": "找不到此 ZoneFlow 区域（已删除或尚未加载）。",
    "zone": "区域",
    "show_journal": "显示植物日志",
    "show_settings": "显示设置",
    "show_diagnostics": "显示诊断",
    "groups": {
      "amounts": "浇水量",
      "rain": "降雨、预报和霜冻",
      "deep_soak": "深层浇灌",
      "soil": "土壤",
      "growth": "生长",
      "deficit": "控水模式",
      "history": "历史",
      "safety": "安全限制与水泵",
      "notifications": "通知",
      "more": "更多"
    },
    "overview": {
      "title": "花园",
      "zone": "区域",
      "status": "状态",
      "next": "下次",
      "last": "上次",
      "sort": "排序",
      "sort_name": "按名称",
      "sort_next": "按下次浇水",
      "icons": "区域图标",
      "no_zones": "还没有 ZoneFlow 区域。",
      "labels": {
        "watering": "正在浇水",
        "service_run": "维护运行",
        "waiting_pump": "等待水泵",
        "locked": "已锁定",
        "snoozed": "今天跳过",
        "paused": "已暂停",
        "watered": "今天已浇水",
        "soil_wet": "土壤湿润",
        "drying": "雨后晾干中",
        "rain_forecast": "预报有雨",
        "rain_covered": "雨水已足够",
        "wet_fortnight": "两周多雨",
        "rain_skip": "因雨跳过",
        "safety_limit": "安全限制",
        "stopped": "已停止",
        "scheduled": "已计划",
        "nothing": "无计划",
        "frost_wait": "霜冻等待",
        "frost_skip": "因霜冻跳过",
        "deep_soak_first": "先深层浇灌"
      },
      "add_zone": "添加区域",
      "show_add": "显示“添加区域”按钮",
      "next_feed": "下次施肥",
      "feed_due": "立即施肥"
    },
    "close": "关闭",
    "device_page": "打开设备页面",
    "fertilized": "已施肥",
    "mark_watered": "标记为已浇水",
    "tips": {
      "crop_coefficient": "衡量植物相比于基准蒸散发量 (ET0) 的需水程度。数值越高需水量越大，越低则越小。",
      "flow_rate_mm_per_min": "灌溉系统的喷灌强度（毫米/分钟）。该参数决定每次灌溉的持续时长。可使用流量计或利用测量容器与秒表测定。",
      "deep_soak_target_mm": "深层浇灌时的目标灌水量，确保水分能够渗透至较深根系。",
      "deep_soak_interval_days": "两次深层浇灌之间的最短间隔天数。设定值越大，深层浇灌频率越低。",
      "growth_ramp_profile": "在幼苗期减少浇水量，并随植物生长逐渐增加水量直至成熟。",
      "deficit_water_pct": "赤字灌溉模式下提供正常水量的百分比。设定较低值会让植物承受一定水分胁迫（有助于促进根系深扎）；较高值则可保持生长繁茂。",
      "mulch_status": "覆盖有机物（或具有密集的树冠、草坪）的土壤水分蒸发量极低。若为裸露土壤请选择“未覆盖”，并调整旁边的修正百分比。",
      "mulch_et_adjustment_pct": "根据土壤覆盖情况微调日常灌水量（-50% 至 +70%）。正值适用于干燥快的裸露土壤，负值适用于保水性强的土壤（如重黏土或阴凉区域）。较大的负值会大幅减少灌水量：仅建议在土壤持续湿润时使用，并观察一至两周。",
      "rain_eff_low": "小雨中实际渗透至根系有效吸收层的比例，其余部分会蒸发或形成地表径流。",
      "rain_eff_mid": "中雨中实际渗透至根系有效吸收层的比例，其余部分会蒸发或形成地表径流。",
      "rain_eff_high": "大雨中实际渗透至根系有效吸收层的比例，其余部分会蒸发或形成地表径流。"
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
  "sensor.next_fertilizing",
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
  // Once a first feed is recorded.
  "sensor.next_fertilizing": (state) => state && !["unknown", "unavailable"].includes(state.state),
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
  ["soil", [
    "number.soil_moisture_dry_pct", "number.soil_moisture_wet_pct", "select.soil_type", "select.drainage", "select.slope",
    "select.mulch_status", "number.mulch_et_adjustment_pct",
  ]],
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
  "button.service_run_10_min", "button.fertilized_today", "button.mark_watered",
]);

function t(hass, key) {
  const lang = (hass && (hass.locale?.language || hass.language)) || "en";
  const table = I18N[lang] || I18N[lang.split("-")[0]] || I18N.en;
  const lookup = (tbl) => key.split(".").reduce((node, part) => (node ? node[part] : undefined), tbl);
  return lookup(table) ?? lookup(I18N.en) ?? key;
}

// Hover text for a setting (keyed by the entity's name after the domain);
// English until a language has its own "tips".
function tip(hass, key) {
  const lang = (hass && (hass.locale?.language || hass.language)) || "en";
  const table = I18N[lang] || I18N[lang.split("-")[0]] || I18N.en;
  return table.tips?.[key] ?? I18N.en.tips?.[key];
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
      .more { display: flex; flex-wrap: wrap; gap: 8px; padding: 8px 16px 16px; border-top: 1px solid var(--divider-color); }
      .more button { display: inline-flex; align-items: center; gap: 6px; padding: 6px 14px; border-radius: 18px;
        border: 1px solid var(--divider-color); background: var(--secondary-background-color, transparent);
        color: var(--primary-text-color); font: inherit; font-size: 0.95em; cursor: pointer; }
      .more button:hover { border-color: var(--primary-color); }
      .more button ha-icon { --mdc-icon-size: 18px; color: var(--secondary-text-color); }
      dialog { border: none; border-radius: var(--ha-dialog-border-radius, 24px); padding: 0; width: min(560px, 94vw);
        max-height: 88vh; background: var(--mdc-theme-surface, var(--card-background-color, #fff));
        color: var(--primary-text-color); box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3); }
      dialog::backdrop { background: rgba(0, 0, 0, 0.45); }
      dialog .dlg { display: flex; flex-direction: column; max-height: 88vh; }
      dialog header { display: flex; align-items: center; gap: 8px; padding: 12px 8px 8px 20px;
        border-bottom: 1px solid var(--divider-color); }
      dialog header .dlg-title { flex: 1; font-size: 1.2em; font-weight: 500; }
      dialog header .dlg-sub { display: block; font-size: 0.8em; font-weight: 400; color: var(--secondary-text-color); }
      dialog header button { border: none; background: none; color: var(--secondary-text-color); cursor: pointer;
        padding: 8px; border-radius: 50%; display: inline-flex; }
      dialog header button:hover { background: var(--secondary-background-color); }
      dialog .dlg-body { overflow-y: auto; padding: 4px 20px 16px; }
      dialog footer { padding: 8px 20px 14px; border-top: 1px solid var(--divider-color); text-align: right; }
      dialog footer a { color: var(--primary-color); text-decoration: none; font-weight: 500; cursor: pointer; }
      .group-title { color: var(--secondary-text-color); font-size: 0.85em; font-weight: 500; text-transform: uppercase;
        letter-spacing: 0.04em; margin: 16px 0 2px; }
      .rows > * { display: block; margin: 4px 0; }
      .missing { padding: 16px; color: var(--secondary-text-color); }
      ${this._config.embedded ? `
      ha-card { box-shadow: none; border: none; background: none; }
      .header { display: none; }
      .status { padding-top: 4px; }` : ""}
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
    const rows = (keys) => keys
      .filter((key) => id(key))
      .map((key) => ({ entity: visible[key].entity_id, _tip: tip(hass, key.split(".")[1]) }));
    const buttons = (items) => {
      const entities = items
        .map(([key, name, icon]) => (id(key) ? {
          entity: visible[key].entity_id, name, icon,
          // One tap presses the button: no "more info" popup to press again.
          tap_action: { action: "call-service", service: "button.press", target: { entity_id: visible[key].entity_id } },
        } : null))
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
        ["button.fertilized_today", t(hass, "fertilized"), "mdi:sprout"],
        ["button.mark_watered", t(hass, "mark_watered"), "mdi:watering-can-outline"],
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
    // Journal, settings and diagnostics: buttons that open a popup, like
    // Home Assistant's own entity dialogs.
    this._popups = {};
    if (this._config.show_journal) this._popups.journal = { icon: "mdi:notebook-outline", parts: [[null, journal]] };
    if (this._config.show_settings) this._popups.settings = { icon: "mdi:cog-outline", parts: groups };
    if (this._config.show_diagnostics) {
      this._popups.diagnostics = { icon: "mdi:chart-box-outline", parts: [[null, diagnostics]] };
    }
    for (const [key, popup] of Object.entries(this._popups)) {
      popup.parts = popup.parts.filter(([, confs]) => confs.length);
      if (!popup.parts.length) delete this._popups[key];
    }
    section("now", now);
    section("controls", controls);
    section("service", service);
    if (Object.keys(this._popups).length) {
      const bar = document.createElement("div");
      bar.className = "more";
      for (const [key, popup] of Object.entries(this._popups)) {
        const button = document.createElement("button");
        const icon = document.createElement("ha-icon");
        icon.setAttribute("icon", popup.icon);
        button.append(icon, document.createTextNode(t(hass, key)));
        button.addEventListener("click", () => this._openPopup(key));
        bar.appendChild(button);
      }
      card.appendChild(bar);
    }
    // Rebuilt while a popup was open (e.g. a setting appeared): open again.
    if (this._popupKey && this._popups[this._popupKey]) this._openPopup(this._popupKey);
  }

  _openPopup(key) {
    const hass = this._hass;
    const popup = this._popups?.[key];
    if (!popup || !this.shadowRoot) return;
    this.shadowRoot.querySelector("dialog")?.remove();
    this._popupKey = key;
    const dialog = document.createElement("dialog");
    dialog.setAttribute("aria-label", t(hass, key));
    const box = document.createElement("div");
    box.className = "dlg";
    const header = document.createElement("header");
    const title = document.createElement("div");
    title.className = "dlg-title";
    title.textContent = t(hass, key);
    const device = hass.devices?.[this._config.device_id];
    const sub = document.createElement("span");
    sub.className = "dlg-sub";
    sub.textContent = this._config.title || device?.name_by_user || device?.name || "";
    title.appendChild(sub);
    const close = document.createElement("button");
    close.setAttribute("aria-label", t(hass, "close"));
    const closeIcon = document.createElement("ha-icon");
    closeIcon.setAttribute("icon", "mdi:close");
    close.appendChild(closeIcon);
    close.addEventListener("click", () => dialog.close());
    header.append(title, close);
    const body = document.createElement("div");
    body.className = "dlg-body";
    for (const [groupKey, confs] of popup.parts) {
      if (groupKey) {
        const heading = document.createElement("div");
        heading.className = "group-title";
        heading.textContent = t(hass, `groups.${groupKey}`);
        body.appendChild(heading);
      }
      const list = document.createElement("div");
      list.className = "rows";
      body.appendChild(list);
      this._addRows(list, confs, "popup");
    }
    box.append(header, body);
    if (hass.user?.is_admin) {
      // The zone's own device page: every entity, logbook, and more.
      const footer = document.createElement("footer");
      const link = document.createElement("a");
      link.textContent = t(hass, "device_page");
      link.addEventListener("click", () => {
        dialog.close();
        history.pushState(null, "", `/config/devices/device/${this._config.device_id}`);
        window.dispatchEvent(new CustomEvent("location-changed"));
      });
      footer.appendChild(link);
      box.appendChild(footer);
    }
    dialog.appendChild(box);
    dialog.addEventListener("click", (ev) => {
      if (ev.target === dialog) dialog.close(); // a click on the backdrop
    });
    dialog.addEventListener("close", () => {
      if (this._popupKey === key) this._popupKey = undefined;
      this._rows = (this._rows || []).filter((row) => !box.contains(row));
      dialog.remove();
    });
    // An entity's own dialog (its name clicked) must not open underneath
    // this one: step aside, and come back when it closes.
    dialog.addEventListener("hass-more-info", () => {
      dialog.close();
      window.addEventListener(
        "dialog-closed",
        () => {
          if (this.isConnected && !this.shadowRoot.querySelector("dialog")) this._openPopup(key);
        },
        { once: true }
      );
    });
    this.shadowRoot.appendChild(dialog);
    dialog.showModal();
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
            if (conf._tip) row.title = conf._tip;
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

// ---------------------------------------------------------------------------
// Overview card: every zone in one table -- status, next and last watering,
// a "water now" button -- and a click on a zone opens its full card.
//
//   type: custom:zoneflow-overview-card
//   sort: name | next          (optional, default name)
//   icons: {<device_id>: mdi:chili-hot}   (optional; set in the editor)
// ---------------------------------------------------------------------------

// Status code -> [short label, icon, is a warning].
const STATUS_LABELS = {
  watering: ["watering", "mdi:water", false],
  service_run: ["service_run", "mdi:wrench-clock", false],
  waiting_pump: ["waiting_pump", "mdi:pump", false],
  lock_held: ["locked", "mdi:lock-alert", true],
  snoozed: ["snoozed", "mdi:sleep", false],
  paused: ["paused", "mdi:pause-circle-outline", false],
  done: ["watered", "mdi:check-circle-outline", false],
  skipped_soil_wet: ["soil_wet", "mdi:water-percent", false],
  waiting_soil_wet: ["soil_wet", "mdi:water-percent", false],
  skipped_drydown: ["drying", "mdi:weather-partly-rainy", false],
  waiting_drydown: ["drying", "mdi:weather-partly-rainy", false],
  skipped_forecast: ["rain_forecast", "mdi:weather-pouring", false],
  skipped_rain_credit: ["rain_covered", "mdi:weather-rainy", false],
  skipped_wet_fortnight: ["wet_fortnight", "mdi:weather-rainy", false],
  cancelled_rain: ["rain_skip", "mdi:weather-pouring", false],
  skipped_service: ["service_run", "mdi:wrench-clock", false],
  refused_runtime_cap: ["safety_limit", "mdi:alert-outline", true],
  refused_deep_soak_cap: ["safety_limit", "mdi:alert-outline", true],
  refused_daily_cap: ["safety_limit", "mdi:alert-outline", true],
  interrupted: ["stopped", "mdi:alert-circle-outline", true],
  next: ["scheduled", "mdi:calendar-clock", false],
  next_deep_soak: ["scheduled", "mdi:calendar-clock", false],
  first_run: ["scheduled", "mdi:calendar-clock", false],
  idle: ["nothing", "mdi:calendar-blank-outline", false],
  waiting_frost: ["frost_wait", "mdi:snowflake", false],
  skipped_frost: ["frost_skip", "mdi:snowflake-alert", false],
  waiting_deep_soak: ["deep_soak_first", "mdi:waves", false],
};

// The plant preset chosen at setup -> the zone's default icon.
const PLANT_ICONS = {
  tomatoes: "mdi:food-apple",
  chilis: "mdi:chili-hot",
  leafy_vegetables: "mdi:leaf",
  herbs: "mdi:sprout",
  strawberries: "mdi:fruit-cherries",
  flowers: "mdi:flower",
  lawn: "mdi:grass",
  shrubs: "mdi:leaf-maple",
  young_tree: "mdi:sprout-outline",
  fruit_tree: "mdi:tree",
};
const DEFAULT_ZONE_ICON = "mdi:sprinkler-variant";

function allZones(hass) {
  // Every ZoneFlow zone: the device of each zone's Status sensor.
  const zones = [];
  for (const entry of Object.values(hass.entities || {})) {
    if (entry.platform !== "zoneflow" || entry.translation_key !== "status" || !entry.device_id) continue;
    if (!entry.entity_id.startsWith("sensor.")) continue;
    const device = hass.devices?.[entry.device_id];
    zones.push({
      device_id: entry.device_id,
      name: device?.name_by_user || device?.name || entry.entity_id,
      status: entry.entity_id,
    });
  }
  return zones;
}

function formatNext(hass, iso) {
  if (!iso) return "—";
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "—";
  const lang = hass.locale?.language || hass.language || "en";
  const timeZone = hass.locale?.time_zone === "local" ? undefined : hass.config?.time_zone;
  const soon = when.getTime() - Date.now() < 6 * 86400 * 1000;
  // Home Assistant's own 12/24-hour setting (profile), else the language's.
  const hour12 = { 12: true, 24: false }[hass.locale?.time_format];
  const options = soon
    ? { weekday: "short", hour: "numeric", minute: "2-digit", hour12 }
    : { weekday: "short", day: "numeric", month: "short" };
  try {
    return new Intl.DateTimeFormat(lang, { ...options, timeZone }).format(when);
  } catch (err) {
    return new Intl.DateTimeFormat(undefined, options).format(when);
  }
}

function formatDay(hass, isoDate) {
  // "2026-10-12" (a date sensor) -> "Mon 12 Oct" in the user's language.
  const [y, m, d] = String(isoDate).split("-").map(Number);
  if (!y || !m || !d) return String(isoDate);
  const lang = hass.locale?.language || hass.language || "en";
  const options = { weekday: "short", day: "numeric", month: "short" };
  try {
    return new Intl.DateTimeFormat(lang, { ...options, timeZone: "UTC" }).format(new Date(Date.UTC(y, m - 1, d)));
  } catch (err) {
    return new Intl.DateTimeFormat(undefined, { ...options, timeZone: "UTC" }).format(new Date(Date.UTC(y, m - 1, d)));
  }
}

function formatState(hass, stateObj) {
  if (!stateObj || ["unknown", "unavailable"].includes(stateObj.state)) return "—";
  if (typeof hass.formatEntityState === "function") return hass.formatEntityState(stateObj);
  const unit = stateObj.attributes?.unit_of_measurement;
  return unit ? `${stateObj.state} ${unit}` : stateObj.state;
}

class ZoneFlowOverviewCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("zoneflow-overview-card-editor");
  }

  static getStubConfig() {
    return { sort: "name" };
  }

  setConfig(config) {
    this._config = { sort: "name", icons: {}, ...(config || {}) };
    this._signature = undefined;
    this._open = this._open || new Set();
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 2 + allZones(this._hass || {}).length;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  _zones() {
    const hass = this._hass;
    const zones = allZones(hass).map((zone) => {
      const status = hass.states[zone.status];
      const keyed = zoneEntities(hass, zone.device_id);
      const measured = keyed["sensor.last_cycle_water_liters"];
      const estimate = keyed["sensor.last_water_delivered"];
      const last = measured && !measured.hidden ? measured.entity_id : estimate?.entity_id;
      const button = keyed["button.run_routine"]?.entity_id;
      const plant = status?.attributes?.plant;
      const feed = hass.states[keyed["sensor.next_fertilizing"]?.entity_id];
      return {
        ...zone,
        icon: this._config.icons?.[zone.device_id] || PLANT_ICONS[plant] || DEFAULT_ZONE_ICON,
        code: status?.attributes?.code,
        text: status?.state,
        next: status?.attributes?.next_watering,
        last,
        button,
        feed: feed && !["unknown", "unavailable"].includes(feed.state) ? feed.state : null,
        feedDue: Boolean(feed?.attributes?.due),
      };
    });
    const byName = (a, b) => a.name.localeCompare(b.name, hass.locale?.language);
    if (this._config.sort === "next") {
      const rank = (z) => (z.code === "paused" || !z.next ? Infinity : new Date(z.next).getTime());
      zones.sort((a, b) => rank(a) - rank(b) || byName(a, b));
    } else {
      zones.sort(byName);
    }
    return zones;
  }

  _render() {
    if (!this._config || !this._hass) return;
    const zones = this._zones();
    const signature = JSON.stringify([
      zones.map((z) => [z.device_id, z.name, z.icon, z.last, z.button]),
      this._config.sort === "next" ? zones.map((z) => z.device_id) : null,
      this._hass.locale?.language,
      this._config.title,
      this._config.show_add,
      !!this._hass.user?.is_admin,
    ]);
    if (signature !== this._signature) {
      this._signature = signature;
      this._build(zones);
    }
    this._update(zones);
  }

  _build(zones) {
    const hass = this._hass;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const root = this.shadowRoot;
    root.innerHTML = "";
    const style = document.createElement("style");
    style.textContent = `
      ha-card { display: block; container-type: inline-size; }
      .title { font-size: 1.25em; font-weight: 500; padding: 16px 16px 8px; }
      .grid { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(0, 1.5fr) minmax(0, 1.15fr) minmax(0, 0.75fr) 48px;
        align-items: center; column-gap: 8px; padding: 0 8px 0 16px; }
      .head { color: var(--secondary-text-color); font-size: 0.8em; text-transform: uppercase; letter-spacing: 0.04em;
        padding-bottom: 6px; margin: 0 12px; }
      /* Each zone its own tile, a little apart from the next. */
      .zone { margin: 0 12px 8px; border: 1px solid var(--divider-color); border-radius: 12px; overflow: hidden;
        background: var(--card-background-color, transparent); }
      .add { display: flex; align-items: center; justify-content: center; gap: 8px; width: calc(100% - 24px);
        margin: 4px 12px 12px; padding: 10px; border: 1px dashed var(--divider-color); border-radius: 12px;
        background: none; color: var(--primary-color); font: inherit; font-weight: 500; cursor: pointer; }
      .add:hover { border-color: var(--primary-color); background: var(--secondary-background-color); }
      .row { min-height: 52px; cursor: pointer; }
      .row:hover, .row[aria-expanded="true"] { background: var(--secondary-background-color); }
      .row:focus-visible { outline: 2px solid var(--primary-color); outline-offset: -2px; }
      .name { display: flex; align-items: center; gap: 10px; font-weight: 500; min-width: 0; }
      .name span, .status span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .name ha-icon { color: var(--state-icon-color, var(--primary-color)); flex: none; }
      .names { display: flex; flex-direction: column; min-width: 0; }
      .feed { display: flex; align-items: center; gap: 3px; font-weight: 400; color: var(--secondary-text-color); }
      .feed[hidden] { display: none; }
      .feed ha-icon { --mdc-icon-size: 14px; color: inherit; }
      .feed.due { color: var(--warning-color, #ff9800); font-weight: 500; }
      .status { display: flex; align-items: center; gap: 6px; min-width: 0; color: var(--primary-text-color); }
      .status ha-icon { --mdc-icon-size: 18px; flex: none; color: var(--secondary-text-color); }
      .status.warn, .status.warn ha-icon { color: var(--warning-color, #ff9800); }
      .next, .last { color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .action ha-icon-button { color: var(--primary-color); }
      .action ha-icon-button[disabled] { color: var(--disabled-text-color); }
      .details { padding: 0 8px 8px; }
      .empty { padding: 4px 16px 12px; color: var(--secondary-text-color); }
      /* Phones: two lines per zone -- the name, then status and next. */
      @container (max-width: 480px) {
        .head { display: none; }
        .row { grid-template-columns: minmax(0, 1fr) auto 44px;
          grid-template-areas: "name name action" "status next action"; row-gap: 2px; padding-top: 8px; padding-bottom: 8px; }
        .row .name { grid-area: name; }
        .row .status { grid-area: status; font-size: 0.9em; }
        .row .next { grid-area: next; font-size: 0.9em; }
        .row .last { display: none; }
        .row .action { grid-area: action; }
      }
    `;
    root.appendChild(style);
    const card = document.createElement("ha-card");
    root.appendChild(card);
    const tr = (key) => t(hass, `overview.${key}`);
    const title = document.createElement("div");
    title.className = "title";
    title.textContent = this._config.title || tr("title");
    card.appendChild(title);
    this._rows = {};
    const addButton = () => {
      // Adding a zone is ZoneFlow's normal setup (admins only, like any
      // integration).
      if (!hass.user?.is_admin || this._config.show_add === false) return;
      const add = document.createElement("button");
      add.className = "add";
      const icon = document.createElement("ha-icon");
      icon.setAttribute("icon", "mdi:plus");
      add.append(icon, document.createTextNode(tr("add_zone")));
      add.addEventListener("click", () => {
        history.pushState(null, "", "/config/integrations/dashboard/add?domain=zoneflow");
        window.dispatchEvent(new CustomEvent("location-changed"));
      });
      card.appendChild(add);
    };
    if (!zones.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = tr("no_zones");
      card.appendChild(empty);
      addButton();
      return;
    }
    const head = document.createElement("div");
    head.className = "grid head";
    for (const [key, cls] of [["zone", ""], ["status", ""], ["next", "next"], ["last", "last"], ["", ""]]) {
      const cell = document.createElement("div");
      cell.className = cls;
      cell.textContent = key ? tr(key) : "";
      head.appendChild(cell);
    }
    card.appendChild(head);

    for (const zone of zones) {
      const wrap = document.createElement("div");
      wrap.className = "zone";
      const row = document.createElement("div");
      row.className = "grid row";
      row.tabIndex = 0;
      row.setAttribute("role", "button");
      const name = document.createElement("div");
      name.className = "name";
      const icon = document.createElement("ha-icon");
      icon.setAttribute("icon", zone.icon);
      const label = document.createElement("span");
      label.textContent = zone.name;
      // Next fertilizing, small under the name (once a feed is recorded).
      const feed = document.createElement("small");
      feed.className = "feed";
      const feedIcon = document.createElement("ha-icon");
      feedIcon.setAttribute("icon", "mdi:sprout");
      const feedText = document.createElement("span");
      feed.append(feedIcon, feedText);
      const names = document.createElement("div");
      names.className = "names";
      names.append(label, feed);
      name.append(icon, names);
      const status = document.createElement("div");
      status.className = "status";
      const statusIcon = document.createElement("ha-icon");
      const statusText = document.createElement("span");
      status.append(statusIcon, statusText);
      const next = document.createElement("div");
      next.className = "next";
      const last = document.createElement("div");
      last.className = "last";
      const action = document.createElement("div");
      action.className = "action";
      const water = document.createElement("ha-icon-button");
      water.label = t(hass, "water_now");
      water.title = t(hass, "water_now");
      const waterIcon = document.createElement("ha-icon");
      waterIcon.setAttribute("icon", "mdi:water");
      water.appendChild(waterIcon);
      water.addEventListener("click", (ev) => {
        ev.stopPropagation();
        this._waterNow(zone);
      });
      action.appendChild(water);
      row.append(name, status, next, last, action);
      const details = document.createElement("div");
      details.className = "details";
      details.hidden = !this._open.has(zone.device_id);
      const toggle = () => {
        const opening = details.hidden;
        details.hidden = !opening;
        row.setAttribute("aria-expanded", String(opening));
        if (opening) {
          this._open.add(zone.device_id);
          this._fillDetails(zone, details);
        } else {
          this._open.delete(zone.device_id);
        }
      };
      row.addEventListener("click", toggle);
      row.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          toggle();
        }
      });
      row.setAttribute("aria-expanded", String(!details.hidden));
      if (!details.hidden) this._fillDetails(zone, details);
      wrap.append(row, details);
      card.appendChild(wrap);
      this._rows[zone.device_id] = { status, statusIcon, statusText, next, last, water, details, feed, feedText };
    }
    addButton();
  }

  _fillDetails(zone, details) {
    if (details.firstChild) {
      const inner = details.querySelector("zoneflow-card");
      if (inner) inner.hass = this._hass;
      return;
    }
    const inner = document.createElement("zoneflow-card");
    inner.setConfig({ device_id: zone.device_id, show_journal: false, show_settings: true, embedded: true });
    inner.hass = this._hass;
    details.append(inner);
  }

  _update(zones) {
    const hass = this._hass;
    for (const zone of zones) {
      const row = this._rows?.[zone.device_id];
      if (!row) continue;
      const [labelKey, icon, warn] = STATUS_LABELS[zone.code] || [null, "mdi:help-circle-outline", false];
      row.statusIcon.setAttribute("icon", icon);
      row.statusText.textContent = labelKey ? t(hass, `overview.labels.${labelKey}`) : zone.text || "—";
      row.status.title = zone.text || "";
      row.status.classList.toggle("warn", warn);
      row.next.textContent = zone.code === "paused" ? "—" : formatNext(hass, zone.next);
      row.last.textContent = zone.last ? formatState(hass, hass.states[zone.last]) : "—";
      row.water.disabled = !zone.button || zone.code === "paused";
      row.feed.hidden = !zone.feed;
      row.feed.classList.toggle("due", zone.feedDue);
      row.feedText.textContent = zone.feed ? (zone.feedDue ? t(hass, "overview.feed_due") : formatDay(hass, zone.feed)) : "";
      row.feed.title = zone.feed ? `${t(hass, "overview.next_feed")}: ${formatDay(hass, zone.feed)}` : "";
      if (!row.details.hidden) {
        const inner = row.details.querySelector("zoneflow-card");
        if (inner) inner.hass = hass;
      }
    }
  }

  _toast(message) {
    this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true }));
  }

  async _waterNow(zone) {
    if (!zone.button) return;
    try {
      await this._hass.callService("button", "press", { entity_id: zone.button });
    } catch (err) {
      // e.g. the zone is paused: say why instead of failing silently.
      this._toast(err?.message || String(err));
      return;
    }
    // "Water now" still goes through the checks (not due, soil wet...):
    // a moment later, say what the zone made of it.
    setTimeout(() => {
      const status = this._hass?.states[zone.status];
      if (status) this._toast(`${zone.name}: ${status.state}`);
    }, 1500);
  }
}

class ZoneFlowOverviewCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { sort: "name", icons: {}, ...(config || {}) };
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._render();
    else if (this._form) this._form.hass = hass;
  }

  _render() {
    if (!this._hass || !this._config) return;
    const hass = this._hass;
    const tr = (key) => t(hass, `overview.${key}`);
    const zones = allZones(hass).sort((a, b) => a.name.localeCompare(b.name));
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", (ev) => {
        const value = ev.detail.value;
        const icons = {};
        for (const zone of allZones(this._hass)) {
          const icon = value[`icon_${zone.device_id}`];
          if (icon) icons[zone.device_id] = icon;
        }
        const config = { ...this._config, sort: value.sort || "name", icons };
        if (value.title) config.title = value.title;
        else delete config.title;
        if (!Object.keys(icons).length) delete config.icons;
        if (value.show_add === false) config.show_add = false;
        else delete config.show_add;
        this._config = config;
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    const labels = { title: tr("title"), sort: tr("sort"), show_add: tr("show_add") };
    const data = {
      title: this._config.title || "",
      sort: this._config.sort || "name",
      show_add: this._config.show_add !== false,
    };
    const iconFields = zones.map((zone) => {
      labels[`icon_${zone.device_id}`] = zone.name;
      data[`icon_${zone.device_id}`] = this._config.icons?.[zone.device_id] || "";
      const plant = hass.states[zone.status]?.attributes?.plant;
      return {
        name: `icon_${zone.device_id}`,
        selector: { icon: { placeholder: PLANT_ICONS[plant] || DEFAULT_ZONE_ICON } },
      };
    });
    this._form.hass = hass;
    this._form.computeLabel = (schema) => labels[schema.name] || schema.title || schema.name;
    this._form.schema = [
      { name: "title", selector: { text: {} } },
      {
        name: "sort",
        selector: {
          select: {
            mode: "dropdown",
            options: [
              { value: "name", label: tr("sort_name") },
              { value: "next", label: tr("sort_next") },
            ],
          },
        },
      },
      ...(iconFields.length
        ? [{ type: "expandable", name: "", title: tr("icons"), flatten: true, schema: iconFields }]
        : []),
      { name: "show_add", selector: { boolean: {} } },
    ];
    this._form.data = data;
  }
}

// Defined as soon as this file loads -- and again if Home Assistant's
// frontend replaces the page's custom-element registry afterwards (it can
// install a scoped-registry polyfill after early-loaded modules like this
// one have run; definitions made before that are then invisible to it).
const ELEMENTS = [
  ["zoneflow-card", ZoneFlowCard],
  ["zoneflow-card-editor", ZoneFlowCardEditor],
  ["zoneflow-overview-card", ZoneFlowOverviewCard],
  ["zoneflow-overview-card-editor", ZoneFlowOverviewCardEditor],
];
function defineElements() {
  for (const [tag, cls] of ELEMENTS) {
    try {
      if (!window.customElements.get(tag)) window.customElements.define(tag, cls);
    } catch (err) {
      // Already known to the underlying registry under this tag: nothing to do.
    }
  }
}
defineElements();
for (const delay of [0, 250, 1000, 3000, 10000]) setTimeout(defineElements, delay);
window.addEventListener("load", defineElements);
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "zoneflow-overview-card")) {
  window.customCards.push({
    type: "zoneflow-overview-card",
    name: "ZoneFlow overview",
    description: "All ZoneFlow zones in one table: status, next and last watering, water now. Click a zone for its full card.",
    preview: true,
    documentationURL: "https://github.com/Dreamer41/ha-smart-irrigation#dashboard",
  });
}
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
