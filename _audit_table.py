"""Audit the bauhaus 'table' template: print every element's geometry and measure fit."""
import sys
from _bh_specs import SPECS
from server.layout import layout_slide, est_lines, text_h
from server.themes import get_builtin

THEME = get_builtin("bauhaus")
W, H = THEME["slide_w"], THEME["slide_h"]


def audit(name, spec, deck=None):
    deck = deck or [spec]
    out = layout_slide(spec, THEME, 0, deck, "Audit")
    print("=" * 78)
    print(f"### {name}   bg={out['bg']}")
    for i, e in enumerate(out["elements"]):
        t = e["t"]
        if t == "table":
            print(f"[{i}] table x={e['x']:.3f} y={e['y']:.3f} w={e['w']:.3f} h={e['h']:.3f} "
                  f"right={e['x']+e['w']:.3f} bottom={e['y']+e['h']:.3f} size={e['size']}")
            print(f"      cols={e['columns']}")
            print(f"      header_fill={e['header_fill']} header_text={e['header_text']} "
                  f"text={e['text']} fill_a={e['fill_a']} fill_b={e['fill_b']} border={e['border']}")
            n = len(e["rows"]) + 1
            rh = e["h"] / n
            cw = e["w"] / len(e["columns"])
            print(f"      rows={n}  row_h={rh:.3f}  cell_w={cw:.3f}  (layout assumed col_w="
                  f"{e['w']/len(e['columns'])-0.3:.3f})")
            # widest real cell at the shipped size
            worst = 0.0
            for r in [e["columns"]] + e["rows"]:
                for v in r:
                    hh = text_h(v, e["size"], cw, "body", 1.2)
                    if hh > worst:
                        worst, worstv = hh, v
            print(f"      tallest cell text = {worst:.3f} in  ({worstv!r})  row_h={rh:.3f}  "
                  f"{'OVERFLOW' if worst > rh + 1e-9 else 'ok'}")
            # how many wrapped lines does the worst cell need at cell width?
            for r in e["rows"]:
                for v in r:
                    ln = est_lines(v, e["size"], cw, "body")
                    if ln > 1:
                        print(f"      wraps to {ln} lines: {v!r} -> "
                              f"{ln*e['size']/72*1.2:.3f} in vs row {rh:.3f}")
        else:
            ln = e.get("line")
            print(f"[{i}] {t:6s} x={e['x']:.3f} y={e['y']:.3f} w={e['w']:.3f} h={e['h']:.3f} "
                  f"right={e['x']+e['w']:.3f} bottom={e['y']+e['h']:.3f} rot={e.get('rot',0)} "
                  f"fill={e.get('fill')} line={e.get('line')} line={ln}")
            if t == "text":
                txt = " | ".join(p["text"] for p in e["paras"])
                print(f"       paras={[(p['size'], p.get('caps'), p.get('spacing'), p.get('font'), p.get('bold')) for p in e['paras']]}")
                print(f"       text={txt!r}")
        bad = []
        if e["x"] < -0.001 or e["y"] < -0.001:
            if not e.get("bleed"):
                bad.append("negative origin")
        if e["x"] + e["w"] > W + 0.001 or e["y"] + e["h"] > H + 0.001:
            if not e.get("bleed"):
                bad.append(f"past slide edge ({e['x']+e['w']:.3f}, {e['y']+e['h']:.3f})")
        if bad:
            print(f"       !! {', '.join(bad)}")
    # pairwise overlaps of non-table elements
    boxes = [(i, e) for i, e in enumerate(out["elements"]) if e["t"] in ("rect", "text", "image")]
    for a in range(len(boxes)):
        for b in range(a + 1, len(boxes)):
            i, ea = boxes[a]
            j, eb = boxes[b]
            ox = min(ea["x"] + ea["w"], eb["x"] + eb["w"]) - max(ea["x"], eb["x"])
            oy = min(ea["y"] + ea["h"], eb["y"] + eb["h"]) - max(ea["y"], eb["y"])
            if ox > 0.02 and oy > 0.02:
                print(f"  overlap [{i}]{ea['t']} x [{j}]{eb['t']}: {ox:.3f} x {oy:.3f} in")
    return out


SAMPLE = next(s for s in SPECS if s["type"] == "table")
audit("sample: 5 rows x 3 cols", SAMPLE)

LONG = {"type": "table", "title": "Token sheet",
        "columns": ["Design token name", "Resolved value", "Where it is applied"],
        "rows": [["surface / elevated background", "#FFFFFF",
                  "Card fills and any raised panel that sits on the off-white canvas"],
                 ["border / heavy structural stroke", "#121212 at 2.75pt",
                  "Every card edge in the deck, drawn as a solid rule"],
                 ["shadow / hard offset", "#121212 offset 0.08in",
                  "Depth cue behind every card, never blurred"],
                 ["radius / corner treatment", "0 or full circle",
                  "Constructivist geometry only, no rounded rectangles anywhere"],
                 ["type / heading", "Outfit ExtraBold uppercase",
                  "Headlines, tracked tight at -0.5 points"]]}
audit("long: 5 rows, long cell text, 3 cols", LONG, [SAMPLE, LONG])

MANY = {"type": "table", "title": "Token sheet",
        "columns": ["Token", "Value", "Use"],
        "rows": [["background", "#F0F0F0", "Canvas"], ["surface", "#FFFFFF", "Cards"],
                 ["primary-red", "#D02020", "Action"], ["primary-blue", "#1040C0", "Panels"],
                 ["primary-yellow", "#F0C020", "Highlights"], ["foreground", "#121212", "Type & borders"],
                 ["border", "#121212", "Every card edge"], ["shadow", "#121212", "Offset behind cards"]]}
audit("many: 8 rows x 3 cols", MANY, [SAMPLE, MANY])