import base64
import io
import json
import re
from pathlib import Path

import anthropic
from PIL import Image

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from extraction_prompt import EXTRACTION_PROMPT

_MAX_BYTES = 4 * 1024 * 1024  # 4 MB

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_PASS_1_KEYS = {
    "script", "language", "language_confidence", "readable_text",
    "place_name", "route_number", "plate_format", "driving_side",
    "speed_sign_format", "domain_extension", "currency_symbol",
}
_PASS_2_KEYS = {
    "biome", "vegetation_specific", "sky_condition", "terrain",
    "soil_color", "architecture", "pole_type", "road_surface",
    "road_markings", "infrastructure_quality",
}

_EMPTY_RESULT: dict = {
    "pass_1": {k: ([] if k == "readable_text" else None) for k in _PASS_1_KEYS},
    "pass_2": {k: None for k in _PASS_2_KEYS},
}


def _compress_image(image_path: str) -> tuple[bytes, str]:
    """Return (image_bytes, media_type), resizing if the file exceeds 4 MB.

    Images under the limit are returned as-is (original bytes, original format).
    Images over the limit are iteratively scaled down by 0.75x until under 4 MB,
    then re-encoded as JPEG (quality 85) which is accepted by the Claude API.
    """
    path = Path(image_path)
    raw = path.read_bytes()

    # Detect format from magic bytes, not file extension.
    # collect.py saves Street View images with a .png extension even though
    # the API returns JPEG data, so extension-based detection is unreliable.
    if raw[:2] == b"\xff\xd8":
        media_type = "image/jpeg"
    elif raw[:4] == b"\x89PNG":
        media_type = "image/png"
    elif raw[:6] in (b"GIF87a", b"GIF89a"):
        media_type = "image/gif"
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        media_type = "image/webp"
    else:
        media_type = "image/jpeg"  # safe fallback for unknown formats

    if len(raw) <= _MAX_BYTES:
        return raw, media_type

    # Need to resize — work in memory, output as JPEG
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    buf = io.BytesIO()

    while True:
        buf.seek(0)
        buf.truncate()
        img.save(buf, format="JPEG", quality=85)
        if buf.tell() <= _MAX_BYTES:
            break
        # Scale down by 75% and try again
        w, h = img.size
        img = img.resize((int(w * 0.75), int(h * 0.75)), Image.LANCZOS)

    print(f"[extractor] image resized to {buf.tell() / 1024 / 1024:.2f} MB")
    return buf.getvalue(), "image/jpeg"


def _load_image_b64(image_path: str) -> tuple[str, str]:
    """Return (base64_data, media_type), compressing first if over 4 MB."""
    raw_bytes, media_type = _compress_image(image_path)
    data = base64.standard_b64encode(raw_bytes).decode("utf-8")
    return data, media_type


def _parse_response(raw: str) -> dict:
    """Extract JSON from Claude's response, stripping markdown fences if present."""
    # Strip ```json ... ``` or ``` ... ``` fences
    text = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        # Grab the first {...} block in case there's leading/trailing prose
        obj_match = re.search(r"\{.*\}", text, re.DOTALL)
        if obj_match:
            text = obj_match.group(0)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def extract(image_paths: list[str]) -> tuple[dict, str]:
    """Send one or more images to Claude Sonnet and return (parsed_features, raw_response).

    When multiple images are provided (e.g. 4 headings of the same location),
    all are sent in a single API call so Claude can synthesise across views.

    On any failure returns (_EMPTY_RESULT, raw_response_or_empty_string).
    Never raises.
    """
    raw_response = ""
    try:
        # Build image content blocks
        content: list[dict] = []
        for path in image_paths:
            b64_data, media_type = _load_image_b64(path)
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64_data,
                },
            })

        # Prepend a brief multi-view context when more than one image is sent.
        # The EXTRACTION_PROMPT itself is unchanged (tested, do not modify).
        if len(image_paths) > 1:
            preamble = (
                f"You are seeing {len(image_paths)} Street View images of the same "
                f"location taken at different headings (0°, 90°, 180°, 270°). "
                f"Synthesise features from all views and return one JSON object.\n\n"
            )
            prompt_text = preamble + EXTRACTION_PROMPT
        else:
            prompt_text = EXTRACTION_PROMPT

        content.append({"type": "text", "text": prompt_text})

        message = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": content}],
        )

        raw_response = message.content[0].text
        parsed = _parse_response(raw_response)

        if "pass_1" not in parsed or "pass_2" not in parsed:
            return _EMPTY_RESULT.copy(), raw_response

        return parsed, raw_response

    except Exception as exc:  # noqa: BLE001
        print(f"[extractor] error: {exc}")
        return _EMPTY_RESULT.copy(), raw_response
