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

def parse_to_markdown(path: str, max_chars: int = 40_000) -> str:
    """Parse any supported document to clean Markdown string."""
    ext = Path(path).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file format: {ext}")

    # Primary: MarkItDown (handles docx, xlsx, pptx, csv, txt, html, md)
    try:
        md = _get_markitdown()
        result = md.convert(path)
        if result.text_content and result.text_content.strip():
            return result.text_content.strip()[:max_chars]
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
            return text[:max_chars]
        
        if ext == ".pdf":
            raise RuntimeError(f"PDF contains no extractable text layer (image-only): {path}")
    except Exception as e2:
        raise RuntimeError(f"All PDF parsers exhausted: {e2}") from e2

    raise RuntimeError(f"Could not extract text from {path}")
