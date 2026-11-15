/**
 * Read a design token from web/src/tokens.css at call time.
 *
 * Cesium and Chart.js need colour strings, not CSS variables. Reading them
 * when a pin, circle or chart is built - never at module load - keeps
 * tokens.css the single source of truth for every colour in the app.
 */
export function token(name, fallback = '') {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}
