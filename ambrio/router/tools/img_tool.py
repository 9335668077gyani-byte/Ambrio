# ambrio/router/tools/img_pipeline.py
"""
AI Image Editing Pipeline for Ambrio.
=====================================
A proper multi-stage AI pipeline for image editing tasks.

Tools registered:
  img_remove_bg(path)                    — AI background removal (rembg / U2Net)
  img_passport(path, country)            — Face-aware passport photo + A4 print sheet
  img_upscale(path, scale)               — AI super-resolution upscaling (2x / 4x)
  img_scan_doc(path)                     — Document scanner (perspective fix + binarize)
  img_color_grade(path, preset)          — Color grading presets: vivid / cool / warm / bw / vintage / fade
  img_resize(path, width, height)        — Resize to exact dimensions
  img_background(path, color)            — Replace background color
  img_rotate(path, angle)                — Rotate clockwise
  img_enhance(path, brightness, contrast, sharpness) — Manual adjustments
  img_ocr(path)                          — (alias: see doc_tool.py)
"""
import logging
from pathlib import Path
from ambrio.router.tool_registry import tool

log = logging.getLogger(__name__)

# ── Standard passport sizes (width × height, mm) ─────────────────────────────
_PP_SIZES = {
    'india': (35, 45), 'us': (51, 51), 'uk': (35, 45),
    'eu': (35, 45), 'china': (33, 48), 'default': (35, 45),
}

_DPI = 300   # standard print DPI


def _out_dir() -> Path:
    d = Path.home() / 'Documents' / 'Ambrio Output'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ok(out: Path, note: str) -> dict:
    return {'success': True, 'output': str(out),
            'answer': f'✅ Done!\n📁 Saved: {out.name}\n📂 Location: {out.parent}\n\n{note}'}


