"""Shared terrain features for Earth, Moon, and Mars."""
from __future__ import annotations

import warnings

import numpy as np
from scipy.ndimage import gaussian_filter

GRID_M = 500.0
WINDOW_M = 1000.0
# Features whose contract value is an area share, reported as a mean, not a p50.
AREA_SHARE_FEATURES = ("flat_frac", "steep_frac")
FLAT_DEG = 5.0
STEEP_DEG = 25.0
MIN_WINDOWS = 9
L_2KM = 2000.0
L_10KM = 10000.0

SENS_BASELINES = {
    "moon": {"rough_2km_gM": 330.0, "rough_10km_gM": 1650.0},
    "mars": {"rough_2km_gR": 760.0, "rough_10km_gR": 3800.0},
}


def _fill(dem: np.ndarray, nodata: float | None) -> np.ndarray:
    values = np.array(dem, dtype=float, copy=True)
    if nodata is not None:
        values[values == nodata] = np.nan
    return values


def _validate_grid(dem: np.ndarray, px_m: float) -> None:
    if dem.ndim != 2 or not dem.size:
        raise ValueError("dem must be a non-empty 2-D array")
    if not np.isfinite(px_m) or px_m <= 0:
        raise ValueError("px_m must be a finite positive number")


def _resample(a: np.ndarray, px_m: float, grid_m: float) -> tuple[np.ndarray, float]:
    k = max(1, int(round(grid_m / px_m)))
    ny, nx = a.shape
    ny2, nx2 = ny // k * k, nx // k * k
    if ny2 == 0 or nx2 == 0:
        return np.empty((0, 0), dtype=float), k * px_m
    blocks = a[:ny2, :nx2].reshape(ny2 // k, k, nx2 // k, k)
    return np.nanmean(blocks, axis=(1, 3)), k * px_m


def _slope(grid: np.ndarray, px_m: float) -> np.ndarray:
    if min(grid.shape) < 2:
        return np.full(grid.shape, np.nan)
    dzdy, dzdx = np.gradient(grid, px_m, px_m)
    return np.degrees(np.arctan(np.hypot(dzdx, dzdy)))


def _windows(shape: tuple[int, int], width: int):
    ny, nx = shape
    for i in range(0, ny - width + 1, width):
        for j in range(0, nx - width + 1, width):
            yield i, j


def _residual(grid: np.ndarray, px_m: float, length_m: float) -> np.ndarray:
    finite = np.isfinite(grid)
    if not finite.any():
        return np.full(grid.shape, np.nan)
    filled = np.where(finite, grid, np.nanmean(grid))
    return grid - gaussian_filter(filled, sigma=length_m / px_m, mode="reflect")


def _rough_windows(
    residual: np.ndarray, px_m: float, width: int, length_m: float
) -> list[float]:
    values = []
    for i, j in _windows(residual.shape, width):
        block = residual[i:i + width, j:j + width]
        if np.isfinite(block).any():
            values.append(float(np.sqrt(np.nanmean(block ** 2)) / length_m * 1000.0))
    return values


def _summarise(
    values: list[float], unit: str, err: float | None = None, err_note: str = ""
) -> dict:
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    n = int(v.size)
    if n:
        p10, p50, p90 = (float(x) for x in np.percentile(v, [10, 50, 90]))
    else:
        p10 = p50 = p90 = float("nan")
    return {
        "p10": p10,
        "p50": p50,
        "p90": p90,
        "err": err,
        "err_note": err_note or ("" if err is not None else "not propagated"),
        "n": n,
        "unit": unit,
        "provisional": n < MIN_WINDOWS,
    }


def compute(
    dem: np.ndarray,
    px_m: float,
    *,
    nodata: float | None = None,
    dem_vertical_error_m: float | None = None,
    grid_m: float = GRID_M,
    window_m: float = WINDOW_M,
) -> dict[str, dict]:
    """Return window quantiles and propagated measurement error per feature."""
    raw = _fill(dem, nodata)
    _validate_grid(raw, px_m)
    if not np.isfinite(grid_m) or grid_m <= 0:
        raise ValueError("grid_m must be a finite positive number")
    if not np.isfinite(window_m) or window_m <= 0:
        raise ValueError("window_m must be a finite positive number")
    if dem_vertical_error_m is not None and (
        not np.isfinite(dem_vertical_error_m) or dem_vertical_error_m < 0
    ):
        raise ValueError("dem_vertical_error_m must be finite and non-negative")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        grid, px_g = _resample(raw, px_m, grid_m)
        width = max(1, int(round(window_m / px_g)))
        slope = _slope(grid, px_g)
        res2 = _residual(grid, px_g, L_2KM)
        res10 = _residual(grid, px_g, L_10KM)

        relief, hypsometry, slope_median, slope_p90 = [], [], [], []
        flat, steep = [], []
        for i, j in _windows(grid.shape, width):
            g = grid[i:i + width, j:j + width]
            if not np.isfinite(g).any():
                continue
            s = slope[i:i + width, j:j + width]
            p5, p95 = np.nanpercentile(g, [5, 95])
            relief.append(float((p95 - p5) / 1000.0))
            lo, hi = np.nanmin(g), np.nanmax(g)
            hypsometry.append(float((np.nanmean(g) - lo) / (hi - lo)) if hi > lo else np.nan)
            valid_slope = np.isfinite(s)
            if valid_slope.any():
                sv = s[valid_slope]
                slope_median.append(float(np.median(sv)))
                slope_p90.append(float(np.percentile(sv, 90)))
                flat.append(float(np.mean(sv < FLAT_DEG)))
                steep.append(float(np.mean(sv > STEEP_DEG)))

        rough2 = _rough_windows(res2, px_g, width, L_2KM)
        rough10 = _rough_windows(res10, px_g, width, L_10KM)

    error = dem_vertical_error_m
    relief_error = error * np.sqrt(2) / 1000.0 if error is not None else None
    slope_error = (
        float(np.degrees(np.arctan(np.sqrt(2) * error / px_g)))
        if error is not None
        else None
    )
    independent = "independent-error assumption"
    relief_error_note = (
        f"two elevations, error x sqrt(2), {independent}"
        if error is not None
        else "DEM vertical accuracy not supplied"
    )
    slope_error_note = (
        f"approximate, from elevation error over grid spacing, {independent}"
        if error is not None
        else "DEM vertical accuracy not supplied"
    )
    return {
        "relief_km": _summarise(
            relief, "km", relief_error, relief_error_note,
        ),
        "slope_med_deg": _summarise(
            slope_median, "deg", slope_error, slope_error_note,
        ),
        "slope_p90_deg": _summarise(
            slope_p90, "deg", slope_error, slope_error_note,
        ),
        "rough_2km": _summarise(rough2, "permil"),
        "rough_10km": _summarise(rough10, "permil"),
        "hypso_int": _summarise(hypsometry, "0-1"),
        "flat_frac": _summarise(flat, "0-1"),
        "steep_frac": _summarise(steep, "0-1"),
    }


def compute_sensitivity(
    dem: np.ndarray,
    px_m: float,
    body: str,
    *,
    nodata: float | None = None,
    window_m: float = WINDOW_M,
) -> dict:
    """Return gravity-scaled roughness as sensitivity-only outputs."""
    if body not in SENS_BASELINES:
        raise ValueError(f"body must be one of {list(SENS_BASELINES)}")
    native = _fill(dem, nodata)
    _validate_grid(native, px_m)
    if not np.isfinite(window_m) or window_m <= 0:
        raise ValueError("window_m must be a finite positive number")
    spec = SENS_BASELINES[body]
    if px_m > min(spec.values()) / 3:
        raise ValueError(
            f"pixel {px_m} m too coarse for a {min(spec.values())} m baseline"
        )
    width = max(1, int(round(window_m / px_m)))
    features = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for key, length_m in spec.items():
            residual = _residual(native, px_m, length_m)
            values = _rough_windows(residual, px_m, width, length_m)
            features[key] = _summarise(values, "permil", None, "sensitivity only")
    return {
        "body": body,
        "horizontal_axis": "gravity_scaled_sensitivity",
        "features": features,
    }


def terrain_features(
    dem_m: np.ndarray,
    px_m: float,
    nodata: float | None = None,
    baselines: tuple[str, ...] = ("rough_2km", "rough_10km"),
    grid_m: float = GRID_M,
) -> dict[str, float]:
    """Compatibility interface returning scalar p50 values for existing callers.

    ``grid_m`` is the resampling grid, i.e. the slope baseline. It must match
    the Earth grid the targets are compared against: 500 m for the 30 m
    Copernicus export, ~1855 m for the ETOPO 60 arc-second fallback grid.
    Comparing a 500 m target slope with a 1855 m Earth slope biases every
    terrain match, because slope over a longer baseline reads lower.
    """
    summaries = compute(dem_m, px_m, nodata=nodata, grid_m=grid_m)
    out = {key: float(summary["p50"]) for key, summary in summaries.items()}
    # The contract defines each scalar over the WHOLE footprint (the target
    # circle / the Earth cell): relief is P95 - P5 of the footprint, slope_p90
    # is the 90th percentile of its slopes, flat_frac is the share of its area
    # below 5 deg. compute() instead summarises per 1 km window and reports the
    # median across windows - a different statistic, and a degenerate one once
    # a window is a single pixel (relief inside one pixel is zero). The Earth
    # grid is computed over the whole cell, so these must be too. Same resample,
    # slope, residual and thresholds as compute(); only the statistic differs.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        grid, px_g = _resample(_fill(dem_m, nodata), px_m, grid_m)
        if np.isfinite(grid).sum() >= 4:
            z = grid[np.isfinite(grid)]
            p5, p95 = np.percentile(z, [5, 95])
            out["relief_km"] = float((p95 - p5) / 1000.0)
            span = float(z.max() - z.min())
            out["hypso_int"] = float((z.mean() - z.min()) / span) if span > 1e-6 else float("nan")
            slope = _slope(grid, px_g)
            sv = slope[np.isfinite(slope)]
            if sv.size:
                out["slope_med_deg"] = float(np.median(sv))
                out["slope_p90_deg"] = float(np.percentile(sv, 90))
                out["flat_frac"] = float(np.mean(sv < FLAT_DEG))
                out["steep_frac"] = float(np.mean(sv > STEEP_DEG))
            for key, length in (("rough_2km", L_2KM), ("rough_10km", L_10KM)):
                if key in out and length / px_g >= 0.5:
                    res = _residual(grid, px_g, length)
                    if np.isfinite(res).any():
                        out[key] = float(np.sqrt(np.nanmean(res ** 2)) / length * 1000.0)
    for key in baselines:
        if key in out:
            continue
        body = "moon" if key.endswith("_gM") else "mars" if key.endswith("_gR") else None
        if body is None:
            raise KeyError(key)
        sensitivity = compute_sensitivity(dem_m, px_m, body, nodata=nodata)
        out[key] = float(sensitivity["features"][key]["p50"])
    return out


def compare_tile(
    mine: dict, theirs: dict, tol_rel: float = 0.15
) -> dict[str, tuple[float, float, float, str]]:
    """Compare corresponding numeric feature values by relative difference."""
    if not np.isfinite(tol_rel) or tol_rel < 0:
        raise ValueError("tol_rel must be finite and non-negative")
    report = {}
    for key in sorted(set(mine) | set(theirs)):
        a = float(mine.get(key, float("nan")))
        b = float(theirs.get(key, float("nan")))
        if not np.isfinite(a) or not np.isfinite(b):
            report[key] = (a, b, float("inf"), "MISMATCH")
            continue
        denom = max(abs(a), abs(b), 1e-9)
        relative = abs(a - b) / denom
        report[key] = (a, b, relative, "ok" if relative <= tol_rel else "MISMATCH")
    return report
