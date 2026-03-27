# geolocator-ai

Multi-source image intelligence pipeline that extracts geographic features from Street View imagery using Claude's vision API, performs direct location inference, and stores structured results for analytical querying and iterative prompt refinement.

**Target:** 20,000+ per 5-round GeoGuessr game (out of 25,000 max)  
**Stack:** Python · Claude Sonnet · DuckDB · Polars · Streamlit

---

## Quick start

```bash
git clone https://github.com/yourname/geolocator-ai.git
cd geolocator-ai
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with your API keys

# Test on a single image
python evaluate.py path/to/screenshot.png

# Collect labeled images
python collect.py --locations 500 --output data/images

# Run full pipeline
python main.py --input data/images

# Analyze results
python analyze.py

# Launch the app
streamlit run app.py
```

### Required API keys (.env)

```
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_MAPS_API_KEY=AIza...
```

---

## What this does

Takes a Street View image and answers "where in the world is this?" through a structured pipeline:

1. **Extract + Infer** — Claude Sonnet analyzes the image in a single call, returning both ~20 structured geographic features AND a direct location guess with coordinates and reasoning
2. **Route** — If a geocodable place name was found in the image, Nominatim geocoding overrides Claude's guess for higher precision
3. **Store** — Log everything to DuckDB: extracted features, guessed city/country/coordinates, reasoning, actual coordinates, score
4. **Analyze** — Query DuckDB to identify systematic failure patterns and which features predict accuracy
5. **Refine** — Encode analytical findings back into the extraction prompt as corrective instructions
6. **Display** — Streamlit app with map, reasoning panel, and historical analysis

### The refinement loop

The pipeline's core methodology is iterative prompt refinement based on empirical error analysis:

```
Run images → analyze errors in DuckDB → identify failure patterns
→ add corrective instructions to prompt → re-run → measure improvement
```

Each iteration makes Claude's geolocation inference more accurate and consistent by directing its attention to the features that empirically matter most.

---

## Architecture

```
Screenshot → extractor.py (features + location guess in ONE Claude call)
           → router.py (geocode override if place name found)
           → geo.py (select best coordinates)
           → DuckDB (structured storage)
           → analyze.py (error patterns → prompt improvements)
           → Streamlit (interactive display)
```

---

## App

Streamlit interface for running the pipeline interactively and reviewing results.

### Live analysis view

Upload a screenshot or paste from clipboard. The app runs the full pipeline and displays:

- **Original image** — The uploaded screenshot
- **Result card** — Predicted city/country, coordinates, confidence
- **Map** — Guess pin (blue), actual pin if known (green), distance line
- **Reasoning panel** — Claude's reasoning, extracted features, which features drove the decision
- **Score** — GeoGuessr points if actual location is provided

### Historical analysis view

Browse and query all processed rounds from DuckDB:

- Filter by score range, country, path taken
- Sort by worst rounds to investigate failures
- View feature importance and confusion patterns
- Drill into any round to see its full pipeline trace

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
├── config.py               # API keys, thresholds
├── evaluate.py             # Single-image CLI debug tool
│
│   Pipeline modules
├── extractor.py            # Claude API → features + location guess
├── extraction_prompt.py    # Combined extraction + inference prompt
├── router.py               # Geocode override when place name found
├── geo.py                  # Coordinate selection
├── scoring.py              # Haversine distance + GeoGuessr points
│
│   Analytical (runs in background / post-hoc)
├── scorer.py               # Bayesian scoring — analytical purposes only
├── feature_region_map.py   # 127-feature knowledge base (reference)
├── centroids.json          # Coverage-weighted centroids (reference)
│
│   Post-hoc
├── calibrate.py            # Prompt refinement analysis
├── analyze.py              # Feature importance, confusion matrix
├── collect.py              # Street View API image scraper
├── sanity_check.py         # Quick DB diagnostics
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
| `guessed_city` | VARCHAR | Claude's city-level guess |
| `guessed_country` | VARCHAR | Claude's country guess |
| `guess_reasoning` | VARCHAR | Claude's one-sentence reasoning |
| `guess_confidence` | FLOAT | Claude's self-assessed confidence |
| `path_taken` | VARCHAR | `claude_direct` or `geocode` |
| `features_used` | VARCHAR[] | Which features drove the guess |
| `guess_lat/lng` | DOUBLE | Predicted coordinates |
| `actual_lat/lng` | DOUBLE | True coordinates (optional) |
| `distance_km` | FLOAT | Haversine error |
| `geoguessr_score` | INTEGER | 0–5,000 points |
| `raw_response` | TEXT | Full Claude response for debugging |

