# construction/ — the Construction dimension (C)

The challenge asks about conditions relevant to **building a permanent base**,
not just visiting one. Dimension C is our answer, and it is the part of the
project nobody else at the hackathon will have.

| File | Owner | Task | What it is |
|---|---|---|---|
| `construction_criteria.md` | Finn | F4 | What a builder actually checks on new ground, each criterion mapped to a feature id — or marked "can't measure from orbit", which is itself an honest finding. |
| `regolith_constants.json` | Julia | J4 | Moon and Mars upper-regolith values (bulk density, thickness, cohesion, friction angle) with a citation each. |
| `soil_features_gee.py` | Clara | C2 | OpenLandMap bulk density + sand fraction → Earth grid columns. |

## Features (contract/feature_dictionary.yaml, dimension C)

| id | tier | where it comes from |
|---|---|---|
| `flat_frac` | MVP | Sofia's terrain module — share of area below 5° slope at 400 m |
| `steep_frac` | MVP | Sofia's terrain module — share above 25° |
| `bulk_density` | stretch | Earth: OpenLandMap (Clara). Moon/Mars: `regolith_constants.json` |
| `sand_frac` | stretch | Earth only, site-card context, not scored |
| `rock_abund` | stretch | Moon/Mars only (Diviner, TES/THEMIS), target-card context |
| `bedrock_depth_m` | stretch | Earth: SoilGrids. Site-card context |

Thermal cycling on the construction panel reuses `diurnal_amp_k` from the
thermal dimension — shown, but deliberately not weighted twice.

## If the expert call changes the thresholds

`FLAT_MAX_DEG = 5.0` and `STEEP_MIN_DEG = 25.0` live in **one place**:
`engine/terrain_features.py`. If Finn's call moves them, change them there,
tell Eduard and Sofia before 18:00, and both the Earth export and the
planetary fingerprints stay consistent. Changing them anywhere else silently
makes the Earth and the Moon numbers mean different things.

## The honest line for the site card

A test site on Earth can rehearse *procedures* — excavation, grading,
foundation laying, 3D printing with local material — but never the loads. At
1/6 g a bucket of regolith weighs a sixth as much while keeping all its mass,
so forces, dust ballistics and slope stability all behave differently. Say
that on the panel; it is a stronger answer than pretending otherwise.
