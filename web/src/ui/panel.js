/**
 * Explore controls (task F9): target, mission profile, dimension weights and
 * the Earth filters. The panel owns no scoring logic; it reports changes and
 * main.js decides when to re-score (debounced).
 */
import { legendGradient, MIN_SCORE } from '../heatmap.js';

const esc = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

/** Travel-time slider stops, in hours. 0 means "no limit". */
const TRAVEL_STOPS = [0, 1, 2, 4, 6, 8, 12, 24];

/**
 * @param {HTMLElement} el
 * @param {object} o
 * @param {object} o.meta       earth_meta.json
 * @param {object[]} o.targets  targets.json
 * @param {object[]} o.missions missions.json profiles
 * @param {object} o.state      initial values
 * @param {object} o.on         callbacks: target(id), profile(id), weights(w), filters(f)
 */
export function createPanel(el, { meta, targets, missions, state, on }) {
  const dims = Object.entries(meta.dimensions);
  const hasNovelty = Boolean(meta.logistics?.known_analog_km);
  const hasTravel = Boolean(meta.logistics?.travel_min);
  const hasProtected = Boolean(meta.logistics?.protected_frac);

  const group = (body, label) => {
    const opts = targets
      .filter((t) => t.body === body)
      .map((t) => `<option value="${esc(t.id)}">${esc(t.name)}</option>`)
      .join('');
    return opts ? `<optgroup label="${label}">${opts}</optgroup>` : '';
  };

  el.innerHTML = `
    <section class="ctl">
      <label class="field">
        <span>Target site</span>
        <select data-k="target">
          <option value="">Choose a Moon or Mars site</option>
          ${group('moon', 'Moon')}
          ${group('mars', 'Mars')}
        </select>
      </label>
      <p class="hint" data-k="target-hint">Or click a spot on the left globe.</p>
      <p class="blurb" data-k="blurb" hidden></p>
    </section>

    <section class="ctl">
      <p data-k="status" class="status">Pick a target to light up Earth.</p>
      <div class="legend" aria-label="Similarity colour scale">
        <div class="legend-bar" style="background:${legendGradient()}"></div>
        <div class="legend-labels"><span>${MIN_SCORE}</span><span>Similarity</span><span>1.0</span></div>
      </div>
    </section>

    <section class="ctl">
      <label class="field">
        <span>Mission profile</span>
        <select data-k="profile">
          ${missions.map((m) => `<option value="${esc(m.id)}">${esc(m.name)}</option>`).join('')}
          <option value="custom">Custom weights</option>
        </select>
      </label>
      <p class="hint" data-k="purpose"></p>
      <div class="weights">
        ${dims
          .map(
            ([d, spec]) => `
          <label class="weight">
            <span class="weight-name">${esc(spec.name)}${spec.tier === 'stretch' ? ' <em>beta</em>' : ''}</span>
            <input type="range" min="0" max="3" step="0.5" data-dim="${d}" aria-label="${esc(spec.name)} weight" />
            <output data-out="${d}"></output>
          </label>`,
          )
          .join('')}
      </div>
    </section>

    <section class="ctl">
      <h3 class="ctl-title">Filters</h3>
      <label class="check">
        <input type="checkbox" data-k="gravity" />
        <span>Gravity scaling <small>compare terrain at the body's gravity-scaled baselines (heuristic)</small></span>
      </label>
      <label class="check" ${hasNovelty ? '' : 'hidden'}>
        <input type="checkbox" data-k="novelty" />
        <span>Novelty mode <small>hide cells within 100 km of known analog sites</small></span>
      </label>
      <label class="field" ${hasTravel ? '' : 'hidden'}>
        <span>Max travel time to a city: <b data-k="travel-out"></b></span>
        <input type="range" min="0" max="${TRAVEL_STOPS.length - 1}" step="1" data-k="travel" />
      </label>
      <label class="check" ${hasProtected ? '' : 'hidden'}>
        <input type="checkbox" data-k="protected" />
        <span>Exclude protected areas</span>
      </label>
      <label class="check">
        <input type="checkbox" data-k="known" />
        <span>Show known analog sites</span>
      </label>
    </section>
  `;

  const $ = (k) => el.querySelector(`[data-k="${k}"]`);
  const sliders = [...el.querySelectorAll('input[data-dim]')];

  function showWeights(w) {
    for (const s of sliders) {
      const d = s.dataset.dim;
      s.value = String(w[d] ?? 0);
      el.querySelector(`[data-out="${d}"]`).textContent = String(w[d] ?? 0);
      s.closest('.weight').classList.toggle('off', !(w[d] > 0));
    }
  }

  function showProfile(id) {
    $('profile').value = id;
    const m = missions.find((x) => x.id === id);
    $('purpose').textContent = m ? m.purpose : 'Your own mix of dimensions.';
  }

  function travelLabel(i) {
    const h = TRAVEL_STOPS[i];
    return h === 0 ? 'no limit' : `${h} h`;
  }

  // ---- initial values -------------------------------------------------------
  showProfile(state.profileId);
  showWeights(state.weights);
  $('gravity').checked = state.gravity;
  $('novelty').checked = state.novelty;
  $('protected').checked = state.excludeProtected;
  $('known').checked = state.showKnown;
  const travelIdx = Math.max(0, TRAVEL_STOPS.indexOf(state.maxTravelH));
  $('travel').value = String(travelIdx);
  $('travel-out').textContent = travelLabel(travelIdx);

  // ---- events -----------------------------------------------------------------
  $('target').addEventListener('change', (e) => e.target.value && on.target(e.target.value));

  $('profile').addEventListener('change', (e) => {
    const id = e.target.value;
    showProfile(id);
    const m = missions.find((x) => x.id === id);
    if (m) {
      showWeights(m.weights);
      on.profile(id, { ...m.weights });
    }
  });

  for (const s of sliders) {
    s.addEventListener('input', () => {
      const w = Object.fromEntries(sliders.map((x) => [x.dataset.dim, Number(x.value)]));
      showWeights(w);
      showProfile('custom');
      on.weights(w);
    });
  }

  const filters = () => ({
    gravity: $('gravity').checked,
    novelty: $('novelty').checked,
    maxTravelH: TRAVEL_STOPS[Number($('travel').value)],
    excludeProtected: $('protected').checked,
  });
  for (const k of ['gravity', 'novelty', 'protected']) {
    $(k).addEventListener('change', () => on.filters(filters()));
  }
  $('travel').addEventListener('input', (e) => {
    $('travel-out').textContent = travelLabel(Number(e.target.value));
    on.filters(filters());
  });
  $('known').addEventListener('change', (e) => on.known(e.target.checked));

  return {
    setTarget(t) {
      $('target').value = t?.id ?? '';
      $('blurb').hidden = !t?.blurb;
      $('blurb').textContent = t?.blurb ?? '';
    },
    setStatus(text, kind = '') {
      const s = $('status');
      s.textContent = text;
      s.dataset.kind = kind;
    },
    setHint(text) {
      $('target-hint').textContent = text;
    },
  };
}
