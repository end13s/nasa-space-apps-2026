"""Generate Earth feature maps and run regional sanity checks."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REGIONS = {
    "Sahara": (15.0, 30.0, -15.0, 35.0),
    "Atacama": (-28.0, -18.0, -73.0, -67.0),
    "Amazon": (-10.0, 5.0, -75.0, -50.0),
    "Greenland": (60.0, 84.0, -75.0, -10.0),
}
REQUIRED_MVP = {
    "ti_class",
    "tmin_k",
    "tmax_k",
    "albedo",
    "litho_class",
    "ice_idx",
    "precip_mm",
    "ndvi_max",
    "relief_km",
    "slope_med_deg",
    "slope_p90_deg",
    "flat_frac",
    "steep_frac",
}
REQUIRED_SPREADS = {
    "relief_km__sd",
    "slope_med_deg__sd",
    "slope_p90_deg__sd",
    "tmin_k__sd",
    "tmax_k__sd",
    "albedo__sd",
    "ice_idx__sd",
    "precip_mm__sd",
    "ndvi_max__sd",
}


def _region_rows(frame: pd.DataFrame, bounds: tuple[float, float, float, float]):
    south, north, west, east = bounds
    return frame.loc[
        frame["lat"].between(south, north)
        & frame["lon"].between(west, east)
    ]


def _sanity_checks(frame: pd.DataFrame) -> list[str]:
    checks: list[str] = []
    tests = (
        ("Sahara NDVI median <= 0.2", "Sahara", "ndvi_max", 0.2, "max"),
        ("Atacama NDVI median <= 0.2", "Atacama", "ndvi_max", 0.2, "max"),
        ("Amazon NDVI median >= 0.8", "Amazon", "ndvi_max", 0.8, "min"),
        ("Greenland ice_idx median >= 0.9", "Greenland", "ice_idx", 0.9, "min"),
    )
    for label, region, column, threshold, relation in tests:
        if column not in frame.columns:
            checks.append(f"SKIP {label}: {column} is absent")
            continue
        values = _region_rows(frame, REGIONS[region])[column].dropna()
        if values.empty:
            checks.append(f"FAIL {label}: no valid cells in region")
        else:
            median = float(values.median())
            passed = median <= threshold if relation == "max" else median >= threshold
            result = "PASS" if passed else "FAIL"
            checks.append(
                f"{result} {label}: median={median:.3f}, "
                f"n={len(values):,}, threshold={threshold:.2f}"
            )
    return checks


def _write_maps(frame: pd.DataFrame, output_dir: Path) -> int:
    excluded = {"cell_id", "lat", "lon", "qa_flags"}
    columns = [
        column
        for column in frame.select_dtypes(include=[np.number]).columns
        if column not in excluded
    ]
    if not columns:
        raise ValueError("parquet contains no numeric feature columns to map")

    output_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for column in columns:
        values = frame[column].to_numpy(dtype=np.float64)
        finite = np.isfinite(values)
        if not finite.any():
            print(f"WARNING: {column} has no finite values; skipping map.")
            continue
        low, high = np.nanquantile(values, [0.02, 0.98])
        if low == high:
            low, high = float(np.nanmin(values)), float(np.nanmax(values))
        fig, axis = plt.subplots(figsize=(12, 5))
        points = axis.scatter(
            frame["lon"],
            frame["lat"],
            c=values,
            s=0.5,
            cmap="viridis",
            vmin=low,
            vmax=high if high > low else low + 1,
            linewidths=0,
            rasterized=True,
        )
        axis.set(
            title=column,
            xlabel="Longitude",
            ylabel="Latitude",
            xlim=(-180, 180),
            ylim=(-90, 90),
        )
        fig.colorbar(points, ax=axis, label=column)
        fig.tight_layout()
        fig.savefig(output_dir / f"{column}.png", dpi=160)
        plt.close(fig)
        written += 1
    print("Inspect the maps for scan-line striping and spatial artifacts.")
    return written


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid", type=Path, default=Path("earth_grid.parquet"))
    parser.add_argument("--out", type=Path, default=Path("qc_maps"))
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="fail if any MVP feature is absent",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    frame = pd.read_parquet(args.grid)
    required = {"cell_id", "lat", "lon", "qa_flags"}
    missing_columns = required - set(frame.columns)
    if missing_columns:
        raise ValueError(
            "grid is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )
    if frame["cell_id"].duplicated().any():
        raise ValueError("grid has duplicate cell_id values")
    ids = pd.to_numeric(frame["cell_id"], errors="coerce").to_numpy(
        dtype=np.float64
    )
    if (
        not np.isfinite(ids).all()
        or (ids < 0).any()
        or (ids >= 720 * 1440).any()
        or (ids != np.floor(ids)).any()
    ):
        raise ValueError("cell_id values are outside the canonical grid")
    expected_lat = 90 - (ids // 1440 + 0.5) * 0.25
    expected_lon = -180 + (ids % 1440 + 0.5) * 0.25
    if not np.allclose(frame["lat"], expected_lat, atol=1e-4, rtol=0):
        raise ValueError("lat values do not match the canonical cell_id grid")
    if not np.allclose(frame["lon"], expected_lon, atol=1e-4, rtol=0):
        raise ValueError("lon values do not match the canonical cell_id grid")

    flags = pd.to_numeric(frame["qa_flags"], errors="coerce").to_numpy(
        dtype=np.float64
    )
    if (
        not np.isfinite(flags).all()
        or (flags < 0).any()
        or (flags > 15).any()
        or (flags != np.floor(flags)).any()
    ):
        raise ValueError("qa_flags must contain only the defined bits 1, 2, 4, and 8")

    for column in frame.columns:
        if column.endswith("__sd"):
            spread = pd.to_numeric(frame[column], errors="coerce").to_numpy(
                dtype=np.float64
            )
            if (spread[np.isfinite(spread)] < 0).any():
                raise ValueError(f"{column} contains negative spatial spread")

    missing_mvp = sorted(REQUIRED_MVP - set(frame.columns))
    missing_spreads = sorted(REQUIRED_SPREADS - set(frame.columns))
    missing_country = "country_iso3" not in frame.columns
    if missing_spreads:
        missing_mvp.extend(missing_spreads)
    if missing_country:
        missing_mvp.append("country_iso3")
    if missing_mvp:
        message = "MVP features absent: " + ", ".join(missing_mvp)
        if args.require_complete:
            raise ValueError(message)
        print("WARNING: " + message)

    print(f"Rows: {len(frame):,}")
    print(f"Map files written: {_write_maps(frame, args.out)}")
    failures = 0
    for check in _sanity_checks(frame):
        print(check)
        failures += check.startswith("FAIL")
    if failures:
        raise SystemExit(f"{failures} regional sanity check(s) failed")


if __name__ == "__main__":
    main()
