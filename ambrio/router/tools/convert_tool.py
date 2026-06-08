# ambrio/router/tools/convert_tool.py
"""
File Conversion Tool for Ambrio.
Converts documents between formats locally, no cloud needed.

Supported conversions:
  docx  → pdf, txt
  pdf   → txt
  txt   → docx
  xlsx  → csv
  csv   → xlsx
  md    → html, txt
  html  → txt
  jpg/png → pdf
"""
import logging
from pathlib import Path
from ambrio.router.tool_registry import tool

log = logging.getLogger(__name__)

# ── Conversion matrix ─────────────────────────────────────────────────────────
_SUPPORTED = {
    '.docx': ['pdf', 'txt'],
    '.doc':  ['txt'],
    '.pdf':  ['txt'],
    '.txt':  ['docx', 'pdf'],
    '.md':   ['html', 'txt', 'docx'],
    '.html': ['txt', 'docx'],
    '.xlsx': ['csv', 'txt'],
    '.xls':  ['csv'],
    '.csv':  ['xlsx'],
    '.jpg':  ['pdf'],
    '.jpeg': ['pdf'],
    '.png':  ['pdf'],
    '.bmp':  ['pdf'],
    '.webp': ['pdf'],
    '.gif':  ['pdf'],
    '.tiff': ['pdf'],
}


def _out_path(src: Path, target_ext: str) -> Path:
    """Build output path alongside source with new extension."""
    return src.parent / (src.stem + '.' + target_ext.lstrip('.'))


