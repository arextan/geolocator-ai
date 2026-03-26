"""
calibrate.py — confidence threshold grid search.

Replays the 608 stored rounds from geoguessr.db without making any API calls.
For each (high_threshold, medium_threshold) pair it re-scores every round using
the current centroids.json and feature_region_map.py, then reports avg/median
GeoGuessr score and tier distribution.

By default uses the stored confidence_score from the DB (fast).
With --rescore, reconstructs the features dict from stored columns and re-runs
scorer.score() — required to capture the benefit of new normalization rules.

Usage:
    python calibrate.py
    python calibrate.py --rescore
    python calibrate.py --db geoguessr.db
    python calibrate.py --high-range 0.4 0.8 --medium-range 0.15 0.5 --step 0.05
"""

import argparse
import json
import math
from pathlib import Path

import duckdb
import polars as pl

from feature_region_map import FEATURE_REGION_MAP
from scoring import geoguessr_score, haversine

_DB_DEFAULT = "geoguessr.db"

# Centroid loading — mirrors geo.py
_CENTROIDS_PATH = Path(__file__).parent / "centroids.json"
try:
    _CENTROIDS: dict = json.loads(_CENTROIDS_PATH.read_text())
except FileNotFoundError:
    _CENTROIDS = {}


# ---------------------------------------------------------------------------
# Centroid lookup
# ---------------------------------------------------------------------------

def _centroid_for_region(region: str) -> tuple[float, float] | None:
    """Return (lat, lng) from centroids.json, falling back to FEATURE_REGION_MAP."""
    if region in _CENTROIDS:
        c = _CENTROIDS[region]
        return float(c["lat"]), float(c["lng"])
    if region in FEATURE_REGION_MAP:
        d = FEATURE_REGION_MAP[region]
        return float(d["lat"]), float(d["lng"])
    return None


# ---------------------------------------------------------------------------
# Tier assignment
# ---------------------------------------------------------------------------

def _assign_tier(score: float, high: float, medium: float) -> str:
    if score >= high:
        return "high"
    if score >= medium:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Per-round score estimation
# ---------------------------------------------------------------------------

def _estimate_score(
    row: dict,
    high: float,
    medium: float,
) -> int | None:
    """Re-score one DB row under (high, medium) thresholds.

    Uses:
    - geocode path  → actual guess_lat/guess_lng (path_taken == "geocode")
    - high/medium   → region centroid lookup
    - low           → hedge centroid (stored as guess_lat/guess_lng in DB)

    Returns None if actual coordinates are missing.
    """
    actual_lat = row.get("actual_lat")
    actual_lng = row.get("actual_lng")
    if actual_lat is None or actual_lng is None:
        return None

    path_taken = row.get("path_taken", "bayesian")
    confidence_score = row.get("confidence_score") or 0.0
    top_regions = row.get("top_regions_parsed") or []
    region = top_regions[0]["region"] if top_regions else None

    # Geocode path is unaffected by threshold changes
    if path_taken == "geocode":
        guess_lat = row.get("guess_lat")
        guess_lng = row.get("guess_lng")
        if guess_lat is None or guess_lng is None:
            return None
        dist = haversine(guess_lat, guess_lng, actual_lat, actual_lng)
        return geoguessr_score(dist)

    # Bayesian path — apply new threshold
    tier = _assign_tier(confidence_score, high, medium)

    if tier in ("high", "medium") and region:
        coords = _centroid_for_region(region)
        if coords:
            dist = haversine(coords[0], coords[1], actual_lat, actual_lng)
            return geoguessr_score(dist)

    # Low confidence — use stored hedge/fallback guess from DB
    guess_lat = row.get("guess_lat")
    guess_lng = row.get("guess_lng")
    if guess_lat is None or guess_lng is None:
        return None
    dist = haversine(guess_lat, guess_lng, actual_lat, actual_lng)
    return geoguessr_score(dist)


# ---------------------------------------------------------------------------
# Grid search
# ---------------------------------------------------------------------------

