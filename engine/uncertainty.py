"""Monte-Carlo uncertainty band on the overall score (task E11, stretch).

Every feature has a spread: the within-cell standard deviation of the Earth
measurement (the `__sd` columns) and the spread of the target fingerprint
inside its 15 km circle (the `sd` block of targets.json). A score of 0.81 that
could just as easily be 0.55 is a different claim from one that could not.

For the top N cells we draw N_MC samples of both sides and report P10/P50/P90.

In the browser this runs in the worker only after the user picks a target, over
the top 500 cells, so it never blocks the first heatmap.
"""

from __future__ import annotations

import numpy as np

from score import Contract, score_grid

N_MC = 30


def uncertainty_band(
    grid: dict[str, np.ndarray],
    grid_sd: dict[str, np.ndarray],
    target: dict,
    target_sd: dict,
    contract: Contract,
    subset: np.ndarray,
    n_mc: int = N_MC,
    weights: dict | None = None,
    body: str | None = None,
    seed: int = 0,
) -> dict[str, np.ndarray]:
    """P10 / P50 / P90 of S for the cells in ``subset``.

    grid/grid_sd  feature id -> full-length arrays (value and 1-sigma spread)
    target        feature id -> value;  target_sd: feature id -> 1-sigma
    subset        indices of the cells to evaluate (e.g. the top 500)
    """
    rng = np.random.default_rng(seed)
    sub = {k: v[subset] for k, v in grid.items()}
    sub_sd = {k: grid_sd.get(k, np.zeros_like(v))[subset] for k, v in grid.items()}

    samples = np.empty((n_mc, len(subset)), dtype=np.float64)
    for i in range(n_mc):
        noisy_grid = {
            k: v + rng.normal(0.0, np.nan_to_num(sub_sd[k], nan=0.0))
            for k, v in sub.items()
        }
        noisy_target = {
            k: float(v + rng.normal(0.0, float(target_sd.get(k, 0.0) or 0.0)))
            for k, v in target.items()
        }
        # classes stay integers: jittering a class label is meaningless
        for spec in contract.features:
            if spec.sigma_mode in ("class", "matrix"):
                if spec.id in noisy_grid:
                    noisy_grid[spec.id] = sub[spec.id]
                if spec.id in noisy_target:
                    noisy_target[spec.id] = target[spec.id]

        r = score_grid(noisy_grid, noisy_target, contract, weights=weights, body=body)
        samples[i] = r.overall

    return {
        "p10": np.nanpercentile(samples, 10, axis=0),
        "p50": np.nanpercentile(samples, 50, axis=0),
        "p90": np.nanpercentile(samples, 90, axis=0),
    }
