"""Build Earth Engine images for Analog Atlas' non-terrain Earth features.

AI-assisted code (Claude); reviewed and adapted to the repository data contract.
Authenticate and initialize Earth Engine in the calling notebook or script.
Export tasks are intentionally kept separate from these image builders.
"""

from __future__ import annotations

import ee

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
UNAVAILABLE_FEATURES = ("ti_class", "litho_class", "mafic_idx", "soil_moist")


def _to_grid(image: ee.Image, source_projection: ee.Projection) -> ee.Image:
    """Reduce a source image onto the contract's fixed 0.25-degree grid."""
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


def build_thermal() -> ee.Image:
    """Return tmin_k, tmax_k, diurnal_amp_k, and albedo.

    Monthly MODIS composites are formed across 2021-2025 before selecting
    each cell's coldest night and warmest day month.
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
    temperatures = _to_grid(
        tmin.addBands(tmax).addBands(diurnal_amp), lst_projection
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
    albedo_grid = _to_grid(albedo, albedo_collection.first().projection())
    return temperatures.addBands(albedo_grid).toFloat()


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

    ndvi_collection = ee.ImageCollection("MODIS/061/MOD13A2").select("NDVI")
    ndvi_projection = ndvi_collection.first().projection()

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
        _to_grid(precipitation, era_projection)
        .addBands(_to_grid(ndvi, ndvi_projection))
        .toFloat()
    )


def build_ice() -> ee.Image:
    """Return the contract's ice_idx from permafrost, glacier, and snow clues."""
    era = ee.ImageCollection("ECMWF/ERA5_LAND/MONTHLY_AGGR").filterDate(
        "2015-01-01", "2025-01-01"
    )
    soil_temperature = era.select("soil_temperature_level_1")
    era_projection = soil_temperature.first().projection()
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
        _to_grid(frozen_ground, era_projection)
        .max(_to_grid(perennial_snow, snow_projection))
        .max(_to_grid(glacier_fraction, snow_projection))
        .rename("ice_idx")
    )
    return ice_index.toFloat()


def build_logistics() -> ee.Image:
    """Return travel time and annual VIIRS radiance."""
    accessibility = ee.Image(
        "Oxford/MAP/accessibility_to_cities_2015_v1_0"
    ).select("accessibility")
    travel = _to_grid(
        accessibility.rename("travel_min"), accessibility.projection()
    )

    viirs_collection = (
        ee.ImageCollection("NOAA/VIIRS/DNB/ANNUAL_V22")
        .filterDate("2023-01-01", "2024-01-01")
        .select("average")
    )
    viirs = viirs_collection.first()
    radiance = _to_grid(
        viirs.rename("viirs_rad"), viirs_collection.first().projection()
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
        _to_grid(protected, source_projection)
        .rename("protected_frac")
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
    "build_logistics",
    "build_protected",
    "build_soil",
    "build_thermal",
    "build_water_biology",
    "export_options",
]
