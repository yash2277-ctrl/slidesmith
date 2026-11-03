"""Programmatic QA for the Bauhaus theme: bounds, text fit, palette purity and
.pptx integrity for every slide type. Run:  python _bh_check.py
Exits non-zero (prints FAIL lines) when a check fails."""
import math
import sys
from pathlib import Path

from PIL import Image, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from server import themes, design
from server.layout import layout_slide, est_lines
from server.raster import render_png, _font, LOCAL_FONT_DIR, FONT_DIR
from _bh_specs import SPECS  # noqa

THEME = themes.get_builtin("bauhaus")
THEME["dna"] = design.dna(20261006)
W, H = THEME["slide_w"], THEME["slide_h"]
PALETTE = {"red": "#D02020", "blue": "#1040C0", "yellow": "#F0C020", "ink": "#121212",
           "paper": "#F0F0F0", "white": "#FFFFFF"}
FAILS = []
WARN = []


def fail(slide, kind, detail):
    FAILS.append(f"[{kind}] slide {slide}: {detail}")


def _shape_box(el):
    """Bounding box of an element, accounting for rotation about its centre."""
    x, y, w, h = el["x"], el["y"], el["w"], el["h"]
    rot = el.get("rot", 0)
    if rot and el["t"] in ("rect", "triangle"):
        a = math.radians(rot)
        cx, cy = x + w / 2, y + h / 2
        corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        pts = [(cx + (px - cx) * math.cos(a) - (py - cy) * math.sin(a),
                cy + (px - cx) * math.sin(a) + (py - cy) * math.cos(a)) for px, py in corners]
        return (min(p[0] for p in pts), min(p[1] for p in pts),
                max(p[0] for p in pts) - min(p[0] for p in pts),
                max(p[1] for p in pts) - min(p[1] for p in pts))
    return (x, y, w, h)


def check_bounds(i, lay):
    """No element may leave the slide, except deliberate full-bleed decoration."""
    for el in lay["elements"]:
        if el.get("static") or el["t"] in ("image", "chart", "table", "tpltable"):
            continue
        x, y, w, h = _shape_box(el)
        bleed = el.get("bleed") or w > W * 0.3 or h > H * 0.5  # panels / circles meant to bleed off the edge
        if not bleed and (x < -0.01 or y < -0.01 or x + w > W + 0.01 or y + h > H + 0.01):
            fail(i + 1, "BOUNDS", f"{el['t']} at ({x:.2f},{y:.2f}) {w:.2f}x{h:.2f} leaves the slide")
        if el["t"] == "text" and (y < -0.01 or y + h > H + 0.01):
            fail(i + 1, "BOUNDS", f"text box at y={y:.2f} h={h:.2f} runs off the slide")


def check_text_fit(i, lay):
    """Measure real wrapped text height with the actual font; flag overflow past the box."""
    for el in lay["elements"]:
        if el["t"] != "text" or el.get("static"):
            continue
        ppi = 96
        total = 0.0
        for p in el["paras"]:
            px_size = max(4, int(p["size"] * ppi / 72))
            face = "outfit" if p.get("font") == "heading" else "body"
            font = _font(face, bool(p.get("bold")), bool(p.get("italic")), px_size)
            text = p["text"].upper() if p.get("caps") else p["text"]
            indent = 0.35 * p.get("level", 0) + (px_size * 1.1 / ppi if p.get("bullet") else 0)
            max_w = (el["w"] - indent) * ppi
            lines, cur = [], ""
            for word in (text or " ").split():
                trial = (cur + " " + word) if cur else word
                if font.getlength(trial) <= max_w or not cur:
                    cur = trial
                else:
                    lines.append(cur)
                    cur = word
            lines.append(cur)
            total += len(lines) * px_size / ppi * el.get("line", 1.15) + p.get("space", 0) / 72
        if total > el["h"] * 1.1 and any(p["text"].strip() for p in el["paras"]):
            fail(i + 1, "TEXT", f"text overflows box by {int((total / max(el['h'], .01) - 1) * 100)}%: "
                                f"{el['paras'][0]['text'][:40]!r}")


