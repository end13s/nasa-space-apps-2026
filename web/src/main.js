import 'cesium/Build/Cesium/Widgets/widgets.css';
import './style.css';
import { createViewer, TargetGlobe, BODIES } from './globes.js';
import { createScorer } from './scoring.js';
import { createHeatmap } from './heatmap.js';
import { TargetPicker, flyToPoint, distanceKm } from './picking.js';
import { createPins } from './pins.js';
import { createPanel } from './ui/panel.js';
import { createTabs, renderValidation, renderDiscoveries } from './ui/tabs.js';
import { renderSiteCard } from './ui/siteCard.js';
import regolith from '../../construction/regolith_constants.json';

// Resolve against the page, not the module: the worker resolves relative URLs
// against its own script location, so it must get an absolute one.
const DATA_URL = new URL('data/', document.baseURI).href;

/** Clicking the left globe snaps to a preset within this distance. */
const SNAP_KM = 400;
/** Camera height as a fraction of body radius for the synced fly-to (F12). */
const PAIR_RATIO = 0.06;

const state = {
  body: 'moon',
  meta: null,
  targets: [],
  missions: [],
  profileId: 'balanced',
  weights: null,
  gravity: false,
  novelty: false,
  maxTravelH: 0,
  excludeProtected: false,
  showKnown: true,
  target: null,
  last: null, // latest 'scored' result
  selected: null, // cellIndex of the open site card
  validation: null,
  deepDives: null,
  breaksText: null,
};

const scorer = createScorer(DATA_URL);
const targetGlobe = new TargetGlobe(document.getElementById('target-globe'), state.body);
const earth = createViewer(document.getElementById('earth-globe'), 'earth');

let heatmap = null;
let pins = null;
let panel = null;

// ---- Tabs -------------------------------------------------------------------
const tabs = createTabs(document.getElementById('panel'), (name) => {
  if (name === 'validation') renderValidation(tabs.panel('validation'), state.validation, state.body);
  if (name === 'discoveries') {
    renderDiscoveries(tabs.panel('discoveries'), state.deepDives, state.last?.hotspots, openDiscovery);
  }
});

// ---- Moon / Mars toggle --------------------------------------------------
const toggle = document.querySelector('.body-toggle');
const label = document.getElementById('target-label');

function setBody(body) {
  if (body === state.body) return;
  state.body = body;
  toggle.querySelectorAll('button').forEach((b) => {
    b.setAttribute('aria-pressed', String(b.dataset.body === body));
  });
  label.textContent = BODIES[body].name;
  targetGlobe.setBody(body);
  if (tabs.current === 'validation') renderValidation(tabs.panel('validation'), state.validation, body);
}

toggle.addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-body]');
  if (!btn || btn.dataset.body === state.body) return;
  setBody(btn.dataset.body);
  clearTarget();
});

// ---- Target picking (F7) ----------------------------------------------------
const picker = new TargetPicker(targetGlobe, { onPick: onTargetGlobeClick });

function onTargetGlobeClick(lat, lon) {
  if (!state.meta) return;
  const R = BODIES[state.body].ellipsoid.maximumRadius;
  let best = null;
  let bestKm = Infinity;
  for (const t of state.targets) {
    if (t.body !== state.body) continue;
    const d = distanceKm(lat, lon, t.lat, t.lon, R);
    if (d < bestKm) {
      bestKm = d;
      best = t;
    }
  }
  if (best && bestKm <= SNAP_KM) {
    selectTarget(best);
    panel.setHint(`Snapped to ${best.name}, ${Math.round(bestKm)} km from your click.`);
  } else {
    panel.setHint(
      best
        ? `No preset within ${SNAP_KM} km (nearest: ${best.name}, ${Math.round(bestKm)} km). ` +
            'Fingerprints for any spot need the global grids, coming soon.'
        : 'No presets on this body yet.',
    );
  }
}

