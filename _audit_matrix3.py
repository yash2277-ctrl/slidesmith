"""Precise escape test: does matrix text physically leave its card / hit its neighbour?"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from server import themes, design
from server.layout import layout_slide, text_h, est_lines
from server.raster import _font
from _bh_specs import SPECS

T = themes.get_builtin("bauhaus"); T["dna"] = design.dna(20261006)


def measured(el):
    ppi = 96; total = 0.0; lines_n = 0
    for p in el["paras"]:
        px = max(4, int(p["size"] * ppi / 72))
        f = _font("outfit" if p.get("font") == "heading" else "body", bool(p.get("bold")),
                  bool(p.get("italic")), px)
        text = p["text"].upper() if p.get("caps") else p["text"]
        max_w = (el["w"] - 0.35 * p.get("level", 0)) * ppi
        lines, cur = [], ""
        for w_ in (text or " ").split():
            trial = (cur + " " + w_) if cur else w_
            if f.getlength(trial) <= max_w or not cur: cur = trial
            else: lines.append(cur); cur = w_
        lines.append(cur)
        lines_n = len(lines)
        total += len(lines) * px / ppi * el.get("line", 1.15)
    return total, lines_n


def probe(label, spec):
    lay = layout_slide(spec, T, 8, SPECS, "Deck")
    els = lay["elements"]
    cards = [e for e in els if e["t"] == "rect" and e.get("fill") == "#FFFFFF" and e["w"] > 5]
    print(f"\n--- {label}")
    for ci, card in enumerate(cards):
        cx0, cy0, cx1, cy1 = card["x"], card["y"], card["x"] + card["w"], card["y"] + card["h"]
        texts = [e for e in els if e["t"] == "text"
                 and e["x"] >= cx0 - 0.2 and e["x"] < cx1 and e["y"] >= cy0 - 0.2 and e["y"] < cy1 + 0.5]
        for t in texts:
            m, nl = measured(t)
            bottom = t["y"] + m          # real ink bottom (valign top)
            bot_box = t["y"] + t["h"]
            over_box = m - t["h"]
            esc = bottom - cy1          # >0 means ink crosses the card's bottom border
            tag = []
            if esc > 0: tag.append(f"INK CROSSES CARD BOTTOM by {esc:.3f}in")
            if over_box > 0.01: tag.append(f"box overflow +{over_box:.3f}in")
            if tag:
                print(f"  card{ci} [{cx0:.2f},{cy0:.2f} {card['w']:.2f}x{card['h']:.2f}] "
                      f"text {nl}L @{(t['paras'][0]['size'])}pt box y={t['y']:.3f} h={t['h']:.3f} "
                      f"ink bottom={bottom:.3f} -> " + "; ".join(tag))
                print(f"      {t['paras'][0]['text'][:70]!r}")
    return lay


BODY = ("Product launches, design talks, culture decks, poster-like covers and keynote openers. "
        "These are the moments where one idea has to land hard from across a crowded room.")

for n in (60, 120, 180, 240, 300, 400, 500):
    b = " ".join(["word%d" % i for i in range(n)])
    probe(f"q1 body {len(b)} chars, others short",
          {"type": "matrix", "title": "Decision matrix",
           "quadrants": [{"heading": "Use it", "text": b},
                         {"heading": "Balance it", "text": "Short."},
                         {"heading": "Soften it", "text": "Short."},
                         {"heading": "Avoid it", "text": "Short."}],
           "x_axis": "Expressiveness", "y_axis": "Formality"})

for n in (60, 120, 200, 300):
    hd = " ".join(["Headingword%d" % i for i in range(n)])
    probe(f"long heading {len(hd)} chars",
          {"type": "matrix", "title": "Decision matrix",
           "quadrants": [{"heading": hd, "text": BODY},
                         {"heading": "Balance it", "text": "Short."},
                         {"heading": "Soften it", "text": "Short."},
                         {"heading": "Avoid it", "text": "Short."}],
           "x_axis": "Expressiveness", "y_axis": "Formality"})

# no axes -> taller cards, does that path differ?
for n in (200, 400):
    b = " ".join(["word%d" % i for i in range(n)])
    probe(f"NO axes, body {len(b)} chars",
          {"type": "matrix", "title": "Decision matrix",
           "quadrants": [{"heading": "Use it", "text": b}] * 4})

# estimator accuracy table
print("\n=== estimator vs real, body CHAR_W=0.5 (est_lines) ===")
from server.raster import _font as F
for size in (11, 14, 15):
    px = int(size * 96 / 72)
    f = F("body", False, False, px)
    for txt in [BODY, "word " * 60, "The quick brown fox jumps over the lazy dog again and again",
                "Legal, medical and dense documentation work."]:
        max_w = 5.1865 * 96
        lines, cur = [], ""
        for w_ in txt.split():
            trial = (cur + " " + w_) if cur else w_
            if f.getlength(trial) <= max_w or not cur: cur = trial
            else: lines.append(cur); cur = w_
        lines.append(cur)
        real = len(lines)
        est = est_lines(txt, size, 5.1865, "body")
        # real avg char width as a fraction of size
        frac = f.getlength(txt) / (px * len(txt)) * 72 / size
        print(f"  size={size} est={est} real={real} implied CHAR_W={frac:.3f}  {txt[:45]!r}")
