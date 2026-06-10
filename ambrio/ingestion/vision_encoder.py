# ambrio/ingestion/vision_encoder.py
import os
import base64
from typing import Any
from pathlib import Path

# Gemini supported image types
SUPPORTED_IMAGE_MIMES = {
    ".png": "image/png",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif"
}

MAX_SIZE_MB = 20

class ImageEncoderError(ValueError): pass

def encode_image_for_gemini(path: str | os.PathLike) -> dict[str, str]:
    """
    Encode an image to Base64 and return the format required by Google GenAI.
    Returns: {"mime_type": "...", "data": "base64_string"}
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Image not found: {path}")

    size_mb = os.path.getsize(path) / 1_048_576
    if size_mb > MAX_SIZE_MB:
        raise ImageEncoderError(f"Image is {size_mb:.1f}MB — max is {MAX_SIZE_MB}MB")

    ext = Path(path).suffix.lower()
    if ext not in SUPPORTED_IMAGE_MIMES:
        raise ImageEncoderError(f"File is not an image or unsupported format: {ext}")
        
    mime = SUPPORTED_IMAGE_MIMES[ext]

    try:
        with open(path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")
        return {"mime_type": mime, "data": b64_data}
    except (OSError, ValueError) as e:
        raise ImageEncoderError(f"Failed to read and encode image: {e}") from e
