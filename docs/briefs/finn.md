# Finn — proxy reframe brief

> **Status: pending the sync decision.** If the team votes no, build F11 as
> originally specced and ignore this.

**This is free if decided before you start F11 at 09:15 Sunday, and expensive
after.** That is the only reason it is being discussed tonight.

## What changes

The site card becomes a **proxy card**. Same data, different claim:

| old | new |
|---|---|
| ✅ Strong analog / ◐ Partial / ❌ Breaks down | **Supports / Conditional / Cannot test** |
| overall similarity gauge | **proxy strength for this experiment** (same number, rescoped and relabelled) |
| mission profile dropdown | experiment dropdown |
| — | **evidence strip**: an A–D chip per variable |

It is not more work than the card you planned — arguably less, because the
three columns are data, not threshold prose. Eduard's worker gives you the
columns pre-sorted; you render them.

## The one non-obvious layout decision

**"Cannot test" must be the most visible column, not the smallest.** It inverts
the usual hierarchy, and it is the single thing most likely to win Validity
points. A judge who sees a tool state its own limits trusts the rest of it.

Suggested weighting: Supports and Conditional side by side on top, Cannot test
full-width underneath with its own heading and no apology. Never collapse it
behind a "show more".

## What you get from the worker

```js
worker.postMessage({ type: 'cell', cellIndex });
// -> { type: 'cellInfo', card }
card.proxy = {
  supports:    [{ id, label, score, grade }],       // matched AND transferable
  conditional: [{ id, label, score, grade, correction }],  // matched, needs a stated correction
  cannot_test: [{ id, label, reason }]              // not transferable, or no Earth equivalent at all
}
card.overall   // renamed in the UI to "proxy strength", same field
```

`grade` is `"A" | "B" | "C" | "D"` — the evidence strip. `correction` is a
sentence from Julia, render it verbatim; do not paraphrase a physics caveat.

Eduard publishes this shape tonight **with placeholder rows** precisely so you
are not blocked on Julia's copy. Build against the placeholders.

## Evidence strip

A small chip per variable, four states. Keep it subtle — it is context, not
decoration — but make the legend reachable (tooltip or one line under the
card): A multiple instruments or ground truth · B single orbital instrument ·
C model-derived · D poorly constrained.

One caveat Julia will give you a line for: a grade-D variable is scored with a
*wider* tolerance, so a poorly-known target scores *higher*. The strip is what
stops that reading as "better match".

## Everything else is unchanged

F12 fly-to, F13 tabs, F15 construction test-campaign text, F16 QA fixes, F17
README. The heatmap you already shipped does not change at all — the scalar it
paints is the same number under a new name.

## What to cut if you are behind

F14 (3D terrain toggle) goes first, as planned. If Sunday midday is tight, the
evidence strip can ship as a single aggregate grade per card rather than per
variable — still honest, much faster.

## Definition of done

Proxy card renders all three columns from worker data with no hard-coded
prose; Cannot test is the most prominent block; evidence chips present with a
legend; no string in the UI says an Earth site *is* a Moon or Mars site.