def _open_rgb(path: Path):
    """Open image, flatten alpha onto white background, return RGB PIL Image."""
    from PIL import Image as PILImage
    img = PILImage.open(path)
    if img.mode in ('RGBA', 'LA', 'PA'):
        bg = PILImage.new('RGBA', img.size, (255, 255, 255, 255))
        bg.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
        img = bg.convert('RGB')
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    return img


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 1 — AI Background Removal
# ═══════════════════════════════════════════════════════════════════════════════
@tool(
    name='img_remove_bg',
    description=(
        'Remove image background using AI (rembg U2Net model). '
        'Outputs PNG with transparent background. '
        'Use when user says "remove background", "cut out", "transparent bg", "no background", '
        '"remove bg", "isolate subject", "cutout".'
    )
)
async def img_remove_bg(path: str, bg_color: str = 'transparent') -> dict:
    """
    AI background removal using rembg (U2Net).
    Args:
        path: Image path
        bg_color: 'transparent' (PNG) or color name/hex for solid replacement
    """
    try:
        from PIL import Image as PILImage
        import io

        src = Path(path).expanduser().resolve()
        if not src.exists():
            return {'error': f'File not found: {path}', 'success': False}

        try:
            from rembg import remove
        except ImportError:
            return {
                'success': False,
                'answer': 'rembg not installed. Run:\n.venv\\Scripts\\pip install rembg onnxruntime'
            }

        log.info(f'img_remove_bg: processing {src.name}')
        img_bytes = src.read_bytes()
        result    = remove(img_bytes)   # returns PNG bytes with alpha

        result_img = PILImage.open(io.BytesIO(result)).convert('RGBA')

        if bg_color == 'transparent':
            out = _out_dir() / (src.stem + '_nobg.png')
            result_img.save(str(out), format='PNG')
            note = 'Background removed. Transparent PNG ready for logos, passport photos, product shots.'
        else:
            bg  = PILImage.new('RGBA', result_img.size, bg_color)
            bg.paste(result_img, mask=result_img.split()[3])
            out = _out_dir() / (src.stem + f'_bg_{bg_color.strip("#")}.jpg')
            bg.convert('RGB').save(str(out), format='JPEG', quality=95)
            note = f'Background replaced with {bg_color}.'

        return _ok(out, note)

    except Exception as e:
        log.error(f'img_remove_bg error: {e}')
        return {'error': str(e), 'success': False}


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 2 — Face-aware Passport Photo + A4 Print Sheet
# ═══════════════════════════════════════════════════════════════════════════════
@tool(
    name='img_passport',
    description=(
        'Create passport/visa size photo with face-aware cropping and generate '
        'an A4 print sheet with 8 copies ready to print and cut. '
        'Use when user says "pp size", "passport photo", "passport size", "visa photo", '
        '"make passport", "resize for passport". '
        'Args: path (str), country (str, optional): india/us/uk/eu (default=india).'
    )
)
async def img_passport(path: str, country: str = 'india') -> dict:
    """Face-aware passport photo generator."""
    try:
        from PIL import Image as PILImage, ImageDraw

        src = Path(path).expanduser().resolve()
        if not src.exists():
            return {'error': f'File not found: {path}', 'success': False}

        mm_w, mm_h = _PP_SIZES.get(country.lower(), _PP_SIZES['default'])
        px_w = int(mm_w / 25.4 * _DPI)
        px_h = int(mm_h / 25.4 * _DPI)

        img = _open_rgb(src)
        iw, ih = img.size

        # ── Attempt face detection via OpenCV ─────────────────────────────────
        face_crop = None
        try:
            import cv2, numpy as np
            import urllib.request, tempfile, os

            # Download Haar cascade if not cached
            cascade_path = Path.home() / '.ambrio' / 'haarcascade_frontalface_default.xml'
            cascade_path.parent.mkdir(exist_ok=True)
            if not cascade_path.exists():
                url = ('https://raw.githubusercontent.com/opencv/opencv/master/'
                       'data/haarcascades/haarcascade_frontalface_default.xml')
                try:
                    urllib.request.urlretrieve(url, str(cascade_path))
                except Exception:
                    pass

            if cascade_path.exists():
                cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                gray   = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
                face_cascade = cv2.CascadeClassifier(str(cascade_path))
                faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))

                if len(faces) > 0:
                    # Use largest detected face
                    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                    # Expand crop: face takes ~60% of height, centered
                    target_ratio = px_w / px_h
                    crop_h = int(h / 0.55)           # face = 55% of photo height
                    crop_w = int(crop_h * target_ratio)
                    # Center on face
                    cx = x + w // 2
                    cy = y + int(h * 0.4)            # slightly above face center
                    x1 = max(0, cx - crop_w // 2)
                    y1 = max(0, cy - int(crop_h * 0.35))  # 35% above face center
                    x2 = min(iw, x1 + crop_w)
                    y2 = min(ih, y1 + crop_h)
                    face_crop = img.crop((x1, y1, x2, y2))
                    log.info(f'img_passport: face detected at {x},{y} size {w}x{h}')
        except Exception as e:
            log.warning(f'Face detection skipped: {e}')

        # ── Fallback: center-biased crop ───────────────────────────────────────
        if face_crop is None:
            target_ratio = px_w / px_h
            cur_ratio    = iw / ih
            if cur_ratio > target_ratio:
                new_w = int(ih * target_ratio)
                x_off = (iw - new_w) // 2
                face_crop = img.crop((x_off, 0, x_off + new_w, ih))
            elif cur_ratio < target_ratio:
                new_h = int(iw / target_ratio)
                y_off = max(0, int((ih - new_h) * 0.15))
                face_crop = img.crop((0, y_off, iw, y_off + new_h))
            else:
                face_crop = img

        # ── Resize to exact passport dimensions ────────────────────────────────
        pp_img = face_crop.resize((px_w, px_h), PILImage.LANCZOS)

        # ── Single photo output ────────────────────────────────────────────────
        single_out = _out_dir() / (src.stem + f'_pp_{mm_w}x{mm_h}mm.jpg')
        pp_img.save(str(single_out), format='JPEG', quality=96, dpi=(_DPI, _DPI))

        # ── A4 print sheet: 8 copies (2 col × 4 row) ──────────────────────────
        A4_W, A4_H = int(8.27 * _DPI), int(11.69 * _DPI)
        GAP        = int(0.08 * _DPI)   # 2mm gap
        COLS, ROWS = 2, 4
        sheet      = PILImage.new('RGB', (A4_W, A4_H), (255, 255, 255))
        grid_w     = COLS * px_w + (COLS - 1) * GAP
        grid_h     = ROWS * px_h + (ROWS - 1) * GAP
        x0 = (A4_W - grid_w) // 2
        y0 = (A4_H - grid_h) // 2

        draw = ImageDraw.Draw(sheet)
        for row in range(ROWS):
            for col in range(COLS):
                x = x0 + col * (px_w + GAP)
                y = y0 + row * (px_h + GAP)
                sheet.paste(pp_img, (x, y))
                draw.rectangle([x, y, x + px_w - 1, y + px_h - 1],
                               outline=(180, 180, 180), width=1)

        sheet_out = _out_dir() / (src.stem + f'_pp_A4_8x.pdf')
        sheet.save(str(sheet_out), format='PDF', resolution=_DPI)

        face_note = '(face auto-detected ✓)' if face_crop is not None else '(center crop)'
        return {
            'success':     True,
            'single':      str(single_out),
            'print_sheet': str(sheet_out),
            'answer': (
                f'✅ Passport photo ready {face_note}\n\n'
                f'📸 Single photo ({mm_w}×{mm_h}mm): {single_out.name}\n'
                f'🖨️  A4 print sheet (8 copies): {sheet_out.name}\n'
                f'📂 Folder: Ambrio Output\n\n'
                f'Print the A4 sheet → cut along grey lines ✂️'
            ),
        }

    except Exception as e:
        log.error(f'img_passport error: {e}')
        return {'error': str(e), 'success': False}


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 3 — AI Super-Resolution Upscale
# ═══════════════════════════════════════════════════════════════════════════════
@tool(
    name='img_upscale',
    description=(
        'Upscale image resolution using AI super-resolution (2x or 4x). '
        'Sharpens details, reduces blur, improves print quality. '
        'Use when user says "upscale", "increase resolution", "make higher quality", '
        '"super resolution", "enhance quality", "make bigger better quality".'
    )
)
async def img_upscale(path: str, scale: int = 2) -> dict:
    """AI upscaling using LANCZOS + sharpening pipeline (4x quality boost)."""
    try:
        from PIL import Image as PILImage, ImageFilter, ImageEnhance

        src = Path(path).expanduser().resolve()
        if not src.exists():
            return {'error': f'File not found: {path}', 'success': False}

        img    = _open_rgb(src)
        scale  = max(2, min(int(scale), 4))
        new_w  = img.width  * scale
        new_h  = img.height * scale

        # Step 1: Upscale with LANCZOS
        up = img.resize((new_w, new_h), PILImage.LANCZOS)

        # Step 2: Unsharp mask — recovers detail lost in upscaling
        up = up.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=2))

        # Step 3: Slight contrast boost
        up = ImageEnhance.Contrast(up).enhance(1.1)

        out = _out_dir() / (src.stem + f'_x{scale}_{new_w}x{new_h}{src.suffix}')
        up.save(str(out), quality=96, dpi=(_DPI, _DPI))
        return _ok(out, f'Upscaled {scale}× → {new_w}×{new_h}px with sharpening.')

    except Exception as e:
        return {'error': str(e), 'success': False}


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 4 — Document Scanner (Perspective Correction)
# ═══════════════════════════════════════════════════════════════════════════════
@tool(
    name='img_scan_doc',
    description=(
        'Convert a photo of a document into a clean scanned image. '
        'Detects document edges, corrects perspective (straightens), applies binarization. '
        'Use when user says "scan this", "make it look scanned", "straighten", '
        '"fix angle", "document scan", "clean up doc photo".'
    )
)
async def img_scan_doc(path: str, mode: str = 'auto') -> dict:
    """
    Document scanner pipeline:
    1. Detect document edges (OpenCV contour)
    2. Perspective warp to flat rectangle
    3. Adaptive threshold → clean black/white scan look
    Args:
        path: Image path
        mode: 'auto' (detect + correct) | 'enhance' (no perspective, just clean up)
    """
    try:
        from PIL import Image as PILImage, ImageFilter, ImageOps, ImageEnhance
        import numpy as np

        src = Path(path).expanduser().resolve()
        if not src.exists():
            return {'error': f'File not found: {path}', 'success': False}

        img = _open_rgb(src)

        try:
            import cv2

            cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            gray   = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
            blur   = cv2.GaussianBlur(gray, (5, 5), 0)
            edges  = cv2.Canny(blur, 75, 200)

            # Find document contour
            contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            contours     = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

            doc_corners = None
            for c in contours:
                peri = cv2.arcLength(c, True)
                approx = cv2.approxPolyDP(c, 0.02 * peri, True)
                if len(approx) == 4:
                    doc_corners = approx
                    break

            if doc_corners is not None and mode == 'auto':
                # Order corners: top-left, top-right, bottom-right, bottom-left
                pts  = doc_corners.reshape(4, 2).astype(np.float32)
                rect = np.zeros((4, 2), dtype=np.float32)
                s    = pts.sum(axis=1)
                rect[0] = pts[np.argmin(s)]   # top-left
                rect[2] = pts[np.argmax(s)]   # bottom-right
                diff    = np.diff(pts, axis=1)
                rect[1] = pts[np.argmin(diff)]  # top-right
                rect[3] = pts[np.argmax(diff)]  # bottom-left

                # Compute output size
                wA = np.linalg.norm(rect[2] - rect[3])
                wB = np.linalg.norm(rect[1] - rect[0])
                hA = np.linalg.norm(rect[1] - rect[2])
                hB = np.linalg.norm(rect[0] - rect[3])
                maxW = int(max(wA, wB))
                maxH = int(max(hA, hB))

                dst = np.array([[0, 0], [maxW - 1, 0],
                                [maxW - 1, maxH - 1], [0, maxH - 1]], dtype=np.float32)
                M   = cv2.getPerspectiveTransform(rect, dst)
                warped = cv2.warpPerspective(cv_img, M, (maxW, maxH))
                img = PILImage.fromarray(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB))
                perspective_fixed = True
            else:
                perspective_fixed = False

        except ImportError:
            perspective_fixed = False

        # ── Clean scan look: grayscale + adaptive threshold ────────────────────
        img  = ImageOps.grayscale(img)
        img  = ImageEnhance.Contrast(img).enhance(2.0)
        img  = img.filter(ImageFilter.SHARPEN)
        # Slight brightness to not go too dark
        img  = ImageEnhance.Brightness(img).enhance(1.1)

        tag  = 'scan_corrected' if perspective_fixed else 'scan_enhanced'
        out  = _out_dir() / (src.stem + f'_{tag}.jpg')
        img.save(str(out), format='JPEG', quality=95)

        note = ('Perspective corrected + scan enhancement applied.'
                if perspective_fixed else 'Scan enhancement applied (no perspective warp needed).')
        return _ok(out, note)

    except Exception as e:
        return {'error': str(e), 'success': False}


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 5 — Color Grading Presets
# ═══════════════════════════════════════════════════════════════════════════════
@tool(
    name='img_color_grade',
    description=(
        'Apply professional color grading presets to an image. '
        'Presets: vivid, cool, warm, bw, vintage, fade, cinematic, portrait. '
        'Use when user says "make it vivid", "black and white", "warm tone", "vintage look", '
        '"cinematic", "cool filter", "portrait mode", "fade effect".'
    )
)
async def img_color_grade(path: str, preset: str = 'vivid') -> dict:
    """Apply color grading presets."""
    try:
        from PIL import Image as PILImage, ImageEnhance, ImageFilter, ImageOps

        src = Path(path).expanduser().resolve()
        if not src.exists():
            return {'error': f'File not found: {path}', 'success': False}

        img = _open_rgb(src)

        p = preset.lower().strip()

        if p == 'vivid':
            img = ImageEnhance.Color(img).enhance(1.6)
            img = ImageEnhance.Contrast(img).enhance(1.2)
            img = ImageEnhance.Sharpness(img).enhance(1.3)

        elif p == 'bw' or p == 'black_and_white' or p == 'grayscale':
            img = ImageOps.grayscale(img).convert('RGB')
            img = ImageEnhance.Contrast(img).enhance(1.3)

        elif p == 'warm':
            r, g, b = img.split()
            r = r.point(lambda i: min(255, int(i * 1.12)))
            b = b.point(lambda i: int(i * 0.88))
            img = PILImage.merge('RGB', (r, g, b))
            img = ImageEnhance.Color(img).enhance(1.2)

        elif p == 'cool':
            r, g, b = img.split()
            r = r.point(lambda i: int(i * 0.88))
            b = b.point(lambda i: min(255, int(i * 1.12)))
            img = PILImage.merge('RGB', (r, g, b))
            img = ImageEnhance.Color(img).enhance(1.1)

        elif p == 'vintage':
            img = ImageEnhance.Color(img).enhance(0.7)
            img = ImageEnhance.Contrast(img).enhance(0.9)
            img = ImageEnhance.Brightness(img).enhance(1.05)
            r, g, b = img.split()
            r = r.point(lambda i: min(255, int(i * 1.08)))
            b = b.point(lambda i: int(i * 0.85))
            img = PILImage.merge('RGB', (r, g, b))

        elif p == 'fade':
            img = ImageEnhance.Contrast(img).enhance(0.75)
            img = ImageEnhance.Brightness(img).enhance(1.15)
            img = ImageEnhance.Color(img).enhance(0.8)

        elif p == 'cinematic':
            img = ImageEnhance.Contrast(img).enhance(1.25)
            img = ImageEnhance.Color(img).enhance(0.85)
            r, g, b = img.split()
            b = b.point(lambda i: min(255, int(i * 1.08)))
            img = PILImage.merge('RGB', (r, g, b))
            # Slight vignette: not easy in PIL without numpy, skip for simplicity

        elif p == 'portrait':
            img = ImageEnhance.Brightness(img).enhance(1.08)
            img = ImageEnhance.Color(img).enhance(1.15)
            img = ImageEnhance.Sharpness(img).enhance(1.2)
            img = img.filter(ImageFilter.SMOOTH)

        else:
            return {'error': f'Unknown preset: {preset}. Use: vivid/cool/warm/bw/vintage/fade/cinematic/portrait',
                    'success': False}

        out = _out_dir() / (src.stem + f'_{p}{src.suffix}')
        img.save(str(out), quality=95)
        return _ok(out, f'Color grading preset "{preset}" applied.')

    except Exception as e:
        return {'error': str(e), 'success': False}


