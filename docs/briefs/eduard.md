# Eduard — proxy reframe brief

> **Status: pending the sync decision.** Everything below assumes the team votes
> yes. If it votes no, nothing here happens and the existing E-tasks stand.

You are the gate. Julia, Michal and Finn all write against a schema that does
not exist yet, so **your 45 minutes come before their three hours.** Publish the
schema first, implement second.

## Step 1 — schema, tonight, before anything else (~45 min)

### `contract/transfer_rules.yaml` (new file, you create it empty-but-valid)

```yaml
version: 1
# status: transferable | conditional | not_transferable
# Julia fills the rows, Sofia reviews the physics. You own the shape.
rules:
  ti_class:
    moon:
      status: not_transferable
      note: "Thermal inertia of particulate material depends on pore gas pressure.
             In vacuum, conduction between grains is radically lower, so a matching
             Earth class does not behave the same way."
    mars:
      status: conditional
      correction: "Valid only with a stated pressure correction: the same grain size
                   reads a higher TI at 1 bar than at 6 mbar."
  rough_2km:
    moon: {status: conditional, correction: "Compare at the gravity-scaled baseline (330 m)."}
    mars: {status: conditional, correction: "Compare at the gravity-scaled baseline (760 m)."}
  precip_mm:
    moon: {status: transferable}
    mars: {status: transferable}

# Variables with no Earth equivalent at all. These populate the "Cannot test"
# column directly and come from contract/body_constants.json, not from data.
never_testable:
  - {id: gravity,   moon: "1.62 m/s2 (1/6 g)", mars: "3.72 m/s2 (3/8 g)"}
  - {id: radiation, moon: "unshielded GCR and SPE", mars: "no global field"}
  - {id: pressure,  moon: "vacuum", mars: "~6 mbar CO2"}
```

### `targets.json` gains a `grades` block (tell Michal the shape)

```json
"grades": {"relief_km": "B", "slope_med_deg": "B", "ti_class": "B", "bulk_density": "D"},
"grade_notes": {"bulk_density": "literature constant, not measured at this site"}
```

### Grade → σ multiplier (your constant, put it in `score.py`)

| grade | meaning | σ multiplier |
|---|---|---|
| A | multiple instruments or ground truth | ×1.0 |
| B | single orbital instrument, no ground truth | ×1.5 |
| C | model-derived or extrapolated | ×2.5 |
| D | poorly constrained | ×4.0 |

Post all three of these in `#data` the moment they exist. Placeholder content is
fine — Finn needs the **shape**, not the rows.

## Step 2 — engine (Sunday, ~1–2 h)

1. **Grade inflation.** `score_grid()` already accepts `sigma_overrides`. Read
   `target["grades"]`, map through the table, pass it in. ~20 lines.
2. **Rescope the aggregate.** Keep the geometric mean — the heatmap, the hotspot
   suppression and the Pareto filter all need one scalar per cell, so it cannot
   be deleted. Compute it over the experiment's required variables only (weights
   already do this) and rename it **proxy strength** everywhere.
3. **Transfer status per variable** into `site_card()` output, so Finn's three
   columns are pure data: `supports` = matched ∧ transferable, `conditional` =
   matched ∧ conditional, `cannot_test` = not_transferable ∪ never_testable.
4. **`pack_web.py`** copies `transfer_rules.yaml` into the bundle alongside
   `missions.json`.

## Step 3 — validation (only if E9/E10 are green by 11:00)

- **Keep** the known-analog recall test. It runs today and produces numbers.
  Present it as "the Earth-side data and the similarity function behave
  sensibly", not as proof the method is right about Mars.
- **Add grade sensitivity:** re-run with every grade-D variable widened ×2 and
  report whether the top-20 changes. Cheap, and it directly answers "is this
  conclusion resting on your weakest data?"
- **Add leave-one-feature-out** if time allows: match on all variables except
  *f*, then check whether the top sites independently recover *f* within its
  uncertainty, against a random baseline. ~40 lines on `validate.py`. This is
  real predictive validation and it is the strongest thing on the table.

## Watch this

Inflating σ for poorly-known variables makes **poorly-known targets score
higher** — a vague target is easier to match. Nobody will read it that way. The
evidence strip is therefore not decoration; without it the grades actively
mislead. Say this out loud at the sync.

## Definition of done

Schema published tonight; grades drive σ; the card's three columns come from
data not prose; the README records the framing decision, its date, and that it
came out of an AI-assisted discussion the team then argued through.
