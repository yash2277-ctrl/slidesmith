"""Audit of the Bauhaus 'two_column' template. Read-only."""
import math, sys, io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from PIL import Image
from server import themes, design
from server.layout import layout_slide, text_h, est_lines, Frame
from server.raster import render_png, _font
from _bh_specs import SPECS

THEME = themes.get_builtin("bauhaus")
THEME["dna"] = design.dna(20261006)
W, H = THEME["slide_w"], THEME["slide_h"]

SAMPLE = next(s for s in SPECS if s["type"] == "two_column")

def deep(spec, n=6):
    return {"type": "two_column", "title": spec["title"], **spec}

LONG = {
    "type": "two_column", "title": "Form versus function in the Bauhaus workshop",
    "left": {"heading": "Form follows a very long heading that will certainly wrap onto two lines",
             "bullets": [f"Bullet {i}: geometry, primary colour and honest construction decide every "
                         f"element on the page, never decoration" for i in range(1, 7)]},
    "right": {"heading": "Function",
              "bullets": [f"Point {i}: every element must earn the space it occupies" for i in range(1, 7)]},
}

LONG2 = {
    "type": "two_column", "title": "Left heavy",
    "left": {"heading": "Design", "bullets": [f"Long left bullet {i} with a fair amount of explanatory text in it " * 2 for i in range(1, 7)]},
    "right": {"heading": "Build", "bullets": ["Short."]},
}

EMPTY = {"type": "two_column", "title": "Empty columns", "left": {}, "right": {}}
NOHEAD = {"type": "two_column", "title": "No headings",
          "left": {"bullets": ["one", "two"]}, "right": {"bullets": ["three", "four"]}}

CASES = [("sample", SAMPLE), ("long6", LONG), ("long2-leftheavy", LONG2), ("empty", EMPTY), ("no-heading", NOHEAD)]

def box_of(el):
    x, y, w, h = el["x"], el["y"], el["w"], el["h"]
    rot = el.get("rot", 0)
    if rot:
        a = math.radians(rot); cx, cy = x + w / 2, y + h / 2
        pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        pts = [(cx + (px-cx)*math.cos(a) - (py-cy)*math.sin(a),
                cy + (px-cx)*math.sin(a) + (py-cy)*math.cos(a)) for px, py in pts]
        X0 = min(p[0] for p in pts); Y0 = min(p[1] for p in pts)
        return X0, Y0, max(p[0] for p in pts)-X0, max(p[1] for p in pts)-Y0
    return x, y, w, h

def real_text_h(el):
    ppi = 96
    total = 0.0
    detail = []
    for p in el["paras"]:
        px = max(4, int(p["size"] * ppi / 72))
        f = _font("outfit", bool(p.get("bold")), bool(p.get("italic")), px)
        text = p["text"].upper() if p.get("caps") else p["text"]
        indent = 0.35 * p.get("level", 0) + (px * 1.1 / ppi if p.get("bullet") else 0)
        maxw = (el["w"] - indent) * ppi
        lines, cur = [], ""
        for word in (text or " ").split():
            trial = (cur + " " + word) if cur else word
            if f.getlength(trial) <= maxw or not cur:
                cur = trial
            else:
                lines.append(cur); cur = word
        lines.append(cur)
        total += len(lines) * px / ppi * el.get("line", 1.15) + p.get("space", 0) / 72
        detail.append((p["text"][:34], len(lines)))
    return total, detail

def overlap(a, b):
    ax, ay, aw, ah = box_of(a); bx, by, bw, bh = box_of(b)
    ox = min(ax+aw, bx+bw) - max(ax, bx)
    oy = min(ay+ah, by+bh) - max(ay, by)
    return ox, oy

for name, spec in CASES:
    i = 0
    lay = layout_slide(spec, THEME, i, [spec], "Audit")
    print("=" * 74)
    print(f"CASE {name}   content_rect={Frame(THEME,'two_column').content_rect()}")
    for k, el in enumerate(lay["elements"]):
        x, y, w, h = box_of(el)
        ln = el.get("line")
        lns = f" line={ln}" if ln else " line=None"
        rot = f" rot={el['rot']}" if el.get("rot") else ""
        extra = ""
        if el["t"] == "text":
            th, det = real_text_h(el)
            extra = f"  NEED={th:.3f} box={h:.3f} {'*** OVERFLOW +%.3f (%.0f%%) ***' % (th-h, (th/h-1)*100) if th > h else 'fits'}"
            extra += f" lines={det}"
        print(f"  [{k:02d}] {el['t']:9s} x={x:7.3f} y={y:7.3f} w={w:7.3f} h={h:7.3f} r={x+w:7.3f} b={y+h:7.3f} fill={el.get('fill')}{lns}{rot}{extra}")
        if not el.get("bleed"):
            if x < -0.01 or y < -0.01 or x + w > W + 0.01 or y + h > H + 0.01:
                print(f"       !!! OUT OF SLIDE ({W}x{H})")
    # text-vs-text overlap
    texts = [e for e in lay["elements"] if e["t"] == "text"]
    for a in range(len(texts)):
        for b in range(a+1, len(texts)):
            ox, oy = overlap(texts[a], texts[b])
            if ox > 0.004 and oy > 0.004:
                print(f"       !!! TEXT OVERLAP: [{texts[a]['paras'][0]['text'][:22]!r}] x [{texts[b]['paras'][0]['text'][:22]!r}] = {ox:.3f} x {oy:.3f} in")
    # text inside card borders
    cards = [e for e in lay["elements"] if e["t"] == "rect" and e.get("line") and e["w"] > 3]
    for t in texts:
        tx, ty, tw, th = box_of(t)
        for c in cards:
            cx, cy, cw, ch = box_of(c)
            inside = tx >= cx - .001 and ty >= cy - .001 and tx+tw <= cx+cw+.001 and ty+th <= cy+ch+.001
            if not inside and min(cx+cw, tx+tw) > max(cx, tx) and min(cy+ch, ty+th) > max(cy, ty):
                print(f"       !!! TEXT CROSSES CARD BORDER: {t['paras'][0]['text'][:26]!r} box=({tx:.2f},{ty:.2f},{tx+tw:.2f},{ty+th:.2f}) card=({cx:.2f},{cy:.2f},{cx+cw:.2f},{cy+ch:.2f})")
    # shadows vs other cards
    shadows = [e for e in lay["elements"] if e["t"] == "rect" and not e.get("line") and e.get("fill") == "#121212" and e["w"] > 3]
    for s in shadows:
        for c in cards:
            ox, oy = overlap(s, c)
            if ox > 0.004 and oy > 0.004:
                print(f"       !!! SHADOW OVERLAPS CARD: {ox:.3f} x {oy:.3f} in")
    png = render_png(lay, THEME, ppi=96)
    print(f"  PNG {len(png)//1024} KB -> data/_bh_preview/audit_{name}.png")
    p = Path("data/_bh_preview"); p.mkdir(parents=True, exist_ok=True)
    (p / f"audit_{name}.png").write_bytes(png)