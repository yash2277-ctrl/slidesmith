"""Audit harness for the Bauhaus 'bullets' template. Prints every element's
geometry, plus measured wrapped text height vs box height, for 3 content scales."""
import io, math, sys
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from server import themes, design
from server.layout import layout_slide
from server.raster import render_png, _font
from _bh_specs import SPECS

THEME = themes.get_builtin("bauhaus")
THEME["dna"] = design.dna(20261006)
W, H = THEME["slide_w"], THEME["slide_h"]
print(f"slide {W} x {H}  content_rect default = (0.75, 1.95, 11.833, 4.70)")


def rot_box(el):
    x, y, w, h = el["x"], el["y"], el["w"], el["h"]
    rot = el.get("rot", 0)
    if rot and el["t"] in ("rect", "triangle", "ellipse"):
        a = math.radians(rot)
        cx, cy = x + w / 2, y + h / 2
        pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        pts = [(cx + (px - cx) * math.cos(a) - (py - cy) * math.sin(a),
                cy + (px - cx) * math.sin(a) + (py - cy) * math.cos(a)) for px, py in pts]
        return (min(p[0] for p in pts), min(p[1] for p in pts),
                max(p[0] for p in pts) - min(p[0] for p in pts),
                max(p[1] for p in pts) - min(p[1] for p in pts))
    return (x, y, w, h)


def measure(el):
    """Real wrapped height with the actual bundled font, inches."""
    ppi = 96
    total = 0.0
    per = []
    for p in el["paras"]:
        px_size = max(4, int(p["size"] * ppi / 72))
        face = "outfit" if p.get("font") == "heading" else "body"
        font = _font(face, bool(p.get("bold")), bool(p.get("italic")), px_size)
        text = p["text"].upper() if p.get("caps") else p["text"]
        sp = p.get("spacing", 0) / 72 * 72  # pts
        max_w = (el["w"] - 0.35 * p.get("level", 0)) * ppi
        lines, cur = [], ""
        for word in (text or " ").split():
            trial = (cur + " " + word) if cur else word
            if font.getlength(trial) + sp * len(trial) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur); cur = word
        lines.append(cur)
        per.append(len(lines))
        total += len(lines) * px_size / ppi * el.get("line", 1.15)
    return total, per


def dump(name, spec, idx=0):
    lay = layout_slide(spec, THEME, idx, SPECS, "Audit")
    print("\n" + "=" * 100)
    print(f"CASE {name}   type={spec['type']}  bullets={len(spec.get('bullets', []))}")
    print("=" * 100)
    for n, el in enumerate(lay["elements"]):
        x, y, w, h = rot_box(el)
        ln = el.get("line")
        lw = ln.get("width", 0) if isinstance(ln, dict) else 0
        base = f"[{n:02d}] {el['t']:8s} x={x:6.2f} y={y:6.2f} w={w:6.2f} h={h:6.2f} rot={el.get('rot',0):>4} line={lw:<5} fill={el.get('fill','')}"
        if el["t"] == "text":
            m, per = measure(el)
            ps = [(p["text"][:34], p["size"], p["color"]) for p in el["paras"]]
            print(base + f" need={m:.2f} vs h={el['h']:.2f} lines={per}")
            print(f"      paras={ps}")
        else:
            print(base)
        if x < -0.01 or y < -0.01 or x + w > W + 0.01 or y + h > H + 0.01:
            print(f"      !!! OUT OF SLIDE (right={x+w:.2f} bottom={y+h:.2f})")
    # pairwise text-box overlap
    txt = [e for e in lay["elements"] if e["t"] == "text"]
    for i in range(len(txt)):
        for j in range(i + 1, len(txt)):
            a, b = txt[i], txt[j]
            ox = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
            oy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
            if ox > 0.01 and oy > 0.01:
                print(f"      !!! TEXT OVERLAP {i}<->{j} ({ox:.2f}x{oy:.2f}) "
                      f"{a['paras'][0]['text'][:25]!r} / {b['paras'][0]['text'][:25]!r}")
    png = render_png(lay, THEME, ppi=96)
    p = Path(f"data/_audit_{name}.png"); p.parent.mkdir(exist_ok=True)
    p.write_bytes(png)
    im = Image.open(io.BytesIO(png))
    # count low-contrast hairline pixels in the divider band
    print(f"  -> png {im.size} saved {p}")
    return lay


sample = SPECS[2]
dump("sample", sample)

long_text = {"type": "bullets", "title": "Core principles of the constructivist grid",
             "bullets": [{"text": b["text"] * 2, "sub": [s + " and extended supporting detail line" for s in b["sub"]]}
                         for b in sample["bullets"]]}
dump("long", long_text)

six = {"type": "bullets", "title": "Six principles",
       "bullets": [{"text": f"Principle number {i+1}: geometry carries the whole composition",
                    "sub": [f"Supporting note {i+1} about honest construction"]} for i in range(6)]}
dump("six", six)

six_plain = {"type": "bullets", "title": "Six plain points",
             "bullets": [{"text": f"Point {i+1} of the deck", "sub": []} for i in range(6)]}
dump("six_plain", six_plain)

nine = {"type": "bullets", "title": "Nine points",
        "bullets": [{"text": f"Point {i+1} of the deck", "sub": []} for i in range(9)]}
dump("nine", nine)