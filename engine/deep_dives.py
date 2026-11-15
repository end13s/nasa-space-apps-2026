"""Generate the Discoveries-tab cards from real scores (task S9/S10).

For each (target, experiment profile) pair: score the Earth grid, apply novelty
mode (hide cells within 100 km of a documented analog site), keep picks at
least 1000 km apart, take the best complete cell, and write

    science/deep_dives/<card>.md     the card, with the numbers behind it
    science/deep_dives/index.json    the list the Discoveries tab renders

Numbers always come from the engine. Place names, summaries and the field
campaign come from science/deep_dives/curated.json, written by a person after
looking at the site - and they are only attached if the engine still picks a
cell within CURATION_MATCH_KM of the curated one. If the data changes and the
pick moves, the card falls back to an explicit DRAFT banner instead of quietly
describing a different place.

    python engine/deep_dives.py

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
    # (card id, target, experiment profile, question)
    ("lunar_polar_ops", "moon_shackleton_rim", "lunar_south_pole_ops",
     "Where on Earth can a crew rehearse surface operations under polar light on terrain like the Shackleton rim?"),
    ("mars_lake_sediments", "mars_jezero_delta", "mars_astrobiology",
     "Where on Earth can a sampling team rehearse work on dry, unvegetated, low-relief ground like the Jezero delta?"),
    ("base_site_prep", "moon_artemis_haworth", "base_construction",
     "Where on Earth can construction robots rehearse site preparation on ground shaped like the Haworth region?"),
]

NOVELTY_KM = 100.0
DIVERSITY_KM = 1000.0       # three cards in one mountain range teach a judge nothing new
CURATION_MATCH_KM = 50.0


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

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cur_path = out / "curated.json"
    curated = json.loads(cur_path.read_text(encoding="utf-8")) if cur_path.exists() else {}

    near_known = np.full(len(df), np.inf)
    for _, k in known.iterrows():
        np.minimum(near_known, haversine_km(lat, lon, float(k["lat"]), float(k["lon"])), out=near_known)
    novel = near_known >= NOVELTY_KM
    # Coastal cells (under 50 % land, qa bit 2) mix land with sea; a showcased
    # site should describe one place, not an average of a desert and an ocean.
    if "qa_flags" in df.columns:
        novel &= (df["qa_flags"].to_numpy() & 2) == 0
    spec_of = {f.id: f for f in c.features}

    chosen: list[tuple[float, float]] = []
    index = []
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
        clat, clon = float(row["lat"]), float(row["lon"])
        chosen.append((clat, clon))

        cur = curated.get(card_id)
        if cur and haversine_km(clat, clon, cur["lat"], cur["lon"]) > CURATION_MATCH_KM:
            print(f"  {card_id}: pick moved {haversine_km(clat, clon, cur['lat'], cur['lon']):.0f} km "
                  f"from the curated site - writing a DRAFT card")
            cur = None

        ns, ew = ("N" if clat >= 0 else "S"), ("E" if clon >= 0 else "W")
        name = cur["name"] if cur else f"{prof['name']} — {abs(clat):.1f}°{ns}, {abs(clon):.1f}°{ew}"
        summary = cur["summary"] if cur else (
            f"Best complete, novel Earth cell for this experiment against {t['name']}: "
            f"proxy strength {card['proxy_strength']:.2f}. Not yet reviewed.")

        lines = [f"# {name}", ""]
        if not cur:
            lines += ["> **DRAFT — not yet reviewed.** The numbers come from the engine; the place has "
                      "not been checked on imagery. Add an entry to `curated.json` before showing this card.", ""]
        lines += [
            f"**Experiment.** {prof['name']}, against **{t['name']}** ({t['body'].capitalize()}).",
            "",
            f"**Question.** {question}",
            "",
            f"**Where.** {fmt(clat, 3)}°, {fmt(clon, 3)}°"
            + (f" — {cur['place']}" if cur else "")
            + f". [Open in Worldview](https://worldview.earthdata.nasa.gov/?v={clon-1:.2f},{clat-1:.2f},{clon+1:.2f},{clat+1:.2f}). "
            f"{near_known[i]:.0f} km from the nearest documented analog site — not a place the field already uses.",
            "",
            f"**Proxy strength:** {card['proxy_strength']:.2f}. A secondary figure; the three columns below are the claim.",
            "",
        ]
        if abs(clat) > 60 and "ice_idx" in df.columns and row["ice_idx"] < 0.05 and not cur:
            lines += ["> ⚠ **Ice status unresolved.** Above 60° our ice layer only resolves the Antarctic "
                      "and Greenland ice sheets; small ice caps are invisible to it. Check imagery.", ""]
        if cur and cur.get("why"):
            lines += ["## Why this site", "", cur["why"], ""]

        lines += ["## Target vs candidate", "",
                  "| feature | target | candidate | similarity | grade |",
                  "|---|---:|---:|---:|---|"]
        for fid, arr in r.features.items():
            s = float(arr[i])
            g = (t.get("grades") or {}).get(fid) or (t.get("grades") or {}).get("__terrain__", "C")
            unit = spec_of[fid].unit if fid in spec_of else ""
            lines.append(f"| {fid} ({unit}) | {fmt(t['features'].get(fid))} | "
                         f"{fmt(row[fid] if fid in df.columns else None)} | {fmt(s, 3)} | {g} |")
        lines.append("")

        def col(title, rows, key):
            o = [f"## {title}", ""]
            if not rows:
                o.append("_None._")
            for x in rows:
                sc = f" — similarity {x['score']:.2f}" if x.get("score") is not None else ""
                o.append(f"- **{x['label']}**{sc}. {x.get(key) or ''}".rstrip())
            return o + [""]

        lines += col("Supports", card["supports"], "note")
        lines += col("Conditional — usable with the stated correction", card["conditional"], "correction")
        lines += col("Cannot test here", card["cannot_test"], "reason")
        if cur and cur.get("campaign"):
            lines += ["## The field campaign this enables", "", cur["campaign"], ""]
        lines += [f"*Numbers generated by `engine/deep_dives.py` from the shipped Earth grid and "
                  f"`contract/targets.json`{'; place and campaign text reviewed by the team' if cur else ''}.*"]
        (out / f"{card_id}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

        index.append({
            "id": card_id, "name": name, "lat": clat, "lon": clon, "body": t["body"],
            "summary": summary, "target": tid, "profile": pid, "file": f"{card_id}.md",
            "proxy_strength": round(card["proxy_strength"], 3), "reviewed": bool(cur),
        })
        print(f"  {card_id:22s} -> {clat:7.2f}, {clon:8.2f}  strength {card['proxy_strength']:.3f}  "
              f"{'reviewed' if cur else 'DRAFT'}  [{len(card['supports'])}/{len(card['conditional'])}/{len(card['cannot_test'])}]")

    (out / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
