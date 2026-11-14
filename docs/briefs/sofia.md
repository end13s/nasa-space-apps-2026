# Sofia — proxy reframe brief

> **Adopted at the Saturday sync.** This is the plan now, not a proposal.
> Anything in your existing task list that this does not mention is unchanged.

Your workload barely moves. What changes is where two things you were already
going to write end up living, and they end up somewhere more useful.

## 1. The gravity-scaling caveat becomes a contract row (~15 min)

You were going to write a paragraph saying gravity scaling is a heuristic. It
now becomes a formal row in `contract/transfer_rules.yaml`, which the app
renders on every card:

```yaml
rough_2km:
  moon: {status: conditional,
         correction: "Comparable only at the Moon-gravity-scaled baseline of 330 m.
                      Landform size scales roughly as 1/g; this ignores material
                      strength and erosion history."}
  mars: {status: conditional,
         correction: "Comparable only at the Mars-gravity-scaled baseline of 760 m."}
```

Same sentence you would have written, now attached to the number it qualifies
instead of buried in a README. Julia writes the table; **you review the physics
on every row**, and these are yours outright.

While you are there, the rows worth your judgement: `ti_class` (pore gas
pressure — conditional for Mars, not transferable for the Moon), `tmin_k` /
`tmax_k` (not transferable for the Moon, Earth cannot reach PSR cold),
`flat_frac` / `steep_frac` (transferable as geometry, but slope *stability* is
gravity-dependent — worth a conditional note).

## 2. Validation interpretation gains one question (S6)

Same session with Eduard, one extra thing to look at: **does the ranking flip
when grade-D variables are widened?** If one poorly-constrained number decides
the top 20, the card has to say so. That is a finding, not a failure.

Keep the existing known-analog recall test. The reframe document argues it is
weak because those sites encode the same intuitions we encode — that critique
is fair, but it is still the only check we have against external ground truth,
it runs today, and "the method is not broken" is what a judge wants shown.
Present it as a sanity check on the Earth-side data, not as proof we are right
about Mars.

If Eduard gets leave-one-feature-out working Sunday morning, **that** becomes
the headline validity number and you interpret it: match on everything except
feature *f*, then see whether the top sites independently recover *f*. That is
a predictive claim, and it is much stronger than recall.

## 3. Discovery hunt gets a sharper question (S7)

Instead of "best analog overall", run it per experiment: *the best proxy for
autonomous navigation in dry regolith*, *the best proxy for excavation in
indurated regolith*, *the best proxy for ice-bearing drilling*. Same procedure,
same filters, same Worldview artifact check — but each of your three
deep-dive sites is now the answer to a specific question, which is far easier
to write up and far more useful to a mission team.

Prefer variety as planned: one lunar-polar-ish, one Mars astrobiology, one
surprise.

## 4. Deep dives (S9) gain one section

Each card already states "where it breaks". Now it also states **what a
campaign here could and could not prove**, split the same three ways as the
app: Supports / Conditional / Cannot test. Finn writes the construction
paragraph for each; you write the science scope.

## Completely unchanged, and still the most important work you have

- **S1–S4: the terrain module and the cross-check.** Nothing in this reframe
  touches it. If your GEE export and the numpy module disagree by 30 % on
  roughness, every proxy card in the app is wrong and no amount of honest
  framing saves it. This is still the single highest-value task on the team.
- S5 Artemis terrain with Michal — the hand-off needs starting now, not at
  21:00. Agree who holds `targets.json` when; the suggestion is Michal owns the
  file and you send him terrain dicts.
- S8 terrain profiles, S11 README, S12 fact-check.

## Definition of done

Every conditional row in the transfer table has a correction you would defend
to a geologist; the gravity-scaling caveat appears on the cards rather than
only in the README; the cross-check table is posted regardless of what the
sync decides.
