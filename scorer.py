"""
Bayesian scorer — phase 1 step 5.

Takes the extracted features dict from extractor.py and returns the top
region prediction with confidence score, tier, and hedge coords.

Pipeline:
1. Collect non-null observed features from pass_1 + pass_2
2. Apply language confidence gate (drop language if confidence < 0.7)
3. Compute log-posterior = log(prior) + sum(log(likelihood)) for each region
4. Softmax-normalise to probabilities
5. Assign confidence tier via thresholds from config.py
6. For low-tier rounds, return biome-aware hedge centroid instead of region centroid
"""

import math

from config import HIGH_CONFIDENCE_THRESHOLD, MEDIUM_CONFIDENCE_THRESHOLD
from feature_region_map import (
    BIOME_HEDGE_CENTROIDS,
    DEFAULT_LIKELIHOOD,
    FEATURE_REGION_MAP,
)

# Features extracted by Claude that carry geographic signal.
# Listed explicitly so new extraction fields don't silently enter scoring.
_SCORED_FEATURES: frozenset[str] = frozenset({
    "script",
    "language",
    "plate_format",
    "driving_side",
    "road_markings",
    "biome",
    "vegetation_specific",
    "terrain",
    "soil_color",
    "architecture",
    "pole_type",
    "infrastructure_quality",
})

# Features to always skip (list types, meta fields, or too noisy to score).
_SKIP_FEATURES: frozenset[str] = frozenset({
    "readable_text",
    "language_confidence",
    "place_name",
    "route_number",
    "currency_symbol",
    "sky_condition",
    "speed_sign_format",
    "domain_extension",
    "road_surface",
})

# Minimum language_confidence to include language as a scored feature.
_LANGUAGE_CONFIDENCE_MIN: float = 0.70


def _collect_observed(features: dict) -> dict[str, str]:
    """Flatten pass_1/pass_2 into {feature: normalised_value} for scoring.

    - Skips null and empty-list values.
    - Drops language when language_confidence < _LANGUAGE_CONFIDENCE_MIN.
    - Normalises values to lowercase stripped strings.
    """
    p1 = features.get("pass_1", {})
    p2 = features.get("pass_2", {})
    lang_conf: float = float(p1.get("language_confidence") or 0.0)

    observed: dict[str, str] = {}
    for pass_dict in (p1, p2):
        for feature, value in pass_dict.items():
            if feature in _SKIP_FEATURES:
                continue
            if feature not in _SCORED_FEATURES:
                continue
            if value is None or value == []:
                continue
            if feature == "language" and lang_conf < _LANGUAGE_CONFIDENCE_MIN:
                continue
            observed[feature] = str(value).lower().strip()

    return observed


def _bayesian_log_scores(observed: dict[str, str]) -> dict[str, float]:
    """Return log-posterior score for each region.

    log P(region | evidence) ∝ log P(region) + Σ log P(feature_value | region)

    Unrecognised feature values receive DEFAULT_LIKELIHOOD (not zero) so a
    single unusual observation cannot zero-out a region entirely.
    """
    scores: dict[str, float] = {}
    for region, data in FEATURE_REGION_MAP.items():
        log_score = math.log(data["prior"])
        feature_map = data["features"]
        for feature, value in observed.items():
            if feature in feature_map:
                likelihood = feature_map[feature].get(value, DEFAULT_LIKELIHOOD)
            else:
                likelihood = DEFAULT_LIKELIHOOD
            log_score += math.log(max(likelihood, 1e-9))
        scores[region] = log_score
    return scores


def _softmax(log_scores: dict[str, float]) -> dict[str, float]:
    """Convert log-scores to probabilities via numerically stable softmax."""
    max_val = max(log_scores.values())
    exp_scores = {r: math.exp(s - max_val) for r, s in log_scores.items()}
    total = sum(exp_scores.values())
    return {r: v / total for r, v in exp_scores.items()}


def _tier(top_prob: float) -> str:
    if top_prob >= HIGH_CONFIDENCE_THRESHOLD:
        return "high"
    if top_prob >= MEDIUM_CONFIDENCE_THRESHOLD:
        return "medium"
    return "low"


def _hedge_coords(features: dict) -> tuple[float, float]:
    """Return biome-aware hedge centroid for low-confidence rounds."""
    raw_biome = features.get("pass_2", {}).get("biome")
    biome: str | None = raw_biome.lower().strip() if raw_biome else None
    return BIOME_HEDGE_CENTROIDS.get(biome) or BIOME_HEDGE_CENTROIDS[None]


def score(features: dict) -> dict:
    """Run Bayesian scoring on extracted features.

    Args:
        features: dict from extractor.extract() with pass_1 and pass_2 keys.

    Returns:
        region:           top predicted region name (str)
        score:            posterior probability of top region (0.0–1.0)
        confidence_tier:  "high" | "medium" | "low"
        top_regions:      list of up to 5 dicts {"region": str, "score": float},
                          sorted by score descending
        features_used:    list of feature names that contributed to scoring
        hedge_lat:        hedge centroid latitude  (float if tier=="low", else None)
        hedge_lng:        hedge centroid longitude (float if tier=="low", else None)
    """
    observed = _collect_observed(features)
    log_scores = _bayesian_log_scores(observed)
    probs = _softmax(log_scores)

    sorted_regions = sorted(probs.items(), key=lambda x: x[1], reverse=True)
    top_region, top_prob = sorted_regions[0]
    confidence_tier = _tier(top_prob)

    hedge_lat: float | None = None
    hedge_lng: float | None = None
    if confidence_tier == "low":
        hedge_lat, hedge_lng = _hedge_coords(features)

    return {
        "region": top_region,
        "score": round(top_prob, 4),
        "confidence_tier": confidence_tier,
        "top_regions": [
            {"region": r, "score": round(s, 4)}
            for r, s in sorted_regions[:5]
        ],
        "features_used": list(observed.keys()),
        "hedge_lat": hedge_lat,
        "hedge_lng": hedge_lng,
    }
