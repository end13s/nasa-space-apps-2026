"""Synthetic stand-in data so nobody waits for the real pipelines (task E3).

Produces files with exactly the schema of Section 5.2 of the team plan:

    data_work/earth_grid.parquet   same columns as Clara's real export
    data_work/targets.json         same shape as Michal's real fingerprints

The numbers are invented but plausible and spatially coherent, so Julia's
heatmap looks like a planet rather than TV static and the engine exercises
every code path (classes, logs, NaNs, gravity swaps). Every target carries
"synthetic": true, and pack_web.py stamps the same flag into earth_meta.json,
so a fake build can never be mistaken for a real one in the demo.

Usage
-----
    python engine/fake_data.py --out data_work
    python engine/pack_web.py --earth data_work/earth_grid.parquet \
        --targets data_work/targets.json --out web/public/data

AI-assisted: scaffolded with Claude, reviewed by Eduard.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter

from illumination import OBLIQUITY_DEG, lowsun_frac

NROWS, NCOLS = 720, 1440
RES = 0.25
SEED = 20261114


def _noise(rng: np.random.Generator, sigma: float) -> np.ndarray:
    """Smooth, periodic-in-longitude random field on the full grid, mean 0 sd 1."""
    raw = rng.standard_normal((NROWS, NCOLS))
    field = gaussian_filter(raw, sigma=sigma, mode=("nearest", "wrap"))
    field -= field.mean()
    sd = field.std()
    return field / (sd if sd > 0 else 1.0)


def build_grid(seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    lat = 90.0 - (np.arange(NROWS) + 0.5) * RES
    lon = -180.0 + (np.arange(NCOLS) + 0.5) * RES
    LAT, LON = np.meshgrid(lat, lon, indexing="ij")

    # ---- land mask: smooth noise thresholded to about 24 % land, plus a polar cap, plus a
    #      polar cap so Antarctica exists and the ice features have somewhere
    #      to live.
    continents = _noise(rng, 18.0)
    land = continents > np.quantile(continents, 0.76)
    land |= LAT < -63.0
    land &= LAT > -89.5

    # ---- terrain -----------------------------------------------------------
    mountains = np.clip(_noise(rng, 6.0), 0, None) ** 1.5
    ruggedness = np.clip(_noise(rng, 3.0) * 0.5 + mountains, 0, None)
    relief = np.clip(ruggedness * 1.6 + rng.random((NROWS, NCOLS)) * 0.15, 0.01, 7.5)
    slope_med = np.clip(relief * 4.5 + _noise(rng, 4.0) * 1.2, 0.05, 40.0)
    slope_p90 = np.clip(slope_med * 2.1 + 1.5, 0.1, 58.0)
    rough2 = np.clip(relief * 7.0 + 1.0 + _noise(rng, 5.0), 0.2, 75.0)
    rough10 = np.clip(rough2 * 0.55 + 0.5, 0.2, 75.0)
    hypso = np.clip(0.48 + _noise(rng, 7.0) * 0.08, 0.05, 0.95)

    # ---- climate -----------------------------------------------------------
    abslat = np.abs(LAT)
    tmax = np.clip(318.0 - 0.95 * abslat - relief * 5.0 + _noise(rng, 8.0) * 6.0, 230.0, 345.0)
    tmin = np.clip(tmax - 35.0 - 1.1 * abslat - relief * 4.0 + _noise(rng, 8.0) * 5.0, 190.0, 305.0)
    diurnal = np.clip(8.0 + (tmax - tmin) * 0.25 + _noise(rng, 6.0) * 4.0, 2.0, 45.0)

    # Wet belts at the equator and mid-latitudes, dry at ~25 deg, like Earth.
    wet_belt = np.exp(-((abslat - 2.0) / 12.0) ** 2) + 0.7 * np.exp(-((abslat - 52.0) / 14.0) ** 2)
    wetness = np.clip(wet_belt + _noise(rng, 7.0) * 0.45, 0.0, None)
    precip = np.clip(wetness ** 2 * 2400.0 + 3.0, 0.0, 6000.0)
    aridity = 1.0 - np.clip(precip / 900.0, 0.0, 1.0)

    ndvi = np.clip(
        0.85 * (1.0 - np.exp(-precip / 650.0)) * np.clip((tmax - 258.0) / 50.0, 0.0, 1.0)
        + _noise(rng, 4.0) * 0.05,
        -0.05,
        0.95,
    )
    soil_moist = np.clip(0.03 + 0.45 * (1.0 - aridity) + _noise(rng, 5.0) * 0.03, 0.0, 0.6)

    # ---- ice ---------------------------------------------------------------
    cold = np.clip((268.0 - tmin) / 25.0, 0.0, 1.0)
    ice = np.clip(cold * (0.35 + 0.65 * np.clip(relief / 3.0, 0, 1)) + (LAT < -70.0) * 1.0, 0.0, 1.0)
    ice = np.clip(ice + _noise(rng, 4.0) * 0.05, 0.0, 1.0)

    # ---- material ----------------------------------------------------------
    albedo = np.clip(
        0.12 + 0.20 * aridity + 0.45 * ice - 0.06 * ndvi + _noise(rng, 4.0) * 0.03, 0.02, 0.88
    )
    # thermal-inertia class: dust/sand in dry lowlands, rock on steep ground,
    # class 4 under ice.
    ti = np.full((NROWS, NCOLS), 2.0)
    ti = np.where(aridity > 0.75, 1.0, ti)
    ti = np.where((aridity > 0.9) & (slope_med < 2.0), 0.0, ti)
    ti = np.where(slope_med > 12.0, 3.0, ti)
    ti = np.where(ice > 0.6, 4.0, ti)
    ti = np.clip(ti + np.round(_noise(rng, 3.0) * 0.4), 0, 4)

    litho_field = _noise(rng, 5.0)
    litho = np.digitize(litho_field, [-0.9, -0.2, 0.45, 1.1]) + 1.0  # 1..5
    litho = np.where(ice > 0.8, 5.0, litho)
    mafic = np.clip(0.98 + (litho == 1) * 0.04 + _noise(rng, 4.0) * 0.01, 0.9, 1.1)

    # ---- atmosphere --------------------------------------------------------
    aod = np.clip(0.08 + 0.7 * aridity ** 2 + _noise(rng, 5.0) * 0.1, 0.0, 3.0)
    wind = np.clip(6.0 + 5.0 * np.clip(abslat / 60.0, 0, 1) + _noise(rng, 5.0) * 2.5, 0.2, 29.0)

    # ---- illumination (the real analytic function, not noise) --------------
    lowsun_col = lowsun_frac(lat, OBLIQUITY_DEG["earth"])
    lowsun = np.repeat(lowsun_col[:, None], NCOLS, axis=1)
    shadow = np.clip(lowsun * 0.3 + slope_med / 60.0 + _noise(rng, 4.0) * 0.05, 0.0, 1.0)

    # ---- logistics ---------------------------------------------------------
    remoteness = np.clip(_noise(rng, 9.0) * 0.5 + 0.5 + aridity * 0.4 + ice * 0.5, 0.0, None)
    travel = np.clip(remoteness ** 2 * 900.0 + 5.0, 1.0, 5000.0)
    protected = np.clip(_noise(rng, 4.0) * 0.35 + 0.12, 0.0, 1.0)
    viirs = np.clip(np.exp(-remoteness * 3.0) * 60.0 + rng.random((NROWS, NCOLS)) * 0.2, 0.0, None)

    # ---- gravity-scaled roughness (shorter baseline -> a bit rougher) ------
    rough2_gM = np.clip(rough2 * 1.35 + _noise(rng, 5.0) * 0.5, 0.2, 75.0)
    rough10_gM = np.clip(rough10 * 1.25 + _noise(rng, 5.0) * 0.4, 0.2, 75.0)
    rough2_gR = np.clip(rough2 * 1.15 + _noise(rng, 5.0) * 0.4, 0.2, 75.0)
    rough10_gR = np.clip(rough10 * 1.10 + _noise(rng, 5.0) * 0.3, 0.2, 75.0)

    # ---- flatten to the land-cell table -----------------------------------
    rows, cols = np.nonzero(land)
    cell_id = (rows.astype(np.int32) * NCOLS + cols).astype(np.int32)
    sel = (rows, cols)

    df = pd.DataFrame(
        {
            "cell_id": cell_id,
            "lat": LAT[sel].astype(np.float32),
            "lon": LON[sel].astype(np.float32),
            "relief_km": relief[sel],
            "slope_med_deg": slope_med[sel],
            "slope_p90_deg": slope_p90[sel],
            "rough_2km": rough2[sel],
            "rough_10km": rough10[sel],
            "rough_2km_gM": rough2_gM[sel],
            "rough_10km_gM": rough10_gM[sel],
            "rough_2km_gR": rough2_gR[sel],
            "rough_10km_gR": rough10_gR[sel],
            "hypso_int": hypso[sel],
            "ti_class": ti[sel],
            "tmin_k": tmin[sel],
            "tmax_k": tmax[sel],
            "diurnal_amp_k": diurnal[sel],
            "albedo": albedo[sel],
            "litho_class": litho[sel],
            "mafic_idx": mafic[sel],
            "ice_idx": ice[sel],
            "precip_mm": precip[sel],
            "soil_moist": soil_moist[sel],
            "ndvi_max": ndvi[sel],
            "aod_p90": aod[sel],
            "wind_p95": wind[sel],
            "lowsun_frac": lowsun[sel],
            "shadow_frac_lowsun": shadow[sel],
            "travel_min": travel[sel],
            "protected_frac": protected[sel],
            "viirs_rad": viirs[sel],
        }
    )

    # within-cell spread, for the Monte-Carlo uncertainty band
    for col, frac in [
        ("relief_km", 0.18),
        ("slope_med_deg", 0.20),
        ("rough_2km", 0.15),
        ("rough_10km", 0.15),
        ("tmin_k", 0.02),
        ("tmax_k", 0.02),
        ("albedo", 0.10),
        ("ice_idx", 0.15),
        ("precip_mm", 0.20),
        ("ndvi_max", 0.12),
    ]:
        df[col + "__sd"] = (df[col].abs() * frac).astype(np.float32)

    # qa flags: pretend the polar-night LST gap and a few coastal cells
    qa = np.zeros(len(df), dtype=np.uint16)
    qa |= np.where(np.abs(df["lat"].to_numpy()) > 66.5, 4, 0).astype(np.uint16)
    qa |= (np.random.default_rng(seed + 1).random(len(df)) < 0.04).astype(np.uint16) * 2
    df["qa_flags"] = qa

    # fake country codes, just so the site card has a field to render
    codes = np.array(["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"])
    df["country_iso3"] = codes[(df["cell_id"].to_numpy() // 977) % len(codes)]

    # a few genuine data voids, so the "partial" path gets exercised
    void = np.random.default_rng(seed + 2).random(len(df)) < 0.015
    df.loc[void, "ti_class"] = np.nan
    void2 = np.random.default_rng(seed + 3).random(len(df)) < 0.01
    df.loc[void2, "tmin_k"] = np.nan

    float_cols = [c for c in df.columns if c not in ("cell_id", "qa_flags", "country_iso3")]
    df[float_cols] = df[float_cols].astype(np.float32)
    return df


# ---------------------------------------------------------------------------
# Synthetic targets - real coordinates (Section 4), invented fingerprints.
# Michal's targets.json replaces this file wholesale.
# ---------------------------------------------------------------------------

_TARGET_SEEDS = [
    # id, body, name, lat, lon, relief, slope, ti, tmin, tmax, albedo, litho, ice, blurb
    ("moon_shackleton_rim", "moon", "Shackleton crater rim", -89.66, 129.20,
     4.2, 14.0, 3, 60, 220, 0.16, 2, 0.75, "Near-permanent illumination beside a permanently shadowed region."),
    ("moon_artemis_mons_mouton", "moon", "Mons Mouton plateau", -84.70, 22.00,
     3.1, 9.5, 3, 75, 235, 0.15, 2, 0.45, "Artemis candidate landing region, broad high plateau."),
    ("moon_artemis_nobile_rim_1", "moon", "Nobile Rim 1", -85.30, 35.00,
     2.6, 11.0, 3, 70, 230, 0.15, 2, 0.55, "Artemis candidate landing region on the Nobile crater rim."),
    ("moon_marius_pit", "moon", "Marius Hills pit", 14.09, -56.24,
     0.35, 3.0, 2, 95, 390, 0.09, 1, 0.0, "Lava-tube skylight in a mare volcanic complex."),
    ("moon_apollo17", "moon", "Taurus-Littrow valley", 20.19, 30.77,
     2.0, 7.0, 3, 100, 385, 0.11, 1, 0.0, "Apollo 17 site: ground truth for the method."),
    ("mars_jezero", "mars", "Jezero crater", 18.4, 77.5,
     0.62, 2.1, 2, 185, 285, 0.13, 3, 0.02, "Ancient lake delta; Perseverance landing site."),
    ("mars_gale", "mars", "Gale crater", -5.4, 137.8,
     1.90, 4.0, 2, 180, 290, 0.14, 3, 0.0, "Layered sediments and sulfates; Curiosity landing site."),
    ("mars_oxia", "mars", "Oxia Planum", 18.3, -24.6,
     0.25, 1.1, 2, 185, 280, 0.12, 3, 0.03, "Clay-rich plains; Rosalind Franklin landing site."),
    ("mars_meridiani", "mars", "Meridiani Planum", -1.9, -5.5,
     0.18, 0.8, 1, 190, 295, 0.11, 4, 0.0, "Hematite and sulfate plains; evaporite analog."),
    ("mars_gusev", "mars", "Gusev crater", -14.6, 175.5,
     0.45, 1.8, 2, 182, 288, 0.15, 1, 0.0, "Basaltic plains with hydrothermal silica."),
    ("mars_arcadia", "mars", "Arcadia Planitia", 40.0, -170.0,
     0.20, 0.7, 1, 150, 250, 0.18, 3, 0.65, "Mid-latitude shallow ice; human landing candidate."),
    ("mars_deuteronilus", "mars", "Deuteronilus Mensae", 43.0, 22.0,
     1.40, 6.5, 2, 148, 245, 0.17, 3, 0.80, "Glacier-like viscous flow features."),
]


def build_targets(seed: int = SEED) -> list[dict]:
    rng = np.random.default_rng(seed + 10)
    out = []
    for (tid, body, name, lat, lon, relief, slope, ti, tmin, tmax, albedo, litho, ice, blurb) in _TARGET_SEEDS:
        rough2 = float(np.clip(relief * 8.0 + 1.0, 0.2, 75.0))
        feats = {
            "relief_km": float(relief),
            "slope_med_deg": float(slope),
            "slope_p90_deg": float(min(slope * 2.2 + 1.0, 58.0)),
            "rough_2km": rough2,
            "rough_10km": float(rough2 * 0.55),
            "hypso_int": float(np.clip(0.5 + rng.normal(0, 0.05), 0.05, 0.95)),
            "ti_class": float(ti),
            "tmin_k": float(tmin),
            "tmax_k": float(tmax),
            "diurnal_amp_k": float(tmax - tmin),
            "albedo": float(albedo),
            "litho_class": float(litho),
            "ice_idx": float(ice),
            "precip_mm": 0.0,
            "soil_moist": 0.0,
            "ndvi_max": 0.0,
            "aod_p90": 0.0 if body == "moon" else 0.35,
            "wind_p95": 0.0 if body == "moon" else 6.0,
            "lowsun_frac": float(lowsun_frac(lat, OBLIQUITY_DEG[body])),
            "shadow_frac_lowsun": float(np.clip(0.2 + slope / 40.0, 0.0, 1.0)),
        }
        sd = {k: abs(v) * 0.15 for k, v in feats.items() if k not in ("litho_class", "ti_class")}
        sd["ti_class"] = 0.5
        out.append(
            {
                "id": tid,
                "body": body,
                "name": name,
                "lat": lat,
                "lon": lon,
                "radius_km": 15,
                "synthetic": True,
                "features": feats,
                "sd": sd,
                "tags": ["synthetic"],
                "sources": ["SYNTHETIC placeholder - replace with Michal's targets.json (M5)"],
                "blurb": blurb,
            }
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic Analog Atlas inputs")
    ap.add_argument("--out", default="data_work", help="output directory")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    df = build_grid(args.seed)
    grid_path = out / "earth_grid.parquet"
    df.to_parquet(grid_path, index=False)

    targets = build_targets(args.seed)
    targets_path = out / "targets.json"
    targets_path.write_text(json.dumps(targets, indent=2), encoding="utf-8")

    print(f"wrote {grid_path}  ({len(df):,} land cells, {len(df.columns)} columns)")
    print(f"wrote {targets_path}  ({len(targets)} synthetic targets)")
    print("land fraction: %.1f %%" % (100.0 * len(df) / (NROWS * NCOLS)))


if __name__ == "__main__":
    main()
