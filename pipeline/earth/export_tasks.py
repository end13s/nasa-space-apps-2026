"""Launch the independent Earth Engine exports for the Earth grid.

Run after installing the Earth pipeline dependencies and authenticating Earth
Engine. ATI thresholds and a GLiM asset are optional inputs; without them the
thermal output includes raw ATI for calibration and lithology is not exported.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

import ee

from gee_features import (
    build_ice,
    build_land_quality,
    build_lithology,
    build_logistics,
    build_protected,
    build_soil,
    build_thermal,
    build_water_biology,
    export_options,
)


def _read_breakpoints(path: Path | None) -> tuple[float, ...] | None:
    if path is None:
        return None
    data: Any = json.loads(path.read_text(encoding="utf-8"))
    values = data.get("ati_breakpoints") if isinstance(data, dict) else data
    if not isinstance(values, list):
        raise ValueError(
            "ATI threshold file must be a JSON list or an object with "
            "'ati_breakpoints'"
        )
    if len(values) != 4:
        raise ValueError("ATI threshold file must contain four breakpoints")
    return tuple(float(value) for value in values)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", help="Earth Engine Cloud project ID")
    parser.add_argument(
        "--ti-breakpoints",
        type=Path,
        help="JSON file with four calibrated ATI breakpoints",
    )
    parser.add_argument(
        "--glim-asset",
        help="Uploaded Earth Engine FeatureCollection asset ID for GLiM",
    )
    parser.add_argument(
        "--glim-code-property",
        default="lithology",
        help="GLiM feature property containing codes from lithology_classes.yaml",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        choices=(
            "soil",
            "thermal",
            "water_biology",
            "ice",
            "logistics",
            "land_quality",
            "lithology",
        ),
        help="Launch only selected task groups",
    )
    return parser.parse_args()


def build_exports(
    ti_breakpoints: tuple[float, ...] | None,
    glim_asset: str | None,
    glim_code_property: str,
    selected: set[str],
) -> dict[str, ee.Image]:
    builders: dict[str, Callable[[], ee.Image]] = {
        "soil": build_soil,
        "thermal": lambda: build_thermal(ti_breakpoints),
        "water_biology": build_water_biology,
        "ice": build_ice,
        "logistics": lambda: build_logistics().addBands(build_protected()),
        "land_quality": build_land_quality,
    }
    aliases = {
        "soil": "earth_soil",
        "thermal": "earth_thermal",
        "water_biology": "earth_water_bio",
        "ice": "earth_ice",
        "logistics": "earth_logistics",
        "land_quality": "earth_land_quality",
        "lithology": "earth_lithology",
    }
    if glim_asset:
        builders["lithology"] = lambda: build_lithology(
            glim_asset, glim_code_property
        )
    return {
        aliases[group]: builders[group]()
        for group in sorted(selected)
        if group in builders
    }


def main() -> None:
    args = _parse_args()
    breakpoints = _read_breakpoints(args.ti_breakpoints)
    aliases = {
        "soil": "earth_soil",
        "thermal": "earth_thermal",
        "water_biology": "earth_water_bio",
        "ice": "earth_ice",
        "logistics": "earth_logistics",
        "land_quality": "earth_land_quality",
        "lithology": "earth_lithology",
    }
    selected = set(args.only or aliases)
    if args.only is None and not args.glim_asset:
        selected.discard("lithology")
    if "lithology" in selected and not args.glim_asset:
        raise ValueError(
            "To export lithology, provide --glim-asset and "
            "--glim-code-property"
        )

    if args.project:
        ee.Initialize(project=args.project)
    else:
        ee.Initialize()

    exports = build_exports(
        breakpoints, args.glim_asset, args.glim_code_property, selected
    )
    selected_names = {aliases[name] for name in selected}

    for name in sorted(selected_names):
        task = ee.batch.Export.image.toDrive(
            image=exports[name].toFloat(), **export_options(name)
        )
        task.start()
        status = task.status()
        print(
            f"{name}: state={status['state']} "
            f"task_id={status.get('id', 'unknown')}"
        )
    if "thermal" in selected and breakpoints is None:
        print("NOTE: earth_thermal contains ati_raw but no ti_class.")
    if "lithology" not in selected and args.only is None:
        print("NOTE: litho_class is not exported; GLiM asset is unavailable.")


if __name__ == "__main__":
    main()
