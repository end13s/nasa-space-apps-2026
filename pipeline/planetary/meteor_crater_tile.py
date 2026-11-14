"""Clara <-> Michal terrain check on the agreed Earth test tile.

Owner: Michal.
AI-assisted: first version written with Claude, then run and checked by Michal.

The test tile is the 0.25 deg Earth grid cell that contains Meteor Crater
(35.03 N, 111.02 W):  row 219, col 275, cell_id 315635,
lat 35.00 .. 35.25 N, lon 111.25 .. 111.00 W.

Run from the repo root:

    python3 pipeline/planetary/meteor_crater_tile.py

1. It prints my terrain numbers for that cell (Copernicus GLO-30, reprojected
   to a local equidistant grid at 30 m, features from the SHARED definition in
   engine/terrain_features.py). Send them to Clara.
2. When Clara sends her Earth Engine numbers for the same cell, paste them into
   CLARA below and run again: it prints the compare_tile report
   (pass = less than 15 % relative difference).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))
from terrain_features import compare_tile, terrain_features  # noqa: E402

# Copernicus GLO-30 tile N35 W112 (covers 35-36 N, 112-111 W), public COG on AWS.
DEM_URL = (
    "/vsicurl/https://copernicus-dem-30m.s3.amazonaws.com/"
    "Copernicus_DSM_COG_10_N35_00_W112_00_DEM/Copernicus_DSM_COG_10_N35_00_W112_00_DEM.tif"
)
RES_M = 30.0

# The grid cell (Section 5.1: row 0 = 90 N edge, col 0 = -180 edge, 0.25 deg).
ROW, COL = 219, 275
SOUTH, NORTH = 90 - (ROW + 1) * 0.25, 90 - ROW * 0.25      # 35.00, 35.25
WEST, EAST = -180 + COL * 0.25, -180 + (COL + 1) * 0.25    # -111.25, -111.00

# Clara's numbers for the same cell go here, e.g. {"relief_km": 0.41, ...}
CLARA: dict[str, float] = {}


def read_cell_dem() -> np.ndarray:
    try:
        import rasterio
        from rasterio.crs import CRS
        from rasterio.enums import Resampling
        from rasterio.transform import from_origin
        from rasterio.vrt import WarpedVRT
        from rasterio.warp import transform as warp_transform
    except ImportError:
        sys.exit("rasterio is missing - run:  python3 -m pip install rasterio pyproj")

    lat0, lon0 = (SOUTH + NORTH) / 2, (WEST + EAST) / 2
    local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m +no_defs"
    )
    # Cell corners -> local metres; the window is their bounding box.
    xs, ys = warp_transform(
        "EPSG:4326", local, [WEST, EAST, WEST, EAST], [SOUTH, SOUTH, NORTH, NORTH]
    )
    west, east, south, north = min(xs), max(xs), min(ys), max(ys)
    width = int(round((east - west) / RES_M))
    height = int(round((north - south) / RES_M))

    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", VSI_CACHE=True):
        with rasterio.open(DEM_URL) as src:
            with WarpedVRT(
                src,
                crs=local,
                transform=from_origin(west, north, RES_M, RES_M),
                width=width,
                height=height,
                resampling=Resampling.bilinear,
                src_nodata=src.nodata,
                nodata=np.nan,
                dtype="float32",
            ) as vrt:
                dem = vrt.read(1).astype(np.float64)
            scale = src.scales[0] if src.scales else 1.0
            offset = src.offsets[0] if src.offsets else 0.0
    print(f"window {width} x {height} px at {RES_M:.0f} m  "
          f"(~{width * RES_M / 1000:.1f} x {height * RES_M / 1000:.1f} km)")
    return dem * scale + offset


def main() -> None:
    cell_id = ROW * 1440 + COL
    print(f"Meteor Crater test cell {cell_id}: lat {SOUTH}..{NORTH}, lon {WEST}..{EAST}")
    dem = read_cell_dem()
    mine = terrain_features(dem, RES_M)
    mine = {k: round(float(v), 4) for k, v in mine.items()}

    print("\nMy numbers (send these to Clara):")
    print(json.dumps(mine, indent=2))
    if not np.isfinite(mine.get("rough_10km", np.nan)):
        print("\nNOTE: rough_10km is NaN because this cell is smaller than the 30 km the "
              "shared function needs for a 10 km baseline. Eduard has to decide how "
              "to handle it (e.g. pad the window) - post this in #data.")

    if CLARA:
        print("\ncompare_tile (mine vs Clara, 15 % tolerance):")
        for k, (a, b, rel, verdict) in compare_tile(mine, CLARA).items():
            print(f"  {k:16s} {a:10.4f} {b:10.4f}   diff {rel:6.1%}   {verdict}")
    else:
        print("\nWhen Clara sends her numbers, paste them into CLARA at the top of this "
              "file and run it again.")


if __name__ == "__main__":
    main()
