"""Add DEM-derived terrain summaries from Michal's local target clips."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Mapping

import numpy as np

from engine.terrain_features import compute


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, np.integer):
        return int(value)
    return value


def terrain_for_clip(path: str | Path, dem_vertical_error_m: float | None = None) -> dict:
    try:
        import rasterio
    except ImportError as exc:
        raise RuntimeError("rasterio is required to read target DEM clips") from exc

    with rasterio.open(path) as source:
        if source.crs is None or not source.crs.is_projected:
            raise ValueError(f"{path}: clip must use a projected metric CRS")
        units = str(source.crs.linear_units or "").lower()
        if units and "metre" not in units and "meter" not in units:
            raise ValueError(f"{path}: projection units must be metres")
        x_res = abs(source.transform.a)
        y_res = abs(source.transform.e)
        if (
            not np.isclose(x_res, y_res)
            or not np.isclose(source.transform.b, 0)
            or not np.isclose(source.transform.d, 0)
        ):
            raise ValueError(f"{path}: pixels must be square and axis-aligned")
        dem = source.read(1).astype(np.float64)
        pixel_m = float(x_res)
        scale = source.scales[0] if source.scales else 1.0
        offset = source.offsets[0] if source.offsets else 0.0
        nodata = source.nodata
        if nodata is not None:
            dem[dem == nodata] = np.nan
        dem = dem * scale + offset
        return compute(
            dem,
            pixel_m,
            dem_vertical_error_m=dem_vertical_error_m,
        )


def update_targets(
    targets: list[dict],
    clips_dir: str | Path,
    vertical_error_m: Mapping[str, float] | None = None,
) -> list[dict]:
    """Update feature p50s while keeping spread and measurement error separate."""
    root = Path(clips_dir)
    result = []
    for target in targets:
        target = dict(target)
        clip = root / f"{target['id']}.tif"
        if not clip.is_file():
            raise FileNotFoundError(f"missing terrain clip for {target['id']}: {clip}")
        error = (vertical_error_m or {}).get(target["id"])
        summaries = terrain_for_clip(clip, error)
        features = dict(target.get("features", {}))
        for key, summary in summaries.items():
            if np.isfinite(summary["p50"]):
                features[key] = summary["p50"]
        target["features"] = features
        target["terrain_windows"] = summaries
        result.append(target)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clips-dir", required=True, help="one projected <target_id>.tif per target")
    parser.add_argument("--targets", default="contract/targets.json")
    parser.add_argument("--out", required=True, help="write updated targets to this separate JSON file")
    parser.add_argument("--vertical-error-m", type=float)
    args = parser.parse_args()
    targets = json.loads(Path(args.targets).read_text(encoding="utf-8"))
    errors = {
        target["id"]: args.vertical_error_m
        for target in targets
        if args.vertical_error_m is not None
    }
    updated = update_targets(targets, args.clips_dir, errors)
    Path(args.out).write_text(
        json.dumps(_json_safe(updated), indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(f"wrote {len(updated)} target terrain summaries to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
