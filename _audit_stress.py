"""Stress: push two_column bullets until text escapes the card."""
import sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from server import themes, design
from server.layout import layout_slide, Frame
from server.raster import _font
from _bh_specs import SPECS

THEME = themes.get_builtin("bauhaus"); THEME["dna"] = design.dna(20261006)
W, H = THEME["slide_w"], THEME["slide_h"]
X, Y, CW, CH = Frame(THEME, "two_column").content_rect()
print("content_rect", X, Y, CW, CH, "slide", W, H)

def real_h(el):
    total, det = 0.0, []
    for p in el["paras"]:
        px = max(4, int(p["size"] * 96 / 72))
        f = _font("outfit", bool(p.get("bold")), False, px)
        t = p["text"].upper() if p.get("caps") else p["text"]
        ind = px * 1.1 / 96 if p.get("bullet") else 0
        mw = (el["w"] - ind) * 96
        lines, cur = [], ""
        for wd in (t or " ").split():
            tr = (cur + " " + wd) if cur else wd
            if f.getlength(tr) <= mw or not cur: cur = tr
            else: lines.append(cur); cur = wd
        lines.append(cur)
        total += len(lines) * px / 96 * el.get("line", 1.15) + p.get("space", 0) / 72
        det.append(len(lines))
    return total, det

for n, words in [(4, 12), (6, 12), (6, 18), (7, 18), (7, 22), (8, 25)]:
    body = "geometry primary colour honest construction decides every element " * 1
    spec = {"type": "two_column", "title": "Stress",
            "left": {"heading": "Left", "bullets": [(body.strip() + " ") * 0 + ("word " * words) + f"item{i}" for i in range(n)]},
            "right": {"heading": "Right", "bullets": [f"short {i}" for i in range(n)]}}
    lay = layout_slide(spec, THEME, 0, [spec], "Audit")
    cards = [e for e in lay["elements"] if e["t"] == "rect" and e.get("line") and e["w"] > 3]
    bl = [e for e in lay["elements"] if e["t"] == "text" and e["paras"] and e["paras"][0].get("bullet")]
    worst = ""
    for b in bl:
        need, det = real_h(b)
        over = need - b["h"]
        # does real text bottom clear the card it sits in?
        cb = [c for c in cards if c["x"] - 0.2 < b["x"] < c["x"] + c["w"]]
        cb = cb[0] if cb else None
        escape = (b["y"] + need) - (cb["y"] + cb["h"]) if cb else None
        worst += (f"  bullets box=({b['x']:.2f},{b['y']:.2f},h={b['h']:.3f}) NEED={need:.3f} "
                  f"lines={det} over={over:+.3f}in real_bottom={b['y']+need:.3f} card_bottom={cb['y']+cb['h']:.3f} "
                  f"ESCAPE_CARD={escape:+.3f} card_top={cb['y']:.3f} card_h={cb['h']:.3f}\n")
        if b["y"] + need > H - 0.85:
            worst += f"      !!! TEXT PAST CONTENT AREA (y={b['y']+need:.3f} > {H-0.85:.3f} footer band)\n"
    print(f"n={n} words={words}: panel_h={cards[0]['h']:.3f} card_top={cards[0]['y']:.3f}")
    print(worst)