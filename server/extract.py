"""Turn uploaded source documents into plain text for the prompt, and into
page images so a document the user attached can actually be *shown* on a slide."""
from __future__ import annotations

import io
import re
import zipfile

MAX_CHARS = 60000
MAX_PAGES = 12       # pages rendered per document (enough for a letter or a certificate)
IMAGE_EXT = ("png", "jpg", "jpeg", "gif", "bmp", "webp", "tif", "tiff")


def _xml_text(xml: str, para_tag: str) -> str:
    xml = re.sub(rf"</{para_tag}>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)


def extract_text(name: str, data: bytes) -> str:
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    text = ""
    if ext == "pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages[:80])
    elif ext == "docx":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            text = _xml_text(z.read("word/document.xml").decode("utf-8", "ignore"), "w:p")
    elif ext in ("xlsx", "xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        parts = []
        for ws in wb.worksheets[:6]:
            rows = []
            for row in ws.iter_rows(values_only=True):
                if row and any(v is not None for v in row):
                    rows.append(",".join("" if v is None else str(v).replace(",", " ") for v in row))
                if len(rows) >= 400:
                    rows.append("... (truncated)")
                    break
            parts.append(f"[Sheet: {ws.title}] (CSV)\n" + "\n".join(rows))
        text = "\n\n".join(parts)
    elif ext in ("pptx", "potx"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            slides = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                            key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[-1]).group(1)))
            parts = [f"[Slide {i + 1}]\n" + _xml_text(z.read(n).decode("utf-8", "ignore"), "a:p") for i, n in enumerate(slides)]
            text = "\n\n".join(parts)
    elif ext in IMAGE_EXT:
        text = ""  # a picture has no text; its page image is what matters
    else:
        text = data.decode("utf-8", "ignore")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:MAX_CHARS]


def extract_pages(name: str, data: bytes) -> list[tuple[int, bytes]]:
    """Pages of the document as PNG bytes: [(page number, png)].

    PDFs are rasterized page by page; a plain image counts as its own single page.
    This is what lets a slide show the real offer letter or certificate the user
    attached instead of only its text."""
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    out: list[tuple[int, bytes]] = []
    if ext in IMAGE_EXT:
        try:
            from PIL import Image
            with Image.open(io.BytesIO(data)) as im:
                buf = io.BytesIO()
                im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB").save(buf, "PNG")
                return [(1, buf.getvalue())]
        except Exception:
            return []
    if ext != "pdf":
        return []
    try:
        import pypdfium2
    except ImportError:  # no renderer available: the document's text is still used
        return []
    try:
        doc = pypdfium2.PdfDocument(io.BytesIO(data))
    except Exception:
        return []
    try:
        for i in range(min(len(doc), MAX_PAGES)):
            try:
                img = doc[i].render(scale=2).to_pil()  # ~144dpi: crisp on a slide, still small
                if min(img.size) < 200:
                    continue
                img.thumbnail((1700, 2200))
                buf = io.BytesIO()
                img.convert("RGB").save(buf, "JPEG", quality=88)
                out.append((i + 1, buf.getvalue()))
            except Exception:
                continue
    finally:
        try:
            doc.close()
        except Exception:
            pass
    return out