# web/ — Finn (Julia: copy, About modal, CSS polish)

Vite + CesiumJS dual-globe app. `src/worker/` is Eduard's — treat it as an API,
and tell him in `#web` if you need the protocol changed rather than editing it.

## What is already here

- `src/worker/score_core.js` — the scoring maths, a port of `engine/score.py`,
  proven identical to 1e-8 by `engine/tests/test_parity.py`.
- `src/worker/score.worker.js` — the Web Worker wrapper. Loads the packed data,
  scores on demand, returns hotspots and site cards.
- `public/data/` — a packed bundle built from **synthetic** data, so you can
  build the whole UI before Clara's and Michal's exports land. Every file is
  stamped `"synthetic": true`; the About modal should surface that flag so a
  fake build can never be demoed as real.

## Worker protocol

```js
const worker = new Worker(new URL('./worker/score.worker.js', import.meta.url), { type: 'module' });

worker.postMessage({ type: 'init', dataUrl: 'data/', body: 'earth' });
// -> { type: 'ready', meta }           meta.features, meta.grid, meta.dimensions

worker.postMessage({
  type: 'score',
  target,                                  // one entry of targets.json
  weights: { T: 1, H: 1, M: 1, W: 1, B: 1, C: 1, A: 0, I: 0 },
  gravityScaling: false,
  body: 'moon',                            // which gravity-scaled column to swap in
  filters: { noveltyKm: 100, maxTravelMin: 600, excludeProtected: true },
  k: 20, minSepKm: 200,
});
// -> { type: 'scored', scores: Float32Array, dims: {T: Float32Array, ...},
//      mask: Uint8Array|null, hotspots: [{cellId, lat, lon, score, detail}], ms }

worker.postMessage({ type: 'cell', cellIndex });
// -> { type: 'cellInfo', card }          everything a site card needs
```

`scores[i]` corresponds to `index[i]` (the `earth_index.bin` cell id), **not**
to a pixel. To paint the heatmap, map cell id → row/col:

```js
const row = Math.floor(cellId / meta.grid.ncols);
const col = cellId % meta.grid.ncols;
// 1440 x 720 ImageData, then Cesium.SingleTileImageryProvider over
// Rectangle.fromDegrees(-180, -90, 180, 90)
```

Use `ImageData` and write the whole buffer at once — per-pixel `fillRect` will
not hit the 300 ms budget. Alpha 0 below S = 0.2 so the globe shows through.

## Notes that will save you an hour

- `NaN` in `scores` means the cell could not be scored (no data), not zero.
  Leave those transparent.
- `card.partial === true` means an MVP feature was missing for that cell — show
  a small "partial data" chip rather than hiding it.
- Dimension verdicts: ≥ 0.7 strong, 0.4–0.7 partial, < 0.4 breaks. The helper
  is exported as `classifyDimension` from `score_core.js`; use it instead of
  hard-coding the thresholds, so the site card and the engine never disagree.
- The colormap must be perceptually uniform and colorblind-safe (viridis or
  magma). The heatmap is the main visual a judge sees.
- No Cesium ion token: pass `baseLayer: false` and add NASA Trek / GIBS imagery
  providers explicitly. No NASA logo anywhere in the UI.

## Still to scaffold (J1)

`package.json`, `vite.config.js`, `index.html`, `src/main.js`, `src/globes.js`,
`src/heatmap.js`, `src/ui/` (F1). The GitHub Pages workflow in
`.github/workflows/pages.yml` builds `web/` automatically as soon as a
`package.json` exists; until then it publishes the data bundle only.
