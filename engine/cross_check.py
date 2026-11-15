"""Compare a local DEM's terrain summaries with a GEE tile export."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping

import numpy as np

from engine.terrain_features import compute

DEFAULT_TOLERANCES = {
    "relief_km": 0.10,
    "slope_med_deg": 0.10,
    "slope_p90_deg": 0.10,
    "rough_2km": 0.20,
    "rough_10km": 0.20,
}


def _values(raw: Mapping) -> dict[str, float]:
    values = raw.get("features", raw)
    if not isinstance(values, Mapping):
        raise ValueError("GEE data must be a feature mapping")
    flattened = {}
    for key, value in values.items():
        if isinstance(value, Mapping):
            value = value.get("p50", value.get("value"))
        if value is not None:
            flattened[str(key)] = float(value)
    return flattened


def compare_features(local: Mapping[str, float], gee: Mapping) -> dict:
    """Compare local and GEE values using the agreed per-feature tolerances."""
    remote = _values(gee)
    if not local and not remote:
        raise ValueError("no terrain features were supplied for comparison")
    report = {}
    for key in sorted(set(local) | set(remote)):
        a = float(local.get(key, float("nan")))
        b = float(remote.get(key, float("nan")))
        tolerance = DEFAULT_TOLERANCES.get(key, 0.10)
        if not np.isfinite(a) or not np.isfinite(b):
            report[key] = {
                "local": a,
                "gee": b,
                "relative_difference": None,
                "tolerance": tolerance,
                "status": "missing",
            }
            continue
        relative = abs(a - b) / max(abs(a), abs(b), 1e-9)
        report[key] = {
            "local": a,
            "gee": b,
            "relative_difference": relative,
            "tolerance": tolerance,
            "status": "pass" if relative <= tolerance else "mismatch",
        }
    return report


def run_config(config: Mapping) -> dict:
    """Read a projected DEM and GEE values from one tile-config mapping."""
    try:
        import rasterio
    except ImportError as exc:
        raise RuntimeError("rasterio is required to read the local DEM") from exc

    dem_path = Path(config["dem_path"])
    gee_path = Path(config["gee_json"])
    with rasterio.open(dem_path) as source:
        if source.crs is None or not source.crs.is_projected:
            raise ValueError("DEM must use a projected metric CRS, not latitude/longitude")
        units = str(source.crs.linear_units or "").lower()
        if units and "metre" not in units and "meter" not in units:
            raise ValueError("DEM projection units must be metres")
        x_res = abs(source.transform.a)
        y_res = abs(source.transform.e)
        if (
            not np.isclose(x_res, y_res)
            or not np.isclose(source.transform.b, 0)
            or not np.isclose(source.transform.d, 0)
        ):
            raise ValueError("DEM pixels must be square and axis-aligned")
        dem = source.read(1).astype(np.float64)
        nodata = config.get("nodata", source.nodata)
        scale = source.scales[0] if source.scales else 1.0
        offset = source.offsets[0] if source.offsets else 0.0
        if nodata is not None:
            dem[dem == nodata] = np.nan
        dem = dem * scale + offset
        pixel_m = float(x_res)

    summaries = compute(
        dem,
        pixel_m,
        dem_vertical_error_m=config.get("dem_vertical_error_m"),
    )
    local = {key: value["p50"] for key, value in summaries.items()}
    gee = json.loads(gee_path.read_text(encoding="utf-8"))
    return compare_features(local, gee)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="JSON with dem_path and gee_json")
    parser.add_argument("--out", help="optional JSON report path")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    report = run_config(config)
    for key, result in report.items():
        diff = result["relative_difference"]
        rendered = "n/a" if diff is None else f"{100 * diff:.1f}%"
        print(
            f"{key:16s} {result['status']:8s} "
            f"diff={rendered:>6s} tolerance={100 * result['tolerance']:.0f}%"
        )
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return int(any(item["status"] != "pass" for item in report.values()))


if __name__ == "__main__":
    raise SystemExit(main())
