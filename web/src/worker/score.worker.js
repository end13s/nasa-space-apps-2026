/**
 * Web Worker wrapper around score_core.js (task E6, Julia's entry point J4).
 *
 * Protocol - every message is {type, ...}, every reply is {type, ...}.
 *
 *   main -> worker  {type: 'init', dataUrl: '/data/', body: 'earth'}
 *   worker -> main  {type: 'ready', meta}
 *
 *   main -> worker  {type: 'score', target, weights,
 *                    gravityScaling, body, filters: {
 *                      noveltyKm, maxTravelMin, excludeProtected}}
 *   worker -> main  {type: 'scored', scores (Float32Array, transferred),
 *                    dims: {T: Float32Array, ...}, hotspots: [...], ms}
 *
 *   main -> worker  {type: 'cell', cellIndex}
 *   worker -> main  {type: 'cellInfo', card}
 *
 * The score arrays are transferred, not copied, so the main thread can hand
 * them straight to the canvas painter.
 */

import {
  scoreAll,
  topHotspots,
  cellLatLon,
  classifyDimension,
  decode,
  proxyCard,
  gradeSigmaOverrides,
} from './score_core.js';

const state = {
  meta: null,
  features: null,
  index: null,
  logistics: null,
  country: null,
  transfer: null,
  target: null,
  last: null,
};

async function fetchBin(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return new Uint8Array(await r.arrayBuffer());
}

async function init(dataUrl, body) {
  const base = dataUrl.endsWith('/') ? dataUrl : `${dataUrl}/`;
  const meta = await (await fetch(`${base}${body}_meta.json`)).json();
  const [features, indexRaw] = await Promise.all([
    fetchBin(`${base}${body}_features.bin`),
    fetchBin(`${base}${body}_index.bin`),
  ]);
  state.meta = meta;
  state.features = features;
  state.index = new Uint32Array(indexRaw.buffer);

  if (meta.logistics_order?.length) {
    try {
      state.logistics = await fetchBin(`${base}${body}_logistics.bin`);
    } catch {
      state.logistics = null;
    }
  }
  try {
    state.transfer = await (await fetch(`${base}transfer_rules.json`)).json();
  } catch {
    state.transfer = { rules: {}, never_testable: [], feature_labels: {} };
  }
  if (meta.country_codes?.length) {
    try {
      state.country = await fetchBin(`${base}${body}_country.bin`);
    } catch {
      state.country = null;
    }
  }
  return meta;
}

/** Logistics value for one cell, decoded. */
function logisticsValue(cellIndex, name) {
  const meta = state.meta;
  if (!state.logistics || !meta.logistics_order) return NaN;
  const j = meta.logistics_order.indexOf(name);
  if (j < 0) return NaN;
  const spec = meta.logistics[name];
  const code = state.logistics[cellIndex * meta.logistics_order.length + j];
  return decode(code, spec.lo, spec.hi, spec.scale);
}

/** Build the visibility mask from the UI filters. */
function buildMask(filters = {}) {
  const meta = state.meta;
  const n = meta.n_cells;
  const { noveltyKm = 0, maxTravelMin = 0, excludeProtected = false } = filters;
  if (!noveltyKm && !maxTravelMin && !excludeProtected) return null;

  const mask = new Uint8Array(n).fill(1);
  for (let i = 0; i < n; i++) {
    if (noveltyKm > 0) {
      const d = logisticsValue(i, 'known_analog_km');
      if (Number.isFinite(d) && d < noveltyKm) {
        mask[i] = 0;
        continue;
      }
    }
    if (maxTravelMin > 0) {
      const t = logisticsValue(i, 'travel_min');
      if (Number.isFinite(t) && t > maxTravelMin) {
        mask[i] = 0;
        continue;
      }
    }
    if (excludeProtected) {
      const p = logisticsValue(i, 'protected_frac');
      if (Number.isFinite(p) && p > 0.5) mask[i] = 0;
    }
  }
  return mask;
}

function cellCard(cellIndex) {
  const meta = state.meta;
  const last = state.last;
  const cellId = state.index[cellIndex];
  const { lat, lon } = cellLatLon(cellId, meta.grid);

  const dims = {};
  const verdict = {};
  if (last) {
    for (const [d, arr] of Object.entries(last.dims)) {
      dims[d] = arr[cellIndex];
      verdict[d] = classifyDimension(arr[cellIndex]);
    }
  }

  const values = {};
  meta.features.forEach((f, j) => {
    values[f.id] = decode(state.features[cellIndex * meta.features.length + j], f.lo, f.hi);
  });

  return {
    cellIndex,
    cellId,
    lat,
    lon,
    overall: last ? last.scores[cellIndex] : NaN,
    dims,
    verdict,
    values,
    partial: last ? Boolean(last.partial[cellIndex]) : false,
    logistics: {
      travel_min: logisticsValue(cellIndex, 'travel_min'),
      protected_frac: logisticsValue(cellIndex, 'protected_frac'),
      viirs_rad: logisticsValue(cellIndex, 'viirs_rad'),
      known_analog_km: logisticsValue(cellIndex, 'known_analog_km'),
    },
    country:
      state.country && meta.country_codes
        ? meta.country_codes[state.country[cellIndex]]
        : null,
    // Supports / Conditional / Cannot test - the proxy card (reframe, Sat sync)
    proxy:
      last && state.target
        ? proxyCard(meta, last.features, cellIndex, state.target, state.transfer,
                    last.scores[cellIndex], last.partial[cellIndex])
        : null,
  };
}

self.onmessage = async (e) => {
  const msg = e.data;
  try {
    if (msg.type === 'init') {
      const meta = await init(msg.dataUrl ?? 'data/', msg.body ?? 'earth');
      self.postMessage({ type: 'ready', meta });
      return;
    }

    if (msg.type === 'score') {
      const t0 = performance.now();
      state.target = msg.target;
      const res = scoreAll(state.meta, state.features, msg.target, msg.weights, {
        gravityScaling: msg.gravityScaling,
        body: msg.body ?? msg.target?.body,
        sigmaOverrides: gradeSigmaOverrides(state.meta, msg.target),
      });
      state.last = res;

      const mask = buildMask(msg.filters);
      const hotspots = topHotspots(res.scores, state.index, state.meta.grid, {
        k: msg.k ?? 20,
        minSepKm: msg.minSepKm ?? 200,
        mask,
        partial: msg.includePartial ? null : res.partial,
      }).map((h) => ({ ...h, detail: cellCard(h.i) }));

      // The arrays are cloned, not transferred: the worker keeps them so that
      // a later {type:'cell'} message can still build a site card from them.
      self.postMessage({
        type: 'scored',
        scores: res.scores,
        dims: res.dims,
        mask,
        hotspots,
        ms: performance.now() - t0,
      });
      return;
    }

    if (msg.type === 'cell') {
      self.postMessage({ type: 'cellInfo', card: cellCard(msg.cellIndex) });
      return;
    }

    self.postMessage({ type: 'error', error: `unknown message ${msg.type}` });
  } catch (err) {
    self.postMessage({ type: 'error', error: String(err?.stack ?? err) });
  }
};
