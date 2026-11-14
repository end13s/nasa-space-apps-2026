import 'cesium/Build/Cesium/Widgets/widgets.css';
import './style.css';
import { createViewer, TargetGlobe, BODIES } from './globes.js';
import { createScorer } from './scoring.js';
import { createHeatmap, legendGradient, MIN_SCORE } from './heatmap.js';

// Resolve against the page, not the module: the worker resolves relative URLs
// against its own script location, so it must get an absolute one.
const DATA_URL = new URL('data/', document.baseURI).href;

const state = {
  body: 'moon',
  meta: null,
  targets: [],
  missions: [],
  target: null,
  weights: null,
  last: null, // latest 'scored' result
};

let heatmap = null; // created once earth_meta.json is in

const scorer = createScorer(DATA_URL);

const target = new TargetGlobe(document.getElementById('target-globe'), state.body);
const earth = createViewer(document.getElementById('earth-globe'), 'earth');

// ---- Moon / Mars toggle --------------------------------------------------
const toggle = document.querySelector('.body-toggle');
const label = document.getElementById('target-label');

toggle.addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-body]');
  if (!btn || btn.dataset.body === state.body) return;
  state.body = btn.dataset.body;
  toggle.querySelectorAll('button').forEach((b) => {
    b.setAttribute('aria-pressed', String(b === btn));
  });
  label.textContent = BODIES[state.body].name;
  target.setBody(state.body);
  state.target = null;
  heatmap?.clear();
  if (state.meta) renderTargetPicker();
});

// ---- Data bundle status ---------------------------------------------------
// The About modal (Julia) will show this properly. Until then a chip makes it
// impossible to demo a synthetic bundle as real.
const status = document.getElementById('data-status');

async function loadJson(name) {
  const r = await fetch(`${DATA_URL}${name}`);
  if (!r.ok) throw new Error(`${name}: ${r.status}`);
  return r.json();
}

async function loadData() {
  try {
    const [meta, targets, missions] = await Promise.all([
      scorer.ready,
      loadJson('targets.json'),
      loadJson('missions.json'),
    ]);
    state.meta = meta;
    heatmap = createHeatmap(earth, meta);
    state.targets = targets;
    state.missions = missions.profiles ?? [];
    state.weights = { ...(state.missions[0]?.weights ?? defaultWeights(meta)) };
    status.textContent = meta.synthetic
      ? 'Synthetic data'
      : `${meta.n_cells.toLocaleString()} Earth cells`;
    status.classList.toggle('synthetic', Boolean(meta.synthetic));
    renderTargetPicker();
  } catch (err) {
    console.error(err);
    status.textContent = 'Data failed to load';
    status.classList.add('error');
  }
  status.hidden = false;
}

function defaultWeights(meta) {
  return Object.fromEntries(
    Object.entries(meta.dimensions).map(([d, spec]) => [d, spec.default_weight ?? 1]),
  );
}

// ---- Target picker (minimal; F7 adds grouping + click-anywhere) -----------
const panel = document.getElementById('panel');

function renderTargetPicker() {
  const options = state.targets
    .filter((t) => t.body === state.body)
    .map((t) => `<option value="${t.id}">${t.name}</option>`)
    .join('');
  panel.innerHTML = `
    <label class="field">
      <span>Target on ${BODIES[state.body].name}</span>
      <select id="target-select">
        <option value="">Choose a site</option>
        ${options}
      </select>
    </label>
    <p id="score-status" class="panel-empty">Pick a target to light up Earth.</p>
    <div class="legend" aria-label="Similarity colour scale">
      <div class="legend-bar" style="background:${legendGradient()}"></div>
      <div class="legend-labels"><span>${MIN_SCORE}</span><span>Similarity</span><span>1.0</span></div>
    </div>
  `;
  panel.querySelector('#target-select').addEventListener('change', (e) => {
    const t = state.targets.find((x) => x.id === e.target.value);
    if (t) selectTarget(t);
  });
}

async function selectTarget(t) {
  state.target = t;
  await runScore();
}

async function runScore() {
  if (!state.target) return;
  const out = panel.querySelector('#score-status');
  out.textContent = 'Scoring Earth...';
  try {
    const res = await scorer.score({
      target: state.target,
      weights: state.weights,
      gravityScaling: false,
      filters: {},
    });
    if (res.stale) return;
    state.last = res;
    const index = await scorer.index;
    const shown = heatmap.update(res.scores, index, res.mask);
    const top = res.hotspots[0];
    const summary = top
      ? `Best match ${top.score.toFixed(2)} at ${top.lat.toFixed(1)}, ${top.lon.toFixed(1)}.`
      : 'No cells matched.';
    out.textContent = summary;
    const { showMs } = await shown;
    if (Number.isFinite(showMs)) {
      // Click-to-heatmap budget is 300 ms (team plan F6).
      console.info(
        `[atlas] score ${res.ms.toFixed(0)} ms, round trip ${res.roundTripMs.toFixed(0)} ms, ` +
          `paint ${heatmap.lastPaintMs.toFixed(1)} ms, on screen +${showMs.toFixed(0)} ms`,
      );
    }
    document.dispatchEvent(new CustomEvent('atlas:scored', { detail: res }));
  } catch (err) {
    console.error(err);
    out.textContent = 'Scoring failed. See the console.';
  }
}

loadData();

// Handy while building; remove before the code freeze.
window.atlas = { state, target, earth, scorer, get heatmap() { return heatmap; } };
