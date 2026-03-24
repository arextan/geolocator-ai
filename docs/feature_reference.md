GEOLOCATOR-AI: 127 FEATURE REFERENCE
=====================================

This is the domain knowledge base. All 127 features belong in feature_region_map.py.
Claude extracts ~20 of these per image. The Bayesian scorer consults all 127.

Priority order for building the map:
1. Unique scripts (instant country ID)
2. License plate combos (instant country ID)
3. Driving side (eliminates half the world)
4. Road marking color (strong regional signal)
5. Vegetation biome (eliminates large zones)
6. Pole type (strong regional signal)
7. Diacritics/suffixes (within-Latin-script ID)
8. Soil color (geographic confirmation)
9. Architecture style (cultural confirmation)
10. Infrastructure quality (development tier proxy)

=====================================
TIER 1 — DETERMINISTIC (~15 features)
Near 100% confidence, identifies country instantly
=====================================

UNIQUE SCRIPTS
  Georgian script        → Georgia only
  Armenian script        → Armenia only
  Thai script            → Thailand only
  Korean script          → Korea only
  Japanese script        → Japan only (3 mixed scripts)
  Hebrew script          → Israel only
  Sinhala script         → Sri Lanka only

READABLE TEXT
  Exact words on signs   → Google Translate → language → region
  Business names         → country-specific franchises
  Phone number format    → country code visible on ads
  Highway shield text    → country/state specific

LICENSE PLATE
  Format + color combo   → often country unique
  Blue strip left side   → European Union
  Yellow rear/white front → UK, Australia, Netherlands
  Long thin plate        → Japan
  Yellow plate           → Colombia, Namibia, Israel, Oman

=====================================
TIER 2 — STRONG SINGLE SIGNALS (~12 features)
Eliminate 50-80% of world alone
=====================================

DRIVING SIDE
  Left hand traffic      → ~75 countries
  Right hand traffic     → ~120 countries

ROAD MARKINGS
  Yellow center line     → Americas + Japan/Korea/South Africa
  White center line      → Europe, Australia, most of world
  Dashed white edges     → Nordic (Sweden, Norway, Denmark, Iceland)
  Yellow edge + white center → South Africa, Botswana, Eswatini, Lesotho
  Thin center line       → Russia specific

HEMISPHERE SIGNALS
  Shadow tip direction   → N or S hemisphere
  Sun position in sky    → N or S hemisphere
  Satellite dish angle   → points toward equator
                           south = northern hemisphere
                           north = southern hemisphere
                           straight up = near equator

SCRIPT ON SIGNS (non-unique but strong)
  Cyrillic               → Russia/Eastern Europe/Central Asia
  Arabic                 → Middle East/North Africa (~22 countries)
  Devanagari             → India/Nepal
  Chinese                → China/Taiwan/Singapore

=====================================
TIER 3 — COMBINATORIAL (~25 features)
Need 2+ to be confident
=====================================

UTILITY POLES
  Wooden H-frame crossbar → North America, Japan
  Concrete curved neck    → Eastern/Western Europe
  Metal lattice           → Middle East, parts of Asia
  Bundled overhead chaos  → Southeast Asia, South Asia
  None visible            → underground cabling = wealthy urban

ROAD INFRASTRUCTURE
  Guardrail W-beam silver → North America standard
  Guardrail thrie-beam    → Europe common
  Guardrail rope/cable    → New Zealand, some Nordic
  Road quality excellent  → W. Europe, USA, Canada, Australia, Japan
  Road quality poor/cracked → Eastern Europe, parts of Africa/Asia
  Road width very wide    → USA, Canada, Turkey
  Road width very narrow  → Western Europe

HIGHWAY SIGNS
  Interstate blue/red shield → USA
  Trans-Canada maple leaf    → Canada
  BR-xxx prefix             → Brazil national highway
  SP/RJ/MG prefix           → Brazil state (state abbreviation)
  M/A/B road prefix         → Great Britain
  E-road green sign         → Europe (E + number)
  E-xx with dash            → Spain specifically
  SCT shield format         → Mexico federal
  Blue hexagon number       → Japan prefectural road
  Blue triangle number      → Japan national highway

STOP SIGN WORD
  STOP                   → USA, Canada, Australia, Philippines
  ARRET                  → Quebec Canada, France
  PARE                   → Brazil, Portugal
  ALTO                   → Mexico, Central America
  STOJ                   → Bosnia, Serbia, Croatia

=====================================
TIER 4 — ENVIRONMENTAL (~20 features)
Biome + geology
=====================================

VEGETATION BIOME
  Tropical rainforest    → equatorial band ±10° latitude
  Savanna/dry grass      → sub-Saharan Africa, Brazil cerrado, Australia
  Mediterranean scrub    → 30-45° latitude both hemispheres
  Boreal/taiga forest    → 50-70° North (Russia, Canada, Scandinavia)
  Temperate deciduous    → 40-60° North (Europe, NE USA, China, Japan)
  Dense evergreen        → Pacific Northwest, Nordic, Siberia
  Desert scrub           → 15-35° latitude bands
  Alpine treeline        → Andes, Alps, Himalayas, Rockies

SPECIFIC VEGETATION
  Eucalyptus             → Australia, Southern Africa, Mediterranean
  Palm trees tropical    → SE Asia, sub-Saharan Africa, Caribbean
  Birch trees            → Nordic, Russia, Eastern Europe, Pacific NW
  Baobab                 → sub-Saharan Africa (very strong signal)