Full schema: [`docs/data_model.md`](docs/data_model.md)

---

## Example queries

```sql
-- Failure analysis: where does Claude get it wrong?
SELECT round_id, guessed_country, distance_km, guess_reasoning
FROM rounds WHERE geoguessr_score < 500
ORDER BY distance_km DESC;

-- Feature correlation with accuracy
SELECT unnest(features_used) AS feature,
       COUNT(*) AS times_used,
       ROUND(AVG(geoguessr_score)) AS avg_score
FROM rounds GROUP BY feature ORDER BY avg_score DESC;

-- Country-level accuracy
SELECT guessed_country, COUNT(*) AS rounds,
       ROUND(AVG(geoguessr_score)) AS avg_score,
       ROUND(AVG(distance_km)) AS avg_error_km
FROM rounds GROUP BY guessed_country ORDER BY avg_score DESC;

-- Text detection impact
SELECT 
    CASE WHEN language IS NOT NULL THEN 'text_found' ELSE 'no_text' END AS text_status,
    COUNT(*) AS rounds,
    ROUND(AVG(geoguessr_score)) AS avg_score
FROM rounds GROUP BY text_status;

-- High confidence failures (prompt refinement targets)
SELECT round_id, guess_confidence, geoguessr_score, 
       guessed_country, guess_reasoning
FROM rounds WHERE guess_confidence > 0.7 AND geoguessr_score < 1000;
```

---

## Key design decisions

**Single-call extraction + inference** — One Claude API call returns both structured features (for analysis) and a direct location guess (for scoring). Features provide the audit trail; inference provides the accuracy.

**Geocoding override** — When Claude reads a specific place name with high language confidence, Nominatim geocoding overrides Claude's coordinate guess for higher precision.

**Iterative prompt refinement** — Error analysis identifies systematic failure patterns (e.g., "confuses rural France with Russia 40% of the time"). Corrective instructions are added to the prompt ("hedgerows and narrow lanes indicate Western Europe, not Russia"). Each iteration measurably improves accuracy.

**Features for analysis, not scoring** — The structured features aren't used to compute the location guess. They're stored alongside the guess so you can analyze which features correlate with accuracy and which visual cues Claude relies on.

**Bayesian scorer as analytical tool** — The original Bayesian scoring approach was tested and found to degrade accuracy vs direct inference. It's kept running in the background to produce feature importance rankings and confusion matrices, but doesn't influence the actual guess.

---

## Performance history

| Version | Avg score | Median | Notes |
|---------|-----------|--------|-------|
| Manual test (5 rounds) | ~3,260 | — | Direct Claude analysis in chat |
| V1 Bayesian pipeline | 1,025 | 350 | 43% wrong continent, feature decomposition degraded inference |
| V2 Direct inference | *pending* | — | Expected 2,800–3,500+ based on manual test |

### Key finding

Decomposing Claude's visual understanding into discrete features and reassembling them via Bayesian likelihood multiplication performs significantly worse than letting Claude infer the location directly. The pipeline's value is in structuring the output for analysis and iteratively refining the prompt, not in replacing Claude's inference with manual scoring logic.

---

## Known limitations

- **Replica environments** (theme parks, cultural villages) produce geographically misleading features. No single-frame fix.
- **Rural images without text** (84% of collected dataset) rely entirely on environmental inference — accuracy ceiling is lower than urban images with signs.
- **Nominatim rate limit** (1 req/sec). Fine for batch, needs caching for live use.
- **607 training images** — directional results, not definitive. Expandable with additional collection runs.

---

## Tech stack

| Layer | Tool | Why |
|-------|------|-----|
| Runtime | Python 3.11+ | Standard for analytics |
| Vision + Inference | Claude Sonnet | Best VLM for structured extraction + geolocation |
| Geocoding | geopy + Nominatim | Free, sufficient volume |
| Spatial | GeoPandas + Shapely | Point-in-polygon, centroid ops |
| Dataframes | Polars | Faster than pandas, cleaner API |
| Storage | DuckDB | Analytical queries, zero infrastructure |
| App | Streamlit + pydeck | Fast analytical UI, built-in maps |
| HTTP | httpx | Async image collection |
| Analysis | scikit-learn, matplotlib, seaborn | Feature importance + charts |

---

## License

MIT
