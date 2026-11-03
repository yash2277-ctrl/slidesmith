"""Ad-hoc audit of the bauhaus CLOSING slide (_bh_hero closing branch).
Run:  python _bh_closing_audit.py
Prints every element's geometry and measures real wrapped text with the shipped font.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from server import themes, design
from server.layout import layout_slide
from server.raster import _font
from _bh_specs import SPECS

THEME = themes.get_builtin("bauhaus")
THEME["dna"] = design.dna(20261006)
W, H = THEME["slide_w"], THEME["slide_h"]
PPI = 96


def rot_box(el):
    x, y, w, h = el["x"], el["y"], el["w"], el["h"]
    rot = el.get("rot", 0)
    if rot and el["t"] in ("rect", "triangle", "ellipse"):
        a = math.radians(rot)
        cx, cy = x + w / 2, y + h / 2
        pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        rp = [(cx + (px - cx) * math.cos(a) - (py - cy) * math.sin(a),
               cy + (px - cx) * math.sin(a) + (py - cy) * math.cos(a)) for px, py in pts]
        return (min(p[0] for p in rp), min(p[1] for p in rp),
                max(p[0] for p in rp) - min(p[0] for p in rp),
                max(p[1] for p in rp) - min(p[1] for p in rp))
    return (x, y, w, h)


def wrapped_in(el):
    """Real wrapped height in inches using the shipped Outfit font."""
    total = 0.0
    detail = []
    for p in el["paras"]:
        px_size = max(4, int(p["size"] * PPI / 72))
        face = "outfit" if p.get("font") == "heading" else "body"
        font = _font(face, bool(p.get("bold")), bool(p.get("italic")), px_size)
        text = p["text"].upper() if p.get("caps") else p["text"]
        indent = 0.35 * p.get("level", 0) + (px_size * 1.1 / PPI if p.get("bullet") else 0)
        max_w = (el["w"] - indent) * PPI
        lines, cur = [], ""
        for word in (text or " ").split():
            trial = (cur + " " + word) if cur else word
            if font.getlength(trial) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
        # letter-spacing applied by renderers
        sp = p.get("spacing", 0) or 0
        if sp:
            max_w_eff = max_w - sp * PPI / 72 * max(len(l) - 1 for l in lines)
            if max_w_eff < max_w:
                lines2, cur = [], ""
                for word in (text or " ").split():
                    trial = (cur + " " + word) if cur else word
                    wpx = font.getlength(trial) + sp * PPI / 72 * len(trial)
                    if wpx <= max_w or not cur:
                        cur = trial
                    else:
                        lines2.append(cur)
                        cur = word
                lines2.append(cur)
                lines = lines2
        total += len(lines) * px_size / PPI * el.get("line", 1.15) + p.get("space", 0) / 72
        detail.append((text[:46], len(lines), round(px_size / PPI, 3)))
    return total, detail


def audit(name, spec, index=0):
    lay = layout_slide(spec, THEME, index, [spec], "Bauhaus Design System")
    print("=" * 100)
    print(f"{name}   bg={lay['bg']}")
    print("=" * 100)
    print(f"{'#':>3} {'type':<9} {'x':>6} {'y':>6} {'w':>6} {'h':>6} {'rot':>4} {'line':>5} "
          f"{'fill':>8} {'a':>4}  {'rotbox(x,y,w,h)':<26} {'fit':>7}")
    els = lay["elements"]
    for i, el in enumerate(els):
        ln = (el.get("line") or {}).get("width", 0) if isinstance(el.get("line"), dict) else 0
        rb = rot_box(el)
        fit = ""
        if el["t"] == "text":
            tot, _ = wrapped_in(el)
            fit = f"{tot:.2f}/{el['h']:.2f}" + (" OVER" if tot > el["h"] + 0.02 else "")
        flag = ""
        if not el.get("bleed"):
            if rb[0] < -0.01 or rb[1] < -0.01 or rb[0] + rb[2] > W + 0.01 or rb[1] + rb[3] > H + 0.01:
                flag = " <<OFFSLIDE"
        print(f"{i:>3} {el['t']:<9} {el['x']:>6.2f} {el['y']:>6.2f} {el['w']:>6.2f} {el['h']:>6.2f} "
              f"{el.get('rot', 0):>4} {ln:>5.2f} {str(el.get('fill')):>8} {el.get('alpha', 1):>4}  "
              f"({rb[0]:.2f},{rb[1]:.2f},{rb[2]:.2f},{rb[3]:.2f}){' ' * 0:<0}{flag}")
        if el["t"] == "text":
            tot, det = wrapped_in(el)
            for t, nl, sz in det:
                print(f"        para size={sz}\" lines={nl} {t!r}")
            print(f"        box h={el['h']:.3f}  wrapped={tot:.3f}  align={el['align']} valign={el['valign']} "
                  f"box=({el['x']:.2f},{el['y']:.2f},{el['w']:.2f},{el['h']:.2f})  "
                  f"bottom={el['y'] + el['h']:.2f}")
    # overlap check between text boxes and non-bleed shapes
    print("-- text/text and text/opaque-shape overlaps --")
    texts = [e for e in els if e["t"] == "text"]
    solids = [e for e in els if e["t"] != "text" and not e.get("bleed") and el_alpha(e) >= 0.99]
    hits = 0
    for a in range(len(texts)):
        for b in range(a + 1, len(texts)):
            ta, tb = texts[a], texts[b]
            ix = min(ta["x"] + ta["w"], tb["x"] + tb["w"]) - max(ta["x"], tb["x"])
            iy = min(ta["y"] + ta["h"], tb["y"] + tb["h"]) - max(ta["y"], tb["y"])
            if ix > 0.01 and iy > 0.01:
                hits += 1
                print(f"  TEXT/TEXT overlap {ix:.2f}x{iy:.2f}: {ta['paras'][0]['text'][:28]!r} <> "
                      f"{tb['paras'][0]['text'][:28]!r}")
    for ta in texts:
        tb_, dd = wrapped_in(ta)
        gx0, gx1, gy0, gy1 = glyph_run(ta, tb_)
        for s in solids:
            rb = rot_box(s)
            ix = min(gx1, rb[0] + rb[2]) - max(gx0, rb[0])
            iy = min(gy1, rb[1] + rb[3]) - max(gy0, rb[1])
            if ix > 0.05 and iy > 0.05:
                hits += 1
                print(f"  TEXT/SHAPE overlap {ix:.2f}x{iy:.2f} text={ta['paras'][0]['text'][:28]!r} "
                      f"shape=({rb[0]:.2f},{rb[1]:.2f},{rb[2]:.2f},{rb[3]:.2f}) fill={s.get('fill')}")
    # rotated (bleed) shapes vs text glyph runs
    print("-- text glyph run vs ROTATED/bleed shape --")
    for ta in texts:
        tb_, _ = wrapped_in(ta)
        gx0, gx1, gy0, gy1 = glyph_run(ta, tb_)
        for s in [e for e in els if e["t"] != "text" and e.get("bleed")]:
            rb = rot_box(s)
            ix = min(gx1, rb[0] + rb[2]) - max(gx0, rb[0])
            iy = min(gy1, rb[1] + rb[3]) - max(gy0, rb[1])
            if ix > 0.05 and iy > 0.05:
                print(f"  BOX overlap {ix:.2f}x{iy:.2f} text={ta['paras'][0]['text'][:30]!r} "
                      f"shape rot={s.get('rot',0)} box=({rb[0]:.2f},{rb[1]:.2f},{rb[2]:.2f},{rb[3]:.2f})")
    if not hits:
        print("  none")
    print()


def glyph_run(el, wrapped):
    """Horizontal extent of the rendered glyph run = widest WRAPPED line, placed per align."""
    widest = 0.0
    for p in el["paras"]:
        px_size = max(4, int(p["size"] * PPI / 72))
        face = "outfit" if p.get("font") == "heading" else "body"
        font = _font(face, bool(p.get("bold")), bool(p.get("italic")), px_size)
        text = p["text"].upper() if p.get("caps") else p["text"]
        sp_px = (p.get("spacing") or 0) * PPI / 72
        sp = sp_px / PPI  # inches
        max_w = (el["w"] - 0.35 * p.get("level", 0)) * PPI
        lines, cur = [], ""
        for word in (text or " ").split():
            trial = (cur + " " + word) if cur else word
            if font.getlength(trial) + sp_px * len(trial) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
        for ln in lines:
            widest = max(widest, font.getlength(ln) / PPI + sp * len(ln))
    if el["align"] == "c":
        cx = el["x"] + el["w"] / 2
        gx0, gx1 = cx - widest / 2, cx + widest / 2
    elif el["align"] == "r":
        gx0, gx1 = el["x"] + el["w"] - widest, el["x"] + el["w"]
    else:
        gx0, gx1 = el["x"], el["x"] + widest
    if el["valign"] == "m":
        gy0, gy1 = el["y"] + (el["h"] - wrapped) / 2, el["y"] + (el["h"] + wrapped) / 2
    elif el["valign"] == "b":
        gy0, gy1 = el["y"] + el["h"] - wrapped, el["y"] + el["h"]
    else:
        gy0, gy1 = el["y"], el["y"] + wrapped
    return gx0, gx1, gy0, gy1


def el_alpha(e):
    return e.get("alpha", 1)


def _k(t):
    pass


closing = dict(next(s for s in SPECS if s["type"] == "closing"))
audit("CLOSING (spec sample)", closing)

long_closing = {
    "type": "closing",
    "kicker": "Section seven wrap up and the next steps",
    "title": "Design the poster so every slide has to prove the system is real",
    "subtitle": "Form follows function and function follows an honest grid, so make every "
                "single slide in this deck demonstrate the discipline you claim to value.",
    "contact": "studio@bauhaus-poster.example / +49 30 000000",
}
audit("CLOSING (long text + kicker)", long_closing)

noisy = {
    "type": "closing",
    "title": "x",
    "subtitle": "",
    "contact": "",
}
audit("CLOSING (no subtitle / no contact)", noisy)

titled = {
    "type": "closing",
    "title": "Build the poster",
    "subtitle": "Form follows function - make every slide prove it",
    "contact": "slidesmith.local",
    "image": {"src": "data/x.jpg", "w": 4, "h": 3},
}
audit("CLOSING (with photo -> _photo_hero)", titled)

huge_title = {
    "type": "closing",
    "kicker": "Nine principles",
    "title": ("Design the poster so that every single slide in this deck has to "
              "demonstrate the discipline that the system claims to value above all "
              "other considerations in the modern visual language"),
    "subtitle": ("Form follows function and function follows an honest grid, so make "
                 "every slide in this deck demonstrate the discipline you claim to "
                 "value, without ever letting the decoration lie about what the content "
                 "actually says to the people who are reading it in the room"),
    "contact": "studio@bauhaus-poster.example / +49 30 000000 / berlin",
}
audit("CLOSING (very long title + subtitle + kicker + contact)", huge_title)

short_title = {
    "type": "closing",
    "title": "Thank you",
    "subtitle": "Questions welcome",
    "contact": "hello@example.com",
}
audit("CLOSING (very short)", short_title)

empty = {"type": "closing", "title": ""}
audit("CLOSING (empty title, no sub/contact)", empty)

# ---- real PNG proof of the composited bleed colours on the yellow block
print("=" * 100)
print("PNG pixel probe (real render_png, closing sample)")
print("=" * 100)
import io
from PIL import Image
from server.raster import render_png

lay = layout_slide(closing, THEME, 0, [closing], "Bauhaus")
img = Image.open(io.BytesIO(render_png(lay, THEME, ppi=96))).convert("RGB")
for label, xi, yi in [("red bleed centre", 12.03, 0.20),
                      ("blue diamond centre", 0.15, 5.55),
                      ("flat yellow field", 6.67, 7.20),
                      ("far right flat", 13.10, 7.40)]:
    px = img.getpixel((int(xi * 96), int(yi * 96)))
    print(f"  {label:<22} ({xi:.2f},{yi:.2f}) -> #{px[0]:02X}{px[1]:02X}{px[2]:02X}")
