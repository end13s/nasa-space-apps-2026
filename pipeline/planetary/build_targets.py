"""Build contract/targets.json - Moon & Mars target fingerprints (tasks M3-M5).

Owner: Michal.
AI-assisted: first version written with Claude, then run, checked and edited by
Michal before merging.

Run from the repo root:

    python3 pipeline/planetary/build_targets.py

What it does, per target:
  1. Reads a window of the planetary DEM around the target straight from the
     server (GDAL /vsicurl/ windowed read - the 0.7-22 GB files are never
     downloaded). Mars: MOLA-HRSC. Moon 60S-60N: SLDEM2015. Moon south of
     80S: the LOLA 80-90S polar DEM from PGDA (cloud-optimized GeoTIFF).
  2. Reprojects that window to a local azimuthal-equidistant grid in metres,
     centred on the target, so slope and roughness are measured in real
     distances (never on a lat/lon grid).
  3. Computes the terrain features with the SHARED definition in
     engine/terrain_features.py (Sofia's module, the same definition the Earth
     export is checked against - never re-derive them here).
  4. Estimates `sd` by recomputing the terrain with the centre shifted
     north/south/east/west (5 km, or radius/3 for small targets) and taking
     the standard deviation.
  5. Adds the "0 by definition" features and any non-terrain values filled in
     OTHER below, gives every value an evidence grade A-D (see GRADES), then
     writes contract/targets.json and checks it against the contract.

Footprint: a square of side 2 x radius_km (30 km for the default 15 km), the
same idea as one 0.25 deg Earth cell (~28 km). rough_10km needs a window of at
least 30 km, so targets with radius_km < 15 (e.g. the 5 km Jezero delta) have
no rough_10km - it is left out, never written as a guess.

Targets whose lat/lon is still None are skipped with a message (the Artemis
regions whose official outlines we do not have yet).
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
DEFAULT_RADIUS_KM = 15
MAX_SHIFT_M = 5000.0  # centre shift used to estimate sd (radius/3 if smaller)

DEM = {
    "mars": {
        "url": "/vsicurl/https://planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/"
        "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif",
        "res_m": 200.0,
        "sphere": "+R=3396190",
        "source": "MOLA-HRSC blended DEM 200 m v2 (Fergason, Hare & Laura 2018, USGS Astrogeology)",
        "grade": "B",  # orbital DEM, no ground truth for the terrain statistics
    },
    "moon": {
        # SLDEM2015 only covers 60S-60N; polar targets use "moon_south" below.
        "url": "/vsicurl/https://planetarymaps.usgs.gov/mosaic/LolaKaguya_Topo/"
        "Lunar_LRO_LOLAKaguya_DEMmerge_60N60S_512ppd.tif",
        "res_m": 100.0,
        "sphere": "+R=1737400",
        "source": "LOLA + Kaguya TC merged DEM, SLDEM2015 512 ppd (Barker et al. 2016, USGS Astrogeology)",
        "grade": "B",  # orbital DEM, no ground truth for the terrain statistics
    },
    "moon_south": {
        # LOLA 80-90S DEM, 40 m/px, south polar stereographic, cloud-optimized
        # GeoTIFF (685 MB; a 20 m version exists, but we resample to 100 m).
        "url": "/vsicurl/https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_40MPP_ADJ.TIF",
        "res_m": 100.0,
        "sphere": "+R=1737400",
        "source": "LOLA south polar DEM LDEM_80S_40MPP_ADJ (Barker et al. 2023, PSJ 4:183, "
        "doi:10.3847/PSJ/acf3e1; data doi:10.60903/gsfcpgda-lola-spole)",
        "grade": "B",  # orbital laser altimetry, no ground truth
    },
}


def dem_key(body: str, lat: float) -> str:
    """Which DEM covers this target."""
    if body == "mars":
        return "mars"
    if body == "moon" and abs(lat) <= 60:
        return "moon"
    if body == "moon" and lat <= -80:
        return "moon_south"
    raise ValueError(f"no DEM configured for {body} at latitude {lat}")

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
    {
        # Same crater, different question: the lake-sediment delta that is the
        # reason Perseverance went there (Eduard, Sat 14:12). Small radius on
        # purpose; rough_10km is undefined at 5 km and is left out.
        "id": "mars_jezero_delta",
        "body": "mars",
        "name": "Jezero western delta front",
        "lat": 18.48,
        "lon": 77.39,
        "radius_km": 5,
        "tags": ["sedimentary", "delta", "astrobiology"],
        "blurb": "Lake delta front in Jezero crater; the sedimentary target for the astrobiology profile.",
        "coord_source": "centre: western fan unit NHjf2 (18.48N 77.39E) in Sun & Stack 2020, "
        "USGS SIM 3464, doi:10.3133/sim3464",
    },
    {
        "id": "moon_shackleton_rim",
        "body": "moon",
        "name": "Shackleton crater and rim",
        "lat": -89.67,
        "lon": 129.78,
        "tags": ["polar", "illumination", "psr"],
        "blurb": "Crater at the lunar south pole: near-permanently lit rim around a permanently shadowed floor.",
        "coord_source": "centre: IAU Gazetteer of Planetary Nomenclature, Shackleton (feature 5450), "
        "diameter 20.9 km - the 15 km circle covers the whole crater and rim",
    },
]

# The nine Artemis III candidate regions (NASA update, Oct 2024).
# Centres come from the official region OUTLINES, never guessed: each centre is
# the area centroid of the outline polygon, computed in south polar
# stereographic (the projection the outlines are defined in - they come out as
# exact 16-30 km squares there). Format (lat, lon): planetocentric,
# east-positive, -180..180. While a centre is None the region is skipped.
#
# Two sources:
#  - MOON_TREK_2022: NASA Moon Trek layer "Artemis III Candidate Landing
#    Regions, S Pole" (A3_Named_regions_SP.geojson). It still holds the 2022
#    set of 13; these five regions kept the same names in the Oct 2024 list.
#  - USGS_2024: the regions new in 2024, from the USGS release of the
#    down-selected regions (outlines from LROC QuickMap). Centre = mean of the
#    1 km grid-cell centres, converted from the file's projection (Moon 2015
#    sphere, south polar stereographic, k0 0.994, false E/N 500 km).
# Cross-check: the 2024 "Mons Mouton" centre lands within ~1 km of the 2022
# Moon Trek "Leibnitz Beta Plateau" centre - the same place under its new IAU
# name, from two independent files and two different conversions.
# Still missing: Mons Mouton Plateau (its USGS files are too big to upload;
# the 1 km .dbf alone is enough).
MOON_TREK_2022 = ("centre: centroid of the region outline in the NASA Moon Trek layer "
                  "'Artemis III Candidate Landing Regions, S Pole' (2022 outlines; region kept in the Oct 2024 list)")
USGS_2024 = ("centre: centre of the region's 1 km grid in USGS 'Down Selected Artemis III Candidate "
             "Landing Site Navigational Grids' (McClernan 2024, doi:10.5066/P1MEQ6UK; outlines from LROC QuickMap)")
ARTEMIS = [
    # (id,                                 name,                  (lat, lon),             source)
    ("moon_artemis_peak_near_cabeus_b",   "Peak near Cabeus B",  (-83.6514, -68.7263),   USGS_2024),
    ("moon_artemis_haworth",              "Haworth",             (-86.7639, -22.7770),   MOON_TREK_2022),
    ("moon_artemis_malapert_massif",      "Malapert Massif",     (-85.9948, -0.2358),    MOON_TREK_2022),
    ("moon_artemis_mons_mouton_plateau",  "Mons Mouton Plateau", None,                   None),
    ("moon_artemis_mons_mouton",          "Mons Mouton",         (-85.4218, 31.6755),    USGS_2024),
    ("moon_artemis_nobile_rim_1",         "Nobile Rim 1",        (-85.4381, 37.3667),    MOON_TREK_2022),
    ("moon_artemis_nobile_rim_2",         "Nobile Rim 2",        (-83.9540, 58.8221),    MOON_TREK_2022),
    ("moon_artemis_de_gerlache_rim_2",    "de Gerlache Rim 2",   (-88.2300, -64.6284),   MOON_TREK_2022),
    ("moon_artemis_slater_plain",         "Slater Plain",        (-87.1697, 125.4596),   USGS_2024),
]
for _tid, _name, _centre, _src in ARTEMIS:
    TARGETS.append(
        {
            "id": _tid,
            "body": "moon",
            "name": f"Artemis candidate landing region: {_name}",
            "lat": None if _centre is None else _centre[0],
            "lon": None if _centre is None else _centre[1],
            "tags": ["polar", "artemis", "permanent-base"],
            "blurb": f"{_name}, one of NASA's nine candidate crew landing regions near the lunar south pole "
                     "(announced for Artemis III, Oct 2024).",
            "coord_source": _src,
        }
    )

# Real zeros on the Moon and Mars ("0 by definition" in feature_dictionary.yaml).
# These are genuine values, not placeholders. soil_moist is a stretch feature,
# but it is just as exactly zero, so it goes in with the other two.
ZERO_BY_DEFINITION = {"precip_mm": 0.0, "ndvi_max": 0.0, "soil_moist": 0.0}

# ---------------------------------------------------------------------------
# Evidence grades (adopted at the Saturday sync). Every value in targets.json
# carries a letter; Eduard turns it into a tolerance, so a weakly known value
# cannot produce false precision.
#   A  multiple instruments, or ground truth at the site
#   B  single orbital instrument, no ground truth
#   C  model-derived or extrapolated - incl. anything inferred from latitude
#   D  poorly constrained - e.g. a literature constant instead of a measurement
#   DEF exact by definition, not measured (engine/score.py GRADE_SIGMA)
# Grade by SOURCE, not by value: "__terrain__" covers every DEM-derived
# feature (TERRAIN_KEYS) in one line, and each DEM below carries its grade.
# A grade is a summary of what the citation in "sources" already says, and it
# describes how well we know the value over the whole footprint, not at one
# rover position.
# ---------------------------------------------------------------------------
GRADES = ("A", "B", "C", "D", "DEF")
TERRAIN_KEYS = ("relief_km", "slope_med_deg", "slope_p90_deg", "hypso_int",
                "flat_frac", "steep_frac", "rough_2km", "rough_10km")
# The by-definition zeros (no rain, no plants, no soil moisture on the Moon or
# Mars) are exact but not evidence of anything, so they get DEF - A keeps
# meaning "measured, with ground truth".
ZERO_GRADE = "DEF"

# Non-terrain MVP features still to fill per target:
#   ti_class, tmin_k, tmax_k, albedo, litho_class, ice_idx
# Take each from its product (see feature_dictionary.yaml) and cite it.
# Leave a feature OUT until it has a real value - never write a placeholder
# zero; the engine skips missing features, but a wrong zero poisons a whole
# dimension. Format:
#   "mars_jezero": {
#       "features": {"albedo": <value>},
#       "sd":       {"albedo": <uncertainty>},
#       "grades":   {"albedo": "<A-D>"},   # terrain is graded via its DEM
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
        "grades": {
            "ti_class": "B",     # THEMIS orbital; MEDA ground truth covers only the rover traverse,
            "albedo": "B",       #   a tiny part of the 30 km window (Eduard's audit, Sat 15:13)
            "litho_class": "B",  # Perseverance analysed the floor rocks along its traverse only;
                                 #   over the 30 km window the class rests on orbital mapping
            "ice_idx": "C",      # inferred from the ice-stability latitude, not measured here
        },
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
        "grades": {
            "ti_class": "B",     # THEMIS, orbital - the cited source has no ground truth
            "tmin_k": "A",       # REMS, measured on the surface
            "tmax_k": "A",
            "albedo": "C",       # regional average used as a model input, not measured in our window
            "litho_class": "A",  # Curiosity ground truth
            "ice_idx": "C",      # inferred from the ice-stability latitude
        },
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
        "grades": {
            "ti_class": "B",     # Apollo 17 ground truth covers the landing area, not the massifs in the window
            "tmin_k": "C",       # Diviner equatorial values extrapolated to 20N
            "tmax_k": "C",       #   (A if replaced by the Apollo 17 heat-flow surface thermometers)
            "litho_class": "A",  # Apollo 17 samples
            "ice_idx": "C",      # inferred from latitude: no PSRs at 20N
        },
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
    "mars_jezero_delta": {
        "features": {"litho_class": 3, "ice_idx": 0.0},
        "sd": {"ice_idx": 0.05},
        "grades": {
            "litho_class": "A",  # Perseverance Delta Front campaign ground truth
            "ice_idx": "C",      # inferred from the ice-stability latitude
        },
        "sources": [
            "litho_class: deltaic sedimentary rocks of the western fan front, deposited in a lake "
            "(Perseverance Delta Front campaign; Sun & Stack 2020, USGS SIM 3464, unit NHjf2) -> class 3",
            "ice_idx: 18N is far equatorward of the near-surface ice stability zone (Morgan et al. 2021)",
        ],
    },
    # Shackleton and the Artemis regions get their non-terrain values from the
    # polar products below (polar_values), automatically for every target.
}

# ---------------------------------------------------------------------------
# South-polar targets (Shackleton + Artemis regions)
# ---------------------------------------------------------------------------
# ice_idx = share of the target window in permanent shadow, from the PGDA PSR
# maps (Mazarico et al. 2011). Permanent shadow is where water ice can be
# cold-trapped, which is why these regions are candidates. Still to fold in:
# LEND hydrogen. Still to add for these targets: tmin_k / tmax_k (Diviner
# polar products), albedo, ti_class.
#
# The same PSR map is published in several copies. On Sat 16:08-16:14 the
# PGDA COG link would not open and the PGDA TIF opened but failed reading
# tiles ("got 0 bytes"), so each copy is now tested with a small real read
# before it is used, and a read failure later on moves to the next copy.
# If none works, the build does NOT stop: ice_idx is left out for the polar
# targets and everything else is still written.
PSR_CANDIDATES = [
    # (url, metres per pixel) - 75-90S at 120 m first, then 65-90S at 240 m
    ("http://imbrium.mit.edu/EXTRAS/ILLUMINATION/JP2/LPSR_75S_120M_201608.JP2", 120.0),
    ("https://pgda.gsfc.nasa.gov/data/MoonIllumination/LPSR_75S_120M_201608.TIF", 120.0),
    ("https://pgda.gsfc.nasa.gov/data/MoonIllumination/LPSR_75S_120M_201608_COG.TIF", 120.0),
    ("https://pgda.gsfc.nasa.gov/data/MoonIllumination/LPSR_65S_240M_201608.TIF", 240.0),
    ("https://pgda.gsfc.nasa.gov/data/MoonIllumination/LPSR_65S_240M_201608_COG.TIF", 240.0),
]
_psr_bad: set[str] = set()
_psr_current: dict | None = None


def psr_map() -> dict | None:
    """The first PSR copy that passes a small real read (near Shackleton), or None."""
    global _psr_current
    if _psr_current is not None:
        return _psr_current
    for url, res in PSR_CANDIDATES:
        if url in _psr_bad:
            continue
        cfg = {"url": "/vsicurl/" + url, "res_m": res, "sphere": "+R=1737400",
               "name": url.rsplit("/", 1)[-1]}
        try:
            test = read_local_raster(cfg, -89.67, 129.78, 3000.0, nearest=True)
            if not np.isfinite(test).any():
                raise ValueError("test read returned no data")
        except Exception as e:  # noqa: BLE001 - any failure means "try the next copy"
            print(f"  PSR map not usable, trying the next copy: {url} ({type(e).__name__})")
            _psr_bad.add(url)
            continue
        print(f"  using PSR map {url}")
        _psr_current = cfg
        return cfg
    return None


def read_psr(lat: float, lon: float, half_m: float) -> tuple[dict | None, np.ndarray | None]:
    """PSR window around (lat, lon); moves to the next copy if a read fails."""
    global _psr_current
    while True:
        m = psr_map()
        if m is None:
            return None, None
        try:
            return m, read_local_raster(m, lat, lon, half_m, nearest=True)
        except Exception as e:  # noqa: BLE001
            print(f"  PSR read failed on {m['name']} ({type(e).__name__}) - trying the next copy")
            _psr_bad.add(m["url"].removeprefix("/vsicurl/"))
            _psr_current = None


def psr_source(name: str) -> str:
    return (f"ice_idx: share of the window in permanent shadow, PGDA PSR map {name} "
            "(Mazarico et al. 2011, Icarus 211:1066, doi:10.1016/j.icarus.2010.10.030); permanent "
            "shadow is the cold-trap proxy - a model from LOLA topography, LEND hydrogen not folded in yet")
POLAR_LITHO_SOURCE = ("litho_class: south-polar terrain is feldspathic highland (crater, basin and massif "
                      "material, no mare) on the Unified Geologic Map of the Moon (Fortezzo et al. 2020) "
                      "-> class 2; regional call, per-target unit check still to do")


def read_local_raster(cfg: dict, lat: float, lon: float, half_m: float, nearest: bool = False) -> np.ndarray:
    """Raster window centred on (lat, lon), side 2*half_m, in local equidistant metres.

    cfg has "url", "res_m" and "sphere". nearest=True for masks/classes (no
    blending of category values); bilinear otherwise.
    """
    try:
        import rasterio
        from rasterio.crs import CRS
        from rasterio.enums import Resampling
        from rasterio.transform import from_origin
        from rasterio.vrt import WarpedVRT
    except ImportError:
        sys.exit("rasterio is missing - run:  python3 -m pip install rasterio pyproj")

    res = cfg["res_m"]
    n = int(round(2 * half_m / res))
    local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={lat} +lon_0={lon} {cfg['sphere']} +units=m +no_defs"
    )
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", VSI_CACHE=True,
                      GDAL_HTTP_MAX_RETRY="3", GDAL_HTTP_RETRY_DELAY="1"):
        with rasterio.open(cfg["url"]) as src:
            with WarpedVRT(
                src,
                crs=local,
                transform=from_origin(-half_m, half_m, res, res),
                width=n,
                height=n,
                resampling=Resampling.nearest if nearest else Resampling.bilinear,
                src_nodata=src.nodata,
                nodata=np.nan,
                dtype="float32",
            ) as vrt:
                arr = vrt.read(1).astype(np.float64)
            scale = src.scales[0] if src.scales else 1.0
            offset = src.offsets[0] if src.offsets else 0.0
    return arr * scale + offset


def read_local_dem(key: str, lat: float, lon: float, half_m: float) -> np.ndarray:
    """DEM window; key is an entry of DEM ("mars", "moon", "moon_south")."""
    return read_local_raster(DEM[key], lat, lon, half_m)


def polar_values(lat: float, lon: float, radius_km: float) -> tuple[dict, list | None]:
    """Non-terrain values for a south-polar target, in the same shape as OTHER.

    litho_class is always set. ice_idx is the PSR share of the window, with sd
    from the same four shifted footprints as the terrain; it is left out (and
    `seen` is None) when no PSR map could be opened. The share is taken over
    ALL pixels of the window, so a map that stores "not shadowed" as nodata
    still gives the right number.
    """
    values = {
        "features": {"litho_class": 2},
        "sd": {},
        "grades": {"litho_class": "C"},  # regional call from the map, not yet checked target by target
        "sources": [POLAR_LITHO_SOURCE],
    }
    half = radius_km * 1000.0
    shift = min(MAX_SHIFT_M, half / 3.0)
    m, big = read_psr(lat, lon, half + shift)
    if m is None:
        return values, None

    res = m["res_m"]
    n = int(round(2 * half / res))
    p = int(round(shift / res))

    shares = []
    for dx, dy in [(0, 0), (shift, 0), (-shift, 0), (0, shift), (0, -shift)]:
        i0 = p - int(round(dy / res))
        j0 = p + int(round(dx / res))
        w = big[i0 : i0 + n, j0 : j0 + n]
        shares.append(np.count_nonzero(np.isfinite(w) & (w > 0)) / w.size)
    seen = sorted({float(v) for v in np.unique(big[np.isfinite(big)])[:6]})

    values["features"]["ice_idx"] = shares[0]
    values["sd"]["ice_idx"] = float(np.std(shares))
    values["grades"]["ice_idx"] = "C"  # PSR is modelled from LOLA topography; ice itself is not measured
    values["sources"].insert(0, psr_source(m["name"]))
    return values, seen


def terrain_with_sd(key: str, lat: float, lon: float, radius_km: float) -> tuple[dict, dict]:
    """Terrain features at the target, plus sd from 4 shifted footprints."""
    res = DEM[key]["res_m"]
    half = radius_km * 1000.0
    shift = min(MAX_SHIFT_M, half / 3.0)
    big = read_local_dem(key, lat, lon, half + shift)  # one read, padded
    n = int(round(2 * half / res))
    p = int(round(shift / res))

    runs = []
    for dx, dy in [(0, 0), (shift, 0), (-shift, 0), (0, shift), (0, -shift)]:
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


def expand_grades(raw: dict, feats: dict) -> dict:
    """Per-source grades -> one grade per feature present in `feats`.

    "__terrain__" expands to every DEM-derived feature (TERRAIN_KEYS).
    Later entries override earlier ones, so a specific feature can still
    be graded differently from its source group.
    """
    out = {}
    for k, g in raw.items():
        if g not in GRADES:
            raise ValueError(f"grade {g!r} for {k!r} is not one of {GRADES}")
        for kk in (TERRAIN_KEYS if k == "__terrain__" else (k,)):
            if kk in feats:
                out[kk] = g
    return out


def build() -> list[dict]:
    out = []
    skipped = []
    for t in TARGETS:
        body, lat, lon = t["body"], t["lat"], t["lon"]
        if lat is None or lon is None:
            skipped.append(t["id"])
            continue
        assert -90 <= lat <= 90 and -180 <= lon <= 180, f"{t['id']}: lat/lon out of range"
        radius_km = t.get("radius_km", DEFAULT_RADIUS_KM)
        key = dem_key(body, lat)

        print(f"{t['id']}: reading {key} DEM around {lat}, {lon} (radius {radius_km} km) ...", flush=True)
        feats, sd = terrain_with_sd(key, lat, lon, radius_km)
        if not np.isfinite(feats["relief_km"]):
            print(f"  WARNING: no DEM data at {t['id']} - check the coordinates / longitude convention")
        elif key == "moon_south" and feats["relief_km"] < 0.5:
            print(f"  WARNING: relief {feats['relief_km']:.2f} km at a south-polar target - expected 2-6 km. "
                  "Check the coordinates; this usually means the reprojection is wrong.")

        polar = {}
        if key == "moon_south":
            polar, seen = polar_values(lat, lon, radius_km)
            if seen is None:
                print("  WARNING: no PSR map could be opened - ice_idx left out for this target")
            else:
                share = polar["features"]["ice_idx"]
                print(f"  PSR map values seen: {seen} -> ice_idx (PSR share of the window) = {share:.3f}")
                if share > 0.9:
                    print("  WARNING: >90 % of the window counted as permanent shadow - check the PSR map encoding")

        extra = OTHER.get(t["id"], {})
        feats.update(ZERO_BY_DEFINITION)
        feats.update(polar.get("features", {}))
        feats.update(extra.get("features", {}))
        sd.update(polar.get("sd", {}))
        sd.update(extra.get("sd", {}))

        feats = clean(feats)
        sd = {k: v for k, v in clean(sd).items() if k in feats}
        raw_grades = {"__terrain__": DEM[key]["grade"]}
        raw_grades.update({k: ZERO_GRADE for k in ZERO_BY_DEFINITION})
        raw_grades.update(polar.get("grades", {}))
        raw_grades.update(extra.get("grades", {}))
        grades = expand_grades(raw_grades, feats)
        print("  " + ", ".join(f"{k}={v} [{grades.get(k, '?')}]" for k, v in feats.items()))

        out.append(
            {
                "id": t["id"],
                "body": body,
                "name": t["name"],
                "lat": lat,
                "lon": lon,
                "radius_km": radius_km,
                "synthetic": False,
                "features": feats,
                "sd": sd,
                "grades": grades,
                "tags": t["tags"],
                "sources": [DEM[key]["source"]]
                + ([t["coord_source"]] if t.get("coord_source") else [])
                + list(polar.get("sources", []))
                + list(extra.get("sources", [])),
                "blurb": t["blurb"],
            }
        )
    if skipped:
        print(f"\nSkipped {len(skipped)} target(s) with no centre yet (need the 2024 region outlines):")
        for tid in skipped:
            print(f"  {tid}")
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
        ungraded = sorted(set(t["features"]) - set(t.get("grades", {})))
        print(f"  {t['id']:34s} unknown: {unknown or '-'}   missing MVP: {missing or '-'}"
              f"   ungraded: {ungraded or '-'}")
        if unknown:
            sys.exit("Unknown feature ids - they must match feature_dictionary.yaml exactly.")


def main() -> None:
    targets = build()
    check(targets)
    OUT.write_text(json.dumps(targets, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT}  ({len(targets)} targets)")


if __name__ == "__main__":
    main()
