# ambrio/router/tools/img_tool.py
"""
Image Editing Tool for Ambrio.

Tools registered:
  img_passport(path)                    — resize image to passport photo (35×45mm), output 8-on-A4 print sheet
  img_resize(path, width, height)       — resize to exact pixel dimensions
  img_crop(path, mode)                  — crop: square_center | top_half | bottom_half
  img_background(path, color)           — change/add background color (white, black, blue, ...)
  img_rotate(path, angle)               — rotate by degrees (90, 180, 270, any)
  img_enhance(path, brightness, contrast, sharpness) — adjust image quality
"""
import logging
from pathlib import Path
from ambrio.router.tool_registry import tool

log = logging.getLogger(__name__)


def _output_dir() -> Path:
    d = Path.home() / 'Documents' / 'Ambrio Output'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ok(out: Path, note: str) -> dict:
    return {
        'success':  True,
        'output':   str(out),
        'answer':   f'Done! Saved to: {out}\n({note})',
    }


# ── Passport photo standard sizes (mm) ───────────────────────────────────────
_PP_SIZES = {
    'india':  (35, 45),   # Indian passport / visa
    'us':     (51, 51),   # US passport (2×2 inch)
    'uk':     (35, 45),   # UK passport
    'eu':     (35, 45),   # EU Schengen visa
    'china':  (33, 48),
    'default': (35, 45),
}


@tool(
    name='img_passport',
    description=(
        'Resize a photo to passport/visa size and generate a print-ready A4 sheet with 8 copies. '
        'Use when user says "pp size", "passport size", "passport photo", "visa photo", '
        '"make passport photo", "resize for passport". '
        'Args: path (str) — image path. country (str, optional) — india/us/uk/eu (default: india).'
    )
)
async def img_passport(path: str, country: str = 'india') -> dict:
    """
    Create passport-size photo and generate an A4 print sheet with 8 copies.
    Standard India passport: 35×45 mm @ 300 DPI
    """
    try:
        from PIL import Image as PILImage, ImageOps, ImageDraw

        src = Path(path).expanduser().resolve()
        if not src.exists():
            return {'error': f'File not found: {path}', 'success': False}

        # ── Target dimensions ─────────────────────────────────────────────────
        mm_w, mm_h = _PP_SIZES.get(country.lower(), _PP_SIZES['default'])
        DPI   = 300
        px_w  = int(mm_w / 25.4 * DPI)   # mm → inches → pixels
        px_h  = int(mm_h / 25.4 * DPI)

        img = PILImage.open(src).convert('RGBA')

        # ── White background for transparent PNGs ─────────────────────────────
        bg = PILImage.new('RGBA', img.size, (255, 255, 255, 255))
        bg.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
        img = bg.convert('RGB')

        # ── Smart crop: center-crop to target aspect ratio ────────────────────
        iw, ih = img.size
        target_ratio = px_w / px_h
        current_ratio = iw / ih

        if current_ratio > target_ratio:
            # Too wide — crop sides
            new_w = int(ih * target_ratio)
            x_off = (iw - new_w) // 2
            img   = img.crop((x_off, 0, x_off + new_w, ih))
        elif current_ratio < target_ratio:
            # Too tall — crop top/bottom (keep face: bias toward top 80%)
            new_h = int(iw / target_ratio)
            y_off = max(0, int((ih - new_h) * 0.2))   # 20% offset from top
            img   = img.crop((0, y_off, iw, y_off + new_h))

        # ── Resize to exact passport dimensions ───────────────────────────────
        pp_img = img.resize((px_w, px_h), PILImage.LANCZOS)

        # ── Save single passport photo ────────────────────────────────────────
        single_out = _output_dir() / (src.stem + f'_passport_{mm_w}x{mm_h}mm.jpg')
        pp_img.save(str(single_out), format='JPEG', quality=95, dpi=(DPI, DPI))

        # ── Generate A4 print sheet with 8 copies (2 col × 4 row) ────────────
        A4_W   = int(8.27  * DPI)   # 2480 px
        A4_H   = int(11.69 * DPI)   # 3508 px
        MARGIN = int(0.2   * DPI)   # 5 mm margin
        GAP    = int(0.1   * DPI)   # 3 mm gap between photos

        COLS, ROWS = 2, 4
        sheet = PILImage.new('RGB', (A4_W, A4_H), (255, 255, 255))

        # Center the grid on the sheet
        grid_w = COLS * px_w + (COLS - 1) * GAP
        grid_h = ROWS * px_h + (ROWS - 1) * GAP
        x_start = (A4_W - grid_w) // 2
        y_start = (A4_H - grid_h) // 2

        for row in range(ROWS):
            for col in range(COLS):
                x = x_start + col * (px_w + GAP)
                y = y_start + row * (px_h + GAP)
                sheet.paste(pp_img, (x, y))

        # Add faint cut guide lines
        draw = ImageDraw.Draw(sheet)
        line_color = (200, 200, 200)
        for row in range(ROWS):
            for col in range(COLS):
                x = x_start + col * (px_w + GAP)
                y = y_start + row * (px_h + GAP)
                draw.rectangle([x, y, x + px_w - 1, y + px_h - 1],
                               outline=line_color, width=1)

        sheet_out = _output_dir() / (src.stem + f'_passport_A4_8x.pdf')
        sheet.save(str(sheet_out), format='PDF', resolution=DPI)

        return {
            'success':    True,
            'single':     str(single_out),
            'print_sheet': str(sheet_out),
            'answer': (
                f'✅ Passport photo ready!\n\n'
                f'📸 Single photo ({mm_w}×{mm_h}mm): {single_out.name}\n'
                f'🖨️  A4 print sheet (8 copies): {sheet_out.name}\n'
                f'📁 Saved in: Ambrio Output folder\n\n'
                f'Print the A4 sheet and cut along the guide lines.'
            ),
        }

    except ImportError:
        return {'error': 'Install Pillow: pip install Pillow', 'success': False}
    except Exception as e:
        log.error(f'img_passport error: {e}')
        return {'error': str(e), 'path': path, 'success': False}


