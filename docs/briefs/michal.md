# Michal — proxy reframe brief

> **Adopted at the Saturday sync.** This is the plan now, not a proposal.
> Anything in your existing task list that this does not mention is unchanged.

**Read this first: your priority does not change.** You owe 12 more targets by
22:00, Artemis regions first. Grades are an enhancement on top. If grading ever
threatens the target count, the targets win and the grades wait.

## What's new: an evidence grade per variable

Every number in `targets.json` gets a letter saying how well we actually know
it. Eduard turns the letter into a tolerance — a D-grade value is scored with a
much wider σ, so it cannot produce false precision.

| grade | meaning | typical case in your data |
|---|---|---|
| **A** | multiple instruments, or ground truth | Gale temperatures from REMS on the surface |
| **B** | single orbital instrument, no ground truth | MOLA-HRSC terrain, THEMIS TI, Diviner temperatures |
| **C** | model-derived or extrapolated | MCD climatology, SWIM consensus ice, anything you inferred from latitude |
| **D** | poorly constrained | regolith bulk density from a literature constant, PSR temperatures below Diviner resolution |

## Grade by **source**, not by value

This is the whole trick for keeping it to ~10 minutes per target. You already
group your citations by source in the `OTHER` dict — grade the source once and
let the variables inherit:

```python
"mars_gale": {
    "features": {...},
    "sd": {...},
    "grades": {
        "__terrain__": "B",      # everything from the DEM inherits this
        "ti_class": "B",         # THEMIS, orbital, no ground truth
        "tmin_k": "A",           # REMS, measured on the surface
        "tmax_k": "A",
        "albedo": "B",
        "litho_class": "A",      # Curiosity ground truth
        "ice_idx": "C",          # inferred from the ice-stability latitude, not measured here
    },
    "sources": [...],
}
```

`__terrain__` covers relief, slopes, roughness, hypso, flat_frac and steep_frac
in one line — add that expansion in `build_targets.py` where you already merge
`OTHER` into the feature dict. Five to seven entries per target, not fourteen.

## Honest grading is the point

A grade-D value is **not** a failure — it is the project telling the truth
about what orbital data can and cannot establish. Resist grading everything B
to look thorough. Specifically:

- Anything you took from a *literature constant* rather than a measurement at
  that site is **D**. Bulk density for every lunar and Martian target is D until
  someone lands there.
- Anything inferred from latitude or a model (your `ice_idx = 0` reasoning from
  the ice-stability zone, MCD temperatures) is **C**, not B. The reasoning is
  sound; the measurement is absent.
- Apollo 17 and Gale have genuine ground truth for some variables. Those are
  the only **A** grades you are likely to have, and they are worth having —
  they show the grade scale is real and not a formality.

## Also worth one line each in `sources`

You are already writing per-value citations with DOIs, which is the best
sourcing on the team. Keep doing exactly that; the grade is a summary of what
the citation already says, not extra research.

## Where you actually are (targets.json v2, merged)

Done: Shackleton, 5 Artemis regions, the Jezero delta split, plus the original
three. That is the hard part of M4/M5.

Still open, in priority order:
1. **The remaining 4 Artemis regions** - the DoD is all nine.
2. Grades on everything you have shipped (see above, ~10 min per target).
3. Jezero `tmin_k`/`tmax_k`; Apollo 17 `albedo` (LROC WAC 643 nm).
4. M7 global grids, M8 illumination from PGDA, M9 deep dives with Sofia,
   M11 README.

One physics note now that the transfer rules exist: `shadow_frac_lowsun` for
lunar targets must come from the **horizon-based PGDA illumination maps**, not
from the latitude-only analytic function. At Shackleton the crater rim, not the
latitude, decides what is lit. The transfer rule says so on the card, so the
data should match the claim.

## Definition of done

Every MVP variable in `targets.json` carries a grade; no literature constant is
graded better than D; the Artemis regions exist.
