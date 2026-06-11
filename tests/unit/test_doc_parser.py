import pytest
from ambrio.ingestion.doc_parser import parse_to_markdown

def test_parses_txt_file(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("Hello World\nLine 2\nLine 3")
    result = parse_to_markdown(str(f))
    assert "Hello World" in result
    assert "Line 2" in result

def test_parses_csv_to_table(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("name,age,city\nAlice,30,Mumbai\nBob,25,Delhi")
    result = parse_to_markdown(str(f))
    assert "Alice" in result

def test_rejects_video_extension(tmp_path):
    f = tmp_path / "file.mp4"
    f.write_bytes(b"not a video")
    with pytest.raises(ValueError, match="Unsupported"):
        parse_to_markdown(str(f))

def test_respects_max_chars(tmp_path):
    f = tmp_path / "big.txt"
    f.write_text("A" * 100_000)
    result = parse_to_markdown(str(f), max_chars=1000)
    # The new watermark adds length, so we check if it starts with A*1000 and has the watermark
    assert result.startswith("A" * 1000)
    assert "[TRUNCATED" in result

def test_parse_to_markdown_respects_15k_default(tmp_path):
    """Default max_chars must be 15_000, not 40_000."""
    from ambrio.ingestion.doc_parser import MAX_CHARS_DEFAULT
    assert MAX_CHARS_DEFAULT == 15_000

def test_parse_to_markdown_appends_watermark_when_truncated(tmp_path):
    """When content is truncated, a [TRUNCATED] marker must be appended."""
    from ambrio.ingestion.doc_parser import parse_to_markdown
    big_file = tmp_path / "big.txt"
    big_file.write_text("A" * 20_000, encoding="utf-8")
    result = parse_to_markdown(str(big_file), max_chars=100)
    assert len(result) <= 170  # 100 chars + watermark length
    assert "[TRUNCATED" in result
