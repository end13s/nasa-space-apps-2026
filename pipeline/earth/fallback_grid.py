"""Build a REAL Earth feature grid without Google Earth Engine.

Why this exists
---------------
The primary Earth pipeline is Clara's Earth Engine export (gee_features.py +
gee_terrain.py). It is better than this in every way: MODIS land *surface*
temperature, a 30 m DEM, thermal-inertia classes, lithology, ice, vegetation.
This module is the fallback for when that export cannot be run - no Earth
Engine credentials, or no time left - so that the project ships measurements of
the real Earth instead of synthetic data.

Sources, both open and login-free
---------------------------------
* ETOPO 2022, 60 arc-second surface elevation (NOAA NCEI)
      -> relief, slope, roughness, buildable and steep ground fractions
* WorldClim 2.1, 10 arc-minute monthly climate normals 1970-2000
      -> coldest-month minimum and warmest-month maximum temperature,
         annual precipitation

Two deviations from the contract, both deliberate and both recorded in the
output metadata. They are reported on the card rather than hidden:

1. **Slope baseline.** ETOPO 60" is about 1.85 km per pixel at the equator, so
   slope is measured at that baseline rather than the contracted 400 m. Slope
   measured over a longer baseline reads systematically lower, so terrain
   comparisons against targets computed at 400 m are biased low. The baseline
   actually used is written into the parquet metadata as `slope_baseline_m`.
   `rough_2km` is not produced at all - a 2 km baseline is one pixel.

2. **Air temperature, not surface temperature.** WorldClim is 2 m air
   temperature; the contract specifies MODIS land surface temperature. In
   deserts the two differ by 10-20 K. These features are therefore graded C
   (model-derived) on the Earth side.

Features this does NOT produce, and which are simply absent (the engine skips a
feature missing from the whole grid, rather than flagging every cell partial):
    ti_class, albedo, litho_class, ice_idx, ndvi_max, soil_moist,
    bulk_density, sand_frac, bedrock_depth_m, aod_p90, wind_p95, rough_2km
and the logistics columns.

Usage
-----
    python pipeline/earth/fallback_grid.py \
        --etopo data_raw/etopo/etopo60s.tif \
        --worldclim data_raw/worldclim \
        --out data_work/earth_grid.parquet

AI-assisted: written with Claude, reviewed by Eduard.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

NROWS, NCOLS = 720, 1440
RES = 0.25

# Buildability thresholds - must match engine/terrain_features.py
FLAT_MAX_DEG = 5.0
STEEP_MIN_DEG = 25.0

EARTH_R_M = 6371008.8


def _read_band(path: Path) -> np.ndarray:
    import rasterio

    with rasterio.open(path) as src:
        arr = src.read(1).astype(np.float32)
        nodata = src.nodata
    if nodata is not None:
        arr = np.where(arr == nodata, np.nan, arr)
    return arr


# ---------------------------------------------------------------------------
# WorldClim -> temperature and precipitation on the 0.25 degree grid
# ---------------------------------------------------------------------------


def _to_grid_mean_sd(a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Resample a 10 arc-minute field (2160x1080) to 0.25 deg, with spread.

    0.25 / (10/60) = 1.5, which is not an integer, so each pixel is first
    split into 2x2 (giving 5 arc-minute cells, exactly 3 per 0.25 degree) and
    then block-averaged. The standard deviation across the 3x3 sub-cells is
    the within-cell spatial spread used for the uncertainty band.
    """
    fine = np.repeat(np.repeat(a, 2, axis=0), 2, axis=1)  # -> 4320 x 2160
    blocks = fine.reshape(NROWS, 3, NCOLS, 3)
    with np.errstate(invalid="ignore"):
        mean = np.nanmean(blocks, axis=(1, 3))
        sd = np.nanstd(blocks, axis=(1, 3))
    return mean.astype(np.float32), sd.astype(np.float32)


