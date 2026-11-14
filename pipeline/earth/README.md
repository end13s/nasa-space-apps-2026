# pipeline/earth/ — Clara

**Goal:** `earth_grid.parquet` — every feature in `contract/feature_dictionary.yaml`
for every 0.25° land cell on Earth, quality-checked, by Saturday 23:00.

## Files to write here

| File | Task | Purpose |
|---|---|---|
| `gee_features.py` | C2–C6 | One function per feature group, each returning an `ee.Image` band with the dictionary's exact feature id as the band name. |
| `export_tasks.py` | C7 | Launch 3–4 separate `Export.image.toDrive` tasks so one failure does not block everything. Post task ids in `#data`. |
| `tif_to_parquet.py` | C8 | Multiband GeoTIFF → parquet with `cell_id`, `lat`, `lon`, the feature columns, `__sd` columns, `qa_flags`. |
| `qc_maps.ipynb` | C8–C9 | One PNG map per feature, posted in `#data`. |

## Non-negotiables

- **Export geometry** (Section 5.1): `crs='EPSG:4326'`,
  `crsTransform=[0.25, 0, -180, 0, -0.25, 90]`, `dimensions='1440x720'`,
  `maxPixels=1e13`. Anything else and `cell_id` stops meaning the same thing in
  every file.
- **Band names = feature ids**, spelled exactly as in the dictionary. The
  packer looks columns up by name and silently skips what it cannot find (it
  prints a WARNING for missing MVP features — read the output).
- **Land mask**: GLO-30 not null and land fraction > 50 %. Flag coastal cells
  (`qa_flags` bit 2) rather than dropping them.
- **Terrain must match Michal's**: the definitions live in
  `engine/terrain_features.py`. Before exporting for real, run your GEE version
  and Michal's numpy version on the agreed test tile (a 0.25° cell over Meteor
  Crater, 35.03 N, 111.02 W) and compare with
  `engine.terrain_features.compare_tile`. A 15 % relative difference is the
  threshold; anything larger goes in `#data` before exporting.
- **Two-stage reduction**: 100 m → 1 km → 0.25°. Earth Engine caps
  `reduceResolution` at 65,536 input pixels per output pixel, so a single jump
  from 30 m to 0.25° silently fails.
- Scale factors are easy to get wrong and expensive to discover late:
  MODIS LST `× 0.02` → K, NDVI `× 0.0001`, ERA5-Land precipitation is metres
  per month (`× 1000 × 12` for mm/yr).

## Hand-off

Drop `earth_grid.parquet` in the shared Drive `analog-atlas-data/` and ping
Eduard in `#data`. He runs:

```bash
python engine/pack_web.py --grid <path>/earth_grid.parquet \
    --targets contract/targets.json --out web/public/data
```

The packer prints per-feature coverage and warns when values clip against the
dictionary's `lo`/`hi` — if you see clipping warnings, that is a real signal
about your units, not a cosmetic one.

## Fallbacks (Section 11)

- Exports slow or failing → split further, drop stretch features, drop to 0.5°.
- Account approval delayed → MODIS CMG products from Earthdata Search at 0.05°
  plus Copernicus DEM 90 m tiles.
