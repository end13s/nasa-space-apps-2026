"""Analog Atlas similarity engine - Python reference implementation (task E4).

This file is the definition of the score. web/src/worker/score_core.js is a
line-for-line port of it and engine/tests/test_parity.py proves the two agree
to 1e-3 on random cells. If you change the maths here, change it there in the
same commit or the parity test fails - that is deliberate.

Pipeline of a single query
--------------------------
1. per-feature similarity   s_f in [0, 1]          (Gaussian / class / matrix)
2. per-dimension score      s_d = sum(w_f s_f) / sum(w_f)
3. overall score            S   = weighted geometric mean of (s_d + eps)

The geometric mean is the point: a site that matches beautifully on four
dimensions and is hopeless on the fifth is not a good analog, and an
arithmetic mean would hide that.

AI-assisted: scaffolded with Claude, reviewed and tested by Eduard.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import yaml

CONTRACT_DIR = Path(__file__).resolve().parent.parent / "contract"

# Floor added to every dimension score before taking logs. Keeps ln() finite
# and sets how brutally one dead dimension punishes the overall score.
# Exposed here (and in earth_meta.json) so it can be tuned on Sunday morning
# together with the sigmas, instead of being buried in the formula.
#   eps = 0.01  -> 5 dims, one at zero, rest perfect  => S ~ 0.40
#   eps = 1e-6  -> same case                          => S ~ 0.06
DEFAULT_EPS = 0.01

DIM_ORDER = ["T", "H", "M", "W", "B", "C", "A", "I"]

# Evidence grades (the proxy reframe, adopted at the Saturday sync).
# A target value we barely know must not produce a sharp similarity score, so
# the grade inflates that variable's tolerance instead of hiding it.
#   A multiple instruments or ground truth | B single orbital instrument
#   C model-derived or extrapolated        | D poorly constrained
GRADE_SIGMA = {"A": 1.0, "B": 1.5, "C": 2.5, "D": 4.0}
DEFAULT_GRADE = "C"          # ungraded is not "perfectly known"

# Features that come out of engine/terrain_features.compute(), so one
# "__terrain__" grade in targets.json covers all of them.
TERRAIN_DERIVED = {
    "relief_km", "slope_med_deg", "slope_p90_deg", "hypso_int",
    "flat_frac", "steep_frac",
    "rough_2km", "rough_10km",
    "rough_2km_gM", "rough_10km_gM", "rough_2km_gR", "rough_10km_gR",
}

# A feature counts as "matching" on a card at or above this similarity.
MATCH_FEATURE = 0.6


# ---------------------------------------------------------------------------
# Contract loading
# ---------------------------------------------------------------------------


@dataclass
class FeatureSpec:
    """One row of contract/feature_dictionary.yaml."""

    id: str
    dim: str
    tier: str
    unit: str
    lo: float
    hi: float
    sigma: float
    sigma_mode: str
    sigma_floor: float = 0.0
    gravity_swap: dict = field(default_factory=dict)
    earth_only: bool = False
    scored: bool = True

    @property
    def is_mvp(self) -> bool:
        return self.tier == "mvp"


@dataclass
class Contract:
    features: list[FeatureSpec]
    dimensions: dict[str, dict]
    litho_matrix: np.ndarray  # 1-indexed 6x6, row/col 0 unused
    eps: float = DEFAULT_EPS

    def by_id(self, fid: str) -> FeatureSpec:
        for f in self.features:
            if f.id == fid:
                return f
        raise KeyError(fid)

    def scored_features(self, tiers: Sequence[str] = ("mvp", "stretch")) -> list[FeatureSpec]:
        """Features that take part in scoring, in dictionary order.

        Earth-only gravity-swap columns are excluded: they are read through
        the swap, never scored against a planetary value of their own.
        """
        return [
            f
            for f in self.features
            if f.scored and f.tier in tiers and not f.earth_only
        ]

    def default_weights(self) -> dict[str, float]:
        return {d: float(v.get("default_weight", 1)) for d, v in self.dimensions.items()}


def load_contract(
    contract_dir: Path | str = CONTRACT_DIR,
    eps: float = DEFAULT_EPS,
) -> Contract:
    contract_dir = Path(contract_dir)
    raw = yaml.safe_load((contract_dir / "feature_dictionary.yaml").read_text(encoding="utf-8"))

    features = []
    for row in raw["features"]:
        features.append(
            FeatureSpec(
                id=row["id"],
                dim=row["dim"],
                tier=row.get("tier", "mvp"),
                unit=str(row.get("unit", "")),
                lo=float(row["lo"]),
                hi=float(row["hi"]),
                sigma=float(row.get("sigma", 1.0)),
                sigma_mode=row.get("sigma_mode", "abs"),
                sigma_floor=float(row.get("sigma_floor", 0.0)),
                gravity_swap=dict(row.get("gravity_swap", {}) or {}),
                earth_only=bool(row.get("earth_only", False)),
                scored=bool(row.get("scored", True)),
            )
        )

    litho = yaml.safe_load((contract_dir / "lithology_classes.yaml").read_text(encoding="utf-8"))
    matrix = np.zeros((6, 6), dtype=np.float64)
    for a, row in litho["similarity"].items():
        for b, v in row.items():
            matrix[int(a), int(b)] = float(v)

    return Contract(
        features=features,
        dimensions=raw["dimensions"],
        litho_matrix=matrix,
        eps=eps,
    )


def load_body_constants(contract_dir: Path | str = CONTRACT_DIR) -> dict:
    return json.loads((Path(contract_dir) / "body_constants.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Per-feature similarity
# ---------------------------------------------------------------------------


def feature_similarity(
    x: np.ndarray,
    t: float,
    spec: FeatureSpec,
    litho_matrix: np.ndarray,
    sigma_override: float | None = None,
) -> np.ndarray:
    """Similarity of every cell value ``x`` to the single target value ``t``.

    NaN in ``x`` propagates as NaN, which the caller reads as "missing, drop
    this feature from this cell's dimension average".
    """
    x = np.asarray(x, dtype=np.float64)
    sigma = spec.sigma if sigma_override is None else float(sigma_override)

    if spec.sigma_mode == "matrix":
        out = np.full(x.shape, np.nan, dtype=np.float64)
        ok = np.isfinite(x)
        if not np.isfinite(t):
            return out
        ti = int(round(t))
        xi = np.clip(np.round(x[ok]), 1, 5).astype(np.int64)
        out[ok] = litho_matrix[xi, np.clip(ti, 1, 5)]
        return out

    if spec.sigma_mode == "log":
        xa = np.log10(np.maximum(x, 0.0) + 1.0)
        ta = np.log10(max(t, 0.0) + 1.0)
        s = sigma
    elif spec.sigma_mode == "rel":
        xa, ta = x, t
        s = max(sigma * abs(t), spec.sigma_floor)
    else:  # "abs" and "class" share the Gaussian form; class sigma counts classes
        xa, ta = x, t
        s = sigma

    if not np.isfinite(ta) or s <= 0:
        return np.full(x.shape, np.nan, dtype=np.float64)

    z = (xa - ta) / s
    return np.exp(-0.5 * z * z)


# ---------------------------------------------------------------------------
# Full scoring
# ---------------------------------------------------------------------------


@dataclass
class ScoreResult:
    overall: np.ndarray                 # (n_cells,) final score S, NaN where unscorable
    dims: dict[str, np.ndarray]         # dimension -> (n_cells,) s_d, NaN where no data
    features: dict[str, np.ndarray]     # feature id -> (n_cells,) s_f
    partial: np.ndarray                 # bool, True where any MVP feature was missing
    used_features: list[str]
    weights: dict[str, float]
    eps: float


def score_grid(
    grid: Mapping[str, np.ndarray],
    target: Mapping[str, float],
    contract: Contract,
    weights: Mapping[str, float] | None = None,
    gravity_scaling: bool = False,
    body: str | None = None,
    tiers: Sequence[str] = ("mvp", "stretch"),
    sigma_overrides: Mapping[str, float] | None = None,
) -> ScoreResult:
    """Score every cell of ``grid`` against one target fingerprint.

    grid     mapping feature id -> float array of length n_cells (pandas
             DataFrame works directly). Missing values are NaN.
    target   mapping feature id -> float (the ``features`` block of one entry
             in targets.json).
    body     "moon" or "mars"; only needed when gravity_scaling is on, to pick
             which gravity-scaled Earth column to swap in.
    """
    weights = dict(contract.default_weights() if weights is None else weights)
    sigma_overrides = dict(sigma_overrides or {})

    n = None
    for v in grid.values():
        n = len(np.asarray(v))
        break
    if n is None:
        raise ValueError("empty grid")

    feats = [f for f in contract.scored_features(tiers) if f.id in target]

    dim_num: dict[str, np.ndarray] = {}
    dim_den: dict[str, np.ndarray] = {}
    per_feature: dict[str, np.ndarray] = {}
    missing_mvp = np.zeros(n, dtype=bool)
    used: list[str] = []

    for spec in feats:
        column = spec.id
        if gravity_scaling and spec.gravity_swap and body in spec.gravity_swap:
            swapped = spec.gravity_swap[body]
            if swapped in grid:
                column = swapped
        if column not in grid:
            continue

        t = float(target.get(spec.id, np.nan))
        s = feature_similarity(
            np.asarray(grid[column], dtype=np.float64),
            t,
            spec,
            contract.litho_matrix,
            sigma_overrides.get(spec.id),
        )
        per_feature[spec.id] = s
        used.append(spec.id)

        ok = np.isfinite(s)
        if spec.is_mvp:
            missing_mvp |= ~ok

        d = spec.dim
        if d not in dim_num:
            dim_num[d] = np.zeros(n, dtype=np.float64)
            dim_den[d] = np.zeros(n, dtype=np.float64)
        w = 1.0  # equal feature weights inside a dimension, by contract
        dim_num[d] += np.where(ok, s * w, 0.0)
        dim_den[d] += np.where(ok, w, 0.0)

    dims: dict[str, np.ndarray] = {}
    for d in DIM_ORDER:
        if d not in dim_num:
            continue
        with np.errstate(invalid="ignore", divide="ignore"):
            sd = np.where(dim_den[d] > 0, dim_num[d] / np.maximum(dim_den[d], 1e-12), np.nan)
        dims[d] = sd

    eps = contract.eps
    log_sum = np.zeros(n, dtype=np.float64)
    w_sum = np.zeros(n, dtype=np.float64)
    norm = np.log(1.0 + eps)
    for d, sd in dims.items():
        wd = float(weights.get(d, 0.0))
        if wd <= 0:
            continue
        ok = np.isfinite(sd)
        contrib = np.log(np.where(ok, sd, 1.0) + eps) - norm
        log_sum += np.where(ok, wd * contrib, 0.0)
        w_sum += np.where(ok, wd, 0.0)

    with np.errstate(invalid="ignore", divide="ignore"):
        overall = np.where(w_sum > 0, np.exp(log_sum / np.maximum(w_sum, 1e-12)), np.nan)

    return ScoreResult(
        overall=overall,
        dims=dims,
        features=per_feature,
        partial=missing_mvp,
        used_features=used,
        weights=weights,
        eps=eps,
    )


# ---------------------------------------------------------------------------
# Hotspots: greedy non-maximum suppression on the sphere
# ---------------------------------------------------------------------------

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2, radius_km: float = EARTH_RADIUS_KM):
    """Great-circle distance. Scalars or arrays, degrees in, km out."""
    p1 = np.radians(np.asarray(lat1, dtype=np.float64))
    p2 = np.radians(np.asarray(lat2, dtype=np.float64))
    dp = p2 - p1
    dl = np.radians(np.asarray(lon2, dtype=np.float64) - np.asarray(lon1, dtype=np.float64))
    a = np.sin(dp / 2.0) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2.0) ** 2
    return 2.0 * radius_km * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def top_hotspots(
    scores: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    k: int = 20,
    min_sep_km: float = 200.0,
    mask: np.ndarray | None = None,
    candidate_pool: int = 20000,
) -> list[int]:
    """Indices of the ``k`` best cells, no two within ``min_sep_km``.

    Greedy NMS over the best ``candidate_pool`` cells - sorting 300k cells and
    walking the top 20k is plenty and keeps the worker under a frame budget.
    """
    s = np.asarray(scores, dtype=np.float64).copy()
    if mask is not None:
        s = np.where(mask, s, np.nan)
    valid = np.flatnonzero(np.isfinite(s))
    if valid.size == 0:
        return []
    order = valid[np.argsort(-s[valid])][:candidate_pool]

    chosen: list[int] = []
    clat: list[float] = []
    clon: list[float] = []
    for idx in order:
        if chosen:
            d = haversine_km(lat[idx], lon[idx], np.array(clat), np.array(clon))
            if np.min(d) < min_sep_km:
                continue
        chosen.append(int(idx))
        clat.append(float(lat[idx]))
        clon.append(float(lon[idx]))
        if len(chosen) >= k:
            break
    return chosen


# ---------------------------------------------------------------------------
# Site-card helpers
# ---------------------------------------------------------------------------

STRONG, PARTIAL = 0.7, 0.4


def classify_dimension(s_d: float) -> str:
    """strong / partial / breaks - thresholds from Section 6 of the plan."""
    if not np.isfinite(s_d):
        return "nodata"
    if s_d >= STRONG:
        return "strong"
    if s_d >= PARTIAL:
        return "partial"
    return "breaks"


def site_card(result: ScoreResult, index: int) -> dict:
    """Everything the UI needs for one Earth cell, as plain JSON types."""
    dims = {d: float(v[index]) for d, v in result.dims.items()}
    return {
        "overall": float(result.overall[index]),
        "dims": dims,
        "verdict": {d: classify_dimension(v) for d, v in dims.items()},
        "features": {f: float(v[index]) for f, v in result.features.items()},
        "partial": bool(result.partial[index]),
    }


def load_transfer_rules(contract_dir: Path | str = CONTRACT_DIR) -> dict:
    """contract/transfer_rules.yaml, or an empty ruleset if it is not there yet.

    Missing file or missing row is never read as "transferable" - it is
    reported as unassessed, which lands in the Conditional column.
    """
    path = Path(contract_dir) / "transfer_rules.yaml"
    if not path.exists():
        return {"rules": {}, "never_testable": [], "feature_labels": {}}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def grade_sigma_overrides(contract: Contract, target: Mapping) -> dict[str, float]:
    """Per-feature sigma, widened by the target's evidence grade.

    targets.json carries {"grades": {"__terrain__": "B", "ti_class": "B", ...}}.
    "__terrain__" applies to every feature in TERRAIN_DERIVED.
    """
    grades = dict(target.get("grades", {}) or {})
    terrain_grade = grades.pop("__terrain__", None)
    out: dict[str, float] = {}
    for spec in contract.features:
        if spec.sigma_mode == "matrix":
            continue  # no sigma to widen
        g = grades.get(spec.id)
        if g is None and terrain_grade and spec.id in TERRAIN_DERIVED:
            g = terrain_grade
        if g is None:
            continue
        out[spec.id] = spec.sigma * GRADE_SIGMA.get(str(g).upper(), GRADE_SIGMA[DEFAULT_GRADE])
    return out


def feature_grade(target: Mapping, feature_id: str) -> str:
    grades = target.get("grades", {}) or {}
    if feature_id in grades:
        return str(grades[feature_id]).upper()
    if feature_id in TERRAIN_DERIVED and "__terrain__" in grades:
        return str(grades["__terrain__"]).upper()
    return DEFAULT_GRADE


def proxy_card(
    result: ScoreResult,
    index: int,
    target: Mapping,
    transfer: Mapping,
    contract: Contract,
) -> dict:
    """The card the UI renders: Supports / Conditional / Cannot test.

    A variable reaches **Supports** only if it both matches and transfers.
    Matching numbers on a non-transferable variable are not evidence, so they
    go to Cannot test - that is the whole point of the reframe.
    """
    body = str(target.get("body", "")).lower()
    rules = (transfer or {}).get("rules", {}) or {}
    labels = (transfer or {}).get("feature_labels", {}) or {}
    spec_of = {f.id: f for f in contract.features}

    supports, conditional, cannot, unmatched = [], [], [], []

    for fid, arr in result.features.items():
        s_f = float(arr[index])
        spec = spec_of.get(fid)
        row = {
            "id": fid,
            "label": labels.get(fid, fid),
            "dim": spec.dim if spec else None,
            "score": None if not np.isfinite(s_f) else round(s_f, 3),
            "grade": feature_grade(target, fid),
        }
        rule = (rules.get(fid) or {}).get(body) or {}
        status = rule.get("status", "unassessed")

        if status == "not_transferable":
            row["reason"] = rule.get("note", "Physics does not carry over to this body.")
            cannot.append(row)
            continue
        if not np.isfinite(s_f) or s_f < MATCH_FEATURE:
            row["reason"] = "measured, does not match this target"
            unmatched.append(row)
            continue
        if status == "transferable":
            if rule.get("note"):
                row["note"] = rule["note"]
            supports.append(row)
        else:
            row["correction"] = rule.get(
                "correction", "Transfer not yet assessed - treat as conditional."
            )
            conditional.append(row)

    for nt in (transfer or {}).get("never_testable", []) or []:
        if body in nt:
            cannot.append({
                "id": nt["id"],
                "label": nt.get("label", nt["id"]),
                "score": None,
                "grade": None,
                "reason": nt[body],
                "never_testable": True,
            })

    key = lambda r: -(r["score"] or 0)
    return {
        "supports": sorted(supports, key=key),
        "conditional": sorted(conditional, key=key),
        "cannot_test": cannot,
        "not_matched": sorted(unmatched, key=key),
        "proxy_strength": float(result.overall[index]),
        "partial": bool(result.partial[index]),
    }


if __name__ == "__main__":
    c = load_contract()
    print(f"contract v1: {len(c.features)} features, "
          f"{len(c.scored_features(('mvp',)))} scored at MVP tier")
    print("dimensions:", ", ".join(f"{k}={v['name']}" for k, v in c.dimensions.items()))
