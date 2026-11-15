# Analog Atlas

**NASA Space Apps Challenge 2026 — "Identify Earth Locations that Analog the
Permanent Moon Base Locations and Mars"**

Pick a site on the Moon or Mars. Analog Atlas builds a physical fingerprint of it
from NASA orbital data — terrain, thermal inertia, surface material, water/ice,
vegetation and buildability — and scores every land cell on Earth against it, in
the browser, live.

**What we claim:** for a stated experiment, an Earth site can be compared to a
target on named, measured features, with its uncertainty quantified, and the
features whose physics does not carry over can be identified and reported.

**What we do not claim:** that any Earth site reproduces a planetary
environment. The output is not a ranking of Earth sites by resemblance to Mars.
It is a *proxy card* per site: what the site **supports**, what is
**conditional** on a stated correction, and what it **cannot test** at all.

Team: Eduard · Clara · Michal · Sofia · Finn · Julia

> Status: scaffold. The engine, the contract and the packing pipeline run today
> on synthetic data. Real Earth / Moon / Mars data lands as Clara's and Michal's
> exports finish.

---

## Quick start (60 seconds)

```bash
python -m pip install -r requirements.txt

# 1. synthetic Earth grid + synthetic targets  (no network, ~30 s)
python engine/fake_data.py --out data_work

# 2. pack them for the browser
python engine/pack_web.py --grid data_work/earth_grid.parquet \
    --targets data_work/targets.json --out web/public/data

# 3. prove the maths
python engine/tests/test_score.py      # engine unit tests
python engine/tests/test_parity.py     # Python vs the browser port (needs node)
```

Nobody waits for real data: `fake_data.py` emits exactly the schema the real
pipelines emit, and every file it writes is stamped `"synthetic": true` so a
fake build can never be mistaken for a real one in the demo.

---

## How it works

For a target fingerprint **t** and an Earth cell **x**:

1. **Per-feature similarity**, `s_f ∈ [0, 1]`
   - continuous: `exp(-0.5 · ((x − t) / σ)²)`
   - relative σ (roughness): `σ = max(0.3 · |t|, floor)`
   - log features (precipitation): compared as `log10(x + 1)`
   - classes (thermal inertia): Gaussian over class distance
   - lithology: a 5×5 similarity matrix, not a distance
   - missing: the feature drops out and its dimension is renormalised; the cell
     is flagged *partial*
2. **Per-dimension score**: `s_d = Σ w_f·s_f / Σ w_f`
3. **Proxy strength**: weighted **geometric** mean,
   `S = exp( Σ_d W_d · ln(s_d + ε) / Σ_d W_d )`, normalised so identical
   fingerprints give exactly 1.0. It is a secondary field, never the headline —
   the card leads with scope, not with a number.

### Two kinds of uncertainty, kept apart

**How well we know the target.** Every value in `targets.json` carries an
evidence grade — **A** multiple instruments or ground truth, **B** single
validated instrument, **C** model-derived or extrapolated, **D** sparse or
unvalidated, and **DEF** for quantities that are exact by definition (zero
rainfall on the Moon). The grade widens that variable's σ, so a poorly-known
target cannot produce a sharp score. Note the consequence, which the evidence
strip exists to make visible: a vaguer target is *easier* to match, so a high
score on grade-D data is weaker evidence, not stronger.

**Whether the physics carries over.** `contract/transfer_rules.yaml` gives every
variable a status per body: transferable, conditional with a stated correction,
or not transferable. It is a physical judgement, not a probability, and it is
fixed before results are computed.

A variable reaches **Supports** only if it both matches *and* transfers. Thermal
inertia can match a lunar target exactly and still be filed under **Cannot
test**, because in vacuum there is no gas conduction between grains — matching
numbers do not imply matching behaviour. That invariant is enforced by a unit
test.

The geometric mean is the whole point: a site that matches beautifully on four
dimensions and is hopeless on the fifth is **not** a good analog, and an
arithmetic mean would hide that.

`ε` (default 0.01) sets how harshly one dead dimension punishes the total. It
lives in `engine/score.py` and is written into `earth_meta.json`, so it is
tuned deliberately on Sunday morning rather than being buried in the formula.

**All scoring runs in the browser**, in a Web Worker, on precomputed quantized
grids. There is no backend to host, to pay for, or to fall over during judging.

---

## Repository map