@tool(
    name='doc_convert',
    description=(
        'Convert a file from one format to another. '
        'Supports: docx→pdf/txt, pdf→txt, txt→docx, xlsx→csv, csv→xlsx, '
        'md→html/txt, html→txt, jpg/png→pdf. '
        'Args: path (str) — source file path, to (str) — target format e.g. "pdf", "txt", "docx", "csv", "xlsx".'
    )
)
async def doc_convert(path: str, to: str) -> dict:
    """
    Convert a file to another format.
    Args:
        path: Absolute path to the source file
        to:   Target format — pdf, txt, docx, csv, xlsx, html
    """
    try:
        src = Path(path).expanduser().resolve()
        if not src.exists():
            return {'error': f'File not found: {path}', 'success': False}

        src_ext = src.suffix.lower()
        tgt_ext = to.lower().lstrip('.')
        out     = _out_path(src, tgt_ext)

        # ── DOCX → PDF ───────────────────────────────────────────────────────
        if src_ext in ('.docx', '.doc') and tgt_ext == 'pdf':
            try:
                from docx2pdf import convert
                convert(str(src), str(out))
                return _ok(out, 'Word → PDF via Microsoft Word')
            except Exception as e:
                # Fallback: try LibreOffice if installed
                import subprocess
                result = subprocess.run(
                    ['soffice', '--headless', '--convert-to', 'pdf',
                     '--outdir', str(out.parent), str(src)],
                    capture_output=True, timeout=30
                )
                if result.returncode == 0:
                    return _ok(out, 'Word → PDF via LibreOffice')
                return {'error': f'PDF conversion needs Microsoft Word or LibreOffice installed. '
                                 f'Install either app then retry. ({e})',
                        'success': False}

        # ── DOCX → TXT ───────────────────────────────────────────────────────
        elif src_ext in ('.docx', '.doc') and tgt_ext == 'txt':
            from docx import Document
            doc  = Document(str(src))
            text = '\n'.join(p.text for p in doc.paragraphs)
            out.write_text(text, encoding='utf-8')
            return _ok(out, 'Word → Plain Text')

        # ── PDF → TXT ────────────────────────────────────────────────────────
        elif src_ext == '.pdf' and tgt_ext == 'txt':
            try:
                import pdfplumber
                text_parts = []
                with pdfplumber.open(str(src)) as pdf:
                    for page in pdf.pages:
                        t = page.extract_text()
                        if t:
                            text_parts.append(t)
                out.write_text('\n\n'.join(text_parts), encoding='utf-8')
                return _ok(out, 'PDF → Plain Text via pdfplumber')
            except ImportError:
                return {'error': 'Install pdfplumber: pip install pdfplumber', 'success': False}

        # ── TXT / MD → DOCX ──────────────────────────────────────────────────
        elif src_ext in ('.txt', '.md', '.html') and tgt_ext == 'docx':
            from docx import Document
            from docx.shared import Pt
            content = src.read_text(encoding='utf-8', errors='replace')
            doc = Document()
            doc.core_properties.title = src.stem
            for line in content.split('\n'):
                if line.strip():
                    p = doc.add_paragraph(line)
                    p.style.font.size = Pt(11)
                else:
                    doc.add_paragraph('')
            out = _out_path(src, 'docx')
            doc.save(str(out))
            return _ok(out, 'Text → Word Document')

        # ── TXT → PDF ────────────────────────────────────────────────────────
        elif src_ext == '.txt' and tgt_ext == 'pdf':
            # First convert to docx, then to pdf
            result = await doc_convert(path, 'docx')
            if result.get('success'):
                return await doc_convert(result['saved_to'], 'pdf')
            return result

        # ── MD → HTML ────────────────────────────────────────────────────────
        elif src_ext == '.md' and tgt_ext == 'html':
            try:
                import markdown as md_lib
                text = src.read_text(encoding='utf-8')
                html = md_lib.markdown(text, extensions=['tables', 'fenced_code'])
                full = f'<!DOCTYPE html><html><body>\n{html}\n</body></html>'
                out.write_text(full, encoding='utf-8')
                return _ok(out, 'Markdown → HTML')
            except ImportError:
                return {'error': 'Install markdown: pip install markdown', 'success': False}

        # ── MD → TXT ─────────────────────────────────────────────────────────
        elif src_ext == '.md' and tgt_ext == 'txt':
            text = src.read_text(encoding='utf-8')
            # Strip markdown symbols
            import re
            text = re.sub(r'#{1,6}\s*', '', text)
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            text = re.sub(r'\*(.+?)\*', r'\1', text)
            text = re.sub(r'`(.+?)`', r'\1', text)
            out.write_text(text, encoding='utf-8')
            return _ok(out, 'Markdown → Plain Text')

        # ── HTML → TXT ───────────────────────────────────────────────────────
        elif src_ext == '.html' and tgt_ext == 'txt':
            try:
                from bs4 import BeautifulSoup
                html = src.read_text(encoding='utf-8')
                soup = BeautifulSoup(html, 'html.parser')
                out.write_text(soup.get_text(), encoding='utf-8')
                return _ok(out, 'HTML → Plain Text')
            except ImportError:
                return {'error': 'Install bs4: pip install beautifulsoup4', 'success': False}

        # ── XLSX → CSV ───────────────────────────────────────────────────────
        elif src_ext in ('.xlsx', '.xls') and tgt_ext == 'csv':
            import openpyxl, csv
            wb = openpyxl.load_workbook(str(src), read_only=True, data_only=True)
            ws = wb.active
            with open(str(out), 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                for row in ws.iter_rows(values_only=True):
                    writer.writerow(['' if v is None else str(v) for v in row])
            wb.close()
            return _ok(out, 'Excel → CSV')

        # ── CSV → XLSX ───────────────────────────────────────────────────────
        elif src_ext == '.csv' and tgt_ext == 'xlsx':
            import openpyxl, csv
            wb = openpyxl.Workbook()
            ws = wb.active
            with open(str(src), newline='', encoding='utf-8', errors='replace') as f:
                for row in csv.reader(f):
                    ws.append(row)
            wb.save(str(out))
            return _ok(out, 'CSV → Excel')

        # ── IMAGE → PDF ───────────────────────────────────────────────────────
        elif src_ext in ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp', '.gif') and tgt_ext == 'pdf':
            try:
                from PIL import Image as PILImage

                img = PILImage.open(str(src))

                # Handle RGBA/palette modes
                if img.mode in ('RGBA', 'P', 'LA'):
                    bg = PILImage.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    bg.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = bg
                else:
                    img = img.convert('RGB')

                # A4 at 150 DPI (enough for sharp ID cards)
                DPI       = 150
                A4_W_PX   = int(8.27  * DPI)   # 1240 px
                A4_H_PX   = int(11.69 * DPI)   # 1753 px
                MARGIN_PX = int(0.4   * DPI)   # 60 px

                img_w, img_h = img.size

                # Auto-rotate: if image is wider than tall → landscape page
                if img_w > img_h:
                    canvas_w, canvas_h = A4_H_PX, A4_W_PX   # landscape
                else:
                    canvas_w, canvas_h = A4_W_PX, A4_H_PX   # portrait

                # Scale image to fit canvas with margin
                max_w = canvas_w - 2 * MARGIN_PX
                max_h = canvas_h - 2 * MARGIN_PX
                scale = min(max_w / img_w, max_h / img_h)
                new_w = int(img_w * scale)
                new_h = int(img_h * scale)
                img   = img.resize((new_w, new_h), PILImage.LANCZOS)

                # Paste onto white A4 canvas centered
                canvas = PILImage.new('RGB', (canvas_w, canvas_h), (255, 255, 255))
                x_off  = (canvas_w - new_w) // 2
                y_off  = (canvas_h - new_h) // 2
                canvas.paste(img, (x_off, y_off))

                canvas.save(str(out), format='PDF', resolution=DPI)
                return _ok(out, f'Image → A4 PDF ({"landscape" if img_w > img_h else "portrait"}, {DPI} DPI)')
            except ImportError:
                return {'error': 'Install Pillow: pip install Pillow', 'success': False}

        else:
            supported = _SUPPORTED.get(src_ext, [])
            if supported:
                return {
                    'error': f'Cannot convert {src_ext} to .{tgt_ext}. '
                             f'Supported targets for {src_ext}: {supported}',
                    'success': False
                }
            else:
                return {
                    'error': f'File type {src_ext} is not supported for conversion. '
                             f'Supported: {list(_SUPPORTED.keys())}',
                    'success': False
                }

    except Exception as e:
        log.error(f'doc_convert error: {e}')
        return {'error': str(e), 'path': path, 'success': False}


def _ok(out: Path, method: str) -> dict:
    return {
        'success':   True,
        'saved_to':  str(out),
        'method':    method,
        'file_name': out.name,
        'answer':    f'Done! Converted file saved to: {out}',
    }
