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
from .feature_region_map import (
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

# ---------------------------------------------------------------------------
# Feature normalization
#
# Claude returns free-text descriptions; feature_region_map.py expects fixed
# categorical keys.  Each entry below is (substring_pattern, canonical_value).
# Patterns are matched in order against the lowercased Claude output; the
# first match wins.  Returns None when nothing matches (→ DEFAULT_LIKELIHOOD).
# ---------------------------------------------------------------------------

_NORM_RULES: dict[str, list[tuple[str, str]]] = {
    "architecture": [
        ("soviet",             "soviet_bloc"),
        ("brutalist",          "soviet_bloc"),
        ("prefab",             "soviet_bloc"),
        ("colonial_british",   "colonial_british"),
        ("colonial british",   "colonial_british"),
        ("colonial_portuguese","colonial_portuguese"),
        ("colonial portuguese","colonial_portuguese"),
        ("colonial_spanish",   "colonial_spanish"),
        ("colonial spanish",   "colonial_spanish"),
        ("modern glass",       "modern_glass"),
        ("glass curtain",      "modern_glass"),
        ("mud brick",          "mud_brick"),
        ("adobe",              "mud_brick"),
        ("mud wall",           "mud_brick"),
        ("terracotta",         "terracotta_tiles"),
        ("white cube",         "white_cube"),
        ("white render",       "white_cube"),
        # Wooden must come before corrugated — a building can be "wooden with corrugated roof"
        ("timber",             "traditional_wooden"),
        ("wooden",             "traditional_wooden"),
        ("wood frame",         "traditional_wooden"),
        ("log cabin",          "traditional_wooden"),
        ("corrugated metal",   "corrugated_metal"),
        ("corrugated",         "corrugated_metal"),
        ("colonial",           "colonial_british"),   # generic colonial fallback
    ],
    "road_markings": [
        ("nordic",            "nordic_dashed"),
        ("yellow edge",       "yellow_edge_white_center"),
        ("yellow curb",       "yellow_curb"),
        ("yellow center",     "yellow_center"),
        ("yellow",            "yellow_center"),
        ("white center",      "white_center"),
        ("white dashed",      "white_center"),
        ("white",             "white_center"),
    ],
    "pole_type": [
        ("h-frame",           "wooden_h_frame"),
        ("h frame",           "wooden_h_frame"),
        # concrete curved must come before bundled — a pole can be "concrete curved with bundled wires"
        ("concrete curved",   "concrete_curved"),
        ("concrete",          "concrete_curved"),
        ("metal lattice",     "metal_lattice"),
        ("lattice",           "metal_lattice"),
        ("bundled",           "bundled_overhead"),
    ],
    "vegetation_specific": [
        ("eucalyptus",        "eucalyptus"),
        ("palm",              "palm"),
        ("birch",             "birch"),
        ("pine",              "evergreen"),
        ("spruce",            "evergreen"),
        ("fir",               "evergreen"),
        ("conifer",           "evergreen"),
        ("evergreen",         "evergreen"),
    ],
    "biome": [
        ("temperate deciduous","temperate_deciduous"),
        ("temperate",         "temperate_deciduous"),
        ("tropical rainforest","tropical_rainforest"),
        ("tropical rain",     "tropical_rainforest"),
        ("tropical savanna",  "savanna"),
        ("tropical dry",      "savanna"),
        ("tropical",          "tropical_rainforest"),
        ("savanna",           "savanna"),
        ("cerrado",           "savanna"),
        ("mediterranean",     "mediterranean"),
        ("desert",            "desert"),
        ("semi-arid",         "desert"),
        ("steppe",            "desert"),
        ("boreal",            "boreal"),
        ("taiga",             "boreal"),
        ("tundra",            "tundra"),
        ("alpine",            "alpine"),
        ("subtropical",       "subtropical_coastal"),
    ],
    "soil_color": [
        ("red laterite",      "red_laterite"),
        ("red-brown laterite","red_laterite"),
        ("red-orange",        "red_laterite"),
        ("red",               "red_laterite"),
        ("black",             "black_chernozem"),
        ("dark brown/black",  "black_chernozem"),
        ("rocky",             "rocky_grey"),
        ("grey",              "rocky_grey"),
        ("gray",              "rocky_grey"),
        ("sandy",             "sandy_pale"),
        ("tan",               "sandy_pale"),
        ("pale",              "sandy_pale"),
    ],
}


def _normalize_value(feature: str, raw_value: str) -> str:
    """Map a free-text Claude output to the nearest categorical key.

    Returns the canonical value if a keyword matches, or the original
    value unchanged (so exact matches in feature_region_map still work).
    """
    if feature not in _NORM_RULES:
        return raw_value
    lower = raw_value.lower()
    for pattern, canonical in _NORM_RULES[feature]:
        if pattern in lower:
            return canonical
    return raw_value  # no match — original value passed through to lookup


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
            normalised = _normalize_value(feature, str(value).lower().strip())
            observed[feature] = normalised

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
