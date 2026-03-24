import os
from dotenv import load_dotenv

load_dotenv()

# API keys
ANTHROPIC_API_KEY: str = os.environ["ANTHROPIC_API_KEY"]
GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")

# Model
CLAUDE_MODEL: str = "claude-sonnet-4-6"

# Confidence gate thresholds
# Scores above HIGH_THRESHOLD → use sub-region centroid
# Scores above MEDIUM_THRESHOLD → use country centroid
# Below medium → biome-aware hedge (low tier)
HIGH_CONFIDENCE_THRESHOLD: float = 0.65
MEDIUM_CONFIDENCE_THRESHOLD: float = 0.35

# Geocoding
NOMINATIM_USER_AGENT: str = "geolocator-ai/1.0"
NOMINATIM_RATE_LIMIT_SECONDS: float = 1.0  # 1 req/sec hard limit

# GeoGuessr scoring decay constant (validated against known scores)
GEOGUESSR_DECAY_KM: float = 1492.7
GEOGUESSR_MAX_SCORE: int = 5000
