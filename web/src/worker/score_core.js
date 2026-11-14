/**
 * Analog Atlas scoring core - JavaScript port of engine/score.py (task E6).
 *
 * Pure ES module, no DOM and no worker API, so that:
 *   - score.worker.js can wrap it,
 *   - engine/tests/test_parity.py can run it under plain node and prove it
 *     agrees with the Python to 1e-3 on random cells.
 *
 * If you change a formula here, change engine/score.py in the same commit.
 *
 * AI-assisted: ported with Claude from the Python reference, reviewed by Eduard.
 */

export const MISSING = 255;
export const DIM_ORDER = ['T', 'H', 'M', 'W', 'B', 'C', 'A', 'I'];

/** uint8 code -> physical value. NaN where the code is the missing marker. */
export function decode(code, lo, hi, scale = 'linear') {
  if (code === MISSING) return NaN;
  if (scale === 'log') {
    const llo = Math.log10(lo + 1);
    const lhi = Math.log10(hi + 1);
    return Math.pow(10, llo + (code / 254) * (lhi - llo)) - 1;
  }
  return lo + (code / 254) * (hi - lo);
}

/** Similarity of one feature value against the target value. NaN = missing. */
export function featureSimilarity(x, t, spec, lithoMatrix) {
  if (!Number.isFinite(x) || !Number.isFinite(t)) return NaN;

  if (spec.sigma_mode === 'matrix') {
    const xi = Math.min(5, Math.max(1, Math.round(x)));
    const ti = Math.min(5, Math.max(1, Math.round(t)));
    return lithoMatrix[xi][ti];
  }

  let xa = x;
  let ta = t;
  let s = spec.sigma;

  if (spec.sigma_mode === 'log') {
    xa = Math.log10(Math.max(x, 0) + 1);
    ta = Math.log10(Math.max(t, 0) + 1);
  } else if (spec.sigma_mode === 'rel') {
    s = Math.max(spec.sigma * Math.abs(t), spec.sigma_floor || 0);
  }
  if (!(s > 0)) return NaN;

  const z = (xa - ta) / s;
  return Math.exp(-0.5 * z * z);
}

/**
 * Build the per-query plan once: which column index feeds which feature,
 * honouring the gravity swap. Cheap, but doing it outside the cell loop keeps
 * the hot loop free of string lookups.
 */
export function buildPlan(meta, target, { gravityScaling = false, body = null, tiers = null } = {}) {
  const colOf = new Map();
  meta.features.forEach((f, i) => colOf.set(f.id, i));

  const plan = [];
  for (const f of meta.features) {
    if (f.scored === false) continue;
    if (f.earth_only) continue;
    if (tiers && !tiers.includes(f.tier)) continue;
    const t = target.features ? target.features[f.id] : target[f.id];
    if (t === undefined || t === null || !Number.isFinite(t)) continue;

    let col = colOf.get(f.id);
    if (gravityScaling && body && f.gravity_swap && f.gravity_swap[body]) {
      const swapped = colOf.get(f.gravity_swap[body]);
      if (swapped !== undefined) col = swapped;
    }
    if (col === undefined) continue;

    const src = meta.features[col];
    plan.push({
      id: f.id,
      dim: f.dim,
      col,
      lo: src.lo,
      hi: src.hi,
      target: t,
      spec: f,
      mvp: f.tier === 'mvp',
    });
  }
  return plan;
}

/**
 * Score every cell.
 *
 * @param {Object}   meta      parsed <body>_meta.json
 * @param {Uint8Array} features row-major [nCells x nFeatures]
 * @param {Object}   target    one entry of targets.json
 * @param {Object}   weights   {T: 1, H: 1, ...}
 * @returns {{scores: Float32Array, dims: Object, partial: Uint8Array}}
 */
