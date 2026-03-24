# geolocator-ai

Multi-source image intelligence pipeline that extracts geographic features from Street View imagery using Claude's vision API, scores them against a domain knowledge base, and outputs coordinate guesses with calibrated confidence levels.

**Target:** 20,000+ per 5-round GeoGuessr game (out of 25,000 max)  
**Stack:** Python · Claude Sonnet · DuckDB · Polars · GeoPandas · Streamlit

---

### Required API keys (.env)

```
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_MAPS_API_KEY=AIza...
```

---

## What this does

Takes a Street View image and answers "where in the world is this?" through 6 pipeline steps:

1. **Extract** — Claude Sonnet analyzes the image and returns structured JSON with ~20 geographic features
2. **Route** — If a place name was found, geocode it. Otherwise, score features against the knowledge base.
3. **Score** — Bayesian scorer multiplies feature likelihoods against region priors. Confidence gate prevents overcommitment.
4. **Resolve** — Convert the top region to lat/lng via coverage-weighted centroids.
5. **Store** — Log everything to DuckDB.
6. **Display** — Show results in Streamlit with map, reasoning, and confidence breakdown.

---

## App

Streamlit interface for running the pipeline interactively and reviewing results.

### Live analysis view

Upload a screenshot or paste from clipboard. The app runs the full pipeline and displays:

- **Original image** — The uploaded screenshot
- **Result card** — Predicted city/region/country, coordinates, confidence tier
- **Map** — Guess pin (blue), actual pin if known (green), alternative candidate regions as faded circles, distance line between guess and actual
- **Reasoning panel** — Which features were extracted, which drove the decision, routing path taken, Bayesian scores for top 5 regions
- **Score** — GeoGuessr points if actual location is provided

### Historical analysis view

Browse and query all processed rounds from DuckDB:

- Filter by score range, confidence tier, path taken, region
- Sort by worst rounds to investigate failures
- View feature importance and confusion matrix
- Drill into any round to see its full pipeline trace

---

## Architecture

```
                        ┌─────────────────────────┐
                        │     Streamlit app       │
                        │ (upload / results / map)│
                        └────────────┬────────────┘
                                     │ reads/writes
                                     ▼
Screenshot(s) → extractor.py → router.py → scorer.py → geo.py
                 (Claude API)   (geocode     (Bayesian    (centroids)
                                or score?)    + gate)
                                                              │
                                                              ▼
                                                        geoguessr.db
                                                         (DuckDB)
```

---

## Project structure

```
geolocator-ai/
├── README.md
├── requirements.txt
├── .env.example
│
│   App
├── app.py                  # Streamlit interface
│
│   Pipeline (core)
├── main.py                 # Batch orchestration — resumes on failure
├── config.py               # API keys, thresholds, region definitions
├── evaluate.py             # Single-image CLI debug tool
│
│   Pipeline modules
├── extractor.py            # Claude API → structured JSON
├── router.py               # Geocode vs Bayesian path decision
├── scorer.py               # Bayesian scoring + confidence gate
├── geo.py                  # GeoPandas spatial lookup + centroids
├── scoring.py              # Haversine distance + GeoGuessr points
│
│   Data and knowledge
├── feature_region_map.py   # 127-feature domain knowledge base
├── centroids.json          # Coverage-weighted centroids per region
├── geoguessr.db            # DuckDB storage
│
│   Post-hoc
├── calibrate.py            # Threshold grid search
├── analyze.py              # Decision tree, feature importance, confusion matrix
├── collect.py              # Street View API image scraper
│
├── data/
│   └── images/
│
└── docs/
    ├── pipeline.md
    ├── data_model.md
    ├── feature_reference.md
    └── findings.md
```

---

## Data model

Each round is one row in DuckDB.

