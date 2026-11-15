"""Export per-site ATI samples for human review and TI class calibration."""

from __future__ import annotations

import argparse

import ee

from gee_features import DRIVE_FOLDER, GRID, build_thermal


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sites-asset",
        required=True,
        help="Earth Engine FeatureCollection asset with site_id and ti_class",
    )
    parser.add_argument("--project", help="Earth Engine Cloud project ID")
    parser.add_argument(
        "--description", default="earth_ti_calibration_samples"
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.project:
        ee.Initialize(project=args.project)
    else:
        ee.Initialize()

    sites = ee.FeatureCollection(args.sites_asset)
    samples = build_thermal().select("ati_raw").reduceRegions(
        collection=sites,
        reducer=ee.Reducer.median(),
        crs=GRID["crs"],
        crsTransform=GRID["crsTransform"],
    )
    task = ee.batch.Export.table.toDrive(
        collection=samples,
        description=args.description,
        folder=DRIVE_FOLDER,
        fileFormat="CSV",
        selectors=["site_id", "ti_class", "median"],
    )
    task.start()
    status = task.status()
    print(
        f"{args.description}: state={status['state']} "
        f"task_id={status.get('id', 'unknown')}"
    )
    print(
        "Review the exported site medians by known class, agree on four "
        "increasing breakpoints with Julia/Eduard, then save valid JSON as "
        '{"ati_breakpoints": [b0, b1, b2, b3]}.'
    )


if __name__ == "__main__":
    main()
