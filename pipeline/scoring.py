import math
from config import GEOGUESSR_DECAY_KM, GEOGUESSR_MAX_SCORE

_EARTH_RADIUS_KM = 6371.0


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return great-circle distance in km between two lat/lng points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def geoguessr_score(distance_km: float) -> int:
    """Convert distance to GeoGuessr points (0–5000).

    Formula: 5000 * exp(-distance_km / 1492.7)
    Decay constant validated against known GeoGuessr scores.
    """
    return round(GEOGUESSR_MAX_SCORE * math.exp(-distance_km / GEOGUESSR_DECAY_KM))
