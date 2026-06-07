import pytest
from ambrio.router.memory.token_compressor import (
    compress_messages, compress_text, compression_stats
)

def test_compress_short_text_unchanged():
    short = "Hello world"
    assert compress_text(short) == short

def test_compress_long_text_reduces_size():
    long_text = "This is a test sentence. " * 500  # ~12500 chars
    compressed = compress_text(long_text, max_tokens=200)
    assert len(compressed) < len(long_text)

def test_compress_messages_preserves_structure():
    msgs = [
        {'role': 'system', 'content': 'You are Ambrio.'},
        {'role': 'user', 'content': 'What parts are low?'},
        {'role': 'assistant', 'content': 'Let me check. ' * 200},
    ]
    compressed = compress_messages(msgs, max_tokens=500)
    assert isinstance(compressed, list)
    assert len(compressed) >= 1
    assert all('role' in m and 'content' in m for m in compressed)

def test_compression_stats_shows_savings():
    original = "x" * 4000
    compressed = "x" * 400
    stats = compression_stats(original, compressed)
    assert stats['saved_pct'] == 90.0
    assert stats['original_tokens_est'] == 1000
    assert stats['compressed_tokens_est'] == 100

def test_compress_deduplicates_repeated_lines():
    repeated = "Error: connection failed\n" * 100
    compressed = compress_text(repeated, max_tokens=100)
    assert len(compressed) < len(repeated)