SOIL COLOR
  Red laterite           → sub-Saharan Africa, SE Asia, Brazil north
  Black chernozem        → Ukraine, Russia steppe, US Great Plains
  Sandy pale             → Middle East, North Africa, Australia outback
  Dark volcanic          → Iceland, Hawaii, Indonesia
  Rocky grey             → Alpine regions, Iceland

GEOLOGY/TERRAIN
  Flat completely        → Netherlands, Denmark, Bangladesh, US plains
  Flat with escarpments  → South Africa, parts of Brazil
  Andean mountain        → Peru, Bolivia, Ecuador, Chile, Colombia
  Fjord coastline        → Norway, New Zealand south

=====================================
TIER 5 — ARCHITECTURE AND INFRASTRUCTURE (~15 features)
=====================================

BUILDING STYLE
  Soviet bloc flats      → Former USSR + Warsaw Pact
  Colonial Spanish       → Latin America
  Colonial Portuguese    → Brazil, Mozambique, Angola
  Colonial British       → India, Kenya, Australia, Caribbean
  Traditional wooden     → Nordic, Pacific Northwest, rural Japan
  Mud brick/adobe        → North Africa, Middle East, Andean
  Corrugated metal roofs → sub-Saharan Africa, Pacific Islands
  White cube flat roof   → Mediterranean, Middle East
  Terracotta roof tiles  → Mediterranean Europe, Latin America

INFRASTRUCTURE QUALITY PROXY
  Very high              → W. Europe, USA, Canada, Japan, Australia, Singapore
  Medium                 → Eastern Europe, Brazil cities, South Africa
  Low                    → rural developing world
  Vehicle age old        → developing world indicator

STREET FURNITURE
  Bus stop design        → country specific styles
  Bollard shape/color    → France yellow, Poland black/white, etc
  Mailbox color/style    → country specific
  Street lighting style  → varies by region

=====================================
TIER 6 — LATIN SCRIPT DISCRIMINATORS (~30 features)
=====================================

SPECIAL CHARACTERS (DIACRITICS)
  ø å æ                  → Denmark, Norway, Faroe Islands
  ö ä ü                  → Germany, Sweden, Finland, Austria, Hungary
  ñ                      → Spain, Latin America
  ç ğ ş ı               → Turkey
  ă â î ș ț             → Romania
  ę ą ś ź ż ł           → Poland
  č š ž                  → Czech, Slovak, Slovenian, Croatian, Bosnian
  ß                      → Germany, Austria, Switzerland
  ã õ ê ô               → Portugal, Brazil
  þ ð                    → Iceland only (unique)

WORD PATTERNS
  High consonant clusters → Polish, Czech, Slovak
  Long compound words    → German, Finnish, Dutch, Norwegian
  Vowel endings dominant → Italian, Spanish, Portuguese, Romanian
  Short words apostrophes → French

SUFFIXES
  -nen -inen -järvi -mäki → Finland
  -vik -berg -fjord -dal  → Nordic
  -burg -bach -dorf -heim → German speaking
  -escu -anu              → Romania
  -ovic -ic               → Balkan

BILINGUAL COMBINATIONS
  Latin + Thai           → Thailand
  Latin + Arabic         → Middle East/N.Africa
  Latin + Devanagari     → India/Nepal
  Latin + Sinhala        → Sri Lanka
  Latin + Welsh          → Wales specifically
  Latin + Maori          → New Zealand
  Latin + French         → Canada Quebec border/Belgium
  Latin + Afrikaans      → South Africa
  Latin + Swahili        → East Africa

=====================================
TIER 7 — META AND GOOGLE CAMERA SIGNALS (~10 features)
=====================================

IMAGE QUALITY
  Blurry/low resolution  → older USA or Australia coverage
  Very old camera gen    → certain Eastern European countries

CAMERA POSITION SIGNALS
  Antenna visible        → driving side confirmation
  Mirror shadow visible  → driving side confirmation
  Steering wheel visible → driving side confirmation
  Camera height          → varies by Street View generation

COVERAGE DENSITY SIGNAL
  Sparse/trekker imagery → Mongolia, Bhutan, rare countries
  Dense urban coverage   → W. Europe, USA, Japan
  Mostly rural roads     → Russia, Brazil interior

SUN/SHADOW ANALYSIS
  Shadow length very long → high latitude 50-70°N/S
  Shadow length medium   → mid latitude 30-50°
  Shadow length short    → low latitude 10-30°
  Shadow = zero          → equatorial ±10°

=====================================
FEATURE COUNT SUMMARY
=====================================

Tier 1 — Deterministic signals:      ~15 features
Tier 2 — Strong single signals:      ~12 features
Tier 3 — Combinatorial signals:      ~25 features
Tier 4 — Environmental signals:      ~20 features
Tier 5 — Architecture signals:       ~15 features
Tier 6 — Latin discriminators:       ~30 features
Tier 7 — Meta/camera signals:        ~10 features

Total:                               ~127 features

Realistically extractable by Claude per image: 8-15 features
Features needed for confident guess: 3-4 minimum

=====================================
NOTES
=====================================

- Tier 7 features (shadow angles, camera height, satellite dish tilt) 
  should NOT be in the extraction prompt — they hallucinate. They are 
  included here for completeness of the knowledge base only.

- The extraction prompt asks for ~20 features. The remaining ~107 
  features serve as reference material in feature_region_map.py 
  that the Bayesian scorer consults.

- After running 500 images, feature selection will determine which 
  of the 20 extracted features actually carry predictive weight. 
  Features with >85% null rate or low importance scores get dropped 
  from the prompt and replaced with better candidates.
