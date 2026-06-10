# ambrio/ingestion/mime_guard.py
import os
from pathlib import Path

BLOCKED_EXTENSIONS  = {".mp4",".avi",".mkv",".mov",".wmv",".flv",
                        ".webm",".m4v",".3gp",".mpeg",".mpg",".ts",".vob"}
BLOCKED_MIME_PREFIX = "video/"
MAX_SIZE_MB         = 50

class VideoFileError(ValueError):  pass
class FileTooLargeError(ValueError): pass

def validate_file(path: str) -> str:
    """Validate file for processing. Returns MIME type string. Raises on blocked files."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    size_mb = os.path.getsize(path) / 1_048_576
    if size_mb > MAX_SIZE_MB:
        raise FileTooLargeError(f"File is {size_mb:.1f}MB — max is {MAX_SIZE_MB}MB")
    ext = Path(path).suffix.lower()
    if ext in BLOCKED_EXTENSIONS:
        raise VideoFileError(f"Video files not supported: {ext}")
    try:
        import magic
        mime = magic.from_file(path, mime=True)
        if mime.startswith(BLOCKED_MIME_PREFIX):
            raise VideoFileError(f"Video MIME type blocked: {mime}")
        return mime
    except ImportError:
        # python-magic not available — extension check above was sufficient
        return "application/octet-stream"
