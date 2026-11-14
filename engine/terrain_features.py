"""The single shared definition of every terrain feature.

**Owner: Sofia** (task S1). Scaffolded by Eduard so that the engine, the fake
data generator and the tests have something to run against from the first
hour - Sofia replaces or extends the internals, keeps the signatures.

Why one module: terrain feeds every similarity score, and it is the part most
likely to break silently if the Earth code and the Moon/Mars code compute
things slightly differently. Michal imports this (do not rewrite it); Sofia
reimplements the same definitions in Earth Engine for the global Earth export
and proves both versions agree on the test tiles (S4). If they drift, every
cross-body score is comparing apples to oranges and the UI cannot show it.

Main entry point
----------------
    compute(dem_m, px_m, nodata=None, baselines=("rough_2km", "rough_10km"))

``dem_m`` must already be in a **local metric projection** (equal-distance,
centred on the cell or target circle) - never a lat/lon grid. At 85 S a degree
of longitude is 9 km, and roughness measured "per degree" means nothing.

Returns a dict whose keys are feature ids from
contract/feature_dictionary.yaml: relief_km, slope_med_deg, slope_p90_deg,
hypso_int, flat_frac, steep_frac and one entry per requested roughness
baseline.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter

# Roughness baselines in metres. The gravity-scaled ones correspond to the
# 2 km and 10 km planetary baselines under 1/g landform scaling; they must
# match contract/body_constants.json -> gravity_scaled_baselines_m.
BASELINES_M = {
    "rough_2km": 2000.0,
    "rough_10km": 10000.0,
    "rough_2km_gM": 330.0,
    "rough_10km_gM": 1657.0,
    "rough_2km_gR": 759.0,
    "rough_10km_gR": 3794.0,
}

SLOPE_BASELINE_M = 400.0

# Buildability thresholds (dimension C). Finn's expert call (F4) may move
# these - if it does, change them HERE ONLY, tell Eduard, and both the Earth
# export and the planetary fingerprints stay consistent.
FLAT_MAX_DEG = 5.0
STEEP_MIN_DEG = 25.0


# ---------------------------------------------------------------------------
# Individual features
# ---------------------------------------------------------------------------


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


def slope_deg(dem_m: np.ndarray, px_m: float) -> np.ndarray:
    """Slope magnitude in degrees from a projected (equal-distance) DEM."""
    gy, gx = np.gradient(dem_m, px_m, px_m)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def slope_field_400m(dem_m: np.ndarray, px_m: float) -> np.ndarray:
    """Slope at the agreed 400 m baseline.

    The DEM is block-averaged to ~400 m first, so the slope means the same
    thing whether the source was 30 m Copernicus or 200 m MOLA-HRSC.
    """
    factor = max(1, int(round(SLOPE_BASELINE_M / px_m)))
    coarse = _block_mean(dem_m, factor)
    return slope_deg(coarse, px_m * factor)


def slope_stats(dem_m: np.ndarray, px_m: float) -> tuple[float, float]:
    """(median slope, 90th-percentile slope) at the 400 m baseline."""
    s = slope_field_400m(dem_m, px_m)
    v = s[np.isfinite(s)]
    if v.size < 4:
        return float("nan"), float("nan")
    return float(np.median(v)), float(np.percentile(v, 90))


def buildability(dem_m: np.ndarray, px_m: float) -> tuple[float, float]:
    """(flat_frac, steep_frac) - dimension C, the construction MVP features.

    flat_frac  share of the area with slope < FLAT_MAX_DEG  (buildable)
    steep_frac share of the area with slope > STEEP_MIN_DEG (no-build)
    Both at the same 400 m baseline as the other slope features, so a site
    card can state them next to slope_med_deg without a caveat.
    """
    s = slope_field_400m(dem_m, px_m)
    v = s[np.isfinite(s)]
    if v.size < 4:
        return float("nan"), float("nan")
    return float((v < FLAT_MAX_DEG).mean()), float((v > STEEP_MIN_DEG).mean())


def roughness_permille(dem_m: np.ndarray, px_m: float, baseline_m: float) -> float:
    """std(DEM - Gaussian(DEM, L)) / L * 1000, the detrended roughness.

    Normalising by the baseline makes the number behave like a slope, which is
    what lets the gravity-scaled comparison mean anything.
    """
    sigma_px = baseline_m / px_m
    if sigma_px < 0.5 or dem_m.shape[0] < 3 * sigma_px:
        return float("nan")
    filled = np.where(np.isfinite(dem_m), dem_m, np.nanmean(dem_m))
    smooth = gaussian_filter(filled, sigma=sigma_px, mode="reflect")
    resid = filled - smooth
    return float(np.std(resid) / baseline_m * 1000.0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def compute(
    dem_m: np.ndarray,
    px_m: float,
    nodata: float | None = None,
    baselines: tuple[str, ...] = ("rough_2km", "rough_10km"),
) -> dict[str, float]:
    """All terrain + buildability features for one cell or target circle.

    dem_m     2-D elevation array in metres, in a local metric projection.
    px_m      ground sample distance in metres (isotropic).
    nodata    sentinel value to mask out, if the raster uses one.
    baselines which roughness baselines to compute (keys of BASELINES_M).
    """
    dem = np.asarray(dem_m, dtype=np.float64)
    if nodata is not None:
        dem = np.where(dem == nodata, np.nan, dem)

    med, p90 = slope_stats(dem, px_m)
    flat, steep = buildability(dem, px_m)
    out = {
        "relief_km": relief_km(dem),
        "slope_med_deg": med,
        "slope_p90_deg": p90,
        "hypso_int": hypsometric_integral(dem),
        "flat_frac": flat,
        "steep_frac": steep,
    }
    for key in baselines:
        out[key] = roughness_permille(dem, px_m, BASELINES_M[key])
    return out


# Back-compat alias; `compute` is the name in Sofia's task description.
terrain_features = compute


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
    """Cross-check helper for S4: numpy vs GEE, or Earth vs planetary code.

    Returns {feature: (mine, theirs, relative difference, ok/MISMATCH)}.
    Sofia's agreed tolerances: relief and slope within 10 %, roughness within
    20 %. Anything failing goes in #data before either pipeline exports.
    """
    report = {}
    for k in sorted(set(mine) | set(theirs)):
        a, b = mine.get(k, float("nan")), theirs.get(k, float("nan"))
        denom = max(abs(a), abs(b), 1e-9)
        rel = abs(a - b) / denom
        report[k] = (a, b, rel, "ok" if rel <= tol_rel else "MISMATCH")
    return report
