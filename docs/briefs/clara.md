# Clara — proxy reframe brief

> **Status: pending the sync decision.** Either way, almost nothing changes for
> you — this brief exists so you are not surprised by new vocabulary at the
> sync.

**No new exports. No new features. No code changes.** Your critical path is
exactly what it was: launch the exports by 18:00, deliver
`earth_grid.parquet` by 23:00.

## What the reframe actually is

The app stops saying "this Earth cell resembles Mars" and starts saying "for
this experiment, this site supports these conclusions, needs a correction for
these, and cannot test these at all". Each variable also carries an **evidence
grade** A–D saying how well we know it.

Your data is the Earth half of every one of those statements, which is why the
only thing asked of you is provenance honesty.

## The one addition: ~10 minutes, at hand-off

When you deliver the parquet, send Eduard a short note in `#data` saying, per
feature, whether it is **measured** or **model-derived**. That single
distinction sets the Earth-side evidence grade. For example:

| feature | which | grade it implies |
|---|---|---|
| `tmin_k`, `tmax_k`, `albedo`, `ndvi_max` | measured (MODIS) | B |
| `precip_mm` | **reanalysis**, not a direct measurement (ERA5-Land) | C |
| `ice_idx` from ESA CCI Permafrost | measured product | B |
| `ice_idx` from the ERA5 soil-temperature **proxy** fallback | model-derived | C |
| `bulk_density`, `sand_frac` (OpenLandMap) | interpolated from point samples | C |
| `travel_min` (Oxford MAP) | modelled accessibility surface | C |

You do not need to write grades into the parquet — a message is enough, Eduard
puts them in the metadata. But **which fallback you ended up using matters**:
if the ESA CCI permafrost file was slow and you used the ERA5 proxy, say so,
because the grade changes.

## Your `qa_flags` get more important, not more work

The flags you were already producing — cloudy LST gaps, coastal cells, polar
night, DEM voids — now feed the per-cell evidence grade directly. A cell whose
thermal data came from a polar-night gap should not produce a confident thermal
match, and the flag is what prevents that.

So: populate them properly, and don't be tempted to drop flagged cells instead
of flagging them. A flagged cell is useful; a missing cell is invisible.

## Vocabulary you will hear at the sync

- **Evidence grade (A–D)** — how well a variable is known. Widens the tolerance
  rather than hiding the variable.
- **Transfer status** — whether a match on a variable means the same thing on
  the other body. Thermal inertia is the famous one: it depends on pore gas
  pressure, so the same sand reads higher at 1 bar than at 6 mbar.
- **Proxy card** — what the site card becomes: Supports / Conditional / Cannot
  test.

## Unchanged

C2 soil (the Construction dimension depends on it — Finn's panel is empty
without your OpenLandMap bulk density and sand fraction), C3 thermal, C4
material, C5 water/ice/biology, C6 logistics, **C7 exports by 18:00**, C8
parquet with Sofia's terrain merged in, C9 QC maps, C10 delivery, C14 README.

## Definition of done

Unchanged from before — parquet loads, every MVP feature has ≥ 95 % land
coverage except polar LST which is flagged, QC PNGs posted — **plus** the
one-paragraph measured-vs-modelled note at hand-off.
