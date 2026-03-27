"""
main.py — Phase 2 batch orchestration.

Processes a directory of images through the full pipeline
(extract → route → [score analytical] → geo) and stores every round in DuckDB.

Images produced by collect.py are grouped by location prefix:
    loc_0001_h0.png, loc_0001_h90.png, loc_0001_h180.png, loc_0001_h270.png
    → one round with round_id "loc_0001", all 4 sent to Claude in one call.

Single images (e.g. test.png) are treated as their own round with
round_id equal to the filename stem ("test").

Idempotent: already-processed round_ids are skipped, so a crashed run
can be resumed safely by re-running the same command.

Usage:
    python main.py --input data/images/
    python main.py --input data/images/ --actuals actuals.csv
    python main.py --input data/images/ --actuals actuals.csv --db geoguessr.db
    python main.py --input data/images/ --reset-db
"""

import argparse
import json
import re
import sys
from pathlib import Path

import duckdb
import polars as pl

from extractor import extract
from geo import resolve
from router import route
from scorer import score as bayesian_score
from scoring import geoguessr_score, haversine

_IMAGE_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp"})
_DB_DEFAULT = "geoguessr.db"

# Matches filenames produced by collect.py: loc_0001_h0.png, loc_0042_h270.png
_LOC_PREFIX_RE = re.compile(r"^(loc_\d+)_h\d+$")

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS rounds (
    round_id               VARCHAR PRIMARY KEY,
    timestamp              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    image_files            VARCHAR[],
    script                 VARCHAR,
    language               VARCHAR,
    language_confidence    FLOAT,
    readable_text          VARCHAR[],
    place_name             VARCHAR,
    route_number           VARCHAR,
    plate_format           VARCHAR,
    driving_side           VARCHAR,
    speed_sign_format      VARCHAR,
    domain_extension       VARCHAR,
    currency_symbol        VARCHAR,
    biome                  VARCHAR,
    vegetation_specific    VARCHAR,
    sky_condition          VARCHAR,
    terrain                VARCHAR,
    soil_color             VARCHAR,
    architecture           VARCHAR,
    pole_type              VARCHAR,
    road_surface           VARCHAR,
    road_markings          VARCHAR,
    infrastructure_quality VARCHAR,
    guessed_city           VARCHAR,
    guessed_country        VARCHAR,
    guess_reasoning        VARCHAR,
    guess_confidence       FLOAT,
    path_taken             VARCHAR,
    scorer_region          VARCHAR,
    scorer_confidence      FLOAT,
    scorer_top_regions     JSON,
    features_used          VARCHAR[],
    guess_lat              DOUBLE,
    guess_lng              DOUBLE,
    actual_lat             DOUBLE,
    actual_lng             DOUBLE,
    distance_km            FLOAT,
    geoguessr_score        INTEGER,
    raw_response           TEXT,
    extraction_failed      BOOLEAN DEFAULT FALSE
);
"""


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------

def _group_locations(images: list[Path]) -> dict[str, list[Path]]:
    """Group image paths by location prefix.

    collect.py images  → loc_0001_h0.png … loc_0001_h270.png  → "loc_0001"
    Single images      → test.png                              → "test"

    Images within each group are sorted (heading order).
    """
    groups: dict[str, list[Path]] = {}
    for p in images:
        m = _LOC_PREFIX_RE.match(p.stem)
        prefix = m.group(1) if m else p.stem
        groups.setdefault(prefix, []).append(p)
    for paths in groups.values():
        paths.sort()
    return groups


# ---------------------------------------------------------------------------
# Actuals helpers
# ---------------------------------------------------------------------------

def _load_actuals_csv(path: str) -> dict[str, tuple[float, float]]:
    """Load actuals CSV (columns: filename, lat, lng) → {filename: (lat, lng)}."""
    df = pl.read_csv(path)
    return {
        row["filename"]: (float(row["lat"]), float(row["lng"]))
        for row in df.iter_rows(named=True)
    }


def _load_sidecar(image_path: Path) -> tuple[float, float] | None:
    """Read <image_stem>.json next to the image file for {lat, lng}."""
    sidecar = image_path.with_suffix(".json")
    if not sidecar.exists():
        return None
    try:
        data = json.loads(sidecar.read_text())
        return float(data["lat"]), float(data["lng"])
    except Exception:
        return None


def _actual_coords_for_group(
    paths: list[Path],
    actuals_csv: dict[str, tuple[float, float]],
) -> tuple[float, float] | None:
    """Resolve actual coordinates for a group of images.

    Priority:
    1. actuals CSV keyed by the first image filename
    2. Sidecar JSON of the first image (all headings share the same coords)
    """
    first = paths[0]
    return actuals_csv.get(first.name) or _load_sidecar(first)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _existing_ids(con: duckdb.DuckDBPyConnection) -> set[str]:
    return {r[0] for r in con.execute("SELECT round_id FROM rounds").fetchall()}


def _run_pipeline(
    paths: list[Path],
) -> tuple[dict, dict | None, dict, dict, str]:
    """Run extract → route → score (analytical) → geo for one location group.

    Returns (features, router_result, scorer_result, geo_result, raw_response).
    """
    features, raw_response = extract([str(p) for p in paths])
    router_result = route(features)
    scorer_result = bayesian_score(features)
    geo_result = resolve(features, router_result)
    return features, router_result, scorer_result, geo_result, raw_response


def _build_row(
    round_id: str,
    paths: list[Path],
    features: dict,
    router_result: dict | None,
    scorer_result: dict,
    geo_result: dict,
    raw_response: str,
    actual_coords: tuple[float, float] | None,
) -> dict:
    """Flatten all pipeline outputs into a dict matching the rounds schema."""
    p1 = features.get("pass_1", {})
    p2 = features.get("pass_2", {})
    lg = features.get("location_guess", {}) or {}

    actual_lat: float | None = None
    actual_lng: float | None = None
    distance_km: float | None = None
    pts: int | None = None

    if actual_coords is not None:
        actual_lat, actual_lng = actual_coords
        distance_km = haversine(
            geo_result["lat"], geo_result["lng"], actual_lat, actual_lng
        )
        pts = geoguessr_score(distance_km)

    path_taken = router_result["path"] if router_result else "claude"

    return {
        "round_id":               round_id,
        "image_files":            [p.name for p in paths],
        # pass_1
        "script":                 p1.get("script"),
        "language":               p1.get("language"),
        "language_confidence":    p1.get("language_confidence"),
        "readable_text":          p1.get("readable_text") or [],
        "place_name":             p1.get("place_name"),
        "route_number":           p1.get("route_number"),
        "plate_format":           p1.get("plate_format"),
        "driving_side":           p1.get("driving_side"),
        "speed_sign_format":      p1.get("speed_sign_format"),
        "domain_extension":       p1.get("domain_extension"),
        "currency_symbol":        p1.get("currency_symbol"),
        # pass_2
        "biome":                  p2.get("biome"),
        "vegetation_specific":    p2.get("vegetation_specific"),
        "sky_condition":          p2.get("sky_condition"),
        "terrain":                p2.get("terrain"),
        "soil_color":             p2.get("soil_color"),
        "architecture":           p2.get("architecture"),
        "pole_type":              p2.get("pole_type"),
        "road_surface":           p2.get("road_surface"),
        "road_markings":          p2.get("road_markings"),
        "infrastructure_quality": p2.get("infrastructure_quality"),
        # location_guess
        "guessed_city":           lg.get("city"),
        "guessed_country":        lg.get("country"),
        "guess_reasoning":        lg.get("reasoning"),
        "guess_confidence":       lg.get("confidence"),
        # routing + analytical scorer
        "path_taken":             path_taken,
        "scorer_region":          scorer_result.get("region"),
        "scorer_confidence":      scorer_result.get("score"),
        "scorer_top_regions":     json.dumps(scorer_result.get("top_regions", [])),
        "features_used":          scorer_result.get("features_used", []),
        # coordinates
        "guess_lat":              geo_result["lat"],
        "guess_lng":              geo_result["lng"],
        "actual_lat":             actual_lat,
        "actual_lng":             actual_lng,
        "distance_km":            distance_km,
        "geoguessr_score":        pts,
        # meta
        "raw_response":           raw_response,
        "extraction_failed":      raw_response == "",
    }


def _insert_row(con: duckdb.DuckDBPyConnection, row: dict) -> None:
    cols = ", ".join(row.keys())
    placeholders = ", ".join(["?" for _ in row])
    con.execute(
        f"INSERT INTO rounds ({cols}) VALUES ({placeholders})",
        list(row.values()),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="GeoLocator AI — batch pipeline")
    parser.add_argument("--input",    required=True,       help="Directory of images to process")
    parser.add_argument("--actuals",  default=None,        help="CSV with columns: filename, lat, lng")
    parser.add_argument("--db",       default=_DB_DEFAULT, help=f"DuckDB file path (default: {_DB_DEFAULT})")
    parser.add_argument("--reset-db", action="store_true", help="Drop and recreate the rounds table before processing")
    args = parser.parse_args()

    input_dir = Path(args.input)
    if not input_dir.is_dir():
        print(f"[main] error: '{input_dir}' is not a directory")
        sys.exit(1)

    # Actuals from CSV (optional)
    actuals: dict[str, tuple[float, float]] = {}
    if args.actuals:
        try:
            actuals = _load_actuals_csv(args.actuals)
            print(f"[main] loaded {len(actuals)} actuals from {args.actuals}")
        except Exception as exc:
            print(f"[main] warning: could not load actuals CSV: {exc}")

    # Discover and group images
    all_images = sorted(
        p for p in input_dir.iterdir()
        if p.is_file() and p.suffix.lower() in _IMAGE_EXTENSIONS
    )
    if not all_images:
        print(f"[main] no images found in {input_dir}")
        sys.exit(0)

    groups = _group_locations(all_images)
    total = len(groups)
    total_images = len(all_images)
    print(f"[main] found {total_images} image(s) in {total} location group(s) in {input_dir}")

    con = duckdb.connect(args.db)
    try:
        if args.reset_db:
            con.execute("DROP TABLE IF EXISTS rounds")
            print("[main] rounds table dropped")

        con.execute(_CREATE_TABLE_SQL)
        existing = _existing_ids(con)

        n_skip = sum(1 for rid in groups if rid in existing)
        if n_skip:
            print(f"[main] {n_skip} already processed — skipping")

        processed = failed = 0

        for idx, (round_id, paths) in enumerate(groups.items(), start=1):
            if round_id in existing:
                continue

            img_label = f"{round_id} ({len(paths)} image{'s' if len(paths) > 1 else ''})"
            print(f"Processing {idx}/{total}: {img_label}", flush=True)

            actual_coords = _actual_coords_for_group(paths, actuals)

            try:
                features, router_result, scorer_result, geo_result, raw_response = (
                    _run_pipeline(paths)
                )
                row = _build_row(
                    round_id, paths,
                    features, router_result, scorer_result, geo_result,
                    raw_response, actual_coords,
                )
                _insert_row(con, row)
                processed += 1

                source  = geo_result.get("source", "?")
                region  = geo_result.get("region", "?")
                score_s = f"  {row['geoguessr_score']} pts" if row["geoguessr_score"] is not None else ""
                print(f"  -> {region} via {source}{score_s}")

            except Exception as exc:
                failed += 1
                print(f"  -> ERROR: {exc}")

    finally:
        con.close()

    print(f"\n[main] done — processed={processed}  skipped={n_skip}  failed={failed}")


if __name__ == "__main__":
    main()
