"""Generate the Discoveries-tab deep-dive cards from real scores (task S9/S10).

For each (target, experiment profile) pair, score the Earth grid, apply novelty
mode (hide cells within 100 km of a documented analog site), take the best
complete cell, and write a markdown card with the numbers behind it.

The cards are *data-backed drafts*: every number comes from the engine, and the
three columns come from the same proxy-card logic the app uses. What a script
cannot do is name the place well or judge whether it is reachable, so each card
ends with an explicit checklist for a human to finish before it is shown.

    python engine/deep_dives.py --grid data_work/earth_fallback.parquet \
        --targets contract/targets.json --out science/deep_dives

AI-assisted: written with Claude, reviewed by Eduard.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from score import (
    grade_sigma_overrides,
    haversine_km,
    load_contract,
    load_transfer_rules,
    proxy_card,
    score_grid,
    top_hotspots,
)

PICKS = [
    # (card id, target, experiment profile, one-line question)
    ("lunar_polar_ops", "moon_shackleton_rim", "lunar_south_pole_ops",
     "Where on Earth can a crew rehearse surface operations on rough, cold, low-relief-to-high-relief polar terrain like the Shackleton rim?"),
    ("mars_lake_sediments", "mars_jezero_delta", "mars_astrobiology",
     "Where on Earth can a sampling team rehearse work on dry, unvegetated, sediment-dominated ground like the Jezero delta?"),
    ("base_site_prep", "moon_artemis_haworth", "base_construction",
     "Where on Earth can construction robots rehearse site preparation on ground that is as flat, firm and dry as the Haworth candidate region?"),
]

NOVELTY_KM = 100.0
# Each Discoveries card should show a different place - the brief asks for
# variety, and three cards in one mountain range teach a judge nothing new.
DIVERSITY_KM = 1000.0


def fmt(v, nd=2):
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.{nd}f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", default="data_work/earth_fallback.parquet")
    ap.add_argument("--targets", default="contract/targets.json")
    ap.add_argument("--analogs", default="science/known_analogs.csv")
    ap.add_argument("--missions", default="science/missions.json")
    ap.add_argument("--out", default="science/deep_dives")
    args = ap.parse_args()

    c = load_contract()
    tr = load_transfer_rules()
    df = pd.read_parquet(args.grid)
    lat, lon = df["lat"].to_numpy(np.float64), df["lon"].to_numpy(np.float64)
    grid = {f.id: df[f.id].to_numpy(np.float64) for f in c.features if f.id in df.columns}
    targets = {t["id"]: t for t in json.loads(Path(args.targets).read_text(encoding="utf-8"))}
    profiles = {p["id"]: p for p in json.loads(Path(args.missions).read_text(encoding="utf-8"))["profiles"]}
    known = pd.read_csv(args.analogs).dropna(subset=["lat", "lon"])

    near_known = np.full(len(df), np.inf)
    for _, k in known.iterrows():
        np.minimum(near_known, haversine_km(lat, lon, float(k["lat"]), float(k["lon"])), out=near_known)
    novel = near_known >= NOVELTY_KM

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    spec_of = {f.id: f for f in c.features}

    chosen: list[tuple[float, float]] = []
    for card_id, tid, pid, question in PICKS:
        if tid not in targets or pid not in profiles:
            print(f"  skip {card_id}: missing {tid if tid not in targets else pid}")
            continue
        t, prof = targets[tid], profiles[pid]
        r = score_grid(grid, t["features"], c, weights=prof["weights"], body=t["body"],
                       sigma_overrides=grade_sigma_overrides(c, t))
        allowed = novel.copy()
        for clat, clon in chosen:
            allowed &= haversine_km(lat, lon, clat, clon) >= DIVERSITY_KM
        hs = top_hotspots(r.overall, lat, lon, k=3, mask=allowed, partial=r.partial)
        if not hs:
            print(f"  skip {card_id}: no complete novel cell")
            continue
        i = hs[0]
        card = proxy_card(r, i, t, tr, c)
        row = df.iloc[i]
        chosen.append((float(row["lat"]), float(row["lon"])))

        lines = [
            f"# {prof['name']}: an Earth proxy for {t['name']}",
            "",
            f"> **Draft generated from the engine.** Every number below comes from the scores; "
            f"the place name and the access notes need a human check before this card is shown.",
            "",
            f"**Question.** {question}",
            "",
            f"**Candidate.** {fmt(row['lat'],3)}°, {fmt(row['lon'],3)}° — "
            f"[open in Worldview](https://worldview.earthdata.nasa.gov/?v={row['lon']-1:.2f},{row['lat']-1:.2f},{row['lon']+1:.2f},{row['lat']+1:.2f}). "
            f"{near_known[i]:.0f} km from the nearest documented analog site, so this is not a place the field already uses.",
            "",
            *( [f"> ⚠ **Ice status unresolved.** This cell is above 60° latitude and our ice layer "
                f"reads it as ice-free, but that layer (ETOPO surface minus bedrock) only resolves the "
                f"Antarctic and Greenland ice sheets. Small ice caps are invisible to it. **Check "
                f"imagery before showing this card** - if the site is glaciated, use the next candidate.",
                ""]
               if abs(row["lat"]) > 60 and "ice_idx" in df.columns and row["ice_idx"] < 0.05 else [] ),
            f"**Proxy strength for this experiment:** {card['proxy_strength']:.3f} "
            f"(geometric mean over the experiment's weighted dimensions; a secondary figure — the columns below are the claim).",
            "",
            "## Target vs candidate",
            "",
            "| feature | target | candidate | similarity | grade |",
            "|---|---:|---:|---:|---|",
        ]
        for fid, arr in r.features.items():
            s = float(arr[i])
            tv = t["features"].get(fid)
            ev = row[fid] if fid in df.columns else None
            unit = spec_of[fid].unit if fid in spec_of else ""
            g = (t.get("grades") or {}).get(fid) or (t.get("grades") or {}).get("__terrain__", "C")
            lines.append(f"| {fid} ({unit}) | {fmt(tv)} | {fmt(ev)} | {fmt(s,3)} | {g} |")

        def col(title, rows, key):
            out_lines = [f"## {title}", ""]
            if not rows:
                out_lines.append("_None._")
            for x in rows:
                extra = x.get(key) or ""
                score = f" — similarity {x['score']:.2f}" if x.get("score") is not None else ""
                out_lines.append(f"- **{x['label']}**{score}. {extra}".rstrip())
            return out_lines + [""]

        lines += [""]
        lines += col("Supports", card["supports"], "note")
        lines += col("Conditional — usable with the stated correction", card["conditional"], "correction")
        lines += col("Cannot test", card["cannot_test"], "reason")
        lines += [
            "## Before this card is shown",
            "",
            "- [ ] Name the place and the nearest settlement (Worldview link above)",
            "- [ ] Check the cell on imagery: is it the terrain the numbers say, or a data artifact?",
            "- [ ] Note access: road, permits, protected-area status",
            "- [ ] One sentence on the field campaign this site would enable",
            "",
            f"*Generated by `engine/deep_dives.py` from `{Path(args.grid).name}` and `{Path(args.targets).name}`.*",
        ]
        (out / f"{card_id}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"  {card_id:22s} -> {row['lat']:.2f}, {row['lon']:.2f}  strength {card['proxy_strength']:.3f}  "
              f"[{len(card['supports'])} supports / {len(card['conditional'])} conditional / {len(card['cannot_test'])} cannot]")


if __name__ == "__main__":
    main()
