# pipeline/earth/ — Clara (non-terrain layers) + Sofia (terrain)

> **What ships today:** the app's Earth grid comes from `fallback_grid.py`
> (ETOPO 2022 + WorldClim 2.1, open data, no Earth Engine account). The Earth
> Engine pipeline described below is complete but has not been run; when it is,
> rebuild the targets with `--grid-m 500` so the terrain baselines match again.
> Known limits of the fallback: slope at a ~1.85 km baseline, 2 m air
> temperature instead of land surface temperature, ice-sheet fraction only
> (no mountain glaciers or small ice caps), and no albedo, thermal-inertia
> class, lithology or NDVI.

Two people export into the **same 0.25° grid**, and Clara merges the results
into one `earth_grid.parquet` by Saturday 23:00.

| File | Owner | Task | Purpose |
|---|---|---|---|
| `gee_features.py` | Clara | C2–C6 | Soil (construction), thermal, material, water/ice/biology, logistics. |
| `gee_terrain.py` | Sofia | S3 | Terrain + buildability on Copernicus GLO-30, from the shared definitions in `engine/terrain_features.py`. |
| `export_tasks.py` | Clara | C7 | Launch six separate `Export.image.toDrive` task groups (seven when GLiM is ready) so one failure does not block everything. Post task ids in `#data`. |
| `tif_to_parquet.py` | Clara | C8 | Multiband GeoTIFFs (hers **and** Sofia's) → one parquet with `cell_id`, `lat`, `lon`, feature columns, `__sd` columns, `qa_flags`. |
| `qc_maps.py` | Clara | C8–C9 | One PNG map per feature, with regional sanity checks. |

`gee_features.py` contains importable image builders. `export_tasks.py` starts
separate Earth Engine tasks and prints each task ID. Continuous feature
builders emit a within-cell spatial standard deviation as
`<feature>__sd`; this describes sub-cell heterogeneity, not sensor accuracy.
`build_thermal()` also emits `ati_raw`; it emits the scored `ti_class` only
when given four calibrated breakpoints.

The planned `science/calibration_sites.geojson` is not present in the repo;
Julia owns that J3 deliverable. Ask Julia/Eduard for the reviewed sites with
known `ti_class` labels. Upload the GeoJSON as an Earth Engine table asset,
then run `calibrate_ti.py --sites-asset <asset-id>` to export per-site ATI
medians. Agree on the four increasing cutoffs with the science owners and save
them as JSON, e.g. `{"ati_breakpoints": [b0, b1, b2, b3]}`. Do not invent
cutoffs or infer labels from unlabeled sites.

`build_lithology()` needs a GLiM Earth Engine FeatureCollection asset with a
code property matching `contract/lithology_classes.yaml`'s `earth_glim` keys.
The function maps those codes and uses a 1 km rasterization followed by mode
reduction to the common grid. The GLiM source/asset is not currently in the
repo; upload the source before requesting that export. `mafic_idx` and
`soil_moist` remain unavailable until their source data are added.

Country ISO3 codes are read locally by `tif_to_parquet.py` from a Natural
Earth admin-0 vector containing an `ISO_A3` field (or from a
`cell_id,country_iso3` CSV). `USDOS/LSIB_SIMPLE/2017` has FIPS two-letter
codes, not ISO3, so do not relabel its codes as ISO3.

Install optional tools with
`python -m pip install -r requirements.txt -r pipeline/earth/requirements.txt`.
Authenticate Earth Engine in the environment where you run the scripts.
Example:

```bash
python pipeline/earth/export_tasks.py \
    --ti-breakpoints data_work/ati_breakpoints.json \
    --glim-asset projects/<project>/assets/glim
```

Until thresholds and the GLiM asset are ready, omit the corresponding options;
the launcher explicitly reports that `ti_class` or `litho_class` is not being
exported. It never substitutes guessed classes.

After all canonical TIFFs, including `earth_land_quality.tif` and Sofia's
`earth_terrain.tif`, are in one directory:

```bash
python pipeline/earth/tif_to_parquet.py \
    --tif-dir data_work/earth_exports \
    --country-vector data_raw/ne_10m_admin_0_countries.geojson \
    --out data_work/earth_grid.parquet
python pipeline/earth/qc_maps.py \
    --grid data_work/earth_grid.parquet \
    --out data_work/qc_maps
```

The parquet builder verifies that every raster is exactly 1440 × 720 with the
contract transform, keeps coastal land cells and sets QA bit 2 below 50% land,
and sets bit 8 for incomplete DEM coverage. Pass `--require-complete` to fail
if any MVP feature, required spatial spread, or country code is missing. The QC
script checks Sahara/Atacama NDVI, Amazon NDVI, and Greenland `ice_idx`,
validates the grid/QA flags, and writes one PNG per numeric feature.

Sofia needs access to Clara's Earth Engine project — add her as a member in
the first ten minutes, it is a common half-hour sink.

## Non-negotiables (both of you)

- **Export geometry**: `crs='EPSG:4326'`,
  `crsTransform=[0.25, 0, -180, 0, -0.25, 90]`, world-bounds `region`,
  `maxPixels=1e13`. Earth Engine treats `dimensions` and `crsTransform` as
  mutually exclusive, so don't pass both; this transform and region define the
  expected 1440 × 720 grid. Check the exported TIFF dimensions and transform
  before merging so `cell_id` remains aligned between both exports.
- **Band names = feature ids**, spelled exactly as in
  `contract/feature_dictionary.yaml`. The packer looks columns up by name and
  prints a WARNING for missing MVP features — read its output.
- **High-resolution mask reduction**: 10–30 m land/DEM masks are staged through
  100 m and 1 km before the 0.25° grid. Every `reduceResolution` call is capped
  at 65,536 inputs. Other source layers use their native 500 m–9 km grids and
  reduce directly when the input count stays within that cap.
- **Land mask**: GLO-30 not null and land fraction > 50 %. Flag coastal cells
  (`qa_flags` bit 2) rather than dropping them.
- Launch exports by **18:00**. They take 1–4 hours; this is the critical path.

## Clara — what is yours

Soil (C2, the easy warm-up): OpenLandMap bulk density and sand fraction at
0 cm, band `b0`, bulk density × 0.01 → g/cm³. These feed the Construction
dimension, so Finn's panel is empty without them.

Thermal (C3), material (C4), water/ice/biology (C5), logistics (C6). Scale
factors are easy to get wrong and expensive to discover late: MODIS LST
`× 0.02` → K, NDVI `× 0.0001`, albedo `× 0.001`, ERA5-Land precipitation is
metres per month (`× 1000 × 12` for mm/yr). ATI masks ΔT < 5 K; it is a
calibration diagnostic until the approved `ti_class` breakpoints are supplied.

**Terrain is not yours** — Sofia exports it on the same grid and hands you the
GeoTIFF for the merge.

## Sofia — what is yours

`gee_terrain.py` must produce the same features as your numpy module, on the
same grid: `relief_km`, `slope_med_deg`, `slope_p90_deg`, `rough_2km`,
`rough_10km`, the four gravity-scaled baselines, `hypso_int`, and the
buildability pair `flat_frac` / `steep_frac`.

The cross-check (S4) is the most important validity test in the project:
compute the same tiles locally from the open AWS bucket `copernicus-dem-30m`
with `engine/terrain_features.py`, then compare against the GEE export.
Tolerance: relief and slope within 10 %, roughness within 20 %. There is a
helper for the table:

```python
from engine.terrain_features import compute, compare_tile
compare_tile(numpy_result, gee_result)   # -> {feature: (a, b, rel, ok/MISMATCH)}
```

If they disagree, find out why before midnight. A silent 30 % roughness offset
between Earth and the Moon makes every cross-body score meaningless, and
nothing in the UI will reveal it.

## Hand-off

`earth_grid.parquet` → shared Drive `analog-atlas-data/`, ping Eduard in
`#data`. He runs:

```bash
python engine/pack_web.py --grid <path>/earth_grid.parquet \
    --targets contract/targets.json --out web/public/data
```

The packer prints per-feature coverage and warns when values clip against the
dictionary's `lo`/`hi` — clipping warnings are a real signal about your units,
not cosmetic.

## Fallbacks (Section 11)

- Exports slow or failing → split further, drop stretch features, drop to 0.5°.
- Account approval delayed → MODIS CMG products from Earthdata Search at 0.05°
  plus Copernicus DEM 90 m tiles.