function selectTarget(t) {
  if (t.body !== state.body) setBody(t.body);
  state.target = t;
  panel.setTarget(t);
  picker.show(t);
  closeSite();
  scheduleScore(0);
}

function clearTarget() {
  state.target = null;
  state.last = null;
  heatmap?.clear();
  pins?.clear();
  panel?.setTarget(null);
  panel?.setHint('Or click a spot on the left globe.');
  panel?.setStatus('Pick a target to light up Earth.');
  closeSite();
}

// ---- Scoring (F5) -------------------------------------------------------------
let scoreTimer = null;

/** Debounced re-score: sliders fire many events, the worker wants one. */
function scheduleScore(delay = 150) {
  clearTimeout(scoreTimer);
  scoreTimer = setTimeout(runScore, delay);
}

function filtersForWorker() {
  return {
    noveltyKm: state.novelty ? 100 : 0,
    maxTravelMin: state.maxTravelH ? state.maxTravelH * 60 : 0,
    excludeProtected: state.excludeProtected,
  };
}

async function runScore() {
  if (!state.target || !state.meta) return;
  panel.setStatus('Scoring Earth...', 'busy');
  try {
    const res = await scorer.score({
      target: state.target,
      weights: state.weights,
      gravityScaling: state.gravity,
      body: state.target.body,
      filters: filtersForWorker(),
    });
    if (res.stale) return;
    state.last = res;
    const index = await scorer.index;
    const shown = heatmap.update(res.scores, index, res.mask);
    pins.setHotspots(res.hotspots);
    const top = res.hotspots[0];
    panel.setStatus(
      top
        ? `Top proxy strength ${top.score.toFixed(2)}. Click a numbered pin, or anywhere on land, for the site card.`
        : 'No cells pass the current filters.',
    );
    if (tabs.current === 'discoveries') {
      renderDiscoveries(tabs.panel('discoveries'), state.deepDives, res.hotspots, openDiscovery);
    }
    if (state.selected != null) openSite(state.selected, { fly: false });
    const { showMs } = await shown;
    if (Number.isFinite(showMs)) {
      // Click-to-heatmap budget is 300 ms (team plan F6).
      console.info(
        `[atlas] score ${res.ms.toFixed(0)} ms, round trip ${res.roundTripMs.toFixed(0)} ms, ` +
          `paint ${heatmap.lastPaintMs.toFixed(1)} ms, on screen +${showMs.toFixed(0)} ms`,
      );
    }
  } catch (err) {
    console.error(err);
    panel.setStatus('Scoring failed. See the console.', 'error');
  }
}

// ---- Site card + synced fly-to (F11, F12) ---------------------------------------
let siteRequest = 0;
let siteCard = null; // handle from renderSiteCard

async function openSite(cellIndex, { fly = true } = {}) {
  if (!state.last) {
    panel.setStatus('Pick a target first, then click Earth.');
    return;
  }
  state.selected = cellIndex;
  pins.highlight(cellIndex);
  const req = ++siteRequest;
  const card = await scorer.cell(cellIndex);
  if (req !== siteRequest) return;
  renderSite(tabs.panel('site'), card);
  tabs.enable('site');
  if (tabs.current !== 'site') tabs.show('site');
  if (fly) flyPair(card);
}

function closeSite() {
  state.selected = null;
  siteRequest++;
  siteCard?.destroy();
  siteCard = null;
  pins?.highlight(-1);
  tabs.enable('site', false);
  if (tabs.current === 'site') tabs.show('explore');
}

/** Fly both globes to the pair at the same height-to-radius ratio (F12). */
function flyPair(card) {
  flyToPoint(earth, 'earth', card.lat, card.lon, PAIR_RATIO);
  const t = state.target;
  if (t) flyToPoint(targetGlobe.viewer, t.body, t.lat, t.lon, PAIR_RATIO);
}

