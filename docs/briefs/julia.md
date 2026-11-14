# Julia — proxy reframe brief

> **Adopted at the Saturday sync.** This is the plan now, not a proposal.
> Anything in your existing task list that this does not mention is unchanged.

You get the biggest shift, and your night **reorders**. Two people — Finn and
Eduard — block on one file you write. It moves ahead of your UI copy.

## What changes in one sentence

The app stops claiming "this Earth site resembles Mars" and starts claiming
"for this experiment, this site supports these conclusions, needs a correction
for these, and cannot test these at all". You own the words that make that
claim true.

## 1. Transfer table — `contract/transfer_rules.yaml` — **by 22:00 tonight**

This is the new critical path. Eduard publishes the file shape; you fill the
rows. One row per variable, per body:

- **transferable** — a match means the same thing on both bodies
- **conditional** — a match is usable *only with a stated correction*, and you
  write that correction in one sentence
- **not_transferable** — matching numbers do not imply matching behaviour

~20 variables × 2 bodies. Most rows are quick (`precip_mm` on the Moon: zero on
both, transferable). A handful carry the whole project:

| variable | the thing to say |
|---|---|
| `ti_class` | Thermal inertia depends on pore gas pressure: 1 bar on Earth, ~6 mbar on Mars, vacuum on the Moon. The same sand reads higher on Earth. **Conditional for Mars, not transferable for the Moon.** |
| `rough_*` | Only comparable at the gravity-scaled baseline — conditional, correction stated. |
| `tmin_k` / `tmax_k` | Earth cannot reach 25–40 K PSR temperatures or lunar noon. Not transferable for the Moon. |
| `ndvi_max` | A match means "no vegetation confound". Transferable — but Earth biology is still a contamination source for biosignature work, which belongs in Cannot test. |
| gravity, radiation, pressure | No Earth site tests these. They are permanent **Cannot test** rows, sourced from `body_constants.json`. |

Sofia reviews the physics. If a row would take more than five minutes to
justify, mark it `conditional` with an honest note and move on.

**If this file isn't done by 22:00, say so in `#blockers` and it gets cut** —
Finn cannot build the card against nothing.

## 2. `missions.json` → experiment profiles (~20 min)

Rename and add one array. A profile stops being "a planet mood" and becomes an
experiment a mission team would actually run:

```json
{
  "id": "rover_nav_dry_regolith",
  "name": "Autonomous navigation in dry regolith",
  "purpose": "Test autonomous mapping and traverse planning on loose, dry, unvegetated ground.",
  "required_variables": ["slope_med_deg", "slope_p90_deg", "rough_2km", "ti_class", "ndvi_max", "flat_frac"],
  "weights": {"T": 3, "H": 3, "M": 1, "C": 1, "W": 1, "B": 0, "A": 0, "I": 1}
}
```

Keep the weights you already wrote — just add `required_variables` and rename
so each reads as an experiment: "Excavation in indurated regolith", "Drill
performance in ice-bearing ground", "Thermal cycling of structural coatings",
"Autonomous mapping under extreme aridity", "Base construction and site prep".

## 3. `breaks_text.json` — this one gets *smaller*

The "Cannot test" column is generated from the transfer table plus the
`always_on` body constants you already wrote. So the per-dimension
break-down prose you were going to write mostly disappears. What stays: the
`why` line per dimension (one sentence, why the variable matters), and the
always-on constants.

## 4. UI copy (J6) — unchanged work, new labels

- The gauge is **proxy strength for this experiment**, never "similarity to Mars".
- Column headers: **Supports / Conditional / Cannot test**.
- The evidence strip needs a one-line legend: A multiple instruments or ground
  truth, B single orbital instrument, C model-derived, D poorly constrained.
- One sentence in the About modal that a higher grade-D tolerance means a
  *vaguer* target, not a better one — otherwise the grades mislead.

## Video and page (J10, J12)

The narrative gets simpler and more honest. The line to beat:

> "Earth can't be Mars. But for the right experiment, the right place on Earth
> is a proxy — and we show exactly where the proxy stops."

The "Cannot test" column on screen for two seconds is worth more to a judge
than any heatmap flourish.

## Unchanged

J1 team admin (still the thing that decides whether we can win at all), J2
known analogs, J3 calibration sites, J4 regolith constants, J8 QA, J13 Submit.

## Definition of done

Transfer table complete and reviewed by Sofia; every profile reads as an
experiment with its required variables listed; no string anywhere in the app
claims an Earth site *is* a lunar or Martian site.
