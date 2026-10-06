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
 * Also here: zoneflow-overview-card, every zone in one table (further down),
 * and a dashboard strategy that builds a whole dashboard from the zones.
 */
const CARD_VERSION = "1.6.5";

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
      "water_use": "Water use estimate",
      "water_use_note": "Only used to work out litres for the water-use numbers. It does not change when or how long the zone waters. Leave at 0 if you do not know it.",
      "rain": "Rain, forecast and frost",
      "deep_soak": "Deep soak",
      "soil": "Soil",
      "growth": "Growth",
      "deficit": "Deficit mode",
      "history": "History",
      "safety": "Safety limits and pump",
      "notifications": "Notifications",
      "more": "More",
      "climate": "Climate control",
      "misting": "Misting",
      "garden": "Garden area"
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
      "feed_due": "Fertilize now",
      "other_area": "Other"
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
      "rain_eff_high": "Share of heavy rain that actually reaches the roots. The rest runs off or evaporates.",
      "heat_temp": "The heater switches on when the inside temperature falls below this, and off again a little above it (see Climate Hysteresis).",
      "vent_temp": "Vents open when the inside temperature reaches this, and only when the outside air is cooler than inside.",
      "fan_temp": "Fans switch on at this inside temperature (at or above the vent temperature), and only when the outside air is cooler than inside.",
      "climate_hysteresis": "The gap between a device switching on and off, so it doesn't flick on and off around one temperature.",
      "outside_margin": "Ventilation starts only when the outside air is at least this much cooler than inside, so it never pulls in hotter air.",
      "max_humidity": "Vents and fans also run when the inside humidity is above this, unless it is cold.",
      "mist_temp": "Misting can start when the inside temperature is at or above this.",
      "mist_min_humidity": "Misting can start when the inside humidity falls to this or lower.",
      "mist_stop_humidity": "Misting never runs when the inside humidity is at or above this.",
      "mist_min_temp": "No misting below this inside temperature.",
      "mist_light_level": "Misting can start when the light reading reaches this level (needs a light sensor).",
      "mist_on_seconds": "How long each misting pulse lasts.",
      "mist_off_seconds": "The rest between misting pulses.",
      "max_mist_minutes_per_hour": "A hard limit on misting in any 60 minutes. A mister switched on by hand also goes off after this long.",
      "vent_open_pct": "How far a vent opens (for vents that can be set to a position).",
      "auto_resume": "On: a device you switch by hand goes back to automatic after Auto Resume After. Off: it stays as you left it until you press Resume automatic.",
      "auto_resume_hours": "How long a device you switched by hand is left alone before ZoneFlow takes it back (while Auto Resume is on).",
      "manual_rain_mm": "Rain you read from a simple rain gauge. Press Add rain to record it; the amount goes back to 0.",
      "zone_flow_l_min": "What the whole zone gives per minute (heads x flow per head). Used only to estimate litres; it does not change when or how much the zone waters. Leave 0 if you do not know it.",
      "sensor_offline_hours": "A sensor that sends nothing for this many hours counts as offline, and the climate control goes to its failsafe. Raise it if a steady sensor causes false warnings.",
      "ventilation_failsafe": "What vents and fans do when no inside temperature sensor is working. Misters always go off.",
      "heater_failsafe": "What the heater does when no inside temperature sensor is working. It never runs non-stop without a sensor.",
      "misting_trigger": "What starts misting: any of the triggers, or only temperature, humidity or light."
    },
    "close": "Close",
    "device_page": "Open the device page",
    "fertilized": "Fertilized",
    "mark_watered": "Mark watered",
    "add_rain": "Add rain",
    "resume_automatic": "Resume automatic",
    "crops": "Crops",
    "in_greenhouse": "In greenhouse",
    "garden": {
      "none": "No area",
      "new": "New area…",
      "name": "Area name"
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
      "water_use": "Wasserverbrauchsschätzung",
      "water_use_note": "Wird nur verwendet, um Liter für die Wasserverbrauchswerte zu berechnen. Es ändert nicht, wann oder wie lange die Zone bewässert. Auf 0 belassen, wenn unbekannt.",
      "rain": "Regen, Vorhersage und Frost",
      "deep_soak": "Tiefenbewässerung",
      "soil": "Boden",
      "growth": "Wachstum",
      "deficit": "Defizitmodus",
      "history": "Verlauf",
      "safety": "Sicherheitslimits und Pumpe",
      "notifications": "Benachrichtigungen",
      "more": "Mehr",
      "climate": "Klimasteuerung",
      "misting": "Vernebelung",
      "garden": "Gartenbereich"
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
      "feed_due": "Jetzt düngen",
      "other_area": "Sonstige"
    },
    "close": "Schließen",
    "device_page": "Geräteseite öffnen",
    "fertilized": "Gedüngt",
    "mark_watered": "Als bewässert markieren",
    "add_rain": "Regen hinzufügen",
    "resume_automatic": "Automatik fortsetzen",
    "crops": "Kulturen",
    "in_greenhouse": "Im Gewächshaus",
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
      "rain_eff_high": "Anteil starken Regens, der die Wurzeln erreicht. Der Rest verdunstet oder fließt oberflächlich ab.",
      "heat_temp": "Die Heizung schaltet sich ein, wenn die Innentemperatur unter diesen Wert fällt, und etwas darüber wieder aus (siehe Klima-Hysterese).",
      "vent_temp": "Lüftungen öffnen sich, wenn die Innentemperatur diesen Wert erreicht und die Außenluft kühler ist als innen.",
      "fan_temp": "Lüfter schalten sich bei dieser Innentemperatur ein (bei oder über der Lüftungstemperatur) und nur, wenn die Außenluft kühler ist als innen.",
      "climate_hysteresis": "Die Spanne zwischen Ein- und Ausschalten eines Geräts, damit es nicht ständig um eine Temperatur herum schaltet.",
      "outside_margin": "Die Belüftung startet nur, wenn die Außenluft mindestens um diesen Wert kühler ist als innen, damit nie heißere Luft angesaugt wird.",
      "max_humidity": "Lüfter und Lüftungen laufen auch, wenn die Innenfeuchtigkeit über diesem Wert liegt, außer es ist kalt.",
      "mist_temp": "Die Vernebelung kann starten, wenn die Innentemperatur diesen Wert erreicht oder überschreitet.",
      "mist_min_humidity": "Die Vernebelung kann starten, wenn die Innenfeuchtigkeit auf diesen Wert oder darunter fällt.",
      "mist_stop_humidity": "Die Vernebelung läuft niemals, wenn die Innenfeuchtigkeit diesen Wert erreicht oder überschreitet.",
      "mist_min_temp": "Keine Vernebelung unterhalb dieser Innentemperatur.",
      "mist_light_level": "Die Vernebelung kann starten, wenn der Lichtwert diesen Pegel erreicht (erfordert einen Lichtsensor).",
      "mist_on_seconds": "Wie lange jeder Vernebelungsimpuls dauert.",
      "mist_off_seconds": "Die Pause zwischen den Vernebelungsimpulsen.",
      "max_mist_minutes_per_hour": "Eine feste Obergrenze für die Vernebelung innerhalb von 60 Minuten. Ein manuell eingeschalteter Vernebler schaltet sich nach dieser Zeit ebenfalls aus.",
      "vent_open_pct": "Wie weit eine Lüftung öffnet (für Lüftungen, die auf eine bestimmte Position eingestellt werden können).",
      "auto_resume": "Ein: Ein manuell geschaltetes Gerät kehrt nach Automatische Fortsetzung nach wieder zur Automatik zurück. Aus: Es bleibt so eingestellt, bis Sie Automatik fortsetzen drücken.",
      "auto_resume_hours": "Wie lange ein manuell geschaltetes Gerät unverändert bleibt, bevor ZoneFlow wieder die Steuerung übernimmt (wenn Automatische Fortsetzung aktiv ist).",
      "manual_rain_mm": "Regenmenge von einem einfachen Regenmesser. Drücken Sie Regen hinzufügen zum Speichern; der Wert wird danach auf 0 zurückgesetzt.",
      "zone_flow_l_min": "Was die gesamte Zone pro Minute liefert (Tropfer x Durchfluss pro Tropfer). Wird nur zur Schätzung der Liter verwendet; es ändert nicht, wann oder wie viel die Zone bewässert. Belassen Sie es auf 0, wenn Sie es nicht wissen.",
      "sensor_offline_hours": "Ein Sensor, der so viele Stunden nichts sendet, gilt als offline, und die Klimasteuerung geht in den Notbetrieb. Erhöhen Sie den Wert, wenn ein gleichmäßig messender Sensor Fehlalarme auslöst.",
      "ventilation_failsafe": "Was Lüftungen und Lüfter tun, wenn kein Innen-Temperatursensor funktioniert. Vernebler schalten sich immer aus.",
      "heater_failsafe": "Was die Heizung tut, wenn kein Innen-Temperatursensor funktioniert. Ohne Sensor läuft sie niemals ununterbrochen.",
      "misting_trigger": "Was die Vernebelung startet: jeder beliebige Auslöser oder nur Temperatur, Feuchtigkeit oder Licht."
    },
    "garden": {
      "none": "Kein Bereich",
      "new": "Neuer Bereich …",
      "name": "Name des Bereichs"
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
      "water_use": "Estimación del consumo de agua",
      "water_use_note": "Solo se usa para calcular los litros de las cifras de consumo de agua. No cambia cuándo ni cuánto tiempo riega la zona. Déjalo en 0 si no lo sabes.",
      "rain": "Lluvia, previsión y heladas",
      "deep_soak": "Riego profundo",
      "soil": "Suelo",
      "growth": "Crecimiento",
      "deficit": "Modo déficit",
      "history": "Historial",
      "safety": "Límites de seguridad y bomba",
      "notifications": "Notificaciones",
      "more": "Más",
      "climate": "Control de clima",
      "misting": "Nebulización",
      "garden": "Área del jardín"
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
      "feed_due": "Abonar ya",
      "other_area": "Otras"
    },
    "close": "Cerrar",
    "device_page": "Abrir la página del dispositivo",
    "fertilized": "Abonado",
    "mark_watered": "Marcar como regado",
    "add_rain": "Añadir lluvia",
    "resume_automatic": "Reanudar automático",
    "crops": "Cultivos",
    "in_greenhouse": "En invernadero",
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
      "rain_eff_high": "Proporción de lluvia intensa que llega realmente a las raíces. El resto se evapora o se pierde por escorrentía.",
      "heat_temp": "El calefactor se enciende cuando la temperatura interior cae por debajo de esto, y se apaga un poco por encima (consulte Histéresis de clima).",
      "vent_temp": "Las rejillas se abren cuando la temperatura interior alcanza este valor, y solo si el aire exterior es más frío que el interior.",
      "fan_temp": "Los ventiladores se encienden a esta temperatura interior (a la par o por encima de la temperatura de las rejillas), y solo si el aire exterior es más frío que el interior.",
      "climate_hysteresis": "El desfase entre el encendido y apagado de un dispositivo para evitar interrupciones constantes cerca de una misma temperatura.",
      "outside_margin": "La ventilación solo comienza si el aire exterior está al menos así de más frío que el interior, para no introducir aire más caliente.",
      "max_humidity": "Los ventiladores y rejillas también funcionan cuando la humedad interior supera este límite, a menos que haga frío.",
      "mist_temp": "La nebulización puede empezar cuando la temperatura interior está en o por encima de este valor.",
      "mist_min_humidity": "La nebulización puede empezar cuando la humedad interior desciende a este valor o menos.",
      "mist_stop_humidity": "La nebulización nunca se activa si la humedad interior alcanza o supera este límite.",
      "mist_min_temp": "Sin nebulización por debajo de esta temperatura interior.",
      "mist_light_level": "La nebulización puede empezar cuando el nivel de luz alcance este valor (requiere un sensor de luz).",
      "mist_on_seconds": "Duración de cada pulso de nebulización.",
      "mist_off_seconds": "Pausa de reposo entre pulsos de nebulización.",
      "max_mist_minutes_per_hour": "Límite máximo de nebulización en un periodo de 60 minutos. Un nebulizador encendido manualmente se apaga también tras este periodo.",
      "vent_open_pct": "Cuánto abre una rejilla (para rejillas con posición regulable).",
      "auto_resume": "Activado: un dispositivo cambiado a mano vuelve a automático tras Reanudación automática tras. Desactivado: permanece como lo dejaste hasta que pulses Reanudar automático.",
      "auto_resume_hours": "Tiempo que un dispositivo cambiado a mano se deja sin modificar antes de que ZoneFlow retome el control (mientras la Reanudación automática esté activada).",
      "manual_rain_mm": "Lluvia leída en un pluviómetro manual. Pulsa Añadir lluvia para registrarla; la cantidad volverá a 0.",
      "zone_flow_l_min": "Lo que da toda la zona por minuto (emisores x caudal por emisor). Se usa solo para estimar litros; no cambia cuándo ni cuánto riega la zona. Déjelo en 0 si no lo sabe.",
      "sensor_offline_hours": "Un sensor que no envía nada durante estas horas se considera sin conexión y el control del clima pasa a su modo de seguridad. Auméntalo si un sensor estable provoca avisos falsos.",
      "ventilation_failsafe": "Qué hacen las rejillas y ventiladores cuando no funciona ningún sensor de temperatura interior. Los nebulizadores siempre se apagan.",
      "heater_failsafe": "Qué hace el calefactor cuando no funciona ningún sensor de temperatura interior. Nunca funciona de forma continua sin un sensor.",
      "misting_trigger": "Qué inicia la nebulización: cualquiera de los activadores, o solo la temperatura, humedad o luz."
    },
    "garden": {
      "none": "Sin área",
      "new": "Nueva área…",
      "name": "Nombre del área"
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
      "water_use": "Veden käytön arvio",
      "water_use_note": "Käytetään vain litrojen laskemiseen veden käytön luvuissa. Ei muuta sitä, milloin tai kuinka kauan vyöhyke kastelee. Jätä 0, jos et tiedä.",
      "rain": "Sade, ennuste ja halla",
      "deep_soak": "Syväkastelu",
      "soil": "Maa",
      "growth": "Kasvu",
      "deficit": "Vajaakastelu",
      "history": "Historia",
      "safety": "Turvarajat ja pumppu",
      "notifications": "Ilmoitukset",
      "more": "Lisää",
      "climate": "Ilmastonsäätö",
      "misting": "Sumutus",
      "garden": "Puutarhan alue"
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
      "feed_due": "Lannoita nyt",
      "other_area": "Muut"
    },
    "close": "Sulje",
    "device_page": "Avaa laitesivu",
    "fertilized": "Lannoita",
    "mark_watered": "Merkitse kastelluksi",
    "add_rain": "Lisää sade",
    "resume_automatic": "Palauta automatiikka",
    "crops": "Kasvit",
    "in_greenhouse": "Kasvihuoneessa",
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
      "rain_eff_high": "Runsaan sateen osuus, joka todellisuudessa saavuttaa juuret. Loput haihtuu tai valuu pois.",
      "heat_temp": "Lämmitin kytkeytyy päälle, kun sisälämpötila laskee tämän alle, ja sammuu hieman sen yläpuolella (katso Ilmastosäädön hystereesi).",
      "vent_temp": "Tuuletusluukut avautuvat, kun sisälämpötila saavuttaa tämän arvon, ja vain silloin, kun ulkoilma on sisäilmaa viileämpää.",
      "fan_temp": "Tuulettimet kytkeytyvät päälle tässä sisälämpötilassa (tuuletusluukun lämpötilassa tai sen yläpuolella) ja vain silloin, kun ulkoilma on sisäilmaa viileämpää.",
      "climate_hysteresis": "Ero laitteen kytkeytymisen ja sammumisen välillä, jotta se ei edestakaisin kytkeydy tietyn lämpötilan ympärillä.",
      "outside_margin": "Tuuletus alkaa vasta, kun ulkoilma on vähintään näin paljon sisäilmaa viileämpää, jottei se koskaan vedä sisään kuumempaa ilmaa.",
      "max_humidity": "Tuulettimet ja tuuletusluukut toimivat myös silloin, kun sisäilman kosteus ylittää tämän, ellei ole kylmä.",
      "mist_temp": "Sumutus voi alkaa, kun sisälämpötila on tämä tai enemmän.",
      "mist_min_humidity": "Sumutus voi alkaa, kun sisäilman kosteus laskee tähän tai alemmas.",
      "mist_stop_humidity": "Sumutus ei koskaan pyöri, kun sisäilman kosteus on tämä tai enemmän.",
      "mist_min_temp": "Ei sumutusta tämän sisälämpötilan alapuolella.",
      "mist_light_level": "Sumutus voi alkaa, kun valoisuuslukema saavuttaa tämän tason (tarvitsee valoisuusanturin).",
      "mist_on_seconds": "Kuinka kauan kukin sumutuspulssi kestää.",
      "mist_off_seconds": "Tauko sumutuspulssien välillä.",
      "max_mist_minutes_per_hour": "Tiukka enimmäisraja sumutukselle minkä tahansa 60 minuutin jakson aikana. Käsin päälle kytketty sumutin sammuu myös tämän ajan kuluttua.",
      "vent_open_pct": "Kuinka paljon tuuletusluukku avautuu (luukuille, jotka voidaan asettaa tiettyyn asentoon).",
      "auto_resume": "Päällä: käsin kytketty laite palaa automatiikalle Automaattipaluun viiveen jälkeen. Pois: laite pysyy siinä tilassa, jonka jätit, kunnes painat Palauta automatiikka.",
      "auto_resume_hours": "Kuinka kauan käsin kytkettyä laitetta ei ohjata, ennen kuin ZoneFlow ottaa sen takaisin (kun Automaattipaluu on päällä).",
      "manual_rain_mm": "Yksinkertaisesta sademittarista lukemasi sademäärä. Tallenna se painamalla Lisää sade; määrä nollautuu.",
      "zone_flow_l_min": "Mitä koko vyöhyke antaa minuutissa (suuttimet x yhden suuttimen virtaama). Käytetään vain litrojen arviointiin; ei muuta sitä, milloin tai kuinka paljon vyöhyke kastelee. Jätä 0, jos et tiedä.",
      "sensor_offline_hours": "Anturi, joka ei lähetä mitään näin moneen tuntiin, katsotaan poissaolevaksi, ja ilmastonohjaus siirtyy vikatilaan. Nosta arvoa, jos tasaisesti mittaava anturi aiheuttaa vääriä varoituksia.",
      "ventilation_failsafe": "Mitä tuuletusluukut ja tuulettimet tekevät, kun mikään sisälämpötila-anturi ei toimi. Sumuttimet sammuvat aina.",
      "heater_failsafe": "Mitä lämmitin tekee, kun mikään sisälämpötila-anturi ei toimi. Se ei koskaan pyöri taukoamatta ilman anturia.",
      "misting_trigger": "Mikä käynnistää sumutuksen: mikä tahansa käynnistimistä tai vain lämpötila, kosteus tai valoisuus."
    },
    "garden": {
      "none": "Ei aluetta",
      "new": "Uusi alue…",
      "name": "Alueen nimi"
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
      "water_use": "Estimation de la consommation d'eau",
      "water_use_note": "Sert uniquement à calculer les litres des chiffres de consommation d'eau. Cela ne change ni le moment ni la durée de l'arrosage de la zone. Laissez 0 si vous ne le connaissez pas.",
      "rain": "Pluie, prévisions et gel",
      "deep_soak": "Arrosage profond",
      "soil": "Sol",
      "growth": "Croissance",
      "deficit": "Arrosage réduit",
      "history": "Historique",
      "safety": "Limites de sécurité et pompe",
      "notifications": "Notifications",
      "more": "Plus",
      "climate": "Contrôle du climat",
      "misting": "Brumisation",
      "garden": "Partie du jardin"
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
      "feed_due": "Engrais à apporter",
      "other_area": "Autres"
    },
    "close": "Fermer",
    "device_page": "Ouvrir la page de l'appareil",
    "fertilized": "Engrais apporté",
    "mark_watered": "Marquer comme arrosé",
    "add_rain": "Ajouter de la pluie",
    "resume_automatic": "Reprendre en automatique",
    "crops": "Cultures",
    "in_greenhouse": "Dans la serre",
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
      "rain_eff_high": "Proportion de pluie forte atteignant réellement les racines. Le reste s'évapore ou ruisselle.",
      "heat_temp": "Le chauffage s'allume lorsque la température intérieure descend sous ce seuil, et s'éteint un peu au-dessus (voir Hystérésis climatique).",
      "vent_temp": "Les ouvrants s'ouvrent lorsque la température intérieure atteint ce seuil, et uniquement si l'air extérieur est plus frais qu'à l'intérieur.",
      "fan_temp": "Les ventilateurs s'allument à cette température intérieure (égale ou supérieure à la température des ouvrants), et uniquement si l'air extérieur est plus frais qu'à l'intérieur.",
      "climate_hysteresis": "L'écart entre le déclenchement et l'arrêt d'un appareil, pour éviter les oscillations rapides autour de la température consigne.",
      "outside_margin": "La ventilation ne démarre que si l'air extérieur est au moins aussi plus frais que l'intérieur, afin de ne jamais faire entrer d'air plus chaud.",
      "max_humidity": "Les ventilateurs et ouvrants s'activent aussi quand l'humidité intérieure dépasse ce seuil, sauf s'il fait froid.",
      "mist_temp": "La brumisation peut démarrer si la température intérieure est supérieure ou égale à ce seuil.",
      "mist_min_humidity": "La brumisation peut démarrer quand l'humidité intérieure tombe à ce niveau ou en dessous.",
      "mist_stop_humidity": "La brumisation s'arrête systématiquement dès que l'humidité intérieure atteint ou dépasse ce seuil.",
      "mist_min_temp": "Pas de brumisation en dessous de cette température intérieure.",
      "mist_light_level": "La brumisation peut démarrer lorsque la luminosité atteint ce niveau (nécessite un capteur de luminosité).",
      "mist_on_seconds": "Durée de chaque impulsion de brumisation.",
      "mist_off_seconds": "Durée du temps de repos entre deux impulsions de brumisation.",
      "max_mist_minutes_per_hour": "Limite stricte de brumisation sur une période glissante de 60 minutes. Un brumisateur allumé manuellement s'éteint aussi passé ce délai.",
      "vent_open_pct": "Pourcentage d'ouverture de l'ouvrant (pour les ouvrants dont la position est réglable).",
      "auto_resume": "Activé : un appareil basculé manuellement repasse en automatique après Reprise automatique après. Désactivé : il reste en l'état jusqu'à ce que vous appuyiez sur Reprendre en automatique.",
      "auto_resume_hours": "Durée pendant laquelle un appareil basculé manuellement est laissé tel quel avant que ZoneFlow ne en reprenne le contrôle (lorsque la Reprise automatique est activée).",
      "manual_rain_mm": "Pluie relevée sur un pluviomètre manuel. Appuyez sur Ajouter de la pluie pour l'enregistrer ; la valeur repassera à 0.",
      "zone_flow_l_min": "Ce que toute la zone fournit par minute (goutteurs x débit par goutteur). Utilisé uniquement pour estimer les litres ; cela ne change pas le moment ni la quantité d'eau arrosée. Laissez à 0 si vous ne le savez pas.",
      "sensor_offline_hours": "Un capteur qui n'envoie rien pendant ce nombre d'heures est considéré hors ligne, et le contrôle climatique passe en mode de sécurité. Augmentez cette valeur si un capteur stable provoque de fausses alertes.",
      "ventilation_failsafe": "Comportement des ouvrants et ventilateurs en cas de panne du capteur de température intérieure. Les brumisateurs s'éteignent toujours.",
      "heater_failsafe": "Comportement du chauffage en cas de panne du capteur de température intérieure. Il ne fonctionne jamais en continu sans capteur.",
      "misting_trigger": "Conditions de démarrage de la brumisation : n'importe quel déclencheur, ou exclusivement température, humidité ou luminosité."
    },
    "garden": {
      "none": "Aucune partie",
      "new": "Nouvelle partie…",
      "name": "Nom de la partie"
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
      "water_use": "Stima dell'uso dell'acqua",
      "water_use_note": "Serve solo a calcolare i litri per i dati sull'uso dell'acqua. Non cambia quando né per quanto tempo la zona irriga. Lascia 0 se non lo conosci.",
      "rain": "Pioggia, previsioni e gelo",
      "deep_soak": "Irrigazione profonda",
      "soil": "Terreno",
      "growth": "Crescita",
      "deficit": "Modalità deficit",
      "history": "Cronologia",
      "safety": "Limiti di sicurezza e pompa",
      "notifications": "Notifiche",
      "more": "Altro",
      "climate": "Controllo climatico",
      "misting": "Nebulizzazione",
      "garden": "Area del giardino"
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
      "feed_due": "Concima ora",
      "other_area": "Altre"
    },
    "close": "Chiudi",
    "device_page": "Apri la pagina del dispositivo",
    "fertilized": "Concimato",
    "mark_watered": "Segna come annaffiato",
    "add_rain": "Aggiungi pioggia",
    "resume_automatic": "Ripristina automatico",
    "crops": "Colture",
    "in_greenhouse": "In serra",
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
      "rain_eff_high": "Quota di pioggia intensa che raggiunge effettivamente le radici. La parte restante evapora o scivola via per ruscellamento.",
      "heat_temp": "Il riscaldatore si accende quando la temperatura interna scende sotto questo valore e si spegne poco sopra (vedi Isteresi climatica).",
      "vent_temp": "Le aperture si aprono quando la temperatura interna raggiunge questo valore, e solo se l’aria esterna è più fresca di quella interna.",
      "fan_temp": "Le ventole si attivano a questa temperatura interna (pari o superiore a quella delle aperture), e solo se l’aria esterna è più fresca di quella interna.",
      "climate_hysteresis": "Lo scarto tra l’accensione e lo spegnimento di un dispositivo, per evitare continue attivazioni intorno a una singola temperatura.",
      "outside_margin": "La ventilazione si avvia solo se l’aria esterna è più fresca di quella interna di almeno questo valore, evitando di introdurre aria più calda.",
      "max_humidity": "Aperture e ventole si attivano anche quando l’umidità interna supera questo valore, a meno che non faccia freddo.",
      "mist_temp": "La nebulizzazione può avviarsi quando la temperatura interna raggiunge o supera questo valore.",
      "mist_min_humidity": "La nebulizzazione può avviarsi quando l’umidità interna scende a questo valore o al di sotto.",
      "mist_stop_humidity": "La nebulizzazione non si attiva mai se l’umidità interna è pari o superiore a questo valore.",
      "mist_min_temp": "Nessuna nebulizzazione al di sotto di questa temperatura interna.",
      "mist_light_level": "La nebulizzazione può avviarsi quando la luminosità raggiunge questo livello (richiede un sensore di luminosità).",
      "mist_on_seconds": "Durata di ciascun impulso di nebulizzazione.",
      "mist_off_seconds": "Pausa tra gli impulsi di nebulizzazione.",
      "max_mist_minutes_per_hour": "Limite massimo di nebulizzazione in un intervallo di 60 minuti. Anche un nebulizzatore attivato manualmente si spegne dopo questo tempo.",
      "vent_open_pct": "Grado di apertura di una finestra di ventilazione (per aperture posizionabili).",
      "auto_resume": "Attivo: un dispositivo azionato manualmente torna in automatico dopo Ripristino automatico dopo. Disattivo: rimane nello stato impostato finché non premi Ripristina automatico.",
      "auto_resume_hours": "Per quanto tempo un dispositivo azionato manualmente viene lasciato invariato prima che ZoneFlow ne riprenda il controllo (mentre il Ripristino automatico è attivo).",
      "manual_rain_mm": "Pioggia rilevata da un semplice pluviometro. Premi Aggiungi pioggia per registrarla; la quantità tornerà a 0.",
      "zone_flow_l_min": "Quanto eroga l'intera zona al minuto (erogatori x flusso per erogatore). Utilizzato solo per stimare i litri; non modifica quando o quanto la zona irriga. Lascia 0 se non lo conosci.",
      "sensor_offline_hours": "Un sensore che non invia nulla per queste ore è considerato offline e il controllo del clima passa alla modalità di sicurezza. Aumentalo se un sensore stabile causa falsi avvisi.",
      "ventilation_failsafe": "Comportamento di aperture e ventole quando nessun sensore di temperatura interna funziona. I nebulizzatori si spengono sempre.",
      "heater_failsafe": "Comportamento del riscaldatore quando nessun sensore di temperatura interna funziona. Non rimane mai in funzione continua senza sensore.",
      "misting_trigger": "Cosa avvia la nebulizzazione: qualsiasi condizione, oppure solo temperatura, umidità o luminosità."
    },
    "garden": {
      "none": "Nessuna area",
      "new": "Nuova area…",
      "name": "Nome dell'area"
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
      "water_use": "Schatting waterverbruik",
      "water_use_note": "Wordt alleen gebruikt om liters uit te rekenen voor de waterverbruikcijfers. Het verandert niet wanneer of hoe lang de zone sproeit. Laat op 0 staan als u het niet weet.",
      "rain": "Regen, verwachting en vorst",
      "deep_soak": "Diepe watergift",
      "soil": "Bodem",
      "growth": "Groei",
      "deficit": "Spaarmodus",
      "history": "Geschiedenis",
      "safety": "Veiligheidslimieten en pomp",
      "notifications": "Meldingen",
      "more": "Meer",
      "climate": "Klimaatbeheersing",
      "misting": "Nevelen",
      "garden": "Tuingedeelte"
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
      "feed_due": "Nu bemesten",
      "other_area": "Overige"
    },
    "close": "Sluiten",
    "device_page": "Apparaatpagina openen",
    "fertilized": "Bemest",
    "mark_watered": "Markeer als bewaterd",
    "add_rain": "Regen toevoegen",
    "resume_automatic": "Automatisch hervatten",
    "crops": "Gewassen",
    "in_greenhouse": "In kas",
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
      "rain_eff_high": "Het deel van zware regen dat daadwerkelijk de wortels bereikt. De rest verdampt of stroomt weg.",
      "heat_temp": "De verwarming schakelt in wanneer de binnentemperatuur hieronder zakt, en weer uit iets erboven (zie Klimaathysterese).",
      "vent_temp": "Ventilatie opent wanneer de binnentemperatuur dit bereikt, en alleen wanneer de buitenlucht koeler is dan binnen.",
      "fan_temp": "Ventilatoren schakelen in bij deze binnentemperatuur (op of boven de ventilatietemperatuur), en alleen wanneer de buitenlucht koeler is dan binnen.",
      "climate_hysteresis": "Het verschil tussen het in- en uitschakelen van een apparaat, zodat het niet continu aan- en uitschakelt rond één temperatuur.",
      "outside_margin": "Ventilatie start alleen wanneer de buitenlucht minstens zo veel koeler is dan binnen, zodat er nooit warmere lucht wordt binnengehaald.",
      "max_humidity": "Ventilatie en ventilatoren draaien ook wanneer de luchtvochtigheid binnen hierboven is, tenzij het koud is.",
      "mist_temp": "Nevelen kan starten wanneer de binnentemperatuur op of boven dit niveau is.",
      "mist_min_humidity": "Nevelen kan starten wanneer de luchtvochtigheid binnen daalt tot dit niveau of lager.",
      "mist_stop_humidity": "Nevelen draait nooit wanneer de luchtvochtigheid binnen op of boven dit niveau is.",
      "mist_min_temp": "Geen nevelen onder deze binnentemperatuur.",
      "mist_light_level": "Nevelen kan starten wanneer de lichtmeting dit niveau bereikt (lichtsensor vereist).",
      "mist_on_seconds": "Hoe lang elke nevelpuls duurt.",
      "mist_off_seconds": "De rusttijd tussen nevelpulsen.",
      "max_mist_minutes_per_hour": "Een harde limiet voor nevelen in een periode van 60 minuten. Een handmatig ingeschakelde nevelaar gaat na deze tijd ook uit.",
      "vent_open_pct": "Hoe ver een ventilatie opent (voor ventilaties die op een stand ingesteld kunnen worden).",
      "auto_resume": "Aan: een handmatig geschakeld apparaat keert terug naar automatisch na Automatisch hervatten na. Uit: het blijft zoals je het achterliet totdat je op Automatisch hervatten drukt.",
      "auto_resume_hours": "Hoe lang een handmatig geschakeld apparaat met rust wordt gelaten voordat ZoneFlow de bediening overneemt (terwijl Automatisch hervatten aan staat).",
      "manual_rain_mm": "Regen afgelezen van een eenvoudige regenmeter. Druk op Regen toevoegen om op te slaan; de hoeveelheid gaat terug naar 0.",
      "zone_flow_l_min": "Wat de gehele zone per minuut geeft (druppelaars x debiet per druppelaar). Alleen gebruikt om liters te schatten; het verandert niet wanneer of hoeveel de zone sproeit. Laat op 0 staan als u het niet weet.",
      "sensor_offline_hours": "Een sensor die zo veel uur niets stuurt, geldt als offline en de klimaatregeling gaat naar de noodstand. Verhoog dit als een stabiele sensor valse waarschuwingen geeft.",
      "ventilation_failsafe": "Wat ventilatie en ventilatoren doen als er geen binnentemperatuursensor werkt. Nevelaars gaan altijd uit.",
      "heater_failsafe": "Wat de verwarming doet als er geen binnentemperatuursensor werkt. Deze draait nooit ononderbroken zonder sensor.",
      "misting_trigger": "Wat het nevelen start: elke willekeurige trigger, of alleen temperatuur, luchtvochtigheid of licht."
    },
    "garden": {
      "none": "Geen gedeelte",
      "new": "Nieuw gedeelte…",
      "name": "Naam van het gedeelte"
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
      "water_use": "Szacowanie zużycia wody",
      "water_use_note": "Służy wyłącznie do obliczania litrów dla danych o zużyciu wody. Nie zmienia tego, kiedy ani jak długo strefa podlewa. Pozostaw 0, jeśli nie znasz tej wartości.",
      "rain": "Deszcz, prognoza i przymrozki",
      "deep_soak": "Głębokie podlewanie",
      "soil": "Gleba",
      "growth": "Wzrost",
      "deficit": "Tryb deficytowy",
      "history": "Historia",
      "safety": "Limity bezpieczeństwa i pompa",
      "notifications": "Powiadomienia",
      "more": "Więcej",
      "climate": "Sterowanie klimatem",
      "misting": "Zamgławianie",
      "garden": "Obszar ogrodu"
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
      "feed_due": "Nawieź teraz",
      "other_area": "Inne"
    },
    "close": "Zamknij",
    "device_page": "Otwórz stronę urządzenia",
    "fertilized": "Nawożono",
    "mark_watered": "Oznacz jako podlane",
    "add_rain": "Dodaj deszcz",
    "resume_automatic": "Wznów automatykę",
    "crops": "Uprawy",
    "in_greenhouse": "W szklarni",
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
      "rain_eff_high": "Część opadów ulewnego deszczu, która rzeczywiście dociera do strefy korzeniowej. Reszta paruje lub spływa.",
      "heat_temp": "Grzejnik włącza się, gdy temperatura wewnętrzna spadnie poniżej tej wartości, i wyłącza nieco powyżej niej (patrz Histereza klimatu).",
      "vent_temp": "Wietrzniki otwierają się, gdy temperatura wewnętrzna osiągnie tę wartość, i tylko wtedy, gdy powietrze na zewnątrz jest chłodniejsze niż wewnątrz.",
      "fan_temp": "Wentylatory włączają się przy tej temperaturze wewnętrznej (równej lub wyższej od temperatury otwarcia wietrzników) i tylko wtedy, gdy powietrze na zewnątrz jest chłodniejsze niż wewnątrz.",
      "climate_hysteresis": "Różnica między włączeniem a wyłączeniem urządzenia, zapobiegająca ciągłemu przełączaniu wokół jednej wartości temperatury.",
      "outside_margin": "Wentylacja uruchamia się tylko wtedy, gdy powietrze na zewnątrz jest o co najmniej tyle chłodniejsze niż wewnątrz, dzięki czemu nigdy nie wciąga gorącego powietrza.",
      "max_humidity": "Wentylatory i wietrzniki działają również wtedy, gdy wilgotność wewnętrzna przekracza tę wartość, chyba że jest zimno.",
      "mist_temp": "Zamgławianie może się rozpocząć, gdy temperatura wewnętrzna jest równa tej wartości lub wyższa.",
      "mist_min_humidity": "Zamgławianie może się rozpocząć, gdy wilgotność wewnętrzna spadnie do tej wartości lub niżej.",
      "mist_stop_humidity": "Zamgławianie nigdy nie działa, gdy wilgotność wewnętrzna jest równa tej wartości lub wyższa.",
      "mist_min_temp": "Brak zamgławiania poniżej tej temperatury wewnętrznej.",
      "mist_light_level": "Zamgławianie może się rozpocząć, gdy poziom światła osiągnie tę wartość (wymaga czujnika światła).",
      "mist_on_seconds": "Czas trwania każdego impulsu zamgławiania.",
      "mist_off_seconds": "Przerwa między impulsami zamgławiania.",
      "max_mist_minutes_per_hour": "Sztywny limit zamgławiania w ciągu dowolnych 60 minut. Zamgławiacz włączony ręcznie również wyłącza się po tym czasie.",
      "vent_open_pct": "Stopień otwarcia wietrznika (dla wietrzników z możliwością ustawienia pozycji).",
      "auto_resume": "Włączone: urządzenie przełączone ręcznie wraca do automatyki po Czasie automatycznego wznowienia. Wyłączone: pozostaje w obecnym stanie, dopóki nie naciśniesz Wznów automatykę.",
      "auto_resume_hours": "Jak długo urządzenie przełączone ręcznie pozostaje bez zmian, zanim ZoneFlow przejmie nad nim kontrolę (gdy Wznowienie automatyczne jest włączone).",
      "manual_rain_mm": "Ilość deszczu odczytana ze zwykłego deszczomierza. Naciśnij Dodaj deszcz, aby ją zapisać; wartość powróci do 0.",
      "zone_flow_l_min": "Ile daje cała strefa na minutę (emitery x przepływ na emiter). Używane tylko do szacowania litrów; nie zmienia tego, kiedy ani ile wody podaje strefa. Pozostaw 0, jeśli nie znasz tej wartości.",
      "sensor_offline_hours": "Czujnik, który nie wysyła nic przez tyle godzin, jest uznawany za offline, a sterowanie klimatem przechodzi w tryb awaryjny. Zwiększ tę wartość, jeśli stabilny czujnik powoduje fałszywe ostrzeżenia.",
      "ventilation_failsafe": "Co robią wietrzniki i wentylatory, gdy żaden czujnik temperatury wewnętrznej nie działa. Zamgławiacze zawsze się wyłączają.",
      "heater_failsafe": "Co robi grzejnik, gdy żaden czujnik temperatury wewnętrznej nie działa. Nigdy nie działa bez przerwy bez czujnika.",
      "misting_trigger": "Co uruchamia zamgławianie: dowolny z wyzwalaczy lub tylko temperatura, wilgotność bądź światło."
    },
    "garden": {
      "none": "Brak obszaru",
      "new": "Nowy obszar…",
      "name": "Nazwa obszaru"
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
      "water_use": "Estimativa do uso de água",
      "water_use_note": "Utilizado apenas para calcular os litros dos números de uso de água. Não altera quando nem durante quanto tempo a zona irriga. Deixe 0 se não souber.",
      "rain": "Chuva, previsão e geada",
      "deep_soak": "Rega profunda",
      "soil": "Solo",
      "growth": "Crescimento",
      "deficit": "Rega deficitária",
      "history": "Histórico",
      "safety": "Limites de segurança e bomba",
      "notifications": "Notificações",
      "more": "Mais",
      "climate": "Controlo de clima",
      "misting": "Nebulização",
      "garden": "Área do jardim"
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
      "feed_due": "Adubar agora",
      "other_area": "Outras"
    },
    "close": "Fechar",
    "device_page": "Abrir a página do dispositivo",
    "fertilized": "Adubado",
    "mark_watered": "Marcar como regado",
    "add_rain": "Adicionar chuva",
    "resume_automatic": "Retomar automático",
    "crops": "Culturas",
    "in_greenhouse": "Na estufa",
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
      "rain_eff_high": "Percentagem de chuva forte que chega efetivamente às raízes. O restante evapora ou escorre.",
      "heat_temp": "O aquecedor liga-se quando a temperatura interior desce abaixo deste valor e desliga-se um pouco acima (consulte Histerese do clima).",
      "vent_temp": "As aberturas abrem quando a temperatura interior atinge este valor e apenas quando o ar exterior está mais frio do que o interior.",
      "fan_temp": "Os ventiladores ligam-se a esta temperatura interior (igual ou superior à temperatura das aberturas) e apenas quando o ar exterior está mais frio do que o interior.",
      "climate_hysteresis": "O intervalo entre um dispositivo ligar e desligar, evitando alternâncias constantes perto de uma mesma temperatura.",
      "outside_margin": "A ventilação só começa quando o ar exterior está pelo menos esta quantidade mais frio do que o interior, para nunca introduzir ar mais quente.",
      "max_humidity": "Os ventiladores e aberturas também funcionam quando a humidade interior está acima deste valor, a menos que esteja frio.",
      "mist_temp": "A nebulização pode iniciar quando a temperatura interior for igual ou superior a este valor.",
      "mist_min_humidity": "A nebulização pode iniciar quando a humidade interior descer até este valor ou inferior.",
      "mist_stop_humidity": "A nebulização nunca é executada quando a humidade interior for igual ou superior a este valor.",
      "mist_min_temp": "Sem nebulização abaixo desta temperatura interior.",
      "mist_light_level": "A nebulização pode iniciar quando a leitura de luz atingir este nível (requer sensor de luz).",
      "mist_on_seconds": "Duração de cada impulso de nebulização.",
      "mist_off_seconds": "Intervalo de descanso entre impulsos de nebulização.",
      "max_mist_minutes_per_hour": "Limite máximo de nebulização em qualquer janela de 60 minutos. Um nebulizador ligado manualmente também se desliga após este tempo.",
      "vent_open_pct": "O quanto uma abertura se abre (para aberturas com regulação de posição).",
      "auto_resume": "Ligado: um dispositivo alterado manualmente volta ao modo automático após Retoma automática após. Desligado: permanece como o deixou até premir Retomar automático.",
      "auto_resume_hours": "Quanto tempo um dispositivo alterado manualmente é mantido inalterado antes de o ZoneFlow retomar o controlo (enquanto a Retoma automática estiver ligada).",
      "manual_rain_mm": "Chuva lida num pluviómetro simples. Prima Adicionar chuva para registar; o valor volta a 0.",
      "zone_flow_l_min": "Quanto a zona inteira fornece por minuto (emissores x fluxo por emissor). Utilizado apenas para estimar os litros; não altera quando ou o quanto a zona irriga. Deixe 0 se não souber.",
      "sensor_offline_hours": "Um sensor que não envia nada durante estas horas é considerado offline e o controlo do clima passa ao modo de segurança. Aumente o valor se um sensor estável causar avisos falsos.",
      "ventilation_failsafe": "O que as aberturas e ventiladores fazem quando nenhum sensor de temperatura interior está a funcionar. Os nebulizadores desligam-se sempre.",
      "heater_failsafe": "O que o aquecedor faz quando nenhum sensor de temperatura interior está a funcionar. Nunca funciona ininterruptamente sem um sensor.",
      "misting_trigger": "O que inicia a nebulização: qualquer um dos gatilhos ou apenas temperatura, humidade ou luz."
    },
    "garden": {
      "none": "Sem área",
      "new": "Nova área…",
      "name": "Nome da área"
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
      "water_use": "Uppskattning av vattenförbrukning",
      "water_use_note": "Används bara för att räkna ut liter till vattenförbrukningssiffrorna. Det ändrar inte när eller hur länge zonen vattnar. Lämna på 0 om du inte vet.",
      "rain": "Regn, prognos och frost",
      "deep_soak": "Djupvattning",
      "soil": "Jord",
      "growth": "Tillväxt",
      "deficit": "Sparläge",
      "history": "Historik",
      "safety": "Säkerhetsgränser och pump",
      "notifications": "Aviseringar",
      "more": "Mer",
      "climate": "Klimatstyrning",
      "misting": "Dimmning",
      "garden": "Trädgårdsområde"
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
      "feed_due": "Gödsla nu",
      "other_area": "Övriga"
    },
    "close": "Stäng",
    "device_page": "Öppna enhetssidan",
    "fertilized": "Gödslat",
    "mark_watered": "Markera som vattnad",
    "add_rain": "Lägg till regn",
    "resume_automatic": "Återgå till automatik",
    "crops": "Grödor",
    "in_greenhouse": "I växthus",
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
      "rain_eff_high": "Andel av kraftigt regn som faktiskt når rötterna. Resten dunstar eller rinner av.",
      "heat_temp": "Värmaren slås på när innetemperaturen sjunker under detta och stängs av igen lite ovanför (se Klimathysteres).",
      "vent_temp": "Vädringen öppnas när innetemperaturen når detta, och endast när uteluften är kallare än inne.",
      "fan_temp": "Fläktarna slås på vid denna innetemperatur (vid eller över vädringstemperaturen), och endast när uteluften är kallare än inne.",
      "climate_hysteresis": "Skillnaden mellan att en enhet slås på och av, så att den inte slår på och av hela tiden kring samma temperatur.",
      "outside_margin": "Vädringen startar bara när uteluften är minst så här mycket kallare än inne, så att den aldrig drar in varmare luft.",
      "max_humidity": "Vädring och fläktar körs också när fuktigheten inne är över detta, såvida det inte är kallt.",
      "mist_temp": "Dimmning kan starta när innetemperaturen är vid eller över detta.",
      "mist_min_humidity": "Dimmning kan starta när innetemperaturen sjunker till detta eller lägre.",
      "mist_stop_humidity": "Dimmning körs aldrig när fuktigheten inne är vid eller över detta.",
      "mist_min_temp": "Ingen dimmning under denna innetemperatur.",
      "mist_light_level": "Dimmning kan starta när ljusvärdet når denna nivå (kräver en ljusgivare).",
      "mist_on_seconds": "Hur länge varje dimmimpuls varar.",
      "mist_off_seconds": "Pausen mellan dimmimpulser.",
      "max_mist_minutes_per_hour": "En fast gräns för dimmning under valfria 60 minuter. En dimmare som slås på manuellt stängs också av efter denna tid.",
      "vent_open_pct": "Hur mycket en vädring öppnas (för vädring som kan ställas in i ett visst läge).",
      "auto_resume": "På: en enhet du ändrat manuellt återgår till automatik efter Auto-återgång efter. Av: den står kvar i sitt läge tills du trycker på Återgå till automatik.",
      "auto_resume_hours": "Hur länge en enhet du ändrat manuellt lämnas ifred innan ZoneFlow tar över styrningen igen (när Auto-återgång är på).",
      "manual_rain_mm": "Regnmängd du läst av från en enkel regnmätare. Tryck på Lägg till regn för att spara; mängden återgår till 0.",
      "zone_flow_l_min": "Vad hela zonen ger per minut (droppare x flöde per droppare). Används endast för att uppskatta liter; det ändrar inte när eller hur mycket zonen vattnar. Lämna som 0 om du inte vet.",
      "sensor_offline_hours": "En sensor som inte skickar något på så här många timmar räknas som offline, och klimatstyrningen går till sitt nödläge. Höj värdet om en stabil sensor ger falska varningar.",
      "ventilation_failsafe": "Vad vädring och fläktar gör när ingen innetemperaturgivare fungerar. Dimmare stängs alltid av.",
      "heater_failsafe": "Vad värmaren gör när ingen innetemperaturgivare fungerar. Den körs aldrig oavbrutet utan en givare.",
      "misting_trigger": "Vad som startar dimmning: någon av utlösarna, eller enbart temperatur, fuktighet eller ljus."
    },
    "garden": {
      "none": "Inget område",
      "new": "Nytt område…",
      "name": "Områdets namn"
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
      "water_use": "Odhad spotřeby vody",
      "water_use_note": "Slouží jen k výpočtu litrů pro údaje o spotřebě vody. Nemění, kdy ani jak dlouho zóna zavlažuje. Pokud hodnotu neznáte, nechte 0.",
      "rain": "Déšť, předpověď a mráz",
      "deep_soak": "Hloubková zálivka",
      "soil": "Půda",
      "growth": "Růst",
      "deficit": "Deficitní režim",
      "history": "Historie",
      "safety": "Bezpečnostní limity a čerpadlo",
      "notifications": "Oznámení",
      "more": "Další",
      "climate": "Řízení klimatu",
      "misting": "Mlžení",
      "garden": "Zahradní oblast"
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
      "feed_due": "Pohnojit teď",
      "other_area": "Ostatní"
    },
    "close": "Zavřít",
    "device_page": "Otevřít stránku zařízení",
    "fertilized": "Pohnojeno",
    "mark_watered": "Označit jako zalité",
    "add_rain": "Přidat déšť",
    "resume_automatic": "Obnovit automatiku",
    "crops": "Plodiny",
    "in_greenhouse": "V skleníku",
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
      "rain_eff_high": "Podíl silného deště, který se skutečně dostane ke kořenům. Zbytek odteče nebo se odpaří.",
      "heat_temp": "Topení se zapne, když vnitřní teplota klesne pod tuto hodnotu, a vypne se o něco výše (viz Hystereze klimatu).",
      "vent_temp": "Větrací otvory se otevřou, když vnitřní teplota dosáhne této hodnoty, a pouze tehdy, když je venkovní vzduch chladnější než vnitřní.",
      "fan_temp": "Ventilátory se zapnou při této vnitřní teplotě (při nebo nad teplotou otevření větrání) a pouze tehdy, když je venkovní vzduch chladnější než vnitřní.",
      "climate_hysteresis": "Rozdíl mezi zapnutím a vypnutím zařízení, aby se nepravidelně nepřepínalo kolem jedné hodnoty teploty.",
      "outside_margin": "Větrání se spustí pouze v případě, že venkovní vzduch je o tuto hodnotu chladnější než vnitřní, aby se nevpouštěl teplejší vzduch.",
      "max_humidity": "Ventilátory a větrací otvory běží také tehdy, když je vnitřní vlhkost nad touto hodnotou, pokud není chladno.",
      "mist_temp": "Mlžení se může spustit, když je vnitřní teplota na této hodnotě nebo vyšší.",
      "mist_min_humidity": "Mlžení se může spustit, když vnitřní vlhkost klesne na tuto hodnotu nebo nižší.",
      "mist_stop_humidity": "Mlžení se nikdy nespustí, když je vnitřní vlhkost na této hodnotě nebo vyšší.",
      "mist_min_temp": "Mlžení je zakázáno pod touto vnitřní teplotou.",
      "mist_light_level": "Mlžení se může spustit, když úroveň osvětlení dosáhne této hodnoty (vyžaduje snímač osvětlení).",
      "mist_on_seconds": "Jak dlouho trvá jeden pulz mlžení.",
      "mist_off_seconds": "Pauza mezi pulzy mlžení.",
      "max_mist_minutes_per_hour": "Pevný limit mlžení během libovolných 60 minut. Mlžovač zapnutý ručně se po této době také vypne.",
      "vent_open_pct": "Míra otevření větracího otvoru (pro otvory, u kterých lze nastavit polohu).",
      "auto_resume": "Zapnuto: ručně přepnuté zařízení se vrátí do automatického režimu po uplynutí Zpoždění automatického návratu. Vypnuto: zůstane ve stavu, v jakém jste jej nechali, dokud nestisknete Obnovit automatiku.",
      "auto_resume_hours": "Jak dlouho zůstane ručně přepnuté zařízení bez zásahu, než si je ZoneFlow vezme zpět (při zapnutém Automatickém návratu).",
      "manual_rain_mm": "Množství srážek zjištěné z běžného srážkoměru. Stisknutím tlačítka Přidat déšť jej uložíte; hodnota se pak vynuluje.",
      "zone_flow_l_min": "Kolik celá zóna dává za minutu (počet emitorů x průtok na emitor). Používá se pouze k odhadu litrů; nemění to, kdy nebo kolik zóna zavlažuje. Pokud hodnotu neznáte, ponechte 0.",
      "sensor_offline_hours": "Senzor, který tolik hodin nic nepošle, se považuje za offline a řízení klimatu přejde do nouzového režimu. Zvyšte hodnotu, pokud stabilní senzor způsobuje falešná varování.",
      "ventilation_failsafe": "Co dělají větrací otvory a ventilátory, když nefunguje žádný snímač vnitřní teploty. Mlžovače se vždy vypnou.",
      "heater_failsafe": "Co dělá topení, když nefunguje žádný snímač vnitřní teploty. Bez snímače nikdy neběží nepřetržitě.",
      "misting_trigger": "Co spouští mlžení: jakýkoli ze spouštěčů, nebo pouze teplota, vlhkost či světlo."
    },
    "garden": {
      "none": "Bez oblasti",
      "new": "Nová oblast…",
      "name": "Název oblasti"
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
      "water_use": "Skøn over vandforbrug",
      "water_use_note": "Bruges kun til at regne liter ud til vandforbrugstallene. Det ændrer ikke, hvornår eller hvor længe zonen vander. Lad den stå på 0, hvis du ikke kender den.",
      "rain": "Regn, vejrudsigt og frost",
      "deep_soak": "Dybdevanding",
      "soil": "Jord",
      "growth": "Vækst",
      "deficit": "Sparetilstand",
      "history": "Historik",
      "safety": "Sikkerhedsgrænser og pumpe",
      "notifications": "Notifikationer",
      "more": "Mere",
      "climate": "Klimastyring",
      "misting": "Forstøvning",
      "garden": "Haveområde"
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
      "feed_due": "Gød nu",
      "other_area": "Øvrige"
    },
    "close": "Luk",
    "device_page": "Åbn enhedssiden",
    "fertilized": "Gødsket",
    "mark_watered": "Markér som vandet",
    "add_rain": "Tilføj regn",
    "resume_automatic": "Genoptag automatik",
    "crops": "Aftrøder",
    "in_greenhouse": "I drivhus",
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
      "rain_eff_high": "Andel af kraftig regn, der reelt når rødderne. Resten fordamper eller løber af.",
      "heat_temp": "Varmelegemet tændes, når den indendørs temperatur falder til under dette, og slukker igen lidt over (se Klimahysterese).",
      "vent_temp": "Udluftningen åbnes, når den indendørs temperatur når dette, og kun når udeluften er koldere end indeluften.",
      "fan_temp": "Ventilatorer tændes ved denne indendørstemperatur (ved eller over udluftningstemperaturen), og kun når udeluften er koldere end indeluften.",
      "climate_hysteresis": "Forskellen mellem at en enhed tændes og slukkes, så den ikke konstant tænder og slukker omkring den samme temperatur.",
      "outside_margin": "Ventilation starter kun, når udeluften er mindst så meget koldere end indeluften, så der aldrig trækkes varmere luft ind.",
      "max_humidity": "Ventilatorer og udluftning kører også, når den indendørs fugtighed er over dette, medmindre det er koldt.",
      "mist_temp": "Forstøvning kan starte, når den indendørs temperatur er på eller over dette.",
      "mist_min_humidity": "Forstøvning kan starte, når den indendørs fugtighed falder til dette eller lavere.",
      "mist_stop_humidity": "Forstøvning kører aldrig, når den indendørs fugtighed er på eller over dette.",
      "mist_min_temp": "Ingen forstøvning under denne indendørstemperatur.",
      "mist_light_level": "Forstøvning kan starte, når lysmålingen når dette niveau (kræver en lyssensor).",
      "mist_on_seconds": "Hvor længe hver forstøvningspuls varer.",
      "mist_off_seconds": "Pausen mellem forstøvningspulser.",
      "max_mist_minutes_per_hour": "En fast grænse for forstøvning inden for en periode på 60 minutter. En forstøver skiftet manuelt slukker også efter så lang tid.",
      "vent_open_pct": "Hvor meget en udluftning åbner (for udluftninger der kan indstilles til en position).",
      "auto_resume": "Til: en enhed skiftet manuelt vender tilbage til automatik efter Auto-genoptag efter. Fra: den forbliver som du forlod den, indtil du trykker på Genoptag automatik.",
      "auto_resume_hours": "Hvor længe en manuelt betjent enhed lades være i fred, før ZoneFlow tager styringen tilbage (når Auto-genoptag er slået til).",
      "manual_rain_mm": "Regnmængde du har aflæst fra en simpel regnmåler. Tryk på Tilføj regn for at gemme den; mængden nulstilles herefter.",
      "zone_flow_l_min": "Hvad hele zonen giver pr. minut (dryppere x flow pr. drypper). Bruges kun til at skønne liter; det ændrer ikke, hvornår eller hvor meget zonen vander. Lad stå på 0, hvis du ikke kender det.",
      "sensor_offline_hours": "En sensor, der ikke sender noget i så mange timer, regnes som offline, og klimastyringen går i nøddrift. Hæv værdien, hvis en stabil sensor giver falske advarsler.",
      "ventilation_failsafe": "Hvad udluftning og ventilatorer gør, når ingen indendørs temperatursensor virker. Forstøvere slukker altid.",
      "heater_failsafe": "Hvad varmelegemet gør, når ingen indendørs temperatursensor virker. Det kører aldrig uafbrudt uden en sensor.",
      "misting_trigger": "Hvad der starter forstøvningen: enhver af udløserne, eller kun temperatur, fugtighed eller lys."
    },
    "garden": {
      "none": "Intet område",
      "new": "Nyt område…",
      "name": "Områdets navn"
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
      "water_use": "Vízhasználat becslése",
      "water_use_note": "Csak a vízhasználati adatok literszámának kiszámítására szolgál. Nem változtatja meg, hogy a zóna mikor és mennyi ideig öntöz. Hagyja 0-n, ha nem ismeri.",
      "rain": "Eső, előrejelzés és fagy",
      "deep_soak": "Mélyöntözés",
      "soil": "Talaj",
      "growth": "Növekedés",
      "deficit": "Takarékos mód",
      "history": "Előzmények",
      "safety": "Biztonsági korlátok és szivattyú",
      "notifications": "Értesítések",
      "more": "Egyéb",
      "climate": "Klímaszabályozás",
      "misting": "Párásítás",
      "garden": "Kerti terület"
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
      "feed_due": "Tápanyag most",
      "other_area": "Egyéb"
    },
    "close": "Bezárás",
    "device_page": "Eszközoldal megnyitása",
    "fertilized": "Tápanyag pótolva",
    "mark_watered": "Megjelölés öntözöttként",
    "add_rain": "Eső hozzáadása",
    "resume_automatic": "Automatika folytatása",
    "crops": "Növények",
    "in_greenhouse": "Üvegházban",
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
      "rain_eff_high": "A heves eső azon hányada, amely valóban eléri a gyökereket. A többi elpárolog vagy elfolyik.",
      "heat_temp": "A fűtés bekapcsol, ha a belső hőmérséklet ez alá esik, és kikapcsol kevéssel felette (lásd Klíma hiszterézis).",
      "vent_temp": "A szellőzők akkor nyitnak ki, ha a belső hőmérséklet eléri ezt az értéket, és csak akkor, ha a külső levegő hűvösebb a belsőnél.",
      "fan_temp": "A ventilátorok ezen belső hőmérsékleten kapcsolnak be (a szellőzési hőmérsékleten vagy afelett), és csak akkor, ha a külső levegő hűvösebb a belsőnél.",
      "climate_hysteresis": "Az eszköz be- és kikapcsolása közötti különbség, így nem kapcsolgat folyamatosan egyetlen hőmérsékletérték körül.",
      "outside_margin": "A szellőztetés csak akkor indul el, ha a külső levegő legalább ennyivel hűvösebb a belsőnél, így soha nem szív be melegebb levegőt.",
      "max_humidity": "A szellőzők és ventilátorok akkor is működnek, ha a belső páratartalom ez felett van, kivéve, ha hideg van.",
      "mist_temp": "A párásítás akkor indulhat el, ha a belső hőmérséklet eléri vagy meghaladja ezt az értéket.",
      "mist_min_humidity": "A párásítás akkor indulhat el, ha a belső páratartalom erre a szintre vagy ez alá esik.",
      "mist_stop_humidity": "A párásítás soha nem működik, ha a belső páratartalom eléri ezt az értéket vagy afelett van.",
      "mist_min_temp": "Ezen belső hőmérséklet alatt nincs párásítás.",
      "mist_light_level": "A párásítás akkor indulhat el, ha a fénymérés eléri ezt a szintet (fényérzékelőt igényel).",
      "mist_on_seconds": "Milyen hosszú egy-egy párásítási impulzus.",
      "mist_off_seconds": "A párásítási impulzusok közötti szünet ideje.",
      "max_mist_minutes_per_hour": "Szigorú korlát a párásításra bármely 60 perces időszakban. A kézzel bekapcsolt párásító is kikapcsol ennyi idő után.",
      "vent_open_pct": "Mennyire nyíljon ki a szellőző (pozicionálható szellőzők esetén).",
      "auto_resume": "Be: a kézzel kapcsolodó eszköz az Automatikus folytatás késleltetése után visszatér automatikus módba. Ki: abban az állapotban marad, amíg meg nem nyomja az Automatika folytatása gombot.",
      "auto_resume_hours": "Mennyi ideig marad változatlanul a kézzel kapcsolodó eszköz, mielőtt a ZoneFlow visszaveszi az irányítást (amikor az Automatikus folytatás be van kapcsolva).",
      "manual_rain_mm": "Egyszerű csapadékmérőből leolvasott esőmennyiség. Nyomja meg az Eső hozzáadása gombot a rögzítéshez; az érték ezután 0-ra vált.",
      "zone_flow_l_min": "Amit a teljes zóna ad percenként (csepegtetők x csepegtetőnkénti vízhozam). Csak a literek becslésére szolgál; nem változtatja meg, hogy a zóna mikor vagy mennyit öntöz. Hagyja 0 értéken, ha nem tudja.",
      "sensor_offline_hours": "Az az érzékelő, amely ennyi órán át nem küld semmit, offline-nak számít, és a klímavezérlés vészüzemmódba lép. Növelje az értéket, ha egy egyenletesen mérő érzékelő téves figyelmeztetéseket okoz.",
      "ventilation_failsafe": "Mit tegyenek a szellőzők és ventilátorok, ha nem működik belső hőmérséklet-érzékelő. A párásítók mindig kikapcsolnak.",
      "heater_failsafe": "Mit tegyen a fűtés, ha nem működik belső hőmérséklet-érzékelő. Érzékelő nélkül soha nem működik folyamatosan.",
      "misting_trigger": "Mi indítja el a párásítást: az indítók bármelyike, vagy csak a hőmérséklet, a páratartalom vagy a fény."
    },
    "garden": {
      "none": "Nincs terület",
      "new": "Új terület…",
      "name": "A terület neve"
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
      "water_use": "Anslag for vannforbruk",
      "water_use_note": "Brukes bare til å regne ut liter for vannforbrukstallene. Det endrer ikke når eller hvor lenge sonen vanner. La stå på 0 hvis du ikke vet det.",
      "rain": "Regn, værmelding og frost",
      "deep_soak": "Dypvanning",
      "soil": "Jord",
      "growth": "Vekst",
      "deficit": "Underskuddsvanning",
      "history": "Historikk",
      "safety": "Sikkerhetsgrenser og pumpe",
      "notifications": "Varsler",
      "more": "Mer",
      "climate": "Klimastyring",
      "misting": "Tåkelegging",
      "garden": "Hageområde"
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
      "feed_due": "Gjødsle nå",
      "other_area": "Andre"
    },
    "close": "Lukk",
    "device_page": "Åpne enhetssiden",
    "fertilized": "Gjødslet",
    "mark_watered": "Merk som vannet",
    "add_rain": "Legg til regn",
    "resume_automatic": "Gjenoppta automatikk",
    "crops": "Kulturer",
    "in_greenhouse": "I drivhus",
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
      "rain_eff_high": "Andel av kraftig regn som faktisk når røttene. Resten fordamper eller renner vekk.",
      "heat_temp": "Varmeovnen slås på når innendørstemperaturen faller under dette, og av igjen litt over (se Klimahysterese).",
      "vent_temp": "Lufting åpnes når innendørstemperaturen når dette, og bare når uteluften er kaldere enn inne.",
      "fan_temp": "Vifter slås på ved denne innendørstemperaturen (ved eller over luftingstemperaturen), og bare når uteluften er kaldere enn inne.",
      "climate_hysteresis": "Avstanden mellom at en enhet slås på og av, slik at den ikke vipper fram og tilbake rundt én temperatur.",
      "outside_margin": "Lufting starter bare når uteluften er minst så mye kaldere enn inne, slik at varmere luft aldri trekkes inn.",
      "max_humidity": "Lufting og vifter kjører også når fuktigheten inne er over dette, med mindre det er kaldt.",
      "mist_temp": "Tåkelegging kan starte når innendørstemperaturen er ved eller over dette.",
      "mist_min_humidity": "Tåkelegging kan starte når fuktigheten inne faller til dette eller lavere.",
      "mist_stop_humidity": "Tåkelegging kjører aldri når fuktigheten inne er ved eller over dette.",
      "mist_min_temp": "Ingen tåkelegging under denne innendørstemperaturen.",
      "mist_light_level": "Tåkelegging kan starte når lysmålingen når dette nivået (krever lyssensor).",
      "mist_on_seconds": "Hvor lenge hver tåkeleggingspuls varer.",
      "mist_off_seconds": "Hvilepause mellom tåkeleggingspulser.",
      "max_mist_minutes_per_hour": "En øvre grense for tåkelegging i løpet av en 60-minutters periode. En tåkelegger slått på manuelt slås også av etter så lang tid.",
      "vent_open_pct": "Hvor mye luftingen åpner seg (for ventiler som kan stilles inn i posisjon).",
      "auto_resume": "På: en enhet som er slått på/av manuelt går tilbake til automatikk etter Automatisk gjenoptakelse etter. Av: den blir stående som du forlot den til du trykker på Gjenoppta automatikk.",
      "auto_resume_hours": "Hvor lenge en manuelt betjent enhet står urørt før ZoneFlow tar over styringen igjen (når Automatisk gjenoptakelse er på).",
      "manual_rain_mm": "Regnmengde du avleser fra en enkel regnmåler. Trykk på Legg til regn for å registrere den; mengden tilbakestilles til 0.",
      "zone_flow_l_min": "Hva hele sonen gir per minutt (utløp x gjennomstrømning per utløp). Brukes kun til å anslå liter; det endrer ikke når eller hvor mye sonen vanner. La stå som 0 hvis du ikke vet det.",
      "sensor_offline_hours": "En sensor som ikke sender noe på så mange timer, regnes som frakoblet, og klimastyringen går i nøddrift. Øk verdien hvis en stabil sensor gir falske varsler.",
      "ventilation_failsafe": "Hva lufting og vifter gjør når ingen innvendig temperatursensor fungerer. Tåkeleggere slås alltid av.",
      "heater_failsafe": "Hva varmeovnen gjør når ingen innvendig temperatursensor fungerer. Den kjører aldri uavbrutt uten sensor.",
      "misting_trigger": "Hva som starter tåkelegging: enhver utløser, eller bare temperatur, fuktighet eller lys."
    },
    "garden": {
      "none": "Ingen område",
      "new": "Nytt område…",
      "name": "Områdets navn"
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
      "water_use": "Estimativa do uso de água",
      "water_use_note": "Usado apenas para calcular os litros dos números de uso de água. Não altera quando nem por quanto tempo a zona irriga. Deixe 0 se você não souber.",
      "rain": "Chuva, previsão e geada",
      "deep_soak": "Irrigação profunda",
      "soil": "Solo",
      "growth": "Crescimento",
      "deficit": "Irrigação deficitária",
      "history": "Histórico",
      "safety": "Limites de segurança e bomba",
      "notifications": "Notificações",
      "more": "Mais",
      "climate": "Controle de clima",
      "misting": "Nebulização",
      "garden": "Área do jardim"
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
      "feed_due": "Adubar agora",
      "other_area": "Outras"
    },
    "close": "Fechar",
    "device_page": "Abrir a página do dispositivo",
    "fertilized": "Adubado",
    "mark_watered": "Marcar como regado",
    "add_rain": "Adicionar chuva",
    "resume_automatic": "Retomar automático",
    "crops": "Culturas",
    "in_greenhouse": "Na estufa",
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
      "rain_eff_high": "Proporção de chuva forte que realmente atinge as raízes. O restante evapora ou escorre.",
      "heat_temp": "O aquecedor liga quando a temperatura interna cai abaixo disto e desliga um pouco acima (veja Histerese do Clima).",
      "vent_temp": "Aberturas de ventilação abrem quando a temperatura interna atinge este valor, e apenas quando o ar externo estiver mais frio que o interno.",
      "fan_temp": "Ventiladores ligam nesta temperatura interna (na temperatura de ventilação ou acima), e apenas quando o ar externo estiver mais frio que o interno.",
      "climate_hysteresis": "O intervalo entre um dispositivo ligar e desligar, para não oscilar em torno de uma mesma temperatura.",
      "outside_margin": "A ventilação só começa quando o ar externo estiver pelo menos este valor mais frio que o interno, evitando puxar ar mais quente.",
      "max_humidity": "Ventiladores e aberturas de ventilação também funcionam quando a umidade interna está acima disto, a menos que esteja frio.",
      "mist_temp": "A nebulização pode iniciar quando a temperatura interna estiver igual ou acima disto.",
      "mist_min_humidity": "A nebulização pode iniciar quando a umidade interna cair para isto ou menos.",
      "mist_stop_humidity": "A nebulização nunca roda quando a umidade interna está igual ou acima disto.",
      "mist_min_temp": "Sem nebulização abaixo desta temperatura interna.",
      "mist_light_level": "A nebulização pode iniciar quando a leitura de luz atingir este nível (necessita de sensor de luz).",
      "mist_on_seconds": "Duração de cada pulso de nebulização.",
      "mist_off_seconds": "Tempo de descanso entre pulsos de nebulização.",
      "max_mist_minutes_per_hour": "Limite máximo de nebulização a cada 60 minutos. Um nebulizador ligado manualmente também desliga após esse tempo.",
      "vent_open_pct": "Quanto uma abertura de ventilação abre (para aberturas ajustáveis por posição).",
      "auto_resume": "Ligado: um dispositivo alterado manualmente volta ao modo automático após Retomada automática após. Desligado: permanece como você deixou até pressionar Retomar automático.",
      "auto_resume_hours": "Quanto tempo um dispositivo alterado manualmente fica sem intervenção antes que o ZoneFlow retome o controle (enquanto a Retomada automática estiver ligada).",
      "manual_rain_mm": "Chuva lida em um pluviômetro simples. Pressione Adicionar chuva para registrar; a quantidade volta para 0.",
      "zone_flow_l_min": "Quanto a zona inteira fornece por minuto (emissores x vazão por emissor). Usado apenas para estimar os litros; não altera quando ou o quanto a zona irriga. Deixe 0 se não souber.",
      "sensor_offline_hours": "Um sensor que não envia nada por estas horas é considerado offline, e o controle do clima entra no modo de segurança. Aumente o valor se um sensor estável causar alertas falsos.",
      "ventilation_failsafe": "O que aberturas e ventiladores fazem quando nenhum sensor de temperatura interna funciona. Nebulizadores sempre desligam.",
      "heater_failsafe": "O que o aquecedor faz quando nenhum sensor de temperatura interna funciona. Ele nunca roda continuamente sem um sensor.",
      "misting_trigger": "O que inicia a nebulização: qualquer um dos gatilhos ou apenas temperatura, umidade ou luminosidade."
    },
    "garden": {
      "none": "Sem área",
      "new": "Nova área…",
      "name": "Nome da área"
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
      "water_use": "Оценка расхода воды",
      "water_use_note": "Используется только для расчёта литров в данных о расходе воды. Не влияет на то, когда и как долго зона поливает. Оставьте 0, если не знаете.",
      "rain": "Дождь, прогноз и заморозки",
      "deep_soak": "Глубокий полив",
      "soil": "Почва",
      "growth": "Рост",
      "deficit": "Режим дефицита",
      "history": "История",
      "safety": "Защитные лимиты и насос",
      "notifications": "Уведомления",
      "more": "Ещё",
      "climate": "Управление климатом",
      "misting": "Туманообразование",
      "garden": "Участок сада"
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
      "feed_due": "Подкормить сейчас",
      "other_area": "Прочее"
    },
    "close": "Закрыть",
    "device_page": "Открыть страницу устройства",
    "fertilized": "Подкормлено",
    "mark_watered": "Отметить полив",
    "add_rain": "Добавить дождь",
    "resume_automatic": "Возобновить авторежим",
    "crops": "Культуры",
    "in_greenhouse": "В теплице",
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
      "rain_eff_high": "Доля сильного дождя, которая реально доходит до корней. Остальное испаряется или стекает.",
      "heat_temp": "Обогреватель включается, когда температура внутри опускается ниже этого значения, и отключается чуть выше него (см. Гистерезис климата).",
      "vent_temp": "Форточки открываются при достижении этой температуры внутри и только если воздух снаружи прохладнее внутреннего.",
      "fan_temp": "Вентиляторы включаются при этой температуре внутри (не ниже температуры открытия форточек) и только если воздух снаружи прохладнее внутреннего.",
      "climate_hysteresis": "Интервал между включением и выключением устройства для предотвращения частых срабатываний около порогового значения.",
      "outside_margin": "Проветривание начинается, только если воздух снаружи холоднее внутреннего минимум на эту величину, исключая забор жаркого воздуха.",
      "max_humidity": "Форточки и вентиляторы также работают при превышении этой влажности внутри, если не холодно.",
      "mist_temp": "Туманообразование запускается, если температура внутри достигла или превысила это значение.",
      "mist_min_humidity": "Туманообразование запускается, если влажность внутри опустилась до этого значения или ниже.",
      "mist_stop_humidity": "Туманообразование отключается при достижении этой влажности внутри или выше.",
      "mist_min_temp": "Запрет туманообразования при температуре внутри ниже этого значения.",
      "mist_light_level": "Туманообразование запускается при достижении этого уровня освещенности (требуется датчик освещенности).",
      "mist_on_seconds": "Длительность одного импульса подачи тумана.",
      "mist_off_seconds": "Длительность паузы между импульсами тумана.",
      "max_mist_minutes_per_hour": "Лимит суммарного времени работы тумана за любой 60-минутный интервал. Ручное включение тумана также выключается по истечении этого времени.",
      "vent_open_pct": "Степень открытия форточки (для форточек с поддержкой точного позиционирования).",
      "auto_resume": "Вкл: вручную переключенное устройство вернется в авторежим через Автовозврат через. Выкл: устройство остается в текущем состоянии, пока вы не нажмете Возобновить авторежим.",
      "auto_resume_hours": "Сколько времени переключенное вручную устройство остается без изменений, прежде чем ZoneFlow снова возьмет его под контроль (при включенном Автовозврате).",
      "manual_rain_mm": "Количество осадков, измеренное обычным дождемером. Нажмите Добавить дождь, чтобы сохранить значение; показатель сбросится на 0.",
      "zone_flow_l_min": "Сколько дает вся зона в минуту (капельницы x расход на капельницу). Используется только для оценки литров; не меняет время и объем полива зоны. Оставьте 0, если не знаете.",
      "sensor_offline_hours": "Датчик, который ничего не передаёт столько часов, считается офлайн, и управление климатом переходит в аварийный режим. Увеличьте значение, если стабильный датчик вызывает ложные предупреждения.",
      "ventilation_failsafe": "Поведение форточек и вентиляторов при отказе датчика температуры внутри. Туманообразование всегда отключается.",
      "heater_failsafe": "Поведение обогревателя при отказе датчика температуры внутри. Без датчика непрерывная работа запрещена.",
      "misting_trigger": "Условие запуска тумана: любое из условий либо только температура, влажность или освещенность."
    },
    "garden": {
      "none": "Без участка",
      "new": "Новый участок…",
      "name": "Название участка"
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
      "water_use": "Odhad spotreby vody",
      "water_use_note": "Slúži len na výpočet litrov pre údaje o spotrebe vody. Nemení, kedy ani ako dlho zóna zavlažuje. Ak hodnotu nepoznáte, ponechajte 0.",
      "rain": "Dážď, predpoveď a mráz",
      "deep_soak": "Hĺbková zálievka",
      "soil": "Pôda",
      "growth": "Rast",
      "deficit": "Deficitný režim",
      "history": "História",
      "safety": "Bezpečnostné limity a čerpadlo",
      "notifications": "Oznámenia",
      "more": "Viac",
      "climate": "Riadenie klímy",
      "misting": "Zahmlievanie",
      "garden": "Záhradná oblasť"
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
      "feed_due": "Pohnojiť teraz",
      "other_area": "Ostatné"
    },
    "close": "Zavrieť",
    "device_page": "Otvoriť stránku zariadenia",
    "fertilized": "Pohnojené",
    "mark_watered": "Označiť ako zaliate",
    "add_rain": "Pridať dážď",
    "resume_automatic": "Obnoviť automatiku",
    "crops": "Plodiny",
    "in_greenhouse": "V skleníku",
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
      "rain_eff_high": "Podiel silného dažďa, ktorý sa skutočne dostane ku koreňom. Zvyšok odtečie alebo sa odparí.",
      "heat_temp": "Ohrievač sa zapne, keď vnútorná teplota klesne pod túto hodnotu, a vypne o niečo vyššie (pozri Hysterézia klímy).",
      "vent_temp": "Vetranie sa otvorí, keď vnútorná teplota dosiahne túto hodnotu, a iba vtedy, keď je vonkajší vzduch chladnejší ako vnútorný.",
      "fan_temp": "Ventilátory sa zapnú pri tejto vnútornej teplote (pri alebo nad teplotou vetrania) a iba vtedy, keď je vonkajší vzduch chladnejší ako vnútorný.",
      "climate_hysteresis": "Medzera medzi zapnutím a vypnutím zariadenia, aby sa nezapínalo a nevypínalo neustále okolo jednej teploty.",
      "outside_margin": "Vetranie sa spustí iba vtedy, keď je vonkajší vzduch aspoň o toliko chladnejší ako vnútorný, aby sa nikdy nevťahoval horúcejší vzduch.",
      "max_humidity": "Ventilátory a vetranie bežia aj vtedy, keď je vnútorná vlhkosť nad touto hodnotou, pokiaľ nie je chladno.",
      "mist_temp": "Zahmlievanie sa môže spustiť, keď je vnútorná teplota na alebo nad touto hodnotou.",
      "mist_min_humidity": "Zahmlievanie sa môže spustiť, keď vnútorná vlhkosť klesne na túto alebo nižšiu hodnotu.",
      "mist_stop_humidity": "Zahmlievanie nikdy nebeží, keď je vnútorná vlhkosť na alebo nad touto hodnotou.",
      "mist_min_temp": "Žiadne zahmlievanie pod touto vnútornou teplotou.",
      "mist_light_level": "Zahmlievanie sa môže spustiť, keď hodnota osvetlenia dosiahne túto úroveň (vyžaduje senzor osvetlenia).",
      "mist_on_seconds": "Ako dlho trvá každý impulz zahmlievania.",
      "mist_off_seconds": "Pauza medzi impulzmi zahmlievania.",
      "max_mist_minutes_per_hour": "Pevný limit pre zahmlievanie počas akýchkoľvek 60 minút. Zahmlievač zapnutý ručne sa po tomto čase tiež vypne.",
      "vent_open_pct": "Ako veľmi sa vetranie otvorí (pre vetranie, ktoré je možné nastaviť do polohy).",
      "auto_resume": "Zapnuté: ručne prepnuté zariadenie sa vráti do automatického režimu po uplynutí Zpoždenia automatického návratu. Vypnuté: zostane v stave, v akom ste ho nechali, kým nestlačíte Obnoviť automatiku.",
      "auto_resume_hours": "Ako dlho zostane ručne prepnuté zariadenie bez zásahu, kým nad ním ZoneFlow opäť prevezme kontrolu (keď je zapnutý Automatický návrat).",
      "manual_rain_mm": "Množstvo zrážok odčítané z obyčajného zrážkomera. Stlačte Pridať dážď na uloženie; hodnota sa potom vynuluje.",
      "zone_flow_l_min": "Čo celá zóna dáva za minútu (emitory x prietok na emitor). Používa sa len na odhad litrov; nemení to, kedy alebo koľko zóna zavlažuje. Ak ho nepoznáte, ponechajte 0.",
      "sensor_offline_hours": "Senzor, ktorý toľko hodín nič nepošle, sa považuje za offline a riadenie klímy prejde do núdzového režimu. Zvýšte hodnotu, ak stabilný senzor spôsobuje falošné varovania.",
      "ventilation_failsafe": "Čo robia vetranie a ventilátory, keď nefunguje žiaden senzor vnútornej teploty. Zahmlievače sa vždy vypnú.",
      "heater_failsafe": "Čo robí ohrievač, keď nefunguje žiaden senzor vnútornej teploty. Bez senzora nikdy nebeží nepretržite.",
      "misting_trigger": "Čo spúšťa zahmlievanie: akýkoľvek zo spúšťačov, alebo iba teplota, vlhkosť či svetlo."
    },
    "garden": {
      "none": "Bez oblasti",
      "new": "Nová oblasť…",
      "name": "Názov oblasti"
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
      "water_use": "Оцінка використання води",
      "water_use_note": "Використовується лише для розрахунку літрів у даних про використання води. Не впливає на те, коли і як довго зона поливає. Залиште 0, якщо не знаєте.",
      "rain": "Дощ, прогноз і заморозки",
      "deep_soak": "Глибокий полив",
      "soil": "Ґрунт",
      "growth": "Ріст",
      "deficit": "Дефіцитний полив",
      "history": "Історія",
      "safety": "Запобіжні ліміти й насос",
      "notifications": "Сповіщення",
      "more": "Більше",
      "climate": "Клімат-контроль",
      "misting": "Туманоутворення",
      "garden": "Ділянка саду"
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
      "feed_due": "Підживити зараз",
      "other_area": "Інше"
    },
    "close": "Закрити",
    "device_page": "Відкрити сторінку пристрою",
    "fertilized": "Підживлено",
    "mark_watered": "Позначити полив",
    "add_rain": "Додати дощ",
    "resume_automatic": "Vidnovyty avtomatyku",
    "crops": "Культури",
    "in_greenhouse": "У теплиці",
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
      "rain_eff_high": "Частка сильного дощу, яка дійсно досягає коріння. Решта випаровується або стікає.",
      "heat_temp": "Обігрівач вмикається, коли температура всередині падає нижче цього значення, і вимикається трохи вище за нього (див. «Гістерезис клімату»).",
      "vent_temp": "Кватирки відкриваються, коли температура всередині досягає цього значення, і лише якщо повітря зовні холодніше за внутрішнє.",
      "fan_temp": "Вентилятори вмикаються при цій температурі всередині (рівній або вищій за температуру відкриття кватирок) і лише якщо повітря зовні холодніше.",
      "climate_hysteresis": "Інтервал між увімкненням і вимкненням пристрою, щоб запобігти частому спрацьовуванню біля однієї точки температури.",
      "outside_margin": "Провітрювання починається лише тоді, коли зовнішнє повітря холодніше за внутрішнє щонайменше на це значення, щоб не затягувати спеку.",
      "max_humidity": "Вентилятори та кватирки також працюють, коли вологість всередині перевищує це значення, якщо надворі не холодно.",
      "mist_temp": "Туманоутворення може вмикатися, коли температура всередині досягає цього значення або вища за нього.",
      "mist_min_humidity": "Туманоутворення може вмикатися, коли вологість всередині падає до цього значення або нижче.",
      "mist_stop_humidity": "Туманоутворення ніколи не працює, якщо вологість всередині досягає цього значення або перевищує його.",
      "mist_min_temp": "Туманоутворення заборонено при температурі всередині нижче цієї межі.",
      "mist_light_level": "Туманоутворення може вмикатися при досягненні цього рівня освітленості (потрібен датчик освітленості).",
      "mist_on_seconds": "Тривалість кожного імпульсу туманоутворення.",
      "mist_off_seconds": "Тривалість паузи між імпульсами туманоутворення.",
      "max_mist_minutes_per_hour": "Строге обмеження загального часу туманоутворення за будь-які 60 хвилин. Туманоутворювач, увімкнений вручну, також вимкнеться після цього часу.",
      "vent_open_pct": "Ступінь відкриття кватирок (для кватирок із підтримкою позиціонування).",
      "auto_resume": "Увімкнено: пристрій, переключений вручну, повертається до авторежиму через Автоматичне відновлення через. Вимкнено: залишається у вибраному стані, поки ви не натиснете Відновити авторежим.",
      "auto_resume_hours": "Скільки часу пристрій, переключений вручну, залишається без змін, перш ніж ZoneFlow знову візьме його під контроль (коли Автоматичне відновлення увімкнено).",
      "manual_rain_mm": "Кількість осадків з простого дощоміра. Натисніть Додати дощ, щоб зберегти; значення скинеться на 0.",
      "zone_flow_l_min": "Скільки дає вся зона за хвилину (крапельниці x витрата на крапельницю). Використовується лише для оцінки літрів; не змінює час або об'єм поливу зони. Залиште 0, якщо не знаєте.",
      "sensor_offline_hours": "Датчик, який нічого не передає стільки годин, вважається офлайн, і керування кліматом переходить в аварійний режим. Збільште значення, якщо стабільний датчик спричиняє хибні попередження.",
      "ventilation_failsafe": "Дія кватирок і вентиляторів при несправності всіх внутрішніх датчиків температури. Туманоутворювачі завжди вимикаються.",
      "heater_failsafe": "Дія обігрівача при несправності всіх внутрішніх датчиків температури. Він ніколи не працює безперервно без датчика.",
      "misting_trigger": "Що саме запускає туманоутворення: будь-який із тригерів або лише температура, вологість чи освітленість."
    },
    "garden": {
      "none": "Без ділянки",
      "new": "Нова ділянка…",
      "name": "Назва ділянки"
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
      "water_use": "用水量估算",
      "water_use_note": "仅用于计算用水量数据中的升数。不会改变区域何时浇水或浇水多久。不知道时请保持为 0。",
      "rain": "降雨、预报和霜冻",
      "deep_soak": "深层浇灌",
      "soil": "土壤",
      "growth": "生长",
      "deficit": "控水模式",
      "history": "历史",
      "safety": "安全限制与水泵",
      "notifications": "通知",
      "more": "更多",
      "climate": "环境控制",
      "misting": "喷雾",
      "garden": "花园地块"
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
      "feed_due": "立即施肥",
      "other_area": "其他"
    },
    "close": "关闭",
    "device_page": "打开设备页面",
    "fertilized": "已施肥",
    "mark_watered": "标记为已浇水",
    "add_rain": "添加降雨",
    "resume_automatic": "恢复自动",
    "crops": "作物",
    "in_greenhouse": "温室内",
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
      "rain_eff_high": "大雨中实际渗透至根系有效吸收层的比例，其余部分会蒸发或形成地表径流。",
      "heat_temp": "当室内温度低于此值时开启加热器，高于此值一定幅度时再次关闭（参见“气候控制迟滞”）。",
      "vent_temp": "当室内温度达到此值且室外空气比室内凉爽时，打开通风口。",
      "fan_temp": "当室内温度达到此值（高于或等于通风口打开温度）且室外空气比室内凉爽时，开启风扇。",
      "climate_hysteresis": "设备开启和关闭之间的温度差，防止设备在单一温度点附近频繁开关。",
      "outside_margin": "仅当室外空气至少比室内凉爽此数值时才开启通风，以防吸入更热的空气。",
      "max_humidity": "当室内湿度高于此值且天气不冷时，也将运行通风口和风扇。",
      "mist_temp": "当室内温度达到或高于此值时可以启动喷雾。",
      "mist_min_humidity": "当室内湿度降至或低于此值时可以启动喷雾。",
      "mist_stop_humidity": "当室内湿度达到或高于此值时，绝不运行喷雾。",
      "mist_min_temp": "低于此室内温度时不进行喷雾。",
      "mist_light_level": "当光照读数达到此数值时可以启动喷雾（需要光照传感器）。",
      "mist_on_seconds": "每次喷雾脉冲的持续时间。",
      "mist_off_seconds": "喷雾脉冲之间的休息间隔。",
      "max_mist_minutes_per_hour": "任何 60 分钟内喷雾总时长的硬性限制。手动开启的喷雾器也会在此时长后自动关闭。",
      "vent_open_pct": "通风口打开的位置程度（适用于支持设置位置的通风口）。",
      "auto_resume": "开启：手动切换的设备将在“自动恢复延迟”后恢复自动模式。关闭：保持原状，直到您点击“恢复自动”。",
      "auto_resume_hours": "手动切换的设备在 ZoneFlow 接管控制之前保持原状的时间（当“自动恢复”开启时）。",
      "manual_rain_mm": "从普通雨量计读取的降雨量。点击“添加降雨”进行记录，数值将清零。",
      "zone_flow_l_min": "整个区域每分钟的出水量（灌水器数量 x 每个灌水器的流量）。仅用于估算升数；不会改变区域的浇水时间或浇水量。如果不知道请保持为 0。",
      "sensor_offline_hours": "传感器在这么多小时内没有任何上报即视为离线，气候控制将进入故障安全模式。如果数值稳定的传感器引起误报，请调高此值。",
      "ventilation_failsafe": "当没有可用的室内温度传感器时通风口和风扇的动作。喷雾器将始终关闭。",
      "heater_failsafe": "当没有可用的室内温度传感器时加热器的动作。在没有传感器的情况下，它绝不会不间断连续运行。",
      "misting_trigger": "触发喷雾的条件：满足任意触发条件，或仅限温度、湿度或光照。"
    },
    "garden": {
      "none": "无地块",
      "new": "新地块…",
      "name": "地块名称"
    }
  }
};