def build_climate(wc_dir: Path) -> dict[str, np.ndarray]:
    print("  WorldClim: reading 36 monthly rasters ...")
    tmin = np.stack([_read_band(wc_dir / "tmin" / f"wc2.1_10m_tmin_{m:02d}.tif") for m in range(1, 13)])
    tmax = np.stack([_read_band(wc_dir / "tmax" / f"wc2.1_10m_tmax_{m:02d}.tif") for m in range(1, 13)])
    prec = np.stack([_read_band(wc_dir / "prec" / f"wc2.1_10m_prec_{m:02d}.tif") for m in range(1, 13)])

    with np.errstate(invalid="ignore"):
        coldest = np.nanmin(tmin, axis=0) + 273.15   # coldest-month mean minimum
        warmest = np.nanmax(tmax, axis=0) + 273.15   # warmest-month mean maximum
        annual = np.nansum(prec, axis=0)
        # a cell with no valid month is ocean, not a dry place
        annual = np.where(np.all(np.isnan(prec), axis=0), np.nan, annual)
        amp = np.nanmean(tmax - tmin, axis=0)

    out = {}
    for name, field in (("tmin_k", coldest), ("tmax_k", warmest),
                        ("precip_mm", annual), ("diurnal_amp_k", amp)):
        mean, sd = _to_grid_mean_sd(field)
        out[name] = mean
        out[name + "__sd"] = sd
    return out


# ---------------------------------------------------------------------------
# ETOPO -> terrain on the 0.25 degree grid
# ---------------------------------------------------------------------------


