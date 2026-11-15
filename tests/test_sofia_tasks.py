from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from engine.cross_check import compare_features, run_config
from engine.fact_check import check_document
from engine.targets_terrain import update_targets
from engine.terrain_features import compute, compute_sensitivity, terrain_features
from engine.validate import grade_d_sensitivity, rank_experiment
from engine.score import load_contract
from pipeline.earth.gee_terrain import GRID_TRANSFORM, OUTPUT_FEATURES


def test_terrain_summary_separates_spread_from_vertical_error():
    yy, xx = np.mgrid[:40, :40]
    dem = 120 * np.sin(xx / 5) + 60 * np.cos(yy / 4)
    result = compute(dem, 500, dem_vertical_error_m=5)

    relief = result["relief_km"]
    assert set(relief) == {
        "p10", "p50", "p90", "err", "err_note", "n", "unit", "provisional"
    }
    assert relief["n"] == 400
    assert relief["p10"] <= relief["p50"] <= relief["p90"]
    assert relief["err"] == pytest.approx(5 * np.sqrt(2) / 1000)
    assert result["rough_2km"]["err"] is None
    assert "rough_2km_gM" not in result
    assert not relief["provisional"]
    missing_error = compute(dem, 500)["relief_km"]
    assert missing_error["err"] is None
    assert "not supplied" in missing_error["err_note"]


def test_terrain_summary_marks_small_samples_provisional():
    result = compute(np.arange(16, dtype=float).reshape(4, 4), 500)
    assert result["relief_km"]["n"] == 4
    assert result["relief_km"]["provisional"]


def test_terrain_rejects_bad_pixel_size_and_sensitivity_resolution():
    dem = np.ones((20, 20))
    with pytest.raises(ValueError, match="px_m"):
        compute(dem, 0)
    with pytest.raises(ValueError, match="too coarse"):
        compute_sensitivity(dem, 200, "moon")


def test_gravity_scaled_roughness_is_separate_and_labeled_sensitivity():
    yy, xx = np.mgrid[:40, :40]
    dem = 100 * np.sin(xx / 4)
    result = compute_sensitivity(dem, 30, "moon")
    assert result["body"] == "moon"
    assert result["horizontal_axis"] == "gravity_scaled_sensitivity"
    assert set(result["features"]) == {"rough_2km_gM", "rough_10km_gM"}
    assert all(value["err_note"] == "sensitivity only" for value in result["features"].values())


def test_legacy_terrain_interface_still_returns_scalar_values():
    yy, xx = np.mgrid[:40, :40]
    result = terrain_features(100 * np.sin(xx / 4), 500)
    assert isinstance(result["relief_km"], float)
    assert {"rough_2km", "rough_10km", "flat_frac", "steep_frac"} <= result.keys()


def test_cross_check_uses_feature_specific_tolerances():
    report = compare_features(
        {"relief_km": 1.0, "rough_2km": 10.0},
        {"features": {"relief_km": 1.08, "rough_2km": 13.0}},
    )
    assert report["relief_km"]["status"] == "pass"
    assert report["rough_2km"]["status"] == "mismatch"


def test_cross_check_reads_a_metric_raster_and_gee_json(tmp_path):
    import rasterio
    from rasterio.transform import from_origin

    yy, xx = np.mgrid[:40, :40]
    dem = (120 * np.sin(xx / 5) + 60 * np.cos(yy / 4)).astype("float32")
    dem_path = tmp_path / "tile.tif"
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        height=dem.shape[0],
        width=dem.shape[1],
        count=1,
        dtype=dem.dtype,
        crs="EPSG:32612",
        transform=from_origin(500000, 5000000, 500, 500),
    ) as output:
        output.write(dem, 1)
    expected = compute(dem, 500)
    gee_path = tmp_path / "gee.json"
    gee_path.write_text(
        json.dumps({"features": {key: value["p50"] for key, value in expected.items()}}),
        encoding="utf-8",
    )
    report = run_config({"dem_path": str(dem_path), "gee_json": str(gee_path)})
    assert all(item["status"] == "pass" for item in report.values())


def test_target_clip_outputs_p50_and_full_window_records(tmp_path):
    import rasterio
    from rasterio.transform import from_origin

    yy, xx = np.mgrid[:40, :40]
    dem = (120 * np.sin(xx / 5) + 60 * np.cos(yy / 4)).astype("float32")
    clip = tmp_path / "mars_test.tif"
    with rasterio.open(
        clip,
        "w",
        driver="GTiff",
        height=dem.shape[0],
        width=dem.shape[1],
        count=1,
        dtype=dem.dtype,
        crs="EPSG:32612",
        transform=from_origin(500000, 5000000, 500, 500),
        nodata=-9999,
    ) as output:
        output.write(dem, 1)

    updated = update_targets(
        [{"id": "mars_test", "features": {"albedo": 0.2}, "sd": {"albedo": 0.1}}],
        tmp_path,
    )[0]
    assert updated["features"]["relief_km"] == updated["terrain_windows"]["relief_km"]["p50"]
    assert updated["features"]["albedo"] == 0.2
    assert updated["sd"] == {"albedo": 0.1}


def test_grade_d_widening_can_change_top_twenty():
    contract = load_contract()
    target = {
        "id": "grade_d_test",
        "body": "mars",
        "features": {"relief_km": 0.0, "slope_med_deg": 0.0},
        "grades": {"relief_km": "D"},
    }
    grid = {
        "relief_km": np.array([0.0, 1.0]),
        "slope_med_deg": np.array([4.0, 0.0]),
    }
    result = grade_d_sensitivity(grid, target, contract, top_k=1)
    assert result["grade_d_features"] == ["relief_km"]
    assert result["top_before"] == [0]
    assert result["top_after"] == [1]
    assert result["overlap_fraction"] == 0


def test_experiment_ranking_applies_each_experiment_filter():
    contract = load_contract()
    target = {
        "body": "mars",
        "features": {"relief_km": 0.0},
    }
    grid = {
        "relief_km": np.array([0.1, 0.2, 0.3]),
        "precip_mm": np.array([0.0, 1000.0, 0.0]),
    }
    result = rank_experiment(
        grid,
        target,
        contract,
        experiment_id="dry_navigation",
        filters={"precip_mm": {"max": 100}},
        k=2,
        cell_ids=[10, 11, 12],
    )
    assert [row["cell_id"] for row in result] == [10, 12]


def test_fact_check_reports_unknown_feature_and_placeholder(tmp_path):
    page = tmp_path / "project_page.md"
    page.write_text("Uses `relief_km` and `imaginary_feature`. TODO", encoding="utf-8")
    errors = check_document(page)
    assert any("imaginary_feature" in error for error in errors)
    assert any("unresolved" in error for error in errors)


def test_fact_check_accepts_document_with_valid_feature_ids():
    assert check_document(ROOT / "README.md") == []


def test_gee_export_schema_matches_terrain_contract():
    assert GRID_TRANSFORM == [0.25, 0, -180, 0, -0.25, 90]
    assert {
        "relief_km",
        "slope_med_deg",
        "slope_p90_deg",
        "rough_2km",
        "rough_10km",
        "rough_2km_gM",
        "rough_10km_gM",
        "rough_2km_gR",
        "rough_10km_gR",
        "flat_frac",
        "steep_frac",
    } <= set(OUTPUT_FEATURES)


def test_missing_target_clip_is_an_explicit_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="mars_missing"):
        update_targets([{"id": "mars_missing"}], tmp_path)
