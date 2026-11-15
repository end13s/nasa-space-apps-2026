"""Build Earth Engine images for Analog Atlas' non-terrain Earth features.

AI-assisted code (Claude); reviewed and adapted to the repository data contract.
Authenticate and initialize Earth Engine in the calling notebook or script.
Export tasks are intentionally kept separate from these image builders.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

import ee
import yaml

GRID = {
    "crs": "EPSG:4326",
    "crsTransform": [0.25, 0, -180, 0, -0.25, 90],
}
GRID_REGION_BOUNDS = [-180, -90, 180, 90]
EXPECTED_GRID_DIMENSIONS = "1440x720"
EXPORT_MAX_PIXELS = 1e13
DRIVE_FOLDER = "analog-atlas-data"

_START_DATE = "2021-01-01"
_END_DATE = "2026-01-01"
_YEARS = range(2021, 2026)
_MONTHS = range(1, 13)

# These contract features need a calibrated or ingested source before this
# module can produce them. Do not substitute an uncalibrated proxy.
UNAVAILABLE_FEATURES = ("mafic_idx", "soil_moist")


def _to_grid(
    image: ee.Image,
    source_projection: ee.Projection,
    band_names: Sequence[str],
) -> ee.Image:
    """Reduce source bands to cell means and within-cell spatial standard deviations."""
    mean = (
        image.setDefaultProjection(source_projection)
        .reduceResolution(reducer=ee.Reducer.mean(), maxPixels=65536)
        .reproject(**GRID)
    )
    spatial_sd = (
        image.setDefaultProjection(source_projection)
        .reduceResolution(reducer=ee.Reducer.stdDev(), maxPixels=65536)
        .reproject(**GRID)
        .rename([f"{name}__sd" for name in band_names])
    )
    return mean.addBands(spatial_sd)


def _validate_ti_breakpoints(breakpoints: Sequence[float]) -> tuple[float, ...]:
    values = tuple(float(value) for value in breakpoints)
    if len(values) != 4 or any(not math.isfinite(value) for value in values):
        raise ValueError("ti_class needs exactly four finite ATI breakpoints")
    if any(value < 0 for value in values):
        raise ValueError("ATI breakpoints cannot be negative")
    if any(left >= right for left, right in zip(values, values[1:])):
        raise ValueError("ATI breakpoints must be strictly increasing")
    return values


def _reduce_fraction(
    image: ee.Image, source_projection: ee.Projection
) -> ee.Image:
    """Reduce 10-30 m masks via 100 m and 1 km before the Earth grid."""
    at_100m = (
        image.setDefaultProjection(source_projection)
        .reduceResolution(reducer=ee.Reducer.mean(), maxPixels=65536)
        .reproject(crs=source_projection, scale=100)
    )
    at_1km = (
        at_100m.reduceResolution(
            reducer=ee.Reducer.mean(), maxPixels=65536
        ).reproject(crs=source_projection, scale=1000)
    )
    return (
        at_1km.reduceResolution(
            reducer=ee.Reducer.mean(), maxPixels=65536
        )
        .reproject(**GRID)
    )


def _mean_to_grid(image: ee.Image, source_projection: ee.Projection) -> ee.Image:
    return (
        image.setDefaultProjection(source_projection)
        .reduceResolution(reducer=ee.Reducer.mean(), maxPixels=65536)
        .reproject(**GRID)
    )


def _monthly_lst(
    collection: ee.ImageCollection, temperature_band: str, quality_band: str
) -> list[ee.Image]:
    """Return one quality-masked, scaled median image per calendar month."""

    def valid_temperature(image: ee.Image) -> ee.Image:
        good_quality = image.select(quality_band).bitwiseAnd(3).eq(0)
        return image.select(temperature_band).multiply(0.02).updateMask(
            good_quality
        )

    return [
        collection.filter(ee.Filter.calendarRange(month, month, "month"))
        .map(valid_temperature)
        .median()
        for month in _MONTHS
    ]


def build_soil() -> ee.Image:
    """Return OpenLandMap bulk density and sand fraction on the Earth grid."""
    bulk = ee.Image(
        "OpenLandMap/SOL/SOL_BULKDENS-FINEEARTH_USDA-4A1H_M/v02"
    ).select("b0")
    sand = ee.Image(
        "OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02"
    ).select("b0")

    bulk_grid = _to_grid(
        bulk.multiply(0.01).rename("bulk_density"), bulk.projection()
    )
    sand_grid = _to_grid(sand.rename("sand_frac"), sand.projection())
    return bulk_grid.addBands(sand_grid).toFloat()


def build_thermal(ti_breakpoints: Sequence[float] | None = None) -> ee.Image:
    """Return thermal features, spatial spreads, and ATI for calibration.

    Monthly MODIS composites are formed across 2021-2025 before selecting
    each cell's coldest night and warmest day month. Supply four calibrated
    ATI cutoffs to include the scored ``ti_class`` band; without calibration,
    only the raw ATI diagnostic is emitted.
    """
    lst = ee.ImageCollection("MODIS/061/MYD11A2").filterDate(
        _START_DATE, _END_DATE
    )
    lst_projection = lst.first().select("LST_Day_1km").projection()

    day_months = _monthly_lst(lst, "LST_Day_1km", "QC_Day")
    night_months = _monthly_lst(lst, "LST_Night_1km", "QC_Night")

    tmax = (
        ee.ImageCollection.fromImages(day_months)
        .max()
        .rename("tmax_k")
    )
    tmin = (
        ee.ImageCollection.fromImages(night_months)
        .min()
        .rename("tmin_k")
    )
    amplitudes = [
        day.subtract(night)
        for day, night in zip(day_months, night_months)
    ]
    diurnal_amp = (
        ee.ImageCollection.fromImages(amplitudes)
        .median()
        .rename("diurnal_amp_k")
    )
    temperature_bands = tmin.addBands(tmax).addBands(diurnal_amp)
    temperatures = _to_grid(
        temperature_bands,
        lst_projection,
        ("tmin_k", "tmax_k", "diurnal_amp_k"),
    )

    albedo_collection = (
        ee.ImageCollection("MODIS/061/MCD43A3")
        .filterDate(_START_DATE, _END_DATE)
        .select("Albedo_WSA_shortwave")
    )
    albedo = (
        albedo_collection.median()
        .multiply(0.001)
        .rename("albedo")
    )
    albedo_grid = _to_grid(
        albedo, albedo_collection.first().projection(), ("albedo",)
    )

    temperature_means = temperatures.select(
        ["tmin_k", "tmax_k", "diurnal_amp_k"]
    )
    albedo_mean = albedo_grid.select("albedo")
    ati = (
        ee.Image(1)
        .subtract(albedo_mean)
        .divide(
            temperature_means.select("diurnal_amp_k").updateMask(
                temperature_means.select("diurnal_amp_k").gt(5)
            )
        )
        .rename("ati_raw")
    )
    result = temperatures.addBands(albedo_grid).addBands(ati)

    if ti_breakpoints is not None:
        cuts = _validate_ti_breakpoints(ti_breakpoints)
        classes = (
            ati.gt(cuts[0])
            .add(ati.gt(cuts[1]))
            .add(ati.gt(cuts[2]))
            .add(ati.gt(cuts[3]))
            .rename("ti_class")
            .toFloat()
        )
        result = result.addBands(classes)
    return result.toFloat()


def build_lithology(asset_id: str, code_property: str) -> ee.Image:
    """Map an uploaded GLiM feature asset to majority ``litho_class`` cells.

    The GLiM source is not hosted in this repository or as a known public
    Earth Engine asset. Upload it first and pass its asset ID and code field.
    """
    if not asset_id.strip() or not code_property.strip():
        raise ValueError("GLiM asset ID and lithology-code property are required")
    contract_path = (
        Path(__file__).resolve().parents[2]
        / "contract"
        / "lithology_classes.yaml"
    )
    with contract_path.open(encoding="utf-8") as source:
        code_mapping = yaml.safe_load(source)["earth_glim"]

    collection = ee.FeatureCollection(asset_id)
    mapping = ee.Dictionary(code_mapping)
    recognized = collection.filter(
        ee.Filter.inList(code_property, list(code_mapping))
    )

    def assign_class(feature: ee.Feature) -> ee.Feature:
        class_id = mapping.get(ee.String(feature.get(code_property)))
        return feature.set("class_id", class_id)

    classes = recognized.map(assign_class).reduceToImage(
        properties=["class_id"], reducer=ee.Reducer.first()
    )
    return (
        classes.reproject(crs="EPSG:4326", scale=1000)
        .reduceResolution(reducer=ee.Reducer.mode(), maxPixels=65536)
        .reproject(**GRID)
        .rename("litho_class")
        .toFloat()
    )


def build_land_quality() -> ee.Image:
    """Return land/DEM coverage and the per-cell QA bitmask.

    Coastal cells with land coverage below 50% are retained and receive bit 2.
    Cells with no land or no valid GLO-30 data are masked in the parquet stage.
    """
    worldcover = ee.ImageCollection("ESA/WorldCover/v200").first()
    worldcover_projection = worldcover.select("Map").projection()
    land = worldcover.select("Map").neq(80).unmask(0).rename("land")
    land_fraction = _reduce_fraction(land, worldcover_projection).rename(
        "land_fraction"
    )

    dem_collection = ee.ImageCollection("COPERNICUS/DEM/GLO30")
    dem = dem_collection.mosaic().select("DEM")
    dem_projection = dem_collection.first().select("DEM").projection()
    valid_dem = (
        dem.mask()
        .reduce(ee.Reducer.min())
        .unmask(0)
        .rename("dem_valid")
    )
    dem_valid_fraction = _reduce_fraction(
        valid_dem, dem_projection
    ).rename("dem_valid_fraction")

    lst = ee.ImageCollection("MODIS/061/MYD11A2").filterDate(
        _START_DATE, _END_DATE
    )

    def qa_observation(image: ee.Image) -> ee.Image:
        day_quality = image.select("QC_Day").bitwiseAnd(3)
        night_quality = image.select("QC_Night").bitwiseAnd(3)
        return (
            day_quality.eq(2)
            .Or(night_quality.eq(2))
            .rename("cloudy")
            .addBands(
                night_quality.eq(3).rename("unavailable")
            )
        )

    qa_collection = lst.map(qa_observation)
    qa_projection = lst.first().select("QC_Day").projection()
    cloud_fraction = _mean_to_grid(
        qa_collection.select("cloudy").mean(), qa_projection
    )
    unavailable_fraction = _mean_to_grid(
        qa_collection.select("unavailable").mean(), qa_projection
    )
    latitude = ee.Image.pixelLonLat().select("latitude").abs()

    qa_flags = (
        cloud_fraction.gt(0.5)
        .multiply(1)
        .add(land_fraction.gt(0).And(land_fraction.lt(0.5)).multiply(2))
        .add(
            latitude.gte(66.56)
            .And(unavailable_fraction.gt(0.5))
            .multiply(4)
        )
        .add(dem_valid_fraction.lt(1).multiply(8))
        .rename("qa_flags")
        .toUint16()
    )
    return (
        land_fraction.addBands(dem_valid_fraction)
        .addBands(cloud_fraction.rename("lst_cloud_gap_fraction"))
        .addBands(unavailable_fraction.rename("lst_unavailable_fraction"))
        .addBands(qa_flags)
        .toFloat()
    )


def build_water_biology() -> ee.Image:
    """Return annual precipitation and median annual-maximum NDVI."""
    era = ee.ImageCollection("ECMWF/ERA5_LAND/MONTHLY_AGGR").filterDate(
        "2015-01-01", "2025-01-01"
    )
    era_projection = era.first().select("total_precipitation_sum").projection()
    precipitation = (
        era.select("total_precipitation_sum")
        .mean()
        .multiply(12_000)
        .rename("precip_mm")
    )

    ndvi_collection = ee.ImageCollection("MODIS/061/MOD13A2")
    ndvi_projection = ndvi_collection.first().select("NDVI").projection()

    def good_ndvi(image: ee.Image) -> ee.Image:
        quality = image.select("SummaryQA")
        return image.select("NDVI").multiply(0.0001).updateMask(quality.lte(1))

    yearly_maxima = [
        ndvi_collection.filterDate(f"{year}-01-01", f"{year + 1}-01-01")
        .map(good_ndvi)
        .max()
        for year in _YEARS
    ]
    ndvi = (
        ee.ImageCollection.fromImages(yearly_maxima)
        .median()
        .rename("ndvi_max")
    )

    return (
        _to_grid(precipitation, era_projection, ("precip_mm",))
        .addBands(_to_grid(ndvi, ndvi_projection, ("ndvi_max",)))
        .toFloat()
    )


def build_ice() -> ee.Image:
    """Return the contract's ice_idx from permafrost, glacier, and snow clues."""
    era = ee.ImageCollection("ECMWF/ERA5_LAND/MONTHLY_AGGR").filterDate(
        "2015-01-01", "2025-01-01"
    )
    soil_temperature = era.select("soil_temperature_level_1")
    annual_maxima = [
        soil_temperature.filterDate(f"{year}-01-01", f"{year + 1}-01-01").max()
        for year in range(2015, 2025)
    ]
    frozen_ground = (
        ee.ImageCollection.fromImages(annual_maxima)
        .median()
        .lt(273.15)
        .rename("frozen_ground")
    )

    snow_collection = (
        ee.ImageCollection("MODIS/061/MOD10A1")
        .filterDate(_START_DATE, _END_DATE)
        .filter(
            ee.Filter.Or(
                ee.Filter.calendarRange(1, 1, "day_of_month"),
                ee.Filter.calendarRange(8, 8, "day_of_month"),
                ee.Filter.calendarRange(15, 15, "day_of_month"),
                ee.Filter.calendarRange(22, 22, "day_of_month"),
            )
        )
        .select("NDSI_Snow_Cover")
    )
    snow_projection = snow_collection.first().projection()

    def snow_observation(image: ee.Image) -> ee.Image:
        snow_cover = image.select("NDSI_Snow_Cover")
        valid = snow_cover.lte(100)
        return snow_cover.gt(40).updateMask(valid)

    perennial_snow = (
        snow_collection.map(snow_observation)
        .mean()
        .gt(0.9)
        .rename("perennial_snow")
    )

    glacier_fraction = (
        ee.Image.constant(0)
        .byte()
        .setDefaultProjection(snow_projection)
        .paint(ee.FeatureCollection("GLIMS/current"), 1)
    )

    ice_index = (
        frozen_ground.setDefaultProjection(snow_projection)
        .max(perennial_snow)
        .max(glacier_fraction)
        .rename("ice_idx")
    )
    return _to_grid(ice_index, snow_projection, ("ice_idx",)).toFloat()


