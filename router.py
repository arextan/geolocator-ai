import math
import time

from geopy.geocoders import Nominatim

from config import NOMINATIM_RATE_LIMIT_SECONDS, NOMINATIM_USER_AGENT

_SANITY_MAX_KM = 150  # reject geocode result if it's further than this from Claude's guess


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlng / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

# Maps detected language names → plausible ISO 3166-1 alpha-2 country codes.
# Used to reject geocode results that conflict with the detected language
# (e.g. "Springfield" geocoded to USA when language is Thai).
# Languages absent from this map impose no country constraint.
_LANGUAGE_COUNTRIES: dict[str, set[str]] = {
    "portuguese":   {"BR", "PT", "AO", "MZ", "CV", "GW", "ST", "TL"},
    "spanish":      {"ES", "MX", "AR", "CL", "CO", "PE", "VE", "EC", "BO",
                     "PY", "UY", "CR", "PA", "GT", "HN", "SV", "NI", "DO", "CU", "PR"},
    "french":       {"FR", "BE", "CH", "CA", "LU", "MC", "SN", "CI", "CM",
                     "CD", "MG", "BF", "NE", "ML", "TG", "BJ", "GN", "GA",
                     "CG", "TN", "MA", "DZ", "HT", "RE", "MU"},
    "german":       {"DE", "AT", "CH", "LI", "LU", "BE"},
    "dutch":        {"NL", "BE", "SR"},
    "italian":      {"IT", "CH", "SM", "VA"},
    "russian":      {"RU", "KZ", "BY", "KG", "TJ"},
    "ukrainian":    {"UA"},
    "polish":       {"PL"},
    "romanian":     {"RO", "MD"},
    "czech":        {"CZ"},
    "slovak":       {"SK"},
    "hungarian":    {"HU"},
    "bulgarian":    {"BG"},
    "serbian":      {"RS", "BA", "ME"},
    "croatian":     {"HR", "BA"},
    "slovenian":    {"SI"},
    "macedonian":   {"MK"},
    "albanian":     {"AL", "XK", "MK"},
    "greek":        {"GR", "CY"},
    "latvian":      {"LV"},
    "lithuanian":   {"LT"},
    "estonian":     {"EE"},
    "swedish":      {"SE", "FI"},
    "norwegian":    {"NO"},
    "danish":       {"DK"},
    "finnish":      {"FI"},
    "turkish":      {"TR", "CY"},
    "georgian":     {"GE"},
    "armenian":     {"AM"},
    "azerbaijani":  {"AZ"},
    "hebrew":       {"IL"},
    "arabic":       {"SA", "EG", "IQ", "SY", "JO", "LB", "YE", "OM", "AE",
                     "QA", "BH", "KW", "LY", "TN", "DZ", "MA", "MR", "SD", "SO"},
    "farsi":        {"IR", "AF"},
    "urdu":         {"PK", "IN"},
    "hindi":        {"IN"},
    "bengali":      {"BD", "IN"},
    "nepali":       {"NP", "IN"},
    "sinhala":      {"LK"},
    "thai":         {"TH"},
    "vietnamese":   {"VN"},
    "khmer":        {"KH"},
    "lao":          {"LA"},
    "burmese":      {"MM"},
    "indonesian":   {"ID"},
    "malay":        {"MY", "BN", "SG"},
    "tagalog":      {"PH"},
    "japanese":     {"JP"},
    "korean":       {"KR", "KP"},
    "chinese":      {"CN", "TW", "SG", "HK", "MO"},
    "mongolian":    {"MN"},
    "kazakh":       {"KZ"},
    "swahili":      {"TZ", "KE", "UG"},
    "amharic":      {"ET"},
    "catalan":      {"ES", "AD", "FR"},
}

_geocoder = Nominatim(user_agent=NOMINATIM_USER_AGENT)


def _language_matches_country(language: str | None, country_code: str | None) -> bool:
    """Return True if country_code is plausible for language.

    Returns True when language or country is unknown, or when language has no
    entry in _LANGUAGE_COUNTRIES (no constraint imposed).
    """
    if not language or not country_code:
        return True
    expected = _LANGUAGE_COUNTRIES.get(language.lower())
    if expected is None:
        return True
    return country_code.upper() in expected


def route(features: dict) -> dict | None:
    """Decide geocode path vs Bayesian path.

    Geocode path conditions (all must hold):
      - pass_1.place_name is not None
      - pass_1.language_confidence > 0.8
      - Nominatim returns a result
      - Geocoded country is consistent with detected language

    Returns a dict on success:
        {"lat": float, "lng": float, "place_name": str,
         "country_code": str, "path": "geocode"}

    Returns None to signal Bayesian path. Never raises.
    """
    try:
        p1 = features.get("pass_1", {})
        place_name: str | None = p1.get("place_name")
        language: str | None = p1.get("language")
        language_confidence: float = p1.get("language_confidence") or 0.0

        if not place_name:
            return None

        if language_confidence <= 0.8:
            print(f"[router] skipping geocode — language_confidence {language_confidence:.2f} ≤ 0.8")
            return None

        # Respect Nominatim 1 req/sec rate limit
        time.sleep(NOMINATIM_RATE_LIMIT_SECONDS)

        location = _geocoder.geocode(place_name, addressdetails=True, timeout=10)
        if location is None:
            print(f"[router] no geocode result for '{place_name}'")
            return None

        address = location.raw.get("address", {})
        country_code: str = address.get("country_code", "").upper()

        if not _language_matches_country(language, country_code):
            print(
                f"[router] rejected '{place_name}' → {country_code} "
                f"(conflicts with language '{language}')"
            )
            return None

        # Sanity check 1 — distance from Claude's own location guess
        lg = features.get("location_guess", {}) or {}
        claude_lat: float | None = lg.get("lat")
        claude_lng: float | None = lg.get("lng")

        if claude_lat is not None and claude_lng is not None:
            dist_km = _haversine(location.latitude, location.longitude, claude_lat, claude_lng)
            if dist_km > _SANITY_MAX_KM:
                print(
                    f"[router] rejected '{place_name}' → {location.latitude:.4f}, "
                    f"{location.longitude:.4f} — {dist_km:.0f} km from Claude's guess "
                    f"(>{_SANITY_MAX_KM} km threshold)"
                )
                return None

            # Sanity check 2 — geocoded country vs Claude's guessed country
            geocoded_country = (
                location.raw.get("address", {}).get("country", "").strip().lower()
            )
            claude_country = (lg.get("country") or "").strip().lower()
            if geocoded_country and claude_country and geocoded_country != claude_country:
                print(
                    f"[router] rejected '{place_name}' — geocoded country '{geocoded_country}' "
                    f"!= Claude's guessed country '{claude_country}'"
                )
                return None

        print(
            f"[router] geocode path: '{place_name}' → "
            f"{location.latitude:.4f}, {location.longitude:.4f} ({country_code})"
        )
        return {
            "lat": location.latitude,
            "lng": location.longitude,
            "place_name": place_name,
            "country_code": country_code,
            "path": "geocode",
        }

    except Exception as exc:
        print(f"[router] error: {exc}")
        return None