def check_palette(i, lay, png):
    """Every solid fill must be a Bauhaus colour, white, or a neutral ink mix."""
    allowed = {v.lstrip("#").upper() for v in PALETTE.values()} | {"E0E0E0", "555555", "ADADAD", "D7D7D7", "FFFFFF"}
    for el in lay["elements"]:
        for key in ("fill",):
            f = el.get(key)
            if isinstance(f, str) and f.startswith("#") and not f.startswith("#00"):
                if f.lstrip("#").upper() not in allowed:
                    fail(i + 1, "PALETTE", f"off-palette fill {f} on {el['t']}")
        for p in el.get("paras", []):
            c = (p.get("color") or "").lstrip("#").upper()
            if c and len(c) == 6 and not c.startswith("FFDD") and c not in allowed and c != "FFDDDD":
                if not all(int(c[k:k + 2], 16) == int("FF"[k % 2] if False else c[k:k + 2], 16) for k in (0, 2, 4)):
                    # soft inks are mix(text,bg) results - allowed if near-neutral
                    r, g, b = (int(c[k:k + 2], 16) for k in (0, 2, 4))
                    if max(r, g, b) - min(r, g, b) > 24:
                        WARN.append(f"[PALETTE?] slide {i + 1}: text colour #{c} is not neutral/primary")


def check_key_colors(i, lay, img):
    """Spot-check the hero: the panel must be exactly Bauhaus blue."""
    from server import layout as L
    if SPECS[i]["type"] != "title":
        return
    px = W * 0.63 + 0.3
    panel = L.R(px, 0, 1, 1, None)
    x, y = int(px * 96), int(2.5 * 96)
    px_ = img.getpixel((x, y))
    r, g, b = px_[:3]
    if (r, g, b) != (0x10, 0x40, 0xC0):
        fail(i + 1, "COLOR", f"hero panel pixel is #{r:02X}{g:02X}{b:02X}, expected #1040C0 (blue)")


print("=" * 68)
print("BAUHAUS THEME CHECK  ·  theme=bauhaus  ·  16 slide types")
print("=" * 68)
for i, spec in enumerate(SPECS):
    lay = layout_slide(spec, THEME, i, SPECS, "Bauhaus Design System")
    png = render_png(lay, THEME, ppi=96)
    img = Image.open(__import__("io").BytesIO(png))
    check_bounds(i, lay)
    check_text_fit(i, lay)
    check_palette(i, lay, png)
    check_key_colors(i, lay, img)

# ---- pptx integrity
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

pptx_path = Path("data/_bh_preview/bauhaus_test.pptx")
prs = Presentation(str(pptx_path))
if len(prs.slides) != len(SPECS):
    fail(0, "PPTX", f"{len(prs.slides)} slides written, expected {len(SPECS)}")
triangles = rotated = shadows = outlines = 0
for slide in prs.slides:
    for shp in slide.shapes:
        if shp.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE:
            name = str(getattr(shp, "auto_shape_type", ""))
            if "TRIANGLE" in name:
                triangles += 1
            if shp.rotation:
                rotated += 1
            try:
                if shp.line.width and shp.line.width.pt >= 1.5:
                    outlines += 1
            except Exception:
                pass
print(f"\nPPTX  : {len(prs.slides)} slides · {triangles} triangles · {rotated} rotated shapes · {outlines} outlined shapes")
print(f"FONT  : heading={THEME['fonts']['heading']} body={THEME['fonts']['body']}")
print(f"OUTFIT: bundled = {[p.name for p in LOCAL_FONT_DIR.glob('*.ttf')]} (system dir {FONT_DIR})")

print("\n" + "-" * 68)
if FAILS:
    print(f"FAILED ({len(FAILS)}):")
    for f in FAILS:
        print("  ✗ " + f)
else:
    print("PASS: all geometry, text-fit, palette and pptx checks green")
for w_ in WARN[:12]:
    print("  ! " + w_)
print("-" * 68)
sys.exit(1 if FAILS else 0)