def build_logistics() -> ee.Image:
    """Return travel time and annual VIIRS radiance."""
    accessibility = ee.Image(
        "Oxford/MAP/accessibility_to_cities_2015_v1_0"
    ).select("accessibility")
    travel = _to_grid(
        accessibility.rename("travel_min"),
        accessibility.projection(),
        ("travel_min",),
    )

    viirs_collection = (
        ee.ImageCollection("NOAA/VIIRS/DNB/ANNUAL_V22")
        .filterDate("2023-01-01", "2024-01-01")
        .select("average")
    )
    viirs = viirs_collection.first()
    radiance = _to_grid(
        viirs.rename("viirs_rad"),
        viirs_collection.first().projection(),
        ("viirs_rad",),
    )
    return travel.addBands(radiance).toFloat()


def build_protected() -> ee.Image:
    """Return the approximate protected-area fraction at 0.25 degrees."""
    accessibility = ee.Image(
        "Oxford/MAP/accessibility_to_cities_2015_v1_0"
    ).select("accessibility")
    source_projection = accessibility.projection()
    protected = (
        ee.Image.constant(0)
        .byte()
        .setDefaultProjection(source_projection)
        .paint(ee.FeatureCollection("WCMC/WDPA/current/polygons"), 1)
    )
    return (
        _to_grid(protected, source_projection, ("protected_frac",))
        .toFloat()
    )


def export_options(description: str) -> dict[str, object]:
    """Return common Drive export options for a built image."""
    return {
        "description": description,
        "folder": DRIVE_FOLDER,
        "region": ee.Geometry.Rectangle(
            GRID_REGION_BOUNDS, proj=GRID["crs"], geodesic=False
        ),
        "maxPixels": EXPORT_MAX_PIXELS,
        **GRID,
    }


__all__ = [
    "DRIVE_FOLDER",
    "EXPORT_MAX_PIXELS",
    "EXPECTED_GRID_DIMENSIONS",
    "GRID",
    "GRID_REGION_BOUNDS",
    "UNAVAILABLE_FEATURES",
    "build_ice",
    "build_land_quality",
    "build_lithology",
    "build_logistics",
    "build_protected",
    "build_soil",
    "build_thermal",
    "build_water_biology",
    "export_options",
]
