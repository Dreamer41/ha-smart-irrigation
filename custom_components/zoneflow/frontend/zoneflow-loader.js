// ZoneFlow Irrigation: loads the ZoneFlow dashboard cards.
// Shipped with the ZoneFlow integration, served from /zoneflow_static/ and
// listed under Settings -> Dashboards -> Resources.
//
// Home Assistant can show a dashboard while it is still starting, before
// ZoneFlow has loaded. This keeps trying until the cards are there.
const defineStrategy = () => {
  const tag = "ll-strategy-dashboard-zoneflow";
  if (window.customElements.get(tag)) return;
  try {
    window.customElements.define(tag, class extends HTMLElement {
      static async generate(config, hass) {
        for (let waited = 0; !window.__zoneflowDashboardStrategy; waited += 250) {
          if (waited >= 60000) throw new Error("The ZoneFlow card did not load.");
          await new Promise((resolve) => setTimeout(resolve, 250));
        }
        return window.__zoneflowDashboardStrategy.generate(config, hass);
      }
    });
  } catch (err) {
    // Known to the registry already: nothing to do.
  }
};
defineStrategy();
for (const delay of [250, 1000, 3000, 10000]) setTimeout(defineStrategy, delay);
const base = "/zoneflow_static/zoneflow-card.js";
const query = new URL(import.meta.url).search;
let tries = 0;
const load = () => {
  if (window.customElements.get("zoneflow-overview-card")) return;
  // The same URL as the one on the page: the browser loads it only once.
  const url = query && !tries ? base + query : `${base}?t=${Date.now()}`;
  import(url).catch(() => {
    tries += 1;
    if (tries < 120) setTimeout(load, Math.min(1000 * tries, 5000));
  });
};
load();
