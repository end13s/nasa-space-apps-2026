# pipeline/planetary/ — Michal

**Goal:** `contract/targets.json` — a trustworthy fingerprint for every Moon and
Mars preset, by Saturday 22:00 (Eduard needs it for the walking skeleton), plus
the coarse global grids for click-anywhere on Sunday morning.

## Files to write here

| File | Task | Purpose |
|---|---|---|
| `download.sh` | M1 | The exact product URLs, so anyone can reproduce the build. |
| `../../contract/lithology_classes.yaml` | M2 | You write it, Sofia reviews it. |
| `moon_features.py` | M4 | LOLA / Diviner / LROC / LEND → features per target region. |
| `mars_features.py` | M3 | MOLA-HRSC / TES / SWIM / MCD → features per target. |
| `ti_classes.py` | M6 | Thermal-inertia class thresholds per body, with the justification paragraph Sofia needs. |
| `build_targets.py` | M3–M5 | Writes `contract/targets.json`. |

> **As built:** everything above lives in one script, `build_targets.py`. The
> product URLs, versions, citations and processing steps are in
> [Moon & Mars data](#moon--mars-data-m11) at the bottom of this file.

## Non-negotiables

- **Terrain code is shared and it is Sofia's.** Use
  `engine/terrain_features.compute(dem, px_m, nodata=...)` for window
  quantiles and measurement-error records. `terrain_features(...)` remains a
  scalar-p50 compatibility helper for existing planetary code. Do not
  re-derive relief, slope, roughness or buildability. Sofia reimplements the
  definitions in Earth Engine and cross-checks test tiles (S4).
- **The lunar south pole is a hand-off, not a solo task** (M4): you reproject
  the LOLA polar clips to a local equidistant projection, Sofia runs the
  terrain module on them and writes the terrain fields into `targets.json`.
  Agree who edits the file when, so you do not overwrite each other.
- **Construction features come with the terrain pass**: `flat_frac` and
  `steep_frac` fall out of `compute()` for free. `bulk_density` and
  `rock_abund` you fill from `construction/regolith_constants.json` (Julia)
  and Diviner / TES rock abundance.
- **Coordinates**: planetocentric latitude, longitude **east-positive,
  −180…+180**. Mars products published in 0–360°E must be converted
  (`lon -= 360 if lon > 180`). Getting this wrong puts Jezero in the wrong
  hemisphere and nobody notices until the demo.
- **Project before measuring.** Compute terrain features on a local
  equidistant projection centred on the target (polar stereographic for the
  lunar south pole), never on a lat/lon grid — at 85°S a degree of longitude is
  9 km, and roughness in "degrees" means nothing.
- **Sofia's target-clip handoff.** After clips are ready, put one projected
  `<target_id>.tif` per target in a directory and run
  `python -m engine.targets_terrain --clips-dir <dir> --targets
  contract/targets.json --out <new-file>`. It writes p50 feature values and
  full quantile/error records separately; it never overwrites Michal's source.
- **Never download a whole 10 GB DEM**: use GDAL `/vsicurl/` windowed reads
  (`gdal.Warp(..., outputBounds=..., dstSRS=<local equidistant>)`).
- **Do not guess Artemis region coordinates.** Take the region outlines from
  NASA Moon Trek and use the centroid with a 15 km radius. Sofia double-checks
  every coordinate.

## targets.json schema (Section 5.2)

```json
[{
  "id": "mars_jezero",
  "body": "mars",
  "name": "Jezero crater",
  "lat": 18.4, "lon": 77.5, "radius_km": 15,
  "features": {"relief_km": 0.62, "slope_med_deg": 2.1,
               "flat_frac": 0.78, "steep_frac": 0.02, "bulk_density": 1.3},
  "sd":       {"relief_km": 0.10, "slope_med_deg": 0.6},
  "tags": ["sedimentary", "astrobiology"],
  "sources": ["MOLA-HRSC blended DEM 200 m", "TES TI (Putzig & Mellon 2007)"],
  "blurb": "Ancient lake delta; Perseverance landing site."
}]
```

Feature ids must match `contract/feature_dictionary.yaml` exactly. Features you
cannot produce: leave them out rather than writing a zero — the engine
renormalises around a missing feature, but a wrong zero silently poisons a
whole dimension. (Real zeros, like precipitation on Mars, are genuine values —
write those.)

`engine/fake_data.py` emits a synthetic `targets.json` in exactly this shape;
use it as a reference and as a smoke test for the loader.

## Validate before handing over

```bash
python - <<'PY'
import json
from pathlib import Path
import sys; sys.path.insert(0, "engine")
from score import load_contract
c = load_contract(); ids = {f.id for f in c.features}
for t in json.loads(Path("contract/targets.json").read_text()):
    unknown = set(t["features"]) - ids
    missing = {f.id for f in c.scored_features(("mvp",))} - set(t["features"])
    print(t["id"], "unknown:", sorted(unknown) or "-", "missing MVP:", sorted(missing) or "-")
PY
```

---

## Moon & Mars data (M11)

Every value in `contract/targets.json` comes from the products below, read by
`build_targets.py`. Each value also carries its own citation in the target's
`sources` list and an evidence grade in `grades`. This section is the overview.

### Rebuild

```bash
python3 pipeline/planetary/build_targets.py      # from the repo root
```

Needs `rasterio` (GDAL) and an internet connection. Rasters are read window by
window over HTTP (GDAL `/vsicurl/`) and never downloaded whole. Two files are
fetched whole: the Diviner table (156 MB) and the THEMIS Jezero mosaic
(1.7 MB). Both are cached once in `~/.cache/analog_atlas`, outside the repo.

A run takes about ten minutes. It prints every value with its grade, writes
`contract/targets.json`, then runs the contract check. The check reports
unknown feature ids, missing MVP features, ungraded values and values outside
the dictionary range.

### Targets

Coordinates are planetocentric, longitude east-positive, −180…180. The
footprint is a square of side 2 × `radius_km`: 30 km by default, about one
0.25° Earth cell. Centres come from published outlines or gazetteers and are
never estimated by eye.

| id | lat, lon | footprint | centre from |
|---|---|---|---|
| `mars_jezero` | 18.40, 77.50 | 30 km | Jezero crater, rounded centre |
| `mars_gale` | −5.40, 137.80 | 30 km | Gale crater, rounded centre |
| `mars_jezero_delta` | 18.48, 77.39 | 10 km | western fan unit NHjf2, Sun & Stack 2020, USGS SIM 3464, doi:10.3133/sim3464 |
| `moon_apollo17` | 20.19, 30.77 | 30 km | Apollo 17 landing site |
| `moon_shackleton_rim` | −89.67, 129.78 | 30 km | IAU Gazetteer of Planetary Nomenclature, Shackleton (feature 5450) |
| `moon_artemis_peak_near_cabeus_b` | −83.6514, −68.7263 | 30 km | USGS 2024 grid |
| `moon_artemis_haworth` | −86.7639, −22.7770 | 30 km | Moon Trek 2022 outline |
| `moon_artemis_malapert_massif` | −85.9948, −0.2358 | 30 km | Moon Trek 2022 outline |
| `moon_artemis_mons_mouton_plateau` | −84.3375, 30.6186 | 30 km | USGS 2024 grid (region is 78 × 58 km; the footprint covers its middle) |
| `moon_artemis_mons_mouton` | −85.4218, 31.6755 | 30 km | USGS 2024 grid |
| `moon_artemis_nobile_rim_1` | −85.4381, 37.3667 | 30 km | Moon Trek 2022 outline |
| `moon_artemis_nobile_rim_2` | −83.9540, 58.8221 | 30 km | Moon Trek 2022 outline |
| `moon_artemis_de_gerlache_rim_2` | −88.2300, −64.6284 | 30 km | Moon Trek 2022 outline |
| `moon_artemis_slater_plain` | −87.1697, 125.4596 | 30 km | USGS 2024 grid |

The two sources for the nine Artemis III candidate regions (NASA, Oct 2024)
are:

- **Moon Trek 2022 outline:** the area centroid of the region outline in the
  NASA Moon Trek layer "Artemis III Candidate Landing Regions, S Pole". This
  layer holds the 2022 set of 13 regions; these five kept their names in 2024.
- **USGS 2024 grid:** the centre of the region's 1 km grid in the USGS "Down
  Selected Artemis III Candidate Landing Site Navigational Grids" (McClernan
  2024, doi:10.5066/P1MEQ6UK), converted from south polar stereographic
  (Moon 2015 sphere, k0 0.994, false E/N 500 km).

