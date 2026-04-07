"""
Feature-region likelihood map for Bayesian geolocation scoring.

Structure:
    FEATURE_REGION_MAP[region]["features"][feature_name][value] = P(value | region)

Priors are coverage-weighted estimates of each region's share of GeoGuessr world.
Feature likelihoods are P(observed_value | region).
Values not listed in a region's feature dict receive DEFAULT_LIKELIHOOD (fail-open).

Regions (18): japan, south_korea, china, thailand, southeast_asia,
india_subcontinent, middle_east, north_africa, sub_saharan_africa,
south_africa, russia_central_asia, eastern_europe, western_europe,
nordic, brazil, latin_america, usa_canada, australia_new_zealand

Build priority (from feature_reference.md):
1. Unique scripts         — instant country ID
2. License plate format   — instant country ID
3. Driving side           — eliminates half the world
4. Road marking color     — strong regional signal
5. Vegetation biome       — eliminates large zones
6. Pole type              — strong regional signal
7. Language/diacritics    — within-Latin-script ID
8. Soil color             — geographic confirmation
9. Architecture style     — cultural confirmation
10. Infrastructure quality — development tier proxy
"""

DEFAULT_LIKELIHOOD: float = 0.02

FEATURE_REGION_MAP: dict[str, dict] = {

    # -------------------------------------------------------------------------
    # EAST ASIA
    # -------------------------------------------------------------------------

    "japan": {
        "prior": 0.06,
        "lat": 36.2,
        "lng": 138.3,
        "features": {
            "script": {
                "japanese": 0.96, "latin": 0.03, "chinese": 0.01,
            },
            "language": {
                "japanese": 0.96, "english": 0.02,
            },
            "driving_side": {
                "left": 0.97, "right": 0.03,
            },
            "road_markings": {
                "yellow_center": 0.82, "white_center": 0.14, "yellow_curb": 0.03,
            },
            "biome": {
                "temperate_deciduous": 0.40, "subtropical_coastal": 0.28,
                "boreal": 0.12, "alpine": 0.10, "tropical_rainforest": 0.05,
            },
            "pole_type": {
                "wooden_h_frame": 0.68, "concrete_curved": 0.20,
                "none_visible": 0.08, "metal_lattice": 0.04,
            },
            "architecture": {
                "traditional_wooden": 0.28, "modern_glass": 0.35,
                "brutalist_colonial_mix": 0.15, "terracotta_tiles": 0.05,
            },
            "infrastructure_quality": {
                "high": 0.90, "medium": 0.09, "low": 0.01,
            },
            "plate_format": {
                "japanese_narrow": 0.95,
            },
        },
    },

    "south_korea": {
        "prior": 0.03,
        "lat": 36.5,
        "lng": 127.9,
        "features": {
            "script": {
                "hangul": 0.95, "latin": 0.03, "chinese": 0.02,
            },
            "language": {
                "korean": 0.96, "english": 0.02,
            },
            "driving_side": {
                "right": 0.99, "left": 0.01,
            },
            "road_markings": {
                "yellow_center": 0.80, "white_center": 0.17,
            },
            "biome": {
                "temperate_deciduous": 0.62, "subtropical_coastal": 0.18,
                "boreal": 0.12, "alpine": 0.05,
            },
            "pole_type": {
                "concrete_curved": 0.45, "bundled_overhead": 0.28,
                "none_visible": 0.15, "metal_lattice": 0.10,
            },
            "infrastructure_quality": {
                "high": 0.78, "medium": 0.19, "low": 0.03,
            },
        },
    },

    "china": {
        "prior": 0.03,
        "lat": 35.0,
        "lng": 105.0,
        "features": {
            "script": {
                "chinese": 0.92, "latin": 0.05, "arabic": 0.02,
            },
            "language": {
                "chinese": 0.93, "english": 0.03,
            },
            "driving_side": {
                "right": 0.99, "left": 0.01,
            },
            "road_markings": {
                "yellow_center": 0.65, "white_center": 0.30,
            },
            "biome": {
                "temperate_deciduous": 0.33, "subtropical_coastal": 0.20,
                "desert": 0.15, "tropical_rainforest": 0.10, "boreal": 0.10,
            },
            "pole_type": {
                "concrete_curved": 0.40, "bundled_overhead": 0.28,
                "metal_lattice": 0.20, "wooden_h_frame": 0.05,
            },
            "architecture": {
                "modern_glass": 0.30, "soviet_bloc": 0.15,
                "traditional_wooden": 0.10,
            },
            "infrastructure_quality": {
                "high": 0.42, "medium": 0.45, "low": 0.13,
            },
        },
    },

    # -------------------------------------------------------------------------
    # SOUTHEAST ASIA
    # -------------------------------------------------------------------------

    "thailand": {
        "prior": 0.03,
        "lat": 15.0,
        "lng": 101.0,
        "features": {
            "script": {
                "thai": 0.92, "latin": 0.06, "chinese": 0.02,
            },
            "language": {
                "thai": 0.93, "english": 0.04,
            },
            "driving_side": {
                "left": 0.97, "right": 0.03,
            },
            "road_markings": {
                "white_center": 0.55, "yellow_center": 0.40,
            },
            "biome": {
                "tropical_rainforest": 0.45, "subtropical_coastal": 0.28,
                "savanna": 0.15,
            },
            "pole_type": {
                "bundled_overhead": 0.50, "concrete_curved": 0.28,
                "metal_lattice": 0.15,
            },
            "infrastructure_quality": {
                "medium": 0.55, "high": 0.20, "low": 0.25,
            },
        },
    },

    "southeast_asia": {
        "prior": 0.06,
        "lat": 8.0,
        "lng": 112.0,
        "features": {
            "script": {
                "latin": 0.65, "chinese": 0.10, "arabic": 0.10, "thai": 0.05,
            },
            "language": {
                "vietnamese": 0.28, "indonesian": 0.22, "malay": 0.15,
                "tagalog": 0.14, "khmer": 0.05, "burmese": 0.04,
            },
            "driving_side": {
                "right": 0.60, "left": 0.40,
            },
            "road_markings": {
                "yellow_center": 0.45, "white_center": 0.50,
            },
            "biome": {
                "tropical_rainforest": 0.60, "subtropical_coastal": 0.25,
                "savanna": 0.10,
            },
            "pole_type": {
                "bundled_overhead": 0.55, "concrete_curved": 0.25,
                "metal_lattice": 0.14,
            },
            "infrastructure_quality": {
                "medium": 0.50, "low": 0.35, "high": 0.15,
            },
            "soil_color": {
                "red_laterite": 0.35,
            },
        },
    },

    # -------------------------------------------------------------------------
    # SOUTH ASIA
    # -------------------------------------------------------------------------

    "india_subcontinent": {
        "prior": 0.05,
        "lat": 20.0,
        "lng": 78.0,
        "features": {
            "script": {
                "devanagari": 0.52, "latin": 0.20, "arabic": 0.08,
                "sinhala": 0.05, "bengali": 0.06,
            },
            "language": {
                "hindi": 0.38, "english": 0.20, "bengali": 0.10,
                "urdu": 0.08, "tamil": 0.05, "nepali": 0.04,
            },
            "driving_side": {
                "left": 0.97, "right": 0.03,
            },
            "road_markings": {
                "white_center": 0.65, "yellow_center": 0.28,
            },
            "biome": {
                "tropical_rainforest": 0.25, "savanna": 0.28,
                "desert": 0.20, "temperate_deciduous": 0.12,
            },
            "pole_type": {
                "bundled_overhead": 0.48, "metal_lattice": 0.25,
                "concrete_curved": 0.15, "wooden_h_frame": 0.08,
            },
            "infrastructure_quality": {
                "low": 0.45, "medium": 0.45, "high": 0.10,
            },
            "architecture": {
                "corrugated_metal": 0.20, "mud_brick": 0.15,
                "colonial_british": 0.12,
            },
        },
    },

    # -------------------------------------------------------------------------
    # MIDDLE EAST & NORTH AFRICA
    # -------------------------------------------------------------------------

    "middle_east": {
        "prior": 0.02,
        "lat": 24.0,
        "lng": 45.0,
        "features": {
            "script": {
                "arabic": 0.78, "latin": 0.20,
            },
            "language": {
                "arabic": 0.75, "english": 0.10, "farsi": 0.08, "urdu": 0.04,
            },
            "driving_side": {
                "right": 0.95, "left": 0.05,
            },
            "road_markings": {
                "white_center": 0.80, "yellow_center": 0.15,
            },
            "biome": {
                "desert": 0.72, "subtropical_coastal": 0.15, "mediterranean": 0.10,
            },
            "soil_color": {
                "sandy_pale": 0.70, "rocky_grey": 0.15,
            },
            "infrastructure_quality": {
                "high": 0.42, "medium": 0.45, "low": 0.13,
            },
            "architecture": {
                "white_cube": 0.35, "modern_glass": 0.25, "mud_brick": 0.15,
            },
        },
    },

    "north_africa": {
        "prior": 0.02,
        "lat": 30.0,
        "lng": 10.0,
        "features": {
            "script": {
                "arabic": 0.70, "latin": 0.25,
            },
            "language": {
                "arabic": 0.65, "french": 0.20, "berber": 0.08,
            },
            "driving_side": {
                "right": 0.97, "left": 0.03,
            },
            "road_markings": {
                "white_center": 0.80, "yellow_center": 0.15,
            },
            "biome": {
                "desert": 0.58, "mediterranean": 0.25, "savanna": 0.12,
            },
            "soil_color": {
                "sandy_pale": 0.55, "rocky_grey": 0.20, "red_laterite": 0.10,
            },
            "infrastructure_quality": {
                "medium": 0.50, "low": 0.35, "high": 0.15,
            },
        },
    },

    # -------------------------------------------------------------------------
    # SUB-SAHARAN AFRICA
    # -------------------------------------------------------------------------

    "sub_saharan_africa": {
        "prior": 0.05,
        "lat": -3.0,
        "lng": 25.0,
        "features": {
            "script": {
                "latin": 0.94, "arabic": 0.04,
            },
            "language": {
                "english": 0.30, "french": 0.25, "swahili": 0.15,
                "portuguese": 0.08, "amharic": 0.04,
            },
            "driving_side": {
                "right": 0.70, "left": 0.30,
            },
            "road_markings": {
                "white_center": 0.70, "yellow_center": 0.25,
            },
            "biome": {
                "savanna": 0.50, "tropical_rainforest": 0.28, "desert": 0.10,
            },
            "infrastructure_quality": {
                "low": 0.55, "medium": 0.38, "high": 0.07,
            },
            "soil_color": {
                "red_laterite": 0.50, "sandy_pale": 0.20, "black_chernozem": 0.08,
            },
            "architecture": {
                "corrugated_metal": 0.40, "mud_brick": 0.20,
            },
            "pole_type": {
                "metal_lattice": 0.35, "bundled_overhead": 0.28,
                "concrete_curved": 0.20, "wooden_h_frame": 0.10,
            },
        },
    },

    "south_africa": {
        "prior": 0.02,
        "lat": -28.5,
        "lng": 25.0,
        "features": {
            "script": {
                "latin": 0.97,
            },
            "language": {
                "english": 0.45, "afrikaans": 0.25, "zulu": 0.10,
                "xhosa": 0.06,
            },
            "driving_side": {
                "left": 0.97, "right": 0.03,
            },
            "road_markings": {
                # yellow edge + white center is the South Africa standard
                "yellow_edge_white_center": 0.55, "white_center": 0.30,
                "yellow_center": 0.10,
            },
            "biome": {
                "savanna": 0.40, "mediterranean": 0.22,
                "temperate_deciduous": 0.18, "desert": 0.12,
            },
            "infrastructure_quality": {
                "medium": 0.52, "high": 0.30, "low": 0.18,
            },
            "soil_color": {
                "red_laterite": 0.25, "sandy_pale": 0.22, "rocky_grey": 0.18,
            },
            "vegetation_specific": {
                "eucalyptus": 0.18,
            },
        },
    },

    # -------------------------------------------------------------------------
    # EUROPE & RUSSIA
    # -------------------------------------------------------------------------

    "russia_central_asia": {
        "prior": 0.08,
        "lat": 57.0,
        "lng": 70.0,
        "features": {
            "script": {
                "cyrillic": 0.88, "latin": 0.08, "arabic": 0.02,
            },
            "language": {
                "russian": 0.72, "kazakh": 0.08, "ukrainian": 0.06,
                "uzbek": 0.04,
            },
            "driving_side": {
                "right": 0.99, "left": 0.01,
            },
            "road_markings": {
                "white_center": 0.72, "yellow_center": 0.15,
                "nordic_dashed": 0.08,
            },
            "biome": {
                "boreal": 0.35, "temperate_deciduous": 0.25,
                "desert": 0.18, "tundra": 0.10,
            },
            "infrastructure_quality": {
                "medium": 0.50, "low": 0.35, "high": 0.15,
            },
            "architecture": {
                "soviet_bloc": 0.50, "traditional_wooden": 0.20,
            },
            "pole_type": {
                "concrete_curved": 0.35, "wooden_h_frame": 0.30,
                "metal_lattice": 0.20,
            },
            "soil_color": {
                "black_chernozem": 0.22, "sandy_pale": 0.18, "rocky_grey": 0.10,
            },
        },
    },

    "eastern_europe": {
        "prior": 0.07,
        "lat": 50.0,
        "lng": 22.0,
        "features": {
            "script": {
                "latin": 0.78, "cyrillic": 0.22,
            },
            "language": {
                "polish": 0.18, "romanian": 0.15, "czech": 0.10,
                "hungarian": 0.10, "bulgarian": 0.08, "serbian": 0.06,
                "ukrainian": 0.06, "croatian": 0.05,
            },
            "driving_side": {
                "right": 0.99, "left": 0.01,
            },
            "road_markings": {
                "white_center": 0.85, "yellow_center": 0.08,
            },
            "biome": {
                "temperate_deciduous": 0.65, "boreal": 0.15, "mediterranean": 0.10,
            },
            "infrastructure_quality": {
                "medium": 0.60, "high": 0.28, "low": 0.12,
            },
            "architecture": {
                "soviet_bloc": 0.30, "terracotta_tiles": 0.15,
                "traditional_wooden": 0.10,
            },
            "pole_type": {
                "concrete_curved": 0.50, "metal_lattice": 0.18,
                "wooden_h_frame": 0.12,
            },
            "plate_format": {
                "eu_rectangle": 0.80,
            },
        },
    },

    "western_europe": {
        "prior": 0.17,
        "lat": 48.0,
        "lng": 8.0,
        "features": {
            "script": {
                "latin": 0.97, "arabic": 0.02,
            },
            "language": {
                "french": 0.20, "german": 0.18, "spanish": 0.15,
                "italian": 0.12, "dutch": 0.08, "portuguese": 0.06,
                "english": 0.10, "catalan": 0.03,
            },
            "driving_side": {
                # UK + Ireland drive left; rest drive right
                "right": 0.85, "left": 0.15,
            },
            "road_markings": {
                "white_center": 0.85, "yellow_center": 0.08,
                "nordic_dashed": 0.04,
            },
            "biome": {
                "temperate_deciduous": 0.55, "mediterranean": 0.25,
                "boreal": 0.08,
            },
            "infrastructure_quality": {
                "high": 0.80, "medium": 0.18, "low": 0.02,
            },
            "architecture": {
                "terracotta_tiles": 0.22, "traditional_wooden": 0.15,
                "white_cube": 0.10, "modern_glass": 0.20,
            },
            "pole_type": {
                "concrete_curved": 0.42, "none_visible": 0.22,
                "wooden_h_frame": 0.12, "metal_lattice": 0.12,
            },
            "plate_format": {
                "eu_rectangle": 0.85, "uk_rectangle": 0.10,
            },
        },
    },

    "nordic": {
        "prior": 0.03,
        "lat": 62.0,
        "lng": 15.0,
        "features": {
            "script": {
                "latin": 0.97,
            },
            "language": {
                "swedish": 0.28, "norwegian": 0.25, "danish": 0.18,
                "finnish": 0.18, "icelandic": 0.08,
            },
            "driving_side": {
                "right": 0.99, "left": 0.01,
            },
            "road_markings": {
                # Nordic dashed white edges are the key discriminator
                "nordic_dashed": 0.40, "white_center": 0.52,
                "yellow_center": 0.05,
            },
            "biome": {
                "boreal": 0.50, "temperate_deciduous": 0.25, "tundra": 0.15,
            },
            "infrastructure_quality": {
                "high": 0.88, "medium": 0.11, "low": 0.01,
            },
            "architecture": {
                "traditional_wooden": 0.40, "modern_glass": 0.25,
            },
            "pole_type": {
                "none_visible": 0.35, "wooden_h_frame": 0.28,
                "concrete_curved": 0.25,
            },
            "vegetation_specific": {
                "birch": 0.40, "evergreen": 0.28,
            },
            "plate_format": {
                "eu_rectangle": 0.80,
            },
        },
    },

    # -------------------------------------------------------------------------
    # AMERICAS
    # -------------------------------------------------------------------------

    "brazil": {
        "prior": 0.07,
        "lat": -14.0,
        "lng": -50.0,
        "features": {
            "script": {
                "latin": 0.97,
            },
            "language": {
                "portuguese": 0.97, "english": 0.02,
            },
            "driving_side": {
                "right": 0.99, "left": 0.01,
            },
            "road_markings": {
                "yellow_center": 0.80, "white_center": 0.17,
                "yellow_curb": 0.02,
            },
            "biome": {
                "tropical_rainforest": 0.30, "savanna": 0.28,
                "subtropical_coastal": 0.20, "temperate_deciduous": 0.10,
            },
            "infrastructure_quality": {
                "medium": 0.55, "high": 0.25, "low": 0.20,
            },
            "soil_color": {
                "red_laterite": 0.40, "black_chernozem": 0.10,
            },
            "architecture": {
                "colonial_portuguese": 0.28, "brutalist_colonial_mix": 0.25,
                "modern_glass": 0.15, "corrugated_metal": 0.10,
            },
            "pole_type": {
                "concrete_curved": 0.38, "wooden_h_frame": 0.22,
                "metal_lattice": 0.20,
            },
        },
    },

    "latin_america": {
        "prior": 0.07,
        "lat": -5.0,
        "lng": -70.0,
        "features": {
            "script": {
                "latin": 0.97,
            },
            "language": {
                "spanish": 0.92, "english": 0.04, "portuguese": 0.02,
            },
            "driving_side": {
                "right": 0.97, "left": 0.03,
            },
            "road_markings": {
                "yellow_center": 0.65, "white_center": 0.30,
                "yellow_curb": 0.03,
            },
            "biome": {
                "tropical_rainforest": 0.20, "savanna": 0.15,
                "desert": 0.15, "mediterranean": 0.14,
                "temperate_deciduous": 0.14, "alpine": 0.10,
            },
            "infrastructure_quality": {
                "medium": 0.50, "low": 0.35, "high": 0.15,
            },
            "architecture": {
                "colonial_spanish": 0.40, "brutalist_colonial_mix": 0.20,
                "mud_brick": 0.10,
            },
            "soil_color": {
                "red_laterite": 0.20, "sandy_pale": 0.15,
            },
        },
    },

    "usa_canada": {
        "prior": 0.13,
        "lat": 40.0,
        "lng": -95.0,
        "features": {
            "script": {
                "latin": 0.97,
            },
            "language": {
                "english": 0.88, "french": 0.08, "spanish": 0.03,
            },
            "driving_side": {
                "right": 0.99, "left": 0.01,
            },
            "road_markings": {
                "yellow_center": 0.85, "white_center": 0.12,
            },
            "biome": {
                "temperate_deciduous": 0.35, "boreal": 0.18,
                "desert": 0.12, "mediterranean": 0.10, "savanna": 0.05,
            },
            "infrastructure_quality": {
                "high": 0.68, "medium": 0.28, "low": 0.04,
            },
            "architecture": {
                "traditional_wooden": 0.25, "modern_glass": 0.30,
                "colonial_british": 0.10,
            },
            "pole_type": {
                "wooden_h_frame": 0.65, "none_visible": 0.15,
                "concrete_curved": 0.12,
            },
            "plate_format": {
                "us_rectangle": 0.88, "canadian_rectangle": 0.08,
            },
        },
    },

    # -------------------------------------------------------------------------
    # OCEANIA
    # -------------------------------------------------------------------------

    "australia_new_zealand": {
        "prior": 0.04,
        "lat": -27.0,
        "lng": 134.0,
        "features": {
            "script": {
                "latin": 0.97,
            },
            "language": {
                "english": 0.97, "maori": 0.02,
            },
            "driving_side": {
                "left": 0.99, "right": 0.01,
            },
            "road_markings": {
                "white_center": 0.80, "yellow_center": 0.15,
            },
            "biome": {
                "savanna": 0.28, "desert": 0.25, "mediterranean": 0.20,
                "temperate_deciduous": 0.15,
            },
            "infrastructure_quality": {
                "high": 0.72, "medium": 0.25, "low": 0.03,
            },
            "vegetation_specific": {
                "eucalyptus": 0.55, "palm": 0.10,
            },
            "architecture": {
                "traditional_wooden": 0.25, "colonial_british": 0.20,
                "modern_glass": 0.20,
            },
            "pole_type": {
                "wooden_h_frame": 0.40, "concrete_curved": 0.25,
                "none_visible": 0.20,
            },
        },
    },
}

# Coverage-weighted hedge centroids by biome.
# Used when confidence_tier == "low" — points to the highest-coverage
# location for each biome rather than the geographic midpoint.
BIOME_HEDGE_CENTROIDS: dict[str | None, tuple[float, float]] = {
    "tropical_rainforest":  (-3.0,  113.0),  # Indonesia/Borneo — peak SE Asia coverage
    "subtropical_coastal":  (23.0,  113.0),  # SE China coast
    "savanna":              (-15.0,  30.0),  # Zimbabwe/Zambia
    "mediterranean":        (37.0,   14.0),  # Sicily / S. Italy
    "temperate_deciduous":  (48.0,   15.0),  # Central Europe
    "boreal":               (60.0,   65.0),  # W. Siberia / Scandinavia
    "desert":               (25.0,   30.0),  # Egypt / Sudan
    "alpine":               (45.0,   10.0),  # Alps
    "tundra":               (67.0,   30.0),  # N. Scandinavia
    None:                   (20.0,   20.0),  # Unknown — central Africa fallback
}
