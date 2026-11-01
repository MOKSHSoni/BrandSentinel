"""Image checks: OCR (so claims inside images are verified like any other text), WCAG contrast measured on
the detected text pixels, dominant colours for the palette check, and alt text.

Measurements are stored with the draft version; pass/fail is decided at review time by the accessibility and
palette rules, so an admin changing a threshold re-evaluates stored images without re-uploading them.
"""

import base64
import io
import logging
import re
import threading
from pathlib import Path

log = logging.getLogger("brandsentinel.images")

MAX_SIDE = 1280
OCR_CONFIG = Path(__file__).with_name("ocr_config.yaml")  # single-threaded, no angle model, no upscaling
MAX_IMAGES = 8
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
_engine = None
_engine_failed = False
_lock = threading.Lock()
_infer_lock = threading.Lock()  # one OCR at a time, so simultaneous uploads never stack their memory peaks


def warm_up() -> None:
    """Load OCR while the server is idle (called in a background thread at start-up), so the one-time
    load spike never coincides with a user's upload."""
    _ocr_engine()


def _ocr_engine():
    """Load RapidOCR on first use only (about 100 MB); None if it cannot be loaded on this host."""
    global _engine, _engine_failed
    if _engine is not None or _engine_failed:
        return _engine
    with _lock:
        if _engine is None and not _engine_failed:
            try:
                from rapidocr_onnxruntime import RapidOCR

                _engine = RapidOCR(config_path=str(OCR_CONFIG))
            except Exception as e:  # missing package, missing system library, out of memory
                log.warning("OCR unavailable: %s", e)
                _engine_failed = True
    return _engine


def load_image(data: bytes):
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    img.load()
    img = img.convert("RGB")
    if max(img.size) > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE))
    return img


def _clean_ocr(text: str) -> str:
    # OCR often reads a final capital I as a lower-case l in acronyms ("UPl"); restore it.
    text = re.sub(r"\b([A-Z]{2,})l\b", lambda m: m.group(1) + "I", text)
    return re.sub(r"\s+", " ", text).strip()


def run_ocr(img) -> tuple[str, list[dict]]:
    engine = _ocr_engine()
    if engine is None:
        return "unavailable", []
    import numpy as np

    with _infer_lock:
        result, _ = engine(np.asarray(img))
    lines = []
    for box, text, conf in result or []:
        conf = float(conf)
        text = _clean_ocr(text)
        if conf < 0.5 or not text:
            continue
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        lines.append({"text": text, "box": [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))],
                      "conf": round(conf, 2)})
    lines.sort(key=lambda l: (l["box"][1], l["box"][0]))
    return ("ok" if lines else "no_text"), lines


def _luminance(rgb) -> float:
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast_ratio(a, b) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def hex_of(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(int(round(c)) for c in rgb))


def rgb_of(hex_colour: str) -> tuple[int, int, int]:
    h = hex_colour.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def text_contrast(img, box) -> dict | None:
    """Split the pixels inside a text box into two groups by brightness (Otsu); the larger group is the
    background, the smaller the text. Contrast is the WCAG ratio between the two average colours."""
    import numpy as np

    x0, y0, x1, y1 = box
    crop = np.asarray(img.crop((x0, y0, max(x1, x0 + 1), max(y1, y0 + 1))), dtype=float).reshape(-1, 3)
    if len(crop) < 20:
        return None
    lum = crop @ np.array([0.2126, 0.7152, 0.0722])
    hist, edges = np.histogram(lum, bins=64, range=(0, 255))
    total, best, threshold = lum.size, -1.0, lum.mean()
    cum_w, cum_m, mean_all = 0.0, 0.0, (hist * (edges[:-1] + edges[1:]) / 2).sum()
    for i in range(64):
        cum_w += hist[i]
        cum_m += hist[i] * (edges[i] + edges[i + 1]) / 2
        if cum_w == 0 or cum_w == total:
            continue
        w0, w1 = cum_w / total, 1 - cum_w / total
        m0, m1 = cum_m / cum_w, (mean_all - cum_m) / (total - cum_w)
        between = w0 * w1 * (m0 - m1) ** 2
        if between > best:
            best, threshold = between, edges[i + 1]
    dark, light = crop[lum < threshold], crop[lum >= threshold]
    if len(dark) == 0 or len(light) == 0:
        return None
    bg, fg = (light, dark) if len(light) >= len(dark) else (dark, light)
    bg_c, fg_c = bg.mean(axis=0), fg.mean(axis=0)
    return {"ratio": round(contrast_ratio(fg_c, bg_c), 2), "fg": hex_of(fg_c), "bg": hex_of(bg_c),
            "large": (y1 - y0) >= 32}


def dominant_colours(img, k: int = 6) -> list[dict]:
    from PIL import Image

    small = img.copy()
    small.thumbnail((128, 128), Image.NEAREST)  # no smoothing: every pixel keeps a colour from the image
    q = small.quantize(colors=k, method=2)
    palette = q.getpalette()
    counts = sorted(q.getcolors(), reverse=True)
    total = sum(c for c, _ in counts)
    out = []
    for count, idx in counts:
        rgb = palette[idx * 3 : idx * 3 + 3]
        out.append({"hex": hex_of(rgb), "share": round(count / total, 3)})
    return out


def preview(img, max_side: int = 640) -> str:
    p = img.copy()
    p.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    p.save(buf, format="JPEG", quality=78)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def analyse_image(data: bytes, name: str, source: str, alt: str | None) -> dict:
    """Everything the review needs about one image. alt is None when the format has no alt text concept
    (a directly uploaded image) or the attribute is missing."""
    asset = {"name": name, "source": source, "alt": alt, "ocr_status": "failed", "lines": [], "colours": [],
             "width": 0, "height": 0, "preview": ""}
    try:
        img = load_image(data)
    except Exception as e:
        asset["error"] = f"Could not open the image: {e}"
        return asset
    asset.update(width=img.size[0], height=img.size[1], preview=preview(img), colours=dominant_colours(img))
    status, lines = run_ocr(img)
    for line in lines:
        line["contrast"] = text_contrast(img, line["box"])
    asset.update(ocr_status=status, lines=lines)
    return asset


# ---------- image blocks inside the draft text ----------

HEADER_RE = re.compile(r"^\[Image (\d+): ([^\]\n]*)\][ \t]*$", re.M)


def image_block(index: int, asset: dict) -> str:
    """How an image appears in the draft text: a header line, then the text read from it."""
    body = "\n".join(l["text"] for l in asset.get("lines", []))
    return f"[Image {index}: {asset['name']}]" + (f"\n{body}" if body else "")


def parse_blocks(text: str) -> list[dict]:
    """Locate each image block: header span, body span and the span of every OCR line."""
    blocks = []
    for m in HEADER_RE.finditer(text):
        body_start = m.end() + 1 if text[m.end() : m.end() + 1] == "\n" else m.end()
        end = text.find("\n\n", body_start)
        body_end = len(text) if end < 0 else end
        lines, pos = [], body_start
        for line in text[body_start:body_end].split("\n"):
            lines.append((pos, pos + len(line)))
            pos += len(line) + 1
        blocks.append({"index": int(m.group(1)), "header": (m.start(), m.end()),
                       "body": (body_start, body_end), "lines": lines if body_end > body_start else []})
    return blocks


def mask_headers(text: str) -> str:
    """Blank out header lines (same length) so '[Image 1: banner.png]' is never read as a claim."""
    return HEADER_RE.sub(lambda m: " " * len(m.group(0)), text)
