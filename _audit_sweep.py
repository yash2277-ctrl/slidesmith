"""Find the realistic overflow threshold for _bh_two_col bullets."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from server import themes, design
from server.layout import layout_slide, Frame
from server.raster import _font

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

print("nbul  charlen  panel_h  est_need(box)  real_need  real_bottom  card_bottom  escape_card  escape_slide")
for nb in (3, 4, 5, 6, 7):
    for clen in (40, 60, 80, 100, 130, 160, 200):
        bullet = ("word " * 40)[:clen]
        spec = {"type": "two_column", "title": "Threshold sweep",
                "left": {"heading": "Left", "bullets": [bullet[:clen]] * nb},
                "right": {"heading": "Right", "bullets": [bullet[:clen]] * nb}}
        lay = layout_slide(spec, THEME, 0, [spec], "Audit")
        cards = [e for e in lay["elements"] if e["t"] == "rect" and e.get("line") and e["w"] > 3]
        b = [e for e in lay["elements"] if e["t"] == "text" and e["paras"] and e["paras"][0].get("bullet")][0]
        c = [cc for cc in cards if cc["x"] - 0.25 < b["x"] < cc["x"] + cc["w"]][0]
        need = real_h(b)
        esc_c = (b["y"] + need) - (c["y"] + c["h"])
        esc_s = (b["y"] + need) - H
        flag = "  <<< TEXT OFF SLIDE" if esc_s > 0 else ("  < text out of card" if esc_c > 0 else "")
        print(f"{nb:3d}  {clen:5d}  {c['h']:7.3f}  {b['h']:11.3f}  {need:10.3f}  {b['y']+need:12.3f}  {c['y']+c['h']:11.3f}  {esc_c:+11.3f}  {esc_s:+11.3f}{flag}")