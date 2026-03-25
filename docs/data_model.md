# Data model

DuckDB schema and example analytical queries for the GeoGuessr pipeline.

---

## Schema

One table, one row per round.

```sql
CREATE TABLE rounds (
    -- Identifiers
    round_id            VARCHAR PRIMARY KEY,
    timestamp           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    image_files         VARCHAR[],

    -- Pass 1: Deterministic features
    script              VARCHAR,        -- latin, cyrillic, arabic, thai, hangul, null
    language            VARCHAR,        -- spanish, french, null
    language_confidence FLOAT,          -- 0.0–1.0, null if no language
    readable_text       VARCHAR[],      -- array of text strings found
    place_name          VARCHAR,        -- geocodable place name or null
    route_number        VARCHAR,        -- road/route number or null
    plate_format        VARCHAR,        -- eu_long, latin_american, us_short, null
    driving_side        VARCHAR,        -- left, right, null
    speed_sign_format   VARCHAR,        -- red_circle, white_rectangle, null
    domain_extension    VARCHAR,        -- .br, .co.za, null
    currency_symbol     VARCHAR,        -- R$, ₹, null

    -- Pass 2: Probabilistic features
    biome               VARCHAR,        -- tropical, temperate, boreal, desert, null
    vegetation_specific VARCHAR,        -- monterey_cypress, baobab, null
    sky_condition       VARCHAR,        -- clear, overcast_grey, tropical_cumulus
    terrain             VARCHAR,        -- flat, rolling_hills, mountainous, coastal
    soil_color          VARCHAR,        -- red_laterite, tan_brown, black, sandy, null
    architecture        VARCHAR,        -- dutch_canal, brutalist_colonial, null
    pole_type           VARCHAR,        -- wooden_h_frame, concrete_curved, null
    road_surface        VARCHAR,        -- asphalt_good, asphalt_poor, dirt, cobble
    road_markings       VARCHAR,        -- yellow_center, white_center, none
    infrastructure_quality VARCHAR,     -- high, medium, low

    -- Routing and scoring
    path_taken          VARCHAR,        -- geocode, bayesian
    confidence_score    FLOAT,          -- top region posterior probability
    confidence_tier     VARCHAR,        -- high, medium, low
    top_regions         JSON,           -- [{"region":"peru","score":0.42}, ...]
    features_used       VARCHAR[],      -- which features drove the decision

    -- Coordinates
    guess_lat           DOUBLE,
    guess_lng           DOUBLE,
    actual_lat          DOUBLE,
    actual_lng          DOUBLE,

    -- Results
    distance_km         FLOAT,          -- haversine distance
    geoguessr_score     INTEGER,        -- 0–5,000

    -- Debug
    raw_response        TEXT,           -- full Claude API response
    extraction_failed   BOOLEAN DEFAULT FALSE
);
```

---

## Example queries

### Performance overview

```sql
SELECT
    COUNT(*) AS total_rounds,
    ROUND(AVG(geoguessr_score)) AS avg_score,
    ROUND(AVG(distance_km), 0) AS avg_distance_km,
    SUM(geoguessr_score) AS total_score,
    SUM(CASE WHEN geoguessr_score >= 4500 THEN 1 ELSE 0 END) AS excellent_rounds,
    SUM(CASE WHEN geoguessr_score < 1000 THEN 1 ELSE 0 END) AS bad_rounds
FROM rounds
WHERE NOT extraction_failed;
```

### Path comparison

```sql
SELECT
    path_taken,
    COUNT(*) AS rounds,
    ROUND(AVG(geoguessr_score)) AS avg_score,
    ROUND(AVG(distance_km), 1) AS avg_distance_km,
    MIN(geoguessr_score) AS worst,
    MAX(geoguessr_score) AS best
FROM rounds
WHERE NOT extraction_failed
GROUP BY path_taken;
```

### Confidence tier calibration check

```sql
SELECT
    confidence_tier,
    COUNT(*) AS rounds,
    ROUND(AVG(geoguessr_score)) AS avg_score,
    ROUND(STDDEV(geoguessr_score)) AS score_stddev,
    ROUND(AVG(distance_km), 0) AS avg_error_km
FROM rounds
WHERE path_taken = 'bayesian' AND NOT extraction_failed
GROUP BY confidence_tier
ORDER BY avg_score DESC;
```

### Feature effectiveness

```sql
SELECT
    unnest(features_used) AS feature,
    COUNT(*) AS times_used,
    ROUND(AVG(geoguessr_score)) AS avg_score_when_used,
    ROUND(AVG(distance_km), 0) AS avg_error_when_used
FROM rounds
WHERE NOT extraction_failed
GROUP BY feature
ORDER BY avg_score_when_used DESC;
```

### Worst rounds (investigate these)

```sql
SELECT
    round_id,
    actual_lat, actual_lng,
    guess_lat, guess_lng,
    distance_km,
    geoguessr_score,
    confidence_tier,
    confidence_score,
    path_taken,
    features_used,
    language,
    biome,
    architecture
FROM rounds
WHERE geoguessr_score < 1000 AND NOT extraction_failed
ORDER BY distance_km DESC;
```

### High confidence failures (calibration bugs)

```sql
SELECT
    round_id,
    confidence_score,
    confidence_tier,
    geoguessr_score,
    distance_km,
    features_used,
    top_regions
FROM rounds
WHERE confidence_tier = 'high'
  AND geoguessr_score < 2500
  AND NOT extraction_failed
ORDER BY distance_km DESC;
```

### Region-level error analysis

```sql
SELECT
    top_regions->>'$[0].region' AS predicted_region,
    COUNT(*) AS rounds,
    ROUND(AVG(distance_km), 0) AS avg_error_km,
    ROUND(AVG(geoguessr_score)) AS avg_score,
    SUM(CASE WHEN geoguessr_score < 2000 THEN 1 ELSE 0 END) AS bad_rounds
FROM rounds
WHERE path_taken = 'bayesian' AND NOT extraction_failed
GROUP BY predicted_region
ORDER BY avg_error_km DESC;
```

### Feature null rate (which features are actually extractable?)

```sql
SELECT
    'script' AS feature, ROUND(100.0 * COUNT(*) FILTER (WHERE script IS NOT NULL) / COUNT(*), 1) AS fill_pct FROM rounds
UNION ALL SELECT
    'language', ROUND(100.0 * COUNT(*) FILTER (WHERE language IS NOT NULL) / COUNT(*), 1) FROM rounds
UNION ALL SELECT
    'place_name', ROUND(100.0 * COUNT(*) FILTER (WHERE place_name IS NOT NULL) / COUNT(*), 1) FROM rounds
UNION ALL SELECT
    'biome', ROUND(100.0 * COUNT(*) FILTER (WHERE biome IS NOT NULL) / COUNT(*), 1) FROM rounds
UNION ALL SELECT
    'architecture', ROUND(100.0 * COUNT(*) FILTER (WHERE architecture IS NOT NULL) / COUNT(*), 1) FROM rounds
UNION ALL SELECT
    'soil_color', ROUND(100.0 * COUNT(*) FILTER (WHERE soil_color IS NOT NULL) / COUNT(*), 1) FROM rounds
UNION ALL SELECT
    'pole_type', ROUND(100.0 * COUNT(*) FILTER (WHERE pole_type IS NOT NULL) / COUNT(*), 1) FROM rounds
ORDER BY fill_pct DESC;
```

This query is critical for feature selection — if a feature is null 90% of the time, consider dropping it from the extraction prompt.
