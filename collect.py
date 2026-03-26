"""
collect.py — Phase 2 Street View image collection.

Downloads Street View imagery at stratified random locations worldwide.
For each accepted location, fetches 4 headings (0, 90, 180, 270 degrees)
and writes one sidecar JSON per image with the actual panorama coordinates.

Usage:
    python collect.py --locations 500 --output data/images/
    python collect.py --locations 500 --output data/images/ --dry-run
    python collect.py --locations 100 --output data/images/ --concurrency 5
"""

import argparse
import asyncio
import json
import random
import sys
from pathlib import Path

import httpx

from config import GOOGLE_MAPS_API_KEY

# ---------------------------------------------------------------------------
# API constants
# ---------------------------------------------------------------------------

_SV_IMAGE_URL    = "https://maps.googleapis.com/maps/api/streetview"
_SV_METADATA_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"

HEADINGS  = [0, 90, 180, 270]
_IMG_SIZE = "640x640"
_FOV      = 90
_PITCH    = 0

# Snap-radius tiers (metres).  The metadata API snaps to the nearest panorama
# within this distance.  Dense regions use a small radius to stay on-point;
# sparse regions use a large radius so rural roads and villages are reachable
# without biasing the sample toward cities.  API maximum is 50,000 m.
_RADIUS_DENSE  =  1_000   # W.Europe, Japan, S.Korea — road every ~500 m
_RADIUS_MEDIUM = 10_000   # Brazil, SE Asia, India, Eastern Europe
_RADIUS_SPARSE = 50_000   # Russia, Africa, Middle East, Latin America outback

# ---------------------------------------------------------------------------
# Region sampling specs
#
# Each entry:
#   target  — ideal number of locations to collect from this region
#   mult    — max_attempts = target * mult  (higher for sparse coverage)
#   boxes   — list of (lat_min, lat_max, lng_min, lng_max) bounding boxes
#
# Targets sum to 500.  When --locations differs from 500 they are scaled
# proportionally, so the distribution stays consistent.
# ---------------------------------------------------------------------------

_REGION_SPECS: dict[str, dict] = {
    "western_europe": {
        "target": 40, "mult": 3, "snap_radius": _RADIUS_DENSE,
        "boxes": [(36.0, 70.0, -9.0, 28.0)],
    },
    "usa_canada": {
        "target": 40, "mult": 2, "snap_radius": _RADIUS_DENSE,
        "boxes": [
            (25.0, 50.0, -125.0, -65.0),   # continental USA
            (43.0, 60.0, -140.0, -53.0),   # Canada
        ],
    },
    "brazil": {
        "target": 30, "mult": 4, "snap_radius": _RADIUS_MEDIUM,
        "boxes": [(-33.0, 5.0, -73.0, -35.0)],
    },
    "russia_central_asia": {
        "target": 28, "mult": 6, "snap_radius": _RADIUS_SPARSE,
        "boxes": [
            (50.0, 70.0, 30.0, 130.0),     # European + western Russia
            (40.0, 55.0, 55.0, 90.0),      # Kazakhstan / Central Asia
        ],
    },
    "japan": {
        "target": 28, "mult": 2, "snap_radius": _RADIUS_DENSE,
        "boxes": [(30.0, 45.0, 129.0, 146.0)],
    },
    "eastern_europe": {
        "target": 28, "mult": 3, "snap_radius": _RADIUS_MEDIUM,
        "boxes": [(44.0, 58.0, 14.0, 32.0)],
    },
    "latin_america": {
        "target": 28, "mult": 5, "snap_radius": _RADIUS_SPARSE,
        "boxes": [(-55.0, 22.0, -92.0, -35.0)],
    },
    "southeast_asia": {
        "target": 38, "mult": 4, "snap_radius": _RADIUS_MEDIUM,
        "boxes": [(-8.0, 22.0, 95.0, 141.0)],
    },
    "india_subcontinent": {
        "target": 35, "mult": 4, "snap_radius": _RADIUS_MEDIUM,
        "boxes": [(6.0, 36.0, 67.0, 97.0)],
    },
    "sub_saharan_africa": {
        "target": 25, "mult": 10, "snap_radius": _RADIUS_SPARSE,
        "boxes": [(-35.0, 15.0, -18.0, 51.0)],
    },
    "australia_new_zealand": {
        "target": 25, "mult": 3, "snap_radius": _RADIUS_SPARSE,
        "boxes": [
            (-44.0, -10.0, 112.0, 154.0),  # Australia
            (-47.0, -34.0, 166.0, 178.0),  # New Zealand
        ],
    },
    "south_korea": {
        "target": 20, "mult": 2, "snap_radius": _RADIUS_DENSE,
        "boxes": [(34.0, 38.5, 126.0, 130.0)],
    },
    "nordic": {
        "target": 20, "mult": 4, "snap_radius": _RADIUS_MEDIUM,
        "boxes": [
            (55.0, 71.0, 4.0, 31.0),
            (63.0, 66.0, -24.0, -13.0),    # Iceland
        ],
    },
    "thailand": {
        "target": 18, "mult": 3, "snap_radius": _RADIUS_MEDIUM,
        "boxes": [(5.5, 21.0, 97.5, 105.5)],
    },
    "middle_east": {
        "target": 18, "mult": 5, "snap_radius": _RADIUS_SPARSE,
        "boxes": [(12.0, 37.0, 34.0, 63.0)],
    },
    "south_africa": {
        "target": 18, "mult": 3, "snap_radius": _RADIUS_MEDIUM,
        "boxes": [(-35.0, -22.0, 16.0, 33.0)],
    },
    "north_africa": {
        "target": 15, "mult": 6, "snap_radius": _RADIUS_SPARSE,
        "boxes": [(19.0, 37.0, -17.0, 37.0)],
    },
}

