"""Shared terrain feature definitions - numpy reference (Section 7.3).

**Critical rule from the plan:** Clara's Earth (GEE) code and Michal's planetary
(rasterio) code must compute the same numbers from the same DEM. This file is
the definition. Michal calls it directly. Clara reimplements it in Earth Engine
and then proves the two agree on one test tile with ``compare_tile`` below -
a 0.25 degree cell over Meteor Crater is the agreed tile.

If these drift apart, every cross-body similarity score is comparing apples to
oranges and no amount of good UI saves the project.

AI-assisted: scaffolded with Claude, reviewed by Eduard.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter

# Gravity-scaled roughness baselines, metres. Must match
# contract/body_constants.json -> gravity_scaled_baselines_m.
BASELINES_M = {
    "rough_2km": 2000.0,
    "rough_10km": 10000.0,
    "rough_2km_gM": 330.0,
    "rough_10km_gM": 1657.0,
    "rough_2km_gR": 759.0,
    "rough_10km_gR": 3794.0,
}

SLOPE_BASELINE_M = 400.0


def relief_km(dem_m: np.ndarray) -> float:
    """P95 minus P5 elevation, in kilometres."""
    v = dem_m[np.isfinite(dem_m)]
    if v.size < 10:
        return float("nan")
    return float((np.percentile(v, 95) - np.percentile(v, 5)) / 1000.0)


def hypsometric_integral(dem_m: np.ndarray) -> float:
    v = dem_m[np.isfinite(dem_m)]
    if v.size < 10:
        return float("nan")
    lo, hi = float(v.min()), float(v.max())
    if hi - lo < 1e-6:
        return float("nan")
    return float((v.mean() - lo) / (hi - lo))


def slope_deg(dem_m: np.ndarray, pixel_m: float) -> np.ndarray:
    """Slope magnitude in degrees from a projected (equal-distance) DEM."""
    gy, gx = np.gradient(dem_m, pixel_m, pixel_m)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def slope_stats(dem_m: np.ndarray, pixel_m: float) -> tuple[float, float]:
    """(median slope, 90th-percentile slope) at the 400 m baseline.

    The DEM is box-averaged to ~400 m first, so that the slope means the same
    thing whether the source was 30 m Copernicus or 200 m MOLA-HRSC.
    """
    factor = max(1, int(round(SLOPE_BASELINE_M / pixel_m)))
    coarse = _block_mean(dem_m, factor)
    s = slope_deg(coarse, pixel_m * factor)
    v = s[np.isfinite(s)]
    if v.size < 4:
        return float("nan"), float("nan")
    return float(np.median(v)), float(np.percentile(v, 90))


def roughness_permille(dem_m: np.ndarray, pixel_m: float, baseline_m: float) -> float:
    """std(DEM - Gaussian(DEM, L)) / L * 1000, the detrended roughness.

    Normalising by the baseline makes the number behave like a slope, which is
    what lets the gravity-scaled comparison in Section 5.3 mean anything.
    """
    sigma_px = baseline_m / pixel_m
    if sigma_px < 0.5 or dem_m.shape[0] < 3 * sigma_px:
        return float("nan")
    filled = np.where(np.isfinite(dem_m), dem_m, np.nanmean(dem_m))
    smooth = gaussian_filter(filled, sigma=sigma_px, mode="nearest")
    resid = filled - smooth
    return float(np.std(resid) / baseline_m * 1000.0)


def terrain_features(dem_m: np.ndarray, pixel_m: float, which: list[str] | None = None) -> dict:
    """All terrain features for one cell or target circle.

    dem_m     2-D elevation array in metres, already in an equal-distance
              projection centred on the cell (so ``pixel_m`` is isotropic).
    pixel_m   ground sample distance in metres.
    """
    which = which or ["rough_2km", "rough_10km"]
    med, p90 = slope_stats(dem_m, pixel_m)
    out = {
        "relief_km": relief_km(dem_m),
        "slope_med_deg": med,
        "slope_p90_deg": p90,
        "hypso_int": hypsometric_integral(dem_m),
    }
    for key in which:
        out[key] = roughness_permille(dem_m, pixel_m, BASELINES_M[key])
    return out


def _block_mean(a: np.ndarray, factor: int) -> np.ndarray:
    if factor <= 1:
        return a
    ny, nx = a.shape
    ny2, nx2 = (ny // factor) * factor, (nx // factor) * factor
    if ny2 == 0 or nx2 == 0:
        return a
    b = a[:ny2, :nx2].reshape(ny2 // factor, factor, nx2 // factor, factor)
    return np.nanmean(b, axis=(1, 3))


def compare_tile(mine: dict, theirs: dict, tol_rel: float = 0.15) -> dict:
    """Clara vs Michal on the shared test tile.

    Returns {feature: (mine, theirs, relative difference, pass/fail)}. Anything
    failing goes into #data before either pipeline exports for real.
    """
    report = {}
    for k in sorted(set(mine) | set(theirs)):
        a, b = mine.get(k, float("nan")), theirs.get(k, float("nan"))
        denom = max(abs(a), abs(b), 1e-9)
        rel = abs(a - b) / denom
        report[k] = (a, b, rel, "ok" if rel <= tol_rel else "MISMATCH")
    return report