def build_terrain(etopo_path: Path, stripe_rows: int = 60,
                  bed_path: Path | None = None) -> dict[str, np.ndarray]:
    """Terrain statistics per 0.25 degree cell from ETOPO 60 arc-second.

    Processed in horizontal stripes so the 933 MB global array is never held
    in memory at once. Each 0.25 degree cell is exactly 15x15 ETOPO pixels.
    """
    import rasterio

    out = {k: np.full((NROWS, NCOLS), np.nan, np.float32) for k in (
        "relief_km", "slope_med_deg", "slope_p90_deg", "hypso_int",
        "flat_frac", "steep_frac", "rough_10km",
        "relief_km__sd", "slope_med_deg__sd", "elev_m", "land_frac", "ice_idx",
    )}

    bed_src = rasterio.open(bed_path) if bed_path and Path(bed_path).exists() else None
    with rasterio.open(etopo_path) as src:
        H, W = src.height, src.width
        fy, fx = H // NROWS, W // NCOLS          # 15, 15
        print(f"  ETOPO: {W} x {H}, {fx} x {fy} pixels per cell")
        px_m = np.radians(180.0 / H) * EARTH_R_M  # metre size of one pixel in latitude

        for r0 in range(0, NROWS, stripe_rows):
            r1 = min(r0 + stripe_rows, NROWS)
            win = rasterio.windows.Window(0, r0 * fy, W, (r1 - r0) * fy)
            dem = src.read(1, window=win).astype(np.float32)

            # ETOPO is SURFACE elevation including bathymetry. A coastal cell
            # that mixes land with an ocean trench produces several kilometres
            # of fake relief - before this mask the "steepest cells on Earth"
            # came out over the Cayman Trench. Sea-floor pixels are removed
            # from the statistics and the land fraction is recorded, so a cell
            # that is mostly ocean can be flagged rather than trusted.
            is_land = dem > 0

            # Ice thickness = surface - bedrock. ETOPO 2022 compiles both, so
            # every glacier and ice sheet appears. Without this the Antarctic
            # plateau reads as "flat, cold, dry" - i.e. perfectly Martian -
            # and became the top proxy for the Jezero lake delta.
            if bed_src is not None:
                bed = bed_src.read(1, window=win).astype(np.float32)
                iced = is_land & ((dem - bed) > 10.0)
                nb_ = r1 - r0
                landn = is_land.reshape(nb_, fy, NCOLS, fx).sum(axis=(1, 3))
                icen = iced.reshape(nb_, fy, NCOLS, fx).sum(axis=(1, 3))
                with np.errstate(invalid="ignore", divide="ignore"):
                    out["ice_idx"][r0:r1] = np.where(landn > 0, icen / landn, np.nan)
            dem = np.where(is_land, dem, np.nan)

            lat_mid = 90.0 - (np.arange(r0, r1) + 0.5) * RES
            # slope at the native pixel baseline; dx shrinks with cos(lat)
            gy, gx = np.gradient(dem, px_m, px_m)
            coslat = np.cos(np.radians(
                90.0 - (np.arange(dem.shape[0]) + (r0 * fy)) * (180.0 / H)))
            gx = gx / np.maximum(coslat, 0.05)[:, None]
            slope = np.degrees(np.arctan(np.hypot(gx, gy)))

            # detrended roughness at a ~10 km baseline
            from scipy.ndimage import gaussian_filter
            sigma_px = 10000.0 / px_m
            filled = np.where(np.isfinite(dem), dem, 0.0)  # sea treated as flat
            resid = filled - gaussian_filter(filled, sigma=sigma_px, mode="nearest")

            nb = r1 - r0
            out["land_frac"][r0:r1] = is_land.reshape(nb, fy, NCOLS, fx).mean(axis=(1, 3))
            d = dem.reshape(nb, fy, NCOLS, fx)
            s = slope.reshape(nb, fy, NCOLS, fx)
            rr = resid.reshape(nb, fy, NCOLS, fx)
            with np.errstate(invalid="ignore"):
                p95 = np.nanpercentile(d, 95, axis=(1, 3))
                p5 = np.nanpercentile(d, 5, axis=(1, 3))
                dmin = np.nanmin(d, axis=(1, 3))
                dmax = np.nanmax(d, axis=(1, 3))
                dmean = np.nanmean(d, axis=(1, 3))
                out["relief_km"][r0:r1] = (p95 - p5) / 1000.0
                out["relief_km__sd"][r0:r1] = np.nanstd(d, axis=(1, 3)) / 1000.0
                out["elev_m"][r0:r1] = dmean
                span = np.where(dmax - dmin > 1e-6, dmax - dmin, np.nan)
                out["hypso_int"][r0:r1] = (dmean - dmin) / span
                out["slope_med_deg"][r0:r1] = np.nanmedian(s, axis=(1, 3))
                out["slope_p90_deg"][r0:r1] = np.nanpercentile(s, 90, axis=(1, 3))
                out["slope_med_deg__sd"][r0:r1] = np.nanstd(s, axis=(1, 3))
                out["flat_frac"][r0:r1] = np.nanmean((s < FLAT_MAX_DEG), axis=(1, 3))
                out["steep_frac"][r0:r1] = np.nanmean((s > STEEP_MIN_DEG), axis=(1, 3))
                out["rough_10km"][r0:r1] = np.nanstd(rr, axis=(1, 3)) / 10000.0 * 1000.0
            print(f"    rows {r0:4d}-{r1:<4d} done", flush=True)
    return out


# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a real Earth grid without Earth Engine")
    ap.add_argument("--etopo", default="data_raw/etopo/etopo60s.tif")
    ap.add_argument("--etopo-bed", default="data_raw/etopo/etopo60s_bed.tif",
                    help="ETOPO bedrock elevation; surface minus bedrock gives ice thickness")
    ap.add_argument("--worldclim", default="data_raw/worldclim")
    ap.add_argument("--out", default="data_work/earth_grid.parquet")
    args = ap.parse_args()

    cols: dict[str, np.ndarray] = {}
    sources = {}

    wc = Path(args.worldclim)
    if (wc / "tmin").is_dir():
        cols.update(build_climate(wc))
        sources["climate"] = ("WorldClim 2.1, 10 arc-minute monthly normals 1970-2000. "
                              "2 m AIR temperature, not land surface temperature - graded C.")
    else:
        print("  WorldClim missing - skipping temperature and precipitation")

    etopo = Path(args.etopo)
    if etopo.exists():
        cols.update(build_terrain(etopo, bed_path=Path(args.etopo_bed)))
        if not np.isfinite(cols["ice_idx"]).any():
            del cols["ice_idx"]
        sources["terrain"] = ("ETOPO 2022 60 arc-second surface elevation (NOAA NCEI). "
                              "Slope measured at the ~1.85 km pixel baseline, NOT the "
                              "contracted 400 m; rough_2km not produced.")
    else:
        print(f"  ETOPO missing at {etopo} - skipping terrain")

    if not cols:
        raise SystemExit("no sources available - nothing to build")

    # Land mask: real land where ETOPO is above sea level, or where WorldClim
    # reports climate. The union keeps Antarctica (no WorldClim coverage) and
    # below-sea-level land such as Death Valley (ETOPO negative).
    land = np.zeros((NROWS, NCOLS), bool)
    if "land_frac" in cols:
        land |= np.nan_to_num(cols["land_frac"], nan=0.0) > 0.0
    if "tmin_k" in cols:
        land |= np.isfinite(cols["tmin_k"])
    print(f"  land cells: {land.sum():,} ({100*land.mean():.1f} % of the grid)")

    lat = 90.0 - (np.arange(NROWS) + 0.5) * RES
    lon = -180.0 + (np.arange(NCOLS) + 0.5) * RES
    LAT, LON = np.meshgrid(lat, lon, indexing="ij")
    rows, colsi = np.nonzero(land)

    df = pd.DataFrame({
        "cell_id": (rows.astype(np.int32) * NCOLS + colsi).astype(np.int32),
        "lat": LAT[land].astype(np.float32),
        "lon": LON[land].astype(np.float32),
    })
    for name, field in cols.items():
        if name in ("elev_m", "land_frac"):
            continue
        df[name] = field[land].astype(np.float32)

    # zero by definition on the Moon and Mars, measured as zero here
    qa = np.zeros(len(df), np.uint16)
    if "land_frac" in cols:                      # bit 2 = coastal, under 50 % land
        qa |= np.where(cols["land_frac"][land] < 0.5, 2, 0).astype(np.uint16)
    if "tmin_k" in df:
        qa |= np.where(~np.isfinite(df["tmin_k"].to_numpy()), 4, 0).astype(np.uint16)
    df["qa_flags"] = qa

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    marker = Path(str(out) + ".SYNTHETIC")
    if marker.exists():
        marker.unlink()
    Path(str(out) + ".SOURCES.json").write_text(json.dumps({
        "build": "fallback_grid.py (no Earth Engine)",
        "sources": sources,
        "slope_baseline_m": 1855,
        "deviations": [
            "slope and roughness measured at the ETOPO pixel baseline (~1.85 km), not 400 m",
            "temperatures are 2 m air temperature (WorldClim), not MODIS land surface temperature",
        ],
        "ice_idx_note": "ICE-SHEET fraction (ETOPO surface minus bedrock > 10 m). Resolves the "
                        "Antarctic and Greenland ice sheets only - mountain glaciers, small ice "
                        "caps (Svalbard, Patagonia, Alps), permafrost and perennial snow read 0.",
        "earth_grades": {"ice_idx": "B", "tmin_k": "C", "tmax_k": "C", "diurnal_amp_k": "C",
                         "precip_mm": "C", "__terrain__": "B"},
    }, indent=2), encoding="utf-8")

    print(f"\nwrote {out}  ({len(df):,} land cells, {len(df.columns)} columns)")
    print("features:", ", ".join(c for c in df.columns if not c.endswith("__sd")))


if __name__ == "__main__":
    main()
