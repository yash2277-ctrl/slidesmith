"""Stress: long matrix content -> find real overflow with the actual font metrics."""
import sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from server import themes, design
from server.layout import layout_slide, text_h
from server.raster import _font
from _bh_specs import SPECS

T = themes.get_builtin("bauhaus"); T["dna"] = design.dna(20261006)


def measured(el):
    ppi = 96; total = 0.0; det = []
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
        det.append((len(lines), px, p["text"][:45]))
        total += len(lines) * px / ppi * el.get("line", 1.15)
    return total, det


def run(name, spec):
    lay = layout_slide(spec, T, 8, SPECS, "Deck")
    print("=" * 74); print("CASE", name); print("=" * 74)
    worst = 0.0
    for el in lay["elements"]:
        if el["t"] != "text": continue
        if not any(p["text"].strip() for p in el["paras"]): continue
        m, det = measured(el)
        pct = (m / el["h"] - 1) * 100 if el["h"] else 0
        worst = max(worst, pct)
        mark = "  <<< OVERFLOW" if pct > 1 else ""
        print(f"  box h={el['h']:5.3f} need={m:5.3f} ({pct:+6.1f}%) {det}{mark}")
    # card fit: does body text spill past the card's inner bottom?
    print(f"  worst={worst:+.1f}%")
    return lay


L1 = {"type": "matrix", "title": "Decision matrix", "quadrants": [
  {"heading": "Use it when the story is the product and the audience is broad, general and "
              "unfamiliar with the detail",
   "text": ("Product launches, design talks, culture decks, poster-like covers and keynote "
            "openers. These are moments where a single idea has to land hard from across a "
            "crowded room and read correctly even before anybody has finished reading the "
            "slide title above it, so the composition has to do the persuading on its own.")},
  {"heading": "Balance it", "text": "Data-heavy reviews: keep charts plain."},
  {"heading": "Soften it", "text": "Sensitive topics: swap red for blue."},
  {"heading": "Avoid it", "text": "Legal, medical and dense documentation work."}],
  "x_axis": "Expressiveness", "y_axis": "Formality"}

run("very long heading, short bodies", L1)

L2 = {"type": "matrix", "title": "Decision matrix", "quadrants": [
  {"heading": "High impact, low effort",
   "text": ("Quick wins that pay for the programme twice over. Start here, ship these in the "
            "first quarter, and use the momentum they generate to buy political room for the "
            "expensive work further down the matrix, which nobody will fund until somebody "
            "has already shown the board what finishing looks like in practice.")}] * 4,
  "x_axis": "Expressiveness of the message to the market", "y_axis": "Formality of the register"}

run("all four long", L2)

L3 = {"type": "matrix", "title": "Extreme", "quadrants": [
  {"heading": "Q" * 3, "text": "word " * 260}] * 4}
run("pathological", L3)

# no axes at all
L4 = {"type": "matrix", "title": "No axes", "quadrants": [
  {"heading": "A", "text": "alpha " * 90}, {"heading": "B", "text": "beta " * 90},
  {"heading": "C", "text": "gamma " * 90}, {"heading": "D", "text": "delta " * 90}]}
run("no axes, huge bodies", L4)
