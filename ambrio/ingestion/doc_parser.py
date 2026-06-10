from pathlib import Path

SUPPORTED_EXTENSIONS = {
    ".pdf",".docx",".doc",".xlsx",".xls",
    ".csv",".txt",".md",".html",".htm",".pptx"
}

def parse_to_markdown(path: str, max_chars: int = 40_000) -> str:
    """Parse any supported document to clean Markdown string."""
    ext = Path(path).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file format: {ext}")

    # Primary: MarkItDown (handles docx, xlsx, pptx, csv, txt, html, md)
    try:
        from markitdown import MarkItDown
        result = MarkItDown().convert(path)
        if result.text_content.strip():
            return result.text_content.strip()[:max_chars]
    except Exception as e:
        if ext != ".pdf":
            raise RuntimeError(f"MarkItDown failed on {ext}: {e}") from e

    # PDF fallback: PyMuPDF (handles scanned + native PDFs)
    try:
        import fitz
        doc  = fitz.open(path)
        text = "\n\n".join(page.get_text() for page in doc)
        doc.close()
        if text.strip():
            return text.strip()[:max_chars]
    except Exception as e2:
        raise RuntimeError(f"All PDF parsers exhausted: {e2}") from e2

    raise RuntimeError(f"Could not extract text from {path}")