export function scoreAll(meta, features, target, weights, opts = {}) {
  const n = meta.n_cells;
  const nf = meta.features.length;
  const eps = opts.eps ?? meta.eps ?? 0.01;
  const litho = meta.litho_matrix;
  const plan = buildPlan(meta, target, opts);

  const dimsPresent = [...new Set(plan.map((p) => p.dim))].sort(
    (a, b) => DIM_ORDER.indexOf(a) - DIM_ORDER.indexOf(b)
  );
  const dimIdx = new Map(dimsPresent.map((d, i) => [d, i]));
  const nd = dimsPresent.length;

  const scores = new Float32Array(n);
  const dimArrays = dimsPresent.map(() => new Float32Array(n));
  const partial = new Uint8Array(n);

  const num = new Float64Array(nd);
  const den = new Float64Array(nd);
  const wd = dimsPresent.map((d) => Number(weights?.[d] ?? 0));
  const norm = Math.log(1 + eps);

  for (let c = 0; c < n; c++) {
    num.fill(0);
    den.fill(0);
    let missedMvp = 0;
    const base = c * nf;

    for (let k = 0; k < plan.length; k++) {
      const p = plan[k];
      const code = features[base + p.col];
      const x = decode(code, p.lo, p.hi);
      const s = featureSimilarity(x, p.target, p.spec, litho);
      if (Number.isFinite(s)) {
        const d = dimIdx.get(p.dim);
        num[d] += s;
        den[d] += 1;
      } else if (p.mvp) {
        missedMvp = 1;
      }
    }
    partial[c] = missedMvp;

    let logSum = 0;
    let wSum = 0;
    for (let d = 0; d < nd; d++) {
      const sd = den[d] > 0 ? num[d] / den[d] : NaN;
      dimArrays[d][c] = sd;
      if (wd[d] > 0 && Number.isFinite(sd)) {
        logSum += wd[d] * (Math.log(sd + eps) - norm);
        wSum += wd[d];
      }
    }
    scores[c] = wSum > 0 ? Math.exp(logSum / wSum) : NaN;
  }

  const dims = {};
  dimsPresent.forEach((d, i) => {
    dims[d] = dimArrays[i];
  });
  return { scores, dims, partial, plan };
}

/** cell_id -> {lat, lon} cell centre, using the grid block of meta. */
export function cellLatLon(cellId, grid) {
  const row = Math.floor(cellId / grid.ncols);
  const col = cellId % grid.ncols;
  return {
    lat: grid.lat0 - (row + 0.5) * grid.res_deg,
    lon: grid.lon0 + (col + 0.5) * grid.res_deg,
  };
}

const EARTH_RADIUS_KM = 6371.0088;

export function haversineKm(lat1, lon1, lat2, lon2) {
  const toRad = Math.PI / 180;
  const p1 = lat1 * toRad;
  const p2 = lat2 * toRad;
  const dp = p2 - p1;
  const dl = (lon2 - lon1) * toRad;
  const a =
    Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(Math.min(1, Math.max(0, a))));
}

/**
 * Top-k cells, no two within minSepKm (greedy non-maximum suppression).
 * `mask` is an optional Uint8Array: 0 hides the cell (novelty / travel-time /
 * protected-area filters are applied by the caller).
 */
export function topHotspots(scores, index, grid, { k = 20, minSepKm = 200, mask = null, pool = 20000 } = {}) {
  const n = scores.length;
  const cand = [];
  for (let i = 0; i < n; i++) {
    if (mask && !mask[i]) continue;
    const s = scores[i];
    if (Number.isFinite(s)) cand.push(i);
  }
  cand.sort((a, b) => scores[b] - scores[a]);
  const top = cand.slice(0, pool);

  const chosen = [];
  for (const i of top) {
    const { lat, lon } = cellLatLon(index[i], grid);
    let ok = true;
    for (const c of chosen) {
      if (haversineKm(lat, lon, c.lat, c.lon) < minSepKm) {
        ok = false;
        break;
      }
    }
    if (!ok) continue;
    chosen.push({ i, cellId: index[i], lat, lon, score: scores[i] });
    if (chosen.length >= k) break;
  }
  return chosen;
}

export const STRONG = 0.7;
export const PARTIAL = 0.4;

export function classifyDimension(sd) {
  if (!Number.isFinite(sd)) return 'nodata';
  if (sd >= STRONG) return 'strong';
  if (sd >= PARTIAL) return 'partial';
  return 'breaks';
}
