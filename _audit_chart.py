"""Audit harness: render bauhaus 'chart' at several scales and print every element."""
import sys
from _bh_specs import SPECS
from server.layout import layout_slide, est_lines
from server.themes import get_builtin

TH = get_builtin('bauhaus')
W, H = TH['slide_w'], TH['slide_h']
PALETTE = {'#D02020', '#1040C0', '#F0C020', '#121212', '#F0F0F0', '#FFFFFF'}


def wrapped_h(el):
    """Measured wrapped height of a text box, using layout.est_lines."""
    total = 0.0
    for p in el['paras']:
        s = p['size']
        total += est_lines(p['text'], s, el['w'], p.get('font', 'body')) * s / 72 * el.get('line', 1.15)
        total += p.get('space', 0) / 72
    return total


def dump(name, spec, index=9):
    out = layout_slide(spec, TH, index, [spec], 'Audit')
    els = out['elements']
    print(f"\n===== {name}  ({len(els)} elements) =====")
    print(f"{'i':>2} {'t':<6} {'x':>7} {'y':>7} {'w':>7} {'h':>7} {'x2':>7} {'y2':>7} "
          f"{'rot':>4} {'ln':>5} {'rad':>5} {'fill':>8}  need/box  note")
    problems = []
    for i, e in enumerate(els):
        x, y, w, h = e['x'], e['y'], e['w'], e['h']
        rot = e.get('rot', 0)
        _l = e.get('line')
        ln = _l.get('width', '') if isinstance(_l, dict) else ''
        rad = e.get('radius', '')
        fill = e.get('fill', '')
        note = ''
        if e['t'] == 'text':
            need = wrapped_h(e)
            note = f"h={need:.2f}" + ("  ** TEXT OVERFLOWS BOX **" if need > h + 0.02 else "")
            if need > h + 0.02:
                problems.append((i, 'text-overflow', f"need {need:.3f} > box {h:.3f}"))
            # text inside a card?
            for j, c in enumerate(els):
                if c['t'] in ('rect',) and (c.get('line') or c.get('radius')) and \
                        c['x'] <= x + 0.001 and c['y'] <= y + 0.001 and \
                        x + w >= c['x'] + c['w'] - 0.001 and y + h >= c['y'] + c['h'] - 0.001 and \
                        need > c['h'] + 0.02:
                    problems.append((i, 'text-escapes-card',
                                     f"text needs {need:.3f} from y={y:.3f} -> bottom {y+need:.3f}; "
                                     f"card y={c['y']:.3f} h={c['h']:.3f} -> bottom {c['y']+c['h']:.3f}"))
        if e['t'] == 'chart':
            note = f"colors={e['colors']} grid={e['grid']} text={e['text']} bg={e['bg']}"
            for c in e['colors']:
                if c.upper() not in PALETTE:
                    problems.append((i, 'off-palette-fill', f"chart series fill {c}"))
            if e['grid'].upper() not in PALETTE:
                problems.append((i, 'off-palette', f"chart grid {e['grid']}"))
            if e['text'].upper() not in PALETTE:
                problems.append((i, 'off-palette', f"chart label text {e['text']}"))
        # bounds
        if e['t'] != 'chart':
            x2, y2 = x + w, y + h
            if rot:
                import math
                cx, cy = x + w / 2, y + h / 2
                r = math.hypot(w, h) / 2
                x2, y2 = cx + r, cy + r
            if x < -0.01 or y < -0.01 or x2 > W + 0.01 or y2 > H + 0.01:
                note += f"  ** OUT OF BOUNDS x2={x2:.3f} y2={y2:.3f} **"
                problems.append((i, 'out-of-bounds', f"x2={x2:.3f} y2={y2:.3f}"))
        if e['t'] == 'rect' and rad:
            note += f"  ** ROUNDED r={rad} **"
        if e['t'] == 'rect' and e.get('fill', '').upper() not in PALETTE and e.get('fill'):
            note += f"  ** OFF-PALETTE FILL {e['fill']} **"
        print(f"{i:>2} {e['t']:<6} {x:7.3f} {y:7.3f} {w:7.3f} {h:7.3f} {x+w:7.3f} {y+h:7.3f} "
              f"{rot:>4} {str(ln):>5} {str(rad):>5} {str(fill):>8}  {note}")
    # pairwise overlap among text boxes
    tb = [(i, e) for i, e in enumerate(els) if e['t'] == 'text']
    for a in range(len(tb)):
        for b in range(a + 1, len(tb)):
            ia, ea = tb[a]; ib, eb = tb[b]
            ox = min(ea['x'] + ea['w'], eb['x'] + eb['w']) - max(ea['x'], eb['x'])
            oy = min(ea['y'] + ea['h'], eb['y'] + eb['h']) - max(ea['y'], eb['y'])
            if ox > 0.02 and oy > 0.02:
                problems.append((ia, 'text-box-overlap',
                                 f"el{ia} vs el{ib} overlap {ox:.3f}x{oy:.3f}"))
    print("--- problems ---")
    for p in problems or ["(none)"]:
        print(" ", p)
    return out, problems


BASE = [s for s in SPECS if s['type'] == 'chart'][0]

# case 1: the shipped sample
dump("sample (4 cats, 1 series, takeaway)", BASE)

# case 2: 6 categories, 3 series, pie
p = {"type": "chart", "title": "Primary color usage across six regions and three years",
     "chart": {"kind": "column", "unit": "%",
               "categories": ["Red", "Blue", "Yellow", "Black", "White", "Off-white"],
               "series": [{"name": "Share", "values": [30, 28, 17, 25, 9, 4]},
                          {"name": "Trend", "values": [22, 25, 20, 18, 12, 6]},
                          {"name": "Other", "values": [5, 4, 9, 7, 30, 40]}]},
     "takeaway": "Black and white hold the composition; primaries carry it"}
dump("6 categories x 3 series", p)

# case 3: long takeaway text, no takeaway-length guard
p = {"type": "chart", "title": "Primary color usage",
     "chart": {"kind": "column", "unit": "%", "categories": ["Red", "Blue", "Yellow", "Black"],
               "series": [{"name": "Share", "values": [30, 28, 17, 25]}]},
     "takeaway": ("Black and white hold the composition while the three primaries carry every "
                  "section of the deck, and this very long illustrative sentence keeps going so that "
                  "we can observe what happens when the takeaway text runs far past the panel height "
                  "that the layout engine reserved for it in the narrow right hand column of the chart "
                  "slide template for the Bauhaus deck, which is the case under test here today.")}
dump("very long takeaway", p)

# case 4: no takeaway (chart spans full width)
p = {"type": "chart", "title": "Primary color usage",
     "chart": {"kind": "column", "unit": "%", "categories": ["Red", "Blue", "Yellow", "Black"],
               "series": [{"name": "Share", "values": [30, 28, 17, 25]}]}}
dump("no takeaway", p)

# case 5: pie with 6 categories
p = {"type": "chart", "title": "Share of the palette",
     "chart": {"kind": "pie", "unit": "%",
               "categories": ["Red", "Blue", "Yellow", "Black", "White", "Off-white"],
               "series": [{"name": "Share", "values": [30, 28, 17, 25, 9, 4]}]},
     "takeaway": "Yellow is the smallest block"}
dump("pie, 6 categories", p)
