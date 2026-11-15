# Project page — draft text

Paste-ready for the Space Apps project page. Every field the submission form
asks for. **Numbers marked `[N]` must be replaced with real validation output
before submitting — do not ship a placeholder.**

---

## Project name

**Analog Atlas**

---

## High-level summary (≤ 150 words)

Before anyone builds a base at the lunar south pole, every drill, rover and
construction method is rehearsed on Earth. Those rehearsal sites are chosen
mostly by tradition — Devon Island, the Atacama, Iceland — rather than by
measurement.

Analog Atlas measures them instead. Pick any site on the Moon or Mars; we build
a physical fingerprint of it from NASA orbital data — terrain, thermal inertia,
rock type, ice, dryness, buildability — and score every land cell on Earth
against it, in the browser, live.

The output is not a resemblance ranking. For a stated experiment, each site
gets a proxy card: what it **supports**, what is **conditional** on a stated
physical correction, and what it **cannot test** at all. Gravity, vacuum and
radiation appear in that last column on every card, every time.

The value is honest scope. A tool that states its own limits is one a mission
team can actually plan with.

---

## Link to demo

`[YouTube URL]` — 30-second video, English subtitles burned in, public, no login.

## Link to final project

`https://end13s.github.io/nasa-space-apps-2026/`
Repository: `https://github.com/end13s/nasa-space-apps-2026`

---

## Detailed description

**The question we answer.** The challenge asks which Earth locations are
analogous to candidate permanent lunar base sites and to Mars, and what each
analog does and does not represent. We treat an Earth site as an *experimental
proxy*: a place where a specific measurable condition approximates a specific
condition on the target, for a specific test. A proxy is defined relative to an
experiment, never relative to a whole planet.

**How it works.** Each target is characterised from orbital data over a 15 km
footprint: relief, slope, roughness at two baselines, buildable and steep
ground fractions, thermal-inertia class, surface temperature extremes, albedo,
lithology class, and near-surface ice. The same quantities are computed for
every 0.25° land cell on Earth — about 350,000 cells — from the same
definitions, in one shared code module, so the two sides are measuring the same
thing.

Per feature, similarity is a Gaussian kernel with a tolerance σ that states how
far apart two sites can be and still count as the same kind of place. Features
group into dimensions: terrain, thermal, material, water/ice, vegetation,
construction, and optionally atmosphere and illumination. Dimension scores
combine into a **weighted geometric mean**, so a site that matches on five
dimensions and fails the sixth is correctly reported as failing — an arithmetic
mean would hide it.

**Two kinds of uncertainty, reported separately.**

- *How well we know the target.* Every value in `targets.json` carries an
  evidence grade: **A** multiple instruments or ground truth, **B** single
  validated instrument, **C** model-derived or extrapolated, **D** sparse or
  unvalidated, plus **DEF** for quantities that are exact by definition (zero
  rainfall on the Moon). The grade widens that variable's tolerance, so a
  poorly-known target cannot produce a sharp score.
- *Whether the physics carries over.* Every variable has a transfer status per
  body: transferable, conditional with a stated correction, or not
  transferable. This is a physical judgement, not a probability, and it is set
  before results are computed.

The clearest case is thermal inertia. It depends on the pressure of gas in the
pores — 1 bar on Earth, ~6 mbar on Mars, vacuum on the Moon — so the same sand
reads higher on Earth. An Earth site can match a lunar thermal-inertia class
*exactly* and the card still files it under **Cannot test**, because matching
numbers do not imply matching behaviour in vacuum.

**What a user sees.** Two synced globes. Pick a target from 14 presets —
including Shackleton and the Artemis candidate regions — or by clicking. Earth
lights up with a similarity heatmap in under a second. Click a hotspot: both
cameras fly to matching zoom, and the proxy card opens with the three columns,
an evidence chip per variable, the logistics of reaching the site, and the
always-present physical limits.

