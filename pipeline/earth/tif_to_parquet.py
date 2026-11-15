"""Merge aligned Earth and terrain GeoTIFF exports into earth_grid.parquet."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from affine import Affine
from rasterio.features import rasterize
from rasterio.warp import transform_geom

NROWS, NCOLS = 720, 1440
EXPECTED_TRANSFORM = Affine(0.25, 0, -180, 0, -0.25, 90)
GRID_SHAPE = (NROWS, NCOLS)

# Fallback band names are used only when GeoTIFF band descriptions are absent.
BAND_NAMES: dict[str, tuple[tuple[str, ...], ...]] = {
    "earth_soil.tif": (
        ("bulk_density", "sand_frac"),
        ("bulk_density", "sand_frac", "bulk_density__sd", "sand_frac__sd"),
    ),
    "earth_thermal.tif": (
        (
            "tmin_k",
            "tmax_k",
            "diurnal_amp_k",
            "tmin_k__sd",
            "tmax_k__sd",
            "diurnal_amp_k__sd",
            "albedo",
            "albedo__sd",
            "ati_raw",
        ),
        (
            "tmin_k",
            "tmax_k",
            "diurnal_amp_k",
            "tmin_k__sd",
            "tmax_k__sd",
            "diurnal_amp_k__sd",
            "albedo",
            "albedo__sd",
            "ati_raw",
            "ti_class",
        ),
    ),
    "earth_water_bio.tif": (
        ("precip_mm", "precip_mm__sd", "ndvi_max", "ndvi_max__sd"),
    ),
    "earth_ice.tif": (("ice_idx", "ice_idx__sd"),),
    "earth_logistics.tif": (
        (
            "travel_min",
            "travel_min__sd",
            "viirs_rad",
            "viirs_rad__sd",
            "protected_frac",
            "protected_frac__sd",
        ),
    ),
    "earth_land_quality.tif": (
        (
            "land_fraction",
            "dem_valid_fraction",
            "lst_cloud_gap_fraction",
            "lst_unavailable_fraction",
            "qa_flags",
        ),
    ),
    "earth_terrain.tif": (
        (
            "relief_km",
            "slope_med_deg",
            "slope_p90_deg",
            "rough_2km",
            "rough_10km",
            "rough_2km_gM",
            "rough_10km_gM",
            "rough_2km_gR",
            "rough_10km_gR",
            "hypso_int",
            "flat_frac",
            "steep_frac",
        ),
    ),
    "earth_lithology.tif": (("litho_class",),),
}
REQUIRED_RASTERS = ("earth_land_quality.tif",)
OPTIONAL_RASTERS = (
    "earth_terrain.tif",
    "earth_lithology.tif",
)
MVP_FEATURES = {
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


def _read_raster(path: Path) -> dict[str, np.ndarray]:
    with rasterio.open(path) as source:
        if source.width != NCOLS or source.height != NROWS:
            raise ValueError(
                f"{path}: expected {NCOLS}x{NROWS}, got "
                f"{source.width}x{source.height}"
            )
        if source.crs is None or source.crs.to_epsg() != 4326:
            raise ValueError(f"{path}: expected EPSG:4326, got {source.crs}")
        if source.transform != EXPECTED_TRANSFORM:
            raise ValueError(
                f"{path}: grid transform mismatch: {source.transform!r}"
            )

        configured_names = BAND_NAMES.get(path.name, ())
        names = tuple(source.descriptions)
        generic_names = any(
            not name
            or re.fullmatch(r"(?:band[_\s]*)?b?\d+", name.strip(), re.I)
            for name in names
        )
        if len(names) != source.count or generic_names:
            names = next(
                (group for group in configured_names if len(group) == source.count),
                (),
            )
        if len(names) != source.count:
            raise ValueError(
                f"{path}: cannot identify {source.count} bands; add descriptions "
                "or update BAND_NAMES"
            )
        data = source.read(out_dtype="float32")
        if source.nodata is not None:
            data[data == source.nodata] = np.nan
    return {name: data[index] for index, name in enumerate(names)}


def _load_country_codes(path: Path | None) -> pd.Series | None:
    if path is None:
        return None
    country = pd.read_csv(path, dtype={"country_iso3": "string"})
    required = {"cell_id", "country_iso3"}
    if not required.issubset(country.columns):
        raise ValueError(
            f"{path}: expected columns cell_id,country_iso3"
        )
    if country["cell_id"].duplicated().any():
        raise ValueError(f"{path}: duplicate cell_id values")
    invalid = country["country_iso3"].notna() & ~country[
        "country_iso3"
    ].str.fullmatch(r"[A-Z]{3}")
    if invalid.any():
        raise ValueError(f"{path}: country_iso3 values must be uppercase ISO3")
    return country.set_index("cell_id")["country_iso3"]


def _rasterize_country_codes(
    path: Path, code_field: str
) -> np.ndarray:
    """Assign ISO3 codes by grid-cell center from a Natural Earth vector file."""
    try:
        import fiona
    except ImportError as error:
        raise RuntimeError(
            "Reading a country vector requires Fiona; install the Earth "
            "pipeline requirements"
        ) from error

    with fiona.open(path) as source:
        if source.crs is None and not source.crs_wkt:
            raise ValueError(f"{path}: country vector has no CRS")
        if source.schema is None or code_field not in source.schema["properties"]:
            raise ValueError(f"{path}: missing country code field {code_field!r}")
        shapes: list[tuple[dict, int]] = []
        code_by_id: dict[int, str] = {}
        for feature in source:
            code = str(feature["properties"].get(code_field, "")).upper()
            if code in {"", "-99", "NAN", "NONE"}:
                continue
            if feature["geometry"] is None:
                continue
            if not re.fullmatch(r"[A-Z]{3}", code):
                raise ValueError(
                    f"{path}: {code_field} contains non-ISO3 code {code!r}"
                )
            if code not in code_by_id:
                code_by_id[code] = len(code_by_id) + 1
            country_id = code_by_id[code]
            geometry = transform_geom(
                source.crs_wkt or source.crs, "EPSG:4326", feature["geometry"]
            )
            shapes.append((geometry, country_id))

    if not shapes:
        raise ValueError(f"{path}: no country polygons with valid ISO3 codes")
    ids = rasterize(
        shapes,
        out_shape=GRID_SHAPE,
        transform=EXPECTED_TRANSFORM,
        fill=0,
        all_touched=False,
        dtype="uint16",
    )
    countries = np.full(GRID_SHAPE, None, dtype=object)
    for country_id, code in enumerate(code_by_id, start=1):
        countries[ids == country_id] = code
    return countries


def build_parquet(
    tif_dir: Path,
    output: Path,
    country_csv: Path | None = None,
    country_vector: Path | None = None,
    country_field: str = "ISO_A3",
    require_complete: bool = False,
) -> pd.DataFrame:
    if country_csv is not None and country_vector is not None:
        raise ValueError("provide either --country-csv or --country-vector, not both")
    missing_required = [
        filename for filename in REQUIRED_RASTERS if not (tif_dir / filename).is_file()
    ]
    if missing_required:
        raise FileNotFoundError(
            "Required land/QA raster missing: " + ", ".join(missing_required)
        )

    arrays: dict[str, np.ndarray] = {}
    known_files = set(BAND_NAMES)
    for filename in sorted(known_files):
        path = tif_dir / filename
        if not path.is_file():
            continue
        for name, values in _read_raster(path).items():
            if name in arrays:
                raise ValueError(f"duplicate raster band {name!r} in {path}")
            arrays[name] = values

    for filename in OPTIONAL_RASTERS:
        if not (tif_dir / filename).is_file():
            print(f"WARNING: {filename} missing; its features will be absent.")

    required_quality_bands = {
        "land_fraction",
        "dem_valid_fraction",
        "qa_flags",
    }
    if not required_quality_bands.issubset(arrays):
        raise ValueError(
            "earth_land_quality.tif must contain "
            + ", ".join(sorted(required_quality_bands))
        )

    rows, cols = np.indices(GRID_SHAPE)
    cell_id = rows * NCOLS + cols
    lat = 90 - (rows + 0.5) * 0.25
    lon = -180 + (cols + 0.5) * 0.25

    land_fraction = arrays["land_fraction"]
    dem_fraction = arrays["dem_valid_fraction"]
    # Keep coastal land cells; bit 2 flags those below 50% land coverage.
    keep = (
        np.isfinite(land_fraction)
        & (land_fraction > 0)
        & np.isfinite(dem_fraction)
        & (dem_fraction > 0)
    )
    if not keep.any():
        raise ValueError("land/DEM masks select zero cells")

    table: dict[str, np.ndarray] = {
        "cell_id": cell_id[keep].astype(np.int32),
        "lat": lat[keep].astype(np.float32),
        "lon": lon[keep].astype(np.float32),
    }
    for name, values in arrays.items():
        if name in required_quality_bands or name in {
            "lst_cloud_gap_fraction",
            "lst_unavailable_fraction",
        }:
            continue
        table[name] = values[keep]

    flags = np.nan_to_num(
        arrays["qa_flags"], nan=0.0, posinf=0.0, neginf=0.0
    ).astype(np.uint16)
    flags |= ((land_fraction > 0) & (land_fraction < 0.5)).astype(np.uint16) * 2
    flags |= (dem_fraction < 1).astype(np.uint16) * 8
    table["qa_flags"] = flags[keep]

    if country_vector is not None:
        country_grid = _rasterize_country_codes(country_vector, country_field)
        table["country_iso3"] = country_grid[keep]
    else:
        country_codes = _load_country_codes(country_csv)
        if country_codes is not None:
            selected_ids = table["cell_id"]
            table["country_iso3"] = (
                country_codes.reindex(selected_ids).to_numpy(dtype=object)
            )
        else:
            print(
                "WARNING: country_iso3 not populated; provide a Natural Earth "
                "vector with ISO_A3 codes or a cell_id,country_iso3 CSV."
            )

    required_features = MVP_FEATURES | {"country_iso3"}
    missing_features = sorted(required_features - table.keys())
    missing_spreads = sorted(REQUIRED_SPREADS - table.keys())
    missing_features.extend(missing_spreads)
    if missing_features:
        message = "Missing Earth grid outputs: " + ", ".join(missing_features)
        if require_complete:
            raise ValueError(message)
        print("WARNING: " + message)

    frame = pd.DataFrame(table)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output, index=False)
    print(f"Wrote {len(frame):,} land cells to {output}")
    return frame


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tif-dir", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, default=Path("earth_grid.parquet"))
    parser.add_argument(
        "--country-csv",
        type=Path,
        help="cell_id,country_iso3 lookup generated from a country-boundary source",
    )
    parser.add_argument(
        "--country-vector",
        type=Path,
        help="Natural Earth country vector with ISO3 codes (default field ISO_A3)",
    )
    parser.add_argument("--country-field", default="ISO_A3")
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="fail unless core MVP thermal, material, and terrain features exist",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    build_parquet(
        args.tif_dir,
        args.out,
        country_csv=args.country_csv,
        country_vector=args.country_vector,
        country_field=args.country_field,
        require_complete=args.require_complete,
    )


if __name__ == "__main__":
    main()
