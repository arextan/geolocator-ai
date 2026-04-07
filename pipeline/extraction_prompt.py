# Extraction prompt template
# This is the prompt sent to Claude Sonnet with the image(s)
# Save this in extractor.py as the EXTRACTION_PROMPT constant

EXTRACTION_PROMPT = """You are a geolocation analyst. Analyze this Street View image and extract geographic features.

Work through these categories IN ORDER. For each, report what you observe or null if not visible.

1. TEXT AND SIGNAGE
- Any readable text on signs, storefronts, billboards, advertisements
- Route numbers or highway markers
- Place names (city, town, district, street names)
- Domain extensions on ads (.br, .co.za, .com.au)
- Phone number formats or country codes
- Currency symbols on price tags

2. LANGUAGE IDENTIFICATION
- What script is visible? (latin, cyrillic, arabic, thai, hangul, devanagari, etc.)
- What specific language? Look at diacritics: ñ=Spanish, ã/õ=Portuguese, ø=Danish/Norwegian, ç=Turkish/French/Portuguese, ă/ș/ț=Romanian
- Confidence level 0.0-1.0 for language identification

3. DRIVING AND ROAD
- Driving side: LEFT or RIGHT (look at vehicle position, road orientation)
- Road marking colors: yellow center line (Americas), white center line (Europe/Asia)
- Road surface: asphalt quality, dirt, cobblestone
- Speed sign format: red circle (Europe), white rectangle (Americas)

4. VEHICLES AND PLATES
- License plate format if visible: EU long rectangle, US short rectangle, etc.
- Plate colors: yellow rear (UK/NL), blue strip (EU)

5. INFRASTRUCTURE
- Utility pole type: wooden H-frame, concrete curved, metal lattice, bundled overhead wires
- Architecture style: describe the building materials, roof style, window style
- Building materials: stone, brick, concrete, wood, corrugated metal

6. ENVIRONMENT
- Vegetation biome: tropical, temperate deciduous, boreal, desert, Mediterranean, savanna
- Specific tree species if identifiable: eucalyptus, palm, cypress, birch, baobab
- Terrain: flat, rolling hills, mountainous, coastal
- Soil color if visible: red laterite, tan/brown, black, sandy
- Sky/weather: clear, overcast grey, tropical cumulus, hazy

7. INFRASTRUCTURE QUALITY
- Overall development level: high (W.Europe/Japan/USA), medium (E.Europe/Brazil cities), low (rural developing)

8. MISIDENTIFICATION PATTERNS — READ BEFORE GUESSING

DECISIVE RULES — these OVERRIDE all other visual signals:

- NO CENTER LINE + white edge lines only = ITALY. This pattern is nearly unique to Italy in Europe. Even if other features suggest Portugal, Spain, or Greece, guess Italy.
- Yellow EDGE lines + white CENTER line = South Africa, Botswana, Eswatini, or Lesotho. NOT USA. This combination is nearly unique worldwide.
- Left-hand driving = ONLY guess from this list: UK, Ireland, Japan, Australia, New Zealand, India, Sri Lanka, Bangladesh, Thailand, Indonesia, Malaysia, South Africa, Kenya, Botswana, Mozambique, Uganda, Tanzania. If you detect left-hand driving, do NOT guess any country not on this list.

REGIONAL GUIDANCE — use to narrow between similar regions:

- SOUTHERN AFRICA vs AMERICAN SOUTHWEST: Dry semi-arid terrain with sparse scrubland does NOT mean USA. Check for left-hand driving, Afrikaans/English bilingual signs, South African wire strand fencing (not American T-post fencing), and red-brown soil. Do NOT default to USA/Mexico for arid landscapes.

- VIETNAM vs THAILAND: Vietnamese text uses Latin script with heavy diacritics (ă, ơ, ư, ê). Thai uses a unique curving script. Vietnamese roads have red-and-white kilometer markers. Latin script + diacritics + tropical = Vietnam not Thailand.

- BRAZIL INTERIOR: Brazilian locations are frequently in the interior (cerrado, caatinga) not just coastal cities. Red laterite soil with sparse savanna in South America is likely central Brazil, not Africa. Look for concrete kilometer posts and BR-xxx highway markers.

- NORDIC: Swedish roads have yellow-edged reflector posts and blue road signs. Norwegian national roads have green signs with white text. Finnish 1st class roads have RED signs, 2nd class YELLOW signs, regional roads WHITE signs. Iceland has NO trees and black volcanic soil. Denmark has short-dashed edge markings. Text clue: ø or æ = Danish/Norwegian. ö or ä without ø = Swedish/Finnish.

- MEDITERRANEAN: Greek signs use blue backgrounds with white text. Portugal has cobblestone (calçada) sidewalks and blue/white azulejo tiles. Spain uses blue highway signs and black-and-white striped curbs. Turkey has wide multi-lane roads uncommon in southern Europe.

- ARGENTINA vs AUSTRALIA: Argentina uses yellow center lines and drives right. Australia uses white center lines and drives left. Argentine soil is grey-brown, Australian soil is red-orange.

- RUSSIA vs NORDIC: Russian roads have thinner center lines and poor maintenance. If the landscape looks Nordic but there is NO Cyrillic text, guess Nordic not Russia.

9. LOCATION GUESS
- Based on ALL features observed above, name the single most likely city or town where this image was taken
- city: the most specific geocodable place (city, town, or district). If you cannot narrow below country level, use the country capital.
- country: country name in English
- lat/lng: your best coordinate estimate (decimal degrees). Be as precise as the evidence allows — do not round to country centroid if you can do better.
- reasoning: one concise sentence (max 20 words) citing the key features that drove your guess
- confidence: 0.0–1.0 for how certain you are of this specific city

10. BLANK IMAGE
- If the image appears to be a blank, grey, or black placeholder with no visible Street View imagery, set all features to null and set location_guess confidence to 0.0. Do not attempt to guess a location from a placeholder image.

11. BEFORE FINALIZING YOUR GUESS, check it against these rules:
- Did you observe no center line + white edge lines? If yes, change your guess to Italy.
- Did you observe yellow edge + white center lines? If yes, change to South Africa/Botswana.
- Did you detect left-hand driving? If yes, verify your guess is a left-driving country.
If any rule triggers, override your initial guess even if other features disagree.

Respond with ONLY this JSON object, no other text:

{
  "pass_1": {
    "script": null,
    "language": null,
    "language_confidence": null,
    "readable_text": [],
    "place_name": null,
    "route_number": null,
    "plate_format": null,
    "driving_side": null,
    "speed_sign_format": null,
    "domain_extension": null,
    "currency_symbol": null
  },
  "pass_2": {
    "biome": null,
    "vegetation_specific": null,
    "sky_condition": null,
    "terrain": null,
    "soil_color": null,
    "architecture": null,
    "pole_type": null,
    "road_surface": null,
    "road_markings": null,
    "infrastructure_quality": null
  },
  "location_guess": {
    "city": null,
    "country": null,
    "lat": null,
    "lng": null,
    "reasoning": null,
    "confidence": null
  }
}

For place_name: return ONLY the place name as a string (e.g. "Belo Horizonte", "Route 7"). Do not add qualifiers, guesses, or commentary like "likely southern France". If unsure whether text is a place name, return null.

Fill in observed values. Use null for anything not visible or not determinable. Use the exact field names shown. Do not add commentary or explanation."""
