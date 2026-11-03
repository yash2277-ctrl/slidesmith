"""Max-length two_column: 7 bullets x 600 chars (schema caps at slide_schema.py:120-122)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from server import themes, design
from server.layout import layout_slide, Frame
from server.raster import _font, render_png
from server.slide_schema import normalize

THEME = themes.get_builtin("bauhaus"); THEME["dna"] = design.dna(20261006)
W, H = THEME["slide_w"], THEME["slide_h"]

def real_h(el):
    total = 0.0
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
    return total

raw = {"type": "two_column", "title": "Two columns with the maximum schema-allowed content",
       "left": {"heading": "A left column heading that runs long enough to wrap onto a second line",
                "bullets": [{"text": ("Maximal bullet body text " * 30)[:600]} for _ in range(7)]},
       "right": {"heading": "Right", "bullets": [{"text": ("Maximal bullet body text " * 30)[:600]} for _ in range(7)]}}
spec = normalize(raw)
print("schema-normalised: left bullets =", len(spec["left"]["bullets"]), "chars each =",
      [len(b) for b in spec["left"]["bullets"]][:2])

lay = layout_slide(spec, THEME, 0, [spec], "Audit")
cards = [e for e in lay["elements"] if e["t"] == "rect" and e.get("line") and e["w"] > 3]
for k, el in enumerate(lay["elements"]):
    if el["t"] != "text": continue
    need = real_h(el)
    tag = ""
    if need > el["h"]:
        tag += f" *** BOX OVERFLOW +{need-el['h']:.3f} ({(need/el['h']-1)*100:.0f}%)"
    cb = [c for c in cards if c["x"] - 0.25 < el["x"] < c["x"] + c["w"]]
    if cb:
        c = cb[0]
        if el["y"] + need > c["y"] + c["h"]:
            tag += f" *** TEXT ESCAPES CARD BOTTOM by {el['y']+need-(c['y']+c['h']):.3f}in (text bottom {el['y']+need:.3f} vs card bottom {c['y']+c['h']:.3f})"
    if el["y"] + need > H:
        tag += " *** OFF SLIDE"
    print(f"  [{k:02d}] {el['paras'][0]['text'][:40]!r:44s} y={el['y']:.3f} h={el['h']:.3f} need={need:.3f}{tag}")

print("\ncard geometry:", [(round(c['x'],3), round(c['y'],3), round(c['w'],3), round(c['h'],3)) for c in cards])
Path("data/_bh_preview").mkdir(parents=True, exist_ok=True)
png = render_png(lay, THEME, ppi=96)
Path("data/_bh_preview/audit_max.png").write_bytes(png)
print("wrote data/_bh_preview/audit_max.png")
# also show raster's own self-reported issues
import io
from PIL import Image
print("raster issues:", render_png.__module__)