"""Focused numeric checks on the CURRENT server/layout.py _bh_bullets."""
import sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from server import themes, design
import server.layout as L
from _bh_specs import SPECS

THEME = themes.get_builtin("bauhaus"); THEME["dna"] = design.dna(20261006)
W, H = THEME["slide_w"], THEME["slide_h"]

def rotbox(el):
    x, y, w, h = el["x"], el["y"], el["w"], el["h"]
    r = el.get("rot", 0)
    if r and el["t"] in ("rect", "triangle", "ellipse"):
        a = math.radians(r); cx, cy = x + w/2, y + h/2
        pts = [(x,y),(x+w,y),(x+w,y+h),(x,y+h)]
        pts = [(cx+(px-cx)*math.cos(a)-(py-cy)*math.sin(a),
                cy+(px-cx)*math.sin(a)+(py-cy)*math.cos(a)) for px,py in pts]
        return min(p[0] for p in pts), min(p[1] for p in pts), \
               max(p[0] for p in pts), max(p[1] for p in pts)
    return x, y, x+w, y+h

def body_texts(lay):
    return [e for e in lay["elements"] if e["t"] == "text"
            and e["w"] > 8 and e["y"] > 1.8 and e["paras"][0]["text"] not in ("Audit",)]

def case(name, items):
    sp = {"type": "bullets", "title": "T", "bullets": items}
    lay = L.layout_slide(sp, THEME, 0, SPECS, "Audit")
    bt = body_texts(lay)
    size = bt[0]["paras"][0]["size"]
    x0, y0, x1, y1 = lay["elements"][0]["x"], 0, 0, 0
    bx0 = min(rotbox(e)[0] for e in bt); bx1 = max(rotbox(e)[2] for e in bt)
    by0 = min(rotbox(e)[1] for e in bt); by1 = max(rotbox(e)[3] for e in bt)
    # badges: shapes with a 0.5-ish box at x ~ 0.75
    badges = [e for e in lay["elements"] if e["t"] in ("rect","ellipse")
              and abs(e["w"]-0.5) < 0.02 and e["x"] < 1.0]
    shad = [e for e in badges if not e.get("line")]
    rotb = [e for e in shad if e.get("rot")]
    # badge-vs-badge vertical overlap (rotated badge true bbox)
    problems = []
    for i in range(len(badges)-1):
        for j in range(i+1, len(badges)):
            a, b = rotbox(badges[i]), rotbox(badges[j])
            if abs(badges[i]["y"]-badges[j]["y"]) < 1e-9: continue
            if badges[i]["y"] < badges[j]["y"]: a, b = b, a
            if a[3] > b[1] + 1e-9:
                problems.append(f"badge {i}/{j} overlap {a[3]-b[1]:.3f}in")
    foot = [e for e in lay["elements"] if e["t"] == "text" and e["paras"][0]["text"] == "Audit"]
    ftop = min(e["y"] for e in foot)
    print(f"{name:22s} n={len(items):2d} size={size:4} block=({bx0:.2f},{by0:.2f})-({bx1:.2f},{by1:.2f}) "
          f"footer_top={ftop:.2f} {'OVER-FOOTER by %.2f' % (by1-ftop) if by1>ftop else ''} "
          f"{'; '.join(sorted(set(problems)))}")
    if rotb:
        r = rotb[0]
        rx0, ry0, rx1, ry1 = rotbox(r)
        print(f"{'':22s} rotated badge(shadow) true bbox x {rx0:.3f}..{rx1:.3f} y {ry0:.3f}..{ry1:.3f}"
              f"  margin x={L.Frame(THEME,'bullets').mx:.3f}")
    return lay

print("--- bullet-count sweep (plain one-line items) ---")
for n in range(3, 13):
    case(f"plain n={n}", [{"text": f"Point {i+1} of the deck", "sub": []} for i in range(n)])
print()
print("--- bullet-count sweep (each item has a sub line) ---")
for n in range(3, 11):
    case(f"with sub n={n}", [{"text": f"Point {i+1} of the deck", "sub": [f"note {i+1}"]} for i in range(n)])
print()
print("--- long copy, 4 items ---")
LONG = "Geometric purity only circles squares and triangles and nothing else whatsoever in the whole composition"
for mult in (1, 2, 3, 4):
    case(f"long x{mult}", [{"text": LONG*mult, "sub": [LONG[:60]]} for _ in range(4)])

print()
print("=== rotated-square badge math (_bh_badge) ===")
d = 0.5; s = d*0.78
print(f"docstring says 'same visual diagonal'; actual diagonal = {s}*sqrt(2) = {s*math.sqrt(2):.4f} vs d = {d}")
print(f"  -> oversized by {s*math.sqrt(2)-d:.4f} in ({100*(s*math.sqrt(2)/d-1):.1f}%)")
print(f"correct k for equal diagonal = 1/sqrt(2) = {1/math.sqrt(2):.4f}")
lay = case("sample", SPECS[2]["bullets"])
rot = [e for e in lay["elements"] if e.get("rot") == 45 and e["t"] == "rect"]
for r in rot:
    rx0, ry0, rx1, ry1 = rotbox(r)
    cx = r["x"] + r["w"]/2
    print(f"  rotated rect role={'shadow' if not r.get('line') else 'badge'} centre_x={cx:.3f} "
          f"bbox {rx0:.3f}..{rx1:.3f} left-of-margin={0.75-rx0:.3f}in")
num = [e for e in lay["elements"] if e["t"] == "text" and e["w"] == 0.5 and e["h"] == 0.5]
badge = [r for r in rot if r.get("line")][0]
print(f"  number box centre_x={badge['x']+badge['w']/2:.3f} vs diamond centre_x={badge['x']+badge['w']/2:.3f}"
      .replace("vs diamond centre_x=%.3f" % (badge['x']+badge['w']/2), "vs diamond centre_x=%.3f" % (badge['x']+badge['w']/2)))
print(f"  number box x={num[-1]['x']:.3f}..{num[-1]['x']+num[-1]['w']:.3f} centre={(num[-1]['x']+num[-1]['w']/2):.3f}")
print(f"  => number sits {num[-1]['x']+num[-1]['w']/2-(badge['x']+badge['w']/2):.3f}in right of the yellow diamond's centre")