| Column | Type | Description |
|--------|------|-------------|
| `round_id` | VARCHAR | Unique identifier |
| `script` | VARCHAR | Detected writing system |
| `language` | VARCHAR | Detected language |
| `place_name` | VARCHAR | Geocodable text or null |
| `path_taken` | VARCHAR | `geocode` or `bayesian` |
| `confidence_tier` | VARCHAR | `high`, `medium`, `low` |
| `features_used` | VARCHAR[] | Which features drove the guess |
| `guess_lat/lng` | DOUBLE | Predicted coordinates |
| `actual_lat/lng` | DOUBLE | True coordinates |
| `distance_km` | FLOAT | Haversine error |
| `geoguessr_score` | INTEGER | 0–5,000 points |
| `raw_response` | TEXT | Full Claude response for debugging |

Full schema: [`docs/data_model.md`](docs/data_model.md)

---

## Example queries

```sql
-- Failure analysis
SELECT round_id, distance_km, confidence_tier, features_used
FROM rounds WHERE geoguessr_score < 1000
ORDER BY distance_km DESC;

-- Feature effectiveness
SELECT unnest(features_used) AS feature,
       COUNT(*) AS times_used,
       ROUND(AVG(geoguessr_score)) AS avg_score
FROM rounds GROUP BY feature ORDER BY avg_score DESC;

-- Path comparison
SELECT path_taken, COUNT(*) AS rounds,
       ROUND(AVG(geoguessr_score)) AS avg_score
FROM rounds GROUP BY path_taken;

-- High confidence failures (calibration bugs)
SELECT round_id, confidence_score, geoguessr_score, features_used
FROM rounds WHERE confidence_tier = 'high' AND geoguessr_score < 2500;
```

---

## Key design decisions

**Two-pass extraction** — Pass 1 extracts deterministic signals (text, script, plates). Pass 2 extracts probabilistic signals (biome, architecture, terrain). Separation lets the router use Pass 1 confidence to decide the scoring path.

**Geocoding branch** — Place name found → geocode for ~4,600 pts. Without geocoding → country centroid at ~3,500. The router prevents that waste.

**Confidence gate** — Prevents overcommitment on weak signals. Would have recovered ~1,000 pts on a Bangladesh round incorrectly committed to Vietnam.

**Coverage-weighted centroids** — Geographic centroids are wrong. Street View coverage isn't uniform. For large countries the shift is 500–1,000km.

**Idempotent processing** — Pipeline checks DuckDB for existing rounds before processing. Crash-safe.

**Raw response archiving** — Full Claude response stored for debugging without re-running API calls.

---

## Preliminary results

5 live test rounds (manual screenshots, single frame):

| Round | Location | Guess | Score | Notes |
|-------|----------|-------|-------|-------|
| 1 | Southern France | Sisteron, France | ~4,800 | French text + stone architecture |
| 2 | Lima, Peru | Lima, Peru | ~4,998 | Spanish text + grey garua sky |
| 3 | Bodega Bay, CA | Marin/Sonoma coast | ~4,700 | Monterey cypress + coastal grass |
| 4 | Chittagong, BD | Vietnam | ~1,800 | Overcommitment (gate would fix) |
| 5 | Huis Ten Bosch, JP | Netherlands | ~0 | Dutch replica (known limitation) |

**Total: ~16,300 / 25,000.** Projected with gating + standard locations: ~20,500.

---

## Known limitations

- **Replica environments** defeat single-frame analysis. No fix — documented edge case.
- **Nominatim rate limit** (1 req/sec). Fine for batch, needs caching for live use.
- **Common place names** may geocode incorrectly without language cross-reference.
- **500 samples / ~30 regions** — directional results, not definitive.

---

## Tech stack

| Layer | Tool | Why |
|-------|------|-----|
| Runtime | Python 3.11+ | Standard for analytics |
| Vision | Claude Sonnet | Best structured extraction from images |
| Geocoding | geopy + Nominatim | Free, sufficient volume |
| Spatial | GeoPandas + Shapely | Point-in-polygon, centroid ops |
| Dataframes | Polars | Faster than pandas, cleaner API |
| Storage | DuckDB | Analytical queries, zero infrastructure |
| App | Streamlit + pydeck | Fast analytical UI, built-in maps |
| HTTP | httpx | Async image collection |
| Analysis | scikit-learn, matplotlib, seaborn | Decision tree + charts |

---

## License

MIT
