"""Audit of the Bauhaus 'cards' template. Prints per-element geometry + real
font-measured wrapped height vs box height, plus overlap / bounds analysis."""
import math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from server import themes, design
from server.layout import layout_slide
from server.raster import _font

THEME = themes.get_builtin("bauhaus")
THEME["dna"] = design.dna(20261006)
W, H = THEME["slide_w"], THEME["slide_h"]
PPI = 96


def measured(el):
    """Real wrapped height in inches using the bundled/system font."""
    total = 0.0
    detail = []
    for p in el["paras"]:
        px = max(4, int(round(p["size"] * PPI / 72)))
        face = "outfit" if p.get("font") == "heading" else "body"
        f = _font(face, bool(p.get("bold")), bool(p.get("italic")), px)
        text = p["text"].upper() if p.get("caps") else p["text"]
        spacing = p.get("spacing", 0) / 72 * PPI  # pt tracking
        maxw = el["w"] * PPI
        lines, cur = [], ""
        for word in (text or " ").split():
            trial = (cur + " " + word) if cur else word
            wl = f.getlength(trial) + spacing * PPI / 72 * max(0, len(trial) - 1)
            if wl <= maxw or not cur:
                cur = trial
            else:
                lines.append(cur); cur = word
        lines.append(cur)
        # longest line width check
        widest = max((f.getlength(l) + spacing * PPI / 72 * max(0, len(l) - 1) for l in lines), default=0) / PPI
        total += len(lines) * px / PPI * el.get("line", 1.15) + p.get("space", 0) / 72
        detail.append((p["size"], len(lines), round(widest, 3), text[:44]))
    return total, detail


def rotbox(el):
    x, y, w, h = el["x"], el["y"], el["w"], el["h"]
    rot = el.get("rot", 0)
    if rot:
        a = math.radians(rot)
        cx, cy = x + w / 2, y + h / 2
        pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        pts = [(cx + (px - cx) * math.cos(a) - (py - cy) * math.sin(a),
                cy + (px - cx) * math.sin(a) + (py - cy) * math.cos(a)) for px, py in pts]
        return min(p[0] for p in pts), min(p[1] for p in pts), \
               max(p[0] for p in pts) - min(p[0] for p in pts), \
               max(p[1] for p in pts) - min(p[1] for p in pts)
    return x, y, w, h


def overlap(a, b):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    ox = min(ax + aw, bx + bw) - max(ax, bx)
    oy = min(ay + ah, by + bh) - max(ay, by)
    return (ox, oy) if ox > 0.004 and oy > 0.004 else None


def report(name, spec, idx=3):
    lay = layout_slide(spec, THEME, idx, [spec], "Audit")
    els = lay["elements"]
    print("=" * 96)
    print(f"{name}   ({len(els)} elements)  bg={lay['bg']}")
    print("=" * 96)
    for k, el in enumerate(els):
        tag = el.get("bleed") and " BLEED" or ""
        ln = el.get("line")
        lw = f" lw={ln['width'] if isinstance(ln, dict) else ln}" if ln else ""
        r = f" rot={el['rot']}" if el.get("rot") else ""
        rad = f" radius={el['radius']}" if el.get("radius") else ""
        al = f" alpha={el['alpha']}" if el.get("alpha") is not None else ""
        rb = rotbox(el)
        extra = ""
        if el["t"] == "text":
            m, det = measured(el)
            extra = f" | measured_h={m:.3f} box_h={el['h']:.3f} {'OVERFLOW +%.3f' % (m - el['h']) if m > el['h'] + 0.005 else 'ok'}"
            extra += f" lines={[(d[0], d[1], d[2]) for d in det]}"
        print(f"{k:3d} {el['t']:9s} x={el['x']:7.3f} y={el['y']:7.3f} w={el['w']:6.3f} h={el['h']:6.3f}"
              f" fill={el.get('fill')}{lw}{r}{rad}{al}{tag}{extra}")
        if el["t"] != "text":
            print(f"      rotbox x={rb[0]:.3f} y={rb[1]:.3f} w={rb[2]:.3f} h={rb[3]:.3f}  right={rb[0]+rb[2]:.3f} bottom={rb[1]+rb[3]:.3f}")

    print("-" * 96)
    print("BOUNDS (slide 13.333 x 7.5):")
    for k, el in enumerate(els):
        rb = rotbox(el)
        if rb[0] < -0.01 or rb[1] < -0.01 or rb[0] + rb[2] > W + 0.01 or rb[1] + rb[3] > H + 0.01:
            if not el.get("bleed"):
                print(f"  OUT k={k} {el['t']} rotbox=({rb[0]:.3f},{rb[1]:.3f},{rb[2]:.3f},{rb[3]:.3f})")
    print("  (none flagged above = all inside)")

    print("TEXT/TEXT and TEXT/CARD-BORDER overlaps (text boxes only):")
    texts = [(k, el) for k, el in enumerate(els) if el["t"] == "text"]
    for a in range(len(texts)):
        for b in range(a + 1, len(texts)):
            ka, ea = texts[a]; kb, eb = texts[b]
            o = overlap(rotbox(ea), rotbox(eb))
            if o:
                print(f"  TEXT OVERLAP k{ka}/k{kb} by {o[0]:.3f}x{o[1]:.3f}in :: "
                      f"{ea['paras'][0]['text'][:26]!r} / {eb['paras'][0]['text'][:26]!r}")
    print("  (done)")
    return lay


base = [s for s in __import__("_bh_specs").SPECS if s["type"] == "cards"][0]
report("SAMPLE 3 cards", base)

six = {"type": "cards", "title": "Six cards", "cards": [
    {"heading": f"Card number {i+1}", "text": "Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore."}
    for i in range(6)]}
report("6 cards, long text", six)

longtext = {"type": "cards", "title": "One very long title for the cards slide to stress the heading fit",
            "cards": [
    {"heading": "Constructivist typography and its many rules",
     "text": "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat."},
    {"heading": "B", "text": "Short."},
    {"heading": "C", "text": "Short."}]}
report("3 cards, very long single card", longtext)

icons = {"type": "cards", "title": "Cards with icons", "cards": [
    {"heading": "Alpha", "text": "Has an icon in the tile.", "icon": "mdi:shape"},
    {"heading": "Beta", "text": "No icon here, so it gets a number."},
    {"heading": "Gamma", "text": "Also numbered."}]}
report("3 cards, mixed icon/number tiles", icons)

one = {"type": "cards", "title": "Single card", "cards": [
    {"heading": "Solo", "text": "Only one card in the deck."}]}
report("1 card", one)