function openDiscovery(d) {
  if (d.i != null) {
    openSite(d.i);
    return;
  }
  const i = pins.cellIndexAt(d.lat, d.lon);
  if (i >= 0) openSite(i);
}

/** Site card (F11) in the Site tab. Re-rendered on every re-score. */
function renderSite(el, card) {
  siteCard?.destroy();
  el.replaceChildren();
  siteCard = renderSiteCard(el, {
    card,
    target: state.target,
    weights: state.weights,
    meta: state.meta,
    breaksText: state.breaksText,
    regolith,
    onClose: () => tabs.show('explore'),
  });
}

// ---- Data bundle ------------------------------------------------------------
// The About modal (Julia) will show this properly. Until then a chip makes it
// impossible to demo a synthetic bundle as real.
const status = document.getElementById('data-status');

async function loadJson(name, optional = false) {
  const r = await fetch(`${DATA_URL}${name}`);
  if (!r.ok) {
    if (optional) return null;
    throw new Error(`${name}: ${r.status}`);
  }
  return r.json();
}

function defaultWeights(meta) {
  return Object.fromEntries(
    Object.entries(meta.dimensions).map(([d, spec]) => [d, spec.default_weight ?? 1]),
  );
}

async function loadData() {
  try {
    const [meta, targets, missions, index] = await Promise.all([
      scorer.ready,
      loadJson('targets.json'),
      loadJson('missions.json'),
      scorer.index,
    ]);
    // Nice-to-have files: the app works without them.
    const [validation, known, deepDives, breaksText] = await Promise.all([
      loadJson('validation.json', true).catch(() => null),
      loadJson('known_analogs.json', true).catch(() => null),
      loadJson('deep_dives/index.json', true).catch(() => null),
      loadJson('breaks_text.json', true).catch(() => null),
    ]);
    Object.assign(state, { meta, targets, validation, deepDives, breaksText });
    state.missions = missions.profiles ?? [];
    const first = state.missions.find((m) => m.id === state.profileId) ?? state.missions[0];
    state.profileId = first?.id ?? 'custom';
    state.weights = { ...defaultWeights(meta), ...(first?.weights ?? {}) };

    heatmap = createHeatmap(earth, meta);
    pins = createPins(earth, meta, index, {
      onSelect: (i) => openSite(i),
      onMiss: () => panel.setStatus('That spot is ocean or has no data. Click on land.'),
    });
    if (known) pins.setKnownAnalogs(known);
    pins.showKnown(state.showKnown);

    panel = createPanel(tabs.panel('explore'), {
      meta,
      targets,
      missions: state.missions,
      state,
      on: {
        target: (id) => {
          const t = state.targets.find((x) => x.id === id);
          if (t) selectTarget(t);
        },
        profile: (id, w) => {
          state.profileId = id;
          state.weights = { ...state.weights, ...w };
          scheduleScore(0);
        },
        weights: (w) => {
          state.profileId = 'custom';
          state.weights = w;
          scheduleScore();
        },
        filters: (f) => {
          Object.assign(state, f);
          scheduleScore();
        },
        known: (on) => {
          state.showKnown = on;
          pins.showKnown(on);
        },
      },
    });

    status.textContent = meta.synthetic
      ? 'Synthetic data'
      : `${meta.n_cells.toLocaleString()} Earth cells`;
    status.classList.toggle('synthetic', Boolean(meta.synthetic));
  } catch (err) {
    console.error(err);
    status.textContent = 'Data failed to load';
    status.classList.add('error');
    tabs.panel('explore').innerHTML =
      '<p class="hint">The data bundle is not available yet, so scoring is off. The globes still work.</p>';
  }
  status.hidden = false;
}
loadData();

// Handy while building; remove before the code freeze.
window.atlas = {
  state,
  earth,
  scorer,
  get target() {
    return targetGlobe;
  },
  get heatmap() {
    return heatmap;
  },
  get pins() {
    return pins;
  },
};
