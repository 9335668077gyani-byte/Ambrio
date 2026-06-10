# tests/unit/test_vision_encoder.py
import pytest
import base64
from ambrio.ingestion.vision_encoder import encode_image_for_gemini, ImageEncoderError

def test_encodes_valid_image(tmp_path):
    f = tmp_path / "test.jpg"
    # Write a tiny fake JPEG
    f.write_bytes(b"\xff\xd8\xfffakeimage")
    result = encode_image_for_gemini(str(f))
    
    assert "mime_type" in result
    assert result["mime_type"] == "image/jpeg"
    assert "data" in result
    assert isinstance(result["data"], str)
    # Ensure it's valid base64
    base64.b64decode(result["data"])

def test_raises_on_non_image(tmp_path):
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF-1.4")
    with pytest.raises(ImageEncoderError, match="not an image"):
        encode_image_for_gemini(str(f))

def test_raises_on_missing_file():
    with pytest.raises(FileNotFoundError):
        encode_image_for_gemini("does_not_exist.png")