| Path | Owner | What |
|---|---|---|
| `contract/feature_dictionary.yaml` | Eduard | **The source of truth.** Every feature id, unit, quantization range, σ and data source. Frozen v1 Saturday 14:30; changes go through Eduard in `#data`. |
| `contract/lithology_classes.yaml` | Michal (Sofia reviews) | 5 lithology classes, the GLiM/USGS mappings and the similarity matrix. |
| `contract/body_constants.json` | Michal | Gravity, pressure, obliquity, day length, temperature ranges — drives the always-on "where it breaks" lines. |
| `contract/targets.json` | Michal | Moon/Mars target fingerprints (M5). |
| `engine/score.py` | Eduard | Reference implementation of the score. |
| `engine/terrain_features.py` | **Sofia** | Shared window-statistics definition for terrain/buildability; scalar-p50 adapter retained for planetary callers. |
| `engine/cross_check.py` | **Sofia** | Per-feature NumPy/GEE tile comparison with contract tolerances. |
| `engine/targets_terrain.py` | **Sofia** | Applies local DEM clips to a separate copy of the planetary target fingerprints. |
| `engine/fact_check.py` | **Sofia** | Checks project-page identifiers and transfer-rule wording against the contracts. |
| `engine/illumination.py` | Eduard | Analytic sun geometry, shared across bodies. |
| `engine/fake_data.py` | Eduard | Synthetic grid + targets so nobody is blocked. |
| `engine/pack_web.py` | Eduard | parquet → `.bin` + `meta.json` for the browser. |
| `engine/validate.py` | Eduard / Sofia | Validation, ablation, grade-D ranking sensitivity and filtered per-experiment rankings. |
| `engine/tests/` | Eduard | Unit tests + Python↔JS parity. |
| `tests/test_sofia_tasks.py` | Sofia | Terrain spread/error, cross-check, target handoff, discovery ranking and fact-check tests. |
| `pipeline/earth/gee_features.py` | Clara | Earth Engine extraction of the non-terrain layers: thermal, albedo, lithology, ice, water, vegetation, soil, logistics. |
| `pipeline/earth/gee_terrain.py` | Sofia | Earth Engine terrain export on the same grid, from the shared definitions. |
| `construction/` | Finn (criteria), Clara (soil), Julia (constants) | The Construction dimension: what a builder checks, mapped to features. |
| `pipeline/planetary/` | Michal | LRO / MGS / Odyssey / MRO products → grids and fingerprints. |
| `science/` | Julia (content), Sofia (deep dives) | Known analogs, calibration sites, mission profiles, breaks text, deep dives. |
| `web/` | Finn (Julia: copy, About, polish) | CesiumJS dual-globe app. `web/src/worker/` is Eduard's. |
| `demo/` | Julia | Script, recordings, video, backup slides. |

### Git rules

- `main` is protected. Work on `name/feature` branches. **Eduard merges.**
- Large data (> 50 MB) never goes into git — use the shared Drive folder
  `analog-atlas-data/`. Only the packed web bundle (< 20 MB) is committed.
- Changing a schema means asking Eduard in `#data` **first**.

---

## Data contract, in one table

| Grid | Resolution | Size | Cell id |
|---|---|---|---|
| Earth | 0.25° EPSG:4326 | 1440 × 720, land cells only | `row*1440 + col`, row 0 = 90°N, col 0 = −180° |
| Moon | 0.5° | 720 × 360 | `row*720 + col` |
| Mars | 0.5° | 720 × 360 | `row*720 + col` |

Cell centre: `lat = 90 − (row + 0.5)·res`, `lon = −180 + (col + 0.5)·res`.
Longitude is **east-positive, −180…+180** on every body; Mars products in
0–360°E must be converted (`lon -= 360 if lon > 180`).

Packed bundle in `web/public/data/`:

| File | Layout |
|---|---|
| `earth_features.bin` | `Uint8[n_cells × n_features]`, row-major. 0–254 linear between `lo` and `hi`; **255 = missing**. |
| `earth_sd.bin` | same layout, the `__sd` columns (uncertainty band). |
| `earth_index.bin` | `Uint32` cell_id per row. |
| `earth_logistics.bin` | `Uint8`, travel time / protected fraction / night lights / distance to the nearest known analog. |
| `earth_meta.json` | feature table, quantization bounds, σ, grid geometry, lithology matrix, ε. |

---

## Data sources

**NASA.** Earth: MODIS LST (MOD11A2 / MYD11A2), MCD43A3 albedo, MOD13A2 NDVI,
MOD10A1 snow, MAIAC MCD19A2, ASTER GED, SMAP L4, NASA GIBS imagery.
Moon: LRO LOLA, Diviner, LROC, LEND, PGDA illumination and PSR maps.
Mars: MGS MOLA and TES, Mars Odyssey THEMIS and GRS, MRO-derived SWIM ice
consensus. Archives and tools: PDS, Moon Trek, Mars Trek, Earthdata, Worldview.

