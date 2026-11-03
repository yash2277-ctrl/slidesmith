"""Render each quote element alone and report its true ink bbox (pixels)."""
import io
from PIL import Image
from _bh_specs import SPECS
from server.layout import layout_slide
from server.themes import get_builtin
from server.slide_schema import normalize
from server.raster import Raster

PPI = 144
th = get_builtin('bauhaus')

def ink_bbox(els):
    lay = {"w": 13.333, "h": 7.5, "bg": {"type": "solid", "color": "#F0F0F0"}, "elements": els}
    img = Raster(lay, th, PPI).render()[0]
    im = Image.open(io.BytesIO(img)).convert("RGB")
    px = im.load()
    xs, ys = [], []
    for j in range(im.height):
        for i in range(im.width):
            r, g, b = px[i, j]
            if not (abs(r-240) < 6 and abs(g-240) < 6 and abs(b-240) < 6):
                xs.append(i); ys.append(j)
    if not xs:
        return None
    return (min(xs)/PPI, min(ys)/PPI, max(xs)/PPI, max(ys)/PPI)

cases = {
 'sample': {'type':'quote','quote':'Architecture begins where two bricks are put together well.','attribution':'Ludwig Mies van der Rohe'},
 'verylong': {'type':'quote','quote':'The law of architecture states that whenever a building is erected, something new must be built beside it, and whenever something new is built, something old must be demolished, and whenever something is demolished, something extraordinary must be built.','attribution':'Michael Graves'},
}
for name, s in cases.items():
    out = layout_slide(s, th, 0, [normalize(s)], 'Audit')
    print('==', name)
    boxes = []
    for k, e in enumerate(out['elements']):
        bb = ink_bbox([e])
        boxes.append((k, e, bb))
        if bb:
            print('  [%d] %-8s ink bbox x=[%.3f,%.3f] y=[%.3f,%.3f]  (declared x=[%.3f,%.3f] y=[%.3f,%.3f])'
                  % (k, e['t'], bb[0], bb[2], bb[1], bb[3], e['x'], e['x']+e['w'], e['y'], e['y']+e['h']))
    for a in range(len(boxes)):
        for b in range(a+1, len(boxes)):
            ka, ea, ba = boxes[a]; kb, eb, bb = boxes[b]
            if not ba or not bb or 'paras' not in ea or 'paras' not in eb: continue
            ox = min(ba[2], bb[2]) - max(ba[0], bb[0])
            oy = min(ba[3], bb[3]) - max(ba[1], bb[1])
            if ox > 0.005 and oy > 0.005:
                print('  !! INK COLLISION [%d]%r x [%d]%r overlap %.3f x %.3f in' % (ka, ea['paras'][0]['text'][:14], kb, eb['paras'][0]['text'][:14], ox, oy))
