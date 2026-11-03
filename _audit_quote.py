import math
from _bh_specs import SPECS
from server.layout import layout_slide, est_lines
from server.themes import get_builtin
from server.slide_schema import normalize

W, H = 13.333, 7.5
th = get_builtin('bauhaus')

def audit(spec, label):
    deck = [normalize(spec)]
    out = layout_slide(spec, th, 0, deck, 'Audit')
    print('=' * 78)
    print(label, '| bg', out['bg'])
    els = out['elements']
    for i, e in enumerate(els):
        line = e.get('line')
        lw = ('%.2f' % line['width']) if isinstance(line, dict) else '-'
        print('  [%d] %-8s x=%7.3f y=%7.3f w=%6.3f h=%6.3f rot=%-5s fill=%-8s lw=%s bleed=%s' % (
            i, e.get('t'), e['x'], e['y'], e['w'], e['h'], e.get('rot'), e.get('fill'), lw, e.get('bleed')))
        # slide-edge / rotated bounds
        x0, y0, x1, y1 = e['x'], e['y'], e['x'] + e['w'], e['y'] + e['h']
        if e.get('rot'):
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            r = math.hypot(e['w'], e['h']) / 2
            x0, y0, x1, y1 = cx - r, cy - r, cx + r, cy + r
            print('       ROT-AABB: x=[%.3f,%.3f] y=[%.3f,%.3f]' % (x0, x1, y0, y1))
        if not e.get('bleed'):
            if x0 < -0.001 or y0 < -0.001 or x1 > W + 0.001 or y1 > H + 0.001:
                print('       !! OFF-SLIDE (%.3f,%.3f)-(%.3f,%.3f)  slide is %.3f x %.3f' % (x0, y0, x1, y1, W, H))
        for p in e.get('paras', []):
            tw = e['w']
            lines = est_lines(p['text'], p['size'], tw, p.get('font', 'body'))
            need = lines * p['size'] / 72 * e.get('line', 1.15)
            flag = '  !! TEXT OVERFLOWS' if need > e['h'] * 1.08 else ''
            print('       para sz=%.1f font=%s bold=%s caps=%s spacing=%s lines=%d need=%.3f box=%.3f%s'
                  % (p['size'], p.get('font'), p.get('bold'), bool(p.get('caps')), p.get('spacing'),
                     lines, need, e['h'], flag))
            print('         %r' % p['text'][:90])
    # pairwise text-box overlap
    for a in range(len(els)):
        for b in range(a + 1, len(els)):
            ea, eb = els[a], els[b]
            if 'paras' not in ea or 'paras' not in eb: continue
            ox = min(ea['x']+ea['w'], eb['x']+eb['w']) - max(ea['x'], eb['x'])
            oy = min(ea['y']+ea['h'], eb['y']+eb['h']) - max(ea['y'], eb['y'])
            if ox > 0.01 and oy > 0.01:
                print('  !! TEXT-BOX OVERLAP [%d]x[%d] by %.3f x %.3f' % (a, b, ox, oy))
    return out

short = [s for s in SPECS if s['type'] == 'quote'][0]
audit(short, 'SAMPLE quote (short)')

audit({'type': 'quote',
       'quote': 'Design is not just what it looks like and feels like. Design is how it works.',
       'attribution': 'Steve Jobs'},
      'LONGER quote (72 chars)')

audit({'type': 'quote',
       'quote': ('The law of architecture states that whenever a building is erected, something '
                 'new must be built beside it, and whenever something new is built, something '
                 'old must be demolished, and whenever something is demolished, something '
                 'extraordinary must be built.'),
       'attribution': 'Michael Graves, on rebuilding the Bauhaus in a Chicago suburb'},
      'VERY LONG quote (5 lines at full width)')

audit({'type': 'quote', 'quote': 'Short.', 'attribution': 'A'}, 'TINY quote')
audit({'type': 'quote', 'quote': 'No attribution at all here.', 'attribution': ''}, 'NO attribution')
