"""Single-image evaluation CLI.

Usage:
    python evaluate.py <image_path>
    python evaluate.py <image_path> --actual <lat> <lng>

Examples:
    python evaluate.py data\images\test.png
    python evaluate.py data\images\test.png --actual 21.03 105.85
"""

import argparse
import sys


def _print_features(features: dict) -> None:
    p1 = features.get("pass_1", {})
    p2 = features.get("pass_2", {})

    print("\n=== PASS 1 — Deterministic ===")
    for key, val in p1.items():
        print(f"  {key:<22} {val}")

    print("\n=== PASS 2 — Probabilistic ===")
    for key, val in p2.items():
        print(f"  {key:<22} {val}")


def main() -> None:
    parser = argparse.ArgumentParser(description="GeoLocator AI — single image evaluation")
    parser.add_argument("image", help="Path to the image file")
    parser.add_argument(
        "--actual",
        nargs=2,
        metavar=("LAT", "LNG"),
        type=float,
        help="Actual location as lat lng (optional — enables distance/score output)",
    )
    args = parser.parse_args()

    # --- Extraction ---
    try:
        from extractor import extract
    except ImportError as e:
        print(f"[evaluate] cannot import extractor: {e}")
        sys.exit(1)

    print(f"\nProcessing: {args.image}")
    features, raw_response = extract(args.image)
    _print_features(features)

    # --- Scoring (only if actual coords provided) ---
    if args.actual is not None:
        actual_lat, actual_lng = args.actual
        try:
            from scoring import haversine, geoguessr_score
        except ImportError:
            print("\n[evaluate] scoring.py not available — skipping distance/score")
            return

        # Pipeline modules not yet built — no guess coords yet
        guess_lat = features.get("guess_lat")
        guess_lng = features.get("guess_lng")

        if guess_lat is not None and guess_lng is not None:
            distance_km = haversine(guess_lat, guess_lng, actual_lat, actual_lng)
            score = geoguessr_score(distance_km)
            print(f"\n=== SCORING ===")
            print(f"  Guess      {guess_lat:.4f}, {guess_lng:.4f}")
            print(f"  Actual     {actual_lat:.4f}, {actual_lng:.4f}")
            print(f"  Distance   {distance_km:.1f} km")
            print(f"  Score      {score} / 5000")
        else:
            print("\n[evaluate] no guess coordinates yet — run full pipeline for scoring")


if __name__ == "__main__":
    main()