Cross-check: the 2024 Mons Mouton centre lands within ~1 km of the 2022
Leibnitz Beta Plateau centre. That is the same place under its old name, found
from two independent files with two different conversions.

### Products

| Quantity | Product (file / version) | Resolution | Feeds | Citation |
|---|---|---|---|---|
| Mars topography | MOLA–HRSC blended DEM v2, `Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif` (USGS Astrogeology) | 200 m | terrain, Mars targets | Fergason, Hare & Laura 2018 |
| Moon topography, 60°S–60°N | SLDEM2015 LOLA + Kaguya TC merge, `Lunar_LRO_LOLAKaguya_DEMmerge_60N60S_512ppd.tif` | 512 ppd (read at 100 m) | terrain, Apollo 17 | Barker et al. 2016 |
| Moon topography, 80°–90°S | LOLA `LDEM_80S_40MPP_ADJ` (PGDA) | 40 m (read at 100 m) | terrain, south-polar targets | Barker et al. 2023, PSJ 4:183, doi:10.3847/PSJ/acf3e1; data doi:10.60903/gsfcpgda-lola-spole |
| Permanent shadow | LOLA PSR map `LPSR_75S_120M_201608` (MIT LOLA archive / PGDA copies) | 120 m | `ice_idx`, `context.psr_share_50km` | Mazarico et al. 2011, Icarus 211:1066, doi:10.1016/j.icarus.2010.10.030 |
| Lunar surface temperature | Diviner Global Cumulative Product `global_cumul_avg_cyl_90s80s_002.tab` (all nadir data, Jul 2009 – Apr 2015) | 0.5° × 0.5° × 15 min local time | `tmin_k`, `tmax_k`, `diurnal_amp_k`, `context.tmin_coldest_k` (south-polar targets) | Williams et al. 2017, Icarus 283:300, doi:10.1016/j.icarus.2016.08.012; PDS bundle doi:10.17189/wj0s-w188 |
| Lunar albedo | LOLA normal albedo at 1064 nm, GDR `LDAM_50S_1000M_FLOAT` (south polar) and `LDAM_10_FLOAT` (global) | 1 km / 0.1° | `albedo`, all lunar targets | Lucey et al. 2014, JGR Planets 119:1665, doi:10.1002/2013JE004592 |
| Mars albedo | TES Lambert (bolometric) albedo, `Mars_MGS_TES_Albedo_mosaic_global_7410m.tif` (USGS Astrogeology) | 7.4 km | `albedo`, Mars targets | Christensen et al. 2001, JGR 106(E10):23823, doi:10.1029/2000JE001370 |
| Mars thermal inertia | THEMIS-derived TI of Jezero crater, `Jezero_Thermal_Inertia_v1.tiff` | ~100 m | `ti_class`, Jezero and the delta | Edwards & Buz 2021, Zenodo, doi:10.5281/zenodo.4931348 |
| Lunar lithology | Unified Geologic Map of the Moon | 1:5M | `litho_class`, south-polar targets | Fortezzo et al. 2020 |

