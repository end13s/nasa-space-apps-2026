# science/ - Sofia's folder

Everything in here is **content**, not code, and all of it is read by the app
at runtime or by `engine/validate.py`. Eduard put placeholder files in place so
that the pipeline runs end to end today; replace them, keep the schema.

| File | Task | What it must become |
|---|---|---|
| `known_analogs.csv` | S2 | At least 15 rows, **every coordinate checked on Worldview**, `verified` set to `yes`, a real `reference_url` on each row. This file is the validation ground truth and also drives novelty mode, so a wrong coordinate quietly corrupts both. |
| `calibration_sites.geojson` | S3 | 10+ polygons of 10-30 km with a known TI class and lithology, for Clara's ATI binning. |
| `missions.json` | S5 | 5-6 mission profiles. The weights are per dimension (T, H, M, W, B, A, I). |
| `breaks_text.json` | S6 | The sentences that turn a number into understanding. Plain language, 30 words max per line. |
| `deep_dives/*.md` | S10 | One file per discovery site; Julia renders them in the Discoveries tab. |

## known_analogs.csv columns

| column | meaning |
|---|---|
| `id` | lowercase slug, stable, used as a key |
| `name` | display name |
| `lat`, `lon` | decimal degrees, **lon is east-positive, -180..+180** |
| `analog_for` | `moon` or `mars` (one row per body if a site is both) |
| `analog_type` | short free text, shown in the validation table |
| `accessible_by_design` | `yes` if the site is famous partly because it is easy to reach - this is the honesty column from Section 6.1 point 6 |
| `verified` | `no` until the coordinate has been eyeballed on Worldview |
| `reference_url` | a paper, mission page or agency page |

## Why `accessible_by_design` matters

Our validation asks whether the method rediscovers known analogs. Some known
analogs were chosen because a road goes there, not because they are the best
physical match. Those rows are expected to rank lower, and saying so in the
write-up is worth more to the Validity score than hiding it.