@tool(
    name='img_resize',
    description=(
        'Resize an image to specific pixel dimensions. '
        'Args: path (str), width (int), height (int). '
        'Use when user says "resize to WxH", "make it 200x200", "change image size".'
    )
)
async def img_resize(path: str, width: int, height: int) -> dict:
    try:
        from PIL import Image as PILImage
        src = Path(path).expanduser().resolve()
        if not src.exists():
            return {'error': f'File not found: {path}', 'success': False}

        img = PILImage.open(src).convert('RGB')
        img = img.resize((int(width), int(height)), PILImage.LANCZOS)
        out = _output_dir() / (src.stem + f'_{width}x{height}{src.suffix}')
        img.save(str(out), quality=95)
        return _ok(out, f'Resized to {width}×{height}px')
    except Exception as e:
        return {'error': str(e), 'success': False}


@tool(
    name='img_background',
    description=(
        'Change or add a solid background color to an image (replaces transparent areas). '
        'Args: path (str), color (str) — e.g. "white", "blue", "red", "#FF0000". '
        'Use when user says "white background", "blue bg", "remove background color".'
    )
)
async def img_background(path: str, color: str = 'white') -> dict:
    try:
        from PIL import Image as PILImage
        src = Path(path).expanduser().resolve()
        if not src.exists():
            return {'error': f'File not found: {path}', 'success': False}

        img  = PILImage.open(src).convert('RGBA')
        bg   = PILImage.new('RGBA', img.size, color)
        bg.paste(img, mask=img.split()[3])
        out  = _output_dir() / (src.stem + f'_bg_{color.strip("#")}.jpg')
        bg.convert('RGB').save(str(out), quality=95)
        return _ok(out, f'Background set to {color}')
    except Exception as e:
        return {'error': str(e), 'success': False}


@tool(
    name='img_rotate',
    description=(
        'Rotate an image by degrees. '
        'Args: path (str), angle (int) — degrees clockwise (e.g. 90, 180, 270). '
        'Use when user says "rotate", "flip", "turn image".'
    )
)
async def img_rotate(path: str, angle: int = 90) -> dict:
    try:
        from PIL import Image as PILImage
        src = Path(path).expanduser().resolve()
        if not src.exists():
            return {'error': f'File not found: {path}', 'success': False}

        img = PILImage.open(src)
        img = img.rotate(-int(angle), expand=True)  # PIL rotates CCW, user expects CW
        out = _output_dir() / (src.stem + f'_rotated{angle}{src.suffix}')
        img.save(str(out))
        return _ok(out, f'Rotated {angle}° clockwise')
    except Exception as e:
        return {'error': str(e), 'success': False}


@tool(
    name='img_enhance',
    description=(
        'Adjust image brightness, contrast, and sharpness. '
        'Args: path (str), brightness (float, default 1.0), contrast (float, default 1.0), sharpness (float, default 1.0). '
        '1.0 = original. 1.5 = 50% more. 0.5 = 50% less. '
        'Use when user says "brighten", "increase contrast", "sharpen image", "make clearer".'
    )
)
async def img_enhance(path: str, brightness: float = 1.0,
                      contrast: float = 1.0, sharpness: float = 1.0) -> dict:
    try:
        from PIL import Image as PILImage, ImageEnhance
        src = Path(path).expanduser().resolve()
        if not src.exists():
            return {'error': f'File not found: {path}', 'success': False}

        img = PILImage.open(src).convert('RGB')
        if brightness != 1.0:
            img = ImageEnhance.Brightness(img).enhance(float(brightness))
        if contrast != 1.0:
            img = ImageEnhance.Contrast(img).enhance(float(contrast))
        if sharpness != 1.0:
            img = ImageEnhance.Sharpness(img).enhance(float(sharpness))

        tag = f'b{brightness}_c{contrast}_s{sharpness}'.replace('.', '')
        out = _output_dir() / (src.stem + f'_enhanced_{tag}{src.suffix}')
        img.save(str(out), quality=95)
        return _ok(out, f'Enhanced — brightness:{brightness} contrast:{contrast} sharpness:{sharpness}')
    except Exception as e:
        return {'error': str(e), 'success': False}