// Where each entity goes, by "<domain>.<translation key>". Anything not
// listed lands by its category: settings -> "More", diagnostics ->
// Diagnostics, everyday -> Now. So entities added later appear by themselves.
const NOW = [
  // Greenhouse / indoor zones (1.6)
  "sensor.greenhouse_status",
  "sensor.inside_vpd",
  "binary_sensor.ventilation_allowed",
  "sensor.misting_today",
  "sensor.soil_moisture",
  "sensor.soil_moisture_status",
  "sensor.next_irrigation_estimate",
  "sensor.days_until_next_run",
  "sensor.next_fertilizing",
  "sensor.last_cycle_water_liters",
  "sensor.last_water_delivered",
  "sensor.last_water_volume",
  "sensor.rain_today",
  "sensor.routine_weekly_target",
  "sensor.avg_peak_temp_3d",
  "sensor.water_used_30d",
  "sensor.water_used_year",
  "sensor.growth_ramp_pct",
  "sensor.deficit_status",
];
// Shown only while they say something (deficit mode on).
const ONLY_WHEN = {
  // Litres need a Zone Flow or a flow meter.
  "sensor.last_water_volume": (state) => state && !["unknown", "unavailable"].includes(state.state),
  "sensor.water_used_30d": (state) => state && !["unknown", "unavailable"].includes(state.state),
  "sensor.water_used_year": (state) => state && !["unknown", "unavailable"].includes(state.state),
  "sensor.deficit_status": (state) => state && state.state !== "off",
  // Once a first feed is recorded.
  "sensor.next_fertilizing": (state) => state && !["unknown", "unavailable"].includes(state.state),
};
const CONTROLS = ["switch.greenhouse_control", "switch.pause", "datetime.paused_until", "switch.deficit_mode"];
const JOURNAL = ["select.health_status", "text.health_notes", "datetime.last_fertilizing", "select.fertilizing_interval"];
const SETTINGS_GROUPS = [
  ["garden", ["text.garden_area"]],
  ["climate", [
    "number.heat_temp", "number.vent_temp", "number.fan_temp", "number.climate_hysteresis",
    "number.outside_margin", "number.max_humidity", "number.vent_open_pct", "switch.auto_resume", "number.auto_resume_hours",
    "number.sensor_offline_hours", "select.ventilation_failsafe", "select.heater_failsafe",
  ]],
  ["misting", [
    "select.misting_trigger", "switch.mist_at_night", "number.mist_temp", "number.mist_min_humidity",
    "number.mist_stop_humidity", "number.mist_min_temp", "number.mist_light_level",
    "number.mist_on_seconds", "number.mist_off_seconds", "number.max_mist_minutes_per_hour",
  ]],
  ["amounts", [
    "number.flow_rate_mm_per_min", "number.target_weekly_mm", "number.target_weekly_hot_mm",
    "number.target_weekly_cool_mm", "select.demand_model", "number.crop_coefficient",
    "number.hot_temp_threshold", "number.cool_temp_threshold", "number.fallback_temp",
    "number.routine_pulse_count", "number.routine_pulse_rest_minutes",
  ]],
  ["water_use", ["number.zone_flow_l_min"]],
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
  "button.service_run_10_min", "button.service_run_15_min", "button.fertilized_today", "button.mark_watered",
  "number.manual_rain_mm", "button.add_manual_rain", "button.resume_automatic",
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
        if (when && !when(this._hass.states[e.entity_id])) return false;
        // A meter that has counted nothing says nothing; the litres estimate
        // (Last Water Volume) stands in for it.
        if (key === "sensor.last_cycle_water_liters" && !(Number(this._hass.states[e.entity_id]?.state) > 0)) return false;
        // With a flow meter that counted, its litres are on the card already.
        if (key === "sensor.last_water_volume") {
          const measured = entities["sensor.last_cycle_water_liters"];
          const litres = Number(this._hass.states[measured?.entity_id]?.state);
          if (measured && !measured.hidden && litres > 0) return false;
        }
        return true;
      })
    );
    const statusAttrs = this._hass.states[visible["sensor.status"]?.entity_id]?.attributes || {};
    const valve = statusAttrs.valve;
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
      statusAttrs.greenhouse || null,
      statusAttrs.crops || null,
    ]);
    if (signature !== this._signature) {
      this._signature = signature;
      this._build(visible, valve, statusAttrs);
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

  _build(visible, valve, statusAttrs = {}) {
    const hass = this._hass;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const root = this.shadowRoot;
    this._buildId = (this._buildId || 0) + 1;
    this._open = this._open || {};
    this._cropList = undefined;
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
      .in-greenhouse { display: flex; align-items: center; gap: 6px; padding: 0 16px 8px; margin-top: -6px;
        color: var(--secondary-text-color); font-size: 0.9em; }
      .in-greenhouse ha-icon { --mdc-icon-size: 16px; }
      .crops zoneflow-overview-card { display: block; margin: 0 -12px; }
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
      .area-row { display: flex; align-items: center; gap: 8px; padding: 6px 16px; min-height: 40px; }
      .area-label { flex: 1; min-width: 0; }
      .area-select, .area-input { font: inherit; color: var(--primary-text-color); background: var(--secondary-background-color);
        border: 1px solid var(--divider-color); border-radius: 6px; padding: 6px 8px; max-width: 55%; min-width: 0; }
      .group-note { color: var(--secondary-text-color); font-size: 0.85em; margin: -4px 0 8px; line-height: 1.35; }
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
    icon.setAttribute(
      "icon",
      this._config.icon || (visible["sensor.greenhouse_status"] && !visible["sensor.status"] ? "mdi:greenhouse" : "mdi:sprinkler-variant")
    );
    const title = document.createElement("div");
    title.className = "title";
    title.textContent = this._config.title || device?.name_by_user || device?.name || t(hass, "zone");
    header.append(icon, title);
    card.appendChild(header);
    this._statusEl = document.createElement("div");
    this._statusEl.className = "status";
    card.appendChild(this._statusEl);
    // A crop: which greenhouse it is in.
    if (statusAttrs.greenhouse?.name) {
      const where = document.createElement("div");
      where.className = "in-greenhouse";
      const whereIcon = document.createElement("ha-icon");
      whereIcon.setAttribute("icon", "mdi:greenhouse");
      where.append(whereIcon, document.createTextNode(`${t(hass, "in_greenhouse")}: ${statusAttrs.greenhouse.name}`));
      card.appendChild(where);
    }

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
      ...buttons([["button.resume_automatic", t(hass, "resume_automatic"), "mdi:play-circle-outline"]]),
      // Manual rain (outdoor zones without a rain gauge): the amount, then
      // the button that records it.
      ...rows(["number.manual_rain_mm"]),
      ...buttons([["button.add_manual_rain", t(hass, "add_rain"), "mdi:weather-pouring"]]),
    ];
    const minutes = t(hass, "min");
    const service = [
      ...rows(["switch.service_mode"]),
      ...buttons([
        ["button.service_run_1_min", `1 ${minutes}`, "mdi:timer-outline"],
        ["button.service_run_5_min", `5 ${minutes}`, "mdi:timer-outline"],
        ["button.service_run_10_min", `10 ${minutes}`, "mdi:timer-outline"],
        ["button.service_run_15_min", `15 ${minutes}`, "mdi:timer-outline"],
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
    // A greenhouse: its crops, as in the overview card (status, next and
    // last watering, Water now; tap one for its full card).
    const crops = (statusAttrs.crops || []).map((c) => c.device_id).filter(Boolean);
    if (crops.length && this._config.show_crops !== false) {
      const el = document.createElement("div");
      el.className = "section crops";
      const heading = document.createElement("div");
      heading.className = "section-title";
      heading.textContent = t(hass, "crops");
      const list = document.createElement("zoneflow-overview-card");
      list.setConfig({ device_ids: crops, embedded: true, show_add: false });
      list.hass = hass;
      el.append(heading, list);
      card.appendChild(el);
      this._cropList = list;
    } else {
      this._cropList = undefined;
    }
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
        // Some groups say in plain words what their settings are for.
        const noteText = t(hass, `groups.${groupKey}_note`);
        if (noteText && !noteText.startsWith("groups.")) {
          const note = document.createElement("div");
          note.className = "group-note";
          note.textContent = noteText;
          body.appendChild(note);
        }
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

  _areaRow(conf) {
    // The Garden Area field as a dropdown of the areas in use (Home Assistant's
    // own text row would need the name typed), with "New area..." for a new one.
    const wrap = document.createElement("div");
    wrap.className = "area-row";
    const label = document.createElement("span");
    label.className = "area-label";
    const select = document.createElement("select");
    select.className = "area-select";
    const input = document.createElement("input");
    input.type = "text";
    input.className = "area-input";
    input.maxLength = 40;
    input.hidden = true;
    wrap.append(label, select, input);
    const NEW = "__new__";
    let shown = null;
    const save = (value) => this._hass.callService("text", "set_value", { entity_id: conf.entity, value });
    select.addEventListener("change", () => {
      if (select.value === NEW) {
        input.hidden = false;
        input.placeholder = t(this._hass, "garden.name");
        input.focus();
        return;
      }
      input.hidden = true;
      save(select.value);
    });
    input.addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter") return;
      const value = input.value.trim();
      if (!value) return;
      input.hidden = true;
      input.value = "";
      save(value);
    });
    Object.defineProperty(wrap, "hass", {
      set: (hass) => {
        const raw = hass.states?.[conf.entity]?.state;
        const current = raw && !["unknown", "unavailable"].includes(raw) ? raw : "";
        const names = gardenAreas(hass);
        if (current && !names.some((n) => n.toLowerCase() === current.toLowerCase())) names.push(current);
        const signature = JSON.stringify([names, current, hass.locale?.language, conf.name]);
        if (signature === shown) return;
        shown = signature;
        label.textContent = conf.name || t(hass, "groups.garden");
        select.textContent = "";
        const option = (value, text) => {
          const el = document.createElement("option");
          el.value = value;
          el.textContent = text;
          select.appendChild(el);
        };
        option("", t(hass, "garden.none"));
        for (const name of names) option(name, name);
        option(NEW, t(hass, "garden.new"));
        select.value = names.find((n) => n.toLowerCase() === current.toLowerCase()) || "";
        input.hidden = true;
      },
    });
    return wrap;
  }

  _addRows(list, confs) {
    const build = this._buildId;
    this._helpers().then(
      (helpers) => {
        if (build !== this._buildId) return; // rebuilt meanwhile
        for (const raw of confs) {
          const conf = this._shortName(raw);
          const add = (before) => {
            const isArea = this._hass.entities?.[conf.entity]?.translation_key === "garden_area";
            const row = isArea ? this._areaRow(conf) : helpers.createRowElement(conf);
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
    if (this._cropList) this._cropList.hass = this._hass;
    const hass = this._hass;
    for (const row of this._rows || []) row.hass = hass;
    if (!this._statusEl) return;
    // A zone that waters shows its watering status; one that only
    // controls the climate shows the climate status.
    const status = hass.states[(visible["sensor.status"] || visible["sensor.greenhouse_status"])?.entity_id];
    const code = status?.attributes?.code;
    this._statusEl.textContent = status ? status.state : "";
    this._statusEl.classList.toggle("warn", ["lock_held", "refused_daily_cap", "refused_runtime_cap",
      "refused_deep_soak_cap", "interrupted", "failsafe", "mist_halted"].includes(code));
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
// Climate-only zones (no valve): the status text comes from the zone itself
// (already in the user's language); only the icon and warning are chosen here.
const CLIMATE_STATUS = {
  climate_failsafe: ["mdi:alert-circle-outline", true],
  climate_mist_halted: ["mdi:alert-circle-outline", true],
  climate_heating: ["mdi:radiator", false],
  climate_ventilating_temperature: ["mdi:fan", false],
  climate_ventilating_humidity: ["mdi:fan", false],
  climate_misting: ["mdi:water-outline", false],
  climate_held: ["mdi:hand-back-right-outline", false],
  climate_control_off: ["mdi:power-off", false],
  climate_gate_blocked: ["mdi:window-closed-variant", false],
  climate_idle: ["mdi:check-circle-outline", false],
};

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

function gardenAreas(hass) {
  // The garden areas in use by any zone, each name once (letter case aside), by name.
  const names = new Map();
  for (const zone of allZones(hass)) {
    const area = hass.states?.[zone.status]?.attributes?.garden_area;
    if (area && !names.has(area.toLowerCase())) names.set(area.toLowerCase(), area);
  }
  return [...names.values()].sort((a, b) => a.localeCompare(b, hass.locale?.language || undefined));
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
      // The meter's litres once it has counted something; else the estimate.
      const metered = Boolean(measured && !measured.hidden && Number(hass.states[measured.entity_id]?.state) > 0);
      const last = metered ? measured.entity_id : estimate?.entity_id;
      const lastVolume = keyed["sensor.last_water_volume"];
      const button = keyed["button.run_routine"]?.entity_id;
      const plant = status?.attributes?.plant;
      // A zone with no valve to water has no irrigation status: it shows
      // its climate status instead.
      const climateEntry = keyed["sensor.greenhouse_status"];
      const climate = climateEntry && !climateEntry.hidden && keyed["sensor.status"]?.hidden ? climateEntry : null;
      const climateState = climate ? hass.states[climate.entity_id] : null;
      const feed = hass.states[keyed["sensor.next_fertilizing"]?.entity_id];
      return {
        ...zone,
        icon: this._config.icons?.[zone.device_id] || (climate ? "mdi:greenhouse" : PLANT_ICONS[plant] || DEFAULT_ZONE_ICON),
        code: climate ? `climate_${climateState?.attributes?.code || ""}` : status?.attributes?.code,
        text: climate ? climateState?.state : status?.state,
        next: climate ? undefined : status?.attributes?.next_watering,
        last: climate ? undefined : last,
        lastIsEstimate: !metered,
        lastVolume: climate || !lastVolume || lastVolume.hidden ? undefined : lastVolume.entity_id,
        button: climate ? undefined : button,
        feed: feed && !["unknown", "unavailable"].includes(feed.state) ? feed.state : null,
        feedDue: Boolean(feed?.attributes?.due),
        parent: status?.attributes?.greenhouse?.device_id || null,
        area: status?.attributes?.garden_area || null,
      };
    });
    const byName = (a, b) => a.name.localeCompare(b.name, hass.locale?.language);
    if (this._config.sort === "next") {
      const rank = (z) => (z.code === "paused" || !z.next ? Infinity : new Date(z.next).getTime());
      zones.sort((a, b) => rank(a) - rank(b) || byName(a, b));
    } else {
      zones.sort(byName);
    }
    const only = this._config.device_ids;
    const shown = Array.isArray(only) ? zones.filter((z) => only.includes(z.device_id)) : zones;
    // A greenhouse's crops right under it.
    const ids = new Set(shown.map((z) => z.device_id));
    const ordered = [];
    for (const zone of shown) {
      if (zone.parent && ids.has(zone.parent)) continue;
      ordered.push(zone);
      ordered.push(...shown.filter((z) => z.parent === zone.device_id).map((z) => ({ ...z, crop: true })));
    }
    // Garden areas: the zones under their area's heading (areas by name, the
    // zones with no area last). Without any area nothing changes.
    if (ordered.some((z) => z.area)) {
      const groups = new Map();
      for (const z of ordered) {
        const key = z.area || "";
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(z);
      }
      const names = [...groups.keys()].sort((a, b) => (a === "" ? 1 : b === "" ? -1 : a.localeCompare(b, hass.locale?.language)));
      return names.flatMap((name) => groups.get(name).map((z, i) => ({ ...z, areaStart: i === 0, areaName: name })));
    }
    return ordered;
  }

  _render() {
    if (!this._config || !this._hass) return;
    const zones = this._zones();
    const signature = JSON.stringify([
      zones.map((z) => [z.device_id, z.name, z.icon, z.last, z.button, z.crop || false, z.area || null, z.areaStart || false]),
      this._config.device_ids || null,
      this._config.embedded || false,
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
      .zone.crop { margin-left: 36px; }
      .area-title { margin: 14px 12px 6px; font-size: 0.85em; font-weight: 500; letter-spacing: 0.04em;
        text-transform: uppercase; color: var(--secondary-text-color); }
      ${this._config.embedded ? `
      ha-card { box-shadow: none; border: none; background: none; }
      .title { display: none; }` : ""}
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
      if (zone.areaStart) {
        const heading = document.createElement("div");
        heading.className = "area-title";
        heading.textContent = zone.areaName || tr("other_area");
        card.appendChild(heading);
      }
      const wrap = document.createElement("div");
      wrap.className = zone.crop ? "zone crop" : "zone";
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
    // Crops are listed here already: not again inside their greenhouse.
    inner.setConfig({ device_id: zone.device_id, show_journal: false, show_settings: true, embedded: true, show_crops: false });
    inner.hass = this._hass;
    details.append(inner);
  }

  _update(zones) {
    const hass = this._hass;
    for (const zone of zones) {
      const row = this._rows?.[zone.device_id];
      if (!row) continue;
      const climateLook = CLIMATE_STATUS[zone.code];
      const [labelKey, icon, warn] = climateLook
        ? [null, climateLook[0], climateLook[1]]
        : STATUS_LABELS[zone.code] || [null, "mdi:help-circle-outline", false];
      row.statusIcon.setAttribute("icon", icon);
      row.statusText.textContent = labelKey ? t(hass, `overview.labels.${labelKey}`) : zone.text || "—";
      row.status.title = zone.text || "";
      row.status.classList.toggle("warn", warn);
      row.next.textContent = zone.code === "paused" ? "—" : formatNext(hass, zone.next);
      row.last.textContent = zone.last ? formatState(hass, hass.states[zone.last]) : "—";
      const volume = zone.lastVolume ? hass.states[zone.lastVolume] : null;
      if (zone.last && volume && !["unknown", "unavailable"].includes(volume.state) && zone.lastIsEstimate) {
        row.last.textContent += ` · ${formatState(hass, volume)}`;
      }
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

// A ready-made dashboard: an overview tab and one tab per zone, built from
// the zones that exist each time the dashboard opens -- so a new zone
// appears by itself. Settings -> Dashboards -> Add dashboard -> new from
// scratch, then in its raw editor:
//
//   strategy:
//     type: custom:zoneflow
//
// (Home Assistant's own "take control" turns it into a normal dashboard to
// edit by hand.) The tabs reuse the two cards above.
function slug(text) {
  return String(text || "zone")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "zone";
}

function zoneIcon(hass, zone) {
  const registry = Object.values(hass.entities || {});
  // Greenhouse and indoor zones have a climate status of their own.
  // (A crop has the entity too, hidden: it has no climate of its own.)
  const climate = registry.some(
    (e) => e.platform === "zoneflow" && e.device_id === zone.device_id && e.translation_key === "greenhouse_status" && !e.hidden
  );
  if (climate) return "mdi:greenhouse";
  const plant = hass.states?.[zone.status]?.attributes?.plant;
  return PLANT_ICONS[plant] || DEFAULT_ZONE_ICON;
}

function buildDashboard(hass) {
  const zones = allZones(hass).sort((a, b) => a.name.localeCompare(b.name, hass.locale?.language || undefined));
  const views = [];
  if (!zones.length) {
    return {
      title: "ZoneFlow",
      views: [{
        title: "ZoneFlow",
        path: "zoneflow",
        icon: DEFAULT_ZONE_ICON,
        cards: [{ type: "markdown", content: "No ZoneFlow zones yet. Add one under Settings → Devices & services." }],
      }],
    };
  }
  // Use the whole width: one card fills the page ("panel"); a greenhouse
  // with crops lays its cards out side by side.
  views.push({
    title: t(hass, "overview.title"),
    path: "overview",
    icon: "mdi:view-dashboard-outline",
    type: "panel",
    cards: [{ type: "custom:zoneflow-overview-card" }],
  });
  const used = new Set(["overview"]);
  const unique = (name) => {
    let path = slug(name);
    for (let n = 2; used.has(path); n += 1) path = `${slug(name)}-${n}`;
    used.add(path);
    return path;
  };
  const parentOf = (zone) => hass.states?.[zone.status]?.attributes?.greenhouse?.device_id || null;
  const areaOf = (zone) => hass.states?.[zone.status]?.attributes?.garden_area || null;
  const ids = new Set(zones.map((z) => z.device_id));
  const cardsFor = (zone) => {
    // A greenhouse's crops have their own cards beside it: not listed again.
    const crops = zones.filter((z) => parentOf(z) === zone.device_id);
    return [
      { type: "custom:zoneflow-card", device_id: zone.device_id, ...(crops.length ? { show_crops: false } : {}) },
      ...crops.map((c) => ({ type: "custom:zoneflow-card", device_id: c.device_id })),
    ];
  };
  const tops = zones.filter((z) => !ids.has(parentOf(z))); // not a crop
  // Garden areas: one tab per area, its zones side by side.
  const areas = new Map();
  for (const zone of tops) {
    const area = areaOf(zone);
    if (!area) continue;
    if (!areas.has(area)) areas.set(area, []);
    areas.get(area).push(zone);
  }
  const areaNames = [...areas.keys()].sort((a, b) => a.localeCompare(b, hass.locale?.language || undefined));
  for (const area of areaNames) {
    const cards = areas.get(area).flatMap(cardsFor);
    views.push({
      title: area,
      path: unique(area),
      icon: "mdi:flower-outline",
      ...(cards.length === 1 ? { type: "panel" } : {}),
      cards,
    });
  }
  for (const zone of tops) {
    if (areaOf(zone)) continue; // on its area's tab
    const cards = cardsFor(zone);
    views.push({
      title: zone.name,
      path: unique(zone.name),
      icon: cards.length > 1 ? "mdi:greenhouse" : zoneIcon(hass, zone),
      ...(cards.length > 1 ? {} : { type: "panel" }),
      cards,
    });
  }
  return { title: "ZoneFlow", views };
}

class ZoneFlowDashboardStrategy extends HTMLElement {
  static async generate(config, hass) {
    return buildDashboard(hass);
  }

  static async generateDashboard(info) {
    return buildDashboard(info.hass);
  }
}
// The loader (frontend.py) registers the element early, because Home
// Assistant waits only 5 s for it; it hands over to this one.
window.__zoneflowDashboardStrategy = ZoneFlowDashboardStrategy;

// Defined as soon as this file loads -- and again if Home Assistant's
// frontend replaces the page's custom-element registry afterwards (it can
// install a scoped-registry polyfill after early-loaded modules like this
// one have run; definitions made before that are then invisible to it).
const ELEMENTS = [
  ["zoneflow-card", ZoneFlowCard],
  ["zoneflow-card-editor", ZoneFlowCardEditor],
  ["zoneflow-overview-card", ZoneFlowOverviewCard],
  ["zoneflow-overview-card-editor", ZoneFlowOverviewCardEditor],
  // The dashboard strategy: `strategy: {type: custom:zoneflow}`.
  ["ll-strategy-dashboard-zoneflow", ZoneFlowDashboardStrategy],
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
