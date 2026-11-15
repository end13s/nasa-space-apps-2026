"""Pack a feature parquet into the browser bundle (task E7).

parquet (float32, one row per land cell)  ->  web/public/data/

    earth_features.bin   Uint8  [n_cells x n_features], row-major.
                         0..254 = linear between lo and hi, 255 = missing.
    earth_sd.bin         Uint8  same layout, the __sd columns (optional).
    earth_index.bin      Uint32 cell_id per row.
    earth_logistics.bin  Uint8  [n_cells x n_logistics], same quantization,
                         log-scaled where the meta says so.
    earth_country.bin    Uint8  index into meta.country_codes.
    earth_meta.json      everything the worker needs to decode and score.

Nothing here is Earth-specific: --body moon|mars packs Michal's global grids
for the click-anywhere feature with the same code.

Usage
-----
    python engine/pack_web.py --grid data_work/earth_grid.parquet \
        --targets data_work/targets.json \
        --analogs science/known_analogs.csv \
        --out web/public/data

AI-assisted: scaffolded with Claude, reviewed by Eduard.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from score import DEFAULT_EPS, GRADE_SIGMA, haversine_km, load_contract, load_transfer_rules

MISSING = 255
GRID_NCOLS = {"earth": 1440, "moon": 720, "mars": 720}
GRID_RES = {"earth": 0.25, "moon": 0.5, "mars": 0.5}

# Logistics columns get their own quantization bounds; "log" means the value
# is log10(x+1)-scaled before quantizing, because travel time and distance are
# interesting at 30 minutes and at 30 hours alike.
LOGISTICS_PACK = {
    "travel_min": {"lo": 0.0, "hi": 5000.0, "scale": "log", "unit": "minutes"},
    "protected_frac": {"lo": 0.0, "hi": 1.0, "scale": "linear", "unit": "0-1"},
    "viirs_rad": {"lo": 0.0, "hi": 100.0, "scale": "log", "unit": "nW/cm2/sr"},
    "known_analog_km": {"lo": 0.0, "hi": 4000.0, "scale": "log", "unit": "km"},
}


def quantize(values: np.ndarray, lo: float, hi: float, scale: str = "linear") -> np.ndarray:
    """float -> uint8, 255 reserved for missing."""
    v = np.asarray(values, dtype=np.float64)
    if scale == "log":
        v = np.log10(np.maximum(v, 0.0) + 1.0)
        lo, hi = np.log10(lo + 1.0), np.log10(hi + 1.0)
    out = np.full(v.shape, MISSING, dtype=np.uint8)
    ok = np.isfinite(v)
    if hi <= lo:
        raise ValueError(f"bad quantization bounds lo={lo} hi={hi}")
    q = np.clip((v[ok] - lo) / (hi - lo), 0.0, 1.0) * 254.0
    out[ok] = np.round(q).astype(np.uint8)
    return out


def dequantize(code: np.ndarray, lo: float, hi: float, scale: str = "linear") -> np.ndarray:
    """Inverse of quantize - used by the parity test and by validate.py."""
    c = np.asarray(code)
    out = np.full(c.shape, np.nan, dtype=np.float64)
    ok = c != MISSING
    if scale == "log":
        llo, lhi = np.log10(lo + 1.0), np.log10(hi + 1.0)
        out[ok] = 10.0 ** (llo + (c[ok] / 254.0) * (lhi - llo)) - 1.0
    else:
        out[ok] = lo + (c[ok] / 254.0) * (hi - lo)
    return out


def known_analog_distance_km(
    lat: np.ndarray, lon: np.ndarray, analogs: pd.DataFrame | None
) -> np.ndarray:
    """Great-circle distance from every cell to the nearest known analog site."""
    if analogs is None or len(analogs) == 0:
        return np.full(len(lat), np.nan)
    best = np.full(len(lat), np.inf)
    for _, row in analogs.iterrows():
        d = haversine_km(lat, lon, float(row["lat"]), float(row["lon"]))
        np.minimum(best, d, out=best)
    return best


def pack(
    grid_path: Path,
    out_dir: Path,
    body: str = "earth",
    analogs_path: Path | None = None,
    targets_path: Path | None = None,
    contract_dir: Path | None = None,
    extra_json: dict[str, Path] | None = None,
) -> dict:
    contract = load_contract(contract_dir) if contract_dir else load_contract()
    df = pd.read_parquet(grid_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    if "cell_id" not in df.columns:
        raise SystemExit("grid is missing cell_id - check the Section 5.1 contract")

    n = len(df)
    lat = df["lat"].to_numpy(dtype=np.float64)
    lon = df["lon"].to_numpy(dtype=np.float64)

    # ---- features ---------------------------------------------------------
    specs = [f for f in contract.features if f.id in df.columns]
    missing_mvp = [f.id for f in contract.features if f.is_mvp and f.id not in df.columns]
    if missing_mvp:
        print(f"  WARNING: MVP features absent from the grid: {', '.join(missing_mvp)}")

    feat = np.empty((n, len(specs)), dtype=np.uint8)
    coverage = {}
    for j, spec in enumerate(specs):
        col = df[spec.id].to_numpy(dtype=np.float64)
        feat[:, j] = quantize(col, spec.lo, spec.hi)
        coverage[spec.id] = float(np.isfinite(col).mean())
        clipped = np.isfinite(col) & ((col < spec.lo) | (col > spec.hi))
        if clipped.mean() > 0.001:
            print(
                f"  WARNING: {spec.id} clipped in {100 * clipped.mean():.1f} % of cells "
                f"- widen lo/hi in the feature dictionary"
            )

    # ---- per-cell standard deviations (for the uncertainty band) ----------
    sd_specs = [s for s in specs if f"{s.id}__sd" in df.columns]
    sd = np.empty((n, len(sd_specs)), dtype=np.uint8)
    for j, spec in enumerate(sd_specs):
        # sd shares the feature's span but starts at zero
        sd[:, j] = quantize(df[f"{spec.id}__sd"].to_numpy(dtype=np.float64), 0.0, spec.hi - spec.lo)

    # ---- logistics (Earth only) -------------------------------------------
    analogs = None
    if analogs_path and Path(analogs_path).exists():
        analogs = pd.read_csv(analogs_path)
        analogs = analogs.dropna(subset=["lat", "lon"])
        print(f"  known analogs: {len(analogs)} sites from {analogs_path}")
    elif body == "earth":
        print("  WARNING: no known_analogs.csv - novelty mode will be disabled in the UI")

    log_cols: list[str] = []
    log_meta: dict[str, dict] = {}
    if body == "earth":
        df = df.copy()
        df["known_analog_km"] = known_analog_distance_km(lat, lon, analogs)
        log_cols = [c for c in LOGISTICS_PACK if c in df.columns]
        logi = np.empty((n, len(log_cols)), dtype=np.uint8)
        for j, c in enumerate(log_cols):
            spec = LOGISTICS_PACK[c]
            logi[:, j] = quantize(df[c].to_numpy(dtype=np.float64), spec["lo"], spec["hi"], spec["scale"])
            log_meta[c] = spec
    else:
        logi = np.empty((n, 0), dtype=np.uint8)

    # ---- country codes ----------------------------------------------------
    country_codes: list[str] = []
    if "country_iso3" in df.columns:
        cats = pd.Categorical(df["country_iso3"].fillna("---"))
        country_codes = [str(c) for c in cats.categories][:255]
        idx = np.clip(cats.codes.astype(np.int16), 0, 254).astype(np.uint8)
        (out_dir / f"{body}_country.bin").write_bytes(idx.tobytes())

    # ---- write ------------------------------------------------------------
    (out_dir / f"{body}_features.bin").write_bytes(feat.tobytes(order="C"))
    (out_dir / f"{body}_index.bin").write_bytes(df["cell_id"].to_numpy(dtype=np.uint32).tobytes())
    if len(sd_specs):
        (out_dir / f"{body}_sd.bin").write_bytes(sd.tobytes(order="C"))
    if logi.shape[1]:
        (out_dir / f"{body}_logistics.bin").write_bytes(logi.tobytes(order="C"))
    if "qa_flags" in df.columns:
        (out_dir / f"{body}_qa.bin").write_bytes(df["qa_flags"].to_numpy(dtype=np.uint16).tobytes())

    synthetic_grid = Path(str(grid_path) + ".SYNTHETIC").exists()
    synthetic_targets = False
    if targets_path and Path(targets_path).exists():
        targets = json.loads(Path(targets_path).read_text(encoding="utf-8"))
        synthetic_targets = any(t.get("synthetic") for t in targets)
        (out_dir / "targets.json").write_text(json.dumps(targets), encoding="utf-8")
    synthetic = synthetic_grid or synthetic_targets

    # --- the app's "nice to have" files: known analogs, validation, deep dives ---
    if analogs is not None and len(analogs):
        cols = [c for c in ("id", "name", "lat", "lon", "analog_for", "analog_type",
                            "accessible_by_design", "reference_url") if c in analogs.columns]
        rows = analogs[cols].where(analogs[cols].notna(), None).to_dict(orient="records")
        (out_dir / "known_analogs.json").write_text(json.dumps(rows), encoding="utf-8")

    deep_src = Path("science/deep_dives")
    if deep_src.is_dir():
        cards = sorted(x for x in deep_src.glob("*.md") if not x.name.startswith("_"))
        if cards:
            dd = out_dir / "deep_dives"
            dd.mkdir(exist_ok=True)
            index = []
            for md in cards:
                shutil.copyfile(md, dd / md.name)
                first = next((ln.lstrip("# ").strip()
                              for ln in md.read_text(encoding="utf-8").splitlines()
                              if ln.startswith("#")), md.stem)
                index.append({"id": md.stem, "title": first, "file": md.name})
            # Prefer the generator's index: it carries name, lat/lon, body,
            # summary, target and profile, which the Discoveries tab needs.
            gen = deep_src / "index.json"
            if gen.exists():
                shutil.copyfile(gen, dd / "index.json")
            else:
                (dd / "index.json").write_text(json.dumps(index), encoding="utf-8")
            print(f"  deep dives: {len(index)}")

    for name, src in (extra_json or {}).items():
        if Path(src).exists():
            shutil.copyfile(src, out_dir / name)
        else:
            print(f"  note: {src} not there yet, skipping {name}")

    transfer = load_transfer_rules(contract_dir) if contract_dir else load_transfer_rules()
    (out_dir / "transfer_rules.json").write_text(json.dumps(transfer), encoding="utf-8")

    meta = {
        "body": body,
        "grade_sigma": GRADE_SIGMA,
        "n_cells": int(n),
        "grid": {
            "ncols": GRID_NCOLS[body],
            "nrows": GRID_NCOLS[body] // 2,
            "res_deg": GRID_RES[body],
            "lat0": 90.0,
            "lon0": -180.0,
            "note": "lat = lat0 - (row + 0.5) * res; lon = lon0 + (col + 0.5) * res; row = cell_id // ncols",
        },
        "eps": DEFAULT_EPS,
        "contract_version": 1,
        "synthetic": synthetic,
        "synthetic_grid": synthetic_grid,
        "synthetic_targets": synthetic_targets,
        "dimensions": contract.dimensions,
        "features": [
            {
                "id": s.id,
                "dim": s.dim,
                "tier": s.tier,
                "unit": s.unit,
                "lo": s.lo,
                "hi": s.hi,
                "sigma": s.sigma,
                "sigma_mode": s.sigma_mode,
                "sigma_floor": s.sigma_floor,
                "gravity_swap": s.gravity_swap,
                "earth_only": s.earth_only,
                "scored": s.scored,
                "coverage": round(coverage[s.id], 4),
            }
            for s in specs
        ],
        "sd_features": [s.id for s in sd_specs],
        "logistics": log_meta,
        "logistics_order": log_cols,
        "country_codes": country_codes,
        "litho_matrix": contract.litho_matrix.tolist(),
        "missing_code": MISSING,
    }
    (out_dir / f"{body}_meta.json").write_text(json.dumps(meta), encoding="utf-8")

    total = sum(p.stat().st_size for p in out_dir.glob("*") if p.is_file())
    print(f"  {body}: {n:,} cells x {len(specs)} features")
    for p in sorted(out_dir.glob("*")):
        if p.is_file():
            print(f"    {p.name:24s} {p.stat().st_size / 1e6:7.2f} MB")
    print(f"  total bundle: {total / 1e6:.2f} MB  (budget 20 MB)")
    if total > 20e6:
        print("  WARNING: over the 20 MB budget - drop stretch features or coarsen the grid")
    if synthetic:
        what = []
        if synthetic_grid:
            what.append("the Earth grid")
        if synthetic_targets:
            what.append("at least one target")
        print(f"  NOTE: SYNTHETIC data in this bundle ({' and '.join(what)}) - "
              f"the About modal must say so")
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description="Pack a feature grid for the web app")
    ap.add_argument("--grid", required=True, help="earth_grid.parquet / moon_grid.parquet / ...")
    ap.add_argument("--body", default="earth", choices=["earth", "moon", "mars"])
    ap.add_argument("--out", default="web/public/data")
    ap.add_argument("--targets", default=None)
    ap.add_argument("--analogs", default="science/known_analogs.csv")
    ap.add_argument("--validation", default="validation/validation.json",
                    help="validate.py output, copied into the bundle for the UI tab")
    ap.add_argument("--science-dir", default="science",
                    help="copy missions.json / breaks_text.json from here")
    args = ap.parse_args()

    science = Path(args.science_dir)
    extra = {
        "missions.json": science / "missions.json",
        "breaks_text.json": science / "breaks_text.json",
        # written by engine/validate.py; the Validation tab is empty without it
        "validation.json": Path(args.validation),
    }
    pack(
        grid_path=Path(args.grid),
        out_dir=Path(args.out),
        body=args.body,
        analogs_path=Path(args.analogs) if args.analogs else None,
        targets_path=Path(args.targets) if args.targets else None,
        extra_json=extra,
    )


if __name__ == "__main__":
    main()
