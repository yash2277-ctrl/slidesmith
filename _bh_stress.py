"""Stress the Bauhaus templates the way real decks stress them: long text, many
items, deep nesting. Reuses the same bounds + real-font text-fit checks as
_bh_check.py. Run:  python _bh_stress.py
"""
import io
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from server import themes, design
from server.layout import layout_slide
from server.raster import render_png, _font
from server.slide_schema import normalize

THEME = themes.get_builtin("bauhaus")
THEME["dna"] = design.dna(777)  # a different DNA seed than the sample run
W, H = THEME["slide_w"], THEME["slide_h"]
FAILS = []

LONG = ("A deliberately overlong sentence that pushes every fitting calculation to its "
        "limit and then some, because real decks carry sentences nobody trimmed twice, "
        "which is exactly where a layout engine quietly breaks apart")
MID = "A reasonably long but survivable line of slide copy that a careful presenter might actually write out loud"


def spec(t, **kw):
    return normalize({"type": t, "title": kw.pop("title", "A Deliberately Long Slide Title About Construction"), **kw})


def many(t, key, n, **tmpl):
    return spec(t, title=f"{n} items on one slide", **{key: [dict(tmpl, heading=f"Item {i + 1}", text=LONG if i % 2 else MID)
                                                           for i in range(n)]}, **({} ))


CASES = [
    ("6 cards, long text", spec("cards", cards=[{"heading": f"Card {i+1}", "text": LONG} for i in range(6)])),
    ("4 cards, short text", spec("cards", cards=[{"heading": f"Card {i+1}", "text": "Three words."} for i in range(4)])),
    ("6 bullets with subs", spec("bullets", bullets=[{"text": LONG, "sub": [MID, "And a tight sub-point."]} for _ in range(6)])),
    ("8 bullets, no subs", spec("bullets", bullets=[MID for _ in range(8)])),
    ("5 stats, long labels", spec("stats", stats=[{"value": v, "label": LONG[:44], "detail": LONG} for v in ("99.9%", "12M", "3x", "450", "-27%")])),
    ("6 timeline steps", spec("timeline", steps=[{"label": f"Step {i+1}", "heading": f"Phase {i+1}", "text": LONG} for i in range(6)])),
    ("3 timeline steps", spec("timeline", steps=[{"label": f"Step {i+1}", "heading": f"Phase {i+1}", "text": MID} for i in range(3)])),
    ("5 chevron steps", spec("process", steps=[{"heading": f"Stage {i+1}", "text": LONG} for i in range(5)])),
    ("two columns, 6 bullets", spec("two_column", left={"heading": "The left side heading", "bullets": [LONG] * 6},
                                    right={"heading": "The right side heading", "bullets": [MID] * 6})),
    ("matrix, long quadrants", spec("matrix", quadrants=[{"heading": f"Quadrant {i+1}", "text": LONG} for i in range(4)],
                                    x_axis="Low to high", y_axis="Slow to fast")),
    ("long quote", spec("quote", quote=LONG * 2, attribution="Someone With A Very Long Name And Title, Somewhere")),
    ("8x5 table", spec("table", columns=[f"Column {i}" for i in range(5)],
                       rows=[[f"Cell {r}-{c} with a bit of text" for c in range(5)] for r in range(8)])),
    ("5 funnel stages", spec("funnel", stages=[{"label": f"Stage {i+1}", "value": str((i + 1) * 1000), "text": LONG} for i in range(5)])),
    ("6 quiz options", spec("quiz", title="Which of these is not a primary shape?",
                           options=["Circle", "Square", "Triangle", "Hexagon", "Pentagon", "Oval"], answer=3,
                           explanation=LONG)),
    ("image slide, long bullets", spec("image", side="left", text=LONG,
                                       bullets=[{"text": LONG, "sub": [MID]} for _ in range(3)])),
    ("chart + takeaway", spec("chart", chart={"kind": "column", "categories": [f"C{i}" for i in range(9)],
                                              "series": [{"name": "Series one with a long name", "values": list(range(1, 10))}]},
                              takeaway=LONG)),
]


def shape_box(el):
    import math
    x, y, w, h = el["x"], el["y"], el["w"], el["h"]
    rot = el.get("rot", 0)
    if rot and el["t"] in ("rect", "triangle"):
        a = math.radians(rot)
        cx, cy = x + w / 2, y + h / 2
        pts = [(cx + (px - cx) * math.cos(a) - (py - cy) * math.sin(a),
                cy + (px - cx) * math.sin(a) + (py - cy) * math.cos(a))
               for px, py in ((x, y), (x + w, y), (x + w, y + h), (x, y + h))]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
    return x, y, w, h


def check(label, lay):
    for el in lay["elements"]:
        if el.get("static") or el["t"] in ("image", "chart", "table", "tpltable"):
            continue
        x, y, w, h = shape_box(el)
        if not el.get("bleed") and (x < -0.01 or y < -0.01 or x + w > W + 0.01 or y + h > H + 0.01):
            FAILS.append(f"{label}: {el['t']} out of bounds ({x:.2f},{y:.2f} {w:.2f}x{h:.2f})")
    for el in lay["elements"]:
        if el["t"] != "text" or el.get("static"):
            continue
        total = 0.0
        for p in el["paras"]:
            px_size = max(4, int(p["size"] * 96 / 72))
            font = _font("outfit" if p.get("font") == "heading" else "body",
                         bool(p.get("bold")), bool(p.get("italic")), px_size)
            text = p["text"].upper() if p.get("caps") else p["text"]
            indent = 0.35 * p.get("level", 0) + (px_size * 1.1 / 96 if p.get("bullet") else 0)
            max_w = (el["w"] - indent) * 96
            lines, cur = 0, ""
            for word in (text or " ").split():
                trial = (cur + " " + word) if cur else word
                if font.getlength(trial) <= max_w or not cur:
                    cur = trial
                else:
                    lines += 1
                    cur = word
            total += (lines + 1) * px_size / 96 * el.get("line", 1.15) + p.get("space", 0) / 72
        if total > el["h"] * 1.12 and any(p["text"].strip() for p in el["paras"]):
            FAILS.append(f"{label}: text overflows by {int((total / max(el['h'], .01) - 1) * 100)}%: "
                         f"{el['paras'][0]['text'][:38]!r}")


print("=" * 66)
print("BAUHAUS STRESS TEST  ·  long text and full slides")
print("=" * 66)
for label, s in CASES:
    deck = [s]
    lay = layout_slide(s, THEME, 1, deck, "Stress deck")
    render_png(lay, THEME, ppi=96)
    check(label, lay)
    print(f"  {label:<28} rendered")

print("\n" + "-" * 66)
if FAILS:
    print(f"FAILED ({len(FAILS)}):")
    for f in FAILS:
        print("  ✗ " + f)
else:
    print("PASS: every stress case stays inside the slide and inside its boxes")
print("-" * 66)
sys.exit(1 if FAILS else 0)
