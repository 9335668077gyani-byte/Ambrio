# ambrio/router/memory/token_compressor.py
"""
Token Compression Layer — wraps headroom-ai to compress context before LLM.
Falls back to a built-in truncation compressor if headroom is unavailable.

Usage:
    from ambrio.router.memory.token_compressor import compress_messages, compress_text

    # Compress a list of {role, content} messages
    compressed = compress_messages(messages, max_tokens=4096)

    # Compress a raw string (tool result, file content, etc.)
    compressed_text = compress_text(tool_output, max_tokens=512)
"""
import logging, re
from typing import Any

log = logging.getLogger(__name__)

# ── Try headroom-ai ───────────────────────────────────────────────────────────
_headroom_available = False
try:
    from headroom import compress as _hr_compress
    _headroom_available = True
    log.info("headroom-ai loaded — 60-95% token compression active")
except ImportError:
    log.info("headroom-ai not available — using built-in compressor")


# ── Fallback built-in compressor ──────────────────────────────────────────────
def _builtin_compress_text(text: str, max_chars: int = 3000) -> str:
    """Simple but effective built-in compressor when headroom isn't available."""
    if len(text) <= max_chars:
        return text

    # Remove excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    text = re.sub(r'\t+', ' ', text)

    if len(text) <= max_chars:
        return text

    # Remove repeated boilerplate lines
    lines = text.splitlines()
    seen = set()
    deduped = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            deduped.append(line)
            continue
        key = stripped[:60]  # first 60 chars as dedup key
        if key not in seen:
            deduped.append(line)
            seen.add(key)
    text = '\n'.join(deduped)

    if len(text) <= max_chars:
        return text

    # Smart truncation: keep head + tail (most important parts)
    head_chars = int(max_chars * 0.6)
    tail_chars = max_chars - head_chars - 60
    head = text[:head_chars]
    tail = text[-tail_chars:] if tail_chars > 0 else ""
    omitted = len(text) - head_chars - tail_chars
    return f"{head}\n\n... [{omitted} chars compressed] ...\n\n{tail}"


def _builtin_compress_messages(messages: list[dict], max_tokens: int = 4096) -> list[dict]:
    """Compress a message list by truncating long assistant/tool messages."""
    # Rough char-to-token ratio: 1 token ≈ 4 chars
    max_chars = max_tokens * 4
    total_chars = sum(len(m.get('content', '')) for m in messages)

    if total_chars <= max_chars:
        return messages

    # Budget: system + user get priority, assistant/tool get compressed
    result = []
    remaining = max_chars

    for msg in messages:
        role    = msg.get('role', '')
        content = msg.get('content', '')

        if role in ('system', 'user'):
            # Keep user/system messages intact (they're instructions)
            result.append(msg)
            remaining -= len(content)
        else:
            # Compress assistant/tool messages
            budget   = min(len(content), max(500, remaining // max(1, len(messages))))
            compressed = _builtin_compress_text(content, max_chars=budget)
            result.append({**msg, 'content': compressed})
            remaining -= len(compressed)

    return result


# ── Public API ────────────────────────────────────────────────────────────────
def compress_messages(messages: list[dict], max_tokens: int = 4096) -> list[dict]:
    """
    Compress a list of {role, content} chat messages to fit within max_tokens.
    Uses headroom-ai if available, falls back to built-in compressor.

    Args:
        messages:   List of dicts with 'role' and 'content' keys
        max_tokens: Target token budget (approximate)

    Returns:
        Compressed messages list — same format, fewer tokens
    """
    if not messages:
        return messages

    if _headroom_available:
        try:
            result = _hr_compress(messages, budget=max_tokens)
            # headroom returns various types depending on version
            if isinstance(result, list):
                return result
            elif hasattr(result, 'messages'):
                return result.messages
            else:
                return messages  # fallback
        except Exception as e:
            log.warning(f"headroom compress failed ({e}), using built-in")

    return _builtin_compress_messages(messages, max_tokens)


def compress_text(text: str, max_tokens: int = 512) -> str:
    """
    Compress a single text string (tool output, file content, etc.).
    Uses headroom-ai if available, falls back to built-in compressor.

    Args:
        text:       Raw text to compress
        max_tokens: Target token budget (1 token ≈ 4 chars)

    Returns:
        Compressed string — fewer tokens, same key information
    """
    if not text or len(text) < 200:
        return text  # too short to bother

    if _headroom_available:
        try:
            # headroom can compress single strings via message wrapping
            result = _hr_compress(
                [{'role': 'tool', 'content': text}],
                budget=max_tokens
            )
            if isinstance(result, list) and result:
                return result[0].get('content', text)
            elif hasattr(result, 'messages') and result.messages:
                return result.messages[0].get('content', text)
        except Exception as e:
            log.warning(f"headroom text compress failed ({e}), using built-in")

    return _builtin_compress_text(text, max_chars=max_tokens * 4)


def compression_stats(original: str | list, compressed: str | list) -> dict:
    """Return token savings stats."""
    if isinstance(original, list):
        orig_chars = sum(len(m.get('content', '')) for m in original)
        comp_chars = sum(len(m.get('content', '')) for m in compressed)
    else:
        orig_chars = len(original)
        comp_chars = len(compressed)

    saved_pct = round((1 - comp_chars / max(orig_chars, 1)) * 100, 1)
    return {
        'original_tokens_est': orig_chars // 4,
        'compressed_tokens_est': comp_chars // 4,
        'saved_pct': saved_pct,
        'engine': 'headroom-ai' if _headroom_available else 'built-in',
    }
