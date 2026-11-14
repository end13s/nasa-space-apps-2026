"""Analytic sun geometry shared by the Earth and the planetary pipelines.

Task E5. Clara (Earth) and Michal (Moon/Mars) both import ``lowsun_frac`` from
here so that the ``lowsun_frac`` column means exactly the same thing on every
body - that is the whole point of putting it in one file.

The model is deliberately simple and is documented as such on the site card:

    declination  d(t) = obliquity * sin(2*pi*t / year)
    max daily elevation at latitude phi = 90 - |phi - d(t)|

That is the elevation of the sun at local solar noon for a circular orbit with
no eccentricity and no atmospheric refraction. For the question we ask - "what
fraction of the year does this place only ever see the sun below 10 degrees?" -
that is accurate to roughly a day of the year, which is far inside the
resolution of everything else in the pipeline.

AI-assisted: scaffolded with Claude, reviewed and tested by Eduard.
"""

from __future__ import annotations

import numpy as np

# Obliquity of each body, degrees. Mirrors contract/body_constants.json.
OBLIQUITY_DEG = {
    "earth": 23.44,
    "moon": 1.54,
    "mars": 25.19,
}


def max_solar_elevation_deg(
    lat_deg: float | np.ndarray,
    obliquity_deg: float,
    n_samples: int = 365,
) -> np.ndarray:
    """Daily maximum solar elevation over one year.

    Returns an array of shape ``(..., n_samples)``: one noon elevation per
    sampled day. Negative values mean the sun never rises that day.
    """
    lat = np.asarray(lat_deg, dtype=np.float64)
    t = np.arange(n_samples, dtype=np.float64) / n_samples
    decl = obliquity_deg * np.sin(2.0 * np.pi * t)
    return 90.0 - np.abs(lat[..., None] - decl)


def lowsun_frac(
    lat_deg: float | np.ndarray,
    obliquity_deg: float,
    threshold_deg: float = 10.0,
    n_samples: int = 365,
) -> np.ndarray | float:
    """Fraction of the year when the daily max solar elevation stays below
    ``threshold_deg``.

    This is the ``lowsun_frac`` feature in contract/feature_dictionary.yaml.
    1.0 means the sun never climbs higher than the threshold all year - the
    grazing-light regime of the lunar south pole and of high Earth latitudes.

    >>> round(float(lowsun_frac(-85.0, OBLIQUITY_DEG["moon"])), 3)
    1.0
    >>> round(float(lowsun_frac(0.0, OBLIQUITY_DEG["earth"])), 3)
    0.0
    """
    elev = max_solar_elevation_deg(lat_deg, obliquity_deg, n_samples)
    frac = (elev < threshold_deg).mean(axis=-1)
    return float(frac) if np.ndim(lat_deg) == 0 else frac


def lowsun_frac_for_body(lat_deg, body: str, threshold_deg: float = 10.0):
    """Convenience wrapper: ``lowsun_frac_for_body(lat, "mars")``."""
    body = body.lower()
    if body not in OBLIQUITY_DEG:
        raise KeyError(f"unknown body {body!r}; expected one of {sorted(OBLIQUITY_DEG)}")
    return lowsun_frac(lat_deg, OBLIQUITY_DEG[body], threshold_deg)


def polar_night_frac(lat_deg, obliquity_deg: float, n_samples: int = 365):
    """Fraction of the year the sun never rises at all. Context for site cards."""
    elev = max_solar_elevation_deg(lat_deg, obliquity_deg, n_samples)
    frac = (elev < 0.0).mean(axis=-1)
    return float(frac) if np.ndim(lat_deg) == 0 else frac


if __name__ == "__main__":  # quick manual check
    for body, obl in OBLIQUITY_DEG.items():
        lats = np.array([0.0, 30.0, 60.0, 78.0, -85.0, -89.5])
        print(f"{body:6s} obliquity={obl:5.2f}")
        for lat, f in zip(lats, lowsun_frac(lats, obl)):
            print(f"    lat {lat:7.1f}  lowsun_frac {f:.3f}")
