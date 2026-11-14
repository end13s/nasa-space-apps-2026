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

## Frontend (F1-F13)

Vite 7 + vanilla JS + CesiumJS 1.143.0 + Chart.js. No framework, no backend,
no Cesium ion token.

### Run it

```bash
cd web
npm install
npm run dev        # http://localhost:5173
npm run build      # -> web/dist, what GitHub Pages serves
```

`predev` / `prebuild` copy Cesium's static assets into `public/cesium`
(`scripts/copy-cesium.mjs`). You need a data bundle in `public/data/`; see the
root README quick start (`fake_data.py` + `pack_web.py`).

### Module map

| File | Task | What it does |
|---|---|---|
| `src/main.js` | F5-F12 | App state and wiring: target -> score -> heatmap + pins -> site card. |
| `src/globes.js` | F2, F3 | Moon/Mars viewer (rebuilt on toggle) and Earth viewer; NASA imagery. |
| `src/scoring.js` | F5 | Promise wrapper around the worker. Latest score request wins. |
| `src/heatmap.js` | F6 | Viridis heatmap: one 1440x720 canvas handed to Cesium as a single tile. |
| `src/picking.js` | F7, F12 | Target circle on the left globe, click-to-snap, shared fly-to helper. |
| `src/pins.js` | F8 | Numbered hotspot pins, grey known-analog markers, click anywhere on land. |
| `src/ui/panel.js` | F9 | Target, mission profile, weights, filters. Re-score is debounced 150 ms. |
| `src/ui/tabs.js` | F13 | Explore / Site / Validation / Discoveries. |
| `src/ui/siteCard.js` | F11 | Site card: radar, verdicts, breaks, construction panel, logistics. |

### Data the app reads (`public/data/`)

| File | Required | From |
|---|---|---|
| `earth_meta.json`, `earth_features.bin`, `earth_index.bin`, ... | yes | `engine/pack_web.py` |
| `targets.json`, `missions.json`, `breaks_text.json` | yes | `pack_web.py` copies them |
| `validation.json` | no, Validation tab says "not yet" | `engine/validate.py` (E9) |
| `known_analogs.json` | no, grey markers hidden | `science/known_analogs.csv` as JSON (array of rows, `lat`/`lon` as numbers) |
| `deep_dives/index.json` | no, Discoveries lists current top matches | Sofia (S9): `[{id, name, lat, lon, body, summary}]` |

**Ask for Eduard:** have `pack_web.py` also write `validation.json` and
`known_analogs.json` into the bundle, so the deployed site has them.

### Imagery gotchas (checked Sat Nov 14)

- Moon/Mars Trek tiles: 2x1 equirectangular grid at level 0, 256 px. Max level: Moon 8, Mars 7.
- GIBS EPSG:4326 **WMTS** tiles are 288 degrees wide at level 0, so they don't line up
  with Cesium's geographic tiling. Earth uses GIBS **WMS** instead.
- `cesium@1.143.0` declares `@cesium/engine@^26.1.0`; npm resolves a newer engine that
  breaks the import. `package.json` `overrides` pins engine 26.1.0 and widgets 16.1.0.

### Dev pages

`dev/site-card.html` renders the site card from a saved worker card
(`dev/site-card.json`); `heatmap-test.html` is a local-only heatmap harness.
Neither ships in the build.
