"""
geo.py — phase 1 step 6.

Converts scorer output (and optional router geocode result) into final
lat/lng coordinates. Three resolution paths, tried in order:

1. geocode   — router found a place name and geocoded it directly
2. region_centroid — scorer confidence is high/medium; use the region's
                     static centroid from feature_region_map.py
3. hedge     — scorer confidence is low; use the biome-aware hedge
               centroid already computed by scorer.py

Falls back to (20.0, 20.0) if all else fails. Never raises.

Note: static centroids in feature_region_map.py will be replaced by
properly computed coverage-weighted centroids (centroids.json) in phase 2.
"""

from feature_region_map import FEATURE_REGION_MAP

_GLOBAL_FALLBACK = (20.0, 20.0)


def resolve(
    scorer_result: dict,
    router_result: dict | None = None,
) -> dict:
    """Return final coordinates for the round.

    Args:
        scorer_result: dict from scorer.score() — must contain at least
                       region, confidence_tier, hedge_lat, hedge_lng.
        router_result: dict from router.route(), or None if Bayesian path.

    Returns:
        lat:    float
        lng:    float
        source: "geocode" | "region_centroid" | "hedge" | "fallback"
        region: region name from scorer (str), or place_name if geocoded
    """
    try:
        # ------------------------------------------------------------------
        # Path 1 — geocoded place name from router
        # ------------------------------------------------------------------
        if router_result is not None:
            lat = router_result.get("lat")
            lng = router_result.get("lng")
            if lat is not None and lng is not None:
                return {
                    "lat": float(lat),
                    "lng": float(lng),
                    "source": "geocode",
                    "region": router_result.get("place_name", "unknown"),
                }

        # ------------------------------------------------------------------
        # Path 2 — high / medium confidence → region centroid
        # ------------------------------------------------------------------
        tier = scorer_result.get("confidence_tier", "low")
        region = scorer_result.get("region")

        if tier in ("high", "medium") and region in FEATURE_REGION_MAP:
            region_data = FEATURE_REGION_MAP[region]
            return {
                "lat": float(region_data["lat"]),
                "lng": float(region_data["lng"]),
                "source": "region_centroid",
                "region": region,
            }

        # ------------------------------------------------------------------
        # Path 3 — low confidence → biome-aware hedge centroid
        # ------------------------------------------------------------------
        hedge_lat = scorer_result.get("hedge_lat")
        hedge_lng = scorer_result.get("hedge_lng")

        if hedge_lat is not None and hedge_lng is not None:
            return {
                "lat": float(hedge_lat),
                "lng": float(hedge_lng),
                "source": "hedge",
                "region": region or "unknown",
            }

    except Exception as exc:
        print(f"[geo] error: {exc}")

    # ------------------------------------------------------------------
    # Fallback — should never be reached in normal operation
    # ------------------------------------------------------------------
    print("[geo] using global fallback centroid (20.0, 20.0)")
    return {
        "lat": _GLOBAL_FALLBACK[0],
        "lng": _GLOBAL_FALLBACK[1],
        "source": "fallback",
        "region": "unknown",
    }
