"""Audit of the bauhaus matrix / 2x2 template: real geometry at short and long scale."""
import math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from server import themes, design
from server.layout import layout_slide, text_h, est_lines
from server.raster import _font
from _bh_specs import SPECS

THEME = themes.get_builtin("bauhaus")
THEME["dna"] = design.dna(20261006)
W, H = THEME["slide_w"], THEME["slide_h"]

SAMPLE = [s for s in SPECS if s["type"] == "matrix"][0]

LONG = {
    "type": "matrix", "title": "When to use Bauhaus across a long enterprise programme deck",
    "quadrants": [
        {"heading": "Use it when the audience is persuaded by spectacle",
         "text": "Product launches, design talks, culture decks, poster-like covers and any "
                 "moment where a single idea has to land hard from across a crowded room and "
                 "read correctly even before anybody has finished reading the slide title above it."},
        {"heading": "Balance it against dense evidence",
         "text": "Data-heavy reviews: keep charts plain and let exactly one slide shout, while "
                 "every other slide in the deck stays deliberately quiet so the reader can find "
                 "the signal without hunting for it among competing blocks of decoration."},
        {"heading": "Soften it for sensitive subjects",
         "text": "Sensitive topics: swap red for blue as the leading block, drop the black rule "
                 "under the heading, and let the quiet off-white background carry the composition "
                 "so the words stay the loudest element on the page."},
        {"heading": "Avoid it entirely for",
         "text": "Legal, medical and dense documentation work, compliance packs, audit trails and "
                 "any slide where the reader needs to compare numbers precisely rather than "
                 "absorb an impressionistic mood from a colour field."},
    ],
    "x_axis": "Expressiveness of the message", "y_axis": "Formality of the register",
}

MIN = {"type": "matrix", "title": "SWOT", "quadrants": [], "x_axis": "", "y_axis": ""}


def layout(spec, idx=8):
    deck = [SAMPLE]
    return layout_slide(spec, THEME, idx, deck, "Bauhaus Design System")


def box(el):
    x, y, w, h = el["x"], el["y"], el["w"], el["h"]
    rot = el.get("rot", 0)
    if rot:
        a = math.radians(rot)
        cx, cy = x + w / 2, y + h / 2
        pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        pts = [(cx + (px - cx) * math.cos(a) - (py - cy) * math.sin(a),
                cy + (px - cx) * math.sin(a) + (py - cy) * math.cos(a)) for px, py in pts]
        return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)
    return x, y, x + w, y + h


def measured(el):
    """Real wrapped height in inches, using the actual font at 96 ppi."""
    ppi = 96
    total = 0.0
    detail = []
    for p in el["paras"]:
        px = max(4, int(p["size"] * ppi / 72))
        face = "outfit" if p.get("font") == "heading" else "body"
        f = _font(face, bool(p.get("bold")), bool(p.get("italic")), px)
        text = p["text"].upper() if p.get("caps") else p["text"]
        indent = 0.35 * p.get("level", 0) + (px * 1.1 / ppi if p.get("bullet") else 0)
        max_w = (el["w"] - indent) * ppi
        lines, cur = [], ""
        for w_ in (text or " ").split():
            trial = (cur + " " + w_) if cur else w_
            if f.getlength(trial) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur); cur = w_
        lines.append(cur)
        detail.append((p["text"][:40], p["size"], len(lines)))
        total += len(lines) * px / ppi * el.get("line", 1.15) + p.get("space", 0) / 72
    return total, detail


def report(name, spec):
    lay = layout(spec)
    els = lay["elements"]
    print("=" * 78)
    print(f"CASE {name}  ({len(els)} elements)")
    print("=" * 78)
    for el in els:
        x0, y0, x1, y1 = box(el)
        lnv = el.get("line") if el["t"] != "text" else None
        lw = (lnv or {}).get("width", 0) if isinstance(lnv, dict) else 0
        if el["t"] == "text":
            m, det = measured(el)
            paras = " | ".join(f"{p['text'][:34]!r} {p['size']}pt caps={p.get('caps',False)} "
                              f"sp={p.get('spacing')} col={p['color']}" for p in el["paras"])
            over = (m - el["h"]) / el["h"] * 100 if el["h"] else 0
            flag = "  <<< OVERFLOW" if over > 1 else ""
            print(f"TEXT  ({x0:6.3f},{y0:6.3f}) {x1-x0:6.3f}x{y1-y0:6.3f}  "
                  f"need {m:5.3f} vs box {el['h']:5.3f} ({over:+6.1f}%){flag}")
            print(f"        {paras}")
            if over > 1:
                for d in det:
                    print(f"          line-detail {d}")
        else:
            rot = el.get("rot", 0)
            print(f"{el['t']:6s} ({x0:6.3f},{y0:6.3f}) {x1-x0:6.3f}x{y1-y0:6.3f}  fill={el.get('fill')} "
                  f"line={lw} rot={rot}")
    # bounds
    print("-- bounds violations --")
    for el in els:
        x0, y0, x1, y1 = box(el)
        if el["t"] == "text" and (x0 < -0.01 or y0 < -0.01 or x1 > W + 0.01 or y1 > H + 0.01):
            print(f"   OFF-SLIDE text ({x0:.3f},{y0:.3f})-({x1:.3f},{y1:.3f}) {el['paras'][0]['text'][:40]!r}")
        if el["t"] != "text" and not el.get("bleed") and (x0 < -0.01 or y0 < -0.01 or x1 > W + 0.01 or y1 > H + 0.01):
            print(f"   OFF-SLIDE shape {el['t']} ({x0:.3f},{y0:.3f})-({x1:.3f},{y1:.3f})")
    return els


def overlaps(els):
    txt = [e for e in els if e["t"] == "text"]
    print("-- text/text box overlaps --")
    hit = False
    for i in range(len(txt)):
        for j in range(i + 1, len(txt)):
            a, b = box(txt[i]), box(txt[j])
            ox = min(a[2], b[2]) - max(a[0], b[0])
            oy = min(a[3], b[3]) - max(a[1], b[1])
            if ox > 0.002 and oy > 0.002:
                print(f"   OVERLAP {ox:.3f}x{oy:.3f}  {txt[i]['paras'][0]['text'][:28]!r} vs {txt[j]['paras'][0]['text'][:28]!r}")
                hit = True
    if not hit:
        print("   none")


for nm, sp in (("SAMPLE", SAMPLE), ("LONG", LONG), ("MIN/empty quadrants", MIN)):
    e = report(nm, sp)
    overlaps(e)
    print()
