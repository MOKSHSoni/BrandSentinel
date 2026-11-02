"""Content intake: plain text, DOCX, PDF, images and web pages become one normalised text string, plus the
images found in them (see services/images.py)."""

import io
import re
import zipfile

from . import images

MAX_BYTES = 5 * 1024 * 1024
MAX_CHARS = 20_000
MAX_UNZIPPED = 60 * 1024 * 1024

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


class IntakeError(ValueError):
    pass


def _docx(data: bytes) -> tuple[str, list[dict]]:
    from docx import Document

    with zipfile.ZipFile(io.BytesIO(data)) as z:  # a small .docx can unpack to gigabytes
        if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
            raise IntakeError("This Word file is too large once unpacked.")
    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    assets = []
    # Inline and floating pictures; Word keeps the alt text in wp:docPr/@descr.
    for frame in doc.element.body.xpath(".//wp:inline | .//wp:anchor"):
        doc_pr = frame.find("wp:docPr", NS)
        blip = frame.find(".//a:blip", NS)
        if blip is None or len(assets) >= images.MAX_IMAGES:
            continue
        rid = blip.get(f"{{{NS['r']}}}embed")
        part = doc.part.related_parts.get(rid)
        if part is None:
            continue
        alt = (doc_pr.get("descr") or doc_pr.get("title") or "").strip() if doc_pr is not None else ""
        name = part.partname.split("/")[-1]
        assets.append(images.analyse_image(part.blob, name, "docx", alt))
    return "\n\n".join(p for p in parts if p.strip()), assets


def _pdf(data: bytes) -> tuple[str, list[dict]]:
    """Page text plus embedded pictures, so a scanned PDF is read by OCR like any other image."""
    import fitz

    assets: list[dict] = []
    seen: set[int] = set()
    with fitz.open(stream=data, filetype="pdf") as pdf:
        text = "\n\n".join(page.get_text() for page in pdf)
        for page in pdf:
            for info in page.get_images(full=True):
                xref, width, height = info[0], info[2], info[3]
                if xref in seen or min(width, height) < 48 or len(assets) >= images.MAX_IMAGES:
                    continue
                seen.add(xref)
                name = f"page {page.number + 1} picture {len(assets) + 1}"
                if width * height > images.MAX_PIXELS:
                    assets.append(images.failed_asset(name, "pdf", f"The image is too large ({width}×{height} pixels)."))
                    continue
                pix = fitz.Pixmap(pdf, xref)
                if pix.n - pix.alpha > 3:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                assets.append(images.analyse_image(pix.tobytes("png"), name, "pdf", None))
    return text, assets


def with_image_blocks(text: str, assets: list[dict]) -> str:
    blocks = [images.image_block(i + 1, a) for i, a in enumerate(assets)]
    return "\n\n".join(p for p in [text.strip(), *blocks] if p)


def extract(filename: str, data: bytes) -> tuple[str, list[dict]]:
    if len(data) > MAX_BYTES:
        raise IntakeError("File is larger than 5 MB.")
    name = filename.lower()
    assets: list[dict] = []
    try:
        if name.endswith(".docx"):
            text, assets = _docx(data)
        elif name.endswith(".pdf"):
            text, assets = _pdf(data)
            if not text.strip() and not assets:
                raise IntakeError("No readable text or pictures were found in this PDF.")
        elif name.endswith((".txt", ".md")):
            text = data.decode("utf-8", errors="replace")
        elif name.endswith(images.IMAGE_EXTS):
            asset = images.analyse_image(data, filename, "upload", None)
            if asset.get("error"):
                raise IntakeError(asset["error"])
            text, assets = "", [asset]
        else:
            raise IntakeError("Upload a .docx, .pdf, .txt or image (.png, .jpg, .webp) file.")
    except IntakeError:
        raise
    except Exception as e:
        raise IntakeError(f"Could not read {filename}: {e}") from e
    return normalise(with_image_blocks(text, assets)), assets


def extract_text(filename: str, data: bytes) -> str:
    return extract(filename, data)[0]


def normalise(text: str, truncate: bool = False) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise IntakeError("The draft is empty.")
    if len(text) > MAX_CHARS:
        if not truncate:
            raise IntakeError(f"Drafts are limited to {MAX_CHARS:,} characters.")
        cut = text.rfind("\n\n", 0, MAX_CHARS)
        text = text[: cut if cut > 0 else MAX_CHARS]
    return text


def make_docx(title: str, content: str, image: bytes | None = None) -> bytes:
    from docx import Document
    from docx.shared import Inches

    doc = Document()
    doc.core_properties.title = title
    for para in content.split("\n\n"):
        doc.add_paragraph(para)
    if image:
        doc.add_picture(io.BytesIO(image), width=Inches(5))  # no alt text, on purpose, for the demo
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
