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

## Non-negotiables

- **Terrain code is shared and it is Sofia's.** Import
  `engine/terrain_features.compute(dem_m, px_m, nodata)`; do not re-derive
  relief, slope, roughness or the buildability pair. Sofia reimplements the
  same definitions in Earth Engine for the whole Earth and cross-checks both
  against your output on the test tiles (S4). If they drift, every cross-body
  score is meaningless and nothing in the UI shows it.
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
