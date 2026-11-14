"""Unit tests for the similarity engine (task E4 definition of done).

Run from the repo root:   python -m pytest engine/tests -q
(or without pytest:       python engine/tests/test_score.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

from score import (  # noqa: E402
    classify_dimension,
    haversine_km,
    load_contract,
    score_grid,
    top_hotspots,
)

CONTRACT = load_contract()
MVP = [f.id for f in CONTRACT.scored_features(("mvp",))]


def _target(**overrides) -> dict:
    base = {
        "relief_km": 1.2,
        "slope_med_deg": 6.0,
        "slope_p90_deg": 14.0,
        "rough_2km": 9.0,
        "rough_10km": 5.0,
        "ti_class": 2.0,
        "tmin_k": 210.0,
        "tmax_k": 290.0,
        "albedo": 0.18,
        "litho_class": 1.0,
        "ice_idx": 0.1,
        "precip_mm": 0.0,
        "ndvi_max": 0.0,
    }
    base.update(overrides)
    return base


def _grid_from(rows: list[dict]) -> dict:
    return {k: np.array([r[k] for r in rows], dtype=np.float64) for k in rows[0]}


def test_identical_vectors_score_one():
    t = _target()
    grid = _grid_from([dict(t)])
    r = score_grid(grid, t, CONTRACT, tiers=("mvp",))
    assert abs(r.overall[0] - 1.0) < 1e-9, r.overall[0]
    for d, v in r.dims.items():
        assert abs(v[0] - 1.0) < 1e-9, (d, v[0])


def test_one_dead_dimension_drags_the_score_down():
    """The geometric mean must punish a single hopeless dimension.

    Note for the Sunday sigma meeting: the plan's DoD says "S < 0.1" for this
    case, but with the plan's own formula (eps = 0.01) five dimensions with one
    at zero give S ~ 0.40. The behaviour is right - one dead dimension costs
    far more than it would under an arithmetic mean - the number in the DoD
    just assumed a smaller eps. Both are asserted below so the choice is
    explicit rather than accidental.
    """
    t = _target()
    bad = dict(t)
    bad["ndvi_max"] = 0.9  # dimension B collapses, everything else perfect
    grid = _grid_from([bad])

    r = score_grid(grid, t, CONTRACT, tiers=("mvp",))
    arithmetic = float(np.nanmean([v[0] for v in r.dims.values()]))
    assert r.dims["B"][0] < 0.001
    assert r.overall[0] < 0.45
    assert r.overall[0] < arithmetic - 0.3

    harsh = load_contract(eps=1e-6)
    r2 = score_grid(grid, t, harsh, tiers=("mvp",))
    assert r2.overall[0] < 0.1


def test_missing_features_are_renormalised_not_zeroed():
    t = _target()
    partial = dict(t)
    partial["ti_class"] = np.nan
    grid = _grid_from([partial])
    r = score_grid(grid, t, CONTRACT, tiers=("mvp",))
    assert bool(r.partial[0]) is True
    assert abs(r.overall[0] - 1.0) < 1e-9  # the rest still matches perfectly


def test_lithology_matrix_is_used():
    t = _target(litho_class=1.0)
    rows = [dict(t, litho_class=c) for c in (1.0, 3.0, 2.0, 4.0)]
    r = score_grid(_grid_from(rows), t, CONTRACT, tiers=("mvp",))
    s = r.features["litho_class"]
    assert s[0] == 1.0          # basalt vs basalt
    assert abs(s[1] - 0.4) < 1e-9   # basalt vs clastic sediment
    assert abs(s[2] - 0.2) < 1e-9   # basalt vs crystalline
    assert s[3] == 0.0          # basalt vs evaporite


def test_precip_is_compared_in_log_space():
    t = _target(precip_mm=0.0)
    rows = [dict(t, precip_mm=p) for p in (0.0, 10.0, 2000.0)]
    r = score_grid(_grid_from(rows), t, CONTRACT, tiers=("mvp",))
    s = r.features["precip_mm"]
    assert s[0] == 1.0
    assert 0.0 < s[2] < s[1] < 1.0


def test_gravity_swap_changes_the_column_read():
    t = _target()
    grid = _grid_from([dict(t)])
    grid["rough_2km_gM"] = np.array([40.0])   # wildly different from the target
    grid["rough_10km_gM"] = np.array([40.0])

    off = score_grid(grid, t, CONTRACT, gravity_scaling=False, body="moon")
    on = score_grid(grid, t, CONTRACT, gravity_scaling=True, body="moon")
    assert off.features["rough_2km"][0] > 0.99
    assert on.features["rough_2km"][0] < 0.2


def test_hotspots_respect_the_separation_radius():
    # three cells: two neighbours in Nevada, one in Mongolia
    lat = np.array([38.0, 38.5, 45.0])
    lon = np.array([-117.0, -117.2, 103.0])
    scores = np.array([0.9, 0.88, 0.80])
    picked = top_hotspots(scores, lat, lon, k=3, min_sep_km=200.0)
    assert picked == [0, 2]


def test_haversine_sanity():
    d = haversine_km(0.0, 0.0, 0.0, 1.0)
    assert 111.0 < d < 112.0


def test_verdict_thresholds():
    assert classify_dimension(0.95) == "strong"
    assert classify_dimension(0.55) == "partial"
    assert classify_dimension(0.1) == "breaks"
    assert classify_dimension(float("nan")) == "nodata"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL  {name}: {exc}")
    print("all green" if not failures else f"{failures} failing")
    sys.exit(1 if failures else 0)
