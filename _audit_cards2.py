"""Stress cases for the Bauhaus cards template."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from server import themes, design
from server.layout import layout_slide, est_lines
from server.raster import _font

THEME = themes.get_builtin("bauhaus")
THEME["dna"] = design.dna(20261006)
W, H = THEME["slide_w"], THEME["slide_h"]
PPI = 96
LOREM = ("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor "
         "incididunt ut labore et dolore magna aliqua.")


def real_lines(text, size, width, kind="body", bold=False, caps=False):
    px = max(4, int(round(size * PPI / 72)))
    f = _font("outfit" if kind == "heading" else "body", bold, False, px)
    t = text.upper() if caps else text
    maxw = width * PPI
    lines, cur = [], ""
    for w_ in (t or " ").split():
        trial = (cur + " " + w_) if cur else w_
        if f.getlength(trial) <= maxw or not cur:
            cur = trial
        else:
            lines.append(cur); cur = w_
    lines.append(cur)
    return lines, max((f.getlength(l) for l in lines), default=0) / PPI


def check(name, spec):
    lay = layout_slide(spec, THEME, 3, [spec], "Audit")
    print("=" * 100)
    print(name)
    frame_top, frame_bot = None, None
    cards, texts, issues = [], [], []
    for el in lay["elements"]:
        if el["t"] == "rect" and el.get("line") and el["line"].get("width") == 2.75:
            cards.append(el)
        if el["t"] == "text":
            texts.append(el)
    # card grid
    for el in cards:
        print(f"  card x={el['x']:.3f} y={el['y']:.3f} w={el['w']:.3f} h={el['h']:.3f} right={el['x']+el['w']:.3f} bottom={el['y']+el['h']:.3f}")
    if cards:
        frame_top = min(c["y"] for c in cards); frame_bot = max(c["y"] + c["h"] for c in cards)
        print(f"  card block: top={frame_top:.3f} bottom={frame_bot:.3f}  (content area 1.950 .. 6.650)")
        if frame_bot > 6.651:
            issues.append(f"card block bottom {frame_bot:.3f} exceeds content bottom 6.650")
        if frame_top < 1.949:
            issues.append(f"card block top {frame_top:.3f} above content top 1.950")
        if frame_bot > H - 0.80:
            issues.append(f"card block bottom {frame_bot:.3f} collides with footer (footer text at y=7.000)")
        if min(c["x"] for c in cards) < 0.749 or max(c["x"] + c["w"] for c in cards) > 12.584:
            issues.append("card outside margins")
    # text inside cards
    for el in texts:
        p = el["paras"][0]
        if not p["text"].strip():
            continue
        host = next((c for c in cards
                     if el["y"] >= c["y"] - 0.01 and el["y"] + el["h"] <= c["y"] + c["h"] + 0.01
                     and el["x"] >= c["x"] - 0.01 and el["x"] + el["w"] <= c["x"] + c["w"] + 0.01), None)
        if host is None:
            continue
        lines, widest = real_lines(p["text"], p["size"], el["w"], p.get("font", "body"),
                                   bool(p.get("bold")), bool(p.get("caps")))
        need = len(lines) * (p["size"] * PPI / 72) * el.get("line", 1.15) / PPI
        tag = ""
        if need > el["h"] + 0.01:
            tag = "  <== BODY/HEAD TEXT EXCEEDS BOX"
            issues.append(f"text {p['text'][:34]!r}: real {need:.3f}in > box {el['h']:.3f}in ({len(lines)} lines @{p['size']}pt)")
        if widest > el["w"] + 0.01:
            tag += "  <== WIDER THAN BOX"
            issues.append(f"text {p['text'][:34]!r}: widest line {widest:.3f}in > box w {el['w']:.3f}in")
        # bottom edge vs card bottom
        bot = el["y"] + need
        if bot > host["y"] + host["h"] - 0.05:
            tag += f"  <== TEXT BOTTOM {bot:.3f} vs CARD BOTTOM {host['y']+host['h']:.3f}"
            issues.append(f"text {p['text'][:34]!r} bottom {bot:.3f} vs card bottom {host['y']+host['h']:.3f}")
        print(f"   txt x={el['x']:.3f} y={el['y']:.3f} w={el['w']:.3f} h={el['h']:.3f} need={need:.3f} "
              f"lines={len(lines)} widest={widest:.3f} :: {p['text'][:40]!r}{tag}")
    if issues:
        print("  ISSUES:")
        for i in issues:
            print("   - " + i)
    else:
        print("  no geometry issue found")
    return lay


for n in (2, 3, 4, 5, 6, 8):
    check(f"{n} cards, long text",
          {"type": "cards", "title": f"{n} cards", "cards": [
              {"heading": f"Constructivist principle number {i+1}",
               "text": LOREM} for i in range(n)]})

check("6 cards, very long text",
      {"type": "cards", "title": "Six", "cards": [
          {"heading": "Constructivist typography and its many rules",
           "text": (LOREM + " " + LOREM)} for _ in range(6)]})

check("6 cards, short text",
      {"type": "cards", "title": "Six short", "cards": [
          {"heading": f"Card {i+1}", "text": "Two words."} for i in range(6)]})

check("4 cards, short text",
      {"type": "cards", "title": "Four", "cards": [
          {"heading": f"Card {i+1}", "text": "Two words."} for i in range(4)]})

check("5 cards, short text",
      {"type": "cards", "title": "Five", "cards": [
          {"heading": f"Card {i+1}", "text": "Two words."} for i in range(5)]})

check("6 cards, long single-word headings",
      {"type": "cards", "title": "Six", "cards": [
          {"heading": "Antidisestablishmentarianism", "text": "Short body."} for _ in range(6)]})