**Partner agencies.** ESA: Copernicus GLO-30 DEM, Sentinel-1/2, ERA5-Land
(Copernicus/ECMWF), ESA CCI Permafrost, Mars Climate Database (ESA/CNES).
JAXA: ALOS / G-Portal. CSA: RADARSAT.

**Other open data.** GLiM lithology (Hartmann & Moosdorf 2012), WDPA protected
areas, Oxford MAP accessibility, VIIRS night lights, USGS Astrogeology geologic
maps and DEMs.

Full per-dataset provenance, including asset ids, versions and date ranges,
lives in `contract/feature_dictionary.yaml` and in the pipeline README files.

---

## Use of AI ("Super Intelligence") — disclosure

We use AI tools as accelerators and we say exactly where:

- **Planning and framing.** The first draft of our project plan, including an
  early version of the concept, was produced with Anthropic's Claude. A later
  AI-assisted discussion proposed reframing the project from "which Earth places
  resemble Mars" to "which Earth sites are proxies for which experiments, and
  where does the proxy stop". The team discussed that reframing at a sync,
  argued about which experiments and transfer rules belonged in it, adopted it,
  and recorded the decision below. The features, targets, transfer rules and
  experiments are the team's own choices.
- **Code assistance.** Claude (Claude Code) was used to scaffold and review
  parts of `engine/`, `web/src/worker/` and the contract files. Every file that
  was AI-assisted says so in its header. All of it was read, tested and
  corrected by a human before merging.
- **CesiumJS agent skills** (CesiumGS/cesiumjs-skills, Apache-2.0) assist the
  frontend work.
- **No AI-generated imagery or video** is used in the demo. If that changes, the
  asset carries a visible watermark.
- No NASA logos or branding appear in anything we generate.

---

## Decision record

| Date | Decision | Why |
|---|---|---|
| Sat 14 Nov | Contract frozen: `feature_dictionary.yaml` v1 | One source of truth for every pipeline, engine and port |
| Sat 14 Nov | Added the Construction dimension (C) | The challenge asks about *permanent* bases; buildability is measurable and nobody else scores it |
| Sat 14 Nov | Roughness quantization ceiling 80 → 160 ‰ (v1.1) | A real Apollo 17 fingerprint measured 92 ‰; the old ceiling would have clipped every Earth cell rough enough to match it |
| Sat 14 Nov | **Adopted the proxy reframe** | A resemblance ranking cannot state what a site fails to test; scope statements can. Discussed and adopted by the team at the Saturday sync |
| Sat 14 Nov | Kept the Gaussian kernel; deferred distribution-based divergence | Comparing distributions needs per-cell quantiles, which would require re-running the Earth export and would exceed the browser data budget. Listed as future work |
| Sat 14 Nov | Validation percentiles area-weighted | Equal-angle cells over-count high latitudes |
| Sat 14 Nov | Hotspots exclude cells missing an MVP feature | Missing features are renormalised away, so incomplete cells were outranking complete ones |

## Honest limitations

- Terrain values are p50s across non-overlapping 1 km windows after 500 m
  resampling; p10/p90 describe within-footprint variability, not measurement
  error. A separate `err` field is populated only where vertical accuracy is
  provided. Fewer than nine windows marks a result provisional.
- Earth cannot reproduce lunar permanently-shadowed-region temperatures
  (~25–40 K), the two-week lunar night, 1/6 g, vacuum, or the unshielded
  radiation environment. Those are reported as breaks on **every** site card,
  not quietly dropped.
- Thermal inertia of loose material depends on pore gas pressure (1 bar on
  Earth, ~6 mbar on Mars, vacuum on the Moon). The same sand reads higher on
  Earth. That is why we compare **classes calibrated within each body**, never
  raw TI numbers.
- Gravity scaling of roughness baselines (`× g_body/g_Earth`) is a heuristic for
  gravity-driven landform size. It is a toggle, and validation is reported with
  it on and off.
- Known analog sites were partly chosen because they are *accessible*, not only
  because they are similar. Recall against them measures agreement with current
  practice, not correctness, and is reported as a sanity check rather than as
  proof the method is right.
- Validation percentiles are **area-weighted**: a 0.25° cell at 70° latitude
  covers about a third of an equatorial one, and counting cells equally
  inflates high-latitude results.
- Cells missing a required measurement are scored but excluded from the ranked
  findings. A missing feature is renormalised away rather than penalised, so a
  cell with a gap can outrank a complete one — on synthetic data, four of the
  top five hotspots were incomplete cells before this was fixed.

## License

Code: MIT. Data: each source keeps its own license and citation requirements —
see the data sources section.
