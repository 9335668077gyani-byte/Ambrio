# tests/unit/test_mime_guard.py
import pytest
from ambrio.ingestion.mime_guard import validate_file, VideoFileError, FileTooLargeError

def test_blocks_mp4_by_extension(tmp_path):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"fake video data")
    with pytest.raises(VideoFileError):
        validate_file(str(f))

def test_blocks_mkv_by_extension(tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"fake")
    with pytest.raises(VideoFileError):
        validate_file(str(f))

def test_allows_pdf(tmp_path):
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF-1.4 fake content")
    # Should not raise
    result = validate_file(str(f))
    assert result is not None

def test_raises_file_not_found():
    with pytest.raises(FileNotFoundError):
        validate_file("C:/does/not/exist.pdf")

def test_raises_file_too_large(tmp_path, monkeypatch):
    f = tmp_path / "large.pdf"
    f.write_bytes(b"dummy")
    
    # Mock getsize to simulate a 51MB file
    import os
    monkeypatch.setattr(os.path, "getsize", lambda x: 51 * 1_048_576)
    
    with pytest.raises(FileTooLargeError):
        validate_file(str(f))