_BASELINE_TOTAL: int = sum(s["target"] for s in _REGION_SPECS.values())  # 500


# ---------------------------------------------------------------------------
# Sampling helpers
# ---------------------------------------------------------------------------

def _sample_point(boxes: list[tuple[float, float, float, float]]) -> tuple[float, float]:
    """Pick a uniformly random (lat, lng) from one of the bounding boxes."""
    lat_min, lat_max, lng_min, lng_max = random.choice(boxes)
    return round(random.uniform(lat_min, lat_max), 6), round(random.uniform(lng_min, lng_max), 6)


def _scale_targets(requested: int) -> dict[str, int]:
    """Scale per-region targets proportionally to the requested total."""
    scale = requested / _BASELINE_TOTAL
    targets = {r: max(1, round(s["target"] * scale)) for r, s in _REGION_SPECS.items()}
    # Absorb rounding error into the largest region
    delta = requested - sum(targets.values())
    if delta:
        biggest = max(targets, key=targets.__getitem__)
        targets[biggest] += delta
    return targets


def _next_loc_index(output_dir: Path) -> int:
    """Return the next unused location index by scanning existing loc_NNNN_h0.png files."""
    indices = []
    for p in output_dir.glob("loc_*_h0.png"):
        try:
            indices.append(int(p.stem.split("_")[1]))
        except (IndexError, ValueError):
            pass
    return (max(indices) + 1) if indices else 1


# ---------------------------------------------------------------------------
# Async API helpers
# ---------------------------------------------------------------------------

