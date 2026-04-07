"""
geo.py — coordinate resolution (post-pivot).

Priority order:
1. geocode   — router found a geocodable place name
2. claude    — Claude's location_guess lat/lng from extractor
3. fallback  — (20.0, 20.0)

Never raises.
"""

_GLOBAL_FALLBACK = (20.0, 20.0)


def resolve(
    features: dict,
    router_result: dict | None = None,
) -> dict:
    """Return final coordinates for the round.

    Args:
        features:      parsed output from extractor.extract() — must contain
                       a 'location_guess' key.
        router_result: dict from router.route(), or None if no place name found.

    Returns dict with keys: lat, lng, source, region.
    """
    try:
        # ------------------------------------------------------------------
        # Path 1 — geocoded place name from router (highest precision)
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
        # Path 2 — Claude's direct location guess
        # ------------------------------------------------------------------
        guess = features.get("location_guess", {}) or {}
        lat = guess.get("lat")
        lng = guess.get("lng")
        if lat is not None and lng is not None:
            city = guess.get("city") or "unknown"
            country = guess.get("country") or ""
            label = f"{city}, {country}" if country else city
            return {
                "lat": float(lat),
                "lng": float(lng),
                "source": "claude",
                "region": label,
            }

    except Exception as exc:
        print(f"[geo] error: {exc}")

    # ------------------------------------------------------------------
    # Fallback — should rarely be reached
    # ------------------------------------------------------------------
    print("[geo] using global fallback (20.0, 20.0)")
    return {
        "lat": _GLOBAL_FALLBACK[0],
        "lng": _GLOBAL_FALLBACK[1],
        "source": "fallback",
        "region": "unknown",
    }
