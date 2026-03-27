"""
refiner.py — city-level location narrowing via a second Claude call.

After the Bayesian scorer identifies a region with medium or high confidence,
the refiner sends the extracted features to Claude Sonnet and asks it to
narrow down to a specific city or area within that region.  The result is
geocoded via Nominatim for precise coordinates.

This is the step that closes the gap between the pipeline's centroid-level
accuracy (~1,000–2,000 pts) and what a human analyst would score by reasoning
about city-specific cues (~4,000+ pts).

Integration:
    evaluate.py  — pass --refine flag
    main.py      — pass --refine flag

Never raises; returns None on any failure so callers fall back gracefully.
"""

import time

from geopy.geocoders import Nominatim

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    NOMINATIM_RATE_LIMIT_SECONDS,
    NOMINATIM_USER_AGENT,
)

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
_geocoder = Nominatim(user_agent=NOMINATIM_USER_AGENT)

# ---------------------------------------------------------------------------
# Region → natural-language description for the prompt
# ---------------------------------------------------------------------------

_REGION_DESCRIPTIONS: dict[str, str] = {
    "japan":                 "Japan",
    "south_korea":           "South Korea",
    "china":                 "China",
    "thailand":              "Thailand",
    "southeast_asia":        "Southeast Asia (Indonesia, Malaysia, Vietnam, Philippines, Cambodia, Myanmar, Laos)",
    "india_subcontinent":    "the Indian subcontinent (India, Pakistan, Bangladesh, Sri Lanka, Nepal)",
    "middle_east":           "the Middle East (Saudi Arabia, UAE, Jordan, Iraq, Syria, Lebanon, Yemen, Oman, Kuwait)",
    "north_africa":          "North Africa (Morocco, Algeria, Tunisia, Libya, Egypt)",
    "sub_saharan_africa":    "sub-Saharan Africa",
    "south_africa":          "South Africa",
    "russia_central_asia":   "Russia or Central Asia (Kazakhstan, Kyrgyzstan, Uzbekistan, Tajikistan)",
    "eastern_europe":        "Eastern Europe (Poland, Czech Republic, Slovakia, Hungary, Romania, Ukraine, Bulgaria, Serbia, Croatia)",
    "western_europe":        "Western Europe (France, Germany, Spain, Italy, UK, Netherlands, Belgium, Portugal, Switzerland, Austria)",
    "nordic":                "the Nordic region (Sweden, Norway, Denmark, Finland, Iceland)",
    "brazil":                "Brazil",
    "latin_america":         "Latin America (Mexico, Colombia, Argentina, Chile, Peru, and other South/Central American countries)",
    "usa_canada":            "the United States or Canada",
    "australia_new_zealand": "Australia or New Zealand",
}

_REFINE_PROMPT_TEMPLATE = """\
You are an expert geolocation analyst. Based on the geographic features extracted \
from a Street View image, your task is to identify the most likely specific city or \
area within {region_description}.

## Extracted features

{features_text}

## Your task

Name the single most likely city, town, or specific area within {region_description} \
where this image was taken. Base your answer on the combination of features — \
language, script, architecture, vegetation, infrastructure, road markings, and any \
visible text.

Rules:
- Respond with ONLY a JSON object, no explanation
- city_name must be a real, geocodable place name (city, town, or district)
- country must be the country name in English
- reasoning must be one concise sentence (max 20 words)
- confidence is your 0.0–1.0 certainty that this specific city is correct
- If you cannot narrow below country level, set city_name to the country capital

{{"city_name": "...", "country": "...", "reasoning": "...", "confidence": 0.0}}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _features_to_text(features: dict) -> str:
    """Render extracted features as a readable text block for the prompt."""
    p1 = features.get("pass_1", {})
    p2 = features.get("pass_2", {})
    lines = []
    for key, val in {**p1, **p2}.items():
        if val is None or val == [] or key in ("readable_text",):
            continue
        lines.append(f"- {key}: {val}")
    return "\n".join(lines) if lines else "(no features extracted)"


def _parse_refine_response(raw: str) -> dict | None:
    """Extract JSON from Claude's refiner response."""
    import json, re
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        obj = re.search(r"\{.*\}", text, re.DOTALL)
        if obj:
            text = obj.group(0)
    try:
        return json.loads(text)
    except Exception:
        return None


def _geocode_city(city_name: str, country: str) -> tuple[float, float] | None:
    """Geocode '{city_name}, {country}' via Nominatim. Returns (lat, lng) or None."""
    query = f"{city_name}, {country}"
    try:
        time.sleep(NOMINATIM_RATE_LIMIT_SECONDS)
        location = _geocoder.geocode(query, timeout=10)
        if location is None:
            # Retry with country alone as fallback
            time.sleep(NOMINATIM_RATE_LIMIT_SECONDS)
            location = _geocoder.geocode(country, timeout=10)
        if location:
            return float(location.latitude), float(location.longitude)
    except Exception as exc:
        print(f"[refiner] geocode error for '{query}': {exc}")
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def refine(
    features: dict,
    scorer_result: dict,
) -> dict | None:
    """Narrow a medium/high-confidence region prediction to city-level coordinates.

    Args:
        features:      dict from extractor.extract() with pass_1 and pass_2 keys.
        scorer_result: dict from scorer.score() — must contain region and
                       confidence_tier.

    Returns a dict on success:
        {"lat": float, "lng": float, "city_name": str, "country": str,
         "reasoning": str, "confidence": float, "source": "refine"}

    Returns None when:
        - confidence_tier is "low" (not worth refining)
        - Claude fails to return a parseable city name
        - Nominatim cannot geocode the result
    """
    tier = scorer_result.get("confidence_tier", "low")
    if tier == "low":
        return None

    region = scorer_result.get("region", "")
    region_desc = _REGION_DESCRIPTIONS.get(region, region.replace("_", " ").title())
    features_text = _features_to_text(features)

    prompt = _REFINE_PROMPT_TEMPLATE.format(
        region_description=region_desc,
        features_text=features_text,
    )

    try:
        message = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text
        parsed = _parse_refine_response(raw)
    except Exception as exc:
        print(f"[refiner] Claude error: {exc}")
        return None

    if not parsed:
        print("[refiner] could not parse response")
        return None

    city_name = parsed.get("city_name", "").strip()
    country   = parsed.get("country", "").strip()
    reasoning = parsed.get("reasoning", "")
    confidence = float(parsed.get("confidence", 0.0))

    if not city_name or not country:
        print("[refiner] missing city_name or country in response")
        return None

    print(f"[refiner] '{city_name}, {country}' — {reasoning} (conf={confidence:.2f})")

    coords = _geocode_city(city_name, country)
    if coords is None:
        print(f"[refiner] geocode failed for '{city_name}, {country}'")
        return None

    return {
        "lat":        coords[0],
        "lng":        coords[1],
        "city_name":  city_name,
        "country":    country,
        "reasoning":  reasoning,
        "confidence": confidence,
        "source":     "refine",
    }
