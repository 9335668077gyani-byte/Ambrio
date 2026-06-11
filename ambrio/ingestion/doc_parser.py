from pathlib import Path
from typing import Any

SUPPORTED_EXTENSIONS = {
    ".pdf",".docx",".doc",".xlsx",".xls",
    ".csv",".txt",".md",".html",".htm",".pptx"
}

_MARKITDOWN_INSTANCE: Any = None

def _get_markitdown() -> Any:
    global _MARKITDOWN_INSTANCE
    if _MARKITDOWN_INSTANCE is None:
        from markitdown import MarkItDown
        _MARKITDOWN_INSTANCE = MarkItDown()
    return _MARKITDOWN_INSTANCE

MAX_CHARS_DEFAULT: int = 15_000   # 15k chars ≈ ~3,750 tokens — safe for all models

def parse_to_markdown(path: str, max_chars: int = MAX_CHARS_DEFAULT) -> str:
    """Parse any supported document to clean Markdown string.

    Hard cap at max_chars to prevent context window overflow.
    Truncated content is marked with [TRUNCATED — {N} chars removed].
    """
    ext = Path(path).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file format: {ext}")

    def _truncate(text: str) -> str:
        if len(text) <= max_chars:
            return text
        removed = len(text) - max_chars
        return text[:max_chars] + f"\n\n[TRUNCATED — {removed:,} chars removed to fit context window]"

    # Primary: MarkItDown (handles docx, xlsx, pptx, csv, txt, html, md)
    try:
        md = _get_markitdown()
        result = md.convert(path)
        if result.text_content and result.text_content.strip():
            return _truncate(result.text_content.strip())
    except Exception as e:
        if ext != ".pdf":
            raise RuntimeError(f"MarkItDown failed on {ext}: {e}") from e

    # PDF fallback: PyMuPDF (handles scanned + native PDFs)
    try:
        import fitz
        text_parts = []
        current_len = 0
        with fitz.open(path) as doc:
            for page in doc:
                page_text = page.get_text()
                if page_text:
                    text_parts.append(page_text)
                    current_len += len(page_text)
                    if current_len >= max_chars:
                        break
        
        text = "\n\n".join(text_parts).strip()
        if text:
            return _truncate(text)
        
        if ext == ".pdf":
            raise RuntimeError(f"PDF contains no extractable text layer (image-only): {path}")
    except Exception as e2:
        raise RuntimeError(f"All PDF parsers exhausted: {e2}") from e2

    raise RuntimeError(f"Could not extract text from {path}")