def _grid_search(
    rows: list[dict],
    high_values: list[float],
    medium_values: list[float],
) -> pl.DataFrame:
    results = []
    for high in high_values:
        for medium in medium_values:
            if medium >= high:
                continue
            scores = []
            tier_counts = {"high": 0, "medium": 0, "low": 0}
            for row in rows:
                path_taken = row.get("path_taken", "bayesian")
                if path_taken == "geocode":
                    tier_counts["high"] += 1  # geocode always best-path
                else:
                    cs = row.get("confidence_score") or 0.0
                    tier_counts[_assign_tier(cs, high, medium)] += 1

                pts = _estimate_score(row, high, medium)
                if pts is not None:
                    scores.append(pts)

            if not scores:
                continue

            avg = sum(scores) / len(scores)
            median = sorted(scores)[len(scores) // 2]
            results.append({
                "high": round(high, 2),
                "medium": round(medium, 2),
                "avg_score": round(avg),
                "median_score": round(median),
                "n_high": tier_counts["high"],
                "n_medium": tier_counts["medium"],
                "n_low": tier_counts["low"],
                "n_rounds": len(scores),
            })

    return pl.DataFrame(results).sort("avg_score", descending=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="GeoLocator AI — threshold calibration")
    parser.add_argument("--db", default=_DB_DEFAULT)
    parser.add_argument("--rescore", action="store_true",
                        help="Re-run scorer on stored features (picks up new normalization rules)")
    parser.add_argument("--high-range",   nargs=2, type=float, default=[0.40, 0.85],
                        metavar=("MIN", "MAX"))
    parser.add_argument("--medium-range", nargs=2, type=float, default=[0.15, 0.50],
                        metavar=("MIN", "MAX"))
    parser.add_argument("--step", type=float, default=0.05)
    args = parser.parse_args()

    con = duckdb.connect(args.db)
    raw_rows = con.execute("""
        SELECT path_taken, confidence_score, confidence_tier,
               top_regions, guess_lat, guess_lng,
               actual_lat, actual_lng, geoguessr_score,
               -- pass_1 columns for --rescore
               script, language, language_confidence, place_name,
               plate_format, driving_side, speed_sign_format, domain_extension,
               currency_symbol,
               -- pass_2 columns for --rescore
               biome, vegetation_specific, sky_condition, terrain, soil_color,
               architecture, pole_type, road_surface, road_markings,
               infrastructure_quality
        FROM rounds
        WHERE actual_lat IS NOT NULL
    """).fetchall()
    cols = [
        "path_taken", "confidence_score", "confidence_tier",
        "top_regions", "guess_lat", "guess_lng",
        "actual_lat", "actual_lng", "geoguessr_score",
        "script", "language", "language_confidence", "place_name",
        "plate_format", "driving_side", "speed_sign_format", "domain_extension",
        "currency_symbol",
        "biome", "vegetation_specific", "sky_condition", "terrain", "soil_color",
        "architecture", "pole_type", "road_surface", "road_markings",
        "infrastructure_quality",
    ]
    con.close()

    rows: list[dict] = []
    for raw in raw_rows:
        row = dict(zip(cols, raw))
        try:
            row["top_regions_parsed"] = json.loads(row["top_regions"] or "[]")
        except Exception:
            row["top_regions_parsed"] = []
        rows.append(row)

    # --rescore: re-run scorer.score() on stored features to pick up new
    # normalization rules (architecture, road_markings, etc.)
    if args.rescore:
        from scorer import score as bayesian_score
        print("[calibrate] re-scoring all rounds with current scorer...")
        for row in rows:
            if row["path_taken"] == "geocode":
                continue
            features = {
                "pass_1": {
                    "script":              row["script"],
                    "language":            row["language"],
                    "language_confidence": row["language_confidence"],
                    "readable_text":       [],
                    "place_name":          row["place_name"],
                    "plate_format":        row["plate_format"],
                    "driving_side":        row["driving_side"],
                    "speed_sign_format":   row["speed_sign_format"],
                    "domain_extension":    row["domain_extension"],
                    "currency_symbol":     row["currency_symbol"],
                },
                "pass_2": {
                    "biome":                  row["biome"],
                    "vegetation_specific":    row["vegetation_specific"],
                    "sky_condition":          row["sky_condition"],
                    "terrain":                row["terrain"],
                    "soil_color":             row["soil_color"],
                    "architecture":           row["architecture"],
                    "pole_type":              row["pole_type"],
                    "road_surface":           row["road_surface"],
                    "road_markings":          row["road_markings"],
                    "infrastructure_quality": row["infrastructure_quality"],
                },
            }
            result = bayesian_score(features)
            row["confidence_score"]  = result["score"]
            row["top_regions_parsed"] = result["top_regions"]
            # Update hedge coords in guess_lat/guess_lng for low-tier rounds
            if result["confidence_tier"] == "low":
                row["guess_lat"] = result.get("hedge_lat") or row["guess_lat"]
                row["guess_lng"] = result.get("hedge_lng") or row["guess_lng"]
        print(f"[calibrate] re-scoring complete")

    print(f"[calibrate] loaded {len(rows)} rounds with actual coordinates")

    # Current baseline (using stored scores)
    stored_scores = [r["geoguessr_score"] for r in rows if r["geoguessr_score"] is not None]
    print(f"\nBaseline (stored scores from DB):")
    print(f"  avg={round(sum(stored_scores)/len(stored_scores))}  "
          f"median={sorted(stored_scores)[len(stored_scores)//2]}")

    def _frange(lo: float, hi: float, step: float) -> list[float]:
        vals = []
        v = lo
        while v <= hi + 1e-9:
            vals.append(round(v, 4))
            v += step
        return vals

    high_values   = _frange(args.high_range[0],   args.high_range[1],   args.step)
    medium_values = _frange(args.medium_range[0],  args.medium_range[1], args.step)

    print(f"\nGrid: high={high_values[0]}–{high_values[-1]}, "
          f"medium={medium_values[0]}–{medium_values[-1]}, step={args.step}")
    print(f"Combinations: {sum(1 for h in high_values for m in medium_values if m < h)}\n")

    df = _grid_search(rows, high_values, medium_values)

    print("=== TOP 20 THRESHOLD COMBINATIONS ===")
    print(df.head(20).to_pandas().to_string(index=False))

    best = df.row(0, named=True)
    print(f"\n=== BEST ===")
    print(f"  high_threshold   = {best['high']}")
    print(f"  medium_threshold = {best['medium']}")
    print(f"  avg_score        = {best['avg_score']}")
    print(f"  median_score     = {best['median_score']}")
    print(f"  tier breakdown   = high:{best['n_high']}  medium:{best['n_medium']}  low:{best['n_low']}")

    print(f"\nCurrent config.py values for comparison:")
    from config import HIGH_CONFIDENCE_THRESHOLD, MEDIUM_CONFIDENCE_THRESHOLD
    print(f"  HIGH_CONFIDENCE_THRESHOLD   = {HIGH_CONFIDENCE_THRESHOLD}")
    print(f"  MEDIUM_CONFIDENCE_THRESHOLD = {MEDIUM_CONFIDENCE_THRESHOLD}")


if __name__ == "__main__":
    main()
