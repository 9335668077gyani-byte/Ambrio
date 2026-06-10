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

def test_raises_on_large_file(tmp_path, monkeypatch):
    f = tmp_path / "huge.jpg"
    f.write_bytes(b"\xff\xd8\xfffakeimage")
    # Mock getsize to return 21 MB
    import os
    monkeypatch.setattr(os.path, "getsize", lambda p: 21 * 1024 * 1024)
    
    with pytest.raises(ImageEncoderError, match="Image is .* max is 20MB"):
        encode_image_for_gemini(str(f))

def test_raises_on_read_error(tmp_path):
    f = tmp_path / "test.jpg"
    f.write_bytes(b"\xff\xd8\xfffakeimage")
    
    import builtins
    original_open = builtins.open
    
    def mock_open(*args, **kwargs):
        raise PermissionError("Access Denied")
        
    with pytest.MonkeyPatch.context() as m:
        m.setattr("builtins.open", mock_open)
        with pytest.raises(ImageEncoderError, match="Failed to read and encode image: Access Denied"):
            encode_image_for_gemini(str(f))
