// Dev page for the site card (F11). Not part of the production build.
import '../src/style.css';
import { renderSiteCard } from '../src/ui/siteCard.js';

// Inline copy of construction/regolith_constants.json (version 1): Vite only
// serves files under web/, so the dev page cannot fetch the original.
const REGOLITH = {
  version: 1,
  moon: {
    bulk_density_g_cm3: { min: 1.3, typical: 1.5, max: 1.9, verified: false },
    regolith_thickness_m: { mare: 4.0, highland: 12.0, verified: false },
    cohesion_kpa: { min: 0.1, typical: 1.0, max: 3.0, verified: false },
    friction_angle_deg: { min: 30, typical: 42, max: 50, verified: false },
  },
  mars: {
    bulk_density_g_cm3: { min: 1.1, typical: 1.3, max: 1.6, verified: false },
    regolith_thickness_m: { typical: 5.0, verified: false },
    cohesion_kpa: { min: 0.5, typical: 2.0, max: 5.0, verified: false },
    friction_angle_deg: { min: 25, typical: 35, max: 45, verified: false },
  },
};

const getJson = async (url) => {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
};

const [fixture, meta, breaksText, targets] = await Promise.all([
  getJson('./site-card.json'),
  getJson('../data/earth_meta.json'),
  getJson('../data/breaks_text.json'),
  getJson('../data/targets.json'),
]);

const clone = (x) => structuredClone(x);

function variant(name) {
  const card = clone(fixture.card);
  let target = clone(fixture.target);
  let weights = clone(fixture.weights);

  if (name === 'gaps') {
    card.partial = true;
    card.country = '---';
    card.p10 = 0.71;
    card.p90 = 0.85;
    card.dims.A = NaN;
    card.verdict.A = 'nodata';
    card.dims.H = 0.31;
    card.verdict.H = 'breaks';
    card.values.bulk_density = NaN;
    card.values.sand_frac = NaN;
    card.values.diurnal_amp_k = NaN;
    card.logistics.travel_min = NaN;
    card.logistics.known_analog_km = 812.4;
  } else if (name === 'moon') {
    target = clone(targets.find((t) => t.id === 'moon_apollo17'));
    delete target.features.bulk_density;
    card.country = null;
    card.logistics.travel_min = 42;
  } else if (name === 'few') {
    weights = { C: 3, T: 1, H: 0, M: 0, W: 0, B: 0, A: 0, I: 0 };
  }
  return { card, target, weights };
}

const cols = [document.getElementById('col-340'), document.getElementById('col-320')];
const select = document.getElementById('variant');
const status = document.getElementById('status');
let handles = [];

function render() {
  for (const hdl of handles) hdl.destroy();
  const v = variant(select.value);
  handles = cols.map((col) => {
    const handle = renderSiteCard(col, {
      ...v,
      meta,
      breaksText,
      regolith: REGOLITH,
      onClose: () => handle.destroy(),
    });
    return handle;
  });

  requestAnimationFrame(() => {
    const report = cols.map((col) => {
      const over = col.scrollWidth - col.clientWidth;
      return `${col.id.slice(4)} px: ${over > 0 ? `overflow ${over} px` : 'no overflow'}`;
    });
    status.textContent = report.join(' · ');
    status.className = report.some((r) => r.includes('overflow ')) ? 'dev-bad' : 'dev-ok';
  });
}

select.addEventListener('change', render);
render();
