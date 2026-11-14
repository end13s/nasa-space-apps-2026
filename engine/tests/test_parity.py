"""Python <-> JavaScript parity test (task E6 definition of done).

The browser never runs engine/score.py: it runs web/src/worker/score_core.js.
This test proves the two produce the same number on 1000 random cells, so the
validation report and the heatmap a judge sees are the same method.

    python engine/tests/test_parity.py        # needs node on PATH

Tolerance: 1e-3 on the overall score, as agreed in the plan.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
ENGINE = ROOT / "engine"
sys.path.insert(0, str(ENGINE))

from pack_web import MISSING, dequantize  # noqa: E402
from score import load_contract, score_grid  # noqa: E402

TOL = 1e-3
N_CELLS = 1000
SEED = 7


def build_job(contract, rng):
    """Random packed cells plus a random target, in the on-the-wire format."""
    specs = [f for f in contract.features if not f.earth_only and f.scored]
    all_specs = contract.features  # the .bin carries every column

    codes = rng.integers(0, 256, size=(N_CELLS, len(all_specs)), dtype=np.uint8)
    # make ~3 % genuinely missing so the renormalisation path is exercised
    codes[rng.random(codes.shape) < 0.03] = MISSING

    target_features = {}
    for s in specs:
        if s.sigma_mode == "matrix":
            target_features[s.id] = float(rng.integers(1, 6))
        elif s.sigma_mode == "class":
            target_features[s.id] = float(rng.integers(0, 5))
        else:
            target_features[s.id] = float(rng.uniform(s.lo, s.hi))

    meta = {
        "n_cells": N_CELLS,
        "eps": contract.eps,
        "grid": {"ncols": 1440, "nrows": 720, "res_deg": 0.25, "lat0": 90.0, "lon0": -180.0},
        "features": [
            {
                "id": s.id,
                "dim": s.dim,
                "tier": s.tier,
                "lo": s.lo,
                "hi": s.hi,
                "sigma": s.sigma,
                "sigma_mode": s.sigma_mode,
                "sigma_floor": s.sigma_floor,
                "gravity_swap": s.gravity_swap,
                "earth_only": s.earth_only,
                "scored": s.scored,
            }
            for s in all_specs
        ],
        "litho_matrix": contract.litho_matrix.tolist(),
    }
    weights = {"T": 1.0, "H": 1.0, "M": 1.0, "W": 1.0, "B": 1.0, "C": 1.0, "A": 0.0, "I": 0.0}
    return meta, codes, all_specs, target_features, weights


def run_node(job: dict) -> dict:
    with tempfile.TemporaryDirectory() as td:
        job_path = Path(td) / "job.json"
        job_path.write_text(json.dumps(job), encoding="utf-8")
        out = subprocess.run(
            ["node", str(ENGINE / "tests" / "parity_runner.mjs"), str(job_path)],
            capture_output=True,
            text=True,
        )
    if out.returncode != 0:
        raise RuntimeError(f"node failed:\n{out.stderr}")
    return json.loads(out.stdout)


def main(gravity: bool = False) -> int:
    contract = load_contract()
    rng = np.random.default_rng(SEED)
    meta, codes, all_specs, target_features, weights = build_job(contract, rng)

    job = {
        "meta": meta,
        "features": codes.reshape(-1).tolist(),
        "target": {"features": target_features, "body": "mars"},
        "weights": weights,
        "gravityScaling": gravity,
        "body": "mars",
    }
    js = run_node(job)

    # Python side: dequantize exactly as the JS does, then score.
    grid = {
        s.id: dequantize(codes[:, j], s.lo, s.hi)
        for j, s in enumerate(all_specs)
    }
    py = score_grid(
        grid,
        target_features,
        contract,
        weights=weights,
        gravity_scaling=gravity,
        body="mars",
    )

    js_scores = np.array(js["scores"], dtype=np.float64)
    both_nan = np.isnan(js_scores) & np.isnan(py.overall)
    diff = np.where(both_nan, 0.0, np.abs(js_scores - py.overall))
    worst = float(np.nanmax(diff))

    label = "gravity ON " if gravity else "gravity OFF"
    print(f"  {label}  cells={N_CELLS}  max |JS - Python| = {worst:.2e}")
    for d, arr in py.dims.items():
        if d in js["dims"]:
            dd = np.nanmax(np.abs(np.array(js["dims"][d], dtype=np.float64) - arr))
            print(f"      dim {d}: {dd:.2e}")
    if worst > TOL:
        idx = int(np.nanargmax(diff))
        print(f"  FAIL at cell {idx}: JS {js_scores[idx]} vs Python {py.overall[idx]}")
        return 1
    return 0


if __name__ == "__main__":
    rc = main(gravity=False) + main(gravity=True)
    print("parity OK" if rc == 0 else "PARITY BROKEN - fix score.py / score_core.js together")
    sys.exit(1 if rc else 0)
