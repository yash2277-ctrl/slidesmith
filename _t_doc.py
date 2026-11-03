"""End-to-end: attach a real PDF, resolve its page, render it onto a slide, export pptx."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from server import media, themes
from server.extract import extract_pages, extract_text
from server.layout import layout_slide
from server.media import resolve_document
from server.raster import inspect
from server.renderer import build_pptx
from server.slide_schema import normalize, validate

pdf = Path(sys.argv[1] if len(sys.argv) > 1 else Path.home() / "Downloads" / "Bipin Chaudhary.pdf")
data = pdf.read_bytes()
name = pdf.name
print("file:", name, len(data), "bytes")

text = extract_text(name, data)
print("text chars:", len(text), "|", text[:90].replace("\n", " "))

pages = []
for num, png in extract_pages(name, data):
    saved = media.save_page(png, "testtag", num)
    if saved:
        pages.append(saved)
print("pages rendered:", len(pages), pages[0]["src"] if pages else "", pages[0]["w"], "x", pages[0]["h"] if pages else "")
print("resolves on disk:", bool(media.local_path(pages[0]["src"])))

sources = [{"name": name, "text": text, "pages": pages, "doc_id": "#D1"}]

theme = {**themes.get_builtin("clean"), "dna": {}}
spec = normalize({"type": "document", "title": "Offer letter", "doc": "#D1", "pages": [1],
                  "caption": "CodeAlpha offer letter - Bipin Chaudhary"})
print("validate:", validate(spec))
resolve_document(spec, sources)
print("page_images:", spec.get("page_images"), "doc_name:", spec.get("doc_name"))

lay = layout_slide(spec, theme, 0, [spec], "Internship")
png, issues = inspect(lay, spec, theme)
Path("_t_doc_real.png").write_bytes(png)
imgs = [e for e in lay["elements"] if e["t"] == "image"]
print("issues:", issues)
for e in imgs:
    print("IMG x=%.2f y=%.2f w=%.2f h=%.2f src=%s" % (e["x"], e["y"], e["w"], e["h"], e["src"]))

# a stale handle must degrade, not explode
bad = normalize({"type": "document", "title": "Missing", "doc": "#D9", "pages": [3]})
resolve_document(bad, sources)
print("stale doc ->", bad.get("page_images"))
badlay = layout_slide(bad, theme, 1, [bad], "Internship")
print("stale layout els:", len(badlay["elements"]))

out = Path("_t_doc.pptx")
build_pptx([{"spec": spec, "status": "done"}, {"spec": bad, "status": "done"}], theme, "Internship", out)
print("pptx:", out, out.stat().st_size, "bytes")

from pptx import Presentation
pr = Presentation(str(out))
sl = pr.slides[0]
print("slide1 shapes:", [(sh.shape_type, sh.name) for sh in sl.shapes])
print("pictures:", len([sh for sh in sl.shapes if sh.shape_type == 13]))
print("OK")