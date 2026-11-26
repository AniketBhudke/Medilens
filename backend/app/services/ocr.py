"""Image pre-processing, blur / quality guardrail and optional classic OCR pre-pass."""
import io

import numpy as np
from PIL import Image, ImageOps

BLUR_THRESHOLD = 60.0     # variance of Laplacian below this = too blurry
MIN_SIDE = 500            # px
MAX_SIDE = 2000           # downscale for the AI call


def _laplacian_variance(gray: np.ndarray) -> float:
    g = gray.astype(np.float32)
    lap = (-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:])
    return float(lap.var())


def assess_and_prepare(data: bytes) -> tuple[bytes, dict]:
    """Return (jpeg_bytes, quality_report)."""
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    w, h = img.size
    gray = np.asarray(ImageOps.grayscale(img))
    # judge sharpness on a normalised size so big and small photos compare fairly
    probe = ImageOps.grayscale(img)
    probe.thumbnail((1200, 1200))
    blur = _laplacian_variance(np.asarray(probe))
    brightness = float(gray.mean())

    issues = []
    if min(w, h) < MIN_SIDE:
        issues.append("The image resolution is very low.")
    if blur < BLUR_THRESHOLD:
        issues.append("The photo looks blurry.")
    if brightness < 50:
        issues.append("The photo is too dark.")
    if brightness > 235:
        issues.append("The photo is overexposed.")

    scale = MAX_SIDE / max(w, h)
    if scale < 1:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    report = {
        "width": w, "height": h, "blur_score": round(blur, 1), "brightness": round(brightness, 1),
        "is_poor": bool(issues), "issues": issues,
    }
    return buf.getvalue(), report


def optional_ocr_text(jpeg_bytes: bytes) -> str:
    """Classic OCR (Tesseract) hint passed to the AI as a cross-check. Silent no-op if not installed."""
    try:
        import pytesseract  # type: ignore
        return pytesseract.image_to_string(Image.open(io.BytesIO(jpeg_bytes)))[:4000]
    except Exception:
        return ""
