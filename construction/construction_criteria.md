# Construction criteria → features

**Owner: Finn (task F4).** Template scaffolded by Eduard; fill it in from the
expert call and commit it. It is also the backbone of the Construction section
of the README and of the "a test here could / couldn't prove" lines on the
site card.

Deadline: **Saturday 17:30**, because if the call moves the 5° / 25° slope
thresholds, Sofia needs to know before her 18:00 GEE export.

## How to fill this in

One row per thing a builder checks. Map it to a feature id from
`contract/feature_dictionary.yaml`, or write **"can't measure from orbit"** —
that is not a gap, it is a finding, and it belongs on the site card and in the
limitations section.

| What a builder checks | Why it matters | Feature that measures it | Notes |
|---|---|---|---|
| How flat the ground is | Grading cost, foundation and pad layout | `flat_frac` | threshold 5° — confirm |
| How much is too steep to build on | No-build zones, rockfall, excavation cost | `steep_frac` | threshold 25° — confirm |
| How firm / dense the ground is | Load bearing, settlement | `bulk_density` | Earth: OpenLandMap; Moon/Mars: literature |
| How hard it is to dig | Excavation time and equipment | `bulk_density` + `rock_abund` | |
| How deep the bedrock sits | Whether you can found on rock or must float the structure | `bedrock_depth_m` | Earth only |
| Water, frost, freeze-thaw | Foundation damage, seasonal access | `ice_idx`, `diurnal_amp_k` | |
| Temperature swing | Thermal fatigue of structures | `diurnal_amp_k` | reused from dimension H, not double-weighted |
| … | | | |

## Expert call questions (F4)

1. Before you build on a new site, what do you check about the ground first?
2. What makes ground good or bad for foundations — soil type, density, water, frost, depth to rock?
3. What makes excavation slow or expensive?
4. How flat does a site need to be, and how much grading is normal?
5. What would make a site completely unbuildable?
6. Which of these could you guess from a satellite photo or an elevation map, and which need someone on site?
7. If you wanted to test construction robots or new building methods somewhere remote, what would you want that site to have?

**Before the call:** ask permission. Do not name the expert, their employer or
their company anywhere in the repo, the project page or the video without
explicit consent — "a working construction professional" is enough.

## Output for Julia

5–8 plain-language bullets for the construction "breaks" text in
`science/breaks_text.json` (dimension C): what a construction test on Earth
*can* prove, and what it structurally cannot.