Exact URLs, including the fallback copies, are in `build_targets.py` (`DEM`,
`PSR_CANDIDATES`, `GCP`, `ALBEDO_CANDIDATES`, `THEMIS_TI`).

**Site-level literature values** fill what no footprint product covers yet:

| Target | Feature | Source |
|---|---|---|
| `mars_jezero` | `tmin_k` / `tmax_k` | MEDA ground temperature, Ls 13–203: Munguira et al. 2023, JGR Planets 128, doi:10.1029/2022JE007559 |
| `mars_jezero` | `litho_class` | Farley et al. 2022, Science, doi:10.1126/science.abo2196 |
| `mars_jezero_delta` | `tmin_k` / `tmax_k` | Same MEDA values, extrapolated to the delta front |
| `mars_jezero_delta` | `litho_class` | Delta Front campaign; Sun & Stack 2020 |
| `mars_gale` | `ti_class` | THEMIS TI: Fergason et al. 2012, Space Sci Rev, doi:10.1007/s11214-012-9891-3 |
| `mars_gale` | `tmin_k` / `tmax_k` | REMS ground temperature (Gómez-Elvira et al. 2017) |
| `mars_gale` | `litho_class` | Curiosity results |
| `moon_apollo17` | `ti_class` | Lucchitta 1992 |
| `moon_apollo17` | `tmin_k` / `tmax_k` | Diviner equatorial values: Williams et al. 2017 |
| `moon_apollo17` | `litho_class` | Muehlberger et al. 1973, Science, doi:10.1126/science.182.4113.672 |
| Mars targets | `ice_idx` = 0 | Equatorward of the ice-stability zone: Morgan et al. 2021, Nature Astronomy, doi:10.1038/s41550-020-01290-z |

### Processing, per target

1. **Window read.** The footprint plus a 5 km margin is read with GDAL
   `/vsicurl/` and warped (`WarpedVRT`) to a local azimuthal-equidistant grid
   centred on the target (`+proj=aeqd`, body sphere: Moon 1737.4 km, Mars
   3396.19 km). Every distance is therefore in metres. Continuous fields use
   bilinear resampling; masks and class maps use nearest.
2. **Terrain.** Uses Sofia's shared `engine/terrain_features.py`, never
   re-derived here: the p50 over non-overlapping 1 km windows after resampling
   to 500 m.
   - `rough_10km` is left out when the footprint side is under 30 km (the
     delta).
   - A separate check on the footprint's height range (p95 − p5) catches bad
     reads.
3. **`sd`.** Each value is recomputed with the centre shifted 5 km north,
   south, east and west (radius/3 for small footprints). `sd` is the standard
   deviation of the five results. It says how much the value depends on
   exactly where the footprint sits; it is not measurement error.
