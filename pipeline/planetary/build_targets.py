"""Build contract/targets.json - Moon & Mars target fingerprints (tasks M3-M5).

Owner: Michal.
AI-assisted: first version written with Claude, then run, checked and edited by
Michal before merging.

Run from the repo root:

    python3 pipeline/planetary/build_targets.py

What it does, per target:
  1. Reads a window of the planetary DEM around the target straight from the
     USGS server (GDAL /vsicurl/ windowed read - the 11-22 GB files are never
     downloaded).
  2. Reprojects that window to a local azimuthal-equidistant grid in metres,
     centred on the target, so slope and roughness are measured in real
     distances (never on a lat/lon grid).
  3. Computes the terrain features with the SHARED definition in
     engine/terrain_features.py (the same function Clara's Earth numbers are
     checked against - never re-derive them here).
  4. Estimates `sd` by recomputing the terrain with the centre shifted 5 km
     north/south/east/west and taking the standard deviation.
  5. Adds the "0 by definition" features and any non-terrain values filled in
     OTHER below, then writes contract/targets.json and checks it against the
     contract.

Footprint: a square of side 2 x radius_km (30 km for the default 15 km), the
same idea as one 0.25 deg Earth cell (~28 km). rough_10km needs a window of at
least 30 km, so do not shrink it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))
from terrain_features import terrain_features  # noqa: E402  (shared definition)

OUT = ROOT / "contract" / "targets.json"
RADIUS_KM = 15
SHIFT_M = 5000.0  # centre shift used to estimate sd

DEM = {
    "mars": {
        "url": "/vsicurl/https://planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/"
        "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif",
        "res_m": 200.0,
        "sphere": "+R=3396190",
        "source": "MOLA-HRSC blended DEM 200 m v2 (Fergason, Hare & Laura 2018, USGS Astrogeology)",
    },
    "moon": {
        # SLDEM2015 only covers 60S-60N. South-pole targets need the LOLA polar
        # DEM from PGDA instead (polar stereographic) - add that before the
        # Shackleton / Artemis targets.
        "url": "/vsicurl/https://planetarymaps.usgs.gov/mosaic/LolaKaguya_Topo/"
        "Lunar_LRO_LOLAKaguya_DEMmerge_60N60S_512ppd.tif",
        "res_m": 100.0,
        "sphere": "+R=1737400",
        "source": "LOLA + Kaguya TC merged DEM, SLDEM2015 512 ppd (Barker et al. 2016, USGS Astrogeology)",
    },
}

# Longitude: east-positive, -180..+180 on every body.
TARGETS = [
    {
        "id": "mars_jezero",
        "body": "mars",
        "name": "Jezero crater",
        "lat": 18.4,
        "lon": 77.5,
        "tags": ["sedimentary", "astrobiology"],
        "blurb": "Ancient lake delta; Perseverance landing site.",
    },
    {
        "id": "mars_gale",
        "body": "mars",
        "name": "Gale crater",
        "lat": -5.4,
        "lon": 137.8,
        "tags": ["sedimentary", "layered"],
        "blurb": "Layered sediments and sulfates; Curiosity landing site.",
    },
    {
        "id": "moon_apollo17",
        "body": "moon",
        "name": "Taurus-Littrow valley (Apollo 17)",
        "lat": 20.19,
        "lon": 30.77,
        "tags": ["ground-truth", "mare"],
        "blurb": "Apollo 17 landing site: ground truth for the method.",
    },
]

# Real zeros on the Moon and Mars ("0 by definition" in feature_dictionary.yaml).
# These are genuine values, not placeholders.
ZERO_BY_DEFINITION = {"precip_mm": 0.0, "ndvi_max": 0.0}

# Non-terrain MVP features still to fill per target:
#   ti_class, tmin_k, tmax_k, albedo, litho_class, ice_idx
# Take each from its product (see feature_dictionary.yaml) and cite it.
# Leave a feature OUT until it has a real value - never write a placeholder
# zero; the engine skips missing features, but a wrong zero poisons a whole
# dimension. Format:
#   "mars_jezero": {
#       "features": {"albedo": <value>},
#       "sd":       {"albedo": <uncertainty>},
#       "sources":  ["<product and citation>"],
#   },
#
# v1 values below come from published rover / orbital results for these exact
# sites (sources listed per target). They are site-level estimates, not yet
# computed over the 30 km window from the global products - replace them with
# product values (TES/THEMIS, MCD, Diviner, LROC, USGS maps) once those reads
# are in place. Still missing on purpose (no reliable number yet):
#   mars_jezero    tmin_k, tmax_k  -> Mars Climate Database at 18.4N 77.5E
#   moon_apollo17  albedo          -> LROC WAC 643 nm normalized reflectance
OTHER: dict[str, dict] = {
    "mars_jezero": {
        "features": {"ti_class": 2, "albedo": 0.16, "litho_class": 1, "ice_idx": 0.0},
        "sd": {"ti_class": 0.5, "albedo": 0.03, "ice_idx": 0.05},
        "sources": [
            "ti_class: THEMIS TI ~200-400 around the rover traverse (Vicente-Retortillo et al., EPSC2026-1140); "
            "MEDA TI 180-605 (Martinez et al. 2023, JGR Planets, doi:10.1029/2022JE007537); "
            "Mars bins 100/250/600/1200 -> class 2",
            "albedo: OMEGA regional mean ~0.16, MEDA noon albedo 0.10-0.23 (Vicente-Retortillo et al., EPSC2026-1140)",
            "litho_class: crater floor is igneous - Seitah olivine cumulate, Maaz lava flows (Farley et al. 2022, "
            "Science, doi:10.1126/science.abo2196); the delta in the west of the window is sedimentary (class 3) "
            "- Sofia to confirm",
            "ice_idx: 18N is far equatorward of the near-surface ice stability zone (~50 deg; Morgan et al. 2021, "
            "Nature Astronomy, doi:10.1038/s41550-020-01290-z)",
        ],
    },
    "mars_gale": {
        "features": {"ti_class": 2, "tmin_k": 175.0, "tmax_k": 285.0, "albedo": 0.20,
                     "litho_class": 3, "ice_idx": 0.0},
        "sd": {"ti_class": 0.5, "tmin_k": 8.0, "tmax_k": 8.0, "albedo": 0.05, "ice_idx": 0.05},
        "sources": [
            "ti_class: THEMIS TI 250-410 over most of the landing region, layered units 400-500 "
            "(Fergason et al. 2012, Space Sci Rev, doi:10.1007/s11214-012-9891-3) -> class 2",
            "tmin_k / tmax_k: REMS ground temperature, daily max ~250-290 K and daily min ~170-210 K over the year "
            "(Gomez-Elvira et al., Granada 2017 workshop) - measured on the crater floor; Mount Sharp is a bit colder",
            "albedo: ~0.20 average for the Gale region, range 0.1-0.3 (used in REMS/Navcam radiative studies)",
            "litho_class: Aeolis Mons (Mount Sharp) is a thick stack of sedimentary rocks (Curiosity results) -> class 3",
            "ice_idx: 5S is far equatorward of the near-surface ice stability zone (Morgan et al. 2021)",
        ],
    },
    "moon_apollo17": {
        "features": {"ti_class": 1, "tmin_k": 95.0, "tmax_k": 385.0, "litho_class": 1, "ice_idx": 0.0},
        "sd": {"ti_class": 0.5, "tmin_k": 5.0, "tmax_k": 10.0, "ice_idx": 0.02},
        "sources": [
            "ti_class: regolith-covered valley floor (old mare regolith ~14 m thick; Lucchitta 1992, "
            "LPI Workshop on Geology of the Apollo 17 Landing Site) -> class 1",
            "tmin_k / tmax_k: Diviner, ~387-397 K at noon and ~95 K before sunrise near the equator "
            "(Williams et al. 2017, Icarus, doi:10.1016/j.icarus.2016.08.012); 20N noon is a few K lower",
            "litho_class: basalt-flooded valley floor under a dark pyroclastic mantle (Muehlberger et al. 1973, "
            "Science, doi:10.1126/science.182.4113.672) -> class 1; the massifs in the window are feldspathic "
            "breccia (class 2) - check the majority class with the USGS map",
            "ice_idx: no permanently shadowed regions at 20N (lunar PSRs are polar)",
        ],
    },
}


def read_local_dem(body: str, lat: float, lon: float, half_m: float) -> np.ndarray:
    """DEM window centred on (lat, lon), side 2*half_m, in local equidistant metres."""
    try:
        import rasterio
        from rasterio.crs import CRS
        from rasterio.enums import Resampling
        from rasterio.transform import from_origin
        from rasterio.vrt import WarpedVRT
    except ImportError:
        sys.exit("rasterio is missing - run:  python3 -m pip install rasterio pyproj")

    d = DEM[body]
    res = d["res_m"]
    n = int(round(2 * half_m / res))
    local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={lat} +lon_0={lon} {d['sphere']} +units=m +no_defs"
    )
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", VSI_CACHE=True):
        with rasterio.open(d["url"]) as src:
            with WarpedVRT(
                src,
                crs=local,
                transform=from_origin(-half_m, half_m, res, res),
                width=n,
                height=n,
                resampling=Resampling.bilinear,
                src_nodata=src.nodata,
                nodata=np.nan,
                dtype="float32",
            ) as vrt:
                dem = vrt.read(1).astype(np.float64)
            scale = src.scales[0] if src.scales else 1.0
            offset = src.offsets[0] if src.offsets else 0.0
    return dem * scale + offset


def terrain_with_sd(body: str, lat: float, lon: float) -> tuple[dict, dict]:
    """Terrain features at the target, plus sd from 4 shifted footprints."""
    res = DEM[body]["res_m"]
    half = RADIUS_KM * 1000.0
    big = read_local_dem(body, lat, lon, half + SHIFT_M)  # one read, padded
    n = int(round(2 * half / res))
    p = int(round(SHIFT_M / res))

    runs = []
    for dx, dy in [(0, 0), (SHIFT_M, 0), (-SHIFT_M, 0), (0, SHIFT_M), (0, -SHIFT_M)]:
        i0 = p - int(round(dy / res))  # row 0 is north
        j0 = p + int(round(dx / res))  # col 0 is west
        runs.append(terrain_features(big[i0 : i0 + n, j0 : j0 + n], res))

    centre = runs[0]
    sd = {}
    for k in centre:
        vals = np.array([r[k] for r in runs], dtype=np.float64)
        vals = vals[np.isfinite(vals)]
        if vals.size >= 2:
            sd[k] = float(np.std(vals))
    return centre, sd


def clean(d: dict) -> dict:
    """Drop NaN/inf (missing stays missing) and round for readability."""
    return {k: round(float(v), 4) for k, v in d.items() if np.isfinite(v)}


def build() -> list[dict]:
    out = []
    for t in TARGETS:
        body, lat, lon = t["body"], t["lat"], t["lon"]
        assert body in DEM, f"{t['id']}: no DEM configured for body {body!r}"
        assert -90 <= lat <= 90 and -180 <= lon <= 180, f"{t['id']}: lat/lon out of range"

        print(f"{t['id']}: reading DEM around {lat}, {lon} ...", flush=True)
        feats, sd = terrain_with_sd(body, lat, lon)
        if not np.isfinite(feats["relief_km"]):
            print(f"  WARNING: no DEM data at {t['id']} - check the coordinates / longitude convention")

        extra = OTHER.get(t["id"], {})
        feats.update(ZERO_BY_DEFINITION)
        feats.update(extra.get("features", {}))
        sd.update(extra.get("sd", {}))

        feats = clean(feats)
        sd = {k: v for k, v in clean(sd).items() if k in feats}
        print("  " + ", ".join(f"{k}={v}" for k, v in feats.items()))

        out.append(
            {
                "id": t["id"],
                "body": body,
                "name": t["name"],
                "lat": lat,
                "lon": lon,
                "radius_km": RADIUS_KM,
                "synthetic": False,
                "features": feats,
                "sd": sd,
                "tags": t["tags"],
                "sources": [DEM[body]["source"]] + list(extra.get("sources", [])),
                "blurb": t["blurb"],
            }
        )
    return out


def check(targets: list[dict]) -> None:
    """Same check as the bottom of pipeline/planetary/README.md."""
    from score import load_contract

    c = load_contract()
    ids = {f.id for f in c.features}
    mvp = {f.id for f in c.scored_features(("mvp",))}
    print("\nContract check:")
    for t in targets:
        unknown = sorted(set(t["features"]) - ids)
        missing = sorted(mvp - set(t["features"]))
        print(f"  {t['id']:16s} unknown: {unknown or '-'}   missing MVP: {missing or '-'}")
        if unknown:
            sys.exit("Unknown feature ids - they must match feature_dictionary.yaml exactly.")


def main() -> None:
    targets = build()
    check(targets)
    OUT.write_text(json.dumps(targets, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT}  ({len(targets)} targets)")


if __name__ == "__main__":
    main()
