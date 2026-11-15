# pipeline/earth/ — Clara (non-terrain layers) + Sofia (terrain)

Two people export into the **same 0.25° grid**, and Clara merges the results
into one `earth_grid.parquet` by Saturday 23:00.

| File | Owner | Task | Purpose |
|---|---|---|---|
| `gee_features.py` | Clara | C2–C6 | Soil (construction), thermal, material, water/ice/biology, logistics. |
| `gee_terrain.py` | Sofia | S3 | Terrain + buildability on Copernicus GLO-30, from the shared definitions in `engine/terrain_features.py`. |
| `export_tasks.py` | Clara | C7 | Launch 3–4 separate `Export.image.toDrive` tasks so one failure does not block everything. Post task ids in `#data`. |
| `tif_to_parquet.py` | Clara | C8 | Multiband GeoTIFFs (hers **and** Sofia's) → one parquet with `cell_id`, `lat`, `lon`, feature columns, `__sd` columns, `qa_flags`. |
| `qc_maps.ipynb` | Clara | C8–C9 | One PNG map per feature, posted in `#data`. |

`gee_features.py` contains importable image builders; initialize Earth Engine
in the calling notebook or script, then export the returned images with the
shared grid settings. It currently builds soil, thermal, water/biology, ice,
logistics, and protected-area layers. The contract features `ti_class`,
`litho_class`, `mafic_idx`, and `soil_moist` still need their calibration or
source ingestion before they can be exported; do not substitute proxy bands.

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
- **Two-stage reduction**: 100 m → 1 km → 0.25°. Earth Engine caps
  `reduceResolution` at 65,536 input pixels per output pixel, so a single jump
  from 30 m silently fails.
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
metres per month (`× 1000 × 12` for mm/yr). Mask ΔT < 5 K in the ATI
calculation or cloud and water artifacts poison the thermal-inertia classes.

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
