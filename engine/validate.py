"""Validation protocol and ablation study (task E9, Section 6.1).

The question a judge will ask is "how do you know this works?". This is the
answer: without ever being told where the known analog sites are, does the
method rank them near the top of Earth?

    python engine/validate.py --grid data_work/earth_grid.parquet \
        --targets data_work/targets.json --analogs science/known_analogs.csv \
        --out validation

Writes validation_report.md (for the README and the project page) and
validation.json (for Julia's Validation tab).

Target: at least 70 % of known analogs inside the top 10 % of land cells.
If we miss it, we tune sigma globally - never per site, which would be
overfitting - and we report the miss honestly.

AI-assisted: scaffolded with Claude, reviewed by Eduard.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from score import DIM_ORDER, haversine_km, load_contract, score_grid

NULL_SAMPLES = 1000


def best_score_per_cell(grid, targets, contract, body, weights=None, gravity=False, drop_dim=None):
    """S_body(x) = max over that body's preset targets of S(x, t)."""
    w = dict(contract.default_weights() if weights is None else weights)
    if drop_dim:
        w[drop_dim] = 0.0

    best = np.full(len(next(iter(grid.values()))), np.nan)
    for t in targets:
        if t.get("body") != body:
            continue
        r = score_grid(grid, t["features"], contract, weights=w, gravity_scaling=gravity, body=body)
        best = np.fmax(best, r.overall)
    return best


def percentile_ranks(scores: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """Percentile rank (0-100) of the given cells among all scored land cells."""
    valid = np.isfinite(scores)
    ranked = np.argsort(np.argsort(scores[valid]))
    pct = np.full(len(scores), np.nan)
    pct[valid] = 100.0 * ranked / max(valid.sum() - 1, 1)
    return pct[idx]


def nearest_cells(lat, lon, sites: pd.DataFrame) -> list[int]:
    """Index of the grid cell closest to each site."""
    out = []
    for _, row in sites.iterrows():
        d = haversine_km(lat, lon, float(row["lat"]), float(row["lon"]))
        out.append(int(np.argmin(d)))
    return out


def evaluate(grid, lat, lon, targets, analogs, contract, body, gravity=False, drop_dim=None):
    sites = analogs[analogs["analog_for"].str.lower() == body]
    if len(sites) == 0:
        return None
    scores = best_score_per_cell(grid, targets, contract, body, gravity=gravity, drop_dim=drop_dim)
    idx = np.array(nearest_cells(lat, lon, sites))
    pct = percentile_ranks(scores, idx)

    rng = np.random.default_rng(42)
    valid = np.flatnonzero(np.isfinite(scores))
    null_idx = rng.choice(valid, size=min(NULL_SAMPLES, valid.size), replace=False)
    null_pct = percentile_ranks(scores, null_idx)

    return {
        "body": body,
        "n_sites": int(len(sites)),
        "median_percentile": float(np.nanmedian(pct)),
        "null_median_percentile": float(np.nanmedian(null_pct)),
        "recall_top5": float(np.nanmean(pct >= 95.0)),
        "recall_top10": float(np.nanmean(pct >= 90.0)),
        "sites": [
            {
                "id": str(r["id"]),
                "name": str(r["name"]),
                "percentile": float(p),
                "accessible_by_design": str(r.get("accessible_by_design", "")).lower() == "yes",
            }
            for (_, r), p in zip(sites.iterrows(), pct)
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Analog Atlas validation + ablation")
    ap.add_argument("--grid", required=True)
    ap.add_argument("--targets", required=True)
    ap.add_argument("--analogs", default="science/known_analogs.csv")
    ap.add_argument("--out", default="validation")
    args = ap.parse_args()

    contract = load_contract()
    df = pd.read_parquet(args.grid)
    lat = df["lat"].to_numpy(dtype=np.float64)
    lon = df["lon"].to_numpy(dtype=np.float64)
    grid = {f.id: df[f.id].to_numpy(dtype=np.float64) for f in contract.features if f.id in df.columns}
    targets = json.loads(Path(args.targets).read_text(encoding="utf-8"))
    analogs = pd.read_csv(args.analogs).dropna(subset=["lat", "lon"])

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {"headline": {}, "ablation": {}, "synthetic": any(t.get("synthetic") for t in targets)}
    for body in ("moon", "mars"):
        base = evaluate(grid, lat, lon, targets, analogs, contract, body)
        if base is None:
            continue
        report["headline"][body] = base

        abl = {}
        for d in DIM_ORDER:
            if d not in base and d not in contract.dimensions:
                continue
            r = evaluate(grid, lat, lon, targets, analogs, contract, body, drop_dim=d)
            if r:
                abl[f"without_{d}"] = round(r["median_percentile"] - base["median_percentile"], 2)
        g = evaluate(grid, lat, lon, targets, analogs, contract, body, gravity=True)
        if g:
            abl["gravity_scaling_on"] = round(g["median_percentile"] - base["median_percentile"], 2)
        report["ablation"][body] = abl

    (out_dir / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = ["# Validation report", ""]
    if report["synthetic"]:
        lines += ["> **Built from SYNTHETIC data.** These numbers mean nothing until the",
                  "> real grids and fingerprints are in place. Do not quote them.", ""]
    for body, r in report["headline"].items():
        lines += [
            f"## {body.capitalize()} ({r['n_sites']} known analogs)",
            "",
            f"- median percentile of known analogs: **{r['median_percentile']:.1f}** "
            f"(null baseline {r['null_median_percentile']:.1f})",
            f"- recall in the top 5 % of land cells: **{100 * r['recall_top5']:.0f} %**",
            f"- recall in the top 10 % of land cells: **{100 * r['recall_top10']:.0f} %** "
            f"(target: 70 %)",
            "",
            "| site | percentile | accessible by design |",
            "|---|---:|---|",
        ]
        for s in sorted(r["sites"], key=lambda s: -s["percentile"]):
            lines.append(
                f"| {s['name']} | {s['percentile']:.1f} | "
                f"{'yes' if s['accessible_by_design'] else 'no'} |"
            )
        lines += ["", "### Ablation (change in median percentile)", "",
                  "| variant | delta |", "|---|---:|"]
        for k, v in report["ablation"].get(body, {}).items():
            lines.append(f"| {k} | {v:+.2f} |")
        lines.append("")

    lines += [
        "## How to read this",
        "",
        "Known analog sites were partly chosen because they are accessible, not only",
        "because they are physically similar. Sites marked *accessible by design* are",
        "expected to rank lower, and that is a property of the ground truth, not a",
        "failure of the method.",
        "",
    ]
    (out_dir / "validation_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out_dir / 'validation_report.md'} and {out_dir / 'validation.json'}")
    for body, r in report["headline"].items():
        print(f"  {body}: median percentile {r['median_percentile']:.1f}, "
              f"top-10% recall {100 * r['recall_top10']:.0f} %")


if __name__ == "__main__":
    main()