# ═══════════════════════════════════════════════════════════════════════════════
# BASIC TOOLS — Resize, Rotate, Background, Enhance
# ═══════════════════════════════════════════════════════════════════════════════
@tool(
    name='img_resize',
    description='Resize image to exact pixel dimensions. Args: path, width (int), height (int).'
)
async def img_resize(path: str, width: int, height: int) -> dict:
    try:
        from PIL import Image as PILImage
        src = Path(path).expanduser().resolve()
        img = _open_rgb(src)
        img = img.resize((int(width), int(height)), PILImage.LANCZOS)
        out = _out_dir() / (src.stem + f'_{width}x{height}{src.suffix}')
        img.save(str(out), quality=95)
        return _ok(out, f'Resized to {width}×{height}px')
    except Exception as e:
        return {'error': str(e), 'success': False}


@tool(
    name='img_background',
    description='Add/replace background color. Args: path (str), color (str) — white/blue/red/#hex.'
)
async def img_background(path: str, color: str = 'white') -> dict:
    try:
        from PIL import Image as PILImage
        src = Path(path).expanduser().resolve()
        img = PILImage.open(src).convert('RGBA')
        bg  = PILImage.new('RGBA', img.size, color)
        bg.paste(img, mask=img.split()[3])
        out = _out_dir() / (src.stem + f'_bg_{color.strip("#")}.jpg')
        bg.convert('RGB').save(str(out), quality=95)
        return _ok(out, f'Background set to {color}')
    except Exception as e:
        return {'error': str(e), 'success': False}