async def _check_metadata(
    client: httpx.AsyncClient,
    lat: float,
    lng: float,
    radius: int,
) -> tuple[float, float] | None:
    """Query Street View metadata endpoint.

    Returns the actual panorama (lat, lng) if coverage exists,
    or None if status is not OK (ZERO_RESULTS / NOT_FOUND).
    """
    resp = await client.get(
        _SV_METADATA_URL,
        params={"location": f"{lat},{lng}", "radius": radius, "key": GOOGLE_MAPS_API_KEY},
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "OK":
        return None
    loc = data["location"]
    return round(float(loc["lat"]), 6), round(float(loc["lng"]), 6)


async def _fetch_heading(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    lat: float,
    lng: float,
    heading: int,
    out_path: Path,
) -> None:
    """Download one heading image into out_path. Raises on HTTP error."""
    async with sem:
        resp = await client.get(
            _SV_IMAGE_URL,
            params={
                "size":    _IMG_SIZE,
                "location": f"{lat},{lng}",
                "heading": heading,
                "fov":     _FOV,
                "pitch":   _PITCH,
                "key":     GOOGLE_MAPS_API_KEY,
            },
        )
        resp.raise_for_status()
        out_path.write_bytes(resp.content)


async def _collect_location(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    lat: float,
    lng: float,
    loc_idx: int,
    output_dir: Path,
    snap_radius: int,
) -> tuple[bool, float, float]:
    """Process one candidate location.

    1. Metadata check — returns actual panorama coords or rejects.
    2. Downloads all 4 heading images concurrently.
    3. Writes sidecar JSON for each successfully saved image.

    Returns (success, actual_lat, actual_lng).
    success is True only if all 4 headings downloaded cleanly.
    """
    actual = await _check_metadata(client, lat, lng, snap_radius)
    if actual is None:
        return False, lat, lng

    actual_lat, actual_lng = actual
    sidecar = {"lat": actual_lat, "lng": actual_lng}

    # Build tasks for all 4 headings
    stems     = [f"loc_{loc_idx:04d}_h{h}" for h in HEADINGS]
    out_paths = [output_dir / f"{stem}.png" for stem in stems]
    tasks     = [
        _fetch_heading(client, sem, actual_lat, actual_lng, h, p)
        for h, p in zip(HEADINGS, out_paths)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    success_count = 0
    for stem, out_path, result in zip(stems, out_paths, results):
        if isinstance(result, Exception):
            print(f"    warning: {stem}.png failed — {result}")
            out_path.unlink(missing_ok=True)
        else:
            (output_dir / f"{stem}.json").write_text(json.dumps(sidecar))
            success_count += 1

    all_ok = success_count == len(HEADINGS)
    if not all_ok and success_count < len(HEADINGS):
        # Partial download — clean up to keep the directory consistent
        for out_path, stem in zip(out_paths, stems):
            out_path.unlink(missing_ok=True)
            (output_dir / f"{stem}.json").unlink(missing_ok=True)

    return all_ok, actual_lat, actual_lng


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------

def _dry_run(locations: int) -> None:
    targets = _scale_targets(locations)
    total_shown = 0
    print(f"DRY RUN — {locations} locations across {len(_REGION_SPECS)} regions\n")
    print(f"  {'region':<25}  {'target':>6}  {'radius':>7}  {'sample points'}")
    print(f"  {'-'*25}  {'-'*6}  {'-'*7}  {'-'*40}")
    for region, spec in _REGION_SPECS.items():
        n = targets[region]
        total_shown += n
        samples = [_sample_point(spec["boxes"]) for _ in range(min(3, n))]
        sample_str = "  ".join(f"({lat:8.4f}, {lng:9.4f})" for lat, lng in samples)
        radius_str = f"{spec['snap_radius']:,}m"
        print(f"  {region:<25}  {n:>6}  {radius_str:>7}  {sample_str}")
    print(f"\n  {'TOTAL':<25}  {total_shown:>6}")


# ---------------------------------------------------------------------------
# Main async runner
# ---------------------------------------------------------------------------

async def _run(args: argparse.Namespace) -> None:
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    targets = _scale_targets(args.locations)
    loc_idx = _next_loc_index(output_dir)

    if loc_idx > 1:
        already = loc_idx - 1
        print(f"[collect] resuming — {already} location(s) already downloaded, starting at loc_{loc_idx:04d}")

    grand_collected = 0
    grand_attempts  = 0

    async with httpx.AsyncClient(timeout=20) as client:
        sem = asyncio.Semaphore(args.concurrency)

        for region, spec in _REGION_SPECS.items():
            target       = targets[region]
            max_attempts = target * spec["mult"]
            collected    = 0
            attempts     = 0

            print(f"\n[{region}] target={target}  max_attempts={max_attempts}")

            while collected < target and attempts < max_attempts:
                lat, lng = _sample_point(spec["boxes"])
                attempts       += 1
                grand_attempts += 1

                try:
                    ok, actual_lat, actual_lng = await _collect_location(
                        client, sem, lat, lng, loc_idx, output_dir, spec["snap_radius"]
                    )
                except Exception as exc:
                    print(f"  error ({lat:.4f}, {lng:.4f}): {exc}")
                    ok = False

                if ok:
                    collected       += 1
                    grand_collected += 1
                    print(
                        f"  loc_{loc_idx:04d}: {actual_lat:.4f}, {actual_lng:.4f}"
                        f"  [{collected}/{target}]",
                        flush=True,
                    )
                    loc_idx += 1

            hit_pct = f"{collected / attempts * 100:.0f}%" if attempts else "n/a"
            print(f"  -> {collected}/{target} collected  ({attempts} attempts, {hit_pct} hit rate)")

    print(f"\n[collect] done — {grand_collected} locations, {grand_attempts} attempts total")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="GeoLocator AI — Street View image collector")
    parser.add_argument("--locations",   type=int, default=500,        help="Total locations to collect (default: 500)")
    parser.add_argument("--output",      default="data/images",        help="Output directory (default: data/images)")
    parser.add_argument("--concurrency", type=int, default=10,         help="Max concurrent image downloads (default: 10)")
    parser.add_argument("--dry-run",     action="store_true",          help="Print sample coordinates without making API calls")
    args = parser.parse_args()

    if args.dry_run:
        _dry_run(args.locations)
        return

    if not GOOGLE_MAPS_API_KEY:
        print("[collect] error: GOOGLE_MAPS_API_KEY is not set in .env")
        sys.exit(1)

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