**Validation.** `[N]`% of documented analog sites fall in the top 10% of land
cells, against an area-weighted null baseline at 50%. Ablation shows which
dimensions carry the result. Percentiles are area-weighted, because a 0.25° cell
at 70° latitude covers a third of an equatorial one and counting cells equally
inflates high-latitude results. Cells missing a required measurement are scored
but excluded from the ranked findings — a cell with a gap can otherwise
outrank a complete one, since the missing feature is renormalised away rather
than penalised.

**Limitations.** Known analog sites were chosen partly because they are
*reachable*, so recall against them measures agreement with existing practice,
not correctness. Earth cannot reproduce 1/6 g, vacuum, the radiation
environment, the 29.5-day lunar day, or permanently-shadowed-region
temperatures of 25–40 K. Gravity-scaled roughness is a heuristic and is
reported as a sensitivity result, not a default. `[Add the measured-vs-modelled
status of the Earth grid here before submitting.]`

**Tech stack.** Python (NumPy, SciPy, pandas, PyArrow) for the offline
pipeline; Google Earth Engine for Earth features; GDAL/rasterio for planetary
data; CesiumJS for the dual globes; a Web Worker running a JavaScript port of
the scoring engine, verified identical to the Python reference to 3×10⁻⁸ on
random cells; GitHub Pages for hosting. No backend — all scoring runs in the
browser on a quantized 19 MB grid.

---

## Use of Super Intelligence (AI)

We used AI tools as accelerators and we are specific about where.

- **Planning and framing.** The first draft of our project plan was produced
  with Anthropic's Claude, as was a later proposal to reframe the project from
  "which Earth places resemble Mars" to "which Earth sites are proxies for
  which experiments". The team discussed that reframing at a sync, argued about
  which experiments and transfer rules belonged in it, adopted it as our own,
  and recorded the decision in the repository README.
- **Code assistance.** Claude (Claude Code) was used to scaffold and review
  parts of the scoring engine, the browser port, the data contract and the
  packaging pipeline. Files that were AI-assisted say so in their header. All
  of it was read, tested and corrected by a human before merging.
- **CesiumJS agent skills** (CesiumGS/cesiumjs-skills, Apache-2.0) assisted the
  frontend work.
- **No AI-generated imagery or video** appears in the demo or on this page.
- No NASA logos or branding appear in anything we generated.

---

## NASA data

- **Earth:** MODIS land surface temperature (MOD11A2 / MYD11A2), MCD43A3
  albedo, MOD13A2 NDVI, MOD10A1 snow cover, MAIAC MCD19A2 aerosol optical
  depth, ASTER GED, SMAP L4 soil moisture, NASA GIBS imagery.
- **Moon:** LRO LOLA topography and 1064 nm albedo, Diviner thermal products,
  LROC WAC imagery, LEND neutron data, PGDA permanently-shadowed-region and
  illumination maps, USGS Unified Geologic Map of the Moon.
- **Mars:** MGS MOLA topography and TES thermal inertia and albedo, Mars
  Odyssey THEMIS and GRS, MRO-derived SWIM ice consensus, USGS Mars global
  geologic map.
- **Archives and tools:** PDS, Moon Trek, Mars Trek, Earthdata, Worldview.

## Partner and other data

- **ESA:** Copernicus GLO-30 DEM, Sentinel-2, ERA5-Land (Copernicus/ECMWF),
  ESA CCI Permafrost, Mars Climate Database (ESA/CNES).
- **JAXA:** ALOS / G-Portal.
- **CSA:** RADARSAT open data.
- **Other open data:** GLiM global lithological map (Hartmann & Moosdorf 2012),
  OpenLandMap and SoilGrids soil properties, WDPA protected areas, Oxford MAP
  accessibility surface, VIIRS night lights, USGS Astrogeology products.

---

## Before you press Submit

- [ ] Replace every `[N]` with a real number from `validation_report.md`
- [ ] Demo link opens in an incognito window with no login
- [ ] Project link opens in an incognito window and **the globes load with data**
- [ ] Video is ≤ 30.0 s with burned-in English subtitles
- [ ] Screenshots under 10 MB each
- [ ] All six team members confirmed at the same Local Event
- [ ] Both checkboxes ticked on the submission form