4. **`ice_idx` (south-polar targets).** The share of the footprint in
   permanent shadow, counted over all pixels so a map that stores "not
   shadowed" as nodata still gives the right number.
   `context.psr_share_50km` is the same share over a 50 km circle.
5. **Diviner temperatures (south-polar targets).**
   - For each 0.5° bin, take the coldest and the warmest of the 96 local-time
     bins of the mean day. Bins with data in fewer than 48 local times are
     dropped.
   - Average by area over the footprint, sampled on a 250 m local grid. This
     gives `tmin_k` and `tmax_k`; `diurnal_amp_k` is their difference.
   - `context.tmin_coldest_k` is the coldest bin in the footprint.
6. **Albedo.** The mean of the map over the footprint (sampled at 1 km; 3 km
   for the global LOLA map). Values ≤ 0 count as no data.
7. **`ti_class` (Jezero targets).** The median THEMIS TI over the footprint,
   binned with the Mars edges from `feature_dictionary.yaml` (100 / 250 / 600
   / 1200 SI → class 0–4).
8. **Zeros by definition.** `precip_mm`, `ndvi_max` and `soil_moist` are 0 on
   both bodies (grade DEF).
9. **Fallbacks, never placeholders.**
   - Every map has its published copies listed. The first copy that passes a
     small real read is used, and a later read failure moves to the next.
   - If a product fails completely, the feature is left out. The exceptions are
     Jezero `albedo` / `ti_class` and Gale `albedo`, where the earlier
     literature value is used and its own source line says so.
   - A run that leaves something out prints a `WARNING` line saying so.

### Evidence grades

Grades follow the project scale (A multiple instruments or ground truth,
B one orbital instrument, C model-derived or extrapolated, D literature
constant, DEF exact by definition). A grade describes how well the value is
known over the whole footprint, not at one rover position.

| Grade | Values |
|---|---|
| A | Gale `tmin_k` / `tmax_k` (REMS) and `litho_class` (Curiosity); Apollo 17 `litho_class` (samples); delta `litho_class` (Delta Front campaign) |
| B | All DEM terrain; Diviner polar temperatures; LOLA and TES albedo; THEMIS `ti_class` (Jezero, delta); Gale and Apollo 17 `ti_class`; Jezero `tmin_k` / `tmax_k` and `litho_class` (measured along the traverse only) |
| C | `ice_idx` everywhere (a PSR model at the poles, latitude elsewhere); polar `litho_class` and `ti_class` (regional call / extrapolated); Apollo 17 `tmin_k` / `tmax_k` (equatorial Diviner values); delta `tmin_k` / `tmax_k` (extrapolated) |
| DEF | The zeros by definition |
| D | None |

### Limitations, Moon and Mars side

- **`ice_idx` is the area of cold traps, not an amount of ice.** Landing
  regions sit on lit ridges by design, so the share is small. The Earth column
  is permafrost and glacier fraction, a different quantity.
- **The Diviner GCP averages all seasons.** Against the warmest-month /
  coldest-month definition, `tmax_k` reads low and `tmin_k` reads high. The
  240 m seasonal polar products (Williams et al. 2019) would fix this, but they
  are 144–192 files of ~200 MB each.
  - At 0.5° the coldest bins in our footprints are 31–48 K. The permanently
    shadowed floors themselves are colder still (Paige et al. 2010,
    doi:10.1126/science.1187726).
- **LOLA normal albedo is not broadband albedo.** It is zero-phase reflectance
  at 1064 nm and reads higher than a broadband albedo of the same ground.
- **Polar `ti_class` is extrapolated.** No Diviner thermophysical map reaches
  the poles. The H-parameter map (Hayne et al. 2017, doi:10.1002/2017JE005387)
  and the rock-abundance mosaics (Powell et al. 2023, doi:10.1029/2022JE007532)
  both stop at 70°.
- **Polar `litho_class` is one regional call**: feldspathic highlands.
- **Jezero temperatures cover Ls 13–203 only.** Northern winter is missing, so
  `tmin_k` is probably a little warm. The delta uses the same numbers.
- **The 10 km delta footprint is small.** It has no `rough_10km`, and its TES
  albedo rests on a few 7.4 km pixels.
- **Terrain uses the shared 500 m / 1 km definition.** Each window is then 2 × 2
  cells, so `hypso_int` is ≈ 0.50 and `steep_frac` is 0 for every target. The
  200 m Mars DEM resamples to 400 m (rounding in the shared module), not 500 m.
  Both points are flagged to the terrain owner.
- **Not footprint products.** Mars and Apollo 17 values other than albedo, the
  Jezero `ti_class` and terrain are site-level literature values.
