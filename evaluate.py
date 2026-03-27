"""Single-image evaluation CLI.

Usage:
    python evaluate.py <image_path>
    python evaluate.py <image_path> --actual <lat> <lng>

Examples:
    python evaluate.py data/images/test.png
    python evaluate.py data/images/test.png --actual 21.03 105.85
"""

import argparse


def _print_extraction(features: dict) -> None:
    p1 = features.get("pass_1", {})
    p2 = features.get("pass_2", {})
    print("\n=== PASS 1 — Deterministic ===")
    for key, val in p1.items():
        print(f"  {key:<24} {val}")
    print("\n=== PASS 2 — Probabilistic ===")
    for key, val in p2.items():
        print(f"  {key:<24} {val}")


def _print_location_guess(guess: dict) -> None:
    print("\n=== LOCATION GUESS (Claude) ===")
    print(f"  city       {guess.get('city')}")
    print(f"  country    {guess.get('country')}")
    print(f"  lat        {guess.get('lat')}")
    print(f"  lng        {guess.get('lng')}")
    print(f"  reasoning  {guess.get('reasoning')}")
    print(f"  confidence {guess.get('confidence')}")


def _print_scorer(scorer_result: dict) -> None:
    print("\n=== BAYESIAN SCORER (analytical only) ===")
    print(f"  region           {scorer_result['region']}")
    print(f"  score            {scorer_result['score']:.4f}")
    print(f"  confidence_tier  {scorer_result['confidence_tier']}")
    print(f"  features_used    {', '.join(scorer_result['features_used'])}")
    print("\n  top 5 regions:")
    for entry in scorer_result["top_regions"]:
        bar = "#" * int(entry["score"] * 40)
        print(f"    {entry['region']:<25} {entry['score']:.4f}  {bar}")


def _print_geo(geo_result: dict) -> None:
    print("\n=== COORDINATE RESOLUTION ===")
    print(f"  source     {geo_result['source']}")
    print(f"  region     {geo_result['region']}")
    print(f"  lat        {geo_result['lat']:.4f}")
    print(f"  lng        {geo_result['lng']:.4f}")


def _print_score(guess_lat: float, guess_lng: float, actual_lat: float, actual_lng: float) -> None:
    from scoring import haversine, geoguessr_score
    distance_km = haversine(guess_lat, guess_lng, actual_lat, actual_lng)
    pts = geoguessr_score(distance_km)
    print("\n=== RESULT ===")
    print(f"  guess      {guess_lat:.4f}, {guess_lng:.4f}")
    print(f"  actual     {actual_lat:.4f}, {actual_lng:.4f}")
    print(f"  distance   {distance_km:.1f} km")
    print(f"  score      {pts} / 5000")


def main() -> None:
    parser = argparse.ArgumentParser(description="GeoLocator AI — single image evaluation")
    parser.add_argument("image", help="Path to the image file")
    parser.add_argument(
        "--actual",
        nargs=2,
        metavar=("LAT", "LNG"),
        type=float,
        help="Actual location (optional) — enables distance and GeoGuessr score output",
    )
    args = parser.parse_args()

    print(f"\nProcessing: {args.image}")

    # ------------------------------------------------------------------
    # Step 1 — Extraction (features + location guess in one call)
    # ------------------------------------------------------------------
    from extractor import extract
    features, _raw = extract([args.image])
    _print_extraction(features)
    _print_location_guess(features.get("location_guess", {}))

    # ------------------------------------------------------------------
    # Step 2 — Router (geocode overrides Claude's guess when place found)
    # ------------------------------------------------------------------
    from router import route
    router_result = route(features)

    if router_result is not None:
        print(f"\n=== ROUTER — geocode path ===")
        print(f"  place_name   {router_result['place_name']}")
        print(f"  country_code {router_result['country_code']}")
        print(f"  lat          {router_result['lat']:.4f}")
        print(f"  lng          {router_result['lng']:.4f}")
    else:
        print("\n=== ROUTER — no geocodable place name found ===")

    # ------------------------------------------------------------------
    # Step 3 — Scorer (analytical only — not used for the final guess)
    # ------------------------------------------------------------------
    from scorer import score as bayesian_score
    scorer_result = bayesian_score(features)
    _print_scorer(scorer_result)

    # ------------------------------------------------------------------
    # Step 4 — Coordinate resolution
    # ------------------------------------------------------------------
    from geo import resolve
    geo_result = resolve(features, router_result)
    _print_geo(geo_result)

    # ------------------------------------------------------------------
    # Step 5 — Scoring (only if --actual provided)
    # ------------------------------------------------------------------
    if args.actual is not None:
        actual_lat, actual_lng = args.actual
        _print_score(geo_result["lat"], geo_result["lng"], actual_lat, actual_lng)
    else:
        print(f"\n  (pass --actual <lat> <lng> to calculate distance and score)")


if __name__ == "__main__":
    main()
