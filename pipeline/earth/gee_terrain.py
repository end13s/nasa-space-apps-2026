"""Export window-based terrain features from Copernicus GLO-30 with Earth Engine."""
from __future__ import annotations

import argparse

GRID_TRANSFORM = [0.25, 0, -180, 0, -0.25, 90]
OUTPUT_FEATURES = (
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
)


def build_terrain_image(ee):
    """Build the 500 m terrain layers and reduce their window stats to 0.25°."""
    metric_projection = ee.Projection("EPSG:6933").atScale(500)
    source = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM").mosaic()
    valid = source.mask().rename("valid")
    window_kernel = ee.Kernel.fixed(
        2, 2, [[1, 1], [1, 1]], x=0, y=0, normalize=False
    )
    coordinates500 = ee.Image.pixelCoordinates(metric_projection)
    window_anchor500 = (
        coordinates500.select("x").mod(2).eq(0)
        .And(coordinates500.select("y").mod(2).eq(0))
    )
    dem500 = (
        source.reduceResolution(reducer=ee.Reducer.mean(), maxPixels=4096)
        .reproject(metric_projection)
        .rename("elevation")
    )
    valid500 = (
        valid.reduceResolution(reducer=ee.Reducer.mean(), maxPixels=4096)
        .reproject(metric_projection)
    )
    elevation_stats = dem500.reduceNeighborhood(
        reducer=ee.Reducer.percentile([5, 95]).combine(
            ee.Reducer.minMax().combine(ee.Reducer.mean(), sharedInputs=True),
            sharedInputs=True,
        ),
        kernel=window_kernel,
    )
    relief = elevation_stats.select("elevation_p95").subtract(
        elevation_stats.select("elevation_p5")
    ).divide(1000).rename("relief_km")
    lo = elevation_stats.select("elevation_min")
    hi = elevation_stats.select("elevation_max")
    mean = elevation_stats.select("elevation_mean")
    hypsometry = (
        mean.subtract(lo).divide(hi.subtract(lo)).updateMask(hi.gt(lo)).rename("hypso_int")
    )
    slope = ee.Terrain.slope(dem500).rename("slope")
    slope_stats = slope.reduceNeighborhood(
        reducer=ee.Reducer.median().combine(
            ee.Reducer.percentile([90]).combine(ee.Reducer.mean(), sharedInputs=True),
            sharedInputs=True,
        ),
        kernel=window_kernel,
    )
    slope_median = slope_stats.select("slope_median").rename("slope_med_deg")
    slope_p90 = slope_stats.select("slope_p90").rename("slope_p90_deg")
    flat = slope.lt(5).reduceNeighborhood(
        ee.Reducer.mean(), window_kernel
    ).rename("flat_frac")
    steep = slope.gt(25).reduceNeighborhood(
        ee.Reducer.mean(), window_kernel
    ).rename("steep_frac")

    roughness = []
    for label, length_m in (("rough_2km", 2000), ("rough_10km", 10000)):
        gaussian = ee.Kernel.gaussian(
            radius=3 * length_m, sigma=length_m, units="meters", normalize=True
        )
        residual = dem500.subtract(dem500.convolve(gaussian))
        rms = residual.pow(2).reduceNeighborhood(
            ee.Reducer.mean(), window_kernel
        ).sqrt()
        roughness.append(rms.divide(length_m).multiply(1000).rename(label))

    source100 = (
        source.reduceResolution(reducer=ee.Reducer.mean(), maxPixels=4096)
        .reproject(ee.Projection("EPSG:6933").atScale(100))
        .rename("elevation")
    )
    sensitivity_kernel = ee.Kernel.fixed(
        10,
        10,
        [[1] * 10 for _ in range(10)],
        x=0,
        y=0,
        normalize=False,
    )
    projection100 = ee.Projection("EPSG:6933").atScale(100)
    coordinates100 = ee.Image.pixelCoordinates(projection100)
    window_anchor100 = (
        coordinates100.select("x").mod(10).eq(0)
        .And(coordinates100.select("y").mod(10).eq(0))
    )
    sensitivity = []
    for label, length_m in (
        ("rough_2km_gM", 330),
        ("rough_10km_gM", 1650),
        ("rough_2km_gR", 760),
        ("rough_10km_gR", 3800),
    ):
        gaussian = ee.Kernel.gaussian(
            radius=3 * length_m, sigma=length_m, units="meters", normalize=True
        )
        residual = source100.subtract(source100.convolve(gaussian))
        rms = residual.pow(2).reduceNeighborhood(
            ee.Reducer.mean(), sensitivity_kernel
        ).sqrt()
        window_stat = rms.divide(length_m).multiply(1000).rename(label)
        sensitivity.append(
            window_stat.updateMask(window_anchor100)
            .reduceResolution(reducer=ee.Reducer.mean(), maxPixels=100)
            .reproject(metric_projection)
        )

    windows = ee.Image.cat(
        [
            relief,
            slope_median,
            slope_p90,
            *roughness,
            *sensitivity,
            hypsometry,
            flat,
            steep,
        ]
    ).updateMask(valid500).updateMask(window_anchor500)
    aggregate = ee.Reducer.percentile([10, 50, 90]).combine(
        ee.Reducer.stdDev(), sharedInputs=True
    )
    reduced = windows.reduceResolution(reducer=aggregate, maxPixels=65536)
    raw_names = []
    output_names = []
    for feature in OUTPUT_FEATURES:
        for suffix, output_suffix in (
            ("p10", "__p10"),
            ("p50", ""),
            ("p90", "__p90"),
            ("stdDev", "__sd"),
        ):
            raw_names.append(f"{feature}_{suffix}")
            output_names.append(f"{feature}{output_suffix}")
    stats = reduced.select(raw_names, output_names)
    valid_fraction = valid500.reduceResolution(
        reducer=ee.Reducer.mean(), maxPixels=65536
    ).rename("land_fraction")
    return stats.updateMask(valid_fraction.gt(0.5)).set(
        "gravity_scaled_bands_are_sensitivity_only", True
    )


def start_export(ee, project: str | None, folder: str, description: str):
    if project:
        ee.Initialize(project=project)
    else:
        ee.Initialize()
    image = build_terrain_image(ee)
    task = ee.batch.Export.image.toDrive(
        image=image,
        description=description,
        folder=folder,
        fileNamePrefix=description,
        region=ee.Geometry.Rectangle([-180, -90, 180, 90], geodesic=False),
        crs="EPSG:4326",
        crsTransform=GRID_TRANSFORM,
        maxPixels=1e13,
        fileFormat="GeoTIFF",
    )
    task.start()
    return task


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", help="Earth Engine Cloud project id")
    parser.add_argument("--folder", default="analog-atlas-data")
    parser.add_argument("--description", default="analog_atlas_terrain")
    args = parser.parse_args()
    try:
        import ee
    except ImportError as exc:
        raise SystemExit("Install earthengine-api to run this export") from exc
    task = start_export(ee, args.project, args.folder, args.description)
    print(f"started Earth Engine export task {task.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
