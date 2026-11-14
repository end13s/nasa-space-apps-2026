"""Pareto front over the dimension scores (task E11, stretch).

One number hides trade-offs. A site that is the best terrain match and a poor
thermal match is not "worse" than a middling site with a higher weighted mean -
it is a different choice. The Pareto front is the set of sites that no other
site beats on *every* dimension, which is the honest way to show that.

    python engine/pareto.py --grid ... --targets ... --target-id mars_jezero

The JS port lives in web/src/worker/ as a simple O(n^2) loop over the top 5000
cells; this module is the reference and the offline tool.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from score import load_contract, score_grid, top_hotspots


def pareto_front(points: np.ndarray) -> np.ndarray:
    """Boolean mask of non-dominated rows (higher is better on every column).

    O(n log n)-ish in practice: sort by the first column descending, then sweep.
    NaN is treated as the worst possible value so partial cells never dominate.
    """
    p = np.where(np.isfinite(points), points, -np.inf)
    n = len(p)
    order = np.argsort(-p[:, 0], kind="stable")
    keep = np.zeros(n, dtype=bool)
    front: list[int] = []
    for i in order:
        dominated = False
        for j in front:
            if np.all(p[j] >= p[i]) and np.any(p[j] > p[i]):
                dominated = True
                break
        if not dominated:
            front.append(int(i))
    keep[front] = True
    return keep


def main() -> None:
    ap = argparse.ArgumentParser(description="Pareto front of Earth sites for one target")
    ap.add_argument("--grid", required=True)
    ap.add_argument("--targets", required=True)
    ap.add_argument("--target-id", required=True)
    ap.add_argument("--pool", type=int, default=5000, help="top-N cells by overall score")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    contract = load_contract()
    df = pd.read_parquet(args.grid)
    grid = {f.id: df[f.id].to_numpy(dtype=np.float64) for f in contract.features if f.id in df.columns}
    targets = {t["id"]: t for t in json.loads(Path(args.targets).read_text(encoding="utf-8"))}
    t = targets[args.target_id]

    r = score_grid(grid, t["features"], contract, body=t.get("body"))
    dims = [d for d in r.dims if contract.default_weights().get(d, 0) > 0]
    pool = np.argsort(-np.nan_to_num(r.overall, nan=-1.0))[: args.pool]

    pts = np.column_stack([r.dims[d][pool] for d in dims])
    mask = pareto_front(pts)
    chosen = pool[mask]

    # thin out neighbours so the scatter is readable
    keep = top_hotspots(
        r.overall[chosen],
        df["lat"].to_numpy()[chosen],
        df["lon"].to_numpy()[chosen],
        k=60,
        min_sep_km=200.0,
    )
    rows = [
        {
            "cell_id": int(df["cell_id"].to_numpy()[chosen][i]),
            "lat": float(df["lat"].to_numpy()[chosen][i]),
            "lon": float(df["lon"].to_numpy()[chosen][i]),
            "overall": float(r.overall[chosen][i]),
            **{d: float(r.dims[d][chosen][i]) for d in dims},
        }
        for i in keep
    ]
    payload = {"target": args.target_id, "dimensions": dims, "sites": rows}
    out = Path(args.out) if args.out else None
    if out:
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"wrote {out} ({len(rows)} non-dominated sites)")
    else:
        print(json.dumps(payload, indent=2)[:2000])


if __name__ == "__main__":
    main()