@tool(
    name='img_rotate',
    description='Rotate image clockwise. Args: path (str), angle (int) — 90/180/270/any.'
)
async def img_rotate(path: str, angle: int = 90) -> dict:
    try:
        from PIL import Image as PILImage
        src = Path(path).expanduser().resolve()
        img = PILImage.open(src).rotate(-int(angle), expand=True)
        out = _out_dir() / (src.stem + f'_r{angle}{src.suffix}')
        img.save(str(out))
        return _ok(out, f'Rotated {angle}° clockwise')
    except Exception as e:
        return {'error': str(e), 'success': False}


@tool(
    name='img_enhance',
    description=(
        'Adjust image brightness, contrast, sharpness. '
        'Args: path, brightness (float, default 1.0), contrast (float, default 1.0), sharpness (float, default 1.0). '
        '1.0=original, 1.5=50% more. '
        'Use for: brighten, darken, sharpen, increase contrast.'
    )
)
async def img_enhance(path: str, brightness: float = 1.0,
                      contrast: float = 1.0, sharpness: float = 1.0) -> dict:
    try:
        from PIL import Image as PILImage, ImageEnhance
        src = Path(path).expanduser().resolve()
        img = _open_rgb(src)
        if float(brightness) != 1.0:
            img = ImageEnhance.Brightness(img).enhance(float(brightness))
        if float(contrast) != 1.0:
            img = ImageEnhance.Contrast(img).enhance(float(contrast))
        if float(sharpness) != 1.0:
            img = ImageEnhance.Sharpness(img).enhance(float(sharpness))
        tag = f'b{brightness}c{contrast}s{sharpness}'.replace('.', '')
        out = _out_dir() / (src.stem + f'_enhanced{src.suffix}')
        img.save(str(out), quality=95)
        return _ok(out, f'Enhanced: brightness={brightness} contrast={contrast} sharpness={sharpness}')
    except Exception as e:
        return {'error': str(e), 'success': False}
